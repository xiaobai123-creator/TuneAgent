#!/usr/bin/env python3
"""Run the week-two intent parser and a platform adapter from the terminal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import ensure_project_root_on_path

PROJECT_ROOT = ensure_project_root_on_path()

from tuneagent.agent.intent_parser import IntentParseError, SearchIntent, parse_intent
from tuneagent.cleaning.models import Song
from tuneagent.cleaning.pipeline import CleaningPipeline, CleaningResult
from tuneagent.platforms.base import AdapterError
from tuneagent.platforms.mock import MockNeteaseAdapter
from tuneagent.platforms.netease import NeteaseAdapter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse a natural-language TuneAgent request and search songs."
    )
    parser.add_argument(
        "request",
        nargs="*",
        help='natural-language request, for example: "国风 按热度 前15"',
    )
    parser.add_argument(
        "--platform",
        choices=("mock", "netease"),
        default="mock",
        help="adapter to use (default: mock)",
    )
    parser.add_argument(
        "--export-cleaned",
        type=Path,
        help="write the cleaned result and report to a JSON fixture",
    )
    return parser.parse_args()


def format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "--:--"
    total_seconds = max(duration_ms, 0) // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def format_song_line(index: int, song: Song) -> str:
    album = song.album or "未知专辑"
    return (
        f"{index:>2}. {song.title} — {song.artist} | "
        f"{album} | {format_duration(song.duration_ms)} | fee={song.fee}"
    )


def print_candidates(songs: list[Song]) -> None:
    print(f"\n清洗前候选（{len(songs)} 首，包含重复和不可用歌曲）：")
    if not songs:
        print("没有获取到候选歌曲。")
        return
    for index, song in enumerate(songs, start=1):
        print(format_song_line(index, song))


def print_cleaned_result(result: CleaningResult) -> None:
    report = result.report
    print("\n清洗统计：")
    print(report.summary())
    print(f"实际排序指标：{report.sort_metric_name}")
    print(f"排序说明：{report.sort_fallback_reason}")

    print(f"\n清洗后结果（{report.final_count} 首，目标 {report.target_limit} 首）：")
    if not result.songs:
        print("没有可用歌曲。")
        return
    for index, song in enumerate(result.songs, start=1):
        print(format_song_line(index, song))
    if report.final_count < report.target_limit:
        print(
            f"注意：仅找到 {report.final_count} 首可用歌曲，"
            f"少于目标 {report.target_limit} 首。"
        )


def export_cleaned_result(
    path: Path,
    *,
    intent: SearchIntent,
    platform: str,
    candidate_count: int,
    result: CleaningResult,
) -> Path:
    export_path = path if path.is_absolute() else PROJECT_ROOT / path
    export_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "query": intent.to_dict(),
        "platform": platform,
        "candidate_count": candidate_count,
        **result.to_dict(),
    }
    export_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return export_path


def main() -> int:
    args = parse_args()
    request_text = " ".join(args.request).strip()
    if not request_text:
        request_text = input("请输入搜索请求：").strip()

    intent = parse_intent(request_text)
    print("解析结果：")
    print(json.dumps(intent.to_dict(), ensure_ascii=False, indent=2))

    adapter = MockNeteaseAdapter() if args.platform == "mock" else NeteaseAdapter()
    candidate_limit = min(100, intent.limit * 3)
    print(f"\n候选请求数量：{candidate_limit}（最终目标 {intent.limit}）")
    candidates = adapter.search(intent.keyword, intent.sort_by, candidate_limit)
    print_candidates(candidates)

    result = CleaningPipeline().run(
        candidates,
        sort_by=intent.sort_by,
        limit=intent.limit,
    )
    print_cleaned_result(result)

    if args.export_cleaned:
        export_path = export_cleaned_result(
            args.export_cleaned,
            intent=intent,
            platform=adapter.platform,
            candidate_count=len(candidates),
            result=result,
        )
        print(f"\n清洗结果已保存：{export_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AdapterError, IntentParseError, OSError, ValueError) as error:
        print(f"run_cli: {error}", file=sys.stderr)
        raise SystemExit(1) from error
