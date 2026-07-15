#!/usr/bin/env python3
"""ticket_api_mcp.py — the MCP tool bridge: the governed ticket API + guarded file/git/test-run
ops, exposed as MCP tools behind a PER-ROLE ALLOWLIST (ticket #178, gated on the #174 research
`checkouts/current/docs/research/mcp_tool_access_least_privilege.md`).

WHAT AN MCP SERVER IS HERE: a process that speaks JSON-RPC 2.0 over stdin/stdout (one JSON object
per line). An agent's client connects, calls `tools/list` to learn what it may do, and `tools/call`
to do it. This file implements that protocol with the standard library alone — the repo is
stdlib-only (DEPENDENCIES.md: "setup.py is stdlib-only ... no third-party packages, no pip
install"), so no `mcp` SDK is imported.

THE POINT — least privilege by ABSENCE, not by filtering. Launch with `--role`; the server then
registers ONLY that role's tools. Two independent layers, per research §4:

  layer 1 (research option (c), the trust boundary): `tools/list` returns ONLY the role's tools, so
      a capability outside the role is ABSENT from the agent's context — there is nothing to call.
  layer 2 (research option (b), defense-in-depth): `tools/call` re-checks the role allowlist
      SERVER-SIDE and REFUSES anything outside it (JSON-RPC error -32601, logged to stderr) even if
      a client asks for it by name anyway. The layers fail safe independently.

This replaces `pair_loop.py`'s `--allowedTools` string (research option (a)), which is only a
client-side name filter over tools that stay fully present in the process — and which today grants
workers `Bash(python3:*)`, i.e. arbitrary shell (pair_loop.py:493).

NO SHELL. Tools come exclusively from MCP. `test_run` is the ONLY tool that executes anything: it
takes a RUNNER NAME chosen from a fixed allowlist (never a command string), runs it via
`subprocess.run(argv, shell=False)`, and refuses everything else. No free-form string ever reaches
a shell. There is no commit/merge/push tool at all — the git pen stays with the harness `Forge`
(pair_loop.py:194), so no agent can alter history.

THE ROLE PROFILES (research §2, §6):

  dispatch — spawn + route ONLY, the exact 5:
             ticket_queue, ticket_kind, ticket_assign, edge_record, ticket_progress.
             SPAWN = authorize an agent on a ticket (ticket_assign) + record the 'spawned' edge
             (edge_record); ROUTE = read the queue, label a kind, append a progress note.
             It has NO file, git, or test tool, and every write it holds mutates ROUTING METADATA
             ONLY (a set-once kind label, an authorization row, a graph edge, a journal note).
             None of them is a work-product sink, so the dispatch agent CANNOT WRITE CODE.
             Proven by `--selftest` (checks d1-d8), including that a refused write creates no file.
  worker   — file/git/test ONLY (file_read, file_write_deliverable, git_read_file, git_blame,
             git_log, test_run) plus READ-ONLY ticket context for grounding (ticket_journal,
             ticket_manifest, kind_roster, lessons_recent, doc_read). It holds NO route WRITE and
             no spawn tool: every ticket-API tool in this profile is a GET.
  judge    — the same read-only context + git reads + test_run (an adversary must execute to prove
             a bug), and NO writer of any kind: it never authors.
  forge    — the harness identity, never handed to a model: the governance writes (work_record,
             ticket_progress, ticket_lesson) plus read context.

`work_record` is exposed by this bridge (the ticket requires the work route) but is granted to the
FORGE profile only — research §2 note: `work.record` is a harness-held governance write, exposed to
no model-driven role. Grep the PROFILES table below; it is the whole policy.

Every db call goes through the governed REST surface (`rest.php?route=...`) with the same call
semantics and `.secrets/ats.env` key loading `pair_loop.py` uses (pair_loop.py:141-186) — this
server holds no SQL pen.

Usage:
    python3 ticket_api_mcp.py --role dispatch                     # serve MCP on stdio (the 5 tools)
    python3 ticket_api_mcp.py --role worker --deliverable docs/X.md   # writes ONLY that one path
    python3 ticket_api_mcp.py --profiles                          # print the role->tool matrix
    python3 ticket_api_mcp.py --selftest                          # prove the acceptance; no db/net

--role is required to serve. `--deliverable PATH` (repo-relative) locks `file_write_deliverable` to
exactly that path; without it the worker profile still lists the tool but every call is REFUSED, so
a launch that forgets it cannot silently write somewhere else.

--selftest proves the ticket's ACCEPTANCE with NO network, NO db, NO agents, and NO writes into
this repo (it drives a throwaway temp root and deletes it): that a non-allowlisted tool call is
refused, and that the dispatch role provably cannot write code. Prints one PASS/FAIL line per
check; exits 0 only if every check passed.

Registry-gated per note-for-claude: walks UP to registry.json and throws if it cannot see it (the
php runner path comes from the registry's `paths.php`); any unexpected exception files a
timestamped Variant-A bug report to the registry's `bug_reports` sink.

Exit codes:
    0  served cleanly / --profiles printed / --selftest: every check PASSED
    1  --selftest: at least one check FAILED
    2  usage or configuration error — a one-line message, never a traceback
"""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback
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


