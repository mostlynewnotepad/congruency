#!/usr/bin/env python3
"""capability_restriction.py — the DISPATCHER's capability floor: deny Write/Edit/code-authoring in
the PERMISSION LAYER, so the routing agent cannot author code even if it decides to try (ticket #210).

THE PROBLEM. `pair_loop.py --dispatch` spawns the routing agent dispatch-01 with

    claude -p <prompt> --allowedTools "Read,Grep,Glob"          (pair_loop.py:789, via spawn_claude
                                                                 at pair_loop.py:723-727)

and tells it, in prose, "You route; you never author work product" (DISPATCH_RULES,
pair_loop.py:753). Prose is discipline, not enforcement. `--allowedTools` does not help either: it is
an ALLOW-list that AUTO-APPROVES the names in it — it is not a deny-list, and it does not remove
Write/Edit from the process. Anything else falls through to the ordinary permission pipeline, where a
`Write` sitting in ANY settings file's `permissions.allow` (a user's own ~/.claude/settings.json is
enough), or a `defaultMode` of `acceptEdits`/`bypassPermissions`, silently re-grants exactly the
capability the prose forbids. This module closes that gap with a rule the harness itself enforces.

WHAT THIS FILE IS. The POLICY plus the two mechanisms that carry it, in one file:

  1. THE PERMISSION BLOCK — the `permissions` stanza (bare-name deny rules) that Claude Code's own
     permission engine enforces before it consults anything else. This is the load-bearing layer.
  2. THE HOOK — a `PreToolUse` hook whose command is THIS FILE (`capability_restriction.py hook`).
     It is an independent second layer that reads the tool call on stdin and answers `deny`.

It emits them (`block`, `settings`), installs them (`install`), IS the hook (`hook`), lets you fire a
single tool call at the policy and watch it refuse (`check`), audits a settings file against the
invariants that make it enforceable (`verify`), and proves the lot (`selftest`).

TERMS, defined at first use — this file is read by an auditor who never saw its author.

  * THE DISPATCHER (dispatch-01) is the routing agent: it reads the ticket queue and decides, per
    ticket, "run / skip / stop" (do_dispatch, pair_loop.py:770-835). It authors nothing. The WORKER
    is the agent a "run" decision spawns, in its own branch+worktree, and it MUST author — its tools
    are "Read,Grep,Glob,Write,Edit,Bash(python3:*),..." (FOCUS["build"]["worker_tools"],
    pair_loop.py:716). The two roles therefore need OPPOSITE file permissions, which is the entire
    design constraint here; see SCOPE below.
  * A PERMISSION RULE is a string in a settings file's `permissions.allow` / `.deny` / `.ask`. It is
    either a BARE tool name (`"Write"`) or a tool name with a pattern in parentheses
    (`"Bash(git *)"`). The distinction is not cosmetic — see THE BARE-NAME TRAP.
  * A BARE-NAME DENY RULE is the first thing Claude Code checks on every tool call, before the
    tool's own path checks, before `ask` rules, and before the permission MODE. It cannot be
    out-voted by an allow rule anywhere, because deny rules from every settings source are UNIONED
    and any match denies.
  * `--settings <file-or-json>` is the Claude Code flag that loads one more settings layer for ONE
    spawn. Rules from it get the source `flagSettings`.
  * THE DISPATCH-TOOLS MCP is `ticket_api_mcp.py --role dispatch` (ticket #178): an MCP server that
    registers ONLY the dispatch role's 5 routing tools (`ticket_queue`, `ticket_kind`,
    `ticket_assign`, `edge_record`, `ticket_progress` — PROFILES, ticket_api_mcp.py:364-376). None of
    them is a work-product sink. That module restricts by ABSENCE (the tool is not in the process);
    this module restricts by REFUSAL (the tool is present but the harness says no). They are
    complementary, and this file reads that module's real PROFILES table rather than restating it
    (see `dispatch_profile()`), so the two cannot drift apart silently.
  * DISPATCH(), in this repo, is not a tool the model calls: a "run" decision becomes a CHILD
    `pair_loop.py --ticket` PROCESS with its own branch and worktree (child_cmd, pair_loop.py:758-767;
    spawned at pair_loop.py:824). That is the "create-build-context -> hand to a tooled agent" path,
    and the dispatcher reaches it by RETURNING A PLAN, never by writing a file. Denying the authoring
    tools therefore removes the shortcut without touching the sanctioned route — which is precisely
    the ticket's "the same task succeeds only via dispatch()".

THE BARE-NAME TRAP — the single most important fact in this file, and the reason the deny block is
spelled the way it is. It would be natural to write `"deny": ["Write(**)"]` to mean "no writing
anywhere". That rule DOES NOTHING. Two independent confirmations from the shipped binary:

  * The tool-level rule matcher refuses any rule that carries a pattern: it returns false immediately
    when the rule has parenthesised content, so ONLY bare-name rules can deny a tool outright.
  * Claude Code's own settings VALIDATOR warns that a `Write(path)` / `NotebookEdit(path)` /
    `MultiEdit(path)` rule "is not matched by file permission checks — only Edit(path) rules are",
    and tells you to use `Edit(path)` because "Edit rules cover all file-editing tools".

So a parenthesised Write rule is matched by NOTHING: not by the tool-level matcher (it has a
pattern), and not by the file-path checks (those only consult `Edit(path)`). The rules below are
therefore BARE NAMES ONLY — the one spelling that is unconditionally enforced. `verify` FAILS a
settings file that regresses to the parenthesised form, and `selftest` mutation-tests that failure so
the check cannot rot into a rubber stamp.

WHY BASH IS DENIED WHOLE, not by prefix. The ticket says "deny code-writing Bash". There is no sound
prefix-enumeration of that: `Bash(python3:*)` still runs `python3 -c "open('x','w')..."`, and a shell
can author a file via `tee`, `>`, `sed -i`, `cp`, `heredoc`, `perl -pi`, or a compiler. Every such
list is a list of the tricks its author happened to think of. The dispatcher is granted no Bash at
all today (`--allowedTools "Read,Grep,Glob"`, pair_loop.py:789), so denying `Bash` outright costs it
nothing it has and is strictly stronger than any prefix set. One bare rule, no enumeration, no gaps.

WHY Agent/Task IS DENIED. A subagent is a capability laundry: an agent that cannot Write can ask a
subagent that can. `Task` is an alias of the canonical `Agent` in this build, so BOTH spellings are
denied — a rule naming the wrong one of an alias pair is a rule that silently never fires.

THE TWO LAYERS, and why the hook is second and not first. Claude Code combines a PreToolUse hook's
answer with the rules like this: a hook that says `deny` denies; a hook that says `allow` is then
STILL checked against the deny rules and the deny rule OVERRIDES it; a hook that says nothing falls
through to the rules. So the rules are the floor and the hook cannot lower it — a hook can only ever
add a refusal. That asymmetry is why the permission block is the primary mechanism and the hook is
defence in depth: hooks can be switched off wholesale by a `disableAllHooks` managed setting, and a
hook is a process that can fail; a deny rule is none of those things. Both are shipped because they
fail independently.

SCOPE — why this is a `--settings` file and NOT `.claude/settings.json`. A project settings file at
the repo root would be read by EVERY `claude` spawned with the repo as cwd, and worker worktrees are
checkouts of the same repo — so a committed `.claude/settings.json` denying Write would also break
the worker, whose whole job is to Write the deliverable (pair_loop.py:716). A user settings file is
worse: global. Role-scoping therefore requires a per-spawn layer, which is exactly `--settings`. Two
properties of that layer, both verified in the shipped binary, make it the right tool:

  * Rules loaded from `--settings` are READ-ONLY at runtime: removing a rule whose source is
    `flagSettings` raises "Cannot delete permission rules from read-only settings". The dispatcher
    cannot un-deny itself through `/permissions`.
  * `flagSettings` cannot be excluded by `--setting-sources`: the resolver ADDS `flagSettings` and
    `policySettings` to whatever source list it is handed. The layer cannot be dropped.

The default install path is <repo>/.claude/dispatcher-settings.json. That directory is gitignored
(.gitignore:34 — `.claude/`), so the file never enters a commit and never appears in a worker's
worktree; and the name is deliberately NOT `settings.json`, so nothing auto-loads it. It applies to
exactly one spawn: the one that passes `--settings`.

WIRING IT (the one change outside this file, which this file does not make — ticket #210's
deliverable is this module and it touches nothing else). `capability_restriction.py argv` prints the
exact spawn, and the one-line edit that installs the floor permanently is to pass the file through
`spawn_claude`'s argv at pair_loop.py:727, for the dispatch spawn at pair_loop.py:789. Until that
edit lands, `install` + `argv` give a dispatcher spawn that is restricted today, by hand.

WHAT THIS FILE DOES NOT CLAIM. It does not re-implement Claude Code's permission engine, and it does
NOT claim to have run `claude` — that binary is not among the runners this ticket's worker may
execute. What it PROVES by execution is the hook (`selftest` pipes real PreToolUse payloads into a
real subprocess of this file and reads the real decisions) and the policy document's invariants
(`verify`, mutation-tested). What it GROUNDS by reading is the rule semantics: every claim above
about the permission engine was read out of the installed Claude Code binary, and `probe` re-reads it
in front of you (see PROVENANCE).

PROVENANCE — how the claims above were established, and how to re-check them. They were read from the
installed Claude Code executable itself (v2.1.210 at the time of writing, resolved via
`~/.local/bin/claude`), which embeds its JavaScript. `python3 capability_restriction.py probe` finds
the current binary, greps it for the enforcement points, and prints what it found — so the claims are
re-derivable on the reader's machine rather than taken on trust. It exits 0 when the binary confirms
every one, 1 when it does not (they may have moved in that version — re-read them before trusting the
deny block), and 2 when no binary can be found at all (a missing binary makes them UNKNOWN here,
never "confirmed" and never "disproven"). `selftest` folds the same probe in as a SKIP-able check: it
is reported as SKIP, never as PASS, when the binary is absent.

Usage:
    python3 capability_restriction.py block          # the exact permission block + hook (annotated)
    python3 capability_restriction.py block --json   # ... the same, as bare JSON, nothing else
    python3 capability_restriction.py settings       # the complete dispatcher settings file, as JSON
    python3 capability_restriction.py argv           # the exact `claude` argv the dispatcher spawns with
    python3 capability_restriction.py install        # write the settings file (prints the path)
    python3 capability_restriction.py install --path P --force
    python3 capability_restriction.py verify         # audit the installed file against the invariants
    python3 capability_restriction.py verify --path P
    python3 capability_restriction.py check --tool Write --input '{"file_path":"/tmp/x","content":"y"}'
    python3 capability_restriction.py hook           # BE the PreToolUse hook: reads stdin, prints JSON
    python3 capability_restriction.py probe          # re-derive the rule semantics from the binary
    python3 capability_restriction.py selftest       # prove all of it; writes nothing into this repo

SIDE EFFECTS, stated exactly (ticket #153's lesson: a "creates no files" claim is checkable, so it
had better be true). `block`, `settings`, `argv`, `verify`, `check`, `hook` and `probe` CREATE NO
FILES and write nothing anywhere — not even a __pycache__ entry (see the bytecode note below).
`selftest` writes NOTHING INTO THIS REPO: it exercises `install` against a throwaway temp directory
outside the repo and removes it, and it proves the repo is untouched by listing <repo>/.claude before
and after (check r4). `install` is the only command that writes into the repo: exactly ONE file, and
it refuses to overwrite an existing one without --force. The ONE exception to all of the above is the
error path every tool in this repo shares: an UNEXPECTED exception appends a line to the registry's
`bug_reports` sink (logs/, gitignored), per note-for-claude. That is a crash report, not a side
effect of any command working as documented.

Exit codes (each prints ONE line on failure, never a traceback):
    0  the command did its job. For `check` and `hook`: the policy ANSWERED — read the printed
       decision, which is `deny` or a fall-through; a refusal is this tool working, not failing.
    1  a NEGATIVE ANSWER, not a malfunction. `verify`: the settings file does NOT hold the invariants
       (each one is named). `selftest`: at least one check FAILED. `probe`: the installed binary did
       NOT confirm every claim this module relies on (they may have moved in that version).
    2  a precondition or usage failure — an unreadable/unparseable settings file, a missing --tool,
       a bad --input, no Claude Code binary for `probe`, an unknown command or none at all, or
       (install) a file already there without --force.

Pure-python stdlib, one file — the repo is stdlib-only (DEPENDENCIES.md). Registry-gated per
note-for-claude: it walks UP to registry.json and refuses to run without it; any unexpected exception
files a timestamped Variant-A bug report to the registry's `bug_reports` sink.
"""
# NO BYTECODE CACHE — set before anything else imports. `block`/`verify`/`selftest` promise they
# create no files; importing this module as a module (as selftest's subprocesses do) would otherwise
# mint tools/__pycache__/capability_restriction.*.pyc in the repo tree and break that promise.
import sys

