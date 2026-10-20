"""Facts about one member's week, taken from the trace input, that the checks compare drafts to."""

import json
import re
from dataclasses import dataclass
from itertools import combinations

from weekly_summary.evals.vocab import Concept, load_vocab, phrase
from weekly_summary.models import MemberWeek

_NUMBER = re.compile(r"\b\d{1,2}:\d{2}\b|(?<![\w.:])\d[\d,]*(?:\.\d+)?(?:%)?(?![\w:])")

_UNITS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_WORD_NUMBER = re.compile(
    r"\b(?:(" + "|".join(_TENS) + r")(?:[- ](" + "|".join(k for k in _UNITS if _UNITS[k] < 10) + r"))?"
    r"|(" + "|".join(_UNITS) + r"))(?:\s+hundred(?:\s+and)?(?:\s+(" + "|".join(_TENS) + r"))?)?\b"
)


def numbers_in(text: str) -> list[float]:
    """Numbers written as digits ("10,450", "6.1%", "26:12" as 26.12) or as words ("fifty-two")."""
    values: list[float] = []
    for token in _NUMBER.findall(text):
        token = token.replace(",", "").rstrip("%")
        values.append(float(token.replace(":", ".")))
    for match in _WORD_NUMBER.finditer(text.lower()):
        tens, unit_after, unit, hundred_tens = match.groups()
        value = _TENS[tens] + (_UNITS[unit_after] if unit_after else 0) if tens else _UNITS[unit or "zero"]
        if "hundred" in match.group(0):
            value = value * 100 + (_TENS[hundred_tens] if hundred_tens else 0)
        values.append(float(value))
    return values


@dataclass(frozen=True)
class Biomarker:
    name: str  # resting heart rate, HRV, body weight
    concept: Concept
    values: tuple[float, ...]  # this week and last week


@dataclass(frozen=True)
class WeekFacts:
    member_first: str
    coach_first: str
    coach_full: str
    other_coach_firsts: frozenset[str]
    avoid_weight_talk: bool
    biomarkers: tuple[Biomarker, ...]
    lab_names: tuple[Concept, ...]
    pain_terms: tuple[str, ...]  # pain, injury or illness the member reported this week
    condition_terms: tuple[str, ...]
    distress_terms: tuple[str, ...]
    injection_terms: tuple[str, ...]
    sleep_hours: tuple[float, ...]
    daily_steps: tuple[float, ...]
    sessions: tuple[tuple[str, str, bool], ...]  # (weekday, workout name, completed), lowercase
    completed: int
    planned: int
    specifics: tuple[Concept, ...]  # things the draft can name to be specific
    grounded_numbers: frozenset[float]


# Coach names seen in this deployment's data, so a sign-off from the wrong coach is recognized.
KNOWN_COACH_FIRSTS = frozenset({"Jordan", "Elena", "Priya", "Marcus", "Sam", "Tasha"})

_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_GENERIC_WORKOUT_WORDS = {
    "strength",
    "full",
    "body",
    "upper",
    "lower",
    "day",
    "session",
    "class",
    "run",
    "easy",
    "walk",
    "the",
    "and",
    "with",
    "of",
    "a",
    "to",
    "new",
    "block",
    "only",
    "intro",
    "practice",
    "x",
}


def _lab_concepts(week: MemberWeek) -> tuple[Concept, ...]:
    concepts: list[Concept] = []
    for lab in week.new_labs:
        # "Vitamin D, 25-hydroxy" -> "vitamin d, 25-hydroxy" and "vitamin d"
        name = lab.name.lower()
        concepts.append(phrase(name))
        head = re.split(r"[,(]", name)[0].strip()
        if head and head != name:
            concepts.append(phrase(head))
    return tuple(concepts)


def _member_text(week: MemberWeek) -> str:
    notes = [w.member_note for w in week.workouts if w.member_note]
    said = [m.text for m in week.messages if m.sender == "member"]
    return "\n".join(notes + said)


