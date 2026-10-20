# Weekly Summary

This app writes a weekly progress summary for a Future member. One LLM call writes the draft, and a coach approves it before the member reads it.

Read the assessment prompt for your task. Read `GUIDEBOOK.md` for the rules that the drafts must follow.

## Setup

You need [uv](https://docs.astral.sh/uv/). It installs Python 3.14 for you.

```
uv sync
```

Set a provider and an API key:

```
export LLM_PROVIDER=anthropic   # or openai
export ANTHROPIC_API_KEY=...    # or OPENAI_API_KEY
export LLM_MODEL=...            # optional
```

Set `LLM_PROVIDER=replay` to use the recorded drafts in the traces file. The replay client makes no API call. It ignores the system prompt, so a prompt change has no effect in replay mode.

## Commands

```
uv run weekly-summary show t_001        # print the input and the recorded draft for one trace
uv run weekly-summary generate t_001    # write a new draft for the input of one trace
uv run weekly-summary run               # write new drafts for all traces into runs/
uv run weekly-summary --traces other.jsonl run
uv run pytest
uv run ruff check .
uv run pyright
```

## Layout

| Path | What it does |
|---|---|
| `weekly_summary/models.py` | The data shapes: `MemberWeek` is the input, `Trace` is one logged call. |
| `weekly_summary/prompt.py` | The system prompt and the input format. |
| `weekly_summary/generate.py` | The feature. It sends one `MemberWeek` to the model and returns the draft. |
| `weekly_summary/llm.py` | The client wrapper for Anthropic, OpenAI, and replay. |
| `weekly_summary/data.py` | Loads traces from JSONL. |
| `data/traces.jsonl` | 60 recent production traces, with no labels. |
