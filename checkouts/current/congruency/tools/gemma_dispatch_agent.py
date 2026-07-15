#!/usr/bin/env python3
"""gemma_dispatch_agent.py — the LEAST-PRIVILEGE dispatch agent: a Gemma-3 model that reads the
ticket queue, decides run/skip/stop, and spawns worker pairs — and that is STRUCTURALLY INCAPABLE
of authoring work product (ticket #179; gated on R3 = research #174
`checkouts/current/docs/research/mcp_tool_access_least_privilege.md`, and B3 = build #178, the MCP
bridge `ticket_api_mcp.py`).

WHAT THIS IS. `pair_loop.py --dispatch` today spawns its dispatcher with `claude -p ...
--allowedTools "Read,Grep,Glob"` (pair_loop.py:565). That string is a CLIENT-SIDE NAME FILTER over
tools that are still fully present in the process — research #174 §4(a) — so the dispatcher is only
*asked* not to read the repo, never *prevented*. This module replaces that with research #174's
chosen enforcement, option (c): the model is launched with ONE tool surface, an MCP server started
as `ticket_api_mcp.py --role dispatch`, whose `tools/list` is exactly

    {ticket_queue, ticket_kind, ticket_assign, edge_record, ticket_progress}

and nothing else. There is no Write, no Edit, no Bash, no codebean, no git tool in the model's
context to call. The capability is ABSENT, not filtered — that is what makes it a trust boundary
(research §4: "absence beats filtering"), and it is what the ticket's acceptance means by
"structurally incapable of authoring work product".

TERMS, DEFINED ONCE (this file assumes you have read nothing else):
  MCP        — Model Context Protocol: a server that speaks JSON-RPC 2.0 over stdin/stdout, one
               JSON object per line. A client calls `tools/list` to learn what it may do and
               `tools/call` to do it. `ticket_api_mcp.py` implements it with the stdlib alone.
  the queue  — the OPEN/REQUESTED tickets, oldest first: route `ticket.queue`
               (migrations/0032_dispatch_routes.sql:5-10).
  a stop     — a ticket of kind `stop` aimed at another ticket by a `stops` edge. While an
               unreleased stop aims at a ticket (or any ancestor of it), that ticket authorizes
               NOTHING. The count is route `ticket.stops`
               (migrations/0030_pair_loop_routes.sql:21-26).
  the brake  — checking `ticket.stops` BEFORE acting. pair_loop does it at pair_loop.py:1002-1006.
  a kind     — a ticket's class (build/bug/documentation/design/... /stop/start), which fixes its
               pattern (pair vs solo) and its role names (migrations/0029_ticket_authorization.sql:
               27-45). Set-once: re-kinding is refused by `tg_tickets_immutable_identity` (:111-117).
  work product — a deliverable: code, prose, a recorded artifact, a minted work UID. Dispatch
               produces none of it; it only routes.

THE FIVE TOOLS, AND WHY EACH IS NOT A WAY TO AUTHOR (research §5.3):
    ticket_queue     GET  ticket.queue      read the queue                            0032:5-10
    ticket_kind      POST ticket.kind       set a set-once kind LABEL                 0030:14-19
    ticket_assign    POST ticket.assign     authorize a REGISTERED agent, in a role   0033:6-11
    edge_record      POST edge.record       record a parent->child graph edge         0012:16-23
    ticket_progress  POST ticket.progress   append an attributed journal note         0029:193-198
Every write in that set mutates ROUTING METADATA ONLY — a label, an authorization row, an edge, an
append-only note. The set contains no `work.record`, `artifact.record`, `doc.record`,
`source.record`, `bug.record` and no `ticket.create`; there is no file, shell, or git tool in the
context at all. So the model's maximal achievable effect is to route the queue — its whole mandate.

HOW A "SPAWN" HAPPENS — THE AGENT AUTHORIZES IT, THE HARNESS EXECUTES IT:
  * The AGENT's half is AUTHORIZATION, and it is all the agent can do: `ticket_assign` authorizes an
    agent on a ticket in a role, and `edge_record` records the provenance edge. It cannot invent an
    agent to authorize: `ticket.assign` is refused by the db trigger `tg_ticket_agents_registered`
    (migrations/0029_ticket_authorization.sql:152-156) unless the agent is already REGISTERED, and
    `agent.register` is NOT in the dispatch profile (ticket_api_mcp.py:366) — it is a harness-held
    governance write (research §2 note). So the agent cannot forge an authorization.
  * The HARNESS's half is EXECUTION: for each "run" this module launches
    `pair_loop.py --ticket N --deliverable PATH` as a child process, exactly as
    `pair_loop.do_dispatch` does (pair_loop.py:592-607). That child opens the ticket's own branch +
    worktree and registers and assigns its OWN fresh pair (pair_loop.py:1036-1039). The model has no
    shell and cannot launch anything: it emits a plan, and this harness — not the model — acts.
  * Minting a STOP ticket is likewise harness-held, because `ticket.create` is not in the dispatch
    profile (research §5.4). This module mints it the way pair_loop does (pair_loop.py:583-588):
    ticket.create, then ticket.kind=stop, then a `stops` edge aimed at the offending ticket.

THE HARNESS PRE-COMPUTES THE BRAKE; THE MODEL NEVER READS IT (research #173 affordance A, cited by
research #174 §2 note and §6). `ticket.stops` is deliberately NOT in the grant. Both large models
apply the stop RULE reliably but cannot discover the cross-ticket relationship themselves, so this
harness reads `ticket.stops` per queued ticket and injects two booleans per ticket:
    has_active_stop  — an unreleased stop aims at this ticket or an ancestor => it authorizes nothing
    gated            — has_active_stop, OR the ticket is itself a control ticket (kind stop/start)
                       => not actionable by a pair; the correct action is "skip"
This keeps the safety-critical reverse lookup out of the model AND out of the model's tool surface.
AND THE FLAGS ARE ENFORCED, NOT SUGGESTED: if the model answers "run" for a gated ticket, this
harness OVERRIDES it to "skip", journals the override, and spawns nothing (see apply_plan). The
brake does not depend on the model complying.

THE STRUCTURED OUTPUT CHANNEL (research #175 = R4, via ollama_agent.py). Every model turn is
JSON-Schema-constrained through Ollama's `format` field and then VALIDATED in python; a violation is
fed back as a corrective turn and retried. gemma3 is NEVER sent a `tools` array (it hard-errors on
Ollama's tools API), so tool intents travel as schema-constrained JSON — research #175 §5.1's
primary recommendation. The step schema's `tool` enum is built from the MCP server's OWN
`tools/list`, so the constrained decoder cannot even spell a tool the profile does not grant. This
module reuses `ollama_agent.py`'s R4-proven transport/extractor/validator rather than re-deriving
them (see load_ollama_agent).

FOUR LAYERS, FAILING SAFE INDEPENDENTLY:
    1. LAUNCH   (research option (c), the trust boundary) — the model's only tool surface is an MCP
                server started with `--role dispatch`; nothing else is connected. tools/list is the 5.
    2. DECODER  — the step schema's `tool` enum is exactly those 5 + "finish", so a constrained
                reply cannot name anything else.
    3. SERVER   (research option (b), defense-in-depth) — `ticket_api_mcp.py` re-checks the role
                allowlist SERVER-SIDE and refuses anything outside it (JSON-RPC -32601), even if a
                client asks by name anyway (ticket_api_mcp.py:455-460).
    4. CLIENT   — this module's McpClient also refuses a tool absent from tools/list, and PINS the
                journal identity: a `ticket_progress` note the model tries to attribute to another
                agent is re-attributed to the dispatch agent and the attempt is logged. (This is the
                weakest layer by construction — a client-side check — and is never relied on: layers
                1-3 already hold. It exists so "journals every decision AS the dispatch agent" is a
                property of the code and not of the model's goodwill.)

MODEL: gemma3:27b by default — research #173 §3.1's dispatch pick (6/6 once stop/gate flags are
pre-computed), read from `ollama_agent.ROLE_MODELS["dispatch"]` so the two files cannot drift.
num_ctx is sized to the payload with a 32768 FLOOR for this role (research #174 §6's `num_ctx >= 32k`
for #179; Ollama's default is 4096 whatever the model can do, which silently TRUNCATES a full-queue
dispatch and makes the model reason over a fragment). The floor is capped by the model's real
context length, read live from Ollama.

Usage:
    python3 gemma_dispatch_agent.py --dispatch [N]   # route the live queue; execute up to N decisions
    python3 gemma_dispatch_agent.py --plan           # decide + journal only; execute NOTHING
    python3 gemma_dispatch_agent.py --probe          # the ACTUAL granted tool surface + model readiness
    python3 gemma_dispatch_agent.py --selftest       # prove the acceptance offline; no db, no Ollama

EXPECT --dispatch/--plan TO BE SLOW, AND KNOW WHY. gemma3:27b is a 27-billion-parameter model
running locally, and the live queue is ~90 tickets, so ONE turn means prefilling a ~55k-token
context and generating up to ~9.5k tokens of plan: minutes per turn on a laptop, and a full run can
exceed the 900s default --timeout. That is the model being large, not the tool being stuck — every
turn prints a `~ <label>: asking <model> (num_ctx=..., num_predict=..., Ns left)...` line before it
waits and how long it took after, so progress is visible. Raise --timeout for a long queue, cap the
work with --dispatch N, or start with --probe (instant) and --selftest (seconds, and it needs no
model at all). --plan on the live queue is the honest smoke test; --selftest is the fast one.

--dispatch N caps how many of the plan's decisions are executed (default 5), mirroring pair_loop's
--dispatch. --plan runs the SAME agent with the SAME 5 tools and still journals its decisions — that
is the agent's mandate, and a journal note is routing metadata, the only kind of thing dispatch can
ever write — but the HARNESS then performs no action at all: no pair is spawned, no stop ticket is
minted, and no kind is applied (a kind is set-once, so labelling on a dry run would burn the one
chance the real run has to label it). --plan is therefore "decide and journal", not "read-only": the
agent is a dispatch agent in both modes, and journaling is what a dispatch agent does. The one thing
it can never do, in either mode, is author work product.

SIDE EFFECTS, STATED PLAINLY (the ticket forbids the AGENT code/shell/file-writes; this states what
the HARNESS does, so the two are never confused):
  * The AGENT (the model) writes nothing but routing metadata through the 5 routes above. It has no
    file, shell, git, or code tool in its context. --selftest proves a refused write creates no file.
  * The HARNESS (this file, no model involved) does what a harness must: it launches child processes
    (`pair_loop.py` per "run", and the MCP server itself), and on a "stop" it mints a stop ticket via
    ticket.create. It writes no file into the repo except the one exception every tool in this repo
    shares: an unexpected exception appends a Variant-A bug report to the registry's bug_reports
    sink (note-for-claude; registry.json "bug_reports").
  * --selftest is the exception to the exception: it drives a throwaway temp directory and a
    throwaway stub of the REST surface bound to 127.0.0.1 on an ephemeral port, then deletes the
    directory. It needs no db, no Ollama, no api key and no external network, spawns no pair, and
    touches this repo not at all.

Governance: the harness reads and writes ONLY through the governed REST surface (`rest.php?route=`)
with the same call semantics and `.secrets/ats.env` key loading pair_loop uses
(pair_loop.py:141-186) — this module holds no SQL pen. --dispatch/--plan refuse to start without
CONGRUENCY_API_KEY. The dispatch identity must already be REGISTERED (`agent.register`); its birth
prompt is read back from the record via `agent.prompt` and is what the model is born with, exactly
as pair_loop does (pair_loop.py:554-556).

Exit codes:
    0  the queue was routed (or --plan printed it; --probe: the grant is the ticket's five and the
       model is ready; --selftest: every check PASSED)
    1  --selftest: at least one check FAILED. --probe: the grant is NOT the ticket's five, or the
       dispatch model is unavailable (not installed, or Ollama unreachable)
    2  usage/configuration error, or an unexpected fault — a one-line message (never a traceback),
       and a Variant-A bug report was filed
"""
import argparse
import http.server
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request


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


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT, REGISTRY = find_registry(HERE)
CONG = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")

