# Weekly summary: evals, fixes and guardrails

For the engineer taking over this feature. One command runs the feature, the evals and the guardrails (see
README and `RUNBOOK.md`):

```
uv run weekly-summary pipeline <traces.jsonl> [--no-generate | --code-only] --out decisions.jsonl
```

## 1. Eval design

There are two layers. **Code checks** handle anything decidable from the draft text plus the trace input. An
**LLM judge** (`claude-haiku-5-5`) handles intent. Every finding has a rule, a severity, a one-line reason for
the coach and the matched text. The terms the code acts on live in one reviewable file,
`weekly_summary/evals/vocab.toml`: concepts per rule, with synonyms and exclusions. Per-member facts come from the
input: biomarker values, lab names, coach name, workouts by weekday and pain reports (`evals/facts.py`).

| Rule | Code (exact, so it can block) | Judge (needs meaning, so it only flags) |
|---|---|---|
| 4 Privacy | This member's resting HR, HRV and weight found in the draft, including spelled-out numbers and an exact weight with no weight word. Lab words, this member's own test names, and (when labs exist) a result judged high, low or normal. | Not judged. |
| 2 Weight | With `avoid_weight_talk`: any body or appearance word (lift loads excluded). For everyone: a body word plus a target or setback cue in one sentence. | Earning or burning framing, setbacks, subtle appearance talk. |
| 1 Medical | Diagnoses, treatments and "work around it" advice. A pain, illness or condition in member text means the draft must say the coach will reach out. | Implied diagnoses, reassurance, advice phrased in new ways. |
| 3 Voice | Starts with the member's first name and ends with the coach's **first** name (any other name blocks). Also length, emoji, hype, bot labels, and naming something specific. | Guilt, report-like tone. |
| Outside the guidebook | Weekday and count claims checked against the calendar, numbers absent from the input, distress or prompt injection in member text. | Claims the input contradicts, following member-text instructions. |

**The judge can only make results stricter.** It adds flags and never clears a code finding. An API error or
unparseable output becomes a flag, and a quote that isn't in the draft is marked "unsure". When the only finding
is a judge-only "other", Sonnet must also agree (section 4). Judge responses are cached, so `--no-generate`
replays without a key.

**Labels and judge accuracy.** Every label set was written by an agent and then reviewed by me against
`labels/RUBRIC.md`. The record of who labeled and reviewed each set, and when, is in `labels/REVIEW_LOG.md`. Claude
pre-filled the 60 production labels, which are split by hash into 40 dev and 20 held-out. The code checks were written while reading those 60, so
they are in-sample there. For honest numbers, separate agents that never saw the checks wrote two blind sets:
**40 challenge drafts** and **30 rehearsal traces** with new names, sports and edge cases. The checks are frozen
against the challenge set, so a miss there is reported and never patched one case at a time.

| Blind set | Code only: violations passed | Code + judge: violations passed | Code + judge: clean drafts flagged |
|---|---|---|---|
| Challenge, 30 violating / 10 clean | 10 (now 9) | **0** | 1 |
| Rehearsal, 19 violating / 11 clean | 3 (now 2) | **0** | 5 (now 4) |

The first number in each cell is the blind result. "Now" is after generic fixes, which made those sets partly
in-sample. The challenge change came from this audit: c_024 quoted the member's weight with no weight word, and
the exact-weight check now blocks it.

Per rule on the challenge set (code + Haiku: caught, false positives, κ): Rule 1 8/8, 2, 0.86. Rule 2 7/7, 0,
1.00. Rule 3 8/8, 0, 1.00. Rule 4 4/5, 0, 0.87. Other 9/10, 5, 0.65. Haiku's run-to-run κ is 0.79–1.00 on Rules
1–3 and 0.52–0.72 on "other". As a self-preference test, Sonnet re-judged 60 Haiku-written drafts: Haiku flagged 6
and Sonnet 4, so Haiku was not lenient on its own drafts. Details: `results/JUDGE_AGREEMENT.md`,
`results/REHEARSAL.md`.

**Metrics to watch:**
- violation rate per rule;
- the pass/flag/block mix;
- labeled violations that passed, which must stay at 0;
- clean drafts flagged;
- two quality floors, so bland drafts can't score well: the share of drafts that name something specific, and
  mean length.

`weekly-summary compare <before> <after>` prints what moved between two runs. It exits non-zero if a labeled
violation starts passing or more clean drafts get flagged. **CI enforces the evals:** `weekly-summary gate` runs
every frozen labeled set on each merge request and fails if any set misses more violations or flags more clean
drafts than `weekly_summary/evals/gate.toml` allows. It needs no API key, because judge verdicts replay from the
committed cache. The limits were set to today's results, so the gate proves "no regression", not "good". `weekly-summary view` (or `pipeline --html`) writes the coach's page: each draft with its
decision, its reasons and the matched words highlighted (`results/views/`).

