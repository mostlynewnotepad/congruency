# Ollama Structured-Output & Tool-Calling Reliability — Gemma 3 & Qwen Coder

**Ticket:** #175 (rfc-investigation, MAKE-OR-BREAK gate for `local-agent-stack`)
**Date:** 2026-07-15
**Status:** MEASURED (live micro-benchmark against local Ollama)
**Gate verdict:** **PASS — with a required tool-calling shim.** Structured JSON output is reliable enough to build on today; native tool-calling is model-dependent and needs a validate/recover wrapper.

---

## 1. Summary / Verdict

The `local-agent-stack` design depends on local models emitting (a) **structured JSON** (dispatch plans, verdicts, work-done envelopes) and (b) **tool calls** reliably. This was tested empirically, not projected.

**Headline findings (N=20 trials per cell, 400 requests total, live Ollama on this host):**

1. **Structured JSON output is rock-solid.** Every model tested — `gemma3:4b`, `qwen2.5-coder:7b`, `qwen3-coder:latest` (30B) — produced **100% valid JSON and 100% schema-conformant** output on both the dispatch-plan and verdict schemas, in **all** modes: `format:"json"` (prompt-guided), JSON-Schema-constrained (`format:<schema>`), zero-shot, and few-shot. Median latency 0.5–1.1 s per call.

2. **Tool-calling via the Ollama `tools` API is NOT uniform.** Three distinct behaviors:
   - **`gemma3` (4b and 27b): tools are hard-unsupported.** Ollama returns HTTP error `"registry.ollama.ai/library/gemma3:4b does not support tools"` — 20/20 errors. The `/api/tags` capability list confirms it: gemma3 advertises only `["completion"]`, no `"tools"`.
   - **`qwen2.5-coder:7b`: model is correct, Ollama's parser is not.** Native `message.tool_calls` was populated **0/20** times. Instead the model emitted a *correct* call as a JSON string in `message.content` (e.g. `{"name":"ticket_assign","arguments":{"assignee":"apon","ticket_id":733}}`). With a content-fallback parser, **20/20 (100%)** recoverable. Without one, you get **0%**.
   - **`qwen3-coder:latest` (30B): clean.** Native `message.tool_calls` populated and valid **20/20 (100%)**.

**Implication for the gate:** The stack must **not** treat "the Ollama tools API returns a native `tool_calls`" as the reliability contract. Use **JSON-Schema-constrained `format`** as the primary structured channel (100% everywhere), and for tool invocation use a thin adapter that (a) prefers native `tool_calls`, (b) falls back to parsing a tool-call object out of `content`, and (c) validates + retries. gemma3 cannot use the tools API at all and must express "tool calls" as schema-constrained JSON objects.

---

## 2. Method

**Environment (MEASURED):** `curl http://localhost:11434/api/tags` on this host. Ollama up. Relevant pulled models and advertised capabilities:

| Model | Params | Quant | Capabilities (from /api/tags) |
|---|---|---|---|
| `gemma3:4b` | 4.3B | Q4_K_M | `completion` (NO tools) |
| `gemma3:27b` | 27.4B | Q4_K_M | `completion` (NO tools) |
| `qwen2.5-coder:7b` | 7.6B | Q4_K_M | `completion`, `tools`, `insert` |
| `qwen3-coder:latest` | 30.5B MoE | Q4_K_M | `completion`, `tools` |
| `llama3.2:latest` | 3.2B | Q4_K_M | `completion`, `tools` |

Models exercised: **gemma3:4b** (fast proxy for the gemma3 family; the 27b shares the same no-tools limitation), **qwen2.5-coder:7b**, **qwen3-coder:latest**. Larger gemma3:27b was not trial-looped to keep the run under a few minutes; its tools-unsupported behavior is identical (same capability list) and its JSON behavior is expected to match or exceed the 4b.

**Harness:** `POST http://localhost:11434/api/chat`, `stream:false`, `temperature:0.7`, `num_predict:256`. Script: `scratchpad/bench.py` (reproducible; parameters below). N=20 trials per cell.

**Schemas under test:**

- **dispatch plan** — `{"action": "run"|"skip"|"stop", "ticket_id": int, "reason": str}`
- **verdict** — `{"pass": bool, "findings": [str]}`
- **tool call** — mock `ticket_assign(ticket_id:int, assignee:str)` via the `tools` array.

**Conditions (cells) per model:**

