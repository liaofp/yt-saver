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
        """
        修正版：支持分片上传，解决 4MB 限制
        """
        file_name = os.path.basename(local_path)
        file_size = os.path.getsize(local_path)
        
        # 1. 如果文件小于 4MB，使用简单上传 (提高小文件效率)
        if file_size < 4 * 1024 * 1024:
            url = f"{self.api_url}:/uploads/{file_name}:/content"
            with open(local_path, "rb") as f:
                resp = requests.put(url, data=f, headers=self.get_headers(), timeout=300)
                resp.raise_for_status()
            return resp.json()

        # 2. 大文件：创建上传会话 (Upload Session)
        # 路径：/uploads/文件名
        session_url = f"{self.api_url}:/uploads/{file_name}:/createUploadSession"
        session_res = requests.post(session_url, headers=self.get_headers()).json()
        
        if 'uploadUrl' not in session_res:
            raise Exception(f"创建上传会话失败: {session_res}")
        
        upload_url = session_res['uploadUrl']
        
        # 3. 分片上传逻辑
        # OneDrive 要求分片大小必须是 320KB 的倍数，这里采用 10MB
        chunk_size = 10 * 320 * 1024  # 3.2MB (也可改为 10 * 1024 * 1024) [cite: 25]
        print(f"🚀 开始大文件分片上传: {file_name} ({file_size/1024/1024:.2f}MB)")
        
        with open(local_path, "rb") as f:
            start = 0
            while start < file_size:
                end = min(start + chunk_size, file_size)
                chunk_data = f.read(end - start)
                
                # Content-Range 格式：bytes start-end/total
                headers = {
                    "Content-Length": str(len(chunk_data)),
                    "Content-Range": f"bytes {start}-{end-1}/{file_size}"
                }
                
                # 注意：分片上传不需要全局 Authorization 头，session url 已包含权限
                put_res = requests.put(upload_url, data=chunk_data, headers=headers, timeout=600)
                
                if put_res.status_code in [200, 201]:
                    # 200/201 代表最后一片上传完成
                    print(f"✅ 上传完成")
                    return put_res.json()
                elif put_res.status_code == 202:
                    # 202 代表分片接受成功，继续下一片
                    progress = (end / file_size) * 100
                    print(f"  > 已上传 {progress:.1f}% ...")
                    start = end
                else:
                    raise Exception(f"分片上传失败: {put_res.text}")

    def get_file_info(self, item_id):
        """获取文件详情"""
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}"
        return requests.get(url, headers=self.get_headers()).json()

    def download_file(self, item_id, local_path):
        """流式下载到本地"""
        file_info = self.get_file_info(item_id)
        cloud_name = file_info['name']
        download_url = file_info.get("@microsoft.graph.downloadUrl")

        if os.path.isdir(local_path):
            final_path = os.path.join(local_path, cloud_name) [cite: 34]
        else:
            final_path = local_path
            os.makedirs(os.path.dirname(os.path.abspath(final_path)), exist_ok=True)

        print(f"正在下载: {cloud_name} -> {final_path}") [cite: 35]
        
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            with open(final_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024): # 1MB chunk [cite: 37]
                    if chunk:
                        f.write(chunk)
        
        print(f"✅ 下载完成！") [cite: 37]
        return final_path

    def delete_file(self, item_id):
        """删除云端文件"""
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}"
        return requests.delete(url, headers=self.get_headers()).status_code == 204 [cite: 23, 24]