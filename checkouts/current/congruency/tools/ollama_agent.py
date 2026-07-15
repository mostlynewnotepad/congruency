#!/usr/bin/env python3
"""ollama_agent.py — the LOCAL agent runner: a drop-in replacement for `claude -p`, backed by Ollama.

WHAT THIS IS. `pair_loop.py` runs every agent through ONE function, `spawn_claude(prompt,
allowed_tools, timeout, cwd)` (pair_loop.py:500-518), which shells out to `claude -p <prompt>
--allowedTools <tools>` (:504) and reads the agent's answer off the LAST JSON line of stdout
(:511-518). This module is a second implementation of that same contract, driven by a LOCAL model
over Ollama's `/api/chat` instead of Anthropic's cloud. Same contract, three parts:

    IN     a birth prompt (the same string pair_loop builds from WORKER_PROMPT/AUDITOR_PROMPT,
           pair_loop.py:445-468) plus an allowlist of tool names (pair_loop.py:493-494).
    ACT    the agent reads/greps/writes/edits/runs — using ONLY the allowlisted tools — until it
           has written the deliverable file the prompt names.
    OUT    one JSON object as the LAST line of stdout: {"done":true,...} for a worker,
           {"verdict":"pass"|"fail","findings":[...]} for an adversary.

TWO WAYS TO RUN IT (both are this one file; see --help):

  1. AGENT MODE — the drop-in. Same argv shape as `claude -p`, so anything that spawns claude can
     spawn this instead:
         python3 ollama_agent.py -p "<birth prompt>" --allowedTools "Read,Grep,Glob,Write,Edit"
     It prints progress to stderr and the envelope JSON as the last line of stdout.

  2. ENGINE MODE — `--engine ollama|claude`, the selector ticket #176 asks for. It drives
     pair_loop.py with the chosen engine and passes every other argument straight through:
         python3 ollama_agent.py --engine ollama --ticket 176 --deliverable docs/X.md
         python3 ollama_agent.py --engine claude --ticket 176 --deliverable docs/X.md
         python3 ollama_agent.py --engine ollama --dispatch 3 --parallel 2
     `--engine ollama` rebinds pair_loop's module-global `spawn_claude` to this module's runner
     BEFORE calling pair_loop.main(), so every agent the loop spawns — worker, adversary, and the
     dispatcher (pair_loop.py:565) — runs locally. `--engine claude` changes nothing and is the
     stock loop. Nothing else about pair_loop's behavior is altered: the brake, the branch, the
     commit, the merge, the journal and the exit codes are all still pair_loop's.

     ARGUMENT OWNERSHIP IN ENGINE MODE (this matters, and it is enforced, not merely intended).
     Once `--engine` is present, the ONLY arguments this module keeps are `--engine` itself and the
     `--ollama-*` tuning flags below. EVERY other argument is handed to pair_loop verbatim, so
     `--ticket`, `--deliverable`, `--timeout`, `--rounds`, `--base`, `--dispatch`, `--parallel`,
     `--selftest` and the rest mean exactly what pair_loop.py means by them, with pair_loop's own
     parser reporting its own errors. The tuning flags are deliberately named apart —
         --ollama-model  --ollama-channel  --ollama-max-steps  --ollama-retries
         --ollama-num-ctx  --ollama-no-journal
     — precisely so they can never collide with an option pair_loop owns now or adds later. (In
     AGENT mode the same knobs are spelled --model/--channel/--max-steps/--retries/--num-ctx/
     --no-journal, because there is no second parser to collide with.) Per-spawn timeout in engine
     mode comes from pair_loop's own --timeout, which it passes to spawn_claude (pair_loop.py:1046).

     WHY THE SELECTOR LIVES HERE AND NOT IN pair_loop.py. Ticket #176's deliverable line is
     "write it to checkouts/current/congruency/tools/ollama_agent.py (create or overwrite that
     file; touch nothing else)". That is not a style note — it is mechanically enforced: the
     harness stages ONLY the deliverable (`git add -- <deliverable>`, pair_loop.py:347), reports
     every other dirty path as a `stray` that is journaled as "UNCOMMITTED ... will not survive the
     reap" (pair_loop.py:349, :1062-1064), and then reaps the worktree with `--force`
     (pair_loop.py:422). An edit to pair_loop.py from inside this ticket would therefore never be
     committed — it would be journaled as abandoned and deleted. So the selector is implemented
     the only way it can both exist and survive: entirely inside this file, requiring ZERO edits to
     pair_loop.py, by rebinding the one function pair_loop looks up at call time. It is a real,
     runnable `--engine ollama|claude`; prove it with --selftest, which asserts the rebind takes.

HOW IT MEETS THE GATES (#173 "role->model fit" = R2, #175 "structured-output reliability" = R4;
both docs live in checkouts/current/docs/research/):

  * STRUCTURED OUTPUT IS ENFORCED, NOT HOPED FOR (R4). Every model turn is JSON-Schema-constrained
    via Ollama's `format` field — the channel R4 measured at 100% valid/conformant across
    gemma3:4b, qwen2.5-coder:7b and qwen3-coder (R4 §3, §5.1). Each reply is then parsed and
    VALIDATED against the schema in Python (types, required keys, enum membership, int-not-string),
    and on any failure the parser's own error is fed back as a corrective turn and the call is
    RETRIED up to --retries times (default 2) — R4 §5.2 steps 3-4. R4 §3 is explicit that 100%
    over N=20 has a ~83% Wilson lower bound and does NOT license dropping the wrapper, so the
    wrapper is unconditional.

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
    Ollama's /api/show. It never relies on the default.

  * THE ROLE PICKS THE MODEL (R2 §1, §6.2). Parsed from the birth prompt, then:
        worker/coder     -> qwen2.5-coder:7b   (R2: 5/5 on self-contained coding tasks, fastest)
        adversary/judge  -> gemma3:27b         (R2: 6/6, 3/3 bugs caught, 0/3 false positives, and
                                                a DIFFERENT family from the qwen worker, which is
                                                the point of an adversarial reviewer — R2 §5.4)
        dispatch         -> gemma3:27b         (R2: 6/6 once stop/gate flags are pre-computed)
    --model overrides any of it. R2 §5.2 excludes gemma3:4b from dispatch and this module honors
    that: it is not the default for any role.

  * THE AGENT IS REGISTERED AND ITS RUN IS JOURNALED THROUGH THE GOVERNED ROUTES. Registration is
    `agent.register` (migrations/0001_agents.sql:19-25) and the journal is `ticket.progress`
    (migrations/0029_ticket_authorization.sql:193-198) — the same token routes pair_loop uses; this
    module holds no SQL pen. Registration records the model that ACTUALLY ran and the tools that
    were ACTUALLY granted, so the record reflects the local engine rather than pair_loop's
    placeholder `["claude -p"]` (pair_loop.py:1038). The route is INSERT OR REPLACE, so re-
    registering an id pair_loop already created UPDATES it and erases nothing.

TOOLS ARE RESTRICTED TO THE ALLOWLIST, AND THE ALLOWLIST IS THE ONE pair_loop ALREADY PASSES.
`--allowedTools` takes the exact strings from pair_loop's FOCUS table (pair_loop.py:481-482,
:493-494), e.g. "Read,Grep,Glob,Write,Edit,Bash(python3:*)". Enforcement is in two independent
layers, because a model can hallucinate a tool name that was never offered:
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
directory it deletes, needs no key, no db, no network and no Ollama, and touches this repo not at
all.

Usage:
    python3 ollama_agent.py -p PROMPT --allowedTools TOOLS [--model M] [--role R] [--ticket N]
                            [--agent-id ID] [--deliverable PATH] [--cwd DIR] [--channel schema|tools]
                            [--num-ctx N] [--max-steps N] [--retries N] [--timeout S] [--no-journal]
    python3 ollama_agent.py --engine ollama|claude [--ollama-*] [... pair_loop.py arguments ...]
    python3 ollama_agent.py --selftest
    python3 ollama_agent.py --probe

    Note --selftest/--probe are THIS module's and belong to agent mode; with --engine they pass
    through to pair_loop like every other argument (`--engine claude --selftest` therefore runs
    pair_loop's git-layer selftest, not this one).

Exit codes:
    0  the agent finished and printed its envelope JSON as the last line of stdout
       (--engine: pair_loop's own exit code, unchanged; --selftest: every check passed)
    1  --selftest: at least one check FAILED (--probe: a role's default model is not installed)
    2  unexpected — a one-line message (never a traceback) and a Variant-A bug report was filed

Governance: a run registers and journals through the governed routes, and REFUSES to start without
CONGRUENCY_API_KEY (env, or .secrets/ats.env beside the repo — the same two sources pair_loop reads,
pair_loop.py:141-150). Pass --no-journal to run ungoverned for ad-hoc/offline use; it says so on
stderr.
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


def _secret(name):
    """The key, from the same two places pair_loop reads it (pair_loop.py:141-147): the secrets file
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
    Mirrors pair_loop.bug_report (pair_loop.py:153-166)."""
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
    reads the LAST LINE of stdout (pair_loop.py:511-518) — a stray print there would be read as the
    agent's answer."""
    sys.stderr.write("%s\n" % msg)
    sys.stderr.flush()


