"""
Integration tests for yt-saver.

These tests simulate the full end-to-end flow:
1. GitHub Actions workflow completes and prints a result block.
2. Local provider parses the result block from logs.
3. Provider downloads the file and cleans up the cloud copy.

All external network calls and subprocess commands are mocked.
"""
from __future__ import annotations

import unittest
from unittest import mock
import sys
import os
import tempfile
import configparser
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.aliyun import AliyunProvider
from providers.onedrive import OnedriveProvider
from providers.gofile import GofileProvider
from providers.aliclient import AlipanClient
from providers.odclient import OneDriveClient
import youtube
from main import BatchDownloader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(download_path: str | None = None) -> configparser.ConfigParser:
    """Build a ConfigParser with an optional custom download path."""
    cfg = configparser.ConfigParser()
    cfg.add_section("Storage")
    cfg.set("Storage", "download_path", download_path or tempfile.mkdtemp())
    return cfg


def _aliyun_logs(
    drive_id: str = "d123", file_id: str = "f456", file_name: str = "test.opus"
) -> str:
    """Return a simulated GitHub Actions log for Aliyun Drive."""
    return (
        "[2024-01-01T00:00:00Z] some workflow step\n"
        "---RESULT_START---\n"
        f"DRIVE_ID: {drive_id}\n"
        f"FILE_ID: {file_id}\n"
        f"FILE_NAME: {file_name}\n"
        "---RESULT_END---\n"
        "[2024-01-01T00:00:01Z] cleanup step\n"
    )


def _onedrive_logs(
    item_id: str = "i789", file_name: str = "test.opus"
) -> str:
    """Return a simulated GitHub Actions log for OneDrive."""
    return (
        "[2024-01-01T00:00:00Z] some workflow step\n"
        "---RESULT_START---\n"
        f"ITEM_ID: {item_id}\n"
        f"FILE_NAME: {file_name}\n"
        "---RESULT_END---\n"
        "[2024-01-01T00:00:01Z] cleanup step\n"
    )


def _gofile_logs(dl_url: str = "https://gofile.io/d/abc123") -> str:
    """Return a simulated GitHub Actions log for GoFile."""
    return (
        "[2024-01-01T00:00:00Z] some workflow step\n"
        "---RESULT_START---\n"
        f"DL_URL: {dl_url}\n"
        "---RESULT_END---\n"
        "[2024-01-01T00:00:01Z] cleanup step\n"
    )


# ---------------------------------------------------------------------------
# End-to-end provider flows
# ---------------------------------------------------------------------------

class TestAliyunEndToEnd(unittest.TestCase):
    """Full flow: Aliyun logs -> AliyunProvider -> AlipanClient download -> delete"""

    @mock.patch("providers.aliclient.requests.Session")
    @mock.patch("providers.aliyun.os.makedirs")
    def test_full_retrieval_and_cleanup(
        self,
        mock_makedirs: mock.MagicMock,
        mock_session_cls: mock.MagicMock,
    ) -> None:
        mock_session = mock_session_cls.return_value

        # All session.post calls in sequence:
        # 1. token refresh, 2. drive info, 3. get_file_info, 4. get_download_url, 5. delete_file
        mock_session.post.return_value.json.side_effect = [
            {"access_token": "acc", "refresh_token": "ref"},
            {"resource_drive_id": "d123"},
            {"name": "test.opus"},
            {"url": "https://example.com/dl"},
            {},
        ]
        mock_session.post.return_value.status_code = 204

        mock_cm = mock.MagicMock()
        mock_cm.iter_content.return_value = [b"fake audio data"]
        mock_cm.raise_for_status.return_value = None
        mock_session.get.return_value.__enter__ = mock.MagicMock(
            return_value=mock_cm
        )
        mock_session.get.return_value.__exit__ = mock.MagicMock(
            return_value=False
        )

        cfg = _make_config()
        provider = AliyunProvider(cfg)
        logs = _aliyun_logs(
            drive_id="d123", file_id="f456", file_name="test.opus"
        )
        provider.handle_result(logs, token="fake_refresh_token")

        # Verify directory creation
        mock_makedirs.assert_called_once()
        # Verify delete was called (look for call to delete endpoint)
        post_calls = mock_session.post.call_args_list
        delete_calls = [
            c for c in post_calls if "delete" in str(c.args[0] if c.args else "")
        ]
        self.assertTrue(
            len(delete_calls) > 0
            or any("delete" in str(c) for c in post_calls)
        )