DISPATCH_AGENT = "dispatch-01"          # the registered identity every decision is journaled as
DISPATCH_ROLE = "dispatch"              # ticket_api_mcp.py's profile name (ticket_api_mcp.py:366)
MCP_SERVER = os.path.join(HERE, "ticket_api_mcp.py")
PAIR_LOOP = os.path.join(HERE, "pair_loop.py")

# research #174 §6 (#179): "num_ctx >= 32k (role_model_fit affordance B — the default 4096 silently
# truncates a full-queue dispatch)". Capped by the model's real context length at request time.
DISPATCH_NUM_CTX_FLOOR = 32768

# num_ctx sizes the model's INPUT; num_predict caps its OUTPUT, and the two truncate different ends
# of the same dispatch. One step is one small tool call, but the PLAN carries one entry per queued
# ticket, so its budget must scale with the queue or the reply is cut off mid-array — and a truncated
# reply is invalid JSON, which the retry loop cannot fix because every retry truncates in the same
# place. Measured against the live queue: a plan entry runs ~150 chars ≈ 36 tokens (~4 chars/token,
# ollama_agent.py:312-321's own conversion), so a 79-ticket queue needs ~2900 — more than a flat
# 2048 would ever emit. 96 tokens/ticket is that measurement with ~2.5x headroom for long reasons.
STEP_NUM_PREDICT = 1024                 # one tool call: {"thought","tool","args"} and nothing more
PLAN_TOKENS_PER_TICKET = 96
PLAN_NUM_PREDICT_FLOOR = 2048


def plan_num_predict(queue_len):
    """The output budget for the plan, sized to the queue. See STEP_NUM_PREDICT above."""
    return max(PLAN_NUM_PREDICT_FLOOR, PLAN_TOKENS_PER_TICKET * int(queue_len) + 512)

# The exact grant (research #174 §2/§2.1; served by ticket_api_mcp.py:366). This module does not
# GRANT these — the MCP server does. This tuple is what we ASSERT the server handed us, so a drift
# in that file is caught here loudly instead of silently widening the model's surface.
DISPATCH_TOOLS = ("ticket_queue", "ticket_kind", "ticket_assign", "edge_record", "ticket_progress")

# Routes that can emit work product. The grant must not intersect this set — that is what
# "cannot author work product" MEANS, asserted mechanically rather than promised in prose.
WORK_PRODUCT_ROUTES = ("work.record", "artifact.record", "doc.record", "source.record",
                       "bug.record", "ticket.create", "ticket.lesson", "agent.register")

CONTROL_KINDS = ("stop", "start")       # migrations/0029_ticket_authorization.sql:44-45
FINISH = "finish"


def _secret(name):
    """The key, from the same two places pair_loop reads it (pair_loop.py:141-147): the secrets file
    beside the repo first, then the environment."""
    path = os.path.join(os.path.dirname(ROOT), ".secrets", "ats.env")
    if os.path.isfile(path):
        for line in open(path):
            if line.strip().startswith(name + "="):
                return line.strip().split("=", 1)[1]
    return os.environ.get(name)


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks).
    Mirrors pair_loop.bug_report (pair_loop.py:153-166)."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "gemma_dispatch_agent.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:], "note": "gemma dispatch agent",
            }) + "\n")
    except Exception:  # noqa: BLE001
        pass


class Unexpected(RuntimeError):
    pass


class Refused(RuntimeError):
    """A tool call a layer forbids. Reported BACK to the model as a tool result it can react to —
    never raised out of the run."""


def log(msg):
    print(msg)
    sys.stdout.flush()


# ── the governed REST surface — the HARNESS's identity, never the model's ────────────────────────
# The model reaches the db ONLY through the MCP dispatch profile. These two functions are the
# harness half: reading the queue and the brake, and the governance writes (ticket.create for a
# stop) that research §2 keeps out of every model-driven role. Semantics mirror pair_loop.py:174-190.
def rest(route, obj=None, method=None):
    url = CONG + "/rest.php?route=" + route
    if obj is not None and (method or "POST") == "GET":
        url += "&" + "&".join("%s=%s" % (k, urllib.request.quote(str(v))) for k, v in obj.items())
        obj = None
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json",
                                          "X-Api-Key": _secret("CONGRUENCY_API_KEY") or ""})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.loads(r.read().decode())
    except urllib.error.URLError as e:
        raise Unexpected("the congruency REST surface is unreachable at %s (%s) — is the server "
                         "running? Override with $CONGRUENCY_URL." % (CONG, e.reason))
    if "error" in out:
        raise Unexpected("route %s failed: %s" % (route, out["error"]))
    return out


def rows(route, params):
    return rest(route, params, method="GET").get("rows", [])


# ── ollama_agent.py: the R4-proven transport/extractor/validator, reused rather than re-derived ──
_OA = None


