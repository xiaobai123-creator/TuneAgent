#!/usr/bin/env python3
"""Run the TuneAgent unattended collector."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from _bootstrap import ensure_project_root_on_path

PROJECT_ROOT = ensure_project_root_on_path()

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

from tuneagent.collector.chart import NeteaseChartSource
from tuneagent.collector.runner import CollectorRunner, RunnerConfig
from tuneagent.collector.scheduler import SchedulerConfig, run_forever
from tuneagent.collector.store import CollectorStore

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "watch.toml"
DEFAULT_DB_PATH = "data/tuneagent.db"
DEFAULT_LOG_PATH = "logs/watch.log"


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as config_file:
        payload = tomllib.load(config_file)
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件必须是 TOML 表：{path}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TuneAgent 采集器：定时抓取网易云新歌榜并清洗入库。"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="配置文件路径（默认：config/watch.toml）",
    )
    parser.add_argument("--db", type=Path, help="SQLite 数据库路径")
    parser.add_argument("--interval", type=float, help="采集间隔（秒）")
    parser.add_argument("--once", action="store_true", help="只运行一轮")
    parser.add_argument(
        "--status",
        action="store_true",
        help="只查看运行状态，不抓取",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        help="最多运行几轮后退出（演示/测试用）",
    )
    parser.add_argument("--chart-id", type=int, help="网易云榜单 ID")
    parser.add_argument("--log-path", type=Path, help="日志文件路径")
    parser.add_argument("--verbose", action="store_true", help="输出 DEBUG 日志")
    return parser


def parse_settings(args: argparse.Namespace) -> dict[str, Any]:
    config_path = resolve_path(args.config)
    if not config_path.is_file() and args.config != DEFAULT_CONFIG_PATH:
        raise FileNotFoundError(f"配置文件不存在：{config_path}")
    payload = load_toml(config_path)

    collector = payload.get("collector", {})
    source = payload.get("source", {})
    if not isinstance(collector, dict) or not isinstance(source, dict):
        raise ValueError("配置中的 [collector] 和 [source] 必须是表")

    def pick(
        cli_value: Any,
        config_value: Any,
        default: Any,
    ) -> Any:
        if cli_value is not None:
            return cli_value
        if config_value is not None:
            return config_value
        return default

    db_path = resolve_path(
        pick(args.db, collector.get("db_path"), DEFAULT_DB_PATH)
    )
    log_path = resolve_path(
        pick(args.log_path, collector.get("log_path"), DEFAULT_LOG_PATH)
    )
    interval = float(
        pick(args.interval, collector.get("interval_seconds"), 1800)
    )
    failure_backoff = float(
        collector.get("failure_backoff_seconds", 300)
    )
    max_backoff = float(collector.get("max_backoff_seconds", 3600))
    timeout = float(collector.get("request_timeout_seconds", 20))
    retries = int(collector.get("retries", 2))
    retry_backoff = float(collector.get("retry_backoff_seconds", 2.0))
    source_type = str(source.get("type", "netease-chart"))
    source_name = str(source.get("name", "netease-new-songs"))
    chart_id = int(pick(args.chart_id, source.get("chart_id"), 3779629))
    chart_url = str(
        source.get(
            "chart_url",
            "https://music.163.com/api/playlist/detail",
        )
    )

    if source_type != "netease-chart":
        raise ValueError(
            f"当前只支持 netease-chart，收到：{source_type}"
        )
    if interval <= 0:
        raise ValueError("interval 必须大于 0")
    if timeout <= 0:
        raise ValueError("request_timeout_seconds 必须大于 0")
    if retries < 0:
        raise ValueError("retries 不能为负数")
    if retry_backoff < 0:
        raise ValueError("retry_backoff_seconds 不能为负数")

    return {
        "db_path": db_path,
        "log_path": log_path,
        "interval": interval,
        "failure_backoff": failure_backoff,
        "max_backoff": max_backoff,
        "timeout": timeout,
        "retries": retries,
        "retry_backoff": retry_backoff,
        "source_name": source_name,
        "chart_id": chart_id,
        "chart_url": chart_url,
    }


def setup_logging(log_path: Path, verbose: bool) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def format_local(value: str | None) -> str:
    if not value:
        return "暂无"
    try:
        return (
            datetime.fromisoformat(value)
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S %Z")
        )
    except ValueError:
        return value


def print_status(
    summary: dict[str, Any],
    runs: list[dict[str, Any]],
    *,
    source_name: str,
    db_path: Path,
) -> None:
    print("TuneAgent 采集状态")
    print(f"  数据源：{source_name}")
    print(f"  数据库：{db_path}")
    print(
        f"  总轮次：{summary['total_runs']}"
        f"（成功 {summary['successes']}，失败 {summary['failures']}）"
    )
    print(f"  最近成功：{format_local(summary['last_success_at'])}")
    print(f"  连续失败：{summary['consecutive_failures']}")
    print(f"  唯一歌曲：{summary['unique_songs']}")
    print(f"  最近 24h 新增：{summary['new_songs_24h']}")
    if summary["last_error"]:
        print(f"  最近错误：{summary['last_error']}")
    if runs:
        print("  最近采集：")
        for run in runs:
            error = (
                f"  error={run['error']}" if run.get("error") else ""
            )
            print(
                f"    #{run['id']} {run['status']} "
                f"{format_local(run['started_at'])} "
                f"raw={run['raw_count']} dedup={run['dedup_count']} "
                f"valid={run['valid_count']} new={run['new_count']} "
                f"dropped={run['dropped_count']}{error}"
            )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.once and args.status:
        parser.error("--once 与 --status 不能同时使用")
    if args.max_runs is not None and (args.once or args.status):
        parser.error("--max-runs 只用于常驻模式")

    try:
        settings = parse_settings(args)
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as error:
        print(f"配置错误：{error}", file=sys.stderr)
        return 2

    db_path: Path = settings["db_path"]
    if args.status and not db_path.exists():
        print(f"暂无采集数据：{db_path}")
        return 0

    try:
        store = CollectorStore(db_path)
        if args.status:
            summary = store.status_summary(settings["source_name"])
            runs = store.latest_runs(
                limit=5,
                source=settings["source_name"],
            )
            print_status(
                summary,
                runs,
                source_name=settings["source_name"],
                db_path=db_path,
            )
            return 0

        setup_logging(settings["log_path"], args.verbose)
        source = NeteaseChartSource(
            name=settings["source_name"],
            chart_url=settings["chart_url"],
            chart_id=settings["chart_id"],
            timeout=settings["timeout"],
        )
        runner = CollectorRunner(
            source,
            store,
            config=RunnerConfig(
                retries=settings["retries"],
                retry_backoff_seconds=settings["retry_backoff"],
            ),
        )

        if args.once:
            outcome = runner.run_once()
            return 0 if outcome.success else 1

        stop_event = threading.Event()

        def handle_signal(signum: int, _frame: Any) -> None:
            print(f"\n收到信号 {signum}，正在停止采集...")
            stop_event.set()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        scheduler_config = SchedulerConfig(
            interval_seconds=settings["interval"],
            failure_backoff_seconds=settings["failure_backoff"],
            max_backoff_seconds=settings["max_backoff"],
        )
        print(
            f"采集器已启动：{settings['source_name']}，"
            f"间隔 {settings['interval']:.0f}s，数据库 {db_path}"
        )
        run_forever(
            runner,
            config=scheduler_config,
            stop_event=stop_event,
            max_runs=args.max_runs,
        )
        return 0
    except KeyboardInterrupt:
        print("\n已停止。")
        return 0
    except (OSError, ValueError) as error:
        print(f"run_watch: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
