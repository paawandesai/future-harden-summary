import json
from pathlib import Path

from weekly_summary.models import Trace

DEFAULT_TRACES = Path(__file__).resolve().parent.parent / "data" / "traces.jsonl"


def load_traces(path: Path = DEFAULT_TRACES) -> list[Trace]:
    with path.open() as f:
        return [Trace.model_validate_json(line) for line in f if line.strip()]


def read_traces(path: Path) -> list[Trace | tuple[str, str]]:
    """Like load_traces, for unseen files: a line that doesn't parse comes back in its place as (trace_id
    or line number, error) instead of stopping the run, and a missing draft or metadata field gets a default."""
    items: list[Trace | tuple[str, str]] = []
    with path.open() as f:
        for number, line in enumerate(f, 1):
            if not line.strip():
                continue
            trace_id = f"line {number}"
            try:
                raw = json.loads(line)
                trace_id = str(raw.get("trace_id") or trace_id)
                raw = {"created_at": "1970-01-01T00:00:00Z", "prompt_version": "", "model": "", "output": ""} | raw
                raw["output"] = raw["output"] or ""
                items.append(Trace.model_validate(raw))
            except (ValueError, AttributeError) as error:
                items.append((trace_id, type(error).__name__))
    return items
