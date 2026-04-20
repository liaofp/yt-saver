from abc import ABC, abstractmethod
import os

class StorageProvider(ABC):
    def __init__(self, config):
        # 路径可配置，支持波浪号扩展
        raw_path = config.get('Storage', 'download_path', fallback='~/Downloads')
        self.download_dir = os.path.expanduser(raw_path)

    @abstractmethod
    def handle_result(self, logs, token=None):
        """解析日志并执行下载/清理"""
        pass