ROOT, REGISTRY = find_registry(os.path.dirname(os.path.abspath(__file__)))
CONG = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")  # newest first; we echo the client's if known
SERVER_NAME = "congruency-ticket-api"
SERVER_VERSION = "1.0.0"


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks).
    note-for-claude: every tool files a timestamped report when an exception is thrown."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "ticket_api_mcp.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:], "note": "ticket-api MCP bridge",
            }) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _secret(name):
    """CONGRUENCY_API_KEY from .secrets/ats.env or the env — same loader as pair_loop.py:141-147."""
    path = os.path.join(os.path.dirname(ROOT), ".secrets", "ats.env")
    if os.path.isfile(path):
        for line in open(path):
            if line.strip().startswith(name + "="):
                return line.strip().split("=", 1)[1]
    return os.environ.get(name)


class Refused(Exception):
    """A tool call the policy refuses. Carries the JSON-RPC error code the caller sees."""

    def __init__(self, message, code=-32601):
        super().__init__(message)
        self.code = code


# ── REST (the governed surface; no SQL pen) — call semantics mirror pair_loop.py:174-186 ─────────
def rest(route, obj=None, method=None):
    url = CONG + "/rest.php?route=" + route
    if obj is not None and (method or "POST") == "GET":
        url += "&" + "&".join("%s=%s" % (k, urllib.request.quote(str(v))) for k, v in obj.items())
        obj = None
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json",
                                          "X-Api-Key": _secret("CONGRUENCY_API_KEY") or ""})
    with urllib.request.urlopen(req, timeout=15) as r:
        out = json.loads(r.read().decode())
    if "error" in out:
        raise Refused("route %s failed: %s" % (route, out["error"]), code=-32603)
    return out


# ── the ticket-API route tools ───────────────────────────────────────────────────────────────────
# tool_name -> (route, method, {param: type}, [required params], description)
# Params/methods are read from the migrations that define each route; the citation is on each line.
ROUTE_TOOLS = {
    # dispatch's spawn+route surface
    "ticket_queue":    ("ticket.queue", "GET", {}, [],
                        "the dispatch queue: OPEN/REQUESTED tickets, oldest first"),                    # 0032
    "ticket_kind":     ("ticket.kind", "POST", {"id": "int", "kind": "str"}, ["id", "kind"],
                        "classify a ticket (set-once; the identity trigger refuses re-kinding)"),       # 0030
    "ticket_assign":   ("ticket.assign", "POST", {"ticket_id": "int", "agent_id": "str", "role": "str"},
                        ["ticket_id", "agent_id", "role"],
                        "authorize a REGISTERED agent on a ticket in a role (idempotent)"),             # 0033
    "edge_record":     ("edge.record", "POST", {"parent_id": "int", "child_id": "int", "kind": "str"},
                        ["parent_id", "child_id", "kind"],
                        "record a parent->child ticket edge (e.g. 'spawned')"),                         # 0012
    "ticket_progress": ("ticket.progress", "POST",
                        {"ticket_id": "int", "agent_id": "str", "note": "str", "steps_remaining": "int"},
                        ["ticket_id", "agent_id", "note"],
                        "append an attributed progress report (+ steps until the goal)"),               # 0029
    # read-only context (worker/judge grounding)
    "ticket_journal":  ("ticket.journal", "GET", {"ticket_id": "int"}, ["ticket_id"],
                        "the full append-only journal for a ticket"),                                   # 0029
    "ticket_manifest": ("ticket.manifest", "GET", {"ticket_id": "int"}, ["ticket_id"],
                        "every UID'd item the ticket authorized"),                                      # 0029
    "ticket_crew":     ("ticket.crew", "GET", {"ticket_id": "int"}, ["ticket_id"],
                        "the agents authorized on a ticket, with roles"),                               # 0029
    "kind_roster":     ("kind.roster", "GET", {}, [],
                        "the ticket kinds: pair vs solo, with role names"),                             # 0029
    "lifecycle_steps": ("lifecycle.steps", "GET", {"kind": "str", "version": "int"}, ["kind"],
                        "the enumerable lifecycle steps for a kind"),                                   # 0029
    "lessons_recent":  ("lessons.recent", "GET", {"n": "int"}, [],
                        "harvested lessons across tickets, newest first (omit n for all)"),             # 0031
    "doc_read":        ("doc.read", "GET", {"repo": "str", "path": "str"}, ["repo", "path"],
                        "read one ingested repo doc body"),                                             # 0017
    # governance writes — FORGE ONLY, never a model-driven role (research §2)
    "work_record":     ("work.record", "POST", {"ticket_id": "int", "kind": "str", "ref": "str", "note": "str"},
                        ["ticket_id", "kind", "ref"],
                        "mint a PERMANENT work UID into a ticket's manifest"),                          # 0029
    "ticket_lesson":   ("ticket.lesson", "POST", {"ticket_id": "int", "agent_id": "str", "note": "str"},
                        ["ticket_id", "agent_id", "note"],
                        "append the distilled lesson for a settled ticket"),                            # 0031
}