sys.dont_write_bytecode = True

import argparse
import json
import os
import re
import shlex
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
TOOLS = os.path.dirname(SELF)
DEFAULT_SETTINGS = os.path.join(ROOT, ".claude", "dispatcher-settings.json")
MCP_SERVER = "dispatch-tools"          # the --mcp-config key the dispatch MCP is registered under;
                                       # Claude Code names its tools mcp__<key>__<tool>


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
                "filename": "capability_restriction.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:],
                "note": "dispatcher capability restriction (ticket #210)",
            }) + "\n")
    except Exception:  # noqa: BLE001 — a failed report must never mask the failure it reports
        pass


class Fault(Exception):
    """A precondition/usage failure — reported as one line, exit 2."""


# ── THE POLICY ────────────────────────────────────────────────────────────────────────────────────
# Every entry is a BARE tool name. That is not a style choice: the tool-level rule matcher ignores
# any rule carrying a parenthesised pattern, so a bare name is the only spelling that denies a tool
# outright. See THE BARE-NAME TRAP in the module docstring. `verify` enforces this mechanically.
#
# Each name is paired with WHY it is denied, and the reason is printed to the model in the hook's
# refusal — a refusal that does not say what to do instead just gets retried.
DENIED = {
    "Write":        "creates or overwrites a file — the dispatcher authors nothing",
    "Edit":         "edits a file in place — the dispatcher authors nothing",
    "MultiEdit":    "edits files in place (legacy Edit variant) — the dispatcher authors nothing",
    "NotebookEdit": "edits notebook cells — code is code",
    "Bash":         "a shell can author a file in unbounded ways (tee, >, sed -i, python3 -c ...), "
                    "so it is denied whole rather than by an always-incomplete prefix list",
    "Task":         "a subagent could author on the dispatcher's behalf (alias of Agent)",
    "Agent":        "a subagent could author on the dispatcher's behalf",
}

