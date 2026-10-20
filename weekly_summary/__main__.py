import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from weekly_summary.data import DEFAULT_TRACES, load_traces, read_traces
from weekly_summary.evals import crosscheck
from weekly_summary.evals.judge import CONFIRM_MODEL, DEFAULT_CACHE, JUDGE_VERSION, Judge
from weekly_summary.evals.report import compare, compare_markdown, load_details, load_labels, markdown, summarize
from weekly_summary.generate import generate_summary
from weekly_summary.llm import DEFAULT_MODELS, LLMClient, make_client
from weekly_summary.models import Trace
from weekly_summary.pipeline import CallBudget, Mode, Result, run_pipeline, unreadable_detail
from weekly_summary.prompt import PROMPT_VERSION

DEFAULT_LABELS = DEFAULT_TRACES.parent.parent / "labels" / "labels.jsonl"


def _client_for(traces: list[Trace]) -> Callable[[Trace], LLMClient]:
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    model = os.environ.get("LLM_MODEL")
    if provider == "replay":
        # Traces can share an input, so replay each trace from itself, not from an input lookup.
        return lambda trace: make_client(provider, model, [trace])
    try:
        client = make_client(provider, model, traces)
    except ValueError as e:
        sys.exit(str(e))
    return lambda trace: client


def _find(traces: list[Trace], trace_id: str) -> Trace:
    for trace in traces:
        if trace.trace_id == trace_id:
            return trace
    sys.exit(f"No trace with id {trace_id!r}.")


