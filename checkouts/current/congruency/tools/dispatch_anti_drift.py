#!/usr/bin/env python3
"""dispatch_anti_drift.py — the DISPATCHER's role anchor: re-inject the dispatcher directive on every
turn and rebuild its situational awareness from the LEDGER, so role adherence cannot decay as the
context grows (ticket #211).

THE PROBLEM. A role stated once, at birth, is a role that fades. `pair_loop.py --dispatch` builds the
routing agent's turn out of three things — its REGISTERED birth prompt, the queue, and the rules:

    prompt = (reg[0]["prompt"] + "\\n\\nTHE QUEUE:\\n" + json.dumps(queue, indent=1)
              + "\\n" + DISPATCH_RULES)                                        (pair_loop.py:788)

Every one of those is STANDING CONTEXT: said once, at the top, and then pushed further and further
back as the conversation grows. Two failure modes follow, and they are the two this file exists to
remove. (1) ROLE DRIFT: the further the directive recedes, the more the agent answers as a helpful
general-purpose assistant — explaining, opining, proposing patches — instead of routing. (2) STALE
STATE: the queue was true when it was pasted in and is a memory thereafter, so an agent that "recalls"
a ticket's status is recalling a snapshot, not reading the ledger. Prose at the top of a long
conversation is not a control; it is a hope that decays monotonically with token count.

WHAT THIS FILE IS. The ANCHOR plus the two mechanisms that carry it, in one file:

  1. THE HOOK — a `UserPromptSubmit` hook whose command is THIS FILE (`dispatch_anti_drift.py hook`).
     It runs on EVERY turn, before the model sees the user's message, and injects the directive plus a
     freshly-read ledger digest through `hookSpecificOutput.additionalContext`. This is the
     load-bearing layer: it is the only one whose position in context does not depend on turn number.
  2. THE MINIMAL PROFILE — the birth prompt this role should be REGISTERED with (`agent.register`).
     It is deliberately small, because everything that must never be forgotten has moved OUT of the
     birth prompt (said once, drifts) and INTO the per-turn anchor (said every turn, cannot drift).

It emits them (`directive`, `anchor`, `profile`, `block`, `settings`), installs the hook (`install`),
IS the hook (`hook`), audits an installed settings file (`verify`), MEASURES the ticket's acceptance
criterion against context length (`drift`), re-derives its claims from the shipped binary (`probe`),
and proves the lot (`selftest`).

TERMS, defined at first use — this file is read by an auditor who never saw its author.

  * THE DISPATCHER (dispatch-01) is the routing agent: it reads the ticket queue and decides, per
    ticket, "run / skip / stop" (do_dispatch, pair_loop.py:770-835). It authors nothing. The WORKER is
    the agent a "run" decision spawns, in its own branch+worktree, and it MUST author — its tools are
    "Read,Grep,Glob,Write,Edit,Bash(python3:*),..." (FOCUS["build"]["worker_tools"], pair_loop.py:716).
    The two roles need OPPOSITE treatment, which is why this hook is per-spawn; see SCOPE.
  * A HOOK is a command Claude Code runs at a named point in its own loop, handing it a JSON payload
    on stdin and reading a JSON answer on stdout. `UserPromptSubmit` is the point just after the user
    submits a message and before the model is called — i.e. once per TURN, every turn.
  * `additionalContext` is the one field of a `UserPromptSubmit` answer that puts text into the
    model's context for that turn. Claude Code's own embedded hook reference describes it as "Text
    injected into model context"; `probe` re-reads that line, and the code that consumes it, out of
    the installed binary in front of you (see PROVENANCE).
  * THE LEDGER, for the dispatcher, is the ticket record the routing decision is made from: the
    `tickets` table, read through the governed `ticket.queue` route — 'SELECT id, kind, status,
    component, title, body FROM tickets WHERE upper(status) IN (''OPEN'', ''REQUESTED'') ORDER BY id'
    (migrations/0032_dispatch_routes.sql:6-9). That is the same route the dispatcher's own MCP exposes
    to it as `ticket_queue` (ROUTE_TOOLS, ticket_api_mcp.py:169; PROFILES["dispatch"],
    ticket_api_mcp.py:364-366), so the hook and the agent read the SAME surface and cannot disagree.
    NOT TO BE CONFUSED WITH `tracker/tickets.jsonl`, which SIGNALS.md:25 also calls "the ledger": that
    is the separate jazz tracker's file, whose ids run 1-15 in this checkout — a different id space
    from the dispatcher's queue, whose ids run in the hundreds — and it is not what dispatch-01 routes.
    The two are unrelated systems that share a word. When this file says "the ledger" it means the
    `ticket.queue` surface, always.
  * THE DISPATCH-TOOLS MCP is `ticket_api_mcp.py --role dispatch` (ticket #178): an MCP server that
    registers ONLY the dispatch role's 5 routing tools (`ticket_queue`, `ticket_kind`, `ticket_assign`,
    `edge_record`, `ticket_progress` — PROFILES, ticket_api_mcp.py:364-366). None is a work-product
    sink. Claude Code names its tools `mcp__<server-key>__<tool>`, so `ticket_queue` reaches the model
    as `mcp__dispatch-tools__ticket_queue` — the spelling the anchor tells it to use. This file reads
    that module's real PROFILES table rather than restating it (see `dispatch_profile()`), so the
    anchor cannot go on naming a tool the profile has dropped.
  * `b_tools`, WHICH DOES NOT EXIST. Ticket #211 says the dispatcher rebuilds awareness "via b_tools".
    There is no `b_tools` in this repository — no module, no MCP server, no tool namespace; the name
    appears nowhere outside the ticket text. The real surface it describes is the dispatch-tools MCP
    above, and that is what this file builds against. This is stated rather than quietly papered over
    because a reader who greps for `b_tools` on the strength of the ticket must find out here, from
    the artifact, that the name is a dead end and what replaced it.

WHY THE HOOK, AND NOT A BIGGER PROMPT. The distinction the ticket rests on is POSITION, not content.
Text in the birth prompt is inserted once and thereafter sits at a FIXED, ever-receding distance from
the model's attention: at turn 500 it is 500 turns back, and no amount of emphasis changes that. Text
injected by a `UserPromptSubmit` hook is re-inserted at the SAME place on every turn — immediately
before the user's current message — so its distance from the point of decision is CONSTANT and
independent of how long the session has run. That constancy is the entire anti-drift mechanism, and it
is the property `drift` measures: not "is the anchor persuasive", which no test can answer, but "is
the anchor byte-identical and present at turn 1 and at turn N, for any N, at any transcript size",
which is exactly what a mechanical check can answer and what "does not decay with context length"
reduces to.

THE DIVISION OF LABOUR WITH #210. The ticket's acceptance names three behaviours, and this file is
honest about which of them it carries:
  * "does not write code" — carried by `capability_restriction.py` (ticket #210), which DENIES the
    authoring tools in the permission layer. This file does not duplicate that and does not depend on
    it; the anchor merely tells the dispatcher what is already true of its tool surface.
  * "does not answer off-role" and "it dispatches" — carried HERE, by the anchor: the directive that
    names the role, the instruction on what to do with an off-role request, and the fresh ledger
    digest that makes routing the path of least resistance.
The two mechanisms live in the SAME settings file and must not clobber each other. `install` therefore
MERGES: it reads whatever is already at the target, preserves every key it does not own (notably #210's
`permissions` block and its `PreToolUse` hook), and adds or replaces ONLY the hook entries that RUN
this file. Ownership is decided by the script the command executes, never by a substring of it — a
third-party hook that merely mentions this file's name in an argument is somebody else's and survives
untouched (check n1). It is idempotent — installing twice yields the same document as installing once —
and `selftest` proves the interlock by running #210's OWN `verify` against the merged file (check x1).
Where the existing document is malformed in a way the merge cannot honour (`hooks` that is not an
object, an event that is not a list), `install` REFUSES with exit 2 and writes nothing, rather than
replacing what it cannot read. This is the governance rule the repo runs on, applied to a JSON file:
produce, don't erase.

FAIL SOFT ON THE LEDGER, NEVER ON THE ROLE. The hook reads the ledger over HTTP from the local
congruency API, and that read can fail: the server may be down, slow, or unauthenticated. The anchor is
therefore built in two independently-failing parts. The DIRECTIVE is a constant in this file and is
emitted unconditionally — it needs no network, no database and no configuration, so there is no state
of the world in which the role anchor is missing. The LEDGER DIGEST is best-effort: on any failure the
digest is replaced by an explicit one-line UNAVAILABLE notice naming the cause, and the anchor tells
the dispatcher to read the queue with its own tool before deciding. It never fabricates a queue and
never silently omits the section, because a dispatcher shown nothing would conclude the queue was
empty. A hook that crashed instead would be worse than all of this: the turn would proceed with NO
anchor at all, which is precisely the failure this ticket exists to prevent — so the hook catches
everything and always emits the directive. Bound the cost, too: the read is capped by --ledger-timeout
(default 5s) inside the hook's own 10s budget, and the digest is capped at --queue-head entries, so the
anchor stays small and bounded no matter how long the queue grows.

MEMORY-MINIMIZATION, CONCRETELY. The registered profile for dispatch-01 was 1660 characters of standing
context when this was written (`agent.prompt`, migrations/0029_ticket_authorization.sql:171-174) against
539 for `MINIMAL_PROFILE` — but that number is a live fact about a database, so `profile --diff` RE-READS
it and prints both sizes rather than asking you to trust the figure here. Every governance invariant the
registered prompt states — append-only, journal progress, a ticket authorizes you — is stated ONCE and
then drifts with everything else, so each one moves into the anchor and is restated every turn.
`MINIMAL_PROFILE` keeps only what a birth prompt is actually for: the identity, the role, and the
instruction to obey the per-turn anchor. Two of the registered prompt's instructions are not relocated
but DROPPED, and `profile --diff` says so in as many words: it tells the dispatcher to use `kind.roster`
and `work.record`, and neither is in the dispatch role's profile (PROFILES["dispatch"],
ticket_api_mcp.py:364-366) — an instruction naming a tool the role does not have is not guidance, it is
standing context that can only mislead. This file does NOT register the profile: `agent.register` is a
governed write and #211's deliverable is this module, which touches nothing else. `profile
--register-argv` prints the exact call to make the change, for a human to run.

SCOPE — why this is a `--settings` file and NOT `.claude/settings.json`. A project settings file at the
repo root is read by EVERY `claude` spawned with the repo as cwd, and worker worktrees are checkouts of
the same repo — so a committed `.claude/settings.json` carrying this hook would re-anchor the WORKER as
"the dispatcher" and tell it not to write code, which is the exact opposite of its job
(pair_loop.py:716). Role-scoping requires a per-spawn layer, which is exactly `--settings`. The default
install path is <repo>/.claude/dispatcher-settings.json — the same file #210 uses, which is why
`install` merges — and that directory is gitignored (.gitignore:34 — `.claude/`), so the file never
enters a commit and never appears in a worker's worktree. The name is deliberately NOT `settings.json`,
so nothing auto-loads it;
it applies to exactly one spawn: the one that passes `--settings`. `verify` FAILS a document that
carries this hook under an auto-loaded project/user settings filename.

WIRING IT (the one change outside this file, which this file does not make — #211's deliverable is this
module and it touches nothing else). `dispatch_anti_drift.py argv` prints the exact spawn. The one-line
edit that installs the anchor permanently is to pass the settings file through `spawn_claude`'s argv at
pair_loop.py:727, for the dispatch spawn at pair_loop.py:789. Until that edit lands, `install` + `argv`
give an anchored dispatcher spawn today, by hand.

A NOTE ON `claude -p`, STATED PLAINLY BECAUSE IT LIMITS THE CLAIM. The dispatch spawn today is
one-shot: `claude -p <prompt>` (spawn_claude, pair_loop.py:723-727; called at pair_loop.py:789) starts a
fresh process with empty context, submits ONE prompt, and exits. On that path there is exactly one turn,
so the hook fires exactly once and drift has no room to occur in the first place — the anchor is
correct there but not yet load-bearing. What this file is for is every dispatcher session that is NOT
one-shot: an interactive or resumed session, a `--continue`, or the multi-step loop that
`gemma_dispatch_agent.py` already runs (SYSTEM, gemma_dispatch_agent.py:519-520, whose agent "acts ONE
STEP AT A TIME" over many turns). The ticket's premise — "after a long, noisy session" — describes those,
and the mechanism is installed and proven here so that it is already in place when the dispatcher runs
long. Claiming otherwise would be claiming the one-shot path had a drift problem to solve.

WHAT THIS FILE DOES NOT CLAIM. It does not claim to have run `claude`: that binary is not among the
runners #211's worker may execute, so no measurement here observes a model's actual reply, and `drift`
does not pretend to. `drift` measures the ANCHOR — the input the model is guaranteed to receive — and
reports exactly that. What is PROVEN BY EXECUTION here: the hook (real subprocesses of this file, real
UserPromptSubmit payloads, real answers read back), the ledger fail-soft path (exercised against a dead
endpoint), the merge/idempotence of `install` (against a throwaway temp directory, with #210's own
verify run over the result), and `verify`'s invariants (mutation-tested — each is shown to FAIL a
document broken in exactly the way it exists to catch). What is GROUNDED BY READING: the hook contract,
read out of the installed Claude Code binary, which `probe` re-reads on demand.

PROVENANCE — how the claims about `UserPromptSubmit` were established, and how to re-check them. They
were read from the installed Claude Code executable itself (v2.1.210 at the time of writing, resolved
via ~/.local/bin/claude), which embeds its JavaScript. `python3 dispatch_anti_drift.py probe` finds the
current binary, greps it for the exact enforcement points this module relies on, and prints what it
found — so the claims are re-derivable on the reader's machine rather than taken on trust. It exits 0
when the binary confirms every one, 1 when it does not (they may have moved in that version — re-read
them before trusting the hook block), and 2 when no binary can be found at all (a missing binary makes
them UNKNOWN here, never "confirmed" and never "disproven"). `selftest` folds the same probe in as a
SKIP-able check: it is reported as SKIP, never as PASS, when the binary is absent.

Usage:
    python3 dispatch_anti_drift.py directive       # the role directive, verbatim — the invariant text
    python3 dispatch_anti_drift.py anchor          # the exact text the hook injects this turn
    python3 dispatch_anti_drift.py anchor --no-ledger      # ... the offline part alone
    python3 dispatch_anti_drift.py profile         # the minimal birth prompt this role should carry
    python3 dispatch_anti_drift.py profile --diff  # ... next to the one registered now, with sizes
    python3 dispatch_anti_drift.py profile --register-argv # the agent.register call to install it
    python3 dispatch_anti_drift.py block           # the hooks stanza (annotated)
    python3 dispatch_anti_drift.py block --json    # ... the same, as bare JSON, nothing else
    python3 dispatch_anti_drift.py settings        # the merged dispatcher settings file, as JSON
    python3 dispatch_anti_drift.py argv            # the exact `claude` argv an anchored spawn is
    python3 dispatch_anti_drift.py install         # merge the hook into the settings file (prints it)
    python3 dispatch_anti_drift.py install --path P
    python3 dispatch_anti_drift.py verify          # audit the installed file against the invariants
    python3 dispatch_anti_drift.py hook            # BE the UserPromptSubmit hook: stdin -> stdout JSON
    python3 dispatch_anti_drift.py drift           # MEASURE the acceptance: anchor vs context length
    python3 dispatch_anti_drift.py drift --turns 200 --json
    python3 dispatch_anti_drift.py probe           # re-derive the hook contract from the binary
    python3 dispatch_anti_drift.py selftest        # prove all of it; writes nothing into this repo

SIDE EFFECTS, stated exactly (ticket #153's lesson: a "creates no files" claim is checkable, so it had
better be true). `directive`, `anchor`, `profile`, `block`, `settings`, `argv`, `verify`, `hook`,
`drift` and `probe` CREATE NO FILES and write nothing anywhere — not even a __pycache__ entry (see the
bytecode note below). They are not all pure, and the difference is worth naming: `anchor`, `hook`,
`drift` and `profile --diff` perform a READ-ONLY HTTP GET against the local congruency API (a `GET
ticket.queue` / `GET agent.prompt` — both `auth: public` SELECT-only routes,
migrations/0032_dispatch_routes.sql:5-10 and migrations/0029_ticket_authorization.sql:171-174), which
mutates nothing and is skipped entirely with `--no-ledger`. `install` is the only command that writes
into the repo: exactly ONE file, merged not overwritten, and it never removes a key it does not own.
`selftest` writes NOTHING INTO THIS REPO: it exercises `install` against a throwaway temp directory
outside the repo and removes it, and it proves the repo is untouched by listing <repo>/.claude before
and after (check r1). The ONE exception to all of the above is the error path every tool in this repo
shares: an UNEXPECTED exception appends a line to the registry's `bug_reports` sink (logs/, gitignored),
per note-for-claude. That is a crash report, not a side effect of any command working as documented.

Exit codes (each prints ONE line on failure, never a traceback):
    0  the command did its job. For `hook`: the anchor was emitted — ALWAYS. `hook` is the one command
       that never returns anything else and never validates its own options: it clamps a nonsense
       --queue-head/--ledger-timeout rather than refusing it, because exiting non-zero would be read
       as a blocking error and leave the turn with no role anchor, which is the failure this file
       exists to prevent. Every other command rejects the same input with exit 2.
    1  a NEGATIVE ANSWER, not a malfunction. `verify`: the settings file does NOT hold the invariants
       (each one is named). `drift`: the anchor is NOT invariant across context length — the ticket's
       acceptance criterion does not hold as installed. `selftest`: at least one check FAILED.
       `probe`: the installed binary did NOT confirm every claim this module relies on.
    2  a precondition or usage failure — an unreadable/unparseable settings file, an unwritable
       install target, a --turns below 2, a --queue-head below 1, a non-positive --ledger-timeout, no
       Claude Code binary for `probe`, an unknown command or none at all.

Pure-python stdlib, one file — the repo is stdlib-only (DEPENDENCIES.md). Registry-gated per
note-for-claude: it walks UP to registry.json and refuses to run without it; any unexpected exception
files a timestamped Variant-A bug report to the registry's `bug_reports` sink.
"""
# NO BYTECODE CACHE — set before anything else imports. `anchor`/`hook`/`selftest` promise they create
# no files; importing this module as a module (as selftest's subprocesses do) would otherwise mint
# tools/__pycache__/dispatch_anti_drift.*.pyc in the repo tree and break that promise.
import sys