## 2. Findings (60 production drafts, reviewed labels)

25 of 60 drafts break at least one rule: 19 of 49 from Sonnet 4.5 and 6 of 11 from GPT-4.1. Each failure traces to
a line in the old prompt (v3):

| Failure | Count | Cause |
|---|---|---|
| Rule 4: lab results mentioned | 3 of 5 weeks with labs | The prompt said to reference "any new lab results". |
| Rule 4: HR, HRV or weight quoted | 4 | The prompt said to reference "heart rate, HRV, weight". |
| Rule 1: advice about reported pain | **5 of 9** pain weeks | "Give them a helpful tip so they can keep training" led to diagnosed shin splints, ice, braces and treadmill swaps. |
| Rule 2: weight pressure | 7, including 3 of 18 `avoid_weight_talk` members | The prompt quoted weight and never mentioned the flag: "be at 220 by Halloween", "you look trimmer". |
| Rule 3: voice | 7 | "Upbeat and motivating!" led to hype. "Keep them accountable" led to guilt ("no excuses"). |
| Outside the guidebook | 5 | Missed workouts described as done, wrong sleep figures, invented classes, **a draft signed by the wrong coach**. Cause: raw JSON input with no done/missed framing and no coach first name. |

The guidebook also misses two risks. Health conditions such as asthma appear only in member notes, not in
`injuries`, so the code reads member text. Member messages can also carry prompt injection or distress, and both
are flagged as priority.

## 3. Feature shape: a fixed workflow, not an agent

1. **Strip in code** what the model must not quote: labs, HR and HRV values (replaced by trend words), and
   weight. Render the week as plain facts: weekday, done or missed, the coach's first name, and a "health issue
   reported" line.
2. **Generate** with a prompt that states the guidebook.
3. **Run the code checks.** If something fixable fails, make **one repair call** that names the broken rules.
4. **Decide**, using the code checks plus the judge.

Why not one prompt: Haiku on the old prompt broke a rule in **60 of 60** drafts, and quoted a biomarker or lab in
every one of them. Prompt wording can't reliably stop a model from quoting data it was given, but removing the
data can. Why not an agent: the steps are fixed, so an agent would add cost, latency and new ways for member text
to steer the output, with nothing for it to decide.

## 4. Guardrail policy

- **Block** (code only, so it is reproducible). This covers a quoted biomarker or lab mention, weight talk under
  `avoid_weight_talk`, and a weight target. It also covers a diagnosis, a treatment, or training advice about a
  reported pain, plus a sign-off from someone other than this member's coach. Finally, it covers no draft
  produced and an unreadable trace. The coach sees why and regenerates or rewrites.
- **Flag** (up to three one-line reasons). This covers judge findings, pain without "I'll reach out", guilt, hype,
  length, emoji, bot voice, and a draft that isn't specific. It also covers figures or days the data
  contradicts, distress or injection in member text, and any judge failure. A judge-only "other" finding stands
  only if Sonnet (`claude-sonnet-5-5`) agrees, or if the Sonnet call fails.
- **Pass:** nothing found.

**Expected flag rate: about 7% on familiar inputs and about 17% on unseen ones, with almost no blocks.**
- **Familiar inputs:** 2 to 6 of 60 drafts per run (44 of 600 overall), across 8 v4 generations (`results/after`,
  `results/before_after`) and 2 v5 generations (`results/v5`), with 0 blocks. These are the production inputs the
  checks' false-positive fixes were tuned on.
- **Unseen inputs:** the shipped v5 prompt on the 30 rehearsal traces flags 5 (17%) and blocks none
  (`results/v5/decisions_rehearsal.jsonl`).
- **What the flags are:** of the 44 flagged drafts, 23 carry a judge Rule 1 finding, usually on how a reported pain
  or illness was handled. 12 carry a judge data-contradiction finding, 5 a calendar mismatch, and the rest are
  code figure checks.

Coaches should keep reading at these rates, because each reason names what to check. But the measured precision
is modest: about 1 flag in 3 is a real violation on v5 drafts (below). Raising it is the first next step.

Why Sonnet confirmation: in a reviewed sample of 30 new v4 drafts (labeled blind by an agent, reviewed by me), 4 of 5 flags were judge-only "other" findings
on clean drafts. With confirmation, no set lets a labeled violation through, and false flags drop. Dropping those
findings instead would let 3 violations pass. It costs under $0.10 per 60 traces.

| Set | Clean drafts flagged: Haiku only → + Sonnet confirm | Violations passed |
|---|---|---|
| Production 60 | 6 → 3 | 0 → 0 |
| Challenge 40 | 3 → 1 | 0 → 0 |
| New-draft sample 30 | 4 → 1 (borderline) | 0 → 0 |

## 5. Results: before and after