JSON_TYPE = {"int": "integer", "str": "string"}


# ── guarded file / git / test-run ops ────────────────────────────────────────────────────────────
def safe_path(ctx, rel):
    """Resolve a repo-relative path under ctx['root'], REFUSING any escape (../, absolute, symlink
    out). Returns the real absolute path."""
    if not isinstance(rel, str) or not rel:
        raise Refused("path must be a non-empty repo-relative string", code=-32602)
    if os.path.isabs(rel):
        raise Refused("path must be repo-relative, not absolute: %r" % rel, code=-32602)
    root = os.path.realpath(ctx["root"])
    p = os.path.realpath(os.path.join(root, rel))
    if p != root and not p.startswith(root + os.sep):
        raise Refused("refused: path escapes the repo root: %r" % rel, code=-32602)
    return p


def t_file_read(ctx, args):
    """Read a repo file (path-guarded). Read-only: opens 'r', creates nothing."""
    p = safe_path(ctx, args.get("path"))
    if not os.path.isfile(p):
        raise Refused("no such file in the repo: %r" % args.get("path"), code=-32602)
    with open(p) as fh:
        return {"path": args["path"], "content": fh.read()}


def t_file_write_deliverable(ctx, args):
    """Write the ticket's ONE declared deliverable — the only write tool in this server.

    The path is fixed at launch (--deliverable). Any other path is refused, so a worker cannot
    author arbitrary files; a launch with no deliverable declared refuses every write."""
    if not ctx.get("deliverable"):
        raise Refused("refused: no deliverable was declared at launch (--deliverable) — this "
                      "server writes nothing", code=-32602)
    path = args.get("path")
    if path != ctx["deliverable"]:
        raise Refused("refused: this server writes ONLY the declared deliverable %r (asked for %r)"
                      % (ctx["deliverable"], path), code=-32602)
    content = args.get("content")
    if not isinstance(content, str):
        raise Refused("content must be a string", code=-32602)
    p = safe_path(ctx, path)                       # the declared path is guarded too, not trusted
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(p, "w") as fh:
        fh.write(content)
    return {"path": path, "bytes": len(content.encode())}


def _git(ctx, *argv):
    """Read-only git, argv list, shell=False. Subcommands are hardcoded by the tools below — no
    caller string ever selects a git verb, and no commit/merge/push tool exists here."""
    r = subprocess.run(["git", *argv], cwd=ctx["root"], capture_output=True, text=True, shell=False)
    if r.returncode != 0:
        raise Refused("git %s failed: %s" % (argv[0], (r.stderr or r.stdout).strip()[-200:]), code=-32603)
    return r.stdout


def t_git_read_file(ctx, args):
    """Read a file's content at a git ref WITHOUT touching the working tree (git show ref:path)."""
    path = args.get("path")
    safe_path(ctx, path)                            # guard the path even though git reads the blob
    ref = args.get("ref") or "HEAD"
    if not isinstance(ref, str) or ref.startswith("-"):
        raise Refused("refused: bad git ref %r" % ref, code=-32602)
    return {"path": path, "ref": ref, "content": _git(ctx, "show", "%s:%s" % (ref, path))}


def t_git_blame(ctx, args):
    path = args.get("path")
    safe_path(ctx, path)
    return {"path": path, "blame": _git(ctx, "blame", "--", path)}


def t_git_log(ctx, args):
    path = args.get("path")
    n = args.get("n") or 20
    if not isinstance(n, int) or n < 1 or n > 500:
        raise Refused("n must be an integer 1..500", code=-32602)
    argv = ["log", "--oneline", "-n", str(n)]
    if path:
        safe_path(ctx, path)
        argv += ["--", path]
    return {"log": _git(ctx, *argv)}


def php_binary():
    """The repo php, from the registry (config-as-data, note-for-claude). Not system php."""
    return os.path.join(ROOT, REGISTRY.get("paths", {}).get("php", "tooling/congruencey-harness/php/php"))


