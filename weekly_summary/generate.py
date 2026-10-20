from weekly_summary.llm import LLMClient
from weekly_summary.models import MemberWeek
from weekly_summary.prompt import SYSTEM_PROMPT, render_user_message


def generate_summary(week: MemberWeek, client: LLMClient) -> str:
    return client.complete(SYSTEM_PROMPT, render_user_message(week))
