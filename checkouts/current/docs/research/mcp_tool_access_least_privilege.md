# MCP-Only Tool Access + Least-Privilege Dispatch Agent

**Ticket:** #174 (rfc-investigation). GATES build **#178** (MCP tool bridge) and **#179** (least-privilege Gemma dispatch agent).
**Date:** 2026-07-15
**Status:** GROUNDED — routes enumerated from the live db (`api_routes`, 62 routes, method column read directly); MCP server/tool inventory taken from the connected servers in this environment; enforcement contrasted against the actual `pair_loop.py` code.
**Builds ON:** #173 `role_model_fit.md` (role→model: dispatch=gemma3:27b with harness-precomputed stop/gate flags; worker=qwen2.5-coder / qwen3-coder; judge=gemma3:27b) and #175 `ollama_structured_output_reliability.md` (JSON-Schema-constrained `format` is the 100% structured channel; gemma3 takes NO `tools` array). Those are CITED, not re-derived.

---

## 1. Summary / Recommendation

**Gate verdict: PASS.** A least-privilege, MCP-only tool design is achievable today with the servers already connected plus two small must-build servers. The dispatch role can be made **structurally incapable** of authoring work product.

Three load-bearing conclusions:

1. **Enforcement point = per-role MCP-server SELECTION at launch (option c), reinforced by a server-side role allowlist (option b).** The dispatch agent is launched with *only* the ticket-api MCP in its `dispatch` profile connected and *no* built-in file/shell/git tools. Its tool context then literally contains only `{ticket.queue, ticket.kind, ticket.assign, edge.record, ticket.progress}` — there is no `Write`, `Bash`, `Edit`, `codebean`, or git tool present to call. This is a real trust boundary because the capability is **absent**, not **filtered**. `pair_loop`'s current `--allowedTools` string (option a) is only a client-side name filter over tools that are still fully present in the process — not a boundary.

2. **codebean already covers file-free worker code authoring.** It is a connected MCP server that authors code as a structured model (`new_module`/`add_class`/`add_function`/`set_body`/`render`/`tree`/`save`) and handles git invisibly — the worker writes code *without ever touching the filesystem, a path, or `git`*. This directly delivers the "no arbitrary file access" goal for the code path.