def load_ollama_agent():
    """Import the sibling ollama_agent.py by path — the repo's established way of loading a sibling
    module (tracker/signals-mcp/server.py:31-35 `_load_store()`; ollama_agent.py:1012-1033 does the
    same to reach pair_loop).

    WHY REUSE IT: ollama_agent.py already carries research #175's measured channel — `format`-
    constrained turns, the native-tool_calls -> content-fallback extractor ladder, the strict
    validator (types, required keys, enum membership, int-not-string) and the live context-length
    probe. Re-implementing them here would be a second, unmeasured copy that could drift from the
    research the gate depends on. It also owns the role->model map, so `gemma3:27b` for dispatch is
    read from one place.

    dont_write_bytecode is forced for the duration: importing a module normally drops a
    `__pycache__/ollama_agent.cpython-*.pyc` NEW FILE next to the source, and --selftest claims it
    touches this repo not at all — a claim about behavior has to be made true by the code, not
    softened in the prose. The flag is restored afterwards."""
    global _OA
    if _OA is not None:
        return _OA
    if not os.path.isfile(os.path.join(HERE, "ollama_agent.py")):
        raise Unexpected("ollama_agent.py not found next to this tool (%s) — this module reuses its "
                         "Ollama transport, extractor and validator" % HERE)
    spec = importlib.util.spec_from_file_location("ollama_agent",
                                                  os.path.join(HERE, "ollama_agent.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["ollama_agent"] = m
    prev = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(m)
    finally:
        sys.dont_write_bytecode = prev
    _OA = m
    return m


def oa_call(fn, *args, **kwargs):
    """Call into ollama_agent, re-raising ITS Unexpected as THIS module's.

    ollama_agent defines its own `Unexpected` (ollama_agent.py:220-221) — a DIFFERENT class from
    this module's, despite the identical name. Without this seam an unreachable Ollama would raise
    `ollama_agent.Unexpected`, sail straight past `except Unexpected` in main, and print a traceback
    — which the docstring promises never happens. Re-raising across the seam is exactly what
    ollama_agent itself does when it drives pair_loop (ollama_agent.py:1049-1050). Proven by
    --selftest (check x1), so the promise is enforced rather than remembered."""
    try:
        return fn(*args, **kwargs)
    except load_ollama_agent().Unexpected as e:
        raise Unexpected(str(e))


# ── the MCP client: the model's ONE tool surface, started with --role dispatch ───────────────────
class McpClient:
    """Speaks JSON-RPC 2.0 over a child `ticket_api_mcp.py --role dispatch`'s stdin/stdout.

    THIS IS THE TRUST BOUNDARY (research #174 §4 option (c)). The model's tool inventory is whatever
    this server's `tools/list` returns and nothing else, because nothing else is connected: no
    built-in Read/Write/Edit/Bash, no codebean, no git-surface. The server is launched with
    `--role dispatch`, so it registers only that profile (ticket_api_mcp.py:450-452) and refuses any
    call outside it server-side as well (:455-460).

    Deliberately NOT given a --deliverable: `file_write_deliverable` is not in the dispatch profile
    at all, and a launch with no deliverable declared refuses every write anyway
    (ticket_api_mcp.py:239-241). Two reasons the writer cannot fire, not one.
    """

    def __init__(self, server=None, role=DISPATCH_ROLE, root=None, env=None, agent_id=DISPATCH_AGENT):
        self.server = server or MCP_SERVER
        self.role = role
        self.root = root or ROOT
        self.env = env
        self.agent_id = agent_id
        self.proc = None
        self.tools = []
        self.calls = []          # every (name, args, ok) the model made — the evidence trail
        self.reattributed = 0    # journal notes the model tried to sign as someone else
        self._id = 0

    # ── transport ──
    def start(self):
        if not os.path.isfile(self.server):
            raise Unexpected("the MCP bridge is not next to this tool (%s) — build #178 provides it"
                             % self.server)
        env = dict(os.environ if self.env is None else self.env)
        # stderr is INHERITED on purpose: the server logs its refusals there (ticket_api_mcp.py:
        # 418-422) and they are evidence. A PIPE nobody drains would eventually block the child.
        self.proc = subprocess.Popen(
            [sys.executable or "python3", self.server, "--role", self.role, "--root", self.root],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env, cwd=self.root)
        init = self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                        "clientInfo": {"name": "gemma_dispatch_agent",
                                                       "version": "1.0.0"}})
        if "error" in init:
            raise Unexpected("the MCP bridge refused the handshake: %s" % init["error"])
        self._notify("notifications/initialized")
        listed = self._rpc("tools/list", {})
        if "error" in listed:
            raise Unexpected("the MCP bridge would not list tools for role %r: %s"
                             % (self.role, listed["error"]))
        self.tools = listed["result"]["tools"]
        return self.tools

    def close(self):
        if not self.proc:
            return
        try:
            self.proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc = None

    def _rpc(self, method, params, notify=False):
        """One JSON-RPC round trip. Raw: NO client-side allowlist check — this is the wire, and
        --selftest uses it to prove the SERVER refuses on its own (layer 3), independently of
        whatever this client would have done."""
        if not self.proc:
            raise Unexpected("the MCP bridge is not running (call start() first)")
        req = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notify:
            self._id += 1
            req["id"] = self._id
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        if notify:
            return None
        line = self.proc.stdout.readline()
        if not line:
            raise Unexpected("the MCP bridge closed its stdout mid-call (method %r)" % method)
        return json.loads(line)

    def _notify(self, method, params=None):
        self._rpc(method, params or {}, notify=True)

    def tool_names(self):
        return [t["name"] for t in self.tools]

    # ── the model's call path ──
    def call(self, name, args):
        """Invoke one tool ON BEHALF OF THE MODEL. Returns the parsed result; raises Refused with a
        message the model can read and correct itself against.

        Layer 4 (the weakest, never relied on): refuse a name absent from tools/list, and PIN the
        journal identity so "journals every decision as the dispatch agent" is enforced rather than
        hoped for. Layers 1-3 (launch, decoder enum, server allowlist) already hold without this."""
        if name not in self.tool_names():
            raise Refused("tool %r is not in this agent's grant (role %s grants exactly: %s). This "
                          "agent routes; it never authors." % (name, self.role,
                                                               ", ".join(self.tool_names())))
        args = dict(args or {})
        if name == "ticket_progress":
            if args.get("agent_id") not in (None, self.agent_id):
                self.reattributed += 1
                log("   ! journal note signed %r re-attributed to %s (the dispatch agent journals "
                    "as itself)" % (args.get("agent_id"), self.agent_id))
            args["agent_id"] = self.agent_id
        resp = self._rpc("tools/call", {"name": name, "arguments": args})
        if "error" in resp:
            self.calls.append((name, args, False))
            raise Refused(resp["error"].get("message") or json.dumps(resp["error"]))
        self.calls.append((name, args, True))
        payload = resp["result"]["content"][0]["text"]
        try:
            return json.loads(payload)
        except ValueError:
            return {"text": payload}

    def called(self, name):
        return [args for n, args, ok in self.calls if n == name and ok]


# ── the model's step / plan schemas (research #175 §5.1: intents as schema-constrained JSON) ─────
def step_schema(tools):
    """One tool call, or `finish`. The `tool` enum is built from the MCP server's OWN tools/list, so
    the constrained decoder cannot spell a tool the profile does not grant (layer 2). Mirrors
    ollama_agent.step_schema (ollama_agent.py:760-774): `args` merges every granted tool's
    properties, all optional — one object shape the grammar can compile, with per-tool required-key
    checking done server-side at dispatch time (ticket_api_mcp.py:405-409)."""
    props = {}
    for t in tools:
        props.update((t.get("inputSchema") or {}).get("properties") or {})
    return {"type": "object",
            "properties": {"thought": {"type": "string"},
                           "tool": {"type": "string",
                                    "enum": [t["name"] for t in tools] + [FINISH]},
                           "args": {"type": "object", "properties": props}},
            "required": ["tool", "args"]}


# The plan envelope. Identical in shape to what pair_loop's dispatcher returns and what
# ollama_agent.ENVELOPES["dispatch"] declares (ollama_agent.py:401-414), so a plan from this agent
# is readable by anything that already reads pair_loop's (pair_loop.py:566, :571-590).
PLAN_SCHEMA = {
    "type": "object",
    "properties": {"plan": {"type": "array", "items": {
        "type": "object",
        "properties": {"ticket": {"type": "integer"},
                       "action": {"type": "string", "enum": ["run", "skip", "stop"]},
                       "kind": {"type": "string"},
                       "deliverable": {"type": "string"},
                       "reason": {"type": "string"}},
        "required": ["ticket", "action", "reason"]}}},
    "required": ["plan"]}

PLAN_SHAPE = ('{"plan": [{"ticket": <id>, "action": "run|skip|stop", "kind": "<kind-or-empty>", '
              '"deliverable": "<path-or-empty>", "reason": "<why>"}]}')

SYSTEM = """You are %(agent)s, the dispatch agent. You ROUTE the ticket queue. You never author work
product: you cannot write code, write a file, or run a command, because no such tool exists for you.

You act ONE STEP AT A TIME. Every reply is exactly one JSON object and nothing else:
  {"thought": "<why, one short line>", "tool": "<tool name>", "args": {<the tool's arguments>}}
The tool result comes back as the next message. Then you emit the next step.

The ONLY tools that exist for you are these — any other name is refused:
%(tools)s
  finish — you have journaled every decision and are ready to give your plan. args: {}

Example of one step:
  {"thought": "journal my decision on #41", "tool": "ticket_progress", "args": {"ticket_id": 41,
   "agent_id": "%(agent)s", "note": "dispatch: run — build ticket, one deliverable"}}

Rules:
- Journal EVERY ticket you decide with ticket_progress, as yourself (%(agent)s), before you finish.
- Do not re-read what you were already given: THE QUEUE below is complete and already carries the
  stop/gate flags. ticket_queue is available if you want to confirm it.
- When every decision is journaled, emit {"thought": "...", "tool": "finish", "args": {}} and you
  will then be asked for your plan.
"""

# Mirrors pair_loop.DISPATCH_RULES (pair_loop.py:521-531) — the same decision rules the current
# dispatcher is given — with the pre-computed flags made explicit, per research #173 affordance A.
DISPATCH_RULES = """
THE QUEUE above lists open/requested tickets. The harness has already read the brake for you and
attached two booleans to each ticket — you cannot and need not look them up yourself:
  "has_active_stop": true  => an unreleased stop ticket aims at it (or at an ancestor): it
                              authorizes NOTHING right now.
  "gated": true            => not actionable by a pair: it is stopped, or it IS a control ticket
                              (kind "stop"/"start"). The only correct action for a gated ticket is
                              "skip". A "run" on a gated ticket is overridden by the harness anyway.

For EACH ticket decide ONE action:
- "run": actionable NOW by a single pair producing ONE deliverable file. Supply "kind" (choose from
  the pair kinds if the ticket is unkinded: build, bug, documentation, bet) and "deliverable" (a
  repo-relative path — mirror the existing layout, e.g. tools go under
  checkouts/current/congruency/tools/, docs under docs/). Never choose "run" for a gated ticket.
- "skip": not actionable — gated tickets, work that needs a spec or a graft first, or anything too
  big for one deliverable. Supply "reason". Be conservative: prefer skip-with-reason over guessing.
- "stop": a job that should NOT proceed at all. Supply "reason" — the harness will aim a stop ticket
  at it. (You cannot create tickets yourself; you are recommending, and the harness acts.)

You route; you never author work product. Decide every ticket in the queue exactly once.
"""


