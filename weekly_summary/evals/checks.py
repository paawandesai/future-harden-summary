"""Deterministic guidebook checks. Each one reads a draft and the week's facts and returns findings.

A finding's `reason` is the one line a coach reads. It names the rule and what was found, and it
never repeats a member's values. `evidence` holds the matched text for eval reports only.
"""

import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from weekly_summary.evals.facts import WeekFacts, numbers_in
from weekly_summary.evals.vocab import Concept, load_vocab, normalize

Rule = Literal["1", "2", "3", "4", "other"]
Severity = Literal["block", "flag"]


class Finding(BaseModel):
    rule: Rule
    check: str
    severity: Severity
    reason: str
    evidence: str = ""
    source: Literal["code", "judge"] = "code"


Check = Callable[[str, WeekFacts], list[Finding]]

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_EMOJI = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f000-\U0001f2ff\U0001f900-\U0001f9ff]️?(?:‍[^\\s]️?)*"
)
_MARKDOWN = re.compile(r"^\s*(?:#{1,6}\s|[-*•]\s|\d+[.)]\s)|\*\*[^*]+\*\*", re.MULTILINE)
_WORD = re.compile(r"[A-Za-z0-9][\w'’-]*")


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE.split(text.strip()) if s]


def _near(value: float, numbers: list[float], tolerance: float) -> bool:
    return any(abs(value - n) <= tolerance for n in numbers)


# Rule 4 ---------------------------------------------------------------------------------------


def biomarker_values(draft: str, facts: WeekFacts) -> list[Finding]:
    """A biomarker value from this member's data, or any number next to a biomarker unit."""
    findings: list[Finding] = []
    for marker in facts.biomarkers:
        for sentence in sentences(draft):
            terms = marker.concept.find(sentence)
            if not terms:
                continue
            numbers = numbers_in(sentence)
            tolerance = 0.5 if marker.name == "body weight" else 0
            exact = [v for v in marker.values if _near(v, numbers, tolerance)]
            unit = re.search(r"\d\s*(bpm|ms)\b", sentence.lower()) if marker.name != "body weight" else None
            # A weight change ("down another 1.4 lb") quotes the weight as surely as the weight does.
            delta = (
                marker.name == "body weight"
                and len(marker.values) == 2
                and _near(round(abs(marker.values[0] - marker.values[1]), 1), numbers, 0.05)
            )
            if exact or unit or delta:
                findings.append(
                    Finding(
                        rule="4",
                        check="biomarker_value",
                        severity="block",
                        reason=f"Quotes a {marker.name} value (Rule 4).",
                        evidence=sentence,
                    )
                )
                break
    return findings


def lab_mentions(draft: str, facts: WeekFacts) -> list[Finding]:
    vocab = load_vocab()
    terms = vocab["rule4.lab"].find(draft)
    for concept in facts.lab_names:
        terms += concept.find(draft)
    if not terms:
        return []
    return [
        Finding(
            rule="4",
            check="lab_mention",
            severity="block",
            reason="Mentions lab results (Rule 4).",
            evidence=", ".join(terms),
        )
    ]


# Rule 2 ---------------------------------------------------------------------------------------


def weight_talk(draft: str, facts: WeekFacts) -> list[Finding]:
    vocab = load_vocab()
    body, target = vocab["rule2.body"], vocab["rule2.target"]
    weight_units = vocab["rule4.biomarker.weight"]
    findings: list[Finding] = []
    if facts.avoid_weight_talk and (terms := body.find(draft)):
        findings.append(
            Finding(
                rule="2",
                check="avoid_weight_talk",
                severity="block",
                reason="Mentions weight, body or appearance for a member who asked to avoid weight talk (Rule 2).",
                evidence=", ".join(terms),
            )
        )
    lift = vocab["rule2.lift"]
    for sentence in sentences(draft):
        # A weight unit next to a lift is a load. Body words still count whatever else is there.
        weight_unit = weight_units.hits(sentence) and not lift.hits(sentence)
        if (body.hits(sentence) or weight_unit) and target.hits(sentence):
            findings.append(
                Finding(
                    rule="2",
                    check="weight_target",
                    severity="block",
                    reason="Sets a weight target or treats weight as something to fix (Rule 2).",
                    evidence=sentence,
                )
            )
            break
    terms = vocab["rule2.earn_burn"].find(draft)
    terms += [t for x in sentences(draft) if vocab["rule2.food"].hits(x) for t in vocab["rule2.earn"].find(x)]
    if terms:
        findings.append(
            Finding(
                rule="2",
                check="earn_burn",
                severity="flag",
                reason="May frame food or exercise as earning or burning something off (Rule 2).",
                evidence=", ".join(terms),
            )
        )
    return findings