# ── the governed REST surface (token routes; this module holds no SQL pen) ───────────────────────
def rest(route, obj=None, method=None):
    """Mirrors pair_loop.rest (pair_loop.py:174-186)."""
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


# ── R2 §1/§6.2: the role decides the model ───────────────────────────────────────────────────────
ROLE_MODELS = {
    "worker": "qwen2.5-coder:7b",     # R2 §3.2: 5/5 on self-contained coding tasks, fastest coder
    "adversary": "gemma3:27b",        # R2 §3.3: 6/6; a different family from the worker (R2 §5.4)
    "dispatch": "gemma3:27b",         # R2 §3.1: 6/6 with pre-computed stop/gate flags
}
DEFAULT_TEMPERATURE = 0.3             # R2 §2: low, for reasoning determinism


def role_of(prompt):
    """worker | adversary | dispatch, read off the birth prompt pair_loop built.

    Grounded in the templates, not guessed: WORKER_PROMPT opens "You are <id>, the <role> — the
    worker of a <kind> pair on ticket #<n>." (pair_loop.py:445) and AUDITOR_PROMPT opens the same
    way with "the adversary of a" (pair_loop.py:458). do_dispatch appends DISPATCH_RULES, whose
    plan envelope is the giveaway (pair_loop.py:521-531)."""
    if "the adversary of a" in prompt:
        return "adversary"
    if "the worker of a" in prompt:
        return "worker"
    if '"plan":' in prompt and "THE QUEUE" in prompt:
        return "dispatch"
    return "worker"