# ── the model driver ─────────────────────────────────────────────────────────────────────────────
class OllamaDriver:
    """gemma3:27b over Ollama, every turn JSON-Schema-constrained and validated.

    Mirrors ollama_agent.constrained (ollama_agent.py:823-855) — research #175 §5.2's ask/extract/
    VALIDATE/corrective-retry wrapper — and reuses its transport, extractor and validator verbatim.
    It is not called directly because `constrained` sizes num_ctx from the payload alone
    (ollama_agent.py:312-321, floor 8192) and takes no override, while research #174 §6 requires a
    32k floor for THIS role: a full queue reasoned over at 8192 is the truncation the flag exists to
    prevent. Everything else is the same code path."""

    def __init__(self, model=None, retries=2, timeout=900, num_ctx=None):
        oa = load_ollama_agent()
        self.oa = oa
        # research #173 §3.1's dispatch pick, read from ollama_agent so the two cannot drift.
        self.model = model or oa.ROLE_MODELS["dispatch"]
        self.retries = retries
        self.num_ctx_override = num_ctx
        self.deadline = time.time() + timeout

    def preflight(self):
        caps = oa_call(self.oa.installed_models)
        if self.model not in caps:
            raise Unexpected("model %r is not installed in Ollama at %s (have: %s) — run "
                             "`ollama pull %s`" % (self.model, self.oa.OLLAMA,
                                                   ", ".join(sorted(caps)) or "none", self.model))
        # research #175 §5.1/§5.4: gemma3 advertises no "tools" capability and hard-errors on a
        # tools array. This driver never sends one — intents travel as constrained JSON — so a
        # model without the capability is fine and needs no warning.
        return caps

    def num_ctx_for(self, chars):
        """Payload-sized, floored at the dispatch floor, capped at what the model really supports.
        ~4 chars/token + 50% headroom is ollama_agent.num_ctx_for's own conversion
        (ollama_agent.py:312-321); context_cap reads the real length live from Ollama's /api/show."""
        if self.num_ctx_override:
            return int(self.num_ctx_override)
        want = int((chars / 4.0) * 1.5) + 2048
        return min(oa_call(self.oa.context_cap, self.model), max(DISPATCH_NUM_CTX_FLOOR, want))

    def ask(self, messages, schema, label="step", num_predict=STEP_NUM_PREDICT):
        convo = list(messages)
        nctx = self.num_ctx_for(sum(len(m.get("content") or "") for m in convo) + 2000)
        last = ""
        for attempt in range(self.retries + 1):
            left = self.deadline - time.time()
            if left <= 0:
                raise Unexpected("the dispatch agent exceeded its time budget (raise --timeout)")
            # A 27B model reasoning over a 90+ ticket queue takes minutes per turn, and a silent
            # tool is indistinguishable from a hung one. Say what is being waited on, before the
            # wait rather than after it.
            log("   ~ %s: asking %s (num_ctx=%d, num_predict=%d, %ds left)..."
                % (label, self.model, nctx, num_predict, int(left)))
            t0 = time.time()
            out = oa_call(self.oa.chat, self.model, convo, fmt=schema, num_ctx=nctx,
                          num_predict=num_predict, timeout=max(5, int(left)))
            log("   ~ %s: replied in %.1fs" % (label, time.time() - t0))
            msg = (out or {}).get("message") or {}
            obj, err = self.oa.extract_json(msg)
            if obj is not None:
                err = self.oa.validate(obj, schema, label)
                if not err:
                    return obj
            last = err
            log("   ! %s attempt %d/%d rejected: %s" % (label, attempt + 1, self.retries + 1, last))
            convo = convo + [
                {"role": "assistant", "content": msg.get("content") or json.dumps(obj or {})},
                {"role": "user", "content": "That reply was rejected: %s\nEmit ONE valid JSON object "
                                            "that matches the schema exactly. No prose, no code "
                                            "fences." % last},
            ]
        raise Unexpected("%s: no schema-conformant reply from %s after %d attempts — last error: %s"
                         % (label, self.model, self.retries + 1, last))


# ── the brake, pre-computed by the HARNESS (research #173 affordance A) ──────────────────────────
def queue_with_flags():
    """The queue, each ticket carrying has_active_stop/gated. `ticket.stops` is read HERE, by the
    harness, and is deliberately absent from the model's grant (research #174 §2 note): the model
    applies the rule, it never performs the cross-ticket reverse lookup."""
    queue = rows("ticket.queue", {})
    for t in queue:
        st = rows("ticket.stops", {"ticket_id": t["id"]})
        stops = int(st[0].get("active_stops") or 0) if st else 0
        t["has_active_stop"] = stops > 0
        t["gated"] = bool(stops > 0 or (t.get("kind") or "") in CONTROL_KINDS)
    return queue


def gate_reason(t):
    """Why a ticket is gated, in the words the journal will carry. None if it is not gated."""
    if t.get("has_active_stop"):
        return "an unreleased stop ticket aims at #%s or an ancestor — it authorizes nothing" % t["id"]
    if (t.get("kind") or "") in CONTROL_KINDS:
        return "#%s is a control ticket (kind %s) — it is applied by a graft, not run by a pair" \
               % (t["id"], t.get("kind"))
    return None


# ── the agent run: the model, its 5 tools, and its plan ──────────────────────────────────────────
def run_agent(driver, mcp, queue, birth_prompt, max_steps=24):
    """Drive the model to a plan, using ONLY the MCP dispatch profile. Returns the plan list."""
    tools = mcp.tools
    granted = mcp.tool_names()
    log("== dispatch agent == model=%s tools=[%s] queue=%d ticket(s)"
        % (getattr(driver, "model", "scripted"), ",".join(granted), len(queue)))

    system = SYSTEM % {"agent": mcp.agent_id,
                       "tools": "\n".join("  %s — %s" % (t["name"], t.get("description", ""))
                                          for t in tools)}
    user = (birth_prompt + "\n\nTHE QUEUE:\n" + json.dumps(queue, indent=1) + "\n" + DISPATCH_RULES)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    schema = step_schema(tools)

    for step_no in range(1, max_steps + 1):
        stp = driver.ask(messages, schema, label="step %d" % step_no)
        name, args = stp.get("tool"), stp.get("args") or {}
        messages.append({"role": "assistant", "content": json.dumps(stp)})
        if name == FINISH:
            log("   . finish after %d step(s)" % step_no)
            break
        log("   . step %d: %s %s" % (step_no, name, json.dumps(args)[:120]))
        try:
            result = json.dumps(mcp.call(name, args))[:4000]
        except Refused as e:
            result = "REFUSED: %s" % e
            log("   ! refused: %s" % e)
        except Exception as e:  # noqa: BLE001 — a tool fault is a RESULT the model can react to
            result = "ERROR: %s: %s" % (type(e).__name__, e)
        messages.append({"role": "user", "content": "TOOL RESULT (%s):\n%s" % (name, result)})
    else:
        log("   ! --max-steps (%d) reached; asking for the plan now (every decision the model did "
            "not journal is journaled by the harness below)" % max_steps)

    messages.append({"role": "user", "content":
                     "Stop using tools. Emit your FINAL plan now as ONE JSON object of exactly this "
                     "shape:\n%s\nOne entry per ticket in the queue. No prose, no code fences."
                     % PLAN_SHAPE})
    # sized to the queue: a flat budget truncates a long plan into invalid JSON (see plan_num_predict)
    return driver.ask(messages, PLAN_SCHEMA, label="plan",
                      num_predict=plan_num_predict(len(queue))).get("plan", [])


# ── the harness half: enforce the plan, journal it, execute it ───────────────────────────────────
def safe_deliverable(path):
    """A deliverable is a repo-relative path the CHILD's worker will write. The model never writes
    it — but the harness hands it to a child process, so it is guarded here rather than trusted:
    absolute paths and any `..` escape are refused."""
    if not isinstance(path, str) or not path.strip():
        return None, "no deliverable path"
    if os.path.isabs(path):
        return None, "deliverable %r is absolute; it must be repo-relative" % path
    full = os.path.realpath(os.path.join(ROOT, path))
    root = os.path.realpath(ROOT)
    if full != root and not full.startswith(root + os.sep):
        return None, "deliverable %r escapes the repo root" % path
    return path, None


def child_cmd(tid, deliverable, a):
    """The `--ticket` child a dispatched "run" becomes: its own process, its own branch+worktree.
    Mirrors pair_loop.child_cmd (pair_loop.py:534-542)."""
    cmd = [sys.executable or "python3", PAIR_LOOP, "--ticket", str(tid),
           "--deliverable", deliverable, "--rounds", str(a.rounds), "--timeout", str(a.timeout)]
    if a.base:
        cmd += ["--base", a.base]
    return cmd


def spawn_children(runs, a):
    """Launch the pairs, up to --parallel at a time; each child owns its own branch + worktree.
    Mirrors pair_loop.do_dispatch's lane loop (pair_loop.py:592-607). HARNESS-HELD: the model has no
    shell and cannot reach this — it emitted a plan, and the harness acts on it."""
    out, lanes, pending = [], [], list(runs)
    log("== dispatch == running %d pair(s), up to %d at a time (branch+worktree each)"
        % (len(runs), max(1, a.parallel)))
    while pending or lanes:
        while pending and len(lanes) < max(1, a.parallel):
            tid, deliv = pending.pop(0)
            p = subprocess.Popen(child_cmd(tid, deliv, a), cwd=ROOT)
            lanes.append((tid, p))
            log("   -> #%s dispatched on branch ticket/%s (pid %s)" % (tid, tid, p.pid))
        for tid, p in list(lanes):
            if p.poll() is not None:
                lanes.remove((tid, p))
                out.append((tid, "run -> exit %s" % p.returncode))
        if lanes:
            time.sleep(1)
    return out


def mint_stop(tid, reason):
    """Aim a stop ticket at #tid. HARNESS-HELD, because `ticket.create` is not in the dispatch
    profile (research #174 §5.4) — the model recommends "stop"; only the harness can mint one.
    Mirrors pair_loop.do_dispatch (pair_loop.py:583-588)."""
    out = rest("ticket.create", {"component": "congruency", "severity": "normal", "patch": "",
                                 "title": "STOP: #%s (dispatched)" % tid, "body": reason or ""})
    sid = int(out.get("rowid", 0))
    rest("ticket.kind", {"id": sid, "kind": "stop"})
    rest("edge.record", {"parent_id": sid, "child_id": tid, "kind": "stops"})
    return sid


