from __future__ import annotations

import yaml
import sys
import os
import time
from typing import Any, Dict, Optional, Tuple

# Import core trigger logic from the original script
from youtube import trigger_github_action
from utils import get_cookies, verify_cookies, refresh_cookies, close_browser
from playwright.sync_api import BrowserContext, Page


class BatchDownloader:
    def __init__(self, config_path: str = "tasks.yml") -> None:
        self.config_path: str = config_path
        self.data: Dict[str, Any] = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            print(f"❌ Error: Configuration file {self.config_path} not found")
            sys.exit(1)
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @staticmethod
    def parse_task(
        task_value: Any, global_cfg: Dict[str, Any]
    ) -> Tuple[Optional[str], str]:
        """
        Parse a single task configuration.
        Supports two formats:
          1. String: "filename"  -> use the given filename (no extension), mode inherits global
          2. Dict:   {filename: "xxx", mode: "audio"} -> per-item parsing, missing keys inherit global
        Returns: (filename, mode)
        """
        filename: Optional[str] = None
        mode: str

        if isinstance(task_value, str):
            # Simple format: string is used directly as filename
            filename = task_value.strip() if task_value.strip() else None
            mode = global_cfg.get("mode", "audio")
        elif isinstance(task_value, dict):
            # Full format: extract from dict, fallback to global defaults
            filename = task_value.get("filename")
            if filename and isinstance(filename, str):
                filename = filename.strip() or None
            mode = task_value.get("mode", global_cfg.get("mode", "audio"))
        else:
            # Unsupported type, use all defaults
            filename = None
            mode = global_cfg.get("mode", "audio")

        return filename, mode

    @staticmethod
    def normalize_filename(filename: Optional[str], mode: str) -> Optional[str]:
        """
        Normalize the filename:
        - Strip any user-supplied extension (yt-dlp decides the correct one based on mode)
        - audio -> .opus, video -> .mp4
        Returns the pure filename without extension (for yt-dlp -o template)
        """
        if not filename:
            return None

        # Strip common audio extensions the user may have mistakenly added
        for ext in [".opus", ".mp3", ".m4a", ".wav", ".flac", ".ogg", ".webm"]:
            if filename.lower().endswith(ext):
                filename = filename[: -len(ext)]
                break
        # Strip common video extensions
        for ext in [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"]:
            if filename.lower().endswith(ext):
                filename = filename[: -len(ext)]
                break

        return filename

    def run(self) -> None:
        global_cfg: Dict[str, Any] = self.data.get("config", {})
        tasks: Dict[str, Any] = self.data.get("tasks", {})

        if not tasks:
            print("! No pending tasks found.")
            return

        # Pre-check: Aliyun Drive must have a token configured
        storage: str = global_cfg.get("storage", "onedrive")
        token: Optional[str] = global_cfg.get("token", None)
        if storage == "aliyun" and not token:
            print("❌ Error: 'aliyun' storage backend requires a token in config.")
            sys.exit(1)

        # Check whether cookies.txt exists locally; if not, guide the user to log in
        context: Optional[BrowserContext] = None
        page: Optional[Page] = None
        if not os.path.exists("cookies.txt"):
            print(
                "[!] cookies.txt not detected. YouTube login is required to obtain cookies..."
            )
            try:
                context, page = get_cookies()
            except Exception as e:
                print(f"❌ Failed to obtain cookies: {e}")
                sys.exit(1)
        else:
            print("[+] Existing cookies.txt detected, skipping login step.")

        total: int = len(tasks)
        print(f"📂 Found {total} tasks, starting batch processing...\n")

        for i, (url, task_value) in enumerate(tasks.items(), 1):
            # After every two tasks, verify whether cookies are still valid
            if i > 1 and (i - 1) % 2 == 0:
                if context and page:
                    print("[*] Two tasks completed, checking cookie validity...")
                    if not verify_cookies(page):
                        print("[!] Cookies expired, attempting self-healing refresh...")
                        if not refresh_cookies(page, context, output_path="cookies.txt"):
                            print("[-] Self-healing refresh failed, re-login required...")
                            try:
                                close_browser(context)
                            except Exception:
                                pass
                            try:
                                context, page = get_cookies()
                            except Exception as e:
                                print(f"❌ Failed to re-obtain cookies: {e}")
                                sys.exit(1)
                else:
                    # If there was no browser context (e.g. user pre-supplied cookies.txt),
                    # verification is impossible; skip
                    pass

            filename, mode = self.parse_task(task_value, global_cfg)

            # If no filename is specified, use the current server timestamp in milliseconds
            if not filename:
                filename = f"{int(time.time() * 1000)}"
            else:
                # User specified a filename; strip any mistakenly added extension
                filename = self.normalize_filename(filename, mode)

            print(f"--- [Task {i}/{total}] URL: {url} ---")
            print(f"    Mode: {mode} | Filename: {filename}")

            # Dynamically simulate an argparse Namespace object
            class Args:
                def __init__(self) -> None:
                    self.url: str = url
                    self.mode: str = mode
                    self.storage: str = storage
                    self.branch: str = global_cfg.get("branch", "main")
                    self.verbose: bool = global_cfg.get("verbose", False)
                    self.token: Optional[str] = token
                    self.path: str = global_cfg.get("path", "/")
                    self.filename: Optional[str] = filename

            current_args = Args()

            try:
                # Call the core trigger function from youtube.py
                trigger_github_action(current_args)
                print(f"✅ Task {i} retrieval completed.\n")
            except SystemExit:
                # trigger_github_action calls sys.exit(1) on failure; abort immediately
                print(f"❌ Task {i} trigger failed, batch processing terminated.")
                sys.exit(1)
            except Exception as e:
                print(f"❌ Task {i} error: {e}")
                print("Batch processing terminated.")
                sys.exit(1)

        # After all tasks, close the browser and delete cookies.txt
        if context:
            close_browser(context)
            print("[+] Browser closed.")

        if os.path.exists("cookies.txt"):
            try:
                os.remove("cookies.txt")
                print("[+] cookies.txt deleted.")
            except Exception as e:
                print(f"[!] Error deleting cookies.txt: {e}")

        print("✨ All batch tasks completed.")


if __name__ == "__main__":
    # Make sure pyyaml is installed: pip install pyyaml
    downloader = BatchDownloader()
    downloader.run()
