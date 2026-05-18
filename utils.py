import os
import sys
import time
from typing import Tuple, Optional
from playwright.sync_api import Playwright, BrowserContext, Page, BrowserType, sync_playwright

def detect_system_browser(playwright: Playwright) -> Tuple[BrowserType, Optional[str], Optional[str]]:
    """
    深度探测系统安装的浏览器，返回最适合的: (浏览器引擎, 通道名称, 绝对路径)
    """
    current_os = sys.platform

    # ==================== 1. WINDOWS 深度探测 ====================
    if current_os == "win32":
        # 探测 Chrome
        chrome_paths = [
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(os.environ.get("LocalAppData", ""), "Google\\Chrome\\Application\\chrome.exe")
        ]
        for p in chrome_paths:
            if os.path.exists(p):
                return playwright.chromium, "chrome", p

        # 探测 Edge
        edge_paths = [
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Microsoft\\Edge\\Application\\msedge.exe"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Microsoft\\Edge\\Application\\msedge.exe")
        ]
        for p in edge_paths:
            if os.path.exists(p):
                return playwright.chromium, "msedge", p

    # ==================== 2. MACOS 深度探测 ====================
    elif current_os == "darwin":
        if os.path.exists("/Applications/Google Chrome.app"):
            return playwright.chromium, "chrome", None
        if os.path.exists("/Applications/Microsoft Edge.app"):
            return playwright.chromium, "msedge", None
        # 极端情况：Mac 上只有自带的 Safari
        if os.path.exists("/Applications/Safari.app"):
            print("[*] 提示：未检测到主流 Chromium 浏览器，切换为 Mac 原生 WebKit (Safari)")
            return playwright.webkit, None, None

    # ==================== 3. LINUX 深度探测 ====================
    elif current_os.startswith("linux"):
        # 探测官方 Chrome
        if os.system("command -v google-chrome >/dev/null 2>&1") == 0:
            return playwright.chromium, "chrome", None
        # 探测开源 Chromium (Ubuntu/Debian 常见)
        for bin_name in ["chromium-browser", "chromium"]:
            if os.system(f"command -v {bin_name} >/dev/null 2>&1") == 0:
                return playwright.chromium, "chromium", None
        # 探测 Edge Linux 版
        if os.system("command -v microsoft-edge >/dev/null 2>&1") == 0:
            return playwright.chromium, "msedge", None
        # 探测 Firefox (许多 Linux 发行版如 Ubuntu 唯一默认自带的浏览器)
        if os.system("command -v firefox >/dev/null 2>&1") == 0:
            print("[*] 提示：未检测到 Chromium 系列浏览器，切换为 Linux 自带的 Firefox")
            return playwright.firefox, None, None

    # ==================== 4. 终极无赖兜底 ====================
    # 如果以上都失败了，强制指向本地 chromium，指望用户可能下载了 playwright 内核
    return playwright.chromium, "chrome", None


def initialize_browser(playwright: Playwright, headless: bool = False) -> Tuple[BrowserContext, Page]:
    """
    终极隐匿版初始化函数：完美绕过 Linux 下 Google 登录的“不安全浏览器”风控。
    """
    browser_type, channel, exe_path = detect_system_browser(playwright)
    
    # 1. 关键：注入核心防检测、去自动化特征的启动参数 (Chromium Arguments)
    ignore_arguments = [
        "--enable-automation", 
        "--disable-extensions"
    ]
    
    extra_arguments = [
        "--disable-blink-features=AutomationControlled", # 核心：禁用Blink引擎的自动化控制特征
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-infobars",                            # 隐藏正受到自动测试软件控制的提示条
        "--window-size=1280,720",
        "--lang=zh-CN,zh;q=0.9"                           # 伪装正常的语言头
    ]

    launch_args = {
        "headless": headless,
        "ignore_default_args": ignore_arguments,         # 忽略 Playwright 默认附带的暴露机器特征的参数
        "args": extra_arguments
    }
    
    if exe_path:
        launch_args["executable_path"] = exe_path
    elif channel:
        launch_args["channel"] = channel

    try:
        browser = browser_type.launch(**launch_args)
    except Exception as e:
        print(f"[-] 拉起本地浏览器失败: {e}")
        raise e
    
    # 2. 创建上下文并完全拟真常规用户环境
    context: BrowserContext = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720},
        locale="zh-CN",
        timezone_id="Asia/Shanghai"
    )
    
    # 3. 终极防御：在每个页面加载前，直接在 JS 运行时里将 webdriver 属性彻底抹除
    # 即使 Google 的极高权限加密脚本运行，也只能拿到 undefined，从而判定你是真人浏览器
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)
    
    page: Page = context.new_page()
    return context, page


