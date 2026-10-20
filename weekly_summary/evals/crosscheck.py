"""Judge-vs-judge agreement: two judge runs over the same drafts, rule by rule.

Used for run-to-run stability (Haiku against itself) and for the self-grading check (Haiku against
Sonnet, on drafts Haiku wrote and on drafts it didn't). Only judge verdicts count; code findings
and judge errors are left out.
"""

from weekly_summary.evals.report import NOT_A_VERDICT, Agreement
from weekly_summary.pipeline import Detail

JUDGED = ("1", "2", "3", "other")


def judged(detail: Detail) -> set[str]:
    return {f.rule for f in detail.findings if f.source == "judge" and f.check not in NOT_A_VERDICT}


def compare(a: list[Detail], b: list[Detail]) -> dict[str, object]:
    """Treats `a` as the reference: tp = both flag, fp = only b flags, fn = only a flags."""
    by_id = {d.trace_id: d for d in b}
    pairs = [(x, by_id[x.trace_id]) for x in a if x.trace_id in by_id and x.judge_ok and by_id[x.trace_id].judge_ok]
    out: dict[str, object] = {"drafts": len(pairs)}
    for rule in JUDGED:
        tp = sum(rule in judged(x) and rule in judged(y) for x, y in pairs)
        fn = sum(rule in judged(x) and rule not in judged(y) for x, y in pairs)
        fp = sum(rule not in judged(x) and rule in judged(y) for x, y in pairs)
        agreement = Agreement(tp=tp, fp=fp, fn=fn, tn=len(pairs) - tp - fp - fn)
        out[rule] = {
            "a_flags": tp + fn,
            "b_flags": tp + fp,
            "both": tp,
            "agree": (tp + agreement.tn) / len(pairs) if pairs else None,
            "kappa": agreement.kappa,
        }
    out["any"] = {
        "a_flags": sum(bool(judged(x)) for x, _ in pairs),
        "b_flags": sum(bool(judged(y)) for _, y in pairs),
    }
    return out


def markdown(result: dict[str, object], a_name: str, b_name: str) -> str:
    lines = [
        f"Drafts judged cleanly by both: {result['drafts']}.",
        "",
        f"| Rule | {a_name} flags | {b_name} flags | Both | Agreement | Kappa |",
        "|---|---|---|---|---|---|",
    ]
    for rule in JUDGED:
        row = result[rule]
        assert isinstance(row, dict)
        agree = "n/a" if row["agree"] is None else f"{row['agree']:.0%}"
        kappa = "n/a" if row["kappa"] is None else f"{row['kappa']:.2f}"
        lines.append(f"| {rule} | {row['a_flags']} | {row['b_flags']} | {row['both']} | {agree} | {kappa} |")
    any_row = result["any"]
    assert isinstance(any_row, dict)
    lines.append(f"| any | {any_row['a_flags']} | {any_row['b_flags']} | | | |")
    return "\n".join(lines)
