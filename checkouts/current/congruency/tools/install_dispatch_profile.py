#!/usr/bin/env python3
"""install_dispatch_profile.py — THE DISPATCH PROFILE: one command that installs a "dispatch mode"
for this Mac's Claude Code, composed from ticket #209 (the tool-set), #210 (the capability floor) and
a role-anchor hook (ticket #212).

THE POINT. #209 gave the dispatcher deterministic TOOLS, #210 took away its authoring PENS. Neither
is wired into anything: #209 is an MCP server nobody registers, and #210 is a settings file nobody
passes. This file is the WIRING — it composes the three parts into a profile you install ONCE and
select with ONE flag, and it PROVES the composition rather than asserting it.

    python3 install_dispatch_profile.py install     # the one command
    dispatch-mode                                   # boots Claude Code in dispatch mode
    claude                                          # unchanged: normal mode

TERMS — defined at first use, because this file is read by an auditor who never met its author.

  * THE DISPATCHER (dispatch-01) is the routing agent: it reads the ticket queue and decides, per
    ticket, run/skip/stop. It authors NOTHING — a "run" becomes a child `pair_loop.py --ticket`
    process with its own branch and worktree, and that child's WORKER does the authoring
    (pair_loop.py: FOCUS["build"]["worker_tools"] grants it Write/Edit; the dispatcher spawn at
    `spawn_claude(prompt, "Read,Grep,Glob", ...)` does not).
  * DRIFT is the failure this profile exists to prevent, named by ticket #208: over a long session the
    dispatcher "forgets to dispatch, starts answering queries as a general-purpose agent, writes/edits
    code ITSELF instead of creating a build context and handing it to a properly-tooled agent."
  * THE LEDGER is the governed REST surface the dispatch tools read every decision from. The
    dispatcher keeps no state in its head; #209's tools re-derive every answer from the ledger on
    each call.
  * AN MCP SERVER is a process speaking JSON-RPC over stdio that offers TOOLS to the model. Claude
    Code names a server's tools `mcp__<server-key>__<tool>` — the key is whatever `mcpServers` maps it
    to. (Grounded: the binary's own `zR()`/`U1()` build exactly that prefix; `probe` re-reads it.)
  * A CUSTOM AGENT is a named profile Claude Code can boot the MAIN THREAD as. The `--agent <agent>`
    flag selects one ("Agent for the current session. Overrides the 'agent' setting."), and applying
    it "Applies the agent's system prompt, tool restrictions, and model" (the `agent` settings key's
    own description). That sentence is the whole mechanism this file leans on, and `probe` re-reads
    both strings out of the installed binary so you need not take it on trust.

THE THREE PARTS, LOADED AND NOT RESTATED. Every fact this file needs about the other two tickets is
IMPORTED from their modules at runtime, never copied. A copy is how a composition silently stops
matching the things it composes.

  b_tools    (#209) tools/dispatch_toolset.py  -> SERVER_NAME, TOOLS.
                    The MCP server key and the EXACT five tool names the profile allows. If #209 grows
                    a sixth tool tomorrow, this profile allows it the next time it is installed; if it
                    grew a WRITER, `verify`/`selftest` FAIL rather than quietly widening the floor.
  b_restrict (#210) tools/capability_restriction.py -> DENIED, ALLOWED, settings_document(),
                    verify_document(), hook_command(), MCP_SERVER.
                    The deny block and the PreToolUse hook are #210's, verbatim, produced by its own
                    code. This file MERGES its anchor hooks and memory keys into that document and
                    then re-runs #210's OWN verify_document() over the merged result, so composing
                    cannot break what #210 proved.
  b_anchor   (#211) NOT LANDED. See THE ANCHOR, below.

THE ANCHOR, and the honest state of the third gate. Ticket #212 says it is "gated on the three above",
but the third — #211 ("re-anchor the dispatcher role every turn; state from ledger not context") — had
NOT delivered when this file was written: on 2026-07-15 its ledger row was status ACTIVE with only
"branch ticket/211 opened" on its journal, no manifest artifact, and no anchor module existed anywhere
under tools/. That is a checkable claim, not a memory: `python3 install_dispatch_profile.py gate`
re-reads it from the live ledger in front of you and prints what it finds NOW.

So this file SHIPS ITS OWN ANCHOR rather than blocking on #211 or pretending to import it:

  * THE BUILT-IN ANCHOR is `anchor-hook` in this file — a UserPromptSubmit + SessionStart hook that
    re-injects the dispatcher directive as `additionalContext` EVERY TURN. It is complete and meets
    this ticket's acceptance today, with no dependency on #211.
  * THE SEAM is `--anchor-module PATH`: point it at #211's module when that lands and the profile uses
    ITS text instead of the built-in. The contract is one function or constant — `anchor_text()`
    returning a str, or an `ANCHOR_TEXT` str. A module that has neither is REFUSED BY NAME, never
    silently ignored.
  * There is NO auto-discovery by guessed filename. Inventing a path #211 has not chosen would be a
    claim about a file that does not exist. `install` and `verify` PRINT which anchor is in force, so
    the answer is always on screen and never inferred.

WHY THE DIRECTIVE, AND NOT THE STATE, IS RE-INJECTED. #211's own body asks for a re-injected directive
PLUS "state from ledger not context". The anchor therefore carries the ROLE and the TOOL CADENCE only
— it never embeds a queue snapshot. A snapshot would be stale the moment it was printed and would put
the dispatcher back to reasoning from context, which is the very thing #209 deleted. The state is the
tools; the anchor just keeps pointing at them.

THE PROFILE, exactly — four files, one command (`install`), all under --prefix (default ~/.claude):

  1. <prefix>/agents/dispatch.md              THE CUSTOM AGENT. Its `tools:` line is the read-only
                                              three plus the five REAL `mcp__dispatch-tools__*` names
                                              read out of #209 — i.e. "ONLY the dispatch toolset +
                                              read". Its `disallowedTools:` is #210's DENIED set. Its
                                              body is the anchor text (so the role is the agent's
                                              system prompt, not just a per-turn reminder).
  2. <prefix>/dispatch-profile/settings.json  #210's settings_document() (the bare-name deny block +
                                              its PreToolUse hook) MERGED with this file's
                                              UserPromptSubmit/SessionStart anchor hooks and the
                                              memory-minimisation keys.
  3. <prefix>/dispatch-profile/mcp.json       {"mcpServers": {"dispatch-tools": {...}}} — stdio,
                                              `python3 <abs>/dispatch_toolset.py --serve`.
  4. <prefix>/dispatch-profile/dispatch-mode  THE LAUNCHER: the one command that boots dispatch mode.

THE WILDCARD TRAP — the single most important fact in this file, and why the agent's tool list is
spelled out name by name. It would be natural to write `tools: Read, Grep, Glob, mcp__dispatch-tools__*`
and mean "read plus the dispatch server". What a BARE `*` does instead is turn the allow-list OFF
ENTIRELY. Read the shipped binary: `wPd()` normalises a tools value and returns `["*"]` if any element
is exactly `*`; `jrt()` then returns UNDEFINED for that, and an agent with `tools: undefined` "inherits
all tools from parent". So one stray `*` element does not widen the list a little — it deletes the
restriction and hands the dispatcher Write. (`mcp__dispatch-tools__*` is NOT that: `.includes("*")` is
an exact-element test, so a suffixed glob survives. The lethal spelling is a standalone `*`, which
`_6()` will also produce from a SPACE — `tools: Read *` splits to `["Read","*"]`.) `verify` FAILS any
tools/disallowedTools list carrying a bare `*`, and `selftest` mutation-tests that failure so the check
cannot rot into a rubber stamp. This is the agent-level cousin of #210's BARE-NAME TRAP: a rule that
reads correctly and restricts nothing.

THE YAML COMMENT TRAP — the same shape one layer down, and this file fell into it before it climbed
out. The agent file is YAML frontmatter, and in a YAML PLAIN (unquoted) scalar a `#` preceded by
whitespace starts a COMMENT: the rest of the line is discarded, silently. This file's own agent
description names its ticket, so the first draft emitted

    description: The DISPATCHER (ticket #212). Routes the ticket queue with ...

which a YAML parser loads as "The DISPATCHER (ticket". Nothing errors; the value is just quietly
truncated. Every frontmatter value is therefore emitted as a DOUBLE-QUOTED scalar (`_yaml_scalar`,
via json.dumps — YAML's double-quoted form takes JSON's escapes); `verify` FAILS a bare value carrying
a ` #` and prints exactly what YAML would have kept; `selftest` mutation-tests that check too (v4b).
The general lesson, and the reason `_frontmatter` and `_tool_list` each imitate the real parser rather
than being convenient: when your checker and the real parser disagree, the checker is the one that is
wrong, and it will go on saying PASS.

WHY --strict-mcp-config. The acceptance says the dispatcher has ONLY the dispatch toolset. Registering
dispatch-tools is not enough on its own — this Mac's other MCP servers (from ~/.claude.json, a
project's .mcp.json) would load alongside it. `--strict-mcp-config` ("Only use MCP servers from
--mcp-config") makes the registration exhaustive rather than additive. Its documented cost is that it
also blocks agent-frontmatter `mcpServers`, which is exactly why the server is declared in mcp.json
and NOT in the agent file: the two mechanisms are mutually exclusive and this profile picks the one
that also excludes everything else.

MINIMAL MEMORY, by mechanism — each lever named with what it actually covers, because "minimal memory"
is an acceptance item and a vague claim is an unprovable one:

  CLAUDE_CODE_DISABLE_CLAUDE_MDS=1   (launcher env)   no CLAUDE.md is loaded at all. The binary's
                                                      `OCe()` is `Boolean(env.CLAUDE_CODE_DISABLE_CLAUDE_MDS || ...)`.
  CLAUDE_CODE_DISABLE_AUTO_MEMORY=1  (launcher env)   no auto-memory read/write. The binary's `Rf()`
                                                      returns false on this env var.
  autoMemoryEnabled: false           (settings)       the same, carried by the settings file so a
                                                      hand-rolled `claude --agent dispatch --settings
                                                      ...` (no launcher, no env) still gets it.
  claudeMdExcludes: [...]            (settings)       the settings-carried fallback for CLAUDE.md,
                                                      for the same no-launcher case. It excludes User/
                                                      Project/Local memory files by glob; it CANNOT
                                                      exclude managed/policy memory, so it is a
                                                      fallback and the env var is the real lever.

SELECTING THE MODE — "a flag/agent selects dispatch mode vs normal":

    dispatch-mode                  DISPATCH MODE. The launcher: agent + deny floor + anchor + only the
                                   dispatch MCP + minimal memory. Extra args pass through.
    claude --agent dispatch        DISPATCH MODE, the flag alone: the agent's prompt + tool
                                   restrictions. This is the ergonomic form and it is a WEAKER one —
                                   no deny floor, no anchor hook, no memory trim, and other MCP
                                   servers still load. `verify` says so rather than letting you
                                   assume the two are equivalent.
    claude                         NORMAL MODE. Untouched. Nothing this profile installs is
                                   auto-loaded: the settings file is not `settings.json`, the mcp file
                                   is not `.mcp.json`, and an agent does nothing until it is selected.

WHAT THIS FILE DOES NOT CLAIM. It does not run `claude` — that binary is not among the runners this
ticket's worker may execute (python3 and the repo php are). So it never claims to have watched a live
dispatch session. What it PROVES BY EXECUTION: the anchor hook (`selftest` pipes real payloads into a
real subprocess of this file and reads the real decisions), the composition against #209's and #210's
real modules, every emitted document against #210's own verify_document() plus this file's invariants,
all mutation-tested. What it GROUNDS BY READING: the CLI/agent/hook semantics above, every one of
which is a byte string in the installed binary that `probe` re-greps in front of you. What is left
UNPROVEN is named as such by `verify` and `probe` — never dressed up as PASS.

Usage:
    python3 install_dispatch_profile.py profile        # the composed profile (every file, annotated)
    python3 install_dispatch_profile.py profile --json # ... as bare JSON, nothing else
    python3 install_dispatch_profile.py install        # THE ONE COMMAND (--prefix P, --force)
    python3 install_dispatch_profile.py verify         # audit an installed profile (--prefix P)
    python3 install_dispatch_profile.py argv           # the exact `claude` argv dispatch mode runs
    python3 install_dispatch_profile.py gate           # the three gates' LIVE status from the ledger
    python3 install_dispatch_profile.py anchor-hook    # BE the anchor hook: stdin JSON -> stdout JSON
    python3 install_dispatch_profile.py probe          # re-derive the CC semantics from the binary
    python3 install_dispatch_profile.py selftest       # prove the lot; writes nothing into this repo
    (any command takes --anchor-module PATH to use #211's anchor instead of the built-in)

SIDE EFFECTS, stated exactly (#153's lesson: a "creates no files" claim is checkable, so it had better
be true). `profile`, `verify`, `argv`, `gate`, `anchor-hook` and `probe` CREATE NO FILES and write
nothing anywhere — not even a __pycache__ entry (see the bytecode note below; importing #209/#210
would otherwise mint one in the REPO's tools/). `install` is the only command that writes: exactly the
four files above, under --prefix, and it refuses to overwrite any of them without --force. `selftest`
installs ONLY into a throwaway temp prefix and proves it two ways (r4/r5): no profile file exists at
the real ~/.claude prefix and nothing profile-shaped appeared there while it ran, and the repo's own
.claude/ is byte-for-byte identical before and after. (The asymmetry is deliberate and not a hedge:
~/.claude is LIVE — every running Claude Code session writes transcripts and snapshots under it — so a
byte-diff there would fail for reasons unrelated to this file, and a flaky check teaches its reader to
ignore red. The repo's .claude/ is quiet, so it gets the strict diff.) `gate` reads
the ledger over HTTP (GET only). The one exception is the error path every tool in this repo shares:
an UNEXPECTED exception appends a line to the registry's `bug_reports` sink (logs/, gitignored), per
note-for-claude — a crash report, not a side effect of any command working as documented.

Exit codes (each prints ONE line on failure, never a traceback):
    0  the command did its job. `verify`: the profile holds every invariant.
    1  a NEGATIVE ANSWER, not a malfunction. `verify`: the installed profile does NOT hold the
       invariants (each is named). `selftest`: at least one check FAILED. `probe`: the installed
       binary did NOT confirm every semantic this profile relies on (they may have moved in that
       version — re-read them before trusting the profile). `gate`: a gate is not landed.
    2  a precondition or usage failure — a missing/unparseable file, an unusable --anchor-module, a
       part that will not load, an unknown command or none at all, or (install) a file already there
       without --force.

Pure-python stdlib, one file — the repo is stdlib-only (DEPENDENCIES.md). Registry-gated per
note-for-claude: it walks UP to registry.json and refuses to run without it; any unexpected exception
files a timestamped Variant-A bug report to the registry's `bug_reports` sink.
"""
# NO BYTECODE CACHE — set BEFORE any local import. This module imports #209 and #210 from the repo's
# tools/ directory; Python writes a module's .pyc while importing it, so without this the "creates no
# files" promise above would be false the first time `profile` ran.
import sys

