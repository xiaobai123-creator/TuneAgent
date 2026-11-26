"""Run the collector on an interval with failure backoff."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from tuneagent.collector.runner import CollectorRunner

LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SchedulerConfig:
    interval_seconds: float = 1800.0
    failure_backoff_seconds: float = 300.0
    max_backoff_seconds: float = 3600.0
    max_doublings: int = 5

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        if self.failure_backoff_seconds <= 0:
            raise ValueError(
                "failure_backoff_seconds must be greater than zero"
            )
        if self.max_backoff_seconds < self.failure_backoff_seconds:
            raise ValueError(
                "max_backoff_seconds must be >= failure_backoff_seconds"
            )
        if self.max_doublings < 0:
            raise ValueError("max_doublings must be zero or greater")


def run_forever(
    runner: CollectorRunner,
    *,
    config: SchedulerConfig,
    stop_event: threading.Event,
    max_runs: int | None = None,
) -> int:
    if max_runs is not None and max_runs <= 0:
        return 0

    runs = 0
    failures = 0
    while not stop_event.is_set():
        outcome = runner.run_once()
        runs += 1
        if outcome.success:
            failures = 0
            delay = config.interval_seconds
        else:
            failures += 1
            doublings = min(failures - 1, config.max_doublings)
            delay = min(
                config.failure_backoff_seconds * (2**doublings),
                config.max_backoff_seconds,
            )
        if max_runs is not None and runs >= max_runs:
            LOG.info("reached max runs (%d); stopping", max_runs)
            break
        LOG.info("next collection in %.0f seconds", delay)
        if stop_event.wait(delay):
            break
    LOG.info("collector scheduler stopped after %d run(s)", runs)
    return runs