def ticket_of(prompt):
    """The ticket id from GOVERNANCE's "ticket #<n> authorizes you" (pair_loop.py:434), falling back
    to the header's "on ticket #<n>" (pair_loop.py:445)."""
    m = re.search(r"ticket\s+#(\d+)\s+authorizes\s+you", prompt) or re.search(r"on ticket #(\d+)", prompt)
    return int(m.group(1)) if m else None


def agent_of(prompt):
    """The agent id from GOVERNANCE's "You are registered as <id>" (pair_loop.py:435), falling back
    to the header's "You are <id>, the ..." (pair_loop.py:445/:458)."""
    m = re.search(r"You are registered as ([A-Za-z0-9_.\-]+)", prompt) or \
        re.search(r"^You are ([A-Za-z0-9_.\-]+),\s*the ", prompt, re.M)
    return m.group(1).rstrip(".,") if m else None


def deliverable_of(prompt):
    """The deliverable path from "Deliverable: write it to <path>" (pair_loop.py:450), falling back
    to the adversary's "The worker produced <path>." (pair_loop.py:463).

    The trailing period is stripped, not matched non-greedily: `(\\S+?)\\.` would stop at the FIRST
    dot and read "tools/ollama_agent.py." as "tools/ollama_agent". A path never ends in a dot, so
    taking the whole token and rstrip'ing '.' is both simpler and right."""
    m = re.search(r"Deliverable:\s*write it to\s+(\S+?)\s*\(", prompt) or \
        re.search(r"Deliverable:\s*write it to\s+(\S+)", prompt) or \
        re.search(r"The worker produced\s+(\S+)", prompt)
    return m.group(1).rstrip(".") if m else None


