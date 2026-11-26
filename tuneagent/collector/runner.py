"""Orchestrate one unattended collection run."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

from tuneagent.collector.cleaning import (
    ParsedSource,
    clean_collected_songs,
)
from tuneagent.collector.store import (
    CollectorStore,
    RunCounts,
    utc_now,
)

LOG = logging.getLogger(__name__)


class CollectorSource(Protocol):
    name: str

    def fetch_raw(self) -> bytes:
        ...

    def parse(self, raw: bytes) -> ParsedSource:
        ...


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    retries: int = 2
    retry_backoff_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.retries < 0:
            raise ValueError("retries must be zero or greater")
        if self.retry_backoff_seconds < 0:
            raise ValueError(
                "retry_backoff_seconds must be zero or greater"
            )


@dataclass(frozen=True, slots=True)
class RunOutcome:
    run_id: int
    status: str
    counts: RunCounts = field(default_factory=RunCounts)
    error: str = ""

    @property
    def success(self) -> bool:
        return self.status == "success"

    def summary(self) -> str:
        if not self.success:
            return f"采集失败（run #{self.run_id}）：{self.error}"
        counts = self.counts
        return (
            f"采集成功（run #{self.run_id}）：原始 {counts.raw_count} -> "
            f"去重 {counts.dedup_count} -> 有效 {counts.valid_count}"
            f"（可用 {counts.available_count}）；新上榜 {counts.new_count}，"
            f"首次发现 {counts.first_seen_count}，掉榜 {counts.dropped_count}，"
            f"排名上升 {counts.rank_up_count}，下降 {counts.rank_down_count}"
        )


class CollectorRunner:
    """Run one fetch-clean-store cycle and record its outcome."""

    def __init__(
        self,
        source: CollectorSource,
        store: CollectorStore,
        *,
        config: RunnerConfig | None = None,
    ) -> None:
        self.source = source
        self.store = store
        self.config = config or RunnerConfig()

    def run_once(self) -> RunOutcome:
        started_at = utc_now()
        try:
            run_id = self.store.start_run(self.source.name, started_at)
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            LOG.exception("failed to start collector run")
            return RunOutcome(run_id=0, status="failed", error=message)

        try:
            raw = self._fetch_with_retry()
            fetched_at = utc_now()
            self.store.save_raw(
                run_id,
                self.source.name,
                raw,
                fetched_at,
            )
            parsed = self.source.parse(raw)
            cleaned = clean_collected_songs(
                parsed.songs,
                invalid_count=parsed.invalid_count,
            )
            ranks = {
                song.id: index
                for index, song in enumerate(cleaned.songs, start=1)
            }
            previous_run_id, previous_ranks = self.store.previous_snapshot(
                self.source.name,
                run_id,
            )
            current_ids = set(ranks)
            previous_ids = set(previous_ranks)

            if previous_run_id is None:
                new_ids: set[int] = set()
                dropped_count = 0
                rank_up_count = 0
                rank_down_count = 0
            else:
                new_ids = current_ids - previous_ids
                dropped_count = len(previous_ids - current_ids)
                common = current_ids & previous_ids
                rank_up_count = sum(
                    1
                    for song_id in common
                    if ranks[song_id] < previous_ranks[song_id]
                )
                rank_down_count = sum(
                    1
                    for song_id in common
                    if ranks[song_id] > previous_ranks[song_id]
                )

            first_seen_ids = self.store.find_new_song_ids(current_ids)
            counts = RunCounts(
                raw_count=cleaned.report.raw_count,
                dedup_count=cleaned.report.deduplicated_count,
                valid_count=cleaned.report.valid_count,
                available_count=cleaned.report.available_count,
                new_count=len(new_ids),
                first_seen_count=len(first_seen_ids),
                dropped_count=dropped_count,
                rank_up_count=rank_up_count,
                rank_down_count=rank_down_count,
            )
            finished_at = utc_now()
            self.store.commit_success(
                run_id,
                source=self.source.name,
                songs=cleaned.songs,
                ranks=ranks,
                previous_ranks=previous_ranks,
                new_ids=new_ids,
                counts=counts,
                report=cleaned.report,
                finished_at=finished_at,
            )
            outcome = RunOutcome(
                run_id=run_id,
                status="success",
                counts=counts,
            )
            LOG.info(outcome.summary())
            return outcome
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            try:
                self.store.mark_failed(
                    run_id,
                    self.source.name,
                    message,
                    utc_now(),
                )
            except Exception:
                LOG.exception("failed to record collector failure")
            LOG.exception("collector run failed: %s", message)
            return RunOutcome(
                run_id=run_id,
                status="failed",
                error=message,
            )

    def _fetch_with_retry(self) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self.config.retries + 1):
            try:
                return self.source.fetch_raw()
            except (ValueError, TypeError):
                raise
            except Exception as error:
                last_error = error
                if attempt >= self.config.retries:
                    break
                delay = self.config.retry_backoff_seconds * (2**attempt)
                LOG.warning(
                    "fetch attempt %d failed: %s; retrying in %.1fs",
                    attempt + 1,
                    error,
                    delay,
                )
                if delay:
                    time.sleep(delay)
        assert last_error is not None
        raise last_error
