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
        # Place a valid non-empty media-like file so download verification passes
        with open(os.path.join(provider.download_dir, "test.opus"), "wb") as f:
            f.write(b"OggS\x00\x02fake-opus-content")
        provider.handle_result(logs, token="fake_token")
        calls = mock_subprocess.call_args_list
        self.assertEqual(len(calls), 3)
        # First call: rclone copy, then deletefile, then lsjson verification
        self.assertIn("copy", calls[0][0][0])
        self.assertIn("deletefile", calls[1][0][0])
        self.assertIn("lsjson", calls[2][0][0])

    @mock.patch("providers.onedrive.time.sleep")
    @mock.patch("builtins.print")
    @mock.patch("providers.onedrive.subprocess.run")
    def test_copy_failure_recovers_on_retry(
        self,
        mock_subprocess: mock.MagicMock,
        mock_print: mock.MagicMock,
        mock_sleep: mock.MagicMock,
    ) -> None:
        from subprocess import CalledProcessError

        logs: str = (
            "---RESULT_START---\n"
            "ITEM_ID: i789\n"
            "FILE_NAME: test.opus\n"
            "---RESULT_END---"
        )
        provider = OnedriveProvider(_make_config())
        copy_calls = {"n": 0}

        def fake_run(cmd, *args, **kwargs):
            if "copy" in cmd:
                copy_calls["n"] += 1
                if copy_calls["n"] == 1:
                    raise CalledProcessError(1, cmd)
                with open(
                    os.path.join(provider.download_dir, "test.opus"), "wb"
                ) as f:
                    f.write(b"OggS\x00\x02fake-opus-content")
                return mock.MagicMock(returncode=0)
            if "deletefile" in cmd:
                return mock.MagicMock(returncode=0)
            if "lsjson" in cmd:
                return mock.MagicMock(returncode=1, stdout="")
            return mock.MagicMock(returncode=0)

        mock_subprocess.side_effect = fake_run
        provider.handle_result(logs, token="fake_token")
        printed = " ".join(str(call) for call in mock_print.call_args_list)
        self.assertIn("attempt 2", printed)
        self.assertIn("Retrieval successful", printed)
        # copy x2, then deletefile (cleanup), then lsjson (verify removal)
        cmds = [c[0][0] for c in mock_subprocess.call_args_list]
        self.assertEqual(cmds[2][1], "deletefile")

    @mock.patch("providers.onedrive.time.sleep")
    @mock.patch("builtins.print")
    @mock.patch("providers.onedrive.subprocess.run")
    def test_copy_failure_still_cleans_cloud(
        self,
        mock_subprocess: mock.MagicMock,
        mock_print: mock.MagicMock,
        mock_sleep: mock.MagicMock,
    ) -> None:
        from subprocess import CalledProcessError

        logs: str = (
            "---RESULT_START---\n"
            "ITEM_ID: i789\n"
            "FILE_NAME: test.opus\n"
            "---RESULT_END---"
        )
        mock_subprocess.side_effect = [
            CalledProcessError(1, ["rclone", "copy"]),  # attempt 1
            CalledProcessError(1, ["rclone", "copy"]),  # attempt 2
            CalledProcessError(1, ["rclone", "copy"]),  # attempt 3
            CalledProcessError(1, ["rclone", "copy"]),  # attempt 4
            CalledProcessError(1, ["rclone", "copy"]),  # attempt 5
            mock.MagicMock(returncode=0),  # deletefile succeeds
            mock.MagicMock(returncode=1, stdout=""),  # lsjson confirms removal
        ]
        provider = OnedriveProvider(_make_config())
        provider.handle_result(logs, token="fake_token")
        printed = " ".join(str(call) for call in mock_print.call_args_list)
        self.assertIn("Failed to retrieve", printed)
        self.assertIn("Cloud file removed", printed)
        cmds = [c[0][0] for c in mock_subprocess.call_args_list]
        self.assertEqual(cmds[5][1], "deletefile")

    @mock.patch("builtins.print")
    @mock.patch("providers.onedrive.subprocess.run")
    def test_cleanup_failure_warns(
        self, mock_subprocess: mock.MagicMock, mock_print: mock.MagicMock
    ) -> None:
        from subprocess import CalledProcessError

        logs: str = (
            "---RESULT_START---\n"
            "ITEM_ID: i789\n"
            "FILE_NAME: test.opus\n"
            "---RESULT_END---"
        )
        mock_subprocess.side_effect = [
            mock.MagicMock(returncode=0),  # copy succeeds
            CalledProcessError(1, ["rclone", "deletefile"]),  # delete attempt 1
            CalledProcessError(1, ["rclone", "deletefile"]),  # delete attempt 2
            mock.MagicMock(returncode=0, stdout='[{"Name": "test.opus"}]'),  # still there
        ]
        provider = OnedriveProvider(_make_config())
        with open(os.path.join(provider.download_dir, "test.opus"), "wb") as f:
            f.write(b"OggS\x00\x02fake-opus-content")
        provider.handle_result(logs, token="fake_token")
        printed = " ".join(str(call) for call in mock_print.call_args_list)
        self.assertIn("Retrieval successful", printed)
        self.assertIn("may still exist", printed)

    @mock.patch("providers.onedrive.time.sleep")
    @mock.patch("builtins.print")
    @mock.patch("providers.onedrive.subprocess.run")
    def test_zero_byte_download_rejected(
        self,
        mock_subprocess: mock.MagicMock,
        mock_print: mock.MagicMock,
        mock_sleep: mock.MagicMock,
    ) -> None:
        logs: str = (
            "---RESULT_START---\n"
            "ITEM_ID: i789\n"
            "FILE_NAME: test.opus\n"
            "---RESULT_END---"
        )
        provider = OnedriveProvider(_make_config())
        # Simulate rclone "succeeding" but leaving an empty file behind
        open(os.path.join(provider.download_dir, "test.opus"), "wb").close()
        provider.handle_result(logs, token="fake_token")
        printed = " ".join(str(call) for call in mock_print.call_args_list)
        self.assertIn("verification failed", printed)
        self.assertNotIn("Retrieval successful", printed)
        # Broken cloud copy must still be cleaned up
        delete_calls = [
            c for c in mock_subprocess.call_args_list if "deletefile" in c[0][0]
        ]
        self.assertEqual(len(delete_calls), 1)

    @mock.patch("providers.onedrive.time.sleep")
    @mock.patch("builtins.print")
    @mock.patch("providers.onedrive.subprocess.run")
    def test_html_error_page_rejected(
        self,
        mock_subprocess: mock.MagicMock,
        mock_print: mock.MagicMock,
        mock_sleep: mock.MagicMock,
    ) -> None:
        logs: str = (
            "---RESULT_START---\n"
            "ITEM_ID: i789\n"
            "FILE_NAME: test.opus\n"
            "---RESULT_END---"
        )
        provider = OnedriveProvider(_make_config())
        # OneDrive returns an HTML error page (HTTP 200) for broken items
        with open(os.path.join(provider.download_dir, "test.opus"), "wb") as f:
            f.write(b"<html><body>An unexpected error has occurred.</body></html>")
        provider.handle_result(logs, token="fake_token")
        printed = " ".join(str(call) for call in mock_print.call_args_list)
        self.assertIn("verification failed", printed)
        self.assertNotIn("Retrieval successful", printed)
        delete_calls = [
            c for c in mock_subprocess.call_args_list if "deletefile" in c[0][0]
        ]
        self.assertEqual(len(delete_calls), 1)

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
