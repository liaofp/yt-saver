import re, os
from .aliclient import AliClient
from .base import StorageProvider

class AliyunProvider(StorageProvider):
    def handle_result(self, logs, token):
        # 匹配云端打印的标准化结果
        match = re.search(r"---RESULT_START---(.*?)---RESULT_END---", logs, re.S)
        if not match: return
        
        data = match.group(1)
        d_id = re.search(r"DRIVE_ID: (\S+)", data).group(1)
        f_id = re.search(r"FILE_ID: (\S+)", data).group(1)
        name = re.search(r"FILE_NAME: (\S+)", data).group(1)

        print(f"📥 正在从阿里云盘自动回传: {name}")
        ali = AliClient(refresh_token=token)
        os.makedirs(self.download_dir, exist_ok=True)
        ali.download_file(file_id=f_id, local_path=os.path.join(self.download_dir))
        ali.delete_file(file_id=f_id)
        print(f"✨ 回传完成，本地路径: {os.path.join(self.download_dir, name)}")