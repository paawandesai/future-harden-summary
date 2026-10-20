"""The feature: a fixed workflow that drafts one member's weekly summary.

1. The input is reduced in code to the facts the model may use (prompt.render_user_message).
2. One model call writes the draft.
3. The code checks run. If any block-level or format finding is fixable, one repair call tells the
   model which rules failed (not the vocabulary that caught them) and asks for a new draft.
4. The caller runs the full checks and the judge on the final draft and decides.
"""

from pydantic import BaseModel

from weekly_summary.evals.checks import run_checks
from weekly_summary.evals.facts import week_facts
from weekly_summary.llm import LLMClient
from weekly_summary.models import MemberWeek
from weekly_summary.prompt import SYSTEM_PROMPT, render_user_message

# Code findings worth one more model call. Grounding and judge findings go to the coach instead.
REPAIRABLE = {
    "biomarker_value", "lab_mention", "avoid_weight_talk", "weight_target", "opening", "signoff",
    "length", "emoji", "bot_voice", "hype", "guilt", "diagnosis", "treatment", "train_through",
    "coach_contact", "specificity",
}


class Draft(BaseModel):
    text: str
    first_draft: str
    repaired: bool
    repair_reasons: list[str]


def generate_summary(week: MemberWeek, client: LLMClient) -> str:
    return client.complete(SYSTEM_PROMPT, render_user_message(week))


def draft_summary(week: MemberWeek, client: LLMClient, repair: bool = True) -> Draft:
    first = generate_summary(week, client)
    findings = [f for f in run_checks(first, week_facts(week)) if f.check in REPAIRABLE]
    if not repair or not findings:
        return Draft(text=first, first_draft=first, repaired=False, repair_reasons=[])
    reasons = sorted({f.reason for f in findings})
    request = (
        render_user_message(week)
        + "\n\nYour previous draft:\n<draft>\n"
        + first
        + "\n</draft>\n\nIt broke these rules:\n"
        + "\n".join(f"- {r}" for r in reasons)
        + "\n\nWrite a new message that follows every rule. Reply with the message only."
    )
    try:
        second = client.complete(SYSTEM_PROMPT, request)
    except LookupError:
        # The replay client only knows first drafts; keep the first draft and let the checks decide.
        return Draft(text=first, first_draft=first, repaired=False, repair_reasons=reasons)
    return Draft(text=second, first_draft=first, repaired=True, repair_reasons=reasons)
