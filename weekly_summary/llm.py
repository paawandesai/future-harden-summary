from typing import Protocol

import anthropic
import openai

from weekly_summary.models import Trace
from weekly_summary.prompt import render_user_message

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-5.5"}


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str) -> str: ...


class AnthropicClient:
    def __init__(self, model: str, max_tokens: int = 1024) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic()

    def complete(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=self.max_tokens,
        )
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAIClient:
    def __init__(self, model: str, max_tokens: int = 1024) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client = openai.OpenAI()

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_completion_tokens=self.max_tokens,
        )
        return response.choices[0].message.content or ""


class ReplayClient:
    """Returns the recorded output for a known input. The system prompt is ignored."""

    model = "replay"

    def __init__(self, traces: list[Trace]) -> None:
        self._outputs = {render_user_message(t.input): t.output for t in traces}

    def complete(self, system: str, user: str) -> str:
        try:
            return self._outputs[user]
        except KeyError:
            raise LookupError(
                "ReplayClient has no recorded output for this input. "
                "It can only replay inputs that appear in its traces."
            ) from None


def make_client(provider: str, model: str | None, traces: list[Trace]) -> LLMClient:
    match provider:
        case "anthropic":
            return AnthropicClient(model or DEFAULT_MODELS["anthropic"])
        case "openai":
            return OpenAIClient(model or DEFAULT_MODELS["openai"])
        case "replay":
            return ReplayClient(traces)
    raise ValueError(f"Unknown LLM_PROVIDER {provider!r}. Use anthropic, openai, or replay.")
