"""Deterministic rule-based parsing for TuneAgent search requests."""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_SORT_BY = "hot"
DEFAULT_LIMIT = 15

SORT_ALIASES = {
    "热度": "hot",
    "热门": "hot",
    "播放": "plays",
    "播放量": "plays",
    "播放次数": "plays",
    "点赞": "likes",
    "点赞量": "likes",
    "喜欢": "likes",
    "收藏": "favorites",
    "收藏量": "favorites",
}

_SORT_PATTERN = re.compile(
    r"(?:按|按照|根据|以)\s*"
    r"(热度|热门|播放量|播放次数|播放|点赞量|点赞|喜欢|收藏量|收藏)"
    r"(?:\s*(?:排序|排列|降序|从高到低|来排))?"
)
_LIMIT_PATTERNS = (
    re.compile(r"(?:前|top\s*)\s*(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)\s*(?:首|条|个)(?:歌曲)?"),
)
_REMAINING_ORDER_WORDS = re.compile(r"(?:排序|降序|从高到低)")
_PREFIX_NOISE = re.compile(
    r"^(?:请|帮我|给我|我想看|我想要|搜索|搜一下|查找|找一下|找|推荐)\s*"
)


class IntentParseError(ValueError):
    """Raised when a natural-language request has no usable search keyword."""


@dataclass(frozen=True, slots=True)
class SearchIntent:
    keyword: str
    sort_by: str = DEFAULT_SORT_BY
    limit: int = DEFAULT_LIMIT

    def to_dict(self) -> dict[str, str | int]:
        return {
            "keyword": self.keyword,
            "sort_by": self.sort_by,
            "limit": self.limit,
        }


def parse_intent(text: str) -> SearchIntent:
    if not isinstance(text, str) or not text.strip():
        raise IntentParseError("请输入包含音乐关键词的搜索请求")

    original = text.strip()
    sort_by = DEFAULT_SORT_BY
    limit = DEFAULT_LIMIT
    remaining = original

    sort_match = _SORT_PATTERN.search(remaining)
    if sort_match:
        sort_by = SORT_ALIASES[sort_match.group(1)]
        remaining = remaining[: sort_match.start()] + remaining[sort_match.end() :]

    for limit_pattern in _LIMIT_PATTERNS:
        limit_match = limit_pattern.search(remaining)
        if limit_match:
            limit = int(limit_match.group(1))
            remaining = remaining[: limit_match.start()] + remaining[limit_match.end() :]
            break

    remaining = _REMAINING_ORDER_WORDS.sub(" ", remaining)
    remaining = _PREFIX_NOISE.sub("", remaining)
    keyword = re.sub(r"\s+", " ", remaining).strip(" \t\r\n,，.。!！?？:：;；")

    if not keyword:
        raise IntentParseError("未能从请求中解析出搜索关键词")
    if not 1 <= limit <= 100:
        raise IntentParseError("搜索数量必须位于 1 到 100 之间")

    return SearchIntent(keyword=keyword, sort_by=sort_by, limit=limit)
