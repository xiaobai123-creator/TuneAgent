from __future__ import annotations

import unittest

from tuneagent.ui.service import (
    DEFAULT_PLATFORM_LABEL,
    RESULT_HEADERS,
    available_platforms,
    run_search,
)


class UIServiceTests(unittest.TestCase):
    def test_normal_search_returns_table_and_report(self) -> None:
        result = run_search("国风 按热度 前15")

        self.assertTrue(result.success)
        self.assertEqual(len(result.rows), 7)
        self.assertEqual(len(result.rows[0]), len(RESULT_HEADERS))
        self.assertEqual(result.rows[0][1], "落了白")
        self.assertEqual(result.rows[0][2], "蒋雪儿Snow.J")
        self.assertIn("原始 20 条 -> 去重后 20 条", result.report_markdown)
        self.assertIn("可用 7 条", result.report_markdown)
        self.assertIn("原始榜单顺序", result.report_markdown)

    def test_like_sort_shows_fallback_reason(self) -> None:
        result = run_search("国风 按点赞 前15")

        self.assertTrue(result.success)
        self.assertIn("歌曲 ID 降序（回退）", result.report_markdown)
        self.assertIn("缺少点赞量", result.report_markdown)
        self.assertEqual(result.rows[0][1], "春庭雪（这一世 太漫长却止步咫尺天涯间）")

    def test_empty_input_returns_friendly_error(self) -> None:
        result = run_search("   ")

        self.assertFalse(result.success)
        self.assertEqual(result.rows, [])
        self.assertIn("请输入搜索请求", result.status_markdown)

    def test_unknown_keyword_and_platform_do_not_raise(self) -> None:
        no_result = run_search("不存在的关键词 按热度 前15")
        self.assertFalse(no_result.success)
        self.assertEqual(no_result.rows, [])
        self.assertIn("没有找到结果", no_result.status_markdown)

        bad_platform = run_search("国风 按热度 前15", "未知平台")
        self.assertFalse(bad_platform.success)
        self.assertIn("暂不支持平台", bad_platform.status_markdown)

    def test_platform_registry_exposes_mock_platform(self) -> None:
        self.assertEqual(available_platforms(), (DEFAULT_PLATFORM_LABEL,))


if __name__ == "__main__":
    unittest.main()
