from __future__ import annotations

import hashlib
import os
import requests
from typing import Any, Dict, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class AlipanClient:
    """
    Aliyun Drive (PDS) API Client.

    Implements the official PDS 2022-03-01 API:
    - Upload:   POST /v2/file/create -> PUT chunks -> POST /v2/file/complete
    - Download: POST /v2/file/get_download_url
    - Delete:   POST /v2/file/delete
    - Info:     POST /v2/file/get
    """

    def __init__(
        self, refresh_token: str, client_id: str = ""
    ) -> None:
        self.refresh_token: str = refresh_token
        self.access_token: Optional[str] = None
        self.drive_id: Optional[str] = None
        self.api_host: str = "https://api.aliyundrive.com"
        self.auth_host: str = "https://auth.aliyundrive.com"
        self.client_id: str = client_id

        # Configure a Session with automatic retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,  # exponential backoff: 1s, 2s, 4s, 8s...
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

        self.update_token()
        self.get_default_drive()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def update_token(self) -> None:
        """Exchange refresh_token for access_token."""
        url: str = f"{self.auth_host}/v2/account/token"
        data: Dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
        }
        try:
            response = self.session.post(url, json=data, timeout=15)
            response.raise_for_status()
            res: Dict[str, Any] = response.json()
            if "access_token" in res:
                self.access_token = res["access_token"]
                self.refresh_token = res["refresh_token"]
                print("[*] Token refresh successful")
            else:
                raise Exception(f"Token refresh failed: {res}")
        except Exception as e:
            raise Exception(f"Auth API connection failed: {str(e)}")

    def get_headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise Exception("Access token is not available")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            ),
        }

    # ------------------------------------------------------------------
    # Drive
    # ------------------------------------------------------------------

    def get_default_drive(self) -> None:
        """Fetch the default drive_id for the authenticated user."""
        url_a: str = f"{self.api_host}/adrive/v1/user/get"
        url_b: str = f"{self.api_host}/v2/user/get"

        last_error: str = ""
        for url in [url_a, url_b]:
            try:
                response = self.session.post(
                    url, json={}, headers=self.get_headers(), timeout=15
                )
                response.raise_for_status()
                res: Dict[str, Any] = response.json()

                if res.get("code") == "NotFound":
                    last_error = res.get("message", "")
                    continue

                # Prefer resource_drive_id, fallback to default_drive_id
                self.drive_id = res.get("resource_drive_id") or res.get(
                    "default_drive_id"
                )

                if self.drive_id:
                    print(
                        f"✅ Successfully located personal drive ID: {self.drive_id}"
                    )
                    return
            except Exception as e:
                last_error = str(e)
                continue

        raise Exception(
            f"Unable to obtain DriveID. Last attempt error: {last_error}"
        )

    def _require_drive_id(self) -> str:
        if not self.drive_id:
            raise Exception("Drive ID is not available. Call get_default_drive() first.")
        return self.drive_id

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    @staticmethod
    def _sha1_file(local_path: str) -> str:
        """Calculate SHA1 hash of a file for rapid-upload detection."""
        sha1 = hashlib.sha1()
        with open(local_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha1.update(chunk)
        return sha1.hexdigest().upper()

    def upload_file(
        self, local_path: str, parent_file_id: str = "root"
    ) -> Dict[str, Any]:
        """
        Upload a file with chunked upload and rapid-upload (deduplication) support.

        Official flow:
        1. POST /v2/file/create  (with optional content_hash for rapid upload)
        2. PUT each chunk to upload_url
        3. POST /v2/file/complete
        """
        if not os.path.exists(local_path):
            raise Exception(f"Local file does not exist: {local_path}")

        file_name: str = os.path.basename(local_path)
        file_size: int = os.path.getsize(local_path)
        drive_id: str = self._require_drive_id()

        # 10 MB per chunk (Aliyun limit is 100 MB per chunk)
        chunk_size: int = 10 * 1024 * 1024

        # 1. Calculate chunks
        part_info_list: list[Dict[str, int]] = []
        part_count: int = (file_size // chunk_size) + (
            1 if file_size % chunk_size > 0 else 0
        )
        if part_count == 0:
            part_count = 1

        for i in range(part_count):
            part_info_list.append({"part_number": i + 1})

        # 2. Create upload task (pre-check)
        create_url: str = f"{self.api_host}/v2/file/create"
        create_data: Dict[str, Any] = {
            "drive_id": drive_id,
            "parent_file_id": parent_file_id,
            "name": file_name,
            "type": "file",
            "check_name_mode": "auto_rename",
            "size": file_size,
            "part_info_list": part_info_list,
        }

        # Add SHA1 hash to enable rapid-upload (deduplication)
        if file_size > 0:
            create_data["content_hash"] = self._sha1_file(local_path)
            create_data["content_hash_name"] = "sha1"

        response = self.session.post(
            create_url, json=create_data, headers=self.get_headers(), timeout=20
        )
        response.raise_for_status()
        create_res: Dict[str, Any] = response.json()

        if "file_id" not in create_res:
            raise Exception(f"Failed to create upload task: {create_res}")

        file_id: str = create_res["file_id"]
        upload_id: Optional[str] = create_res.get("upload_id")

        # 3. Check rapid upload (content-addressed deduplication)
        if create_res.get("rapid_upload"):
            print(f"✨ File {file_name} rapid-uploaded successfully!")
            return create_res

        # 4. Execute chunked upload
        parts_from_server: list[Dict[str, Any]] = create_res.get(
            "part_info_list", []
        )
        if len(parts_from_server) != part_count:
            raise Exception(
                f"Server returned {len(parts_from_server)} parts, "
                f"but client expected {part_count}"
            )

        print(
            f"🚀 Starting upload: {file_name} ({part_count} chunks, "
            f"total {file_size / 1024 / 1024:.2f} MB)"
        )

        with open(local_path, "rb") as f:
            for part in parts_from_server:
                upload_url: str = part["upload_url"]
                part_num: int = part["part_number"]

                f.seek((part_num - 1) * chunk_size)
                chunk_data: bytes = f.read(chunk_size)

                print(f"  > Uploading chunk [{part_num}/{part_count}]...")
                put_res = self.session.put(upload_url, data=chunk_data, timeout=300)
                put_res.raise_for_status()

        # 5. Finalize upload
        complete_url: str = f"{self.api_host}/v2/file/complete"
        complete_data: Dict[str, Any] = {
            "drive_id": drive_id,
            "file_id": file_id,
            "upload_id": upload_id,
        }
        complete_resp = self.session.post(
            complete_url, json=complete_data, headers=self.get_headers(), timeout=20
        )
        complete_resp.raise_for_status()
        final_res: Dict[str, Any] = complete_resp.json()
        print(f"✅ File {file_name} upload complete")
        return final_res

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def get_download_url(self, file_id: str) -> Optional[str]:
        """Obtain a temporary download URL."""
        url: str = f"{self.api_host}/v2/file/get_download_url"
        data: Dict[str, str] = {
            "drive_id": self._require_drive_id(),
            "file_id": file_id,
        }
        response = self.session.post(
            url, json=data, headers=self.get_headers()
        )
        response.raise_for_status()
        res: Dict[str, Any] = response.json()
        return res.get("url")

    def get_file_info(self, file_id: str) -> Dict[str, Any]:
        """Fetch file details (used to obtain the file name)."""
        url: str = f"{self.api_host}/v2/file/get"
        data: Dict[str, str] = {
            "drive_id": self._require_drive_id(),
            "file_id": file_id,
        }
        response = self.session.post(url, json=data, headers=self.get_headers())
        response.raise_for_status()
        res: Dict[str, Any] = response.json()
        if "name" not in res:
            raise Exception(f"Failed to get file info: {res}")
        return res

    def download_file(self, file_id: str, local_path: str) -> str:
        """
        Download a file from Aliyun Drive.
        - If local_path is a directory, use the cloud file name automatically.
        - If local_path is a full file path, rename accordingly.
        """
        file_info: Dict[str, Any] = self.get_file_info(file_id)
        cloud_name: str = file_info["name"]

        final_path: str
        if os.path.isdir(local_path):
            final_path = os.path.join(local_path, cloud_name)
        else:
            final_path = local_path
            parent_dir: str = os.path.dirname(os.path.abspath(final_path))
            os.makedirs(parent_dir, exist_ok=True)

        download_url: Optional[str] = self.get_download_url(file_id)
        if not download_url:
            raise Exception("Failed to obtain download URL")

        print(f"Downloading: {cloud_name} -> {final_path}")

        headers: Dict[str, str] = {
            "Referer": "https://www.aliyundrive.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36"
            ),
        }

        with self.session.get(download_url, headers=headers, stream=True) as r:
            r.raise_for_status()
            with open(final_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1 MB
                    if chunk:
                        f.write(chunk)

        print("✅ Download complete!")
        return final_path

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_file(self, file_id: str) -> bool:
        """
        Permanently delete a file or folder (irreversible).
        Returns True on success, raises Exception on failure.
        """
        url: str = f"{self.api_host}/v2/file/delete"
        data: Dict[str, str] = {
            "drive_id": self._require_drive_id(),
            "file_id": file_id,
        }
        response = self.session.post(url, json=data, headers=self.get_headers())
        if response.status_code == 204:
            print(f"File {file_id} permanently deleted")
            return True

        # Non-204: parse error and raise
        try:
            err_body: Dict[str, Any] = response.json()
        except Exception:
            err_body = {"raw": response.text}
        raise Exception(
            f"Delete failed (HTTP {response.status_code}): {err_body}"
        )


# --- Usage Example ---
if __name__ == "__main__":
    # Replace with your actual refresh_token
    MY_REFRESH_TOKEN: str = "2857b916455e4bc7a441fda54955a2f4"

    try:
        client = AlipanClient(MY_REFRESH_TOKEN)

        # 1. Upload test
        upload_info: Dict[str, Any] = client.upload_file("README.md")
        file_id: str = upload_info["file_id"]

        # 2. Download test
        download_url: Optional[str] = client.get_download_url(file_id=file_id)
        client.download_file(file_id=file_id, local_path="/home/developer/Downloads/")
        print(f"Download URL: {download_url}")

        # 3. Permanent deletion test
        client.delete_file(file_id=file_id)

    except Exception as e:
        print(f"Error: {e}")
