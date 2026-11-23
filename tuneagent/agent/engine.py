"""UI-independent interactive agent with tools and offline fallback."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from tuneagent.agent.events import AgentEvent, AgentTurnResult, EventKind
from tuneagent.agent.intent_parser import IntentParseError, parse_intent
from tuneagent.agent.llm_client import (
    AllModelsFailedError,
    LLMClient,
    LLMClientError,
    LLMNoModelsError,
    ModelView,
)
from tuneagent.agent.tool_executor import (
    TOOL_DEFINITIONS,
    MusicToolExecutor,
    SearchToolResult,
)

EventSink = Callable[[AgentEvent], None]
ConfirmationHandler = Callable[[int], bool]
_OFFLINE_DOWNLOAD_PATTERN = re.compile(
    r"^\s*(?:/download|下载)\s+(\d+)\s*$",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """你是 TuneAgent，一个中文网易云音乐搜索与下载助手。

规则：
1. 搜索音乐时必须调用 search_music，不要凭空生成歌曲或排行榜。
2. 只有用户明确要求下载且上下文中存在歌曲 ID 时，才调用 download_song。
3. 不请求、不展示 Cookie，也不讨论绕过 VIP、地区或版权限制。
4. 平台当前只支持 netease。
5. 回答使用简洁中文；当使用回退排序时，要如实说明指标来源。
6. 下载工具会由终端界面再次向用户确认，不要声称已经下载成功，除非工具返回成功。
7. 当用户询问实时信息、新闻、或音乐之外的领域知识，而你不确定答案时，
   调用 web_search 工具；给出结论时必须保留来源链接。
   若工具返回失败，如实说明"未获取到联网结果"，绝不编造。
