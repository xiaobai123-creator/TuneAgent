from __future__ import annotations

import unittest

from tuneagent.agent.intent_parser import IntentParseError, parse_intent


class IntentParserTests(unittest.TestCase):
    def test_parses_smoke_request(self) -> None:
        intent = parse_intent("国风 按热度 前15")
        self.assertEqual(
            intent.to_dict(),
            {"keyword": "国风", "sort_by": "hot", "limit": 15},
        )

    def test_supports_all_sort_keywords(self) -> None:
        cases = {
            "按热度": "hot",
            "按播放量": "plays",
            "按点赞": "likes",
            "按收藏": "favorites",
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                intent = parse_intent(f"国风 {phrase} 前10")
                self.assertEqual(intent.sort_by, expected)

    def test_parses_top_format_and_defaults(self) -> None:
        intent = parse_intent("国风，按点赞排序，Top 8")
        self.assertEqual(intent.keyword, "国风")
        self.assertEqual(intent.sort_by, "likes")
        self.assertEqual(intent.limit, 8)

        default_intent = parse_intent("国风")
        self.assertEqual(default_intent.sort_by, "hot")
        self.assertEqual(default_intent.limit, 15)

    def test_rejects_request_without_keyword(self) -> None:
        with self.assertRaises(IntentParseError):
            parse_intent("按热度 前15")


if __name__ == "__main__":
    unittest.main()
