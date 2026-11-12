"""Offline Netease adapter backed by the week-one search fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tuneagent.cleaning.models import Song
from tuneagent.platforms.base import (
    AdapterError,
    PlatformAdapter,
    UnsupportedOperationError,
    validate_search_arguments,
)

DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "raw_search_guofeng.json"
)


class MockNeteaseAdapter(PlatformAdapter):
    """A deterministic, network-free adapter for repeatable development."""

    platform = "netease-mock"

    def __init__(
        self,
        fixture_path: str | Path = DEFAULT_FIXTURE_PATH,
        fixture_keyword: str = "国风",
    ) -> None:
        self.fixture_path = Path(fixture_path)
        self.fixture_keyword = fixture_keyword.strip()
        self._songs: tuple[Song, ...] | None = None

    def _load_songs(self) -> tuple[Song, ...]:
        if self._songs is not None:
            return self._songs

        try:
            payload: Any = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise AdapterError(
                f"cannot read mock fixture {self.fixture_path}: {error}"
            ) from error
        except json.JSONDecodeError as error:
            raise AdapterError(
                f"mock fixture is not valid JSON: {self.fixture_path}: {error}"
            ) from error

        result = payload.get("result") if isinstance(payload, dict) else None
        raw_songs = result.get("songs") if isinstance(result, dict) else None
        if not isinstance(raw_songs, list):
            raise AdapterError("mock fixture does not contain result.songs")

        songs: list[Song] = []
        for raw_song in raw_songs:
            if not isinstance(raw_song, dict):
                continue
            try:
                songs.append(Song.from_netease(raw_song))
            except ValueError as error:
                raise AdapterError(f"invalid mock song record: {error}") from error
        self._songs = tuple(songs)
        return self._songs

    def search(
        self,
        keyword: str,
        sort_by: str = "hot",
        limit: int = 15,
    ) -> list[Song]:
        validate_search_arguments(keyword, sort_by, limit)
        if keyword.strip() != self.fixture_keyword:
            return []

        # The fixture has no play/like/favorite metrics. Preserve its stable
        # order and do not fabricate a ranking that the source cannot support.
        return list(self._load_songs()[:limit])

    def download(self, song_id: int, dest_dir: str | Path) -> Path:
        raise UnsupportedOperationError(
            "MockNeteaseAdapter does not download copyrighted song audio; "
            "use the CC0 smoke-test downloader from week one"
        )