sys.dont_write_bytecode = True

import argparse
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
import traceback
import urllib.error
import urllib.request


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
AGENT_ID = "dispatch-01"               # the registered routing identity (pair_loop.py:778)
CONG = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")

HOOK_TIMEOUT = 10                      # seconds Claude Code gives the hook command, whole
LEDGER_TIMEOUT = 5                     # seconds for the ledger read INSIDE that budget; fails soft
QUEUE_HEAD = 12                        # how many queued tickets the digest names; keeps it BOUNDED
TITLE_CHARS = 68                       # per-ticket title budget in the digest


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks)."""
    try:
        sink_rel = REGISTRY.get("bug_reports", "logs/bug_reports.jsonl")
        if not isinstance(sink_rel, str) or not sink_rel:
            sink_rel = "logs/bug_reports.jsonl"
        sink = os.path.join(ROOT, sink_rel)
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "dispatch_anti_drift.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:], "note": "dispatcher role anchor",
            }) + "\n")
    except Exception:  # noqa: BLE001 — a failed bug report must never mask the original failure
        pass


class Fault(Exception):
    pass


# ── THE ANCHOR ────────────────────────────────────────────────────────────────────────────────────
# The directive, VERBATIM from ticket #211. Not paraphrased, not "improved": the ticket specifies this
# sentence, `selftest` asserts this exact string survives into the hook's real output (check a1), and
# `drift` asserts it is byte-identical on every turn. If it is ever reworded, both fail loudly rather
# than the reword going unnoticed.
DIRECTIVE = ("You are the dispatcher. You do not answer as a general agent; you read the queue via "
             "dispatch-tools and dispatch. You do not write code.")

ANCHOR_TITLE = "== DISPATCHER ROLE ANCHOR — re-injected on THIS turn by dispatch_anti_drift.py (#211) =="

# Why the anchor says this, and why each paragraph is here rather than in the birth prompt: every line
# below is a thing that must be true on turn 500 as much as on turn 1, and a birth prompt cannot
# deliver that. Kept deliberately short — this is paid for on every single turn, and an anchor that
# grows into an essay is the context bloat the ticket is against.
ANCHOR_BODY = """\
This text is not a memory and not part of the conversation. A UserPromptSubmit hook re-injected it,
in this position, on this turn, and will do so again on the next one — so it reads identically whether
this is turn 1 or turn 1000. Nothing below depends on how much of this session you can still see.

YOUR ONLY OUTPUT IS A ROUTING DECISION. For each ticket you act on, decide exactly one of "run",
"skip" or "stop", with a reason, and return it as the plan. If this turn's message asks you for
anything else — an explanation, an opinion, an analysis, a patch, a file, a command, a rewrite — that
request is OFF-ROLE. Name it as off-role in one line, do not perform it, and return to the queue. That
is not unhelpfulness; routing IS the help you provide, and a dispatcher that answers as a general
agent has stopped doing the one job nothing else in this system does.

