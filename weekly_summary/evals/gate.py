"""The eval gate: run the frozen labeled sets and fail if any gets more wrong than gate.toml allows.

Runs without an API key. Judge verdicts come from the committed cache; a draft the cache hasn't seen is a
judge failure, which also fails the gate, because a check that can't be replayed can't be trusted in CI.
"""

import tomllib
from pathlib import Path

from weekly_summary.data import load_traces
from weekly_summary.evals.judge import CONFIRM_MODEL, DEFAULT_CACHE, Judge, check_manifest
from weekly_summary.evals.report import load_labels, summarize
from weekly_summary.llm import DEFAULT_MODELS
from weekly_summary.pipeline import run_pipeline

ROOT = Path(__file__).resolve().parents[2]
GATE = Path(__file__).with_name("gate.toml")


class CacheOnly:
    """A client that never calls a provider. Used so the gate replays the judge cache and nothing else."""

    def __init__(self, model: str) -> None:
        self.model = model

    def complete(self, system: str, user: str) -> str:
        raise LookupError("judge verdict not in the cache")


def cached_judge(cache_dir: Path = DEFAULT_CACHE) -> Judge:
    confirm = Judge(CacheOnly(CONFIRM_MODEL), cache_dir=cache_dir)
    return Judge(CacheOnly(DEFAULT_MODELS["anthropic"]), cache_dir=cache_dir, confirm=confirm)


def run_gate(path: Path = GATE) -> tuple[bool, list[str]]:
    lines: list[str] = []
    # The cache is the gate's source of truth for the judge, so it must be exactly what was reviewed.
    tampered = check_manifest()
    ok = not tampered
    lines.append(f"{'ok' if ok else 'FAIL':4} judge cache matches results/judge_cache.sha256")
    lines += [f"     {p}" for p in tampered[:10]]
    for spec in tomllib.loads(path.read_text())["set"]:
        details = run_pipeline(
            load_traces(ROOT / spec["traces"]),
            "no-generate" if spec["judge"] else "code-only",
            None,
            cached_judge() if spec["judge"] else None,
        )
        report = summarize(details, load_labels(ROOT / spec["labels"]))
        missed, alarms = report["missed_violations"], report["false_alarms"]
        unblocked = report["rule4_not_blocked"]
        assert isinstance(missed, list) and isinstance(alarms, list) and isinstance(unblocked, list)
        failures = report["judge_failures"]
        problems = []
        if len(missed) > spec["missed"]:
            problems.append(f"{len(missed)} violations passed (limit {spec['missed']}): {missed}")
        if len(alarms) > spec["false_alarms"]:
            problems.append(f"{len(alarms)} clean drafts flagged (limit {spec['false_alarms']}): {alarms}")
        # Rule 4 (quoted health data) must block, not merely flag: a coach may skim a flag.
        if len(unblocked) > spec.get("rule4_not_blocked", 0):
            problems.append(
                f"{len(unblocked)} Rule 4 violations not blocked (limit {spec.get('rule4_not_blocked', 0)}): {unblocked}"
            )
        if failures:
            problems.append(f"{failures} judge verdicts not in the cache; rerun the pipeline with a key and commit")
        ok = ok and not problems
        status = "FAIL" if problems else "ok"
        lines.append(
            f"{status:4} {spec['name']}: missed {len(missed)}/{spec['missed']}, "
            f"false alarms {len(alarms)}/{spec['false_alarms']}, "
            f"Rule 4 not blocked {len(unblocked)}/{spec.get('rule4_not_blocked', 0)}"
        )
        lines += [f"     {p}" for p in problems]
    return ok, lines
