# Weekly summary: evals, fixes and guardrails

For the engineer taking over this feature. One command runs the feature, the evals and the guardrails (see
README and `RUNBOOK.md`):

```
uv run weekly-summary pipeline <traces.jsonl> [--no-generate | --code-only] --out decisions.jsonl
```

## 1. Eval design

There are two layers. **Code checks** handle anything decidable from the draft plus the trace input. An **LLM
judge** (`claude-haiku-5-5`) handles intent. Each finding has a rule, a severity, a one-line reason for the coach
and the matched text. The terms the code acts on live in one reviewable file, `weekly_summary/evals/vocab.toml`.
Per-member facts come from the input: biomarker values, lab names, coach name, workouts by weekday and pain
reports (`evals/facts.py`).

| Rule | Code (exact, so it can block) | Judge (needs meaning, so it only flags) |
|---|---|---|
| 4 Privacy | This member's resting HR, HRV or weight in the draft, including spelled-out numbers and a bare exact weight. Lab words, this member's test names, and (when labs exist) a result judged high, low or normal. | Not judged. |
| 2 Weight | With `avoid_weight_talk`: any body or appearance word (lift loads excluded). For everyone: a body word plus a target or setback cue. | Earning or burning framing, setbacks, subtle appearance talk. |
| 1 Medical | Diagnoses, treatments and "work around it" advice. A reported pain or condition means the draft must say the coach will reach out. | Implied diagnoses, reassurance, advice in new words. |
| 3 Voice | Opens with the member's first name, ends with the coach's **first** name (another name blocks). Length, emoji, hype, bot labels, naming something specific. | Guilt, report-like tone. |
| Outside the guidebook | Weekday and count claims against the calendar, numbers not in the input, distress in member text, injection in any text field. | Claims the input contradicts, following member-text instructions. |

**The judge can only make results stricter.** It adds flags and never clears a code finding. An API error or
unparseable output becomes a flag. When the only finding is a judge-only "other", Sonnet must agree (section 4).
Judge responses are cached, so `--no-generate` replays without a key.

**Labels and judge accuracy.** Every label set was written by an agent and then reviewed by me against
`labels/RUBRIC.md` (record in `labels/REVIEW_LOG.md`). Claude pre-filled the 60 production labels (40 dev, 20
held-out by hash). The code checks were written while reading those 60, so they are in-sample there. For honest
numbers, agents that never saw the checks wrote two blind sets: **40 challenge drafts** and **30 rehearsal
traces** with new names, sports and edge cases. The checks are frozen against the challenge set: a miss there is
reported, never patched one case at a time.

| Blind set | Code only: violations passed | Code + judge: violations passed | Code + judge: clean drafts flagged |
|---|---|---|---|
| Challenge, 30 violating / 10 clean | 10 (now 8) | **0** | 1 |
| Rehearsal, 19 violating / 11 clean | 3 (now 2) | **0** | 5 (now 4) |

The first number is the blind result. "Now" is after generic fixes, which made those sets partly in-sample. Two
challenge drafts moved after the pre-submission audit: c_024's bare exact weight now blocks, and c_040's claim
that it "complies with all guidebook rules" now flags.

On the challenge set, code + Haiku per rule (caught, false positives, κ): Rule 1 8/8, 2, 0.86. Rule 2 7/7, 0,
1.00. Rule 3 8/8, 0, 1.00. Rule 4 4/5, 0, 0.87. Other 9/10, 5, 0.65. Haiku's run-to-run κ is 0.79–1.00 on Rules
1–3 and 0.52–0.72 on "other". In a self-preference test, Sonnet re-judged 60 Haiku-written drafts and flagged 4
where Haiku flagged 6, so Haiku isn't lenient on its own drafts. Details: `results/JUDGE_AGREEMENT.md`.

**Metrics to watch:** violation rate per rule, the pass/flag/block mix, labeled violations that passed (must stay
0), clean drafts flagged, and two quality floors so bland drafts can't score well (share naming something
specific, mean length). `weekly-summary compare <before> <after>` shows what moved and exits non-zero if things got
worse. **CI enforces the evals:** `weekly-summary gate` replays every frozen labeled set from the committed judge
cache (no key) and fails if any set exceeds the limits in `weekly_summary/evals/gate.toml`. Those limits are
today's results, so the gate proves "no regression", not "good". `weekly-summary view` writes the coach's page,
with each decision, its reasons and the matched words highlighted (`results/views/`).

## 2. Findings (60 production drafts, reviewed labels)

