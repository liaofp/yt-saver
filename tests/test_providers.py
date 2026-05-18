"""Unit tests for providers/ modules"""
from __future__ import annotations

import unittest
from unittest import mock
import sys
import os
import tempfile
import configparser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.base import StorageProvider
from providers.aliyun import AliyunProvider
from providers.onedrive import OnedriveProvider
from providers.gofile import GofileProvider
from providers.aliclient import AlipanClient
from providers.odclient import OneDriveClient


def _make_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.add_section("Storage")
    cfg.set("Storage", "download_path", tempfile.mkdtemp())
    return cfg


class TestStorageProvider(unittest.TestCase):
    def test_download_dir_expansion(self) -> None:
        cfg = configparser.ConfigParser()
        cfg.add_section("Storage")
        cfg.set("Storage", "download_path", "~/Downloads")
        provider = AliyunProvider(cfg)
        self.assertTrue(provider.download_dir.endswith("Downloads"))
        self.assertFalse(provider.download_dir.startswith("~"))


class TestAliyunProvider(unittest.TestCase):
    @mock.patch("providers.aliyun.AlipanClient")
    def test_handle_result(self, mock_client_cls: mock.MagicMock) -> None:
        logs: str = (
            "---RESULT_START---\n"
            "DRIVE_ID: d123\n"
            "FILE_ID: f456\n"
            "FILE_NAME: test.opus\n"
            "---RESULT_END---"
        )
        provider = AliyunProvider(_make_config())
        provider.handle_result(logs, token="fake_token")
        mock_client_cls.assert_called_once_with(
            refresh_token="fake_token", client_id="25dzX3vbYq8VNIpa"
        )
        mock_client_cls.return_value.download_file.assert_called_once()
        mock_client_cls.return_value.delete_file.assert_called_once()

    def test_handle_result_no_match(self) -> None:
        provider = AliyunProvider(_make_config())
        # Should return silently without error
        provider.handle_result("no result block here", token="fake_token")


class TestOnedriveProvider(unittest.TestCase):
    @mock.patch("providers.onedrive.subprocess.run")
    def test_handle_result(self, mock_subprocess: mock.MagicMock) -> None:
        logs: str = (
            "---RESULT_START---\n"
            "ITEM_ID: i789\n"
            "FILE_NAME: test.opus\n"
            "---RESULT_END---"
        )
        provider = OnedriveProvider(_make_config())
        provider.handle_result(logs, token="fake_token")
        calls = mock_subprocess.call_args_list
        self.assertTrue(len(calls) >= 2)
        # First call: rclone copy
        self.assertIn("copy", calls[0][0][0])
        # Second call: rclone deletefile
        self.assertIn("deletefile", calls[1][0][0])

    def test_handle_result_no_match(self) -> None:
        provider = OnedriveProvider(_make_config())
        provider.handle_result("no result block", token="fake_token")


class TestGofileProvider(unittest.TestCase):
    @mock.patch("builtins.print")
    def test_handle_result(self, mock_print: mock.MagicMock) -> None:
        logs: str = "---RESULT_START---\nDL_URL: https://gofile.io/d/abc123\n---RESULT_END---"
        provider = GofileProvider(_make_config())
        provider.handle_result(logs)
        printed = " ".join(str(call) for call in mock_print.call_args_list)
        self.assertIn("gofile.io", printed.lower())

    @mock.patch("builtins.print")
    def test_handle_result_no_match(self, mock_print: mock.MagicMock) -> None:
        provider = GofileProvider(_make_config())
        provider.handle_result("no url here")
        printed = " ".join(str(call) for call in mock_print.call_args_list)
        self.assertIn("failed", printed.lower())


class TestAlipanClient(unittest.TestCase):
    @mock.patch("providers.aliclient.requests.Session")
    def test_init_updates_token(self, mock_session_cls: mock.MagicMock) -> None:
        mock_session = mock_session_cls.return_value
        mock_session.post.return_value.json.side_effect = [
            {"access_token": "acc", "refresh_token": "ref"},
            {"resource_drive_id": "d123"},
        ]
        client = AlipanClient(refresh_token="tok", client_id="cid")
        self.assertEqual(client.access_token, "acc")
        self.assertEqual(client.refresh_token, "ref")

    @mock.patch("providers.aliclient.requests.Session")
    def test_get_headers(self, mock_session_cls: mock.MagicMock) -> None:
        mock_session = mock_session_cls.return_value
        mock_session.post.return_value.json.side_effect = [
            {"access_token": "acc", "refresh_token": "ref"},
            {"resource_drive_id": "d123"},
        ]
        client = AlipanClient(refresh_token="tok")
        headers = client.get_headers()
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Bearer "))


class TestOneDriveClient(unittest.TestCase):
    def test_parse_raw_token(self) -> None:
        client = OneDriveClient("raw_access_token_123")
        self.assertEqual(client.access_token, "raw_access_token_123")

    def test_parse_json_token(self) -> None:
        client = OneDriveClient('{"access_token":"abc","refresh_token":"def"}')
        self.assertEqual(client.access_token, "abc")
        self.assertEqual(client.refresh_token, "def")

    def test_parse_rclone_ini(self) -> None:
        ini: str = "[tmp_od]\nclient_id = myid\nclient_secret = mysec\ntoken = {\"access_token\":\"tok\",\"refresh_token\":\"ref\"}\n"
        client = OneDriveClient(ini)
        self.assertEqual(client.access_token, "tok")
        self.assertEqual(client.refresh_token, "ref")
        self.assertEqual(client.client_id, "myid")
        self.assertEqual(client.client_secret, "mysec")

    def test_empty_token_raises(self) -> None:
        with self.assertRaises(Exception) as cm:
            OneDriveClient("")
        self.assertIn("empty", str(cm.exception).lower())


if __name__ == "__main__":
    unittest.main()