def dedupe_plan(plan):
    """One decision per ticket, first wins. See apply_plan's dedupe note for why this matters."""
    out, seen = [], set()
    for d in plan:
        tid = d.get("ticket")
        if tid in seen:
            log("   ! plan decides #%s more than once — keeping the first decision" % tid)
            continue
        seen.add(tid)
        out.append(d)
    return out


def apply_plan(plan, queue, mcp, a, execute=True, spawn=spawn_children, mint=mint_stop):
    """Enforce, journal, and execute the plan. Returns (results, runs).

    ENFORCEMENT IS HERE, NOT IN THE PROMPT. The model is asked to respect the gate; this function
    does not depend on it having done so:
      * a ticket the queue does not contain is refused outright (the model cannot route what was
        never offered, nor invent an id);
      * a gated ticket is FORCED to "skip" whatever the model answered — the brake is the harness's,
        exactly as it is pair_loop's (pair_loop.py:1002-1006);
      * a "run" with no usable deliverable path degrades to "skip", never to a guess;
      * a ticket the model decided TWICE is decided once — see the dedupe below.
    Every decision — the model's and every override — is journaled as the dispatch agent through
    ticket_progress, which is the ticket's "journals every decision" requirement made mechanical:
    the loop below journals each item exactly once, so a model that finished early or ran out of
    steps still leaves a complete record.
    """
    by_id = {t["id"]: t for t in queue}
    results, runs = [], []

    # One decision per ticket, first wins. A queue of 90+ is a long generation and a model can
    # repeat an entry; two "run"s on one id would launch two pair_loop children for the SAME
    # ticket, and each child opens that ticket's branch and worktree (pair_loop.py:1009-1013) — so
    # the pair would contend with itself over one branch. Deduping BEFORE the cap also keeps
    # --dispatch N a count of tickets, not of repetitions.
    plan = dedupe_plan(plan)

    for d in plan[: max(0, a.dispatch)]:
        tid, act = d.get("ticket"), d.get("action")
        reason = (d.get("reason") or "").strip()

        if tid not in by_id:
            log("   ! plan names #%s, which is not in the queue — refused" % tid)
            results.append((tid, "refused — not in the queue"))
            continue

        t = by_id[tid]
        gate = gate_reason(t)
        if gate and act != "skip":
            log("   ! OVERRIDE #%s: model said %r; %s" % (tid, act, gate))
            reason = "harness override (model said %r): %s%s" % (act, gate,
                                                                 ("; model's reason: " + reason) if reason else "")
            act = "skip"

        deliverable = None
        if act == "run":
            deliverable, why = safe_deliverable(d.get("deliverable"))
            if not deliverable:
                log("   ! #%s: run refused — %s" % (tid, why))
                act, reason = "skip", "run refused — %s%s" % (why, ("; model's reason: " + reason) if reason else "")

        # journal EVERY decision, as the dispatch agent, through the dispatch profile
        note = "dispatch: %s — %s" % (act, reason or deliverable or "(no reason given)")
        try:
            mcp.call("ticket_progress", {"ticket_id": tid, "agent_id": mcp.agent_id, "note": note})
        except (Refused, Unexpected) as e:
            log("   ! could not journal the decision on #%s: %s" % (tid, e))

        if act == "run":
            # `execute` gates this because --plan promises the harness performs NO action, and a
            # kind is set-once: labelling on a dry run would permanently consume the one chance the
            # real run has to label it (tg_tickets_immutable_identity, 0029:111-117). A promise in
            # the usage text has to be made true here, not softened there.
            if execute and d.get("kind"):
                # set-once; the identity trigger refuses re-kinding an already-kinded ticket
                # (migrations/0029_ticket_authorization.sql:111-117), so a refusal here is the db
                # holding a line, not a fault: the existing kind stands and the run proceeds.
                try:
                    mcp.call("ticket_kind", {"id": tid, "kind": d["kind"]})
                except (Refused, Unexpected) as e:
                    log("   . #%s keeps its existing kind (%s)" % (tid, e))
            runs.append((tid, deliverable))
        elif act == "stop":
            if execute:
                sid = mint(tid, reason)
                results.append((tid, "stopped by #%s" % sid))
            else:
                results.append((tid, "would stop (--plan: nothing minted) — %s" % reason))
        else:
            results.append((tid, "skip — %s" % reason))

    if runs:
        if execute:
            results.extend(spawn(runs, a))
        else:
            results.extend((tid, "would run -> %s (--plan: nothing spawned)" % deliv)
                           for tid, deliv in runs)
    return results, runs


# ── the modes ────────────────────────────────────────────────────────────────────────────────────
def birth_prompt_of(agent_id):
    """The dispatch agent's REGISTERED birth prompt, read back from the record — the same thing
    pair_loop.do_dispatch does (pair_loop.py:554-556). The identity is a fact on the record, not a
    string this file invents."""
    reg = rows("agent.prompt", {"agent_id": agent_id})
    if not reg:
        raise Unexpected("%s is not registered — agent.register it first (pair_loop.py:554-556 "
                         "requires the same)" % agent_id)
    return reg[0]["prompt"]


def do_dispatch(a, execute=True):
    if not _secret("CONGRUENCY_API_KEY"):
        raise Unexpected("no CONGRUENCY_API_KEY (checked $CONGRUENCY_API_KEY and %s) — the governed "
                         "routes need it to read the queue and journal the decisions"
                         % os.path.join(os.path.dirname(ROOT), ".secrets", "ats.env"))
    driver = OllamaDriver(model=a.model, retries=a.retries, timeout=a.timeout, num_ctx=a.num_ctx)
    driver.preflight()
    prompt = birth_prompt_of(a.agent_id)
    queue = queue_with_flags()
    if not queue:
        log("== dispatch == queue is empty; nothing to route")
        return 0
    gated = [t["id"] for t in queue if t["gated"]]
    log("== brake == %d of %d queued ticket(s) are gated%s"
        % (len(gated), len(queue), (": " + ", ".join("#%s" % i for i in gated)) if gated else ""))

    mcp = McpClient(server=a.server, agent_id=a.agent_id)
    try:
        mcp.start()
        assert_grant(mcp)
        plan = run_agent(driver, mcp, queue, prompt, max_steps=a.max_steps)
        if not plan:
            raise Unexpected("%s returned no plan" % a.agent_id)
        results, _runs = apply_plan(plan, queue, mcp, a, execute=execute)
    finally:
        mcp.close()

    for tid, what in results:
        log("== %s == #%s: %s" % ("dispatched" if execute else "planned", tid, what))
    if mcp.reattributed:
        log("== journal == %d note(s) the model tried to sign as another agent were re-attributed "
            "to %s" % (mcp.reattributed, a.agent_id))
    return 0


def assert_grant(mcp):
    """The grant the server actually handed us must be EXACTLY the ticket's five. This is a
    tripwire, not the enforcement: the enforcement is that nothing else is connected and that the
    server refuses out-of-role calls. If ticket_api_mcp.py's dispatch profile ever widens, this
    stops the run instead of quietly handing a model more power."""
    got = sorted(mcp.tool_names())
    want = sorted(DISPATCH_TOOLS)
    if got != want:
        raise Unexpected("the MCP bridge granted role %r the tools %s, but this agent's mandate is "
                         "exactly %s — refusing to run with a grant that is not the ticket's"
                         % (mcp.role, ", ".join(got) or "(none)", ", ".join(want)))
    return got


def probe(a):
    """What this agent would ACTUALLY be granted, and whether its model is ready. Needs no db and no
    api key: tools/list never touches the REST surface."""
    mcp = McpClient(server=a.server, agent_id=a.agent_id)
    ok = True
    try:
        mcp.start()
        log("== grant == %s --role %s" % (os.path.relpath(mcp.server, ROOT), mcp.role))
        for t in mcp.tools:
            log("   %-18s %s" % (t["name"], t.get("description", "")))
        try:
            assert_grant(mcp)
            log("   -> exactly the ticket's five; no file, shell, git or code tool is present")
        except Unexpected as e:
            ok = False
            log("   -> MISMATCH: %s" % e)
    finally:
        mcp.close()

    try:
        oa = load_ollama_agent()
        model = a.model or oa.ROLE_MODELS["dispatch"]
        caps = oa_call(oa.installed_models)
        here = model in caps
        ok = ok and here
        log("== model == %s (research #173 §3.1's dispatch pick) — %s"
            % (model, "installed" if here else "MISSING: run `ollama pull %s`" % model))
        if here:
            log("   context length %s; this agent floors num_ctx at %d (research #174 §6)"
                % (oa_call(oa.context_cap, model), DISPATCH_NUM_CTX_FLOOR))
    except Unexpected as e:
        ok = False
        log("== model == %s" % e)
    return 0 if ok else 1


