# Judge agreement (judge j1, prompt v4, 2026-10-20)

Labels: `labels/labels.jsonl` (60 production drafts) and `data/challenge_labels.jsonl` (40 blind challenge
drafts), reviewed and accepted by Paawan on 2026-10-20. After the cross-check below, Paawan approved relabeling 7
drafts as "other" violations (wrong weekday or workout count); the tables use the corrected labels. Judge: `claude-haiku-5-5`, run three
times per draft under separate cache keys (`--judge-repeat`), because these models reject temperature 0.
Cross-check judge: `claude-sonnet-5-5`, once per draft. Borderline label cells are not scored (RUBRIC.md).
The judge does not judge Rule 4 by design (code does), so its Rule 4 recall is 0 in the judge-alone tables.

Total API spend for everything below: about $1.95 (Haiku $0.27, Sonnet $1.66), measured from response usage.

## Summary

- **The judge earns its place out of sample.** On the blind challenge set, code alone let 13 of 30 (8 with the current checks; see `results/challenge/report_code_only.json`) violating
  drafts pass. Code plus the Haiku judge let 0 pass, in all three runs.
- **Rules 1 and 2 are where the judge is strong.** On the challenge set Haiku caught 8/8 Rule 1 and 7/7 Rule 2
  violations with κ 0.86 and 1.00. On the 60 production drafts it caught 5/5 Rule 1 but only 5/7 Rule 2.
  The two Rule 2 misses are the same drafts in every run: t_008 (dev) and t_048 (held-out, pizza as a reward).
  Sonnet catches both.
- **Rule 3 recall from the judge is low (2-4 of 7-8), but code covers Rule 3.** Combined Rule 3 recall is 7/7 and
  8/8. That is the intended split: code checks voice, names and length, and the judge only adds guilt and
  specificity.
- **"Other" is the noisiest rule, and the judges found label errors there.** Both judges independently flagged
  weekday and count mistakes in 7 drafts the labels called clean. I checked each against the input dates:
  c_007 says rowing was Tuesday (Wednesday 09-16), c_010 says Monday and Wednesday (Tuesday 09-15, Thursday
  09-17), c_018 says Tuesday (Wednesday 09-16), c_022 says Thursday (Friday 09-18), c_023 says two spin classes
  (one was missed), c_035 says Saturday (Sunday 09-20), and t_053 (dev) mentions three core classes that aren't in
  the week. Paawan approved relabeling all 7. With the corrected labels, Haiku's "other" recall on the challenge
  set is 8-9 of 10 with precision 0.53-0.67, and Sonnet's is 9/10 at 0.90. Haiku is also the least stable on
  this rule from run to run (κ 0.52-0.72, against 0.79-1.00 for Rules 1-3). Clean drafts flagged or blocked:
  4-6 of 35 production drafts and 3 of 10 challenge drafts for Haiku, versus 2 and 1 for Sonnet. Held-out
  "other" findings were not read, to keep that split clean.
- **No self-grading leniency.** On 60 drafts Haiku wrote with prompt v4, Haiku's judge flagged 6 and Sonnet 4.
  On drafts Haiku didn't write, the ratio was similar (production 27 vs 22, challenge 27 vs 25). If anything,
  Haiku is the stricter judge, on its own output too.
- **Judge reliability:** 0 judge failures in 520 calls. Every judge verdict quoted text that is in the draft.

## Agreement with the labels

Each cell: caught / labeled, false positives, precision, recall, Cohen's κ.

**Judge alone vs labels, dev (40)**