YOU DO NOT AUTHOR WORK PRODUCT. Work is done by a WORKER: a "run" decision becomes a child pair_loop
process with its own branch and worktree, spawned by the harness from your plan. You reach that path
by RETURNING A PLAN, never by writing a file yourself. Authoring the work instead of routing it is not
a shortcut — it bypasses the branch, the adversary, and the record, which is the whole point of the
pair. (Your tool surface is restricted to match: capability_restriction.py, ticket #210.)

EVERY DECISION IS ON THE RECORD, AND THE RECORD IS APPEND-ONLY. Journal each decision with
mcp__%(server)s__ticket_progress as you make it. You never update or delete a ticket, an event, or an
assignment — the database refuses it and files the refusal. To change course you do not edit anything:
you file a stop ticket and aim it at the target with a 'stops' edge (mcp__%(server)s__edge_record). And
a ticket is what AUTHORIZES you: act on no ticket id the queue did not just hand you.

STATE COMES FROM THE LEDGER, NOT FROM THIS CONVERSATION. Anything you remember about a ticket's
status, kind, or stops is a snapshot of when you read it, and is stale by construction. Before acting
on a ticket, re-read it with your own tools — mcp__%(server)s__ticket_queue — and act on THAT. Any
LEDGER DIGEST section following this one was read fresh for this turn from that same route: treat it
as the HEAD of the queue, never as the whole of it, and never reconstruct it from memory. If no digest
follows, then the queue was not read for you this turn — read it yourself before you decide anything."""

# The MINIMAL agent profile: what dispatch-01 should be REGISTERED with (agent.register,
# migrations/0001_agents.sql:20-25). Small on purpose — see MEMORY-MINIMIZATION in the module
# docstring. It carries identity and nothing that the anchor restates every turn, because a governance
# invariant stated once at birth is exactly the thing that drifts; stated every turn, it cannot.
MINIMAL_PROFILE = """\
You are %(agent)s, the dispatcher. You route the ticket queue; you author nothing.

Your standing rules are not in this prompt. They are re-injected on every turn, ahead of each message,
by the dispatcher role anchor (dispatch_anti_drift.py, ticket #211), and the queue itself is read from
the ledger with your own tools. Follow the anchor on the turn you are on. Do not act on anything you
remember about a ticket without re-reading it first: this prompt is deliberately small, and it is not
where your situational awareness comes from.""" % {"agent": AGENT_ID}


def anchor_directive_block():
    """The INVARIANT half of the anchor: the part that must be byte-identical on every turn.

    Split out from the ledger digest deliberately, because the two have opposite requirements and a
    single blob could not honour both. This half must never change — `drift` compares it across turns
    and FAILS if it moves. The other half must change: it is a fresh read, and a ledger digest that
    was byte-identical across turns would mean it had been cached, which is the drift this file
    exists to prevent. Keeping them separate is what lets each be checked for the right property."""
    return "%s\n\n%s\n\n%s" % (ANCHOR_TITLE, DIRECTIVE, ANCHOR_BODY % {"server": MCP_SERVER})


# ── the ledger: the dispatcher's state, re-read every turn ────────────────────────────────────────
def ledger_queue(timeout=LEDGER_TIMEOUT):
    """The queue, read from the governed `ticket.queue` route. Returns (rows, error_or_None).

    Read over the SAME route the dispatcher's own MCP exposes as `ticket_queue`
    (ROUTE_TOOLS, ticket_api_mcp.py:169) so the digest and the agent's own tool cannot disagree about
    what the queue is — a digest built from some other source would be a second opinion, and the point
    of the anchor is that there is only one.

    NEVER RAISES. Every failure — the server being down, slow, unauthenticated, or answering something
    that is not the expected JSON — comes back as an error STRING for the caller to print, because the
    one thing this must not do is take the role anchor down with it. `auth` is `public` on this route
    (migrations/0032_dispatch_routes.sql:8), so no key is sent and none is needed."""
    url = CONG + "/rest.php?route=ticket.queue"
    try:
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return [], "the ledger route answered HTTP %s" % e.code
    except urllib.error.URLError as e:
        return [], "the congruency API at %s is unreachable (%s)" % (CONG, e.reason)
    except (ValueError, OSError) as e:
        return [], "the ledger read failed (%s: %s)" % (type(e).__name__, e)
    if not isinstance(out, dict):
        return [], "the ledger route answered something that is not a JSON object"
    if out.get("error"):
        return [], "the ledger route reported: %s" % out["error"]
    rows = out.get("rows")
    if not isinstance(rows, list):
        return [], "the ledger route answered no `rows` list"
    return rows, None


def ledger_digest(rows, err, head=QUEUE_HEAD, now=None):
    """The queue as a SMALL, BOUNDED block of text: totals, then the oldest `head` tickets.

    Bounded on purpose. The naive anti-drift move is to paste the whole queue in every turn, but the
    queue is over 140 tickets deep in this checkout and re-pasting all of it — with bodies — on every
    turn is the context bloat this ticket is against. The digest is therefore a HEAD plus a count, and the
    anchor says in as many words that it is the head and not the whole, with the tool named for
    reading the rest. Situational awareness is rebuilt each turn; the transcript is not.

    An UNAVAILABLE ledger produces a NAMED failure, never an empty queue: a dispatcher shown an empty
    section would reasonably conclude there was nothing to route, so the notice says what broke and
    tells it to read the queue with its own tool before deciding anything.

    `head` is CLAMPED to at least 1 rather than trusted. The CLI already rejects a non-positive
    --queue-head, so this is the hook's own belt: `rows[:0]` renders "the 0 oldest" above an empty
    list, and a NEGATIVE head silently renders `rows[:-5]` — the TAIL of the queue, printed under a
    heading that calls it the head and a footer that miscounts the remainder. A digest that lies about
    which tickets it is showing is worse than no digest, and the hook must not be able to emit one
    however it is configured."""
    head = max(1, int(head))
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now if now is not None else time.time()))
    if err:
        return ("LEDGER DIGEST — UNAVAILABLE (read at %s): %s.\nYour role above is unaffected. Read "
                "the queue with mcp__%s__ticket_queue before you decide anything, and do not fall "
                "back on what you remember of it." % (stamp, err, MCP_SERVER))
    if not rows:
        return ("LEDGER DIGEST (read at %s from ticket.queue): the queue is EMPTY — no OPEN or "
                "REQUESTED ticket. There is nothing to route this turn." % stamp)
    lines = ["LEDGER DIGEST (read at %s from ticket.queue — fresh this turn, not remembered):" % stamp]
    kinds = {}
    for t in rows:
        kinds[t.get("kind") or "(unkinded)"] = kinds.get(t.get("kind") or "(unkinded)", 0) + 1
    lines.append("  %d ticket(s) OPEN or REQUESTED, by kind: %s"
                 % (len(rows), ", ".join("%s=%d" % (k, n) for k, n in sorted(kinds.items()))))
    shown = rows[:head]
    lines.append("  the %d oldest (id / kind / status / title):" % len(shown))
    for t in shown:
        title = str(t.get("title") or "").replace("\n", " ").strip()
        if len(title) > TITLE_CHARS:
            title = title[:TITLE_CHARS - 1] + "…"
        # 17 wide because `rfc-investigation` is a real kind and is exactly that long; a narrower
        # column does not truncate it, it shunts every later column out of line for that row.
        lines.append("    #%-5s %-17s %-9s %s" % (t.get("id"), t.get("kind") or "(unkinded)",
                                                  t.get("status") or "?", title))
    if len(rows) > len(shown):
        lines.append("  ... and %d more NOT shown. This is the HEAD of the queue, not the whole of "
                     "it — read the rest with mcp__%s__ticket_queue." % (len(rows) - len(shown), MCP_SERVER))
    return "\n".join(lines)


def anchor_text(use_ledger=True, timeout=LEDGER_TIMEOUT, head=QUEUE_HEAD, now=None):
    """The whole anchor for one turn: the invariant directive block, then the fresh ledger digest.

    The order is load-bearing. The directive comes FIRST so that the one thing that must survive is
    never pushed off by a digest that grew; and the digest comes last, closest to the user's message,
    because it is the state the decision is made from."""
    block = anchor_directive_block()
    if not use_ledger:
        return block
    rows, err = ledger_queue(timeout)
    return "%s\n\n%s" % (block, ledger_digest(rows, err, head, now))


# ── the dispatch surface, read from ticket #178's real profile table ──────────────────────────────
def dispatch_profile(path=None):
    """The dispatch role's tool names, read out of ticket_api_mcp.py's real PROFILES table.

    Read, not restated: the anchor tells the dispatcher to read the queue with
    `mcp__dispatch-tools__ticket_queue`, and that instruction is only true while `ticket_queue` is
    actually in the dispatch profile. If this file hard-coded its own copy of that list, #178 could
    rename or drop the tool tomorrow and the anchor would go on naming a tool that does not exist —
    an anchor that instructs the model to call a missing tool is worse than no anchor. So the table is
    parsed from the source of truth, and `selftest` check d1 asserts the agreement.

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
def hook_output(payload, use_ledger=True, timeout=LEDGER_TIMEOUT, head=QUEUE_HEAD):
    """The hook's answer for one UserPromptSubmit payload. Returns the decision dict.

    ALWAYS ANSWERS, and always with the anchor. There is no payload — malformed, empty, unparseable,
    wrong event — for which the right response is silence, and that is the exact opposite of #210's
    PreToolUse hook, which stays silent unless it has something to refuse. The asymmetry is the point:
    a PreToolUse hook that says nothing falls through to the permission rules, which are the floor, so
    silence is safe there. Here there IS no floor underneath — silence means the turn proceeds with no
    role anchor at all, which is the failure this ticket exists to prevent. So this hook fails OPEN
    with the anchor, never closed.

    It never blocks the prompt. `UserPromptSubmit` supports `decision: "block"`, and refusing off-role
    prompts outright might look like a stronger reading of "does not answer off-role" — but a hook
    cannot tell an off-role request from an on-role one (it sees text, not intent), so blocking would
    mean guessing, and a wrong guess silently drops a legitimate routing instruction. The anchor tells
    the MODEL what to do with an off-role request; the tool surface is what actually stops it from
    authoring (#210). This hook's job is to make sure the role is always in front of the model, and it
    does exactly that and nothing more."""
    ctx = anchor_text(use_ledger=use_ledger, timeout=timeout, head=head)
    return {
        "hookSpecificOutput": {
            # The event name is echoed back because Claude Code dispatches on it: the branch that
            # reads `additionalContext` is selected by `hookEventName`, so an answer that omits it or
            # names the wrong event is parsed as some other event's answer and the context is dropped.
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        },
        # suppressOutput keeps the anchor out of the visible transcript: it is machinery, re-emitted
        # every turn, and printing it each time would bury the actual conversation in its own scaffolding.
        "suppressOutput": True,
    }


def do_hook(a):
    """UserPromptSubmit hook mode: one JSON object in on stdin, exactly one JSON object out on stdout.

    Always exits 0, and always prints an anchor. A non-zero exit or a stderr splat is read as a hook
    BLOCKING ERROR, which would turn "the anti-drift hook had a bad day" into "the dispatcher's turn
    was rejected". The payload is READ but not required: `UserPromptSubmit` sends `{"session_id", ...,
    "prompt"}`, and this hook needs none of it — the anchor does not depend on what the user typed,
    which is precisely why it cannot be talked out of it. Draining stdin regardless is deliberate: the
    writer on the other end must not be left with an unread pipe.

    CLAMPS, NEVER REFUSES. Its two numeric options are corrected here rather than validated in `main`
    (where every other command's are), because rejecting them would mean exiting non-zero with no
    anchor — trading a bad digest for no role at all, which is the trade this whole file exists to
    refuse. A nonsense --queue-head or --ledger-timeout in a settings file is a misconfiguration; an
    unanchored turn is the bug. So: take the sane value, emit the anchor, carry on."""
    try:
        sys.stdin.read()
    except (OSError, ValueError):     # no stdin, or a closed pipe — the anchor does not depend on it
        pass
    head = max(1, a.queue_head)
    timeout = a.ledger_timeout if a.ledger_timeout > 0 else LEDGER_TIMEOUT
    try:
        out = hook_output(payload=None, use_ledger=not a.no_ledger, timeout=timeout, head=head)
    except Exception as e:  # noqa: BLE001 — the anchor MUST be emitted; degrade, never disappear
        bug_report("do_hook", e, "python3 %s hook" % SELF, e)
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                      "additionalContext": anchor_directive_block()},
               "suppressOutput": True}
    sys.stdout.write(json.dumps(out) + "\n")
    return 0


