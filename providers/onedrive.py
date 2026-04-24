# File: providers/onedrive.py
import re, os
from .odclient import OneDriveClient
from .base import StorageProvider

class OnedriveProvider(StorageProvider):
    def handle_result(self, logs, token):
        if token is None:
            print("❌ 错误: Provider 接收到的 Token 为空")
            return
        
        # 1. 匹配云端 shell 脚本输出的标准结果标记 [cite: 42]
        match = re.search(r"---RESULT_START---(.*?)---RESULT_END---", logs, re.S)
        if not match: 
            print("⚠️ 未在日志中找到上传结果标记，回传终止。")
            return
        
        data = match.group(1)
        # 提取由 onedrive.sh 打印的 ITEM_ID 和 FILE_NAME
        item_id = re.search(r"ITEM_ID: (\S+)", data).group(1)
        name = re.search(r"FILE_NAME: (\S+)", data).group(1)

        print(f"📥 正在自动回传文件: {name}")
        client = OneDriveClient(token_data_raw=token)
        
        # 2. 确保本地下载目录存在 [cite: 43]
        os.makedirs(self.download_dir, exist_ok=True)
        
        # 3. 执行下载逻辑
        # download_file 内部会自动拼接路径并执行流式写入 [cite: 34, 37]
        final_local_path = client.download_file(item_id=item_id, local_path=self.download_dir)
        
        # 4. 下载完成后清理云端临时文件 [cite: 43]
        client.delete_file(item_id=item_id)
        
        # --- 重点：增加路径和文件名的明确反馈 ---
        print("-" * 30)
        print(f"✨ 回传完成！")
        print(f"📁 存放目录: {self.download_dir}")
        print(f"📄 文件名称: {name}")
        print(f"📍 完整路径: {final_local_path}")
        print("-" * 30)