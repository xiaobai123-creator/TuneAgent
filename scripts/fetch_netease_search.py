#!/usr/bin/env python3
"""Fetch and inspect the first 20 public Netease search results for a keyword."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from _bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

from tuneagent.platforms.base import AdapterError
from tuneagent.platforms.netease import NeteaseAdapter

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_PATH = Path("tests/fixtures/raw_search_guofeng.json")
DEFAULT_KEYWORD = "国风"
DEFAULT_LIMIT = 20
DEFAULT_TIMEOUT_SECONDS = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch public Netease search data or read the saved fixture."
    )
    parser.add_argument(
        "keyword",
        nargs="?",
        default=DEFAULT_KEYWORD,
        help=f"search keyword (default: {DEFAULT_KEYWORD})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("NETEASE_SEARCH_LIMIT", DEFAULT_LIMIT)),
        help=f"number of raw records to print (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--mode",
        choices=("netease", "mock"),
        default="netease",
        help="fetch the public API or read the existing fixture (default: netease)",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(os.getenv("FIXTURE_PATH", DEFAULT_FIXTURE_PATH)),
        help=f"fixture path (default: {DEFAULT_FIXTURE_PATH})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(
            os.getenv("HTTP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        ),
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    return parser.parse_args()


def resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT_DIR / path


def print_songs(songs: list[dict[str, Any]], limit: int) -> None:
    selected_songs = songs[:limit]
    print(f"Printing {len(selected_songs)} raw record(s):")
    for index, song in enumerate(selected_songs, start=1):
        print(f"\n[{index}]")
        print(json.dumps(song, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    if not 1 <= args.limit <= 100:
        raise ValueError("--limit must be between 1 and 100")
    if args.timeout <= 0:
        raise ValueError("--timeout must be greater than zero")

    fixture_path = resolve_project_path(args.fixture)
    if args.mode == "mock":
        if not fixture_path.is_file():
            raise FileNotFoundError(
                f"fixture not found: {fixture_path}; run --mode netease first"
            )
        raw_response = fixture_path.read_bytes()
        print(f"Loaded saved raw response from {fixture_path}")
    else:
        adapter = NeteaseAdapter(timeout=args.timeout)
        raw_response = adapter.fetch_raw_response(args.keyword, args.limit)
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_bytes(raw_response)
        print(f"Saved raw response to {fixture_path}")

    songs = NeteaseAdapter.raw_songs_from_response(raw_response)
    if len(songs) < args.limit:
        raise RuntimeError(
            f"expected at least {args.limit} songs, received {len(songs)}"
        )

    print(f'Keyword: {args.keyword}')
    print(f"Raw record count: {len(songs)}")
    print_songs(songs, args.limit)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AdapterError, OSError, ValueError) as error:
        print(f"fetch_netease_search: {error}", file=sys.stderr)
        raise SystemExit(1) from error
