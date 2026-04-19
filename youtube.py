import json
import os
import re
import sys
import subprocess
import time
from pathlib import Path
import argparse

from aliyundrive_auth import AliyunDriveAuth
from aliyundrive_client import AliyunDriveClient, AliyunDriveError
from gofile_client import GofileClient, GofileError

# --- 配置区 ---
WORKFLOW_ID_OR_NAME = "YouTube-Downloader"
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
    # 每次都交互式输入 refresh token，不保存
    token = input("请输入阿里云盘 refresh token: ").strip()
    if not token:
        raise ValueError("Refresh token 不能为空")
    return token


def parse_aliyun_upload_result(logs: str):
    file_id_match = re.search(r"ALIYUNDRIVE_FILE_ID:\s*([A-Za-z0-9_-]+)", logs)
    file_name_match = re.search(r"ALIYUNDRIVE_FILE_NAME:\s*(.+)", logs)
    if not file_id_match:
        return None, None
    return file_id_match.group(1), file_name_match.group(1).strip() if file_name_match else "downloaded_file"


def parse_gofile_upload_result(logs: str):
    download_page_match = re.search(r"GOFILE_DOWNLOAD_PAGE:\s*(.+)", logs)
    code_match = re.search(r"GOFILE_CODE:\s*(.+)", logs)
    file_name_match = re.search(r"GOFILE_FILE_NAME:\s*(.+)", logs)
    if not download_page_match:
        return None, None, None
    return download_page_match.group(1).strip(), code_match.group(1).strip() if code_match else None, file_name_match.group(1).strip() if file_name_match else "downloaded_file"


def delete_github_run(run_id):
    print(f"🧹 正在彻底删除 GitHub 运行记录 (ID: {run_id})...")
    subprocess.run(["gh", "run", "delete", run_id, "--yes"], check=False)
    print("✅ GitHub 记录已抹除。")


def get_video_stealth(video_url, download_type='audio', branch='main', upload_to='ali'):
    refresh_token = ensure_refresh_token()
    try:
        set_github_secret("ALIYUNDRIVE_REFRESH_TOKEN", refresh_token)
    except Exception as exc:
        print(f"⚠️ 无法设置 GitHub Secret: {exc}")
        print("请确保当前仓库可使用 gh secret set 命令，并手动创建 ALIYUNDRIVE_REFRESH_TOKEN。")
        return

    if os.path.exists(COOKIE_FILE):
        run_command(f"gh secret set YOUTUBE_COOKIES < {COOKIE_FILE}", check=True)

    print(f"📡 调度任务: {video_url} ({download_type}) 上传到 {upload_to} 在分支 {branch}")
    run_command(
        f"gh workflow run {WORKFLOW_ID_OR_NAME} --ref {branch} -f video_url=\"{video_url}\" -f download_type=\"{download_type}\" -f upload_to=\"{upload_to}\"",
        check=True,
    )
    time.sleep(5)

    run_id = run_command(
        f"gh run list --workflow={WORKFLOW_ID_OR_NAME} --limit 1 --json databaseId -q '.[0].databaseId'"
    )
    if not run_id:
        print("❌ 无法获取任务 ID")
        return

    print(f"🚀 任务启动 (ID: {run_id})，等待云端处理...")
    subprocess.run(["gh", "run", "watch", run_id, "--exit-status"], check=False)

    logs = run_command(f"gh run view {run_id} --log")
    if not logs:
        print("❌ 无法获取运行日志，请检查 gh CLI 或 workflow 权限。")
        return

    if upload_to == 'ali':
        # 阿里云盘逻辑
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
    else:
        # Gofile逻辑
        download_page, code, file_name = parse_gofile_upload_result(logs)
        if not download_page:
            print("❌ 无法从工作流日志中提取 Gofile 信息，请检查工作流输出。")
            return

        print(f"✅ Gofile 上传成功")
        print(f"📥 下载页面: {download_page}")
        if code:
            print(f"🔑 代码: {code}")
        print(f"📄 文件名: {file_name}")

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


def download_video_local(video_url, download_type='audio'):
    """本地下载视频"""
    output_dir = Path.home() / "Downloads"
    output_dir.mkdir(parents=True, exist_ok=True)

    if download_type == 'audio':
        command = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "192K",
            "-o", str(output_dir / "%(title)s.%(ext)s"),
            video_url,
        ]
    else:
        command = [
            "yt-dlp",
            "-o", str(output_dir / "%(title)s.%(ext)s"),
            video_url,
        ]

    if os.path.exists(COOKIE_FILE):
        command.extend(["--cookies", COOKIE_FILE])

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"下载失败: {result.stderr}")

    lines = result.stdout.split('\n')
    for line in lines:
        if '[download] Destination:' in line:
            dest = line.split('[download] Destination:')[1].strip()
            return Path(dest)

    files = list(output_dir.glob("*"))
    if files:
        return max(files, key=lambda f: f.stat().st_mtime)
    raise RuntimeError("无法确定下载的文件")


def upload_to_gofile(local_path):
    """上传到Gofile"""
    client = GofileClient()
    info = client.upload_file(str(local_path))
    print(f"✅ Gofile 上传成功")
    print(f"下载页面: {info['downloadPage']}")
    print(f"代码: {info['code']}")
    return info


def parse_args(argv):
    parser = argparse.ArgumentParser(description="下载YouTube视频并上传")
    parser.add_argument("url", help="YouTube视频URL")
    parser.add_argument("--type", choices=['audio', 'video'], default='audio', help="下载类型")
    parser.add_argument("--upload-to", choices=['ali', 'gofile'], default='ali', help="上传目的地")
    parser.add_argument("--branch", default='main', help="GitHub分支")
    return parser.parse_args(argv[1:])


if __name__ == "__main__":
    args = parse_args(sys.argv)
    if args.upload_to == 'ali':
        get_video_stealth(args.url, args.type, args.branch, args.upload_to)
    else:
        try:
            local_path = download_video_local(args.url, args.type)
            print(f"✅ 本地下载完成: {local_path}")
            upload_to_gofile(local_path)
        except Exception as exc:
            print(f"❌ 处理失败: {exc}")
            sys.exit(1)