def _specifics(week: MemberWeek) -> tuple[Concept, ...]:
    terms: set[str] = set()
    for workout in week.workouts:
        if not workout.completed:
            continue
        terms.add(_DAYS[workout.day.weekday()])
        for word in re.findall(r"[a-z][a-z'-]+", workout.name.lower()):
            if word not in _GENERIC_WORKOUT_WORDS and len(word) > 2:
                terms.add(word)
        for word in re.findall(r"[a-z][a-z'-]{3,}", (workout.member_note or "").lower()):
            terms.add(word)
    for number in numbers_in(" ".join(w.name + " " + (w.member_note or "") for w in week.workouts)):
        if number > 12:
            terms.add(f"{number:g}")
            terms.add(f"{number:,.0f}" if number.is_integer() else f"{number:g}")
    return tuple(phrase(t) for t in sorted(terms))


def _grounded(week: MemberWeek) -> frozenset[float]:
    """Numbers the draft may use: anything in the input, simple sums and differences, and constants."""
    data = week.model_dump(mode="json")
    data.pop("week_start", None)
    raw = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", json.dumps(data).replace(",", ""))]
    raw += [float(t.replace(":", ".")) for t in re.findall(r"\d{1,2}:\d{2}", json.dumps(data))]
    base = {round(n, 2) for n in raw}
    derived = set(base)
    small = [n for n in base if n < 100000]
    for a, b in combinations(small, 2):
        derived.add(round(abs(a - b), 2))
        derived.add(round(a + b, 2))
    durations = [w.duration_min for w in week.workouts if w.completed]
    derived.add(float(sum(durations)))
    # Rounded forms: "about 9,000 steps" for 8,950, "7 hours" for 7.0, "over 7" for 7.3.
    for n in list(base):
        for step in (0.5, 1, 5, 10, 50, 100, 500, 1000):
            derived.add(round(round(n / step) * step, 2))
            derived.add(round((n // step) * step, 2))
    derived |= {1760.0, 5280.0, 1000.0, 100.0, 60.0, 24.0, 26.2, 13.1, 3.1, 6.2, 10000.0}
    return frozenset(derived)


def week_facts(week: MemberWeek) -> WeekFacts:
    vocab = load_vocab()
    metrics = [week.metrics] + ([week.prior_week_metrics] if week.prior_week_metrics else [])
    weights = tuple(m.weight_lbs for m in metrics if m.weight_lbs is not None)
    biomarkers = (
        Biomarker(
            "resting heart rate", vocab["rule4.biomarker.resting_hr"], tuple(float(m.resting_hr_bpm) for m in metrics)
        ),
        Biomarker("HRV", vocab["rule4.biomarker.hrv"], tuple(float(m.hrv_ms) for m in metrics)),
        Biomarker("body weight", vocab["rule4.biomarker.weight"], weights),
    )
    said = _member_text(week)
    coach_parts = week.member.coach_name.split()
    return WeekFacts(
        member_first=week.member.first_name,
        coach_first=coach_parts[0],
        coach_full=week.member.coach_name,
        other_coach_firsts=KNOWN_COACH_FIRSTS - {coach_parts[0]},
        avoid_weight_talk=week.member.avoid_weight_talk,
        biomarkers=biomarkers,
        lab_names=_lab_concepts(week),
        pain_terms=tuple(vocab["rule1.pain_report"].find(said)),
        condition_terms=tuple(vocab["rule1.condition"].find(said)),
        distress_terms=tuple(vocab["escalate.distress"].find(said)),
        injection_terms=tuple(vocab["escalate.injection"].find(said)),
        sleep_hours=tuple(m.avg_sleep_hours for m in metrics),
        daily_steps=tuple(float(m.avg_steps) for m in metrics),
        sessions=tuple((_DAYS[w.day.weekday()], w.name.lower(), w.completed) for w in week.workouts),
        completed=sum(w.completed for w in week.workouts),
        planned=len(week.workouts),
        specifics=_specifics(week),
        grounded_numbers=_grounded(week),
    )