class TestOnedriveEndToEnd(unittest.TestCase):
    """Full flow: OneDrive logs -> OnedriveProvider -> rclone copy -> rclone deletefile"""

    @mock.patch("providers.onedrive.subprocess.run")
    def test_full_retrieval_and_cleanup(
        self, mock_subprocess: mock.MagicMock
    ) -> None:
        cfg = _make_config()
        provider = OnedriveProvider(cfg)
        logs = _onedrive_logs(item_id="i789", file_name="test.opus")
        provider.handle_result(logs, token="fake_token")

        calls = mock_subprocess.call_args_list
        self.assertEqual(len(calls), 2)

        # First call: rclone copy
        self.assertEqual(calls[0][0][0][0], "rclone")
        self.assertIn("copy", calls[0][0][0])

        # Second call: rclone deletefile
        self.assertEqual(calls[1][0][0][0], "rclone")
        self.assertIn("deletefile", calls[1][0][0])

    @mock.patch("providers.onedrive.subprocess.run")
    def test_rclone_failure_handled(
        self, mock_subprocess: mock.MagicMock
    ) -> None:
        mock_subprocess.side_effect = [
            mock.MagicMock(),  # copy succeeds
            Exception("rclone deletefile failed"),  # delete throws (but is caught via check=True)
        ]
        # Actually subprocess.run with check=True raises CalledProcessError
        from subprocess import CalledProcessError
        mock_subprocess.side_effect = [
            mock.MagicMock(returncode=0),
            CalledProcessError(1, ["rclone", "deletefile"]),
        ]

        cfg = _make_config()
        provider = OnedriveProvider(cfg)
        logs = _onedrive_logs()
        # Should not raise unhandled exception
        provider.handle_result(logs, token="fake_token")


class TestGofileEndToEnd(unittest.TestCase):
    """Full flow: GoFile logs -> GofileProvider -> prints download link"""

    @mock.patch("builtins.print")
    def test_prints_download_link(self, mock_print: mock.MagicMock) -> None:
        cfg = _make_config()
        provider = GofileProvider(cfg)
        logs = _gofile_logs(dl_url="https://gofile.io/d/xyz789")
        provider.handle_result(logs)

        printed = " ".join(str(call) for call in mock_print.call_args_list)
        self.assertIn("gofile.io/d/xyz789", printed)
        self.assertIn("upload successful", printed.lower())


# ---------------------------------------------------------------------------
# monitor_workflow integration
# ---------------------------------------------------------------------------

class TestMonitorWorkflowIntegration(unittest.TestCase):
    """Simulate the full monitor_workflow function with mocked gh CLI calls."""

    @mock.patch("youtube.run_command")
    @mock.patch("youtube.subprocess.run")
    @mock.patch("youtube.OnedriveProvider")
    def test_monitor_onedrive_full(
        self,
        mock_provider_cls: mock.MagicMock,
        mock_subprocess: mock.MagicMock,
        mock_run_command: mock.MagicMock,
    ) -> None:
        """Simulate: workflow starts -> watch -> logs -> provider handles -> delete run."""
        mock_run_command.side_effect = [
            # 1. gh run list -> returns run id
            ('[{"databaseId": 99999}]', 0),
            # 2. gh run view --log -> returns OneDrive result block
            (_onedrive_logs(item_id="i111", file_name="song.opus"), 0),
            # 3. gh run delete -> success
            ("", 0),
        ]

        youtube.monitor_workflow("main", "onedrive", "fake_od_token", verbose=False)

        # Verify gh run watch was invoked
        mock_subprocess.assert_called_once()
        self.assertIn("gh run watch 99999", str(mock_subprocess.call_args))

        # Verify provider was instantiated and called
        mock_provider_cls.return_value.handle_result.assert_called_once()
        args, _ = mock_provider_cls.return_value.handle_result.call_args
        self.assertIn("---RESULT_START---", args[0])

        # Verify delete command was issued
        delete_calls = [c for c in mock_run_command.call_args_list if "gh run delete" in str(c)]
        self.assertEqual(len(delete_calls), 1)

    @mock.patch("youtube.run_command")
    @mock.patch("youtube.subprocess.run")
    @mock.patch("youtube.AliyunProvider")
    def test_monitor_aliyun_full(
        self,
        mock_provider_cls: mock.MagicMock,
        mock_subprocess: mock.MagicMock,
        mock_run_command: mock.MagicMock,
    ) -> None:
        mock_run_command.side_effect = [
            ('[{"databaseId": 88888}]', 0),
            (_aliyun_logs(drive_id="d222", file_id="f333", file_name="song.opus"), 0),
            ("", 0),
        ]

        youtube.monitor_workflow("main", "aliyun", "fake_ali_token", verbose=False)

        mock_provider_cls.return_value.handle_result.assert_called_once()
        delete_calls = [c for c in mock_run_command.call_args_list if "gh run delete" in str(c)]
        self.assertEqual(len(delete_calls), 1)

    @mock.patch("youtube.run_command")
    @mock.patch("youtube.subprocess.run")
    def test_monitor_gofile_full(
        self, mock_subprocess: mock.MagicMock, mock_run_command: mock.MagicMock
    ) -> None:
        mock_run_command.side_effect = [
            ('[{"databaseId": 77777}]', 0),
            (_gofile_logs(dl_url="https://gofile.io/d/go999"), 0),
            ("", 0),
        ]

        youtube.monitor_workflow("main", "gofile", None, verbose=False)

        delete_calls = [c for c in mock_run_command.call_args_list if "gh run delete" in str(c)]
        self.assertEqual(len(delete_calls), 1)

    @mock.patch("youtube.run_command")
    def test_monitor_no_run_found(self, mock_run_command: mock.MagicMock) -> None:
        """If gh run list returns empty, workflow should exit early."""
        mock_run_command.return_value = ("[]", 0)
        youtube.monitor_workflow("main", "onedrive", "token", verbose=False)
        # gh run list is retried up to 5 times before giving up
        self.assertEqual(mock_run_command.call_count, 5)


