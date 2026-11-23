from __future__ import annotations

import html
import io
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from tuneagent.agent.tool_executor import MusicToolExecutor, TOOL_DEFINITIONS
from tuneagent.platforms.web_search import search_web, search_web_safe

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "bing_rss_sample.xml"


def _rss_feed(
    description: str = "摘要",
    link: str = "https://example.com/test",
) -> bytes:
    escaped_description = html.escape(description, quote=False)
    escaped_link = html.escape(link, quote=False)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Bing Search</title>
    <item>
      <title>测试标题</title>
      <link>{escaped_link}</link>
      <description>{escaped_description}</description>
    </item>
  </channel>
</rss>
""".encode()


class WebSearchTests(unittest.TestCase):
    def test_parses_three_items_from_bing_rss_fixture(self) -> None:
        payload = FIXTURE_PATH.read_bytes()
        with patch(
            "tuneagent.platforms.web_search.urllib.request.urlopen",
            return_value=io.BytesIO(payload),
        ):
            results = search_web("周杰伦", max_results=3)

        self.assertEqual(len(results), 3)
        self.assertTrue(all(result["title"] for result in results))
        self.assertTrue(all(result["url"] for result in results))

    def test_strips_html_tags_from_description(self) -> None:
        html = "<p>歌手 <b>周杰伦</b>&amp; 音乐人</p>"
        with patch(
            "tuneagent.platforms.web_search.urllib.request.urlopen",
            return_value=io.BytesIO(_rss_feed(html)),
        ):
            results = search_web("周杰伦", max_results=1)

        self.assertEqual(results[0]["snippet"], "歌手 周杰伦& 音乐人")

    def test_snippet_is_truncated_to_200_characters(self) -> None:
        description = "<b>" + ("音" * 250) + "</b>"
        with patch(
            "tuneagent.platforms.web_search.urllib.request.urlopen",
            return_value=io.BytesIO(_rss_feed(description)),
        ):
            results = search_web("周杰伦", max_results=1)

        self.assertEqual(len(results[0]["snippet"]), 200)

    def test_ignores_non_http_links(self) -> None:
        payload = _rss_feed(link="javascript:alert(1)")
        with patch(
            "tuneagent.platforms.web_search.urllib.request.urlopen",
            return_value=io.BytesIO(payload),
        ):
            results = search_web("危险链接", max_results=1)

        self.assertEqual(results, [])

    def test_results_include_published_field(self) -> None:
        with patch(
            "tuneagent.platforms.web_search.urllib.request.urlopen",
            return_value=io.BytesIO(_rss_feed()),
        ):
            missing_results = search_web("无日期", max_results=1)

        with patch(
            "tuneagent.platforms.web_search.urllib.request.urlopen",
            return_value=io.BytesIO(FIXTURE_PATH.read_bytes()),
        ):
            fixture_results = search_web("周杰伦", max_results=1)

        self.assertIn("published", missing_results[0])
        self.assertEqual(missing_results[0]["published"], "")
        self.assertIn("published", fixture_results[0])
        self.assertTrue(fixture_results[0]["published"])

    def test_max_results_limits_output(self) -> None:
        payload = FIXTURE_PATH.read_bytes()
        with patch(
            "tuneagent.platforms.web_search.urllib.request.urlopen",
            return_value=io.BytesIO(payload),
        ):
            results = search_web("周杰伦", max_results=2)

        self.assertEqual(len(results), 2)

    def test_network_errors_are_returned_without_raising(self) -> None:
        error = URLError("network unavailable")
        with (
            patch(
                "tuneagent.platforms.web_search.urllib.request.urlopen",
                side_effect=error,
            ) as urlopen,
            patch("tuneagent.platforms.web_search.time.sleep"),
        ):
            results = search_web("周杰伦")
            safe_results, safe_error = search_web_safe("周杰伦")

        self.assertEqual(results, [])
        self.assertEqual(safe_results, [])
        self.assertIn("network unavailable", safe_error)
        self.assertEqual(urlopen.call_count, 4)

    def test_empty_feed_is_not_reported_as_an_error(self) -> None:
        empty_feed = b'<rss version="2.0"><channel></channel></rss>'
        with patch(
            "tuneagent.platforms.web_search.urllib.request.urlopen",
            return_value=io.BytesIO(empty_feed),
        ):
            results, error = search_web_safe("无结果")

        self.assertEqual(results, [])
        self.assertEqual(error, "")

    def test_executor_returns_structured_web_search_content(self) -> None:
        expected = [
            {
                "title": "测试",
                "url": "https://example.com/test",
                "snippet": "摘要",
            }
        ]
        with patch(
            "tuneagent.agent.tool_executor.search_web_safe",
            return_value=(expected, ""),
        ):
            result = MusicToolExecutor(
                PROJECT_ROOT,
                adapter_mode="mock",
            ).execute(
                "web_search",
                {"query": "测试", "max_results": 1},
            )

        self.assertTrue(result.ok)
        self.assertEqual(
            result.content,
            {
                "ok": True,
                "query": "测试",
                "count": 1,
                "results": expected,
            },
        )
        self.assertIn(
            "web_search",
            [tool["function"]["name"] for tool in TOOL_DEFINITIONS],
        )


if __name__ == "__main__":
    unittest.main()
