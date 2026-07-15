#!/usr/bin/env python3
"""ollama_agent.py — the non-claude agent runner: a drop-in replacement for `claude -p`, backed by
either a LOCAL model over Ollama or an OPENAI-COMPATIBLE endpoint (the litellm proxy -> Cerebras
GLM 4.7).

WHAT THIS IS. `pair_loop.py` runs every agent through ONE function, `spawn_claude(prompt,
allowed_tools, timeout, cwd)` (pair_loop.py:723-741), which shells out to `claude -p <prompt>
--allowedTools <tools>` (:727) and reads the agent's answer off the LAST JSON line of stdout
(:734-741). This module is a second implementation of that same contract. Same contract, three parts:

    IN     a birth prompt (the same string pair_loop builds from WORKER_PROMPT/AUDITOR_PROMPT,
           pair_loop.py:615-641) plus an allowlist of tool names (pair_loop.py:704-705, :716-717).
    ACT    the agent reads/greps/writes/edits/runs — using ONLY the allowlisted tools — until it
           has written the deliverable file the prompt names.
    OUT    one JSON object as the LAST line of stdout: {"done":true,...} for a worker,
           {"verdict":"pass"|"fail","findings":[...]} for an adversary.

TWO BACKENDS, ONE PIPELINE. The allowlist, the tools, the workspace boundary, the JSON-Schema
enforcement, the extractor ladder, the validate-and-retry channel and the registration are shared;
only the TRANSPORT and the request/response SHAPE differ. `--api-flavor` picks the shape:

    ollama  (default)  POST $OLLAMA_URL/api/chat            — Ollama's native shape.
    openai             POST $OPENAI_BASE/v1/chat/completions — the OpenAI-compatible shape, which is
                       what the litellm proxy on localhost:4000 speaks. Its `worker` model routes to
                       cerebras/zai-glm-4.7 (GLM 4.7) — see config/litellm/litellm_config.yaml:14-20
                       and config/litellm/start.sh, which sources the key from the wallet.

TWO WAYS TO RUN IT (both are this one file; see --help):

  1. AGENT MODE — the drop-in. Same argv shape as `claude -p`, so anything that spawns claude can
     spawn this instead:
         python3 ollama_agent.py -p "<birth prompt>" --allowedTools "Read,Grep,Glob,Write,Edit"
         python3 ollama_agent.py --api-flavor openai -p "<birth prompt>" --allowedTools "Read,Write"
     It prints progress to stderr and the envelope JSON as the last line of stdout.

  2. ENGINE MODE — `--engine ollama|claude|cerebras`. It drives pair_loop.py with the chosen engine
     and passes every other argument straight through:
         python3 ollama_agent.py --engine cerebras --ticket 411 --deliverable docs/X.md
         python3 ollama_agent.py --engine ollama --ticket 176 --deliverable docs/X.md
         python3 ollama_agent.py --engine claude --ticket 176 --deliverable docs/X.md
         python3 ollama_agent.py --engine cerebras --dispatch 3 --parallel 2
     `--engine ollama` and `--engine cerebras` both rebind pair_loop's module-global `spawn_claude`
     to this module's runner BEFORE calling pair_loop.main(), so every agent the loop spawns — the
     worker (pair_loop.py:1559), the adversary (:1576) and the dispatcher (:789) — runs on the
     chosen backend. They differ ONLY in the api flavor and the role->model map: `ollama` runs local
     models over /api/chat; `cerebras` runs the litellm proxy's models over /v1/chat/completions, so
     the CODER WORKER runs on Cerebras GLM 4.7 (ticket #411). `--engine claude` changes nothing and
     is the stock loop. Nothing else about pair_loop's behavior is altered: the brake, the branch,
     the commit, the merge, the journal and the exit codes are all still pair_loop's.

     ARGUMENT OWNERSHIP IN ENGINE MODE (this matters, and it is enforced, not merely intended).
     Once `--engine` is present, the ONLY arguments this module keeps are `--engine` itself and the
     `--ollama-*` / `--openai-*` tuning flags below. EVERY other argument is handed to pair_loop
     verbatim, so `--ticket`, `--deliverable`, `--timeout`, `--rounds`, `--base`, `--dispatch`,
     `--parallel`, `--selftest` and the rest mean exactly what pair_loop.py means by them, with
     pair_loop's own parser reporting its own errors. The tuning flags are deliberately named apart —
         --ollama-model  --ollama-channel  --ollama-max-steps  --ollama-retries
         --ollama-num-ctx  --ollama-no-journal
         --openai-model  --openai-base  --openai-max-tokens
     — precisely so they can never collide with an option pair_loop owns now or adds later (its
     parser is pair_loop.py:1415-1448; it owns no --engine and no --openai-*/--ollama-* of its own).
     (In AGENT mode the same knobs are spelled --model/--channel/--max-steps/--retries/--num-ctx/
     --no-journal, because there is no second parser to collide with.) Per-spawn timeout in engine
     mode comes from pair_loop's own --timeout, which it passes to spawn_claude (pair_loop.py:1559).

     WHY THE SELECTOR LIVES HERE AND NOT IN pair_loop.py. This file's deliverable line is "write it
     to checkouts/current/congruency/tools/ollama_agent.py (create or overwrite that file; touch
     nothing else)". That is not a style note — it is mechanically enforced: the harness stages ONLY
     the deliverable's scope, reports every dirty path outside it as a `stray`
     (Forge.commit_deliverable, pair_loop.py:507), and then reaps the worktree with `--force`
     (pair_loop.py:585-591). An edit to pair_loop.py from inside this ticket would therefore never
     be committed — it would be journaled as abandoned and deleted. So the selector is implemented
     the only way it can both exist and survive: entirely inside this file, requiring ZERO edits to
     pair_loop.py, by rebinding the one function pair_loop looks up at call time. It is a real,
     runnable `--engine ollama|claude|cerebras`; prove it with --selftest, which asserts the rebind
     takes for BOTH ollama and cerebras.

HOW IT MEETS THE GATES (#173 "role->model fit" = R2, #175 "structured-output reliability" = R4;
both docs live in checkouts/current/docs/research/):

  * STRUCTURED OUTPUT IS ENFORCED, NOT HOPED FOR (R4). Every model turn is JSON-Schema-constrained:
    on the ollama flavor via Ollama's `format` field — the channel R4 measured at 100%
    valid/conformant across gemma3:4b, qwen2.5-coder:7b and qwen3-coder (R4 §3, §5.1) — and on the
    openai flavor via `response_format: {"type":"json_schema", ...}`, the SAME schema object carried
    in the OpenAI-compatible spelling. Each reply is then parsed and VALIDATED against the schema in
    Python (types, required keys, enum membership, int-not-string), and on any failure the parser's
    own error is fed back as a corrective turn and the call is RETRIED up to --retries times
    (default 2) — R4 §5.2 steps 3-4. R4 §3 is explicit that 100% over N=20 has a ~83% Wilson lower
    bound and does NOT license dropping the wrapper, so the wrapper is unconditional on BOTH
    flavors — it is the guarantee, and response_format is only the assist.

  * WHY json_schema IS SENT WITH strict:false (openai flavor). Measured against the live proxy, not
    assumed: with `strict: true` Cerebras REJECTS this module's own schemas outright —
        HTTP 400 CerebrasException - 'additionalProperties' is required to be supplied and set to
        false. Received Model Group=worker
    because OpenAI strict mode demands `additionalProperties:false` on every object, and neither
    step_schema() (whose `args` merges every allowed tool's properties) nor ENVELOPES["dispatch"]
    (whose `kind`/`deliverable` are deliberately OPTIONAL) can satisfy that without changing the
    shapes the ollama flavor shares. With `strict: false` the same schemas are accepted and the
    replies conform. So strict is false, and validate()+retry — which R4 requires regardless — stays
    the actual enforcement.

THE GLM 4.7 CONTRACT (openai flavor; every claim here was measured against the live proxy):

  * REASONING IS ON BY DEFAULT AND SPENDS THE TOKEN BUDGET. GLM 4.7 emits reasoning before content,
    and the reasoning is billed against max_tokens. With max_tokens=64 the model spent all 64 tokens
    reasoning and returned finish_reason="length" with content EMPTY — a reply carrying no answer at
    all. So max_tokens is sized GENEROUSLY (default 40000 = the ceiling the proxy pins on the
    `worker` route, litellm_config.yaml:20, and GLM 4.7's max output), never the ollama path's
    num_predict of 1024. A generous cap is free: billing is per token GENERATED, not per token
    reserved. If it still happens, openai_message() raises a ONE-LINE explanation naming the budget
    and the reasoning tokens spent — never a silent empty envelope.

  * THE ANSWER IS message.content; THE REASONING IS message.reasoning_content. Only `content` is
    read. `reasoning_content` is never parsed as the answer and never fed back into the transcript.

  * REASONING IS SPENT WHERE IT PAYS. Per-turn, not globally (see reasoning_params):
        agentic  clear_thinking:false     — the tool-step loop and any judgement turn (the
                                            adversary's verdict, the dispatcher's plan).
        cheap    reasoning_effort:"none"  — deterministic turns with a known shape: the worker's
                                            final done/ref/note envelope, and every corrective
                                            "your JSON was malformed, re-emit it" retry. Measured:
                                            reasoning_effort:"none" took an envelope turn from 775
                                            reasoning tokens to 0, with identical conformant JSON.
    Both are real Cerebras parameters, not hopeful extras: the endpoint 400s on an unknown property
    ("property 'zzz_bogus_param_xyz' is unsupported"), and both of these are accepted.

  * temperature=1 / top_p=0.95 are GLM 4.7's migration-guide coding defaults and are the same values
    litellm_config.yaml:18-19 pins on the `worker` route. They are sent explicitly so the runner is
    correct even against a base or alias that does not pin them (e.g. `cerebras-glm`, :45-48, pins
    neither). Override with --openai-temperature/--openai-top-p.

  * TOOL CALLS SURVIVE OLLAMA'S PER-MODEL PARSING (R4 §5.2). The extractor is the ladder R4
    requires: prefer native `message.tool_calls`; ELSE parse a JSON object out of `message.content`
    (first '{' .. last '}'); accept BOTH the {"name","arguments"} and {"tool","args"} spellings.
    That single content fallback is what moved qwen2.5-coder from 0% to 100% in R4's measurements.

  * gemma3 IS NEVER SENT A `tools` ARRAY (R4 §5.1, §5.4). gemma3 hard-errors on the tools API
    ("does not support tools"); its /api/tags capabilities list omits "tools". The DEFAULT channel
    (--channel schema) sends no `tools` array to ANY model and instead carries tool intents as
    schema-constrained JSON objects, which is R4's PRIMARY recommendation and works on every model
    including gemma3. --channel tools opts into Ollama's native tools API and is REFUSED, with a
    one-line message, for a model whose capabilities lack "tools".

  * num_ctx IS ALWAYS SET EXPLICITLY (R2 §4, "REQUIRED harness affordance B"). Ollama's default
    num_ctx is 4096 REGARDLESS of the model's 128k/256k capacity, so an unset num_ctx silently
    TRUNCATES a large prompt and the model reasons over a partial payload. This module sizes
    num_ctx per request from the actual payload (~4 chars/token per R2 §4, plus headroom), floors
    it at 8192 (R2's bench value) and caps it at the model's real context length, read live from
    Ollama's /api/show. It never relies on the default. num_ctx is an OLLAMA option and is sent ONLY
    on the ollama flavor; the openai flavor has no such knob (the server owns the context window)
    and sends no `options` block at all.

  * THE ROLE PICKS THE MODEL (R2 §1, §6.2). Parsed from the birth prompt. On the ollama flavor:
        worker/coder     -> qwen2.5-coder:7b   (R2: 5/5 on self-contained coding tasks, fastest)
        adversary/judge  -> gemma3:27b         (R2: 6/6, 3/3 bugs caught, 0/3 false positives, and
                                                a DIFFERENT family from the qwen worker, which is
                                                the point of an adversarial reviewer — R2 §5.4)
        dispatch         -> gemma3:27b         (R2: 6/6 once stop/gate flags are pre-computed)
    --model overrides any of it. R2 §5.2 excludes gemma3:4b from dispatch and this module honors
    that: it is not the default for any role.

    On the openai flavor the names are the PROXY'S model aliases, not raw model ids, because that is
    what /v1/chat/completions accepts there (litellm_config.yaml `model_name:` entries):
        worker/coder     -> "worker"            -> cerebras/zai-glm-4.7   (ticket #411's goal)
        adversary/judge  -> "cerebras-gpt-oss"  -> cerebras/gpt-oss-120b
        dispatch         -> "dispatch"          -> cerebras/gpt-oss-120b
    The adversary is gpt-oss and NOT the GLM worker on purpose: R2 §5.4's different-family rule is
    the whole point of an adversarial reviewer, and gpt-oss-120b is the only other family the proxy
    serves. --openai-model (engine mode) / --model (agent mode) overrides any of it.

  * THE MODEL RECORDED IS THE MODEL THAT RAN. The response body echoes back only the ALIAS
    ("model":"worker"), so the alias is resolved to the real underlying id through the proxy's
    /v1/model/info route ("worker" -> "cerebras/zai-glm-4.7") and THAT is what registration records.
    Resolution is best-effort: if the route cannot be reached the alias is recorded unresolved rather
    than the run being failed.

  * THE AGENT IS REGISTERED AND ITS RUN IS JOURNALED THROUGH THE GOVERNED ROUTES. Registration is
    `agent.register` (migrations/0001_agents.sql:19-25) and the journal is `ticket.progress`
    (migrations/0029_ticket_authorization.sql:193-198) — the same token routes pair_loop uses; this
    module holds no SQL pen. Registration records the model that ACTUALLY ran and the tools that
    were ACTUALLY granted, so the record reflects the engine that really answered rather than
    pair_loop's placeholder `["claude -p"]` (pair_loop.py:1551). The route is INSERT OR REPLACE, so
    re-registering an id pair_loop already created UPDATES it and erases nothing.

TOOLS ARE RESTRICTED TO THE ALLOWLIST, AND THE ALLOWLIST IS THE ONE pair_loop ALREADY PASSES.
`--allowedTools` takes the exact strings from pair_loop's FOCUS table (pair_loop.py:696-720; the
build pair's worker_tools at :716), e.g. "Read,Grep,Glob,Write,Edit,Bash(python3:*)". Enforcement is
in two independent layers, because a model can hallucinate a tool name that was never offered:
    1. only allowlisted tools are described to the model at all, and the step schema's `tool` enum
       is built from that same list; and
    2. every call is re-checked at dispatch time and refused if the name is not allowlisted.
`Bash(<prefix>:*)` restricts Bash to commands whose argv[0] is exactly <prefix>. Bash runs with
shell=False (argv parsed by shlex), so `;`, `&&` and `|` cannot chain a second command past the
prefix gate. Every path argument is resolved and must stay inside the workspace directory; a path
escaping it (via `..`, an absolute path, or a symlink) is refused. A refusal is returned to the
model as a tool result it can react to — it is never a crash.

SIDE EFFECTS, STATED PLAINLY. This tool is an agent runner: writing files IS its job, and in agent
mode the model will create/modify files inside the workspace via the Write/Edit tools when the
allowlist grants them (that is how the deliverable gets written). Outside the workspace it writes
nothing, with one exception shared by every tool in this repo: an unexpected exception appends a
Variant-A bug report to the registry's bug_reports sink (note-for-claude; registry.json
"bug_reports"). --selftest is the exception to the exception: it runs entirely inside a temp
directory it deletes, needs no key, no db, no network, no Ollama and no proxy, and touches this repo
not at all — the openai flavor is proven there against an in-process STUB, by monkeypatching the one
transport function (_openai_post), which is the same call-time-lookup trick --engine uses on
pair_loop.spawn_claude.

Usage:
    python3 ollama_agent.py -p PROMPT --allowedTools TOOLS [--model M] [--role R] [--ticket N]
                            [--agent-id ID] [--deliverable PATH] [--cwd DIR] [--channel schema|tools]
                            [--num-ctx N] [--max-steps N] [--retries N] [--timeout S] [--no-journal]
                            [--api-flavor ollama|openai] [--openai-base URL] [--openai-max-tokens N]
                            [--openai-temperature F] [--openai-top-p F]
    python3 ollama_agent.py --engine ollama|claude|cerebras [--ollama-*] [--openai-*]
                            [... pair_loop.py arguments ...]
    python3 ollama_agent.py --selftest
    python3 ollama_agent.py --probe [--api-flavor openai]

    Note --selftest/--probe are THIS module's and belong to agent mode; with --engine they pass
    through to pair_loop like every other argument (`--engine claude --selftest` therefore runs
    pair_loop's git-layer selftest, not this one).

Exit codes:
    0  the agent finished and printed its envelope JSON as the last line of stdout
       (--engine: pair_loop's own exit code, unchanged; --selftest: every check passed)
    1  --selftest: at least one check FAILED (--probe: a role's default model is not available)
    2  unexpected — a one-line message (never a traceback) and a Variant-A bug report was filed

Governance: a run registers and journals through the governed routes, and REFUSES to start without
CONGRUENCY_API_KEY (env, or .secrets/ats.env beside the repo — the same two sources pair_loop reads,
pair_loop.py:172-177). Pass --no-journal to run ungoverned for ad-hoc/offline use; it says so on
stderr.

The proxy needs no auth for local use. If a litellm master key is ever set, this module reads it from
$LITELLM_MASTER_KEY (or $OPENAI_API_KEY) and sends it as `Authorization: Bearer <key>`; it is never
written to disk or logged. The CEREBRAS key is NOT this module's business: the proxy holds it,
sourced from the wallet by config/litellm/start.sh.
"""
import argparse
import glob as globlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from fnmatch import fnmatch