# ── the artifacts: the hook command, the hooks stanza, the merged settings file ───────────────────
def hook_command(self_path=SELF, python=None):
    """The shell command Claude Code runs for the hook: this file, in `hook` mode, by absolute path.

    Absolute, because a hook runs with the project directory as cwd and this file lives under
    checkouts/current/congruency/tools; and shell-quoted, because the command string is handed to a
    shell and a path with a space would otherwise split into two arguments."""
    return "%s %s hook" % (shlex.quote(python or sys.executable), shlex.quote(self_path))


def hook_block(self_path=SELF, python=None):
    """The `hooks` stanza this file owns: the per-turn anchor, plus the same anchor at session start.

    BOTH events, and the reason is not belt-and-braces. `UserPromptSubmit` is the load-bearing one —
    it is what makes the anchor per-TURN and therefore drift-proof. `SessionStart` is added because a
    resumed session (`--continue`, `--resume`) restores a transcript that may already be long before
    the first new prompt arrives, and the anchor should be in front of the model from the first token
    it generates, not from the second turn onward. The ticket asks for "UserPromptSubmit /
    session-level"; this is both, and they are independent — either alone still anchors."""
    def entry():
        # Built fresh per event, never a shared dict: two events pointing at ONE object would alias,
        # so a later edit to either (a merge appending to one event's list, a caller re-timing a hook)
        # would silently reach through into the other.
        return [{"hooks": [{"type": "command",
                            "command": hook_command(self_path, python),
                            "timeout": HOOK_TIMEOUT}]}]
    return {"hooks": {"UserPromptSubmit": entry(), "SessionStart": entry()}}


def owns_command(cmd):
    """Is this hook command OURS? Used by the merge to replace only its own entries.

    Matched on the SCRIPT the command runs — parsed out of the argv with `_hook_target` and compared
    by basename — not on the whole command string, and not by substring. Both halves of that matter:

      * Not the whole string: the interpreter path and the checkout path vary between installs, so an
        exact match would fail to recognise an entry this file wrote under a different
        `sys.executable` and would then append a SECOND copy, injecting the anchor twice per turn.
      * Not a substring: `"dispatch_anti_drift.py" in cmd` is true of any command that merely MENTIONS
        this file — `python3 /opt/audit/logger.py --note "re-anchored by dispatch_anti_drift.py"` is
        somebody else's hook, and a merge that treats it as its own DELETES it while reporting that it
        preserved everything. Comparing the executed script cannot make that mistake: the script there
        is logger.py, which is not this file."""
    target = _hook_target(cmd)
    return bool(target) and os.path.basename(target) == os.path.basename(SELF)


def merge_hooks(doc, self_path=SELF, python=None):
    """Merge this file's hooks into an existing settings document, preserving everything else.

    THE RULE IS: PRODUCE, DON'T ERASE. The target file is shared with ticket #210, whose `permissions`
    block is the thing that actually stops the dispatcher from authoring code. A naive `install` that
    wrote this file's document over the top would silently delete that floor — a settings file is one
    JSON object, and the last writer wins. So the merge:
      * copies the document and touches no key it does not own (`permissions`, and any hook event
        other than the two in `hook_block`, notably #210's `PreToolUse`, pass through untouched);
      * within its OWN two events, drops any entry already pointing at this file and appends a fresh
        one — so the result is IDEMPOTENT (installing twice == installing once, check m3) and a stale
        path from an earlier checkout is corrected rather than duplicated;
      * preserves any OTHER command hook registered on those two events by someone else.
    Returns a new document; the input is not mutated."""
    out = json.loads(json.dumps(doc)) if doc else {}
    if not isinstance(out, dict):
        raise Fault("the settings document is not a JSON object, so there is nothing to merge into")
    hooks = out.get("hooks")
    if hooks is None:
        hooks = {}
    if not isinstance(hooks, dict):
        # REFUSE, don't overwrite. Replacing a `hooks` value we cannot read would erase whatever it
        # was — and this file's whole merge contract is that it never removes what it does not own.
        # A malformed shared file is a thing for a human to look at, not for this tool to flatten.
        raise Fault("the settings document's `hooks` is a %s, not an object — refusing to merge, "
                    "because replacing it would destroy whatever it was meant to hold. Fix or move "
                    "the file, then re-run." % type(hooks).__name__)
    mine = hook_block(self_path, python)["hooks"]
    for event, groups in mine.items():
        existing = hooks.get(event)
        if existing is not None and not isinstance(existing, list):
            raise Fault("`hooks.%s` is a %s, not a list of hook groups — refusing to merge, because "
                        "replacing it would destroy it. Fix or move the file, then re-run."
                        % (event, type(existing).__name__))
        existing = list(existing) if isinstance(existing, list) else []
        kept = []
        for group in existing:
            if not isinstance(group, dict):
                kept.append(group)
                continue
            inner = [h for h in (group.get("hooks") or [])
                     if not (isinstance(h, dict) and owns_command(h.get("command")))]
            if inner:
                g = dict(group)
                g["hooks"] = inner
                kept.append(g)
            elif not (group.get("hooks") or []):
                kept.append(group)      # an empty group someone else wrote; not ours to delete
        hooks[event] = kept + groups
    out["hooks"] = hooks
    return out


def deny_rules(doc):
    """#210's deny list out of a settings document, or None when there is no well-formed one.

    A FUNCTION rather than `doc["permissions"]["deny"]` at each site, because the shape is not
    guaranteed: this file shares its target with #210 and with whatever a hand-edit leaves behind, so
    `permissions` can be a list, a string, or absent, and `deny` likewise. Reaching into it directly is
    how a reporting line — code that exists only to describe the document — crashes on the exact
    malformed input that `verify_document`'s i6 invariant was written to REPORT. Returning None for
    "no well-formed deny list" keeps that distinction: None means "cannot say", never "zero rules"."""
    perms = doc.get("permissions") if isinstance(doc, dict) else None
    if not isinstance(perms, dict):
        return None
    deny = perms.get("deny")
    return deny if isinstance(deny, list) else None


def read_settings(path):
    """The settings document at `path`, or {} when there is none. Raises Fault on an unreadable one.

    A MISSING file is not an error — it is the first install. An UNPARSEABLE one is, and loudly: the
    merge would otherwise "recover" by treating it as empty and writing a document that silently
    dropped #210's permission block, which is the one outcome this file must never produce."""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except ValueError as e:
        raise Fault("%s is not parseable JSON (%s) — refusing to merge, because overwriting it would "
                    "destroy whatever it was meant to hold (e.g. ticket #210's permission block). Fix "
                    "or move the file, then re-run." % (path, e))
    except OSError as e:
        raise Fault("cannot read %s (%s)" % (path, e))
    if not isinstance(doc, dict):
        raise Fault("%s does not contain a JSON object — refusing to merge" % path)
    return doc


def settings_document(path=DEFAULT_SETTINGS, self_path=SELF, python=None):
    """The settings file as it WOULD BE after `install`: whatever is there now, plus these hooks."""
    return merge_hooks(read_settings(path), self_path, python)


def spawn_argv(settings_path=DEFAULT_SETTINGS, prompt="<the dispatch-01 prompt + THE QUEUE + DISPATCH_RULES>"):
    """The exact `claude` argv an anchored dispatcher spawn is, next to the one pair_loop runs today.

    This is `spawn_claude`'s argv (pair_loop.py:723-727) plus `--settings`. Everything else is
    unchanged: `--allowedTools "Read,Grep,Glob"` still auto-approves the read-only three
    (pair_loop.py:789). The settings file is where both the anchor (this file) and the capability floor
    (#210) live, which is why they merge into one."""
    return ["claude", "-p", prompt, "--allowedTools", "Read,Grep,Glob", "--settings", settings_path]


# ── the profile: the minimal standing context this role should be born with ───────────────────────
def registered_profile(agent_id=AGENT_ID, timeout=LEDGER_TIMEOUT):
    """The birth prompt `agent_id` is REGISTERED with, read back from the record. (row, error).

    Read, never invented — the same thing pair_loop.do_dispatch does before every dispatch
    (`rows("agent.prompt", ...)`, pair_loop.py:778-780) and for the same reason: the identity is a fact
    on the record. Fails soft like the ledger read; a `profile --diff` with no server still prints the
    minimal profile, and says why the comparison is missing rather than inventing the other side."""
    url = CONG + "/rest.php?route=agent.prompt&agent_id=" + urllib.request.quote(agent_id)
    try:
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode())
    except (urllib.error.URLError, ValueError, OSError) as e:
        return None, "could not read the registered profile (%s)" % e
    rows = (out or {}).get("rows")
    if not isinstance(rows, list) or not rows:
        return None, "%s is not registered — there is no profile on the record to compare against" % agent_id
    return rows[0], None


def register_argv(agent_id=AGENT_ID):
    """The exact governed call that would install the minimal profile. PRINTED, never executed.

    `agent.register` is a token-authed write (migrations/0001_agents.sql:20-25) and #211's deliverable
    is this module — it touches nothing else, and a tool that quietly re-registered the dispatcher
    while you were reading its output would be exactly the kind of side effect the ticket forbids. So
    this is a string for a human to run, with the tools list preserved from the record."""
    row, _err = registered_profile(agent_id)
    tools = (row or {}).get("tools") or "[]"
    body = {"agent_id": agent_id, "parent": (row or {}).get("parent") or "",
            "prompt": MINIMAL_PROFILE, "tools": tools}
    # The URL is quoted because `?` is a shell glob character: pasted bare, bash tries to expand it
    # and — with nullglob or a stray match — hands curl something other than what is printed here. A
    # command that cannot be run exactly as printed is not a usable instruction.
    return ("curl -sS -X POST %s \\\n"
            "  -H 'Content-Type: application/json' -H \"X-Api-Key: $CONGRUENCY_API_KEY\" \\\n"
            "  -d %s" % (shlex.quote(CONG + "/rest.php?route=agent.register"),
                         shlex.quote(json.dumps(body))))


# ── emitting ──────────────────────────────────────────────────────────────────────────────────────
def do_directive(_a):
    """The invariant text, alone. This is what must be identical on every turn."""
    print(DIRECTIVE)
    return 0


def do_anchor(a):
    """The exact text the hook injects, printed as the model would receive it."""
    print(anchor_text(use_ledger=not a.no_ledger, timeout=a.ledger_timeout, head=a.queue_head))
    return 0


