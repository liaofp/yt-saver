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
        with sync_playwright() as playwright:
            try:
                # 尝试连接到已运行的 Chrome 浏览器 (假设使用 --remote-debugging-port=9222 启动)
                print("🔍 尝试连接到已运行的 Chrome 浏览器...")
                browser = playwright.chromium.connect_over_cdp("http://localhost:9222")
                print("✅ 成功连接到现有 Chrome 浏览器。")
                context = browser.contexts[0]
                
                # 查找阿里云盘页面
                aliyun_page = None
                print("📋 当前打开的页面：")
                for page in context.pages:
                    print(f"  - {page.url}")
                    if "alipan.com" in page.url or "aliyundrive.com" in page.url:
                        aliyun_page = page
                        break
                
                if aliyun_page:
                    print("✅ 找到阿里云盘页面，正在检查登录状态...")
                    page = aliyun_page
                else:
                    print("❌ 未找到阿里云盘页面。")
                    print("请在浏览器中打开 https://www.alipan.com/ 并完成登录，然后重新运行脚本。")
                    browser.close()
                    raise RuntimeError("请先在浏览器中打开并登录阿里云盘。")
                
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
                    print("请在浏览器中完成阿里云盘登录，然后重新运行脚本。")
                    browser.close()
                    raise RuntimeError("请先在浏览器中登录阿里云盘。")
                    
            except Exception as e:
                print(f"❌ 无法连接到现有 Chrome 浏览器 ({e})")
                print("请确保 Chrome 浏览器已启动并启用远程调试：")
                print("google-chrome --remote-debugging-port=9222")
                print("然后在浏览器中打开 https://www.alipan.com/ 并完成登录，再重新运行脚本。")
                raise RuntimeError("请先启动浏览器并登录阿里云盘。")

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