3. **Only two servers must be built:** a **ticket-api MCP bridge** (#178) that wraps the governed REST routes and exposes a *per-role subset*, and a **run-tests MCP** that replaces `pair_loop`'s raw `Bash(python3:*)` grant with a sandboxed, allowlisted execution tool. (Plus, for the documentation kind, a narrow deliverable-writer constrained to the ticket's one declared path — or reuse codebean for code kinds and gate docs behind that single-path writer.)

---

## 2. Role → MCP-tool matrix

Columns are concrete tools and the server that exposes them. "R" = read route, "W" = write route. The **harness** (`pair_loop`/its successor) — not the agent — still performs the safety-critical governance writes (`work.record`, `ticket.create` for stops, commit/merge); agents get only what their role legitimately needs.

| Role | ticket-api MCP (must-build) | code / file authoring | repo reads | test execution | Built-in fs/shell/git |
|---|---|---|---|---|---|
| **DISPATCH** (gemma3:27b) | `ticket.queue`(R), `ticket.kind`(W), `ticket.assign`(W), `edge.record`(W), `ticket.progress`(W) — **this exact 5, nothing else** | **none** | **none** | **none** | **none** |
| **WORKER** (qwen2.5-coder / qwen3-coder / Claude fallback) | read-context only: `ticket.journal`(R), `ticket.manifest`(R), `kind.roster`(R), `lessons.recent`(R), `doc.read`(R) — **no writes** | **codebean** (code kind: `new_module`/`add_class`/`add_function`/`set_body`/`render`/`tree`/`save`); **deliverable-writer MCP** (doc kind: single declared path only) | **git-surface** `pull_atomic_file`, `query_file_blame`, `inspect_git_surface` | **run-tests MCP** (must-build; allowlisted python3 + repo php) | **none** |
| **JUDGE / adversary** (gemma3:27b) | read-context only: `ticket.journal`(R), `ticket.manifest`(R), `kind.roster`(R) — **no writes** | **none** (never authors) | **git-surface** `pull_atomic_file`, `query_file_blame` | **run-tests MCP** (to *prove* bugs by executing) | **none** |

Notes:
- **No role gets `work.record`, `artifact.record`, `ticket.create`, `doc.record`, `source.record`, `bug.record`, `ticket.approve`, `agent.register`, or `process_status`.** Those are harness-held governance writes. This mirrors today's design: in `pair_loop.py` the *harness* calls `work.record`/`ticket.progress`/`ticket.create`, and the git pen (`commit`/`merge`/`reap`) is held by `forge-t<id>`, never by the worker or dispatcher.
- Dispatch's stop/gate reasoning is fed **harness-precomputed** `has_active_stop`/`gated` flags (role_model_fit affordance A) — so dispatch does not even need `ticket.stops` in its grant; the harness reads it and injects the booleans. This keeps the safety-critical reverse-lookup out of the model AND out of the model's tool surface.

### 2.1 Full route classification (all 62 `api_routes`, method read from the db)

- **Dispatch-safe grant (the 5, all this role may touch):** `ticket.queue`(GET), `ticket.kind`(POST), `ticket.assign`(POST), `edge.record`(POST), `ticket.progress`(POST). Every write here mutates *routing metadata only* (a kind label, an authorization row, an edge, a journal note).
- **Read-context routes (available to worker/judge for grounding, never dispatch's authoring surface):** `ticket.journal`, `ticket.manifest`, `ticket.crew`, `ticket.stops`, `kind.roster`, `children.list`, `lifecycle.steps`, `agent.roster`, `agent.prompt`, `agent.trail`, `tickets.recent`, `lessons.recent`, `doc.list`, `doc.read`, `doc.repos`, `repo.list`, `source.commits`, `guarantee.list`, `guarantee.held`, `mandate.list`, `policy.active`, `binding.list`, `journey.list`, `artifact.list`, `bug.list`, `search.text`, `search.facets`, `run.get`, `run.recent`, `job.get`, `processes.running`, `ticket.approval` (all GET).
- **Worker/governance WRITES — harness-held, exposed to NO local agent role:** `work.record`, `artifact.record`, `ticket.create`, `ticket.lesson`, `ticket.approve`, `doc.record`, `source.record`, `bug.record`, `run.record`, `telemetry.record`, `search.record`, `binding.record`, `guarantee.record`, `journey.record`, `mandate.record`, `policy.create`, `job.put`, `agent.register`, `process_status`, `authorize_process` (all POST).
- **Telemetry/admin reads (neither role's work tool; harness/observability only):** `error.recent`, `error.stats`, `bug.stats`, `search.stats`, `telemetry.recent`.

The critical observation: **the dispatch grant contains no route that can emit a deliverable.** There is no `work.record`, `artifact.record`, `doc.record`, `source.record`, `bug.record`, or `ticket.create` in it, and no code/file/shell tool in its context at all (see §5).

---

## 3. Existing vs must-build MCP servers

### Already connected in this environment (verified from the live tool surface)

| Server | Tools | Role in this design |
|---|---|---|
| **codebean** | `new_module`, `add_class`, `add_function`, `set_body`, `render`, `tree`, `save` | **WORKER code authoring, file-free.** Authors code as a structured model and persists via `save(message)` with git handled invisibly — the worker never touches a path, the filesystem, or `git`. Directly serves the "no arbitrary file access" goal. `save(message, mature=True)` freezes the release form. |
| **git-surface** | `pull_atomic_file`, `query_file_blame`, `inspect_git_surface`, `vm_snapshot`/`vm_save_state`/`vm_restore_state`/`vm_revert`/`vm_pause`/`vm_resume`/`vm_state`/`vm_snapshots`/`vm_discard_saved_state`, `fabric_up`/`fabric_launch`/`fabric_attach`/`fabric_state`/`fabric_instances`/`fabric_leases` | **Read-only repo access for worker + judge** (`pull_atomic_file` reads a blob without fs access; `query_file_blame` for provenance). VM/fabric ops give an *isolated execution surface* the run-tests MCP can snapshot around. Note: git-surface exposes **no commit/merge/push** — those stay with the harness `Forge`, so agents cannot alter history. |
| **mcp-registry** | `list_connectors`, `search_mcp_registry`, `suggest_connectors` | Discovery/meta only. Not an agent work tool; useful to the harness for wiring. |
| **z3 solver** | (ticket-referenced) | **NOT connected in this environment.** No z3 tools are present in the live surface. Out of scope for the tool grants; note if it is wired later it would be a judge/worker *reasoning* aid, never a write surface. |
| ccd_session, visualize, scheduled-tasks, claude-in-chrome | (harness/UX) | Harness- and UX-side; not part of any local agent role's grant. |

### Must build

| Server | Why it must exist | Shape |
|---|---|---|
| **ticket-api MCP bridge** (#178) | No MCP server today exposes the governed REST routes. This is *the enforcement surface*: it wraps the routes and exposes a **per-role profile subset**. | Wrap the `rest.php` surface (same `X-Api-Key` + `rest()` semantics `pair_loop.py` already uses; reuse its secret-loading from `.secrets/ats.env`). A launch parameter `--role={dispatch|worker|judge|forge}` selects which route-tools are registered; server-side, reject any call whose route is not in the launched profile (option b, defense-in-depth). |
| **run-tests MCP** | `pair_loop` currently grants `Bash(python3:*)` and `Bash(<repo>/php)` — **arbitrary python = arbitrary fs/network/shell.** That is the single biggest hole in the current least-privilege story. | A `run_tests(target)` / `run_command(allowlisted)` tool that executes only an allowlist (python3 on the deliverable, the repo php harness), inside a git-surface VM snapshot if isolation is wanted, and returns structured `{passed, output, exit}`. No free-form shell string reaches a shell. |
| **deliverable-writer MCP** (docs) | codebean covers *code*; the `documentation` kind writes prose. A worker needs to write exactly one file — its declared `deliverable` — and nothing else. | A `write_deliverable(content)` tool whose path is fixed to the ticket's declared deliverable (injected at launch), refusing any other path. Preserves "no arbitrary file access" for the doc path. (Alternatively: extend codebean with a prose sink; a path-locked writer is simpler and auditable.) |

---

## 4. Enforcement mechanism — three options, the chosen one, and why it is a real boundary

### (a) `claude -p --allowedTools "<list>"` — pair_loop's current approach
`pair_loop.py` builds a per-kind allow-string (`FOCUS[kind]["worker_tools"]` = `"Read,Grep,Glob,Write,Edit,Bash(python3:*),..."`, dispatch = `"Read,Grep,Glob"`) and passes it to `claude -p --allowedTools`. This is a **client-side name filter**: the built-in `Write`/`Bash`/`Edit`/`Read` tools remain fully present in the process; the client merely refuses calls whose name doesn't match the string. Two failures:
- It is not a trust boundary — a client bug, a filter-parsing edge case, or a prompt-injection that reaches an un-filtered path exposes the *whole* underlying tool (full fs, full shell).
- Even working perfectly it is **not least-privilege**: the build/bug grant *includes* `Bash(python3:*)`, i.e. arbitrary python = arbitrary filesystem and network. The dispatch grant `Read,Grep,Glob` still carries the real `Read`/`Grep`/`Glob` tools reading the whole repo.

### (b) MCP-server-side allowlist
The ticket-api server itself checks the caller's role and refuses any route outside the launched profile. This is a **real server-side boundary for the ticket API** — the client cannot invoke what the server will not serve, regardless of client bugs. But on its own it does not remove the *other* tools (fs, shell, codebean) from the agent's context; it only governs the one server.

### (c) per-role MCP-server SELECTION at launch — **CHOSEN (primary)**
Launch each role's agent process with **only its permitted MCP servers connected and no built-in fs/shell/git tools**. The dispatch agent is started with only the ticket-api MCP in the `dispatch` profile. Its tool inventory is then exactly `{ticket.queue, ticket.kind, ticket.assign, edge.record, ticket.progress}` — there is no `Write`, `Bash`, `Edit`, `codebean`, `run-tests`, or git tool in the context to call.

**Recommendation: (c) as the trust boundary, (b) as defense-in-depth, (a) demoted to at most a redundant inner filter — never relied on.**

**Why (c) is the strongest — absence beats filtering.** A filter (a, and to a degree b) is a runtime policy check over a capability that is physically present; checks can be bypassed, misconfigured, or reasoned around by an injected prompt. Option (c) makes least-privilege a property of the **process's tool inventory**: the capability does not exist in the agent's context, so there is nothing to invoke, bypass, or misconfigure. You cannot call a tool that was never loaded. Server-side (b) then guarantees that *even if a server is wrongly connected*, it still refuses out-of-role routes — so the two layers fail safe independently.

**Contrast with pair_loop, concretely:** today the boundary is "a comma-separated string the `claude` client honors," and that string *grants arbitrary shell to workers*. The redesign moves the boundary to "which MCP servers the OS process was launched with," and removes raw shell/fs entirely in favor of codebean + run-tests + the ticket-api profile.

---

## 5. Dispatch least-privilege proof-sketch (why it cannot author work product)

1. **Launch:** the dispatch agent (gemma3:27b) is started with only the ticket-api MCP, `role=dispatch` profile. No built-in `Bash`/`Write`/`Edit`/file-`Read`, no codebean, no run-tests, no git-surface, no doc-writer are connected.
2. **Resulting tool inventory:** exactly `{ticket.queue (R), ticket.kind (W), ticket.assign (W), edge.record (W), ticket.progress (W)}`.
3. **Every writable route in that set mutates routing metadata only:** a set-once kind label, an authorization row on `ticket_agents`, a graph edge, an append-only journal note. **None of them is a work-product sink** — the set contains no `work.record`, `artifact.record`, `doc.record`, `source.record`, `bug.record`, `ticket.create`, and no file/code write exists in the context.
4. **Therefore the dispatch agent cannot:** author or commit a deliverable (no codebean, no writer, no git), create tickets or stops (no `ticket.create` — the *harness* mints stop tickets in `do_dispatch`), register agents, run code (no run-tests, no shell), or record any artifact/UID. Its maximal achievable effect is to *route the queue* — exactly its mandate.
5. **Independent backstop:** even the routing writes cannot fabricate a settled ticket — the db's `tg_tickets_pair_completion` trigger (migration 0029) refuses `DONE` unless `ticket_agents` holds two distinct agents in two distinct roles, and `work.record`/`process_status DONE` are not in dispatch's grant anyway.
6. **Even-stronger variant (already how pair_loop works):** keep dispatch *harness-mediated* — the agent emits only a JSON plan (via #175's JSON-Schema-constrained `format`; gemma3 takes NO `tools` array per #175 §4) and the harness applies `ticket.kind`/`assign`/`edge.record`/`progress`. Then the dispatch agent is **tool-less** — the absolute floor of least privilege. #179 may ship either form; both cap the capability at the dispatch profile.

---

## 6. Build guidance

### #178 — MCP tool bridge (build this first; #179 depends on it)
- **Deliverable:** a ticket-api MCP server wrapping the 62 governed routes, exposing a **per-role profile**. Reuse `pair_loop.py`'s `rest()` call semantics and its `.secrets/ats.env` `CONGRUENCY_API_KEY` loading; every write continues to flow through `rest.php` (no SQL pen).
- **Profiles to ship:**
  - `dispatch` = `{ticket.queue, ticket.kind, ticket.assign, edge.record, ticket.progress}` — the exact 5.
  - `worker` = read-context routes only (`ticket.journal`, `ticket.manifest`, `kind.roster`, `lessons.recent`, `doc.read`, …); **no writes**.
  - `judge` = read-context routes only; **no writes**.
  - `forge` (harness identity) = the governance writes (`work.record`, `ticket.create`, `ticket.progress`, `process_status`, `agent.register`) — held by the harness, never handed to a model.
- **Enforcement (option b, inside the server):** reject any tool call whose route is not in the launched profile; log the refusal. This is defense-in-depth behind the launch-time server selection.
- **Also build the run-tests MCP** (sandboxed, allowlisted python3 + repo php, structured `{passed, output}`; optionally snapshot via git-surface `vm_save_state`/`vm_revert`) and the **deliverable-writer MCP** (path locked to the ticket's declared deliverable). Standardize code authoring on **codebean** (already connected).

### #179 — Gemma least-privilege dispatch agent
- **Model:** gemma3:27b, `num_ctx ≥ 32k` (role_model_fit affordance B — the default 4096 silently truncates a full-queue dispatch).
- **Launch (option c):** connect **only** the ticket-api MCP in the `dispatch` profile. Do **not** connect codebean, run-tests, git-surface, the deliverable-writer, or any built-in fs/shell/git tool. This is what makes the agent structurally incapable of authoring work product (§5).
- **Input:** the queue with harness-precomputed `has_active_stop`/`gated` booleans per ticket (role_model_fit affordance A — moves dispatch quality from 67% → 100%). The harness reads `ticket.stops`; the agent never does.
- **Output channel:** JSON-Schema-constrained `format` for the plan (#175 §5.1, 100% valid). gemma3 gets **no `tools` array** (#175 §4) — route "tool" intents either as constrained JSON the harness applies (the tool-less variant, strongest) or through the ticket-api MCP's dispatch profile.
- **Ceiling either way:** the agent's maximal capability is the dispatch profile; it can route but cannot build, commit, create, or run.

### Gate line
**PASS.** A least-privilege, MCP-only design is buildable with what exists (codebean = file-free code authoring; git-surface = read-only repo access) plus two small must-builds (ticket-api bridge #178, run-tests MCP) and a path-locked doc writer. Enforcement via per-role MCP-server selection (c) + server-side role allowlist (b) is a real structural trust boundary that `pair_loop`'s `--allowedTools` (a) — which today even grants workers arbitrary `Bash(python3:*)` — is not. The dispatch role can be made provably unable to author work product.
