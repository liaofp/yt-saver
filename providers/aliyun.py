from __future__ import annotations

import re
import os
from typing import Optional
from .aliclient import AlipanClient
from .base import StorageProvider


class AliyunProvider(StorageProvider):
    def handle_result(self, logs: str, token: Optional[str] = None) -> None:
        # Match the standardized result printed by the cloud script
        match = re.search(r"---RESULT_START---(.*?)---RESULT_END---", logs, re.S)
        if not match:
            return

        data: str = match.group(1)
        d_id_match = re.search(r"DRIVE_ID: (\S+)", data)
        f_id_match = re.search(r"FILE_ID: (\S+)", data)
        name_match = re.search(r"FILE_NAME: (\S+)", data)

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
