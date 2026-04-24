import argparse
import subprocess
import sys
import os
from typing import Optional, Tuple, Literal

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
        help="触发 GitHub Actions 的目标分支（调试新功能时使用）"
    )
    debug_group.add_argument(
        "-v", "--verbose", 
        action="store_true", 
        help="启用详细调试日志，显示底层指令输出"
    )

    # 3. 下载与存储配置
    parser.add_argument(
        "-m", "--mode", 
        choices=["audio", "video"], 
        default="audio", 
        help="下载模式：仅音频或视频"
    )
    parser.add_argument(
        "-s", "--storage", 
        choices=["aliyun", "gofile"], 
        default="alipan", 
        help="目标存储平台"
    )

    # 4. 阿里云盘专用参数
    ali_group = parser.add_argument_group("阿里云盘配置")
    ali_group.add_argument(
        "--token", 
        type=str, 
        help="阿里云盘 Refresh Token (存储为 alipan 时必填)"
    )
    ali_group.add_argument(
        "--path", 
        type=str, 
        default="/", 
        help="阿里云盘中的目标存储目录"
    )

    args = parser.parse_args()

    # 业务逻辑约束校验
    if args.storage == "aliyun" and not args.token:
        parser.error("错误：存储后端为 'aliyun' 时，必须提供 --token 参数。")

    return args

def trigger_github_action(args: argparse.Namespace) -> None:
    """
    通过 GitHub CLI 触发远程 Workflow。
    """
    # 检查并同步 Cookies
    if os.path.exists(COOKIE_FILE):
        if args.verbose:
            print(f"[*] 正在同步 {COOKIE_FILE} 到 GitHub Secrets...")
        run_command(f"gh secret set YOUTUBE_COOKIES < {COOKIE_FILE}")

    # 构建 gh workflow run 指令
    # --ref 指定分支
    cmd: str = (
        f"gh workflow run {WORKFLOW_FILE} "
        f"--ref {args.branch} "
        f"-f video_url=\"{args.url}\" "
        f"-f download_type=\"{args.mode}\" "
        f"-f storage_provider=\"{args.storage}\" "
    )

    if args.storage == "alipan":
        cmd += f"-f ali_token=\"{args.token}\" -f ali_path=\"{args.path}\""

    if args.verbose:
        print(f"[*] 正在触发分支 [{args.branch}] 上的 Actions...")

    stdout, code = run_command(cmd, args.verbose)

    if code == 0:
        print(f"✅ 成功：已在分支 '{args.branch}' 上启动下载任务。")
    else:
        print(f"❌ 失败：无法触发 Actions。请检查分支名是否正确或 gh 是否登录。")
        sys.exit(1)

def main() -> None:
    """程序入口"""
    args = setup_args()
    trigger_github_action(args)

if __name__ == "__main__":
    main()