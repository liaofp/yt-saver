import json
import os
import re
import sys
import subprocess
import time
from pathlib import Path

from aliyundrive_auth import AliyunDriveAuth
from aliyundrive_client import AliyunDriveClient, AliyunDriveError

# --- 配置区 ---
WORKFLOW_FILE = "YouTube-Downloader"
COOKIE_FILE = "cookies.txt"
CONFIG_DIR = Path.home() / ".config" / "yt-saver"
CONFIG_FILE = CONFIG_DIR / "aliyundrive.json"
# --------------


def run_command(command, check=False):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"命令失败: {command}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout.strip() if result.returncode == 0 else None


def set_github_secret(name, value):
    subprocess.run(["gh", "secret", "set", name, "--body", value], check=True)


def load_refresh_token() -> str:
    if not CONFIG_FILE.exists():
        return ""
    with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("refresh_token", "")


def save_refresh_token(refresh_token: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump({"refresh_token": refresh_token}, fh)


def ensure_refresh_token() -> str:
    token = load_refresh_token()
    if token:
        return token

    auth = AliyunDriveAuth(CONFIG_FILE)
    token = auth.obtain_refresh_token()
    save_refresh_token(token)
    return token


def parse_aliyun_upload_result(logs: str):
    file_id_match = re.search(r"ALIYUNDRIVE_FILE_ID:\s*([A-Za-z0-9_-]+)", logs)
    file_name_match = re.search(r"ALIYUNDRIVE_FILE_NAME:\s*(.+)", logs)
    if not file_id_match:
        return None, None
    return file_id_match.group(1), file_name_match.group(1).strip() if file_name_match else "downloaded_file"


def delete_github_run(run_id):
    print(f"🧹 正在彻底删除 GitHub 运行记录 (ID: {run_id})...")
    subprocess.run(["gh", "run", "delete", run_id, "--yes"], check=False)
    print("✅ GitHub 记录已抹除。")


def get_video_stealth(video_url, download_type='audio'):
    refresh_token = ensure_refresh_token()
    try:
        set_github_secret("ALIYUNDRIVE_REFRESH_TOKEN", refresh_token)
    except Exception as exc:
        print(f"⚠️ 无法设置 GitHub Secret: {exc}")
        print("请确保当前仓库可使用 gh secret set 命令，并手动创建 ALIYUNDRIVE_REFRESH_TOKEN。")

    if os.path.exists(COOKIE_FILE):
        run_command(f"gh secret set YOUTUBE_COOKIES < {COOKIE_FILE}")

    print(f"📡 调度任务: {video_url} ({download_type})")
    run_command(
        f"gh workflow run {WORKFLOW_FILE} -f video_url=\"{video_url}\" -f download_type=\"{download_type}\"",
        check=True,
    )
    time.sleep(5)

    run_id = run_command(
        f"gh run list --workflow={WORKFLOW_FILE} --limit 1 --json databaseId -q '.[0].databaseId'"
    )
    if not run_id:
        print("❌ 无法获取任务 ID")
        return

    print(f"🚀 任务启动 (ID: {run_id})，等待云端处理...")
    subprocess.run(["gh", "run", "watch", run_id], check=False)

    logs = run_command(f"gh run view {run_id} --log")
    file_id, file_name = parse_aliyun_upload_result(logs)
    if not file_id:
        print("❌ 无法从工作流日志中提取 Aliyun Drive 文件 ID，请检查工作流输出。")
        return

    print(f"✅ Aliyun Drive 上传成功，文件 ID: {file_id}，文件名: {file_name}")

    try:
        local_path = download_aliyun_file(file_id, file_name, refresh_token)
        print(f"✅ 已下载到本地: {local_path}")
    except Exception as exc:
        print(f"❌ 下载 Aliyun Drive 文件失败: {exc}")
        return

    delete_github_run(run_id)


def download_aliyun_file(file_id: str, file_name: str, refresh_token: str) -> str:
    client = AliyunDriveClient(refresh_token)
    local_dir = Path.home() / "Downloads"
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / file_name
    download_url = client.get_download_url(file_id)
    client.download_url(download_url, str(local_path))
    client.delete_file(file_id)
    return str(local_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 youtube.py <URL> [video|audio]")
    else:
        download_type = "audio"
        if len(sys.argv) >= 3 and sys.argv[2].lower() == "video":
            download_type = "video"
        get_video_stealth(sys.argv[1], download_type)

