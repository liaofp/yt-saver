import re
from .base import StorageProvider

class GofileProvider(StorageProvider):
    def handle_result(self, logs, token=None):
        # 1. 解析下载地址
        dl_url = re.search(r"DL_URL: (\S+)", logs).group(1)
        print(f"✅ GoFile：上传成功！")
        print(f"🔗 请手动下载: {dl_url}")
        print(f"💡 该服务无需自动回传与清理。")