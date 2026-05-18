from __future__ import annotations

from abc import ABC, abstractmethod
import os
from typing import Optional


class StorageProvider(ABC):
    def __init__(self, config) -> None:
        # Path is configurable and supports tilde expansion
        raw_path: str = config.get("Storage", "download_path", fallback="~/Downloads")
        self.download_dir: str = os.path.expanduser(raw_path)

    @abstractmethod
    def handle_result(self, logs: str, token: Optional[str] = None) -> None:
        """Parse logs and perform download / cleanup."""
        raise NotImplementedError