# What the dispatcher KEEPS: read-only inspection + the dispatch-tools MCP, and nothing else.
# "Read,Grep,Glob" is exactly what pair_loop.py:789 grants dispatch-01 today; this changes none of
# it. The MCP glob is the one wildcard form allowed in an ALLOW rule — Claude Code's validator
# rejects a wildcard tool name in an allow rule unless it follows a literal `mcp__<server>__` prefix.
ALLOWED = ["Read", "Grep", "Glob", "mcp__%s__*" % MCP_SERVER]

# The hook fires for exactly the denied set. This is a REGEX matcher, deliberately: a plain
# alternation ("Write|Edit|...") is compared by exact membership AFTER alias-normalising each token,
# so a tool invoked under an alias could slip past it. A pattern containing regex metacharacters is
# instead compiled and tested against the tool name AND against that name's aliases, which is
# strictly the more robust of the two paths. It is anchored so `Edit` cannot match `NotebookEdit` by
# accident. The hook re-checks the name itself regardless — the matcher is only a prefilter.
HOOK_MATCHER = "^(%s)$" % "|".join(sorted(DENIED))

# Alias -> canonical tool name, mirroring the alias table in the shipped Claude Code binary. Only the
# pairs that matter here are listed. The hook normalises through this before deciding, so a call that
# arrives under either spelling is judged the same.
ALIASES = {"Task": "Agent"}

HOOK_TIMEOUT = 10          # seconds; this hook parses one JSON object and prints one, so 10s is ample
REFUSAL_HEADLINE = ("DISPATCHER CAPABILITY RESTRICTION (ticket #210): %s is denied for the dispatcher "
                    "role — %s.")
REFUSAL_REMEDY = (" You route; you never author work product. Do not try another tool: the deny rule "
                  "is enforced by the harness for every authoring tool, not just this one. Return "
                  "your routing plan as JSON instead — a ticket you decide to \"run\" is dispatched to "
                  "a worker that has the file tools you do not.")


def canonical(tool_name):
    """The canonical name of a tool, resolving the alias pair (Task -> Agent).

    A rule or a check that names the wrong half of an alias pair silently never fires, which is a
    capability restriction that quietly restricts nothing. Both halves are denied AND every decision
    normalises, so either spelling lands on the same answer."""
    return ALIASES.get(tool_name, tool_name)


def allowing_rule(tool_name):
    """The allow rule in this policy that covers `tool_name`, or None.

    Only the two rule FORMS this policy actually emits are understood, matched the way Claude Code
    matches them: a bare name matches that tool exactly (aliases normalised), and an
    `mcp__<server>__*` rule matches any tool of that server — the one wildcard form the settings
    validator permits in an allow rule. This is a reader's aid, not the permission engine: it answers
    "which of MY rules covers this?", never "will the harness allow it?" (the host's own settings can
    carry rules this file has never seen). `check` says so in as many words."""
    if not isinstance(tool_name, str) or not tool_name:
        return None
    for rule in ALLOWED:
        if rule.endswith("__*"):
            if tool_name.startswith(rule[:-1]):
                return rule
        elif canonical(rule) == canonical(tool_name):
            return rule
    return None


def is_denied(tool_name):
    """The policy, as one predicate: (denied?, why). The hook and `check` share it, so the thing
    `check` demonstrates is the thing the hook does — not a paraphrase of it."""
    if not isinstance(tool_name, str) or not tool_name:
        return False, ""
    for name in (tool_name, canonical(tool_name)):
        if name in DENIED:
            return True, DENIED[name]
    return False, ""


# ── the artifacts: the permission block, the hook, the whole settings file ────────────────────────
def hook_command(self_path=SELF, python=None):
    """The shell command Claude Code runs for the hook: this file, in `hook` mode, by absolute path.

    Absolute, because a hook runs with the project directory as cwd and this file lives under
    checkouts/current/congruency/tools; and shell-quoted, because the command string is handed to a
    shell and a path with a space would otherwise split into two arguments."""
    return "%s %s hook" % (shlex.quote(python or sys.executable), shlex.quote(self_path))


def permission_block():
    """The `permissions` stanza — the load-bearing layer. Bare names only (THE BARE-NAME TRAP)."""
    return {
        "permissions": {
            # Checked before the tool's own path checks, before `ask` rules, and before the
            # permission mode; unioned across every settings source, so no allow rule anywhere —
            # and no `--dangerously-skip-permissions` — can out-vote it.
            "deny": sorted(DENIED),
            "allow": list(ALLOWED),
            "ask": [],
            "defaultMode": "default",
            # Belt and braces: even though a deny rule already survives bypassPermissions, refuse the
            # mode outright so nothing can quietly widen everything else the dispatcher touches.
            "disableBypassPermissionsMode": "disable",
            "additionalDirectories": [],
        }
    }


def hook_block(self_path=SELF, python=None):
    """The `hooks` stanza — the independent second layer (see THE TWO LAYERS)."""
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": HOOK_MATCHER,
                    "hooks": [{
                        "type": "command",
                        "command": hook_command(self_path, python),
                        "timeout": HOOK_TIMEOUT,
                    }],
                }
            ]
        }
    }


def settings_document(self_path=SELF, python=None):
    """The complete dispatcher settings file: the permission block + the hook, and nothing else.

    Nothing else on purpose — this file is loaded with `--settings` as an extra layer over whatever
    the host already has, so every key it names is a key it means to control."""
    doc = {}
    doc.update(permission_block())
    doc.update(hook_block(self_path, python))
    return doc


def spawn_argv(settings_path=DEFAULT_SETTINGS, prompt="<the dispatch-01 prompt + THE QUEUE + DISPATCH_RULES>"):
    """The exact `claude` argv a restricted dispatcher spawn is, next to the one pair_loop runs today.

    This is `spawn_claude`'s argv (pair_loop.py:727) plus `--settings`. `--allowedTools` stays: it
    still auto-approves the read-only three so the dispatcher is not prompted for them. What it never
    did, and what the settings file now does, is DENY the rest."""
    return ["claude", "-p", prompt, "--allowedTools", "Read,Grep,Glob", "--settings", settings_path]