def do_profile(a):
    """The minimal birth prompt; with --diff, the one on the record next to it, with sizes."""
    if a.register_argv:
        print(register_argv())
        return 0
    if not a.diff:
        print(MINIMAL_PROFILE)
        return 0
    row, err = registered_profile()
    print("=" * 78)
    print("REGISTERED NOW (agent.prompt, agent_id=%s)" % AGENT_ID)
    print("=" * 78)
    if err:
        print("(unavailable: %s)" % err)
        now_chars = None
    else:
        print(row["prompt"])
        now_chars = len(row["prompt"])
    print()
    print("=" * 78)
    print("MINIMAL (this file's MINIMAL_PROFILE)")
    print("=" * 78)
    print(MINIMAL_PROFILE)
    print()
    print("sizes: registered=%s chars, minimal=%d chars"
          % ("unknown" if now_chars is None else now_chars, len(MINIMAL_PROFILE)))
    if now_chars:
        print("       the minimal profile carries %d%% of the standing context the registered one does."
              % round(100.0 * len(MINIMAL_PROFILE) / now_chars))
    print()
    print("WHAT CHANGED, LINE BY LINE. Most of the birth prompt is RELOCATED, not deleted — moved from")
    print("a place that drifts (said once, recedes with every turn) to one that cannot (said every")
    print("turn). But not all of it: two things are genuinely dropped, and pretending otherwise would")
    print("be the kind of claim this repo files as a finding. The three cases, kept apart:")
    print()
    print("  RELOCATED to the per-turn anchor — verbatim in `dispatch_anti_drift.py anchor`:")
    print("    * the role, and 'you never author work product'  -> the anchor's directive, every turn")
    print("    * 'history is append-only; stop + graft, never edit' -> the anchor's record paragraph")
    print("    * 'report progress via ticket.progress'          -> the same paragraph")
    print("    * 'a ticket authorizes you'                      -> the same paragraph")
    print("  RELOCATED to the ledger, read at the moment of use rather than remembered:")
    print("    * each ticket's kind and status  -> the digest's columns, and ticket_queue for the rest")
    print("  DROPPED — the registered prompt names these tools, and the dispatch role does not have")
    print("  them. An instruction to use a tool the role lacks is not guidance; it is standing")
    print("  context that can only mislead, and it is the first thing a minimal profile should shed:")
    prof, _authoring, prof_path = dispatch_profile()
    if prof is None:
        print("    * (the dispatch profile could not be read from %s, so this list is UNKNOWN"
              % os.path.basename(prof_path))
        print("      here rather than empty — re-run where ticket_api_mcp.py is present.)")
    else:
        for named, why in (("kind.roster", "the queue already carries each ticket's `kind`"),
                           ("work.record", "the dispatcher produces no work; the forge records it")):
            print("    * %-12s not in the dispatch profile — %s" % (named, why))
        print("      the profile, read from %s just now, is exactly:" % os.path.basename(prof_path))
        print("        %s" % ", ".join(prof))
    print("  NOT HERE AT ALL, deliberately — neither profile nor anchor mentions it:")
    print("    * the BRAKE (a 'stops' edge aimed at a ticket or an ancestor). `ticket.stops` is")
    print("      deliberately absent from the dispatch profile: the harness pre-computes it per")
    print("      ticket and enforces it, overriding the model rather than trusting it")
    print("      (gemma_dispatch_agent.py:66-76). Safety-critical state the harness owns must not be")
    print("      re-implemented as a sentence in a prompt.")
    print()
    print("This command CHANGES NOTHING. To install the minimal profile, run what")
    print("`dispatch_anti_drift.py profile --register-argv` prints.")
    return 0


def do_block(a):
    """The hooks stanza this file owns — annotated, or bare JSON with --json."""
    block = hook_block()
    if a.json:
        print(json.dumps(block, indent=2))
        return 0
    print("=" * 78)
    print(json.dumps(block, indent=2))
    print("=" * 78)
    print()
    print("WHERE IT GOES")
    print("  %s" % DEFAULT_SETTINGS)
    print("  ... MERGED, not written over: that file is shared with ticket #210, whose `permissions`")
    print("  block is what actually denies the dispatcher its authoring tools. `install` preserves")
    print("  every key it does not own; it only ever replaces hook entries pointing at this file.")
    print()
    print("THE TWO EVENTS")
    print("  UserPromptSubmit  fires once per TURN, before the model sees the message. This is the")
    print("                    load-bearing one: it is what makes the anchor's distance from the")
    print("                    decision CONSTANT instead of growing with the session.")
    print("  SessionStart      fires once, at start/resume. A resumed session can already be long")
    print("                    before its first new prompt; this anchors it from the first token.")
    print()
    print("WHAT IT INJECTS  (`dispatch_anti_drift.py anchor` prints it in full)")
    print("  the directive, verbatim and byte-identical every turn, then a ledger digest read fresh")
    print("  from ticket.queue for that turn. The directive needs no network and is emitted even when")
    print("  the ledger read fails, so there is no state of the world with no role anchor.")
    print()
    print("SPAWN IT")
    print("  %s" % " ".join(shlex.quote(x) for x in spawn_argv()))
    return 0


def do_settings(a):
    """The whole settings file as it would be after `install` — the merge result, as JSON."""
    print(json.dumps(settings_document(a.path or DEFAULT_SETTINGS), indent=2))
    return 0


def do_argv(a):
    """The exact spawn, plus the one edit that would make it permanent."""
    argv = spawn_argv(a.path or DEFAULT_SETTINGS)
    print(" ".join(shlex.quote(x) for x in argv))
    print()
    print("This is spawn_claude's argv (pair_loop.py:723-727) plus `--settings`. The dispatch spawn it")
    print("replaces is pair_loop.py:789. To make it permanent, pass the settings file through")
    print("spawn_claude's argv at pair_loop.py:727 — one edit, which #211 does not make: this ticket's")
    print("deliverable is this module and it touches nothing else.")
    return 0


def do_install(a):
    """Merge the hooks into the settings file. The only command that writes into the repo."""
    path = a.path or DEFAULT_SETTINGS
    before = read_settings(path)
    doc = merge_hooks(before)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(json.dumps(doc, indent=2) + "\n")
    except OSError as e:
        raise Fault("cannot write %s (%s)" % (path, e))
    kept = sorted(k for k in doc if k != "hooks")
    print("installed: %s" % path)
    print("  hooks    UserPromptSubmit + SessionStart -> %s" % hook_command())
    print("  merged   %s"
          % ("into an existing file; preserved: %s + hook events %s"
             % (", ".join(kept) or "(no other top-level keys)",
                ", ".join(sorted(k for k in doc["hooks"] if k not in ("UserPromptSubmit", "SessionStart")))
                or "(none)")
             if before else "created (no file was there before)"))
    rules = deny_rules(before)
    if rules is not None:
        print("  #210     the permission block is present and untouched (%d deny rule(s))" % len(rules))
    elif "permissions" in before:
        print("  #210     WARNING: this file has a `permissions` key that is not a block with a deny")
        print("           list. Yours is merged in and nothing was removed, but #210's floor is NOT")
        print("           readable here — run `verify --path %s`." % path)
    else:
        print("  #210     NOTE: no `permissions` block here. This file anchors the ROLE; it does not")
        print("           deny the authoring tools. Run `capability_restriction.py install` for that.")
    print("  spawn    %s" % " ".join(shlex.quote(x) for x in spawn_argv(path)))
    print("  verify   python3 %s verify --path %s" % (SELF, path))
    if os.path.basename(path) == "settings.json":
        print()
        print("  WARNING: %r is an AUTO-LOADED settings filename. Every `claude` started in this repo")
        print("  would read it — including the WORKER in its worktree, which would be told it is the")
        print("  dispatcher and must not write code, when writing the deliverable is its entire job")
        print("  (pair_loop.py:716). This hook must reach exactly one spawn, via --settings.")
    return 0


# ── verifying ─────────────────────────────────────────────────────────────────────────────────────
def verify_document(doc, path=DEFAULT_SETTINGS, self_path=SELF):
    """Audit a settings document against the invariants that make the ANCHOR real. Returns [failures].

    Not a schema check — this is the list of ways a settings file can look anchored and anchor
    nothing. Each invariant is here because getting it wrong yields a file that reads correctly and
    injects nothing, which is worse than an obviously missing hook because nobody looks again.
    `selftest` mutation-tests every one: it breaks the document in exactly that way and asserts this
    function catches it (checks v2-v6), so the checks cannot rot into a rubber stamp."""
    bad = []
    if not isinstance(doc, dict):
        return ["the settings document is not a JSON object"]
    hooks = doc.get("hooks")
    if not isinstance(hooks, dict):
        return ["no `hooks` object — the anchor is not installed at all"]

    # i1 — the per-turn event is wired. Without UserPromptSubmit there is no ANTI-drift: SessionStart
    # alone injects once and then recedes exactly like the birth prompt it was meant to replace.
    groups = hooks.get("UserPromptSubmit")
    if not isinstance(groups, list) or not groups:
        bad.append("no `hooks.UserPromptSubmit` — the anchor would be injected at most once per "
                   "session, which is the drift this file exists to remove")
        groups = []

    # i2 — some entry on that event actually runs THIS file. A UserPromptSubmit hook running something
    # else is someone else's hook and injects none of this.
    cmds = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        for h in group.get("hooks") or []:
            if isinstance(h, dict) and h.get("type") == "command" and h.get("command"):
                cmds.append(h["command"])
    ours = [c for c in cmds if owns_command(c)]
    if not ours:
        bad.append("`hooks.UserPromptSubmit` runs no command from this file (%s) — found %s"
                   % (os.path.basename(self_path), (", ".join(repr(c) for c in cmds) or "no command hook at all")))

    # i3 — exactly one of ours per event. Two entries inject the anchor TWICE per turn: double the
    # per-turn cost for no extra anchoring, and the usual cause is an install that appended instead of
    # replacing. This is a real defect, not a tidiness note.
    if len(ours) > 1:
        bad.append("`hooks.UserPromptSubmit` runs this file %d times — the anchor would be injected "
                   "once per entry, every turn. Re-run `install`, which replaces rather than appends."
                   % len(ours))

    # i4 — the command points at a file that EXISTS. A hook whose target is missing fails on every
    # turn, and a failing hook injects nothing: the session runs unanchored while the settings file
    # goes on looking correct. The usual cause is a path from a different checkout.
    for cmd in ours + [c for c in cmds if not owns_command(c)]:
        target = _hook_target(cmd)
        if target and not os.path.isfile(target):
            bad.append("the hook command points at %r, which does not exist — it would fail on every "
                       "turn and inject nothing. (Re-run `install` to rewrite it with the correct "
                       "path.)" % target)

    # i5 — the anchor is not installed under an AUTO-LOADED filename. This one is about blast radius,
    # not about the dispatcher: an auto-loaded settings.json re-anchors every claude in the repo,
    # including the worker, whose job is exactly what the anchor forbids (pair_loop.py:716).
    if os.path.basename(path) == "settings.json":
        bad.append("this hook is installed as %r, an auto-loaded settings filename — every `claude` "
                   "in this repo would be told it is the dispatcher, including the WORKER, whose job "
                   "is to Write the deliverable. Use a --settings file: %s" % (path, DEFAULT_SETTINGS))

    # i6 — #210's permission block, if this file is sharing the file with it, has survived the merge.
    # Reported as a failure of THIS document, because a merge that ate it is the single most likely
    # way this file could do damage, and "it was fine when I wrote it" is not something a later
    # reader can check without being told to.
    if "permissions" in doc:
        perms = doc.get("permissions")
        if not isinstance(perms, dict) or not isinstance(perms.get("deny"), list) or not perms["deny"]:
            bad.append("`permissions` is present but denies nothing — if ticket #210's capability "
                       "floor was here, it has been damaged. Re-run `capability_restriction.py "
                       "install --force`, then `dispatch_anti_drift.py install` (which merges).")
    return bad