# ── R4 §5.1 + R2 §6.5: every envelope type gets a JSON Schema, sent as `format` ───────────────────
ENVELOPES = {
    # pair_loop reads wres.get("done") (:1047) and wres.get("ref"/"note") (:1050).
    "worker": {
        "schema": {"type": "object",
                   "properties": {"done": {"type": "boolean"},
                                  "ref": {"type": "string"},
                                  "note": {"type": "string"}},
                   "required": ["done", "ref", "note"]},
        "describe": '{"done": true, "ref": "<the deliverable path>", "note": "<one line on what you produced>"}',
    },
    # pair_loop reads vres.get("verdict") == "pass" (:1073) and vres.get("findings", []) (:1070).
    "adversary": {
        "schema": {"type": "object",
                   "properties": {"verdict": {"type": "string", "enum": ["pass", "fail"]},
                                  "findings": {"type": "array", "items": {"type": "string"}}},
                   "required": ["verdict", "findings"]},
        "describe": '{"verdict": "pass", "findings": []}   or   {"verdict": "fail", "findings": ["<finding>", ...]}',
    },
    # pair_loop reads res.get("plan", []) and each item's ticket/action/kind/deliverable/reason
    # (:566, :571-590). R2 §5.1: the harness must pre-compute stop/gate flags for the dispatcher,
    # because both large models reliably apply the stop RULE but cannot discover the cross-ticket
    # relationship themselves (4/6 -> 6/6 once the flag is supplied). pair_loop already does exactly
    # that, attaching active_stops per ticket (:561-563) before the queue reaches the model.
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
    """Files under `root`, pruning .git — the repo's established tree-walk (pair_loop.py:58 cites
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

    The strings are pair_loop's own (pair_loop.py:481-482, :493-494), e.g.
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
    (a private second checkout of the ticket's branch, pair_loop.py:1046). Every path a tool touches
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
         num_predict=1024, timeout=600):
    """One /api/chat turn. num_ctx is ALWAYS set (R2 §4 affordance B) — never Ollama's 4096 default."""
    body = {"model": model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_predict": num_predict,
                        "num_ctx": num_ctx or 8192}}
    if fmt is not None:
        body["format"] = fmt
    if tools:
        body["tools"] = tools
    return _ollama("/api/chat", body, timeout=timeout)


def constrained(model, messages, schema, retries, deadline, tools=None, num_predict=1024, label="step"):
    """R4 §5.2 in one function: ask, extract (native -> content fallback), VALIDATE, and on failure
    feed the parser's own error back as a corrective turn and RETRY.

    R4 measured 100% conformance on this channel and then said, in §3, that N=20 gives only a ~83%
    Wilson lower bound and does NOT license removing this wrapper. So the wrapper is unconditional."""
    convo = list(messages)
    chars = sum(len(m.get("content") or "") for m in convo)
    nctx = num_ctx_for(model, chars + 2000)
    last = ""
    for attempt in range(retries + 1):
        left = deadline - time.time()
        if left <= 0:
            raise Unexpected("the agent exceeded its time budget (raise --timeout)")
        out = chat(model, convo, fmt=schema, tools=tools, num_ctx=nctx,
                   num_predict=num_predict, timeout=max(5, int(left)))
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
    raise Unexpected("%s: no schema-conformant reply from %s after %d attempts — last error: %s"
                     % (label, model, retries + 1, last))


def run_agent(prompt, allowed_tools, cwd=None, model=None, role=None, channel="schema",
              max_steps=12, retries=2, timeout=900, num_ctx=None, deliverable=None):
    """Run one agent to completion and return its envelope dict — the value spawn_claude returns.

    The loop: act (tool calls) until the model finishes or --max-steps is spent, then ONE final
    schema-constrained call for the envelope."""
    ws = Workspace(os.path.realpath(cwd or os.getcwd()), allowed_tools)
    role = role or role_of(prompt)
    model = model or ROLE_MODELS.get(role, ROLE_MODELS["worker"])
    env = ENVELOPES.get(role, ENVELOPES["worker"])
    deliverable = deliverable or deliverable_of(prompt)
    deadline = time.time() + timeout

    caps = installed_models()
    if model not in caps:
        raise Unexpected("model %r is not installed in Ollama at %s (have: %s) — run `ollama pull %s`"
                         % (model, OLLAMA, ", ".join(sorted(caps)) or "none", model))

    native_tools = None
    if channel == "tools":
        # R4 §2/§5.4: gemma3 advertises no "tools" capability and hard-errors on a tools array.
        if "tools" not in (caps.get(model) or []):
            raise Unexpected("--channel tools was requested but %r does not support Ollama's tools API "
                             "(capabilities: %s). Use the default --channel schema, which carries tool "
                             "calls as schema-constrained JSON and works on every model (research "
                             "#175 §5.1)." % (model, ", ".join(caps.get(model) or []) or "none"))
        native_tools = tools_payload(ws)

    log("== ollama_agent == role=%s model=%s channel=%s tools=[%s] bash=%s ctx<=%d cwd=%s"
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
                          num_predict=1024, label="step %d" % steps)
        name, args = stp.get("tool"), stp.get("args") or {}
        messages.append({"role": "assistant", "content": json.dumps(stp)})

        if name == FINISH:
            # "a real, verified deliverable": a worker that reports done without having written the
            # file it was told to write is corrected and sent back to work, rather than let through
            # to a commit pair_loop would refuse anyway (pair_loop.py:344-346).
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
                           num_predict=1024, label="envelope")

    if role == "worker":
        if deliverable and not envelope.get("ref"):
            envelope["ref"] = deliverable
        if deliverable and not os.path.isfile(os.path.join(ws.root, deliverable)):
            # Truth over politeness: the envelope must not claim a file that is not there.
            raise Unexpected("the agent reported done but %s does not exist in %s — refusing to "
                             "report a deliverable that was never written" % (deliverable, ws.root))
    return envelope