# Rule 3 ---------------------------------------------------------------------------------------


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


def opening_and_signoff(draft: str, facts: WeekFacts) -> list[Finding]:
    findings: list[Finding] = []
    words = _WORD.findall(draft)
    if not words or words[0] != facts.member_first:
        findings.append(
            Finding(
                rule="3",
                check="opening",
                severity="flag",
                reason="Does not start with the member's first name (Rule 3).",
                evidence=" ".join(words[:6]),
            )
        )
    tail = draft.strip().rstrip(".!")
    last = words[-1] if words else ""
    if tail.endswith(facts.coach_full) and facts.coach_full != facts.coach_first:
        findings.append(
            Finding(
                rule="3",
                check="signoff",
                severity="flag",
                reason="Signs off with the coach's full name, not first name (Rule 3).",
                evidence=last,
            )
        )
    elif last in facts.other_coach_firsts:
        findings.append(
            Finding(
                rule="3",
                check="signoff",
                severity="block",
                reason="Signed with a different coach's name (Rule 3).",
                evidence=last,
            )
        )
    elif last != facts.coach_first:
        findings.append(
            Finding(
                rule="3",
                check="signoff",
                severity="flag",
                reason="Does not end with the coach's first name (Rule 3).",
                evidence=last,
            )
        )
    return findings


def length_and_format(draft: str, facts: WeekFacts) -> list[Finding]:
    vocab = load_vocab()
    findings: list[Finding] = []
    if (count := word_count(draft)) > 150:
        findings.append(
            Finding(
                rule="3",
                check="length",
                severity="flag",
                reason=f"Runs {count} words, over the 150-word limit (Rule 3).",
                evidence=str(count),
            )
        )
    if (emoji := len(_EMOJI.findall(draft))) > 1:
        findings.append(
            Finding(
                rule="3",
                check="emoji",
                severity="flag",
                reason=f"Uses {emoji} emoji; the limit is one (Rule 3).",
                evidence=str(emoji),
            )
        )
    bot = vocab["rule3.bot"].find(draft)
    if bot or _MARKDOWN.search(draft):
        findings.append(
            Finding(
                rule="3",
                check="bot_voice",
                severity="flag",
                reason="Reads like a bot: a label, heading or list (Rule 3).",
                evidence=", ".join(bot) or "markdown",
            )
        )
    if hype := vocab["rule3.hype"].find(draft):
        findings.append(
            Finding(
                rule="3", check="hype", severity="flag", reason="Uses hype words (Rule 3).", evidence=", ".join(hype)
            )
        )
    if guilt := vocab["rule3.guilt"].find(draft):
        findings.append(
            Finding(
                rule="3",
                check="guilt",
                severity="flag",
                reason="May make the member feel guilty about missed workouts (Rule 3).",
                evidence=", ".join(guilt),
            )
        )
    return findings


def specificity(draft: str, facts: WeekFacts) -> list[Finding]:
    if any(concept.hits(draft) for concept in facts.specifics) or facts.completed == 0:
        return []
    return [
        Finding(
            rule="3",
            check="specificity",
            severity="flag",
            reason="Names nothing specific the member did this week (Rule 3).",
        )
    ]


