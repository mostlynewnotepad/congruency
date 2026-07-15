# Local Qwen-Coder Pair vs the Claude Baseline — Capstone Measurement (#180)

**Ticket:** #180 (test). Capstone of the local-agent-stack effort (#173 role→model fit, #175
structured-output reliability, #176 the `ollama_agent.py` adapter).
**Date:** 2026-07-15
**Status:** **MEASURED** (live against local Ollama on this host; all required models present).
**Question:** Can a LOCAL model pair (Ollama adapter) actually produce a working, self-tested code
deliverable, or is Claude still required?

## Verdict

**LOCAL-WITH-CAVEATS.** On small, self-contained, single-function build units the local **worker
(qwen2.5-coder:7b) is fully capable** — 3/3 correct, 3/3 valid structured output, every task in a
single round, sub-5s. That matches the Claude baseline (3/3) on these tasks. **But the local
adversary (gemma3:27b) cannot be the sole gate:** it caught 3/3 planted bugs yet *stably*
false-rejected one correct solution (a correct regex `parse_log_line`) with a technically-false
finding. So a local pair can settle a small build unit **only when a deterministic, runnable
self-test (oracle) is the authority** — the local judge is a useful second opinion, not a
trustworthy final say. Multi-file / repo-wide worker tasks, and any gate that has no runnable
oracle, still route to Claude.

## Method (MEASURED unless noted)

- Confirmed models via `curl http://localhost:11434/api/tags`: **qwen2.5-coder:7b, qwen3-coder:latest
  (30.5B), gemma3:27b** all installed (plus gemma3:4b, llama3.2). Nothing missing → measurable.
