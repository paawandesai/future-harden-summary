"""Before/after: the v3 prompt against prompt v4 with repair, same traces, same generator, same checks.

Every variant is generated `--runs` times per trace with Haiku, then checked with the code checks and the
Haiku judge. Results are reported per split (dev, held-out) as the mean and spread across runs, so a
difference smaller than the run-to-run spread isn't read as an improvement.

    uv run python -m weekly_summary.evals.before_after --runs 5
    uv run python -m weekly_summary.evals.before_after --runs 5 --rescore   # re-decide saved drafts, no generation

Variants:
- recorded: the production drafts in data/traces.jsonl (v3 prompt, Sonnet 4.5 and GPT-4.1), one run.
- v3: the v3 prompt on Haiku.
- v4-first: prompt v4's first draft, before the repair step.
- v4: prompt v4 after at most one repair, which is what the feature ships.

Drafts are saved as traces files, so they can be re-decided later with `pipeline --no-generate`.
"""

import argparse
import json
import statistics
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from weekly_summary.data import DEFAULT_TRACES, load_traces
from weekly_summary.evals.checks import word_count
from weekly_summary.evals.judge import Judge
from weekly_summary.evals.report import RULES, Label, load_labels, predicted
from weekly_summary.generate import draft_summary
from weekly_summary.llm import AnthropicClient
from weekly_summary.models import Trace
from weekly_summary.pipeline import Detail, run_pipeline
from weekly_summary.prompt import PROMPT_VERSION, V3_SYSTEM_PROMPT, render_v3_user_message

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "before_after"
LABELS = ROOT / "labels" / "labels.jsonl"
SPLITS = ("dev", "held_out")


def _write(path: Path, traces: list[Trace]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(t.model_dump_json() + "\n" for t in traces))


def _generate(traces: list[Trace], make: Callable[[Trace], tuple[str, str]], version: str, model: str, workers: int):
    """Returns (final drafts, first drafts) as traces. A failed generation gets an empty draft."""

    def one(trace: Trace) -> tuple[Trace, Trace]:
        try:
            final, first = make(trace)
        except Exception:  # an empty draft fails the checks, which is the honest result
            final = first = ""
        stamp = datetime.now(UTC)

        def as_trace(text: str) -> Trace:
            return Trace(
                trace_id=trace.trace_id,
                created_at=stamp,
                prompt_version=version,
                model=model,
                input=trace.input,
                output=text,
            )

        return as_trace(final), as_trace(first)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pairs = list(pool.map(one, traces))
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _stats(details: list[Detail], labels: dict[str, Label], split: str) -> dict[str, float]:
    rows = [d for d in details if labels[d.trace_id].split == split]
    n = len(rows)
    out: dict[str, float] = {"n": n}
    for decision in ("pass", "flag", "block"):
        out[decision] = sum(d.decision == decision for d in rows) / n
    for rule in RULES:
        out[rule] = sum(predicted(d, rule, "combined") for d in rows) / n
        out[f"{rule}_code"] = sum(predicted(d, rule, "code") for d in rows) / n
    out["any_violation"] = sum(any(predicted(d, r, "combined") for r in RULES) for d in rows) / n
    out["words"] = sum(word_count(d.draft) for d in rows) / n
    out["specific"] = sum(not any(f.check == "specificity" for f in d.findings) for d in rows) / n
    out["repaired"] = sum(d.repaired for d in rows) / n
    return out


def _summarize(runs: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    keys = runs[0].keys()
    return {
        k: {
            "mean": statistics.fmean(r[k] for r in runs),
            "min": min(r[k] for r in runs),
            "max": max(r[k] for r in runs),
            "sd": statistics.stdev(r[k] for r in runs) if len(runs) > 1 else 0.0,
        }
        for k in keys
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--judge-model", default="claude-haiku-5-5")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--rescore", action="store_true", help="re-decide the saved drafts with the current checks")
    args = parser.parse_args(argv)

    traces = load_traces(DEFAULT_TRACES)
    labels = load_labels(LABELS)
    generator = AnthropicClient(args.model)
    judge_client = AnthropicClient(args.judge_model)
    judge = Judge(judge_client)

    def v3(trace: Trace) -> tuple[str, str]:
        text = generator.complete(V3_SYSTEM_PROMPT, render_v3_user_message(trace.input))
        return text, text

    def v4(trace: Trace) -> tuple[str, str]:
        made = draft_summary(trace.input, generator)
        return made.text, made.first_draft

    files: dict[str, list[Path]] = {"recorded": [DEFAULT_TRACES], "v3": [], "v4-first": [], "v4": []}
    for run in range(1, args.runs + 1):
        paths = {v: OUT / f"drafts_{v.replace('-', '')}_r{run}.jsonl" for v in ("v3", "v4", "v4-first")}
        if not args.rescore:
            final, _ = _generate(traces, v3, "v3", args.model, args.workers)
            _write(paths["v3"], final)
            final, first = _generate(traces, v4, PROMPT_VERSION, args.model, args.workers)
            _write(paths["v4"], final)
            _write(paths["v4-first"], first)
        for variant, path in paths.items():
            files[variant].append(path)

    summary: dict[str, object] = {
        "generator": args.model,
        "judge": args.judge_model,
        "runs": args.runs,
        "date": datetime.now(UTC).date().isoformat(),
    }
    for variant, paths in files.items():
        per_split: dict[str, list[dict[str, float]]] = {s: [] for s in SPLITS}
        for i, path in enumerate(paths, 1):
            details = run_pipeline(load_traces(path), "no-generate", None, judge, workers=args.workers)
            if variant == "v4":
                # Keep the repair flag, which only the generation step knows.
                firsts = {t.trace_id: t.output for t in load_traces(OUT / f"drafts_v4first_r{i}.jsonl")}
                for d in details:
                    d.repaired = firsts[d.trace_id] != d.draft
            (OUT / f"details_{variant}_r{i}.jsonl").write_text("".join(d.model_dump_json() + "\n" for d in details))
            for split in SPLITS:
                per_split[split].append(_stats(details, labels, split))
        summary[variant] = {split: _summarize(runs) for split, runs in per_split.items()}
    summary["spend_usd"] = {"generator": round(generator.cost_usd, 4), "judge": round(judge_client.cost_usd, 4)}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["spend_usd"]))


if __name__ == "__main__":
    main()
