from __future__ import annotations

import unittest

from tuneagent.cleaning.models import Song
from tuneagent.platforms.base import UnsupportedOperationError
from tuneagent.platforms.mock import MockNeteaseAdapter


class MockNeteaseAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = MockNeteaseAdapter()

    def test_maps_raw_song_fields_and_multiple_artists(self) -> None:
        songs = self.adapter.search("国风", "hot", 20)
        self.assertEqual(len(songs), 20)
        self.assertIsInstance(songs[0], Song)
        self.assertEqual(songs[0].id, 2068046512)
        self.assertEqual(songs[0].title, "落了白")
        self.assertEqual(songs[0].artists, ("蒋雪儿Snow.J",))

        multi_artist_song = next(song for song in songs if song.title == "我本将心向明月")
        self.assertEqual(
            multi_artist_song.artists,
            ("王朝1982", "朱旭BooBoo"),
        )
        self.assertEqual(multi_artist_song.artist, "王朝1982 / 朱旭BooBoo")

    def test_applies_limit_and_isolates_unknown_keywords(self) -> None:
        self.assertEqual(len(self.adapter.search("国风", "hot", 15)), 15)
        self.assertEqual(self.adapter.search("其他关键词", "hot", 15), [])

    def test_download_is_explicitly_unsupported(self) -> None:
        with self.assertRaises(UnsupportedOperationError):
            self.adapter.download(2068046512, "downloads")


if __name__ == "__main__":
    unittest.main()
