from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rich.console import Console

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from interactive_cli import (  # noqa: E402
    availability_label,
    display_download_path,
    interactive_login,
    render_event,
)
from tuneagent.agent.events import AgentEvent, EventKind  # noqa: E402


class InteractiveCLITests(unittest.TestCase):
    def test_availability_labels(self) -> None:
        self.assertEqual(availability_label(0)[0], "✅ 免费可下")
        self.assertEqual(availability_label(1)[0], "✅ 免费可下")
        self.assertEqual(availability_label(8)[0], "🔒 VIP受限")
        self.assertEqual(availability_label(None)[0], "❔ 状态未知")

    def test_download_path_is_relative_and_posix_style(self) -> None:
        path = PROJECT_ROOT / "downloads" / "song.mp3"
        self.assertEqual(display_download_path(path), "downloads/song.mp3")

    def test_download_success_has_required_server_message(self) -> None:
        output = io.StringIO()
        console = Console(file=output, force_terminal=False, width=240)
        render_event(
            console,
            AgentEvent(
                kind=EventKind.DOWNLOAD_RESULT,
                data={
                    "path": str(PROJECT_ROOT / "downloads" / "song.mp3"),
                },
            ),
        )
        rendered = output.getvalue()
        self.assertIn(
            "✅ 文件已保存至服务器的 downloads/song.mp3。"
            "如果您使用 VS Code 远程连接，请在左侧文件树中右键该文件"
            "选择 Download 下载到本地",
            rendered,
        )

    def test_interactive_login_uses_hidden_input_without_printing_secret(self) -> None:
        output = io.StringIO()
        console = Console(file=output, force_terminal=False, width=160)
        calls: list[str] = []

        class FakeAuthService:
            def login_with_cookie(self, raw_cookie: str) -> SimpleNamespace:
                calls.append(raw_cookie)
                return SimpleNamespace(
                    cookie_path=PROJECT_ROOT / ".netease_cookie"
                )

        with patch(
            "interactive_cli.getpass.getpass",
            return_value="MUSIC_U=top-secret",
        ):
            interactive_login(console, FakeAuthService())  # type: ignore[arg-type]

        self.assertEqual(calls, ["MUSIC_U=top-secret"])
        self.assertIn("Cookie 已安全保存到 .netease_cookie", output.getvalue())
        self.assertNotIn("top-secret", output.getvalue())

    def test_cli_source_contains_no_system_file_picker(self) -> None:
        source = (SCRIPTS_DIR / "interactive_cli.py").read_text(encoding="utf-8")
        forbidden = (
            "tkinter",
            "filedialog",
            "askopenfilename",
            "askdirectory",
            "type=\"file\"",
        )
        for marker in forbidden:
            self.assertNotIn(marker.lower(), source.lower())


if __name__ == "__main__":
    unittest.main()
