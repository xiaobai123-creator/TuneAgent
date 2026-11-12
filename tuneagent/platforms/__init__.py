"""Platform adapter contracts and implementations."""

from tuneagent.platforms.base import (
    AdapterError,
    PlatformAdapter,
    UnsupportedOperationError,
)
from tuneagent.platforms.mock import MockNeteaseAdapter
from tuneagent.platforms.netease import NeteaseAdapter

__all__ = [
    "AdapterError",
    "MockNeteaseAdapter",
    "NeteaseAdapter",
    "PlatformAdapter",
    "UnsupportedOperationError",
]