# ---------------------------------------------------------------------------
# BatchDownloader integration
# ---------------------------------------------------------------------------

class TestBatchDownloaderIntegration(unittest.TestCase):
    """Test main.py batch flow end-to-end with mocked dependencies."""

    @mock.patch("main.trigger_github_action")
    @mock.patch("main.os.path.exists")
    def test_batch_with_mixed_task_formats(
        self, mock_exists: mock.MagicMock, mock_trigger: mock.MagicMock
    ) -> None:
        mock_exists.return_value = True  # cookies.txt exists

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tmp:
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
  "https://youtu.be/ghi":
    mode: audio
"""
            )
            tmp.flush()
            downloader = BatchDownloader(config_path=tmp.name)
            downloader.run()
            self.assertEqual(mock_trigger.call_count, 3)

            # Verify args passed to trigger_github_action
            args_list = [call[0][0] for call in mock_trigger.call_args_list]
            self.assertEqual(args_list[0].filename, "song_one")
            self.assertEqual(args_list[0].mode, "audio")
            self.assertEqual(args_list[1].filename, "song_two")
            self.assertEqual(args_list[1].mode, "video")
            # Third task has no filename but mode inherits from global
            self.assertIsNotNone(args_list[2].filename)  # timestamp
            self.assertEqual(args_list[2].mode, "audio")

        os.unlink(tmp.name)

    @mock.patch("main.trigger_github_action")
    @mock.patch("main.get_cookies")
    @mock.patch("main.os.path.exists")
    def test_batch_auto_login_when_no_cookies(
        self,
        mock_exists: mock.MagicMock,
        mock_get_cookies: mock.MagicMock,
        mock_trigger: mock.MagicMock,
    ) -> None:
        mock_exists.return_value = False  # cookies.txt missing
        mock_get_cookies.return_value = (mock.MagicMock(), mock.MagicMock())

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tmp:
            tmp.write(
                """
config:
  mode: audio
  storage: gofile
  branch: main

tasks:
  "https://youtu.be/abc": "song"
