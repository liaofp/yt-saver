import requests
import json
import os

class OneDriveClient:
    def __init__(self, token_json_str):
        # 解析 rclone 格式的 token
        self.token_data = json.loads(token_json_str)
        self.access_token = self.token_data.get("access_token")
        self.api_url = "https://graph.microsoft.com/v1.0/me/drive/root"
        
    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def upload_file(self, local_path):
        file_name = os.path.basename(local_path)
        # 上传到 OneDrive 根目录下的 uploads 文件夹
        url = f"{self.api_url}:/uploads/{file_name}:/content"
        
        with open(local_path, "rb") as f:
            resp = requests.put(url, data=f, headers=self.get_headers(), timeout=600)
            resp.raise_for_status()
        return resp.json()

    def get_file_info(self, item_id):
        """获取文件元数据（用于获取文件名） [cite: 38]"""
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}"
        return requests.get(url, headers=self.get_headers()).json()

    def download_file(self, item_id, local_path):
        """
        直接将文件下载到本地 [cite: 33]
        """
        # 1. 获取元数据和下载链接 [cite: 33, 35]
        file_info = self.get_file_info(item_id)
        cloud_name = file_info['name']
        download_url = file_info.get("@microsoft.graph.downloadUrl")

        # 2. 智能路径处理：支持目录或具体文件路径 [cite: 33, 34]
        if os.path.isdir(local_path):
            final_path = os.path.join(local_path, cloud_name)
        else:
            final_path = local_path
            os.makedirs(os.path.dirname(os.path.abspath(final_path)), exist_ok=True)

        print(f"正在从 OneDrive 下载: {cloud_name} -> {final_path} [cite: 35]")
        
        # 3. 执行流式下载 [cite: 36, 37]
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            with open(final_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024): # 1MB 分块 [cite: 37]
                    if chunk:
                        f.write(chunk)
        
        return final_path

    def delete_file(self, item_id):
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}"
        return requests.delete(url, headers=self.get_headers()).status_code == 204