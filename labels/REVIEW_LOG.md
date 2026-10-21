# Label review log

Who labeled each set, and when and how a person reviewed it. Every set was first labeled by an agent: Claude for
the production set, and separate blind agents (which never saw the checks or the pipeline's decisions) for the
others. Paawan then checked each set against `labels/RUBRIC.md`, to the depth in the How column, using the review
sheets in the project's shared folder. A review that changed a label is recorded in that row's `notes`.

| Set | Rows | Labeled by | Reviewed by | Reviewed (UTC) | How |
|---|---|---|---|---|---|
| `labels/labels.jsonl` (production) | 60 | Claude (pre-fill) | Paawan | 2026-10-20 15:01 | `labels/REVIEW.md` part 1. Quick read of parts 1 and 2 together (about 3 minutes for 100 rows), accepted with no changes |
| `data/challenge_labels.jsonl` | 40 | blind agent | Paawan | 2026-10-20 15:01 | `labels/REVIEW.md` part 2. Quick read together with part 1, accepted with no changes |
| `data/after_sample_labels.jsonl` (v4 drafts) | 30 | blind agent | Paawan | 2026-10-20 16:40 | `AFTER_SAMPLE_REVIEW.md`. Spot-checked 3 of 30 rows, accepted with no changes; the other 27 were not reviewed |
| `data/rehearsal_labels.jsonl` | 30 | blind agent | Paawan | 2026-10-20 21:29 | Accepted with no changes. 2 rows (r_013, r_019) had already been corrected against the workout dates, before review |
| `data/v5_sample_labels.jsonl` (v5 drafts) | 30 | blind agent | Paawan | 2026-10-20 21:29 | `V5_SAMPLE_REVIEW.md`. Accepted with no changes |

Separately, at 15:16 on 2026-10-20, 7 labels were corrected: 6 in the challenge set (c_007, c_010, c_018, c_022,
c_023, c_035) and 1 in production (t_053). Both judges had flagged these drafts, and the workout dates showed the
label was wrong. Paawan approved the change at 15:15, after the 15:01 acceptance of both sets. Each correction is
recorded in that row's `notes`. Because the judges prompted these corrections, the challenge set's "other"
agreement figures are partly in-sample.
