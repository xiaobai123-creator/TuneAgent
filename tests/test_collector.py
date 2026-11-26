from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from tuneagent.cleaning.models import Song
from tuneagent.collector.chart import ChartSourceError, NeteaseChartSource
from tuneagent.collector.cleaning import clean_collected_songs
from tuneagent.collector.runner import CollectorRunner, RunnerConfig, RunOutcome
from tuneagent.collector.scheduler import SchedulerConfig, run_forever
from tuneagent.collector.store import CollectorStore, RunCounts

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "netease_chart_sample.json"
)
SOURCE = "test-source"


def make_song(
    song_id: int,
    title: str | None = None,
    *,
    artists: tuple[str, ...] = ("测试歌手",),
    album: str | None = "测试专辑",
    duration_ms: int | None = 180_000,
    fee: int | None = 0,
) -> Song:
    return Song(
        platform="netease",
        id=song_id,
        title=title or f"歌曲 {song_id}",
        artists=artists,
        album=album,
        duration_ms=duration_ms,
        fee=fee,
    )


def make_chart_payload(song_ids: list[int]) -> bytes:
    tracks = [
        {
            "id": song_id,
            "name": f"歌曲 {song_id}",
            "artists": [{"name": f"歌手 {song_id}"}],
            "album": {"name": f"专辑 {song_id}"},
            "duration": 180_000,
            "fee": 0,
        }
        for song_id in song_ids
    ]
    return json.dumps(
        {"code": 200, "result": {"tracks": tracks}},
        ensure_ascii=False,
    ).encode("utf-8")


class FakeSource:
    name = "fake-source"

    def __init__(
        self,
        payload: bytes,
        *,
        fail_times: int = 0,
        parse_error: bool = False,
    ) -> None:
        self.payload = payload
        self.fail_times = fail_times
        self.parse_error = parse_error
        self.fetch_count = 0

    def fetch_raw(self) -> bytes:
        self.fetch_count += 1
        if self.fetch_count <= self.fail_times:
            raise ChartSourceError("temporary failure")
        return self.payload

    def parse(self, raw: bytes):
        if self.parse_error:
            raise ChartSourceError("parse failure")
        return NeteaseChartSource.parse(raw)


def commit_songs(
    store: CollectorStore,
    run_id: int,
    songs: list[Song],
    *,
    previous_ranks: dict[int, int] | None = None,
    new_ids: set[int] | None = None,
) -> None:
    previous = previous_ranks or {}
    new_song_ids = new_ids or set()
    report = clean_collected_songs(songs).report
    ranks = {
        song.id: index for index, song in enumerate(songs, start=1)
    }
    first_seen = store.find_new_song_ids(song.id for song in songs)
    counts = RunCounts(
        raw_count=report.raw_count,
        dedup_count=report.deduplicated_count,
        valid_count=report.valid_count,
        available_count=report.available_count,
        new_count=len(new_song_ids),
        first_seen_count=len(first_seen),
        dropped_count=0,
        rank_up_count=0,
        rank_down_count=0,
    )
    store.commit_success(
        run_id,
        source=SOURCE,
        songs=songs,
        ranks=ranks,
        previous_ranks=previous,
        new_ids=new_song_ids,
        counts=counts,
        report=report,
    )


class ChartSourceTests(unittest.TestCase):
    def test_parses_fixture_and_counts_invalid_tracks(self) -> None:
        parsed = NeteaseChartSource.parse(FIXTURE_PATH.read_bytes())

        self.assertEqual(
            [song.id for song in parsed.songs],
            [101, 102, 103, 101, 104, 105],
        )
        self.assertEqual(parsed.invalid_count, 2)

    def test_rejects_invalid_json(self) -> None:
        with self.assertRaises(ChartSourceError):
            NeteaseChartSource.parse(b"not-json")

    def test_rejects_payload_without_tracks(self) -> None:
        with self.assertRaises(ChartSourceError):
            NeteaseChartSource.parse(b'{"code": 200, "result": {}}')

    def test_rejects_empty_track_list(self) -> None:
        with self.assertRaises(ChartSourceError):
            NeteaseChartSource.parse(
                b'{"code": 200, "result": {"tracks": []}}'
            )

    def test_rejects_batch_without_valid_tracks(self) -> None:
        with self.assertRaises(ChartSourceError):
            NeteaseChartSource.parse(
                b'{"code": 200, "result": {"tracks": [{"name": "no id"}]}}'
            )

    def test_fetch_wraps_network_errors(self) -> None:
        with patch(
            "tuneagent.collector.chart.urlopen",
            side_effect=URLError("network unavailable"),
        ):
            with self.assertRaises(ChartSourceError):
                NeteaseChartSource(timeout=1).fetch_raw()


