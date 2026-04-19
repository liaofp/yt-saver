import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import urllib3
from urllib3.util.retry import Retry

AUTH_URL = "https://auth.aliyundrive.com/v2/account/token"
API_BASE = "https://api.aliyundrive.com/v2"


class AliyunDriveError(Exception):
    pass


class AliyunDriveClient:
    def __init__(self, refresh_token: str):
        self.refresh_token = refresh_token
        self.access_token: Optional[str] = None
        self.drive_id: Optional[str] = None

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.get_access_token()}"
        }

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Any:
        url = f"{API_BASE}/{endpoint}"
        response = requests.post(url, json=payload, headers=self._headers(), timeout=60)
        if response.status_code not in (200, 201):
            raise AliyunDriveError(
                f"AliyunDrive API request failed: {endpoint} {response.status_code} {response.text}"
            )
        data = response.json()
        if "code" in data and data["code"] not in (0, "OK"):
            raise AliyunDriveError(f"AliyunDrive API returned error: {data}")
        return data

    def get_access_token(self) -> str:
        if self.access_token:
            return self.access_token

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }
        response = requests.post(AUTH_URL, json=payload, timeout=60)
        if response.status_code != 200:
            raise AliyunDriveError(f"Failed to refresh token: {response.status_code} {response.text}")

        data = response.json()
        if not data.get("access_token"):
            raise AliyunDriveError(f"Invalid refresh token response: {data}")

        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        return self.access_token

    def get_default_drive_id(self) -> str:
        if self.drive_id:
            return self.drive_id

        data = self._post("user/get", {})
        drive_id = data.get("default_drive_id")
        if not drive_id:
            raise AliyunDriveError(f"Unable to resolve default drive id: {data}")
        self.drive_id = drive_id
        return drive_id

    def create_upload_session(self, file_name: str, file_size: int, parent_file_id: str = "root") -> Dict[str, Any]:
        drive_id = self.get_default_drive_id()
        payload = {
            "drive_id": drive_id,
            "parent_file_id": parent_file_id,
            "name": file_name,
            "type": "file",
            "check_name_mode": "auto_rename",
            "size": file_size
        }
        return self._post("file/create", payload)

    def upload_file(self, local_path: str, parent_file_id: str = "root") -> Dict[str, Any]:
        local_path = Path(local_path)
        if not local_path.exists():
            raise AliyunDriveError(f"上传文件不存在: {local_path}")

        session = self.create_upload_session(local_path.name, local_path.stat().st_size, parent_file_id)
        file_id = session.get("file_id")
        upload_id = session.get("upload_id")
        part_info_list = session.get("part_info_list")

        if not file_id or not upload_id or not part_info_list:
            raise AliyunDriveError(f"上传会话创建失败: {session}")

        part_info_for_complete = []
        http = urllib3.PoolManager(cert_reqs='CERT_NONE')
        with local_path.open("rb") as fp:
            for part in part_info_list:
                part_number = part["part_number"]
                upload_url = part["upload_url"]
                # For single part upload, part_size is the file size
                expected_size = local_path.stat().st_size
                chunk = fp.read(expected_size)
                if not chunk:
                    raise AliyunDriveError("读取上传分片失败")
                put_headers = {"Content-Type": "application/octet-stream"}
                retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
                result = http.request('PUT', upload_url, body=chunk, headers=put_headers, retries=retry)
                if result.status not in (200, 201, 204):
                    raise AliyunDriveError(
                        f"上传分片失败: part={part_number} status={result.status} body={result.data.decode()}"
                    )
                etag = result.headers.get('ETag', '').strip('"')
                part_info_for_complete.append({
                    "part_number": part_number,
                    "part_size": expected_size,
                    "etag": etag
                })

        complete_payload = {
            "drive_id": self.get_default_drive_id(),
            "file_id": file_id,
            "upload_id": upload_id,
            "part_info_list": part_info_for_complete
        }
        self._post("file/complete", complete_payload)
        return {
            "file_id": file_id,
            "file_name": local_path.name,
            "drive_id": self.get_default_drive_id()
        }

    def get_download_url(self, file_id: str) -> str:
        payload = {
            "drive_id": self.get_default_drive_id(),
            "file_id": file_id,
            "expire_sec": 3600
        }
        data = self._post("file/get_download_url", payload)
        url = data.get("url")
        if not url:
            raise AliyunDriveError(f"获取下载地址失败: {data}")
        return url

    def delete_file(self, file_id: str) -> None:
        payload = {
            "drive_id": self.get_default_drive_id(),
            "file_id": [file_id]
        }
        self._post("recyclebin/trash", payload)

    def download_url(self, download_url: str, local_path: str) -> None:
        response = requests.get(download_url, stream=True, timeout=120)
        if response.status_code != 200:
            raise AliyunDriveError(f"下载文件失败: {download_url} status={response.status_code}")
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as fh:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    fh.write(chunk)
