import json
import os
import re
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError as exc:
    raise ImportError(
        "请先安装 playwright: python3 -m pip install playwright，然后执行 python3 -m playwright install chromium"
    ) from exc


CONFIG_PATH = Path.home() / ".config" / "yt-saver" / "aliyundrive.json"
REFRESH_TOKEN_RE = re.compile(r'"refresh_token"\s*[:=]\s*"([^"]+)"', re.IGNORECASE)


def _search_refresh_token(data: str) -> str:
    match = REFRESH_TOKEN_RE.search(data)
    if match:
        return match.group(1)
    return ""


def _extract_token_from_storage(storage: dict) -> str:
    for value in storage.values():
        if not isinstance(value, str):
            continue
        token = _search_refresh_token(value)
        if token:
            return token
    return ""


class AliyunDriveAuth:
    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config_path = config_path
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def obtain_refresh_token(self, timeout: int = 180) -> str:
        with sync_playwright() as playwright:
            browser = None
    def obtain_refresh_token(self, timeout: int = 180) -> str:
        print("请输入阿里云盘 refresh_token：")
        print("获取方法：")
        print("1. 在浏览器中打开 https://www.alipan.com/ 并登录")
        print("2. 按 F12 打开开发者工具")
        print("3. 转到 Application > Local Storage > https://www.alipan.com/")
        print("4. 查找 refresh_token 的值并复制")
        print()
        
        try:
            token = input("refresh_token: ").strip()
            if token:
                self.save_refresh_token(token)
                return token
            else:
                raise RuntimeError("未提供 token")
        except (EOFError, KeyboardInterrupt):
            raise RuntimeError("用户取消输入")

    def save_refresh_token(self, refresh_token: str) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as fh:
            json.dump({"refresh_token": refresh_token}, fh)
        print(f"🔐 Refresh Token 已保存到: {self.config_path}")

    def load_refresh_token(self) -> str:
        if not self.config_path.exists():
            return ""
        with open(self.config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("refresh_token", "")