# Rule 1 ---------------------------------------------------------------------------------------

_NEGATION = re.compile(
    r"\b(?:rather than|instead of|not|don't|do not|never|no need to|without|avoid)\s+(?:\w+\s+){0,2}$"
)


def _unnegated(concept: Concept, text: str) -> list[str]:
    """Terms of `concept` in text, except where a negation comes just before ("rather than pushing through")."""
    found: list[str] = []
    for sentence in sentences(normalize(text)):
        for term in concept.find(sentence):
            for match in re.finditer(r"(?<![\w'])" + re.escape(normalize(term)) + r"(?![\w'])", sentence):
                if not _NEGATION.search(sentence[: match.start()]):
                    found.append(term)
                    break
    return found


def medical_advice(draft: str, facts: WeekFacts) -> list[Finding]:
    vocab = load_vocab()
    findings: list[Finding] = []
    reported = bool(facts.pain_terms or facts.condition_terms)
    if diagnosis := vocab["rule1.diagnosis"].find(draft):
        findings.append(
            Finding(
                rule="1",
                check="diagnosis",
                severity="block",
                reason="Names a likely condition or diagnosis (Rule 1).",
                evidence=", ".join(diagnosis),
            )
        )
    if treatment := vocab["rule1.treatment"].find(draft):
        findings.append(
            Finding(
                rule="1",
                check="treatment",
                severity="block" if reported else "flag",
                reason="Recommends a treatment (Rule 1)." if reported else "May recommend a treatment (Rule 1).",
                evidence=", ".join(treatment),
            )
        )
    if reported and (around := _unnegated(vocab["rule1.train_through"], draft)):
        findings.append(
            Finding(
                rule="1",
                check="train_through",
                severity="block",
                reason="Gives training advice about a reported pain or condition (Rule 1).",
                evidence=", ".join(around),
            )
        )
    if reported and not vocab["rule1.coach_contact"].hits(draft):
        findings.append(
            Finding(
                rule="1",
                check="coach_contact",
                severity="flag",
                reason="Member reported pain or illness; the draft doesn't say the coach will reach out (Rule 1).",
                evidence=", ".join(facts.pain_terms + facts.condition_terms),
            )
        )
    return findings


# Outside the guidebook ------------------------------------------------------------------------


def member_signals(draft: str, facts: WeekFacts) -> list[Finding]:
    """Member text the coach must see whatever the draft says."""
    findings: list[Finding] = []
    if facts.distress_terms:
        findings.append(
            Finding(
                rule="other",
                check="distress",
                severity="flag",
                reason="Priority: member's message may show distress or disordered eating. Read it before approving.",
                evidence=", ".join(facts.distress_terms),
            )
        )
    if facts.injection_terms:
        findings.append(
            Finding(
                rule="other",
                check="injection",
                severity="flag",
                reason="Member text contains instructions aimed at the AI. Check the draft did not follow them.",
                evidence=", ".join(facts.injection_terms),
            )
        )
    return findings


_COUNT_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_COUNT_CLAIM = re.compile(
    r"\b(?:all|every one of)\s+(two|three|four|five|six|seven|\d)\b|\b(two|three|four|five|six|seven|\d)\s+for\s+\2\b"
)


def grounding(draft: str, facts: WeekFacts) -> list[Finding]:
    """Numbers and session counts the input does not support."""
    findings: list[Finding] = []
    ungrounded = [
        n
        for n in numbers_in(_strip_times_and_dates(draft))
        if n > 12 and round(n, 2) not in facts.grounded_numbers and n not in (2025, 2026)
    ]
    if ungrounded:
        findings.append(
            Finding(
                rule="other",
                check="ungrounded_number",
                severity="flag",
                reason="States a number that isn't in this week's data. Check it.",
                evidence=", ".join(f"{n:g}" for n in ungrounded),
            )
        )
    past = " ".join(x for x in sentences(normalize(draft)) if not re.search(r"next week|let's|we'll|will ", x))
    for claim in _COUNT_CLAIM.finditer(past):
        word = claim.group(1) or claim.group(2)
        claimed = _COUNT_WORDS.get(word) or int(word)
        if claimed != facts.completed and claimed > facts.completed:
            findings.append(
                Finding(
                    rule="other",
                    check="session_count",
                    severity="flag",
                    reason="Claims more completed sessions than the data shows. Check it.",
                    evidence=claim.group(0),
                )
            )
            break
    return findings