sys.dont_write_bytecode = True

import argparse
import importlib.util
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
import traceback


# ── registry gate (note-for-claude: a tool that cannot see the registry throws) ───────────────────
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
SELF = os.path.abspath(__file__)
TOOLS_DIR = os.path.dirname(SELF)

AGENT_NAME = "dispatch"                 # `claude --agent dispatch`
PROFILE_DIRNAME = "dispatch-profile"
LAUNCHER_NAME = "dispatch-mode"
DEFAULT_PREFIX = os.path.expanduser("~/.claude")

# The read-only inspection tools the dispatcher keeps. Exactly what pair_loop grants dispatch-01
# today (`spawn_claude(prompt, "Read,Grep,Glob", ...)`) — this profile widens nothing.
READ_TOOLS = ["Read", "Grep", "Glob"]

# Memory: the two env levers, each grounded in the binary (see MINIMAL MEMORY in the docstring).
MEMORY_ENV = {
    "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
}
# The settings-carried fallback for the no-launcher case. Globs, matched against absolute paths.
CLAUDE_MD_EXCLUDES = ["**/CLAUDE.md", "**/CLAUDE.local.md"]


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks).

    note-for-claude: every tool files a timestamped report when an exception is thrown — filename,
    function name, time of occurrence, methods to reproduce, possible cause.

    `bug_reports` is read defensively: a non-string value there would raise INSIDE this handler and
    replace the original exception with a confusing one, so a bad config falls back to the default
    sink rather than destroying the report it was called to file."""
    try:
        sink_rel = REGISTRY.get("bug_reports", "logs/bug_reports.jsonl")
        if not isinstance(sink_rel, str) or not sink_rel:
            sink_rel = "logs/bug_reports.jsonl"
        sink = os.path.join(ROOT, sink_rel)
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "install_dispatch_profile.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:],
                "note": "dispatch profile installer (ticket #212)",
            }) + "\n")
    except Exception:  # noqa: BLE001 — a failed report must never mask the failure it reports
        pass


class Fault(Exception):
    """A precondition/usage failure — reported as one line, exit 2."""


# ── the three parts, LOADED not restated ─────────────────────────────────────────────────────────
def load_part(name, path):
    """Import a repo tool as a module, to READ ITS OWN CONSTANTS rather than restate them.

    This is dispatch_toolset.py's load_module() pattern and for its reason: restating #209's tool
    names or #210's deny list here would let this profile drift out of agreement with the tickets it
    composes — which is exactly how a capability floor silently stops matching the thing it floors.
    Importing is offline for both parts (each only walks up to registry.json at import time; neither
    opens the db, the network or a subprocess), and writes no bytecode (set at the top of this file).
    """
    if not os.path.isfile(path):
        raise Fault("no %s at %s — this profile composes it and cannot be built without it" % (name, path))
    spec = importlib.util.spec_from_file_location("_dispatch_profile_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        raise Fault("%s at %s did not load (%s: %s) — refusing to compose a profile around a part "
                    "that will not import" % (name, path, type(e).__name__, e))
    return mod


def parts():
    """(#209 module, #210 module). Loaded fresh each call; both are cheap and neither holds state."""
    dt = load_part("dispatch_toolset", os.path.join(TOOLS_DIR, "dispatch_toolset.py"))
    cr = load_part("capability_restriction", os.path.join(TOOLS_DIR, "capability_restriction.py"))
    for attr, owner in (("SERVER_NAME", dt), ("TOOLS", dt)):
        if getattr(owner, attr, None) is None:
            raise Fault("dispatch_toolset.py no longer exports %s — this profile reads the MCP server "
                        "key and its tool names from it; re-read that module before installing" % attr)
    for attr in ("DENIED", "ALLOWED", "MCP_SERVER", "settings_document", "verify_document",
                 "hook_command"):
        if getattr(cr, attr, None) is None:
            raise Fault("capability_restriction.py no longer exports %s — this profile builds its "
                        "deny floor out of it; re-read that module before installing" % attr)
    # THE SEAM BETWEEN THE TWO PARTS. #210 allows `mcp__<MCP_SERVER>__*`; #209 answers to
    # SERVER_NAME. If those two strings ever disagree, #210's allow rule covers a server that is not
    # registered and the registered server is covered by nothing — the dispatcher would be un-denied
    # but un-granted, i.e. refused, and the profile would look installed while routing nothing. It is
    # one string equality and it is the whole reason these two tickets compose at all, so it is
    # checked rather than assumed.
    if cr.MCP_SERVER != dt.SERVER_NAME:
        raise Fault("the two parts disagree on the MCP server key: capability_restriction.MCP_SERVER "
                    "is %r but dispatch_toolset.SERVER_NAME is %r. #210's allow rule would cover a "
                    "server that is not registered. Reconcile them before installing."
                    % (cr.MCP_SERVER, dt.SERVER_NAME))
    return dt, cr


def mcp_tool_names(dt):
    """The dispatch toolset's tools, as Claude Code names them: `mcp__<server>__<tool>`.

    Read from #209's real TOOLS table, sorted for a stable file. This is what makes "ONLY the dispatch
    toolset" a fact about #209 rather than a list this file happened to type out once."""
    return ["mcp__%s__%s" % (dt.SERVER_NAME, t) for t in sorted(dt.TOOLS)]


def agent_tools(dt):
    """The agent's `tools:` allow-list: read-only inspection + the dispatch toolset, and nothing else.

    Spelled name by name. See THE WILDCARD TRAP in the module docstring: a bare `*` element would make
    Claude Code drop the restriction entirely and hand the dispatcher every tool it has."""
    return list(READ_TOOLS) + mcp_tool_names(dt)


# ── the anchor ────────────────────────────────────────────────────────────────────────────────────
# The dispatcher's standing directive. It is re-injected EVERY turn (UserPromptSubmit) and at session
# start, and it is also the agent's system prompt — belt and braces, because #208's drift is a slow
# forgetting and the cheapest cure is to never stop saying it.
#
# The ROLE sentence is not invented here: "You route; you never author work product." is pair_loop's
# own DISPATCH_RULES, imported below rather than retyped, so the anchor cannot drift from the rules
# the harness actually dispatches under.
ANCHOR_HEADLINE = "YOU ARE THE DISPATCHER (dispatch-01). This directive is re-injected every turn."

ANCHOR_BODY = """\
Your ONLY job is to route the ticket queue. You do not answer as a general-purpose agent, you do not
explain the codebase, and you do not write or edit code — the harness denies you those tools, so
attempting them wastes the turn. The tools below are your whole job; call them and read their answers.
Do not reason about what to do next: %(server)s already did that reasoning, deterministically, from
the ledger.

THE CADENCE — one pass of the loop:
%(cadence)s

STATE LIVES IN THE LEDGER, NOT IN THIS CONTEXT. Every tool re-derives its answer from the ledger on
each call, so you never need to remember what you saw last turn — and you must not act on it. If you
are unsure of anything, call the tool again; that is cheaper and more correct than recalling.

A ticket you decide to run is DISPATCHED, never done by you: %(dispatch_tool)s creates the build
context (branch + worktree) and hands it to a worker that has the file tools you do not. That is the
only path from "this needs code" to code.
"""

# What each tool is FOR, in the order one pass of the loop calls them. Keyed by #209's tool names; the
# cadence is built by looking each name up, so a tool added or renamed in #209 shows up here as an
# explicit gap rather than being silently dropped from the dispatcher's instructions.
CADENCE = [
    ("next_ready_ticket", "the PICK: the oldest queue ticket that passes every ready-rule, or idle "
                          "WITH the reason. Start here."),
    ("capacity",          "pairs running now vs the cap. Consult before dispatching."),
    ("dispatch",          "route the pick: kinds it if needed, records its deliverable, spawns the "
                          "pair — or queues it when at capacity. Both are answers."),
    ("requeue_chains",    "the self-repopulating chains' live heads, so a chain is never left "
                          "unrouted. A ready head is dispatched like any other pick."),
    ("harvest",           "file the distilled lesson for settled tickets that ran a pair. Do this "
                          "when the queue is idle."),
]


def anchor_text(dt=None, anchor_mod=None):
    """The directive the anchor injects. #211's module if one was supplied, else the built-in.

    See THE ANCHOR in the module docstring for why the built-in exists and what the seam's contract
    is. A supplied module that honours neither half of the contract is REFUSED BY NAME — falling back
    to the built-in silently would mean the operator asked for #211's anchor and got this one without
    being told, which is a lie the profile would then keep telling on every turn."""
    if anchor_mod is not None:
        fn = getattr(anchor_mod, "anchor_text", None)
        if callable(fn):
            out = fn()
            if isinstance(out, str) and out.strip():
                return out
            raise Fault("the anchor module's anchor_text() returned %r, not a non-empty string"
                        % (out,))
        const = getattr(anchor_mod, "ANCHOR_TEXT", None)
        if isinstance(const, str) and const.strip():
            return const
        raise Fault("the anchor module at %s honours neither half of the contract: it has no "
                    "anchor_text() returning a str and no non-empty ANCHOR_TEXT str. Refusing to "
                    "install a profile whose anchor is silently the built-in one."
                    % getattr(anchor_mod, "__file__", "(unknown)"))
    if dt is None:
        dt, _cr = parts()
    known = set(dt.TOOLS)
    lines = []
    for name, why in CADENCE:
        mark = "" if name in known else "   [NOT IN dispatch_toolset.TOOLS — re-read #209]"
        lines.append("  %-21s %s%s" % (name + "()", why, mark))
    for extra in sorted(known - {n for n, _w in CADENCE}):
        lines.append("  %-21s (tool present in #209 but not described here — re-read #209)" % (extra + "()"))
    # pair_loop's own words for the role, imported rather than retyped.
    pl = load_part("pair_loop", os.path.join(TOOLS_DIR, "pair_loop.py"))
    rules = getattr(pl, "DISPATCH_RULES", "") or ""
    role = "You route; you never author work product."
    if role not in rules:
        raise Fault("pair_loop.py's DISPATCH_RULES no longer contains %r — the anchor quotes the "
                    "harness's own role sentence and must not invent one. Re-read pair_loop.py."
                    % role)
    body = ANCHOR_BODY % {"server": dt.SERVER_NAME, "cadence": "\n".join(lines),
                          "dispatch_tool": "mcp__%s__dispatch" % dt.SERVER_NAME}
    return "%s\n\n%s\n%s" % (ANCHOR_HEADLINE, role, body)


def load_anchor_module(path):
    """#211's anchor module, when the operator names one. Explicit path only — never guessed."""
    if not path:
        return None
    if not os.path.isfile(path):
        raise Fault("no anchor module at %s — pass the path to #211's landed anchor, or omit "
                    "--anchor-module to use the built-in anchor." % path)
    return load_part("anchor", os.path.abspath(path))


def anchor_source(anchor_path=None):
    """A one-line, honest description of WHICH anchor is in force. Printed by install and verify."""
    if anchor_path:
        return "#211's module at %s (via --anchor-module)" % os.path.abspath(anchor_path)
    return "the BUILT-IN anchor in %s (ticket #211 had not landed; run `gate` for its live status)" % SELF


# ── the anchor hook ───────────────────────────────────────────────────────────────────────────────
# The events the anchor fires on, and what each buys. Both take `additionalContext`, which the binary
# reads back for exactly these event names (probe re-checks the strings).
ANCHOR_EVENTS = ("UserPromptSubmit", "SessionStart")
HOOK_TIMEOUT = 10          # seconds; this hook parses one JSON object and prints one, so 10s is ample


def anchor_command(self_path=SELF, python=None, anchor_path=None):
    """The shell command Claude Code runs for the anchor hook: this file, in `anchor-hook` mode.

    Absolute, because a hook runs with the project directory as cwd and this file lives under
    checkouts/current/congruency/tools; and shell-quoted, because the command string is handed to a
    shell and a path with a space would otherwise split into two arguments. Mirrors #210's
    hook_command() for both reasons."""
    cmd = "%s %s anchor-hook" % (shlex.quote(python or sys.executable), shlex.quote(self_path))
    if anchor_path:
        cmd += " --anchor-module %s" % shlex.quote(os.path.abspath(anchor_path))
    return cmd


def anchor_decision(payload, text):
    """The hook's answer for one payload. Returns (decision_dict_or_None, exit_code).

    The event name is ECHOED from the payload, because the binary reads `additionalContext` off the
    branch matching `hookSpecificOutput.hookEventName` — answering with the wrong event name would
    have the anchor silently inject nothing while every check that only looked at exit codes passed.

    FAIL OPEN, deliberately — the exact opposite of #210's hook, and the difference is worth stating
    because the two hooks sit in the same settings file. #210's hook is a SECURITY control: asked
    about a tool it cannot identify, it must deny, because a control that guesses "probably fine" is
    not a control. This hook is a REMINDER: it grants nothing and takes nothing away, so the worst a
    malformed payload can cost is one un-anchored turn. Blocking the dispatcher's turn because a
    reminder could not be phrased would be a self-inflicted outage, and the deny floor — the thing
    that actually stops it authoring code — does not depend on this hook at all."""
    if not isinstance(payload, dict):
        return None, 0
    event = payload.get("hook_event_name")
    if event not in ANCHOR_EVENTS:
        return None, 0
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}, 0


