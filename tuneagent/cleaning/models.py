"""Shared data models used across platform adapters and the agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _artist_names(raw_song: Mapping[str, Any]) -> tuple[str, ...]:
    artists = raw_song.get("artists")
    if not isinstance(artists, list):
        return ()

    names: list[str] = []
    seen: set[str] = set()
    for artist in artists:
        name: Any
        if isinstance(artist, Mapping):
            name = artist.get("name")
        else:
            name = artist

        if not isinstance(name, str):
            continue
        normalized_name = name.strip()
        if normalized_name and normalized_name not in seen:
            seen.add(normalized_name)
            names.append(normalized_name)
    return tuple(names)


@dataclass(frozen=True, slots=True)
class Song:
    """A platform-neutral song record with its original source payload."""

    platform: str
    id: int
    title: str
    artists: tuple[str, ...]
    album: str | None
    duration_ms: int | None
    fee: int | None
    copyright_id: int | None = None
    status: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def artist(self) -> str:
        """Return a display-friendly artist string for single-column output."""
        return " / ".join(self.artists) if self.artists else "未知歌手"

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "platform": self.platform,
            "id": self.id,
            "title": self.title,
            "artists": list(self.artists),
            "artist": self.artist,
            "album": self.album,
            "duration_ms": self.duration_ms,
            "fee": self.fee,
            "copyright_id": self.copyright_id,
            "status": self.status,
        }
        if include_raw:
            payload["raw"] = dict(self.raw)
        return payload

    @classmethod
    def from_netease(cls, raw_song: Mapping[str, Any]) -> Song:
        raw_copy = dict(raw_song)
        album_payload = raw_song.get("album")
        album_name: str | None = None
        if isinstance(album_payload, Mapping):
            candidate = album_payload.get("name")
            if isinstance(candidate, str) and candidate.strip():
                album_name = candidate.strip()

        title = raw_song.get("name")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Netease song is missing a valid name")

        song_id = _optional_int(raw_song.get("id"))
        if song_id is None:
            raise ValueError(f"Netease song {title!r} is missing a valid id")

        return cls(
            platform="netease",
            id=song_id,
            title=title.strip(),
            artists=_artist_names(raw_song),
            album=album_name,
            duration_ms=_optional_int(raw_song.get("duration")),
            fee=_optional_int(raw_song.get("fee")),
            copyright_id=_optional_int(raw_song.get("copyrightId")),
            status=_optional_int(raw_song.get("status")),
            raw=raw_copy,
        )
