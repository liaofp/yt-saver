import argparse
import subprocess
import sys
import os
import json
import time
import re
from typing import Optional, Tuple
from providers.aliyun import AliyunProvider
from providers.gofile import GofileProvider
from providers.onedrive import OnedriveProvider
import configparser

# --- Static Configuration ---
WORKFLOW_FILE: str = ".github/workflows/download.yml"
COOKIE_FILE: str = "cookies.txt"


def run_command(command: str, verbose: bool = False) -> Tuple[str, int]:
    """
    Execute a system command and return stdout and exit code.
    """
    if verbose:
        print(f"[DEBUG] Executing: {command}")

    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    stdout: str = result.stdout.strip() if result.stdout else ""
    stderr: str = result.stderr.strip() if result.stderr else ""

    if result.returncode != 0 and verbose:
        print(f"[ERROR] {stderr}", file=sys.stderr)

    return stdout, result.returncode


def _parse_result_block(logs: str) -> Optional[dict]:
    """Extract the standardized ---RESULT_START---...---RESULT_END--- block."""
    match = re.search(r"---RESULT_START---(.*?)---RESULT_END---", logs, re.S)
    if not match:
        return None
    data = match.group(1)
    result = {}
    for line in data.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def monitor_workflow(
    branch: str,
    storage_type: str,
    token: Optional[str],
    verbose: bool = False
) -> None:
    print("[*] Waiting for GitHub workflow to start...")
    run_id: Optional[int] = None
    for _ in range(5):
        time.sleep(3)
        get_run_cmd: str = (
            f"gh run list --workflow {os.path.basename(WORKFLOW_FILE)} "
            f"--branch {branch} --limit 1 --json databaseId"
        )
        stdout, _ = run_command(get_run_cmd, verbose)
        try:
            runs = json.loads(stdout)
            if runs:
                run_id = runs[0]["databaseId"]
                break
        except Exception:
            continue

    if not run_id:
        print("❌ Unable to track workflow status.")
        return

    # 1. Live echo of GitHub cloud progress
    subprocess.run(f"gh run watch {run_id}", shell=True)

    # 2. After completion, fetch cloud logs
    print("\n[*] Workflow finished, retrieving file...")
    log_stdout, _ = run_command(f"gh run view {run_id} --log", verbose)

    # 3. Parse result block first to detect failure
    result_block = _parse_result_block(log_stdout)
    if result_block and result_block.get("STATUS") == "FAILED":
        reason = result_block.get("REASON", "Unknown failure reason.")
        error_log = result_block.get("ERROR_LOG", "")
        print("\n❌ GitHub Actions workflow failed to download from YouTube.")
        print(f"   Reason: {reason}")
        if error_log:
            print("\n--- yt-dlp Error Log (last lines) ---")
            print(error_log)
            print("--- End of error log ---")
        print(f"\n[*] Cleaning up GitHub Actions run page (ID: {run_id})...")
        run_command(f"gh run delete {run_id}")
        print("✅ Run record cleared from GitHub project page.")
        return

    # 4. Perform local retrieval and cloud cleanup
    config = configparser.ConfigParser()
    config.add_section("Storage")  # default to ~/Downloads

    if storage_type == "onedrive":
        effective_token: Optional[str] = token or os.environ.get("ONEDRIVE_TOKEN")
        if not effective_token:
            print(
                "\n❌ Error: Local retrieval failed. "
                "OneDrive requires a token to download files."
            )
            print(
                "Please pass a token via -t or set the ONEDRIVE_TOKEN environment variable."
            )
            return

        OnedriveProvider(config).handle_result(log_stdout, effective_token)
    elif storage_type == "aliyun":
        provider = AliyunProvider(config)
        provider.handle_result(log_stdout, token)  # triggers download and delete
    elif storage_type == "gofile":
        GofileProvider(config).handle_result(log_stdout)

    print(f"[*] Cleaning up GitHub Actions run page (ID: {run_id})...")
    run_command(f"gh run delete {run_id}")
    print("✅ Run record cleared from GitHub project page.")


def setup_args() -> argparse.Namespace:
    """
    Configure and parse command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="YouTube automated download and cloud storage tool (GitHub Actions driven)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # 1. Basic positional argument
    parser.add_argument(
        "url", type=str, help="Full URL of the YouTube video or audio"
    )

    # 2. Debug and branch control
    debug_group = parser.add_argument_group("Debug & Branch Configuration")
    debug_group.add_argument(
        "-b",
        "--branch",
        type=str,
        default="main",
        help="Target branch to trigger the GitHub Actions workflow",
    )
    debug_group.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    # 3. Download and storage configuration
    parser.add_argument(
        "-m",
        "--mode",
        choices=["audio", "video"],
        default="audio",
        help="Download mode",
    )
    parser.add_argument(
        "-s",
        "--storage",
        choices=["onedrive", "aliyun", "gofile"],
        default="onedrive",
        help="Target storage platform",
    )

    # 4. Custom filename
    parser.add_argument(
        "-f",
        "--filename",
        type=str,
        default=None,
        help="Custom output filename (extension omitted; yt-dlp will append automatically)",
    )

    # 5. Aliyun Drive specific parameters
    ali_group = parser.add_argument_group("Aliyun Drive Configuration")
    ali_group.add_argument(
        "--token", type=str, help="Aliyun Drive refresh token"
    )
    ali_group.add_argument(
        "--path", type=str, default="/", help="Save path on cloud"
    )

    args = parser.parse_args()

    if args.storage == "aliyun" and not args.token:
        parser.error(
            "Error: --token is required when storage backend is 'aliyun'."
        )

    return args


def trigger_github_action(args: argparse.Namespace) -> None:
    """
    Trigger the remote workflow via GitHub CLI.
    """
    if os.path.exists(COOKIE_FILE):
        if os.path.getsize(COOKIE_FILE) == 0:
            print(f"[!] Warning: {COOKIE_FILE} exists but is empty. Skipping sync to GitHub Secrets.")
        else:
            if args.verbose:
                print(f"[*] Syncing {COOKIE_FILE} to GitHub Secrets...")
            run_command(f"gh secret set YOUTUBE_COOKIES < {COOKIE_FILE}")

    cmd: str = (
        f"gh workflow run {WORKFLOW_FILE} "
        f"--ref {args.branch} "
        f'-f video_url="{args.url}" '
        f'-f download_type="{args.mode}" '
        f'-f storage_provider="{args.storage}" '
    )

    # Pass custom filename if set
    if getattr(args, "filename", None):
        cmd += f'-f output_filename="{args.filename}" '

    if args.storage == "aliyun":
        cmd += f'-f provider_token="{args.token}" -f ali_path="{args.path}"'

    stdout, code = run_command(cmd, args.verbose)

    if code == 0:
        print(f"🚀 Success: Workflow triggered on branch '{args.branch}'.")
        # Force monitoring and retrieval; no longer check args.watch
        monitor_workflow(args.branch, args.storage, args.token, args.verbose)
    else:
        print("❌ Failure: Unable to trigger Actions.")
        sys.exit(1)


def main() -> None:
    args = setup_args()
    trigger_github_action(args)


if __name__ == "__main__":
    main()