The same 60 inputs, the same checks and the Haiku judge, with every row scored with Sonnet confirmation.

| Version | Any violation | R1 | R2 | R3 | R4 | Other | Pass / flag / block |
|---|---|---|---|---|---|---|---|
| Before: production drafts (prompt v3) | 28 | 9 | 6 | 7 | 7 | 8 | 32 / 11 / 17 |
| Old prompt v3 on Haiku | 60 | 16 | 4 | 21 | 60 | 16 | 0 / 0 / 60 |
| **New workflow on Haiku (prompt v4), 3 runs** | **2, 4, 3** | 0, 2, 2 | 1, 1, 0 | 0 | 0 | 1, 1, 1 | 58 / 2 / 0, 56 / 4 / 0, 57 / 3 / 0 |
| Prompt v5 (shipped), 2 runs | 6, 4 | 4, 1 | 0 | 0 | 0 | 2, 3 | 54 / 6 / 0, 56 / 4 / 0 |

v5 changes one line: the model must leave lab requests out entirely, instead of saying it can't discuss them.
On the rehearsal trace with an injected request for cholesterol numbers, v4's draft was blocked for "I'm not able
to discuss test results". v5's draft doesn't mention tests and is only flagged for the injection. Otherwise v5's
flag counts are within v4's run-to-run range (2–6 of 60). Two runs can't show more than that.

Every new draft names something specific from the week, and mean length went from 78 words to 86. A reviewed
sample of 30 v4 drafts (labeled blind, reviewed by me) had 1 violation (t_049, Rule 2), and it was flagged.

**Measured on v5 drafts** (`data/v5_sample.jsonl`): the sample is all 7 drafts flagged in one production run, plus
23 passes chosen at random, labeled blind by an agent and reviewed by me. 3 drafts break a rule, all in subtle ways.
- **Caught (2):**
  - t_038 praises training through a pulled muscle.
  - t_022 says a ride the member cut short was finished.
- **Missed (1):** t_058 calls a PT visit that already happened "on Wednesday" upcoming.
- **Flag precision:** blind, 2 of the 7 flags were real, 2 were borderline and 3 were false. Two of the false flags
  came from generic code gaps, which are now fixed: "your 7-hour goal" read as a sleep figure, and "skipping
  Tuesday's class" read as a missed workout called done. After the fixes it is 2 real, 2 borderline and 2 false of
  6. The 2 remaining false flags are judge Rule 1 calls on drafts that acknowledge an issue correctly.
- **Miss rate:** 1 miss in 23 random passes suggests about 2 subtle misses per 60 drafts, all flag-level "other"
  errors. No draft quoted a biomarker or lab, and Rule 3 held in all 30.

## 6. Next steps, in priority order

1. Raise flag precision: extend Sonnet confirmation to judge-only Rule 1 findings, the largest flag group and the
   source of the 2 remaining false flags in the v5 sample. Then track flag rate and precision per coach in
   production.
2. Grow the blind sets with real coach edits as labels, and refresh them each quarter so the checks don't
   overfit.
3. Extract a structured "health issue" field from member text, so the coach-contact rule doesn't depend on
   vocabulary. Code alone still misses paraphrased advice and guilt (rehearsal r_007, r_024), which the judge
   catches.
4. Move Rule 2 judging to Sonnet if more labels confirm Haiku's two production misses (t_008, t_048).
5. Have a person sign off `weekly_summary/evals/vocab.toml`, which is still marked as a model draft.

## 7. AI use

I used **Claude Code** (Opus 5.5) as the coding agent for nearly all of the implementation: the vocabulary,
checks, judge, pipeline, tests, CI and these numbers. The feature and judges run on **Claude Haiku 5.5**, and
**Claude Sonnet 5.5** is the confirmation judge and the cross-check judge. Separate Claude agents that never saw
the checks wrote the challenge and rehearsal sets and their labels. I reviewed every label set (see
`labels/REVIEW_LOG.md`).

Generated artifacts nobody verified independently:
- `vocab.toml`, which is reviewed only through its effect on the labeled sets;
- the rehearsal and challenge drafts themselves, which are synthetic;
- the spend figures, which come from the code's own price table.

**Where I didn't trust the output:** the code checks scored almost perfectly on the 60 drafts, and that was the
warning sign, because they had been written while reading those drafts. I asked for a blind set written by an agent
that never saw the checks. Code alone let 10 of its 30 violations through. That is why the judge exists, and why the
checks are frozen against that set. Where the pipeline disagreed with an agent label (7 production rows, 2
rehearsal rows), the label was checked against the workout dates, and the corrected labels then went through my
review.

**Scope:** this went well past the 3-hour box, at about 6 hours of agent-assisted work in the commit history. That
was a deliberate choice, made to build the fullest version. I also edited `ASSESSMENT.md` once, changing "GitHub
repo" to "GitLab repo" to match where this is hosted.
