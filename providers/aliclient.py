import requests
import os
import json

class AlipanClient:
    def __init__(self, refresh_token):
        self.refresh_token = refresh_token
        self.access_token = None
        self.drive_id = None
        self.api_host = "https://api.aliyundrive.com"
        self.auth_host = "https://auth.aliyundrive.com"
        # 网页端常用的 client_id
        self.client_id = "25dzX3vbYq8VNIpa" 
        
        # 初始获取 access_token 和 drive_id
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
        response = requests.post(url, json=data).json()
        
        if "access_token" in response:
            self.access_token = response["access_token"]
            self.refresh_token = response["refresh_token"]  # 每次刷新都会返回新的 refresh_token
            print("Token 刷新成功")
        else:
            raise Exception(f"Token 刷新失败: {response}")

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def get_default_drive(self):
        """针对个人网盘优化的 Drive ID 获取逻辑"""
        # 个人网盘通常使用 v2 接口，且路径为 /adrive/v1/user/get 或 /v2/user/get
        # 我们直接尝试最通用的个人中心接口
        url = f"https://api.aliyundrive.com/v2/user/get"
        
        try:
            # 个人版有些接口不需要 body，但必须是 POST
            response = requests.post(url, json={}, headers=self.get_headers())
            res = response.json()
            
            # 调试：如果还是报错，可以打印看下
            if "code" in res and res["code"] == "NotFound":
                # 最后的兜底方案：尝试另一个常见的个人版路径
                url = f"https://api.aliyundrive.com/adrive/v1/user/get"
                res = requests.post(url, json={}, headers=self.get_headers()).json()

            self.drive_id = res.get("default_drive_id") or res.get("resource_drive_id")
            
            if not self.drive_id:
                raise Exception(f"无法获取 DriveID，API 返回: {res}")
                
            print(f"✅ 成功定位个人网盘 Drive ID: {self.drive_id}")
        except Exception as e:
            raise Exception(f"获取 Drive 信息失败: {str(e)}")
        
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

    def upload_file(self, local_path, parent_file_id="root"):
        """优化版上传：支持秒传检测和错误处理"""
        if not os.path.exists(local_path):
            raise Exception(f"本地文件不存在: {local_path}")

        file_name = os.path.basename(local_path)
        file_size = os.path.getsize(local_path)

        # Step A: 创建文件预检
        create_url = f"{self.api_host}/adrive/v2/file/createWithFolders"
        create_data = {
            "drive_id": self.drive_id,
            "parent_file_id": parent_file_id,
            "name": file_name,
            "type": "file",
            "check_name_mode": "auto_rename", # 如果重名，自动重命名
            "size": file_size,
            "part_info_list": [{"part_number": 1}]
        }
        
        response = requests.post(create_url, json=create_data, headers=self.get_headers())
        create_res = response.json()

        # 检查是否请求成功
        if response.status_code not in [200, 201]:
            raise Exception(f"创建文件失败: {create_res}")

        file_id = create_res.get("file_id")
        
        # 核心逻辑：判断是否秒传成功
        if create_res.get("rapid_upload"):
            print(f"✨ 文件 {file_name} 秒传成功！")
            return create_res

        # 如果没有秒传，则执行常规上传
        upload_id = create_res.get("upload_id")
        part_info = create_res.get("part_info_list", [])[0]
        upload_url = part_info.get("upload_url")

        if not upload_url:
            raise Exception(f"未获取到上传地址，请检查权限或文件状态: {create_res}")

        # Step B: 上传二进制流
        print(f"正在上传 {file_name} ...")
        with open(local_path, 'rb') as f:
            upload_res = requests.put(upload_url, data=f)
            upload_res.raise_for_status()

        # Step C: 完成上传
        complete_url = f"{self.api_host}/v2/file/complete"
        complete_data = {
            "drive_id": self.drive_id,
            "file_id": file_id,
            "upload_id": upload_id
        }
        final_res = requests.post(complete_url, json=complete_data, headers=self.get_headers()).json()
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
    MY_REFRESH_TOKEN = "4e518cf6a79d41088356f7751303de1a"
    
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