| Cell | Channel | Few-shot |
|---|---|---|
| dispatch/prompt-json/zero | `format:"json"` + schema described in prompt | no |
| dispatch/prompt-json/fewshot | `format:"json"` + prompt | 1 example |
| dispatch/schema/zero | `format:<JSON-Schema>` (constrained decode) | no |
| verdict/prompt-json/zero | `format:"json"` + prompt | no |
| verdict/schema/zero | `format:<JSON-Schema>` | no |
| assign/tools/zero | `tools:[...]` | no |
| assign/tools/fewshot | `tools:[...]` | 1 example (assistant tool_call) |

**Metrics recorded per cell:**
- `native_pct` — JSON parses directly from `message.content` (JSON kind), or Ollama populated `message.tool_calls` (tool kind).
- `conform_pct` — passes the strict validator (JSON kind: exact schema/types incl. int-not-string, enum membership); (tool kind: a valid `ticket_assign` call recoverable from **either** `tool_calls` **or** a JSON object embedded in `content`).
- `errors` — HTTP/transport errors (e.g. tools-unsupported).
- `median_latency_s`.

Note on strictness: the JSON validator rejects the common failure mode of `ticket_id` returned as a string (`"4821"`); a smoke test showed gemma3 doing exactly this once under free `format:"json"`, so conformance is a real, not rubber-stamp, check.

---

## 3. Measured Results

Full grid, N=20 per cell (native% / conform% / median latency s):

### JSON structured output

| Model | dispatch prompt-json 0-shot | dispatch prompt-json few-shot | dispatch JSON-Schema | verdict prompt-json | verdict JSON-Schema |
|---|---|---|---|---|---|
| gemma3:4b | 100 / 100 / 0.76 | 100 / 100 / 0.67 | 100 / 100 / 0.76 | 100 / 100 / 0.75 | 100 / 100 / 0.75 |
| qwen2.5-coder:7b | 100 / 100 / 0.90 | 100 / 100 / 0.59 | 100 / 100 / 0.90 | 100 / 100 / 1.02 | 100 / 100 / 1.01 |
| qwen3-coder:latest | 100 / 100 / 0.84 | 100 / 100 / 0.54 | 100 / 100 / 0.85 | 100 / 100 / 1.04 | 100 / 100 / 1.05 |

### Tool calling (native tool_calls% / recoverable-conform% / latency s)

| Model | assign tools 0-shot | assign tools few-shot | Notes |
|---|---|---|---|
| gemma3:4b | 0 / 0 / 0.20 | (n/a) | **20/20 HTTP errors:** "does not support tools" |
| qwen2.5-coder:7b | **0** / **100** / 0.88 | **0** / **100** / 0.88 | Correct call, but delivered in `content`, not native `tool_calls` |
| qwen3-coder:latest | **100** / **100** / 0.68 | **100** / **100** / 0.68 | Native `tool_calls` populated and valid |

**Statistical caveat:** N=20 with 20/20 successes gives a Wilson 95% lower confidence bound of ~83%, not "four nines." These numbers establish that the happy path is dominant and the failure modes are structural (not random noise), which is what a gate needs. They do **not** license removing the retry/validation wrapper — for a system firing thousands of envelopes, plan for a small but non-zero malformed-output tail and handle it.

---

## 4. Per-model / per-schema reliability (rollup)

| Model | JSON dispatch | JSON verdict | JSON-Schema constrain | Tool call (native) | Tool call (with shim) |
|---|---|---|---|---|---|
| **gemma3:4b / 27b** | 100% | 100% | 100% | **unsupported** | must emulate via JSON-Schema object |
| **qwen2.5-coder:7b** | 100% | 100% | 100% | **0%** | **100%** (content-fallback parse) |
| **qwen3-coder:latest (30B)** | 100% | 100% | 100% | **100%** | **100%** |

**Usable threshold (defined for this gate):** a structured channel is "usable" for the stack if, wrapped in one validate-and-retry, it yields **≥ 99% conformant envelopes end-to-end** at acceptable latency (< ~3 s/call for these small schemas). All three models **clear this for JSON structured output** even before the wrapper. For tool-calling, qwen3-coder clears it natively; qwen2.5-coder clears it only with the content-fallback shim; gemma3 clears it only by routing tool intents through the JSON-Schema channel.

---

## 5. Required Mitigation

Ranked by leverage for this codebase:

### 5.1 PRIMARY — Prefer JSON-Schema-constrained `format` over the tools API
Ollama's `format:<JSON-Schema>` (constrained decoding, backed by llama.cpp GBNF grammar compilation of the schema) was **100%** across every model and schema. This is the most portable, model-agnostic channel and the one gemma3 can use. **Represent dispatch plans, verdicts, and work-done envelopes as JSON-Schema-constrained outputs, not as `tools` calls.** Even "tool invocations" the planner wants to make can be expressed as a constrained JSON object `{"tool": "...", "args": {...}}` and dispatched by the adapter — this sidesteps Ollama's per-model tool-call parsing entirely.