| Rule | Haiku run 1 | Haiku run 2 | Haiku run 3 | Sonnet |
|---|---|---|---|---|
| rule1 | 2/2, 0 FP, P 1.00, R 1.00, κ 1.00 | 2/2, 0 FP, P 1.00, R 1.00, κ 1.00 | 2/2, 0 FP, P 1.00, R 1.00, κ 1.00 | 2/2, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule2 | 3/4, 0 FP, P 1.00, R 0.75, κ 0.84 | 3/4, 0 FP, P 1.00, R 0.75, κ 0.84 | 3/4, 0 FP, P 1.00, R 0.75, κ 0.84 | 4/4, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule3 | 2/6, 0 FP, P 1.00, R 0.33, κ 0.46 | 2/6, 0 FP, P 1.00, R 0.33, κ 0.46 | 2/6, 0 FP, P 1.00, R 0.33, κ 0.46 | 3/6, 0 FP, P 1.00, R 0.50, κ 0.63 |
| rule4 | 0/4, 0 FP, P –, R 0.00, κ 0.00 | 0/4, 0 FP, P –, R 0.00, κ 0.00 | 0/4, 0 FP, P –, R 0.00, κ 0.00 | 0/4, 0 FP, P –, R 0.00, κ 0.00 |
| other | 4/4, 4 FP, P 0.50, R 1.00, κ 0.62 | 4/4, 1 FP, P 0.80, R 1.00, κ 0.87 | 4/4, 2 FP, P 0.67, R 1.00, κ 0.77 | 3/4, 1 FP, P 0.75, R 0.75, κ 0.72 |

**Code + judge vs labels, dev (40)**

| Rule | Code only | Code + Haiku | Code + Sonnet |
|---|---|---|---|
| rule1 | 2/2, 0 FP, P 1.00, R 1.00, κ 1.00 | 2/2, 0 FP, P 1.00, R 1.00, κ 1.00 | 2/2, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule2 | 4/4, 0 FP, P 1.00, R 1.00, κ 1.00 | 4/4, 0 FP, P 1.00, R 1.00, κ 1.00 | 4/4, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule3 | 6/6, 0 FP, P 1.00, R 1.00, κ 1.00 | 6/6, 0 FP, P 1.00, R 1.00, κ 1.00 | 6/6, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule4 | 4/4, 0 FP, P 1.00, R 1.00, κ 1.00 | 4/4, 0 FP, P 1.00, R 1.00, κ 1.00 | 4/4, 0 FP, P 1.00, R 1.00, κ 1.00 |
| other | 2/4, 1 FP, P 0.67, R 0.50, κ 0.53 | 4/4, 5 FP, P 0.44, R 1.00, κ 0.55 | 3/4, 2 FP, P 0.60, R 0.75, κ 0.63 |

**Judge alone vs labels, held-out (20)**

| Rule | Haiku run 1 | Haiku run 2 | Haiku run 3 | Sonnet |
|---|---|---|---|---|
| rule1 | 3/3, 1 FP, P 0.75, R 1.00, κ 0.82 | 3/3, 0 FP, P 1.00, R 1.00, κ 1.00 | 3/3, 2 FP, P 0.60, R 1.00, κ 0.68 | 3/3, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule2 | 2/3, 0 FP, P 1.00, R 0.67, κ 0.77 | 2/3, 0 FP, P 1.00, R 0.67, κ 0.77 | 2/3, 0 FP, P 1.00, R 0.67, κ 0.77 | 3/3, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule3 | 0/1, 0 FP, P –, R 0.00, κ 0.00 | 0/1, 0 FP, P –, R 0.00, κ 0.00 | 1/1, 0 FP, P 1.00, R 1.00, κ 1.00 | 0/1, 0 FP, P –, R 0.00, κ 0.00 |
| rule4 | 0/3, 0 FP, P –, R 0.00, κ 0.00 | 0/3, 0 FP, P –, R 0.00, κ 0.00 | 0/3, 0 FP, P –, R 0.00, κ 0.00 | 0/3, 0 FP, P –, R 0.00, κ 0.00 |
| other | 1/1, 4 FP, P 0.20, R 1.00, κ 0.27 | 1/1, 6 FP, P 0.14, R 1.00, κ 0.18 | 1/1, 3 FP, P 0.25, R 1.00, κ 0.35 | 1/1, 5 FP, P 0.17, R 1.00, κ 0.22 |

**Code + judge vs labels, held-out (20)**

