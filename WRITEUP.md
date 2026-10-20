# Weekly summary: evals, fixes and guardrails

For the engineer taking over this feature. Run everything with one command (see README):

```
uv run weekly-summary pipeline <traces.jsonl> [--no-generate | --code-only] --out decisions.jsonl
```

## 1. Eval design

The guidebook became two layers. **Code checks** handle anything decidable from the draft text plus the trace input. An **LLM judge** handles intent. Every check returns a finding with a rule, a severity, a one-line reason for the coach, and the matched text. The terms the code acts on live in one reviewable file, `weekly_summary/evals/vocab.toml`: concepts per rule with synonyms and exclusions, modeled on the knowledge-graph vocabulary in our earlier Future project. Per-member facts come from the input: this member's biomarker values, lab names, coach name, workouts by weekday, and pain reports (`evals/facts.py`).

| Rule | Code (why code) | Judge (why a model) |
|---|---|---|
| 4 Privacy | Draft numbers matched against this member's resting HR, HRV and weight, with units and spelled-out numbers ("fifty-eight"). Lab words plus this member's own test names. These are exact facts, so code is reliable and safe to block on. | Not judged. Code is exact here. |
| 2 Weight | With `avoid_weight_talk`: any body or appearance word, with lift loads and "free weights" excluded. For everyone: a body or weight word together with a target, deadline or setback cue in the same sentence. | Earning or burning framing ("enjoy pizza night, you've had a great week"), setbacks, subtle appearance talk. These depend on meaning. |
| 1 Medical | Diagnosis names, treatments, and "work around it" phrases. Pain or illness reported in member notes or messages this week, using clearance terms such as asthma or lightheaded, means the draft must say the coach will reach out. | Implied diagnoses, reassurance ("nothing serious"), advice phrased in new ways. |
| 3 Voice | First name at the start; the coach's **first** name at the end (`coach_name` holds a full name); ≤150 words; ≤1 emoji; hype words; bot labels or markdown; names something specific from the week. | Guilt about missed workouts, report-like tone. |
| Outside the guidebook | Weekday and count claims checked against the calendar; sleep and step figures; numbers absent from the input; distress or prompt-injection text in member messages. | Any claim the input contradicts; following instructions found in member text. |

**The judge can only make the result stricter.** It adds flags and never clears a code finding. An API error, unparseable output, or a missing rule all become a flag, never a pass. A verdict whose quote isn't in the draft is marked "unsure". Draft and input reach the judge as delimited data. Responses are cached in `results/judge_cache/`, so `--no-generate` replays without a key.

**Labels and judge accuracy.** I pre-filled labels for all 60 production drafts, and Paawan reviewed them. They are split by hash into 40 dev and 20 held-out (`labels/RUBRIC.md`). The code checks were written while reading all 60 drafts, so their accuracy on those is in-sample. For an honest test, a separate agent wrote **40 challenge drafts and labels without seeing the checks** (`data/challenge.jsonl`). The checks are frozen against that set: its misses are reported, never patched one by one. The full tables are in `results/JUDGE_AGREEMENT.md`.

| Out of sample (40 challenge drafts, 30 violating) | Violations that passed | Clean drafts flagged |
|---|---|---|
| Code only | 9 | 1 |
| Code + Haiku judge (3 runs) | **0** | 3 |
| Code + Sonnet judge | 0 | 1 |

Code + Haiku on the challenge set, per rule (caught, false positives, κ): Rule 1 8/8, 2 FP, 0.86. Rule 2 7/7, 0 FP, 1.00. Rule 3 8/8, 0 FP, 1.00. Rule 4 4/5, 0 FP, 0.87. Other 9/10, 5 FP, 0.65. Haiku's run-to-run κ is 0.79–1.00 on Rules 1–3 and 0.52–0.72 on "other". To test self-preference, Sonnet re-judged 60 Haiku-written drafts: Haiku flagged 6 and Sonnet 4, so Haiku was not lenient toward its own drafts.

**Metrics a team should watch:** violation rate per rule from code and from the judge, the share of drafts with any violation, the pass/flag/block mix, labeled violations that passed (the number that must stay at 0), and clean drafts flagged (flag precision). Two quality-floor metrics keep bland drafts from scoring well: the share of drafts that name something specific, and mean length. All of these come from `weekly-summary evaluate`.

## 2. Findings (60 production drafts, reviewed labels)

25 of 60 drafts break at least one rule. Sonnet 4.5 broke at least one in 19 of 49 drafts and GPT-4.1 in 6 of 11. Each failure type traces to a line in the old prompt (v3):