# ── registry gate (note-for-claude: a tool that cannot see the registry throws) ──────────────────
def find_registry(start):
    d = os.path.abspath(start)
    while True:
        p = os.path.join(d, "registry.json")
        if os.path.isfile(p):
            return d, json.load(open(p))
        nxt = os.path.dirname(d)
        if nxt == d:
            raise RuntimeError("registry.json not found walking up from %s — refusing to run" % start)
        d = nxt


ROOT, REGISTRY = find_registry(os.path.dirname(os.path.abspath(__file__)))
CONG = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")
OLLAMA = (os.environ.get("OLLAMA_URL") or "http://localhost:11434").rstrip("/")

# The OpenAI-compatible endpoint: the litellm proxy, whose `worker` model routes to
# cerebras/zai-glm-4.7 (config/litellm/litellm_config.yaml:14-20). $OPENAI_BASE overrides it.
OPENAI_BASE = (os.environ.get("OPENAI_BASE") or "http://localhost:4000").rstrip("/")

# The local proxy needs no auth. If a master key is ever set on it, it is read from the environment
# and sent as a Bearer token — never read from a file, never logged, never journaled.
PROXY_KEY = os.environ.get("LITELLM_MASTER_KEY") or os.environ.get("OPENAI_API_KEY")


def _secret(name):
    """The key, from the same two places pair_loop reads it (pair_loop.py:172-181): the secrets file
    beside the repo first, then the environment."""
    path = os.path.join(os.path.dirname(ROOT), ".secrets", "ats.env")
    if os.path.isfile(path):
        for line in open(path):
            if line.strip().startswith(name + "="):
                return line.strip().split("=", 1)[1]
    return os.environ.get(name)


API_KEY = _secret("CONGRUENCY_API_KEY")


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks).
    Mirrors pair_loop.bug_report (pair_loop.py:184)."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "ollama_agent.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:], "note": "ollama_agent runner",
            }) + "\n")
    except Exception:  # noqa: BLE001
        pass


class Unexpected(RuntimeError):
    pass


class Refused(RuntimeError):
    """A tool call the allowlist or the workspace boundary forbids. Reported BACK to the model as a
    tool result (so it can correct itself), never raised out of the run."""


def log(msg):
    """Progress goes to STDERR. Stdout carries the envelope and nothing else, because the caller
    reads the LAST LINE of stdout (pair_loop.py:734-741) — a stray print there would be read as the
    agent's answer."""
    sys.stderr.write("%s\n" % msg)
    sys.stderr.flush()


# ── the governed REST surface (token routes; this module holds no SQL pen) ───────────────────────
def rest(route, obj=None, method=None):
    """Mirrors pair_loop.rest (pair_loop.py:205)."""
    url = CONG + "/rest.php?route=" + route
    if obj is not None and (method or "POST") == "GET":
        url += "&" + "&".join("%s=%s" % (k, urllib.request.quote(str(v))) for k, v in obj.items())
        obj = None
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json", "X-Api-Key": API_KEY or ""})
    with urllib.request.urlopen(req, timeout=15) as r:
        out = json.loads(r.read().decode())
    if "error" in out:
        raise Unexpected("route %s failed: %s" % (route, out["error"]))
    return out


# ── Ollama transport ─────────────────────────────────────────────────────────────────────────────
def _ollama(path, body=None, timeout=600):
    url = OLLAMA + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode()).get("error", "")
        except Exception:  # noqa: BLE001
            pass
        raise Unexpected("ollama %s -> HTTP %s%s" % (path, e.code, (": " + detail) if detail else ""))
    except urllib.error.URLError as e:
        raise Unexpected("ollama unreachable at %s (%s) — is `ollama serve` running? Override with "
                         "$OLLAMA_URL." % (OLLAMA, e.reason))


_TAGS_CACHE = {}


def installed_models(refresh=False):
    """{name: [capabilities]} from /api/tags — R4 §5.4's startup capability probe."""
    if _TAGS_CACHE and not refresh:
        return _TAGS_CACHE
    for m in (_ollama("/api/tags", timeout=20) or {}).get("models", []):
        _TAGS_CACHE[m["name"]] = list(m.get("capabilities") or [])
    return _TAGS_CACHE


_CTX_CACHE = {}


def context_cap(model):
    """The model's REAL context length, read live from /api/show (`<arch>.context_length`).

    Read, not hardcoded: R2 §4 tabulates 32768 for qwen2.5-coder:7b, 131072 for gemma3 and 262144
    for qwen3-coder, and asking the running Ollama keeps those numbers true as models change. Falls
    back to R2's bench value (8192) if the field is absent, which only ever costs context, never
    correctness."""
    if model in _CTX_CACHE:
        return _CTX_CACHE[model]
    cap = 8192
    try:
        info = (_ollama("/api/show", {"model": model}, timeout=30) or {}).get("model_info") or {}
        for k, v in info.items():
            if k.endswith(".context_length") and isinstance(v, int):
                cap = v
                break
    except Unexpected:
        pass
    _CTX_CACHE[model] = cap
    return cap


def num_ctx_for(model, payload_chars, override=None):
    """Size num_ctx to the payload — R2 §4's REQUIRED affordance B.

    Ollama's default is 4096 whatever the model can do, so a big prompt is silently truncated and
    the model reasons over a fragment. ~4 chars/token is R2 §4's own conversion; +50% headroom for
    the reply; floor 8192 (R2's bench value); ceiling = what the model actually supports."""
    if override:
        return int(override)
    want = int((payload_chars / 4.0) * 1.5) + 2048
    return max(8192, min(context_cap(model), want))


# ── OpenAI-compatible transport (the litellm proxy -> Cerebras GLM 4.7) ──────────────────────────
# GLM 4.7's max output, and the ceiling litellm_config.yaml:20 pins on the `worker` route. A cap is
# not a reservation — billing is per token GENERATED — so sizing it at the ceiling costs nothing and
# is what keeps reasoning from eating the whole budget before any content is emitted.
GLM_MAX_TOKENS = 40000
# GLM 4.7's migration-guide coding defaults; the same values litellm_config.yaml:18-19 pins.
OPENAI_TEMPERATURE = 1
OPENAI_TOP_P = 0.95


def _openai_post(path, body=None, timeout=600):
    """The ONE HTTP call of the openai flavor. Every openai-flavor request goes through here, which
    is what makes the flavor provable offline: --selftest monkeypatches this name and the whole
    request/response mapping above it runs untouched against a stub. (Same call-time-lookup trick
    --engine plays on pair_loop.spawn_claude.)"""
    url = OPENAI_BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if PROXY_KEY:
        headers["Authorization"] = "Bearer " + PROXY_KEY
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # The proxy reports a refusal as {"error": {"message": ...}}; surfacing that message is the
        # difference between "HTTP 400" and "CerebrasException - property 'x' is unsupported".
        detail = ""
        try:
            raw = e.read().decode()
            err = json.loads(raw).get("error")
            detail = (err.get("message") if isinstance(err, dict) else err) or raw
        except Exception:  # noqa: BLE001
            pass
        raise Unexpected("openai-compat %s -> HTTP %s%s"
                         % (path, e.code, (": " + str(detail)[:400]) if detail else ""))
    except urllib.error.URLError as e:
        raise Unexpected("the OpenAI-compatible endpoint is unreachable at %s (%s) — is the litellm "
                         "proxy running? Start it with config/litellm/start.sh (it sources the "
                         "Cerebras key from the wallet). Override the address with $OPENAI_BASE."
                         % (OPENAI_BASE, e.reason))


_PROXY_MODELS = {}


def proxy_models(refresh=False):
    """{alias: the real underlying model} from the proxy's /v1/model/info.

    This is how requirement "record the model that ACTUALLY ran" is met: a completion's body echoes
    back only the ALIAS ("model":"worker"), so the alias must be resolved here to learn that `worker`
    is cerebras/zai-glm-4.7. Best-effort by design — a proxy that will not answer this route must not
    fail an otherwise-good run, so the caller falls back to recording the alias unresolved."""
    if _PROXY_MODELS and not refresh:
        return _PROXY_MODELS
    try:
        info = _openai_post("/v1/model/info", None, timeout=20) or {}
    except Unexpected:
        return _PROXY_MODELS
    for m in info.get("data") or []:
        alias = m.get("model_name")
        if alias:
            _PROXY_MODELS[alias] = ((m.get("litellm_params") or {}).get("model")) or alias
    return _PROXY_MODELS


def real_model(alias):
    """'worker' -> 'cerebras/zai-glm-4.7'. The alias itself if the proxy will not say."""
    return proxy_models().get(alias) or alias


def clamp_max_tokens(n):
    """max_tokens for one openai turn: generous by default, never above GLM 4.7's real ceiling."""
    return max(1, min(GLM_MAX_TOKENS, int(n or GLM_MAX_TOKENS)))


def reasoning_params(kind):
    """GLM 4.7 reasons by default; this decides whether that is worth paying for on THIS turn.

        agentic  clear_thinking:false     — a turn whose quality IS the reasoning: the tool-step
                                            loop, the adversary's verdict, the dispatcher's plan.
                                            (clear_thinking:false is the migration guide's
                                            agentic/coding recommendation and also improves cache
                                            hits; it does not switch reasoning off.)
        cheap    reasoning_effort:"none"  — a deterministic turn with a known shape: the worker's
                                            final done/ref/note envelope, and every corrective
                                            "that JSON was rejected, re-emit it" retry. Measured
                                            against the live proxy: this took an envelope turn from
                                            775 reasoning tokens to 0 with identical valid JSON.

    Exactly ONE of the two is sent, never both."""
    return {"reasoning_effort": "none"} if kind == "cheap" else {"clear_thinking": False}


def openai_message(resp):
    """The OpenAI response -> the `message` shape the rest of this module already speaks.

    The mapping is deliberately thin, because Ollama's message and OpenAI's choices[0].message agree
    on the two keys extract_json reads: `content`, and `tool_calls` as [{"function":{"name",
    "arguments"}}] (OpenAI serializes `arguments` as a JSON STRING, which extract_json already
    handles). So the ONLY real work is lifting choices[0].message out and refusing an empty answer.

    reasoning_content is NOT content and is never returned as the answer (the ticket's trap: GLM 4.7
    puts its thinking there, and a runner that read it would parse prose as an envelope)."""
    choices = (resp or {}).get("choices") or []
    if not choices:
        raise Unexpected("the OpenAI-compatible reply carried no choices: %s" % json.dumps(resp)[:200])
    ch = choices[0] or {}
    msg = dict(ch.get("message") or {})
    content = msg.get("content")
    if not (content or "").strip() and not (msg.get("tool_calls") or []):
        # The ticket's warned failure, made loud instead of silent. Measured: max_tokens=64 ->
        # finish_reason "length", 64/64 tokens spent on reasoning, content empty.
        if ch.get("finish_reason") == "length":
            spent = ((resp.get("usage") or {}).get("completion_tokens_details") or {}).get("reasoning_tokens")
            raise Unexpected("the model spent its whole max_tokens budget on REASONING and returned "
                             "no content (finish_reason=length, reasoning_tokens=%s). Raise "
                             "--openai-max-tokens (the ceiling is %d)." % (spent, GLM_MAX_TOKENS))
        raise Unexpected("the model returned an empty reply (finish_reason=%s)" % ch.get("finish_reason"))
    msg["content"] = content or ""
    return msg