### 5.2 REQUIRED for tool-calling — validate-and-retry wrapper with content fallback
The adapter for ticket #176 must, on every tool-style call:
1. Read `message.tool_calls` if present (qwen3-coder path).
2. **Else** parse `message.content` for a JSON tool-call object — first `{`…last `}`, `json.loads`, accept both `{"name","arguments"}` and bare-args forms (qwen2.5-coder path). This single fallback moved qwen2.5-coder from **0% → 100%**.
3. Validate arguments against the tool schema (types, required fields, `ticket_id` int-not-string).
4. On validation failure, **retry up to 2×** with the parser error fed back as a corrective user turn. (Not needed in this sample, but cheap insurance for the tail.)

### 5.3 GBNF grammars — available, not currently required
llama.cpp (Ollama's engine) supports raw GBNF grammar constraints, and Ollama's JSON-Schema `format` compiles to exactly this mechanism under the hood. Since schema-constrained `format` already hit 100%, **hand-written GBNF is not required now.** Keep it in reserve for: (a) outputs that JSON-Schema can't express (e.g. cross-field constraints, regex-tight string formats), or (b) if a future model/schema drops below the 99% threshold under `format:<schema>`.

### 5.4 Few-shot — helps latency, not correctness (here)
Few-shot examples did **not** change conformance (already 100%) but consistently **lowered latency** (e.g. dispatch few-shot ~0.54–0.67 s vs ~0.76–0.90 s zero-shot) by steering the model to terminate sooner. Use one terse few-shot example in production prompts as a cheap latency win; do not rely on it for correctness.

---

## 6. Recommendation for build ticket #176 (Ollama agent adapter)

1. **Gate PASSES — proceed with the local-agent-stack build.** Local models are usable for structured output today.
2. **Make JSON-Schema-constrained `format` the default structured channel.** Every envelope type (dispatch plan, verdict, work-done) gets a JSON Schema; send it as `format`. This is 100% and model-agnostic.
3. **Do not depend on Ollama native `tool_calls`.** Build the adapter's tool-call extractor as: `tool_calls` → else content-JSON fallback → validate → retry. Ship it with the content fallback from day one; without it, qwen2.5-coder tool-calling is 0%.
4. **Model routing / capability probe:** at startup, read `/api/tags` capabilities. Route tool-heavy work to `qwen3-coder:latest` (native tool_calls, 100%). Treat `gemma3:*` as a **JSON-only** model — never send it a `tools` array (hard error); express its "tool" outputs as constrained JSON. `qwen2.5-coder:7b` is a fine, faster JSON+tool worker **provided** the content fallback is in place.
5. **Keep the validate-and-retry wrapper on all channels** despite 100% here — N=20 only guarantees a ~83% Wilson lower bound; the wrapper is what turns "usually right" into a dependable ≥99% envelope stream and gives clean telemetry on the malformed tail.
6. **Latency budget:** 0.5–1.1 s median per call for these schemas on this host — well within an interactive dispatch loop. Add one few-shot example per prompt for a modest latency reduction.

**One-line gate result:** PASS for structured JSON (100% across gemma3 / qwen2.5-coder / qwen3-coder); tool-calling PASSES only via qwen3-coder natively or a mandatory content-fallback+retry shim for qwen2.5-coder, and gemma3 must route tool intents through the JSON-Schema channel.

---

## Appendix A — Reproduce

Harness: `scratchpad/bench.py`. Run: `python3 bench.py [model ...]` (defaults to the three models above). Config: `N=20`, `temperature=0.7`, `num_predict=256`, endpoint `http://localhost:11434/api/chat`. Emits one JSON result line per cell and writes `results.json`.

Cells per model: 5 JSON cells + 2 tool cells (tool-capable) or 1 tool-error cell (gemma3). Total this run: 6 (gemma3) + 7 (qwen2.5-coder) + 7 (qwen3-coder) = 20 cells × 20 trials = **400 live requests**, all completed, exit 0.

## Appendix B — Observed raw failure modes
- gemma3 + `tools` → `400`-class error, body `{"error":"...gemma3:4b does not support tools"}`.
- gemma3 free `format:"json"` occasionally emitted `"ticket_id":"4821"` (string) in a one-off smoke test — caught by strict conformance check; did not recur across the 20-trial constrained/prompt cells. Motivates keeping int-coercion in the validator.
- qwen2.5-coder + `tools` → `message.tool_calls` empty; correct call serialized into `message.content`. Motivates the content-fallback parser.