def _run(traces: list[Trace], client_for: Callable[[Trace], LLMClient], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for trace in traces:
            client = client_for(trace)
            result = Trace(
                trace_id=trace.trace_id,
                created_at=datetime.now(UTC),
                prompt_version=PROMPT_VERSION,
                model=client.model,
                input=trace.input,
                output=generate_summary(trace.input, client),
            )
            f.write(result.model_dump_json() + "\n")
            f.flush()


def _judge(
    budget: int,
    repeat: int = 0,
    cache_dir: Path | None = DEFAULT_CACHE,
    deadline: float | None = None,
    confirm_model: str | None = None,
) -> Judge:
    provider = os.environ.get("JUDGE_PROVIDER", "anthropic")
    model = os.environ.get("JUDGE_MODEL") or DEFAULT_MODELS.get(provider)
    try:
        client = make_client(provider, model, [])
        confirm = make_client(provider, confirm_model, []) if confirm_model else None
    except ValueError as e:
        sys.exit(str(e))
    second = Judge(CallBudget(confirm, budget, deadline), cache_dir=cache_dir) if confirm else None
    return Judge(CallBudget(client, budget, deadline), cache_dir=cache_dir, repeat=repeat, confirm=second)


def _spend(*budgets: CallBudget) -> str:
    total = sum(getattr(b.client, "cost_usd", 0.0) for b in budgets)
    return f"${total:.4f}"


def _pipeline(args: argparse.Namespace, items: list[Trace | tuple[str, str]]) -> None:
    traces = [item for item in items if isinstance(item, Trace)]
    mode: Mode = "code-only" if args.code_only else "no-generate" if args.no_generate else "generate"
    deadline = time.monotonic() + args.deadline if args.deadline else None
    confirm_model = None if args.confirm_model == "none" else args.confirm_model
    judge = (
        None
        if mode == "code-only"
        else _judge(args.max_calls, args.judge_repeat, args.judge_cache, deadline, confirm_model)
    )
    generator_for: Callable[[Trace], LLMClient] | None = None
    budgets: dict[int, CallBudget] = {}
    if mode == "generate":
        client_for = _client_for(traces)

        def budgeted(trace: Trace) -> LLMClient:
            client = client_for(trace)
            # One budget per client; replay clients are made per trace and cost nothing.
            return budgets.setdefault(id(client), CallBudget(client, args.max_calls, deadline))

        generator_for = budgeted

    details = run_pipeline(traces, mode, generator_for, judge, workers=args.workers, prompt=args.prompt)
    done = iter(details)
    details = [next(done) if isinstance(item, Trace) else unreadable_detail(*item, mode) for item in items]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        for d in details:
            f.write(Result(trace_id=d.trace_id, decision=d.decision, reasons=d.reasons).model_dump_json() + "\n")
    if args.details:
        args.details.parent.mkdir(parents=True, exist_ok=True)
        with args.details.open("w") as f:
            for d in details:
                f.write(d.model_dump_json() + "\n")
    counts = {k: sum(d.decision == k for d in details) for k in ("pass", "flag", "block")}
    judges = [j for j in (judge, judge.confirm if judge else None) if j is not None]
    spent = [*budgets.values(), *(j.client for j in judges if isinstance(j.client, CallBudget))]
    print(
        f"{args.out}: {counts} (prompt {args.prompt if mode == 'generate' else '-'}, judge {JUDGE_VERSION} {judge.client.model if judge else '-'}, "
        f"mode {mode}, spent {_spend(*spent)})",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="weekly-summary")
    parser.add_argument("--traces", type=Path, default=DEFAULT_TRACES, help="traces JSONL file")
    commands = parser.add_subparsers(dest="command", required=True)

    show = commands.add_parser("show", help="print a trace's input and output")
    show.add_argument("trace_id")

    generate = commands.add_parser("generate", help="regenerate the summary for one trace")
    generate.add_argument("trace_id")

    run = commands.add_parser("run", help="regenerate summaries for all traces")
    run.add_argument("--out", type=Path, help="output JSONL (default: runs/<UTC timestamp>.jsonl)")
    run.add_argument("--limit", type=int, help="only run the first N traces")

    pipeline = commands.add_parser("pipeline", help="feature, evals and guardrails: one decision line per trace")
    pipeline.add_argument("traces_path", type=Path, nargs="?", help="traces JSONL (default: --traces)")
    pipeline.add_argument("--out", type=Path, default=Path("results/decisions.jsonl"))
    pipeline.add_argument("--details", type=Path, help="also write findings and drafts here")
    skip = pipeline.add_mutually_exclusive_group()
    skip.add_argument("--no-generate", action="store_true", help="decide the drafts already in the traces file")
    skip.add_argument("--code-only", action="store_true", help="like --no-generate, without the LLM judge")
    pipeline.add_argument("--workers", type=int, default=4)
    pipeline.add_argument("--max-calls", type=int, default=500, help="stop calling a model after this many calls")
    pipeline.add_argument(
        "--deadline", type=float, help="seconds; after this no new model calls start, and the rest fail closed"
    )
    pipeline.add_argument("--judge-cache", type=Path, default=DEFAULT_CACHE, help="judge cache directory")
    pipeline.add_argument("--prompt", choices=["v4", "v3"], default="v4", help="v3 only to measure the old prompt")
    pipeline.add_argument(
        "--judge-repeat", type=int, default=0, help="judge again under a fresh cache key (variance runs)"
    )
    pipeline.add_argument(
        "--confirm-model",
        default=CONFIRM_MODEL,
        help='second judge that must agree before an "other" finding without code backing flags; "none" to skip',
    )

    evaluate = commands.add_parser("evaluate", help="metrics for a details file, against labels")
    evaluate.add_argument("details", type=Path)
    evaluate.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    evaluate.add_argument("--out", type=Path, help="write the full report as JSON")

    commands.add_parser("gate", help="fail if the frozen labeled sets get more wrong than evals/gate.toml allows")

    comp = commands.add_parser("compare", help="two runs on the same traces: what got better or worse")
    comp.add_argument("before", type=Path, help="details file of the baseline run")
    comp.add_argument("after", type=Path, help="details file of the changed run")
    comp.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    comp.add_argument("--names", nargs=2, default=["before", "after"])
    comp.add_argument("--out", type=Path, help="write the result as JSON")

    cross = commands.add_parser("crosscheck", help="judge-vs-judge agreement for two details files")
    cross.add_argument("reference", type=Path)
    cross.add_argument("other", type=Path)
    cross.add_argument("--names", nargs=2, default=["A", "B"])
    cross.add_argument("--out", type=Path, help="write the result as JSON")

    args = parser.parse_args(argv)
    if args.command == "crosscheck":
        result = crosscheck.compare(load_details(args.reference), load_details(args.other))
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, indent=2) + "\n")
        print(crosscheck.markdown(result, *args.names))
        return
    if args.command == "gate":
        from weekly_summary.evals.gate import run_gate

        ok, lines = run_gate()
        print("\n".join(lines))
        sys.exit(0 if ok else 1)
    if args.command == "compare":
        labels = load_labels(args.labels) if args.labels and args.labels.exists() else None
        result = compare(load_details(args.before), load_details(args.after), labels)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, indent=2) + "\n")
        print(compare_markdown(result, tuple(args.names)))
        sys.exit(1 if result.get("worse") else 0)
    if args.command == "evaluate":
        labels = load_labels(args.labels) if args.labels and args.labels.exists() else None
        report = summarize(load_details(args.details), labels)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(markdown(report))
        return
    if args.command == "pipeline":
        _pipeline(args, read_traces(args.traces_path or args.traces))
        return
    traces = load_traces(args.traces)

    match args.command:
        case "show":
            trace = _find(traces, args.trace_id)
            print(trace.input.model_dump_json(indent=2))
            print()
            print(trace.output)
        case "generate":
            trace = _find(traces, args.trace_id)
            print(generate_summary(trace.input, _client_for(traces)(trace)))
        case "run":
            out = args.out or Path("runs") / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}.jsonl"
            _run(traces[: args.limit], _client_for(traces), out)
            print(out)


if __name__ == "__main__":
    main()