# ── the dispatch surface, read from ticket #178's real profile table ──────────────────────────────
def dispatch_profile(path=None):
    """The dispatch role's tool names, read out of ticket_api_mcp.py's real PROFILES table.

    Read, not restated: the allow rule below hands the dispatcher `mcp__dispatch-tools__*`, and the
    thing that makes that safe is that the dispatch profile contains no authoring tool. If this file
    hard-coded its own copy of that list, #178 could grow a writer tomorrow and this file would go on
    claiming the surface was safe. So the table is parsed from the source of truth on every run.

    Parsed with `ast`, never imported: importing that module would run its registry gate and pull in
    urllib for a question that is answerable from the source text. Returns (profile, authoring,
    source_path), or (None, None, path) when the module is not present — a caller must treat that as
    UNKNOWN, never as "safe"."""
    import ast
    path = path or os.path.join(TOOLS, "ticket_api_mcp.py")
    if not os.path.isfile(path):
        return None, None, path
    try:
        tree = ast.parse(open(path).read(), filename=path)
    except (SyntaxError, OSError):
        return None, None, path
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in ("PROFILES", "AUTHORING_TOOLS"):
                try:
                    found[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    profiles = found.get("PROFILES")
    authoring = found.get("AUTHORING_TOOLS")
    if not isinstance(profiles, dict) or "dispatch" not in profiles:
        return None, None, path
    return list(profiles["dispatch"]), (set(authoring) if authoring else set()), path


# ── the hook ──────────────────────────────────────────────────────────────────────────────────────
def hook_decision(payload):
    """The hook's answer for one PreToolUse payload. Returns (decision_dict_or_None, exit_code).

    A `None` decision means SAY NOTHING: the tool is not the dispatcher's to be refused here, so the
    hook stays silent and the call falls through to the permission rules, which are the floor. A hook
    that answered "allow" here would be worse than useless — it would be claiming an authority it
    does not have (the deny rules override a hook's allow anyway), and it would auto-approve tools
    this policy never considered.

    FAIL CLOSED. A payload that is not an object, or that carries no usable `tool_name`, is DENIED.
    The hook cannot identify what it is being asked about, and a security control that guesses
    "probably fine" when it cannot see is not a control. This costs nothing in practice — Claude Code
    always sends `{"hook_event_name": "PreToolUse", "tool_name": ..., "tool_input": {...}}` — and the
    refusal names the cause, so the failure is loud rather than silent."""
    if not isinstance(payload, dict):
        return _deny("(unreadable)", "the PreToolUse payload was not a JSON object, so the tool being "
                                     "requested could not be identified; this hook fails closed"), 0
    tool = payload.get("tool_name")
    if not isinstance(tool, str) or not tool:
        return _deny("(unnamed)", "the PreToolUse payload carried no usable `tool_name`, so the tool "
                                  "being requested could not be identified; this hook fails closed"), 0
    denied, why = is_denied(tool)
    if not denied:
        return None, 0
    return _deny(tool, why), 0


def _deny(tool, why):
    """A PreToolUse deny, in the shape Claude Code reads: the decision lives under `hookSpecificOutput`
    with the event name echoed back. (`decision: "block"` is the deprecated spelling for PreToolUse;
    `hookSpecificOutput.permissionDecision` is the current one.)"""
    reason = (REFUSAL_HEADLINE % (tool, why)) + REFUSAL_REMEDY
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "systemMessage": "capability_restriction (#210): denied %s for the dispatcher role." % tool,
    }


def do_hook(_a):
    """PreToolUse hook mode: one JSON object in on stdin, at most one JSON object out on stdout.

    Always exits 0. A non-zero exit or a stderr splat would be read as a hook BLOCKING ERROR, which
    denies the call too — but by way of an error, which would make a routine Read look like a broken
    hook. Speaking the protocol explicitly keeps "denied on purpose" distinguishable from "crashed"."""
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else None
    except ValueError:
        payload = None          # unparseable -> hook_decision fails closed and says why
    decision, code = hook_decision(payload)
    if decision is not None:
        sys.stdout.write(json.dumps(decision) + "\n")
    return code


def do_check(a):
    """Fire one tool call at the policy and print the answer, in English then as the hook's own JSON.

    This runs `hook_decision` — the very function the hook runs — so what you see here is what the
    hook does, not a description of it. `--input` is optional: the decision turns on the tool NAME,
    which is the point (a deny that depended on the arguments could be argued around)."""
    if not a.tool:
        raise Fault("check needs --tool NAME (e.g. --tool Write)")
    try:
        tool_input = json.loads(a.input) if a.input else {}
    except ValueError as e:
        raise Fault("--input is not valid JSON (%s)" % e)
    if not isinstance(tool_input, dict):
        raise Fault("--input must be a JSON object, got %s" % type(tool_input).__name__)
    payload = {"hook_event_name": "PreToolUse", "tool_name": a.tool, "tool_input": tool_input,
               "session_id": "capability-restriction-check", "tool_use_id": "check"}
    decision, _ = hook_decision(payload)
    if decision is None:
        rule = allowing_rule(a.tool)
        print("ALLOW  %s — not an authoring tool; this hook says nothing and the call falls through "
              "to the permission rules." % a.tool)
        if rule:
            print("       This policy's allow rule %r covers it, so the dispatcher keeps it." % rule)
        else:
            print("       No allow rule in this policy covers it (%s), so it is not auto-approved "
                  "here; whether it runs is up to the host's own settings. This policy neither "
                  "grants nor denies it." % ", ".join(ALLOWED))
        print(json.dumps({"decision": "fall-through", "tool": a.tool,
                          "allowed_by": rule}, indent=2))
        return 0
    print("DENY   %s" % a.tool)
    print("       %s" % decision["hookSpecificOutput"]["permissionDecisionReason"])
    print(json.dumps(decision, indent=2))
    return 0


# ── emitting ──────────────────────────────────────────────────────────────────────────────────────
def do_block(a):
    """Print the exact settings.json permission block + hook — the ticket's literal deliverable."""
    doc = settings_document()
    if a.json:
        print(json.dumps(doc, indent=2))
        return 0
    print("THE EXACT settings.json BLOCK for the DISPATCHER role (ticket #210)")
    print("=" * 78)
    print(json.dumps(doc, indent=2))
    print()
    print("WHERE IT GOES: %s" % DEFAULT_SETTINGS)
    print("  Loaded for ONE spawn with `--settings <that path>`, NOT as .claude/settings.json —")
    print("  a project settings file is read by every claude spawned in this repo, and the WORKER")
    print("  (which runs in a worktree of this same repo) must keep Write/Edit to do its job")
    print("  (pair_loop.py:716). Role-scoping requires a per-spawn layer.")
    print()
    print("WHY THE DENY LIST IS BARE NAMES: a rule with parentheses — `Write(**)` — is matched by")
    print("  NOTHING. The tool-level matcher skips any rule carrying a pattern, and the file-path")
    print("  checks only ever consult `Edit(path)` rules. Claude Code's own settings validator says")
    print("  so in as many words. A bare name is the one spelling that denies a tool outright.")
    print()
    for name in sorted(DENIED):
        print("  deny  %-13s %s" % (name, DENIED[name]))
    print()
    for name in ALLOWED:
        print("  allow %-13s %s" % (name, "the dispatch-tools MCP (ticket #178): the 5 routing tools, "
                                           "no work-product sink" if name.startswith("mcp__")
                                     else "read-only inspection (exactly what pair_loop.py:789 grants today)"))
    print()
    print("THE HOOK is this file: `%s`" % hook_command())
    print("  It is the SECOND layer, not the first. A hook that says deny denies; a hook that says")
    print("  allow is still overridden by a deny rule. So the rules are the floor and the hook can")
    print("  only ever add a refusal — which is why both ship: they fail independently.")
    print()
    print("SPAWN IT:  %s" % " ".join(shlex.quote(x) for x in spawn_argv()))
    return 0


def do_settings(_a):
    """The complete settings file as JSON on stdout — pipe it, diff it, install it by hand."""
    print(json.dumps(settings_document(), indent=2))
    return 0


def do_argv(a):
    """The exact `claude` argv for a restricted dispatcher spawn, and the wiring that makes it stick."""
    path = a.path or DEFAULT_SETTINGS
    print("TODAY (pair_loop.py:789 -> spawn_claude, pair_loop.py:727) — the dispatcher spawn:")
    print("  " + " ".join(shlex.quote(x) for x in
                          ["claude", "-p", "<prompt>", "--allowedTools", "Read,Grep,Glob"]))
    print("  `--allowedTools` AUTO-APPROVES those three. It denies nothing: Write and Edit are still")
    print("  in the process, and any `Write` in any settings file's permissions.allow re-grants them.")
    print()
    print("RESTRICTED — the same spawn with the capability floor:")
    print("  " + " ".join(shlex.quote(x) for x in spawn_argv(path)))
    print()
    print("MAKE IT PERMANENT (one line, in pair_loop.py — NOT changed by this ticket, whose")
    print("deliverable is this module alone). spawn_claude builds its argv at pair_loop.py:727:")
    print()
    print('    r = subprocess.run(["claude", "-p", prompt, "--allowedTools", allowed_tools],')
    print()
    print('Give spawn_claude a `settings=None` keyword, append `+ (["--settings", settings] if')
    print("settings else [])` to that argv, and pass settings=%r from the dispatch spawn at" % path)
    print("pair_loop.py:789 (and ONLY there — the worker and auditor spawns must not get it).")
    print()
    print("Check it is installed first:  python3 %s verify" % shlex.quote(SELF))
    if not os.path.isfile(path):
        print()
        print("NOTE: %s does not exist yet — run `install` first, or the spawn will fail with" % path)
        print("      'Error: Settings file not found'.")
    return 0