25 of 60 drafts break at least one rule (19 of 49 from Sonnet 4.5, 6 of 11 from GPT-4.1). Each failure traces to
a line in the old prompt (v3):

| Failure | Count | Cause |
|---|---|---|
| Rule 4: lab results mentioned | 3 of 5 weeks with labs | The prompt said to reference "any new lab results". |
| Rule 4: HR, HRV or weight quoted | 4 | The prompt said to reference "heart rate, HRV, weight". |
| Rule 1: advice about reported pain | **5 of 9** pain weeks | "Give them a helpful tip so they can keep training": shin splints, ice, braces, treadmill swaps. |
| Rule 2: weight pressure | 7, including 3 of 18 `avoid_weight_talk` members | Weight was in the input and the flag never mentioned: "be at 220 by Halloween", "you look trimmer". |
| Rule 3: voice | 7 | "Upbeat and motivating!" led to hype; "keep them accountable" to guilt ("no excuses"). |
| Outside the guidebook | 5 | Missed workouts called done, wrong sleep figures, invented classes, **a draft signed by the wrong coach**. Cause: raw JSON with no done/missed framing and no coach first name. |

The guidebook misses two risks. Conditions such as asthma appear only in member notes, not in `injuries`, so the
code reads member text. Member text can also carry prompt injection or distress, and both are flagged.

## 3. Feature shape: a fixed workflow, not an agent

1. **Strip in code** what the model must not quote: labs, HR and HRV values (replaced by trend words) and weight.
   Render the week as plain facts: weekday, done or missed, the coach's first name, a "health issue reported"
   line. Member and coach text is quoted as data, with health numbers removed.
2. **Generate** with a prompt that states the guidebook.
3. **Run the code checks.** If something fixable fails, make **one repair call** naming the broken rules.
4. **Decide** with the code checks plus the judge.

Why not one prompt: Haiku on the old prompt broke a rule in **60 of 60** drafts and quoted a biomarker or lab in
every one. Wording can't reliably stop a model quoting data it was given; removing the data can. I didn't run the
new prompt on raw input, so this rests on the old prompt's failure. The repair call changes little (blocks fell
from 2–3% to under 1%), so in practice this is one model call with code before and after. Why not an agent: the
steps are fixed, so an agent would add cost, latency and new ways for member text to steer it, with nothing to
decide.

## 4. Guardrail policy

- **Block** (code only, so it is reproducible): a quoted biomarker or lab mention, weight talk under
  `avoid_weight_talk`, a weight target, a diagnosis, a treatment or training advice about a reported pain, a
  sign-off from someone other than this member's coach, an empty draft, no draft produced, and an unreadable
  trace. The coach sees why and regenerates or rewrites.
- **Flag** (up to three one-line reasons): judge findings, pain without "I'll reach out", guilt, hype, length,
  emoji, bot voice, nothing specific, figures or days the data contradicts, distress, injection, a draft that talks
  about its own review, look-alike letters from another alphabet, and any judge failure. A judge-only "other"
  finding stands only if Sonnet (`claude-sonnet-5-5`) agrees or the Sonnet call fails.
- **Pass:** nothing found.

**Expected flag rate: about 7% on familiar inputs and 10–17% on unseen ones, with almost no blocks.**
- **Familiar:** 2 to 6 of 60 drafts per run (44 of 600), across 8 v4 and 2 v5 generations on the production
  inputs, with 0 blocks. The checks' false-positive fixes were tuned on these inputs.
- **Unseen:** v5 on the 30 rehearsal traces flagged 5 (17%), and a second run after the input quoting change
  flagged 3 (10%), with no blocks (`results/v5/`). Two runs can't separate that change from variance.
- **What the flags are:** of the 44, 23 carry a judge Rule 1 finding (how a reported pain was handled), 12 a judge
  data contradiction, 5 a calendar mismatch, and the rest code figure checks.

Coaches should keep reading at these rates, because each reason names what to check. But precision is modest:
about 1 flag in 3 is a real violation on v5 drafts (section 5). Raising it is the first next step.

Why Sonnet confirmation: in a reviewed sample of 30 new v4 drafts, 4 of 5 flags were judge-only "other" findings
on clean drafts. Confirmation cuts false flags without letting any labeled violation through; dropping those
findings outright would let 3 pass. It costs under $0.10 per 60 traces.

| Set | Clean drafts flagged: Haiku only → + Sonnet confirm | Violations passed |
|---|---|---|
| Production 60 | 6 → 3 | 0 → 0 |
| Challenge 40 | 3 → 1 | 0 → 0 |
| New-draft sample 30 | 4 → 1 (borderline) | 0 → 0 |