class CollectedCleaningTests(unittest.TestCase):
    def test_fixture_cleaning_metrics(self) -> None:
        parsed = NeteaseChartSource.parse(FIXTURE_PATH.read_bytes())
        result = clean_collected_songs(
            parsed.songs,
            invalid_count=parsed.invalid_count,
        )
        report = result.report

        self.assertEqual(report.raw_count, 8)
        self.assertEqual(report.unparsable_count, 2)
        self.assertEqual(report.duplicate_count, 1)
        self.assertEqual(report.deduplicated_count, 5)
        self.assertEqual(report.invalid_duration_count, 1)
        self.assertEqual(report.valid_count, 4)
        self.assertEqual(report.available_count, 2)
        self.assertEqual(report.vip_count, 2)
        self.assertEqual(report.missing_album_count, 1)
        self.assertEqual(report.missing_duration_count, 1)
        self.assertEqual(report.missing_artist_count, 0)
        self.assertEqual(report.missing_fee_count, 0)
        self.assertIn("原始 8 条 -> 去重后 5 条", report.summary())

    def test_deduplicates_normalized_identity(self) -> None:
        songs = [
            make_song(1, "Hello, World!", artists=("Artist A",)),
            make_song(2, "hello world", artists=("artist a",)),
        ]

        result = clean_collected_songs(songs)

        self.assertEqual([song.id for song in result.songs], [1])
        self.assertEqual(result.report.duplicate_count, 1)

    def test_drops_non_positive_duration(self) -> None:
        songs = [
            make_song(1, duration_ms=0),
            make_song(2, duration_ms=-1),
            make_song(3, duration_ms=None),
        ]

        result = clean_collected_songs(songs)

        self.assertEqual([song.id for song in result.songs], [3])
        self.assertEqual(result.report.invalid_duration_count, 2)
        self.assertEqual(result.report.missing_duration_count, 1)

    def test_keeps_vip_tracks_and_reports_missing_fields(self) -> None:
        songs = [
            make_song(
                1,
                artists=(),
                album=None,
                fee=8,
            ),
            make_song(2, fee=None),
        ]

        result = clean_collected_songs(songs)

        self.assertEqual([song.id for song in result.songs], [1, 2])
        self.assertEqual(result.report.available_count, 0)
        self.assertEqual(result.report.vip_count, 1)
        self.assertEqual(result.report.missing_artist_count, 1)
        self.assertEqual(result.report.missing_album_count, 1)
        self.assertEqual(result.report.missing_fee_count, 1)

    def test_rejects_negative_invalid_count(self) -> None:
        with self.assertRaises(ValueError):
            clean_collected_songs([], invalid_count=-1)


class CollectorStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.db_path = (
            Path(self.temporary_directory.name) / "collector.db"
        )
        self.store = CollectorStore(self.db_path)

    def scalar(self, query: str, params: tuple = ()) -> int:
        with sqlite3.connect(str(self.db_path)) as connection:
            return int(connection.execute(query, params).fetchone()[0])

    def test_commit_success_persists_counts_and_status(self) -> None:
        run_id = self.store.start_run(SOURCE)
        commit_songs(self.store, run_id, [make_song(1), make_song(2)])

        run = self.store.get_run(run_id)
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run["status"], "success")
        self.assertEqual(run["raw_count"], 2)
        self.assertEqual(run["dedup_count"], 2)
        self.assertEqual(run["valid_count"], 2)
        self.assertEqual(run["first_seen_count"], 2)
        self.assertIsNotNone(run["quality_json"])

        summary = self.store.status_summary(SOURCE)
        self.assertEqual(summary["total_runs"], 1)
        self.assertEqual(summary["successes"], 1)
        self.assertEqual(summary["unique_songs"], 2)
        self.assertEqual(summary["new_songs_24h"], 2)

    def test_upsert_does_not_duplicate_across_runs(self) -> None:
        first_run = self.store.start_run(SOURCE)
        commit_songs(self.store, first_run, [make_song(1)])

        second_run = self.store.start_run(SOURCE)
        commit_songs(self.store, second_run, [make_song(1)])

        self.assertEqual(
            self.store.status_summary(SOURCE)["unique_songs"],
            1,
        )
        self.assertEqual(
            self.store.find_new_song_ids([1]),
            set(),
        )
        second = self.store.get_run(second_run)
        assert second is not None
        self.assertEqual(second["first_seen_count"], 0)

    def test_previous_snapshot_uses_last_successful_run(self) -> None:
        first_run = self.store.start_run(SOURCE)
        commit_songs(
            self.store,
            first_run,
            [make_song(1), make_song(2)],
        )
        failed_run = self.store.start_run(SOURCE)
        self.store.mark_failed(failed_run, SOURCE, "boom")
        third_run = self.store.start_run(SOURCE)

        previous_run, ranks = self.store.previous_snapshot(
            SOURCE,
            third_run,
        )

        self.assertEqual(previous_run, first_run)
        self.assertEqual(ranks, {1: 1, 2: 2})

    def test_raw_blob_is_deduplicated_by_hash(self) -> None:
        first_run = self.store.start_run(SOURCE)
        self.store.save_raw(first_run, SOURCE, b'{"a": 1}')
        second_run = self.store.start_run(SOURCE)
        self.store.save_raw(second_run, SOURCE, b'{"a": 1}')

        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM raw_blob"),
            1,
        )
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM raw_payload"),
            2,
        )

    def test_mark_failed_updates_source_state(self) -> None:
        run_id = self.store.start_run(SOURCE)
        self.store.mark_failed(run_id, SOURCE, "boom")

        run = self.store.get_run(run_id)
        assert run is not None
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error"], "boom")

        summary = self.store.status_summary(SOURCE)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(summary["consecutive_failures"], 1)
        self.assertEqual(summary["last_error"], "boom")

    def test_empty_store_summary(self) -> None:
        summary = self.store.status_summary(SOURCE)

        self.assertEqual(summary["total_runs"], 0)
        self.assertEqual(summary["unique_songs"], 0)
        self.assertEqual(summary["new_songs_24h"], 0)


class CollectorRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = CollectorStore(
            Path(self.temporary_directory.name) / "collector.db"
        )
        self.fixture = FIXTURE_PATH.read_bytes()

    def test_first_run_establishes_baseline(self) -> None:
        runner = CollectorRunner(
            FakeSource(self.fixture),
            self.store,
            config=RunnerConfig(retries=0),
        )

        outcome = runner.run_once()

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.counts.raw_count, 8)
        self.assertEqual(outcome.counts.dedup_count, 5)
        self.assertEqual(outcome.counts.valid_count, 4)
        self.assertEqual(outcome.counts.available_count, 2)
        self.assertEqual(outcome.counts.new_count, 0)
        self.assertEqual(outcome.counts.first_seen_count, 4)
        self.assertEqual(outcome.counts.dropped_count, 0)
        self.assertEqual(
            self.store.status_summary(FakeSource.name)["unique_songs"],
            4,
        )

    def test_second_run_is_idempotent(self) -> None:
        runner = CollectorRunner(
            FakeSource(self.fixture),
            self.store,
            config=RunnerConfig(retries=0),
        )

        first = runner.run_once()
        second = runner.run_once()

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(second.counts.new_count, 0)
        self.assertEqual(second.counts.first_seen_count, 0)
        self.assertEqual(second.counts.dropped_count, 0)
        self.assertEqual(
            self.store.status_summary(FakeSource.name)["unique_songs"],
            4,
        )

    def test_detects_dropped_songs_and_rank_changes(self) -> None:
        first_runner = CollectorRunner(
            FakeSource(make_chart_payload([1, 2, 3])),
            self.store,
            config=RunnerConfig(retries=0),
        )
        first_runner.run_once()

        second_runner = CollectorRunner(
            FakeSource(make_chart_payload([3, 1])),
            self.store,
            config=RunnerConfig(retries=0),
        )
        outcome = second_runner.run_once()

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.counts.new_count, 0)
        self.assertEqual(outcome.counts.dropped_count, 1)
        self.assertEqual(outcome.counts.rank_up_count, 1)
        self.assertEqual(outcome.counts.rank_down_count, 1)

    def test_detects_new_song(self) -> None:
        first_runner = CollectorRunner(
            FakeSource(make_chart_payload([1, 2])),
            self.store,
            config=RunnerConfig(retries=0),
        )
        first_runner.run_once()

        second_runner = CollectorRunner(
            FakeSource(make_chart_payload([1, 2, 3])),
            self.store,
            config=RunnerConfig(retries=0),
        )
        outcome = second_runner.run_once()

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.counts.new_count, 1)
        self.assertEqual(outcome.counts.first_seen_count, 1)
        self.assertEqual(outcome.counts.dropped_count, 0)

    def test_fetch_failure_records_failed_run(self) -> None:
        runner = CollectorRunner(
            FakeSource(self.fixture, fail_times=1),
            self.store,
            config=RunnerConfig(retries=0),
        )

        outcome = runner.run_once()

        self.assertFalse(outcome.success)
        run = self.store.get_run(outcome.run_id)
        assert run is not None
        self.assertEqual(run["status"], "failed")
        summary = self.store.status_summary(FakeSource.name)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(summary["consecutive_failures"], 1)
        self.assertEqual(summary["unique_songs"], 0)

    def test_retry_recovers_from_transient_failure(self) -> None:
        source = FakeSource(self.fixture, fail_times=1)
        runner = CollectorRunner(
            source,
            self.store,
            config=RunnerConfig(
                retries=1,
                retry_backoff_seconds=0,
            ),
        )

        outcome = runner.run_once()

        self.assertTrue(outcome.success)
        self.assertEqual(source.fetch_count, 2)

    def test_raw_payload_is_saved_on_parse_failure(self) -> None:
        runner = CollectorRunner(
            FakeSource(self.fixture, parse_error=True),
            self.store,
            config=RunnerConfig(retries=0),
        )

        outcome = runner.run_once()

        self.assertFalse(outcome.success)
        with sqlite3.connect(
            str(self.store.db_path)
        ) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM raw_blob"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM raw_payload"
                ).fetchone()[0],
                1,
            )

    def test_failed_run_does_not_disturb_previous_snapshot(self) -> None:
        first_runner = CollectorRunner(
            FakeSource(make_chart_payload([1, 2])),
            self.store,
            config=RunnerConfig(retries=0),
        )
        first_runner.run_once()

        failed_runner = CollectorRunner(
            FakeSource(self.fixture, parse_error=True),
            self.store,
            config=RunnerConfig(retries=0),
        )
        failed_runner.run_once()

        third_runner = CollectorRunner(
            FakeSource(make_chart_payload([1, 2])),
            self.store,
            config=RunnerConfig(retries=0),
        )
        outcome = third_runner.run_once()

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.counts.new_count, 0)
        self.assertEqual(outcome.counts.dropped_count, 0)


class FakeSchedulerRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run_once(self) -> RunOutcome:
        self.calls += 1
        return RunOutcome(
            run_id=self.calls,
            status="success",
            counts=RunCounts(),
        )


class SchedulerTests(unittest.TestCase):
    def test_runs_until_max_runs(self) -> None:
        runner = FakeSchedulerRunner()
        config = SchedulerConfig(
            interval_seconds=0.01,
            failure_backoff_seconds=0.01,
            max_backoff_seconds=0.02,
            max_doublings=1,
        )

        runs = run_forever(
            runner,  # type: ignore[arg-type]
            config=config,
            stop_event=threading.Event(),
            max_runs=2,
        )

        self.assertEqual(runs, 2)
        self.assertEqual(runner.calls, 2)

    def test_stop_event_prevents_runs(self) -> None:
        runner = FakeSchedulerRunner()
        stop_event = threading.Event()
        stop_event.set()
        config = SchedulerConfig(
            interval_seconds=0.01,
            failure_backoff_seconds=0.01,
            max_backoff_seconds=0.02,
            max_doublings=1,
        )

        runs = run_forever(
            runner,  # type: ignore[arg-type]
            config=config,
            stop_event=stop_event,
        )

        self.assertEqual(runs, 0)
        self.assertEqual(runner.calls, 0)

    def test_zero_max_runs_is_a_noop(self) -> None:
        runner = FakeSchedulerRunner()
        config = SchedulerConfig(
            interval_seconds=0.01,
            failure_backoff_seconds=0.01,
            max_backoff_seconds=0.02,
            max_doublings=1,
        )

        runs = run_forever(
            runner,  # type: ignore[arg-type]
            config=config,
            stop_event=threading.Event(),
            max_runs=0,
        )

        self.assertEqual(runs, 0)
        self.assertEqual(runner.calls, 0)


if __name__ == "__main__":
    unittest.main()