def openai_chat(model, messages, fmt=None, tools=None, max_tokens=None, reasoning="agentic",
                temperature=OPENAI_TEMPERATURE, top_p=OPENAI_TOP_P, timeout=600):
    """One /v1/chat/completions turn, returned in Ollama's {"message": ...} envelope so that
    constrained()/extract_json()/validate() are shared verbatim by both flavors.

    `fmt` is the SAME JSON Schema object the ollama flavor passes to Ollama's `format`, carried here
    in the OpenAI spelling. strict is FALSE deliberately — see the module docstring: with strict:true
    Cerebras 400s on this module's own schemas because OpenAI strict mode demands
    additionalProperties:false everywhere, which step_schema()/ENVELOPES["dispatch"] cannot supply
    without changing shapes the ollama flavor shares. validate()+retry is the real enforcement."""
    body = {"model": model, "messages": messages, "stream": False,
            "max_tokens": clamp_max_tokens(max_tokens),
            "temperature": temperature, "top_p": top_p}
    body.update(reasoning_params(reasoning))
    if fmt is not None:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "reply", "strict": False, "schema": fmt}}
    if tools:
        body["tools"] = tools
    return {"message": openai_message(_openai_post("/v1/chat/completions", body, timeout=timeout))}


# ── R2 §1/§6.2: the role decides the model ───────────────────────────────────────────────────────
ROLE_MODELS = {
    "worker": "qwen2.5-coder:7b",     # R2 §3.2: 5/5 on self-contained coding tasks, fastest coder
    "adversary": "gemma3:27b",        # R2 §3.3: 6/6; a different family from the worker (R2 §5.4)
    "dispatch": "gemma3:27b",         # R2 §3.1: 6/6 with pre-computed stop/gate flags
}
DEFAULT_TEMPERATURE = 0.3             # R2 §2: low, for reasoning determinism (the OLLAMA flavor;
                                      # the openai flavor uses GLM 4.7's own defaults, see
                                      # OPENAI_TEMPERATURE/OPENAI_TOP_P)

# The openai flavor's role -> model map. These are the PROXY'S aliases (litellm_config.yaml
# `model_name:` entries), not raw model ids, because that is what its /v1/chat/completions accepts.
PROXY_ROLE_MODELS = {
    "worker": "worker",                 # -> cerebras/zai-glm-4.7 (GLM 4.7) — ticket #411's goal
    "adversary": "cerebras-gpt-oss",    # -> cerebras/gpt-oss-120b: a DIFFERENT family from the GLM
                                        # worker, which is the entire point of an adversarial
                                        # reviewer (R2 §5.4). It is the only other family the proxy
                                        # serves (litellm_config.yaml:41-44).
    "dispatch": "dispatch",             # -> cerebras/gpt-oss-120b (litellm_config.yaml:27-30)
}

# Which turns are worth GLM 4.7's reasoning tokens, per role, for the FINAL envelope turn.
# The worker's envelope is a done/ref/note report on work already finished — deterministic, so it is
# "cheap". The adversary's verdict and the dispatcher's plan ARE the judgement: reasoning is the
# product there, so they stay "agentic". Every tool-STEP turn is agentic regardless of role.
ENVELOPE_REASONING = {"worker": "cheap", "adversary": "agentic", "dispatch": "agentic"}


def role_of(prompt):
    """worker | adversary | dispatch, read off the birth prompt pair_loop built.

    Grounded in the templates, not guessed: WORKER_PROMPT opens "You are <id>, the <role> — the
    worker of a <kind> pair on ticket #<n>." (pair_loop.py:615) and AUDITOR_PROMPT opens the same
    way with "the adversary of a" (pair_loop.py:628). The dispatcher's prompt appends DISPATCH_RULES,
    whose plan envelope is the giveaway (pair_loop.py:744)."""
    if "the adversary of a" in prompt:
        return "adversary"
    if "the worker of a" in prompt:
        return "worker"
    if '"plan":' in prompt and "THE QUEUE" in prompt:
        return "dispatch"
    return "worker"


def ticket_of(prompt):
    """The ticket id from GOVERNANCE's "ticket #<n> authorizes you" (pair_loop.py:604), falling back
    to the header's "on ticket #<n>" (pair_loop.py:615)."""
    m = re.search(r"ticket\s+#(\d+)\s+authorizes\s+you", prompt) or re.search(r"on ticket #(\d+)", prompt)
    return int(m.group(1)) if m else None


def agent_of(prompt):
    """The agent id from GOVERNANCE's "You are registered as <id>" (pair_loop.py:605), falling back
    to the header's "You are <id>, the ..." (pair_loop.py:615/:628)."""
    m = re.search(r"You are registered as ([A-Za-z0-9_.\-]+)", prompt) or \
        re.search(r"^You are ([A-Za-z0-9_.\-]+),\s*the ", prompt, re.M)
    return m.group(1).rstrip(".,") if m else None


def deliverable_of(prompt):
    """The deliverable path from "Deliverable: write it to <path>" (WORKER_PROMPT's `%(worker_scope)s`
    slot at pair_loop.py:620, filled by worker_scope() at :646-649), falling back to the adversary's
    "The worker produced <path>." (pair_loop.py:633, filled by auditor_scope() at :659).

    The trailing period is stripped, not matched non-greedily: `(\\S+?)\\.` would stop at the FIRST
    dot and read "tools/ollama_agent.py." as "tools/ollama_agent". A path never ends in a dot, so
    taking the whole token and rstrip'ing '.' is both simpler and right."""
    m = re.search(r"Deliverable:\s*write it to\s+(\S+?)\s*\(", prompt) or \
        re.search(r"Deliverable:\s*write it to\s+(\S+)", prompt) or \
        re.search(r"The worker produced\s+(\S+)", prompt)
    return m.group(1).rstrip(".") if m else None


# ── R4 §5.1 + R2 §6.5: every envelope type gets a JSON Schema, sent as `format` ───────────────────
ENVELOPES = {
    # pair_loop reads wres.get("done") (:1560) and wres.get("ref"/"note") (:1563).
    "worker": {
        "schema": {"type": "object",
                   "properties": {"done": {"type": "boolean"},
                                  "ref": {"type": "string"},
                                  "note": {"type": "string"}},
                   "required": ["done", "ref", "note"]},
        "describe": '{"done": true, "ref": "<the deliverable path>", "note": "<one line on what you produced>"}',
    },
    # pair_loop reads vres.get("verdict") == "pass" (:1582) and vres.get("findings", []) (:1579).
    "adversary": {
        "schema": {"type": "object",
                   "properties": {"verdict": {"type": "string", "enum": ["pass", "fail"]},
                                  "findings": {"type": "array", "items": {"type": "string"}}},
                   "required": ["verdict", "findings"]},
        "describe": '{"verdict": "pass", "findings": []}   or   {"verdict": "fail", "findings": ["<finding>", ...]}',
    },
    # pair_loop reads res.get("plan", []) and each item's ticket/action/kind/deliverable/reason
    # (:790, :795-812). R2 §5.1: the harness must pre-compute stop/gate flags for the dispatcher,
    # because both large models reliably apply the stop RULE but cannot discover the cross-ticket
    # relationship themselves (4/6 -> 6/6 once the flag is supplied). pair_loop already does exactly
    # that, attaching active_stops per ticket (:787) before the queue reaches the model.
    "dispatch": {
        "schema": {"type": "object",
                   "properties": {"plan": {"type": "array", "items": {
                       "type": "object",
                       "properties": {"ticket": {"type": "integer"},
                                      "action": {"type": "string", "enum": ["run", "skip", "stop"]},
                                      "kind": {"type": "string"},
                                      "deliverable": {"type": "string"},
                                      "reason": {"type": "string"}},
                       "required": ["ticket", "action", "reason"]}}},
                   "required": ["plan"]},
        "describe": '{"plan": [{"ticket": <id>, "action": "run|skip|stop", "kind": "<kind-or-empty>", '
                    '"deliverable": "<path-or-empty>", "reason": "<why>"}]}',
    },
}


def validate(obj, schema, path="envelope"):
    """The strict validator R4 §5.2 step 3 requires: types, required keys, enum membership, and
    int-not-string (R4 App B saw gemma3 emit "ticket_id":"4821" once). Returns an error STRING for
    the corrective retry turn, or None when the object conforms.

    Deliberately a small, exact checker for the shapes in ENVELOPES/step_schema rather than a
    general JSON-Schema engine: it has no dependencies (note-for-claude: all tools run in python
    with nothing extra to install) and every rule it enforces is one this module actually emits."""
    t = schema.get("type")
    if t == "object":
        if not isinstance(obj, dict):
            return "%s: expected a JSON object, got %s" % (path, type(obj).__name__)
        for k in schema.get("required", []):
            if k not in obj:
                return "%s: missing required key %r" % (path, k)
        props = schema.get("properties") or {}
        for k, v in obj.items():
            if k in props:
                err = validate(v, props[k], "%s.%s" % (path, k))
                if err:
                    return err
        return None
    if t == "array":
        if not isinstance(obj, list):
            return "%s: expected an array, got %s" % (path, type(obj).__name__)
        for i, v in enumerate(obj):
            err = validate(v, schema.get("items") or {}, "%s[%d]" % (path, i))
            if err:
                return err
        return None
    if t == "string":
        if not isinstance(obj, str):
            return "%s: expected a string, got %s (%r)" % (path, type(obj).__name__, obj)
        if schema.get("enum") and obj not in schema["enum"]:
            return "%s: %r is not one of %s" % (path, obj, schema["enum"])
        return None
    if t == "integer":
        # int-not-string; and a bool must not sneak through, since isinstance(True, int) is True
        if isinstance(obj, bool) or not isinstance(obj, int):
            return "%s: expected an integer, got %s (%r) — emit a number, not a string" % (
                path, type(obj).__name__, obj)
        return None
    if t == "boolean":
        if not isinstance(obj, bool):
            return "%s: expected a boolean (true/false), got %s (%r)" % (path, type(obj).__name__, obj)
        return None
    return None


def extract_json(message):
    """R4 §5.2's extractor ladder, in its required order. Returns (obj, error_string).

    1. native `message.tool_calls` (the qwen3-coder path) — normalized to {"tool","args"};
    2. else a JSON object parsed out of `message.content`, first '{' to last '}' (the qwen2.5-coder
       path: the model emits a CORRECT call as a string in content while tool_calls stays empty —
       R4 measured 0% native / 100% recoverable, so this fallback is the whole difference);
    3. both the {"name","arguments"} and {"tool","args"} spellings are accepted.
    """
    calls = (message or {}).get("tool_calls") or []
    if calls:
        fn = (calls[0] or {}).get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):                      # some builds serialize arguments as a string
            try:
                args = json.loads(args)
            except ValueError:
                return None, "tool_calls[0].function.arguments is not valid JSON: %r" % args[:120]
        return {"tool": fn.get("name"), "args": args if isinstance(args, dict) else {}}, None

    content = (message or {}).get("content") or ""
    i, j = content.find("{"), content.rfind("}")
    if i < 0 or j <= i:
        return None, "no JSON object found in the reply (expected one object, got %r)" % content[:120]
    try:
        obj = json.loads(content[i:j + 1])
    except ValueError as e:
        return None, "the reply is not valid JSON (%s): %r" % (e, content[i:j + 1][:120])
    if not isinstance(obj, dict):
        return None, "expected a JSON object, got %s" % type(obj).__name__
    if "name" in obj and "tool" not in obj:            # the {"name","arguments"} spelling
        obj = {"tool": obj.get("name"), "args": obj.get("arguments") or obj.get("args") or {}}
    if "args" in obj and not isinstance(obj["args"], dict):
        if isinstance(obj["args"], str):
            try:
                obj["args"] = json.loads(obj["args"])
            except ValueError:
                return None, "args is neither an object nor a JSON string: %r" % str(obj["args"])[:120]
        else:
            return None, "args must be a JSON object, got %s" % type(obj["args"]).__name__
    return obj, None


# ── R3: the tool allowlist, and the tools themselves ─────────────────────────────────────────────
MAX_TOOL_OUTPUT = 4000     # tool results are truncated so one long file cannot blow the context


def _read(ws, args):
    p = ws.resolve(args.get("file_path") or args.get("path") or "")
    if not os.path.isfile(p):
        raise Refused("no such file: %s" % ws.rel(p))
    with open(p, errors="replace") as fh:
        lines = fh.read().splitlines()
    off = max(0, int(args.get("offset") or 0))
    lim = int(args.get("limit") or 400)
    body = "\n".join("%6d\t%s" % (off + i + 1, l) for i, l in enumerate(lines[off:off + lim]))
    more = "" if off + lim >= len(lines) else "\n... (%d more lines; use offset/limit)" % (len(lines) - off - lim)
    return (body + more) if body else "(the file is empty)"


def _write(ws, args):
    p = ws.resolve(args.get("file_path") or args.get("path") or "")
    content = args.get("content")
    if content is None:
        raise Refused("Write needs `content`")
    if not isinstance(content, str):
        content = json.dumps(content)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        fh.write(content)
    return "wrote %s (%d bytes)" % (ws.rel(p), len(content))


def _edit(ws, args):
    p = ws.resolve(args.get("file_path") or args.get("path") or "")
    old, new = args.get("old_string"), args.get("new_string")
    if old is None or new is None:
        raise Refused("Edit needs `old_string` and `new_string`")
    if not os.path.isfile(p):
        raise Refused("no such file: %s" % ws.rel(p))
    with open(p, errors="replace") as fh:
        body = fh.read()
    n = body.count(old)
    if n == 0:
        raise Refused("old_string not found in %s — Read it first and copy the text exactly" % ws.rel(p))
    if n > 1 and not args.get("replace_all"):
        raise Refused("old_string appears %d times in %s — make it unique or pass replace_all:true"
                      % (n, ws.rel(p)))
    with open(p, "w") as fh:
        fh.write(body.replace(old, new))
    return "edited %s (%d replacement%s)" % (ws.rel(p), n, "" if n == 1 else "s")