def do_anchor_hook(a):
    """Anchor hook mode: one JSON object in on stdin, at most one JSON object out on stdout.

    Always exits 0. A non-zero exit or a stderr splat would be read as a hook error and shown to the
    user as a broken hook every single turn — an anchor that cannot phrase itself must be quiet, not
    noisy. Mirrors #210's do_hook() in shape for the same reason: "said nothing on purpose" has to
    stay distinguishable from "crashed"."""
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else None
    except ValueError:
        payload = None
    try:
        text = anchor_text(None, load_anchor_module(a.anchor_module))
    except Fault as e:
        # The anchor could not be built (a part moved, or --anchor-module is unusable). Say so IN the
        # injected context rather than dying: a dispatcher told "your anchor is broken" can stop and
        # report, whereas a hook that exits non-zero just paints an error over every turn.
        text = ("DISPATCH PROFILE (ticket #212): the role anchor could NOT be built (%s). The "
                "dispatcher directive below is degraded — re-run `python3 %s verify`.\n\n%s"
                % (e, SELF, ANCHOR_HEADLINE))
    decision, code = anchor_decision(payload, text)
    if decision is not None:
        sys.stdout.write(json.dumps(decision) + "\n")
    return code


# ── the four artifacts ────────────────────────────────────────────────────────────────────────────
def profile_dir(prefix):
    return os.path.join(prefix, PROFILE_DIRNAME)


def paths(prefix=DEFAULT_PREFIX):
    """Every file the profile installs, by role. One dict, so install/verify/selftest cannot disagree
    about where anything lives."""
    d = profile_dir(prefix)
    return {"agent": os.path.join(prefix, "agents", "%s.md" % AGENT_NAME),
            "settings": os.path.join(d, "settings.json"),
            "mcp": os.path.join(d, "mcp.json"),
            "launcher": os.path.join(d, LAUNCHER_NAME)}


def _yaml_scalar(value):
    """One frontmatter value, as a YAML DOUBLE-QUOTED scalar.

    THE YAML COMMENT TRAP, and why nothing here is emitted bare. In a YAML plain (unquoted) scalar a
    `#` preceded by whitespace STARTS A COMMENT, and the rest of the line is discarded. This file's
    own agent description names its ticket — "(ticket #212)" — so emitted bare it would silently
    become "The DISPATCHER (ticket" and the parser would never complain. That is the same shape as
    THE WILDCARD TRAP: a line that reads correctly and means something else.

    A double-quoted scalar has no such rule, and YAML's double-quoted form accepts exactly JSON's
    string escapes — so json.dumps() emits a valid one, and `#`, `:`, `[`, `,` and friends all stop
    being metacharacters. `verify` FAILS a bare value carrying a ` #`, and `selftest` mutation-tests
    that failure."""
    return json.dumps(str(value))


def agent_document(dt, cr, anchor_path=None):
    """The custom agent file: YAML frontmatter + the anchor text as its system prompt.

    `tools` and `disallowedTools` are comma-separated, which the binary's `_6()` splits on commas AND
    spaces (parenthesised patterns survive) before `jrt()` normalises the result — so this spelling is
    the one the parser actually reads. Every name is literal: see THE WILDCARD TRAP. Every value is
    quoted: see THE YAML COMMENT TRAP in _yaml_scalar.

    `name` and `description` are the two the frontmatter parser requires (it returns null without
    either). The body is the prompt: an agent's system prompt is its markdown content."""
    tools = agent_tools(dt)
    denied = sorted(cr.DENIED)
    text = anchor_text(dt, load_anchor_module(anchor_path))
    desc = ("The DISPATCHER (ticket #212). Routes the ticket queue with the %s MCP tools and authors "
            "nothing. Selected with `claude --agent %s`." % (dt.SERVER_NAME, AGENT_NAME))
    fm = [
        "---",
        "name: %s" % _yaml_scalar(AGENT_NAME),
        "description: %s" % _yaml_scalar(desc),
        # ONLY the dispatch toolset + read. Enumerated, never globbed.
        "tools: %s" % _yaml_scalar(", ".join(tools)),
        # #210's deny set, at the agent layer too. The settings deny rules are the floor that actually
        # binds; this is the same policy stated where the agent is defined, so an operator reading the
        # agent file sees the whole shape of the role in one place.
        "disallowedTools: %s" % _yaml_scalar(", ".join(denied)),
        "model: %s" % _yaml_scalar("inherit"),
        "---",
        "",
    ]
    return "\n".join(fm) + text + "\n"


def mcp_document(dt):
    """The MCP registration: the dispatch toolset, on stdio, by absolute path.

    Absolute because the launcher does not control the cwd it is run from. This is the ONLY server
    the profile registers, and --strict-mcp-config makes that exhaustive (see WHY --strict-mcp-config)."""
    return {"mcpServers": {dt.SERVER_NAME: {
        "type": "stdio",
        "command": sys.executable,
        "args": [os.path.join(TOOLS_DIR, "dispatch_toolset.py"), "--serve"],
        "env": {},
    }}}