"""
            )
            tmp.flush()
            # Need to patch os.path.exists specifically for the config file check
            # because BatchDownloader.load_config checks it before our mock kicks in
            # for cookies.txt. Use a side_effect to distinguish paths.
            def _exists_side_effect(path: str) -> bool:
                if path == tmp.name:
                    return True
                return False  # cookies.txt missing
            with mock.patch("main.os.path.exists", side_effect=_exists_side_effect):
                downloader = BatchDownloader(config_path=tmp.name)
                downloader.run()
                mock_get_cookies.assert_called_once()
                mock_trigger.assert_called_once()

        os.unlink(tmp.name)


# ---------------------------------------------------------------------------
# API client integration flows
# ---------------------------------------------------------------------------

class TestAlipanClientIntegration(unittest.TestCase):
    """Test AlipanClient methods in an integrated manner with mocked HTTP."""

    @mock.patch("providers.aliclient.requests.Session")
    def test_upload_small_file_flow(
        self, mock_session_cls: mock.MagicMock
    ) -> None:
        """Simulate: init -> upload small file -> get download URL -> delete."""
        mock_session = mock_session_cls.return_value
        mock_session.post.return_value.json.side_effect = [
            {"access_token": "acc", "refresh_token": "ref"},  # token
            {"resource_drive_id": "d123"},  # drive
            {
                "file_id": "f999",
                "upload_id": "u111",
                "rapid_upload": True,
            },  # create upload -> rapid upload
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write("hello world")
            tmp.flush()
            client = AlipanClient(refresh_token="tok")
            result = client.upload_file(tmp.name)
            self.assertEqual(result["file_id"], "f999")
            os.unlink(tmp.name)

    @mock.patch("providers.aliclient.requests.Session")
    def test_download_file_flow(self, mock_session_cls: mock.MagicMock) -> None:
        """Simulate: init -> get file info -> get download URL -> stream download."""
        mock_session = mock_session_cls.return_value
        # get_file_info, get_download_url, download now use self.session
        mock_session.post.return_value.json.side_effect = [
            {"access_token": "acc", "refresh_token": "ref"},
            {"resource_drive_id": "d123"},
            {"name": "cloud_file.opus"},
            {"url": "https://cdn.example.com/file"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_cm = mock.MagicMock()
            mock_cm.iter_content.return_value = [b"fake data"]
            mock_cm.raise_for_status.return_value = None
            mock_session.get.return_value.__enter__ = mock.MagicMock(
                return_value=mock_cm
            )
            mock_session.get.return_value.__exit__ = mock.MagicMock(
                return_value=False
            )

            client = AlipanClient(refresh_token="tok")
            result_path = client.download_file("f123", tmpdir)
            self.assertTrue(result_path.endswith("cloud_file.opus"))
            self.assertTrue(os.path.exists(result_path))
            with open(result_path, "rb") as f:
                self.assertEqual(f.read(), b"fake data")


class TestOneDriveClientIntegration(unittest.TestCase):
    """Test OneDriveClient methods in an integrated manner with mocked HTTP."""

    @mock.patch("providers.odclient.requests.Session")
    def test_upload_small_file_flow(
        self, mock_session_cls: mock.MagicMock
    ) -> None:
        """Simulate: init -> simple upload (<4MB)."""
        mock_session = mock_session_cls.return_value
        mock_session.put.return_value = mock.MagicMock(
            json=lambda: {"id": "item123", "name": "test.txt"},
            raise_for_status=lambda: None,
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write("small file content")
            tmp.flush()
            client = OneDriveClient('{"access_token":"tok"}')
            result = client.upload_file(tmp.name)
            self.assertEqual(result["id"], "item123")
            os.unlink(tmp.name)

    @mock.patch("providers.odclient.requests.Session")
    def test_download_file_flow(self, mock_session_cls: mock.MagicMock) -> None:
        """Simulate: init -> get file info -> stream download."""
        mock_session = mock_session_cls.return_value
        with tempfile.TemporaryDirectory() as tmpdir:
            # get_file_info uses requests.get directly; download also uses requests.get
            # We need both calls to return proper values.
            call_count = 0
            def _get_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                mock_resp = mock.MagicMock()
                if call_count == 1:
                    # get_file_info
                    mock_resp.json.return_value = {
                        "name": "cloud.doc",
                        "@microsoft.graph.downloadUrl": "https://cdn.example.com/dl",
                    }
                else:
                    # actual download
                    mock_resp.iter_content.return_value = [b"doc content"]
                    mock_resp.raise_for_status.return_value = None
                return mock_resp

            with mock.patch(
                "providers.odclient.requests.get", side_effect=_get_side_effect
            ):
                client = OneDriveClient('{"access_token":"tok"}')
                result_path = client.download_file("item456", tmpdir)
                self.assertTrue(result_path.endswith("cloud.doc"))
                self.assertTrue(os.path.exists(result_path))

    @mock.patch("providers.odclient.requests.Session")
    def test_delete_file_flow(self, mock_session_cls: mock.MagicMock) -> None:
        """Simulate: delete returns 204."""
        mock_session = mock_session_cls.return_value
        # delete_file uses requests.delete directly, not session.delete
        with mock.patch("providers.odclient.requests.delete") as mock_delete:
            mock_response = mock.MagicMock()
            mock_response.status_code = 204
            mock_delete.return_value = mock_response

            client = OneDriveClient('{"access_token":"tok"}')
            result = client.delete_file("item789")
            self.assertTrue(result)


# ---------------------------------------------------------------------------
# Cross-provider consistency tests
# ---------------------------------------------------------------------------

class TestProviderConsistency(unittest.TestCase):
    """Ensure all providers behave consistently when given malformed input."""

    def test_all_providers_handle_missing_result_block(self) -> None:
        cfg = _make_config()
        bad_logs = "some random log content without any markers"

        # None should raise
        AliyunProvider(cfg).handle_result(bad_logs, token="t")
        OnedriveProvider(cfg).handle_result(bad_logs, token="t")
        GofileProvider(cfg).handle_result(bad_logs)

    def test_all_providers_handle_empty_logs(self) -> None:
        cfg = _make_config()
        AliyunProvider(cfg).handle_result("", token="t")
        OnedriveProvider(cfg).handle_result("", token="t")
        GofileProvider(cfg).handle_result("")


if __name__ == "__main__":
    unittest.main()
