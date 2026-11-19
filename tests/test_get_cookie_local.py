from __future__ import annotations

import io
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from get_cookie_local import (  # noqa: E402
    BrowserCookieResult,
    music_u_from_cookies,
    print_manual_fallback,
    read_music_u_from_browsers,
    save_cookie_file,
)


class CookieExtractionHelpersTests(unittest.TestCase):
    def test_extracts_music_u_without_exposing_other_cookies(self) -> None:
        cookies = [
            {"name": "other", "value": "ignored"},
            {"name": "MUSIC_U", "value": " secret-value "},
        ]
        self.assertEqual(music_u_from_cookies(cookies), "secret-value")

    def test_reads_attribute_based_cookie_objects(self) -> None:
        class Cookie:
            name = "MUSIC_U"
            value = "attribute-value"

        self.assertEqual(
            music_u_from_cookies([Cookie()]),
            "attribute-value",
        )

    def test_falls_back_from_chrome_to_edge(self) -> None:
        class FakeBrowserCookies:
            @staticmethod
            def chrome(domain_name: str) -> list[object]:
                del domain_name
                raise RuntimeError("Chrome database locked")

            @staticmethod
            def edge(domain_name: str) -> list[dict[str, str]]:
                del domain_name
                return [{"name": "MUSIC_U", "value": "edge-value"}]

        result = read_music_u_from_browsers(FakeBrowserCookies())
        self.assertIsInstance(result, BrowserCookieResult)
        self.assertEqual(result.music_u, "edge-value")
        self.assertEqual(result.browser, "Edge")
        self.assertEqual(len(result.errors), 1)

    def test_manual_fallback_prioritizes_cookie_editor_guide(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            print_manual_fallback()
        message = output.getvalue()
        self.assertTrue(
            message.startswith(
                "💡 强烈建议安装浏览器 Cookie-Editor 插件一键复制，"
                "或参阅 docs/cookie_guide.md"
            )
        )
        self.assertIn("Application → Storage → Cookies", message)

    def test_saves_cookie_with_restricted_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = save_cookie_file(
                "secret-value",
                Path(temporary_directory),
            )
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "MUSIC_U=secret-value\n",
            )
            if os.name == "posix":
                self.assertEqual(
                    stat.S_IMODE(target.stat().st_mode),
                    0o600,
                )


if __name__ == "__main__":
    unittest.main()
