"""Unit tests for main.py"""
from __future__ import annotations

import unittest
from unittest import mock
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import BatchDownloader


class TestBatchDownloader(unittest.TestCase):
    def test_load_config_missing(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            BatchDownloader(config_path="nonexistent.yml")
        self.assertEqual(cm.exception.code, 1)

    def test_parse_task_string(self) -> None:
        filename, mode = BatchDownloader.parse_task("my_song", {"mode": "audio"})
        self.assertEqual(filename, "my_song")
        self.assertEqual(mode, "audio")

    def test_parse_task_dict(self) -> None:
        filename, mode = BatchDownloader.parse_task(
            {"filename": "my_video", "mode": "video"}, {"mode": "audio"}
        )
        self.assertEqual(filename, "my_video")
        self.assertEqual(mode, "video")

    def test_parse_task_dict_fallback(self) -> None:
        filename, mode = BatchDownloader.parse_task(
            {"filename": "fallback"}, {"mode": "audio"}
        )
        self.assertEqual(filename, "fallback")
        self.assertEqual(mode, "audio")

    def test_parse_task_unsupported(self) -> None:
        filename, mode = BatchDownloader.parse_task(12345, {"mode": "audio"})
        self.assertIsNone(filename)
        self.assertEqual(mode, "audio")

    def test_normalize_filename_audio(self) -> None:
        result = BatchDownloader.normalize_filename("song.opus", "audio")
        self.assertEqual(result, "song")

    def test_normalize_filename_video(self) -> None:
        result = BatchDownloader.normalize_filename("movie.mp4", "video")
        self.assertEqual(result, "movie")

    def test_normalize_filename_none(self) -> None:
        result = BatchDownloader.normalize_filename(None, "audio")
        self.assertIsNone(result)

    def test_normalize_filename_no_extension(self) -> None:
        result = BatchDownloader.normalize_filename("clean_name", "audio")
        self.assertEqual(result, "clean_name")

    @mock.patch("main.trigger_github_action")
    @mock.patch("main.get_cookies")
    @mock.patch("os.path.exists")
    def test_run_batch(
        self,
        mock_exists: mock.MagicMock,
        mock_get_cookies: mock.MagicMock,
        mock_trigger: mock.MagicMock,
    ) -> None:
        mock_exists.return_value = True  # cookies.txt exists
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False
        ) as tmp:
            tmp.write(
                """
config:
  mode: audio
  storage: gofile
  branch: main
  verbose: false

tasks:
  "https://youtu.be/abc": "song_one"
  "https://youtu.be/def":
    filename: "song_two"
    mode: video
"""
            )
            tmp.flush()
            downloader = BatchDownloader(config_path=tmp.name)
            downloader.run()
            self.assertEqual(mock_trigger.call_count, 2)
        os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
