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
            browser = playwright.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto("https://www.aliyundrive.com/")
            print("📦 请在新打开的浏览器中完成阿里网盘登录。")
            print("🔄 登录成功后，脚本将自动尝试提取 refresh_token。")

            found_token = ""
            start = time.time()
            while time.time() - start < timeout:
                time.sleep(3)
                storage = page.evaluate(
                    "() => ({ local: Object.fromEntries(Object.entries(window.localStorage)), session: Object.fromEntries(Object.entries(window.sessionStorage)) })"
                )
                found_token = _extract_token_from_storage(storage.get("local", {}))
                if not found_token:
                    found_token = _extract_token_from_storage(storage.get("session", {}))
                if found_token:
                    print("✅ 已找到 refresh_token。")
                    browser.close()
                    self.save_refresh_token(found_token)
                    return found_token
                print("等待登录结果并提取 refresh_token...")

            browser.close()
            raise RuntimeError(
                "未在本地存储中找到 refresh_token，请确认已完成登录并重试。"
            )

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
