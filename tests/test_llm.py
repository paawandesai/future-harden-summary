import inspect
from types import SimpleNamespace
from typing import Any

from anthropic.resources.messages import Messages
from openai.resources.chat.completions import Completions

from weekly_summary.llm import AnthropicClient, OpenAIClient


class Recorder:
    def __init__(self, response: object) -> None:
        self.kwargs: dict[str, Any] = {}
        self._response = response

    def create(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        return self._response


def test_anthropic_client_call_matches_installed_sdk(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    client = AnthropicClient("claude-sonnet-5-5")
    recorder = Recorder(SimpleNamespace(content=[SimpleNamespace(type="text", text="Hi Maya. Jordan")]))
    monkeypatch.setattr(client, "_client", SimpleNamespace(messages=recorder))

    assert client.complete("system", "user") == "Hi Maya. Jordan"
    inspect.signature(Messages.create).bind(None, **recorder.kwargs)


def test_openai_client_call_matches_installed_sdk(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    client = OpenAIClient("gpt-5.5")
    message = SimpleNamespace(content="Hi Maya. Jordan")
    recorder = Recorder(SimpleNamespace(choices=[SimpleNamespace(message=message)]))
    monkeypatch.setattr(client, "_client", SimpleNamespace(chat=SimpleNamespace(completions=recorder)))

    assert client.complete("system", "user") == "Hi Maya. Jordan"
    inspect.signature(Completions.create).bind(None, **recorder.kwargs)
