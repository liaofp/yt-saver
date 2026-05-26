"""Unit tests for utils.py"""
from __future__ import annotations

import unittest
from unittest import mock
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils


class TestSaveCookies(unittest.TestCase):
    def test_save_cookies_writes_netscape_format(self) -> None:
        mock_context = mock.MagicMock()
        mock_context.cookies.return_value = [
            {
                "domain": ".youtube.com",
                "path": "/",
                "secure": True,
                "expires": 1893456000,
                "name": "SID",
                "value": "value123",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath: str = os.path.join(tmpdir, "cookies.txt")
            # Patch os.getcwd so file is written to tmpdir
            with mock.patch("os.getcwd", return_value=tmpdir):
                utils.save_cookies(mock_context, cookies_file="cookies.txt")
            with open(filepath, "r", encoding="utf-8") as f:
                content: str = f.read()
            self.assertIn("Netscape HTTP Cookie File", content)
            self.assertIn("SID", content)
            self.assertIn("value123", content)


class TestIsLogin(unittest.TestCase):
    def test_is_login_true(self) -> None:
        mock_context = mock.MagicMock()
        mock_context.cookies.return_value = [
            {"name": "__Secure-3PSID"},
            {"name": "SAPISID"},
            {"name": "SID"},
        ]
        self.assertTrue(utils.is_login(mock_context))

    def test_is_login_false(self) -> None:
        mock_context = mock.MagicMock()
        mock_context.cookies.return_value = [
            {"name": "SAPISID"},
            {"name": "SID"},
        ]
        self.assertFalse(utils.is_login(mock_context))


class TestVerifyCookies(unittest.TestCase):
    def test_verify_redirected(self) -> None:
        mock_page = mock.MagicMock()
        mock_page.url = "https://accounts.google.com/signin"
        result: bool = utils.verify_cookies(mock_page)
        self.assertFalse(result)

    def test_verify_valid(self) -> None:
        mock_page = mock.MagicMock()
        mock_page.url = "https://www.youtube.com/feed/subscriptions"
        mock_page.content.return_value = "<html>subscriptions</html>"
        result: bool = utils.verify_cookies(mock_page)
        self.assertTrue(result)


class TestRefreshCookies(unittest.TestCase):
    @mock.patch("utils.save_cookies")
    @mock.patch("utils.verify_cookies")
    def test_refresh_success(
        self, mock_verify: mock.MagicMock, mock_save: mock.MagicMock
    ) -> None:
        mock_page = mock.MagicMock()
        mock_context = mock.MagicMock()
        mock_verify.return_value = True
        result: bool = utils.refresh_cookies(mock_page, mock_context)
        self.assertTrue(result)
        mock_save.assert_called_once()

    @mock.patch("utils.save_cookies")
    def test_refresh_exception(self, mock_save: mock.MagicMock) -> None:
        mock_page = mock.MagicMock()
        mock_page.goto.side_effect = Exception("network error")
        mock_context = mock.MagicMock()
        result: bool = utils.refresh_cookies(mock_page, mock_context)
        self.assertFalse(result)


class TestCloseBrowser(unittest.TestCase):
    def test_close_browser_no_crash(self) -> None:
        mock_context = mock.MagicMock()
        # Should not raise even if context.clear_cookies or context.close raises
        with mock.patch.object(
            mock_context, "clear_cookies", side_effect=Exception("boom")
        ):
            with mock.patch.object(
                mock_context, "close", side_effect=Exception("boom")
            ):
                utils.close_browser(mock_context)

    def test_close_browser_clears_cookies(self) -> None:
        mock_context = mock.MagicMock()
        utils.close_browser(mock_context)
        mock_context.clear_cookies.assert_called_once()
        mock_context.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
