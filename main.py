import yaml
import sys
import os
import time
# 导入原脚本中的核心触发逻辑
from youtube import trigger_github_action
from utils import get_cookies, verify_cookies, refresh_cookies
from playwright.sync_api import BrowserContext, Page


class BatchDownloader:
    def __init__(self, config_path: str = "tasks.yml"):
        self.config_path = config_path
        self.data = self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_path):
            print(f"❌ 错误: 找不到配置文件 {self.config_path}")
            sys.exit(1)
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    @staticmethod
    def parse_task(task_value, global_cfg):
        """
        解析单个任务的配置。
        支持两种格式：
          1. 字符串: "filename"  -> 使用指定文件名（不带扩展名），mode 继承全局
          2. 字典:   {filename: "xxx", mode: "audio"} -> 逐项解析，缺失项继承全局
        返回: (filename, mode)
        """
        if isinstance(task_value, str):
            # 简单格式：字符串直接作为文件名
            filename = task_value.strip() if task_value.strip() else None
            mode = global_cfg.get("mode", "audio")
        elif isinstance(task_value, dict):
            # 完整格式：从字典中提取，缺失项使用全局默认值
            filename = task_value.get("filename")
            if filename and isinstance(filename, str):
                filename = filename.strip() or None
            mode = task_value.get("mode", global_cfg.get("mode", "audio"))
        else:
            # 不支持的类型，全部使用默认值
            filename = None
            mode = global_cfg.get("mode", "audio")

        return filename, mode

    @staticmethod
    def normalize_filename(filename, mode):
        """
        规范化文件名：
        - 去掉用户可能误填的扩展名（由 yt-dlp 根据 mode 自动决定）
        - audio -> .opus, video -> .mp4
        返回不带扩展名的纯文件名（用于 yt-dlp -o 模板）
        """
        if not filename:
            return None

        # 去掉常见的扩展名后缀（用户可能误填）
        # 音频扩展名
        for ext in ['.opus', '.mp3', '.m4a', '.wav', '.flac', '.ogg', '.webm']:
            if filename.lower().endswith(ext):
                filename = filename[:-len(ext)]
                break
        # 视频扩展名
        for ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm']:
            if filename.lower().endswith(ext):
                filename = filename[:-len(ext)]
                break

        return filename

    def run(self):
        global_cfg = self.data.get("config", {})
        tasks = self.data.get("tasks", {})

        if not tasks:
            print("! 没有发现待处理的任务。")
            return

        # 前置校验：阿里云盘必须配置 token
        storage = global_cfg.get("storage", "onedrive")
        token = global_cfg.get("token", None)
        if storage == "aliyun" and not token:
            print("❌ 错误: 存储后端为 'aliyun' 时，必须在 config 中配置 token。")
            sys.exit(1)

        # 检查本地是否已有 cookies.txt，没有则引导用户登录
        context = None
        page = None
        if not os.path.exists("cookies.txt"):
            print("[!] 未检测到 cookies.txt，需要登录 YouTube 获取 Cookie...")
            try:
                context, page = get_cookies()
            except Exception as e:
                print(f"❌ 获取 Cookie 失败: {e}")
                sys.exit(1)
        else:
            print("[+] 检测到已存在的 cookies.txt，跳过登录步骤。")

        total = len(tasks)
        print(f"📂 发现 {total} 个任务，准备开始批量处理...\n")

        for i, (url, task_value) in enumerate(tasks.items(), 1):
            # 每完成两个任务后，检测 cookies 是否还有效
            if i > 1 and (i - 1) % 2 == 0:
                if context and page:
                    print("[*] 已完成两个任务，正在检测 Cookie 有效性...")
                    if not verify_cookies(page):
                        print("[!] Cookie 已失效，尝试自愈刷新...")
                        if not refresh_cookies(page, context, output_path="cookies.txt"):
                            print("[-] 自愈刷新失败，需要重新登录...")
                            try:
                                context.close()
                            except Exception:
                                pass
                            try:
                                context, page = get_cookies()
                            except Exception as e:
                                print(f"❌ 重新获取 Cookie 失败: {e}")
                                sys.exit(1)
                else:
                    # 如果之前没有浏览器上下文（比如用户预先提供了 cookies.txt），
                    # 此时无法验证，跳过检测
                    pass

            filename, mode = self.parse_task(task_value, global_cfg)

            # 如果未指定文件名，使用当前服务器时间毫秒戳
            if not filename:
                filename = f"{int(time.time() * 1000)}"
            else:
                # 用户指定了文件名，去掉可能误填的扩展名
                filename = self.normalize_filename(filename, mode)

            print(f"--- [任务 {i}/{total}] URL: {url} ---")
            print(f"    模式: {mode} | 文件名: {filename}")

            # 动态模拟 argparse 对象
            class Args:
                def __init__(self):
                    self.url = url
                    self.mode = mode
                    self.storage = storage
                    self.branch = global_cfg.get("branch", "main")
                    self.verbose = global_cfg.get("verbose", False)
                    self.token = token
                    self.path = global_cfg.get("path", "/")
                    self.filename = filename

            current_args = Args()

            try:
                # 调用 youtube.py 中的核心触发函数
                trigger_github_action(current_args)
                print(f"✅ 任务 {i} 完成回传。\n")
            except SystemExit:
                # trigger_github_action 在失败时调用 sys.exit(1)，任务失败立即终止程序
                print(f"❌ 任务 {i} 触发失败，批量任务已终止。")
                sys.exit(1)
            except Exception as e:
                print(f"❌ 任务 {i} 出错: {e}")
                print("批量任务已终止。")
                sys.exit(1)

        # 所有任务完成后，关闭浏览器并删除 cookies.txt
        if context:
            try:
                context.close()
                print("[+] 浏览器已关闭。")
            except Exception as e:
                print(f"[!] 关闭浏览器时出错: {e}")

        if os.path.exists("cookies.txt"):
            try:
                os.remove("cookies.txt")
                print("[+] cookies.txt 已删除。")
            except Exception as e:
                print(f"[!] 删除 cookies.txt 时出错: {e}")

        print("✨ 所有批量任务处理完毕。")


if __name__ == "__main__":
    # 确保安装了 pyyaml: pip install pyyaml
    downloader = BatchDownloader()
    downloader.run()
