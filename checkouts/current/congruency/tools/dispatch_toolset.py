#!/usr/bin/env python3
"""dispatch_toolset.py — the DISPATCH TOOL-SET: the MCP server `dispatch-tools`, which moves the
dispatcher's cognition OUT of the model and INTO deterministic tools (ticket #209).

THE POINT. Routing the queue used to be a JUDGEMENT CALL: `pair_loop.py --dispatch` hands dispatch-01
(an LLM) the whole queue plus DISPATCH_RULES and asks it to decide run/skip/stop per ticket
(pair_loop.py, `DISPATCH_RULES` and `do_dispatch`). That model must hold the rules, the queue and what
it already did in its head. THIS server deletes that job: every rule below is CODE, every input is read
from the DURABLE LEDGER on each call, and the dispatcher becomes a thin driver that calls tools in a
fixed cadence and reads their answers. Nothing is remembered between calls — there is nothing TO
remember, because no tool has state and every tool re-derives its answer from the ledger.

WHAT AN MCP SERVER IS HERE: a process speaking JSON-RPC 2.0 over stdin/stdout, one JSON object per
line. A client calls `tools/list` to learn what it may do and `tools/call` to do it. This file
implements that protocol with the STANDARD LIBRARY ALONE — the repo is stdlib-only (DEPENDENCIES.md:
"setup.py is stdlib-only ... no third-party packages, no pip install"), so no `mcp` SDK is imported.
The protocol shape mirrors the repo's existing bridge, `tools/ticket_api_mcp.py`.

THE FIVE TOOLS (each DETERMINISTIC: same ledger state in, same answer out; no model, no spawn to
decide anything, no randomness, no clock-dependent branch):

    next_ready_ticket()  apply the ready-rules to the queue; return the ONE pick, or idle.
    capacity()           pairs running right now vs the configured cap.
    dispatch(ticket)     kind it if needed, then SPAWN the pair (or QUEUE it when at capacity).
    requeue_chains()     report the self-repopulating chains' live heads (index-watch / forge factory).
    harvest()            file the distilled lesson for settled tickets that ran a pair.

TERMS — defined at first use, because this file is read without its author present.

  * THE LEDGER is the governed REST surface (`rest.php?route=...`): the tickets, their journal,
    manifest, kinds, edges and agents. It is the ONLY place these tools read decision state from. No
    tool holds a SQL pen; every read and write is an existing route (each is cited at its use below).
  * THE QUEUE is route `ticket.queue`: `upper(status) IN ('OPEN','REQUESTED')`, oldest id first
    (migrations/0032_dispatch_routes.sql:7). A ticket `ticket.create` mints is REQUESTED, so new work
    is in the queue immediately.
  * IN FLIGHT / CLAIMED. When a pair is dispatched, pair_loop sets the ticket ACTIVE
    (`process_status` -> ACTIVE, pair_loop.py, in the per-round `pair()` step). ACTIVE is NOT
    OPEN/REQUESTED, so a dispatched ticket LEAVES the queue by itself — checked against the record,
    not assumed (VERIFIED, v1). That alone is not quite enough, because pair_loop sets ACTIVE only
    AFTER the pair has started; R3(b) closes the gap.
  * A KIND is the ticket's classification (`ticket_kinds`); `kind.roster` gives each kind's PATTERN —
    `pair` (an adversarial worker+adversary) or `solo`. Today the pair kinds are bet, bug, build and
    documentation. `pair_loop.py` REFUSES a non-pair kind ("kind %r is not a pair kind — the loop
    harnesses pairs"), which is why rule R1 below demands one. `kind` is SET-ONCE: NULL -> value is
    allowed, any later change aborts (tg_tickets_immutable_identity,
    migrations/0029_ticket_authorization.sql:111-117).
  * A STOP TICKET is a `kind=stop` ticket aimed at a target by a `stops` edge (the stop is the edge's
    PARENT, the target its CHILD). Route `ticket.stops` counts ACTIVE (unreleased) stops aimed at a
    ticket OR ANY ANCESTOR, walking `spawned` edges up; a `starts` edge aimed at the stop releases it
    (migrations/0030_pair_loop_routes.sql:21-26). active_stops > 0 means HALT: the ticket authorizes
    nothing. A stop is a BRAKE, not an eraser — a halted ticket is still OPEN.
  * SUPERSEDED means a `supersedes` edge names this ticket as its CHILD: the superseding ticket
    (the edge's PARENT) "owns the predecessor it replaced" (migrations/0012_ticket_edges.sql:1-4).
    The replacement carries the work; rebuilding the predecessor would rebuild retired work.
  * THE DELIVERABLE is the ONE repo-relative file the pair must produce. `pair_loop.py` cannot run
    without it (`ap.error("--deliverable is required to run the pair")`).
  * SETTLED means status DONE. Only a real pair through a real merge gets there — the db itself
    refuses DONE on a pair-kind ticket without two distinct agents in two distinct roles
    (tg_tickets_pair_completion, migrations/0029_ticket_authorization.sql:133-140).

THE READY-RULES — the whole of the "should I run this?" judgement, as code. `next_ready_ticket` walks
the queue OLDEST FIRST (the route's own `ORDER BY id`) and returns the FIRST ticket that passes ALL
four rules, in this fixed order. Every rejection is counted and reported, so an idle answer always
says WHY rather than merely "nothing to do".

  R1 KINDED       — the ticket has a kind AND that kind's pattern is `pair` (kind.roster). An
                    unkinded ticket is not ready because CHOOSING a kind is a judgement, and this
                    server does not judge; `dispatch(ticket, kind=...)` is where a kind is supplied
                    explicitly. Solo and control kinds (stop/start) are not pair work, and pair_loop
                    refuses them.
  R2 NOT STOPPED  — `ticket.stops` reports active_stops == 0 (the brake, checked before anything).
  R3 DELIVERABLE-FILE FREE — both halves of "free":
                    (a) FREE OF A DELIVERED FILE: the ticket's manifest (`ticket.manifest`) holds no
                        recorded artifact. A ticket that already delivered is not re-dispatched.
                    (b) ITS FILE IS UNCLAIMED, in both directions: the ticket is not ITSELF already
                        running, and — if a deliverable is DECLARED for it (see DECLARING A
                        DELIVERABLE) — no OTHER running ticket declares the same path. Two pairs
                        writing one file collide at merge (`merge_to_base` aborts and the ticket
                        stays open), so a claimed path is not ready. The self-check closes a real
                        double-dispatch window: pair_loop sets a ticket ACTIVE — the write that
                        removes it from the queue — only AFTER its child has started, so between the
                        spawn and that write the ticket is still in the queue; its WORKTREE, however,
                        exists from the moment the pair opens it, so that is the earlier, safer
                        signal. A ticket with no declaration claims no path and passes the rest of (b).
  R4 DEPS MET     — the ticket is not SUPERSEDED. This is the only dependency the ledger can state:
                    the edge kinds that exist are `stops`, `spawned` and `supersedes` (verified
                    against the live record — those three are the only kinds present), and there is
                    NO `depends`/`blocks` edge kind in the schema. `stops` is R2's brake; `spawned` is
                    ancestry, not a dependency (a spawned successor never waits on its parent — the
                    parent spawning it is what authorizes it). So "deps met" = "not retired by a
                    successor". This rule is not theoretical — it skips dozens of live tickets
                    (VERIFIED, v5). Finding them all means enumerating parents across EVERY ticket id,
                    not just the open ones: see superseded_ids for why a cheaper queue-only scan
                    silently hands retired tickets to a pair, and max_ticket_id for how the scan's
                    upper bound is checked rather than guessed.

DECLARING A DELIVERABLE — how the deliverable survives a cold context. The ledger carries it, marked
machine-readably with `dispatch-deliverable:` (the convention index_watch.py already uses for its own
`index-watch-predecessor:` / `index-watch-mark:` body lines). It is read from, in order:

    1. the ticket BODY   — a line `dispatch-deliverable: <repo-relative-path>`; a ticket can be minted
                           with its deliverable already declared.
    2. the ticket JOURNAL — the most recent `dispatch-deliverable: <path>` progress note. `dispatch`
                           WRITES this note (route `ticket.progress`) the first time it is told a
                           path, so the choice is made ONCE and is durable from then on.

That is what makes the ACCEPTANCE hold: `dispatch(ticket=N)` with no path re-reads the declaration
from the ledger, so a dispatcher with a COLD context — no memory of what it chose last time — routes
the same ticket to the same file. A ticket with no declaration anywhere is REFUSED by name (never
guessed at): inventing a path is exactly the cognition this ticket removes.

CAPACITY, AND WHY IT IS NOT READ FROM THE LEDGER. Every DECISION input above comes from the ledger.
"How many pairs are running RIGHT NOW" cannot: THE LEDGER CANNOT TELL A LIVE RUN FROM A CRASHED ONE.
A pair that dies leaves its ticket exactly as a running one does — dispatched, unsettled — so any
ledger-derived count includes every run that ever died and the dispatcher would be at capacity
forever. That is not a hypothetical (VERIFIED, v2: dispatched-but-unsettled over-counts the truth by
more than twenty to one).

So `capacity` counts the thing that IS the running pair: its git WORKTREE. pair_loop gives every
in-flight ticket its own worktree (`ticket/<id>`, under the registry's `branch_per_ticket.worktrees`
directory) and REAPS it when the ticket settles, so the worktree exists for exactly the pair's life.
`git worktree list` is read-only, needs no ledger, and reports the truth (VERIFIED, v3).

A worktree kept by a FAILED round counts as running, and that is correct, not a leak: the ticket is
mid-flight, its branch holds that round's commits, and it is not free capacity — pair_loop keeps the
branch and worktree precisely so the next round resumes there.

USAGE

    python3 dispatch_toolset.py --serve                    # speak MCP on stdio (the 5 tools)
    python3 dispatch_toolset.py --tools                    # print the tool list and exit
    python3 dispatch_toolset.py --call next_ready_ticket   # run ONE tool against the LIVE ledger
    python3 dispatch_toolset.py --call capacity
    python3 dispatch_toolset.py --call requeue_chains
    python3 dispatch_toolset.py --call harvest --arg limit=1 --dry-run
    python3 dispatch_toolset.py --call dispatch --arg ticket=<id> --dry-run
    python3 dispatch_toolset.py --call dispatch --arg ticket=<id> --arg deliverable=<path> --dry-run
    python3 dispatch_toolset.py --selftest                 # prove the acceptance; no db, no network

--call takes `--arg k=v` (repeatable; an all-digit value is parsed as an int) and prints the tool's
JSON result. It is the same code path `tools/call` takes, so what it prints is what an MCP client
gets. In the two dispatch lines, <id> is the ticket id `next_ready_ticket` just printed and <path> is
its deliverable — needed only when the ticket declares none yet (see DECLARING A DELIVERABLE); pass a
real id, since a non-integer is refused rather than guessed at.

SIDE EFFECTS, EXACTLY. THREE of the five tools — `next_ready_ticket`, `capacity` and `requeue_chains`
— are READ-ONLY always: they perform GETs only, write nothing to the ledger, and CREATE NO FILES (so
are `--tools` and `--help`). They take no dry_run because they have nothing to dry-run.

Only TWO tools can act, and only through governed routes:
    dispatch  may POST `ticket.kind` and `ticket.progress`, and start a `pair_loop.py` child (whose
              output appends to logs/, which is gitignored).
    harvest   may POST `ticket.lesson` — and, because it calls pair_loop.harvest_settled() rather than
              restating it, that function's own `agent.register` + `ticket.assign` for the scribe.
`dry_run=True` makes both of them read-only too: they report what they WOULD do and write nothing.

`--selftest` drives a FAKE in-memory ledger and a fake host: no db, no network, no spawn, no writes
into this repo, no files. This module writes NO bytecode (`sys.dont_write_bytecode` is set below,
before any local import), so importing the modules it reuses mints no `__pycache__` in the repo tree.
Every claim in this paragraph is checked before/after in isolation, not asserted.

VERIFIED ON THE LIVE RECORD (2026-07-15, read-only — nothing was written to run these). These are
DATED OBSERVATIONS of a moving queue, not standing facts: the counts below will drift as tickets
settle and are dispatched (they visibly did while this file was being written — see v3). What does NOT
drift is the reasoning each one supports, and every number here is reproducible with the read-only
commands above.

  v1  Every ticket ever dispatched had left the queue: 90 tickets carried a `forge-t<id>` agent and
      exactly 0 of them appeared in `ticket.queue`. (Supports IN FLIGHT / CLAIMED.)
  v2  Of those 90, 65 had no recorded artifact while only 3 pairs were actually running — a
      ledger-derived "running" would have reported 65 against a cap of 3. (Supports CAPACITY.)
  v3  `capacity()` named the 3 live pairs #207/#209/#210 against cap 3, i.e. AT CAPACITY, so
      `dispatch()` correctly QUEUED rather than spawned. Re-run an hour later it named #209/#211/#214
      and picked #212 — #207/#210 had settled and #211/#214 had been dispatched by someone else, and
      the tools tracked all of it with NO memory of the earlier answer. That is the acceptance
      demonstrating itself.
  v4  The queue held 149 tickets; `next_ready_ticket()` picked #211 in ~2s, having stepped over 31
      unkinded/solo tickets by R1.
  v5  47 queue tickets were superseded and correctly skipped by R4. A queue-only scan would have seen
      only 8 and handed the other 39 to a pair. (Supports R4 / superseded_ids.)
  v6  The queue topped out at #408 and the newest dispatched ticket was #409, yet #410 existed —
      so max_ticket_id's walk was already load-bearing. (Supports max_ticket_id.)
  v7  The only edge kinds present were `stops`, `spawned` and `supersedes`; the pair kinds were bet,
      bug, build and documentation. (Supports R4 and R1.)
  v8  `harvest(dry_run)` found #176 and #226 harvestable and skipped 53 settled tickets that never ran
      a tournament. `requeue_chains(dry_run)` reported the index-watch head #278 of 8 open members and
      the forge-factory head #307 of 7 under #201.

Registry-gated per note-for-claude: walks UP to registry.json and refuses to run without it (the cap
and the worktrees directory are read from it — config as data, never hardcoded here). Any unexpected
exception files a timestamped Variant-A bug report to the registry's `bug_reports` sink.

Exit codes (each prints ONE line, never a traceback):
    0  served cleanly / --tools / --call succeeded / --selftest: every check PASSED
    1  --selftest: at least one check FAILED / --call: the tool REFUSED (a stated reason, not a crash)
    2  usage or configuration error
"""
# NO BYTECODE CACHE — set BEFORE any local import below. Python writes a module's .pyc while importing
# it, so requeue_chains importing index_watch.py would otherwise mint tools/__pycache__/*.pyc in the
# repo tree. The "creates no files" promise above is only true if this holds first.
import sys

