import os
import threading
from typing import Protocol

import anthropic
import openai

from weekly_summary.models import Trace
from weekly_summary.prompt import render_user_message

DEFAULT_MODELS = {"anthropic": "claude-haiku-5-5", "openai": "gpt-5.5"}

# The project's own key name first; the SDK's usual name still works for a reviewer's key.
ANTHROPIC_KEY_VARS = ("ANTHROPIC_FUTURE_API_KEY", "ANTHROPIC_API_KEY")


# USD per million input and output tokens, for the spend report. Unknown models count as zero.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


def anthropic_api_key() -> str | None:
    return next((os.environ[v] for v in ANTHROPIC_KEY_VARS if os.environ.get(v)), None)


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str) -> str: ...


class AnthropicClient:
    # Haiku 5.5 and Sonnet 5.5 think by default, and thinking counts against max_tokens, so 1024 can cut
    # the answer off. Sampling parameters other than the defaults are rejected by these models.
    # A hung call costs up to timeout x (max_retries + 1). Single calls took 2-10 s in the dry run.
    def __init__(self, model: str, max_tokens: int = 8000, timeout: float = 60, max_retries: int = 3) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.input_tokens = 0
        self.output_tokens = 0
        self._lock = threading.Lock()
        self._client = anthropic.Anthropic(api_key=anthropic_api_key(), timeout=timeout, max_retries=max_retries)

    @property
    def cost_usd(self) -> float:
        price_in, price_out = PRICES.get(self.model, (0.0, 0.0))
        return (self.input_tokens * price_in + self.output_tokens * price_out) / 1e6

    def complete(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=self.max_tokens,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            with self._lock:
                self.input_tokens += usage.input_tokens
                self.output_tokens += usage.output_tokens
        if response.stop_reason == "max_tokens":
            raise RuntimeError("model output hit max_tokens")
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAIClient:
    def __init__(self, model: str, max_tokens: int = 1024, timeout: float = 60, max_retries: int = 3) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client = openai.OpenAI(timeout=timeout, max_retries=max_retries)

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_completion_tokens=self.max_tokens,
        )
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise RuntimeError("model output hit max_completion_tokens")
        return choice.message.content or ""


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
