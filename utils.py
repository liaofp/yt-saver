from __future__ import annotations

import os
import sys
import time
from typing import Tuple, Optional
from playwright.sync_api import (
    Playwright,
    BrowserContext,
    Page,
    BrowserType,
    sync_playwright,
)


def auto_login(page: Page, email: str, password: str) -> bool:
    """
    使用预设的邮箱和密码自动完成 Google/YouTube 登录。
    登录成功后返回 True，失败返回 False。
    """
    print("[*] Auto-login mode: navigating to Google sign-in page...")
    try:
        # 1. 打开 Google 登录页
        page.goto("https://accounts.google.com/signin/v2/identifier?service=youtube")
        page.wait_for_load_state("networkidle")

        # 2. 填写邮箱
        print(f"[*] Filling email: {email}")
        email_input = page.locator('input[type="email"]')
        email_input.wait_for(state="visible", timeout=10000)
        email_input.fill(email)
        time.sleep(0.5)

        # 3. 点击下一步
        page.locator("#identifierNext button").click()
        time.sleep(1.5)

        # 4. 填写密码
        print("[*] Filling password...")
        password_input = page.locator('input[type="password"]')
        password_input.wait_for(state="visible", timeout=10000)
        password_input.fill(password)
        time.sleep(0.5)

        # 5. 点击下一步（登录）
        page.locator("#passwordNext button").click()
        time.sleep(2)

        # 6. 等待页面跳转或加载完成
        page.wait_for_load_state("networkidle", timeout=15000)

        # 7. 检查是否仍在登录页（说明登录失败或需要二次验证）
        current_url = page.url
        if "accounts.google.com" in current_url:
            if "challenge" in current_url or "signin" in current_url:
                print(
                    "[!] Auto-login paused: additional verification required (2FA/CAPTCHA)."
                    " Please complete it manually in the browser."
                )
                # 等待用户手动完成验证，最长 120 秒
                try:
                    page.wait_for_url(lambda url: "accounts.google.com" not in url, timeout=120000)
                    print("[+] Manual verification completed successfully.")
                except Exception:
                    print("[-] Manual verification timeout.")
                    return False
            else:
                print("[-] Auto-login failed: still on login page.")
                return False

        print("[+] Auto-login completed successfully.")
        return True
    except Exception as e:
        print(f"[-] Auto-login error: {e}")
        return False


def detect_system_browser(
    playwright: Playwright,
) -> Tuple[BrowserType, Optional[str], Optional[str]]:
    """
    Deep probe the system for an installed browser and return the best match:
    (browser engine, channel name, absolute path)
    """
    current_os: str = sys.platform

    # ==================== 1. WINDOWS Deep Probe ====================
    if current_os == "win32":
        # Probe Chrome
        chrome_paths = [
            os.path.join(
                os.environ.get("ProgramFiles", "C:\\Program Files"),
                "Google\\Chrome\\Application\\chrome.exe",
            ),
            os.path.join(
                os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
                "Google\\Chrome\\Application\\chrome.exe",
            ),
            os.path.join(
                os.environ.get("LocalAppData", ""),
                "Google\\Chrome\\Application\\chrome.exe",
            ),
        ]
        for p in chrome_paths:
            if os.path.exists(p):
                return playwright.chromium, "chrome", p

        # Probe Edge
        edge_paths = [
            os.path.join(
                os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
                "Microsoft\\Edge\\Application\\msedge.exe",
            ),
            os.path.join(
                os.environ.get("ProgramFiles", "C:\\Program Files"),
                "Microsoft\\Edge\\Application\\msedge.exe",
            ),
        ]
        for p in edge_paths:
            if os.path.exists(p):
                return playwright.chromium, "msedge", p

    # ==================== 2. MACOS Deep Probe ====================
    elif current_os == "darwin":
        if os.path.exists("/Applications/Google Chrome.app"):
            return playwright.chromium, "chrome", None
        if os.path.exists("/Applications/Microsoft Edge.app"):
            return playwright.chromium, "msedge", None
        # Fallback: Safari is available on every Mac
        if os.path.exists("/Applications/Safari.app"):
            print(
                "[*] Note: No mainstream Chromium browser detected, "
                "falling back to native WebKit (Safari)"
            )
            return playwright.webkit, None, None

    # ==================== 3. LINUX Deep Probe ====================
    elif current_os.startswith("linux"):
        # Official Google Chrome
        if os.system("command -v google-chrome >/dev/null 2>&1") == 0:
            return playwright.chromium, "chrome", None
        # Open-source Chromium (common on Ubuntu/Debian)
        for bin_name in ["chromium-browser", "chromium"]:
            if os.system(f"command -v {bin_name} >/dev/null 2>&1") == 0:
                return playwright.chromium, "chromium", None
        # Edge for Linux
        if os.system("command -v microsoft-edge >/dev/null 2>&1") == 0:
            return playwright.chromium, "msedge", None
        # Firefox (default on many distros such as Ubuntu)
        if os.system("command -v firefox >/dev/null 2>&1") == 0:
            print(
                "[*] Note: No Chromium browser detected, "
                "falling back to system Firefox"
            )
            return playwright.firefox, None, None

    # ==================== 4. Ultimate Fallback ====================
    # If nothing above matched, force local chromium and hope the user has a Playwright build
    return playwright.chromium, "chrome", None


