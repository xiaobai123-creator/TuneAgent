"""Deterministic cleaning, filtering, and fallback sorting for song records."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from tuneagent.cleaning.models import Song

SUPPORTED_SORT_VALUES = frozenset({"hot", "plays", "likes", "favorites"})
AVAILABLE_FEES = frozenset({0, 1})
_NON_WORD_PATTERN = re.compile(r"[\W_]+", re.UNICODE)

SORT_LABELS = {
    "hot": (
        "原始榜单顺序",
        "平台返回默认搜索顺序，未提供独立热度指标；保留原始顺序作为热度回退",
    ),
    "plays": (
        "歌曲 ID 降序（回退）",
        "平台原始数据缺少播放量；使用歌曲 ID 降序作为确定性回退",
    ),
    "likes": (
        "歌曲 ID 降序（回退）",
        "平台原始数据缺少点赞量；使用歌曲 ID 降序作为确定性回退",
    ),
    "favorites": (
        "歌曲 ID 降序（回退）",
        "平台原始数据缺少收藏量；使用歌曲 ID 降序作为确定性回退",
    ),
}


def normalize_text(value: str) -> str:
    """Normalize case, Unicode width, whitespace, and punctuation."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return _NON_WORD_PATTERN.sub("", normalized)


def normalized_artist_key(song: Song) -> str:
    normalized_artists = sorted(
        artist
        for artist in (normalize_text(name) for name in song.artists)
        if artist
    )
    return "|".join(normalized_artists)


def is_available(song: Song) -> bool:
    """Only explicit free tracks are eligible for recommendation results."""
    fee = song.fee
    return (
        isinstance(fee, int)
        and not isinstance(fee, bool)
        and fee in AVAILABLE_FEES
    )


@dataclass(frozen=True, slots=True)
class CleaningReport:
    raw_count: int
    deduplicated_count: int
    available_count: int
    final_count: int
    target_limit: int
    sort_by: str
    sort_metric_name: str
    sort_fallback_reason: str

    @property
    def duplicate_count(self) -> int:
        return self.raw_count - self.deduplicated_count

    @property
    def unavailable_count(self) -> int:
        return self.deduplicated_count - self.available_count

    def summary(self) -> str:
        shortfall = ""
        if self.final_count < self.target_limit:
            shortfall = f"（目标 {self.target_limit}，候选不足）"
        return (
            f"原始 {self.raw_count} 条 -> 去重后 {self.deduplicated_count} 条"
            f" -> 可用 {self.available_count} 条"
            f" -> 最终 Top {self.final_count}{shortfall}"
        )

    def to_dict(self) -> dict[str, str | int]:
        return {
            "raw_count": self.raw_count,
            "deduplicated_count": self.deduplicated_count,
            "available_count": self.available_count,
            "final_count": self.final_count,
            "target_limit": self.target_limit,
            "duplicate_count": self.duplicate_count,
            "unavailable_count": self.unavailable_count,
            "sort_by": self.sort_by,
            "sort_metric_name": self.sort_metric_name,
            "sort_fallback_reason": self.sort_fallback_reason,
        }


@dataclass(frozen=True, slots=True)
class CleaningResult:
    songs: tuple[Song, ...]
    report: CleaningReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "report": self.report.to_dict(),
            "songs": [song.to_dict() for song in self.songs],
        }


class CleaningPipeline:
    """Deduplicate, filter unavailable tracks, then sort with honest fallbacks."""

    def deduplicate(self, songs: Iterable[Song]) -> list[Song]:
        deduplicated: list[Song] = []
        seen_ids: set[int] = set()
        seen_identities: set[tuple[str, str]] = set()

        for song in songs:
            if song.id in seen_ids:
                continue

            identity = (normalize_text(song.title), normalized_artist_key(song))
            if identity in seen_identities:
                continue

            seen_ids.add(song.id)
            seen_identities.add(identity)
            deduplicated.append(song)
        return deduplicated

    def filter_available(self, songs: Iterable[Song]) -> list[Song]:
        return [song for song in songs if is_available(song)]

    def sort_songs(self, songs: Iterable[Song], sort_by: str) -> list[Song]:
        if sort_by not in SUPPORTED_SORT_VALUES:
            supported = ", ".join(sorted(SUPPORTED_SORT_VALUES))
            raise ValueError(
                f"unsupported sort_by {sort_by!r}; expected one of {supported}"
            )

        song_list = list(songs)
        if sort_by == "hot":
            return song_list
        return sorted(
            song_list,
            key=lambda song: (-song.id, normalize_text(song.title)),
        )

    def run(
        self,
        songs: Iterable[Song],
        sort_by: str = "hot",
        limit: int = 15,
    ) -> CleaningResult:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("clean result limit must be an integer")
        if not 1 <= limit <= 100:
            raise ValueError("clean result limit must be between 1 and 100")
        if sort_by not in SUPPORTED_SORT_VALUES:
            supported = ", ".join(sorted(SUPPORTED_SORT_VALUES))
            raise ValueError(
                f"unsupported sort_by {sort_by!r}; expected one of {supported}"
            )

        raw_songs = list(songs)
        deduplicated = self.deduplicate(raw_songs)
        available = self.filter_available(deduplicated)
        ordered = self.sort_songs(available, sort_by)
        final_songs = ordered[:limit]
        metric_name, fallback_reason = SORT_LABELS[sort_by]
        report = CleaningReport(
            raw_count=len(raw_songs),
            deduplicated_count=len(deduplicated),
            available_count=len(available),
            final_count=len(final_songs),
            target_limit=limit,
            sort_by=sort_by,
            sort_metric_name=metric_name,
            sort_fallback_reason=fallback_reason,
        )
        return CleaningResult(songs=tuple(final_songs), report=report)
