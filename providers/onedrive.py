from __future__ import annotations

import re
import os
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


class OnedriveProvider(StorageProvider):
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

        # 3. Use rclone copy to fetch the file
        # rclone automatically reads ~/.config/rclone/rclone.conf and handles token refresh
        print("📥 Retrieving file to local machine...")
        try:
            # -P shows progress, --inplace reduces temporary files
            subprocess.run(
                ["rclone", "copy", remote_path, self.download_dir, "-P"],
                check=True,
            )
            print(f"✅ Retrieval successful: {local_path}")

            # 4. Clean up cloud copy after success
            print("🧹 Cleaning up cloud temporary file...")
            subprocess.run(["rclone", "deletefile", remote_path], check=True)
            print("✨ Cloud cleanup complete, task finished.")

        except subprocess.CalledProcessError as e:
            print(
                "❌ Rclone operation failed. Please ensure your local rclone config "
                "has a remote named 'onedrive'"
            )
            print(f"Details: {e}")
