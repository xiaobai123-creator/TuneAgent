"""Common interface implemented by every music platform adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from tuneagent.cleaning.pipeline import SUPPORTED_SORT_VALUES
from tuneagent.cleaning.models import Song


class AdapterError(RuntimeError):
    """Raised when a platform adapter cannot complete an operation."""


class UnsupportedOperationError(AdapterError):
    """Raised for an operation intentionally unavailable in this milestone."""


def validate_search_arguments(keyword: str, sort_by: str, limit: int) -> None:
    if not keyword.strip():
        raise ValueError("search keyword cannot be empty")
    if sort_by not in SUPPORTED_SORT_VALUES:
        supported = ", ".join(sorted(SUPPORTED_SORT_VALUES))
        raise ValueError(f"unsupported sort_by {sort_by!r}; expected one of {supported}")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("search limit must be an integer")
    if not 1 <= limit <= 100:
        raise ValueError("search limit must be between 1 and 100")


class PlatformAdapter(ABC):
    """Stable seam between the agent and interchangeable music platforms."""

    platform: str

    @abstractmethod
    def search(
        self,
        keyword: str,
        sort_by: str = "hot",
        limit: int = 15,
    ) -> list[Song]:
        """Search the platform and return platform-neutral song records."""

    @abstractmethod
    def download(self, song_id: int, dest_dir: str | Path) -> Path:
        """Download a song when supported by the platform implementation."""
