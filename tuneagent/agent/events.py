"""Structured events exchanged between the agent core and presentation layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class EventKind(str, Enum):
    STATUS = "status"
    MODEL_SWITCH = "model_switch"
    TOOL_STARTED = "tool_started"
    SEARCH_RESULT = "search_result"
    DOWNLOAD_PROGRESS = "download_progress"
    DOWNLOAD_RESULT = "download_result"
    ASSISTANT_MESSAGE = "assistant_message"
    OFFLINE_FALLBACK = "offline_fallback"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AgentEvent:
    kind: EventKind
    message: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentTurnResult:
    final_text: str
    events: tuple[AgentEvent, ...]
