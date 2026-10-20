# Live-session runbook

One page for running the pipeline on traces we have not seen. Design and results are in `WRITEUP.md`.

## Before the session

```
git pull && uv sync
export ANTHROPIC_FUTURE_API_KEY=...        # or ANTHROPIC_API_KEY
unset ANTHROPIC_BASE_URL                    # unless you mean to send the key to another host
uv run pytest -q                            # about 2 s, no API calls
head -3 data/rehearsal.jsonl > /tmp/smoke.jsonl
uv run weekly-summary pipeline /tmp/smoke.jsonl --judge-cache "$(mktemp -d)" --max-calls 20 --out /tmp/smoke_out.jsonl
```

The last two lines are a live smoke test. They generate 3 drafts and judge them with an empty cache, so every call
reaches the API. Expect 3 decision lines and a non-zero spend on stderr (about $0.003). If the key is wrong or
missing, all 3 lines are `block` with "No draft could be produced", and the spend is $0.

## The command

```
uv run weekly-summary pipeline <traces.jsonl> --out decisions.jsonl --details details.jsonl \
    --html review.html --judge-cache /tmp/judge_cache_live --deadline 900 --max-calls 400 --max-usd 2
```

`--max-calls` and `--max-usd` cap the whole run, generator and judges together. `--judge-cache` outside the repo
keeps the committed cache, which the gate checks against its manifest, unchanged.

- **Output:** one line per trace in `decisions.jsonl`, `{"trace_id", "decision", "reasons"}`, in input order. A
  summary line on stderr gives pass / flag / block counts and the spend.
- **Coach view:** open `review.html`. Blocked drafts come first, each with its reasons and the matched words
  highlighted. It is the fastest way to show a reviewer what a coach sees.
- **Without generation** (judge the drafts already in the file): add `--no-generate`.
- **Without any API key** (code checks only): `--code-only`.
- **Expect:** for 60 to 100 traces, about 2 to 3 minutes with 4 workers. The cost is about $0.001 per trace, plus
  a few cents for the Sonnet confirmation step. On new drafts, about 7% are flagged on familiar inputs and 10–17% on unseen ones, and blocks are rare. On
  recorded production drafts, expect about 30% blocked.

## When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| Many `block` with "No draft could be produced" | Generation failed (API down, key wrong, budget or deadline hit) | Check the key with the smoke test. Raise `--max-calls` or `--deadline` if the stderr line says the budget ran out |
| Many `flag` with "The automated review could not finish" | The judge failed. Code checks still ran, so code blocks still block | Same as above. `--code-only` gives code-only decisions with no API |
| A run that seems stuck | A slow provider. Each call times out after 60 s and is retried 3 times | `--deadline` stops new calls, and the remaining traces fail closed. Calls already running can take up to 4 more minutes |
| A trace line that is blocked with "This trace could not be read" | The line is not valid JSON or does not match `weekly_summary/models.py` (a missing draft or metadata field is fine) | Every other line still gets its decision, in input order. Fix the line and rerun |
| Surprising flags | Read `details.jsonl`: each finding has its rule, check, evidence and source (code or judge) | `uv run weekly-summary --traces <file> show <trace_id>` prints the input |

## Questions worth having answers ready for

- **Why does code block and the judge only flag?** Blocks must be reproducible. The judge varies between runs.
- **How do we know the checks aren't overfit?** The challenge set (`data/challenge.jsonl`) and the rehearsal set
  (`data/rehearsal.jsonl`) were written by agents that never saw the checks. Both are frozen: no case was patched
  one at a time.
- **What stops a change from making things worse?** CI runs `uv run weekly-summary gate` on every merge
  request. It fails if a frozen labeled set misses more violations or flags more clean drafts than
  `weekly_summary/evals/gate.toml` allows. It needs no API key.
- **Did a change make things better or worse?** `uv run weekly-summary compare <before details> <after details>`
  shows what moved, and exits non-zero if a labeled violation now passes or more clean drafts get flagged.
