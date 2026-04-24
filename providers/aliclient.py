import requests
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class AlipanClient:
    def __init__(self, refresh_token):
        self.refresh_token = refresh_token
        self.access_token = None
        self.drive_id = None
        self.api_host = "https://api.aliyundrive.com"
        self.auth_host = "https://auth.aliyundrive.com"
        self.client_id = "25dzX3vbYq8VNIpa" 
        
        # 配置具备自动重试机制的 Session
        self.session = requests.Session()
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,  # 指数退避：1s, 2s, 4s, 8s...
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        
        self.update_token()
        self.get_default_drive()

    def update_token(self):
        """使用 refresh_token 换取 access_token"""
        url = f"{self.auth_host}/v2/account/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id
        }
        try:
            # 必须设置 timeout 防止卡死
            response = self.session.post(url, json=data, timeout=15).json()
            if "access_token" in response:
                self.access_token = response["access_token"]
                self.refresh_token = response["refresh_token"]
                print("[*] Token 刷新成功")
            else:
                raise Exception(f"Token 刷新失败: {response}")
        except Exception as e:
            raise Exception(f"Auth 接口连接失败: {str(e)}")

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def get_default_drive(self):
        url_a = f"{self.api_host}/adrive/v1/user/get"
        url_b = f"{self.api_host}/v2/user/get"
        
        last_error = ""
        for url in [url_a, url_b]:
            try:
                # 个人版必须是 POST 且 Body 为 {}
                response = self.session.post(url, json={}, headers=self.get_headers(), timeout=15)
                res = response.json()
                
                # 检查返回 code
                if res.get("code") == "NotFound":
                    last_error = res.get("message")
                    continue
                
                # 个人网盘逻辑：优先取 resource_drive_id (资源库) 或 default_drive_id (文件库)
                self.drive_id = res.get("resource_drive_id") or res.get("default_drive_id")
                
                if self.drive_id:
                    print(f"✅ 成功定位个人网盘 Drive ID: {self.drive_id}") 
                    return
            except Exception as e:
                last_error = str(e)
                continue
        
        raise Exception(f"无法获取 DriveID。最后一次尝试错误: {last_error}")
        
    def get_download_url(self, file_id):
        """1. 获取下载链接"""
        url = f"{self.api_host}/v2/file/get_download_url"
        data = {
            "drive_id": self.drive_id,
            "file_id": file_id
        }
        res = requests.post(url, json=data, headers=self.get_headers()).json()
        return res.get("url")

    def delete_file(self, file_id):
        """2. 彻底删除文件 (不可逆)"""
        url = f"{self.api_host}/v2/file/delete"
        data = {
            "drive_id": self.drive_id,
            "file_id": file_id
        }
        res = requests.post(url, json=data, headers=self.get_headers())
        if res.status_code == 204:
            print(f"文件 {file_id} 已彻底删除")
            return True
        return res.json()

    def upload_file(self, local_path: str, parent_file_id: str = "root"):
        """
        高性能上传：支持大文件分片、秒传检测
        """
        if not os.path.exists(local_path):
            raise Exception(f"本地文件不存在: {local_path}")

        file_name = os.path.basename(local_path)
        file_size = os.path.getsize(local_path)
        # 每个分片 10MB (阿里网盘单片上限为 100MB，GitHub 环境建议小一点) [cite: 22]
        chunk_size = 10 * 1024 * 1024 
        
        # 1. 计算分片
        part_info_list = []
        part_count = (file_size // chunk_size) + (1 if file_size % chunk_size > 0 else 0)
        # 如果是 0 字节文件，至少需要一个分片声明
        if part_count == 0: part_count = 1 
        
        for i in range(part_count):
            part_info_list.append({"part_number": i + 1})

        # 2. 创建上传任务 (预检) [cite: 21]
        create_url = f"{self.api_host}/adrive/v2/file/createWithFolders"
        create_data = {
            "drive_id": self.drive_id,
            "parent_file_id": parent_file_id,
            "name": file_name,
            "type": "file",
            "check_name_mode": "auto_rename",
            "size": file_size,
            "part_info_list": part_info_list
        }
        
        create_res = self.session.post(create_url, json=create_data, headers=self.get_headers(), timeout=20).json()

        if "file_id" not in create_res:
            raise Exception(f"创建上传任务失败: {create_res}")

        file_id = create_res["file_id"]
        upload_id = create_res.get("upload_id")

        # 3. 检查秒传 [cite: 24]
        if create_res.get("rapid_upload"):
            print(f"✨ 文件 {file_name} 秒传成功！")
            return create_res

        # 4. 执行分片上传 [cite: 25]
        parts_from_server = create_res.get("part_info_list", [])
        print(f"🚀 开始上传: {file_name} (共 {part_count} 个分片, 总大小 {file_size/1024/1024:.2f}MB)")
        
        with open(local_path, "rb") as f:
            for i, part in enumerate(parts_from_server):
                upload_url = part["upload_url"]
                part_num = part["part_number"]
                
                # 定位分片数据
                f.seek((part_num - 1) * chunk_size)
                chunk_data = f.read(chunk_size)
                
                # 上传分片，设置 5 分钟超时应对大分片 [cite: 25]
                print(f"  > 正在上传分片 [{part_num}/{part_count}]...")
                put_res = self.session.put(upload_url, data=chunk_data, timeout=300)
                put_res.raise_for_status()

        # 5. 完成上传 [cite: 26]
        complete_url = f"{self.api_host}/v2/file/complete"
        complete_data = {
            "drive_id": self.drive_id,
            "file_id": file_id,
            "upload_id": upload_id
        }
        final_res = self.session.post(complete_url, json=complete_data, headers=self.get_headers(), timeout=20).json()
        print(f"✅ 文件 {file_name} 上传完成")
        return final_res
    
    def download_file(self, file_id, local_path):
        """
        改进版下载：
        - 如果 local_path 是目录，自动使用云端文件名
        - 如果 local_path 是完整路径，则重命名下载
        """
        # 1. 获取文件元数据
        file_info = self.get_file_info(file_id)
        cloud_name = file_info['name']

        # 2. 智能路径处理
        if os.path.isdir(local_path):
            # 如果传入的是目录，拼接云端文件名
            final_path = os.path.join(local_path, cloud_name)
        else:
            # 如果传入的是不存在的路径，或者是个具体文件路径
            final_path = local_path
            # 确保父目录存在
            parent_dir = os.path.dirname(os.path.abspath(final_path))
            os.makedirs(parent_dir, exist_ok=True)

        # 3. 获取下载链接
        download_url = self.get_download_url(file_id)
        
        print(f"正在下载: {cloud_name} -> {final_path}")
        
        # 4. 执行流式下载
        headers = {
            "Referer": "https://www.aliyundrive.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        with requests.get(download_url, headers=headers, stream=True) as r:
            r.raise_for_status()
            with open(final_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024): # 1MB chunk
                    if chunk:
                        f.write(chunk)
        
        print(f"✅ 下载完成！")
        return final_path
    
    def get_file_info(self, file_id):
        """获取文件详情（用于获取文件名）"""
        url = f"{self.api_host}/v2/file/get"
        data = {
            "drive_id": self.drive_id,
            "file_id": file_id
        }
        res = requests.post(url, json=data, headers=self.get_headers()).json()
        if "name" not in res:
            raise Exception(f"获取文件信息失败: {res}")
        return res

# --- 使用示例 ---
if __name__ == "__main__":
    # 请替换为你抓取到的 refresh_token
    MY_REFRESH_TOKEN = "2857b916455e4bc7a441fda54955a2f4"
    
    try:
        client = AlipanClient(MY_REFRESH_TOKEN)
        
        # 1. 上传测试
        upload_info = client.upload_file("README.md")
        file_id = upload_info['file_id']
        
        # 2. 下载测试
        download_url = client.get_download_url(file_id=file_id)
        client.download_file(file_id=file_id, local_path="/home/developer/Downloads/")
        print(f"下载链接: {download_url}")
        
        # 3. 彻底删除测试
        client.delete_file(file_id=file_id)
        
    except Exception as e:
        print(f"发生错误: {e}")