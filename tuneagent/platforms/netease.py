"""Netease adapter using the ordinary public search endpoint."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tuneagent.cleaning.models import Song
from tuneagent.platforms.base import (
    AdapterError,
    PlatformAdapter,
    UnsupportedOperationError,
    validate_search_arguments,
)

DEFAULT_SEARCH_URL = "https://music.163.com/api/search/get/web"
DEFAULT_TIMEOUT_SECONDS = 20


class NeteaseAdapter(PlatformAdapter):
    """Search Netease without request signing, cookies, or encryption reversal."""

    platform = "netease"

    def __init__(
        self,
        search_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.search_url = search_url or os.getenv(
            "NETEASE_SEARCH_URL", DEFAULT_SEARCH_URL
        )
        self.timeout = timeout or float(
            os.getenv("HTTP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )
        if self.timeout <= 0:
            raise ValueError("HTTP timeout must be greater than zero")

    def fetch_raw_response(
        self,
        keyword: str,
        limit: int = 15,
    ) -> bytes:
        query = urlencode(
            {
                "csrf_token": "",
                "s": keyword,
                "type": "1",
                "offset": "0",
                "total": "true",
                "limit": str(limit),
            }
        )
        request = Request(
            f"{self.search_url}?{query}",
            headers={
                "Accept": "application/json",
                "Referer": "https://music.163.com/",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
            },
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise AdapterError(
                        f"unexpected Netease HTTP status: {response.status}"
                    )
                raw_response = response.read()
        except HTTPError as error:
            raise AdapterError(f"Netease HTTP {error.code}: {error.reason}") from error
        except URLError as error:
            raise AdapterError(f"Netease network error: {error.reason}") from error
        except TimeoutError as error:
            raise AdapterError(
                f"Netease request timed out after {self.timeout:g}s"
            ) from error

        if not raw_response.strip():
            raise AdapterError("Netease returned an empty response")
        return raw_response

    @staticmethod
    def raw_songs_from_payload(payload: Any) -> list[dict[str, Any]]:
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise AdapterError("Netease response does not contain a result object")
        raw_songs = result.get("songs")
        if not isinstance(raw_songs, list):
            raise AdapterError("Netease response does not contain result.songs")
        return [song for song in raw_songs if isinstance(song, dict)]

    @classmethod
    def raw_songs_from_response(cls, raw_response: bytes) -> list[dict[str, Any]]:
        try:
            payload = json.loads(raw_response.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise AdapterError("Netease response is not valid UTF-8") from error
        except json.JSONDecodeError as error:
            raise AdapterError(f"Netease response is not valid JSON: {error}") from error
        return cls.raw_songs_from_payload(payload)

    @classmethod
    def songs_from_payload(cls, payload: Any) -> list[Song]:
        songs: list[Song] = []
        for raw_song in cls.raw_songs_from_payload(payload):
            try:
                songs.append(Song.from_netease(raw_song))
            except ValueError as error:
                raise AdapterError(f"invalid Netease song record: {error}") from error
        return songs

    def search(
        self,
        keyword: str,
        sort_by: str = "hot",
        limit: int = 15,
    ) -> list[Song]:
        validate_search_arguments(keyword, sort_by, limit)
        raw_response = self.fetch_raw_response(keyword.strip(), limit)
        try:
            payload = json.loads(raw_response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AdapterError(f"cannot parse Netease response: {error}") from error
        return self.songs_from_payload(payload)[:limit]

    def download(self, song_id: int, dest_dir: str | Path) -> Path:
        raise UnsupportedOperationError(
            "Netease audio download is intentionally unavailable: resolving "
            "protected song URLs would require the encrypted API excluded "
            "from this project scope"
        )
