import re, os
from .odclient import OneDriveClient
from .base import StorageProvider

class OnedriveProvider(StorageProvider):
    def handle_result(self, logs, token):
        # 匹配云端 shell 脚本输出的标准化结果 [cite: 42]
        match = re.search(r"---RESULT_START---(.*?)---RESULT_END---", logs, re.S)
        if not match: return
        
        data = match.group(1)
        item_id = re.search(r"ITEM_ID: (\S+)", data).group(1)
        name = re.search(r"FILE_NAME: (\S+)", data).group(1)

        print(f"📥 正在自动回传: {name}")
        client = OneDriveClient(token_json_str=token)
        
        # 确保下载目录存在 
        os.makedirs(self.download_dir, exist_ok=True)
        
        # 调用 client 内部实现的下载方法 
        client.download_file(item_id=item_id, local_path=self.download_dir)
        
        # 下载完成后清理云端 
        client.delete_file(item_id=item_id)
        print(f"✨ 回传完成，本地路径: {os.path.join(self.download_dir, name)} ")