def do_install(a):
    """Write the dispatcher settings file. The ONLY command in this module that writes anything.

    Writes exactly ONE file and refuses to clobber: an existing file is left alone unless --force,
    because a settings file is a security control and silently replacing one somebody tuned is how a
    control quietly stops matching what its owner thinks it says."""
    path = a.path or DEFAULT_SETTINGS
    if os.path.exists(path) and not a.force:
        raise Fault("%s already exists — refusing to overwrite it. Inspect it with `verify --path %s`, "
                    "or pass --force to replace it." % (path, path))
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(json.dumps(settings_document(), indent=2) + "\n")
    print("installed: %s" % path)
    print("  denies : %s" % ", ".join(sorted(DENIED)))
    print("  allows : %s" % ", ".join(ALLOWED))
    print("  hook   : %s" % hook_command())
    print("  spawn  : %s" % " ".join(shlex.quote(x) for x in spawn_argv(path)))
    print("  verify : python3 %s verify --path %s" % (shlex.quote(SELF), shlex.quote(path)))
    if parent and os.path.basename(parent) == ".claude" and os.path.basename(path) == "settings.json":
        print("  WARNING: this file is named settings.json inside .claude/ — it will be auto-loaded for")
        print("           EVERY claude run in this project, including the WORKER, whose job is to Write.")
    return 0


# ── verifying ─────────────────────────────────────────────────────────────────────────────────────
def verify_document(doc, self_path=SELF):
    """Audit a settings document against the invariants that make it ENFORCEABLE. Returns [failures].

    This is not a schema check — it is the list of ways a plausible-looking permission block silently
    restricts nothing. Each invariant is here because getting it wrong produces a file that reads
    correctly and denies nothing, which is the worst possible outcome for a security control.
    `selftest` mutation-tests every one of them: it breaks the document in exactly that way and
    asserts this function catches it, so the checks cannot rot into a rubber stamp."""
    bad = []
    if not isinstance(doc, dict):
        return ["the settings document is not a JSON object"]
    perms = doc.get("permissions")
    if not isinstance(perms, dict):
        return ["no `permissions` object — the block is missing entirely"]
    deny = perms.get("deny")
    allow = perms.get("allow")
    if not isinstance(deny, list):
        return ["`permissions.deny` is missing or not a list — nothing is denied"]
    if not isinstance(allow, list):
        bad.append("`permissions.allow` is missing or not a list")
        allow = []

    # i1 — every authoring tool is denied. A name missing here is a capability handed back.
    for name in sorted(DENIED):
        if name not in deny:
            bad.append("`%s` is not in permissions.deny — the dispatcher could still use it (%s)"
                       % (name, DENIED[name]))

    # i2 — every deny rule is a BARE name. THE BARE-NAME TRAP: the tool-level matcher skips any rule
    # carrying a parenthesised pattern, so a patterned rule can never deny the TOOL. What such a rule
    # does beyond that differs per tool, and saying so precisely matters — a reader told "this denies
    # nothing" about a rule that does something would rightly stop believing the rest of this output.
    for rule in deny:
        if not isinstance(rule, str):
            bad.append("permissions.deny contains a non-string rule (%r)" % (rule,))
            continue
        if "(" in rule or ")" in rule:
            head = rule.split("(")[0]
            if head in ("Write", "NotebookEdit", "MultiEdit"):
                extra = ("and it is matched by NOTHING ELSE either: the file-path checks only ever "
                         "consult `Edit(path)` rules, which is what Claude Code's own settings "
                         "validator warns about. This rule is inert")
            elif head == "Edit":
                extra = ("the file-path checks WOULD honour it for the paths it names — but this "
                         "policy needs the tool denied WHOLE, not one path glob, and a glob is a "
                         "list of the paths its author thought of")
            elif head == "Bash":
                extra = ("the Bash matcher WOULD honour it for that command prefix — but a shell "
                         "authors files in unbounded ways, so only the whole-tool deny is sound")
            else:
                extra = "so it does not deny the tool"
            bad.append("deny rule %r carries a pattern, so the tool-level matcher skips it and the "
                       "TOOL is not denied — %s. Use the bare name %r." % (rule, extra, head))

    # i3 — nothing in the authoring set is also allowed. A deny rule wins regardless, so this is not
    # a hole; it is a contradiction, and a settings file that contradicts itself will be "fixed" by
    # the next reader in whichever direction they guess.
    for rule in allow:
        if isinstance(rule, str) and is_denied(rule.split("(")[0])[0]:
            bad.append("permissions.allow contains %r, which this policy denies — the deny wins, but "
                       "the file contradicts itself and invites someone to resolve it the wrong way."
                       % rule)

    # i4 — an allow rule may only use a wildcard tool name behind a literal mcp__<server>__ prefix;
    # Claude Code's settings validator rejects any other wildcard in an allow rule, and a rejected
    # rule is a rule that is not there.
    for rule in allow:
        if not isinstance(rule, str):
            bad.append("permissions.allow contains a non-string rule (%r)" % (rule,))
            continue
        head = rule.split("(")[0]
        if "*" in head and not re.match(r"^mcp__[^_*][^*]*__", head):
            bad.append("allow rule %r uses a wildcard tool name outside the `mcp__<server>__*` form; "
                       "the settings validator rejects it, so it would grant nothing." % rule)

    # i5 — bypassPermissions is refused outright. A bare deny rule already survives that mode, so
    # this is belt and braces, not the mechanism.
    if perms.get("disableBypassPermissionsMode") != "disable":
        bad.append("permissions.disableBypassPermissionsMode is not \"disable\" — the deny rules still "
                   "hold under bypassPermissions, but every other guard in the session would drop.")

    # i6 — the hook is wired, fires for every denied tool, and points at a file that exists.
    hooks = (doc.get("hooks") or {}).get("PreToolUse")
    if not isinstance(hooks, list) or not hooks:
        bad.append("no `hooks.PreToolUse` — the second layer is missing (the deny rules still hold)")
    else:
        covered, cmds = set(), []
        for group in hooks:
            if not isinstance(group, dict):
                continue
            matcher = group.get("matcher") or "*"
            for name in DENIED:
                if _matcher_hits(matcher, name):
                    covered.add(name)
            for h in group.get("hooks") or []:
                if isinstance(h, dict) and h.get("type") == "command" and h.get("command"):
                    cmds.append(h["command"])
        for name in sorted(set(DENIED) - covered):
            bad.append("the PreToolUse hook matcher does not fire for `%s` — that tool is denied by "
                       "the rules but has no second layer." % name)
        if not cmds:
            bad.append("`hooks.PreToolUse` has no command hook — the matcher fires nothing")
        for cmd in cmds:
            target = _hook_target(cmd)
            if target and not os.path.isfile(target):
                bad.append("the hook command points at %r, which does not exist — the hook would fail "
                           "on every call. (Re-run `install` to rewrite it with the correct path.)"
                           % target)
    return bad