def _hook_target(cmd):
    """The script path a hook command runs, or None. Mirrors `<python> <script> hook`."""
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return None
    for p in parts[1:]:
        if p.endswith(".py"):
            return p
    return None


def do_verify(a):
    """Audit the installed settings file. Exit 1 names every invariant it does not hold."""
    path = a.path or DEFAULT_SETTINGS
    if not os.path.isfile(path):
        raise Fault("no settings file at %s — nothing to verify. Run `install` first." % path)
    doc = read_settings(path)
    bad = verify_document(doc, path)
    print("verifying: %s" % path)
    prof, authoring, prof_path = dispatch_profile()
    if prof is None:
        print("  dispatch surface: UNKNOWN (could not read PROFILES from %s) — the anchor names "
              "`ticket_queue`; confirm it is still the dispatch role's queue tool." % prof_path)
    elif "ticket_queue" in prof:
        print("  dispatch surface: ok — `ticket_queue` is in the dispatch profile (%s), so the "
              "anchor's instruction to read the queue with mcp__%s__ticket_queue is live."
              % (os.path.basename(prof_path), MCP_SERVER))
    else:
        bad.append("the anchor tells the dispatcher to read the queue with `ticket_queue`, but that "
                   "tool is NOT in the dispatch profile (%s) — the instruction names a tool the "
                   "dispatcher does not have. Profile is: %s" % (prof_path, ", ".join(prof)))
    rules = deny_rules(doc)
    if rules is not None:
        print("  #210: the permission block is present (%d deny rule(s)) — verify it with "
              "`capability_restriction.py verify --path %s`." % (len(rules), path))
    elif "permissions" in doc:
        print("  #210: a `permissions` key is present but is not a block with a deny list (see the "
              "FAIL below).")
    if bad:
        print()
        for b in bad:
            print("  FAIL %s" % b)
        print()
        print("%d invariant(s) do not hold — the anchor is NOT reliably installed." % len(bad))
        return 1
    print()
    print("the anchor holds: the UserPromptSubmit hook runs this file exactly once per turn, its "
          "target exists, and nothing it shares the file with has been damaged.")
    return 0


