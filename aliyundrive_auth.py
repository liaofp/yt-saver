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
            try:
                # 尝试连接到已运行的 Chrome 浏览器 (假设使用 --remote-debugging-port=9222 启动)
                print("🔍 尝试连接到已运行的 Chrome 浏览器...")
                browser = playwright.chromium.connect_over_cdp("http://localhost:9222")
                print("✅ 成功连接到现有 Chrome 浏览器。")
                context = browser.contexts[0]
                page = context.pages[0] if context.pages else context.new_page()
                
                # 检查是否已登录阿里云盘
                storage = page.evaluate(
                    "() => ({ local: Object.fromEntries(Object.entries(window.localStorage)), session: Object.fromEntries(Object.entries(window.sessionStorage)) })"
                )
                found_token = _extract_token_from_storage(storage.get("local", {}))
                if not found_token:
                    found_token = _extract_token_from_storage(storage.get("session", {}))
                
                if found_token:
                    print("✅ 已找到 refresh_token，无需重新登录。")
                    browser.close()
                    self.save_refresh_token(found_token)
                    return found_token
                else:
                    print("❌ 未检测到阿里云盘登录状态。")
                    print("请在浏览器中打开 https://www.aliyundrive.com/ 并完成登录，然后重新运行脚本。")
                    browser.close()
                    raise RuntimeError("请先在浏览器中登录阿里云盘。")
                    
            except Exception as e:
                print(f"❌ 无法连接到现有 Chrome 浏览器 ({e})，将启动新浏览器。")
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
