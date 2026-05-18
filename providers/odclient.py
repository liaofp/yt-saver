from __future__ import annotations

import requests
import json
import os
import re
from typing import Any, Dict, Optional


class OneDriveClient:
    def __init__(self, token_data_raw: str) -> None:
        """
        Smart parsing: supports raw Access Token, JSON string, or full Rclone INI config.
        """
        self.access_token: Optional[str] = None
        self.token_data: Dict[str, Any] = {}  # explicitly initialized to prevent AttributeError
        self.refresh_token: Optional[str] = None
        self.client_id: Optional[str] = None
        self.client_secret: Optional[str] = None

        if not token_data_raw:
            raise Exception("Token data is empty")

        self.session = requests.Session()

        # 1. Try extracting from Rclone INI format
        if "[tmp_od]" in token_data_raw or "token =" in token_data_raw:
            cid_match = re.search(r"client_id\s*=\s*(.*)", token_data_raw)
            if cid_match:
                self.client_id = cid_match.group(1).strip()
            cs_match = re.search(r"client_secret\s*=\s*(.*)", token_data_raw)
            if cs_match:
                self.client_secret = cs_match.group(1).strip()

            match = re.search(r"token\s*=\s*(\{.*?\})", token_data_raw)
            if match:
                token_json_str: str = match.group(1)
                try:
                    self.token_data = json.loads(token_json_str)
                except Exception:
                    pass

        # 2. If still empty, try pure JSON parsing
        if not self.token_data:
            try:
                data: Dict[str, Any] = json.loads(token_data_raw)
                # Support nested JSON format exported by rclone
                if isinstance(data.get("token"), str):
                    self.token_data = json.loads(data["token"])
                else:
                    self.token_data = data
            except Exception:
                self.token_data = {"access_token": token_data_raw}

        # Uniformly extract key fields from token_data
        self.access_token = self.token_data.get("access_token")
        self.refresh_token = self.token_data.get("refresh_token")
        if not self.client_id:
            self.client_id = self.token_data.get("client_id")

        if not self.access_token:
            raise Exception("Unable to extract a valid Access Token from input")
        self.api_url: str = "https://graph.microsoft.com/v1.0/me/drive/root"

    def refresh_access_token(self) -> str:
        """When the token expires, use refresh_token to obtain a new access_token."""
        print("🔄 Access Token may have expired, attempting refresh...")
        if not self.refresh_token or not self.client_id:
            raise Exception("Missing refresh_token or client_id, cannot auto-refresh")

        url: str = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        data: Dict[str, str] = {
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
            "scope": "offline_access Files.ReadWrite.All",
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret

        resp = self.session.post(url, data=data)
        if resp.status_code == 200:
            new_data: Dict[str, Any] = resp.json()
            self.access_token = new_data.get("access_token")
            print("✅ Token refresh successful")
            return self.access_token
        else:
            raise Exception(f"Token refresh failed: {resp.text}")

    def get_headers(self) -> Dict[str, str]:
        # Ensure correct Bearer format
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def upload_file(self, local_path: str) -> Dict[str, Any]:
        """Upload with automatic retry on auth failure."""
        try:
            return self._execute_upload(local_path)
        except Exception as e:
            if "InvalidAuthenticationToken" in str(e) or "401" in str(e):
                self.refresh_access_token()
                return self._execute_upload(local_path)  # retry after auth refresh
            raise e

    def _execute_upload(self, local_path: str) -> Dict[str, Any]:
        """
        Fixed version: supports chunked upload to work around the 4 MB limit.
        """
        file_name: str = os.path.basename(local_path)
        file_size: int = os.path.getsize(local_path)

        # 1. Simple upload for files smaller than 4 MB
        if file_size < 4 * 1024 * 1024:
            url: str = f"{self.api_url}:/uploads/{file_name}:/content"
            with open(local_path, "rb") as f:
                resp = self.session.put(
                    url, data=f, headers=self.get_headers(), timeout=300
                )
                resp.raise_for_status()
            return resp.json()

        # 2. Large files: create an upload session
        session_url: str = (
            f"{self.api_url}:/uploads/{file_name}:/createUploadSession"
        )
        session_res: Dict[str, Any] = requests.post(
            session_url, headers=self.get_headers()
        ).json()

        if "uploadUrl" not in session_res:
            raise Exception(f"Failed to create upload session: {session_res}")

        upload_url: str = session_res["uploadUrl"]

        # 3. Chunked upload logic (multiples of 320 KB)
        chunk_size: int = 10 * 320 * 1024  # ~3.2 MB; reduce if network is poor
        print(
            f"🚀 Starting large-file chunked upload: {file_name} "
            f"({file_size / 1024 / 1024:.2f} MB)"
        )

        with open(local_path, "rb") as f:
            start: int = 0
            while start < file_size:
                end: int = min(start + chunk_size, file_size)
                chunk_data: bytes = f.read(end - start)

                # Content-Range format: bytes start-end/total
                headers: Dict[str, str] = {
                    "Content-Length": str(len(chunk_data)),
                    "Content-Range": f"bytes {start}-{end - 1}/{file_size}",
                }

                # Simple per-chunk retry
                success: bool = False
                for attempt in range(3):
                    try:
                        # Chunk upload does NOT need an Authorization header
                        put_res = self.session.put(
                            upload_url, data=chunk_data, headers=headers, timeout=300
                        )
                        if put_res.status_code in [200, 201]:
                            print("✅ Upload complete")
                            return put_res.json()
                        elif put_res.status_code == 202:
                            progress: float = (end / file_size) * 100
                            print(f"  > Uploaded {progress:.1f}% ...")
                            start = end
                            success = True
                            break
                        else:
                            print(
                                f"  ! Chunk upload anomaly ({put_res.status_code}), "
                                f"retrying {attempt + 1}/3..."
                            )
                    except Exception as e:
                        print(
                            f"  ! Network error: {str(e)}, retrying {attempt + 1}/3..."
                        )

                    if attempt < 2:
                        import time

                        time.sleep(2)

                if not success:
                    raise Exception(f"Chunk upload failed: {put_res.text}")

    def get_file_info(self, item_id: str) -> Dict[str, Any]:
        """Fetch file details."""
        url: str = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}"
        return requests.get(url, headers=self.get_headers()).json()

    def download_file(self, item_id: str, local_path: str) -> str:
        """Stream download to local disk."""
        file_info: Dict[str, Any] = self.get_file_info(item_id)
        cloud_name: str = file_info["name"]
        download_url: Optional[str] = file_info.get("@microsoft.graph.downloadUrl")

        final_path: str
        if os.path.isdir(local_path):
            final_path = os.path.join(local_path, cloud_name)
        else:
            final_path = local_path
            os.makedirs(
                os.path.dirname(os.path.abspath(final_path)), exist_ok=True
            )

        print(f"Downloading: {cloud_name} -> {final_path}")

        with requests.get(download_url or "", stream=True) as r:
            r.raise_for_status()
            with open(final_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1 MB chunks
                    if chunk:
                        f.write(chunk)

        print("✅ Download complete!")
        return final_path

    def delete_file(self, item_id: str) -> bool:
        """Delete a cloud file."""
        url: str = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}"
        return requests.delete(url, headers=self.get_headers()).status_code == 204