"""


class AgentEngine:
    """Run model/tool turns and emit presentation-neutral events."""

    def __init__(
        self,
        llm_client: LLMClient | None,
        tools: MusicToolExecutor,
        *,
        max_tool_rounds: int = 4,
    ) -> None:
        self.llm_client = llm_client
        self.tools = tools
        self.max_tool_rounds = max_tool_rounds
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    @property
    def online(self) -> bool:
        return self.llm_client is not None and self.llm_client.has_any_api_key()

    @property
    def current_model_name(self) -> str:
        if self.llm_client is None or not self.llm_client.has_any_api_key():
            return "离线规则模式"
        return self.llm_client.current_model.name

    def model_views(self) -> tuple[ModelView, ...]:
        if self.llm_client is None:
            return ()
        return self.llm_client.model_views()

    def switch_model(self, selector: str) -> str:
        if self.llm_client is None:
            raise LLMClientError("当前没有加载任何在线模型")
        return self.llm_client.select_model(selector).name

    def check_login(self) -> dict[str, Any]:
        return self.tools.check_login()

    def run_turn(
        self,
        user_text: str,
        *,
        event_sink: EventSink | None = None,
        confirm_download: ConfirmationHandler | None = None,
    ) -> AgentTurnResult:
        events: list[AgentEvent] = []

        def emit(
            kind: EventKind,
            message: str = "",
            data: dict[str, Any] | None = None,
        ) -> None:
            event = AgentEvent(kind=kind, message=message, data=data or {})
            events.append(event)
            if event_sink:
                event_sink(event)

        normalized_text = user_text.strip()
        if not normalized_text:
            emit(EventKind.ERROR, "请输入搜索或下载请求")
            return AgentTurnResult(final_text="", events=tuple(events))

        if not self.online:
            emit(
                EventKind.OFFLINE_FALLBACK,
                "未配置可用 API Key，已进入离线规则模式",
            )
            result = self._offline_turn(
                normalized_text,
                emit,
                confirm_download,
            )
            return AgentTurnResult(final_text=result, events=tuple(events))

        self.messages.append({"role": "user", "content": normalized_text})
        for _ in range(self.max_tool_rounds):
            try:
                assert self.llm_client is not None
                completion = self.llm_client.complete(
                    self.messages,
                    TOOL_DEFINITIONS,
                    on_switch=lambda switch: emit(
                        EventKind.MODEL_SWITCH,
                        f"模型已自动切换：{switch.source} -> {switch.target}",
                        {
                            "source": switch.source,
                            "target": switch.target,
                            "reason": switch.reason,
                        },
                    ),
                )
            except (AllModelsFailedError, LLMNoModelsError, LLMClientError) as error:
                emit(
                    EventKind.OFFLINE_FALLBACK,
                    f"在线模型不可用，已降级为离线规则模式：{error}",
                )
                result = self._offline_turn(
                    normalized_text,
                    emit,
                    confirm_download,
                )
                self.messages.append({"role": "assistant", "content": result})
                self._trim_history()
                return AgentTurnResult(final_text=result, events=tuple(events))

            if completion.tool_calls:
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": completion.content or "",
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": call.arguments_json,
                                },
                            }
                            for call in completion.tool_calls
                        ],
                    }
                )
                for call in completion.tool_calls:
                    emit(
                        EventKind.TOOL_STARTED,
                        f"调用工具：{call.name}",
                        {"tool": call.name},
                    )
                    try:
                        arguments = json.loads(call.arguments_json)
                        if not isinstance(arguments, dict):
                            raise ValueError("工具参数必须是 JSON 对象")
                        tool_result = self.tools.execute(
                            call.name,
                            arguments,
                            confirm_download=confirm_download,
                            download_progress=lambda downloaded, total: emit(
                                EventKind.DOWNLOAD_PROGRESS,
                                "正在下载",
                                {
                                    "downloaded": downloaded,
                                    "total": total,
                                },
                            ),
                        )
                        content = dict(tool_result.content)
                    except (
                        json.JSONDecodeError,
                        OSError,
                        RuntimeError,
                        ValueError,
                    ) as error:
                        content = {
                            "ok": False,
                            "error": f"{type(error).__name__}: {error}",
                        }
                        emit(EventKind.ERROR, f"工具参数或执行失败：{error}")
                    else:
                        if (
                            call.name == "web_search"
                            and content.get("ok") is True
                        ):
                            emit(
                                EventKind.STATUS,
                                f"已检索到 {content.get('count', 0)} 条网页结果",
                            )
                        self._emit_tool_result(emit, tool_result)

                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(content, ensure_ascii=False),
                        }
                    )
                continue

            final_text = completion.content.strip()
            if not final_text:
                final_text = "请求已处理完成。"
            self.messages.append({"role": "assistant", "content": final_text})
            self._trim_history()
            emit(EventKind.ASSISTANT_MESSAGE, final_text)
            return AgentTurnResult(final_text=final_text, events=tuple(events))

        error_text = f"工具调用超过 {self.max_tool_rounds} 轮，已停止以避免循环"
        self._trim_history()
        emit(EventKind.ERROR, error_text)
        return AgentTurnResult(final_text=error_text, events=tuple(events))

    def _emit_tool_result(
        self,
        emit: Callable[..., None],
        result: Any,
    ) -> None:
        if result.search_result is not None:
            search_result: SearchToolResult = result.search_result
            emit(
                EventKind.SEARCH_RESULT,
                "搜索与清洗完成",
                {
                    "source": search_result.source,
                    "fallback_reason": search_result.fallback_reason,
                    "report": search_result.report.to_dict(),
                    "songs": [
                        song.to_dict() for song in search_result.songs
                    ],
                },
            )
        if result.download_result is not None:
            download_result = result.download_result
            if download_result.result is not None:
                emit(
                    EventKind.DOWNLOAD_RESULT,
                    "下载完成",
                    download_result.to_tool_content(),
                )
            elif download_result.cancelled:
                emit(EventKind.STATUS, "已取消下载")
            else:
                emit(EventKind.ERROR, download_result.error)

    def _offline_turn(
        self,
        user_text: str,
        emit: Callable[..., None],
        confirm_download: ConfirmationHandler | None,
    ) -> str:
        download_match = _OFFLINE_DOWNLOAD_PATTERN.match(user_text)
        if download_match:
            song_id = int(download_match.group(1))
            result = self.tools.download_song(
                song_id,
                confirm=confirm_download,
                progress_callback=lambda downloaded, total: emit(
                    EventKind.DOWNLOAD_PROGRESS,
                    "正在下载",
                    {"downloaded": downloaded, "total": total},
                ),
            )
            if result.result is not None:
                emit(
                    EventKind.DOWNLOAD_RESULT,
                    "下载完成",
                    result.to_tool_content(),
                )
                return f"歌曲 {song_id} 已下载。"
            if result.cancelled:
                emit(EventKind.STATUS, "已取消下载")
                return "已取消下载。"
            emit(EventKind.ERROR, result.error)
            return f"下载失败：{result.error}"

        try:
            intent = parse_intent(user_text)
            search_result = self.tools.search_music(
                intent.keyword,
                intent.sort_by,
                intent.limit,
                "netease",
                prefer_mock=True,
            )
        except (IntentParseError, ValueError) as error:
            emit(EventKind.ERROR, str(error))
            return (
                f"{error}\n离线模式支持“国风 按热度 前15”"
                "或“下载 <歌曲ID>”。"
            )

        emit(
            EventKind.SEARCH_RESULT,
            "离线搜索与清洗完成",
            {
                "source": search_result.source,
                "fallback_reason": search_result.fallback_reason,
                "report": search_result.report.to_dict(),
                "songs": [song.to_dict() for song in search_result.songs],
            },
        )
        if not search_result.songs:
            text = "离线 Mock 数据中没有找到可用歌曲。"
        else:
            text = search_result.report.summary()
        emit(EventKind.ASSISTANT_MESSAGE, text)
        return text

    def _trim_history(self) -> None:
        if len(self.messages) <= 40:
            return
        system_message = self.messages[0]
        self.messages = [system_message, *self.messages[-39:]]