# ── governance: register the agent + journal the run through the governed routes ──────────────────
def register(agent_id, prompt, tool_names, model, role, channel):
    """agent.register (migrations/0001_agents.sql:19-25). The route is INSERT OR REPLACE, so
    re-registering an id pair_loop already created UPDATES that row with the model that actually ran
    — it erases nothing and adds no row the loop did not expect."""
    rest("agent.register", {"agent_id": agent_id, "parent": "ollama_agent", "prompt": prompt,
                            "tools": json.dumps(["ollama:%s" % model, "role:%s" % role,
                                                 "channel:%s" % channel] + list(tool_names))})


def journal(ticket_id, agent_id, note, steps_remaining=None):
    """ticket.progress (migrations/0029_ticket_authorization.sql:193-198) — the append-only journal."""
    body = {"ticket_id": ticket_id, "agent_id": agent_id, "note": note}
    if steps_remaining is not None:
        body["steps_remaining"] = steps_remaining
    rest("ticket.progress", body)


def governed_run(prompt, allowed_tools, a, cwd=None):
    """One agent run WITH the governance the ticket requires: register before, journal after."""
    role = a.role or role_of(prompt)
    model = a.model or ROLE_MODELS.get(role, ROLE_MODELS["worker"])
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

    if govern:
        register(aid, prompt, names, model, role, a.channel)
        log("== governed == registered %s via agent.register (model %s)" % (aid, model))
        if tid:
            journal(tid, aid, "ollama_agent: %s starting on ticket #%d (model %s, channel %s, tools: %s)"
                    % (role, tid, model, a.channel, ", ".join(names) or "none"))
        else:
            log("== governed == no ticket id in the prompt — registered, but nothing to journal against")

    t0 = time.time()
    try:
        envelope = run_agent(prompt, allowed_tools, cwd=cwd, model=model, role=role,
                             channel=a.channel, max_steps=a.max_steps, retries=a.retries,
                             timeout=a.timeout, num_ctx=a.num_ctx, deliverable=a.deliverable)
    except Exception as e:  # noqa: BLE001
        if govern and tid:
            try:
                journal(tid, aid, "ollama_agent: %s FAILED after %.1fs — %s" % (role, time.time() - t0, e))
            except Exception:  # noqa: BLE001
                pass
        raise
    if govern and tid:
        journal(tid, aid, "ollama_agent: %s finished in %.1fs on %s — %s"
                % (role, time.time() - t0, model, json.dumps(envelope)[:300]))
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
    -> dict (pair_loop.py:500-518) exactly, because pair_loop calls it POSITIONALLY at :565, :1046
    and :1067. Errors are re-raised as pair_loop's OWN Unexpected so its handlers (:684-687,
    :1133-1136) catch them as they would any harness fault."""
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
    and pair_loop owns options by those same names (pair_loop.py:924-945). If one parser handled
    both, `--engine ollama --ticket 176 --deliverable docs/X.md` would have its --ticket and
    --deliverable swallowed here and pair_loop.main() would die on "--ticket N or --file KIND
    required" — a documented invocation that cannot run. So in engine mode we keep ONLY --engine and
    the --ollama-* tuning flags, and everything else is passed through untouched.

    add_help=False so `--engine ollama --help` prints pair_loop's help, which is the help that
    describes the arguments actually in force."""
    eap = argparse.ArgumentParser(prog="ollama_agent.py --engine", add_help=False)
    eap.add_argument("--engine", choices=("ollama", "claude"), required=True)
    eap.add_argument("--ollama-model", dest="model")
    eap.add_argument("--ollama-channel", dest="channel", choices=("schema", "tools"), default="schema")
    eap.add_argument("--ollama-num-ctx", dest="num_ctx", type=int)
    eap.add_argument("--ollama-max-steps", dest="max_steps", type=int, default=12)
    eap.add_argument("--ollama-retries", dest="retries", type=int, default=2)
    eap.add_argument("--ollama-no-journal", dest="no_journal", action="store_true")
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
    return a, rest