def settings_document(dt, cr, self_path=SELF, python=None, anchor_path=None):
    """#210's settings document, MERGED with this profile's anchor hooks and memory keys.

    Built by CALLING #210's settings_document(), never by restating it: the deny block and its
    PreToolUse hook are that ticket's output, so a change there lands here on the next install. The
    merge only ADDS — it appends hook groups under new event names and adds memory keys — so #210's
    invariants survive it, and `verify` re-runs #210's OWN verify_document() over the merged result to
    prove that rather than assume it."""
    doc = cr.settings_document(self_path=os.path.join(TOOLS_DIR, "capability_restriction.py"),
                               python=python)
    hooks = doc.setdefault("hooks", {})
    cmd = anchor_command(self_path, python, anchor_path)
    for event in ANCHOR_EVENTS:
        # No matcher: the anchor fires for every prompt / every session start. A matcher here would be
        # a filter on WHICH turns get re-anchored, and the drift this prevents has no schedule.
        hooks.setdefault(event, []).append(
            {"hooks": [{"type": "command", "command": cmd, "timeout": HOOK_TIMEOUT}]})
    # Minimal memory, the settings half (see MINIMAL MEMORY in the docstring for what each covers).
    doc["autoMemoryEnabled"] = False
    doc["claudeMdExcludes"] = list(CLAUDE_MD_EXCLUDES)
    # Boot the main thread as the dispatch agent even when someone passes only --settings. `--agent`
    # overrides this key, so the launcher's explicit flag still wins; this is the fallback that keeps
    # a hand-rolled `claude --settings <profile>/settings.json` from being a normal agent wearing a
    # deny floor.
    doc["agent"] = AGENT_NAME
    return doc


def agent_is_discoverable(prefix):
    """Will Claude Code actually FIND the agent this prefix installs?

    Agents are discovered from the USER scope (~/.claude/agents) and the PROJECT scope
    (<project>/.claude/agents) — not from an arbitrary directory. So `--prefix ~/.claude` (the
    default) and `--prefix <some-repo>/.claude` both work, and `--prefix /tmp/scratch` installs a
    perfectly valid agent file that `--agent dispatch` will never see.

    That is not a defect to hide: --prefix exists so `selftest` can install without touching this
    Mac, and a throwaway prefix is SUPPOSED to be inert. It IS something to say out loud, because an
    operator who installs to a custom prefix and then runs the launcher would otherwise get a bare
    "agent not found" with nothing pointing at the cause. install and verify print it; neither fails
    on it, because an undiscoverable agent is a property of where you asked it to go, not a broken
    profile."""
    return os.path.realpath(prefix) == os.path.realpath(DEFAULT_PREFIX) \
        or os.path.basename(os.path.realpath(prefix)) == ".claude"


def launcher_script(prefix, dt):
    """THE LAUNCHER: the one command that boots dispatch mode. A POSIX sh script.

    `exec` so the launcher does not linger as a parent process. `"$@"` so extra args pass through
    (`dispatch-mode -p "route the queue"` works). The env vars are set here rather than exported by
    the operator because a profile that needs a remembered `export` is a profile that will be run
    without it."""
    p = paths(prefix)
    argv = spawn_argv(prefix, dt, prompt=None)
    lines = [
        "#!/bin/sh",
        "# dispatch-mode — boot this Mac's Claude Code in DISPATCH MODE (ticket #212).",
        "#",
        "# Installed by: python3 %s install --prefix %s" % (SELF, prefix),
        "# Re-generate after changing the profile; do not hand-edit (install --force rewrites it).",
        "#",
        "# NORMAL MODE is just `claude` — nothing this profile installs is auto-loaded.",
        "set -eu",
        "",
        "# Minimal memory: no CLAUDE.md, no auto-memory (see MINIMAL MEMORY in %s)." % os.path.basename(SELF),
    ]
    for k, v in sorted(MEMORY_ENV.items()):
        lines.append("%s=%s; export %s" % (k, shlex.quote(v), k))
    lines += [
        "",
        "if [ ! -f %s ]; then" % shlex.quote(p["settings"]),
        "  echo 'dispatch-mode: %s is missing — re-run: python3 %s install' >&2"
        % (p["settings"], SELF),
        "  exit 2",
        "fi",
        "",
        "exec " + " ".join(shlex.quote(x) for x in argv) + ' "$@"',
        "",
    ]
    return "\n".join(lines)


def spawn_argv(prefix=DEFAULT_PREFIX, dt=None, prompt=None):
    """The exact `claude` argv dispatch mode runs. Each flag earns its place:

        --agent dispatch        select the profile's agent for the MAIN thread: its system prompt
                                (the anchor), its tool restrictions (read + the dispatch toolset) and
                                its model. This is the flag that selects dispatch mode vs normal.
        --settings <file>       the deny floor (#210) + the anchor hooks + the memory keys. A
                                per-spawn layer, so the WORKER — which runs in a worktree of this same
                                repo and must Write — is untouched (#210's SCOPE).
        --mcp-config <file>     register the dispatch toolset (#209).
        --strict-mcp-config     ...and ONLY it: no other MCP server on this Mac loads.
        --allowedTools          auto-approve the read-only three, exactly as pair_loop does for
                                dispatch-01 today. It denies nothing (that is the settings file's
                                job); it only keeps the dispatcher from being prompted for a Read.
                                The MCP tools are auto-approved by the settings file's allow rule.
    """
    p = paths(prefix)
    argv = ["claude"]
    if prompt is not None:
        argv += ["-p", prompt]
    argv += ["--agent", AGENT_NAME,
             "--settings", p["settings"],
             "--mcp-config", p["mcp"],
             "--strict-mcp-config",
             "--allowedTools", ",".join(READ_TOOLS)]
    return argv


# ── install ───────────────────────────────────────────────────────────────────────────────────────
def do_install(a):
    """THE ONE COMMAND. Writes the four files and prints exactly what it did.

    Refuses to clobber: an existing file is left alone unless --force. A settings file is a security
    control and an agent is a role definition; silently replacing one somebody tuned is how a control
    quietly stops matching what its owner thinks it says (#210's install refuses for the same reason).
    The refusal is checked for ALL four files BEFORE any is written, so a half-installed profile is
    never left behind."""
    prefix = a.prefix or DEFAULT_PREFIX
    dt, cr = parts()
    p = paths(prefix)
    if not a.force:
        existing = [v for v in p.values() if os.path.exists(v)]
        if existing:
            raise Fault("refusing to overwrite %d existing profile file(s): %s. Inspect them with "
                        "`verify --prefix %s`, or pass --force to replace them."
                        % (len(existing), ", ".join(existing), prefix))
    docs = {
        "agent": agent_document(dt, cr, a.anchor_module),
        "settings": json.dumps(settings_document(dt, cr, anchor_path=a.anchor_module), indent=2) + "\n",
        "mcp": json.dumps(mcp_document(dt), indent=2) + "\n",
        "launcher": launcher_script(prefix, dt),
    }
    for role, path in p.items():
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as fh:
            fh.write(docs[role])
    os.chmod(p["launcher"], os.stat(p["launcher"]).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print("installed the DISPATCH PROFILE (ticket #212) under %s" % prefix)
    print("  agent    : %s" % p["agent"])
    print("  settings : %s" % p["settings"])
    print("  mcp      : %s" % p["mcp"])
    print("  launcher : %s  (executable)" % p["launcher"])
    print()
    print("  composed from:")
    print("    #209 %s  -> server %r + %d tools" % (os.path.join(TOOLS_DIR, "dispatch_toolset.py"),
                                                    dt.SERVER_NAME, len(dt.TOOLS)))
    print("    #210 %s  -> denies %s" % (os.path.join(TOOLS_DIR, "capability_restriction.py"),
                                         ", ".join(sorted(cr.DENIED))))
    print("    anchor: %s" % anchor_source(a.anchor_module))
    print()
    print("  the dispatcher gets ONLY: %s" % ", ".join(agent_tools(dt)))
    print()
    print("DISPATCH MODE:  %s" % p["launcher"])
    print("   (or by hand: %s)" % " ".join(shlex.quote(x) for x in spawn_argv(prefix, dt)))
    print("NORMAL MODE:    claude          (unchanged — nothing installed here is auto-loaded)")
    print("VERIFY:         python3 %s verify --prefix %s" % (shlex.quote(SELF), shlex.quote(prefix)))
    if agent_is_discoverable(prefix):
        print()
        print("  Put dispatch mode on your PATH if you like:")
        print("    ln -s %s ~/.local/bin/%s" % (p["launcher"], LAUNCHER_NAME))
    else:
        print()
        print("  NOTE: %s is not a scope Claude Code discovers agents from (it reads" % prefix)
        print("  ~/.claude/agents and <project>/.claude/agents), so `--agent %s` will not find the"
              % AGENT_NAME)
        print("  agent file above. Expected for a throwaway prefix; re-install with no --prefix to")
        print("  put the profile on this Mac.")
    return 0


# ── verify ────────────────────────────────────────────────────────────────────────────────────────
def verify_profile(prefix, dt, cr, docs=None):
    """Audit an installed profile against the invariants that make it ENFORCEABLE. Returns [failures].

    Not a schema check — the list of ways a plausible-looking dispatch profile silently dispatches
    nothing or restricts nothing. Each invariant is here because getting it wrong produces a profile
    that reads correctly and does not hold, which is the worst outcome for a control. `selftest`
    mutation-tests every one: it breaks the profile in exactly that way and asserts this function
    catches it, so the checks cannot rot into a rubber stamp.

    `docs` lets a caller audit in-memory documents (that is what the mutation tests do); by default
    the files under `prefix` are read from disk."""
    bad = []
    p = paths(prefix)
    if docs is None:
        docs = {}
        for role, path in p.items():
            if not os.path.isfile(path):
                bad.append("%s is missing at %s — the profile is not installed (run `install`)"
                           % (role, path))
                continue
            try:
                raw = open(path).read()
            except OSError as e:
                bad.append("%s at %s is unreadable (%s)" % (role, path, e))
                continue
            if role in ("settings", "mcp"):
                try:
                    docs[role] = json.loads(raw)
                except ValueError as e:
                    bad.append("%s at %s is not valid JSON (%s)" % (role, path, e))
                    continue
            else:
                docs[role] = raw
        if bad:
            return bad

    # i1 — THE DENY FLOOR SURVIVED THE MERGE. #210's own checker, over this file's merged document.
    # Re-running the part's checker (rather than a copy of its rules) is the point: if composing broke
    # anything #210 proved, #210 says so in its own words.
    if "settings" in docs:
        for b in cr.verify_document(docs["settings"],
                                    self_path=os.path.join(TOOLS_DIR, "capability_restriction.py")):
            bad.append("settings: %s" % b)

    # i2 — THE ANCHOR IS WIRED, for every event it claims, pointing at a file that exists.
    hooks = (docs.get("settings") or {}).get("hooks") or {}
    for event in ANCHOR_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list) or not groups:
            bad.append("settings: no `hooks.%s` — the role anchor does not fire on %s, so the "
                       "dispatcher is never re-anchored there (this is the anti-drift mechanism)"
                       % (event, event))
            continue
        cmds = [h.get("command") for g in groups if isinstance(g, dict)
                for h in (g.get("hooks") or []) if isinstance(h, dict) and h.get("type") == "command"]
        cmds = [c for c in cmds if c]
        if not cmds:
            bad.append("settings: `hooks.%s` has no command hook — the event fires nothing" % event)
        for cmd in cmds:
            if "anchor-hook" not in cmd:
                bad.append("settings: the %s hook command %r does not run `anchor-hook` — it is not "
                           "the role anchor" % (event, cmd))
            target = _hook_target(cmd)
            if target and not os.path.isfile(target):
                bad.append("settings: the %s hook command points at %r, which does not exist — the "
                           "hook would fail on every turn. (Re-run `install --force`.)"
                           % (event, target))

    # i3 — MINIMAL MEMORY is actually configured. Each key is a lever named in the docstring; a
    # docstring that promises minimal memory over a settings file that does not set it is #153's
    # lesson repeating.
    s = docs.get("settings") or {}
    if s.get("autoMemoryEnabled") is not False:
        bad.append("settings: autoMemoryEnabled is not false — the dispatcher would read and write "
                   "the auto-memory directory, which is standing context this role must not carry")
    if not isinstance(s.get("claudeMdExcludes"), list) or not s.get("claudeMdExcludes"):
        bad.append("settings: claudeMdExcludes is missing or empty — a hand-rolled `claude --agent "
                   "%s --settings ...` (no launcher, no env) would load every CLAUDE.md" % AGENT_NAME)

    # i4 — THE AGENT GRANTS ONLY THE DISPATCH TOOLSET + READ, and THE WILDCARD TRAP is not sprung.
    agent = docs.get("agent") or ""
    fm = _frontmatter(agent)
    if fm is None:
        bad.append("agent: no YAML frontmatter — Claude Code's parser returns null for it, so the "
                   "agent does not exist and `--agent %s` would fail" % AGENT_NAME)
    else:
        # THE YAML COMMENT TRAP: a bare value carrying ` #` is truncated by YAML at the `#`, silently.
        for key, kept in _bare_comment_trap(agent):
            bad.append("agent: `%s:` is an UNQUOTED value containing ` #`, so YAML treats the rest of "
                       "the line as a comment and the parser would load only %r. Quote the value. "
                       "See THE YAML COMMENT TRAP." % (key, kept))
        for key in ("name", "description"):
            if not fm.get(key):
                bad.append("agent: frontmatter has no `%s` — the parser requires it and returns null "
                           "without it (the agent would silently not load)" % key)
        if fm.get("name") and fm["name"] != AGENT_NAME:
            bad.append("agent: frontmatter name is %r but the launcher selects %r — `--agent %s` "
                       "would not find it" % (fm["name"], AGENT_NAME, AGENT_NAME))
        want = agent_tools(dt)
        got = _tool_list(fm.get("tools"))
        if got is None:
            bad.append("agent: no `tools:` line — an agent with no tools list INHERITS EVERY TOOL "
                       "from the parent, including Write. The allow-list is the mechanism.")
        else:
            if "*" in got:
                bad.append("agent: `tools:` contains a bare `*`, so Claude Code drops the restriction "
                           "ENTIRELY (wPd() -> [\"*\"] -> jrt() -> undefined -> inherit all tools) and "
                           "the dispatcher would have Write. See THE WILDCARD TRAP. Enumerate the "
                           "names instead: %s" % ", ".join(want))
            extra = [t for t in got if t not in want]
            missing = [t for t in want if t not in got]
            if extra:
                bad.append("agent: `tools:` grants %s, which is not read-only inspection nor a tool of "
                           "the %s server — the acceptance is ONLY the dispatch toolset + read"
                           % (", ".join(extra), dt.SERVER_NAME))
            if missing:
                bad.append("agent: `tools:` is missing %s — the dispatcher cannot run the loop without "
                           "its own tools" % ", ".join(missing))
            for t in got:
                if cr.is_denied(t.split("(")[0])[0]:
                    bad.append("agent: `tools:` grants %r, which #210 denies — the deny rule wins, but "
                               "the profile contradicts itself" % t)
        dis = _tool_list(fm.get("disallowedTools"))
        if dis is None:
            bad.append("agent: no `disallowedTools:` line — #210's deny set is not stated at the agent "
                       "layer (the settings deny rules still hold)")
        elif "*" in dis:
            bad.append("agent: `disallowedTools:` contains a bare `*`, which jrt() turns into "
                       "undefined — it disallows NOTHING. See THE WILDCARD TRAP.")
        else:
            for name in sorted(cr.DENIED):
                if name not in dis:
                    bad.append("agent: `disallowedTools:` omits %r, which #210 denies (%s)"
                               % (name, cr.DENIED[name]))

    # i5 — THE SERVER IS REGISTERED, under the key #210's allow rule covers, running #209.
    mcp = (docs.get("mcp") or {}).get("mcpServers")
    if not isinstance(mcp, dict) or not mcp:
        bad.append("mcp: no `mcpServers` — the dispatch toolset is not registered, so with "
                   "--strict-mcp-config the dispatcher has NO tools at all")
    else:
        if dt.SERVER_NAME not in mcp:
            bad.append("mcp: no server keyed %r (found: %s) — Claude Code names its tools "
                       "mcp__<key>__<tool>, so the agent's tools and #210's allow rule would name a "
                       "server that is not there" % (dt.SERVER_NAME, ", ".join(sorted(mcp))))
        for key, spec in mcp.items():
            if key != dt.SERVER_NAME:
                bad.append("mcp: registers an extra server %r — the acceptance is ONLY the dispatch "
                           "toolset" % key)
                continue
            args = (spec or {}).get("args") or []
            script = next((x for x in args if str(x).endswith(".py")), None)
            if not script or not os.path.isfile(script):
                bad.append("mcp: server %r runs %r, which is not a file that exists — the server "
                           "would fail to start and every dispatch tool would be absent"
                           % (key, script))
            elif os.path.realpath(script) != os.path.realpath(os.path.join(TOOLS_DIR,
                                                                           "dispatch_toolset.py")):
                bad.append("mcp: server %r runs %s, not this repo's dispatch_toolset.py" % (key, script))
            if "--serve" not in [str(x) for x in args]:
                bad.append("mcp: server %r is not started with --serve, so it would not speak MCP "
                           "(dispatch_toolset.py requires one of --serve/--tools/--call/--selftest)"
                           % key)

    # i6 — THE LAUNCHER selects the agent and points at the files that exist.
    launcher = docs.get("launcher") or ""
    if launcher:
        for flag in ("--agent", "--settings", "--mcp-config", "--strict-mcp-config"):
            if flag not in launcher:
                bad.append("launcher: does not pass %s — dispatch mode would be %s" % (
                    flag, {"--agent": "a normal agent",
                           "--settings": "unrestricted (no deny floor, no anchor)",
                           "--mcp-config": "without the dispatch toolset",
                           "--strict-mcp-config": "additive: this Mac's other MCP servers would load "
                                                  "too, so it would NOT have ONLY the dispatch "
                                                  "toolset"}[flag]))
        for k in sorted(MEMORY_ENV):
            if k not in launcher:
                bad.append("launcher: does not set %s — dispatch mode would boot with standing memory"
                           % k)
        if os.path.isfile(p["launcher"]) and not os.access(p["launcher"], os.X_OK):
            bad.append("launcher: %s is not executable" % p["launcher"])
    return bad


