# AI Engineering Take-Home: Harden a Weekly Summary Feature

**Time:** 3 hours, then a 1-hour live session. 

**Stack:** Python (you can change this). Use any LLM provider with your own API key.

---

## The situation

Future coaches send each member a weekly progress summary. An LLM writes the first draft from the member's week of data. The coach reads the draft, edits it if necessary, and approves it.

The feature is one prompt and one model call. See `weekly_summary/prompt.py`. The team wrote the prompt before the Coaching Content team published a messaging guidebook. See `GUIDEBOOK.md`. Nobody checked the feature against the guidebook.

Nobody filed bug reports. You get 60 recent production traces with no labels. Each trace holds the input that the model received and the draft that it wrote. Assume that some drafts break the guidebook and that coaches miss some of them.

## Your tasks

### 1. Build evals

Turn the guidebook into checks that you can run on any trace.

- Decide which checks are code and which checks need a model. Explain why for each rule.
- Label a sample of the traces yourself. If you use an LLM as a judge, measure how often it agrees with your labels.
- Report metrics that tell a team if a change made the feature better or worse.

### 2. Find the failures

Run your evals on the 60 traces.

- Report which rules fail, how often, and why. Trace each failure type to a cause.
- Look for failures that the guidebook does not name.

### 3. Fix the feature and add guardrails

Change the feature so that fewer drafts break the guidebook. Then add guardrails so that a bad draft does not reach a member unnoticed.

- Each draft ends with one decision: `pass`, `flag`, or `block`. A flag carries a reason that the coach reads in one glance. Decide where each line goes, and defend it. Coaches who see too many flags stop reading them.
- Decide if the feature stays a one-shot prompt, becomes a fixed workflow, or becomes a tool-calling agent. Defend the choice. "It stays one prompt" is an acceptable answer if you show why.
- Use your evals to show the result before and after your changes.

### 4. Write it up

Write `WRITEUP.md` for an engineer who takes over this feature. See "What to submit".

---

## What you get

All paths are relative to the starter repo.


| Path                         | What it is                                                                                    |
| ---------------------------- | --------------------------------------------------------------------------------------------- |
| `GUIDEBOOK.md`               | The four messaging rules. This is the spec.                                                   |
| `data/traces.jsonl`          | 60 production traces. Each line is one `Trace` from `weekly_summary/models.py`.               |
| `weekly_summary/prompt.py`   | The current one-shot prompt.                                                                  |
| `weekly_summary/generate.py` | The feature: one call to the LLM.                                                             |
| `weekly_summary/llm.py`      | A small client wrapper for Anthropic and OpenAI, plus a replay client. Change it as you need. |
| `weekly_summary/__main__.py` | A CLI to show a trace, generate one summary again, or run all traces.                         |


The replay client returns the recorded draft for a trace and makes no API call. Use it to build and test your evals without cost. Use a real provider when you test a change to the feature.

## Requirements

1. One command runs your full pipeline (feature, evals, and guardrails) on a traces file given by path. Put the command in your README.
2. The command writes one JSON line per trace in this shape:

   ```json
   {"trace_id": "t_001", "decision": "flag", "reasons": ["Quotes a resting heart rate value (Rule 4)."]}
   ```

3. The command has a mode that does not generate new drafts. In this mode, it applies your evals and guardrails to the drafts in the traces file. We use it to test your guardrails on the original drafts.
4. Commit your labels and your eval results.
5. Use only the synthetic data in this repo. Do not use real member data.

In the live session, we run your command on traces that you have not seen. Build for traces you have not seen, not only for these 60.

## What to submit

A GitHub repo (private is fine) with your code and `WRITEUP.md`. The write-up covers:

- **Eval design.** Each check, what it measures, and why it is code or a model. How you measured the accuracy of any LLM judge.
- **Findings.** What fails, how often, and the cause. Include anything outside the guidebook.
- **Feature shape.** One-shot, workflow, or agent, and why.
- **Guardrail policy.** What passes, what goes to the coach as a flag, and what you block. What you expect the flag rate to be, and why coaches will accept it.
- **Results.** Before and after numbers from your evals.
- **Next steps.** What you would do with another week, in priority order.
- **AI use.** How you used coding agents, and one place where you did not trust their output.

Keep the write-up short. A reader must finish it in 10 minutes.

## The live session

After internal evaluation of your submission, we may perform a live review session. The live session is 60 minutes. Have your environment ready with a working API key.