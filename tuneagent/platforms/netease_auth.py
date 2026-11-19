"""Validate and securely persist user-supplied Netease login cookies."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from tuneagent.platforms.real_download import (
    RealNeteaseDownloader,
    parse_cookie_header,
)

DEFAULT_COOKIE_FILE = Path(".netease_cookie")
DownloaderFactory = Callable[
    [Mapping[str, str]],
    RealNeteaseDownloader,
]


@dataclass(frozen=True, slots=True)
class LoginResult:
    cookie_path: Path


def serialize_cookie_header(cookies: Mapping[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


class NeteaseAuthService:
    """Validate a cookie with Netease before atomically saving it."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        downloader_factory: DownloaderFactory | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.downloader_factory = downloader_factory or (
            lambda cookies: RealNeteaseDownloader(cookies=cookies)
        )

    def _cookie_path(self, cookie_file: str | Path | None) -> Path:
        configured = cookie_file or os.getenv(
            "NETEASE_COOKIE_FILE",
            str(DEFAULT_COOKIE_FILE),
        )
        path = Path(configured).expanduser()
        return path if path.is_absolute() else self.project_root / path

    def _write_secure(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_name(
            f".{path.name}.{secrets.token_hex(6)}.tmp"
        )
        try:
            with temporary_path.open("w", encoding="utf-8", newline="\n") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            if os.name == "posix":
                temporary_path.chmod(0o600)
            os.replace(temporary_path, path)
            if os.name == "posix":
                path.chmod(0o600)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def login_with_cookie(
        self,
        raw_cookie: str,
        *,
        cookie_file: str | Path | None = None,
    ) -> LoginResult:
        cookies = parse_cookie_header(raw_cookie)
        downloader = self.downloader_factory(cookies)
        downloader.check_login()

        target = self._cookie_path(cookie_file)
        normalized_cookie = serialize_cookie_header(cookies)
        self._write_secure(target, f"{normalized_cookie}\n")
        return LoginResult(cookie_path=target)
