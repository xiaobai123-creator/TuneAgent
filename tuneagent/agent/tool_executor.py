"""Validated, presentation-independent tools used by the interactive agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from tuneagent.cleaning.models import Song
from tuneagent.cleaning.pipeline import (
    CleaningPipeline,
    CleaningReport,
    SUPPORTED_SORT_VALUES,
)
from tuneagent.platforms.base import AdapterError, PlatformAdapter
from tuneagent.platforms.mock import MockNeteaseAdapter
from tuneagent.platforms.netease import NeteaseAdapter
from tuneagent.platforms.real_download import (
    ProgressCallback,
    RealDownloadError,
    RealDownloadResult,
    RealNeteaseDownloader,
)

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_music",
        "description": (
            "Search Netease music through TuneAgent, clean the results, and "
            "return playable songs. Use this whenever the user asks to search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Music search keyword such as 国风.",
                },
                "sort_by": {
                    "type": "string",
                    "enum": sorted(SUPPORTED_SORT_VALUES),
                    "description": (
                        "Requested ranking. Falls back transparently when the "
                        "platform does not expose the real metric."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Maximum number of playable songs to return.",
                },
                "platform": {
                    "type": "string",
                    "enum": ["netease"],
                    "description": "Music platform. Only netease is enabled.",
                },
            },
            "required": ["keyword", "sort_by", "limit"],
            "additionalProperties": False,
        },
    },
}

DOWNLOAD_TOOL = {
    "type": "function",
    "function": {
        "name": "download_song",
        "description": (
            "Download one Netease song by ID after the user explicitly asks. "
            "Only download songs the current account can legitimately access."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "song_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Netease song ID from a previous search.",
                }
            },
            "required": ["song_id"],
            "additionalProperties": False,
        },
    },
}

TOOL_DEFINITIONS = [SEARCH_TOOL, DOWNLOAD_TOOL]

DownloaderFactory = Callable[[], RealNeteaseDownloader]


@dataclass(frozen=True, slots=True)
class SearchToolResult:
    songs: tuple[Song, ...]
    report: CleaningReport
    source: str
    fallback_reason: str = ""

    def to_tool_content(self) -> dict[str, Any]:
        return {
            "ok": True,
            "source": self.source,
            "fallback_reason": self.fallback_reason,
            "report": self.report.to_dict(),
            "songs": [song.to_dict() for song in self.songs],
        }


@dataclass(frozen=True, slots=True)
class DownloadToolResult:
    result: RealDownloadResult | None
    cancelled: bool = False
    error: str = ""

    def to_tool_content(self) -> dict[str, Any]:
        if self.cancelled:
            return {"ok": False, "cancelled": True, "error": "用户取消下载"}
        if self.result is None:
            return {"ok": False, "error": self.error}
        return {
            "ok": True,
            "song_id": self.result.song_id,
            "path": str(self.result.path),
            "size_bytes": self.result.size_bytes,
            "sha256": self.result.sha256,
            "quality": self.result.quality,
        }


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    name: str
    ok: bool
    content: Mapping[str, Any]
    search_result: SearchToolResult | None = None
    download_result: DownloadToolResult | None = None


class MusicToolExecutor:
    """Execute validated music tools without printing or terminal imports."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        adapter_mode: str = "auto",
        downloader_factory: DownloaderFactory | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        if adapter_mode not in {"auto", "mock", "netease"}:
            raise ValueError("adapter_mode must be auto, mock, or netease")
        self.adapter_mode = adapter_mode
        self.downloader_factory = downloader_factory or (
            lambda: RealNeteaseDownloader()
        )

    def _search_adapter(self, prefer_mock: bool) -> tuple[PlatformAdapter, str, str]:
        if prefer_mock or self.adapter_mode == "mock":
            return MockNeteaseAdapter(), "netease-mock", ""
        if self.adapter_mode == "netease":
            return NeteaseAdapter(), "netease", ""

        try:
            return NeteaseAdapter(), "netease", ""
        except AdapterError as error:
            return (
                MockNeteaseAdapter(),
                "netease-mock",
                f"真实搜索不可用，已使用离线 Mock：{error}",
            )

    def search_music(
        self,
        keyword: str,
        sort_by: str,
        limit: int,
        platform: str = "netease",
        *,
        prefer_mock: bool = False,
    ) -> SearchToolResult:
        if not isinstance(keyword, str) or not keyword.strip():
            raise ValueError("keyword must be a non-empty string")
        if platform != "netease":
            raise ValueError(f"unsupported platform: {platform}")
        if sort_by not in SUPPORTED_SORT_VALUES:
            raise ValueError(f"unsupported sort_by: {sort_by}")
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit must be an integer")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        adapter, source, fallback_reason = self._search_adapter(prefer_mock)
        candidate_limit = min(100, limit * 3)
        try:
            candidates = adapter.search(keyword.strip(), sort_by, candidate_limit)
        except AdapterError as error:
            if source == "netease" and not prefer_mock and self.adapter_mode == "auto":
                adapter = MockNeteaseAdapter()
                source = "netease-mock"
                fallback_reason = f"真实搜索失败，已使用离线 Mock：{error}"
                candidates = adapter.search(keyword.strip(), sort_by, candidate_limit)
            else:
                raise

        cleaned = CleaningPipeline().run(candidates, sort_by=sort_by, limit=limit)
        return SearchToolResult(
            songs=cleaned.songs,
            report=cleaned.report,
            source=source,
            fallback_reason=fallback_reason,
        )

    def download_song(
        self,
        song_id: int,
        *,
        confirm: Callable[[int], bool] | None = None,
        progress_callback: ProgressCallback | None = None,
        overwrite: bool = False,
    ) -> DownloadToolResult:
        if isinstance(song_id, bool) or not isinstance(song_id, int) or song_id <= 0:
            raise ValueError("song_id must be a positive integer")
        if confirm is None or not confirm(song_id):
            return DownloadToolResult(result=None, cancelled=True)

        download_dir = Path(os.getenv("DOWNLOAD_DIR", "downloads")).expanduser()
        if not download_dir.is_absolute():
            download_dir = self.project_root / download_dir
        try:
            downloader = self.downloader_factory()
            result = downloader.download(
                song_id,
                download_dir,
                overwrite=overwrite,
                progress_callback=progress_callback,
            )
        except (OSError, RealDownloadError, ValueError) as error:
            return DownloadToolResult(result=None, error=str(error))
        return DownloadToolResult(result=result)

    def check_login(self) -> dict[str, Any]:
        try:
            self.downloader_factory().check_login()
        except (OSError, RealDownloadError, ValueError) as error:
            return {
                "ok": False,
                "message": str(error),
            }
        return {
            "ok": True,
            "message": "网易云 Cookie 有效，账号已登录",
        }

    def execute(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        confirm_download: Callable[[int], bool] | None = None,
        download_progress: ProgressCallback | None = None,
        prefer_mock: bool = False,
    ) -> ToolExecutionResult:
        if name == "search_music":
            keyword = arguments.get("keyword")
            sort_by = arguments.get("sort_by", "hot")
            limit = arguments.get("limit", 15)
            platform = arguments.get("platform", "netease")
            if not isinstance(keyword, str) or not isinstance(sort_by, str):
                raise ValueError("search_music 参数类型错误")
            if not isinstance(limit, int) or isinstance(limit, bool):
                raise ValueError("search_music.limit 必须是整数")
            if not isinstance(platform, str):
                raise ValueError("search_music.platform 必须是字符串")
            result = self.search_music(
                keyword,
                sort_by,
                limit,
                platform,
                prefer_mock=prefer_mock,
            )
            return ToolExecutionResult(
                name=name,
                ok=True,
                content=result.to_tool_content(),
                search_result=result,
            )

        if name == "download_song":
            song_id = arguments.get("song_id")
            if not isinstance(song_id, int) or isinstance(song_id, bool):
                raise ValueError("download_song.song_id 必须是整数")
            result = self.download_song(
                song_id,
                confirm=confirm_download,
                progress_callback=download_progress,
            )
            return ToolExecutionResult(
                name=name,
                ok=result.result is not None,
                content=result.to_tool_content(),
                download_result=result,
            )

        raise ValueError(f"未知工具：{name}")