| Rule | Code only | Code + Haiku | Code + Sonnet |
|---|---|---|---|
| rule1 | 3/3, 0 FP, P 1.00, R 1.00, κ 1.00 | 3/3, 1 FP, P 0.75, R 1.00, κ 0.82 | 3/3, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule2 | 2/3, 0 FP, P 1.00, R 0.67, κ 0.77 | 2/3, 0 FP, P 1.00, R 0.67, κ 0.77 | 3/3, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule3 | 1/1, 0 FP, P 1.00, R 1.00, κ 1.00 | 1/1, 0 FP, P 1.00, R 1.00, κ 1.00 | 1/1, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule4 | 3/3, 0 FP, P 1.00, R 1.00, κ 1.00 | 3/3, 0 FP, P 1.00, R 1.00, κ 1.00 | 3/3, 0 FP, P 1.00, R 1.00, κ 1.00 |
| other | 1/1, 0 FP, P 1.00, R 1.00, κ 1.00 | 1/1, 4 FP, P 0.20, R 1.00, κ 0.27 | 1/1, 5 FP, P 0.17, R 1.00, κ 0.22 |

**Decisions, original**

| Run | Pass | Flag | Block | Labeled violations passed | Clean drafts flagged or blocked |
|---|---|---|---|---|---|
| Code only | 36 | 7 | 17 | 1 ['t_048'] | 0 |
| Code + Haiku (run 1) | 29 | 14 | 17 | 0  | 6 |
| Code + Haiku (run 2) | 31 | 12 | 17 | 0  | 4 |
| Code + Haiku (run 3) | 30 | 13 | 17 | 0  | 5 |
| Code + Sonnet | 33 | 10 | 17 | 0  | 2 |

**Judge alone vs labels, challenge (40)**

| Rule | Haiku run 1 | Haiku run 2 | Haiku run 3 | Sonnet |
|---|---|---|---|---|
| rule1 | 8/8, 2 FP, P 0.80, R 1.00, κ 0.86 | 8/8, 2 FP, P 0.80, R 1.00, κ 0.86 | 8/8, 2 FP, P 0.80, R 1.00, κ 0.86 | 8/8, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule2 | 7/7, 0 FP, P 1.00, R 1.00, κ 1.00 | 7/7, 0 FP, P 1.00, R 1.00, κ 1.00 | 7/7, 0 FP, P 1.00, R 1.00, κ 1.00 | 7/7, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule3 | 3/8, 0 FP, P 1.00, R 0.38, κ 0.49 | 3/8, 0 FP, P 1.00, R 0.38, κ 0.49 | 4/8, 0 FP, P 1.00, R 0.50, κ 0.61 | 3/8, 0 FP, P 1.00, R 0.38, κ 0.49 |
| rule4 | 0/5, 0 FP, P –, R 0.00, κ 0.00 | 0/5, 0 FP, P –, R 0.00, κ 0.00 | 0/5, 0 FP, P –, R 0.00, κ 0.00 | 0/5, 0 FP, P –, R 0.00, κ 0.00 |
| other | 8/10, 4 FP, P 0.67, R 0.80, κ 0.63 | 8/10, 7 FP, P 0.53, R 0.80, κ 0.49 | 9/10, 7 FP, P 0.56, R 0.90, κ 0.56 | 9/10, 1 FP, P 0.90, R 0.90, κ 0.87 |

**Code + judge vs labels, challenge (40)**

| Rule | Code only | Code + Haiku | Code + Sonnet |
|---|---|---|---|
| rule1 | 4/8, 0 FP, P 1.00, R 0.50, κ 0.62 | 8/8, 2 FP, P 0.80, R 1.00, κ 0.86 | 8/8, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule2 | 4/7, 0 FP, P 1.00, R 0.57, κ 0.69 | 7/7, 0 FP, P 1.00, R 1.00, κ 1.00 | 7/7, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule3 | 7/8, 0 FP, P 1.00, R 0.88, κ 0.92 | 8/8, 0 FP, P 1.00, R 1.00, κ 1.00 | 8/8, 0 FP, P 1.00, R 1.00, κ 1.00 |
| rule4 | 4/5, 0 FP, P 1.00, R 0.80, κ 0.87 | 4/5, 0 FP, P 1.00, R 0.80, κ 0.87 | 4/5, 0 FP, P 1.00, R 0.80, κ 0.87 |
| other | 0/10, 1 FP, P 0.00, R 0.00, κ -0.05 | 8/10, 5 FP, P 0.62, R 0.80, κ 0.58 | 9/10, 2 FP, P 0.82, R 0.90, κ 0.81 |

