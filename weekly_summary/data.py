from pathlib import Path

from weekly_summary.models import Trace

DEFAULT_TRACES = Path(__file__).resolve().parent.parent / "data" / "traces.jsonl"


def load_traces(path: Path = DEFAULT_TRACES) -> list[Trace]:
    with path.open() as f:
        return [Trace.model_validate_json(line) for line in f if line.strip()]
