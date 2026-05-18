"""Unit tests for youtube.py"""
from __future__ import annotations

import unittest
from unittest import mock
import argparse
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import youtube


class TestRunCommand(unittest.TestCase):
    @mock.patch("youtube.subprocess.run")
    def test_run_command_success(self, mock_run: mock.MagicMock) -> None:
        mock_run.return_value = mock.MagicMock(
            stdout="hello", stderr="", returncode=0
        )
        stdout, code = youtube.run_command("echo hello", verbose=False)
        self.assertEqual(stdout, "hello")
        self.assertEqual(code, 0)

    @mock.patch("youtube.subprocess.run")
    def test_run_command_failure(self, mock_run: mock.MagicMock) -> None:
        mock_run.return_value = mock.MagicMock(
            stdout="", stderr="error", returncode=1
        )
        stdout, code = youtube.run_command("false", verbose=False)
        self.assertEqual(stdout, "")
        self.assertEqual(code, 1)


class TestSetupArgs(unittest.TestCase):
    @mock.patch("argparse.ArgumentParser.parse_args")
    def test_setup_args_defaults(self, mock_parse: mock.MagicMock) -> None:
        mock_parse.return_value = argparse.Namespace(
            url="https://youtu.be/test",
            branch="main",
            verbose=False,
            mode="audio",
            storage="onedrive",
            filename=None,
            token=None,
            path="/",
        )
        args = youtube.setup_args()
        self.assertEqual(args.url, "https://youtu.be/test")
        self.assertEqual(args.mode, "audio")
        self.assertEqual(args.storage, "onedrive")

    @mock.patch("argparse.ArgumentParser.parse_args")
    def test_setup_args_aliyun_requires_token(self, mock_parse: mock.MagicMock) -> None:
        mock_parse.return_value = argparse.Namespace(
            url="https://youtu.be/test",
            branch="main",
            verbose=False,
            mode="audio",
            storage="aliyun",
            filename=None,
            token=None,
            path="/",
        )
        with mock.patch.object(
            argparse.ArgumentParser, "error", side_effect=SystemExit(2)
        ) as mock_error:
            with self.assertRaises(SystemExit):
                youtube.setup_args()
            mock_error.assert_called_once()


class TestTriggerGithubAction(unittest.TestCase):
    @mock.patch("youtube.run_command")
    @mock.patch("youtube.monitor_workflow")
    @mock.patch("os.path.exists")
    def test_trigger_success(
        self,
        mock_exists: mock.MagicMock,
        mock_monitor: mock.MagicMock,
        mock_run: mock.MagicMock,
    ) -> None:
        mock_exists.return_value = False
        mock_run.return_value = ("", 0)

        args = argparse.Namespace(
            url="https://youtu.be/test",
            branch="main",
            verbose=False,
            mode="audio",
            storage="onedrive",
            filename=None,
            token=None,
            path="/",
        )
        youtube.trigger_github_action(args)
        mock_run.assert_called()
        mock_monitor.assert_called_once_with("main", "onedrive", None, False)

    @mock.patch("youtube.run_command")
    @mock.patch("os.path.exists")
    def test_trigger_failure(
        self, mock_exists: mock.MagicMock, mock_run: mock.MagicMock
    ) -> None:
        mock_exists.return_value = False
        mock_run.return_value = ("error", 1)

        args = argparse.Namespace(
            url="https://youtu.be/test",
            branch="main",
            verbose=False,
            mode="audio",
            storage="onedrive",
            filename=None,
            token=None,
            path="/",
        )
        with self.assertRaises(SystemExit) as cm:
            youtube.trigger_github_action(args)
        self.assertEqual(cm.exception.code, 1)


class TestMonitorWorkflow(unittest.TestCase):
    @mock.patch("youtube.run_command")
    @mock.patch("youtube.subprocess.run")
    @mock.patch("youtube.OnedriveProvider")
    def test_monitor_onedrive(
        self,
        mock_provider_cls: mock.MagicMock,
        mock_subprocess: mock.MagicMock,
        mock_run: mock.MagicMock,
    ) -> None:
        # First call: gh run list returns run id
        # Second call: gh run view returns logs
        # Third call: gh run delete
        mock_run.side_effect = [
            ('[{"databaseId": 12345}]', 0),
            ("---RESULT_START---\nITEM_ID: abc\nFILE_NAME: test.opus\n---RESULT_END---", 0),
            ("", 0),
        ]
        youtube.monitor_workflow("main", "onedrive", "fake_token", verbose=False)
        mock_provider_cls.return_value.handle_result.assert_called_once()

    @mock.patch("youtube.run_command")
    def test_monitor_no_run_id(self, mock_run: mock.MagicMock) -> None:
        mock_run.return_value = ("[]", 0)
        # Should print and return early without error
        youtube.monitor_workflow("main", "gofile", None, verbose=False)


if __name__ == "__main__":
    unittest.main()