# ── --selftest: prove the ACCEPTANCE offline (no db, no Ollama, no api key, no pair spawned) ─────
class _StubHandler(http.server.BaseHTTPRequestHandler):
    """A throwaway stand-in for `rest.php`, bound to 127.0.0.1 on an ephemeral port.

    It is NOT the real surface and does not pretend to be: it serves the handful of routes this run
    touches, with the same {"rows": [...]} / {"error": ...} envelope pair_loop reads
    (pair_loop.py:184-190), so the selftest can drive the WHOLE stack — driver -> MCP subprocess ->
    REST -> journal — with nothing but a temp directory. Where it mirrors a db rule, the rule is
    cited; the real enforcement is always the db's."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # noqa: A002 — silence; the selftest prints its own lines
        pass

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return q.get("route", [""])[0], {k: v[0] for k, v in q.items() if k != "route"}

    def do_GET(self):
        route, params = self._route()
        st = self.server.state
        if route == "ticket.queue":
            return self._send({"rows": [dict(t) for t in st["queue"]]})
        if route == "ticket.stops":
            return self._send({"rows": [{"active_stops": st["stops"].get(int(params["ticket_id"]), 0)}]})
        if route == "agent.prompt":
            return self._send({"rows": [{"agent_id": params.get("agent_id"),
                                         "prompt": st["birth_prompt"]}]})
        return self._send({"error": "no such route: %s" % route})

    def do_POST(self):
        route, _ = self._route()
        st = self.server.state
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if route == "ticket.progress":
            st["journal"].append(body)
            return self._send({"ok": 1})
        if route == "ticket.kind":
            st["kinds"].append(body)
            return self._send({"ok": 1})
        if route == "ticket.assign":
            # mirrors tg_ticket_agents_registered (0029:152-156): only REGISTERED agents may be
            # authorized. The real trigger is the enforcement; this reproduces it so the path runs.
            if body.get("agent_id") not in st["registered"]:
                return self._send({"error": "unregistered agent: a ticket authorizes only "
                                            "REGISTERED agents (agent.register first)"})
            st["assigns"].append(body)
            return self._send({"ok": 1})
        if route == "edge.record":
            st["edges"].append(body)
            return self._send({"ok": 1})
        if route == "ticket.create":
            st["created"].append(body)
            return self._send({"rowid": 900 + len(st["created"])})
        return self._send({"error": "no such route: %s" % route})


class ScriptedDriver:
    """A recorded model, so the selftest is deterministic and needs no Ollama.

    Every scripted reply is pushed through the REAL schema validator on the way out, so a fixture
    that the live constrained decoder could not have produced FAILS here instead of quietly passing:
    the script cannot cheat the schema."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []
        self.budgets = []          # the num_predict each call was given, so sizing can be asserted

    def ask(self, messages, schema, label="step", num_predict=STEP_NUM_PREDICT):
        if not self.replies:
            raise Unexpected("the scripted model ran out of replies at %r" % label)
        self.budgets.append((label, num_predict))
        obj = self.replies.pop(0)
        err = load_ollama_agent().validate(obj, schema, label)
        if err:
            raise Unexpected("the scripted reply for %r does not match the schema this agent "
                             "constrains with: %s" % (label, err))
        self.seen.append((label, obj))
        return obj