def _walk(ws, root, pattern=None):
    """Files under `root`, pruning .git — the repo's established tree-walk (pair_loop.py:60 cites
    gpl_stamp.py php_files() for the same prune)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            if pattern and not fnmatch(ws.rel(p), pattern) and not fnmatch(fn, pattern):
                continue
            yield p


def _grep(ws, args):
    pat = args.get("pattern")
    if not pat:
        raise Refused("Grep needs `pattern`")
    try:
        rx = re.compile(pat)
    except re.error as e:
        raise Refused("bad regex %r: %s" % (pat, e))
    root = ws.resolve(args.get("path") or ".")
    hits = []
    for p in _walk(ws, root if os.path.isdir(root) else os.path.dirname(root), args.get("glob")):
        try:
            with open(p, errors="replace") as fh:
                for n, line in enumerate(fh, 1):
                    if rx.search(line):
                        hits.append("%s:%d:%s" % (ws.rel(p), n, line.rstrip()[:200]))
                        if len(hits) >= 200:
                            return "\n".join(hits) + "\n... (truncated at 200 matches)"
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(hits) if hits else "(no matches)"


def _glob(ws, args):
    pat = args.get("pattern")
    if not pat:
        raise Refused("Glob needs `pattern`")
    root = ws.resolve(args.get("path") or ".")
    found = [ws.rel(p) for p in globlib.glob(os.path.join(root, pat), recursive=True)
             if ".git" not in os.path.relpath(p, ws.root).split(os.sep)]
    return "\n".join(sorted(found)[:200]) if found else "(no matches)"


def _bash(ws, args):
    cmd = args.get("command")
    if not cmd:
        raise Refused("Bash needs `command`")
    argv = ws.check_bash(cmd)
    r = subprocess.run(argv, cwd=ws.root, capture_output=True, text=True, timeout=ws.bash_timeout)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return "exit %s\n%s" % (r.returncode, out or "(no output)")


TOOLS = [
    {"name": "Read",
     "description": "Read a file from the workspace. Args: file_path (required), offset, limit.",
     "inputSchema": {"type": "object",
                     "properties": {"file_path": {"type": "string"},
                                    "offset": {"type": "integer"}, "limit": {"type": "integer"}},
                     "required": ["file_path"]},
     "handler": _read},
    {"name": "Write",
     "description": "Create or overwrite a file in the workspace. Args: file_path, content (both required).",
     "inputSchema": {"type": "object",
                     "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                     "required": ["file_path", "content"]},
     "handler": _write},
    {"name": "Edit",
     "description": "Replace old_string with new_string in a file. old_string must be unique unless "
                    "replace_all is true. Args: file_path, old_string, new_string, replace_all.",
     "inputSchema": {"type": "object",
                     "properties": {"file_path": {"type": "string"}, "old_string": {"type": "string"},
                                    "new_string": {"type": "string"}, "replace_all": {"type": "boolean"}},
                     "required": ["file_path", "old_string", "new_string"]},
     "handler": _edit},
    {"name": "Grep",
     "description": "Search file contents by regex. Args: pattern (required), path, glob.",
     "inputSchema": {"type": "object",
                     "properties": {"pattern": {"type": "string"}, "path": {"type": "string"},
                                    "glob": {"type": "string"}},
                     "required": ["pattern"]},
     "handler": _grep},
    {"name": "Glob",
     "description": "List files matching a glob pattern (e.g. '**/*.py'). Args: pattern (required), path.",
     "inputSchema": {"type": "object",
                     "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
                     "required": ["pattern"]},
     "handler": _glob},
    {"name": "Bash",
     "description": "Run a command in the workspace. Only allowlisted programs may be run, and the "
                    "command is NOT passed to a shell, so ';', '&&' and '|' do not chain. Args: command.",
     "inputSchema": {"type": "object", "properties": {"command": {"type": "string"}},
                     "required": ["command"]},
     "handler": _bash},
]
_BY_NAME = {t["name"]: t for t in TOOLS}
FINISH = "finish"


def parse_allowlist(spec):
    """pair_loop's --allowedTools string -> (names, bash_prefixes).

    The strings are pair_loop's own (pair_loop.py:704-705, :716-717), e.g.
        "Read,Grep,Glob,Write,Edit,Bash(python3:*),Bash(tooling/congruencey-harness/php/php:*)"
    A bare name grants the tool. `Bash(<prefix>:*)` grants Bash restricted to argv[0] == <prefix>;
    a bare `Bash` grants it unrestricted (pair_loop never does that, but the syntax means it).
    Parsed with a regex rather than split(',') because the parenthesised prefix carries punctuation
    of its own, and a name this module does not implement is DROPPED rather than trusted.

    Returns bash_prefixes = None for unrestricted, or a (possibly empty) list of allowed argv[0]s.
    """
    names, prefixes, bash_unrestricted = [], [], False
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(([^)]*)\))?", spec or ""):
        name, inner = m.group(1), m.group(2)
        if name not in _BY_NAME:
            continue
        if name not in names:
            names.append(name)
        if name == "Bash":
            if inner is None:
                bash_unrestricted = True
            else:
                prefixes.append(inner.rsplit(":", 1)[0] if ":" in inner else inner)
    return names, (None if bash_unrestricted else prefixes)


class Workspace:
    """The workspace boundary + the allowlist, enforced at call time.

    `root` is the directory the agent runs in — pair_loop hands its worker the ticket's git WORKTREE
    (a private second checkout of the ticket's branch, pair_loop.py:1559). Every path a tool touches
    is resolved and must land inside it."""

    def __init__(self, root, allowed_tools, bash_timeout=120):
        self.root = os.path.realpath(root)
        self.names, self.bash_prefixes = parse_allowlist(allowed_tools)
        self.bash_timeout = bash_timeout

    def rel(self, p):
        try:
            return os.path.relpath(os.path.realpath(p), self.root)
        except ValueError:
            return p

    def resolve(self, p):
        """Resolve a tool's path argument INSIDE the workspace, or refuse.

        realpath both sides, then compare with commonpath: that catches `..`, an absolute path, and
        a symlink pointing out. A prefix string compare would miss the symlink and would also
        mistake `/repo-evil` for a child of `/repo`."""
        if not p or not isinstance(p, str):
            raise Refused("a file path is required")
        full = os.path.realpath(p if os.path.isabs(p) else os.path.join(self.root, p))
        try:
            inside = os.path.commonpath([full, self.root]) == self.root
        except ValueError:
            inside = False
        if not inside:
            raise Refused("path %r is outside the workspace %s — refused (the ticket's mandate is to "
                          "touch only what it authorizes)" % (p, self.root))
        return full

    def check_bash(self, cmd):
        """Bash gating: argv[0] must be an allowlisted program. Returns the argv to run.

        shlex.split + shell=False on purpose. With shell=True, `python3 x.py ; rm -rf /` starts with
        an allowed prefix and would pass a naive gate while running a second, ungated command; with
        no shell there is no chaining — ';' is just a literal argument."""
        try:
            argv = shlex.split(cmd)
        except ValueError as e:
            raise Refused("could not parse the command (%s): %r" % (e, cmd))
        if not argv:
            raise Refused("empty command")
        if self.bash_prefixes is None:
            return argv
        if argv[0] not in self.bash_prefixes:
            raise Refused("Bash is restricted to %s — %r is not allowlisted (the allowlist grants "
                          "Bash(<program>:*) and argv[0] must match it exactly)"
                          % (", ".join(self.bash_prefixes) or "(nothing)", argv[0]))
        return argv

    def call(self, name, args):
        """Dispatch a tool call. This is the SECOND enforcement layer: only allowlisted tools are
        described to the model and the step enum is built from them, but a model can still emit a
        name it was never offered, so the allowlist is re-checked here."""
        if name not in self.names:
            raise Refused("tool %r is not allowlisted for this agent (allowed: %s)"
                          % (name, ", ".join(self.names) or "(none)"))
        t = _BY_NAME.get(name)
        if not t:
            raise Refused("unknown tool %r (known: %s)" % (name, ", ".join(sorted(_BY_NAME))))
        err = validate(args, t["inputSchema"], name)
        if err:
            raise Refused(err)
        return t["handler"](self, args)


def step_schema(ws):
    """The per-turn schema: one tool call, or `finish`. The `tool` enum is built from the ALLOWLIST,
    so the constrained decoder cannot even spell a tool the agent was not granted (R4 §5.1: express
    tool intents as schema-constrained JSON and sidestep Ollama's per-model tool parsing).

    `args` merges every allowed tool's properties, all optional: one object shape the grammar can
    compile, with the per-tool required-key check done by validate() at dispatch time."""
    props = {}
    for n in ws.names:
        props.update((_BY_NAME[n]["inputSchema"].get("properties") or {}))
    return {"type": "object",
            "properties": {"thought": {"type": "string"},
                           "tool": {"type": "string", "enum": ws.names + [FINISH]},
                           "args": {"type": "object", "properties": props}},
            "required": ["tool", "args"]}


def tools_payload(ws):
    """The allowlisted tools in Ollama's native `tools` shape — used only by --channel tools."""
    return [{"type": "function",
             "function": {"name": _BY_NAME[n]["name"], "description": _BY_NAME[n]["description"],
                          "parameters": _BY_NAME[n]["inputSchema"]}} for n in ws.names]


SYSTEM = """You are an autonomous software agent working inside a single workspace directory.

You act ONE STEP AT A TIME. Every reply is exactly one JSON object and nothing else:
  {"thought": "<why, one short line>", "tool": "<tool name>", "args": {<the tool's arguments>}}
The tool result comes back as the next message. Then you emit the next step. Repeat until done.

The ONLY tools that exist for you are these — any other name is refused:
%(tools)s
  finish — the task is complete. args: {}

Example of one step:
  {"thought": "read the file I must judge", "tool": "Read", "args": {"file_path": "docs/X.md"}}

Rules:
- Paths are relative to the workspace root. You cannot touch anything outside it.
- Do the work for real: read before you claim, and write the file you were asked to write.
- When the task is complete, emit {"thought": "...", "tool": "finish", "args": {}} and you will then
  be asked for your final answer.
"""


def system_prompt(ws):
    return SYSTEM % {"tools": "\n".join("  %s — %s" % (_BY_NAME[n]["name"], _BY_NAME[n]["description"])
                                        for n in ws.names)}


def chat(model, messages, fmt=None, tools=None, num_ctx=None, temperature=DEFAULT_TEMPERATURE,
         num_predict=1024, timeout=600, flavor="ollama", reasoning="agentic", max_tokens=None,
         openai_temperature=OPENAI_TEMPERATURE, openai_top_p=OPENAI_TOP_P):
    """One model turn, on either flavor. Returns Ollama's {"message": ...} envelope either way.

    ollama: /api/chat, with num_ctx ALWAYS set (R2 §4 affordance B) — never Ollama's 4096 default.
    openai: /v1/chat/completions. num_ctx/num_predict/temperature above are OLLAMA options and are
            NOT sent there — the openai flavor sends no `options` block at all (the server owns the
            context window) and carries its own max_tokens/temperature/top_p instead."""
    if flavor == "openai":
        return openai_chat(model, messages, fmt=fmt, tools=tools, max_tokens=max_tokens,
                           reasoning=reasoning, temperature=openai_temperature, top_p=openai_top_p,
                           timeout=timeout)
    body = {"model": model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_predict": num_predict,
                        "num_ctx": num_ctx or 8192}}
    if fmt is not None:
        body["format"] = fmt
    if tools:
        body["tools"] = tools
    return _ollama("/api/chat", body, timeout=timeout)


def constrained(model, messages, schema, retries, deadline, tools=None, num_predict=1024, label="step",
                flavor="ollama", reasoning="agentic", max_tokens=None,
                openai_temperature=OPENAI_TEMPERATURE, openai_top_p=OPENAI_TOP_P):
    """R4 §5.2 in one function: ask, extract (native -> content fallback), VALIDATE, and on failure
    feed the parser's own error back as a corrective turn and RETRY.

    R4 measured 100% conformance on this channel and then said, in §3, that N=20 gives only a ~83%
    Wilson lower bound and does NOT license removing this wrapper. So the wrapper is unconditional —
    and it is flavor-blind: the schema travels as Ollama's `format` or as OpenAI's `response_format`,
    but the VALIDATION and the corrective retry are the same code on both."""
    convo = list(messages)
    # num_ctx is an Ollama option; sizing it means asking Ollama about the model, which the openai
    # flavor must not do (there is no Ollama in that path, and /api/show would not answer for a
    # proxy alias).
    nctx = None
    if flavor != "openai":
        chars = sum(len(m.get("content") or "") for m in convo)
        nctx = num_ctx_for(model, chars + 2000)
    turn_reasoning = reasoning
    last = ""
    for attempt in range(retries + 1):
        left = deadline - time.time()
        if left <= 0:
            raise Unexpected("the agent exceeded its time budget (raise --timeout)")
        out = chat(model, convo, fmt=schema, tools=tools, num_ctx=nctx,
                   num_predict=num_predict, timeout=max(5, int(left)),
                   flavor=flavor, reasoning=turn_reasoning, max_tokens=max_tokens,
                   openai_temperature=openai_temperature, openai_top_p=openai_top_p)
        msg = (out or {}).get("message") or {}
        obj, err = extract_json(msg)
        if obj is None:
            last = err
        else:
            err = validate(obj, schema, label)
            if not err:
                return obj
            last = err
        log("   ! %s attempt %d/%d rejected: %s" % (label, attempt + 1, retries + 1, last))
        convo = convo + [
            {"role": "assistant", "content": msg.get("content") or json.dumps(obj or {})},
            {"role": "user", "content": "That reply was rejected: %s\nEmit ONE valid JSON object that "
                                        "matches the schema exactly. No prose, no code fences." % last},
        ]
        # A correction is "re-emit that, correctly shaped" — a deterministic reformat with the answer
        # already decided, which is exactly the cheap case. Local to this loop, so the caller's
        # policy for the NEXT turn is untouched.
        turn_reasoning = "cheap"
    raise Unexpected("%s: no schema-conformant reply from %s after %d attempts — last error: %s"
                     % (label, model, retries + 1, last))


def run_agent(prompt, allowed_tools, cwd=None, model=None, role=None, channel="schema",
              max_steps=12, retries=2, timeout=900, num_ctx=None, deliverable=None,
              flavor="ollama", max_tokens=None, openai_temperature=OPENAI_TEMPERATURE,
              openai_top_p=OPENAI_TOP_P):
    """Run one agent to completion and return its envelope dict — the value spawn_claude returns.

    The loop: act (tool calls) until the model finishes or --max-steps is spent, then ONE final
    schema-constrained call for the envelope. Identical on both flavors; only the transport and the
    role->model map differ."""
    ws = Workspace(os.path.realpath(cwd or os.getcwd()), allowed_tools)
    role = role or role_of(prompt)
    default_models = PROXY_ROLE_MODELS if flavor == "openai" else ROLE_MODELS
    model = model or default_models.get(role, default_models["worker"])
    env = ENVELOPES.get(role, ENVELOPES["worker"])
    deliverable = deliverable or deliverable_of(prompt)
    deadline = time.time() + timeout

    native_tools = None
    if flavor == "openai":
        # The proxy's own model list is the capability probe here (the openai counterpart of
        # /api/tags): a typo'd alias must be a one-line refusal, not a 400 mid-run. Best-effort —
        # if the route will not answer, the request itself is left to report the truth.
        served = proxy_models()
        if served and model not in served:
            raise Unexpected("model %r is not served by the OpenAI-compatible endpoint at %s (have: "
                             "%s) — check config/litellm/litellm_config.yaml, or pass --model/"
                             "--openai-model." % (model, OPENAI_BASE, ", ".join(sorted(served))))
        if channel == "tools":
            # Same OpenAI function-tool shape tools_payload() already emits; Cerebras accepts it and
            # replies with native tool_calls, which extract_json prefers.
            native_tools = tools_payload(ws)
        log("== ollama_agent == role=%s model=%s (%s) flavor=openai base=%s channel=%s tools=[%s] "
            "bash=%s max_tokens=%d cwd=%s"
            % (role, model, real_model(model), OPENAI_BASE, channel, ",".join(ws.names) or "none",
               "unrestricted" if ws.bash_prefixes is None else (",".join(ws.bash_prefixes) or "denied"),
               clamp_max_tokens(max_tokens), ws.root))
    else:
        caps = installed_models()
        if model not in caps:
            raise Unexpected("model %r is not installed in Ollama at %s (have: %s) — run `ollama pull %s`"
                             % (model, OLLAMA, ", ".join(sorted(caps)) or "none", model))
        if channel == "tools":
            # R4 §2/§5.4: gemma3 advertises no "tools" capability and hard-errors on a tools array.
            if "tools" not in (caps.get(model) or []):
                raise Unexpected("--channel tools was requested but %r does not support Ollama's tools API "
                                 "(capabilities: %s). Use the default --channel schema, which carries tool "
                                 "calls as schema-constrained JSON and works on every model (research "
                                 "#175 §5.1)." % (model, ", ".join(caps.get(model) or []) or "none"))
            native_tools = tools_payload(ws)

        log("== ollama_agent == role=%s model=%s flavor=ollama channel=%s tools=[%s] bash=%s ctx<=%d cwd=%s"
            % (role, model, channel, ",".join(ws.names) or "none",
               "unrestricted" if ws.bash_prefixes is None else (",".join(ws.bash_prefixes) or "denied"),
               context_cap(model), ws.root))

    messages = [{"role": "system", "content": system_prompt(ws)},
                {"role": "user", "content": prompt}]
    schema = step_schema(ws)
    steps, corrections = 0, 0
    while steps < max_steps:
        steps += 1
        stp = constrained(model, messages, schema, retries, deadline, tools=native_tools,
                          num_predict=1024, label="step %d" % steps, flavor=flavor,
                          reasoning="agentic", max_tokens=max_tokens,
                          openai_temperature=openai_temperature, openai_top_p=openai_top_p)
        name, args = stp.get("tool"), stp.get("args") or {}
        messages.append({"role": "assistant", "content": json.dumps(stp)})

        if name == FINISH:
            # "a real, verified deliverable": a worker that reports done without having written the
            # file it was told to write is corrected and sent back to work, rather than let through
            # to a commit pair_loop would refuse anyway (pair_loop.py:485).
            if role == "worker" and deliverable and corrections < 2 \
                    and not os.path.isfile(os.path.join(ws.root, deliverable)):
                corrections += 1
                log("   ! finish refused: %s does not exist yet" % deliverable)
                messages.append({"role": "user", "content":
                                 "You cannot finish: the deliverable %s does not exist in the "
                                 "workspace. Write it with the Write tool, then finish." % deliverable})
                continue
            log("   . finish after %d step(s)" % steps)
            break

        log("   . step %d: %s %s" % (steps, name, json.dumps(args)[:120]))
        try:
            result = ws.call(name, args)
        except Refused as e:
            result = "REFUSED: %s" % e
            log("   ! refused: %s" % e)
        except subprocess.TimeoutExpired:
            result = "REFUSED: the command exceeded its %ss budget" % ws.bash_timeout
        except Exception as e:  # noqa: BLE001  — a tool fault is a RESULT the model can react to
            result = "ERROR: %s: %s" % (type(e).__name__, e)
        if len(result) > MAX_TOOL_OUTPUT:
            result = result[:MAX_TOOL_OUTPUT] + "\n... (truncated at %d chars)" % MAX_TOOL_OUTPUT
        messages.append({"role": "user", "content": "TOOL RESULT (%s):\n%s" % (name, result)})
    else:
        log("   ! --max-steps (%d) reached; asking for the envelope now" % max_steps)

    messages.append({"role": "user", "content":
                     "Stop using tools. Emit your FINAL answer now as ONE JSON object of exactly "
                     "this shape:\n%s\nNo prose, no code fences, no extra keys." % env["describe"]})
    envelope = constrained(model, messages, env["schema"], retries, deadline,
                           num_predict=1024, label="envelope", flavor=flavor,
                           reasoning=ENVELOPE_REASONING.get(role, "agentic"), max_tokens=max_tokens,
                           openai_temperature=openai_temperature, openai_top_p=openai_top_p)

    if role == "worker":
        if deliverable and not envelope.get("ref"):
            envelope["ref"] = deliverable
        if deliverable and not os.path.isfile(os.path.join(ws.root, deliverable)):
            # Truth over politeness: the envelope must not claim a file that is not there.
            raise Unexpected("the agent reported done but %s does not exist in %s — refusing to "
                             "report a deliverable that was never written" % (deliverable, ws.root))
    return envelope


# ── governance: register the agent + journal the run through the governed routes ──────────────────
def register(agent_id, prompt, tool_names, model, role, channel, flavor="ollama"):
    """agent.register (migrations/0001_agents.sql:19-25). The route is INSERT OR REPLACE, so
    re-registering an id pair_loop already created UPDATES that row with the model that actually ran
    — it erases nothing and adds no row the loop did not expect.

    On the openai flavor the recorded model is the RESOLVED one — "cerebras/zai-glm-4.7", not the
    "worker" alias that was requested — so the record names what really answered, which is the whole
    point of registering it (the alias is kept alongside, since it is what was asked for)."""
    if flavor == "openai":
        tags = ["openai:%s" % real_model(model), "proxy-alias:%s" % model, "base:%s" % OPENAI_BASE]
    else:
        tags = ["ollama:%s" % model]
    rest("agent.register", {"agent_id": agent_id, "parent": "ollama_agent", "prompt": prompt,
                            "tools": json.dumps(tags + ["role:%s" % role, "channel:%s" % channel]
                                                + list(tool_names))})


def journal(ticket_id, agent_id, note, steps_remaining=None):
    """ticket.progress (migrations/0029_ticket_authorization.sql:193-198) — the append-only journal."""
    body = {"ticket_id": ticket_id, "agent_id": agent_id, "note": note}
    if steps_remaining is not None:
        body["steps_remaining"] = steps_remaining
    rest("ticket.progress", body)


def governed_run(prompt, allowed_tools, a, cwd=None):
    """One agent run WITH the governance the ticket requires: register before, journal after."""
    role = a.role or role_of(prompt)
    flavor = getattr(a, "flavor", None) or "ollama"
    default_models = PROXY_ROLE_MODELS if flavor == "openai" else ROLE_MODELS
    model = a.model or default_models.get(role, default_models["worker"])
    tid = a.ticket or ticket_of(prompt)
    aid = a.agent_id or agent_of(prompt) or "ollama-agent"
    names, _ = parse_allowlist(allowed_tools)

    govern = not a.no_journal
    if govern and not API_KEY:
        raise Unexpected("no CONGRUENCY_API_KEY (checked $CONGRUENCY_API_KEY and %s) — the governed "
                         "routes need it to register and journal this run. Set the key, or pass "
                         "--no-journal to run ungoverned."
                         % os.path.join(os.path.dirname(ROOT), ".secrets", "ats.env"))
    if not govern:
        log("== ollama_agent == --no-journal: NOT registering or journaling this run (ungoverned)")

    # What ACTUALLY answers: the resolved model on the openai flavor ("cerebras/zai-glm-4.7"), the
    # model name itself on ollama. This is what the record and the journal name.
    ran = real_model(model) if flavor == "openai" else model

    if govern:
        register(aid, prompt, names, model, role, a.channel, flavor=flavor)
        log("== governed == registered %s via agent.register (model %s)" % (aid, ran))
        if tid:
            journal(tid, aid, "ollama_agent: %s starting on ticket #%d (model %s, flavor %s, channel "
                              "%s, tools: %s)" % (role, tid, ran, flavor, a.channel, ", ".join(names) or "none"))
        else:
            log("== governed == no ticket id in the prompt — registered, but nothing to journal against")

    t0 = time.time()
    try:
        envelope = run_agent(prompt, allowed_tools, cwd=cwd, model=model, role=role,
                             channel=a.channel, max_steps=a.max_steps, retries=a.retries,
                             timeout=a.timeout, num_ctx=a.num_ctx, deliverable=a.deliverable,
                             flavor=flavor, max_tokens=getattr(a, "max_tokens", None),
                             openai_temperature=getattr(a, "openai_temperature", OPENAI_TEMPERATURE),
                             openai_top_p=getattr(a, "openai_top_p", OPENAI_TOP_P))
    except Exception as e:  # noqa: BLE001
        if govern and tid:
            try:
                journal(tid, aid, "ollama_agent: %s FAILED after %.1fs — %s" % (role, time.time() - t0, e))
            except Exception:  # noqa: BLE001
                pass
        raise
    if govern and tid:
        journal(tid, aid, "ollama_agent: %s finished in %.1fs on %s — %s"
                % (role, time.time() - t0, ran, json.dumps(envelope)[:300]))
    return envelope


# ── ENGINE MODE: --engine ollama|claude, with no edit to pair_loop.py ─────────────────────────────
def load_pair_loop():
    """Import the sibling pair_loop.py by path — the repo's established way of loading a sibling
    module (tracker/signals-mcp/server.py:31-35, _load_store()).

    dont_write_bytecode is forced for the duration of the import: importing a module normally makes
    CPython drop a `__pycache__/pair_loop.cpython-*.pyc` next to the source, i.e. a NEW FILE inside
    this repo. --selftest calls this and claims it "touches this repo not at all", and a claim about
    behavior has to be made true by the code rather than softened in the prose (#153). The flag is
    restored afterwards, so nothing else's caching behavior changes."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pair_loop.py")
    if not os.path.isfile(p):
        raise Unexpected("pair_loop.py not found next to this tool (%s) — --engine drives it" % p)
    spec = importlib.util.spec_from_file_location("pair_loop", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules["pair_loop"] = m
    prev = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(m)
    finally:
        sys.dont_write_bytecode = prev
    return m


def make_spawn(pl, a):
    """Build the spawn_claude-shaped callable pair_loop will use.

    Signature and return value match pair_loop.spawn_claude(prompt, allowed_tools, timeout, cwd=None)
    -> dict (pair_loop.py:723-741) exactly, because pair_loop calls it POSITIONALLY at :789 (dispatch),
    :1559 (worker) and :1576 (adversary). Errors are re-raised as pair_loop's OWN Unexpected so its
    handler (:1646) catches them as it would any harness fault."""
    def spawn_ollama(prompt, allowed_tools, timeout, cwd=None):
        b = argparse.Namespace(**vars(a))
        b.timeout = timeout                       # pair_loop's --timeout governs each spawn
        b.ticket, b.agent_id, b.role, b.deliverable = None, None, None, None   # read from the prompt
        try:
            return governed_run(prompt, allowed_tools, b, cwd=cwd)
        except Unexpected as e:
            raise pl.Unexpected(str(e))
    return spawn_ollama


def parse_engine_args(argv):
    """Split an engine-mode command line into (our options, pair_loop's argv).

    A SEPARATE parser, on purpose. Agent mode's parser owns --ticket, --deliverable and --timeout,
    and pair_loop owns options by those same names (pair_loop.py:1415-1448). If one parser handled
    both, `--engine ollama --ticket 176 --deliverable docs/X.md` would have its --ticket and
    --deliverable swallowed here and pair_loop.main() would die on "--ticket N or --file KIND
    required" — a documented invocation that cannot run. So in engine mode we keep ONLY --engine and
    the --ollama-* tuning flags, and everything else is passed through untouched.

    add_help=False so `--engine ollama --help` prints pair_loop's help, which is the help that
    describes the arguments actually in force."""
    eap = argparse.ArgumentParser(prog="ollama_agent.py --engine", add_help=False)
    eap.add_argument("--engine", choices=("ollama", "claude", "cerebras"), required=True)
    eap.add_argument("--ollama-model", dest="model")
    eap.add_argument("--ollama-channel", dest="channel", choices=("schema", "tools"), default="schema")
    eap.add_argument("--ollama-num-ctx", dest="num_ctx", type=int)
    eap.add_argument("--ollama-max-steps", dest="max_steps", type=int, default=12)
    eap.add_argument("--ollama-retries", dest="retries", type=int, default=2)
    eap.add_argument("--ollama-no-journal", dest="no_journal", action="store_true")
    # --engine cerebras knobs. A separate dest from --ollama-model so the two can never quietly
    # overwrite each other; the cerebras engine reads openai_model, the ollama engine reads model.
    eap.add_argument("--openai-model", dest="openai_model")
    eap.add_argument("--openai-base", dest="openai_base")
    eap.add_argument("--openai-max-tokens", dest="max_tokens", type=int, default=GLM_MAX_TOKENS)
    eap.add_argument("--openai-temperature", dest="openai_temperature", type=float,
                     default=OPENAI_TEMPERATURE)
    eap.add_argument("--openai-top-p", dest="openai_top_p", type=float, default=OPENAI_TOP_P)
    a, rest = eap.parse_known_args(argv)
    # There is deliberately no --ollama-role: the loop spawns a WORKER and then an ADVERSARY, so the
    # role is per-spawn and is always read from each birth prompt (make_spawn resets it). A single
    # role forced across both spawns would be wrong, so the flag does not exist rather than exist
    # and be ignored. --ollama-model IS honored for every spawn, which is the caller's explicit
    # choice to override research #173's role->model map (including its different-family rule).
    a.role = None
    # Per-spawn: pair_loop passes its own --timeout to spawn_claude, and make_spawn honors it.
    a.timeout, a.ticket, a.agent_id, a.deliverable = 900, None, None, None
    a.prompt, a.allowed_tools, a.cwd = None, None, None
    a.selftest, a.probe = False, False
    # --engine cerebras IS --engine ollama with the api flavor and the role->model map swapped: same
    # rebind, same runner, same governance. That is the whole difference, and it lives here.
    a.flavor = "openai" if a.engine == "cerebras" else "ollama"
    if a.engine == "cerebras":
        a.model = a.openai_model            # None => PROXY_ROLE_MODELS picks per role (worker->GLM 4.7)
        if a.openai_base:
            globals()["OPENAI_BASE"] = a.openai_base.rstrip("/")
    return a, rest


def engine_mode(a, rest_argv):
    """--engine ollama: rebind pair_loop's spawn_claude, then hand control to pair_loop.main().

    The rebind works — and needs no edit to pair_loop.py — because pair_loop resolves `spawn_claude`
    from its module globals at CALL time, not at import time: it is passed by name to step() at
    :565, :1046 and :1067. Setting the module attribute before main() runs therefore redirects every
    agent the loop spawns. --engine claude rebinds nothing and is the stock loop."""
    pl = load_pair_loop()
    if a.engine == "cerebras":
        pl.spawn_claude = make_spawn(pl, a)
        log("== engine == cerebras: pair_loop.spawn_claude -> ollama_agent (openai flavor at %s; the "
            "CODER WORKER runs %s -> %s; adversary %s, dispatch %s)"
            % (OPENAI_BASE, PROXY_ROLE_MODELS["worker"], real_model(PROXY_ROLE_MODELS["worker"]),
               PROXY_ROLE_MODELS["adversary"], PROXY_ROLE_MODELS["dispatch"]))
    elif a.engine == "ollama":
        pl.spawn_claude = make_spawn(pl, a)
        log("== engine == ollama: pair_loop.spawn_claude -> ollama_agent (worker, adversary and "
            "dispatch all run on local models; role->model per research #173)")
    else:
        log("== engine == claude: pair_loop unchanged (stock `claude -p`)")
    sys.argv = ["pair_loop.py"] + rest_argv
    try:
        return pl.main()
    except pl.Unexpected as e:
        pl.bug_report("main", e, "python3 ollama_agent.py --engine %s %s" % (a.engine, " ".join(rest_argv)), e)
        print("UNEXPECTED: %s" % e)
        return 2


# ── --probe: what the backend has here, and what this module would do with it ─────────────────────
def probe(flavor="ollama"):
    """--probe (ollama) / --probe --api-flavor openai (the proxy). Read-only: it lists models and the
    role->model map and runs no agent."""
    if flavor == "openai":
        try:
            served = proxy_models(refresh=True)
        except Unexpected as e:
            print("ollama_agent: %s" % e, file=sys.stderr)
            return 2
        print("== openai-compat == %s%s" % (OPENAI_BASE, "  (auth: Bearer from env)" if PROXY_KEY else ""))
        if not served:
            print("   (the endpoint answered nothing for /v1/model/info — is the litellm proxy up? "
                  "config/litellm/start.sh)")
        for alias in sorted(served):
            print("   %-22s -> %s" % (alias, served[alias]))
        print("== role -> model (the proxy's aliases) ==")
        for role, model in PROXY_ROLE_MODELS.items():
            print("   %-10s -> %-22s %s" % (role, model,
                                            ("ok -> %s" % real_model(model)) if model in served
                                            else "MISSING — no such model_name in litellm_config.yaml"))
        return 0 if served and all(m in served for m in PROXY_ROLE_MODELS.values()) else 1
    try:
        caps = installed_models()
    except Unexpected as e:
        print("ollama_agent: %s" % e, file=sys.stderr)
        return 2
    print("== ollama == %s" % OLLAMA)
    for name in sorted(caps):
        print("   %-28s ctx=%-7s caps=%s" % (name, context_cap(name), ",".join(caps[name]) or "-"))
    print("== role -> model (research #173 §1) ==")
    for role, model in ROLE_MODELS.items():
        print("   %-10s -> %-22s %s" % (role, model,
                                        "ok" if model in caps else "MISSING — run `ollama pull %s`" % model))
    return 0 if all(m in caps for m in ROLE_MODELS.values()) else 1


# ── --selftest: prove the contract in a THROWAWAY temp dir (no db, no network, no Ollama) ─────────
def selftest():
    """Every check runs offline against a temp workspace that is deleted afterwards. Nothing here
    touches this repo, the db, Ollama, or the network."""
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name, ("  — %s" % detail) if detail and not cond else ""))

    base = tempfile.mkdtemp(prefix="ollama_agent-selftest-")
    try:
        os.makedirs(os.path.join(base, "docs"))
        open(os.path.join(base, "docs", "seed.md"), "w").write("hello\nworld\n")
        print("== selftest == throwaway workspace %s" % base)

        # ── the allowlist is parsed from pair_loop's own strings ──
        print("-- allowlist (R3): only allowlisted tools exist")
        spec = "Read,Grep,Glob,Write,Edit,Bash(python3:*),Bash(tooling/congruencey-harness/php/php:*)"
        names, prefixes = parse_allowlist(spec)
        ck("pair_loop's build worker_tools parse to its 6 tools",
           names == ["Read", "Grep", "Glob", "Write", "Edit", "Bash"], str(names))
        ck("Bash(<prefix>:*) yields both prefixes",
           prefixes == ["python3", "tooling/congruencey-harness/php/php"], str(prefixes))
        ro_names, ro_pref = parse_allowlist("Read,Grep,Glob")
        ck("the documentation auditor's allowlist grants no Write/Edit/Bash",
           ro_names == ["Read", "Grep", "Glob"] and ro_pref == [], str((ro_names, ro_pref)))
        ck("an unknown tool name in the spec is dropped, not trusted",
           parse_allowlist("Read,Nonsense,WebFetch")[0] == ["Read"], str(parse_allowlist("Read,Nonsense")[0]))
        ck("bare Bash means unrestricted (pair_loop never grants it; the syntax means it)",
           parse_allowlist("Bash")[1] is None)

        ws = Workspace(base, spec)
        rw = Workspace(base, "Read,Grep,Glob")

        # ── enforcement layer 2: refused at dispatch even if the model invents the name ──
        print("-- enforcement: a non-allowlisted call is REFUSED, not run")
        try:
            rw.call("Write", {"file_path": "docs/x.md", "content": "nope"})
            ck("a read-only agent cannot Write", False, "the call was allowed")
        except Refused as e:
            ck("a read-only agent cannot Write", "not allowlisted" in str(e), str(e))
        ck("...and the refused Write created no file", not os.path.exists(os.path.join(base, "docs", "x.md")))
        try:
            ws.call("WebFetch", {"url": "http://example.com"})
            ck("a tool that was never offered is refused", False, "the call was allowed")
        except Refused as e:
            ck("a tool that was never offered is refused", "not allowlisted" in str(e), str(e))
        ck("the step schema's enum contains ONLY the allowlist + finish",
           step_schema(rw)["properties"]["tool"]["enum"] == ["Read", "Grep", "Glob", FINISH],
           str(step_schema(rw)["properties"]["tool"]["enum"]))

        # ── the workspace boundary ──
        print("-- workspace boundary: no path escapes the worktree")
        for bad in ("../escape.txt", "/etc/passwd", "docs/../../escape.txt"):
            try:
                ws.resolve(bad)
                ck("path %r is refused" % bad, False, "it resolved")
            except Refused:
                ck("path %r is refused" % bad, True)
        ck("a legitimate path inside the workspace resolves",
           ws.resolve("docs/seed.md") == os.path.realpath(os.path.join(base, "docs", "seed.md")))

        # ── Bash gating ──
        print("-- Bash gating: argv[0] must be allowlisted; no shell, so no chaining")
        ck("an allowlisted program is accepted", ws.check_bash("python3 -c 'print(1)'")[0] == "python3")
        for bad in ("rm -rf /", "bash -c 'echo hi'", "/bin/sh"):
            try:
                ws.check_bash(bad)
                ck("Bash refuses %r" % bad, False, "it was allowed")
            except Refused:
                ck("Bash refuses %r" % bad, True)
        argv = ws.check_bash("python3 -c 'pass' ; rm -rf /")
        ck("a chained command does NOT become two commands (shell=False)",
           argv[0] == "python3" and ";" in argv and "rm" in argv, str(argv))
        out = ws.call("Bash", {"command": "python3 -c 'print(6*7)'"})
        ck("Bash actually runs an allowlisted program", "42" in out, out)
        try:
            rw.call("Bash", {"command": "python3 -c 'print(1)'"})
            ck("an agent without Bash cannot run anything", False, "it ran")
        except Refused:
            ck("an agent without Bash cannot run anything", True)

        # ── the tools themselves ──
        print("-- tools: Read/Write/Edit/Grep/Glob do what they say")
        ck("Read returns numbered lines", "hello" in ws.call("Read", {"file_path": "docs/seed.md"}))
        ws.call("Write", {"file_path": "docs/new.md", "content": "alpha\nbeta\n"})
        ck("Write creates the file", open(os.path.join(base, "docs", "new.md")).read() == "alpha\nbeta\n")
        ws.call("Edit", {"file_path": "docs/new.md", "old_string": "alpha", "new_string": "ALPHA"})
        ck("Edit replaces the text", open(os.path.join(base, "docs", "new.md")).read() == "ALPHA\nbeta\n")
        try:
            ws.call("Edit", {"file_path": "docs/new.md", "old_string": "nope", "new_string": "x"})
            ck("Edit refuses a missing old_string", False, "it was allowed")
        except Refused as e:
            ck("Edit refuses a missing old_string", "not found" in str(e), str(e))
        ck("Grep finds a match", "docs/seed.md:2:world" in ws.call("Grep", {"pattern": "^world"}))
        ck("Grep with no match says so", ws.call("Grep", {"pattern": "zzzz-not-here"}) == "(no matches)")
        ck("Glob lists files", "docs/new.md" in ws.call("Glob", {"pattern": "docs/*.md"}))
        try:
            ws.call("Read", {"file_path": "docs/missing.md"})
            ck("Read refuses a missing file with a message, not a traceback", False, "it was allowed")
        except Refused as e:
            ck("Read refuses a missing file with a message, not a traceback", "no such file" in str(e))
        try:
            ws.call("Read", {})
            ck("a call missing a required arg is refused by the validator", False, "it was allowed")
        except Refused as e:
            ck("a call missing a required arg is refused by the validator", "required" in str(e), str(e))

        # ── R4 §5.2: the extractor ladder ──
        print("-- R4 extractor: native tool_calls -> content fallback -> both spellings")
        native = {"tool_calls": [{"function": {"name": "Read", "arguments": {"file_path": "a.md"}}}]}
        ck("native tool_calls are preferred (the qwen3-coder path)",
           extract_json(native)[0] == {"tool": "Read", "args": {"file_path": "a.md"}}, str(extract_json(native)))
        strargs = {"tool_calls": [{"function": {"name": "Read", "arguments": '{"file_path": "a.md"}'}}]}
        ck("tool_calls with string-serialized arguments still parse",
           extract_json(strargs)[0] == {"tool": "Read", "args": {"file_path": "a.md"}}, str(extract_json(strargs)))
        content = {"content": 'Sure!\n{"name":"Read","arguments":{"file_path":"a.md"}}\nDone.'}
        ck("a tool call stranded in content is recovered (the qwen2.5-coder 0%->100% path)",
           extract_json(content)[0] == {"tool": "Read", "args": {"file_path": "a.md"}}, str(extract_json(content)))
        ck("the {tool,args} spelling parses too",
           extract_json({"content": '{"tool":"Grep","args":{"pattern":"x"}}'})[0]
           == {"tool": "Grep", "args": {"pattern": "x"}})
        ck("fenced JSON is recovered (first '{' .. last '}')",
           extract_json({"content": '```json\n{"tool":"finish","args":{}}\n```'})[0]
           == {"tool": "finish", "args": {}})
        ck("no JSON at all is an ERROR STRING, not an exception",
           extract_json({"content": "I cannot help"})[1] is not None)
        ck("malformed JSON is an error string, not an exception",
           extract_json({"content": '{"tool": "Read",,}'})[1] is not None)

        # ── R4 §5.2 step 3: the strict validator ──
        print("-- R4 validator: types, required, enum, int-not-string")
        wsch, asch, dsch = (ENVELOPES["worker"]["schema"], ENVELOPES["adversary"]["schema"],
                            ENVELOPES["dispatch"]["schema"])
        ck("a good worker envelope validates",
           validate({"done": True, "ref": "x.py", "note": "n"}, wsch) is None)
        ck("a missing key is caught", "missing required key" in (validate({"done": True, "ref": "x"}, wsch) or ""))
        ck('done:"true" (a string) is caught, not coerced',
           "expected a boolean" in (validate({"done": "true", "ref": "x", "note": "n"}, wsch) or ""))
        ck("a bad verdict enum value is caught",
           "is not one of" in (validate({"verdict": "maybe", "findings": []}, asch) or ""))
        ck("a good adversary envelope validates",
           validate({"verdict": "fail", "findings": ["a", "b"]}, asch) is None)
        ck("findings must be strings",
           "expected a string" in (validate({"verdict": "fail", "findings": [1]}, asch) or ""))
        ck('ticket:"4821" (R4 App B\'s real gemma3 failure) is caught',
           "expected an integer" in (validate({"plan": [{"ticket": "4821", "action": "run", "reason": "r"}]}, dsch) or ""))
        ck("a good dispatch plan validates",
           validate({"plan": [{"ticket": 1, "action": "skip", "reason": "r"}]}, dsch) is None)
        ck("true is not accepted as an integer (bool is not int here)",
           "expected an integer" in (validate({"plan": [{"ticket": True, "action": "run", "reason": "r"}]}, dsch) or ""))

        # ── the envelopes are the shapes pair_loop actually reads ──
        print("-- envelopes match what pair_loop reads off the last line")
        ck("worker envelope carries done/ref/note (pair_loop.py:1560,:1563)",
           set(wsch["properties"]) == {"done", "ref", "note"})
        ck("adversary envelope carries verdict/findings (pair_loop.py:1579,:1582)",
           set(asch["properties"]) == {"verdict", "findings"})
        ck("dispatch envelope carries a plan (pair_loop.py:790)", "plan" in dsch["properties"])

        # ── reading the birth prompt pair_loop builds ──
        print("-- the birth prompt is parsed for role / ticket / agent / deliverable")
        wp = ("You are coder-t176r1, the coder — the worker of a build pair on ticket #176.\n\n"
              "TICKET: Build: Ollama agent adapter\n\n"
              "Deliverable: write it to checkouts/current/congruency/tools/ollama_agent.py (create or "
              "overwrite that file; touch nothing else).\n"
              "GOVERNANCE: ticket #176 authorizes you — work on nothing else. You are registered as "
              "coder-t176r1 and every action is on the record.")
        ap_ = ("You are tester-t176r1, the tester — the adversary of a build pair on ticket #176.\n\n"
               "The worker produced checkouts/current/congruency/tools/ollama_agent.py. You did NOT see "
               "the worker's reasoning.\nGOVERNANCE: ticket #176 authorizes you — work on nothing else. "
               "You are registered as tester-t176r1 and every action is on the record.")
        ck("the worker prompt reads as role=worker", role_of(wp) == "worker", role_of(wp))
        ck("the adversary prompt reads as role=adversary", role_of(ap_) == "adversary", role_of(ap_))
        ck("the ticket id is read from GOVERNANCE", ticket_of(wp) == 176 and ticket_of(ap_) == 176)
        ck("the agent id is read from GOVERNANCE", agent_of(wp) == "coder-t176r1", str(agent_of(wp)))
        ck("the adversary's agent id is read", agent_of(ap_) == "tester-t176r1", str(agent_of(ap_)))
        ck("the deliverable is read from the worker prompt",
           deliverable_of(wp) == "checkouts/current/congruency/tools/ollama_agent.py", str(deliverable_of(wp)))
        ck("the deliverable is read from the adversary prompt too",
           deliverable_of(ap_) == "checkouts/current/congruency/tools/ollama_agent.py", str(deliverable_of(ap_)))
        ck("role -> model is research #173's mapping",
           ROLE_MODELS["worker"] == "qwen2.5-coder:7b" and ROLE_MODELS["adversary"] == "gemma3:27b"
           and ROLE_MODELS["dispatch"] == "gemma3:27b", str(ROLE_MODELS))
        ck("worker and adversary are DIFFERENT model families (research #173 §5.4)",
           ROLE_MODELS["worker"].split(":")[0].rstrip("0123456789.-")
           != ROLE_MODELS["adversary"].split(":")[0].rstrip("0123456789.-"))
        ck("gemma3:4b is the default for NO role (research #173 §5.2 excludes it)",
           "gemma3:4b" not in ROLE_MODELS.values())

        # ── R2 §4 affordance B: num_ctx is never Ollama's 4096 default ──
        print("-- R2 num_ctx: always set, sized to payload, capped at the model's real context")
        _CTX_CACHE["fake:test"] = 32768
        ck("a small payload still gets at least the 8192 floor, never 4096",
           num_ctx_for("fake:test", 100) == 8192, str(num_ctx_for("fake:test", 100)))
        ck("a big payload scales up (~4 chars/token + headroom)",
           num_ctx_for("fake:test", 80000) > 8192, str(num_ctx_for("fake:test", 80000)))
        ck("num_ctx never exceeds the model's real context length",
           num_ctx_for("fake:test", 10 ** 7) == 32768, str(num_ctx_for("fake:test", 10 ** 7)))
        ck("--num-ctx overrides the sizing", num_ctx_for("fake:test", 100, override=16384) == 16384)
        _CTX_CACHE.pop("fake:test", None)

        # ── the engine selector: the rebind is real, and pair_loop is not edited ──
        print("-- --engine: the selector works by rebinding, with no edit to pair_loop.py")
        try:
            pl = load_pair_loop()
            stock = pl.spawn_claude
            ck("pair_loop.py imports and exposes spawn_claude", callable(stock))
            a = argparse.Namespace(engine="ollama", model=None, role=None, channel="schema",
                                   max_steps=4, retries=2, timeout=60, num_ctx=None,
                                   no_journal=True, ticket=None, agent_id=None, deliverable=None)
            pl.spawn_claude = make_spawn(pl, a)
            ck("--engine ollama rebinds pair_loop.spawn_claude", pl.spawn_claude is not stock)
            import inspect
            sig = list(inspect.signature(pl.spawn_claude).parameters)
            ck("the replacement takes spawn_claude's exact arguments",
               sig == ["prompt", "allowed_tools", "timeout", "cwd"], str(sig))
            ck("...and pair_loop calls spawn_claude by that same 4-arg shape",
               list(inspect.signature(stock).parameters) == sig, str(list(inspect.signature(stock).parameters)))
            pl.spawn_claude = stock
            ck("--engine claude leaves the stock spawn in place", pl.spawn_claude is stock)

            # The #151 trap, locked down: agent mode and pair_loop BOTH have --ticket/--deliverable/
            # --timeout. If engine mode shared agent mode's parser it would swallow them and
            # pair_loop.main() would die on "--ticket N or --file KIND required" — the documented
            # invocation would not run. These assert the passthrough is real.
            ea, erest = parse_engine_args(["--engine", "ollama", "--ticket", "176",
                                           "--deliverable", "docs/X.md"])
            ck("--engine ollama --ticket 176 --deliverable docs/X.md reaches pair_loop INTACT",
               ea.engine == "ollama" and erest == ["--ticket", "176", "--deliverable", "docs/X.md"],
               str(erest))
            ea2, erest2 = parse_engine_args(["--engine", "claude", "--dispatch", "3", "--parallel", "2",
                                             "--timeout", "480", "--rounds", "2", "--base", "main"])
            ck("pair_loop's dispatch/timeout/rounds/base all pass through untouched",
               erest2 == ["--dispatch", "3", "--parallel", "2", "--timeout", "480",
                          "--rounds", "2", "--base", "main"], str(erest2))
            ea3, erest3 = parse_engine_args(["--engine", "ollama", "--ollama-model", "qwen3-coder:latest",
                                             "--ollama-channel", "tools", "--ollama-no-journal",
                                             "--ticket", "9"])
            ck("the --ollama-* tuning flags are consumed here and NOT leaked to pair_loop",
               ea3.model == "qwen3-coder:latest" and ea3.channel == "tools" and ea3.no_journal
               and erest3 == ["--ticket", "9"], str((ea3.model, ea3.channel, erest3)))
            ck("--engine claude --selftest passes --selftest to pair_loop (not this module's)",
               parse_engine_args(["--engine", "claude", "--selftest"])[1] == ["--selftest"])
            ck("pair_loop.py was NOT modified by this ticket (it carries no --engine of its own)",
               "--engine" not in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   "pair_loop.py")).read(),
               "pair_loop.py contains --engine — this ticket must not touch that file")
        except Exception as e:  # noqa: BLE001
            ck("the --engine checks ran", False, "%s: %s" % (type(e).__name__, e))

        # ── ticket #411: the openai flavor, proven OFFLINE against an in-process stub ──
        # Every openai request goes through _openai_post, so replacing that one name puts the whole
        # request/response mapping under test with no proxy, no network and no key.
        print("-- openai flavor (#411): the request shape sent to /v1/chat/completions")
        sent = []
        MODEL_INFO = {"data": [{"model_name": "worker", "litellm_params": {"model": "cerebras/zai-glm-4.7"}},
                               {"model_name": "cerebras-gpt-oss", "litellm_params": {"model": "cerebras/gpt-oss-120b"}},
                               {"model_name": "dispatch", "litellm_params": {"model": "cerebras/gpt-oss-120b"}}]}

        def reply(content, finish="stop", reasoning="thinking...", tool_calls=None, usage=None):
            msg = {"role": "assistant", "content": content, "reasoning_content": reasoning}
            if tool_calls is not None:
                msg["tool_calls"] = tool_calls
            return {"choices": [{"finish_reason": finish, "index": 0, "message": msg}],
                    "model": "worker", "usage": usage or {"completion_tokens": 25}}

        scripted = []

        def stub(path, body=None, timeout=600):
            sent.append((path, body))
            if path == "/v1/model/info":
                return MODEL_INFO
            return scripted.pop(0) if scripted else reply('{"done": true, "ref": "docs/X.md", "note": "n"}')

        real_post, real_base = globals()["_openai_post"], OPENAI_BASE
        _PROXY_MODELS.clear()
        globals()["_openai_post"] = stub
        try:
            out = openai_chat("worker", [{"role": "user", "content": "hi"}],
                              fmt=ENVELOPES["worker"]["schema"], max_tokens=None, reasoning="agentic")
            path, body = sent[-1]
            ck("the endpoint is POST <base>/v1/chat/completions", path == "/v1/chat/completions", path)
            ck("the request carries OpenAI {model, messages, max_tokens}",
               body["model"] == "worker" and body["messages"] == [{"role": "user", "content": "hi"}]
               and body["max_tokens"] == GLM_MAX_TOKENS, json.dumps(body)[:160])
            ck("max_tokens defaults to GLM 4.7's 40000 ceiling, NOT the ollama path's num_predict 1024",
               body["max_tokens"] == 40000 and GLM_MAX_TOKENS == 40000, str(body["max_tokens"]))
            ck("no Ollama `options`/num_ctx block is sent on the openai flavor",
               "options" not in body and "num_ctx" not in body, str(sorted(body)))
            ck("temperature=1 / top_p=0.95 are GLM 4.7's migration-guide defaults (config :18-19)",
               body["temperature"] == 1 and body["top_p"] == 0.95, str((body["temperature"], body["top_p"])))

            print("-- openai flavor: response_format carries the SAME schema, with strict:false")
            rf = body["response_format"]
            ck("response_format is a json_schema", rf["type"] == "json_schema", str(rf["type"]))
            ck("...carrying the identical schema object the ollama flavor sends as `format`",
               rf["json_schema"]["schema"] is ENVELOPES["worker"]["schema"])
            ck("...with strict:false (strict:true is 400'd: Cerebras demands additionalProperties:false, "
               "which step_schema/dispatch cannot supply)", rf["json_schema"]["strict"] is False)
            ck("no response_format is sent when no schema is asked for",
               "response_format" not in openai_chat("worker", [], fmt=None) and "response_format" not in sent[-1][1])

            print("-- openai flavor: the GLM 4.7 reasoning policy, one param per turn")
            openai_chat("worker", [], reasoning="agentic")
            ag = sent[-1][1]
            ck("an agentic turn sends clear_thinking:false and no reasoning_effort",
               ag.get("clear_thinking") is False and "reasoning_effort" not in ag, json.dumps(ag)[:120])
            openai_chat("worker", [], reasoning="cheap")
            chp = sent[-1][1]
            ck("a cheap turn sends reasoning_effort:'none' and no clear_thinking",
               chp.get("reasoning_effort") == "none" and "clear_thinking" not in chp, json.dumps(chp)[:120])
            ck("the WORKER's envelope turn is the cheap one; adversary/dispatch keep reasoning",
               ENVELOPE_REASONING["worker"] == "cheap" and ENVELOPE_REASONING["adversary"] == "agentic"
               and ENVELOPE_REASONING["dispatch"] == "agentic", str(ENVELOPE_REASONING))
            ck("max_tokens is clamped to GLM 4.7's ceiling and never zero",
               (clamp_max_tokens(10 ** 9), clamp_max_tokens(None), clamp_max_tokens(500), clamp_max_tokens(0))
               == (40000, 40000, 500, 40000))

            print("-- openai flavor: the reply is choices[0].message.content, never reasoning_content")
            ck("content is read from choices[0].message.content",
               out["message"]["content"] == '{"done": true, "ref": "docs/X.md", "note": "n"}',
               str(out["message"]["content"]))
            ck("the mapped message is the shape extract_json already parses",
               extract_json(out["message"])[0] == {"done": True, "ref": "docs/X.md", "note": "n"},
               str(extract_json(out["message"])))
            ck("reasoning_content is NOT parsed as the answer (GLM 4.7 puts its thinking there)",
               extract_json(openai_message(reply('{"tool":"finish","args":{}}',
                                                 reasoning='{"tool":"Write","args":{"file_path":"WRONG"}}')))[0]
               == {"tool": "finish", "args": {}})
            ck("a \\r\\n-terminated reply still parses (the live proxy emits one)",
               extract_json(openai_message(reply('{"done": true, "ref": "a", "note": "b"}\r\n')))[0]
               == {"done": True, "ref": "a", "note": "b"})
            ck("native OpenAI tool_calls map straight through (arguments as a JSON string)",
               extract_json(openai_message(reply(None, finish="tool_calls", tool_calls=[
                   {"id": "1", "type": "function",
                    "function": {"name": "Read", "arguments": '{"file_path": "a.md"}'}}])))[0]
               == {"tool": "Read", "args": {"file_path": "a.md"}})

            print("-- openai flavor: reasoning eating the whole budget is a LOUD error, not an empty envelope")
            try:
                openai_message(reply("", finish="length", usage={"completion_tokens": 64,
                                                                "completion_tokens_details": {"reasoning_tokens": 64}}))
                ck("an all-reasoning/no-content reply is refused with a one-line message", False, "it was allowed")
            except Unexpected as e:
                ck("an all-reasoning/no-content reply is refused with a one-line message",
                   "REASONING" in str(e) and "reasoning_tokens=64" in str(e) and "40000" in str(e), str(e))
            ck("...but content=None WITH tool_calls is fine (the live proxy really does that)",
               openai_message(reply(None, finish="tool_calls", tool_calls=[
                   {"function": {"name": "Read", "arguments": "{}"}}]))["content"] == "")
            try:
                openai_message({"choices": []})
                ck("a reply with no choices is refused, not indexed into", False, "it was allowed")
            except Unexpected:
                ck("a reply with no choices is refused, not indexed into", True)

            print("-- openai flavor: #175's validate-and-retry channel works over response_format")
            del sent[:]
            scripted[:] = [reply("I refuse to emit JSON"),
                           reply('{"done": "yes", "ref": "x", "note": "n"}'),
                           reply('{"done": true, "ref": "docs/X.md", "note": "ok"}')]
            got = constrained("worker", [{"role": "user", "content": "go"}], ENVELOPES["worker"]["schema"],
                              2, time.time() + 60, label="envelope", flavor="openai", reasoning="agentic")
            ck("a non-JSON reply then a type-violating reply are both retried, and the valid one returns",
               got == {"done": True, "ref": "docs/X.md", "note": "ok"}, str(got))
            ck("...taking exactly 3 attempts", len([s for s in sent if s[0] == "/v1/chat/completions"]) == 3,
               str(len(sent)))
            ck("the first attempt was agentic; every CORRECTIVE retry drops to reasoning_effort:'none'",
               sent[0][1].get("clear_thinking") is False
               and all(s[1].get("reasoning_effort") == "none" for s in sent[1:]),
               str([s[1].get("reasoning_effort") or s[1].get("clear_thinking") for s in sent]))

            print("-- openai flavor: the model RECORDED is the model that ACTUALLY ran (#411 req 4)")
            ck("the alias 'worker' resolves through /v1/model/info to cerebras/zai-glm-4.7",
               real_model("worker") == "cerebras/zai-glm-4.7", real_model("worker"))
            ck("the worker role maps to the alias that is GLM 4.7",
               PROXY_ROLE_MODELS["worker"] == "worker"
               and real_model(PROXY_ROLE_MODELS["worker"]) == "cerebras/zai-glm-4.7")
            ck("the adversary is a DIFFERENT family from the GLM worker (research #173 §5.4)",
               real_model(PROXY_ROLE_MODELS["adversary"]) == "cerebras/gpt-oss-120b"
               and real_model(PROXY_ROLE_MODELS["adversary"]) != real_model(PROXY_ROLE_MODELS["worker"]),
               real_model(PROXY_ROLE_MODELS["adversary"]))
            ck("an unresolvable alias is recorded as itself rather than failing the run",
               real_model("not-a-real-alias") == "not-a-real-alias")

            print("-- openai flavor: the whole claude-p contract, end to end (prompt in, file out, JSON out)")
            del sent[:]
            scripted[:] = [
                reply('{"thought": "write it", "tool": "Write", "args": {"file_path": "docs/built.md", '
                      '"content": "built by glm\\n"}}'),
                reply('{"thought": "done", "tool": "finish", "args": {}}'),
                reply('{"done": true, "ref": "docs/built.md", "note": "wrote the doc"}'),
            ]
            envelope = run_agent("You are w-1, the coder — the worker of a build pair on ticket #411.\n"
                                 "Deliverable: write it to docs/built.md (create or overwrite that file; "
                                 "touch nothing else).", "Read,Write", cwd=base, flavor="openai",
                                 max_steps=4, retries=1, timeout=60)
            ck("the agent ran the Write tool and the deliverable really exists",
               os.path.isfile(os.path.join(base, "docs", "built.md"))
               and open(os.path.join(base, "docs", "built.md")).read() == "built by glm\n")
            ck("...and returned the envelope pair_loop reads off the last line",
               envelope == {"done": True, "ref": "docs/built.md", "note": "wrote the doc"}, str(envelope))
            ck("...having defaulted the worker role to the GLM 4.7 alias without being told",
               all(s[1]["model"] == "worker" for s in sent if s[0] == "/v1/chat/completions"))
            ck("...and asked for the envelope with reasoning_effort:'none' (the cheap worker envelope)",
               sent[-1][1].get("reasoning_effort") == "none", json.dumps(sent[-1][1])[:120])

            print("-- openai flavor: a worker that never wrote the file cannot report done")
            # 3 steps (finish, refused twice as the file is absent, allowed the third time when the
            # correction budget is spent), then the envelope it is nonetheless not allowed to keep.
            scripted[:] = [reply('{"thought": "lie", "tool": "finish", "args": {}}')] * 3 + \
                          [reply('{"done": true, "ref": "docs/never.md", "note": "lied"}')]
            try:
                run_agent("You are w-1, the coder — the worker of a build pair on ticket #411.\n"
                          "Deliverable: write it to docs/never.md (create or overwrite that file; "
                          "touch nothing else).", "Read,Write", cwd=base, flavor="openai",
                          max_steps=3, retries=0, timeout=60)
                ck("an envelope claiming a file that was never written is refused", False, "it was allowed")
            except Unexpected as e:
                ck("an envelope claiming a file that was never written is refused",
                   "does not exist" in str(e), str(e))

            print("-- openai flavor: a typo'd model is a one-line refusal, not a mid-run 400")
            try:
                run_agent("You are w-1, the coder — the worker of a build pair on ticket #411.",
                          "Read", cwd=base, model="worker-typo", flavor="openai", max_steps=1, timeout=60)
                ck("an alias the proxy does not serve is refused before any turn", False, "it ran")
            except Unexpected as e:
                ck("an alias the proxy does not serve is refused before any turn",
                   "is not served" in str(e), str(e))
        finally:
            globals()["_openai_post"] = real_post
            globals()["OPENAI_BASE"] = real_base
            _PROXY_MODELS.clear()

        print("-- --engine cerebras: the same rebind as --engine ollama, flavor swapped")
        try:
            pl2 = load_pair_loop()
            stock2 = pl2.spawn_claude
            ca, crest = parse_engine_args(["--engine", "cerebras", "--ticket", "411",
                                           "--deliverable", "docs/X.md"])
            ck("--engine cerebras implies the openai flavor", ca.flavor == "openai", ca.flavor)
            ck("--engine cerebras --ticket 411 --deliverable docs/X.md reaches pair_loop INTACT",
               crest == ["--ticket", "411", "--deliverable", "docs/X.md"], str(crest))
            pl2.spawn_claude = make_spawn(pl2, ca)
            ck("--engine cerebras rebinds pair_loop.spawn_claude", pl2.spawn_claude is not stock2)
            import inspect as _inspect
            ck("...to the exact spawn_claude signature pair_loop calls positionally",
               list(_inspect.signature(pl2.spawn_claude).parameters) == ["prompt", "allowed_tools", "timeout", "cwd"])
            pl2.spawn_claude = stock2
            oa, orest = parse_engine_args(["--engine", "ollama", "--ticket", "1", "--deliverable", "d"])
            ck("--engine ollama still means the ollama flavor (unchanged by #411)",
               oa.flavor == "ollama" and orest == ["--ticket", "1", "--deliverable", "d"], oa.flavor)
            ck("--engine claude still rebinds nothing and passes everything through",
               parse_engine_args(["--engine", "claude", "--dispatch", "3"])[1] == ["--dispatch", "3"])
            base_before = OPENAI_BASE
            ka, krest = parse_engine_args(["--engine", "cerebras", "--openai-model", "cerebras-glm",
                                           "--openai-max-tokens", "12345", "--ticket", "9"])
            ck("the --openai-* tuning flags are consumed here and NOT leaked to pair_loop",
               ka.model == "cerebras-glm" and ka.max_tokens == 12345 and krest == ["--ticket", "9"],
               str((ka.model, ka.max_tokens, krest)))
            globals()["OPENAI_BASE"] = base_before
            ck("--engine cerebras with no --openai-model lets the role pick (worker -> GLM 4.7)",
               parse_engine_args(["--engine", "cerebras", "--ticket", "9"])[0].model is None)
        except Exception as e:  # noqa: BLE001
            ck("the --engine cerebras checks ran", False, "%s: %s" % (type(e).__name__, e))

        bad = [n for n, ok, _ in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s"
              % (len(checks) - len(bad), len(checks), "" if not bad else "; FAILED: " + "; ".join(bad)))
        return 1 if bad else 0
    finally:
        shutil.rmtree(base, ignore_errors=True)
        print("== selftest == throwaway workspace removed (this repo, the db, Ollama, the litellm "
              "proxy and the network were never touched)")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    # ENGINE MODE FIRST, with its own parser: every argument except --engine and --ollama-* belongs
    # to pair_loop, including ones agent mode would otherwise claim (--ticket/--deliverable/
    # --timeout/--selftest). See parse_engine_args for why this cannot share agent mode's parser.
    argv = sys.argv[1:]
    if any(x == "--engine" or x.startswith("--engine=") for x in argv):
        a, rest_argv = parse_engine_args(argv)
        return engine_mode(a, rest_argv)

    ap = argparse.ArgumentParser(
        prog="ollama_agent.py",
        description="Agent runner: a drop-in replacement for `claude -p`, backed by a local model "
                    "over Ollama or by an OpenAI-compatible endpoint (the litellm proxy -> Cerebras "
                    "GLM 4.7). Also carries --engine ollama|claude|cerebras, which drives "
                    "pair_loop.py with the chosen engine (no edit to pair_loop.py required).",
        epilog="examples:\n"
               "  python3 ollama_agent.py --selftest\n"
               "  python3 ollama_agent.py --probe\n"
               "  python3 ollama_agent.py --probe --api-flavor openai\n"
               "  python3 ollama_agent.py -p \"You are a-1, the coder — the worker of a build pair on \"\n"
               "                             \"ticket #1. Deliverable: write it to docs/X.md\" \\\n"
               "                          --allowedTools \"Read,Write\" --no-journal\n"
               "  python3 ollama_agent.py --api-flavor openai --no-journal \\\n"
               "                          -p \"...\" --allowedTools \"Read,Write\"   # GLM 4.7\n"
               "  python3 ollama_agent.py --engine ollama --ticket 176 --deliverable docs/X.md\n"
               "  python3 ollama_agent.py --engine cerebras --ticket 411 --deliverable docs/X.md\n"
               "\n"
               "with --engine, every argument except --engine and the tuning flags\n"
               "(--ollama-model/-channel/-num-ctx/-max-steps/-retries/-no-journal and\n"
               "--openai-model/-base/-max-tokens/-temperature/-top-p) is passed to pair_loop.py\n"
               "verbatim, and pair_loop's own --help describes them.\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--print", dest="prompt", metavar="PROMPT",
                    help="the birth prompt (the same as `claude -p PROMPT`)")
    ap.add_argument("--allowedTools", dest="allowed_tools", default="Read,Grep,Glob", metavar="TOOLS",
                    help="comma-separated allowlist in pair_loop's own syntax: "
                         "'Read,Grep,Glob,Write,Edit,Bash(python3:*)' (default: %(default)s)")
    ap.add_argument("--engine", choices=("ollama", "claude", "cerebras"),
                    help="drive pair_loop.py with this engine. Every other argument (--ticket, "
                         "--deliverable, --timeout, --rounds, --base, --dispatch, --selftest, ...) is "
                         "passed to pair_loop verbatim; tune with the --ollama-*/--openai-* flags. "
                         "'cerebras' runs every agent through the litellm proxy, so the coder worker "
                         "runs Cerebras GLM 4.7")
    ap.add_argument("--api-flavor", dest="flavor", choices=("ollama", "openai"), default="ollama",
                    help="the request/response shape: 'ollama' = POST $OLLAMA_URL/api/chat "
                         "(default); 'openai' = POST $OPENAI_BASE/v1/chat/completions, the litellm "
                         "proxy, whose 'worker' model is Cerebras GLM 4.7")
    ap.add_argument("--openai-base", default=None, metavar="URL",
                    help="the OpenAI-compatible base (default: $OPENAI_BASE or %s)" % OPENAI_BASE)
    ap.add_argument("--openai-max-tokens", dest="max_tokens", type=int, default=GLM_MAX_TOKENS,
                    metavar="N",
                    help="max_tokens per openai turn (default: %(default)s = GLM 4.7's max output). "
                         "GLM 4.7 reasons by default and reasoning is billed against this budget, so "
                         "a small value returns EMPTY content — size it generously")
    ap.add_argument("--openai-temperature", type=float, default=OPENAI_TEMPERATURE, metavar="F",
                    help="openai flavor temperature (default: %(default)s — GLM 4.7's coding default)")
    ap.add_argument("--openai-top-p", type=float, default=OPENAI_TOP_P, metavar="F",
                    help="openai flavor top_p (default: %(default)s — GLM 4.7's coding default)")
    ap.add_argument("--model", help="override the role's model. Default per role: ollama flavor %s; "
                                    "openai flavor %s"
                                    % (", ".join("%s=%s" % kv for kv in ROLE_MODELS.items()),
                                       ", ".join("%s=%s" % kv for kv in PROXY_ROLE_MODELS.items())))
    ap.add_argument("--role", choices=tuple(ENVELOPES), help="override the role read from the prompt")
    ap.add_argument("--ticket", type=int, help="ticket id to journal against (default: read from the prompt)")
    ap.add_argument("--agent-id", help="agent id to register (default: read from the prompt)")
    ap.add_argument("--deliverable", help="the file a worker must have written (default: read from the prompt)")
    ap.add_argument("--cwd", help="the workspace directory the agent runs in (default: the current directory)")
    ap.add_argument("--channel", choices=("schema", "tools"), default="schema",
                    help="how tool calls travel: 'schema' = JSON-Schema-constrained JSON, works on every "
                         "model including gemma3 (research #175 §5.1; the default); 'tools' = Ollama's "
                         "native tools API, refused for a model without the 'tools' capability")
    ap.add_argument("--num-ctx", type=int, help="override num_ctx (default: sized to the payload, "
                                                "floor 8192, capped at the model's real context)")
    ap.add_argument("--max-steps", type=int, default=12,
                    help="max tool steps before the envelope is demanded (default: %(default)s)")
    ap.add_argument("--retries", type=int, default=2,
                    help="schema-violation retries per call, per research #175 §5.2 (default: %(default)s)")
    ap.add_argument("--timeout", type=int, default=900, help="seconds for the whole run (default: %(default)s)")
    ap.add_argument("--no-journal", action="store_true",
                    help="do NOT register or journal through the governed routes (ad-hoc/offline use)")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the allowlist, the extractor, the validator and the --engine rebind in a "
                         "THROWAWAY temp dir, then exit (no db, no network, no Ollama; this repo untouched)")
    ap.add_argument("--probe", action="store_true",
                    help="show the models the backend has here and the role->model map, then exit "
                         "(honors --api-flavor: 'openai' probes the litellm proxy instead of Ollama)")
    a, unknown = ap.parse_known_args()

    if a.openai_base:
        globals()["OPENAI_BASE"] = a.openai_base.rstrip("/")
    # --engine cerebras implies the openai flavor whichever mode it is spelled in.
    if a.engine == "cerebras":
        a.flavor = "openai"

    if a.selftest:
        return selftest()
    if a.probe:
        return probe(flavor=a.flavor)
    if a.engine:
        return engine_mode(a, unknown)
    if unknown:
        ap.error("unrecognized arguments: %s (they pass through only with --engine)" % " ".join(unknown))
    if not a.prompt:
        ap.error("-p/--print PROMPT is required (or use --engine, --probe, or --selftest)")

    envelope = governed_run(a.prompt, a.allowed_tools, a, cwd=a.cwd)
    print(json.dumps(envelope))     # the LAST line of stdout — the contract (pair_loop.py:734-741)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Unexpected as e:
        bug_report("main", e, "python3 ollama_agent.py " + " ".join(sys.argv[1:]), e)
        print("ollama_agent: %s" % e, file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("ollama_agent: interrupted", file=sys.stderr)
        sys.exit(2)
