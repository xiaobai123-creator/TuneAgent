#!/usr/bin/env python3
"""Run the week-two intent parser and a platform adapter from the terminal."""

from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

from tuneagent.agent.intent_parser import IntentParseError, parse_intent
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
    return parser.parse_args()


def format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "--:--"
    total_seconds = max(duration_ms, 0) // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def main() -> int:
    args = parse_args()
    request_text = " ".join(args.request).strip()
    if not request_text:
        request_text = input("请输入搜索请求：").strip()

    intent = parse_intent(request_text)
    print("解析结果：")
    print(json.dumps(intent.to_dict(), ensure_ascii=False, indent=2))

    adapter = MockNeteaseAdapter() if args.platform == "mock" else NeteaseAdapter()
    songs = adapter.search(intent.keyword, intent.sort_by, intent.limit)

    print(f"\n{adapter.platform} 搜索结果（{len(songs)} 首）：")
    if not songs:
        print("没有找到匹配的模拟数据。")
        return 0

    for index, song in enumerate(songs, start=1):
        album = song.album or "未知专辑"
        print(
            f"{index:>2}. {song.title} — {song.artist} | "
            f"{album} | {format_duration(song.duration_ms)} | fee={song.fee}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AdapterError, IntentParseError, ValueError) as error:
        print(f"run_cli: {error}", file=sys.stderr)
        raise SystemExit(1) from error
