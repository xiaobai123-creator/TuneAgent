"""Cleaning and quality profiling for collected chart batches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from tuneagent.cleaning.models import Song
from tuneagent.cleaning.pipeline import CleaningPipeline, is_available


@dataclass(frozen=True, slots=True)
class ParsedSource:
    """Songs parsed from one source response, plus unusable records."""

    songs: tuple[Song, ...]
    invalid_count: int = 0


@dataclass(frozen=True, slots=True)
class CollectedCleaningReport:
    raw_count: int
    duplicate_count: int
    unparsable_count: int
    invalid_duration_count: int
    valid_count: int
    available_count: int
    vip_count: int
    missing_album_count: int
    missing_duration_count: int
    missing_artist_count: int
    missing_fee_count: int

    @property
    def parsed_count(self) -> int:
        return self.raw_count - self.unparsable_count

    @property
    def deduplicated_count(self) -> int:
        return self.parsed_count - self.duplicate_count

    @property
    def invalid_count(self) -> int:
        return self.unparsable_count + self.invalid_duration_count

    @property
    def missing_field_count(self) -> int:
        return (
            self.missing_album_count
            + self.missing_duration_count
            + self.missing_artist_count
            + self.missing_fee_count
        )

    def summary(self) -> str:
        missing_note = (
            f"，缺失字段 {self.missing_field_count}"
            if self.missing_field_count
            else ""
        )
        return (
            f"原始 {self.raw_count} 条 -> 去重后 {self.deduplicated_count} 条"
            f" -> 有效 {self.valid_count} 条"
            f"（可用 {self.available_count}，VIP/付费 {self.vip_count}，"
            f"无效 {self.invalid_count}{missing_note}）"
        )

    def quality(self) -> dict[str, int | float]:
        parsed_base = max(self.parsed_count, 1)
        valid_base = max(self.valid_count, 1)
        raw_base = max(self.raw_count, 1)
        return {
            "raw_count": self.raw_count,
            "parsed_count": self.parsed_count,
            "deduplicated_count": self.deduplicated_count,
            "valid_count": self.valid_count,
            "duplicate_count": self.duplicate_count,
            "duplicate_rate": round(self.duplicate_count / parsed_base, 4),
            "unparsable_count": self.unparsable_count,
            "invalid_duration_count": self.invalid_duration_count,
            "invalid_count": self.invalid_count,
            "invalid_rate": round(self.invalid_count / raw_base, 4),
            "available_count": self.available_count,
            "vip_count": self.vip_count,
            "missing_album_count": self.missing_album_count,
            "missing_duration_count": self.missing_duration_count,
            "missing_artist_count": self.missing_artist_count,
            "missing_fee_count": self.missing_fee_count,
            "missing_album_rate": round(self.missing_album_count / valid_base, 4),
            "missing_duration_rate": round(
                self.missing_duration_count / valid_base, 4
            ),
            "missing_artist_rate": round(
                self.missing_artist_count / valid_base, 4
            ),
            "missing_fee_rate": round(self.missing_fee_count / valid_base, 4),
        }

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary(), **self.quality()}


@dataclass(frozen=True, slots=True)
class CollectedCleaningResult:
    songs: tuple[Song, ...]
    report: CollectedCleaningReport


def clean_collected_songs(
    songs: Iterable[Song],
    *,
    invalid_count: int = 0,
) -> CollectedCleaningResult:
    """Deduplicate and validate a collected batch without dropping VIP tracks."""
    if isinstance(invalid_count, bool) or not isinstance(invalid_count, int):
        raise ValueError("invalid_count must be an integer")
    if invalid_count < 0:
        raise ValueError("invalid_count must be zero or greater")

    raw_songs = list(songs)
    deduplicated = CleaningPipeline().deduplicate(raw_songs)
    duplicate_count = len(raw_songs) - len(deduplicated)

    valid: list[Song] = []
    invalid_duration_count = 0
    for song in deduplicated:
        duration = song.duration_ms
        if (
            isinstance(duration, int)
            and not isinstance(duration, bool)
            and duration <= 0
        ):
            invalid_duration_count += 1
            continue
        valid.append(song)

    available_count = sum(1 for song in valid if is_available(song))
    vip_count = sum(
        1
        for song in valid
        if song.fee is not None and not is_available(song)
    )

    report = CollectedCleaningReport(
        raw_count=len(raw_songs) + invalid_count,
        duplicate_count=duplicate_count,
        unparsable_count=invalid_count,
        invalid_duration_count=invalid_duration_count,
        valid_count=len(valid),
        available_count=available_count,
        vip_count=vip_count,
        missing_album_count=sum(1 for song in valid if not song.album),
        missing_duration_count=sum(
            1 for song in valid if song.duration_ms is None
        ),
        missing_artist_count=sum(1 for song in valid if not song.artists),
        missing_fee_count=sum(1 for song in valid if song.fee is None),
    )
    return CollectedCleaningResult(songs=tuple(valid), report=report)
