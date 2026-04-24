import argparse
import subprocess
import sys
import os
import time  # 导入 time 用于延时重试
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

def monitor_workflow(branch: str, verbose: bool = False) -> None:
    """
    监控最近启动的 Workflow 运行状态。
    """
    print("[*] 正在等待 GitHub Actions 分配运行 ID...")
    
    # 给 GitHub 一点响应时间，确保新触发的任务出现在列表中
    time.sleep(3)
    
    # 获取最新的 Run ID
    # --limit 1 获取最近的一次，--json id 只要 ID
    get_run_cmd = f"gh run list --workflow {os.path.basename(WORKFLOW_FILE)} --branch {branch} --limit 1 --json databaseId --jq '.[0].databaseId'"
    
    run_id, code = run_command(get_run_cmd, verbose)
    
    if code != 0 or not run_id:
        print("⚠️ 无法获取运行 ID，可能由于网络延迟。请手动在网页端查看。")
        return

    print(f"[*] 监控任务运行中 (ID: {run_id})...")
    
    # 使用 gh run watch 实时监控
    # --exit-status 会根据任务最终成败返回对应的退出码
    watch_cmd = f"gh run watch {run_id}"
    
    # 使用 subprocess.run 而非自定义 run_command，以便让用户看到 gh 自带的实时刷新界面
    result = subprocess.run(watch_cmd, shell=True)
    
    if result.returncode == 0:
        print(f"✅ 任务 (ID: {run_id}) 执行成功！")
    else:
        print(f"❌ 任务 (ID: {run_id}) 执行失败或已取消。")

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
    debug_group.add_argument(
        "-w", "--watch",
        action="store_true",
        help="启动后阻塞并实时监控工作流进度"
    )

    # 3. 下载与存储配置
    parser.add_argument(
        "-m", "--mode", 
        choices=["audio", "video"], 
        default="audio", 
        help="下载模式"
    )
    parser.add_argument(
        "-s", "--storage", 
        choices=["aliyun", "gofile"], 
        default="aliyun", 
        help="目标存储平台"
    )

    # 4. 阿里云盘专用参数
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

    if args.storage == "aliyun":
        cmd += f"-f provider_token=\"{args.token}\" -f ali_path=\"{args.path}\""

    stdout, code = run_command(cmd, args.verbose)

    if code == 0:
        print(f"🚀 成功：已在分支 '{args.branch}' 上触发任务。")
        # 如果设置了监控标志，执行监控逻辑
        if args.watch:
            monitor_workflow(args.branch, args.verbose)
    else:
        print(f"❌ 失败：无法触发 Actions。")
        sys.exit(1)

def main() -> None:
    args = setup_args()
    trigger_github_action(args)

if __name__ == "__main__":
    main()