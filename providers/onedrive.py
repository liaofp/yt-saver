from __future__ import annotations

import re
import os
import json
import time
import subprocess
from typing import Optional
from .base import StorageProvider


def _find_success_block(logs: str) -> Optional[str]:
    """Find the first RESULT block that contains ITEM_ID (success upload block)."""
    matches = re.findall(r"---RESULT_START---(.*?)---RESULT_END---", logs, re.S)
    for raw in matches:
        # Strip log timestamp prefixes if present
        clean = re.sub(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s*", "", raw, flags=re.M)
        if "ITEM_ID" in clean:
            return clean
    return None


def _remove_remote(remote_path: str, max_attempts: int = 2) -> bool:
    """
    Delete a file from OneDrive and verify it is actually gone.

    Retries the delete once, then confirms via `rclone lsjson` (which fails when
    the path no longer exists). Returns True only when removal is confirmed.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            subprocess.run(["rclone", "deletefile", remote_path], check=True)
        except subprocess.CalledProcessError:
            if attempt < max_attempts:
                continue
        check = subprocess.run(
            ["rclone", "lsjson", remote_path],
            capture_output=True,
            text=True,
        )
        if check.returncode != 0:
            return True  # lsjson errors when the file no longer exists
        try:
            if not json.loads(check.stdout):
                return True
        except Exception:
            pass
    return False


def _verify_download(local_path: str) -> Optional[str]:
    """
    Sanity-check a freshly downloaded file.

    OneDrive Personal occasionally stores uploads with size 0 (metadata glitch);
    downloading such a broken item returns a small HTML error page with HTTP 200,
    which rclone only catches via its size check. Returns an error message if the
    file looks broken, None otherwise.
    """
    try:
        size = os.path.getsize(local_path)
    except OSError as e:
        return f"cannot stat file: {e}"
    if size == 0:
        return "file is empty (0 bytes), the cloud copy is likely broken"
    try:
        with open(local_path, "rb") as f:
            head = f.read(512).lstrip().lower()
    except OSError as e:
        return f"cannot read file: {e}"
    if head.startswith(b"<html") or head.startswith(b"<!doctype html"):
        return "content is an HTML error page, not the expected media file"
    return None


class OnedriveProvider(StorageProvider):
    @staticmethod
    def _discard_bad_download(local_path: str) -> None:
        """Remove a failed/partial download so the next attempt starts clean."""
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
        except OSError:
            pass

    def handle_result(self, logs: str, token: Optional[str] = None) -> None:
        """
        Definitive version: call the locally installed rclone directly.
        """
        # 1. Extract cloud upload info from logs (find success block, not just first block)
        result_text = _find_success_block(logs)
        if result_text is None:
            print("❌ Upload result marker not found in logs.")
            print("   This usually means the workflow failed before uploading.")
            print("   Please check the error message printed above (if any).")
            return

        item_id_match = re.search(r"ITEM_ID:\s*(.*)", result_text)
        file_name_match = re.search(r"FILE_NAME:\s*(.*)", result_text)

        if not item_id_match or not file_name_match:
            print("❌ Unable to parse file ID or file name.")
            return

        file_name: str = file_name_match.group(1).strip()
        # We use the file name for download because rclone handles paths more intuitively
        remote_path: str = f"onedrive:uploads/{file_name}"
        local_path: str = os.path.join(self.download_dir, file_name)

        print(f"[*] Detected cloud file: {file_name}")

        # 2. Ensure local directory exists
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

        # 3. Download with retries. OneDrive's download endpoint intermittently
        #    returns a small HTML error page (HTTP 200) instead of the content
        #    (same backend degradation as the broken upload sessions), so each
        #    attempt is verified and bad local files are discarded and retried.
        max_attempts = 5
        downloaded = False
        for attempt in range(1, max_attempts + 1):
            print(f"📥 Retrieving file to local machine... (attempt {attempt}/{max_attempts})")
            try:
                # --retries 1: retry here, where we can verify each result
                subprocess.run(
                    ["rclone", "copy", remote_path, self.download_dir, "-P", "--retries", "1"],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                print(f"   rclone copy failed: {e}")
                self._discard_bad_download(local_path)
                if attempt < max_attempts:
                    time.sleep(5)
                    continue
                break
            problem = _verify_download(local_path)
            if problem is None:
                downloaded = True
                break
            print(f"   Downloaded file verification failed: {problem}")
            self._discard_bad_download(local_path)
            if attempt < max_attempts:
                print("   Retrying...")
                time.sleep(5)

        # 4. Handle total download failure
        if not downloaded:
            print("❌ Failed to retrieve the file from OneDrive after 5 attempts.")
            print(
                "   If rclone reported 'corrupted on transfer: sizes differ', the "
                "download endpoint returned an HTML error page instead of the "
                "content (transient OneDrive backend issue). Re-run the task later."
            )
            print("[*] Removing the cloud copy (it cannot be retrieved anyway)...")
            if _remove_remote(remote_path):
                print("🧹 Cloud file removed.")
            else:
                print(f"⚠️ Could not confirm cloud file removal: {remote_path}")
            return

        print(f"✅ Retrieval successful: {local_path}")

        # 5. Clean up cloud copy after success; confirm it is really gone
        print("🧹 Cleaning up cloud temporary file...")
        if _remove_remote(remote_path):
            print("✨ Cloud cleanup complete, task finished.")
        else:
            print(f"⚠️ Retrieval succeeded, but the cloud file may still exist: {remote_path}")