sys.dont_write_bytecode = True

import argparse
import importlib.util
import json
import os
import re
import subprocess
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
CONG = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")   # newest first; we echo the client's if known
SERVER_NAME = "dispatch-tools"
SERVER_VERSION = "1.0.0"
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

# The machine-readable deliverable declaration (see DECLARING A DELIVERABLE in the module docstring).
# Same convention as index_watch.py's `index-watch-predecessor:` / `index-watch-mark:` body lines.
DELIV_MARK = "dispatch-deliverable:"
DELIV_RE = re.compile(r"^\s*%s\s*(\S+)\s*$" % re.escape(DELIV_MARK), re.I | re.M)

# How many CONSECUTIVE absent ids end the walk for the highest ticket id (see max_ticket_id). Ticket
# ids are a dense autoincrement, so a run this long with no ticket means the end of the table.
LOOKAHEAD = 25


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks).
    note-for-claude: every tool files a timestamped report when an exception is thrown."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "dispatch_toolset.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:], "note": "dispatch tool-set MCP",
            }) + "\n")
    except Exception:  # noqa: BLE001
        pass


class Refused(Exception):
    """A tool call the rules refuse. Carries the JSON-RPC error code the caller sees.
    A refusal is an ANSWER (a stated reason), never a crash."""

    def __init__(self, message, code=-32602):
        super().__init__(message)
        self.code = code


def config():
    """The `dispatch` and `branch_per_ticket` blocks of registry.json — config as data, not constants.
    Mirrors dispatch_schedule.py's config(), and the same defaults (cap 3)."""
    c = REGISTRY.get("dispatch") or {}
    b = REGISTRY.get("branch_per_ticket") or {}
    return {"cap": int(c.get("cap", 3)),
            "timeout": int(c.get("timeout", 480)),
            "worktrees": b.get("worktrees") or os.path.join(ROOT, ".git", "pair-worktrees")}


# ── THE LEDGER — every decision input, read through the governed surface (no SQL pen) ─────────────
class Ledger:
    """The governed REST surface. Call semantics + api-key loading mirror pair_loop.py's rest()."""

    def __init__(self, base=None, timeout=20):
        self.base = (base or CONG).rstrip("/")
        self.timeout = timeout

    @staticmethod
    def secret(name="CONGRUENCY_API_KEY"):
        """From .secrets/ats.env or the env — the same loader pair_loop.py and ticket_api_mcp.py use."""
        path = os.path.join(os.path.dirname(ROOT), ".secrets", "ats.env")
        if os.path.isfile(path):
            for line in open(path):
                if line.strip().startswith(name + "="):
                    return line.strip().split("=", 1)[1]
        return os.environ.get(name)

    def _open(self, url, data=None, method="GET"):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              "X-Api-Key": self.secret() or ""})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def rows(self, route, params=None):
        """A GET route -> its rows."""
        url = self.base + "/rest.php?route=" + route
        for k, v in (params or {}).items():
            url += "&%s=%s" % (k, urllib.request.quote(str(v)))
        out = self._open(url)
        if isinstance(out, dict) and out.get("error"):
            raise Refused("route %s failed: %s" % (route, out["error"]), code=-32603)
        return (out or {}).get("rows") or []

    def post(self, route, obj):
        """A POST route. Governed writes only — every caller cites the migration that defines it."""
        out = self._open(self.base + "/rest.php?route=" + route, data=json.dumps(obj).encode(),
                         method="POST")
        if isinstance(out, dict) and out.get("error"):
            raise Refused("route %s failed: %s" % (route, out["error"]), code=-32603)
        return out

    def ticket(self, tid):
        """One ticket row (id/kind/status/title/body/...), or {} if there is no such ticket.

        The same read pair_loop.py does before running a pair: `rest.php?api=tickets&id=<id>`. The
        queue route cannot see a non-OPEN ticket, so this is how a DISPATCHED or SETTLED ticket's
        status is read. An id that does not exist answers HTTP 404 (body `{"error": "not found"}`),
        which is an ANSWER — "no such ticket" — not a failure: max_ticket_id walks the id space and
        must be able to ask about ids past the end. Any OTHER HTTP error is a real fault and is
        raised, so a broken surface can never be misread as an empty table.
        """
        try:
            out = self._open(self.base + "/rest.php?api=tickets&id=%d" % int(tid))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
            raise Refused("reading ticket #%s failed: HTTP %s %s" % (tid, e.code, e.reason), code=-32603)
        return (out or {}).get("row") or {}