def _tree(root):
    """Every path under root, so a run's file side effects can be diffed before/after."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            out.append(os.path.relpath(os.path.join(dirpath, fn), root))
    return sorted(out)


def selftest(a):
    """Prove the ticket's acceptance — routes a real queue correctly AND is structurally incapable
    of authoring work product — with no db, no Ollama, no api key and no pair spawned."""
    global CONG
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name,
                                ("  — %s" % detail) if detail and not cond else ""))

    base = tempfile.mkdtemp(prefix="gemma_dispatch-selftest-")
    saved_cong, httpd, mcp = CONG, None, None
    try:
        root = os.path.join(base, "repo")
        os.makedirs(os.path.join(root, "docs"))
        open(os.path.join(root, "registry.json"), "w").write('{"schema": 1, "package": "selftest"}\n')
        print("== selftest == throwaway root %s (this repo, the db and Ollama are untouched)" % root)

        # ── the fixture queue: one runnable, one stopped, one control, one to stop ──
        queue = [
            {"id": 41, "kind": None, "status": "OPEN", "component": "congruency",
             "title": "Build: a widget", "body": "make the widget",
             "has_active_stop": False, "gated": False},
            {"id": 42, "kind": "build", "status": "OPEN", "component": "congruency",
             "title": "Build: a stopped thing", "body": "halted work",
             "has_active_stop": True, "gated": True},
            {"id": 43, "kind": "stop", "status": "OPEN", "component": "congruency",
             "title": "STOP: #42", "body": "halt it", "has_active_stop": False, "gated": True},
            {"id": 44, "kind": "build", "status": "OPEN", "component": "congruency",
             "title": "Build: rewrite everything", "body": "unbounded",
             "has_active_stop": False, "gated": False},
        ]
        state = {"queue": [{k: v for k, v in t.items() if k not in ("has_active_stop", "gated")}
                           for t in queue],
                 "stops": {42: 1}, "journal": [], "kinds": [], "assigns": [], "edges": [],
                 "created": [], "registered": {"dispatch-01"},
                 "birth_prompt": "You are dispatch-01, the dispatcher. You route the queue."}
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
        httpd.state = state
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        stub = "http://127.0.0.1:%d" % httpd.server_address[1]
        CONG = stub
        print("== selftest == throwaway REST stub on %s (loopback only; no external network)" % stub)

        env = dict(os.environ)
        env["CONGRUENCY_URL"] = stub
        env["CONGRUENCY_API_KEY"] = "selftest"
        # The REAL bridge (build #178), launched --role dispatch. Its --root is the THROWAWAY root,
        # not this repo: a write that somehow got through would then land inside `root`, where the
        # before/after diff below would SEE it. Pointing it at the real repo would make that proof
        # watch a directory the refused call could never have touched — i.e. prove nothing.
        mcp = McpClient(root=root, env=env)
        mcp.start()

        # ── b: THE BOUNDARY — the grant is the 5, and nothing else exists ─────────────────────────
        print("-- b: the launch boundary (research #174 §4 option (c)): the grant IS the 5")
        listed = mcp.tool_names()
        ck("b1: the bridge grants EXACTLY the ticket's five tools",
           sorted(listed) == sorted(DISPATCH_TOOLS), ",".join(sorted(listed)))
        ck("b2: assert_grant accepts that grant", assert_grant(mcp) == sorted(DISPATCH_TOOLS))
        ck("b3: no file/shell/git/code tool is present at all",
           not (set(listed) & {"file_read", "file_write_deliverable", "git_read_file", "git_blame",
                               "git_log", "test_run", "save", "set_body", "Write", "Edit", "Bash"}),
           ",".join(sorted(listed)))
        ck("b4: no granted tool is a work-product sink (no work/artifact/doc/create route)",
           not (set(listed) & set(WORK_PRODUCT_ROUTES)))
        ck("b5: every granted tool's description names a routing route, not an authoring one",
           all(any(r in (t.get("description") or "")
                   for r in ("ticket.queue", "ticket.kind", "ticket.assign", "edge.record",
                             "ticket.progress")) for t in mcp.tools),
           "; ".join(t.get("description", "") for t in mcp.tools))

        # The tripwire, exercised against the profile that would ACTUALLY be dangerous: `worker`
        # carries file_write_deliverable and test_run. If a launch ever handed this agent that
        # surface, assert_grant must stop the run rather than quietly let a dispatcher author code.
        wide = McpClient(role="worker", root=root, env=env)
        try:
            wide.start()
            try:
                assert_grant(wide)
                ck("b6: a WIDER role (worker: a writer + an executor) is refused by assert_grant",
                   False, "it was accepted — a dispatcher could author code")
            except Unexpected as e:
                ck("b6: a WIDER role (worker: a writer + an executor) is refused by assert_grant",
                   "is not the ticket's" in str(e), str(e))
            ck("b7: ...and that wider role really did carry the authoring tools it was refused for",
               {"file_write_deliverable", "test_run"} <= set(wide.tool_names()),
               ",".join(sorted(wide.tool_names())))
        finally:
            wide.close()

        # ── d: THE DECODER — the constrained reply cannot even spell another tool ─────────────────
        print("-- d: the decoder enum (layer 2) is built from the grant")
        oa = load_ollama_agent()
        sch = step_schema(mcp.tools)
        ck("d1: the step enum is exactly the grant + finish",
           sch["properties"]["tool"]["enum"] == list(listed) + [FINISH],
           str(sch["properties"]["tool"]["enum"]))
        for forbidden in ("file_write_deliverable", "test_run", "work_record", "Bash", "Write"):
            err = oa.validate({"tool": forbidden, "args": {}}, sch, "step")
            ck("d2: a step naming %r fails the schema (\"is not one of\")" % forbidden,
               err is not None and "is not one of" in err, str(err))
        ck("d3: a granted tool passes the same schema",
           oa.validate({"thought": "read", "tool": "ticket_queue", "args": {}}, sch, "step") is None)

        # ── r: THE SERVER — refuses out-of-role calls on its own, and the write creates NO file ───
        print("-- r: the server allowlist (layer 3), proven on the wire, in isolation")
        # The path the write asks for is INSIDE the bridge's --root, so if the refusal ever stopped
        # working this file would appear and the diff below would catch it.
        deliv_target = os.path.join(root, "docs", "x.md")
        before = _tree(root)
        raw = mcp._rpc("tools/call", {"name": "file_write_deliverable",
                                      "arguments": {"path": "docs/x.md", "content": "code"}})
        ck("r1: a RAW file-write call (bypassing this client) is refused by the server",
           "error" in raw and raw["error"]["code"] == -32601 and "refused" in raw["error"]["message"],
           json.dumps(raw))
        ck("r1b: the refusal names the role and what the role MAY call",
           "dispatch" in raw["error"]["message"] and "ticket_queue" in raw["error"]["message"],
           json.dumps(raw))
        ck("r2: the refused write created NO file (before/after, nothing else touching it)",
           _tree(root) == before and not os.path.exists(deliv_target), "%s -> %s" % (before, _tree(root)))
        raw = mcp._rpc("tools/call", {"name": "test_run",
                                      "arguments": {"runner": "python3", "target": "x.py"}})
        ck("r3: the agent cannot EXECUTE anything (test_run refused)",
           "error" in raw and raw["error"]["code"] == -32601, json.dumps(raw))
        raw = mcp._rpc("tools/call", {"name": "work_record",
                                      "arguments": {"ticket_id": 41, "kind": "code", "ref": "x"}})
        ck("r4: the agent cannot mint a work UID (work_record is forge-only)",
           "error" in raw and raw["error"]["code"] == -32601, json.dumps(raw))
        try:
            mcp.call("file_write_deliverable", {"path": "docs/x.md", "content": "code"})
            ck("r5: this client refuses it too (layer 4)", False, "the call was allowed")
        except Refused as e:
            ck("r5: this client refuses it too (layer 4)", "not in this agent's grant" in str(e), str(e))

        # ── a: the agent cannot forge an authorization ────────────────────────────────────────────
        print("-- a: authorization integrity")
        try:
            mcp.call("ticket_assign", {"ticket_id": 41, "agent_id": "ghost-t41r1", "role": "coder"})
            ck("a1: assigning an UNREGISTERED agent is rejected", False, "it was allowed")
        except Refused as e:
            ck("a1: assigning an UNREGISTERED agent is rejected (mirrors "
               "tg_ticket_agents_registered, 0029:152-156)", "unregistered agent" in str(e), str(e))
        ck("a2: the rejected assign authorized nobody", state["assigns"] == [], str(state["assigns"]))
        ck("a3: agent.register is NOT in the grant, so it cannot register one either",
           "agent_register" not in listed and "agent.register" not in listed)

        # ── e: END TO END — the agent routes the queue, and the harness enforces the brake ────────
        print("-- e: routing the queue end to end (real bridge, real REST envelope, scripted model)")
        scripted = ScriptedDriver([
            {"thought": "read the queue", "tool": "ticket_queue", "args": {}},
            # the model journals #41 — but signs it as somebody else (layer 4 re-attributes it)
            {"thought": "journal 41", "tool": "ticket_progress",
             "args": {"ticket_id": 41, "agent_id": "somebody-else", "note": "dispatch: run — build"}},
            {"thought": "done", "tool": FINISH, "args": {}},
            # the plan: a good run, a "run" on a STOPPED ticket (the harness must override it), a
            # "run" on a CONTROL ticket (likewise), a stop, and an id that was never in the queue.
            {"plan": [
                {"ticket": 41, "action": "run", "kind": "build",
                 "deliverable": "docs/widget.md", "reason": "actionable; one deliverable"},
                {"ticket": 42, "action": "run", "kind": "build", "deliverable": "docs/halted.md",
                 "reason": "looks fine to me"},
                {"ticket": 43, "action": "run", "kind": "build", "deliverable": "docs/ctl.md",
                 "reason": "looks fine to me"},
                {"ticket": 44, "action": "stop", "kind": "", "deliverable": "",
                 "reason": "unbounded; needs a spec first"},
                {"ticket": 999, "action": "run", "kind": "build", "deliverable": "docs/ghost.md",
                 "reason": "invented"},
            ]},
        ])
        args = argparse.Namespace(dispatch=10, rounds=2, timeout=60, parallel=1, base=None,
                                  max_steps=8, agent_id=DISPATCH_AGENT)
        plan = run_agent(scripted, mcp, queue, state["birth_prompt"], max_steps=args.max_steps)
        ck("e1: the agent read the queue through its own ticket_queue tool",
           len(mcp.called("ticket_queue")) == 1, str(mcp.calls))
        ck("e2: a journal note the model signed as another agent was re-attributed to %s"
           % DISPATCH_AGENT,
           mcp.reattributed == 1 and all(j["agent_id"] == DISPATCH_AGENT for j in state["journal"]),
           json.dumps(state["journal"]))

        spawned = []
        minted = []
        results, runs = apply_plan(plan, queue, mcp, args, execute=True,
                                   spawn=lambda r, a_: spawned.extend(r) or [],
                                   mint=lambda tid, why: minted.append((tid, why)) or 900)
        journal = {j["ticket_id"]: j["note"] for j in state["journal"]}

        ck("e3: EVERY decided ticket in the queue is journaled (the ticket's requirement)",
           sorted(journal) == [41, 42, 43, 44], str(sorted(journal)))
        ck("e4: every journal note is attributed to the dispatch agent",
           all(j["agent_id"] == DISPATCH_AGENT for j in state["journal"]),
           json.dumps(state["journal"]))
        ck("e5: a STOPPED ticket the model said 'run' is OVERRIDDEN to skip",
           journal.get(42, "").startswith("dispatch: skip") and "harness override" in journal.get(42, ""),
           journal.get(42))
        ck("e6: ...and the override names the brake, not just a refusal",
           "unreleased stop ticket" in journal.get(42, ""), journal.get(42))
        ck("e7: a CONTROL ticket (kind stop) the model said 'run' is OVERRIDDEN to skip",
           journal.get(43, "").startswith("dispatch: skip") and "control ticket" in journal.get(43, ""),
           journal.get(43))
        ck("e8: only the actionable ticket is spawned as a pair", spawned == [(41, "docs/widget.md")],
           str(spawned))
        ck("e9: the run's kind was applied set-once through ticket_kind",
           state["kinds"] == [{"id": 41, "kind": "build"}], json.dumps(state["kinds"]))
        ck("e10: a 'stop' is minted BY THE HARNESS (the agent has no ticket.create)",
           minted == [(44, "unbounded; needs a spec first")], str(minted))
        ck("e11: a plan entry naming a ticket the queue never held is refused",
           any(t == 999 and "not in the queue" in w for t, w in results), str(results))
        ck("e12: the child command is pair_loop --ticket/--deliverable, mirroring pair_loop.child_cmd",
           child_cmd(41, "docs/widget.md", args)[1:6]
           == [PAIR_LOOP, "--ticket", "41", "--deliverable", "docs/widget.md"],
           str(child_cmd(41, "docs/widget.md", args)))

        # ── g: the harness guards the path it hands a child ───────────────────────────────────────
        print("-- g: the deliverable path a plan names is guarded before a child sees it")
        ck("g1: an absolute deliverable is refused", safe_deliverable("/etc/passwd")[0] is None)
        ck("g2: a deliverable escaping the repo root is refused",
           safe_deliverable("../../escape.md")[0] is None)
        ck("g3: an empty deliverable is refused", safe_deliverable("")[0] is None)
        ck("g4: a normal repo-relative deliverable is accepted",
           safe_deliverable("docs/widget.md")[0] == "docs/widget.md")
        gplan = [{"ticket": 41, "action": "run", "kind": "build", "deliverable": "/etc/passwd",
                  "reason": "bad path"}]
        gspawn = []
        state["journal"].clear()
        apply_plan(gplan, queue, mcp, args, execute=True, spawn=lambda r, a_: gspawn.extend(r) or [],
                   mint=lambda tid, why: 0)
        ck("g5: a run with a bad deliverable degrades to skip and spawns nothing",
           gspawn == [] and state["journal"][0]["note"].startswith("dispatch: skip"),
           json.dumps(state["journal"]))

        # ── dd: a repeated ticket is decided once ─────────────────────────────────────────────────
        # A 90+ ticket queue is a long generation and a model can repeat an entry. Two "run"s on one
        # id would launch two pair_loop children for the SAME ticket, and each opens that ticket's
        # branch + worktree (pair_loop.py:1009-1013) — the pair would contend with itself.
        print("-- dd: a ticket the model decided twice is decided once")
        state["journal"].clear()
        state["kinds"].clear()
        dplan = [{"ticket": 41, "action": "run", "kind": "build", "deliverable": "docs/a.md",
                  "reason": "first"},
                 {"ticket": 41, "action": "run", "kind": "build", "deliverable": "docs/b.md",
                  "reason": "duplicate"}]
        ck("dd1: dedupe_plan keeps the first decision only",
           [d["reason"] for d in dedupe_plan(dplan)] == ["first"], str(dedupe_plan(dplan)))
        dspawn = []
        apply_plan(dplan, queue, mcp, args, execute=True,
                   spawn=lambda r, a_: dspawn.extend(r) or [], mint=lambda t, w: 0)
        ck("dd2: a repeated ticket is spawned ONCE, not twice onto one branch",
           dspawn == [(41, "docs/a.md")], str(dspawn))
        ck("dd3: ...and journaled once, not twice", len(state["journal"]) == 1,
           json.dumps(state["journal"]))

        # ── c: the cap ────────────────────────────────────────────────────────────────────────────
        print("-- c: --dispatch N caps what is executed")
        state["journal"].clear()
        capped = argparse.Namespace(**vars(args))
        capped.dispatch = 1
        cspawn = []
        apply_plan(plan, queue, mcp, capped, execute=True, spawn=lambda r, a_: cspawn.extend(r) or [],
                   mint=lambda tid, why: 0)
        ck("c1: --dispatch 1 decides exactly one ticket", len(state["journal"]) == 1,
           json.dumps(state["journal"]))

        # ── p: --plan executes nothing ────────────────────────────────────────────────────────────
        print("-- p: --plan journals but executes nothing")
        state["journal"].clear()
        state["kinds"].clear()
        pspawn, pmint = [], []
        presults, _ = apply_plan(plan, queue, mcp, args, execute=False,
                                 spawn=lambda r, a_: pspawn.extend(r) or [],
                                 mint=lambda tid, why: pmint.append(tid) or 0)
        ck("p1: --plan spawns no pair and mints no stop ticket", pspawn == [] and pmint == [],
           "%s %s" % (pspawn, pmint))
        ck("p2: --plan still journals every decision (routing metadata is all dispatch can write)",
           len(state["journal"]) == 4, json.dumps(state["journal"]))
        ck("p3: --plan says what it WOULD have done",
           any("would run" in w for _t, w in presults) and any("would stop" in w for _t, w in presults),
           str(presults))
        ck("p4: --plan applies NO kind — set-once, so a dry run must not burn the real run's one "
           "chance to label (0029:111-117)", state["kinds"] == [], json.dumps(state["kinds"]))

        # ── m: model + context, per the research the gate depends on ──────────────────────────────
        print("-- m: the model and its context window")
        ck("m1: the dispatch model is gemma3:27b (research #173 §3.1), read from ollama_agent",
           oa.ROLE_MODELS["dispatch"] == "gemma3:27b", oa.ROLE_MODELS["dispatch"])
        ck("m2: it is a Gemma-3 model, as ticket #179 requires",
           oa.ROLE_MODELS["dispatch"].startswith("gemma3"), oa.ROLE_MODELS["dispatch"])
        ck("m3: the num_ctx floor for this role is >= 32k (research #174 §6)",
           DISPATCH_NUM_CTX_FLOOR >= 32768, str(DISPATCH_NUM_CTX_FLOOR))
        oa._CTX_CACHE["fake:test"] = 131072
        d = OllamaDriver(model="fake:test", timeout=60)
        ck("m4: a small queue still gets the 32k floor, never Ollama's 4096 default",
           d.num_ctx_for(100) == DISPATCH_NUM_CTX_FLOOR, str(d.num_ctx_for(100)))
        ck("m5: a big queue scales past the floor", d.num_ctx_for(400000) > DISPATCH_NUM_CTX_FLOOR,
           str(d.num_ctx_for(400000)))
        ck("m6: num_ctx never exceeds the model's real context length",
           d.num_ctx_for(10 ** 8) == 131072, str(d.num_ctx_for(10 ** 8)))
        oa._CTX_CACHE["small:test"] = 8192
        ck("m7: a model that cannot reach the floor is capped at what it really has, not lied to",
           OllamaDriver(model="small:test", timeout=60).num_ctx_for(100) == 8192)
        ck("m8: --num-ctx overrides the sizing",
           OllamaDriver(model="fake:test", timeout=60, num_ctx=65536).num_ctx_for(100) == 65536)
        oa._CTX_CACHE.pop("fake:test", None)
        oa._CTX_CACHE.pop("small:test", None)

        # num_ctx guards the INPUT; num_predict guards the OUTPUT. A flat output budget truncates a
        # long plan into invalid JSON that no retry can repair, and a 4-ticket fixture is far too
        # small to notice — so the sizing is asserted at the scale the LIVE queue actually runs at.
        print("-- n: the plan's output budget scales with the queue (the other truncation)")
        ck("n1: one tool step gets the small flat budget", STEP_NUM_PREDICT == 1024)
        ck("n2: a tiny queue still gets the floor", plan_num_predict(1) == PLAN_NUM_PREDICT_FLOOR,
           str(plan_num_predict(1)))
        real = 79                       # the live queue's size when this was written
        need = int(real * 147 / 4)      # ~147 chars/entry at ~4 chars/token, measured on real entries
        ck("n3: a %d-ticket queue budgets MORE than the plan needs (~%d tokens), so it cannot "
           "truncate" % (real, need), plan_num_predict(real) > need,
           "%d budgeted vs ~%d needed" % (plan_num_predict(real), need))
        ck("n4: ...and that is strictly more than a flat 2048 would have allowed (the defect this "
           "check exists for)", plan_num_predict(real) > 2048, str(plan_num_predict(real)))
        ck("n5: the plan call actually REQUESTS the sized budget, not the step default",
           dict(scripted.budgets).get("plan") == plan_num_predict(len(queue)),
           str(scripted.budgets))
        ck("n6: every tool step used the step budget",
           all(b == STEP_NUM_PREDICT for lbl, b in scripted.budgets if lbl != "plan"),
           str(scripted.budgets))

        # ── x: the ollama_agent seam — a fault there must not become a traceback here ─────────────
        print("-- x: faults from the reused module cross the seam as this module's Unexpected")

        def _boom():
            raise oa.Unexpected("ollama unreachable at http://127.0.0.1:1 — is `ollama serve` running?")

        try:
            oa_call(_boom)
            ck("x1: an ollama_agent fault is re-raised as this module's Unexpected", False,
               "it did not raise at all")
        except Unexpected as e:
            ck("x1: an ollama_agent fault is re-raised as this module's Unexpected (so main prints "
               "one line, never a traceback)", "ollama unreachable" in str(e), str(e))
        except oa.Unexpected:
            ck("x1: an ollama_agent fault is re-raised as this module's Unexpected", False,
               "it escaped as ollama_agent.Unexpected — main would print a traceback")
        ck("x2: the two Unexpected classes really are distinct (which is why the seam exists)",
           oa.Unexpected is not Unexpected)

        # ── s: no file was written anywhere, by anyone, the whole run ─────────────────────────────
        print("-- s: the whole run's file side effects")
        ck("s1: the throwaway root is byte-for-byte as it started (no file authored, none created)",
           _tree(root) == ["registry.json"], str(_tree(root)))
        ck("s2: the agent's every effect was a routing write (journal/kind), nothing else",
           {n for n, _a, ok in mcp.calls if ok} <= {"ticket_queue", "ticket_progress", "ticket_kind"},
           str(sorted({n for n, _a, ok in mcp.calls if ok})))

        bad = [n for n, ok, _ in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s"
              % (len(checks) - len(bad), len(checks), "" if not bad else "; FAILED: " + "; ".join(bad)))
        return 1 if bad else 0
    finally:
        CONG = saved_cong
        if mcp:
            mcp.close()
        if httpd:
            httpd.shutdown()
            httpd.server_close()
        shutil.rmtree(base, ignore_errors=True)
        print("== selftest == throwaway root and stub removed (this repo, the db, Ollama and the "
              "external network were never touched)")


def main():
    ap = argparse.ArgumentParser(
        prog="gemma_dispatch_agent.py",
        description="The least-privilege dispatch agent: a Gemma-3 model that reads the ticket "
                    "queue, decides run/skip/stop and spawns worker pairs, whose ONLY tool surface "
                    "is ticket_api_mcp.py --role dispatch (ticket.queue, ticket.kind, "
                    "ticket.assign, edge.record, ticket.progress) — so it is structurally "
                    "incapable of authoring work product.",
        epilog="examples:\n"
               "  python3 gemma_dispatch_agent.py --selftest\n"
               "  python3 gemma_dispatch_agent.py --probe\n"
               "  python3 gemma_dispatch_agent.py --plan\n"
               "  python3 gemma_dispatch_agent.py --dispatch 3 --parallel 2\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dispatch", type=int, nargs="?", const=5, metavar="N",
                    help="route the live queue and EXECUTE up to N of the plan's decisions "
                         "(default N=5 when the flag is given bare)")
    ap.add_argument("--plan", action="store_true",
                    help="run the same agent and journal its decisions, but execute NOTHING: no "
                         "pair spawned, no stop ticket minted")
    ap.add_argument("--probe", action="store_true",
                    help="print the tool surface this agent would ACTUALLY be granted (asks the "
                         "bridge) and whether its model is installed, then exit")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the acceptance offline — the grant is the 5, a write is refused and "
                         "creates no file, and a fixture queue routes correctly with the brake "
                         "enforced. No db, no Ollama, no api key, no pair spawned; this repo untouched")
    ap.add_argument("--model", help="override the dispatch model (default: ollama_agent's role->model "
                                    "map, research #173 — gemma3:27b)")
    ap.add_argument("--agent-id", default=DISPATCH_AGENT,
                    help="the REGISTERED dispatch identity every decision is journaled as "
                         "(default: %(default)s)")
    ap.add_argument("--server", default=MCP_SERVER,
                    help="the MCP bridge to launch --role dispatch (default: the sibling "
                         "ticket_api_mcp.py from build #178)")
    ap.add_argument("--parallel", type=int, default=1, metavar="K",
                    help="how many dispatched pairs may run at once (default: %(default)s)")
    ap.add_argument("--rounds", type=int, default=2, help="pair_loop --rounds for each child (default: %(default)s)")
    ap.add_argument("--timeout", type=int, default=900,
                    help="seconds for the whole agent run, and pair_loop --timeout per child spawn "
                         "(default: %(default)s)")
    ap.add_argument("--base", default=None, metavar="BRANCH",
                    help="pair_loop --base for each child (default: pair_loop's own default)")
    ap.add_argument("--max-steps", type=int, default=24,
                    help="max tool steps before the plan is demanded (default: %(default)s)")
    ap.add_argument("--retries", type=int, default=2,
                    help="schema-violation retries per turn, per research #175 §5.2 (default: %(default)s)")
    ap.add_argument("--num-ctx", type=int,
                    help="override num_ctx (default: sized to the queue, floor %d, capped at the "
                         "model's real context)" % DISPATCH_NUM_CTX_FLOOR)
    a = ap.parse_args()

    if a.selftest:
        return selftest(a)
    if a.probe:
        return probe(a)
    if a.plan:
        a.dispatch = a.dispatch if a.dispatch is not None else 10 ** 6
        return do_dispatch(a, execute=False)
    if a.dispatch is None:
        ap.error("one of --dispatch [N], --plan, --probe or --selftest is required")
    return do_dispatch(a, execute=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Unexpected as e:
        bug_report("main", e, "python3 gemma_dispatch_agent.py " + " ".join(sys.argv[1:]), e)
        print("gemma_dispatch_agent: %s" % e, file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("gemma_dispatch_agent: interrupted", file=sys.stderr)
        sys.exit(2)
