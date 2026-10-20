"""Feature, evals and guardrails over a traces file: one decision line per trace.

Modes:
- generate (default): draft a new summary for each trace input, then check and decide.
- no-generate: check and decide the drafts already in the traces file. No generation calls.
- code-only: like no-generate, without the judge, so it needs no API key.
"""

import threading
import time
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
MAX_WORKERS = 16


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
    repair_reasons: list[str] = []
    decision: Decision
    reasons: list[str]
    findings: list[Finding]
    judge_ok: bool | None = None


class Allowance:
    """One run's limits, shared by every model client in it (generator, judge and confirm judge): a number of
    calls, a wall-clock deadline and a dollar amount. Thread-safe."""

    def __init__(self, max_calls: int, deadline: float | None = None, max_usd: float | None = None) -> None:
        self.left = max_calls
        self.deadline = deadline  # a time.monotonic() value
        self.max_usd = max_usd
        self.clients: list[LLMClient] = []
        self._lock = threading.Lock()

    def spent_usd(self) -> float:
        return sum(getattr(c, "cost_usd", 0.0) for c in self.clients)

    def take(self) -> None:
        with self._lock:
            if self.left <= 0:
                raise RuntimeError("call budget spent")
            if self.deadline is not None and time.monotonic() > self.deadline:
                raise TimeoutError("run deadline passed")
            if self.max_usd is not None and self.spent_usd() >= self.max_usd:
                raise RuntimeError("spending cap reached")
            self.left -= 1


class CallBudget:
    """Stops model calls once the run's allowance is used up, so a live run can't overspend or hang on a slow
    provider. Calls refused this way fail closed like any other error. Pass an int for a budget of its own."""

    def __init__(self, client: LLMClient, allowance: Allowance | int, deadline: float | None = None) -> None:
        self.model = client.model
        self.client = client
        self.allowance = allowance if isinstance(allowance, Allowance) else Allowance(allowance, deadline)
        self.allowance.clients.append(client)

    def complete(self, system: str, user: str) -> str:
        self.allowance.take()
        return self.client.complete(system, user)


def evaluate(week: MemberWeek, draft: str, judge: Judge | None) -> tuple[list[Finding], bool | None]:
    findings = run_checks(draft, week_facts(week))
    if judge is None:
        return findings, None
    output, judged = judge.judge(week, draft)
    if judge.confirm and output is not None and _unbacked_other(findings, judged):
        second, _ = judge.confirm.judge(week, draft)
        # A failed confirmation keeps the flag: only a clean "no" from the second judge removes it.
        if second is not None and not any(v.rule == "other" and v.violated for v in second.verdicts):
            judged = [f for f in judged if f.rule != "other"]
    return findings + judged, output is not None


def _unbacked_other(code: list[Finding], judged: list[Finding]) -> bool:
    return any(f.rule == "other" for f in judged) and not any(f.rule == "other" for f in code)


def process(
    trace: Trace,
    mode: Mode,
    generator_for: Callable[[Trace], LLMClient] | None,
    judge: Judge | None,
    prompt: str = "v5",
) -> Detail:
    first_draft, repaired, repair_reasons = None, False, []
    try:
        if mode == "generate":
            assert generator_for is not None
            made = draft_summary(trace.input, generator_for(trace), prompt=prompt)
            draft, first_draft, repaired = made.text, made.first_draft, made.repaired
            repair_reasons = made.repair_reasons if made.repaired else []
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
        repair_reasons=repair_reasons,
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
    prompt: str = "v5",
) -> list[Detail]:
    with ThreadPoolExecutor(max_workers=min(max(1, workers), MAX_WORKERS)) as pool:
        return list(pool.map(lambda t: process(t, mode, generator_for, judge, prompt), traces))


def unreadable_detail(trace_id: str, error: str, mode: Mode) -> Detail:
    """A trace line that didn't parse still gets a decision. Nothing could be checked, so it blocks."""
    finding = Finding(
        rule="other",
        check="pipeline_error",
        severity="block",
        reason="This trace could not be read, so nothing was checked. Write this week's summary by hand.",
        evidence=error,
    )
    return Detail(
        trace_id=trace_id, mode=mode, draft="", decision="block", reasons=[finding.reason], findings=[finding]
    )