# ── probe: re-derive the hook contract from the installed binary ──────────────────────────────────
# Each needle is a literal fragment of the shipped JavaScript. They are the enforcement points this
# module depends on — not paraphrases of the documentation, but the code that actually carries the
# anchor into the model's context. If one stops matching, the contract has moved in that version and
# the hook block should be re-read before it is trusted.
PROBES = [
    (b'case"UserPromptSubmit":u.additionalContext=e.hookSpecificOutput.additionalContext',
     "a UserPromptSubmit hook's `hookSpecificOutput.additionalContext` is read into the turn"),
    (b'v.literal("UserPromptSubmit"),additionalContext:v.string().optional()',
     "the UserPromptSubmit answer schema accepts `additionalContext` as a string"),
    (b'type:"hook_additional_context",content:F.additionalContexts,hookName:"UserPromptSubmit"',
     "that context is pushed into the message stream for the turn, tagged to the hook"),
    (b'additionalContext` - Text injected into model context',
     "the binary's own hook reference calls additionalContext \"Text injected into model context\""),
    (b'case"SessionStart":if(u.additionalContext=e.hookSpecificOutput.additionalContext',
     "SessionStart carries `additionalContext` the same way (the second event this file installs)"),
    (b'matcher:v.string().optional()',
     "a hook group's `matcher` is OPTIONAL — neither event this file installs takes one (the "
     "binary's own reference lists `-` in the matcher column for UserPromptSubmit and SessionStart), "
     "so `hook_block` omits it rather than inventing a pattern that would never be consulted"),
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
    overlap, so a needle straddling a chunk boundary is still found and a 240MB binary never has to be
    held in memory at once."""
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
    """Re-derive this module's claims about the hook contract from the installed binary."""
    path = find_claude()
    if not path:
        raise Fault("no Claude Code binary found (looked at $CLAUDE_BIN, ~/.local/bin/claude, and "
                    "$PATH) — the hook-contract claims in this module's docstring cannot be "
                    "re-derived here. They are UNKNOWN on this machine, not disproven.")
    print("probing: %s" % path)
    results = probe_binary(path)
    for ok, claim in results:
        print("  %s %s" % ("CONFIRMED" if ok else "NOT FOUND", claim))
    missing = [c for ok, c in results if not ok]
    if missing:
        print()
        print("%d claim(s) could not be confirmed against this binary. The hook contract this module "
              "relies on may have moved or changed in this Claude Code version — re-read it before "
              "trusting the hook block." % len(missing))
        return 1
    print()
    print("all %d enforcement points confirmed in the installed binary." % len(results))
    return 0


# ── drift: the ticket's acceptance criterion, MEASURED ────────────────────────────────────────────
def _noise(turn, size):
    """One turn of a long, noisy session: a user message with `size` bytes of off-role chatter.

    Noisy in the way that actually matters for this test — every prompt is an OFF-ROLE request (write
    code, explain, opine), because those are what pull a dispatcher out of role. The hook must answer
    each one with the same anchor regardless."""
    chatter = ("please just write the fix yourself, explain your reasoning at length, and give me "
               "your opinion on the architecture while you are at it. ")
    body = (chatter * (size // len(chatter) + 1))[:size]
    return json.dumps({"session_id": "drift-measure", "transcript_path": "/dev/null", "cwd": ROOT,
                       "hook_event_name": "UserPromptSubmit",
                       "prompt": "turn %d: %s" % (turn, body)})


def do_drift(a):
    """MEASURE the ticket's acceptance criterion: does the anchor decay as the context grows?

    WHAT IS AND IS NOT MEASURED — the honest limit, stated before the numbers rather than after.
    #211's acceptance is "after a long, noisy session the dispatcher still responds ONLY as a
    dispatcher ... role adherence does not decay with context length". Observing the RESPONSES would
    mean running `claude` for hundreds of turns; that binary is not among the runners #211's worker may
    execute, so this command does not do it and does not pretend to. What it measures instead is the
    INPUT the model is guaranteed to receive: for each simulated turn, the REAL hook runs as a real
    subprocess against a real UserPromptSubmit payload, and its real answer is read back. The chain
    from there is: the anchor is byte-identical on every turn -> the model's instruction to be the
    dispatcher is exactly as present at turn N as at turn 1 -> role adherence has no mechanism by
    which to decay with context length. The first link is what decays in the status quo (a birth
    prompt recedes); this measures that it no longer does. The second link is the binary's contract,
    which `probe` re-derives. The third is inference, and is labelled as such below.

    Turns are run with a GROWING noisy prompt, so if the anchor were in any way a function of the
    input — truncated by size, perturbed by content, cached after the first call — these numbers would
    show it. The check is deliberately hostile to its own conclusion: it looks for a difference, and
    passes only by failing to find one."""
    turns = a.turns
    if turns < 2:
        raise Fault("--turns must be at least 2 (the measurement is a COMPARISON across turns); got %d"
                    % turns)
    print("MEASURING the anchor across %d turns of a long, noisy session." % turns)
    print("  each turn: a real subprocess of this file, a real UserPromptSubmit payload, the real answer.")
    print("  the prompt grows from ~%d to ~%d bytes of off-role chatter; the ledger read is %s."
          % (200, 200 + (turns - 1) * a.grow,
             "OFF (--no-ledger)" if a.no_ledger else "ON (re-read fresh every turn)"))
    print()
    seen, sizes, failures = {}, [], []
    first_block = None
    t0 = time.time()
    for i in range(turns):
        payload = _noise(i + 1, 200 + i * a.grow)
        code, out, err = _run_hook(payload, no_ledger=a.no_ledger)
        if code != 0:
            failures.append("turn %d: the hook exited %d (stderr: %r)" % (i + 1, code, err[-160:]))
            continue
        ctx = ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext")
        if not isinstance(ctx, str) or not ctx:
            failures.append("turn %d: the hook emitted no additionalContext" % (i + 1))
            continue
        if DIRECTIVE not in ctx:
            failures.append("turn %d: the directive is NOT in the injected context" % (i + 1))
            continue
        block = ctx.split("\n\nLEDGER DIGEST")[0]
        if first_block is None:
            first_block = block
        elif block != first_block:
            failures.append("turn %d: the directive block CHANGED (it must be byte-identical)" % (i + 1))
        seen[block] = seen.get(block, 0) + 1
        sizes.append(len(ctx))
    elapsed = time.time() - t0

    ok = not failures and len(seen) == 1 and len(sizes) == turns
    result = {
        "turns": turns, "distinct_directive_blocks": len(seen),
        "directive_present_every_turn": not failures and len(sizes) == turns,
        "anchor_bytes_min": min(sizes) if sizes else 0, "anchor_bytes_max": max(sizes) if sizes else 0,
        "seconds": round(elapsed, 2), "failures": failures, "invariant_holds": bool(ok),
    }
    if a.json:
        print(json.dumps(result, indent=2))
        return 0 if ok else 1
    print("  turns measured ................ %d" % turns)
    print("  directive present ............. %s" % ("every turn" if result["directive_present_every_turn"]
                                                    else "NOT on every turn"))
    print("  distinct directive blocks ..... %d  (1 == byte-identical on every turn)" % len(seen))
    print("  anchor size ................... %d..%d bytes  (bounded; independent of the prompt)"
          % (result["anchor_bytes_min"], result["anchor_bytes_max"]))
    print("  wall clock .................... %.2fs" % elapsed)
    print()
    if failures:
        for f in failures[:10]:
            print("  FAIL %s" % f)
        if len(failures) > 10:
            print("  ... and %d more" % (len(failures) - 10))
        print()
        print("the anchor is NOT invariant across context length — #211's acceptance does not hold.")
        return 1
    if len(seen) != 1:
        print("  FAIL the directive block took %d distinct forms across %d turns; it must take one."
              % (len(seen), turns))
        print()
        print("the anchor is NOT invariant across context length — #211's acceptance does not hold.")
        return 1
    print("MEASURED: over %d turns, with the prompt growing %dx, the dispatcher directive was injected"
          % (turns, (200 + (turns - 1) * a.grow) // 200))
    print("on EVERY turn, byte-identical every time, at a bounded size. The role the model is asked to")
    print("hold on turn %d is character-for-character the one it was asked to hold on turn 1, and it" % turns)
    print("arrives in the same position — immediately before the message — every time. There is no")
    print("mechanism left by which role adherence could decay with context length: what decays is")
    print("distance from the instruction, and this instruction's distance is constant.")
    print()
    print("NOT measured here: the model's actual reply. `claude` is not a runner this ticket's worker")
    print("may execute, so this measures the guaranteed INPUT, not the observed output. See `probe`")
    print("for the binary's own contract that additionalContext reaches the model's context.")
    return 0


# ── selftest ──────────────────────────────────────────────────────────────────────────────────────
def _run_hook(payload_text, no_ledger=False, extra=None):
    """Run the REAL hook, as Claude Code runs it: a subprocess of this file in `hook` mode, the payload
    on stdin, the answer on stdout.

    A subprocess and not a function call, deliberately. The thing that has to work is the COMMAND in
    the settings file; calling hook_output() in-process would prove the logic while leaving the argv,
    the stdin plumbing and the exit code — every part actually wired into the harness — untested.
    Returns (exit_code, parsed_stdout_or_None, stderr)."""
    argv = [sys.executable, SELF, "hook"] + (["--no-ledger"] if no_ledger else []) + (extra or [])
    p = subprocess.run(argv, input=payload_text, capture_output=True, text=True, timeout=60)
    out = None
    if p.stdout.strip():
        try:
            out = json.loads(p.stdout)
        except ValueError:
            out = {"__unparseable__": p.stdout}
    return p.returncode, out, p.stderr


def _ctx_of(out):
    """The injected context from a hook answer, or "" — the thing every hook check is really about."""
    return ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext") or ""


def _payload(prompt="route the queue"):
    return json.dumps({"session_id": "selftest", "transcript_path": "/dev/null", "cwd": ROOT,
                       "hook_event_name": "UserPromptSubmit", "prompt": prompt})


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


class _A(object):
    """A stand-in argparse namespace for driving a do_* handler from inside selftest."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


def do_selftest(_a):
    """Prove the deliverable. Prints one PASS/FAIL/SKIP line per check; exits 0 only if none FAILED.

    WHAT IS PROVEN BY EXECUTION vs BY READING — the honest limit, because the difference matters. The
    HOOK is executed for real (a1-a7: real subprocesses of this file, real UserPromptSubmit payloads,
    real answers read back), including its fail-soft path against a dead ledger endpoint. The MERGE is
    executed for real against a throwaway settings file, and the interlock with #210 is proven by
    running #210's OWN verify over the merged result (x1). `verify`'s invariants are executed and
    MUTATION-TESTED (v2-v6: each is shown to FAIL a document broken in exactly the way it exists to
    catch — a check that cannot fail proves nothing). The MODEL is not executed: `claude` is not a
    runner this ticket's worker may run, so the hook CONTRACT is established by reading the shipped
    binary, which p1 re-does here and reports as SKIP — never as PASS — when no binary is found.

    Writes NOTHING INTO THIS REPO: `install` is exercised against a throwaway temp directory, and r1
    lists the repo's own .claude/ before and after to prove it."""
    checks = []

    def ok(tag, cond, msg):
        checks.append((("PASS" if cond else "FAIL"), tag, msg))
        return cond

    def skip(tag, msg):
        checks.append(("SKIP", tag, msg))

    # ── a: THE ANCHOR + THE HOOK, executed for real ───────────────────────────────────────────────
    code, out, err = _run_hook(_payload(), no_ledger=True)
    ctx = _ctx_of(out)
    ok("a1", DIRECTIVE in ctx, "the hook injects the ticket's directive VERBATIM")
    ok("a2", code == 0 and not err.strip(), "the hook exits 0 with a clean stderr (a non-zero exit "
                                            "would read as a blocking error and reject the turn)")
    ok("a3", ((out or {}).get("hookSpecificOutput") or {}).get("hookEventName") == "UserPromptSubmit",
       "the answer echoes hookEventName=UserPromptSubmit (the branch that reads additionalContext is "
       "selected by it; the wrong name silently drops the context)")
    ok("a4", "mcp__%s__ticket_queue" % MCP_SERVER in ctx,
       "the anchor names the real tool the dispatcher reads the ledger with")

    # The hook must answer with the anchor for ANY payload — this is where it differs from #210's
    # PreToolUse hook, which stays silent unless it has something to refuse. Silence here = an
    # unanchored turn, so garbage in must still produce the anchor out.
    for tag, label, blob in (("a5", "an unparseable payload", "{not json at all"),
                             ("a6", "an empty payload", ""),
                             ("a7", "a payload that is a JSON array, not an object", "[1,2,3]")):
        c, o, _e = _run_hook(blob, no_ledger=True)
        ok(tag, c == 0 and DIRECTIVE in _ctx_of(o),
           "the hook still injects the anchor given %s (it fails OPEN: silence would be an "
           "unanchored turn)" % label)

    # ── l: the ledger — fresh every turn, and never able to take the anchor down ───────────────────
    dead = "http://127.0.0.1:9"          # discard port: refuses instantly, so this stays fast
    env_code, env_out, _e = _run_hook(_payload(), extra=["--ledger-timeout", "2"])
    live_ctx = _ctx_of(env_out)
    ok("l1", env_code == 0 and DIRECTIVE in live_ctx,
       "with the real ledger endpoint, the hook answers 0 and still carries the directive")
    ok("l2", "LEDGER DIGEST" in live_ctx,
       "the anchor carries a ledger digest section (state is rebuilt from the ledger each turn)")

    p = subprocess.run([sys.executable, SELF, "hook", "--ledger-timeout", "2"], input=_payload(),
                       capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, CONGRUENCY_URL=dead))
    dead_out = json.loads(p.stdout) if p.stdout.strip().startswith("{") else None
    dead_ctx = _ctx_of(dead_out)
    ok("l3", p.returncode == 0 and DIRECTIVE in dead_ctx,
       "with the ledger endpoint DEAD, the hook still exits 0 and the directive still arrives — the "
       "role anchor does not depend on the network")
    ok("l4", "UNAVAILABLE" in dead_ctx,
       "a dead ledger produces a NAMED unavailable notice, not a silently empty queue (which the "
       "dispatcher would read as 'nothing to route')")

    rows, lerr = ledger_queue(timeout=3)
    if lerr:
        skip("l5", "the live queue is unreachable here (%s) — the digest bound is untested" % lerr)
    else:
        big = ledger_digest(rows, None, head=QUEUE_HEAD)
        ok("l5", len(big) < 4000 and (len(rows) <= QUEUE_HEAD or "NOT shown" in big),
           "the digest of the live %d-ticket queue is BOUNDED (%d bytes) and says it is the head, "
           "not the whole (memory-minimization: the queue is re-read, not re-pasted)" % (len(rows), len(big)))

    # A digest must never misdescribe what it is showing. `rows[:-2]` is the queue's TAIL, and printing
    # it under "the N oldest" while the footer miscounts the rest is wrong output, not untidy output —
    # so the clamp is asserted on a fixture whose head and tail are distinguishable.
    fake = [{"id": i, "kind": "build", "status": "OPEN", "title": "t%d" % i} for i in range(1, 6)]
    for tag, head, label in (("l6", 0, "0"), ("l7", -2, "a negative head")):
        dig = ledger_digest(fake, None, head=head, now=0)
        ok(tag, "#1 " in dig and "#5 " not in dig and "the 1 oldest" in dig,
           "a digest asked for %s still shows the OLDEST ticket and says so (clamped) — it never "
           "prints the queue's tail under a heading that calls it the head" % label)

    # ── d: the dispatch surface, read from ticket #178's real table ────────────────────────────────
    prof, _authoring, prof_path = dispatch_profile()
    if prof is None:
        skip("d1", "ticket_api_mcp.py's PROFILES is unreadable (%s) — the anchor's tool name is "
                   "unverified here, which is UNKNOWN, not ok" % prof_path)
    else:
        ok("d1", "ticket_queue" in prof,
           "`ticket_queue` is really in the dispatch profile, so the anchor names a tool the "
           "dispatcher actually has (read from %s, not restated)" % os.path.basename(prof_path))

    # ── m: the merge — produce, don't erase (the interlock with #210) ──────────────────────────────
    tmp = tempfile.mkdtemp(prefix="anti_drift_selftest_")
    try:
        target = os.path.join(tmp, "dispatcher-settings.json")
        # A stand-in for #210's file: the shape that matters is a `permissions` block plus a
        # PreToolUse hook, which is exactly what the merge must not touch.
        prior = {"permissions": {"deny": ["Write", "Edit", "Bash"], "allow": ["Read"],
                                 "disableBypassPermissionsMode": "disable"},
                 "hooks": {"PreToolUse": [{"matcher": "Write|Edit",
                                           "hooks": [{"type": "command",
                                                      "command": "python3 capability_restriction.py hook",
                                                      "timeout": 10}]}]}}
        with open(target, "w") as fh:
            json.dump(prior, fh)
        _quietly(do_install, _A(path=target))
        merged = json.load(open(target))
        ok("m1", merged.get("permissions") == prior["permissions"],
           "install PRESERVES #210's permission block byte-for-byte (a naive overwrite would delete "
           "the capability floor — the one way this file could do real damage)")
        ok("m2", merged["hooks"].get("PreToolUse") == prior["hooks"]["PreToolUse"],
           "install PRESERVES #210's PreToolUse hook entry untouched")
        ok("m2b", "UserPromptSubmit" in merged["hooks"] and "SessionStart" in merged["hooks"],
           "install adds both of this file's events")
        _quietly(do_install, _A(path=target))
        twice = json.load(open(target))
        ok("m3", twice == merged,
           "install is IDEMPOTENT — installing twice yields the same document (an appending install "
           "would inject the anchor twice per turn, doubling its cost for no benefit)")
        ours = [h for g in twice["hooks"]["UserPromptSubmit"] for h in (g.get("hooks") or [])
                if owns_command(h.get("command"))]
        ok("m4", len(ours) == 1, "...and exactly one entry on UserPromptSubmit runs this file")
        ok("m5", verify_document(twice, target) == [], "`verify` passes the document install writes")

        # ── x: the interlock, proven with #210's OWN verify rather than this file's opinion of it ──
        cap = os.path.join(TOOLS, "capability_restriction.py")
        if not os.path.isfile(cap):
            skip("x1", "capability_restriction.py (#210) is not in this checkout — the interlock is "
                       "untested here")
        else:
            real = os.path.join(tmp, "real-210.json")
            r = subprocess.run([sys.executable, cap, "install", "--path", real],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                skip("x1", "could not stage #210's real settings file (exit %d) — interlock untested"
                     % r.returncode)
            else:
                _quietly(do_install, _A(path=real))
                v = subprocess.run([sys.executable, cap, "verify", "--path", real],
                                   capture_output=True, text=True, timeout=60)
                ok("x1", v.returncode == 0,
                   "after THIS file merges its hooks into #210's REAL settings file, #210's OWN "
                   "`verify` still passes it (exit %d) — the two mechanisms share one file and "
                   "neither breaks the other" % v.returncode)
                ok("x2", verify_document(json.load(open(real)), real) == [],
                   "...and this file's `verify` passes the same merged document")

        # ── n: the merge's blast radius — what it must NOT touch, and what it must not crash on ────
        # A hook that merely NAMES this file is somebody else's. Substring-matching the command would
        # delete it while the receipt claimed everything was preserved.
        third = os.path.join(tmp, "third-party.json")
        alien = {"type": "command",
                 "command": 'python3 /opt/audit/logger.py --note "re-anchored by %s"'
                            % os.path.basename(SELF),
                 "timeout": 5}
        json.dump({"hooks": {"UserPromptSubmit": [{"hooks": [dict(alien)]}]}}, open(third, "w"))
        _quietly(do_install, _A(path=third))
        got = [h for g in json.load(open(third))["hooks"]["UserPromptSubmit"]
               for h in (g.get("hooks") or [])]
        ok("n1", any(h == alien for h in got),
           "install PRESERVES a third-party hook whose command merely MENTIONS this file's name "
           "(ownership is decided by the script the command RUNS, never by a substring)")
        ok("n2", sum(1 for h in got if owns_command(h.get("command"))) == 1,
           "...while still adding exactly one entry of its own alongside it")

        # The reporting lines in `install`/`verify` must survive a `permissions` they cannot read —
        # that shape is exactly what verify's i6 exists to REPORT, so crashing on it would make the
        # diagnostic unreachable for the only case it was written for.
        for tag, shape, label in (("n3", ["Write", "Edit"], "a LIST"), ("n4", "Write", "a STRING")):
            weird = os.path.join(tmp, "weird-perms-%s.json" % tag)
            json.dump({"permissions": shape,
                       "hooks": {"UserPromptSubmit": []}}, open(weird, "w"))
            i = subprocess.run([sys.executable, SELF, "install", "--path", weird],
                               capture_output=True, text=True, timeout=60)
            v = subprocess.run([sys.executable, SELF, "verify", "--path", weird],
                               capture_output=True, text=True, timeout=60)
            ok(tag, i.returncode == 0 and v.returncode == 1 and "Traceback" not in (i.stderr + v.stderr),
               "a `permissions` that is %s does not crash install (exit %d, want 0) or verify (exit "
               "%d, want 1 — the i6 FAIL must be reachable for the shape it exists to catch)"
               % (label, i.returncode, v.returncode))

        # The hook must never be argued out of anchoring by its own flags.
        for tag, flag in (("n5", ["--queue-head", "0"]), ("n6", ["--ledger-timeout", "0"])):
            c, o, _e = _run_hook(_payload(), no_ledger=True, extra=flag)
            ok(tag, c == 0 and DIRECTIVE in _ctx_of(o),
               "the hook CLAMPS a nonsense %s and still exits 0 with the anchor (refusing it would "
               "mean an unanchored turn, which is the failure this file exists to prevent)" % flag[0])

        # ── v: `verify`'s invariants, MUTATION-TESTED so they cannot rot into a rubber stamp ───────
        good = json.load(open(target))
        ok("v1", verify_document(good, target) == [], "verify PASSES a correct document")

        broke = json.loads(json.dumps(good))
        del broke["hooks"]["UserPromptSubmit"]
        ok("v2", verify_document(broke, target) != [],
           "verify FAILS a document with no UserPromptSubmit hook (SessionStart alone injects once, "
           "then recedes exactly like the birth prompt it replaced)")

        broke = json.loads(json.dumps(good))
        for g in broke["hooks"]["UserPromptSubmit"]:
            for h in g.get("hooks") or []:
                h["command"] = "python3 /somewhere/else/other_hook.py hook"
        ok("v3", verify_document(broke, target) != [],
           "verify FAILS a UserPromptSubmit hook that runs someone else's command")

        broke = json.loads(json.dumps(good))
        broke["hooks"]["UserPromptSubmit"] = broke["hooks"]["UserPromptSubmit"] * 2
        ok("v4", verify_document(broke, target) != [],
           "verify FAILS a duplicated entry (the anchor would be injected twice every turn)")

        broke = json.loads(json.dumps(good))
        for g in broke["hooks"]["UserPromptSubmit"]:
            for h in g.get("hooks") or []:
                h["command"] = "%s /nonexistent/%s hook" % (sys.executable, os.path.basename(SELF))
        ok("v5", verify_document(broke, target) != [],
           "verify FAILS a hook command whose target file does not exist (it would fail every turn "
           "and inject nothing, while the settings file went on looking correct)")

        ok("v6", verify_document(good, os.path.join(tmp, "settings.json")) != [],
           "verify FAILS the anchor installed under the auto-loaded name `settings.json` (it would "
           "re-anchor the WORKER as the dispatcher, whose job is exactly what the anchor forbids)")

        broke = json.loads(json.dumps(good))
        broke["permissions"] = {"deny": []}
        ok("v7", verify_document(broke, target) != [],
           "verify FAILS a document whose permission block has been emptied — if #210's floor was "
           "here, a merge that ate it is reported rather than left for a reader to notice")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ── r: no forbidden side effect (ticket #153's lesson: prove it in isolation) ──────────────────
    dot_claude = os.path.join(ROOT, ".claude")
    before = _tree(dot_claude) if os.path.isdir(dot_claude) else set()
    existed = os.path.isdir(dot_claude)
    _quietly(do_anchor, _A(no_ledger=True, ledger_timeout=2, queue_head=QUEUE_HEAD))
    _run_hook(_payload(), no_ledger=True)
    _quietly(do_block, _A(json=False))
    after = _tree(dot_claude) if os.path.isdir(dot_claude) else set()
    ok("r1", before == after and (existed or not os.path.isdir(dot_claude)),
       "anchor/hook/block create NO file in the repo — %s listed before and after one run of each, "
       "with nothing else touching it" % (dot_claude if existed else "<repo>/.claude (absent, still absent)"))
    ok("r2", not os.path.exists(os.path.join(TOOLS, "__pycache__", "dispatch_anti_drift.pyc"))
       and not any(n.startswith("dispatch_anti_drift") for n in
                   (os.listdir(os.path.join(TOOLS, "__pycache__"))
                    if os.path.isdir(os.path.join(TOOLS, "__pycache__")) else [])),
       "...not even a bytecode cache entry (sys.dont_write_bytecode is set before any import)")

    # ── p: the hook contract, re-derived from the installed binary ─────────────────────────────────
    binpath = find_claude()
    if not binpath:
        skip("p1", "no Claude Code binary found — the hook contract is UNKNOWN on this machine, "
                   "neither confirmed nor disproven (run `probe` where one is installed)")
    else:
        results = probe_binary(binpath)
        missing = [c for good_, c in results if not good_]
        ok("p1", not missing, "all %d hook-contract enforcement points are confirmed in the installed "
                              "binary (%s)" % (len(results), os.path.basename(binpath)))

    # ── report ────────────────────────────────────────────────────────────────────────────────────
    for state, tag, msg in checks:
        print("%-4s %-4s %s" % (state, tag, msg))
    failed = [c for c in checks if c[0] == "FAIL"]
    skipped = [c for c in checks if c[0] == "SKIP"]
    print()
    print("%d checks: %d passed, %d failed, %d skipped"
          % (len(checks), len(checks) - len(failed) - len(skipped), len(failed), len(skipped)))
    if failed:
        print("selftest FAILED — the role anchor does not hold as written.")
        return 1
    print("selftest PASSED — the hook injects the dispatcher directive verbatim on every turn "
          "(executed here), rebuilds state from the ledger and survives its loss (executed here), "
          "and merges into #210's settings file without breaking its floor (proven with #210's own "
          "verify). Run `drift` for the acceptance measurement across context length.")
    return 0


# ── cli ───────────────────────────────────────────────────────────────────────────────────────────
COMMANDS = {"directive": do_directive, "anchor": do_anchor, "profile": do_profile, "block": do_block,
            "settings": do_settings, "argv": do_argv, "install": do_install, "verify": do_verify,
            "hook": do_hook, "drift": do_drift, "probe": do_probe, "selftest": do_selftest}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="dispatch_anti_drift.py",
        description="The dispatcher's role anchor (ticket #211): a UserPromptSubmit hook that "
                    "re-injects the dispatcher directive on EVERY turn and rebuilds the queue from "
                    "the ledger, so role adherence cannot decay as context grows. Emits the hook, "
                    "merges it into the dispatcher settings file, IS the hook, and measures it.",
        epilog="commands: " + ", ".join(sorted(COMMANDS)))
    ap.add_argument("command", nargs="?", help="one of: " + ", ".join(sorted(COMMANDS)))
    ap.add_argument("--json", action="store_true", help="block/drift: print bare JSON and nothing else")
    ap.add_argument("--path", help="install/verify/settings/argv: the settings file (default: %s)"
                                   % DEFAULT_SETTINGS)
    ap.add_argument("--no-ledger", action="store_true",
                    help="anchor/hook/drift: skip the ledger read; emit the offline anchor alone")
    ap.add_argument("--ledger-timeout", type=float, default=LEDGER_TIMEOUT, metavar="SECS",
                    help="anchor/hook: seconds for the ledger read before it fails soft (default: %s)"
                         % LEDGER_TIMEOUT)
    ap.add_argument("--queue-head", type=int, default=QUEUE_HEAD, metavar="N",
                    help="anchor/hook: how many queued tickets the digest names (default: %s)" % QUEUE_HEAD)
    ap.add_argument("--diff", action="store_true",
                    help="profile: print the registered profile next to the minimal one, with sizes")
    ap.add_argument("--register-argv", action="store_true",
                    help="profile: print the agent.register call that would install the minimal profile")
    ap.add_argument("--turns", type=int, default=50, metavar="N",
                    help="drift: how many turns of a noisy session to measure (default: 50)")
    ap.add_argument("--grow", type=int, default=400, metavar="BYTES",
                    help="drift: how much the noisy prompt grows per turn (default: 400)")
    a = ap.parse_args(argv)

    if a.path is not None and not a.path.strip():
        # `--path ""` would fall through `a.path or DEFAULT_SETTINGS` to the DEFAULT and write into
        # the repo — a caller who named a path, however emptily, must never have a different file
        # written instead of the one they asked for.
        ap.error("--path is empty. Give a real path, or omit --path to use the default (%s)."
                 % DEFAULT_SETTINGS)

    # A non-positive --queue-head / --ledger-timeout has no sensible reading, and is rejected here —
    # EXCEPT for `hook`. The hook's contract is that it ALWAYS exits 0 with an anchor, because a
    # non-zero exit is read as a blocking error and a turn with no anchor is this ticket's whole
    # failure mode. `ap.error` exits 2 before the command is ever dispatched, so validating the hook
    # here would break the one invariant that matters most, on the one command that must not break.
    # `do_hook` therefore CLAMPS its own inputs instead of refusing them: worse settings, still
    # anchored. Every other command refuses, because for them exit 2 is just a usage failure.
    if a.command != "hook":
        if a.queue_head < 1:
            ap.error("--queue-head must be at least 1 (got %d): a digest of 0 tickets says nothing, "
                     "and a negative head would print the queue's TAIL under a heading that calls it "
                     "the head." % a.queue_head)
        if a.ledger_timeout <= 0:
            ap.error("--ledger-timeout must be greater than 0 (got %g): a non-positive timeout cannot "
                     "complete a read, so every turn would fall back to the UNAVAILABLE notice. Use "
                     "--no-ledger if that is what you want." % a.ledger_timeout)

    if not a.command:
        ap.print_help()
        print()
        print("Nothing was run. Start with `anchor` to see what the hook injects, `drift` to measure "
              "it across context length, or `selftest` to prove it.")
        return 2
    fn = COMMANDS.get(a.command)
    if not fn:
        print("dispatch_anti_drift: unknown command %r — expected one of: %s"
              % (a.command, ", ".join(sorted(COMMANDS))))
        return 2
    return fn(a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as e:
        print("dispatch_anti_drift: %s" % e)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(2)
    except Exception as e:  # noqa: BLE001 — note-for-claude: file a report, then fail on ONE line
        bug_report("main", e, "python3 %s %s" % (SELF, " ".join(sys.argv[1:])), e)
        print("dispatch_anti_drift: unexpected failure (%s: %s) — a timestamped bug report was filed "
              "to the registry's bug_reports sink." % (type(e).__name__, e))
        sys.exit(2)
