"""SQLite persistence for unattended chart collection."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from tuneagent.cleaning.models import Song
from tuneagent.collector.cleaning import CollectedCleaningReport

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS crawl_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    raw_count INTEGER NOT NULL DEFAULT 0,
    dedup_count INTEGER NOT NULL DEFAULT 0,
    valid_count INTEGER NOT NULL DEFAULT 0,
    available_count INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    first_seen_count INTEGER NOT NULL DEFAULT 0,
    dropped_count INTEGER NOT NULL DEFAULT 0,
    rank_up_count INTEGER NOT NULL DEFAULT 0,
    rank_down_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    quality_json TEXT
);

CREATE TABLE IF NOT EXISTS raw_blob (
    sha256 TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    first_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_payload (
    run_id INTEGER PRIMARY KEY REFERENCES crawl_run(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    sha256 TEXT NOT NULL REFERENCES raw_blob(sha256)
);

CREATE TABLE IF NOT EXISTS song (
    song_id INTEGER PRIMARY KEY,
    platform TEXT NOT NULL,
    title TEXT NOT NULL,
    artists TEXT NOT NULL,
    album TEXT,
    duration_ms INTEGER,
    fee INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_run_id INTEGER NOT NULL REFERENCES crawl_run(id)
);

CREATE TABLE IF NOT EXISTS song_snapshot (
    run_id INTEGER NOT NULL REFERENCES crawl_run(id) ON DELETE CASCADE,
    song_id INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    last_rank INTEGER,
    rank_delta INTEGER,
    is_new INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, song_id)
);

CREATE TABLE IF NOT EXISTS source_state (
    source TEXT PRIMARY KEY,
    last_success_at TEXT,
    last_error TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    total_runs INTEGER NOT NULL DEFAULT 0,
    total_failures INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_crawl_run_source_started
    ON crawl_run(source, started_at);
CREATE INDEX IF NOT EXISTS idx_song_first_seen ON song(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_song_last_seen ON song(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_snapshot_song ON song_snapshot(song_id);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class RunCounts:
    raw_count: int = 0
    dedup_count: int = 0
    valid_count: int = 0
    available_count: int = 0
    new_count: int = 0
    first_seen_count: int = 0
    dropped_count: int = 0
    rank_up_count: int = 0
    rank_down_count: int = 0


def _chunks(values: Sequence[int], size: int) -> Iterator[Sequence[int]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


class CollectorStore:
    """Persist raw payloads, cleaned songs, snapshots, and run reports."""

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        self.db_path = path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.db_path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(_SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def start_run(self, source: str, started_at: str | None = None) -> int:
        started = started_at or utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO source_state(source) VALUES (?) "
                "ON CONFLICT(source) DO NOTHING",
                (source,),
            )
            connection.execute(
                "UPDATE source_state SET total_runs = total_runs + 1 "
                "WHERE source = ?",
                (source,),
            )
            cursor = connection.execute(
                "INSERT INTO crawl_run(source, started_at, status) "
                "VALUES (?, ?, 'running')",
                (source, started),
            )
            return int(cursor.lastrowid)

    def save_raw(
        self,
        run_id: int,
        source: str,
        raw: bytes,
        fetched_at: str | None = None,
    ) -> str:
        fetched = fetched_at or utc_now()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("raw response is not valid UTF-8") from error

        digest = hashlib.sha256(raw).hexdigest()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO raw_blob"
                "(sha256, content, size_bytes, first_seen_at) "
                "VALUES (?, ?, ?, ?)",
                (digest, content, len(raw), fetched),
            )
            connection.execute(
                "INSERT OR REPLACE INTO raw_payload"
                "(run_id, source, fetched_at, sha256) VALUES (?, ?, ?, ?)",
                (run_id, source, fetched, digest),
            )
        return digest

    def find_new_song_ids(self, song_ids: Iterable[int]) -> set[int]:
        requested = {int(song_id) for song_id in song_ids}
        if not requested:
            return set()

        existing: set[int] = set()
        ordered = sorted(requested)
        with self._connect() as connection:
            for chunk in _chunks(ordered, 500):
                placeholders = ", ".join("?" for _ in chunk)
                rows = connection.execute(
                    f"SELECT song_id FROM song WHERE song_id IN ({placeholders})",
                    tuple(chunk),
                ).fetchall()
                existing.update(int(row["song_id"]) for row in rows)
        return requested - existing

    def previous_snapshot(
        self,
        source: str,
        run_id: int,
    ) -> tuple[int | None, dict[int, int]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM crawl_run "
                "WHERE source = ? AND status = 'success' AND id < ? "
                "ORDER BY id DESC LIMIT 1",
                (source, run_id),
            ).fetchone()
            if row is None:
                return None, {}
            previous_run_id = int(row["id"])
            rows = connection.execute(
                "SELECT song_id, rank FROM song_snapshot WHERE run_id = ?",
                (previous_run_id,),
            ).fetchall()
        return previous_run_id, {
            int(item["song_id"]): int(item["rank"]) for item in rows
        }

    def commit_success(
        self,
        run_id: int,
        *,
        source: str,
        songs: Sequence[Song],
        ranks: Mapping[int, int],
        previous_ranks: Mapping[int, int],
        new_ids: set[int],
        counts: RunCounts,
        report: CollectedCleaningReport,
        finished_at: str | None = None,
    ) -> None:
        finished = finished_at or utc_now()
        quality_json = json.dumps(report.to_dict(), ensure_ascii=False)
        with self._connect() as connection:
            self._upsert_songs(connection, songs, run_id, finished)
            self._save_snapshot(
                connection,
                run_id,
                ranks,
                previous_ranks,
                new_ids,
            )
            connection.execute(
                """
                UPDATE crawl_run SET
                    finished_at = ?, status = 'success',
                    raw_count = ?, dedup_count = ?, valid_count = ?,
                    available_count = ?, new_count = ?, first_seen_count = ?,
                    dropped_count = ?, rank_up_count = ?, rank_down_count = ?,
                    error = NULL, quality_json = ?
                WHERE id = ?
                """,
                (
                    finished,
                    counts.raw_count,
                    counts.dedup_count,
                    counts.valid_count,
                    counts.available_count,
                    counts.new_count,
                    counts.first_seen_count,
                    counts.dropped_count,
                    counts.rank_up_count,
                    counts.rank_down_count,
                    quality_json,
                    run_id,
                ),
            )
            connection.execute(
                "UPDATE source_state SET last_success_at = ?, "
                "last_error = NULL, consecutive_failures = 0 "
                "WHERE source = ?",
                (finished, source),
            )

    def mark_failed(
        self,
        run_id: int,
        source: str,
        error: str,
        finished_at: str | None = None,
    ) -> None:
        finished = finished_at or utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE crawl_run SET finished_at = ?, status = 'failed', "
                "error = ? WHERE id = ?",
                (finished, error, run_id),
            )
            connection.execute(
                "UPDATE source_state SET last_error = ?, "
                "consecutive_failures = consecutive_failures + 1, "
                "total_failures = total_failures + 1 WHERE source = ?",
                (error, source),
            )

    @staticmethod
    def _upsert_songs(
        connection: sqlite3.Connection,
        songs: Sequence[Song],
        run_id: int,
        seen_at: str,
    ) -> None:
        rows = [
            (
                song.id,
                song.platform,
                song.title,
                json.dumps(list(song.artists), ensure_ascii=False),
                song.album,
                song.duration_ms,
                song.fee,
                seen_at,
                seen_at,
                run_id,
            )
            for song in songs
        ]
        if not rows:
            return
        connection.executemany(
            """
            INSERT INTO song(
                song_id, platform, title, artists, album, duration_ms, fee,
                first_seen_at, last_seen_at, last_run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(song_id) DO UPDATE SET
                platform = excluded.platform,
                title = excluded.title,
                artists = excluded.artists,
                album = excluded.album,
                duration_ms = excluded.duration_ms,
                fee = excluded.fee,
                last_seen_at = excluded.last_seen_at,
                last_run_id = excluded.last_run_id
            """,
            rows,
        )

    @staticmethod
    def _save_snapshot(
        connection: sqlite3.Connection,
        run_id: int,
        ranks: Mapping[int, int],
        previous_ranks: Mapping[int, int],
        new_ids: set[int],
    ) -> None:
        rows = []
        for song_id, rank in ranks.items():
            last_rank = previous_ranks.get(song_id)
            rank_delta = None if last_rank is None else last_rank - rank
            rows.append(
                (
                    run_id,
                    song_id,
                    rank,
                    last_rank,
                    rank_delta,
                    1 if song_id in new_ids else 0,
                )
            )
        if not rows:
            return
        connection.executemany(
            """
            INSERT OR REPLACE INTO song_snapshot(
                run_id, song_id, rank, last_rank, rank_delta, is_new
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM crawl_run WHERE id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def latest_runs(
        self,
        limit: int = 5,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 100))
        query = (
            "SELECT id, source, started_at, finished_at, status, "
            "raw_count, dedup_count, valid_count, available_count, "
            "new_count, first_seen_count, dropped_count, "
            "rank_up_count, rank_down_count, error "
            "FROM crawl_run"
        )
        params: list[Any] = []
        if source:
            query += " WHERE source = ?"
            params.append(source)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(safe_limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def status_summary(self, source: str | None = None) -> dict[str, Any]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=24)
        ).isoformat(timespec="seconds")
        where = " WHERE source = ?" if source else ""
        params: tuple[Any, ...] = (source,) if source else ()
        with self._connect() as connection:
            run_row = connection.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successes, "
                "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failures, "
                "MAX(CASE WHEN status = 'success' THEN finished_at END) "
                "AS last_success "
                f"FROM crawl_run{where}",
                params,
            ).fetchone()
            song_row = connection.execute(
                "SELECT COUNT(*) AS unique_songs FROM song"
            ).fetchone()
            new_row = connection.execute(
                "SELECT COUNT(*) AS new_songs FROM song "
                "WHERE first_seen_at >= ?",
                (cutoff,),
            ).fetchone()
            state_row = None
            if source:
                state_row = connection.execute(
                    "SELECT consecutive_failures, last_error "
                    "FROM source_state WHERE source = ?",
                    (source,),
                ).fetchone()

        return {
            "total_runs": int(run_row["total"] or 0),
            "successes": int(run_row["successes"] or 0),
            "failures": int(run_row["failures"] or 0),
            "last_success_at": run_row["last_success"],
            "unique_songs": int(song_row["unique_songs"] or 0),
            "new_songs_24h": int(new_row["new_songs"] or 0),
            "consecutive_failures": (
                int(state_row["consecutive_failures"] or 0)
                if state_row is not None
                else 0
            ),
            "last_error": (
                state_row["last_error"] if state_row is not None else None
            ),
        }