def initialize_browser(
    playwright: Playwright, headless: bool = False
) -> Tuple[BrowserContext, Page]:
    """
    Ultimate stealth initialization: bypass Google "unsafe browser" checks on Linux.
    """
    browser_type, channel, exe_path = detect_system_browser(playwright)

    # 1. Key: inject anti-detection launch arguments (Chromium)
    ignore_arguments = ["--enable-automation", "--disable-extensions"]

    extra_arguments = [
        "--disable-blink-features=AutomationControlled",  # core: disable Blink automation flags
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-infobars",  # hide "controlled by automated test software" bar
        "--window-size=1280,720",
        "--lang=zh-CN,zh;q=0.9",  # mimic normal language header
        "--incognito",  # force incognito mode: no disk persistence, no shared profile
    ]

    launch_args: dict[str, object] = {
        "headless": headless,
        "ignore_default_args": ignore_arguments,  # drop Playwright defaults that expose automation
        "args": extra_arguments,
    }

    if exe_path:
        launch_args["executable_path"] = exe_path
    elif channel:
        launch_args["channel"] = channel

    try:
        browser = browser_type.launch(**launch_args)
    except Exception as e:
        print(f"[-] Failed to launch local browser: {e}")
        raise e

    # 2. Create a context that fully mimics a regular user environment
    context: BrowserContext = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )

    # 3. Ultimate defense: before every page load, wipe navigator.webdriver in JS runtime
    # Even Google's high-privilege encrypted scripts will only see undefined
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """
    )

    page: Page = context.new_page()
    return context, page


def save_cookies(
    context: BrowserContext, cookies_file: str = "cookies.txt"
) -> None:
    """
    Extract cookies from Playwright memory and convert them to a yt-dlp compatible
    standard Netscape-format text file.
    Output path is resolved against the current working directory.
    """
    current_dir: str = (
        os.path.abspath(os.path.dirname(__file__))
        if "__file__" in locals()
        else os.getcwd()
    )
    output_absolute_path: str = os.path.join(current_dir, cookies_file)

    playwright_cookies = context.cookies()

    try:
        with open(output_absolute_path, "w", encoding="utf-8") as f:
            # Write Netscape spec header
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# https://curl.haxx.se/rfc/cookie_spec.html\n")
            f.write("# This is a generated file! Do not edit.\n\n")

            for cookie in playwright_cookies:
                domain: str = cookie["domain"]
                # Only keep cookies relevant to YouTube / Google authentication
                if not (domain.endswith("youtube.com") or domain.endswith(".google.com")):
                    continue

                include_subdomains: str = "TRUE" if domain.startswith(".") else "FALSE"
                path: str = cookie["path"]
                secure: str = "TRUE" if cookie["secure"] else "FALSE"
                # Netscape format requires a valid positive timestamp for expires.
                # Playwright may return -1 for session cookies; yt-dlp skips these.
                # Clamp to a future date (1 year) to keep the cookie valid.
                raw_expires = cookie.get("expires", -1)
                if raw_expires is None or raw_expires == -1:
                    expires = int(time.time() + 86400 * 365)
                else:
                    expires = int(raw_expires)
                name: str = cookie["name"]
                value: str = cookie["value"]
                httponly: str = "TRUE" if cookie.get("httpOnly", False) else "FALSE"

                # Netscape format: 7 tab-separated columns
                # domain, flag, path, secure, expires, name, value
                f.write(
                    f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"
                )

        print(f"[+] Cookies successfully converted and saved to: {output_absolute_path}")
    except Exception as e:
        print(f"[-] Failed to write cookie file: {e}")


def verify_cookies(page: Page) -> bool:
    """
    Lightweight cookie validity check.
    Visit the subscriptions page; if redirected to accounts.google.com, cookies are invalid.
    """
    print("[*] Verifying current cookie validity...")
    try:
        response = page.goto("https://www.youtube.com/feed/subscriptions")
        current_url: str = page.url

        if "accounts.google.com" in current_url:
            print("[-] Verification failed: cookies expired, login redirect encountered.")
            return False

        # Fallback: check whether the page still shows a login button
        content: str = page.content()
        if 'href="https://accounts.google.com/ServiceLogin' in content:
            print("[-] Verification failed: page shows unauthenticated state.")
            return False

        print("[+] Verification passed: cookies are still valid.")
        return True
    except Exception as e:
        print(f"[-] Exception during verification: {e}")
        return False


def refresh_cookies(
    page: Page, context: BrowserContext, output_path: str = "cookies.txt"
) -> bool:
    """
    Self-healing refresh: reload YouTube homepage to trigger the browser's built-in
    refresh-token mechanism, then re-extract and overwrite the local yt-dlp cookie file.
    """
    print("[*] Triggering self-healing: attempting to refresh page for new cookies...")
    try:
        # Navigate to homepage and let internal JS perform a legal token renewal
        page.goto("https://www.youtube.com/")
        page.wait_for_load_state("networkidle")  # wait until network is idle

        # Update local file
        save_cookies(context, output_path)

        # Re-verify in a closed loop
        return verify_cookies(page)
    except Exception as e:
        print(f"[-] Cookie refresh failed: {e}")
        return False


def is_login(context: BrowserContext) -> bool:
    """
    Secondary event checker: inspect Playwright memory for the core security cookies
    that indicate a successful login.
    """
    cookies = context.cookies()
    cookie_names: set[str] = {c["name"] for c in cookies}

    # The "golden trio" required for yt-dlp to download restricted videos
    required_core_cookies: set[str] = {"__Secure-3PSID", "SAPISID", "SID"}

    # If these core cookies are present, async cross-domain sync is complete
    return required_core_cookies.issubset(cookie_names)


# Global Playwright instance to keep the browser process alive
_playwright_instance: Optional[Playwright] = None


def get_cookies() -> Tuple[Optional[BrowserContext], Optional[Page]]:
    global _playwright_instance

    # If an instance already exists, stop it first to avoid conflicts
    if _playwright_instance:
        try:
            _playwright_instance.stop()
        except Exception:
            pass

    _playwright_instance = sync_playwright().start()

    # 1. Launch a stealthy local browser
    context, page = initialize_browser(_playwright_instance, headless=False)

    print("[*] Opening YouTube homepage...")
    page.goto("https://www.youtube.com/")

    # 检查环境变量是否配置了自动登录凭据
    email = os.environ.get("YOUTUBE_EMAIL")
    password = os.environ.get("YOUTUBE_PASSWORD")

    if email and password:
        print("[!] Auto-login credentials detected in environment variables.")
        login_success = auto_login(page, email, password)
        if not login_success:
            print("[-] Auto-login failed, exiting.")
            context.close()
            _playwright_instance.stop()
            _playwright_instance = None
            return None, None
    else:
        print(
            "[!] [Event listener active] Please click Sign In in the opened browser and complete login..."
        )

        # ==================== Event 1: Listen for login-success DOM signal ====================
        try:
            avatar_selector: str = "button#avatar-btn"
            # wait_for_selector is an efficient low-level event listener:
            # it resumes the moment the element appears, up to 120 s
            page.wait_for_selector(avatar_selector, timeout=120000)
            print(
                "[+] [Event 1 triggered]: user avatar detected on page, DOM-level login confirmed!"
            )
        except Exception:
            print("[-] Login timeout or success element not detected, exiting.")
            context.close()
            _playwright_instance.stop()
            _playwright_instance = None
            return None, None

    # ==================== Event 2: Listen for core cookie write to memory ====================
    print(
        "[*] [Event listener active] Monitoring browser memory, "
        "waiting for core encrypted session cookies to sync..."
    )

    max_cookie_wait: int = 15  # max 15 seconds for background cross-domain sync
    start_time: float = time.time()
    cookies_captured: bool = False

    while time.time() - start_time < max_cookie_wait:
        if is_login(context):
            print(
                "[+] [Event 2 triggered]: core security cookies "
                "(__Secure-3PSID etc.) fully captured in memory!"
            )
            cookies_captured = True
            break
        time.sleep(0.5)  # poll memory at 500 ms intervals

    if not cookies_captured:
        print(
            "[!] Warning: login detected but core security cookies did not fully sync "
            "within 15 s; forcing capture of existing fragments."
        )

    # Trigger instant write: once Event 2 is satisfied, generate the Netscape text file immediately
    save_cookies(context, cookies_file="cookies.txt")
    print(
        "[+] State transition: cookie file written instantly, perfectly compatible with yt-dlp."
    )

    return context, page


def close_browser(context: Optional[BrowserContext] = None) -> None:
    """
    清空浏览器所有数据并关闭浏览器上下文和 Playwright 实例。
    应在所有任务完成后调用。
    """
    global _playwright_instance
    if context:
        try:
            context.clear_cookies()
        except Exception:
            pass
        try:
            context.close()
        except Exception:
            pass
    if _playwright_instance:
        try:
            _playwright_instance.stop()
        except Exception:
            pass
        _playwright_instance = None


def main() -> None:
    # 尝试从 .env 文件加载环境变量（如果存在）
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        print(f"[*] Loaded environment variables from: {env_path}")

    with sync_playwright() as playwright:
        # 1. Launch a stealthy local browser
        context, page = initialize_browser(playwright, headless=False)

        print("[*] Opening YouTube homepage...")
        page.goto("https://www.youtube.com/")

        # 检查环境变量是否配置了自动登录凭据
        email = os.environ.get("YOUTUBE_EMAIL")
        password = os.environ.get("YOUTUBE_PASSWORD")

        if email and password:
            print("[!] Auto-login credentials detected in environment variables.")
            login_success = auto_login(page, email, password)
            if not login_success:
                print("[-] Auto-login failed, exiting.")
                context.close()
                return
        else:
            print(
                "[!] [Event listener active] Please click Sign In in the opened browser and complete login..."
            )

            # ==================== Event 1: Listen for login-success DOM signal ====================
            try:
                avatar_selector: str = "button#avatar-btn"
                page.wait_for_selector(avatar_selector, timeout=120000)
                print(
                    "[+] [Event 1 triggered]: user avatar detected on page, "
                    "DOM-level login confirmed!"
                )
            except Exception:
                print("[-] Login timeout or success element not detected, exiting.")
                context.close()
                return

        # ==================== Event 2: Listen for core cookie write to memory ====================
        print(
            "[*] [Event listener active] Monitoring browser memory, "
            "waiting for core encrypted session cookies to sync..."
        )

        max_cookie_wait: int = 15
        start_time: float = time.time()
        cookies_captured: bool = False

        while time.time() - start_time < max_cookie_wait:
            if is_login(context):
                print(
                    "[+] [Event 2 triggered]: core security cookies "
                    "(__Secure-3PSID etc.) fully captured in memory!"
                )
                cookies_captured = True
                break
            time.sleep(0.5)

        if not cookies_captured:
            print(
                "[!] Warning: login detected but core security cookies did not fully sync "
                "within 15 s; forcing capture of existing fragments."
            )

        # Trigger instant write
        save_cookies(context, cookies_file="cookies.txt")
        print(
            "[+] State transition: cookie file written instantly, perfectly compatible with yt-dlp."
        )

        # ==================== Business Sleep ====================
        print("\n" + "=" * 40)
        print("[*] Module entering normal test sleep phase: waiting 3 minutes (180 s)...")
        print("=" * 40)
        time.sleep(180)

        # 5. After sleep, perform validity check and self-healing test
        print("\n[*] Sleep ended, starting validity assessment...")
        if not verify_cookies(page):
            success: bool = refresh_cookies(
                page, context, cookies_file="cookies.txt"
            )
            if success:
                print("[+] Self-healing successful! New cookies are ready.")
            else:
                print("[-] Self-healing failed.")
        else:
            print("[+] Session is intact, no refresh needed.")

        context.close()


if __name__ == "__main__":
    main()
