import yaml
import sys
import os
import time
# 导入原脚本中的核心触发逻辑
from youtube import trigger_github_action


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
          1. 字符串: "filename.opus"  -> 使用指定文件名，mode 继承全局
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

        total = len(tasks)
        print(f"📂 发现 {total} 个任务，准备开始批量处理...\n")

        for i, (url, task_value) in enumerate(tasks.items(), 1):
            filename, mode = self.parse_task(task_value, global_cfg)

            # 如果未指定文件名，使用当前服务器时间毫秒戳
            if not filename:
                filename = f"{int(time.time() * 1000)}"

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
                # trigger_github_action 在失败时调用 sys.exit(1)，捕获后继续下一任务
                print(f"❌ 任务 {i} 触发失败，跳过。\n")
                continue
            except Exception as e:
                print(f"❌ 任务 {i} 出错: {e}\n")
                continue

        print("✨ 所有批量任务处理完毕。")


if __name__ == "__main__":
    # 确保安装了 pyyaml: pip install pyyaml
    downloader = BatchDownloader()
    downloader.run()