def _matcher_hits(matcher, tool):
    """Does this hook matcher fire for this tool name?

    Mirrors the two paths Claude Code uses, in the same order and for the same reason: a matcher that
    is a plain alternation of names is compared by EXACT membership after alias-normalising each
    token; anything containing a regex metacharacter is compiled and tested against the tool name and
    against that name's aliases. `verify` must judge the matcher the way the harness will, or it
    would bless a matcher that never fires."""
    if not matcher or matcher == "*":
        return True
    if re.match(r"^[A-Za-z0-9_|]+$", matcher):
        return tool in {canonical(t.strip()) for t in matcher.split("|") if t.strip()} \
            or tool in {t.strip() for t in matcher.split("|") if t.strip()}
    try:
        rx = re.compile(matcher)
    except re.error:
        return False
    names = {tool, canonical(tool)} | {a for a, c in ALIASES.items() if c == tool}
    return any(rx.search(n) for n in names)


def _hook_target(cmd):
    """The script path a hook command runs, if it names one we can check. Best-effort: a command we
    cannot parse is not reported as broken, because a false "your hook is broken" is worse than
    silence — it sends the reader to fix something that works."""
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return None
    for part in parts:
        if part.endswith(".py"):
            return part
    return None


def do_verify(a):
    """Audit an installed settings file. Exit 0 if it holds, 1 if it does not, 2 if it cannot be read."""
    path = a.path or DEFAULT_SETTINGS
    if not os.path.isfile(path):
        raise Fault("no settings file at %s — run `install` first (or pass --path)" % path)
    try:
        doc = json.load(open(path))
    except ValueError as e:
        raise Fault("%s is not valid JSON (%s)" % (path, e))
    bad = verify_document(doc)
    if bad:
        print("FAIL %s — %d problem(s):" % (path, len(bad)))
        for b in bad:
            print("  - %s" % b)
        return 1
    print("OK   %s" % path)
    print("     denies %s" % ", ".join(sorted(DENIED)))
    print("     allows %s" % ", ".join(ALLOWED))
    print("     every deny rule is a bare name (the only spelling the tool-level matcher honours),")
    print("     the PreToolUse hook fires for every denied tool, and its command exists.")
    prof, authoring, prof_path = dispatch_profile()
    if prof is None:
        print("     dispatch surface: UNKNOWN — %s is not readable, so `mcp__%s__*` could not be"
              % (prof_path, MCP_SERVER))
        print("     cross-checked against the real dispatch profile.")
    else:
        overlap = sorted(set(prof) & set(authoring or ()))
        if overlap:
            print("FAIL the allowed dispatch surface contains authoring tool(s): %s" % ", ".join(overlap))
            return 1
        print("     dispatch surface: %s (from %s) — no authoring tool among them, so allowing"
              % (", ".join(prof), os.path.relpath(prof_path, ROOT)))
        print("     `mcp__%s__*` grants routing only." % MCP_SERVER)
    return 0


# ── probe: re-derive the rule semantics from the installed binary ─────────────────────────────────
# Each claim this module makes about Claude Code's permission engine, paired with a byte string that
# is present in the shipped binary if and only if the claim's code path is there. These are read, not
# executed: the `claude` binary is not among the runners this ticket's worker may run.
PROBES = [
    (b"is not matched by file permission checks",
     "THE BARE-NAME TRAP: the settings validator itself warns that a Write(path)/NotebookEdit(path) "
     "rule is not matched by the file permission checks — only Edit(path) is."),
    (b"Cannot delete permission rules from read-only settings",
     "--settings rules are READ-ONLY at runtime: the dispatcher cannot delete them via /permissions."),
    (b"but deny rule overrides",
     "A deny rule OVERRIDES a PreToolUse hook that answered `allow` — the rules are the floor."),
    (b"auto-approves every tool call (except explicit deny rules)",
     "bypassPermissions auto-approves everything EXCEPT explicit deny rules — the deny survives it."),
    (b"Bare allowedTools entries auto-approve the whole tool",
     "--allowedTools AUTO-APPROVES; it is not a deny-list. This is the gap ticket #210 closes."),
    (b"permissionDecision",
     "The PreToolUse hook protocol: hookSpecificOutput.permissionDecision is the current spelling."),
]


def find_claude():
    """The installed Claude Code executable, or None. Resolves the launcher through any symlink,
    since the name on PATH is usually a link into a versioned install directory."""
    for cand in (os.environ.get("CLAUDE_BIN"),
                 os.path.expanduser("~/.local/bin/claude"),
                 "/usr/local/bin/claude", "/opt/homebrew/bin/claude"):
        if cand and os.path.exists(cand):
            return os.path.realpath(cand)
    for d in (os.environ.get("PATH") or "").split(os.pathsep):
        p = os.path.join(d, "claude")
        if os.path.isfile(p):
            return os.path.realpath(p)
    return None


def probe_binary(path):
    """Grep the binary for each enforcement point. Returns [(found?, claim)]. Reads in chunks with an
    overlap, so a needle straddling a chunk boundary is still found and a 240MB binary never has to
    be held in memory at once."""
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
    """Re-derive this module's claims about the permission engine from the installed binary."""
    path = find_claude()
    if not path:
        raise Fault("no Claude Code binary found (looked at $CLAUDE_BIN, ~/.local/bin/claude, and "
                    "$PATH) — the claims in this module's docstring cannot be re-derived here. They "
                    "are UNKNOWN on this machine, not disproven.")
    print("probing: %s" % path)
    results = probe_binary(path)
    for ok, claim in results:
        print("  %s %s" % ("CONFIRMED" if ok else "NOT FOUND", claim))
    missing = [c for ok, c in results if not ok]
    if missing:
        print()
        print("%d claim(s) could not be confirmed against this binary. The enforcement points this "
              "module relies on may have moved or changed in this Claude Code version — re-read them "
              "before trusting the deny block." % len(missing))
        return 1
    print()
    print("all %d enforcement points confirmed in the installed binary." % len(results))
    return 0


# ── selftest ──────────────────────────────────────────────────────────────────────────────────────
def _run_hook(payload_text):
    """Run the REAL hook, as Claude Code runs it: a subprocess of this file in `hook` mode, the
    payload on stdin, the decision on stdout.

    A subprocess and not a function call, deliberately. The thing that has to work is the COMMAND in
    the settings file; calling hook_decision() in-process would prove the logic while leaving the
    argv, the stdin plumbing and the exit code — every part that is actually wired into the harness —
    untested. Returns (exit_code, parsed_stdout_or_None, stderr)."""
    p = subprocess.run([sys.executable, SELF, "hook"], input=payload_text,
                       capture_output=True, text=True, timeout=30)
    out = None
    if p.stdout.strip():
        try:
            out = json.loads(p.stdout)
        except ValueError:
            out = {"__unparseable__": p.stdout}
    return p.returncode, out, p.stderr


def _is_deny(out):
    return bool(out) and (out.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"


def _payload(tool, tool_input=None):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                       "tool_input": tool_input or {}, "session_id": "selftest", "tool_use_id": "t1"})


def _quietly(fn, *args):
    """Call fn with stdout muted, returning its value. Used only to keep a fixture's narration out of
    selftest's PASS/FAIL column; exceptions propagate untouched."""
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args)


def _tree(root):
    """Every path under root, for the before/after side-effect proof (ticket #153's lesson)."""
    seen = set()
    for dirpath, dirnames, filenames in os.walk(root):
        for n in list(dirnames) + filenames:
            seen.add(os.path.join(dirpath, n))
    return seen