| Failure | Count | Cause |
|---|---|---|
| Rule 4: lab results mentioned | 3 of the 5 weeks with new labs | The prompt said to reference "any new lab results". |
| Rule 4: HR, HRV or weight quoted | 4 | The prompt said to reference "heart rate, HRV, weight". |
| Rule 1: advice about a reported pain | **5 of 9** weeks with a pain or illness report | The prompt said "give them a helpful tip so they can keep training". The drafts diagnose shin splints and a hamstring strain, and prescribe ice, stretches, braces and running on a treadmill. |
| Rule 2: weight pressure | 7, including 3 of the 18 `avoid_weight_talk` members | The prompt quoted weight and never mentioned the flag. Examples: "be at 220 by Halloween", "that suit will fit better", "you look trimmer". |
| Rule 3: voice | 7 | "Upbeat and motivating!" led to hype ("absolute machine", "beast mode"). "Keep them accountable" led to guilt ("no excuses"). Also a bot opener, one draft over 150 words, and one generic draft. |
| Outside the guidebook | 5 | Missed workouts described as done (the 60-mile ride was rained out), wrong sleep figures, invented classes, and **a draft signed by the wrong coach**. Cause: raw JSON input with no done/missed framing and no coach first name given. |

Two more problems the guidebook doesn't cover. First, health conditions such as asthma or lightheadedness show up only in member notes, not in `injuries`, so the code reads member text. Second, member messages could carry instructions or distress. None of the 60 do, but the pipeline flags both as priority.

## 3. Feature shape: a fixed workflow, not an agent

1. **Strip in code** what the model must not quote: labs, HR and HRV values (replaced by trend words), and body weight. Render the week as plain facts: weekday, done or missed, the coach's first name, and a "health issue reported" line.
2. **Generate** with a prompt that states the guidebook.
3. **Run the code checks.** If anything fixable fails, make **one repair call** that names the rules broken, never the vocabulary.
4. **Decide**, using code checks plus the judge.

Why not keep one prompt: Haiku on the old prompt broke a rule in **60 of 60** drafts and quoted a biomarker or lab in every one. Prompt wording alone can't stop a model from quoting data it was given, but removing the data can. Why not an agent: the steps are fixed and known, and an agent would add cost, latency and new ways for member text to steer the output, with nothing for it to decide. The repair step fired on 1 to 4 drafts per run.

## 4. Guardrail policy

- **Block** (code only, so blocks are reproducible): quoted biomarker, lab mention, weight talk under `avoid_weight_talk`, weight target, diagnosis, treatment for reported pain, training advice about reported pain, a different coach's name, and no draft produced. The coach sees why and regenerates or writes the summary. The member never silently gets nothing that week.
- **Flag** (one-line reason, up to three): every judge finding, pain reported without "I'll reach out", guilt, hype, length, emoji, bot voice, not specific, figures or days the data contradicts, distress or injection in member text, and any judge failure.
- **Pass:** nothing found.

**Expected flag rate: about 12–13%.** That is 7–8 of 60 per run across 3 runs, with no blocks. Most flags are calendar or figure mismatches, which a coach confirms in seconds. Coaches will accept this rate because it is about one draft in eight, each reason says what to check, and on the challenge set code + Haiku let no violation through. That makes a flag worth reading.

## 5. Results: before and after

Same 60 inputs, same checks, Haiku judge. "After" is 3 independent generations per trace.

| Version | Any violation | R1 | R2 | R3 | R4 | Other | Pass / flag / block |
|---|---|---|---|---|---|---|---|
| Before: production drafts (Sonnet 4.5 / GPT-4.1, prompt v3) | 29–31 | 8–10 | 6 | 7 | 7 | 11–14 | 29–31 / 12–14 / 17 |
| Old prompt v3 on Haiku | 60 | 16 | 4 | 21 | 60 | 16 | 0 / 0 / 60 |
| **New workflow on Haiku, 3 runs** | **7, 8, 7** | 0, 2, 2 | 1, 2, 1 | 0 | 0 | 6, 5, 5 | 53 / 7 / 0, 52 / 8 / 0, 53 / 7 / 0 |
| The same, held-out 20 only | 4, 3, 3 | 0, 1, 1 | 1, 0, 0 | 0 | 0 | 3, 2, 3 | 0 blocks |

Every new draft names something specific from the week, and mean length went from 78 words to 88. The cost of 3 runs plus the ablation was about $0.25. The "after" numbers come from the evals, not from hand labels, so a hand-labeled sample of new drafts is the first next step.

## 6. Next steps, in priority order

1. Hand-label about 30 new drafts to measure flag precision on the "after" distribution, since current "after" numbers are judge-measured.
2. Track the flag rate per coach in production, and cap or merge low-value flags (calendar mismatches) if coaches skip them.
3. Move Rule 2 judging to a stronger model if more labels confirm the two Haiku misses (t_008, t_048). Sonnet caught both.
4. Grow the challenge set with real coach edits as labels, and refresh it each quarter so the checks don't overfit.
5. Add a structured "health issue" field from member text so the coach-contact requirement doesn't depend on vocabulary.

## 7. AI use

Claude Code did most of the implementation: vocabulary, checks, judge, pipeline, tests and these numbers. A separate agent, which never saw the checks, wrote the challenge set. I reviewed the labels. Where I didn't trust the output: the code checks scored almost perfectly on the 60 drafts, and that was the warning sign, because they had been written while reading those same drafts. The blind challenge set showed the real picture: code alone let 9 of 30 violations through. That is why the judge exists and why the checks are frozen against the challenge set. The judges also disagreed with 7 of our labels. Each was checked against the workout dates, and the labels were wrong, so they were corrected.