def t_test_run(ctx, args):
    """Execute a repo file under an ALLOWLISTED runner. NO SHELL, ever.

    `runner` is a NAME from RUNNERS (never a command string); the target is path-guarded into the
    repo; extra args must be strings. Everything is passed as an argv list with shell=False, so
    metacharacters are inert data, not syntax. This is what replaces pair_loop's Bash(python3:*)
    grant (pair_loop.py:493)."""
    runners = {"python3": [sys.executable or "python3"], "php": [php_binary()]}
    runner = args.get("runner")
    if runner not in runners:
        raise Refused("refused: runner must be one of %s (a NAME, not a command): %r"
                      % (sorted(runners), runner), code=-32602)
    exe = runners[runner][0]
    if runner == "php" and not os.path.isfile(exe):
        raise Refused("the repo php is not provisioned at %s (run tools/provision_php.py)" % exe,
                      code=-32603)
    target = safe_path(ctx, args.get("target"))
    if not os.path.isfile(target):
        raise Refused("no such file to run: %r" % args.get("target"), code=-32602)
    extra = args.get("args") or []
    if not isinstance(extra, list) or not all(isinstance(x, str) for x in extra):
        raise Refused("args must be a list of strings", code=-32602)
    timeout = args.get("timeout") or 120
    if not isinstance(timeout, int) or timeout < 1 or timeout > 600:
        raise Refused("timeout must be an integer 1..600 seconds", code=-32602)
    try:
        r = subprocess.run([exe, target, *extra], cwd=ctx["root"], capture_output=True, text=True,
                           timeout=timeout, shell=False)
    except subprocess.TimeoutExpired:
        return {"passed": False, "exit": None, "output": "timed out after %ss" % timeout}
    return {"passed": r.returncode == 0, "exit": r.returncode,
            "output": ((r.stdout or "") + (r.stderr or ""))[-8000:]}


OP_TOOLS = {
    "file_read": (t_file_read, {"path": {"type": "string", "description": "repo-relative path"}}, ["path"],
                  "read a repo file (path-guarded to the repo root; read-only)"),
    "file_write_deliverable": (
        t_file_write_deliverable,
        {"path": {"type": "string", "description": "must equal the deliverable declared at launch"},
         "content": {"type": "string", "description": "the full file content"}},
        ["path", "content"],
        "write the ticket's ONE declared deliverable; any other path is refused"),
    "git_read_file": (t_git_read_file,
                      {"path": {"type": "string", "description": "repo-relative path"},
                       "ref": {"type": "string", "description": "git ref (default HEAD)"}}, ["path"],
                      "read a file's content at a git ref, without touching the working tree"),
    "git_blame": (t_git_blame, {"path": {"type": "string", "description": "repo-relative path"}}, ["path"],
                  "line provenance for a repo file"),
    "git_log": (t_git_log, {"path": {"type": "string", "description": "optional repo-relative path"},
                            "n": {"type": "integer", "description": "how many commits (default 20)"}}, [],
                "recent commits (optionally for one path)"),
    "test_run": (t_test_run,
                 {"runner": {"type": "string", "enum": ["python3", "php"],
                             "description": "allowlisted runner NAME (not a command)"},
                  "target": {"type": "string", "description": "repo-relative file to execute"},
                  "args": {"type": "array", "items": {"type": "string"}, "description": "extra argv strings"},
                  "timeout": {"type": "integer", "description": "seconds, 1..600 (default 120)"}},
                 ["runner", "target"],
                 "run a repo file under an allowlisted runner; returns {passed, exit, output}. No shell."),
}


# ── THE POLICY: per-role allowlists (research §2 matrix / §6 profiles) ────────────────────────────
PROFILES = {
    # spawn + route ONLY — the exact 5. No file/git/test tool, no work-product sink.
    "dispatch": ["ticket_queue", "ticket_kind", "ticket_assign", "edge_record", "ticket_progress"],
    # file/git/test ONLY, plus read-only ticket context for grounding. No route write, no spawn.
    "worker": ["file_read", "file_write_deliverable", "git_read_file", "git_blame", "git_log", "test_run",
               "ticket_journal", "ticket_manifest", "kind_roster", "lessons_recent", "doc_read"],
    # reads + execution to PROVE bugs; never authors (no writer of any kind).
    "judge": ["file_read", "git_read_file", "git_blame", "git_log", "test_run",
              "ticket_journal", "ticket_manifest", "kind_roster"],
    # the harness identity — governance writes; never handed to a model.
    "forge": ["work_record", "ticket_progress", "ticket_lesson", "ticket_journal", "ticket_manifest",
              "ticket_crew", "lifecycle_steps", "kind_roster"],
}

# Tools that can author a file, mutate the repo, or execute code. The dispatch profile must not
# intersect this set — that is what "the dispatch agent cannot write code" MEANS, and --selftest
# asserts it mechanically (check d3) rather than trusting this comment.
AUTHORING_TOOLS = {"file_write_deliverable", "test_run"}
WORK_PRODUCT_SINKS = {"work_record", "ticket_lesson"}


def tool_names(role):
    if role not in PROFILES:
        raise Refused("unknown role %r — roles are: %s" % (role, ", ".join(sorted(PROFILES))), code=-32602)
    return list(PROFILES[role])


def tool_spec(name):
    """The MCP tool descriptor (name/description/inputSchema) for one tool."""
    if name in ROUTE_TOOLS:
        route, method, params, required, desc = ROUTE_TOOLS[name]
        props = {k: {"type": JSON_TYPE[t], "description": "%s (%s)" % (k, t)} for k, t in params.items()}
        return {"name": name,
                "description": "%s [route %s, %s]" % (desc, route, method),
                "inputSchema": {"type": "object", "properties": props, "required": list(required)}}
    fn, props, required, desc = OP_TOOLS[name]
    return {"name": name, "description": desc,
            "inputSchema": {"type": "object", "properties": props, "required": list(required)}}


