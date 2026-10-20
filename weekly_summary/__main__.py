import argparse
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from weekly_summary.data import DEFAULT_TRACES, load_traces
from weekly_summary.generate import generate_summary
from weekly_summary.llm import LLMClient, make_client
from weekly_summary.models import Trace
from weekly_summary.prompt import PROMPT_VERSION


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

    args = parser.parse_args(argv)
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
