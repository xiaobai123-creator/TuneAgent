"""Search public web pages through Bing's RSS endpoint."""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

BING_RSS_ENDPOINT = "https://cn.bing.com/search"
REQUEST_TIMEOUT_SECONDS = 8
MAX_RETRIES = 1
RETRY_DELAY_SECONDS = 0.5
SNIPPET_LIMIT = 200
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class _DescriptionTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _validate_arguments(query: str, max_results: int) -> None:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if isinstance(max_results, bool) or not isinstance(max_results, int):
        raise ValueError("max_results must be an integer")
    if max_results < 1:
        raise ValueError("max_results must be positive")


def _strip_html(value: str) -> str:
    parser = _DescriptionTextExtractor()
    parser.feed(value)
    parser.close()
    text = " ".join("".join(parser.parts).split())
    return text[:SNIPPET_LIMIT]


def _search_web_once(query: str, max_results: int) -> list[dict]:
    url = (
        f"{BING_RSS_ENDPOINT}?q={urllib.parse.quote_plus(query)}"
        "&format=rss"
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        raw = response.read()

    root = ET.fromstring(raw)
    results: list[dict] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        if not link.startswith(("http://", "https://")):
            continue
        description = item.findtext("description") or ""
        published = (item.findtext("pubDate") or "").strip()
        results.append(
            {
                "title": title,
                "url": link,
                "snippet": _strip_html(description),
                "published": published,
            }
        )
        if len(results) >= max_results:
            break
    return results


def search_web(query: str, max_results: int = 5) -> list[dict]:
    results, _ = search_web_safe(query, max_results)
    return results


def search_web_safe(query: str, max_results: int = 5) -> tuple[list[dict], str]:
    try:
        _validate_arguments(query, max_results)
    except Exception as error:
        return [], f"{type(error).__name__}: {error}"

    last_error = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            return _search_web_once(query.strip(), max_results), ""
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)
    return [], last_error
