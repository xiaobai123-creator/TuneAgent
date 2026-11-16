"""OpenAI-compatible chat client with ordered model failover."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "llm_models.toml"
DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class ModelConfig:
    name: str
    model: str
    base_url: str
    api_key_env: str
    priority: int = 100
    temperature: float = 0.2


@dataclass(frozen=True, slots=True)
class ModelView:
    index: int
    name: str
    model: str
    configured: bool
    current: bool


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class LLMCompletion:
    content: str
    tool_calls: tuple[ToolCall, ...]
    model_name: str


@dataclass(frozen=True, slots=True)
class ModelSwitch:
    source: str
    target: str
    reason: str


class LLMClientError(RuntimeError):
    """Base error raised by the model client."""


class LLMNoModelsError(LLMClientError):
    """Raised when no model is configured or has an API key."""


class LLMModelNotFoundError(LLMClientError):
    """Raised when a manual model selector does not match."""


class AllModelsFailedError(LLMClientError):
    """Raised after every configured model failed."""

    def __init__(self, failures: list[str]) -> None:
        self.failures = tuple(failures)
        detail = "; ".join(failures) if failures else "no available model"
        super().__init__(f"所有模型均不可用：{detail}")


def load_model_configs(path: str | Path | None = None) -> list[ModelConfig]:
    config_path = Path(
        path or os.getenv("LLM_MODEL_CONFIG", str(DEFAULT_CONFIG_PATH))
    ).expanduser()
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    if not config_path.is_file():
        raise FileNotFoundError(f"模型配置文件不存在：{config_path}")

    with config_path.open("rb") as config_file:
        payload = tomllib.load(config_file)
    raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        raise ValueError("模型配置缺少 [[models]] 数组")

    models: list[ModelConfig] = []
    names: set[str] = set()
    for raw_model in raw_models:
        if not isinstance(raw_model, dict):
            raise ValueError("模型配置项必须是对象")
        try:
            model = ModelConfig(
                name=str(raw_model["name"]),
                model=str(raw_model["model"]),
                base_url=str(raw_model["base_url"]),
                api_key_env=str(raw_model["api_key_env"]),
                priority=int(raw_model.get("priority", 100)),
                temperature=float(raw_model.get("temperature", 0.2)),
            )
        except KeyError as error:
            raise ValueError(f"模型配置缺少字段：{error.args[0]}") from error
        if model.name in names:
            raise ValueError(f"模型配置名称重复：{model.name}")
        names.add(model.name)
        models.append(model)
    return sorted(models, key=lambda item: (item.priority, item.name))


def _default_client_factory(
    model: ModelConfig,
    api_key: str,
) -> Any:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise LLMClientError(
            "OpenAI SDK 未安装，请执行 python -m pip install -e '.[agent]'"
        ) from error
    return OpenAI(
        api_key=api_key,
        base_url=model.base_url,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _is_failover_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code in {401, 403, 408, 409, 429, 500, 502, 503, 504}:
        return True

    error_name = type(error).__name__.lower()
    message = str(error).lower()
    markers = (
        "ratelimit",
        "rate limit",
        "insufficientquota",
        "insufficient quota",
        "quota",
        "authentication",
        "api key",
        "connection",
        "timeout",
        "overloaded",
        "unavailable",
        "does not exist",
        "model not found",
        "unsupported model",
    )
    return any(marker in error_name or marker in message for marker in markers)


class LLMClient:
    """Failover-capable client with no presentation-layer dependencies."""

    def __init__(
        self,
        models: list[ModelConfig],
        *,
        client_factory: Callable[[ModelConfig, str], Any] | None = None,
    ) -> None:
        if not models:
            raise LLMNoModelsError("没有配置任何模型")
        self.models = tuple(models)
        self.client_factory = client_factory or _default_client_factory
        self.active_index = 0
        self._clients: dict[str, Any] = {}

    @classmethod
    def from_default_config(
        cls,
        path: str | Path | None = None,
        *,
        client_factory: Callable[[ModelConfig, str], Any] | None = None,
    ) -> LLMClient:
        return cls(
            load_model_configs(path),
            client_factory=client_factory,
        )

    def _api_key(self, model: ModelConfig) -> str:
        return os.getenv(model.api_key_env, "").strip()

    def has_any_api_key(self) -> bool:
        return any(self._api_key(model) for model in self.models)

    @property
    def current_model(self) -> ModelConfig:
        return self.models[self.active_index]

    def model_views(self) -> tuple[ModelView, ...]:
        return tuple(
            ModelView(
                index=index + 1,
                name=model.name,
                model=model.model,
                configured=bool(self._api_key(model)),
                current=index == self.active_index,
            )
            for index, model in enumerate(self.models)
        )

    def select_model(self, selector: str) -> ModelConfig:
        normalized = selector.strip()
        if not normalized:
            raise LLMModelNotFoundError("模型选择器不能为空")

        if normalized.isdigit():
            index = int(normalized) - 1
            if 0 <= index < len(self.models):
                model = self.models[index]
                if not self._api_key(model):
                    raise LLMModelNotFoundError(
                        f"模型 {model.name} 未配置 {model.api_key_env}"
                    )
                self.active_index = index
                return model

        for index, model in enumerate(self.models):
            if normalized in {model.name, model.model}:
                if not self._api_key(model):
                    raise LLMModelNotFoundError(
                        f"模型 {model.name} 未配置 {model.api_key_env}"
                    )
                self.active_index = index
                return model
        raise LLMModelNotFoundError(f"找不到模型：{selector}")

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        on_switch: Callable[[ModelSwitch], None] | None = None,
    ) -> LLMCompletion:
        if not self.has_any_api_key():
            raise LLMNoModelsError("没有配置可用的模型 API Key")

        original = self.current_model
        ordered = [
            self.current_model,
            *(
                model
                for model in self.models
                if model.name != self.current_model.name
            ),
        ]
        failures: list[str] = []
        last_reason = "主模型不可用"

        for model in ordered:
            api_key = self._api_key(model)
            if not api_key:
                failures.append(f"{model.name}: 缺少 {model.api_key_env}")
                last_reason = f"{model.name} 未配置 API Key"
                continue

            try:
                client = self._clients.get(model.name)
                if client is None:
                    client = self.client_factory(model, api_key)
                    self._clients[model.name] = client
                response = client.chat.completions.create(
                    model=model.model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=model.temperature,
                )
                completion = self._parse_completion(response, model)
            except Exception as error:
                if not _is_failover_error(error):
                    raise LLMClientError(
                        f"{model.name} 请求失败：{type(error).__name__}"
                    ) from error
                last_reason = f"{model.name}: {type(error).__name__}"
                failures.append(last_reason)
                continue

            selected_index = self.models.index(model)
            if selected_index != self.active_index:
                self.active_index = selected_index
                if on_switch:
                    on_switch(
                        ModelSwitch(
                            source=original.name,
                            target=model.name,
                            reason=last_reason,
                        )
                    )
            return completion

        raise AllModelsFailedError(failures)

    @staticmethod
    def _parse_completion(response: Any, model: ModelConfig) -> LLMCompletion:
        choices = getattr(response, "choices", None)
        if not choices:
            raise ValueError("模型响应缺少 choices")
        message = getattr(choices[0], "message", None)
        if message is None:
            raise ValueError("模型响应缺少 message")

        content = getattr(message, "content", "") or ""
        if not isinstance(content, str):
            content = str(content)

        tool_calls: list[ToolCall] = []
        raw_calls = getattr(message, "tool_calls", None) or []
        for index, raw_call in enumerate(raw_calls):
            function = getattr(raw_call, "function", None)
            name = getattr(function, "name", None)
            arguments = getattr(function, "arguments", "{}")
            call_id = getattr(raw_call, "id", None) or f"call_{index}"
            if not isinstance(name, str) or not name:
                continue
            if not isinstance(arguments, str):
                arguments = str(arguments)
            tool_calls.append(
                ToolCall(
                    id=str(call_id),
                    name=name,
                    arguments_json=arguments,
                )
            )
        return LLMCompletion(
            content=content,
            tool_calls=tuple(tool_calls),
            model_name=model.name,
        )
