from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tuneagent.agent.engine import AgentEngine
from tuneagent.agent.events import EventKind
from tuneagent.agent.llm_client import LLMCompletion, ToolCall
from tuneagent.agent.tool_executor import MusicToolExecutor
from tuneagent.platforms.real_download import RealDownloadResult

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeDownloader:
    def __init__(self) -> None:
        self.downloaded_song_id: int | None = None

    def download(
        self,
        song_id: int,
        dest_dir: str | Path,
        *,
        overwrite: bool = False,
        progress_callback: Any = None,
    ) -> RealDownloadResult:
        del dest_dir, overwrite
        self.downloaded_song_id = song_id
        if progress_callback:
            progress_callback(0, 100)
            progress_callback(100, 100)
        root = Path(tempfile.gettempdir())
        return RealDownloadResult(
            song_id=song_id,
            path=root / f"netease-{song_id}-standard.mp3",
            manifest_path=root / f"netease-{song_id}-standard.mp3.json",
            quality="standard",
            size_bytes=100,
            sha256="test-sha256",
        )

    def check_login(self) -> None:
        return None


class ScriptedLLM:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def current_model(self) -> SimpleNamespace:
        return SimpleNamespace(name="deepseek")

    def has_any_api_key(self) -> bool:
        return True

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        on_switch: Any = None,
    ) -> LLMCompletion:
        del tools, on_switch
        self.calls += 1
        if self.calls == 1:
            return LLMCompletion(
                content="",
                tool_calls=(
                    ToolCall(
                        id="call-1",
                        name="search_music",
                        arguments_json=json.dumps(
                            {
                                "keyword": "国风",
                                "sort_by": "hot",
                                "limit": 5,
                                "platform": "netease",
                            }
                        ),
                    ),
                ),
                model_name="deepseek",
            )
        self.asserted_tool_result = any(
            message.get("role") == "tool" for message in messages
        )
        return LLMCompletion(
            content="已找到可用国风歌曲。",
            tool_calls=(),
            model_name="deepseek",
        )


class AgentEngineTests(unittest.TestCase):
    def test_offline_search_emits_structured_results(self) -> None:
        tools = MusicToolExecutor(PROJECT_ROOT, adapter_mode="mock")
        engine = AgentEngine(None, tools)
        events = []

        result = engine.run_turn(
            "国风 按热度 前5",
            event_sink=events.append,
        )

        self.assertTrue(any(event.kind == EventKind.OFFLINE_FALLBACK for event in events))
        search_events = [
            event for event in events if event.kind == EventKind.SEARCH_RESULT
        ]
        self.assertEqual(len(search_events), 1)
        self.assertEqual(len(search_events[0].data["songs"]), 5)
        self.assertIn("最终 Top 5", result.final_text)

    def test_online_engine_executes_tool_call_and_returns_final_text(self) -> None:
        tools = MusicToolExecutor(PROJECT_ROOT, adapter_mode="mock")
        llm = ScriptedLLM()
        engine = AgentEngine(llm, tools)
        events = []

        result = engine.run_turn(
            "搜一下国风最火的5首",
            event_sink=events.append,
        )

        self.assertEqual(result.final_text, "已找到可用国风歌曲。")
        self.assertTrue(llm.asserted_tool_result)
        self.assertTrue(any(event.kind == EventKind.TOOL_STARTED for event in events))
        self.assertTrue(any(event.kind == EventKind.SEARCH_RESULT for event in events))

    def test_offline_download_requires_confirmation_and_emits_progress(self) -> None:
        downloader = FakeDownloader()
        tools = MusicToolExecutor(
            PROJECT_ROOT,
            adapter_mode="mock",
            downloader_factory=lambda: downloader,
        )
        engine = AgentEngine(None, tools)
        events = []

        result = engine.run_turn(
            "下载 12345",
            event_sink=events.append,
            confirm_download=lambda song_id: song_id == 12345,
        )

        self.assertEqual(downloader.downloaded_song_id, 12345)
        self.assertIn("已下载", result.final_text)
        progress_events = [
            event
            for event in events
            if event.kind == EventKind.DOWNLOAD_PROGRESS
        ]
        self.assertGreaterEqual(len(progress_events), 2)
        self.assertTrue(
            any(event.kind == EventKind.DOWNLOAD_RESULT for event in events)
        )


if __name__ == "__main__":
    unittest.main()
