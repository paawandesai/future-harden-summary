# Label review log

Who labeled each set, and when and how a person reviewed it. Every set was first labeled by an agent: Claude for
the production set, and separate blind agents (which never saw the checks or the pipeline's decisions) for the
others. Paawan then reviewed each set against `labels/RUBRIC.md`, using the review sheets in the project's shared
folder. A review that changed a label is recorded in that row's `notes`.

| Set | Rows | Labeled by | Reviewed by | Reviewed (UTC) | How |
|---|---|---|---|---|---|
| `labels/labels.jsonl` (production) | 60 | Claude (pre-fill) | Paawan | 2026-10-20 15:01 | `labels/REVIEW.md` part 1. Accepted with no changes |
| `data/challenge_labels.jsonl` | 40 | blind agent | Paawan | 2026-10-20 15:01 | `labels/REVIEW.md` part 2. Accepted with no changes |
| `data/after_sample_labels.jsonl` (v4 drafts) | 30 | blind agent | Paawan | 2026-10-20 16:40 | `AFTER_SAMPLE_REVIEW.md`. Accepted with no changes |
| `data/rehearsal_labels.jsonl` | 30 | blind agent | Paawan | 2026-10-20 21:29 | Accepted with no changes. 2 rows (r_013, r_019) had already been corrected against the workout dates, before review |
| `data/v5_sample_labels.jsonl` (v5 drafts) | 30 | blind agent | Paawan | 2026-10-20 21:29 | `V5_SAMPLE_REVIEW.md`. Accepted with no changes |

Separately, 7 production labels were corrected when the judges disagreed with them and the workout dates showed the
label was wrong. Each correction is recorded in that row's `notes`, and Paawan's review came after it.
