"""Feature, evals and guardrails over a traces file: one decision line per trace.

Modes:
- generate (default): draft a new summary for each trace input, then check and decide.
- no-generate: check and decide the drafts already in the traces file. No generation calls.
- code-only: like no-generate, without the judge, so it needs no API key.
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel

from weekly_summary.evals.checks import Finding, run_checks
from weekly_summary.evals.facts import week_facts
from weekly_summary.evals.judge import Judge
from weekly_summary.generate import draft_summary
from weekly_summary.llm import LLMClient
from weekly_summary.models import MemberWeek, Trace
from weekly_summary.policy import Decision, decide

Mode = Literal["generate", "no-generate", "code-only"]


class Result(BaseModel):
    trace_id: str
    decision: Decision
    reasons: list[str]


class Detail(BaseModel):
    """Everything behind one decision, for eval reports. Not for the member."""

    trace_id: str
    mode: Mode
    draft: str
    first_draft: str | None = None
    repaired: bool = False
    decision: Decision
    reasons: list[str]
    findings: list[Finding]
    judge_ok: bool | None = None


class CallBudget:
    """Stops model calls after a fixed number, so a live run can't overspend. Thread-safe."""

    def __init__(self, client: LLMClient, max_calls: int) -> None:
        self.model = client.model
        self.client = client
        self._client = client
        self._left = max_calls
        self._lock = threading.Lock()

    def complete(self, system: str, user: str) -> str:
        with self._lock:
            if self._left <= 0:
                raise RuntimeError("call budget spent")
            self._left -= 1
        return self._client.complete(system, user)


def evaluate(week: MemberWeek, draft: str, judge: Judge | None) -> tuple[list[Finding], bool | None]:
    findings = run_checks(draft, week_facts(week))
    if judge is None:
        return findings, None
    output, judged = judge.judge(week, draft)
    return findings + judged, output is not None


def process(
    trace: Trace,
    mode: Mode,
    generator_for: Callable[[Trace], LLMClient] | None,
    judge: Judge | None,
) -> Detail:
    first_draft, repaired = None, False
    try:
        if mode == "generate":
            assert generator_for is not None
            made = draft_summary(trace.input, generator_for(trace))
            draft, first_draft, repaired = made.text, made.first_draft, made.repaired
        else:
            draft = trace.output
        findings, judge_ok = evaluate(trace.input, draft, judge)
    except Exception as error:  # every trace gets a line, failing closed
        draft, judge_ok = "", None
        findings = [
            Finding(
                rule="other",
                check="pipeline_error",
                severity="block" if mode == "generate" else "flag",
                reason="No draft could be produced. Write this week's summary by hand."
                if mode == "generate"
                else "The automated review could not finish. Read this draft fully.",
                evidence=type(error).__name__,
            )
        ]
    outcome = decide(findings)
    return Detail(
        trace_id=trace.trace_id,
        mode=mode,
        draft=draft,
        first_draft=first_draft,
        repaired=repaired,
        decision=outcome.decision,
        reasons=outcome.reasons,
        findings=outcome.findings,
        judge_ok=judge_ok,
    )


def run_pipeline(
    traces: list[Trace],
    mode: Mode,
    generator_for: Callable[[Trace], LLMClient] | None,
    judge: Judge | None,
    workers: int = 4,
) -> list[Detail]:
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(lambda t: process(t, mode, generator_for, judge), traces))