def do_selftest(_a):
    """Prove the deliverable. Prints one PASS/FAIL/SKIP line per check; exits 0 only if none FAILED.

    WHAT IS PROVEN BY EXECUTION vs BY READING — say it plainly, because the difference is the honest
    limit of this file. The HOOK is executed for real (h1-h9: real subprocesses of this file, real
    PreToolUse payloads, real decisions read back). The POLICY DOCUMENT's invariants are executed for
    real, and mutation-tested (v1-v7: each check is shown to FAIL a document broken in exactly the
    way it exists to catch — a check that never fails is not a check). The PERMISSION ENGINE itself is
    not executed: `claude` is not among the runners this ticket's worker may run, so its behaviour is
    established by reading the shipped binary, which p1 re-does here and reports as SKIP — never as
    PASS — when no binary can be found.

    Writes NOTHING into this repo: `install` is exercised against a throwaway temp directory, and
    r1 lists the repo's own .claude/ before and after to prove it."""
    checks = []

    def ok(tag, cond, msg):
        checks.append((("PASS" if cond else "FAIL"), tag, msg))
        return cond

    def skip(tag, msg):
        checks.append(("SKIP", tag, msg))

    # ── h: THE HOOK, executed for real ────────────────────────────────────────────────────────────
    # h1-h5: the ticket's acceptance, first half — "the dispatcher attempting a Write/Edit is refused".
    for i, (tool, inp) in enumerate([
            ("Write", {"file_path": "/tmp/dispatcher_should_not_write.py", "content": "print('hi')"}),
            ("Edit", {"file_path": "/tmp/x.py", "old_string": "a", "new_string": "b"}),
            ("NotebookEdit", {"notebook_path": "/tmp/x.ipynb", "new_source": "print(1)"}),
            ("Bash", {"command": "python3 -c \"open('/tmp/x.py','w').write('code')\""}),
            ("Agent", {"subagent_type": "general-purpose", "prompt": "write the file for me"})], 1):
        rc, out, err = _run_hook(_payload(tool, inp))
        ok("h%d" % i, rc == 0 and _is_deny(out),
           "the real hook DENIES %s (exit %s, decision %r)"
           % (tool, rc, (out or {}).get("hookSpecificOutput", {}).get("permissionDecision")))

    # h6: the alias half of the pair. `Task` is `Agent` under another name; a policy that denied only
    # one spelling would be trivially side-stepped by using the other.
    rc, out, _ = _run_hook(_payload("Task", {"subagent_type": "general-purpose", "prompt": "write it"}))
    ok("h6", rc == 0 and _is_deny(out), "the real hook DENIES Task (the alias of Agent)")

    # h7: the refusal names the sanctioned route. A refusal that does not say what to do instead is a
    # refusal that gets retried until the budget runs out.
    rc, out, _ = _run_hook(_payload("Write", {"file_path": "/tmp/x", "content": "y"}))
    reason = (out or {}).get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
    ok("h7", "routing plan" in reason and "worker" in reason,
       "the refusal tells the dispatcher what to do instead (return a routing plan; the worker authors)")

    # h8: the second half of the acceptance — "the same task succeeds only via dispatch()". The tools
    # the dispatcher routes WITH must not be caught by the restriction, or the cure kills the patient.
    fell_through = []
    for tool in ["Read", "Grep", "Glob",
                 "mcp__%s__ticket_queue" % MCP_SERVER, "mcp__%s__ticket_kind" % MCP_SERVER,
                 "mcp__%s__ticket_assign" % MCP_SERVER, "mcp__%s__edge_record" % MCP_SERVER,
                 "mcp__%s__ticket_progress" % MCP_SERVER]:
        rc, out, _ = _run_hook(_payload(tool, {}))
        fell_through.append(rc == 0 and out is None)
    ok("h8", all(fell_through),
       "the real hook stays SILENT for the routing surface (Read/Grep/Glob + the 5 dispatch MCP "
       "tools), so the sanctioned path still works: %d/%d fell through"
       % (sum(fell_through), len(fell_through)))

    # h8b: falling through is not the same as being granted. The 5 dispatch tools and the read-only
    # three must each be covered by an ALLOW rule, or the dispatcher is merely un-denied — and an
    # un-denied tool with no allow rule is refused in headless mode ("Claude requested permissions to
    # use X, but you haven't granted it yet"), which would break the sanctioned route just as surely
    # as denying it.
    prof_names, _, _ = dispatch_profile()
    routing = ["Read", "Grep", "Glob"] + ["mcp__%s__%s" % (MCP_SERVER, t)
                                          for t in (prof_names or ["ticket_queue"])]
    uncovered = [t for t in routing if not allowing_rule(t)]
    ok("h8b", not uncovered,
       "every tool on the routing surface is COVERED BY AN ALLOW RULE, not merely un-denied "
       "(%d checked: %s)%s" % (len(routing), ", ".join(routing),
                               "" if not uncovered else "; UNCOVERED: %s" % ", ".join(uncovered)))

    # h9: fail closed. A hook that cannot see what it is judging must not wave it through.
    rc, out, _ = _run_hook("not json at all")
    closed_1 = rc == 0 and _is_deny(out)
    rc, out, _ = _run_hook(json.dumps({"hook_event_name": "PreToolUse", "tool_input": {}}))
    closed_2 = rc == 0 and _is_deny(out)
    ok("h9", closed_1 and closed_2,
       "the real hook FAILS CLOSED on an unparseable payload and on one with no tool_name")

    # ── v: the policy document, and the mutation tests that keep `verify` honest ───────────────────
    doc = settings_document()
    ok("v1", verify_document(doc) == [],
       "the emitted settings document holds every invariant (%s)" % (verify_document(doc) or "clean"))

    # v2: the emitted deny list is bare names only — THE BARE-NAME TRAP, checked on the real output.
    ok("v2", all("(" not in r for r in doc["permissions"]["deny"]),
       "every emitted deny rule is a BARE name: %s" % ", ".join(doc["permissions"]["deny"]))

    # v3-v7: MUTATION TESTS. Break the document in exactly the way each invariant exists to catch and
    # assert verify_document NOTICES. A check that cannot fail proves nothing, and a green selftest
    # over a rubber-stamp checker is worse than no selftest at all.
    m = json.loads(json.dumps(doc))
    m["permissions"]["deny"] = [r for r in m["permissions"]["deny"] if r != "Write"]
    ok("v3", any("`Write` is not in permissions.deny" in b for b in verify_document(m)),
       "verify CATCHES a deny list with Write removed")

    m = json.loads(json.dumps(doc))
    m["permissions"]["deny"] = ["Write(**)" if r == "Write" else r for r in m["permissions"]["deny"]]
    fails = verify_document(m)
    ok("v4", any("This rule is inert" in b for b in fails) and any("not in permissions.deny" in b for b in fails),
       "verify CATCHES the parenthesised `Write(**)` regression (the trap that reads right and does "
       "nothing) — and still reports Write as undenied")

    # v4b: and it says so ACCURATELY per tool. `Edit(src/**)` is NOT inert — the file-path checks do
    # honour it; it is merely not a whole-tool deny. A checker that cried "this denies nothing" about
    # a rule that denies something would be teaching the reader a falsehood.
    m = json.loads(json.dumps(doc))
    m["permissions"]["deny"] = ["Edit(src/**)" if r == "Edit" else r for r in m["permissions"]["deny"]]
    fails = verify_document(m)
    ok("v4b", any("WOULD honour it for the paths it names" in b for b in fails)
       and not any("This rule is inert" in b for b in fails),
       "verify describes `Edit(src/**)` accurately — not a whole-tool deny, but NOT called inert "
       "(only the Write family is)")

    m = json.loads(json.dumps(doc))
    m["permissions"]["disableBypassPermissionsMode"] = "allow"
    ok("v5", any("disableBypassPermissionsMode" in b for b in verify_document(m)),
       "verify CATCHES bypassPermissions being re-enabled")

    m = json.loads(json.dumps(doc))
    m["hooks"]["PreToolUse"][0]["matcher"] = "^(Read)$"
    ok("v6", len([b for b in verify_document(m) if "does not fire" in b]) == len(DENIED),
       "verify CATCHES a hook matcher that fires for none of the denied tools")

    m = json.loads(json.dumps(doc))
    m["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = "python3 /nonexistent/gone.py hook"
    ok("v7", any("does not exist" in b for b in verify_document(m)),
       "verify CATCHES a hook command pointing at a file that is not there")

    # v8: the matcher judge agrees with the policy on every denied tool, and does not over-reach.
    ok("v8", all(_matcher_hits(HOOK_MATCHER, t) for t in DENIED)
       and not _matcher_hits(HOOK_MATCHER, "Read")
       and not _matcher_hits(HOOK_MATCHER, "mcp__%s__ticket_queue" % MCP_SERVER),
       "the hook matcher %r fires for every denied tool and for none of the routing surface"
       % HOOK_MATCHER)

    # ── d: the dispatch surface, read from ticket #178's real table ────────────────────────────────
    prof, authoring, prof_path = dispatch_profile()
    if prof is None:
        skip("d1", "ticket_api_mcp.py is not readable at %s — the `mcp__%s__*` allow rule could not "
                   "be cross-checked against the real dispatch profile" % (prof_path, MCP_SERVER))
    else:
        ok("d1", not (set(prof) & set(authoring or ())),
           "the dispatch profile this policy allows contains no authoring tool (profile: %s; "
           "authoring: %s) — read from %s, not restated here"
           % (", ".join(prof), ", ".join(sorted(authoring or ())) or "none",
              os.path.relpath(prof_path, ROOT)))

    # ── r: no forbidden side effect (ticket #153's lesson: prove it in isolation) ──────────────────
    watched = os.path.join(ROOT, ".claude")
    before = _tree(watched) if os.path.isdir(watched) else set()
    before_exists = os.path.isdir(watched)
    tmp = tempfile.mkdtemp(prefix="cap_restrict_selftest_")
    try:
        target = os.path.join(tmp, "nested", "dispatcher-settings.json")

        class _A:
            path, force = target, False
        # install narrates to stdout; here it is a fixture, not a report, so its chatter is muted to
        # keep the PASS/FAIL column readable. Its RETURN VALUE and its file are what get checked.
        rc = _quietly(do_install, _A())
        installed_ok = rc == 0 and os.path.isfile(target)
        # exactly ONE file created, and it verifies
        created = [p for p in _tree(tmp) if os.path.isfile(p)]
        ok("r1", installed_ok and len(created) == 1,
           "install writes exactly ONE file into a throwaway root (%d created)" % len(created))
        doc2 = json.load(open(target))
        ok("r2", verify_document(doc2) == [],
           "the INSTALLED file verifies clean (%s)" % (verify_document(doc2) or "clean"))
        # refuses to clobber
        try:
            _quietly(do_install, _A())
            clobbered = True
        except Fault:
            clobbered = False
        ok("r3", not clobbered, "install REFUSES to overwrite an existing settings file without --force")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    after = _tree(watched) if os.path.isdir(watched) else set()
    ok("r4", before == after and (os.path.isdir(watched) == before_exists),
       "the repo's own .claude/ is byte-for-byte unchanged by this selftest (before %d entries, "
       "after %d) — no command here writes into the repo" % (len(before), len(after)))

    pyc = os.path.join(TOOLS, "__pycache__", "capability_restriction.cpython-%d%d.pyc"
                       % sys.version_info[:2])
    ok("r5", not os.path.exists(pyc),
       "no __pycache__ entry was minted for this module in the repo tree (sys.dont_write_bytecode)")

    # ── p: the claims about the permission engine, re-derived from the installed binary ────────────
    claude = find_claude()
    if not claude:
        skip("p1", "no Claude Code binary found — the permission-engine claims in this module's "
                   "docstring are UNKNOWN on this machine (not disproven). Run `probe` where the "
                   "binary is installed.")
    else:
        results = probe_binary(claude)
        missing = [c for found, c in results if not found]
        ok("p1", not missing,
           "all %d permission-engine enforcement points confirmed in %s%s"
           % (len(results), claude, "" if not missing else "; MISSING: %s" % "; ".join(missing)))

    # ── report ────────────────────────────────────────────────────────────────────────────────────
    for state, tag, msg in checks:
        print("%-4s %-3s %s" % (state, tag, msg))
    failed = [c for c in checks if c[0] == "FAIL"]
    skipped = [c for c in checks if c[0] == "SKIP"]
    print()
    print("%d checks: %d passed, %d failed, %d skipped"
          % (len(checks), len(checks) - len(failed) - len(skipped), len(failed), len(skipped)))
    if failed:
        print("selftest FAILED — the capability restriction does not hold as written.")
        return 1
    print("selftest PASSED — the dispatcher's authoring tools are refused by the hook (executed "
          "here), the permission block holds every invariant that makes it enforceable (mutation-"
          "tested here), and the routing surface still works.")
    return 0


# ── cli ───────────────────────────────────────────────────────────────────────────────────────────
COMMANDS = {"block": do_block, "settings": do_settings, "argv": do_argv, "install": do_install,
            "verify": do_verify, "check": do_check, "hook": do_hook, "probe": do_probe,
            "selftest": do_selftest}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="capability_restriction.py",
        description="The dispatcher's capability floor (ticket #210): deny Write/Edit/code-authoring "
                    "in the permission layer, so the routing agent CANNOT author code. Emits the "
                    "settings.json permission block + the PreToolUse hook, installs them, IS the "
                    "hook, and proves the lot.",
        epilog="commands: " + ", ".join(sorted(COMMANDS)))
    ap.add_argument("command", nargs="?", help="one of: " + ", ".join(sorted(COMMANDS)))
    ap.add_argument("--json", action="store_true", help="block: print bare JSON and nothing else")
    ap.add_argument("--path", help="install/verify/argv: the settings file (default: %s)" % DEFAULT_SETTINGS)
    ap.add_argument("--force", action="store_true", help="install: overwrite an existing settings file")
    ap.add_argument("--tool", help="check: the tool name to fire at the policy, e.g. Write")
    ap.add_argument("--input", help="check: the tool's input, as a JSON object (optional)")
    a = ap.parse_args(argv)

    if not a.command:
        ap.print_help()
        print()
        print("Nothing was run. Start with `block` to see the policy, or `selftest` to prove it.")
        return 2
    fn = COMMANDS.get(a.command)
    if not fn:
        print("capability_restriction: unknown command %r — expected one of: %s"
              % (a.command, ", ".join(sorted(COMMANDS))))
        return 2
    return fn(a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as e:
        print("capability_restriction: %s" % e)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(2)
    except Exception as e:  # noqa: BLE001 — note-for-claude: file a report, then fail on ONE line
        bug_report("main", e, "python3 %s %s" % (SELF, " ".join(sys.argv[1:])), e)
        print("capability_restriction: unexpected failure (%s: %s) — a timestamped bug report was "
              "filed to the registry's bug_reports sink." % (type(e).__name__, e))
        sys.exit(2)
