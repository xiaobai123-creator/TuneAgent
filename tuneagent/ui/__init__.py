"""Web UI service layer kept separate from the Gradio presentation."""

from tuneagent.ui.service import (
    DEFAULT_PLATFORM_LABEL,
    RESULT_HEADERS,
    UIResult,
    available_platforms,
    run_search,
)

__all__ = [
    "DEFAULT_PLATFORM_LABEL",
    "RESULT_HEADERS",
    "UIResult",
    "available_platforms",
    "run_search",
]