# ── THE HOST — the ONLY non-ledger state: which pairs are running, and starting one ───────────────
class Host:
    """Live pair worktrees + spawning pair_loop. See CAPACITY in the module docstring for why the
    running count comes from here and not from the ledger."""

    def __init__(self, root=None, worktrees=None):
        self.root = root or ROOT
        self.worktrees = worktrees or config()["worktrees"]

    def running_tickets(self):
        """Ticket ids with a live pair worktree, ascending.

        `git worktree list --porcelain` is read-only and creates nothing. A worktree counts only when
        BOTH: its branch is `ticket/<id>` (the name pair_loop derives from the ticket id alone — its
        branch_of()), and it sits under the registry's configured worktrees directory. The second test
        is what keeps unrelated worktrees (e.g. an editor's own under .git/ or .claude/) from being
        miscounted as running pairs.
        """
        try:
            out = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=self.root,
                                 capture_output=True, text=True, shell=False, timeout=30)
        except (OSError, subprocess.SubprocessError) as e:
            raise Refused("cannot list git worktrees in %s (%s) — capacity is unknown; refusing to "
                          "guess" % (self.root, e), code=-32603)
        if out.returncode != 0:
            raise Refused("git worktree list failed in %s: %s"
                          % (self.root, (out.stderr or out.stdout).strip()[-200:]), code=-32603)
        base, path, found = os.path.realpath(self.worktrees), None, set()
        for line in out.stdout.splitlines():
            if line.startswith("worktree "):
                path = line.split(" ", 1)[1].strip()
            elif line.startswith("branch ") and path:
                m = re.match(r"^refs/heads/ticket/(\d+)$", line.split(" ", 1)[1].strip())
                rp = os.path.realpath(path)
                if m and (rp == base or rp.startswith(base + os.sep)):
                    found.add(int(m.group(1)))
        return sorted(found)

    def spawn(self, argv, log_path):
        """Start a detached child and return its pid. The child is `pair_loop.py --ticket ...` — the
        SAME child pair_loop's own do_dispatch builds, so a dispatch from here and a dispatch from
        there are the same act. Its output is appended to logs/ (gitignored)."""
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        fh = open(log_path, "a")
        try:
            p = subprocess.Popen(argv, cwd=self.root, stdout=fh, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
        finally:
            fh.close()
        return p.pid


# ── ledger reads the rules are built from ────────────────────────────────────────────────────────
def pair_kinds(led):
    """The kinds whose pattern is `pair` (kind.roster, migrations/0029:...). pair_loop refuses any
    other kind, so only these can be dispatched to a pair."""
    return {k["kind"] for k in led.rows("kind.roster") if (k.get("pattern") or "") == "pair"}


def active_stops(led, tid):
    """The brake: unreleased stops aimed at this ticket or any ancestor (route ticket.stops,
    migrations/0030_pair_loop_routes.sql:21-26)."""
    r = led.rows("ticket.stops", {"ticket_id": tid})
    return int((r[0].get("active_stops") or 0) if r else 0)


def max_ticket_id(led, queue):
    """The highest ticket id that EXISTS, found from the ledger rather than assumed.

    Starts from the highest id the ledger already names — the queue, plus every ticket ever dispatched
    (each has a registered `forge-t<id>` agent) — and then WALKS UP, because a ticket that is neither
    open nor dispatched (settled by another route, or closed) is named by neither and would otherwise
    be invisible. `tickets.id` is a dense autoincrement (INTEGER PRIMARY KEY), so LOOKAHEAD
    consecutive absent ids mean the end of the table. Deterministic: the same ledger gives the same
    bound.

    The walk is not ceremony: a bound taken from the queue and the roster alone is ALREADY wrong on
    this record (VERIFIED, v6 — the queue topped out at #408 and the newest dispatched ticket was
    #409, yet #410 existed). ~25 cheap GETs turn a guessed margin into a checked fact.
    """
    ids = {int(t["id"]) for t in queue}
    ids |= {int(m.group(1)) for m in
            (re.match(r"^forge-t(\d+)$", str(a.get("agent_id") or "")) for a in led.rows("agent.roster"))
            if m}
    top = max(ids) if ids else 0
    probe, misses = top, 0
    while misses < LOOKAHEAD:
        probe += 1
        if led.ticket(probe):
            top, misses = probe, 0
        else:
            misses += 1
    return top


def superseded_ids(led, queue):
    """Ids that a `supersedes` edge names as its CHILD, i.e. tickets a successor has retired.

    `children.list` (migrations/0012_ticket_edges.sql:26-34) reads edges by PARENT and NO route reads
    them by child, so the only way to learn "who supersedes me" is to enumerate the possible parents
    and collect their children. The scan therefore covers EVERY ticket id, not just the open ones.

    Scanning only the QUEUE would be cheaper and is WRONG: a superseder does its job and then settles,
    so the moment it reaches DONE it leaves the queue — and its retired predecessor would look ready
    again and be rebuilt. That is not hypothetical (VERIFIED, v5: a queue-only scan sees 8 retired
    tickets where the full scan sees 47). The 39 it misses are retired by superseders that have
    already settled — #294 by the DONE #375, and #313/#314/#318/#321/#328/#334/#341/#345 all by the
    DONE #226 — and they are exactly the ones it would hand to a pair. Those examples do not go stale
    the way the counts do: the journal and the edges are append-only, so a `supersedes` edge is never
    withdrawn and a DONE ticket never un-settles.

    The scan runs 1..max_ticket_id() — about 430 GETs in ~2s at the size above — and
    `next_ready_ticket` builds it at most once per call, only if a ticket survives R1-R3.
    """
    out = {}
    for pid in range(1, max_ticket_id(led, queue) + 1):
        for c in led.rows("children.list", {"parent_id": pid}):
            if (c.get("kind") or "") == "supersedes":
                out.setdefault(int(c["child_id"]), []).append(pid)
    return out


def declared_deliverable(led, tid, body=None):
    """The deliverable DECLARED for a ticket, or None. Body first, then the newest journal note.
    See DECLARING A DELIVERABLE in the module docstring; the mark is DELIV_MARK."""
    if body is None:
        body = led.ticket(tid).get("body") or ""
    m = DELIV_RE.search(body or "")
    if m:
        return m.group(1)
    found = None
    for ev in led.rows("ticket.journal", {"ticket_id": tid}):     # ORDER BY ts, id -> last wins
        m = DELIV_RE.search(ev.get("note") or "")
        if m:
            found = m.group(1)
    return found


def claimed_deliverables(led, running):
    """{path: ticket} declared by the tickets that are RUNNING right now — the paths R3(b) protects."""
    out = {}
    for tid in running:
        d = declared_deliverable(led, tid)
        if d:
            out[d] = tid
    return out


# ── THE READY-RULES (R1-R4; the module docstring states them in prose) ────────────────────────────
def ready_reason(led, t, kinds, running_claims, superseded, running=()):
    """Apply R1-R4 to ONE queue ticket. Returns None if READY, else a (rule, why) rejection.

    Pure given its inputs, so the same ledger state always yields the same answer.

    `superseded` is the {child: [superseders]} map, or a CALLABLE returning it — R4's scan is the one
    expensive read here, so a caller can pass a memo that is only paid for if a ticket actually
    reaches R4 (see next_ready_ticket).
    """
    tid, kind = int(t["id"]), (t.get("kind") or "")
    if not kind:
        return ("R1-kinded", "no kind — a kind must be supplied explicitly (dispatch(kind=...)); "
                             "choosing one is a judgement this server does not make")
    if kind not in kinds:
        return ("R1-kinded", "kind %r is not a pair kind (pair kinds: %s) — pair_loop harnesses pairs"
                             % (kind, ", ".join(sorted(kinds)) or "(none)"))
    stops = active_stops(led, tid)
    if stops > 0:
        return ("R2-not-stopped", "%d active stop ticket(s) aim at it or an ancestor — HALT" % stops)
    if led.rows("ticket.manifest", {"ticket_id": tid}):
        return ("R3a-delivered", "its manifest already records a delivered artifact")
    if tid in set(running or ()):
        # Closes the double-dispatch window: pair_loop sets the ticket ACTIVE (which is what removes
        # it from the queue) only AFTER its child has started, so between the spawn and that write the
        # ticket is still OPEN/REQUESTED and would otherwise be picked and dispatched a SECOND time.
        # The worktree exists from the moment the pair opens it, so it is the earlier, safer signal.
        return ("R3b-claimed", "it is ALREADY RUNNING — a live pair worktree holds ticket/%d" % tid)
    deliv = declared_deliverable(led, tid, t.get("body"))
    if deliv and deliv in running_claims and running_claims[deliv] != tid:
        return ("R3b-claimed", "its deliverable %s is already being written by running ticket #%s — "
                               "two pairs on one file collide at merge" % (deliv, running_claims[deliv]))
    supers = superseded() if callable(superseded) else superseded
    if tid in supers:
        return ("R4-deps-met", "superseded by #%s — the successor owns the work"
                               % ", #".join(str(x) for x in supers[tid]))
    return None


def next_ready_ticket(led, host, args):
    """THE PICK: the oldest queue ticket that passes every ready-rule, or idle — with the reason.

    Walks `ticket.queue` in its own id order (oldest first) and stops at the FIRST ready ticket, so a
    healthy queue costs a handful of GETs. Every ticket it steps over is counted by the rule that
    rejected it, so `idle` is always explained rather than merely asserted.
    """
    queue = led.rows("ticket.queue")
    kinds = pair_kinds(led)
    running = host.running_tickets()
    claims = claimed_deliverables(led, running)
    rejected, examples, memo = {}, {}, []

    def supers():
        """R4's scan: the one expensive read. Built at most ONCE per call, and only when a ticket has
        actually survived R1-R3 — a queue of unkinded or halted tickets never pays for it."""
        if not memo:
            memo.append(superseded_ids(led, queue))
        return memo[0]

    for t in queue:
        why = ready_reason(led, t, kinds, claims, supers, running)
        if why is None:
            deliv = declared_deliverable(led, int(t["id"]), t.get("body"))
            return {"idle": False,
                    "pick": {"ticket": int(t["id"]), "kind": t.get("kind"), "title": t.get("title"),
                             "deliverable": deliv, "needs_deliverable": deliv is None},
                    "considered": len(queue), "rejected": rejected, "examples": examples,
                    "next_call": ("dispatch(ticket=%s)" % t["id"]) if deliv else
                                 ("dispatch(ticket=%s, deliverable=<repo-relative-path>) — no %s "
                                  "declaration on the ticket yet" % (t["id"], DELIV_MARK))}
        rule, detail = why
        rejected[rule] = rejected.get(rule, 0) + 1
        examples.setdefault(rule, "#%s: %s" % (t["id"], detail))
    return {"idle": True,
            "reason": "no queue ticket passes the ready-rules" if queue else "the queue is empty",
            "considered": len(queue), "rejected": rejected, "examples": examples}


def capacity(led, host, args):
    """RUNNING vs CAP. `running` is the live pair worktrees (see CAPACITY in the module docstring for
    why this one input is not ledger-derived); `cap` is registry.json's dispatch.cap."""
    cfg = config()
    running = host.running_tickets()
    return {"running": len(running), "cap": cfg["cap"], "free": max(0, cfg["cap"] - len(running)),
            "at_capacity": len(running) >= cfg["cap"], "running_tickets": running,
            "source": {"running": "git worktree list -> ticket/<id> worktrees under %s" % cfg["worktrees"],
                       "cap": "registry.json dispatch.cap"}}


def dispatch(led, host, args):
    """DISPATCH ONE TICKET: kind it if needed, declare its deliverable durably, then spawn the pair —
    or QUEUE it when at capacity.

    It re-applies the ready-rules to the named ticket rather than trusting the caller, so a stale or
    hand-typed id cannot slip past the brake. The BUILD CONTEXT (the ticket's branch `ticket/<id>` and
    its own git worktree) is created by pair_loop itself, which holds the git pen and journals the act
    as `forge-t<id>`; this server never touches git history — it starts the same child process
    pair_loop's own do_dispatch starts.

    dry_run=True reports the decision and writes NOTHING (no kind, no note, no child).
    """
    tid = args.get("ticket")
    if not isinstance(tid, int):
        raise Refused("ticket must be an integer ticket id")
    dry = bool(args.get("dry_run"))
    row = led.ticket(tid)
    if not row:
        raise Refused("no ticket #%s in the ledger" % tid)
    status = (row.get("status") or "").upper()
    if status not in ("OPEN", "REQUESTED"):
        raise Refused("ticket #%s is %s, not OPEN/REQUESTED — it is already dispatched or settled "
                      "(a dispatched ticket leaves the queue)" % (tid, status or "(no status)"))

    # ── kind if needed: set-once, so an already-kinded ticket is never re-kinded (the identity
    #    trigger would abort). Choosing a kind is a judgement; only an explicit one is accepted.
    kinds = pair_kinds(led)
    kind, want = row.get("kind") or "", args.get("kind")
    kinded = None
    if not kind:
        if not want:
            raise Refused("ticket #%s has no kind — supply one explicitly: dispatch(ticket=%s, "
                          "kind=<%s>). This server does not choose kinds."
                          % (tid, tid, "|".join(sorted(kinds)) or "pair-kind"))
        if want not in kinds:
            raise Refused("kind %r is not a pair kind (pair kinds: %s) — pair_loop harnesses pairs"
                          % (want, ", ".join(sorted(kinds)) or "(none)"))
        if not dry:
            led.post("ticket.kind", {"id": tid, "kind": want})     # 0030; set-once
        kind, kinded = want, want
        row["kind"] = want
    elif want and want != kind:
        raise Refused("ticket #%s is already kind %r — kind is SET-ONCE and the db refuses re-kinding "
                      "(to change course: stop + spawn a graft)" % (tid, kind))

    # ── the ready-rules, re-applied to THIS ticket (the caller is not trusted) ──
    running = host.running_tickets()
    claims = claimed_deliverables(led, running)
    queue = led.rows("ticket.queue")
    why = ready_reason(led, row, kinds, claims, superseded_ids(led, queue), running)
    if why:
        raise Refused("ticket #%s is not ready (%s): %s" % (tid, why[0], why[1]))

    # ── the deliverable: the caller's, else the ledger's declaration. Never invented. ──
    declared = declared_deliverable(led, tid, row.get("body"))
    deliv = args.get("deliverable") or declared
    if not deliv:
        raise Refused("ticket #%s declares no deliverable and none was supplied — call "
                      "dispatch(ticket=%s, deliverable=<repo-relative-path>) once, and it is recorded "
                      "on the journal as `%s <path>` so later cold-context calls need no memory."
                      % (tid, tid, DELIV_MARK))
    if os.path.isabs(deliv):
        raise Refused("deliverable must be repo-relative, not absolute: %r" % deliv)
    if deliv in claims:
        raise Refused("deliverable %s is already being written by running ticket #%s — two pairs on "
                      "one file collide at merge" % (deliv, claims[deliv]))
    declared_now = None
    if deliv != declared and not dry:
        # Declare it ONCE, durably, on the append-only journal (0029 ticket.progress). This is what a
        # later cold-context dispatch(ticket=N) reads back instead of remembering.
        led.post("ticket.progress", {"ticket_id": tid, "agent_id": DISPATCH_AGENT,
                                     "note": "%s %s" % (DELIV_MARK, deliv)})
        declared_now = deliv

    # ── capacity: spawn, or queue. Both are answers; neither is an error. ──
    cap = capacity(led, host, {})
    out = {"ticket": tid, "kind": kind, "deliverable": deliv, "kinded": kinded,
           "declared": declared_now, "capacity": {k: cap[k] for k in ("running", "cap", "free")},
           "dry_run": dry}
    if cap["at_capacity"]:
        out["action"] = "queued"
        out["reason"] = ("at capacity (%d/%d pairs running: %s) — NOT spawned. The ticket stays in the "
                         "queue; call dispatch again when capacity frees. Nothing to remember: the "
                         "queue and the worktrees are the state."
                         % (cap["running"], cap["cap"], ", ".join("#%d" % i for i in cap["running_tickets"])))
        if not dry:
            led.post("ticket.progress", {"ticket_id": tid, "agent_id": DISPATCH_AGENT,
                                         "note": "dispatch: queued — %s" % out["reason"]})
        return out
    argv = [sys.executable, os.path.join(TOOLS_DIR, "pair_loop.py"), "--ticket", str(tid),
            "--deliverable", deliv, "--timeout", str(config()["timeout"])]
    out["action"] = "spawned"
    out["command"] = " ".join(argv)
    if dry:
        out["action"] = "would-spawn"
        return out
    log = os.path.join(ROOT, "logs", "dispatch_toolset.log")
    out["pid"] = host.spawn(argv, log)
    out["log"] = os.path.relpath(log, ROOT)
    led.post("ticket.progress", {"ticket_id": tid, "agent_id": DISPATCH_AGENT,
                                 "note": "dispatch: spawned pair_loop on #%s -> %s (pid %s)"
                                         % (tid, deliv, out["pid"])})
    return out


# ── the chains: index-watch + the forge factory ───────────────────────────────────────────────────
def load_module(name, path):
    """Import a repo tool as a module, to READ ITS OWN CONSTANTS rather than restate them.

    This is dispatch_schedule.py's load_watch() pattern and for its reason: restating another tool's
    marks here would let this file drift out of agreement with the tool that mints them, which is
    exactly how a chain silently stops matching its own tickets.
    """
    if not os.path.isfile(path):
        raise Refused("no %s at %s — cannot read its chain marks" % (name, path), code=-32603)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        raise Refused("%s at %s did not load (%r)" % (name, path, e), code=-32603)
    return mod


def requeue_chains(led, host, args):
    """THE SELF-REPOPULATING CHAINS: report each chain's live HEAD so it is never left unrouted.

    A CHAIN is a sequence of tickets where each run SPAWNS its successor, so the chain never runs dry:

      index-watch — tools/index_watch.py: a run indexes the new code delta and spawns the next member,
                    whose body carries index_watch's own `index-watch-predecessor:` mark (BODY_PRED).
                    Members are recognised by ITS constants, imported here, never copied.
      forge factory — tools/forge_refactor_ticketer.py mints rewrite tickets, every one a `spawned`
                    child of its FACTORY_TICKET (also imported, not copied).

    THE HEAD is the chain's NEWEST open member — the only one worth routing (dispatch_schedule.py runs
    the head and never older members). This tool REPORTS the heads and whether each is ready; it does
    NOT settle, stop or re-kind anything, because a chain member is settled by its own run or its own
    pair, never by a router.

    It is READ-ONLY, deliberately. An earlier draft journaled "this is the head" on each call; but a
    dispatcher polls this every cadence and the journal is APPEND-ONLY, so that note could never be
    cleaned up — it would bury each head ticket's real history under identical polling noise. A report
    that changes nothing needs no record: the chain state IS the record, and re-reading it is free.

    Its answer composes with the others: a head that is `ready` is dispatched with dispatch(ticket=N).
    """
    queue = led.rows("ticket.queue")
    kinds, out = pair_kinds(led), []

    iw = load_module("index_watch", os.path.join(TOOLS_DIR, "index_watch.py"))
    members = [t for t in queue
               if iw.BODY_PRED in (t.get("body") or "") or iw.BODY_MARK in (t.get("body") or "")
               or (t.get("title") or "").startswith(iw.SUCCESSOR_TITLE.split("(successor")[0].strip())]
    out.append(_chain("index-watch", members, led, kinds, host))

    frt = load_module("forge_refactor_ticketer", os.path.join(TOOLS_DIR, "forge_refactor_ticketer.py"))
    kids = {int(c["child_id"]) for c in led.rows("children.list", {"parent_id": frt.FACTORY_TICKET})
            if (c.get("kind") or "") == "spawned"}
    out.append(_chain("forge-factory", [t for t in queue if int(t["id"]) in kids], led, kinds, host,
                      root=frt.FACTORY_TICKET))
    return {"chains": out,
            "note": "heads that are ready are dispatched with dispatch(ticket=<head>); this tool is "
                    "read-only and settles nothing — a chain member is settled by its own run or its "
                    "own pair"}


def _chain(name, members, led, kinds, host, root=None):
    """One chain's report: its open members, its HEAD (newest open), and whether the head is ready."""
    ids = sorted(int(t["id"]) for t in members)
    ch = {"chain": name, "root": root, "open_members": ids, "open": len(ids), "head": None,
          "ready": False, "status": ""}
    if not ids:
        ch["status"] = "no open members — the chain is dry (its next run reseeds it)"
        return ch
    head = max(ids)
    row = [t for t in members if int(t["id"]) == head][0]
    ch["head"], ch["head_kind"], ch["head_title"] = head, row.get("kind"), row.get("title")
    run = host.running_tickets()
    why = ready_reason(led, row, kinds, claimed_deliverables(led, run), {}, run)
    ch["ready"] = why is None
    ch["status"] = ("head #%d is READY to dispatch" % head if why is None
                    else "head #%d is not ready (%s): %s" % (head, why[0], why[1]))
    if len(ids) > 1:
        ch["status"] += ("; %d older open member(s) %s are NOT routed (the head is the live link)"
                         % (len(ids) - 1, ", ".join("#%d" % i for i in ids[:-1])))
    return ch


# ── harvest ───────────────────────────────────────────────────────────────────────────────────────
def harvest(led, host, args):
    """SAVE THE SETTLED WINNERS: for each settled ticket that ran a pair and has no lesson yet, file
    the distilled lesson on its journal, and report the winning artifact.

    THE TOURNAMENT is the ticket's adversarial rounds; THE WINNER is the artifact that passed and was
    recorded on the manifest (`work.record` -> a permanent UID) by pair_loop at settle. THE LESSON is
    what the record proves happened, distilled onto the journal as a `lesson` event
    (route ticket.lesson, migrations/0031_harvest_routes.sql:13-18) — the input every future worker
    reads through docs/PLAYBOOK.md. Memory an agent may keep is memory it FILED.

    The distillation is not restated here: it calls pair_loop.harvest_settled(), the same mechanical
    harvest the loop runs at settle, so a lesson filed here and one filed there are identical.

    WHICH TICKETS. Candidates are the DISPATCHED tickets (each has a registered `forge-t<id>` agent —
    agent.roster) that are DONE and carry no lesson yet (lessons.recent). A DONE ticket whose journal
    holds NO pair verdicts is SKIPPED, not failed: most settled tickets without a lesson were landed
    by other means and never ran a tournament, so there is nothing to distil and harvest_settled()
    rightly raises on them (VERIFIED, v8). Skipping them is reported, never silent.

    dry_run=True lists exactly what WOULD be harvested and writes nothing.
    """
    dry, limit = bool(args.get("dry_run")), args.get("limit")
    limit = int(limit) if isinstance(limit, int) and limit > 0 else 0
    done_ids = sorted({int(m.group(1)) for m in
                       (re.match(r"^forge-t(\d+)$", str(a.get("agent_id") or ""))
                        for a in led.rows("agent.roster")) if m})
    have = {int(l["ticket_id"]) for l in led.rows("lessons.recent")}
    harvested, skipped, winners = [], [], []
    for tid in done_ids:
        if limit and len(harvested) >= limit:
            break
        if tid in have:
            continue
        row = led.ticket(tid)
        if (row.get("status") or "").upper() != "DONE":
            continue                                   # not settled: its own pair will settle it
        j = led.rows("ticket.journal", {"ticket_id": tid})
        if not [e for e in j if e.get("event") == "progress" and "verdict:" in (e.get("note") or "")]:
            skipped.append({"ticket": tid, "why": "settled but ran no pair tournament (no verdicts on "
                                                  "its journal) — nothing to distil"})
            continue
        win = [{"uid": w.get("uid"), "kind": w.get("kind"), "ref": w.get("ref")}
               for w in led.rows("ticket.manifest", {"ticket_id": tid})]
        item = {"ticket": tid, "title": row.get("title"), "winner": win or None}
        if dry:
            item["would_file"] = "lesson (pair_loop.harvest_settled)"
        else:
            pl = load_module("pair_loop", os.path.join(TOOLS_DIR, "pair_loop.py"))
            pl.harvest_settled(tid)                    # the SAME mechanical harvest the loop runs
            item["filed"] = "lesson"
        harvested.append(item)
        winners += win
    return {"harvested": harvested, "skipped": skipped, "winners": winners,
            "already_harvested": len(have), "candidates": len(done_ids), "dry_run": dry}


DISPATCH_AGENT = "dispatch-01"      # the registered router these tools journal as (pair_loop's own)

# ── the MCP tool table: name -> (fn, properties, required, description) ───────────────────────────
TOOLS = {
    "next_ready_ticket": (
        next_ready_ticket, {}, [],
        "THE PICK: the oldest queue ticket passing every ready-rule (R1 kinded+pair, R2 not stopped, "
        "R3 deliverable-file free, R4 deps met/not superseded), or idle WITH the reason and per-rule "
        "rejection counts. Deterministic; reads the ledger; creates nothing."),
    "capacity": (
        capacity, {}, [],
        "pairs RUNNING right now (live ticket/<id> git worktrees) vs the configured cap "
        "(registry.json dispatch.cap): {running, cap, free, at_capacity, running_tickets}."),
    "dispatch": (
        dispatch,
        {"ticket": {"type": "integer", "description": "the ticket id to dispatch"},
         "deliverable": {"type": "string", "description": "repo-relative path the pair must produce; "
                                                          "omit to reuse the ticket's own declaration"},
         "kind": {"type": "string", "description": "only for an UNKINDED ticket; set-once"},
         "dry_run": {"type": "boolean", "description": "report the decision, write nothing, spawn nothing"}},
        ["ticket"],
        "DISPATCH ONE TICKET: re-check the ready-rules, kind it if needed (set-once), record its "
        "deliverable durably on the journal, then spawn pair_loop (which creates the branch+worktree "
        "build context) — or QUEUE it when at capacity. Returns {action: spawned|queued|would-spawn}."),
    "requeue_chains": (
        requeue_chains, {}, [],
        "the self-repopulating chains (index-watch, forge factory): each chain's open members, its "
        "live HEAD, and whether the head is ready to dispatch. READ-ONLY: settles nothing, writes "
        "nothing (a polled report must not bury the journal it polls)."),
    "harvest": (
        harvest,
        {"limit": {"type": "integer", "description": "harvest at most N tickets this call"},
         "dry_run": {"type": "boolean", "description": "list what would be harvested; write nothing"}},
        [],
        "file the distilled lesson for settled tickets that ran a pair and have none yet, and report "
        "each winner (the manifest artifact). Settled-but-never-paired tickets are SKIPPED, reported."),
}


def tool_spec(name):
    """The MCP tool descriptor (name/description/inputSchema) for one tool."""
    fn, props, required, desc = TOOLS[name]
    return {"name": name, "description": desc,
            "inputSchema": {"type": "object", "properties": props, "required": list(required)}}


def call_tool(ctx, name, args):
    """Invoke ONE tool. Unknown names and bad params are REFUSED before anything is read or written."""
    if name not in TOOLS:
        raise Refused("no such tool %r — this server exposes: %s" % (name, ", ".join(sorted(TOOLS))),
                      code=-32601)
    fn, props, required, _d = TOOLS[name]
    for req in required:
        if args.get(req) is None:
            raise Refused("missing required parameter %r for %s" % (req, name))
    for k in args:
        if k not in props:
            raise Refused("unknown parameter %r for %s (it takes: %s)"
                          % (k, name, ", ".join(sorted(props)) or "no parameters"))
    return fn(ctx["ledger"], ctx["host"], args)


# ── the MCP protocol: JSON-RPC 2.0 over stdio, one object per line ────────────────────────────────
def handle_request(ctx, req):
    """Handle one JSON-RPC request; return the response dict, or None for a notification."""
    rid, method = req.get("id"), req.get("method")
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
                       "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}})
        if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
            return None
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": [tool_spec(n) for n in sorted(TOOLS)]})
        if method == "tools/call":
            result = call_tool(ctx, params.get("name"), params.get("arguments") or {})
            return ok({"content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                       "isError": False})
        return err(-32601, "method not found: %r" % method)
    except Refused as e:
        sys.stderr.write("dispatch_toolset: REFUSED %s — %s\n" % (params.get("name") or method, e))
        sys.stderr.flush()
        return err(e.code, "refused: %s" % e)
    except Exception as e:  # noqa: BLE001 — one bad call never kills the server
        bug_report("handle_request", e, "MCP %s with params %r" % (method, params), e)
        return err(-32603, "internal error in %s: %s" % (method, e))


def serve(ctx):
    """Read JSON-RPC lines on stdin, write responses on stdout. Stdout carries the protocol ONLY —
    a stray byte there corrupts it, which is why every log line goes to stderr."""
    sys.stderr.write("dispatch_toolset: serving %s tools=%s\n" % (SERVER_NAME, ",".join(sorted(TOOLS))))
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


def print_tools():
    """The tool list, so the cadence is legible without reading the code or starting a client."""
    print("dispatch_toolset — the MCP server `%s`: the dispatcher's cognition, as deterministic tools\n"
          % SERVER_NAME)
    for n in sorted(TOOLS):
        spec = tool_spec(n)
        params = spec["inputSchema"]["properties"]
        sig = ", ".join(("%s*" % k) if k in spec["inputSchema"]["required"] else k for k in params)
        print("  %s(%s)" % (n, sig))
        for line in _wrap(spec["description"], 88):
            print("      %s" % line)
        print("")
    print("  the cadence: capacity() -> next_ready_ticket() -> dispatch(pick) ; requeue_chains() and "
          "harvest()\n  periodically. * = required. Every answer is re-derived from the ledger, so no "
          "call depends on\n  a previous one and nothing needs remembering between them.")
    return 0


def _wrap(text, width):
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        out.append(line)
    return out


# ── --selftest: prove the ACCEPTANCE against a FAKE ledger (no db, no network, no spawn) ──────────
class FakeLedger:
    """An in-memory stand-in with the Ledger's exact surface, so the rules are proven with no db and
    no network. It also RECORDS every write, which is how the read-only/dry-run promises are checked
    (a write that happened would show up in .posts)."""

    def __init__(self, tickets, edges=(), events=(), works=(), agents=(), lessons=(), kinds=None):
        self.tickets = {int(t["id"]): dict(t) for t in tickets}
        self.edges, self.events = [dict(e) for e in edges], [dict(e) for e in events]
        self.works, self.agents = [dict(w) for w in works], [dict(a) for a in agents]
        self.lessons, self.posts = [dict(l) for l in lessons], []
        self.kinds = kinds or [{"kind": "build", "pattern": "pair"}, {"kind": "bug", "pattern": "pair"},
                               {"kind": "documentation", "pattern": "pair"},
                               {"kind": "audit", "pattern": "solo"}, {"kind": "stop", "pattern": "solo"}]

    def rows(self, route, params=None):
        p = params or {}
        if route == "ticket.queue":
            return [dict(t) for _, t in sorted(self.tickets.items())
                    if (t.get("status") or "").upper() in ("OPEN", "REQUESTED")]
        if route == "kind.roster":
            return [dict(k) for k in self.kinds]
        if route == "ticket.stops":
            # the real route counts unreleased stops aimed at the ticket OR ANY ANCESTOR ('spawned' up)
            anc, seen = {int(p["ticket_id"])}, set()
            while anc - seen:
                cur = (anc - seen).pop()
                seen.add(cur)
                anc |= {int(e["parent_id"]) for e in self.edges
                        if e["kind"] == "spawned" and int(e["child_id"]) == cur}
            released = {int(e["child_id"]) for e in self.edges if e["kind"] == "starts"}
            n = len([e for e in self.edges if e["kind"] == "stops" and int(e["child_id"]) in anc
                     and int(e["parent_id"]) not in released])
            return [{"active_stops": n}]
        if route == "children.list":
            return [{"child_id": e["child_id"], "kind": e["kind"],
                     "status": (self.tickets.get(int(e["child_id"])) or {}).get("status"),
                     "title": (self.tickets.get(int(e["child_id"])) or {}).get("title")}
                    for e in self.edges if int(e["parent_id"]) == int(p["parent_id"])]
        if route == "ticket.journal":
            return [dict(e) for e in self.events if int(e["ticket_id"]) == int(p["ticket_id"])]
        if route == "ticket.manifest":
            return [dict(w) for w in self.works if int(w["ticket_id"]) == int(p["ticket_id"])]
        if route == "agent.roster":
            return [dict(a) for a in self.agents]
        if route == "lessons.recent":
            return [dict(l) for l in self.lessons]
        raise Refused("FakeLedger has no route %r" % route, code=-32603)

    def post(self, route, obj):
        self.posts.append((route, dict(obj)))
        if route == "ticket.kind":
            t = self.tickets[int(obj["id"])]
            if t.get("kind"):
                raise Refused("set-once: #%s is already kind %r" % (obj["id"], t["kind"]), code=-32603)
            t["kind"] = obj["kind"]
        elif route == "ticket.progress":
            self.events.append({"ticket_id": int(obj["ticket_id"]), "agent_id": obj["agent_id"],
                                "event": "progress", "note": obj.get("note") or ""})
        return {"ok": True}

    def ticket(self, tid):
        return dict(self.tickets.get(int(tid)) or {})


class FakeHost:
    """A host with no git and no processes: `running` is whatever the check declares, and a spawn is
    RECORDED, never executed."""

    def __init__(self, running=(), worktrees="/fake/worktrees"):
        self.running, self.worktrees, self.spawned = list(running), worktrees, []

    def running_tickets(self):
        return sorted(self.running)

    def spawn(self, argv, log_path):
        self.spawned.append((list(argv), log_path))
        return 4242


def selftest():
    """Prove the ticket's ACCEPTANCE with NO db, NO network, NO agents and NO writes into this repo.
    Prints one PASS/FAIL line per check; exits 0 only if every check passed."""
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name,
                                ("  — %s" % detail) if detail and not cond else ""))

    def ctx(led, host):
        return {"ledger": led, "host": host}

    def rpc(c, method, params=None, rid=1):
        return handle_request(c, {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})

    print("== selftest == a FAKE in-memory ledger + a fake host; the db, the network and this repo "
          "are untouched")

    # A queue that exercises every rule at once. #300 is the ONLY ready ticket: #290 is unkinded,
    # #291 is a solo kind, #292 is halted by a stop, #293 already delivered, #294 is superseded,
    # #295's deliverable is claimed by running #999.
    T = [{"id": 290, "kind": None, "status": "REQUESTED", "title": "unkinded", "body": ""},
         {"id": 291, "kind": "audit", "status": "REQUESTED", "title": "solo kind", "body": ""},
         {"id": 292, "kind": "build", "status": "OPEN", "title": "halted", "body": ""},
         {"id": 293, "kind": "build", "status": "REQUESTED", "title": "already delivered", "body": ""},
         {"id": 294, "kind": "build", "status": "REQUESTED", "title": "superseded", "body": ""},
         {"id": 295, "kind": "build", "status": "REQUESTED", "title": "claimed deliverable",
          "body": "%s tools/taken.py" % DELIV_MARK},
         {"id": 300, "kind": "build", "status": "REQUESTED", "title": "THE PICK",
          "body": "%s tools/pick.py" % DELIV_MARK},
         {"id": 301, "kind": "build", "status": "REQUESTED", "title": "younger, also ready", "body": ""},
         {"id": 999, "kind": "build", "status": "ACTIVE", "title": "running",
          "body": "%s tools/taken.py" % DELIV_MARK},
         {"id": 900, "kind": "stop", "status": "REQUESTED", "title": "STOP: #292", "body": ""},
         {"id": 901, "kind": "build", "status": "REQUESTED", "title": "supersedes #294", "body": ""}]
    E = [{"parent_id": 900, "child_id": 292, "kind": "stops"},
         {"parent_id": 901, "child_id": 294, "kind": "supersedes"}]
    W = [{"ticket_id": 293, "uid": 7, "kind": "code", "ref": "tools/done.py"}]

    def fresh():
        return FakeLedger(T, edges=E, works=W), FakeHost(running=[999])

    def fresh_running(extra):
        """The same ledger, with `extra` tickets ALSO holding a live worktree."""
        return FakeLedger(T, edges=E, works=W), FakeHost(running=[999] + list(extra))

    # ── a: the ready-rules pick the right ticket, and every rule bites ────────────────────────────
    print("-- a: the ready-rules")
    led, host = fresh()
    r = next_ready_ticket(led, host, {})
    ck("a1: picks #300 — the oldest ticket passing ALL four rules",
       r["pick"]["ticket"] == 300, json.dumps(r))
    ck("a2: the pick carries the deliverable DECLARED in its body (no path is invented)",
       r["pick"]["deliverable"] == "tools/pick.py" and r["pick"]["needs_deliverable"] is False)
    ck("a3: R1 rejects the unkinded #290 and the solo-kind #291",
       r["rejected"].get("R1-kinded") == 2, json.dumps(r["rejected"]))
    ck("a4: R2 rejects the halted #292 (a stop aimed at it)", r["rejected"].get("R2-not-stopped") == 1)
    ck("a5: R3a rejects #293 — its manifest already records a delivered artifact",
       r["rejected"].get("R3a-delivered") == 1)
    ck("a6: R3b rejects #295 — running #999 is writing the same file",
       r["rejected"].get("R3b-claimed") == 1 and "#999" in r["examples"]["R3b-claimed"])
    ck("a7: R4 rejects the superseded #294", r["rejected"].get("R4-deps-met") == 1)
    ck("a8: idle is EXPLAINED — every skipped ticket is counted by the rule that rejected it",
       sum(r["rejected"].values()) == 6 and set(r["examples"]) == set(r["rejected"]),
       json.dumps(r["rejected"]))

    # DETERMINISM: the same ledger state always yields the same answer.
    ck("a9: DETERMINISTIC — 5 calls on the same state return the identical pick",
       len({json.dumps(next_ready_ticket(*fresh(), {}), sort_keys=True) for _ in range(5)}) == 1)

    # The brake propagates DOWN a spawned chain: a stop on an ancestor halts the descendant.
    led2, host2 = fresh()
    led2.edges.append({"parent_id": 292, "child_id": 300, "kind": "spawned"})
    ck("a10: the brake propagates to a descendant — #300 halted via its ancestor #292, pick moves on",
       next_ready_ticket(led2, host2, {})["pick"]["ticket"] == 301,
       json.dumps(next_ready_ticket(led2, host2, {})))
    led3, host3 = fresh()
    led3.edges.append({"parent_id": 950, "child_id": 900, "kind": "starts"})
    ck("a11: a `starts` edge RELEASES the stop — #292 becomes the pick again",
       next_ready_ticket(led3, host3, {})["pick"]["ticket"] == 292)
    led4, host4 = fresh()
    for t in led4.tickets.values():
        if t["id"] in (300, 301, 901):          # retire every ready ticket; only unready ones remain
            t["status"] = "DONE"
    r4 = next_ready_ticket(led4, host4, {})
    ck("a12: with no ready ticket it returns IDLE with the reason (never a crash, never a guess)",
       r4["idle"] is True and "pick" not in r4 and r4["reason"] and r4["rejected"], json.dumps(r4))
    ck("a13: a read-only tool WROTE NOTHING to the ledger", led.posts == [], json.dumps(led.posts))
    # R4 must see a superseder that has ALREADY SETTLED — it has left the queue, but its predecessor
    # is still retired. A queue-only scan misses exactly this, and hands back retired work.
    led5, host5 = fresh()
    led5.tickets[901]["status"] = "DONE"        # the superseder settles and leaves the queue
    r5 = next_ready_ticket(led5, host5, {})
    ck("a15: a SETTLED superseder still retires its predecessor — #294 is not resurrected",
       r5["pick"]["ticket"] == 300 and r5["rejected"].get("R4-deps-met") == 1, json.dumps(r5["pick"]))
    # The double-dispatch window: a RUNNING ticket is still OPEN until pair_loop sets it ACTIVE.
    ck("a14: a ticket that is ALREADY RUNNING is never picked again, even while still in the queue",
       next_ready_ticket(*fresh_running([300]), {})["pick"]["ticket"] == 301,
       json.dumps(next_ready_ticket(*fresh_running([300]), {})["pick"]))

    # R4's scan is the one expensive read: it must be paid for ONLY when a ticket reaches R4, ONCE,
    # and its upper bound must be CHECKED against the ledger, not guessed.
    class Counting(FakeLedger):
        def __init__(self, *a2, **k2):
            super().__init__(*a2, **k2)
            self.calls = {}

        def rows(self, route, params=None):
            self.calls[route] = self.calls.get(route, 0) + 1
            return super().rows(route, params)

    unkinded = Counting([{"id": i, "kind": None, "status": "REQUESTED", "title": "x", "body": ""}
                         for i in (10, 11, 12)])
    ck("a16: R4's scan is LAZY — a queue where nothing survives R1 never pays for it",
       next_ready_ticket(unkinded, FakeHost(), {})["idle"] is True
       and unkinded.calls.get("children.list", 0) == 0, json.dumps(unkinded.calls))
    S = [{"id": 10, "kind": "build", "status": "REQUESTED", "title": "retired", "body": ""},
         {"id": 11, "kind": "build", "status": "REQUESTED", "title": "ready", "body": ""},
         {"id": 12, "kind": "build", "status": "DONE", "title": "superseder, settled", "body": ""}]
    SE = [{"parent_id": 12, "child_id": 10, "kind": "supersedes"}]
    ck("a17: max_ticket_id WALKS UP to a settled ticket the queue and the roster never name",
       max_ticket_id(FakeLedger(S), FakeLedger(S).rows("ticket.queue")) == 12)
    cnt = Counting(S, edges=SE)
    next_ready_ticket(cnt, FakeHost(), {})
    ck("a18: R4's scan is MEMOISED — one scan of 1..12 per call, not one per ticket",
       cnt.calls["children.list"] == 12, json.dumps(cnt.calls))

    # The REAL Ledger's 404 contract, exercised on the real class (a fake ledger cannot prove this,
    # and the mismatch is not hypothetical: max_ticket_id's walk asks about ids past the end of the
    # table, and a `ticket()` that treated 404 as a fault broke every live call while the fake stayed
    # green). No network: only _open is replaced, so the real ticket() logic runs.
    class _Http(Ledger):
        def __init__(self, code):
            super().__init__()
            self.code = code

        def _open(self, url, data=None, method="GET"):
            raise urllib.error.HTTPError(url, self.code, "err", {}, None)

    ck("a19: the real Ledger.ticket() answers {} on 404 — 'no such ticket' is an ANSWER, not a crash",
       _Http(404).ticket(99999) == {})
    try:
        _Http(500).ticket(1)
        ck("a20: a NON-404 http error is raised, never misread as an empty table", False, "it returned {}")
    except Refused as e:
        ck("a20: a NON-404 http error is raised, never misread as an empty table", "500" in str(e), str(e))

    # ── b: capacity ───────────────────────────────────────────────────────────────────────────────
    print("-- b: capacity = pairs running vs the cap")
    led, host = fresh()
    c = capacity(led, host, {})
    ck("b1: reports running/cap/free from the live worktrees + registry cap",
       c["running"] == 1 and c["cap"] == config()["cap"] and c["running_tickets"] == [999],
       json.dumps(c))
    full = capacity(led, FakeHost(running=[1, 2, 3, 4, 5, 6]), {})
    ck("b2: at_capacity is true when running >= cap, and free never goes negative",
       full["at_capacity"] is True and full["free"] == 0)
    ck("b3: capacity WROTE NOTHING", led.posts == [])

    # ── c: THE ACCEPTANCE — cold context: next_ready_ticket() + dispatch() queue the right ticket ─
    print("-- c: THE ACCEPTANCE — from a COLD context, with NO recall of prior state")
    led, host = FakeLedger(T, edges=E, works=W), FakeHost(running=[999])
    pick = next_ready_ticket(led, host, {})["pick"]
    d = dispatch(led, host, {"ticket": pick["ticket"]})     # no deliverable passed: read from the ledger
    ck("c1: dispatch() SPAWNED the pair on the picked ticket, with NO argument but the id",
       d["action"] == "spawned" and d["ticket"] == 300, json.dumps(d))
    ck("c2: the deliverable came from the LEDGER (the ticket's own declaration), not from the caller",
       d["deliverable"] == "tools/pick.py")
    ck("c3: the spawned child is pair_loop --ticket 300 --deliverable tools/pick.py",
       host.spawned and host.spawned[0][0][1].endswith("pair_loop.py")
       and host.spawned[0][0][2:6] == ["--ticket", "300", "--deliverable", "tools/pick.py"],
       json.dumps(host.spawned[0][0] if host.spawned else []))
    ck("c4: the act is journaled on the ledger (the record, not the model, remembers it)",
       any(r == "ticket.progress" and "spawned" in o["note"] for r, o in led.posts))
    # A SECOND, INDEPENDENT caller: brand-new objects, zero shared memory — exactly a cold context.
    # #300 now has a worktree (the pair opened it) but is STILL in the queue, because pair_loop has
    # not yet set it ACTIVE. The cold caller must not re-dispatch it.
    led_b, host_b = FakeLedger(T, edges=E, works=W), FakeHost(running=[999, 300])
    pick_b = next_ready_ticket(led_b, host_b, {})["pick"]
    ck("c5: a COLD second caller — new objects, no memory — skips the now-running #300 and picks #301",
       pick_b["ticket"] == 301, json.dumps(pick_b))
    try:
        dispatch(led_b, host_b, {"ticket": 300, "deliverable": "tools/pick.py"})
        ck("c6: re-dispatching the already-running #300 is REFUSED (no double-dispatch)", False,
           "it dispatched a second time")
    except Refused as e:
        ck("c6: re-dispatching the already-running #300 is REFUSED (no double-dispatch)",
           "ALREADY RUNNING" in str(e) and host_b.spawned == [], str(e)[:90])

    # ── d: the deliverable declaration survives a cold context ────────────────────────────────────
    print("-- d: declaring a deliverable ONCE makes it durable")
    led, host = FakeLedger(T, edges=E, works=W), FakeHost()
    d1 = dispatch(led, host, {"ticket": 301, "deliverable": "tools/newly.py"})
    ck("d1: a ticket with no declaration accepts one and RECORDS it on the journal",
       d1["declared"] == "tools/newly.py"
       and any(r == "ticket.progress" and DELIV_MARK in o["note"] for r, o in led.posts), json.dumps(d1))
    ck("d2: a later COLD dispatch(ticket=301) reads that declaration back — no memory needed",
       declared_deliverable(led, 301) == "tools/newly.py")
    led_n, host_n = FakeLedger(T, edges=E, works=W), FakeHost()
    try:
        dispatch(led_n, host_n, {"ticket": 301})
        ck("d3: a ticket with NO declaration and no path is REFUSED by name (never guessed)", False,
           "it dispatched anyway")
    except Refused as e:
        ck("d3: a ticket with NO declaration and no path is REFUSED by name (never guessed)",
           "declares no deliverable" in str(e) and host_n.spawned == [], str(e))
    ck("d4: the refused dispatch spawned nothing and wrote nothing",
       host_n.spawned == [] and led_n.posts == [])

    # ── e: dispatch refuses what the rules refuse, and never trusts the caller ────────────────────
    print("-- e: dispatch re-checks the rules; the caller is not trusted")
    for tid, why in ((292, "halted"), (294, "superseded"), (293, "delivered"), (291, "solo kind")):
        led_e, host_e = FakeLedger(T, edges=E, works=W), FakeHost()
        try:
            dispatch(led_e, host_e, {"ticket": tid, "deliverable": "tools/x.py"})
            ck("e: dispatch(#%s) is refused (%s)" % (tid, why), False, "it dispatched anyway")
        except Refused as e:
            ck("e: dispatch(#%s) is refused (%s) and spawns nothing" % (tid, why), not host_e.spawned,
               str(e)[:90])
    led_e, host_e = FakeLedger(T, edges=E, works=W), FakeHost()
    try:
        dispatch(led_e, host_e, {"ticket": 999, "deliverable": "tools/x.py"})
        ck("e5: an ALREADY-DISPATCHED ticket (ACTIVE) is refused", False, "it dispatched anyway")
    except Refused as e:
        ck("e5: an ALREADY-DISPATCHED ticket (ACTIVE) is refused", "ACTIVE" in str(e), str(e)[:90])

    # ── f: kinds if needed — set-once, never chosen for you ───────────────────────────────────────
    print("-- f: kind if needed (set-once)")
    led, host = FakeLedger(T, edges=E, works=W), FakeHost()
    d = dispatch(led, host, {"ticket": 290, "kind": "build", "deliverable": "tools/k.py"})
    ck("f1: an UNKINDED ticket is kinded via ticket.kind, then dispatched",
       d["kinded"] == "build" and d["action"] == "spawned"
       and any(r == "ticket.kind" for r, _ in led.posts), json.dumps(d))
    try:
        dispatch(led, host, {"ticket": 300, "kind": "bug", "deliverable": "tools/x.py"})
        ck("f2: RE-kinding an already-kinded ticket is refused (kind is set-once)", False, "it re-kinded")
    except Refused as e:
        ck("f2: RE-kinding an already-kinded ticket is refused (kind is set-once)",
           "set-once" in str(e).lower(), str(e)[:90])
    led_f, host_f = FakeLedger(T, edges=E, works=W), FakeHost()
    try:
        dispatch(led_f, host_f, {"ticket": 290, "deliverable": "tools/k.py"})
        ck("f3: an unkinded ticket with NO kind supplied is refused — kinds are never chosen for you",
           False, "it chose a kind")
    except Refused as e:
        ck("f3: an unkinded ticket with NO kind supplied is refused — kinds are never chosen for you",
           "does not choose kinds" in str(e), str(e)[:90])
    led_f2, host_f2 = FakeLedger(T, edges=E, works=W), FakeHost()
    try:
        dispatch(led_f2, host_f2, {"ticket": 290, "kind": "audit", "deliverable": "tools/k.py"})
        ck("f4: a SOLO kind is refused (pair_loop harnesses pairs)", False, "it accepted a solo kind")
    except Refused as e:
        ck("f4: a SOLO kind is refused (pair_loop harnesses pairs)", "not a pair kind" in str(e))

    # ── g: at capacity, dispatch QUEUES instead of spawning ───────────────────────────────────────
    print("-- g: at capacity -> queue, not spawn")
    cap = config()["cap"]
    # #999 keeps its claim on tools/taken.py (so #295 stays unready) and the rest fill the cap.
    busy = [999] + list(range(500, 500 + cap - 1))
    led, host = FakeLedger(T, edges=E, works=W), FakeHost(running=busy)
    d = dispatch(led, host, {"ticket": 300})
    ck("g1: at capacity the pick is QUEUED, not spawned — and no child is started",
       d["action"] == "queued" and host.spawned == [], json.dumps(d))
    ck("g2: the queued reason names the running pairs, so the dispatcher needs no memory of them",
       "at capacity" in d["reason"] and "#999" in d["reason"], d.get("reason"))
    ck("g3: a queued ticket stays OPEN in the queue — the next call re-picks it with no recall",
       next_ready_ticket(FakeLedger(T, edges=E, works=W), FakeHost(running=busy), {})["pick"]["ticket"]
       == 300)

    # ── h: dry_run writes NOTHING (proven by the ledger's own write log) ──────────────────────────
    print("-- h: dry_run acts on nothing")
    led, host = FakeLedger(T, edges=E, works=W), FakeHost()
    d = dispatch(led, host, {"ticket": 300, "dry_run": True})
    ck("h1: dispatch(dry_run) reports would-spawn, spawns nothing, and writes NOTHING",
       d["action"] == "would-spawn" and host.spawned == [] and led.posts == [], json.dumps(led.posts))
    ck("h2: dry_run still reports the real command and the real capacity",
       "pair_loop.py" in d["command"] and "--ticket" in d["command"])
    led, host = FakeLedger(T, edges=E, works=W), FakeHost()
    d = dispatch(led, host, {"ticket": 290, "kind": "build", "deliverable": "x.py", "dry_run": True})
    ck("h3: dry_run does not KIND the ticket either (no route write at all)",
       led.posts == [] and led.ticket(290).get("kind") is None, json.dumps(led.posts))

    # ── i: harvest ────────────────────────────────────────────────────────────────────────────────
    print("-- i: harvest = settled winners + the journal's lesson")
    HT = [{"id": 10, "kind": "build", "status": "DONE", "title": "paired + settled", "body": ""},
          {"id": 11, "kind": "build", "status": "DONE", "title": "settled, never paired", "body": ""},
          {"id": 12, "kind": "build", "status": "DONE", "title": "already harvested", "body": ""},
          {"id": 13, "kind": "build", "status": "ACTIVE", "title": "still running", "body": ""}]
    HA = [{"agent_id": "forge-t%d" % i} for i in (10, 11, 12, 13)] + [{"agent_id": "dispatch-01"}]
    HE = [{"ticket_id": 10, "event": "progress", "agent_id": "tester-t10r1", "note": "round 1 verdict: pass"},
          {"ticket_id": 11, "event": "progress", "agent_id": "forge-t11", "note": "landed by the forge"},
          {"ticket_id": 12, "event": "progress", "agent_id": "tester-t12r1", "note": "round 1 verdict: pass"}]
    HW = [{"ticket_id": 10, "uid": 42, "kind": "code", "ref": "tools/winner.py"}]
    hled = FakeLedger(HT, events=HE, works=HW, agents=HA, lessons=[{"ticket_id": 12}])
    h = harvest(hled, FakeHost(), {"dry_run": True})
    ck("i1: harvests the settled ticket that RAN a pair (#10) and reports its winning artifact",
       [x["ticket"] for x in h["harvested"]] == [10]
       and h["harvested"][0]["winner"][0]["ref"] == "tools/winner.py", json.dumps(h))
    ck("i2: a settled ticket that never ran a tournament (#11) is SKIPPED and REPORTED, not failed",
       [x["ticket"] for x in h["skipped"]] == [11], json.dumps(h["skipped"]))
    ck("i3: an already-harvested ticket (#12) is not harvested twice (lessons.recent is the memory)",
       12 not in [x["ticket"] for x in h["harvested"]])
    ck("i4: an unsettled ticket (#13, still running) is never harvested",
       13 not in [x["ticket"] for x in h["harvested"]])
    ck("i5: harvest(dry_run) wrote NOTHING", hled.posts == [], json.dumps(hled.posts))
    h2 = harvest(FakeLedger(HT, events=HE, works=HW, agents=HA, lessons=[]), FakeHost(),
                 {"limit": 1, "dry_run": True})
    ck("i6: limit bounds one call's work", len(h2["harvested"]) == 1)

    # ── ch: the chains — head selection + readiness (the part that is pure logic) ─────────────────
    # _chain is tested directly: requeue_chains() itself IMPORTS index_watch.py/forge_refactor_
    # ticketer.py to read their marks, and loading real modules is not this selftest's promise (no db,
    # no network). That import path is exercised live by `--call requeue_chains`.
    print("-- ch: chain heads")
    CH = [{"id": 60, "kind": "build", "status": "REQUESTED", "title": "older member", "body": ""},
          {"id": 61, "kind": "build", "status": "REQUESTED", "title": "older member", "body": ""},
          {"id": 62, "kind": "build", "status": "REQUESTED", "title": "THE HEAD", "body": ""}]
    cled = FakeLedger(CH)
    c1 = _chain("index-watch", CH, cled, pair_kinds(cled), FakeHost())
    ck("ch1: the HEAD is the NEWEST open member, and it is reported ready",
       c1["head"] == 62 and c1["ready"] is True and c1["open_members"] == [60, 61, 62], json.dumps(c1))
    ck("ch2: older open members are named as NOT routed (the head is the live link)",
       "#60, #61" in c1["status"] and "NOT routed" in c1["status"], c1["status"])
    cled2 = FakeLedger(CH, edges=[{"parent_id": 900, "child_id": 62, "kind": "stops"}])
    c2 = _chain("index-watch", CH, cled2, pair_kinds(cled2), FakeHost())
    ck("ch3: a HALTED head is reported not-ready WITH the reason, never silently skipped",
       c2["head"] == 62 and c2["ready"] is False and "R2-not-stopped" in c2["status"], c2["status"])
    c3 = _chain("forge-factory", [], FakeLedger(CH), pair_kinds(cled), FakeHost(), root=201)
    ck("ch4: a dry chain reports no head and says so (its next run reseeds it)",
       c3["head"] is None and "dry" in c3["status"] and c3["root"] == 201, json.dumps(c3))
    ck("ch5: requeue_chains takes no dry_run — it is READ-ONLY, so there is nothing to dry-run",
       "dry_run" not in TOOLS["requeue_chains"][1] and cled.posts == [])

    # ── j: the MCP protocol (a client can actually connect and call) ───────────────────────────────
    print("-- j: MCP protocol")
    c = ctx(*fresh())
    init = rpc(c, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
    ck("j1: initialize echoes the client's protocol version",
       init["result"]["protocolVersion"] == "2024-11-05", json.dumps(init))
    ck("j2: an unknown protocol version falls back to a supported one",
       rpc(c, "initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"]
       in PROTOCOL_VERSIONS)
    ck("j3: serverInfo names this server", init["result"]["serverInfo"]["name"] == SERVER_NAME)
    listed = [t["name"] for t in rpc(c, "tools/list")["result"]["tools"]]
    ck("j4: tools/list returns EXACTLY the ticket's five tools",
       sorted(listed) == ["capacity", "dispatch", "harvest", "next_ready_ticket", "requeue_chains"],
       ",".join(sorted(listed)))
    ck("j5: every tool has a well-formed MCP inputSchema",
       all(tool_spec(n)["inputSchema"]["type"] == "object" for n in TOOLS))
    r = rpc(c, "tools/call", {"name": "next_ready_ticket", "arguments": {}})
    ck("j6: tools/call runs a tool and returns its JSON result",
       json.loads(r["result"]["content"][0]["text"])["pick"]["ticket"] == 300, json.dumps(r)[:200])
    ck("j7: a notification gets NO response (JSON-RPC requires silence)",
       handle_request(c, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None)
    ck("j8: an unknown method is an error, not a crash",
       rpc(c, "nonsense/method")["error"]["code"] == -32601)
    ck("j9: an unknown tool is refused, not crashed",
       rpc(c, "tools/call", {"name": "rm_rf", "arguments": {}})["error"]["code"] == -32601)
    ck("j10: a missing required parameter is refused, not crashed",
       rpc(c, "tools/call", {"name": "dispatch", "arguments": {}})["error"]["code"] == -32602)
    ck("j11: an unknown parameter is refused (a typo never becomes a silent default)",
       "unknown parameter" in rpc(c, "tools/call",
                                  {"name": "dispatch",
                                   "arguments": {"ticket": 300, "delivrable": "x"}})["error"]["message"])
    ck("j12: a refusal is an ANSWER (a stated reason), never a traceback",
       "refused:" in rpc(c, "tools/call",
                         {"name": "dispatch", "arguments": {"ticket": 292}})["error"]["message"])

    # ── k: the dispatcher holds NO authoring pen ──────────────────────────────────────────────────
    print("-- k: this server routes; it never authors")
    writes = {"ticket.kind", "ticket.progress", "ticket.lesson", "ticket.assign", "agent.register"}
    src = open(os.path.abspath(__file__)).read()
    ck("k1: the only routes this file POSTs are routing/journal writes — no work.record, no artifact",
       not re.search(r'post\("(work\.record|artifact\.record|doc\.record)"', src))
    ck("k2: every route it POSTs is in the routing set %s" % ", ".join(sorted(writes)),
       set(re.findall(r'post\("([a-z_.]+)"', src)) <= writes,
       ",".join(sorted(set(re.findall(r'post\("([a-z_.]+)"', src)) - writes)))
    ck("k3: it holds no git pen — it starts pair_loop (which owns the branch) and runs no other git "
       "verb than the read-only `worktree list`",
       set(re.findall(r'"git", "([a-z-]+)"', src)) == {"worktree"})
    # The SIDE EFFECTS docstring names exactly three always-read-only tools. Prove it, rather than
    # trusting the paragraph: run each against a ledger that records every write, and demand silence.
    for name in ("next_ready_ticket", "capacity"):
        rled, rhost = fresh()
        call_tool({"ledger": rled, "host": rhost}, name, {})
        ck("k4: %s is READ-ONLY as documented (wrote nothing)" % name, rled.posts == [],
           json.dumps(rled.posts))
    rled = FakeLedger(CH)
    _chain("index-watch", CH, rled, pair_kinds(rled), FakeHost())
    ck("k5: the chain report is READ-ONLY as documented (wrote nothing)", rled.posts == [])
    ck("k6: exactly TWO tools declare dry_run — the two the docstring says can act",
       sorted(n for n in TOOLS if "dry_run" in TOOLS[n][1]) == ["dispatch", "harvest"],
       ",".join(sorted(n for n in TOOLS if "dry_run" in TOOLS[n][1])))

    # ── m: the seam with the modules this file REUSES rather than restates ────────────────────────
    # requeue_chains and harvest import these to read their marks / call their harvest, exactly so
    # this file cannot drift out of agreement with them. That trades a copy-paste bug for a RENAME
    # bug, so the names are checked here: importing is offline (no db, no network, no bytecode).
    print("-- m: the reused modules still export what this file reads")
    try:
        iw = load_module("index_watch", os.path.join(TOOLS_DIR, "index_watch.py"))
        ck("m1: index_watch still exports the chain marks requeue_chains matches members on",
           all(isinstance(getattr(iw, k, None), str) for k in ("BODY_PRED", "BODY_MARK", "SUCCESSOR_TITLE")))
        frt = load_module("forge_refactor_ticketer",
                          os.path.join(TOOLS_DIR, "forge_refactor_ticketer.py"))
        ck("m2: forge_refactor_ticketer still exports FACTORY_TICKET (the factory chain's root)",
           isinstance(getattr(frt, "FACTORY_TICKET", None), int))
        pl = load_module("pair_loop", os.path.join(TOOLS_DIR, "pair_loop.py"))
        ck("m3: pair_loop still exports harvest_settled(tid) — the harvest this file calls, not copies",
           callable(getattr(pl, "harvest_settled", None)))
        ck("m4: pair_loop.py is where dispatch spawns the pair from",
           os.path.isfile(os.path.join(TOOLS_DIR, "pair_loop.py")))
    except Refused as e:
        ck("m: the reused modules load", False, str(e))

    print("\n== selftest == %d/%d checks passed" % (sum(1 for _, c_, _ in checks if c_), len(checks)))
    for name, cond, detail in checks:
        if not cond:
            print("   FAILED: %s  — %s" % (name, detail))
    return 0 if all(c_ for _, c_, _ in checks) else 1


def main():
    ap = argparse.ArgumentParser(
        description="dispatch-tools: the dispatcher's cognition as deterministic MCP tools "
                    "(next_ready_ticket, capacity, dispatch, requeue_chains, harvest)")
    ap.add_argument("--serve", action="store_true", help="speak MCP (JSON-RPC 2.0) on stdio")
    ap.add_argument("--tools", action="store_true", help="print the tool list and exit")
    ap.add_argument("--call", metavar="TOOL", choices=sorted(TOOLS),
                    help="run ONE tool against the LIVE ledger and print its JSON result")
    ap.add_argument("--arg", action="append", default=[], metavar="K=V",
                    help="argument for --call (repeatable); an integer value is parsed as an int")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --call dispatch|harvest (the only tools that act): report the decision, "
                         "but write nothing and spawn nothing")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the acceptance against a fake ledger; no db, no network, no files")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if a.tools:
        return print_tools()
    ctx = {"ledger": Ledger(), "host": Host()}
    if a.call:
        args = {}
        for kv in a.arg:
            if "=" not in kv:
                print("dispatch_toolset: --arg must be K=V, got %r" % kv)
                return 2
            k, v = kv.split("=", 1)
            args[k] = int(v) if re.fullmatch(r"-?\d+", v) else v
        if a.dry_run:
            args["dry_run"] = True
        try:
            print(json.dumps(call_tool(ctx, a.call, args), indent=2))
        except Refused as e:
            print("dispatch_toolset: refused: %s" % e)
            return 1
        return 0
    if not a.serve:
        ap.error("one of --serve, --tools, --call TOOL or --selftest is required")
    return serve(ctx)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — one-line message, never a traceback (+ a filed report)
        bug_report("main", e, "python3 dispatch_toolset.py %s" % " ".join(sys.argv[1:]), e)
        print("dispatch_toolset: %s" % e)
        sys.exit(2)
