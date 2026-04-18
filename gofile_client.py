import json
from pathlib import Path
from typing import Any, Dict

import requests


class GofileError(Exception):
    pass


class GofileClient:
    def __init__(self):
        self.server = self._get_server()

    def _get_server(self) -> str:
        response = requests.get("https://api.gofile.io/getServer", timeout=30)
        if response.status_code != 200:
            raise GofileError(f"Failed to get server: {response.status_code} {response.text}")
        data = response.json()
        if data.get("status") != "ok":
            raise GofileError(f"Server response error: {data}")
        return data["data"]["server"]

    def upload_file(self, local_path: str) -> Dict[str, Any]:
        local_path = Path(local_path)
        if not local_path.exists():
            raise GofileError(f"Upload file does not exist: {local_path}")

        url = f"https://{self.server}.gofile.io/uploadFile"
        with local_path.open("rb") as fp:
            files = {"file": (local_path.name, fp, "application/octet-stream")}
            response = requests.post(url, files=files, timeout=300)
        
        if response.status_code != 200:
            raise GofileError(f"Upload failed: {response.status_code} {response.text}")
        
        data = response.json()
        if data.get("status") != "ok":
            raise GofileError(f"Upload response error: {data}")
        
        return data["data"]