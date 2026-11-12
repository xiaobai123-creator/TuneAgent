from __future__ import annotations

import json
import unittest
from pathlib import Path

from tuneagent.cleaning.models import Song
from tuneagent.cleaning.pipeline import CleaningPipeline

CLEANED_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "cleaned_search_guofeng.json"
)


def make_song(
    song_id: int,
    title: str,
    artists: tuple[str, ...] = ("测试歌手",),
    fee: int | None = 0,
) -> Song:
    return Song(
        platform="test",
        id=song_id,
        title=title,
        artists=artists,
        album="测试专辑",
        duration_ms=180_000,
        fee=fee,
    )


class CleaningPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = CleaningPipeline()

    def test_deduplicates_by_id_then_normalized_title_and_artist(self) -> None:
        songs = [
            make_song(1, "第一首", ("Alpha",)),
            make_song(1, "同 ID 但不同歌名", ("Beta",)),
            make_song(2, "  Hello, World!  ", ("Artist A", "Artist B")),
            make_song(3, "hello world", (" artist b ", "ARTIST A")),
        ]

        result = self.pipeline.run(songs, sort_by="hot", limit=15)

        self.assertEqual([song.id for song in result.songs], [1, 2])
        self.assertEqual(result.report.raw_count, 4)
        self.assertEqual(result.report.deduplicated_count, 2)
        self.assertEqual(result.report.duplicate_count, 2)

    def test_filters_vip_paid_and_unknown_fee_tracks(self) -> None:
        songs = [
            make_song(10, "免费 0", fee=0),
            make_song(20, "免费 1", fee=1),
            make_song(30, "VIP", fee=8),
            make_song(40, "未知费用", fee=None),
        ]

        result = self.pipeline.run(songs, sort_by="hot", limit=15)

        self.assertEqual([song.id for song in result.songs], [10, 20])
        self.assertEqual(result.report.available_count, 2)
        self.assertEqual(result.report.unavailable_count, 2)

    def test_reports_counts_and_applies_final_limit(self) -> None:
        songs = [
            make_song(index, f"歌曲 {index}", artists=(f"歌手 {index}",))
            for index in range(1, 6)
        ]

        result = self.pipeline.run(songs, sort_by="hot", limit=3)

        self.assertEqual(result.report.summary(), "原始 5 条 -> 去重后 5 条 -> 可用 5 条 -> 最终 Top 3")
        self.assertEqual([song.id for song in result.songs], [1, 2, 3])
        self.assertEqual(result.report.final_count, 3)

    def test_sort_by_changes_order_with_explicit_fallback(self) -> None:
        songs = [
            make_song(10, "歌曲 10", artists=("歌手",)),
            make_song(30, "歌曲 30", artists=("歌手",)),
            make_song(20, "歌曲 20", artists=("歌手",)),
        ]

        hot_result = self.pipeline.run(songs, sort_by="hot", limit=3)
        likes_result = self.pipeline.run(songs, sort_by="likes", limit=3)

        self.assertEqual([song.id for song in hot_result.songs], [10, 30, 20])
        self.assertEqual([song.id for song in likes_result.songs], [30, 20, 10])
        self.assertEqual(hot_result.report.sort_metric_name, "原始榜单顺序")
        self.assertIn("歌曲 ID 降序", likes_result.report.sort_metric_name)
        self.assertIn("缺少点赞量", likes_result.report.sort_fallback_reason)

    def test_saved_fixture_contains_only_available_songs(self) -> None:
        payload = json.loads(CLEANED_FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(payload["report"]["raw_count"], 20)
        self.assertEqual(payload["report"]["available_count"], 7)
        self.assertEqual(payload["report"]["final_count"], 7)
        self.assertTrue(payload["songs"])
        self.assertTrue(all(song["fee"] in {0, 1} for song in payload["songs"]))


if __name__ == "__main__":
    unittest.main()
