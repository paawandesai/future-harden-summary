"""Metrics over pipeline details: rule rates, agreement with hand labels, decisions and quality."""

import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from weekly_summary.evals.checks import word_count
from weekly_summary.pipeline import Detail

RULES = ("rule1", "rule2", "rule3", "rule4", "other")
NOT_A_VERDICT = {"judge_error", "pipeline_error"}
Source = Literal["code", "judge", "combined"]


class Label(BaseModel):
    trace_id: str
    split: Literal["dev", "held_out"]
    rule1: bool
    rule2: bool
    rule3: bool
    rule4: bool
    other: bool
    borderline: list[str] = []
    notes: str = ""
    labeler: str = ""
    reviewed_by: str | None = None


class Agreement(BaseModel):
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def kappa(self) -> float | None:
        n = self.n
        if not n:
            return None
        observed = (self.tp + self.tn) / n
        yes = ((self.tp + self.fp) / n) * ((self.tp + self.fn) / n)
        no = ((self.fn + self.tn) / n) * ((self.fp + self.tn) / n)
        expected = yes + no
        return (observed - expected) / (1 - expected) if expected < 1 else None


def load_labels(path: Path) -> dict[str, Label]:
    with path.open() as f:
        return {(label := Label.model_validate_json(line)).trace_id: label for line in f if line.strip()}


def load_details(path: Path) -> list[Detail]:
    with path.open() as f:
        return [Detail.model_validate_json(line) for line in f if line.strip()]


def predicted(detail: Detail, rule: str, source: Source) -> bool:
    key = rule.removeprefix("rule")
    return any(
        f.rule == key and f.check not in NOT_A_VERDICT and (source == "combined" or f.source == source)
        for f in detail.findings
    )


def agreement(details: list[Detail], labels: dict[str, Label], rule: str, source: Source, split: str | None) -> Agreement:
    counts = Counter[str]()
    for detail in details:
        label = labels.get(detail.trace_id)
        if label is None or (split and label.split != split):
            continue
        if rule in label.borderline:
            # A reasonable reviewer could go either way, so neither answer is scored (RUBRIC.md).
            continue
        truth, guess = bool(getattr(label, rule)), predicted(detail, rule, source)
        counts["tp" if truth and guess else "fp" if guess else "fn" if truth else "tn"] += 1
    return Agreement(tp=counts["tp"], fp=counts["fp"], fn=counts["fn"], tn=counts["tn"])


def summarize(details: list[Detail], labels: dict[str, Label] | None) -> dict[str, object]:
    n = len(details)
    decisions = Counter(d.decision for d in details)
    report: dict[str, object] = {
        "traces": n,
        "decisions": {k: decisions.get(k, 0) for k in ("pass", "flag", "block")},
        "rule_violation_rate": {
            rule: sum(predicted(d, rule, "combined") for d in details) / n if n else 0 for rule in RULES
        },
        "code_violation_rate": {rule: sum(predicted(d, rule, "code") for d in details) / n if n else 0 for rule in RULES},
        "any_block_finding": sum(any(f.severity == "block" for f in d.findings) for d in details),
        "judge_failures": sum(d.judge_ok is False for d in details),
        "repaired": sum(d.repaired for d in details),
        "quality": {
            "mean_words": round(sum(word_count(d.draft) for d in details) / n, 1) if n else 0,
            "specific": sum(not any(f.check == "specificity" for f in d.findings) for d in details),
        },
    }
    if labels:
        table: dict[str, object] = {}
        for split in (None, "dev", "held_out"):
            for source in ("code", "judge", "combined"):
                for rule in RULES:
                    a = agreement(details, labels, rule, source, split)
                    table[f"{split or 'all'}/{source}/{rule}"] = {
                        **a.model_dump(),
                        "precision": a.precision,
                        "recall": a.recall,
                        "kappa": a.kappa,
                    }
        report["agreement"] = table
        violating = {tid for tid, label in labels.items() if any(getattr(label, r) for r in RULES)}
        report["missed_violations"] = sorted(d.trace_id for d in details if d.trace_id in violating and d.decision == "pass")
        report["false_alarms"] = sorted(d.trace_id for d in details if d.trace_id not in violating and d.decision != "pass")
        report["labels_reviewed"] = sum(label.reviewed_by is not None for label in labels.values())
    return report


def _fmt(x: object) -> str:
    return "n/a" if x is None else f"{x:.2f}" if isinstance(x, float) else str(x)


def markdown(report: dict[str, object]) -> str:
    lines = [
        f"Traces: {report['traces']}. Decisions: {json.dumps(report['decisions'])}. "
        f"Judge failures: {report['judge_failures']}. Repaired: {report['repaired']}.",
        f"Quality: {json.dumps(report['quality'])}.",
        "",
        "| Rule | Violation rate (all checks) | Code only |",
        "|---|---|---|",
    ]
    rates = report["rule_violation_rate"]
    code = report["code_violation_rate"]
    assert isinstance(rates, dict) and isinstance(code, dict)
    for rule in RULES:
        lines.append(f"| {rule} | {rates[rule]:.0%} | {code[rule]:.0%} |")
    agreement_table = report.get("agreement")
    if isinstance(agreement_table, dict):
        lines += [
            "",
            "| Split / source / rule | TP | FP | FN | TN | Precision | Recall | Kappa |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for key, row in agreement_table.items():
            if key.startswith("all/"):
                continue
            lines.append(
                f"| {key} | {row['tp']} | {row['fp']} | {row['fn']} | {row['tn']} | "
                f"{_fmt(row['precision'])} | {_fmt(row['recall'])} | {_fmt(row['kappa'])} |"
            )
        lines += [
            "",
            f"Labeled violations that passed: {report['missed_violations'] or 'none'}.",
            f"Clean drafts that were flagged or blocked: {report['false_alarms'] or 'none'}.",
            f"Labels reviewed by a person: {report['labels_reviewed']}.",
        ]
    return "\n".join(lines)
