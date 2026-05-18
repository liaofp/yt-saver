from __future__ import annotations

import re
from typing import Optional
from .base import StorageProvider


class GofileProvider(StorageProvider):
    def handle_result(self, logs: str, token: Optional[str] = None) -> None:
        # 1. Parse download URL from logs
        dl_match = re.search(r"DL_URL: (\S+)", logs)
        if not dl_match:
            print("❌ Failed to parse GoFile download URL from logs.")
            return
        dl_url: str = dl_match.group(1)
        print("✅ GoFile: upload successful!")
        print(f"🔗 Please download manually: {dl_url}")
        print("💡 This service does not support automatic retrieval or cleanup.")
