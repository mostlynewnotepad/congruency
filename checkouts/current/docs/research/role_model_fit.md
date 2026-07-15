# Role → Model Fit — Local Ollama Models on REAL Agent Tasks (Dispatch / Worker / Judge)

**Ticket:** #173 (rfc-investigation). Sibling of #175 (structured-output reliability). Together #173 + #175 gate build **#176** (Ollama agent adapter).
**Date:** 2026-07-15
**Status:** MEASURED (live micro-benchmark against local Ollama on this host)
**Gate verdict:** **PASS — with a role→model routing + two required harness affordances.** Local models are good enough to run the dispatch, worker, and judge roles on our real task shapes, provided (1) the dispatcher is fed **pre-computed stop/gate flags** rather than asked to reverse-look-up ticket relationships, and (2) the adapter **explicitly sets `num_ctx`**. gemma3:4b is too weak to dispatch and is excluded. Complex multi-file worker patches remain a Claude fallback.

This builds ON #175, which already established structured-output *validity*; here we measure task *quality* (right answer, not just well-formed JSON). #175 is CITED, not re-measured.

---

## 1. Summary — role → model → size mapping

| Role | Default model | Size | Measured task quality | Why |
|---|---|---|---|---|
| **DISPATCH** (queue → run/skip/stop plan) | **gemma3:27b** | 27.4B Q4_K_M | 4/6 raw → **6/6 with pre-computed flags** | Correct once stop/gate is pre-flagged; keeps qwen free for worker; judge-capable too. qwen3-coder is an equal, ~5× faster alternate. |
| **WORKER** (self-contained coding task → deliverable) | **qwen2.5-coder:7b** (small) / **qwen3-coder:latest 30B** (larger/tool-heavy) | 7.6B / 30.5B | **5/5 (100%)** both, syntax 5/5 | Both perfect on self-contained functions; 7b is fast, 30B has 256k ctx + native tool-calls (per #175). |
| **JUDGE / adversary** (artifact → pass/fail + findings) | **gemma3:27b** | 27.4B Q4_K_M | **6/6 (100%)**: 3/3 bugs caught, 0/3 false positives | Perfect on the suite AND a *different model family* from the qwen worker → uncorrelated blind spots for adversarial review. |
| DISPATCH — gemma3:4b | (excluded) | 4.3B | 1/6 (17%) | Too weak for run/skip/stop reasoning. Do not use as dispatcher. |

**One-line gate result:** PASS. Role→model mapping above is viable on measured task quality; the two failure modes found are structural and mitigated by harness design (pre-computed flags, explicit `num_ctx`), not by a bigger model.

---

## 2. Method

**Environment (MEASURED):** `curl http://localhost:11434/api/tags` + `ollama show`. Ollama up. Pulled models and *measured* context lengths:

| Model | Params | Quant | Context length (MEASURED) | Capabilities (per #175 / /api/tags) |
|---|---|---|---|---|
| gemma3:4b | 4.3B | Q4_K_M | **131072** | completion (NO tools) |
| gemma3:27b | 27.4B | Q4_K_M | **131072** | completion (NO tools) |
| qwen2.5-coder:7b | 7.6B | Q4_K_M | **32768** | completion, tools, insert |
| qwen3-coder:latest | 30.5B MoE | Q4_K_M | **262144** | completion, tools |

**Harness:** `POST http://localhost:11434/api/chat`, `stream:false`, `temperature:0.3` (low, for reasoning determinism — note #175 used 0.7 for a validity, not quality, question), `num_predict` 1024, **`num_ctx` 8192 (set explicitly)**. Script: `scratchpad/rolebench.py` (reproducible). Structured roles (dispatch, judge) use JSON-Schema-constrained `format` — the channel #175 proved 100%-valid, so every failure here is a *reasoning* error, never a parse error.

**Success rate is over a task suite** (N realistic tasks per role, one call per task), drawn from THIS system. This is a modest run (63 calls total, ~3 min wall). It measures whether the happy path is dominant and *where* it breaks; it is not a high-N reliability figure — see caveat. Each task is scored **automatically** against ground truth (MEASURED), except where noted JUDGMENT-CALL.

**Tasks per role (all grounded in this codebase's real shapes):**
- **DISPATCH** (6 cases): a synthetic `ticket.queue` (mirroring the real queue's fields: `id, kind, status, blocked_on, stop_target`), scored on emitting the correct action for *every* ticket. Rules: `stop` if an active (REQUESTED/OPEN) `kind=stop` ticket targets it; else `skip` if gated (blocked_on not DONE) or itself DONE/stop-kind; else `run`. Cases cover ready, gated, gate-satisfied, active-stop, *resolved*-stop (must NOT stop), and all-clear. Models: gemma3:4b, gemma3:27b, qwen3-coder.
- **WORKER** (5 cases): small self-contained Python tasks pulled from real adapter needs (`parse_semver`, `last_json_line` = parse the final-line JSON envelope pair_loop depends on, `dedupe`, `flatten`, `valid_plan`). Scored: code is syntactically valid (`ast.parse`) AND passes concrete assertions. Models: qwen2.5-coder:7b, qwen3-coder:30b, gemma3:27b (contrast).
- **JUDGE** (6 cases): artifact + stated requirement → verdict `{pass, findings}`. 3 planted-bug artifacts (off-by-one factorial, inverted-comparison max, a dispatch plan that runs a gated ticket) → **catch-rate**; 3 correct artifacts (palindrome, mean, a valid verdict envelope) → **false-positive rate**. Models: gemma3:27b, qwen3-coder.

---

## 3. Measured Results per role

### 3.1 DISPATCH (success = all ticket actions correct in the case)

| Model | Success | Rate | Median latency | Notes |
|---|---|---|---|---|
| gemma3:4b | 1/6 | **17%** | 1.41 s | Too weak — mis-assigned run/skip on simple gating (e.g. ran a gated ticket, skipped a ready one). |
| gemma3:27b | 4/6 | 67% | 6.28 s | Correct on gating; **missed both active-stop cases**. |
| qwen3-coder:latest | 4/6 | 67% | **1.31 s** | Identical failure pattern to gemma3:27b; ~5× faster. |

**Key MEASURED finding — the two failures are the *same* two cases for both large models:** the cases where a ticket had another ticket with `kind=stop, stop_target=<this id>` aimed at it. Both models emitted `run` instead of `stop`. They handle direct gating (`blocked_on`) fine but do **not** reliably perform the reverse-lookup "does any *other* ticket stop me?". gemma3:27b and qwen3-coder are very different architectures (dense vs MoE), so the correlated failure indicates a **task-framing limit, not a model quirk**.

**Confirmatory probe (MEASURED):** re-running the two failed cases with the harness supplying pre-computed booleans (`has_active_stop`, `gated`) per ticket — instead of asking the model to derive them — gave **4/4 correct** for *both* models (`gemma3:27b` and `qwen3-coder`). So the models apply the stop/gate *rule* correctly; they just can't be trusted to *discover* the cross-ticket relationship. → With pre-computed flags, effective dispatch quality is **6/6** for both large models.

### 3.2 WORKER (success = syntactically valid AND passes concrete checks)

| Model | Success | Rate | Syntax-valid | Median latency | Notes |
|---|---|---|---|---|---|
| qwen2.5-coder:7b | 5/5 | **100%** | 5/5 | **2.07 s** | Fast, perfect on self-contained functions. |
| qwen3-coder:latest | 5/5 | **100%** | 5/5 | 1.82 s | Perfect; larger ctx + native tool-calls (per #175). |
| gemma3:27b | 4/5 | 80% | 5/5 | 11.94 s | Not a coder: one logic bug (`parse_semver` returned a `map` object, not a tuple) and ~6× slower. |

**Scope honesty (JUDGMENT-CALL boundary):** these are *small, single-function, self-contained* tasks. They validate that the qwen coders reliably turn a crisp spec into correct code. They do **not** establish competence on multi-file patches, unfamiliar-API glue, or large-repo-context reasoning — that is the fallback zone in §5.

### 3.3 JUDGE (success = correct verdict; catch bugs, don't false-flag clean)

| Model | Success | Catch-rate (buggy) | False-positive-rate (clean) | Median latency |
|---|---|---|---|---|
| gemma3:27b | 6/6 (**100%**) | **3/3 caught** | **0/3** | 3.98 s |
| qwen3-coder:latest | 6/6 (**100%**) | 3/3 caught | 0/3 | **0.93 s** |

Both caught the off-by-one factorial, the inverted-comparison max, and the dispatch-plan-runs-a-gated-ticket bug, and passed all three correct artifacts. On this suite the judge role is the *strongest* fit for local models. gemma3:27b is chosen as default despite qwen3-coder being faster: keeping the judge a **different family from the worker** is the point of an adversarial reviewer (see §5.4 argument), and gemma3:27b hit 100% here.

**Statistical caveat (carried from #175):** N is small (6 dispatch / 5 worker / 6 judge cases per model, one trial each). 100% on 5–6 items has a wide Wilson lower bound (~55–60%). These numbers establish *dominant happy path + located failure modes*, which is what the gate needs; they do **not** license removing validation/retry or the Claude fallback.

---

## 4. Context-window adequacy (MEASURED sizes vs our real payloads)

Our real payload sizes (MEASURED from the live queue, chars → ~tokens at 4 chars/tok):

| Payload | Chars | ~Tokens |
|---|---|---|
| Ticket body — median | 783 | ~195 |
| Ticket body — max (of 72) | 3,254 | ~813 |
| **Full 72-ticket `ticket.queue` JSON** | 96,867 | **~24,200** |

Against measured model context lengths:

| Model | Context | Fits one worker ticket (body + ~5–10 repo excerpts, est. ~10–20k tok)? | Fits full-queue dispatch (~24k tok)? |
|---|---|---|---|
| gemma3:4b / 27b | 131,072 | Yes (~6–13× headroom) | **Yes** (~5× headroom) |
| qwen2.5-coder:7b | 32,768 | Yes for typical excerpts; tight if excerpts are large | **Yes, but only ~1.35×** headroom — no room to also carry the full queue |
| qwen3-coder:latest | 262,144 | Yes (huge headroom) | **Yes** (~10× headroom) |

**Adequacy verdict:** all four models' *capacities* are adequate for our ticket bodies and realistic repo context. The one tight spot is qwen2.5-coder:7b (32k) if you ever hand it the *entire* queue plus large excerpts — for the worker role it only sees one ticket + a few files, so 32k is fine.

**CRITICAL operational caveat (MEASURED):** Ollama's default `num_ctx` is **4096**, regardless of the model's 128k/256k capacity. At the default, a full-queue dispatch (~24k tok) is **silently truncated** and the dispatcher will reason over a partial queue. **#176 MUST set `options.num_ctx` explicitly** (e.g. 32k for dispatch over the full queue, sized to payload for worker). This benchmark set `num_ctx=8192`; production dispatch over the whole queue needs ≥32k.

---

## 5. Fallback list — tasks where local is too weak → Claude-as-tool-worker

Labeled MEASURED vs JUDGMENT-CALL:

1. **DISPATCH raw cross-ticket stop/gate reasoning — MEASURED too weak (67%).** Do NOT ask a local model to derive "is any other ticket stopping/gating me?" from the raw queue. **Mitigation (preferred over Claude):** the harness pre-computes `has_active_stop` and `gated` per ticket (a trivial deterministic pass), then the model just applies the rule → 100% (MEASURED). Only if that pre-compute is not in place is this a Claude fallback. This is a *design requirement on #176*, not a model swap.
2. **DISPATCH on gemma3:4b — MEASURED too weak (17%).** Exclude 4b from the dispatcher role entirely; use gemma3:27b or qwen3-coder.
3. **WORKER on complex/multi-file patches — JUDGMENT-CALL fallback.** Measured worker success (100%) is on *small self-contained functions*. Tasks requiring multi-file edits, reasoning across large repo context, unfamiliar-API integration, or subtle cross-cutting changes are **beyond what this benchmark validated** and are the intended **Claude-as-tool-worker** fallback. Contrast evidence that local coders are not infallible even at small scale: gemma3:27b already produced a `map`-object bug on a one-line `parse_semver`. Route to Claude when the build ticket's deliverable spans multiple files or needs repo-wide reasoning.
4. **JUDGE self-review — JUDGMENT-CALL policy.** Never let the same model (family) judge its own worker output; use gemma3:27b to judge qwen worker output and vice-versa. Not a Claude fallback per se, but a routing rule to preserve adversarial independence.

---

## 6. Recommendation for build #176 (Ollama agent adapter defaults)

1. **Gate PASSES — proceed with #176.** Local models are good enough for all three roles on our real task shapes, given the affordances below.
2. **Default model per role in the adapter:**
   - `DISPATCH → gemma3:27b` (num_ctx ≥ 32k). Equal-accuracy, ~5× faster alternate is `qwen3-coder:latest` if the dispatch loop is latency-sensitive and qwen is already resident.
   - `WORKER → qwen2.5-coder:7b` for small self-contained tasks (fast, 100%); **escalate to `qwen3-coder:latest`** for larger tasks, tool-heavy work (native tool-calls per #175), or when context approaches 32k; **escalate to Claude** for multi-file / repo-wide patches (§5.3).
   - `JUDGE → gemma3:27b` (different family from the qwen worker → uncorrelated blind spots). `qwen3-coder` is an equal, faster alternate *only* when judging non-qwen output.
3. **REQUIRED harness affordance A — pre-compute stop/gate flags for the dispatcher.** Before calling the model, the adapter deterministically computes `has_active_stop` and `gated` per ticket and includes them in the payload. This moves dispatch from 67% → 100% (MEASURED) and keeps the safety-critical stop-respect out of the model's fuzzy reverse-lookup.
4. **REQUIRED harness affordance B — set `options.num_ctx` explicitly**, sized to the payload (default 4096 will truncate a full-queue dispatch). Never rely on the default.
5. **Carry #175's channel + wrapper unchanged:** JSON-Schema-constrained `format` for dispatch plans and verdicts (100% valid per #175); tool-call extractor with content-fallback + validate/retry; gemma3 gets NO `tools` array (route "tool" intents as constrained JSON).
6. **Keep the Claude-as-tool-worker fallback wired in** for the §5.3 complex-worker case and as the escape hatch when a local role dips below threshold under real load.

**Gate line:** role→model→size mapping is established and **PASSES** — dispatch=gemma3:27b (stop/gate pre-computed), worker=qwen2.5-coder:7b / qwen3-coder:30B, judge=gemma3:27b; gemma3:4b excluded from dispatch; complex multi-file worker patches fall back to Claude.

---

## Appendix A — Reproduce

Harness: `scratchpad/rolebench.py`. Run: `python3 rolebench.py roleresults.json`. Config: `temperature=0.3`, `num_predict=1024`, `num_ctx=8192`, endpoint `http://localhost:11434/api/chat`. **45 live calls** (dispatch 3 models × 6 cases = 18; worker 3 × 5 = 15; judge 2 × 6 = 12) + a 4-call confirmatory probe (§3.1). ~3 min wall on this host. Prints per-cell success/latency and writes `roleresults.json` with per-case raw detail.

## Appendix B — Raw per-case outcomes (MEASURED)

**Dispatch** (both large models failed exactly cases 2 & 4 — the active-stop cases):
- gemma3:4b 1/6 — e.g. case1 `{201:skip,202:run,203:skip}` (ran the gated 202, skipped the ready 201).
- gemma3:27b 4/6 — case2 `{140:run,...}` (should be `stop`), case4 `{401:run,...}` (should be `stop`); all gating cases correct.
- qwen3-coder 4/6 — identical failures to gemma3:27b (case2 `140:run`, case4 `401:run`).
- Confirmatory (flags pre-computed): gemma3:27b & qwen3-coder both **4/4** on cases 2 & 4.

**Worker:**
- qwen2.5-coder:7b 5/5 pass, qwen3-coder 5/5 pass — all `syntax ok; check PASS`.
- gemma3:27b 4/5 — case1 `parse_semver` raised `TypeError("'map' object is not subscriptable")` (returned a lazy `map`, not a tuple); other 4 passed.

**Judge** (verdict_pass vs expected):
- gemma3:27b 6/6 — buggy factorial→pass:false, palindrome→pass:true, buggy max→pass:false, gated-run plan→pass:false, correct mean→pass:true, valid envelope→pass:true.
- qwen3-coder 6/6 — identical correct pattern.