## 5. Results: before and after

The same 60 inputs, checks and Haiku judge, every row scored with Sonnet confirmation. The counts are what the
evals report: for the production drafts, 28 flagged or blocked is the 25 labeled violations from section 2, all
caught, plus 3 clean drafts flagged (t_037, t_041, t_051).

| Version | Flagged or blocked | R1 | R2 | R3 | R4 | Other | Pass / flag / block |
|---|---|---|---|---|---|---|---|
| Before: production drafts (prompt v3) | 28 | 9 | 6 | 7 | 7 | 8 | 32 / 11 / 17 |
| Old prompt v3 on Haiku | 60 | 16 | 4 | 21 | 60 | 16 | 0 / 0 / 60 |
| **New workflow on Haiku (prompt v4), 3 runs** | **2, 4, 3** | 0, 2, 2 | 1, 1, 0 | 0 | 0 | 1, 1, 1 | 58 / 2 / 0, 56 / 4 / 0, 57 / 3 / 0 |
| Prompt v5 (shipped), 2 runs | 6, 4 | 4, 1 | 0 | 0 | 0 | 2, 3 | 54 / 6 / 0, 56 / 4 / 0 |

v5 changes one line: the model leaves lab requests out entirely instead of saying it can't discuss them. On the
rehearsal trace that asks for cholesterol numbers, v4's draft was blocked for "I'm not able to discuss test
results"; v5's isn't. Otherwise v5 is within v4's run-to-run range. Every new draft names something specific, and
mean length went from 78 to 86 words.

**Measured on v5 drafts** (`data/v5_sample.jsonl`: all 7 drafts flagged in one production run plus 23 random
passes, labeled blind and reviewed by me). 3 drafts break a rule, all subtly:
- **Caught:** t_038 praises training through a pulled muscle; t_022 says a ride cut short was finished.
- **Missed:** t_058 calls a PT visit that already happened upcoming.
- **Flag precision:** blind, 2 of 7 flags were real, 3 borderline and 2 false. Two generic code fixes ("your
  7-hour goal" read as a sleep figure, "skipping Tuesday's class" read as a missed workout called done) removed
  one false flag: 2 real, 3 borderline, 1 false of 6, in-sample. The false flag and two borderline ones are judge
  Rule 1 calls on drafts that handled the issue correctly.
- **Miss rate:** 1 miss in 23 random passes suggests about 2 subtle misses per 60 drafts, all flag-level "other"
  errors. No draft quoted a biomarker or lab.

## 6. Next steps, in priority order

1. Raise flag precision: extend Sonnet confirmation to judge-only Rule 1 findings, the largest flag group. Then
   track flag rate and precision per coach in production.
2. Grow the blind sets with real coach edits as labels, refreshed each quarter so the checks don't overfit.
3. Extract a structured "health issue" field from member text, so the coach-contact rule doesn't depend on
   vocabulary. Code alone still misses paraphrased advice and guilt (r_007, r_024); the judge catches them.
4. Move Rule 2 judging to Sonnet if more labels confirm Haiku's two production misses (t_008, t_048).
5. Have a person sign off `vocab.toml`, which is still marked as a model draft.
6. Tell members their summaries are drafted with AI and approved by their coach.

## 7. AI use

I used **Claude Code** (Opus 5.5) as the coding agent for nearly all of the implementation: vocabulary, checks,
judge, pipeline, tests, CI and these numbers. The feature and judges run on **Claude Haiku 5.5**; **Claude Sonnet
5.5** is the confirmation and cross-check judge. Separate Claude agents that never saw the checks wrote the
challenge and rehearsal sets and their labels, and I reviewed every label set. Nobody verified independently:
`vocab.toml` (reviewed only through its effect on the labeled sets), the synthetic blind drafts, and the spend
figures (from the code's own price table).

**Where I didn't trust the output:** the code checks scored almost perfectly on the 60 drafts, and that was the
warning sign, because they had been written while reading those drafts. I had an agent that never saw the checks
write a blind set. Code alone let 10 of its 30 violations through. That is why the judge exists and why the checks
are frozen against that set. Where the pipeline disagreed with an agent label (7 production rows, 2 rehearsal
rows), the label was checked against the workout dates before my review.

**Scope:** this went well past the 3-hour box, at about 6 hours of agent-assisted work in the commit history, by
choice, to build the fullest version. I also edited `ASSESSMENT.md` once, changing "GitHub repo" to "GitLab repo"
to match where this is hosted.
