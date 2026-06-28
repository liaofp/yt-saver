from __future__ import annotations

import re
import os
from typing import Optional
from .aliclient import AlipanClient
from .base import StorageProvider


def _find_success_block(logs: str) -> Optional[str]:
    """Find the first RESULT block that contains DRIVE_ID (success upload block)."""
    matches = re.findall(r"---RESULT_START---(.*?)---RESULT_END---", logs, re.S)
    for raw in matches:
        # Strip log timestamp prefixes if present
        clean = re.sub(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s*", "", raw, flags=re.M)
        if "DRIVE_ID" in clean:
            return clean
    return None


class AliyunProvider(StorageProvider):
    def handle_result(self, logs: str, token: Optional[str] = None) -> None:
        # Match the standardized result printed by the cloud script (find success block)
        result_text = _find_success_block(logs)
        if result_text is None:
            print("❌ Upload result marker not found in logs.")
            print("   This usually means the workflow failed before uploading.")
            print("   Please check the error message printed above (if any).")
            return

        d_id_match = re.search(r"DRIVE_ID: (\S+)", result_text)
        f_id_match = re.search(r"FILE_ID: (\S+)", result_text)
        name_match = re.search(r"FILE_NAME: (\S+)", result_text)

        if not d_id_match or not f_id_match or not name_match:
            print("❌ Failed to parse Aliyun result block.")
            return

        d_id: str = d_id_match.group(1)
        f_id: str = f_id_match.group(1)
        name: str = name_match.group(1)

        print(f"📥 Auto-retrieving from Aliyun Drive: {name}")
        ali = AlipanClient(refresh_token=token or "", client_id="25dzX3vbYq8VNIpa")
        os.makedirs(self.download_dir, exist_ok=True)
        ali.download_file(file_id=f_id, local_path=self.download_dir)
        ali.delete_file(file_id=f_id)
        print(f"✨ Retrieval complete, local path: {os.path.join(self.download_dir, name)}")
