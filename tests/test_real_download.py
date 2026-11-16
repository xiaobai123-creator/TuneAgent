from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tuneagent.platforms.real_download import (
    AccessRestrictedError,
    CookieExpiredError,
    CookieFilePermissionError,
    DEFAULT_ACCOUNT_URL,
    MissingCredentialsError,
    RealNeteaseDownloader,
    load_netease_cookies,
    parse_cookie_header,
)


class FakeResponse:
    def __init__(
        self,
        payload: Any = None,
        *,
        status_code: int = 200,
        chunks: list[bytes] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.chunks = chunks or []
        self.headers = headers or {}
        self.closed = False

    def json(self) -> Any:
        return self.payload

    def iter_content(self, chunk_size: int = 8192) -> list[bytes]:
        del chunk_size
        return self.chunks

    def close(self) -> None:
        self.closed = True


class FakeNeteaseClient:
    def __init__(
        self,
        *,
        account_payload: dict[str, Any] | None = None,
        url_payload: dict[str, Any] | None = None,
        audio_chunks: list[bytes] | None = None,
    ) -> None:
        self.headers: dict[str, str] = {}
        self.cookies: dict[str, str] = {}
        self.account_payload = account_payload or {
            "code": 200,
            "account": {"id": 1},
        }
        self.url_payload = url_payload or {
            "code": 200,
            "data": [{"code": 200, "fee": 0, "url": "https://audio.test/song.mp3"}],
        }
        self.audio_chunks = audio_chunks or [b"ID3", b"\x04\x00", b"\x00" * 64]
        self.encoded_requests: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        del kwargs
        if url == DEFAULT_ACCOUNT_URL:
            return FakeResponse(self.account_payload)
        return FakeResponse(
            status_code=200,
            chunks=self.audio_chunks,
            headers={"Content-Length": str(sum(map(len, self.audio_chunks)))},
        )

    def encoded_post(
        self,
        url: str,
        data: dict[str, Any],
    ) -> FakeResponse:
        self.encoded_requests.append({"url": url, "data": data})
        return FakeResponse(self.url_payload)


class CookieLoadingTests(unittest.TestCase):
    def test_parses_full_cookie_header_and_bare_music_u(self) -> None:
        self.assertEqual(parse_cookie_header("bare-token"), {"MUSIC_U": "bare-token"})
        self.assertEqual(
            parse_cookie_header("MUSIC_U=abc; __csrf=def"),
            {"MUSIC_U": "abc", "__csrf": "def"},
        )

    def test_environment_takes_precedence_over_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cookie_path = Path(temporary_directory) / "cookie"
            cookie_path.write_text("MUSIC_U=from-file\n", encoding="utf-8")
            cookie_path.chmod(0o600)
            with patch.dict(
                os.environ,
                {"NETEASE_MUSIC_U": "from-env"},
                clear=True,
            ):
                cookies = load_netease_cookies(cookie_path)
        self.assertEqual(cookies["MUSIC_U"], "from-env")

    def test_rejects_insecure_cookie_file_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cookie_path = Path(temporary_directory) / "cookie"
            cookie_path.write_text("MUSIC_U=secret\n", encoding="utf-8")
            cookie_path.chmod(0o644)
            with self.assertRaises(CookieFilePermissionError):
                load_netease_cookies(cookie_path)

    def test_missing_cookie_has_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_path = Path(temporary_directory) / "missing"
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(MissingCredentialsError):
                    load_netease_cookies(missing_path)


class RealNeteaseDownloaderTests(unittest.TestCase):
    def test_downloads_streamed_audio_without_exposing_secret(self) -> None:
        client = FakeNeteaseClient()
        downloader = RealNeteaseDownloader(client=client)

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = downloader.download(12345, temporary_directory)
            downloaded = result.path.read_bytes()
            manifest = json.loads(
                result.manifest_path.read_text(encoding="utf-8")
            )

        self.assertTrue(downloaded.startswith(b"ID3"))
        self.assertEqual(result.song_id, 12345)
        self.assertEqual(result.quality, "standard")
        self.assertEqual(result.size_bytes, len(downloaded))
        self.assertEqual(client.encoded_requests[0]["data"]["level"], "standard")
        self.assertNotIn("url", manifest)
        self.assertNotIn("cookie", json.dumps(manifest).lower())

    def test_expired_cookie_is_reported_clearly(self) -> None:
        client = FakeNeteaseClient(
            account_payload={"code": 200, "account": None}
        )
        downloader = RealNeteaseDownloader(client=client)
        with self.assertRaisesRegex(CookieExpiredError, "Cookie"):
            with tempfile.TemporaryDirectory() as temporary_directory:
                downloader.download(12345, temporary_directory)

    def test_restricted_song_is_not_bypassed(self) -> None:
        client = FakeNeteaseClient(
            url_payload={
                "code": 200,
                "data": [{"code": 404, "fee": 8, "url": None}],
            }
        )
        downloader = RealNeteaseDownloader(client=client)
        with self.assertRaisesRegex(AccessRestrictedError, "VIP"):
            with tempfile.TemporaryDirectory() as temporary_directory:
                downloader.download(12345, temporary_directory)


if __name__ == "__main__":
    unittest.main()