def _frontmatter(text):
    """The agent file's YAML frontmatter as a flat dict, or None if there is none.

    A deliberately small reader: this profile emits only `key: <double-quoted scalar>` lines, so that
    is all it parses. It is not a YAML implementation and does not pretend to be — it exists so
    `verify` reads back the file this file WROTE.

    It reads values the way YAML would, in both forms, because a reader that disagreed with the real
    parser would bless a file the parser sees differently — the exact failure THE YAML COMMENT TRAP
    describes. A double-quoted value is unquoted through json.loads (YAML's double-quoted form takes
    JSON's escapes); a BARE value is truncated at a whitespace-preceded `#`, because that is what YAML
    does to it. verify then reports the truncation rather than silently comparing the wrong string."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    out = {}
    for line in text[3:end].splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith('"'):
            try:
                v = json.loads(v)
            except ValueError:
                pass                    # not a well-formed quoted scalar; report it as it stands
        else:
            cut = re.search(r"\s#", v)  # YAML: ` #` in a plain scalar starts a comment
            if cut:
                v = v[:cut.start()].strip()
        out[k.strip()] = v
    return out


def _bare_comment_trap(text):
    """Frontmatter keys whose value is BARE and carries a ` #` — i.e. YAML silently eats the rest.

    Returns [(key, what_yaml_keeps)]. This is the check that would have caught this file's own first
    draft, whose description read "The DISPATCHER (ticket #212)..." unquoted and would have loaded as
    "The DISPATCHER (ticket"."""
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    if end == -1:
        return []
    hits = []
    for line in text[3:end].splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith('"'):
            continue
        cut = re.search(r"\s#", v)
        if cut:
            hits.append((k.strip(), v[:cut.start()].strip()))
    return hits


def _tool_list(value):
    """A frontmatter tools value, split the way the binary's `_6()` splits it: on commas AND spaces,
    with parenthesised patterns kept whole (`Bash(git *)` is one entry, not three).

    `verify` must split the way the parser does or it would bless a list the parser reads differently
    — which is exactly how THE WILDCARD TRAP hides: `Read *` looks like one harmless entry and is two."""
    if value is None:
        return None
    out, buf, depth = [], "", 0
    for ch in str(value):
        if ch == "(":
            depth += 1
            buf += ch
        elif ch == ")":
            depth -= 1
            buf += ch
        elif ch in ", " and depth <= 0:
            if buf.strip():
                out.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf.strip())
    return out


def _hook_target(cmd):
    """The script path a hook command runs, if it names one we can check. Best-effort: a command we
    cannot parse is not reported as broken, because a false "your hook is broken" sends the reader to
    fix something that works. (#210's _hook_target, same reasoning.)"""
    try:
        parts_ = shlex.split(cmd)
    except ValueError:
        return None
    for part in parts_:
        if part.endswith(".py"):
            return part
    return None


def do_verify(a):
    """Audit an installed profile. Exit 0 if it holds, 1 if it does not, 2 if a part will not load."""
    prefix = a.prefix or DEFAULT_PREFIX
    dt, cr = parts()
    p = paths(prefix)
    bad = verify_profile(prefix, dt, cr)
    if bad:
        print("FAIL %s — %d problem(s):" % (prefix, len(bad)))
        for b in bad:
            print("  - %s" % b)
        return 1
    print("OK   the DISPATCH PROFILE holds, under %s" % prefix)
    print("     agent %r grants ONLY: %s" % (AGENT_NAME, ", ".join(agent_tools(dt))))
    print("     denies: %s (bare names — the only spelling the tool-level matcher honours)"
          % ", ".join(sorted(cr.DENIED)))
    print("     anchor: fires on %s; %s" % (" + ".join(ANCHOR_EVENTS), anchor_source(a.anchor_module)))
    print("     mcp   : %r -> %s --serve (and --strict-mcp-config makes it the ONLY server)"
          % (dt.SERVER_NAME, os.path.join(TOOLS_DIR, "dispatch_toolset.py")))
    print("     memory: autoMemoryEnabled=false, claudeMdExcludes=%s; launcher also exports %s"
          % (",".join(CLAUDE_MD_EXCLUDES), ", ".join(sorted(MEMORY_ENV))))
    print()
    print("     DISPATCH MODE: %s" % p["launcher"])
    print("     NORMAL MODE:   claude")
    print()
    print("     NOT EQUIVALENT: `claude --agent %s` alone gets the agent's prompt and tool" % AGENT_NAME)
    print("     restrictions ONLY — no deny floor, no anchor hook, no memory trim, and this Mac's")
    print("     other MCP servers still load. Use the launcher for the whole profile.")
    if not agent_is_discoverable(prefix):
        print()
        print("     NOTE: %s is not a scope Claude Code discovers agents from (it reads" % prefix)
        print("     ~/.claude/agents and <project>/.claude/agents), so `--agent %s` will not find"
              % AGENT_NAME)
        print("     this agent. That is expected for a throwaway prefix; re-install with no --prefix")
        print("     to put it on this Mac.")
    return 0


# ── argv / profile / gate ─────────────────────────────────────────────────────────────────────────
def do_argv(a):
    """The exact `claude` argv dispatch mode runs, and what each flag buys."""
    prefix = a.prefix or DEFAULT_PREFIX
    dt, _cr = parts()
    p = paths(prefix)
    print("DISPATCH MODE — the launcher (%s) execs:" % p["launcher"])
    print()
    for k, v in sorted(MEMORY_ENV.items()):
        print("  %s=%s \\" % (k, v))
    print("  " + " \\\n    ".join(shlex.quote(x) for x in spawn_argv(prefix, dt)))
    print()
    print("NORMAL MODE — unchanged:")
    print("  claude")
    print()
    print("Each flag:")
    print("  --agent %-18s select the dispatch agent for the MAIN thread: its system prompt (the"
          % AGENT_NAME)
    print("  %-25s anchor), its tool restrictions (read + the dispatch toolset), its model." % "")
    print("  --settings <file>         the deny floor (#210) + the anchor hooks + the memory keys.")
    print("  --mcp-config <file>       register the dispatch toolset (#209).")
    print("  --strict-mcp-config       ...and ONLY it — no other MCP server on this Mac loads.")
    print("  --allowedTools Read,...   auto-approve the read-only three (exactly what pair_loop")
    print("                            grants dispatch-01 today). It denies nothing.")
    missing = [v for v in paths(prefix).values() if not os.path.exists(v)]
    if missing:
        print()
        print("NOTE: %d profile file(s) do not exist yet — run `install` first, or the spawn fails."
              % len(missing))
        for m in missing:
            print("      %s" % m)
    return 0


def do_profile(a):
    """Print the whole composed profile: every file, annotated, without installing anything."""
    dt, cr = parts()
    prefix = a.prefix or DEFAULT_PREFIX
    p = paths(prefix)
    docs = {"agent": agent_document(dt, cr, a.anchor_module),
            "settings": settings_document(dt, cr, anchor_path=a.anchor_module),
            "mcp": mcp_document(dt),
            "launcher": launcher_script(prefix, dt)}
    if a.json:
        print(json.dumps({"prefix": prefix, "paths": p, "documents": docs}, indent=2))
        return 0
    print("THE DISPATCH PROFILE (ticket #212) — composed, not installed")
    print("=" * 78)
    print("b_tools    #209  %s" % os.path.join(TOOLS_DIR, "dispatch_toolset.py"))
    print("                 server %r; tools: %s" % (dt.SERVER_NAME, ", ".join(sorted(dt.TOOLS))))
    print("b_restrict #210  %s" % os.path.join(TOOLS_DIR, "capability_restriction.py"))
    print("                 denies: %s" % ", ".join(sorted(cr.DENIED)))
    print("b_anchor   #211  %s" % anchor_source(a.anchor_module))
    print()
    print("THE DISPATCHER GETS ONLY: %s" % ", ".join(agent_tools(dt)))
    print("Every name is literal. A bare `*` in that list would make Claude Code drop the")
    print("restriction entirely and hand the dispatcher Write — see THE WILDCARD TRAP.")
    print()
    for role in ("agent", "settings", "mcp", "launcher"):
        print("-" * 78)
        print("### %s  ->  %s" % (role.upper(), p[role]))
        print("-" * 78)
        body = docs[role]
        print(body if isinstance(body, str) else json.dumps(body, indent=2))
        print()
    print("=" * 78)
    print("INSTALL:  python3 %s install --prefix %s" % (shlex.quote(SELF), shlex.quote(prefix)))
    return 0


def do_gate(a):
    """The three gates' LIVE status, read from the ledger. Read-only (GETs only).

    #212 is "gated on the three above" and this command is how that claim is checked rather than
    remembered: it prints what the ledger says NOW. It reads through #209's own Ledger class, so it
    speaks to the same surface the dispatch tools do."""
    dt, _cr = parts()
    gates = [(209, "b_tools", os.path.join(TOOLS_DIR, "dispatch_toolset.py")),
             (210, "b_restrict", os.path.join(TOOLS_DIR, "capability_restriction.py")),
             (211, "b_anchor", None)]
    print("THE THREE GATES of ticket #212, from the live ledger (%s):" % dt.CONG)
    print()
    unmet = 0
    for tid, role, artifact in gates:
        try:
            row = dt.Ledger().ticket(tid)
        except Exception as e:  # noqa: BLE001 — the ledger being down is an ANSWER here, not a crash
            print("  #%-4s %-11s UNKNOWN — the ledger did not answer (%s: %s)"
                  % (tid, role, type(e).__name__, e))
            unmet += 1
            continue
        status = (row.get("status") or "(none)").upper() if row else "(no such ticket)"
        landed = bool(artifact and os.path.isfile(artifact))
        if not landed:
            unmet += 1
        print("  #%-4s %-11s ledger=%-10s artifact=%s"
              % (tid, role, status, "LANDED" if landed else "NOT LANDED"))
        print("        %s" % (row.get("title") or "")[:88])
        if artifact:
            print("        %s" % artifact)
    print()
    if unmet:
        print("%d gate(s) are not landed as an importable artifact under tools/." % unmet)
        print("The anchor (#211) is the known one: this profile ships its own BUILT-IN anchor so the")
        print("acceptance holds today, and `--anchor-module PATH` adopts #211's when it lands.")
        print("Nothing here blocks `install`.")
        return 1
    print("all three gates are landed.")
    return 0


# ── probe: re-derive the Claude Code semantics from the installed binary ──────────────────────────
# Each claim this profile makes about Claude Code, paired with a byte string that is present in the
# shipped binary if and only if the claim's code path is there. These are read, not executed: the
# `claude` binary is not among the runners this ticket's worker may run.
PROBES = [
    (b"Agent for the current session. Overrides the 'agent' setting.",
     "--agent <agent> selects an agent for THIS session — the flag that picks dispatch vs normal."),
    (b"Name of an agent (built-in or custom) to use for the main thread. Applies the agent's system "
     b"prompt, tool restrictions, and model.",
     "The `agent` setting applies an agent to the MAIN thread, and applying it applies its TOOL "
     "RESTRICTIONS — the mechanism the whole profile rests on."),
    (b"Only use MCP servers from --mcp-config",
     "--strict-mcp-config makes the registration exhaustive: ONLY the dispatch toolset loads."),
    (b"Load MCP servers from JSON files or strings (space-separated)",
     "--mcp-config takes the mcp.json this profile installs."),
    (b"Array of allowed tool names. If omitted, inherits all tools from parent.",
     "An agent's `tools` is an ALLOW-LIST, and OMITTING it inherits everything — which is what the "
     "wildcard trap silently causes."),
    (b'hookEventName:v.literal("UserPromptSubmit"),additionalContext',
     "The UserPromptSubmit hook injects `additionalContext` — how the anchor re-anchors every turn."),
    (b"CLAUDE_CODE_DISABLE_CLAUDE_MDS",
     "The env lever the launcher sets so no CLAUDE.md is loaded (minimal memory)."),
    (b"CLAUDE_CODE_DISABLE_AUTO_MEMORY",
     "The env lever the launcher sets so auto-memory is not read or written (minimal memory)."),
    (b"Enable auto-memory for this project. When false, Claude will not read from or write to the "
     b"auto-memory directory.",
     "The `autoMemoryEnabled` setting this profile sets to false."),
    (b"CLAUDE.md files to exclude from loading",
     "The `claudeMdExcludes` setting — the settings-carried CLAUDE.md fallback."),
]


def probe_binary(path):
    """Grep the binary for each semantic. Returns [(found?, claim)]. Reads in chunks with an overlap,
    so a needle straddling a chunk boundary is still found and a 240MB binary is never held in memory
    at once. (#210's probe_binary, same shape.)"""
    needles = [p[0] for p in PROBES]
    found = {n: False for n in needles}
    biggest = max(len(n) for n in needles)
    with open(path, "rb") as fh:
        tail = b""
        while True:
            chunk = fh.read(1 << 22)
            if not chunk:
                break
            buf = tail + chunk
            for n in needles:
                if not found[n] and n in buf:
                    found[n] = True
            if all(found.values()):
                break
            tail = buf[-biggest:]
    return [(found[n], claim) for n, claim in PROBES]


def do_probe(_a):
    """Re-derive this profile's claims about Claude Code from the installed binary.

    The binary is found with #210's own find_claude() — one finder, so the two tickets cannot disagree
    about which binary they are talking about."""
    _dt, cr = parts()
    path = cr.find_claude()
    if not path:
        raise Fault("no Claude Code binary found (looked at $CLAUDE_BIN, ~/.local/bin/claude, and "
                    "$PATH) — the claims in this module's docstring cannot be re-derived here. They "
                    "are UNKNOWN on this machine, not disproven.")
    print("probing: %s" % path)
    results = probe_binary(path)
    for ok, claim in results:
        print("  %-9s %s" % ("CONFIRMED" if ok else "NOT FOUND", claim))
    missing = [c for ok, c in results if not ok]
    if missing:
        print()
        print("%d claim(s) could not be confirmed against this binary. The semantics this profile "
              "relies on may have moved or changed in this Claude Code version — re-read them before "
              "trusting the profile." % len(missing))
        return 1
    print()
    print("all %d Claude Code semantics confirmed in the installed binary." % len(results))
    return 0


# ── selftest ──────────────────────────────────────────────────────────────────────────────────────
def _run_anchor(payload_text, extra=()):
    """Run the REAL anchor hook, as Claude Code runs it: a subprocess of this file in `anchor-hook`
    mode, the payload on stdin, the decision on stdout.

    A subprocess and not a function call, deliberately (#210's _run_hook, same reasoning): the thing
    that has to work is the COMMAND in the settings file, and an in-process call would prove the logic
    while leaving the argv, the stdin plumbing and the exit code — every part actually wired into the
    harness — untested."""
    p = subprocess.run([sys.executable, SELF, "anchor-hook"] + list(extra), input=payload_text,
                       capture_output=True, text=True, timeout=60)
    out = None
    if p.stdout.strip():
        try:
            out = json.loads(p.stdout)
        except ValueError:
            out = {"__unparseable__": p.stdout}
    return p.returncode, out, p.stderr


def _payload(event, prompt="route the queue"):
    return json.dumps({"hook_event_name": event, "prompt": prompt, "session_id": "selftest",
                       "cwd": ROOT})


def _tree(root):
    """Every path under root, for the before/after side-effect proof (#153's lesson)."""
    seen = set()
    for dirpath, dirnames, filenames in os.walk(root):
        for n in list(dirnames) + filenames:
            seen.add(os.path.join(dirpath, n))
    return seen


def _quietly(fn, *args):
    """Call fn with stdout muted, returning its value. Keeps a fixture's narration out of selftest's
    PASS/FAIL column; exceptions propagate untouched."""
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args)