def call_tool(ctx, name, args):
    """Invoke ONE tool after the role check. Missing required params are refused before any call."""
    spec = tool_spec(name)
    for req in spec["inputSchema"].get("required", []):
        if args.get(req) is None:
            raise Refused("missing required parameter %r for %s" % (req, name), code=-32602)
    if name in ROUTE_TOOLS:
        route, method, params, _req, _d = ROUTE_TOOLS[name]
        payload = {k: args[k] for k in params if args.get(k) is not None}
        return rest(route, payload or ({} if method == "GET" else None), method=method)
    return OP_TOOLS[name][0](ctx, args)


# ── the MCP protocol: JSON-RPC 2.0 over stdio, one object per line ───────────────────────────────
def refuse_log(ctx, name, why):
    """Refusals are LOGGED (research §6) — to STDERR, because stdout is the JSON-RPC channel and a
    stray byte there corrupts the protocol. Logging creates no file."""
    sys.stderr.write("ticket_api_mcp: REFUSED role=%s tool=%s — %s\n" % (ctx.get("role"), name, why))
    sys.stderr.flush()


def handle_request(ctx, req):
    """Handle one JSON-RPC request; return the response dict, or None for a notification."""
    rid = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}
    is_notification = "id" not in req

    def ok(result):
        return None if is_notification else {"jsonrpc": "2.0", "id": rid, "result": result}

    def err(code, message):
        return None if is_notification else {"jsonrpc": "2.0", "id": rid,
                                             "error": {"code": code, "message": message}}

    try:
        if method == "initialize":
            want = params.get("protocolVersion")
            return ok({"protocolVersion": want if want in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                       "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "%s (%s)" % (SERVER_NAME, ctx["role"]),
                                      "version": SERVER_VERSION}})
        if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
            return None
        if method == "ping":
            return ok({})
        if method == "tools/list":
            # layer 1 — the agent's context contains ONLY its role's tools; the rest are ABSENT.
            return ok({"tools": [tool_spec(n) for n in tool_names(ctx["role"])]})
        if method == "tools/call":
            name = params.get("name")
            # layer 2 — server-side allowlist: refuse anything outside the role, by name, always.
            if name not in tool_names(ctx["role"]):
                why = ("not in role profile %r (this role may call: %s)"
                       % (ctx["role"], ", ".join(tool_names(ctx["role"]))))
                refuse_log(ctx, name, why)
                return err(-32601, "refused: tool %r is %s" % (name, why))
            result = call_tool(ctx, name, params.get("arguments") or {})
            return ok({"content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                       "isError": False})
        return err(-32601, "method not found: %r" % method)
    except Refused as e:
        refuse_log(ctx, params.get("name") or method, str(e))
        return err(e.code, str(e))
    except Exception as e:  # noqa: BLE001 — never crash the server on one bad call
        bug_report("handle_request", e, "MCP %s with params %r" % (method, params), e)
        return err(-32603, "internal error in %s: %s" % (method, e))


def serve(ctx):
    """Read JSON-RPC lines on stdin, write responses on stdout. Stdout carries the protocol ONLY."""
    sys.stderr.write("ticket_api_mcp: serving role=%s tools=%s deliverable=%s\n"
                     % (ctx["role"], ",".join(tool_names(ctx["role"])), ctx.get("deliverable") or "(none)"))
    sys.stderr.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        resp = handle_request(ctx, req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


def print_profiles():
    """The role->tool matrix, so the policy is legible without reading the code."""
    print("ticket_api_mcp — per-role MCP tool profiles (tools come ONLY from MCP; no shell)\n")
    for role in ("dispatch", "worker", "judge", "forge"):
        names = tool_names(role)
        authoring = sorted(set(names) & (AUTHORING_TOOLS | WORK_PRODUCT_SINKS))
        print("  %-9s %d tools" % (role, len(names)))
        for n in names:
            kind = "route %s" % ROUTE_TOOLS[n][0] if n in ROUTE_TOOLS else "op"
            print("      %-24s %s" % (n, kind))
        print("      can author/execute/record work product: %s\n" % (", ".join(authoring) or "NOTHING"))
    return 0


# ── --selftest: prove the ACCEPTANCE in a THROWAWAY root (no db, no network, no agents) ──────────
def _st_ctx(role, root, deliverable=None):
    return {"role": role, "root": root, "deliverable": deliverable}


def _st_rpc(ctx, method, params=None, rid=1):
    """Drive the REAL handler over a real JSON-RPC envelope — the same path a client takes."""
    return handle_request(ctx, {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})


def selftest():
    import shutil
    import tempfile

    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name, ("  — %s" % detail) if detail and not cond else ""))

    base = tempfile.mkdtemp(prefix="ticket_api_mcp-selftest-")
    try:
        root = os.path.join(base, "repo")
        os.makedirs(os.path.join(root, "docs"))
        open(os.path.join(root, "registry.json"), "w").write('{"schema": 1, "package": "selftest"}\n')
        open(os.path.join(root, "docs", "seed.md"), "w").write("seed\n")
        subprocess.run(["git", "init", "--quiet", "-b", "main", "."], cwd=root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "mcp@selftest"], cwd=root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "mcp selftest"], cwd=root, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "--quiet", "-m", "init"], cwd=root, capture_output=True)
        print("== selftest == throwaway root %s (this repo, the db and the network are untouched)" % root)

        deliv = "docs/out.md"
        dispatch = _st_ctx("dispatch", root)
        worker = _st_ctx("worker", root, deliverable=deliv)
        judge = _st_ctx("judge", root)

        # ── p1: the protocol handshake works (a client can actually connect) ──────────────────────
        print("-- p: MCP protocol")
        init = _st_rpc(dispatch, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        ck("p1: initialize returns the client's protocol version",
           init["result"]["protocolVersion"] == "2024-11-05", json.dumps(init))
        ck("p2: initialize advertises the tools capability", "tools" in init["result"]["capabilities"])
        ck("p3: an unknown protocol version falls back to a supported one",
           _st_rpc(dispatch, "initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"]
           in PROTOCOL_VERSIONS)
        ck("p4: a notification gets NO response (JSON-RPC requires silence)",
           handle_request(dispatch, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None)
        ck("p5: an unknown method is an error, not a crash",
           _st_rpc(dispatch, "nonsense/method")["error"]["code"] == -32601)

        # ── d: THE DISPATCH AGENT PROVABLY CANNOT WRITE CODE ──────────────────────────────────────
        print("-- d: dispatch = spawn+route ONLY, and provably cannot write code")
        listed = [t["name"] for t in _st_rpc(dispatch, "tools/list")["result"]["tools"]]
        ck("d1: dispatch sees EXACTLY the 5 spawn+route tools (research §2)",
           sorted(listed) == sorted(["ticket_queue", "ticket_kind", "ticket_assign",
                                     "edge_record", "ticket_progress"]), ",".join(sorted(listed)))
        ck("d2: dispatch sees NO file/git/test tool at all (layer 1: the capability is ABSENT)",
           not (set(listed) & set(OP_TOOLS)), ",".join(sorted(set(listed) & set(OP_TOOLS))))
        ck("d3: dispatch holds NO authoring/execution tool and NO work-product sink",
           not (set(listed) & (AUTHORING_TOOLS | WORK_PRODUCT_SINKS)))
        ck("d4: every dispatch write mutates routing metadata only (no work/artifact/doc sink)",
           all(ROUTE_TOOLS[n][0] in ("ticket.queue", "ticket.kind", "ticket.assign",
                                     "edge.record", "ticket.progress") for n in listed))

        # layer 2, proven in ISOLATION: the refused write must create NOTHING on disk.
        target = os.path.join(root, deliv)
        before = sorted(os.listdir(os.path.join(root, "docs")))
        r = _st_rpc(dispatch, "tools/call",
                    {"name": "file_write_deliverable", "arguments": {"path": deliv, "content": "code"}})
        after = sorted(os.listdir(os.path.join(root, "docs")))
        ck("d5: dispatch calling a non-allowlisted tool BY NAME is refused (layer 2)",
           "error" in r and r["error"]["code"] == -32601 and "refused" in r["error"]["message"],
           json.dumps(r))
        ck("d5b: the refusal names the role and what the role MAY call",
           "dispatch" in r["error"]["message"] and "ticket_queue" in r["error"]["message"])
        ck("d6: the refused write created NO file (proven before/after, in isolation)",
           not os.path.exists(target) and before == after, "%s -> %s" % (before, after))
        r = _st_rpc(dispatch, "tools/call", {"name": "test_run",
                                             "arguments": {"runner": "python3", "target": "x.py"}})
        ck("d7: dispatch cannot EXECUTE anything either (test_run refused)",
           "error" in r and r["error"]["code"] == -32601)
        r = _st_rpc(dispatch, "tools/call", {"name": "work_record",
                                             "arguments": {"ticket_id": 1, "kind": "code", "ref": "x"}})
        ck("d8: dispatch cannot record a work UID (work_record is forge-only)",
           "error" in r and r["error"]["code"] == -32601)

        # ── w: the worker sees file/git/test — and no route WRITE ─────────────────────────────────
        print("-- w: worker = file/git/test (+ read-only context), no route write")
        wlisted = [t["name"] for t in _st_rpc(worker, "tools/list")["result"]["tools"]]
        ck("w1: worker sees the file/git/test ops",
           set(OP_TOOLS) <= set(wlisted), ",".join(sorted(set(OP_TOOLS) - set(wlisted))))
        ck("w2: worker holds NO spawn/route tool (dispatch's write surface is absent)",
           not (set(wlisted) & {"ticket_queue", "ticket_kind", "ticket_assign", "edge_record"}))
        ck("w3: every ticket-API tool the worker holds is a GET (no route write)",
           all(ROUTE_TOOLS[n][1] == "GET" for n in wlisted if n in ROUTE_TOOLS),
           ",".join(n for n in wlisted if n in ROUTE_TOOLS and ROUTE_TOOLS[n][1] != "GET"))
        r = _st_rpc(worker, "tools/call", {"name": "ticket_assign",
                                           "arguments": {"ticket_id": 1, "agent_id": "a", "role": "coder"}})
        ck("w4: worker calling a non-allowlisted tool (ticket_assign) is refused",
           "error" in r and r["error"]["code"] == -32601, json.dumps(r))

        # ── g: the deliverable write guard (the worker's ONE path) ────────────────────────────────
        print("-- g: guarded file ops")
        r = _st_rpc(worker, "tools/call",
                    {"name": "file_write_deliverable", "arguments": {"path": deliv, "content": "hello\n"}})
        ck("g1: the worker CAN write its declared deliverable",
           "result" in r and os.path.isfile(target) and open(target).read() == "hello\n", json.dumps(r))
        other = os.path.join(root, "docs", "elsewhere.md")
        r = _st_rpc(worker, "tools/call",
                    {"name": "file_write_deliverable",
                     "arguments": {"path": "docs/elsewhere.md", "content": "x"}})
        ck("g2: a write to ANY other path is refused, and creates no file",
           "error" in r and not os.path.exists(other), json.dumps(r))
        r = _st_rpc(worker, "tools/call",
                    {"name": "file_write_deliverable",
                     "arguments": {"path": "../escape.md", "content": "x"}})
        ck("g3: a path escaping the repo root is refused",
           "error" in r and not os.path.exists(os.path.join(base, "escape.md")))
        nodeliv = _st_ctx("worker", root, deliverable=None)
        r = _st_rpc(nodeliv, "tools/call",
                    {"name": "file_write_deliverable", "arguments": {"path": deliv, "content": "x"}})
        ck("g4: with no deliverable declared at launch, every write is refused",
           "error" in r and "no deliverable" in r["error"]["message"])
        r = _st_rpc(worker, "tools/call", {"name": "file_read", "arguments": {"path": "../../etc/hosts"}})
        ck("g5: file_read refuses a path escaping the repo root", "error" in r)
        r = _st_rpc(worker, "tools/call", {"name": "file_read", "arguments": {"path": "docs/seed.md"}})
        ck("g6: file_read reads a real repo file",
           "result" in r and "seed" in r["result"]["content"][0]["text"])
        r = _st_rpc(worker, "tools/call", {"name": "file_read", "arguments": {}})
        ck("g7: a missing required parameter is refused, not crashed",
           "error" in r and r["error"]["code"] == -32602)

        # ── x: execution is allowlisted; NO shell ─────────────────────────────────────────────────
        print("-- x: test_run = allowlisted runners, no shell")
        open(os.path.join(root, "ok.py"), "w").write("print('ran')\n")
        open(os.path.join(root, "bad.py"), "w").write("import sys; sys.exit(3)\n")
        r = _st_rpc(worker, "tools/call",
                    {"name": "test_run", "arguments": {"runner": "python3", "target": "ok.py"}})
        out = json.loads(r["result"]["content"][0]["text"]) if "result" in r else {}
        ck("x1: test_run executes an allowlisted runner and reports {passed, exit, output}",
           out.get("passed") is True and out.get("exit") == 0 and "ran" in out.get("output", ""),
           json.dumps(r))
        r = _st_rpc(worker, "tools/call",
                    {"name": "test_run", "arguments": {"runner": "python3", "target": "bad.py"}})
        out = json.loads(r["result"]["content"][0]["text"])
        ck("x2: a failing target reports passed=false with its exit code",
           out.get("passed") is False and out.get("exit") == 3)
        r = _st_rpc(worker, "tools/call",
                    {"name": "test_run", "arguments": {"runner": "bash", "target": "ok.py"}})
        ck("x3: a non-allowlisted runner (bash) is refused", "error" in r, json.dumps(r))
        r = _st_rpc(worker, "tools/call",
                    {"name": "test_run", "arguments": {"runner": "python3 ok.py; rm -rf /", "target": "ok.py"}})
        ck("x4: a runner given as a COMMAND STRING is refused (no shell to inject into)", "error" in r)
        marker = os.path.join(root, "pwned")
        r = _st_rpc(worker, "tools/call",
                    {"name": "test_run", "arguments": {"runner": "python3", "target": "ok.py",
                                                       "args": ["; touch pwned", "&& touch pwned"]}})
        ck("x5: shell metacharacters in args are inert data (shell=False), not syntax",
           not os.path.exists(marker) and json.loads(r["result"]["content"][0]["text"])["passed"] is True)
        r = _st_rpc(worker, "tools/call",
                    {"name": "test_run", "arguments": {"runner": "python3", "target": "../../etc/passwd"}})
        ck("x6: test_run refuses a target outside the repo root", "error" in r)

        # ── gi: git ops are read-only, and there is no history-writing tool anywhere ──────────────
        print("-- gi: git ops")
        r = _st_rpc(worker, "tools/call",
                    {"name": "git_read_file", "arguments": {"path": "docs/seed.md", "ref": "HEAD"}})
        ck("gi1: git_read_file reads a blob at a ref",
           "result" in r and "seed" in r["result"]["content"][0]["text"], json.dumps(r)[:200])
        r = _st_rpc(worker, "tools/call", {"name": "git_log", "arguments": {"n": 5}})
        ck("gi2: git_log lists commits", "result" in r and "init" in r["result"]["content"][0]["text"])
        ck("gi3: NO commit/merge/push/reap tool exists in ANY profile (the git pen stays with Forge)",
           not any(k in OP_TOOLS for k in ("git_commit", "git_merge", "git_push", "git_reap")))

        # ── j: the judge reads and executes, but never authors ────────────────────────────────────
        print("-- j: judge = read + execute, never authors")
        jlisted = [t["name"] for t in _st_rpc(judge, "tools/list")["result"]["tools"]]
        ck("j1: judge holds no writer of any kind",
           "file_write_deliverable" not in jlisted and not (set(jlisted) & WORK_PRODUCT_SINKS))
        ck("j2: judge CAN execute (an adversary must run code to prove a bug)", "test_run" in jlisted)
        r = _st_rpc(judge, "tools/call",
                    {"name": "file_write_deliverable", "arguments": {"path": deliv, "content": "x"}})
        ck("j3: judge attempting to write is refused", "error" in r and r["error"]["code"] == -32601)

        # ── i: policy integrity ───────────────────────────────────────────────────────────────────
        print("-- i: policy integrity")
        known = set(ROUTE_TOOLS) | set(OP_TOOLS)
        unknown = {r_: sorted(set(PROFILES[r_]) - known) for r_ in PROFILES if set(PROFILES[r_]) - known}
        ck("i1: every tool named in every profile is implemented", not unknown, json.dumps(unknown))
        ck("i2: the ticket's required routes are all exposed (queue/assign/kind/progress/work/journal)",
           all(t in ROUTE_TOOLS for t in ("ticket_queue", "ticket_assign", "ticket_kind",
                                          "ticket_progress", "work_record", "ticket_journal")))
        ck("i3: work_record is granted to forge ONLY — no model-driven role (research §2)",
           [r_ for r_ in PROFILES if "work_record" in PROFILES[r_]] == ["forge"])
        ck("i4: an unknown role is refused, not served",
           _st_rpc(_st_ctx("root", root), "tools/list")["error"]["code"] == -32602)
        ck("i5: every profile is a subset of the tools this server implements",
           all(set(PROFILES[r_]) <= known for r_ in PROFILES))
        ck("i6: every tool in every profile has a well-formed MCP inputSchema",
           all(tool_spec(n)["inputSchema"]["type"] == "object" for r_ in PROFILES for n in PROFILES[r_]))

        print("\n== selftest == %d/%d checks passed" % (sum(1 for _, c, _ in checks if c), len(checks)))
        for name, cond, detail in checks:
            if not cond:
                print("   FAILED: %s  — %s" % (name, detail))
        return 0 if all(c for _, c, _ in checks) else 1
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description="the ticket-API MCP bridge: governed routes + guarded file/git/test ops, "
                    "behind a per-role allowlist (no shell)")
    ap.add_argument("--role", choices=sorted(PROFILES),
                    help="which profile to serve: the process registers ONLY this role's tools")
    ap.add_argument("--deliverable", metavar="PATH",
                    help="repo-relative path file_write_deliverable is locked to (worker only)")
    ap.add_argument("--root", default=ROOT,
                    help="repo root the guarded file/git/test ops are confined to (default: this repo)")
    ap.add_argument("--profiles", action="store_true", help="print the role->tool matrix and exit")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the acceptance in a throwaway root; no db, no network, no agents")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if a.profiles:
        return print_profiles()
    if not a.role:
        ap.error("--role is required to serve (one of: %s); or use --profiles / --selftest"
                 % ", ".join(sorted(PROFILES)))
    if a.deliverable and os.path.isabs(a.deliverable):
        print("ticket_api_mcp: --deliverable must be repo-relative, not absolute: %s" % a.deliverable)
        return 2
    return serve({"role": a.role, "root": a.root, "deliverable": a.deliverable})


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — one-line message, never a traceback (+ a filed report)
        bug_report("main", e, "python3 ticket_api_mcp.py %s" % " ".join(sys.argv[1:]), e)
        print("ticket_api_mcp: %s" % e)
        sys.exit(2)
