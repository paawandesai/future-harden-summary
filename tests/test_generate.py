import json
from datetime import date, datetime

import pytest

from weekly_summary.__main__ import main
from weekly_summary.data import load_traces
from weekly_summary.generate import generate_summary
from weekly_summary.llm import ReplayClient
from weekly_summary.models import Member, MemberWeek, Message, Metrics, Trace, Workout


def make_week(first_name: str, steps: int) -> MemberWeek:
    return MemberWeek(
        member=Member(
            id=f"m_{first_name.lower()}",
            first_name=first_name,
            coach_name="Jordan",
            goals=["run a 10k"],
            injuries=[],
            avoid_weight_talk=False,
        ),
        week_start=date(2026, 9, 7),
        workouts=[
            Workout(day=date(2026, 9, 8), name="Tempo run", duration_min=40, completed=True),
            Workout(
                day=date(2026, 9, 10),
                name="Lower body strength",
                duration_min=45,
                completed=False,
                member_note="Busy at work",
            ),
        ],
        metrics=Metrics(avg_sleep_hours=7.2, avg_steps=steps, resting_hr_bpm=58, hrv_ms=64),
        new_labs=[],
        messages=[
            Message(sent_at=datetime(2026, 9, 9, 8, 30), sender="member", text="Legs feel good!")
        ],
    )


TRACES = [
    Trace(
        trace_id="t_001",
        created_at=datetime(2026, 9, 14, 12, 0),
        prompt_version="v2",
        model="claude-sonnet-4-5",
        input=make_week("Ava", 9100),
        output="Great week, Ava! Your tempo run was strong. Jordan",
    ),
    Trace(
        trace_id="t_002",
        created_at=datetime(2026, 9, 14, 12, 5),
        prompt_version="v2",
        model="gpt-4.1",
        input=make_week("Ben", 6400),
        output="Nice work, Ben. Let's get that strength session in next week. Jordan",
    ),
]


def write_traces(path, traces: list[Trace]) -> None:
    path.write_text("".join(t.model_dump_json() + "\n" for t in traces))


def test_replay_returns_recorded_output():
    client = ReplayClient(TRACES)

    assert generate_summary(make_week("Ben", 6400), client) == (
        "Nice work, Ben. Let's get that strength session in next week. Jordan"
    )


def test_replay_raises_on_unknown_input():
    client = ReplayClient(TRACES)

    with pytest.raises(LookupError, match="no recorded output"):
        generate_summary(make_week("Ava", 9101), client)


def test_load_traces_round_trips(tmp_path):
    path = tmp_path / "traces.jsonl"
    write_traces(path, TRACES)

    loaded = load_traces(path)

    assert [t.trace_id for t in loaded] == ["t_001", "t_002"]
    assert loaded[1].input.member.first_name == "Ben"
    assert loaded[1].input.workouts[1].member_note == "Busy at work"
    assert loaded == TRACES


def test_run_with_replay_writes_outputs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "replay")
    traces_path = tmp_path / "traces.jsonl"
    out = tmp_path / "runs" / "out.jsonl"
    write_traces(traces_path, TRACES)

    main(["--traces", str(traces_path), "run", "--out", str(out)])

    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [(r["trace_id"], r["output"]) for r in rows] == [
        ("t_001", "Great week, Ava! Your tempo run was strong. Jordan"),
        ("t_002", "Nice work, Ben. Let's get that strength session in next week. Jordan"),
    ]
    assert [(r["prompt_version"], r["model"]) for r in rows] == [("v3", "replay"), ("v3", "replay")]
    assert capsys.readouterr().out == f"{out}\n"


def test_replay_keeps_each_draft_when_inputs_match(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "replay")
    first = TRACES[0]
    second = first.model_copy(update={"trace_id": "t_003", "output": "Second draft, Ava. Jordan"})
    traces_path = tmp_path / "traces.jsonl"
    out = tmp_path / "out.jsonl"
    write_traces(traces_path, [first, second])

    main(["--traces", str(traces_path), "run", "--out", str(out)])
    capsys.readouterr()
    main(["--traces", str(traces_path), "generate", "t_001"])

    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [(r["trace_id"], r["output"]) for r in rows] == [
        ("t_001", "Great week, Ava! Your tempo run was strong. Jordan"),
        ("t_003", "Second draft, Ava. Jordan"),
    ]
    assert capsys.readouterr().out == "Great week, Ava! Your tempo run was strong. Jordan\n"


def test_run_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "replay")
    traces_path = tmp_path / "traces.jsonl"
    out = tmp_path / "out.jsonl"
    write_traces(traces_path, TRACES)

    main(["--traces", str(traces_path), "run", "--out", str(out), "--limit", "1"])

    assert [json.loads(line)["trace_id"] for line in out.read_text().splitlines()] == ["t_001"]
