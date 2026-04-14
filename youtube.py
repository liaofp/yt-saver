import subprocess
import time
import re
import sys
import os

# --- 配置区 ---
WORKFLOW_FILE = "YouTube-Downloader"  # 你的 YAML 文件名
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
    """将视频从 GoFile 下载到本地"""
    print(f"📥 正在从 GoFile 下载视频到本地: {filename}...")
    # 注意：GoFile 的 downloadPage 是一个页面，直接下载需要解析出直链
    # 这里我们提示用户手动点击或使用更复杂的爬虫，因为 GoFile 有下载节点保护
    print(f"🔗 请通过此链接下载: {url}")
    # 专家建议：由于 GoFile 限制，直接流式下载可能被拦截，建议手动点击或调用浏览器
    if sys.platform == 'darwin':
        os.system(f"open {url}")

def get_video_stealth(video_url):
    # 1. 同步 Cookies
    if os.path.exists(COOKIE_FILE):
        run_command(f"gh secret set YOUTUBE_COOKIES < {COOKIE_FILE}")

    # 2. 触发并获取 Run ID
    print(f"📡 调度任务: {video_url}")
    run_command(f"gh workflow run {WORKFLOW_FILE} -f video_url=\"{video_url}\"")
    time.sleep(5) # 等待 API 更新
    
    # 获取最新的 Run ID
    run_id = run_command(f"gh run list --workflow={WORKFLOW_FILE} --limit 1 --json databaseId -q '.[0].databaseId'")
    
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
        download_file(gofile_link, "video_720p.mp4")
        
        # 6. 抹除痕迹
        # 当视频成功“处理”后（此处逻辑为获取链接并尝试开启下载后），删除 GitHub 日志
        delete_github_run(run_id)
    else:
        print("❌ 提取链接失败，请手动检查日志。")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 youtube.py <URL>")
    else:
        get_video_stealth(sys.argv[1])