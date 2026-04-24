import re
import os
import subprocess
from providers.base import StorageProvider

class OnedriveProvider(StorageProvider):
    def handle_result(self, logs, token):
        """
        根治版：直接调用本地系统预装的 rclone
        """
        # 1. 提取云端上传后的信息
        match = re.search(r"---RESULT_START---(.*?)---RESULT_END---", logs, re.S)
        if not match:
            print("❌ 未在日志中找到上传结果标识，请检查 GitHub Actions 日志。")
            return

        result_text = match.group(1)
        item_id_match = re.search(r"ITEM_ID:\s*(.*)", result_text)
        file_name_match = re.search(r"FILE_NAME:\s*(.*)", result_text)
        
        if not item_id_match or not file_name_match:
            print("❌ 无法解析文件 ID 或文件名。")
            return

        file_name = file_name_match.group(1).strip()
        # 注意：这里我们使用文件名进行下载，因为 rclone 对路径支持更直观
        remote_path = f"onedrive:uploads/{file_name}"
        local_path = os.path.join(self.download_dir, file_name)

        print(f"[*] 检测到云端文件: {file_name}")
        
        # 2. 确保本地目录存在
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

        # 3. 使用 rclone copy 抓取文件
        # rclone 会自动读取 ~/.config/rclone/rclone.conf 并处理 Token 刷新
        print(f"📥 正在回传文件到本地...")
        try:
            # -P 显示进度，--inplace 减少临时文件
            subprocess.run(["rclone", "copy", remote_path, self.download_dir, "-P"], check=True)
            print(f"✅ 回传成功: {local_path}")

            # 4. 成功后清理云端
            print(f"🧹 正在清理云端临时文件...")
            subprocess.run(["rclone", "deletefile", remote_path], check=True)
            print("✨ 云端清理完成，任务圆满结束。")

        except subprocess.CalledProcessError as e:
            print(f"❌ Rclone 操作失败。请确认本地 rclone 配置文件中远程端名称为 'onedrive'")
            print(f"错误详情: {e}")