_WEEKDAY = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:'s)?\b")
_FORWARD = re.compile(r"\bnext\b|\blet's\b|\bwe'll\b|\bwill\b|\btomorrow\b|\bthis coming\b|\bplan\b")
_NOT_DONE = re.compile(
    r"\bmiss(?:ed|ing)?\b|\bskip(?:ped)?\b|didn't|did not|\bcut\b|\bslipped\b|\bmoved\b|\bswapped\b|"
    r"\bswap\b|\brain|\bclosed\b|\bsick\b|\bcancel|\bbailed\b|\bstopped\b|\binstead\b|wasn't|couldn't|\bout\b|\boff\b|\blost\b|\blate\b|\bmak(?:e|ing) up\b|\bmade up\b"
)
# Workout kinds a draft counts, and the words in a workout name that make it that kind.
_KINDS = {
    "session": "",
    "sessions": "",
    "workout": "",
    "workouts": "",
    "run": "run",
    "runs": "run",
    "swim": "swim",
    "swims": "swim",
    "ride": "ride|bike|spin|cycl",
    "rides": "ride|bike|spin|cycl",
    "class": "class|yoga|pilates|spin|aerobics",
    "classes": "class|yoga|pilates|spin|aerobics",
    "walk": "walk|hike",
    "walks": "walk|hike",
    "lifting day": "strength|lift|deadlift|squat|bench|push|pull|leg",
    "lifting days": "strength|lift|deadlift|squat|bench|push|pull|leg",
    "strength day": "strength",
    "strength days": "strength",
    "strength session": "strength",
    "strength sessions": "strength",
}
_COUNTED = re.compile(
    r"\b(one|two|three|four|five|six|seven|\d)\s+(?:\w+\s+)?("
    + "|".join(sorted((re.escape(k) for k in _KINDS), key=len, reverse=True))
    + r")\b"
)
_ONE = {"one": 1, **_COUNT_WORDS}


_WORKOUT_WORDS = {
    "run",
    "runs",
    "ride",
    "rides",
    "swim",
    "swims",
    "class",
    "classes",
    "session",
    "sessions",
    "workout",
    "workouts",
    "walk",
    "walks",
    "hike",
    "row",
    "rowing",
    "lift",
    "lifting",
    "strength",
    "yoga",
    "pilates",
    "spin",
    "circuit",
    "circuits",
    "intervals",
    "tempo",
    "drills",
    "match",
    "practice",
    "rehab",
}


def _workout_near(sentence: str, start: int, end: int, names: set[str]) -> bool:
    before = re.findall(r"[a-z][a-z'-]*", sentence[:start])[-4:]
    after = re.findall(r"[a-z][a-z'-]*", sentence[end:])[:4]
    return any(w in _WORKOUT_WORDS or w in names for w in before + after)


