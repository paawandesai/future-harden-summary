"""Turns findings into the one decision a coach sees: pass, flag or block.

- block: a finding that must never reach a member even if a coach skims. Only deterministic code
  checks block, so a block is always reproducible and explainable from the vocabulary.
- flag: a finding a coach should look at, including everything the judge reports and every
  judge failure. The coach reads the first reason; the rest are there if they open the draft.
- pass: nothing found.
"""

from typing import Literal

from pydantic import BaseModel

from weekly_summary.evals.checks import Finding

Decision = Literal["pass", "flag", "block"]

MAX_REASONS = 3


class Outcome(BaseModel):
    decision: Decision
    reasons: list[str]
    findings: list[Finding]


def _rank(finding: Finding) -> tuple[int, int, int]:
    severity = 0 if finding.severity == "block" else 1
    # Health and privacy first, then weight, then facts, then voice.
    rule = {"1": 0, "4": 1, "2": 2, "other": 3, "3": 4}[finding.rule]
    source = 0 if finding.source == "code" else 1
    return severity, rule, source


def decide(findings: list[Finding]) -> Outcome:
    ordered = sorted(findings, key=_rank)
    covered_by_code = {f.rule for f in findings if f.source == "code"}
    reasons: list[str] = []
    for finding in ordered:
        # The judge agreeing with a code finding on the same rule adds nothing for the coach.
        if finding.source == "judge" and finding.rule in covered_by_code and finding.check != "judge_error":
            continue
        if finding.reason not in reasons:
            reasons.append(finding.reason)
    if any(f.severity == "block" for f in findings):
        decision: Decision = "block"
    elif findings:
        decision = "flag"
    else:
        decision = "pass"
    return Outcome(decision=decision, reasons=reasons[:MAX_REASONS], findings=ordered)
