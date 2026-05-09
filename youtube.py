import argparse
import subprocess
import sys
import os
import json
import time  # 导入 time 用于延时重试
from typing import Optional, Tuple, Literal
from providers.aliyun import AliyunProvider
from providers.gofile import GofileProvider
from providers.onedrive import OnedriveProvider
import configparser

# --- 静态配置 ---
WORKFLOW_FILE: str = ".github/workflows/download.yml"
COOKIE_FILE: str = "cookies.txt"


def run_command(command: str, verbose: bool = False) -> Tuple[str, int]:
    """
    执行系统命令并返回标准输出和退出码。
    """
    if verbose:
        print(f"[DEBUG] Executing: {command}")

    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    stdout: str = result.stdout.strip() if result.stdout else ""
    stderr: str = result.stderr.strip() if result.stderr else ""

    if result.returncode != 0 and verbose:
        print(f"[ERROR] {stderr}", file=sys.stderr)

    return stdout, result.returncode


def monitor_workflow(branch: str, storage_type: str, token: str, verbose: bool = False) -> None:
    print("[*] 正在等待 GitHub 任务启动...")
    run_id = None
    for i in range(5):
        time.sleep(3)
        get_run_cmd = f"gh run list --workflow {os.path.basename(WORKFLOW_FILE)} --branch {branch} --limit 1 --json databaseId"
        stdout, _ = run_command(get_run_cmd, verbose)
        try:
            runs = json.loads(stdout)
            if runs:
                run_id = runs[0]['databaseId']
                break
        except:
            continue

    if not run_id:
        print("❌ 无法追踪任务状态。")
        return

    # 1. 实时回显 GitHub 云端进度
    subprocess.run(f"gh run watch {run_id}", shell=True)

    # 2. 任务完成后，获取云端日志
    print("\n[*] 任务结束，正在回传文件...")
    log_stdout, _ = run_command(f"gh run view {run_id} --log", verbose)

    # 3. 执行本地回传与云端删除
    config = configparser.ConfigParser()
    config.add_section('Storage')  # 默认为 ~/Downloads [cite: 34]

    if storage_type == "onedrive":
        effective_token = token or os.environ.get("ONEDRIVE_TOKEN")
        if not effective_token:
            print("\n❌ 错误: 本地回传失败。OneDrive 需要 Token 来下载文件。")
            print("请使用 -t 参数传入 Token JSON，或设置环境变量 ONEDRIVE_TOKEN。")
            return

        OnedriveProvider(config).handle_result(log_stdout, effective_token)
    elif storage_type == "aliyun":
        provider = AliyunProvider(config)
        provider.handle_result(log_stdout, token)  # 此处会触发下载并调用 ali.delete_file [cite: 37]
    elif storage_type == "gofile":
        GofileProvider(config).handle_result(log_stdout)

    print(f"[*] 正在清除 GitHub Actions 页面显示内容 (ID: {run_id})...")
    run_command(f"gh run delete {run_id}")
    print("✅ 运行记录已从 GitHub 项目页面清除。")


def setup_args() -> argparse.Namespace:
    """
    配置并解析命令行参数。
    """
    parser = argparse.ArgumentParser(
        description="YouTube 自动化下载转存工具 (GitHub Actions 驱动)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # 1. 基础定位参数
    parser.add_argument("url", type=str, help="YouTube 视频或音频的完整 URL")

    # 2. 调试与分支控制
    debug_group = parser.add_argument_group("调试与分支配置")
    debug_group.add_argument(
        "-b", "--branch",
        type=str,
        default="main",
        help="触发 GitHub Actions 的目标分支"
    )
    debug_group.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="启用详细调试日志"
    )
    # debug_group.add_argument(
    #     "-w", "--watch",
    #     action="store_true",
    #     help="启动后阻塞并实时监控工作流进度"
    # )

    # 3. 下载与存储配置
    parser.add_argument(
        "-m", "--mode",
        choices=["audio", "video"],
        default="audio",
        help="下载模式"
    )
    parser.add_argument(
        "-s", "--storage",
        choices=["onedrive", "aliyun", "gofile"],
        default="onedrive",
        help="目标存储平台"
    )

    # 4. 文件名自定义
    parser.add_argument(
        "-f", "--filename",
        type=str,
        default=None,
        help="自定义输出文件名（不含扩展名时由 yt-dlp 自动追加）"
    )

    # 5. 阿里云盘专用参数
    ali_group = parser.add_argument_group("阿里云盘配置")
    ali_group.add_argument("--token", type=str, help="阿里云盘 Refresh Token")
    ali_group.add_argument("--path", type=str, default="/", help="保存目录")

    args = parser.parse_args()

    if args.storage == "aliyun" and not args.token:
        parser.error("错误：存储后端为 'aliyun' 时，必须提供 --token 参数。")

    return args


def trigger_github_action(args: argparse.Namespace) -> None:
    """
    通过 GitHub CLI 触发远程 Workflow。
    """
    if os.path.exists(COOKIE_FILE):
        if args.verbose:
            print(f"[*] 正在同步 {COOKIE_FILE} 到 GitHub Secrets...")
        run_command(f"gh secret set YOUTUBE_COOKIES < {COOKIE_FILE}")

    cmd: str = (
        f"gh workflow run {WORKFLOW_FILE} "
        f"--ref {args.branch} "
        f"-f video_url=\"{args.url}\" "
        f"-f download_type=\"{args.mode}\" "
        f"-f storage_provider=\"{args.storage}\" "
    )

    # 透传自定义文件名（如果设置）
    if getattr(args, 'filename', None):
        cmd += f"-f output_filename=\"{args.filename}\" "

    if args.storage == "aliyun":
        cmd += f"-f provider_token=\"{args.token}\" -f ali_path=\"{args.path}\""

    stdout, code = run_command(cmd, args.verbose)

    if code == 0:
        print(f"🚀 成功：已在分支 '{args.branch}' 上触发任务。")
        # 强制执行监控与回传逻辑，不再检查 args.watch
        monitor_workflow(args.branch, args.storage, args.token, args.verbose)
    else:
        print(f"❌ 失败：无法触发 Actions。")
        sys.exit(1)


def main() -> None:
    args = setup_args()
    trigger_github_action(args)


if __name__ == "__main__":
    main()