def calendar_claims(draft: str, facts: WeekFacts) -> list[Finding]:
    """Weekdays and workout counts in past-tense sentences, compared with the week's workouts.

    A workout placed on a day with nothing scheduled, a missed workout described as done (unless
    the sentence says it was missed), or more workouts of a kind than were done all mean the draft
    states something untrue.
    """
    days_done = {day for day, _, done in facts.sessions if done}
    days_any = {day for day, _, _ in facts.sessions}
    names = {w for _, name, _ in facts.sessions for w in re.findall(r"[a-z]{3,}", name)} - {"day", "the", "and", "with"}
    uncategorized = sum(
        1 for _, name, ok in facts.sessions if ok and not any(p and re.search(p, name) for p in _KINDS.values())
    )
    for sentence in sentences(normalize(draft)):
        if _FORWARD.search(sentence):
            continue
        for match in _WEEKDAY.finditer(sentence):
            day = match.group(1)
            if not _workout_near(sentence, match.start(), match.end(), names):
                continue
            if day not in days_any:
                return [
                    _calendar(
                        f"Places a workout on {day.title()}, but nothing was scheduled that day. Check it.", sentence
                    )
                ]
            if day not in days_done and not _NOT_DONE.search(sentence):
                return [_calendar("Describes a missed workout as done. Check it.", sentence)]
        for match in _COUNTED.finditer(sentence):
            # "three of four sessions" and "4 of 5 planned" count what was planned, not what was done.
            if re.search(r"\bof\s*$", sentence[: match.start()]) or re.match(r"\s+planned", sentence[match.end() :]):
                continue
            claimed, kind = _ONE.get(match.group(1)) or int(match.group(1)), match.group(2)
            pattern = _KINDS[kind]
            done = sum(1 for _, name, ok in facts.sessions if ok and (not pattern or re.search(pattern, name)))
            # Workouts whose names fit no kind ("Intervals: 5 x 800m") may be what the draft counts.
            allowance = uncategorized if pattern else 0
            if claimed > done + allowance and not _NOT_DONE.search(sentence):
                return [_calendar("Counts more workouts than the data shows. Check it.", sentence)]
    return []


def _calendar(reason: str, sentence: str) -> Finding:
    return Finding(rule="other", check="calendar", severity="flag", reason=reason, evidence=sentence)


_DIGITS = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
_TARGET_BEFORE = re.compile(r"\b(?:above|below|toward|towards|to|past|under|of)\s*$", re.I)


def _nearest_figure(sentence: str, word: re.Pattern[str]) -> float | None:
    """The digit number closest to `word`, skipping goals such as "toward 7" or "above 7"."""
    anchor = word.search(sentence)
    if not anchor:
        return None
    figures = [
        (abs(m.start() - anchor.start()), float(m.group().replace(",", "")))
        for m in _DIGITS.finditer(sentence)
        if not _TARGET_BEFORE.search(sentence[: m.start()])
    ]
    return min(figures)[1] if figures else None


_SLEEP = re.compile(r"\bsleep\b|\bslept\b", re.I)
_STEPS = re.compile(r"\bsteps\b", re.I)


def activity_values(draft: str, facts: WeekFacts) -> list[Finding]:
    """Sleep or step figures that disagree with this week's or last week's averages."""
    for sentence in sentences(draft):
        hours = _nearest_figure(sentence, _SLEEP)
        if hours is not None and 3 <= hours <= 12 and not _near(hours, list(facts.sleep_hours), 0.3):
            return [_mismatch("sleep", sentence)]
        steps = _nearest_figure(sentence, _STEPS)
        if steps is not None and steps >= 1000 and steps != 10000:
            if not any(abs(steps - v) <= 0.05 * v for v in facts.daily_steps):
                return [_mismatch("steps", sentence)]
    return []


def _mismatch(what: str, sentence: str) -> Finding:
    return Finding(
        rule="other",
        check="activity_value",
        severity="flag",
        reason=f"States a {what} figure that doesn't match this week's data. Check it.",
        evidence=sentence,
    )


def _strip_times_and_dates(text: str) -> str:
    return re.sub(
        r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}\b",
        " ",
        text,
        flags=re.I,
    )


CHECKS: tuple[Check, ...] = (
    biomarker_values,
    lab_mentions,
    weight_talk,
    opening_and_signoff,
    length_and_format,
    specificity,
    medical_advice,
    member_signals,
    grounding,
    activity_values,
    calendar_claims,
)


def run_checks(draft: str, facts: WeekFacts) -> list[Finding]:
    return [finding for check in CHECKS for finding in check(draft, facts)]
