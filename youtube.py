import argparse
import configparser
import subprocess
import time
import sys
import os
from providers.aliyun import AliyunProvider
from providers.gofile import GofileProvider

class ProviderFactory:
    @staticmethod
    def get_provider(name, config):
        if name == "aliyun": return AliyunProvider(config)
        if name == "gofile": return GofileProvider(config)
        raise ValueError(f"Unknown provider: {name}")

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.returncode

def main():
    parser = argparse.ArgumentParser(description="YouTube 解密下载框架")
    parser.add_argument("url", help="YouTube URL")
    parser.add_argument("-b", "--branch", default="main", help="分支名")
    parser.add_argument("-p", "--provider", default="aliyun", choices=["aliyun", "gofile"])
    parser.add_argument("-t", "--token", help="Token (阿里云需 refresh_token)")
    parser.add_argument("--type", default="audio", choices=["audio", "video"])
    
    args = parser.parse_args()
    config = configparser.ConfigParser()
    config.read('config.ini')

    # 1. 触发指定分支
    print(f"🚀 在分支 [{args.branch}] 启动解密任务...")
    dispatch_cmd = (
        f"gh workflow run download.yml --ref {args.branch} "
        f"-f video_url='{args.url}' -f download_type='{args.type}' "
        f"-f storage_provider='{args.provider}' -f provider_token='{args.token or ''}'"
    )
    run_cmd(dispatch_cmd)

    # 2. 获取 Run ID 并监控
    time.sleep(5)
    run_id, _ = run_cmd(f"gh run list --workflow=download.yml --branch {args.branch} --limit 1 --json databaseId --jq '.[0].databaseId'")
    print(f"📡 任务 ID: {run_id}，等待云端处理...")
    run_cmd(f"gh run watch {run_id}")

    # 3. 提取日志并执行策略
    logs, _ = run_cmd(f"gh run view {run_id} --log")
    try:
        provider = ProviderFactory.get_provider(args.provider, config)
        provider.handle_result(logs, args.token)
    except Exception as e:
        print(f"⚠️ 后续处理异常: {e}")
    finally:
        run_cmd(f"gh run delete {run_id}")
        print("✨ 痕迹已清理。")

if __name__ == "__main__":
    main()