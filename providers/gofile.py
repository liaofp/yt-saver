from __future__ import annotations

import re
from typing import Optional
from .base import StorageProvider


def _find_success_block(logs: str) -> Optional[str]:
    """Find the first RESULT block that contains DL_URL (success upload block)."""
    matches = re.findall(r"---RESULT_START---(.*?)---RESULT_END---", logs, re.S)
    for raw in matches:
        # Strip log timestamp prefixes if present
        clean = re.sub(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s*", "", raw, flags=re.M)
        if "DL_URL" in clean:
            return clean
    return None


class GofileProvider(StorageProvider):
    def handle_result(self, logs: str, token: Optional[str] = None) -> None:
        # 1. Parse download URL from logs (find success block)
        result_text = _find_success_block(logs)
        if result_text is None:
            print("❌ Failed to parse GoFile download URL from logs.")
            print("   This usually means the workflow failed before uploading.")
            print("   Please check the error message printed above (if any).")
            return
        dl_match = re.search(r"DL_URL: (\S+)", result_text)
        if not dl_match:
            print("❌ Failed to parse GoFile download URL from result block.")
            return
        dl_url: str = dl_match.group(1)
        print("✅ GoFile: upload successful!")
        print(f"🔗 Please download manually: {dl_url}")
        print("💡 This service does not support automatic retrieval or cleanup.")
