#!/usr/bin/env python3
"""Qwen-style interactive TuneAgent CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

from _bootstrap import ensure_project_root_on_path

PROJECT_ROOT = ensure_project_root_on_path()

try:
    from dotenv import load_dotenv
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.history import FileHistory
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError as error:
    print(
        "交互式 CLI 依赖未安装。请执行：\n"
        "python -m pip install -e '.[agent,real]'",
        file=sys.stderr,
    )
    raise SystemExit(1) from error

from tuneagent.agent.engine import AgentEngine
from tuneagent.agent.events import AgentEvent, EventKind
from tuneagent.agent.llm_client import (
    LLMClient,
    LLMClientError,
    LLMNoModelsError,
)
from tuneagent.agent.tool_executor import MusicToolExecutor
from tuneagent.cleaning.models import Song

APP_VERSION = "0.1.0"
DEFAULT_PROMPT = "国风 按热度 前15"
COMMANDS = ("/help", "/model", "/login", "/exit", "/quit")
_BANNER_LINES = (
    " _____ _   _ _   _ _____    _    ____ _____ _   _ _____",
    "|_   _| | | | \\ | | ____|  / \\  / ___| ____| \\ | |_   _|",
    "  | | | | | |  \\| |  _|   / _ \\| |  _|  _| |  \\| | | |",
    "  | | | |_| | |\\  | |___ / ___ \\ |_| | |___| |\\  | | |",
    "  |_|  \\___/|_| \\_|_____/_/   \\_\\____|_____|_| \\_| |_|",
)


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def _gradient_text(value: str, start: str, end: str) -> Text:
    start_rgb = _hex_to_rgb(start)
    end_rgb = _hex_to_rgb(end)
    result = Text()
    denominator = max(len(value) - 1, 1)
    for index, character in enumerate(value):
        ratio = index / denominator
        rgb = tuple(
            round(start_rgb[channel] + (end_rgb[channel] - start_rgb[channel]) * ratio)
            for channel in range(3)
        )
        result.append(character, style=f"bold #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}")
    return result


def render_banner(console: Console, engine: AgentEngine) -> None:
    for line in _BANNER_LINES:
        console.print(_gradient_text(line, "#2ee6ff", "#f06cff"))

    status = Table.grid(padding=(0, 2))
    status.add_column(style="bold cyan", no_wrap=True)
    status.add_column(style="white")
    status.add_row("Version", APP_VERSION)
    status.add_row("Model", engine.current_model_name)
    status.add_row(
        "Mode",
        "Netease live search" if engine.online else "Offline Mock fallback",
    )
    status.add_row("Commands", "/model  /login  /help  /exit")
    console.print(
        Panel(
            status,
            title="[bold magenta]TuneAgent[/bold magenta]",
            border_style="bright_blue",
            padding=(1, 2),
        )
    )
    console.print(
        "[dim]提示：直接输入自然语言，例如 "
        f"[/dim][cyan]{DEFAULT_PROMPT}[/cyan]"
    )


def format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "--:--"
    total_seconds = max(duration_ms, 0) // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def render_search_result(
    console: Console,
    data: Mapping[str, Any],
) -> None:
    report = data.get("report")
    songs = data.get("songs")
    if not isinstance(report, dict) or not isinstance(songs, list):
        return

    table = Table(
        title="清洗后的歌曲",
        header_style="bold magenta",
        border_style="bright_blue",
        show_lines=False,
    )
    table.add_column("#", justify="right", style="cyan", no_wrap=True)
    table.add_column("ID", justify="right", style="dim", no_wrap=True)
    table.add_column("歌名", style="bold white")
    table.add_column("歌手", style="bright_cyan")
    table.add_column("专辑", style="white")
    table.add_column("时长", justify="right")
    table.add_column("fee", justify="right")

    for index, raw_song in enumerate(songs, start=1):
        if not isinstance(raw_song, dict):
            continue
        table.add_row(
            Text(str(index)),
            Text(str(raw_song.get("id", "-"))),
            Text(str(raw_song.get("title", "-"))),
            Text(str(raw_song.get("artist", "-"))),
            Text(str(raw_song.get("album") or "未知专辑")),
            Text(format_duration(raw_song.get("duration_ms"))),
            Text(str(raw_song.get("fee", "-"))),
        )
    console.print(table)

    summary = str(report.get("summary", "")).strip()
    if summary:
        console.print(f"[bold green]{summary}[/bold green]")
    console.print(
        "[dim]排序指标：[/dim]"
        f"[cyan]{report.get('sort_metric_name', '-')}[/cyan]"
    )
    console.print(
        "[dim]说明：[/dim]"
        f"{report.get('sort_fallback_reason', '-')}"
    )
    fallback_reason = data.get("fallback_reason")
    if fallback_reason:
        console.print(f"[yellow]数据源降级：{fallback_reason}[/yellow]")


def render_event(console: Console, event: AgentEvent) -> None:
    if event.kind == EventKind.ASSISTANT_MESSAGE:
        console.print(Panel(Markdown(event.message), border_style="bright_blue"))
    elif event.kind == EventKind.SEARCH_RESULT:
        render_search_result(console, event.data)
    elif event.kind == EventKind.MODEL_SWITCH:
        console.print(f"[bold yellow]{event.message}[/bold yellow]")
    elif event.kind == EventKind.TOOL_STARTED:
        console.print(f"[dim cyan]>> {event.message}[/dim cyan]")
    elif event.kind == EventKind.OFFLINE_FALLBACK:
        console.print(f"[yellow]{event.message}[/yellow]")
    elif event.kind == EventKind.ERROR:
        console.print(f"[bold red]错误：{event.message}[/bold red]")
    elif event.kind == EventKind.STATUS:
        console.print(f"[cyan]{event.message}[/cyan]")
    elif event.kind == EventKind.DOWNLOAD_RESULT:
        data = event.data
        console.print(
            Panel(
                Text(
                    f"歌曲 ID: {data.get('song_id', '-')}\n"
                    f"文件: {data.get('path', '-')}\n"
                    f"大小: {data.get('size_bytes', '-')} bytes\n"
                    f"SHA-256: {data.get('sha256', '-')}",
                ),
                title="[bold green]下载完成[/bold green]",
                border_style="green",
            )
        )


def render_models(console: Console, engine: AgentEngine) -> None:
    views = engine.model_views()
    if not views:
        console.print("[yellow]当前为离线规则模式，没有加载在线模型。[/yellow]")
        return
    table = Table(title="模型配置", border_style="bright_blue")
    table.add_column("#", justify="right")
    table.add_column("名称")
    table.add_column("模型")
    table.add_column("API Key")
    table.add_column("状态")
    for view in views:
        table.add_row(
            str(view.index),
            view.name,
            view.model,
            "已配置" if view.configured else "未配置",
            "当前" if view.current else "",
        )
    console.print(table)
    console.print("[dim]切换模型：/model <序号或名称>[/dim]")


def check_login(console: Console, engine: AgentEngine) -> None:
    with console.status("[cyan]正在检查网易云登录状态...", spinner="dots"):
        status = engine.check_login()
    if status["ok"]:
        console.print(f"[bold green]{status['message']}[/bold green]")
    else:
        console.print(f"[bold yellow]{status['message']}[/bold yellow]")


def main() -> int:
    load_dotenv(
        dotenv_path=PROJECT_ROOT / ".env",
        override=False,
        encoding="utf-8",
    )
    console = Console(safe_box=True)

    try:
        llm_client = LLMClient.from_default_config()
        if not llm_client.has_any_api_key():
            console.print(
                "[yellow]未检测到模型 API Key，将使用离线规则模式。[/yellow]"
            )
    except (FileNotFoundError, LLMNoModelsError, ValueError) as error:
        console.print(f"[yellow]在线模型未加载：{error}[/yellow]")
        llm_client = None

    tools = MusicToolExecutor(PROJECT_ROOT, adapter_mode="auto")
    engine = AgentEngine(llm_client, tools)
    render_banner(console, engine)

    history_path = PROJECT_ROOT / ".tuneagent_history"
    session: PromptSession[str] = PromptSession(
        history=FileHistory(str(history_path)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=WordCompleter(COMMANDS, sentence=True),
    )
    prompt_text = HTML(
        "<ansicyan><b>TuneAgent</b></ansicyan> "
        "<ansimagenta>&gt;</ansimagenta> "
    )

    def confirm_download(song_id: int) -> bool:
        answer = session.prompt(
            HTML(
                f"<ansiyellow>确认下载歌曲 ID {song_id}? "
                "[y/N]: </ansiyellow>"
            )
        )
        return answer.strip().lower() in {"y", "yes"}

    while True:
        try:
            user_text = session.prompt(prompt_text).strip()
        except KeyboardInterrupt:
            console.print("[dim]已取消当前输入[/dim]")
            continue
        except EOFError:
            console.print("\n[dim]再见。[/dim]")
            return 0

        if not user_text:
            continue
        lowered = user_text.lower()
        if lowered in {"/exit", "/quit"}:
            console.print("[dim]再见。[/dim]")
            return 0
        if lowered == "/help":
            console.print(
                Panel(
                    Markdown(
                        "**自然语言示例**\n\n"
                        f"- `{DEFAULT_PROMPT}`\n"
                        "- `搜一下国风最火的5首`\n"
                        "- `下载 3334714206`（离线模式）\n\n"
                        "**命令**\n\n"
                        "- `/model` 查看模型，`/model 2` 切换\n"
                        "- `/login` 检查网易云 Cookie\n"
                        "- `/exit` 退出"
                    ),
                    border_style="bright_blue",
                )
            )
            continue
        if lowered == "/model":
            render_models(console, engine)
            continue
        if lowered.startswith("/model "):
            selector = user_text.split(maxsplit=1)[1]
            try:
                selected = engine.switch_model(selector)
            except LLMClientError as error:
                console.print(f"[red]{error}[/red]")
            else:
                console.print(f"[bold green]已切换模型：{selected}[/bold green]")
            continue
        if lowered == "/login":
            check_login(console, engine)
            continue
        if user_text.startswith("/"):
            console.print("[red]未知命令，输入 /help 查看帮助。[/red]")
            continue

        last_progress_bucket = -1

        def handle_event(event: AgentEvent) -> None:
            nonlocal last_progress_bucket
            if event.kind == EventKind.DOWNLOAD_PROGRESS:
                downloaded = int(event.data.get("downloaded", 0))
                total_value = event.data.get("total")
                total = int(total_value) if total_value else None
                if total:
                    percent = min(100, int(downloaded * 100 / total))
                    bucket = percent // 10
                    if bucket != last_progress_bucket:
                        console.print(f"[cyan]下载进度：{percent}%[/cyan]")
                        last_progress_bucket = bucket
                else:
                    console.print(
                        f"[cyan]已下载：{downloaded / 1024:.1f} KiB[/cyan]"
                    )
                return
            render_event(console, event)

        try:
            engine.run_turn(
                user_text,
                event_sink=handle_event,
                confirm_download=confirm_download,
            )
        except KeyboardInterrupt:
            console.print("[yellow]当前操作已取消。[/yellow]")
        except Exception as error:
            console.print(
                f"[bold red]Agent 运行错误：{type(error).__name__}: {error}[/bold red]"
            )


if __name__ == "__main__":
    raise SystemExit(main())
