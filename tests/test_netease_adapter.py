from __future__ import annotations

import json
import unittest
from pathlib import Path

from tuneagent.platforms.netease import NeteaseAdapter

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "raw_search_guofeng.json"
)


class NeteaseAdapterMappingTests(unittest.TestCase):
    def test_maps_fixture_without_network_access(self) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        songs = NeteaseAdapter.songs_from_payload(payload)

        self.assertEqual(len(songs), 20)
        self.assertEqual(songs[0].platform, "netease")
        self.assertEqual(songs[0].duration_ms, 180821)
        self.assertEqual(songs[0].fee, 1)

        multi_artist_song = next(song for song in songs if song.title == "我本将心向明月")
        self.assertEqual(len(multi_artist_song.artists), 2)


if __name__ == "__main__":
    unittest.main()
