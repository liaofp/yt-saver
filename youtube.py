import argparse
import subprocess
import sys
import os
import json
import time  # 导入 time 用于延时重试
from typing import Optional, Tuple, Literal
from providers.aliyun import AliyunProvider
from providers.gofile import GofileProvider
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
    """
    强制监控：等待任务完成并执行本地回传/清理 [cite: 2, 4, 5]
    """
    print("[*] 正在同步 GitHub Actions 状态...")
    
    run_id = None
    for i in range(5):
        time.sleep(3)
        get_run_cmd = f"gh run list --workflow {os.path.basename(WORKFLOW_FILE)} --branch {branch} --limit 1 --json databaseId,status" [cite: 3]
        stdout, code = run_command(get_run_cmd, verbose)
        try:
            runs = json.loads(stdout)
            if runs:
                run_id = runs[0]['databaseId']
                break
        except:
            continue
            
    if not run_id:
        print("⚠️ 无法获取运行 ID。")
        return

    # 阻塞当前进程直至 GitHub 任务完成 
    subprocess.run(f"gh run watch {run_id}", shell=True)

    # 核心步骤：抓取日志以获取上传后的文件标识 [cite: 4, 38]
    print("\n[*] 任务完成，正在分析云端数据以执行回传...")
    log_stdout, _ = run_command(f"gh run view {run_id} --log", verbose)
    
    # 虚拟配置对象，用于传递下载路径 [cite: 34, 35]
    config = configparser.ConfigParser()
    config.add_section('Storage')
    
    # 执行具体的 Provider 回传逻辑 [cite: 36, 37]
    if storage_type == "aliyun":
        provider = AliyunProvider(config)
        provider.handle_result(log_stdout, token) # 内部会调用 ali.download_file 和 ali.delete_file 
    elif storage_type == "gofile":
        provider = GofileProvider(config)
        provider.handle_result(log_stdout)

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