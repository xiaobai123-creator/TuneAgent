from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tuneagent.agent.llm_client import (
    AllModelsFailedError,
    LLMClient,
    LLMNoModelsError,
    ModelConfig,
)


class RateLimitFailure(Exception):
    status_code = 429


def completion_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                    tool_calls=[],
                )
            )
        ]
    )


class FakeChatClient:
    def __init__(self, response: object) -> None:
        create = (
            response
            if callable(response)
            else lambda **_: response
        )
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=create)
        )


def model(name: str, key_env: str, priority: int) -> ModelConfig:
    return ModelConfig(
        name=name,
        model=f"{name}-model",
        base_url="https://example.test/v1",
        api_key_env=key_env,
        priority=priority,
    )


class LLMClientTests(unittest.TestCase):
    def test_fails_over_after_rate_limit(self) -> None:
        models = [
            model("primary", "PRIMARY_KEY", 10),
            model("backup", "BACKUP_KEY", 20),
        ]
        switches: list[str] = []

        def factory(config: ModelConfig, api_key: str) -> FakeChatClient:
            del api_key
            if config.name == "primary":
                def fail(**_: object) -> object:
                    raise RateLimitFailure("rate limit")

                return FakeChatClient(fail)
            return FakeChatClient(completion_response("backup answer"))

        with patch.dict(
            os.environ,
            {"PRIMARY_KEY": "a", "BACKUP_KEY": "b"},
            clear=True,
        ):
            client = LLMClient(models, client_factory=factory)
            result = client.complete(
                [{"role": "user", "content": "hello"}],
                [],
                on_switch=lambda event: switches.append(event.target),
            )

        self.assertEqual(result.content, "backup answer")
        self.assertEqual(result.model_name, "backup")
        self.assertEqual(switches, ["backup"])
        self.assertEqual(client.current_model.name, "backup")

    def test_reports_all_models_failed(self) -> None:
        models = [model("only", "ONLY_KEY", 10)]

        def factory(config: ModelConfig, api_key: str) -> FakeChatClient:
            del config, api_key

            def fail(**_: object) -> object:
                raise RateLimitFailure("quota exhausted")

            return FakeChatClient(fail)

        with patch.dict(os.environ, {"ONLY_KEY": "a"}, clear=True):
            client = LLMClient(models, client_factory=factory)
            with self.assertRaises(AllModelsFailedError):
                client.complete([], [])

    def test_no_api_key_raises_offline_signal(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            client = LLMClient([model("offline", "MISSING_KEY", 10)])
            self.assertFalse(client.has_any_api_key())
            with self.assertRaises(LLMNoModelsError):
                client.complete([], [])

    def test_parses_function_tool_call(self) -> None:
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="search_music",
                arguments='{"keyword":"国风","sort_by":"hot","limit":5}',
            ),
        )
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="",
                        tool_calls=[tool_call],
                    )
                )
            ]
        )
        models = [model("tool-model", "TOOL_KEY", 10)]
        with patch.dict(os.environ, {"TOOL_KEY": "key"}, clear=True):
            client = LLMClient(
                models,
                client_factory=lambda config, key: FakeChatClient(response),
            )
            result = client.complete([], [])

        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0].name, "search_music")
        self.assertIn('"国风"', result.tool_calls[0].arguments_json)


if __name__ == "__main__":
    unittest.main()