- Drove the LOCAL worker via Ollama `/api/chat` using the **same contract `ollama_agent.py` uses**:
  `temperature=0.3`, explicit `num_ctx=8192`, JSON-Schema-constrained `format`, and
  extract→validate→retry (≤2 retries) — the R4 wrapper. Role→model defaults per `role_model_fit.md`:
  worker=qwen2.5-coder:7b, adversary=gemma3:27b. (Direct `/api/chat` per the ticket's permitted path;
  the adapter's agent-mode file-writing loop was not needed to answer the correctness question.)
- **3 small, self-contained, objectively-checkable tasks**, each with a runnable pass/fail oracle:
  (a) `roman_to_int(s)`; (b) `parse_log_line(line)` (fixed `date time [LEVEL] message` format);
  (c) `run_length_encode(s)`. Worker output is `ast.parse`d then run against concrete asserts in a
  subprocess.
- **Claude baseline:** I wrote a reference solution per task and ran it against the same oracle — all
  3 pass (MEASURED that the oracle is sound and the baseline is 3/3). What Claude's *worker* would
  emit on these crisp specs is REASONED to match (these are exactly the "small self-contained
  function" shape #173 measured Claude-class models at 100%).
- **Adversary:** gave gemma3:27b, for each task, one correct and one deliberately-buggy solution
  under the adversary envelope schema; scored bug-catch (bad→fail) and false-positive (good→pass).
- Bench script: `scratchpad/pairbench.py` (reproducible). No tool code was modified.

## Per-task results (MEASURED)

| Task | Local valid-output | Local correct | Rounds | Local latency | Claude baseline | Notes |
|---|---|---|---|---|---|---|
| roman_to_int | yes | **PASS** | 1 | 5.0 s | PASS (ref, MEASURED) | subtractive notation handled (MCMXCIV=1994, CDXLIV=444). |
| parse_log_line | yes | **PASS** | 1 | 3.6 s | PASS (ref, MEASURED) | preserved spaces/brackets in message; not fooled by naive split. |
| run_length_encode | yes | **PASS** | 1 | 1.4 s | PASS (ref, MEASURED) | consecutive-run semantics correct incl. `''`→[] and `aabbaa`. |
| **Local worker total** | **3/3 (100%)** | **3/3 (100%)** | all 1st-try | median 3.6 s | **3/3** | worker = qwen2.5-coder:7b. |

**Local worker valid-structured-output rate: 3/3 (100%), zero retries needed.** Correctness unaided:
**3/3.** This reproduces #173 §3.2 (worker 5/5 on self-contained functions) on an independent task set.

## Adversary (gemma3:27b) — MEASURED

| Task | Good→verdict (want pass) | Bad→verdict (want fail) | Bug caught | False positive |
|---|---|---|---|---|
| roman_to_int | pass | fail | yes | no |
| parse_log_line | **fail** | fail | yes | **YES** |
| run_length_encode | pass | fail | yes | no |

- **Bug catch-rate: 3/3 (100%)** — flagged the always-add Roman bug, the naive-split log bug, and the
  `Counter`-merges-runs bug. The adversary genuinely catches bugs; it does not rubber-stamp.
- **False-positive rate: 1/3 (33%)** — it rejected a *correct* regex `parse_log_line`. Re-run **3
  more times: fail, fail, fail** — the false positive is **stable, not a fluke**.
- **The false finding is technically wrong (MEASURED):** its stated reason was that regex `(\S+)`
  "requires non-whitespace characters only… [so] contains hyphens and colons… will cause parsing to
  fail." `\S` *does* match hyphens and colons — the model misunderstood the character class and
  invented a defect in correct code. This is the load-bearing caveat: **a local-judge `fail` is not
  reliable enough to block a correct deliverable on its own.**

## Latency (MEASURED, this host)

- Worker (qwen2.5-coder:7b): **1.4–5.0 s** per task, median ~3.6 s, all single-round.
- Adversary (gemma3:27b): **3.7–13.3 s** per judgment. A full local pair round (worker + two-sided
  judge) is well under a minute per small unit — interactively usable locally.

## Recommendation — which build units are safe to route local

Maps directly onto `role_model_fit.md` §5–6:

1. **SAFE for a local pair — small, self-contained, single-function build units *with a runnable
   self-test as the gate*.** Worker=qwen2.5-coder:7b (escalate to qwen3-coder:latest for
   larger/tool-heavy). The executable oracle/asserts — not the judge — must be the authority on
   merge. gemma3:27b runs as an adversarial second opinion whose *findings* are triaged, but whose
   bare `fail` never blocks a deliverable that passes its own tests (33% stable false-positive rate
   measured here).
2. **Judge-only gating with NO runnable oracle → NOT safe local.** Where correctness can't be settled
   by running code (prose deliverables, design docs, cross-cutting judgment), the local judge's
   false-positive/miss profile is unproven and it demonstrably fabricates findings — keep on Claude
   or require a human/Claude review.
3. **Multi-file / repo-wide / unfamiliar-API worker tasks → Claude** (unchanged from #173 §5.3;
   this test only validates small self-contained functions, per its own scope).
4. **Keep the R4 validate/retry wrapper and Claude fallback wired in** — worker needed 0 retries here
   but N is small (3 tasks, Wilson lower bound is wide), so the wrapper and fallback stay
   unconditional.

**Bottom line:** the local pair *can* settle a real small build unit today — the worker earns it and
the judge helps — **but only with a deterministic self-test holding the gate.** Claude remains
required for multi-file worker patches and for any gate that lacks a runnable oracle.

---
### Appendix — reproduce
`python3 scratchpad/pairbench.py` (needs Ollama up with qwen2.5-coder:7b + gemma3:27b). Config:
`temperature=0.3`, `num_predict=1500`, `num_ctx=8192`, endpoint `http://localhost:11434/api/chat`,
JSON-Schema `format`, ≤2 retries. 3 worker calls + 6 adversary calls + a 3× false-positive re-probe.
Oracles validated first against the Claude-baseline reference solutions (3/3 good pass, 3/3 buggy
fail) before the local run.