def save_cookies(context: BrowserContext, cookies_file: str = "cookies.txt"):
    """
    从 Playwright 内存提取 Cookie，并将其转换为 yt-dlp 兼容的标准 Netscape 规范文本文件。
    输出路径由当前运行路径与指定的 cookies_file 拼接而成。
    """
    # 获取当前工作目录的绝对路径，并拼接文件名
    current_dir = os.path.abspath(os.path.dirname(__file__)) if '__file__' in locals() else os.getcwd()
    output_absolute_path = os.path.join(current_dir, cookies_file)
    
    playwright_cookies = context.cookies()
    
    try:
        with open(output_absolute_path, "w", encoding="utf-8") as f:
            # 写入 Netscape 规范的文件头
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# http://curl.haxx.se/rfc/cookie_spec.html\n")
            f.write("# This is a generated file! Do not edit.\n\n")
            
            for cookie in playwright_cookies:
                domain = cookie['domain']
                include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
                path = cookie['path']
                secure = "TRUE" if cookie['secure'] else "FALSE"
                # 如果没有过期时间，给予一个默认的一天后过期
                expires = int(cookie.get('expires', time.time() + 86400))
                name = cookie['name']
                value = cookie['value']
                
                # Netscape 格式是以 Tab 分隔的 7 列数据
                f.write(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
                
        print(f"[+] Cookie 已成功转换并保存至绝对路径: {output_absolute_path}")
    except Exception as e:
        print(f"[-] 写入 Cookie 文件失败: {e}")


def verify_cookies(page: Page) -> bool:
    """
    轻量级验证 Cookie 是否有效。
    通过无痕上下文访问订阅页，如果遭遇重定向到 accounts.google.com 则说明失效。
    """
    print("[*] 正在验证当前 Cookie 有效性...")
    try:
        # allow_redirects=False 或直接观察跳转后的 URL
        response = page.goto("https://www.youtube.com/feed/subscriptions")
        current_url = page.url
        
        if "accounts.google.com" in current_url:
            print("[-] 验证失败：Cookie 已失效，遭遇登录重定向。")
            return False
            
        # 兜底检查：页面内容是否包含登录按钮特征
        content = page.content()
        if 'href="https://accounts.google.com/ServiceLogin' in content:
            print("[-] 验证失败：页面显示未登录状态。")
            return False
            
        print("[+] 验证成功：Cookie 依然有效。")
        return True
    except Exception as e:
        print(f"[-] 验证过程中发生异常: {e}")
        return False


def refresh_cookies(page: Page, context: BrowserContext, output_path: str = "cookies.txt") -> bool:
    """
    自愈刷新函数：通过重新加载 YouTube 主页，触发浏览器内置的 Refresh Token 机制，
    然后重新提取并覆盖本地的 yt-dlp cookie 文件。
    """
    print("[*] 触发自愈机制：正在尝试刷新页面以获取新 Cookie...")
    try:
        # 回到主页或刷新，让浏览器内部 JS 自动完成合法的 Token 续期
        page.goto("https://www.youtube.com/")
        page.wait_for_load_state("networkidle") # 等待网络请求空闲
        
        # 再次更新本地文件
        save_cookies(context, output_path)
        
        # 再次闭环验证一次
        return verify_cookies(page)
    except Exception as e:
        print(f"[-] 刷新 Cookie 失败: {e}")
        return False


def is_login(context: BrowserContext) -> bool:
    """
    事件二级检查器：检查 Playwright 内存中是否已经集齐了判定登录成功的核心安全 Cookie
    """
    cookies = context.cookies()
    cookie_names = {c['name'] for c in cookies}
    
    # 判定登录成功的黄金三大件（少了它们，yt-dlp 就无法下载受限视频）
    required_core_cookies = {'__Secure-3PSID', 'SAPISID', 'SID'}
    
    # 如果这几个核心 Cookie 已经存在于内存中，说明异步跨域同步已完成
    return required_core_cookies.issubset(cookie_names)


# 全局 Playwright 实例，用于保持浏览器进程生命周期
_playwright_instance = None

def get_cookies() -> Tuple[BrowserContext, Page]:
    global _playwright_instance
    
    # 如果已有实例，先关闭避免冲突
    if _playwright_instance:
        try:
            _playwright_instance.stop()
        except Exception:
            pass
    
    _playwright_instance = sync_playwright().start()
    
    # 1. 启动伪装好的本地浏览器
    context, page = initialize_browser(_playwright_instance, headless=False)
    
    print(f"[*] 正在打开 YouTube 首页...")
    page.goto("https://www.youtube.com/")
    
    print("[!] [事件监听开启] 请在弹出的浏览器中点击登录并完成登录操作...")
    
    # ==================== 事件一：监听登录成功 DOM 信号 ====================
    try:
        avatar_selector = "button#avatar-btn"
        # wait_for_selector 本身就是一个高效的底层事件监听器
        # 它会在元素出现的那一毫秒立刻向下执行，最长等待 120 秒
        page.wait_for_selector(avatar_selector, timeout=120000)
        print("[+] 【事件一激活】: 网页端检测到用户头像，DOM 层登录确认成功！")
    except Exception:
        print("[-] 登录超时或未检测到登录成功的网页元素，程序退出。")
        context.close()
        _playwright_instance.stop()
        _playwright_instance = None
        return None, None

    # ==================== 事件二：监听核心 Cookie 写入内存 ====================
    print("[*] [事件监听开启] 正在监控浏览器内存，等待核心加密会话 Cookie 同步...")
    
    max_cookie_wait = 15  # 最高等待 15 秒用于后台跨域同步
    start_time = time.time()
    cookies_captured = False
    
    while time.time() - start_time < max_cookie_wait:
        if is_login(context):
            print("[+] 【事件二激活】: 核心安全 Cookie (__Secure-3PSID 等) 已完全落入内存！")
            cookies_captured = True
            break
        time.sleep(0.5)  # 以 500 毫秒的高频速率轮询内存状态
        
    if not cookies_captured:
        print("[!] 警告: 虽检测到登录，但核心安全 Cookie 在 15 秒内未完整同步，将强制抓取现有片段。")

    # 触发无延迟写入：一旦事件二满足，瞬间完成 Netscape 文本文件的生成
    save_cookies(context, cookies_file="cookies.txt")
    print("[+] 状态机流转：Cookie 文件写入已即时完成，完美适配 yt-dlp。")
    return context, page


def close_browser(context: BrowserContext = None):
    """
    关闭浏览器上下文及 Playwright 实例。
    应在所有任务完成后调用。
    """
    global _playwright_instance
    if context:
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




def main():
    with sync_playwright() as playwright:
        # 1. 启动伪装好的本地浏览器
        context, page = initialize_browser(playwright, headless=False)
        
        print(f"[*] 正在打开 YouTube 首页...")
        page.goto("https://www.youtube.com/")
        
        print("[!] [事件监听开启] 请在弹出的浏览器中点击登录并完成登录操作...")
        
        # ==================== 事件一：监听登录成功 DOM 信号 ====================
        try:
            avatar_selector = "button#avatar-btn"
            # wait_for_selector 本身就是一个高效的底层事件监听器
            # 它会在元素出现的那一毫秒立刻向下执行，最长等待 120 秒
            page.wait_for_selector(avatar_selector, timeout=120000)
            print("[+] 【事件一激活】: 网页端检测到用户头像，DOM 层登录确认成功！")
        except Exception:
            print("[-] 登录超时或未检测到登录成功的网页元素，程序退出。")
            context.close()
            return

        # ==================== 事件二：监听核心 Cookie 写入内存 ====================
        print("[*] [事件监听开启] 正在监控浏览器内存，等待核心加密会话 Cookie 同步...")
        
        max_cookie_wait = 15  # 最高等待 15 秒用于后台跨域同步
        start_time = time.time()
        cookies_captured = False
        
        while time.time() - start_time < max_cookie_wait:
            if is_login(context):
                print("[+] 【事件二激活】: 核心安全 Cookie (__Secure-3PSID 等) 已完全落入内存！")
                cookies_captured = True
                break
            time.sleep(0.5)  # 以 500 毫秒的高频速率轮询内存状态
            
        if not cookies_captured:
            print("[!] 警告: 虽检测到登录，但核心安全 Cookie 在 15 秒内未完整同步，将强制抓取现有片段。")

        # 触发无延迟写入：一旦事件二满足，瞬间完成 Netscape 文本文件的生成
        save_cookies(context, cookies_file="cookies.txt")
        print("[+] 状态机流转：Cookie 文件写入已即时完成，完美适配 yt-dlp。")

        # ==================== 业务休眠 ====================
        print("\n" + "="*40)
        print("[*] 模块进入正常的测试休眠阶段：等待 3 分钟 (180秒)...")
        print("="*40)
        time.sleep(180)
        
        # 5. 休眠结束后，进行有效性检查与自愈测试
        print("\n[*] 休眠结束，开始执行有效性评估...")
        if not verify_cookies(page):
            success = refresh_cookies(page, context, cookies_file="cookies.txt")
            if success:
                print("[+] 自愈成功！新 Cookie 已就绪。")
            else:
                print("[-] 自愈失败。")
        else:
            print("[+] 会话保存完好，无需刷新。")
            
        context.close()

if __name__ == "__main__":
    main()