class _Args:
    """A stand-in for argparse's namespace, for driving commands as fixtures."""

    def __init__(self, **kw):
        self.prefix = None
        self.force = False
        self.anchor_module = None
        self.json = False
        for k, v in kw.items():
            setattr(self, k, v)


def do_selftest(_a):
    """Prove the deliverable. One PASS/FAIL/SKIP line per check; exit 0 only if none FAILED.

    WHAT IS PROVEN BY EXECUTION vs BY READING — the honest limit of this file, stated plainly. The
    ANCHOR HOOK is executed for real (a1-a6: real subprocesses, real payloads, real decisions). The
    COMPOSITION is executed for real (c1-c5: the real #209/#210 modules, their real constants). The
    PROFILE's invariants are executed and MUTATION-TESTED (v1-v10: each check is shown to FAIL a
    profile broken in exactly the way it exists to catch — a check that never fails is not a check).
    INSTALL is executed against a throwaway prefix (r1-r3), and the ACCEPTANCE is then driven off the
    files it actually wrote (e1: the installed mcp.json starts a real MCP server and its real
    tools/list is compared to the installed agent's real allow-list; e2: the PreToolUse command taken
    verbatim out of the installed settings.json is run against a real Write payload and must deny).
    The CLAUDE CODE RUNTIME is NOT executed: `claude` is not among the runners this ticket's worker
    may run, so its behaviour is established by reading the shipped binary, which p1 re-does here and
    reports as SKIP — never as PASS — when no binary can be found. So "the dispatcher has only these
    tools and cannot Write" is proven about the ARTIFACTS and the SEMANTICS, not by watching a live
    session — that last step is the operator's, and `verify` tells them what to expect.

    Writes NOTHING into this repo or into the real ~/.claude, and proves it (r4, r5)."""
    checks = []

    def ok(tag, cond, msg):
        checks.append((("PASS" if cond else "FAIL"), tag, msg))
        return cond

    def skip(tag, msg):
        checks.append(("SKIP", tag, msg))

    dt, cr = parts()

    # ── c: THE COMPOSITION, against the parts' real modules ───────────────────────────────────────
    ok("c1", cr.MCP_SERVER == dt.SERVER_NAME,
       "the two parts agree on the MCP server key (#210 allows mcp__%s__*, #209 answers to %r)"
       % (cr.MCP_SERVER, dt.SERVER_NAME))
    want = agent_tools(dt)
    ok("c2", want == READ_TOOLS + ["mcp__%s__%s" % (dt.SERVER_NAME, t) for t in sorted(dt.TOOLS)],
       "the agent's tools are READ + #209's real %d tools, read from its TOOLS table: %s"
       % (len(dt.TOOLS), ", ".join(want)))
    # The acceptance's teeth: not one tool the dispatcher keeps may be an authoring tool. This is
    # asked of #210's own predicate, over #209's own tool names — neither list is restated here, so
    # if #209 ever grows a writer this FAILS instead of quietly shipping it.
    authoring = [t for t in want if cr.is_denied(t.split("(")[0])[0]]
    ok("c3", not authoring,
       "NOT ONE tool the dispatcher keeps is an authoring tool (#210's own is_denied() over #209's "
       "own tool names)%s" % ("" if not authoring else "; AUTHORING: %s" % ", ".join(authoring)))
    ok("c4", "*" not in want,
       "no bare `*` element in the agent's tool list (the wildcard trap is not sprung)")
    text = anchor_text(dt)
    ok("c5", all(t in text for t in dt.TOOLS) and "never author work product" in text,
       "the anchor names the role (pair_loop's own sentence) and every one of #209's tools")

    # ── a: THE ANCHOR HOOK, executed for real ─────────────────────────────────────────────────────
    # a1-a2: the ticket's acceptance — "re-anchors its role", on every turn and at session start.
    for i, event in enumerate(ANCHOR_EVENTS, 1):
        rc, out, err = _run_anchor(_payload(event))
        hso = (out or {}).get("hookSpecificOutput") or {}
        good = (rc == 0 and hso.get("hookEventName") == event
                and "DISPATCHER" in (hso.get("additionalContext") or ""))
        ok("a%d" % i, good, "the real hook re-anchors on %s (exit %s, event %r, %d chars of context)"
           % (event, rc, hso.get("hookEventName"), len(hso.get("additionalContext") or "")))

    # a3: the injected text is the anchor, and it names the tools the dispatcher must call. An anchor
    # that says "you are the dispatcher" but not WHAT TO CALL leaves the model to invent a cadence.
    rc, out, _ = _run_anchor(_payload("UserPromptSubmit"))
    ctx = ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext") or ""
    ok("a3", all(t in ctx for t in dt.TOOLS) and "ledger" in ctx.lower(),
       "the injected context names every one of #209's %d tools and points state at the ledger"
       % len(dt.TOOLS))

    # a4: it stays SILENT on events it is not wired for — a hook that answers everything would inject
    # the directive into unrelated events and look like a bug.
    rc, out, _ = _run_anchor(_payload("PreToolUse"))
    ok("a4", rc == 0 and out is None, "the real hook says NOTHING on an event it is not wired for")

    # a5: fail OPEN (see anchor_decision): a malformed payload costs one un-anchored turn, never a
    # blocked one. This is the deliberate opposite of #210's fail-closed hook.
    rc1, out1, _ = _run_anchor("not json at all")
    rc2, out2, _ = _run_anchor(json.dumps({"prompt": "x"}))
    ok("a5", rc1 == 0 and out1 is None and rc2 == 0 and out2 is None,
       "the real hook FAILS OPEN and quiet on an unparseable payload and on one with no event name")

    # a6: THE SEAM. #211's anchor, when supplied, is the one that gets injected — proven with a real
    # stand-in module, through a real subprocess, exactly as the hook would load it.
    tmpmod = tempfile.mkdtemp(prefix="dispatch_profile_anchor_")
    try:
        mp = os.path.join(tmpmod, "fake_211_anchor.py")
        open(mp, "w").write('ANCHOR_TEXT = "ANCHOR-FROM-211: you are the dispatcher."\n')
        rc, out, _ = _run_anchor(_payload("UserPromptSubmit"), ["--anchor-module", mp])
        ctx2 = ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext") or ""
        ok("a6", rc == 0 and "ANCHOR-FROM-211" in ctx2,
           "--anchor-module makes the hook inject THAT module's text (the #211 seam works)")
        # and a module honouring neither half of the contract is refused BY NAME, not silently
        # fallen back from — the operator asked for #211's anchor and must not get this one instead.
        bad_mod = os.path.join(tmpmod, "empty_anchor.py")
        open(bad_mod, "w").write("X = 1\n")
        try:
            _quietly(anchor_text, dt, load_anchor_module(bad_mod))
            refused = False
        except Fault:
            refused = True
        ok("a7", refused,
           "an --anchor-module honouring neither half of the contract is REFUSED, never silently "
           "replaced by the built-in")
    finally:
        shutil.rmtree(tmpmod, ignore_errors=True)

    # ── v: the profile documents, and the mutation tests that keep `verify` honest ────────────────
    prefix0 = "/nonexistent-prefix-for-doc-checks"
    docs = {"agent": agent_document(dt, cr), "settings": settings_document(dt, cr),
            "mcp": mcp_document(dt), "launcher": launcher_script(prefix0, dt)}
    base = verify_profile(prefix0, dt, cr, docs=json.loads(json.dumps(docs)))
    ok("v1", base == [], "the composed profile holds every invariant (%s)" % (base or "clean"))

    # v2: #210's OWN checker passes over the MERGED settings — composing did not break what #210
    # proved. This is the check that makes "merged, not restated" mean something.
    ok("v2", cr.verify_document(docs["settings"],
                                self_path=os.path.join(TOOLS_DIR, "capability_restriction.py")) == [],
       "#210's own verify_document() passes over the settings AFTER this file merged its anchor "
       "hooks and memory keys in")

    def mutate(fn):
        m = json.loads(json.dumps(docs))
        fn(m)
        return verify_profile(prefix0, dt, cr, docs=m)

    # v3 — THE WILDCARD TRAP. The whole reason the tools line is enumerated.
    def _star(m):
        m["agent"] = m["agent"].replace('tools: "Read', 'tools: "*, Read')
    ok("v3", any("bare `*`" in b and "tools" in b for b in mutate(_star)),
       "verify CATCHES a bare `*` in the agent's tools (the trap that reads right and grants "
       "EVERYTHING)")

    # v3b — the space-spelled version of the same trap: `_6()` splits on spaces, so `Read *` is two
    # entries and the second one is lethal.
    def _star_space(m):
        m["agent"] = m["agent"].replace('tools: "Read,', 'tools: "Read *,')
    ok("v3b", any("bare `*`" in b for b in mutate(_star_space)),
       "verify CATCHES the SPACE-spelled wildcard (`tools: Read *`), because it splits the way the "
       "binary's _6() does")

    # v4 — an authoring tool smuggled into the agent's allow-list.
    def _write(m):
        m["agent"] = m["agent"].replace('tools: "Read', 'tools: "Write, Read')
    fails = mutate(_write)
    ok("v4", any("Write" in b for b in fails),
       "verify CATCHES `Write` added to the agent's tools")

    # v4b — THE YAML COMMENT TRAP. This file's own first draft emitted the description bare, and it
    # names its ticket, so YAML would have loaded "The DISPATCHER (ticket" and said nothing. The check
    # exists because the bug was real; the mutation proves the check would have caught it.
    def _bare_desc(m):
        lines = []
        for l in m["agent"].splitlines():
            if l.startswith("description:"):
                l = "description: The DISPATCHER (ticket #212). Routes the queue."
            lines.append(l)
        m["agent"] = "\n".join(lines)
    fails = mutate(_bare_desc)
    ok("v4b", any("UNQUOTED value containing" in b and "The DISPATCHER (ticket" in b for b in fails),
       "verify CATCHES an unquoted frontmatter value that YAML would truncate at a `#` comment")

    # v5 — the anchor silently unwired. The anti-drift mechanism vanishing must not read as OK.
    def _noanchor(m):
        m["settings"]["hooks"].pop("UserPromptSubmit", None)
    ok("v5", any("hooks.UserPromptSubmit" in b for b in mutate(_noanchor)),
       "verify CATCHES the UserPromptSubmit anchor being removed (drift would go unchecked)")

    # v6 — the deny floor removed. #210's checker is the one that must notice, through this one.
    def _nodeny(m):
        m["settings"]["permissions"]["deny"] = [r for r in m["settings"]["permissions"]["deny"]
                                                if r != "Write"]
    ok("v6", any("Write" in b and "settings:" in b for b in mutate(_nodeny)),
       "verify CATCHES Write removed from the deny floor (via #210's own checker)")

    # v7 — the MCP server unregistered / renamed: the agent's tools would name a server that is not
    # there, and with --strict-mcp-config the dispatcher would have no tools at all.
    def _renamed(m):
        m["mcp"]["mcpServers"] = {"something-else": m["mcp"]["mcpServers"][dt.SERVER_NAME]}
    fails = mutate(_renamed)
    ok("v7", any("no server keyed" in b for b in fails) and any("extra server" in b for b in fails),
       "verify CATCHES the MCP server being registered under the wrong key")

    # v8 — memory not minimised.
    def _mem(m):
        m["settings"]["autoMemoryEnabled"] = True
    ok("v8", any("autoMemoryEnabled" in b for b in mutate(_mem)),
       "verify CATCHES auto-memory being left on")

    # v9 — the launcher dropping --strict-mcp-config: the profile would still work, but it would no
    # longer be ONLY the dispatch toolset, which is the acceptance's actual wording.
    def _lax(m):
        m["launcher"] = m["launcher"].replace("--strict-mcp-config", "")
    ok("v9", any("strict-mcp-config" in b for b in mutate(_lax)),
       "verify CATCHES the launcher dropping --strict-mcp-config (other MCP servers would load)")

    # v10 — the agent losing its tools line entirely: inherits EVERY tool, including Write.
    def _notools(m):
        m["agent"] = "\n".join(l for l in m["agent"].splitlines() if not l.startswith("tools:"))
    ok("v10", any("no `tools:` line" in b for b in mutate(_notools)),
       "verify CATCHES the agent having no tools list (which inherits every tool from the parent)")

    # ── r: install, and no forbidden side effect (#153's lesson: prove it in isolation) ───────────
    watched_home = os.path.expanduser("~/.claude")
    watched_repo = os.path.join(ROOT, ".claude")
    before_home = _tree(watched_home) if os.path.isdir(watched_home) else set()
    before_repo = _tree(watched_repo) if os.path.isdir(watched_repo) else set()
    home_existed, repo_existed = os.path.isdir(watched_home), os.path.isdir(watched_repo)

    tmp = tempfile.mkdtemp(prefix="dispatch_profile_selftest_")
    try:
        rc = _quietly(do_install, _Args(prefix=tmp))
        p = paths(tmp)
        installed = [v for v in p.values() if os.path.isfile(v)]
        ok("r1", rc == 0 and len(installed) == 4,
           "install writes exactly the 4 profile files into a throwaway prefix (%d found)"
           % len(installed))
        ok("r2", _quietly(do_verify, _Args(prefix=tmp)) == 0,
           "the INSTALLED profile verifies clean, read back from disk")
        ok("r2b", os.access(p["launcher"], os.X_OK), "the installed launcher is executable")
        try:
            _quietly(do_install, _Args(prefix=tmp))
            clobbered = True
        except Fault:
            clobbered = False
        ok("r3", not clobbered, "install REFUSES to overwrite an installed profile without --force")
        ok("r3b", _quietly(do_install, _Args(prefix=tmp, force=True)) == 0,
           "install --force replaces it")

        # ── e: THE ACCEPTANCE, end-to-end, driven off the INSTALLED files ─────────────────────────
        # Everything above tests documents. These two take what install actually wrote and USE it, so
        # they fail if the profile is well-formed but inert — which is the only failure mode that
        # matters to an operator.

        # e1 — "it has ONLY the dispatch toolset + read". Start the server the way the installed
        # mcp.json literally says (its own command + args), speak real MCP, and demand the served
        # tools are EXACTLY the mcp tools the installed agent allows — no more, no fewer. A
        # registration that is well-formed but serves a different set would pass every document check
        # here and give the dispatcher the wrong tools.
        served, agent_mcp, e1_note = None, None, ""
        try:
            spec = (json.load(open(p["mcp"]))["mcpServers"] or {})[dt.SERVER_NAME]
            reqs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
            proc = subprocess.run([spec["command"]] + list(spec["args"]),
                                  input="\n".join(json.dumps(r) for r in reqs) + "\n",
                                  capture_output=True, text=True, timeout=120)
            for line in proc.stdout.splitlines():
                if line.strip().startswith("{"):
                    o = json.loads(line)
                    if o.get("id") == 2 and "result" in o:
                        served = sorted(t["name"] for t in o["result"]["tools"])
            fm = _frontmatter(open(p["agent"]).read()) or {}
            got = _tool_list(fm.get("tools")) or []
            agent_mcp = sorted(t.split("__")[-1] for t in got if t.startswith("mcp__"))
            read_only = [t for t in got if not t.startswith("mcp__")]
            e1_note = ("; read-only tools: %s" % ", ".join(read_only)) if read_only == READ_TOOLS \
                else "; UNEXPECTED non-mcp tools: %s" % ", ".join(read_only)
        except Exception as ex:  # noqa: BLE001 — the server failing to speak IS the finding
            e1_note = "; the registered server did not answer (%s: %s)" % (type(ex).__name__, ex)
        ok("e1", served is not None and served == agent_mcp and e1_note.startswith("; read-only"),
           "the INSTALLED mcp.json starts a real MCP server that serves EXACTLY the tools the "
           "INSTALLED agent allows (served: %s)%s" % (", ".join(served or ["(none)"]), e1_note))

        # e2 — "refuses code edits". Take the PreToolUse hook command verbatim OUT of the installed
        # settings.json and run it with a real Write payload. This proves the composed profile refuses
        # a code edit — not merely that #210 can refuse one in its own selftest. The command string is
        # the thing that gets wired into the harness, so the command string is what gets run.
        denied, e2_note = False, ""
        try:
            doc = json.load(open(p["settings"]))
            cmd = doc["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write",
                                  "tool_input": {"file_path": "/tmp/dispatcher_should_not_write.py",
                                                 "content": "print('drift')"},
                                  "session_id": "selftest", "tool_use_id": "t1"})
            proc = subprocess.run(shlex.split(cmd), input=payload, capture_output=True, text=True,
                                  timeout=60)
            ans = json.loads(proc.stdout) if proc.stdout.strip() else {}
            decision = (ans.get("hookSpecificOutput") or {}).get("permissionDecision")
            denied = proc.returncode == 0 and decision == "deny"
            e2_note = "decision=%r" % decision
        except Exception as ex:  # noqa: BLE001
            e2_note = "the installed hook command did not answer (%s: %s)" % (type(ex).__name__, ex)
        ok("e2", denied,
           "the PreToolUse hook command taken VERBATIM from the INSTALLED settings.json DENIES a "
           "real Write payload — the profile refuses code edits (%s)" % e2_note)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    after_home = _tree(watched_home) if os.path.isdir(watched_home) else set()
    after_repo = _tree(watched_repo) if os.path.isdir(watched_repo) else set()

    # r4 — NOTHING HERE INSTALLS ONTO THIS MAC. Stated as what it means rather than as a tree diff.
    # ~/.claude is LIVE: every running Claude Code session writes its transcript, shell snapshots and
    # session json under it continuously, so demanding a byte-identical tree would make this check
    # fail on a busy machine for reasons that have nothing to do with this file — a flaky check is
    # worse than none, because it teaches its reader to ignore red. The claim being tested is narrow
    # and exact: selftest installs to a temp prefix, so NO profile file may exist at the real prefix,
    # and nothing profile-shaped may have appeared while it ran. Entries that appeared but are not
    # this profile's are reported, not failed on — they are other sessions doing their job.
    real = paths(DEFAULT_PREFIX)
    landed = [v for v in real.values() if os.path.exists(v)]
    new_here = sorted(set(after_home) - set(before_home))
    ours = [p for p in new_here if os.path.basename(p) in
            {os.path.basename(v) for v in real.values()} or PROFILE_DIRNAME in p.split(os.sep)]
    ok("r4", not landed and not ours,
       "nothing here installs onto this Mac: no profile file exists at the real prefix %s, and "
       "nothing profile-shaped appeared under it while this ran (%d unrelated entr%s appeared — "
       "other live Claude Code sessions write there continuously)%s"
       % (DEFAULT_PREFIX, len(new_here), "y" if len(new_here) == 1 else "ies",
          "" if not (landed or ours) else "; OURS: %s" % ", ".join(landed + ours)))
    # r5 — the repo's own .claude/ IS quiet (nothing else touches it), so it gets the strict tree diff.
    ok("r5", before_repo == after_repo and os.path.isdir(watched_repo) == repo_existed,
       "the repo's own .claude/ is byte-for-byte unchanged (before %d entries, after %d)"
       % (len(before_repo), len(after_repo)))
    pyc = os.path.join(TOOLS_DIR, "__pycache__")
    minted = [f for f in (os.listdir(pyc) if os.path.isdir(pyc) else [])
              if f.startswith(("install_dispatch_profile", "dispatch_toolset",
                               "capability_restriction", "pair_loop"))]
    ok("r6", not minted,
       "importing #209/#210/pair_loop minted no __pycache__ in the repo's tools/ "
       "(sys.dont_write_bytecode)%s" % ("" if not minted else "; FOUND: %s" % ", ".join(minted)))

    # ── p: the Claude Code semantics, re-derived from the installed binary ────────────────────────
    claude = cr.find_claude()
    if not claude:
        skip("p1", "no Claude Code binary found — the CLI/agent/hook semantics this profile relies on "
                   "are UNKNOWN on this machine (not disproven). Run `probe` where it is installed.")
    else:
        results = probe_binary(claude)
        missing = [c for found, c in results if not found]
        ok("p1", not missing,
           "all %d Claude Code semantics confirmed in %s%s"
           % (len(results), claude, "" if not missing else "; MISSING: %s" % "; ".join(missing)))

    # ── report ────────────────────────────────────────────────────────────────────────────────────
    for state, tag, msg in checks:
        print("%-4s %-4s %s" % (state, tag, msg))
    failed = [c for c in checks if c[0] == "FAIL"]
    skipped = [c for c in checks if c[0] == "SKIP"]
    print()
    print("%d checks: %d passed, %d failed, %d skipped"
          % (len(checks), len(checks) - len(failed) - len(skipped), len(failed), len(skipped)))
    if failed:
        print("selftest FAILED — the dispatch profile does not hold as written.")
        return 1
    print("selftest PASSED — the profile composes #209's real tools and #210's real deny floor; the "
          "anchor re-anchors every turn, the installed registration serves EXACTLY the dispatch "
          "toolset the installed agent allows, the installed hook DENIES a real Write (all executed "
          "here), and install touches nothing outside its prefix.")
    return 0


