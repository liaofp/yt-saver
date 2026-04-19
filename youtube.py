import subprocess
import time
import re
import sys
import os
import urllib.request

# --- 配置区 ---
WORKFLOW_ID_OR_NAME = "YouTube-Downloader"  # 你的 YAML 文件名
WORKFLOW_FILE = ".github/workflows/download.yml"
COOKIE_FILE = "cookies.txt"
DEBUG = False
# --------------

def log_info(message):
    print(message)


def log_debug(message):
    if DEBUG:
        print(f"[DEBUG] {message}")


def run_command(command):
    """执行系统命令并返回 stdout 和 exit code"""
    log_debug(f"命令: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    stdout = result.stdout.strip() if result.stdout else ""
    stderr = result.stderr.strip() if result.stderr else ""
    if DEBUG:
        if stdout:
            print(f"[DEBUG stdout] {stdout}")
        if stderr:
            print(f"[DEBUG stderr] {stderr}")
    if result.returncode != 0:
        log_info(f"⚠️ 命令失败: {command} (exit {result.returncode})")
        if stderr:
            log_info(stderr)
    return stdout, result.returncode


def wait_for_workflow_run_id(workflow, retries=12, delay=5):
    """轮询等待 GitHub Actions 运行记录创建并返回 run_id"""
    for attempt in range(1, retries + 1):
        run_id, returncode = run_command(
            f"gh run list --workflow='{workflow}' --limit 1 --json databaseId -q '.[0].databaseId'"
        )
        if returncode == 0 and run_id:
            return run_id
        print(f"⏳ 等待 GitHub Actions 运行记录创建... {attempt}/{retries}")
        time.sleep(delay)
    return None

def delete_github_run(run_id):
    """彻底删除 GitHub 上的运行记录和日志"""
    print(f"🧹 正在彻底删除 GitHub 运行记录 (ID: {run_id})...")
    subprocess.run(f"gh run delete {run_id}", shell=True)
    print("✅ GitHub 记录已抹除。")

def download_file(url, filename):
    """自动解析 GoFile 下载地址并把文件存放到 ~/Downloads。"""
    print(f"📥 尝试解析 GoFile 直链并下载到: {filename}...")
    download_dir = os.path.expanduser("~/Downloads")
    os.makedirs(download_dir, exist_ok=True)
    local_path = os.path.join(download_dir, filename)

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            html = response.read().decode('utf-8', errors='ignore')
    except Exception as exc:
        print(f"⚠️ 无法访问 GoFile 页面: {exc}")
        print(f"🔗 请手动访问下载页面: {url}")
        return

    patterns = [
        r'href="(https://download\.gofile\.io/download[^\"]+)"',
        r'href="(https://[a-z0-9\-]+\.gofile\.io/download[^\"]+)"',
        r'window\.location\.href\s*=\s*"([^"]+)"',
        r'document\.location\.href\s*=\s*"([^"]+)"',
        r'"(https://download\.gofile\.io/download[^"]+)"',
    ]

    direct_url = None
    for pat in patterns:
        match = re.search(pat, html)
        if match:
            direct_url = match.group(1)
            break

    if not direct_url:
        print("⚠️ 未能解析 GoFile 直链，改为输出原始页面地址。")
        print(f"🔗 请手动访问下载页面: {url}")
        return

    print(f"🔗 解析到直链: {direct_url}")
    request = urllib.request.Request(direct_url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            with open(local_path, 'wb') as out_file:
                out_file.write(response.read())
        print(f"✅ 已保存到: {local_path}")
    except Exception as exc:
        print(f"⚠️ 下载文件失败: {exc}")
        print(f"🔗 请手动访问下载页面: {url}")

def get_video_stealth(video_url, download_type='video'):
    # 1. 同步 Cookies
    if os.path.exists(COOKIE_FILE):
        run_command(f"gh secret set YOUTUBE_COOKIES < {COOKIE_FILE}")

    # 2. 触发并获取 Run ID
    print(f"📡 调度任务: {video_url} ({download_type})")
    workflow_output, workflow_code = run_command(
        f"gh workflow run {WORKFLOW_FILE} -f video_url=\"{video_url}\" -f download_type=\"{download_type}\""
    )
    if workflow_code != 0:
        print("❌ 触发 workflow 失败，请检查 GitHub CLI、权限和仓库上下文。")
        return

    if workflow_output:
        print(workflow_output)
    
    # 获取最新的 Run ID，增加重试等待，避免刚 dispatch 时 list 还未同步
    run_id = wait_for_workflow_run_id(WORKFLOW_FILE)
    
    if not run_id:
        log_info("❌ 无法获取任务 ID，请确认 workflow 是否已成功调度。")
        log_info(f"🔎 你可以运行: gh run list --workflow='{WORKFLOW_FILE}' --limit 5")
        return

    # 3. 监控进度
    log_info(f"🚀 任务启动 (ID: {run_id})，等待云端处理...")
    watch_result = subprocess.run(
        f"gh run watch {run_id} --exit-status",
        shell=True,
        text=True,
    )
    if watch_result.returncode != 0:
        log_info(f"❌ gh run watch 失败，运行 {run_id} 未成功完成。exit={watch_result.returncode}")
        log_info("请检查 GitHub Actions 运行日志以了解失败原因。")
        return
    log_info("✅ 远程运行已完成且状态成功。")

    # 4. 提取链接
    logs, log_code = run_command(f"gh run view {run_id} --log")
    if log_code != 0 or not logs:
        log_info("❌ 无法获取运行日志，请检查 gh CLI 或 workflow 权限。")
        return
    links = re.findall(r'https://gofile\.io/d/[a-zA-Z0-9]+', logs)
    
    if links:
        gofile_link = links[-1]
        log_info(f"✅ 获取链接成功: {gofile_link}")
        
        # 5. 下载到本地
        local_file = "audio.opus" if download_type == "audio" else "video_720p.mp4"
        download_file(gofile_link, local_file)
        
        # 6. 抹除痕迹
        # 当视频成功“处理”后（此处逻辑为获取链接并尝试开启下载后），删除 GitHub 日志
        delete_github_run(run_id)
    else:
        print("❌ 提取链接失败，请手动检查日志。")

def parse_args(argv):
    global DEBUG
    args = [arg for arg in argv[1:] if arg not in ("--verbose", "-v")]
    DEBUG = "--verbose" in argv or "-v" in argv

    if len(args) < 1:
        print("Usage: python3 youtube.py <URL> [video|audio] [--verbose]")
        sys.exit(1)

    video_url = args[0]
    download_type = "audio"
    if len(args) >= 2 and args[1].lower() == "video":
        download_type = "video"
    return video_url, download_type


if __name__ == "__main__":
    video_url, download_type = parse_args(sys.argv)
    get_video_stealth(video_url, download_type)

