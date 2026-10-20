# Weekly Summary

This app writes a weekly progress summary for a Future member. A fixed workflow drafts it, checks it against `GUIDEBOOK.md`, and decides pass, flag or block, and a coach approves it before the member reads it. `WRITEUP.md` explains the design and results, and `ASSESSMENT.md` is the original brief.

## Setup

You need [uv](https://docs.astral.sh/uv/). It installs Python 3.14 for you.

```
uv sync
```

Install the git hooks once per clone:

```
uv run pre-commit install
```

On commit they format and lint the staged Python files (under a second). On push they run pyright and the
test suite (a few seconds). CI runs the same checks, so the hooks only save you a round trip.

Set a provider and an API key:

```
export LLM_PROVIDER=anthropic   # or openai
export ANTHROPIC_API_KEY=...    # or OPENAI_API_KEY
export LLM_MODEL=...            # optional
```

The judge has its own provider, `JUDGE_PROVIDER` (default `anthropic`), so the judge and the confirm step need an
Anthropic key even when `LLM_PROVIDER=openai`. With `JUDGE_PROVIDER=openai`, pass `--confirm-model` with an OpenAI
model, or the confirm step is skipped.

Set `LLM_PROVIDER=replay` to use the recorded drafts in the traces file. The replay client makes no API call. It ignores the system prompt, so a prompt change has no effect in replay mode.

## Pipeline (feature, evals and guardrails)

One command runs everything on a traces file and writes one line per trace:
`{"trace_id": "t_001", "decision": "flag", "reasons": ["..."]}`.

```
uv run weekly-summary pipeline data/traces.jsonl --out results/decisions.jsonl --details results/details.jsonl  # new drafts, then check and decide
uv run weekly-summary pipeline data/traces.jsonl --no-generate --details results/details.jsonl  # decide the drafts already in the file
uv run weekly-summary pipeline data/traces.jsonl --code-only --details results/details.jsonl    # same, without the LLM judge (no API key)
uv run weekly-summary evaluate results/details.jsonl                                          # metrics vs labels/labels.jsonl
uv run weekly-summary compare before_details.jsonl after_details.jsonl                         # what moved; exit 1 if worse
uv run weekly-summary gate                                                                     # frozen labeled sets vs evals/gate.toml (CI runs this)
uv run weekly-summary view results/details.jsonl --out review.html                             # coach view: decisions, reasons, highlights
uv run weekly-summary crosscheck results/a.jsonl results/b.jsonl --names Sonnet Haiku          # judge vs judge, per rule
uv run weekly-summary cache-manifest                                                           # after adding judge verdicts on purpose
```

`--code-only` is a smoke mode, not a safety mode: without the judge it lets 8 of the 30 labeled violations in the
blind challenge set pass. Use it to check the pipeline runs, not to approve drafts.

Add `--details results/details.jsonl` to keep every finding and draft for `evaluate`. The key is
read from `ANTHROPIC_FUTURE_API_KEY`, then `ANTHROPIC_API_KEY`. Models come from `LLM_MODEL`
(generator) and `JUDGE_MODEL`; both default to Haiku. When only the judge finds an "other" problem, `--confirm-model`
(default `claude-sonnet-5-5`, `none` to skip) must agree before it flags. `--max-calls` (default 500) and `--max-usd` (default $5) cap the
whole run, generator and judges together, and the run prints what it spent. Each run also writes
`<out>.meta.json` (and `<details>.meta.json`) with the models, prompt and judge versions, mode and time. `--prompt v4` or `--prompt v3` regenerates with an earlier prompt, for comparison only. `--html review.html` also writes the coach view. See `WRITEUP.md` for the design and results, and `RUNBOOK.md` for running it on unseen traces. `--judge-repeat N` judges again under a fresh cache key, for run-to-run variance.
Judge agreement with the labels, and the Sonnet cross-check, are in `results/JUDGE_AGREEMENT.md`.

Judge verdicts are cached in `results/judge_cache/`, and `results/judge_cache.sha256` lists every file's hash. The
gate fails if a cached verdict changes without the manifest, so a cache change always shows up as a small diff.
For traces outside this repo, pass `--judge-cache` a directory outside it.

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
| `weekly_summary/prompt.py` | The system prompt and the input the model sees (health data removed, member text quoted). |
| `weekly_summary/generate.py` | The feature. It drafts one summary and repairs it once if a code check fails. |
| `weekly_summary/pipeline.py` | Runs the feature, checks and judge over a traces file, with the shared call budget. |
| `weekly_summary/policy.py` | Turns findings into pass, flag or block. |
| `weekly_summary/evals/` | Code checks (`checks.py`, `vocab.toml`), the judge, reports, the gate and the coach view. |
| `weekly_summary/llm.py` | The client wrapper for Anthropic, OpenAI, and replay. |
| `weekly_summary/data.py` | Loads traces from JSONL. |
| `data/traces.jsonl` | 60 recent production traces. Their labels are in `labels/labels.jsonl`. |
| `data/`, `labels/`, `results/` | The other labeled sets, the label review log, and every committed run. |

There is no license file on purpose: the repo holds Future's guidebook and data, and all rights are reserved.
