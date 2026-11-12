"""Framework-independent search service used by the TuneAgent Web UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tuneagent.agent.intent_parser import IntentParseError, SearchIntent, parse_intent
from tuneagent.cleaning.pipeline import CleaningPipeline, CleaningReport
from tuneagent.platforms.base import AdapterError, PlatformAdapter
from tuneagent.platforms.mock import MockNeteaseAdapter

DEFAULT_PLATFORM_LABEL = "网易云 Mock"
RESULT_HEADERS = ("序号", "歌名", "歌手", "专辑", "时长", "fee")


@dataclass(frozen=True, slots=True)
class UIResult:
    success: bool
    rows: list[list[str | int]]
    status_markdown: str
    report_markdown: str
    intent: SearchIntent | None = None
    report: CleaningReport | None = None


def available_platforms() -> tuple[str, ...]:
    """Return the platform labels currently available to the UI."""
    return (DEFAULT_PLATFORM_LABEL,)


def format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "--:--"
    total_seconds = max(duration_ms, 0) // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def _adapter_for_platform(
    platform_label: str,
    fixture_path: str | Path | None,
) -> PlatformAdapter:
    if platform_label == DEFAULT_PLATFORM_LABEL:
        adapter = MockNeteaseAdapter()
        if fixture_path is not None:
            adapter = MockNeteaseAdapter(fixture_path=fixture_path)
        return adapter
    supported = "、".join(available_platforms())
    raise ValueError(f"暂不支持平台“{platform_label}”，当前可选：{supported}")


def _failure(message: str) -> UIResult:
    return UIResult(
        success=False,
        rows=[],
        status_markdown=f"### 无法完成搜索\n\n{message}",
        report_markdown="",
    )


def _report_markdown(result_report: CleaningReport, candidate_count: int) -> str:
    shortfall = ""
    if result_report.final_count < result_report.target_limit:
        shortfall = (
            f"\n\n> 目标为 {result_report.target_limit} 首，"
            f"但只有 {result_report.final_count} 首可用歌曲。"
        )
    return f"""### 清洗漏斗

`{result_report.summary()}`

| 阶段 | 数量 |
|---|---:|
| 原始候选 | {result_report.raw_count} |
| 去重后 | {result_report.deduplicated_count} |
| 可用歌曲 | {result_report.available_count} |
| 最终结果 | {result_report.final_count} |

- 重复记录：{result_report.duplicate_count}
- 不可用记录：{result_report.unavailable_count}
- 候选请求数量：{candidate_count}

### 排序依据

- **实际排序指标：** {result_report.sort_metric_name}
- **回退说明：** {result_report.sort_fallback_reason}{shortfall}
"""


def run_search(
    request_text: str,
    platform_label: str = DEFAULT_PLATFORM_LABEL,
    *,
    fixture_path: str | Path | None = None,
) -> UIResult:
    """Run intent parsing, platform search, and cleaning without UI imports."""
    if not request_text or not request_text.strip():
        return _failure("请输入搜索请求，例如：`国风 按热度 前15`。")

    try:
        intent = parse_intent(request_text)
        adapter = _adapter_for_platform(platform_label, fixture_path)
        candidate_limit = min(100, intent.limit * 3)
        candidates = adapter.search(
            intent.keyword,
            intent.sort_by,
            candidate_limit,
        )
    except (AdapterError, IntentParseError, OSError, ValueError) as error:
        return _failure(str(error))

    result = CleaningPipeline().run(
        candidates,
        sort_by=intent.sort_by,
        limit=intent.limit,
    )
    rows = [
        [
            index,
            song.title,
            song.artist,
            song.album or "未知专辑",
            format_duration(song.duration_ms),
            song.fee if song.fee is not None else "-",
        ]
        for index, song in enumerate(result.songs, start=1)
    ]
    report_markdown = _report_markdown(result.report, len(candidates))

    if not candidates:
        return UIResult(
            success=False,
            rows=[],
            status_markdown=(
                "### 没有找到结果\n\n"
                "请尝试其它关键词，或确认 Mock 数据文件是否可用。"
            ),
            report_markdown=report_markdown,
            intent=intent,
            report=result.report,
        )
    if not result.songs:
        return UIResult(
            success=False,
            rows=[],
            status_markdown=(
                "### 没有可用歌曲\n\n"
                "候选歌曲可能都是 VIP、付费或费用状态未知。"
            ),
            report_markdown=report_markdown,
            intent=intent,
            report=result.report,
        )

    shortfall = ""
    if result.report.final_count < result.report.target_limit:
        shortfall = (
            f" 当前仅有 {result.report.final_count} 首可用歌曲，"
            f"少于目标 {result.report.target_limit} 首。"
        )
    return UIResult(
        success=True,
        rows=rows,
        status_markdown=(
            f"### 搜索完成\n\n已返回 {result.report.final_count} 首可用歌曲。"
            f"{shortfall}"
        ),
        report_markdown=report_markdown,
        intent=intent,
        report=result.report,
    )