def engine_mode(a, rest_argv):
    """--engine ollama: rebind pair_loop's spawn_claude, then hand control to pair_loop.main().

    The rebind works — and needs no edit to pair_loop.py — because pair_loop resolves `spawn_claude`
    from its module globals at CALL time, not at import time: it is passed by name to step() at
    :565, :1046 and :1067. Setting the module attribute before main() runs therefore redirects every
    agent the loop spawns. --engine claude rebinds nothing and is the stock loop."""
    pl = load_pair_loop()
    if a.engine == "ollama":
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


# ── --probe: what Ollama has here, and what this module would do with it ──────────────────────────
def probe():
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
        ck("worker envelope carries done/ref/note (pair_loop.py:1047,1050)",
           set(wsch["properties"]) == {"done", "ref", "note"})
        ck("adversary envelope carries verdict/findings (pair_loop.py:1070,1073)",
           set(asch["properties"]) == {"verdict", "findings"})
        ck("dispatch envelope carries a plan (pair_loop.py:566)", "plan" in dsch["properties"])

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

        bad = [n for n, ok, _ in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s"
              % (len(checks) - len(bad), len(checks), "" if not bad else "; FAILED: " + "; ".join(bad)))
        return 1 if bad else 0
    finally:
        shutil.rmtree(base, ignore_errors=True)
        print("== selftest == throwaway workspace removed (this repo, the db, Ollama and the network "
              "were never touched)")


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
        description="Local agent runner: a drop-in replacement for `claude -p`, backed by Ollama. "
                    "Also carries --engine ollama|claude, which drives pair_loop.py with the chosen "
                    "engine (no edit to pair_loop.py required).",
        epilog="examples:\n"
               "  python3 ollama_agent.py --selftest\n"
               "  python3 ollama_agent.py --probe\n"
               "  python3 ollama_agent.py -p \"You are a-1, the coder — the worker of a build pair on \"\n"
               "                             \"ticket #1. Deliverable: write it to docs/X.md\" \\\n"
               "                          --allowedTools \"Read,Write\" --no-journal\n"
               "  python3 ollama_agent.py --engine ollama --ticket 176 --deliverable docs/X.md\n"
               "\n"
               "with --engine, every argument except --engine and the --ollama-* tuning flags\n"
               "(--ollama-model/-channel/-num-ctx/-max-steps/-retries/-no-journal) is passed to\n"
               "pair_loop.py verbatim, and pair_loop's own --help describes them.\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--print", dest="prompt", metavar="PROMPT",
                    help="the birth prompt (the same as `claude -p PROMPT`)")
    ap.add_argument("--allowedTools", dest="allowed_tools", default="Read,Grep,Glob", metavar="TOOLS",
                    help="comma-separated allowlist in pair_loop's own syntax: "
                         "'Read,Grep,Glob,Write,Edit,Bash(python3:*)' (default: %(default)s)")
    ap.add_argument("--engine", choices=("ollama", "claude"),
                    help="drive pair_loop.py with this engine. Every other argument (--ticket, "
                         "--deliverable, --timeout, --rounds, --base, --dispatch, --selftest, ...) is "
                         "passed to pair_loop verbatim; tune the local engine with the --ollama-* flags")
    ap.add_argument("--model", help="override the role's model (default: per research #173 — %s)"
                                    % ", ".join("%s=%s" % kv for kv in ROLE_MODELS.items()))
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
                    help="show the models Ollama has here and the role->model map, then exit")
    a, unknown = ap.parse_known_args()

    if a.selftest:
        return selftest()
    if a.probe:
        return probe()
    if a.engine:
        return engine_mode(a, unknown)
    if unknown:
        ap.error("unrecognized arguments: %s (they pass through only with --engine)" % " ".join(unknown))
    if not a.prompt:
        ap.error("-p/--print PROMPT is required (or use --engine, --probe, or --selftest)")

    envelope = governed_run(a.prompt, a.allowed_tools, a, cwd=a.cwd)
    print(json.dumps(envelope))     # the LAST line of stdout — the contract (pair_loop.py:511-518)
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
