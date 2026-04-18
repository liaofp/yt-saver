import subprocess
import time
import re
import sys
import os
import urllib.request

# --- 配置区 ---
WORKFLOW_ID_OR_NAME = "YouTube-Downloader"  # 你的 YAML 文件名
COOKIE_FILE = "cookies.txt"
# --------------

def run_command(command):
    """执行系统命令并返回结果"""
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None

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
    run_command(f"gh workflow run {WORKFLOW_ID_OR_NAME} -f video_url=\"{video_url}\" -f download_type=\"{download_type}\"")
    time.sleep(5) # 等待 API 更新
    
    # 获取最新的 Run ID
    run_id = run_command(f"gh run list --workflow={WORKFLOW_ID_OR_NAME} --limit 1 --json databaseId -q '.[0].databaseId'")
    
    if not run_id:
        print("❌ 无法获取任务 ID")
        return

    # 3. 监控进度
    print(f"🚀 任务启动 (ID: {run_id})，等待云端处理...")
    subprocess.run(f"gh run watch {run_id}", shell=True)

    # 4. 提取链接
    logs = run_command(f"gh run view {run_id} --log")
    links = re.findall(r'https://gofile\.io/d/[a-zA-Z0-9]+', logs)
    
    if links:
        gofile_link = links[-1]
        print(f"✅ 获取链接成功: {gofile_link}")
        
        # 5. 下载到本地
        local_file = "audio.opus" if download_type == "audio" else "video_720p.mp4"
        download_file(gofile_link, local_file)
        
        # 6. 抹除痕迹
        # 当视频成功“处理”后（此处逻辑为获取链接并尝试开启下载后），删除 GitHub 日志
        delete_github_run(run_id)
    else:
        print("❌ 提取链接失败，请手动检查日志。")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 youtube.py <URL> [video|audio]")
    else:
        download_type = "audio"
        if len(sys.argv) >= 3 and sys.argv[2].lower() == "video":
            download_type = "video"
        get_video_stealth(sys.argv[1], download_type)