# ── cli ───────────────────────────────────────────────────────────────────────────────────────────
COMMANDS = {"profile": do_profile, "install": do_install, "verify": do_verify, "argv": do_argv,
            "gate": do_gate, "anchor-hook": do_anchor_hook, "probe": do_probe,
            "selftest": do_selftest}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="install_dispatch_profile.py",
        description="THE DISPATCH PROFILE (ticket #212): one command installs a dispatch mode for "
                    "this Mac's Claude Code, composed from #209's dispatch tool-set, #210's "
                    "capability floor and a role-anchor hook. `--agent dispatch` (or the installed "
                    "`dispatch-mode` launcher) selects it; plain `claude` is unchanged.",
        epilog="commands: " + ", ".join(sorted(COMMANDS)))
    ap.add_argument("command", nargs="?", help="one of: " + ", ".join(sorted(COMMANDS)))
    ap.add_argument("--prefix", help="install/verify/argv/profile: the profile root (default: %s)"
                                     % DEFAULT_PREFIX)
    ap.add_argument("--force", action="store_true", help="install: overwrite an installed profile")
    ap.add_argument("--anchor-module", metavar="PATH",
                    help="use #211's anchor module instead of the built-in one. It must export "
                         "anchor_text() -> str, or a non-empty ANCHOR_TEXT str.")
    ap.add_argument("--json", action="store_true",
                    help="profile: print the composed profile as bare JSON and nothing else")
    a = ap.parse_args(argv)

    if not a.command:
        ap.print_help()
        print()
        print("Nothing was run. Start with `profile` to see what would be installed, `gate` for the "
              "three gates' live status, or `selftest` to prove it.")
        return 2
    fn = COMMANDS.get(a.command)
    if not fn:
        print("install_dispatch_profile: unknown command %r — expected one of: %s"
              % (a.command, ", ".join(sorted(COMMANDS))))
        return 2
    return fn(a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as e:
        print("install_dispatch_profile: %s" % e)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(2)
    except Exception as e:  # noqa: BLE001 — note-for-claude: file a report, then fail on ONE line
        bug_report("main", e, "python3 %s %s" % (SELF, " ".join(sys.argv[1:])), e)
        print("install_dispatch_profile: unexpected failure (%s: %s) — a timestamped bug report was "
              "filed to the registry's bug_reports sink." % (type(e).__name__, e))
        sys.exit(2)
