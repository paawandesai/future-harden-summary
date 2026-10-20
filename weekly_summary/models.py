from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class Member(BaseModel):
    id: str
    first_name: str
    coach_name: str
    goals: list[str]
    injuries: list[str]
    avoid_weight_talk: bool


class Workout(BaseModel):
    day: date
    name: str
    duration_min: int
    completed: bool
    member_note: str | None = None


class Metrics(BaseModel):
    avg_sleep_hours: float
    avg_steps: int
    resting_hr_bpm: int
    hrv_ms: int
    weight_lbs: float | None = None


class LabResult(BaseModel):
    name: str
    value: float
    unit: str
    reference_range: str


class Message(BaseModel):
    sent_at: datetime
    sender: Literal["member", "coach"]
    text: str


class MemberWeek(BaseModel):
    member: Member
    week_start: date
    workouts: list[Workout]
    metrics: Metrics
    prior_week_metrics: Metrics | None = None
    new_labs: list[LabResult]
    messages: list[Message]


class Trace(BaseModel):
    trace_id: str
    created_at: datetime
    prompt_version: str
    model: str
    input: MemberWeek
    output: str
