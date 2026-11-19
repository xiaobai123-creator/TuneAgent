from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from typing import Mapping

from tuneagent.platforms.netease_auth import NeteaseAuthService
from tuneagent.platforms.real_download import CookieExpiredError


class FakeAuthDownloader:
    def __init__(
        self,
        cookies: Mapping[str, str],
        *,
        fail: bool = False,
    ) -> None:
        self.cookies = dict(cookies)
        self.fail = fail

    def check_login(self) -> None:
        if self.fail:
            raise CookieExpiredError("Cookie 已过期")


class NeteaseAuthServiceTests(unittest.TestCase):
    def test_validates_before_saving_and_restricts_cookie_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            received: dict[str, str] = {}

            def factory(cookies: Mapping[str, str]) -> FakeAuthDownloader:
                received.update(cookies)
                return FakeAuthDownloader(cookies)

            service = NeteaseAuthService(root, downloader_factory=factory)
            result = service.login_with_cookie(
                "MUSIC_U=secret-value; __csrf=csrf-value"
            )

            saved = result.cookie_path.read_text(encoding="utf-8").strip()
            self.assertEqual(received["MUSIC_U"], "secret-value")
            self.assertEqual(saved, "MUSIC_U=secret-value; __csrf=csrf-value")
            if os.name == "posix":
                mode = stat.S_IMODE(result.cookie_path.stat().st_mode)
                self.assertEqual(mode, 0o600)

    def test_failed_validation_does_not_overwrite_existing_cookie(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cookie_path = root / ".netease_cookie"
            cookie_path.write_text("MUSIC_U=old-value\n", encoding="utf-8")
            cookie_path.chmod(0o600)

            service = NeteaseAuthService(
                root,
                downloader_factory=lambda cookies: FakeAuthDownloader(
                    cookies,
                    fail=True,
                ),
            )
            with self.assertRaises(CookieExpiredError):
                service.login_with_cookie("MUSIC_U=new-value")

            self.assertEqual(
                cookie_path.read_text(encoding="utf-8"),
                "MUSIC_U=old-value\n",
            )


if __name__ == "__main__":
    unittest.main()