**Decisions, challenge**

| Run | Pass | Flag | Block | Labeled violations passed | Clean drafts flagged or blocked |
|---|---|---|---|---|---|
| Code only | 22 | 10 | 8 | 13 ['c_007', 'c_010', 'c_014', 'c_015', 'c_016', 'c_019', 'c_023', 'c_024', 'c_025', 'c_028', 'c_038', 'c_039', 'c_040'] | 1 |
| Code + Haiku (run 1) | 7 | 25 | 8 | 0  | 3 |
| Code + Haiku (run 2) | 7 | 25 | 8 | 0  | 3 |
| Code + Haiku (run 3) | 7 | 25 | 8 | 0  | 3 |
| Code + Sonnet | 9 | 23 | 8 | 0  | 1 |


## Judge against judge

Run-to-run stability (Haiku run 1 against runs 2 and 3), κ per rule:

| Set | Rule 1 | Rule 2 | Rule 3 | Other |
|---|---|---|---|---|
| Production (60) | 0.93, 0.94 | 1.00, 1.00 | 1.00, 0.79 | 0.65, 0.52 |
| Challenge (40) | 1.00, 1.00 | 1.00, 1.00 | 1.00, 0.87 | 0.72, 0.67 |

Haiku against Sonnet (flags from each, κ):

| Drafts | Rule 1 | Rule 2 | Rule 3 | Other | Any |
|---|---|---|---|---|---|
| Production (60, Sonnet 4.5 / GPT-4.1) | 6 vs 9, 0.77 | 7 vs 5, 0.82 | 3 vs 2, 0.79 | 10 vs 13, 0.52 | 22 vs 27 |
| Challenge (40, agent-written) | 8 vs 10, 0.86 | 7 vs 7, 1.00 | 4 vs 4, 1.00 | 10 vs 12, 0.75 | 25 vs 27 |
| Haiku-written, prompt v4 (60) | 3 vs 5, 0.73 | 0 vs 0 | 0 vs 0 | 1 vs 1, -0.02 | 4 vs 6 |

The Haiku-written drafts are unlabeled, so this table measures leniency, not accuracy. Their pipeline decisions
were 50 pass, 10 flag, 0 block (Haiku judge) and 52 pass, 8 flag, 0 block (Sonnet judge).

## What this suggests

1. Keep Haiku as the judge. It is about 15 times cheaper than Sonnet, catches every violation in combination
   with code, and shows no leniency toward its own drafts.
2. Rule 2 is the one place Sonnet did better (7/7 vs 5/7 on production drafts, same on the challenge set).
   Moving Rule 2 alone to Sonnet would cost about $0.01 per draft. With 2 misses this is a small-sample call.
3. The label misses above, and code alone missing 10 of 10 challenge "other" violations, are weekday and count claims. A deterministic check that
   matches "<weekday>" and "<n> <workout>" against the week's workouts would catch these exactly. That is a
   generic check, not a per-trace patch, so it doesn't break the challenge-set freeze.

## Reproduce

```
JUDGE_MODEL=claude-haiku-5-5 uv run weekly-summary pipeline data/traces.jsonl --no-generate --judge-repeat 0 \
  --out results/original/decisions_haiku_r0.jsonl --details results/original/details_haiku_r0.jsonl
uv run weekly-summary evaluate results/original/details_haiku_r0.jsonl --out results/original/report_haiku_r0.json
uv run weekly-summary crosscheck results/original/details_sonnet.jsonl results/original/details_haiku_r0.jsonl --names Sonnet Haiku
```

Judge responses are cached in `results/judge_cache/` by judge version, model, input, draft and repeat, so these
commands replay without an API key.
