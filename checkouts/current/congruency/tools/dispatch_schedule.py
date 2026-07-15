#!/usr/bin/env python3
"""dispatch_schedule.py — the dispatch SCHEDULE: dispatch-01's queue lane + the index-watch CHAIN
lane, on one timer, hands-off (ticket #198).

A macOS LaunchAgent runs `dispatch_schedule.py cycle` every `interval_hours`. ONE CYCLE is two
lanes, in the order the code executes them (do_cycle below):

    LANE 1 — THE WATCH (new: ticket #198). Advance the self-repopulating index-watch chain by
             exactly one link: select the newest OPEN index-watch ticket, run it, settle it. The run
             ITSELF spawns the successor (index_watch.py step 8), so the chain never runs dry.
    LANE 2 — THE DISPATCH (pre-existing). `pair_loop.py --dispatch <cap>` — dispatch-01 reads the
             queue and routes up to `cap` tickets to adversarial pairs.

The watch lane runs FIRST on purpose: it settles the chain member it ran, so that member has left
the queue by the time dispatch-01 reads it in lane 2 and dispatch-01 is never asked to route work
this schedule has already done.

TERMS (defined at first use — this file is read without its author present).

  * THE INDEX-WATCH is tools/index_watch.py: one run reads a high-water-mark, computes the
    new/changed code as an omni-git blob-sha DELTA, AST-chunks+embeds each new blob into the vector
    store, records each on the ticket's permanent manifest, advances the mark, and SPAWNS the next
    index-watch ticket carrying it. This module never re-implements any of that; it only decides
    WHICH ticket to run, WHEN, and settles it afterwards.
  * A BLOB SHA is git's content address: the sha IS a hash of the bytes. A changed file is, by
    definition, a new sha.
  * THE CHAIN is the perpetual sequence of index-watch tickets, each SPAWNED by the previous one
    (a parent->child row in `ticket_edges` with kind 'spawned',
    migrations/0012_ticket_edges.sql:6-12). THE HEAD is its newest open member — the only one this
    schedule runs.
  * OPEN means what the dispatch queue means by it: `ticket.queue` selects
    `upper(status) IN ('OPEN','REQUESTED')` (migrations/0032_dispatch_routes.sql:7). A ticket
    ticket.create mints is REQUESTED, so a freshly spawned successor is open by this definition.
  * TO SETTLE a ticket is to drive it to DONE through the governed `process_status` route — the
    same settle pair_loop.py:1102 and local_graph.py:828 perform. It is what removes a ticket from
    the queue.
  * THE BRAKE is `ticket.stops` (migrations/0030_pair_loop_routes.sql:21-26): the count of active
    (unreleased) stop tickets aimed at a ticket OR ANY ANCESTOR, walking 'spawned' edges up.

THE BOUND — one index-watch in flight at a time. Three distinct mechanisms, because "in flight"
has three distinct meanings and only all three together make the ticket's bound true:

  1. ONE RUN AT A TIME (concurrency). An acting turn holds an exclusive, non-blocking `flock` on
     logs/dispatch_schedule.lock from start to finish. A second cycle that finds the lock held says
     so and does nothing (exit 5). launchd will not run two copies of one Label, but a human running
     `cycle` by hand beside the timer would otherwise overlap; the flock is what actually forbids
     it on this host. (A `--dry-run` changes nothing, so it takes no lock and is never blocked by
     one — you can inspect a chain while a cycle is in flight.)
  2. ONE LINK PER CYCLE (progress). Exactly one ticket is run per cycle — the HEAD, the newest open
     chain member. Older open members are never run.
  3. EXACTLY ONE OPEN (the invariant the ticket's ACCEPTANCE names). The head is settled once its
     successor exists, and any older open member is settled as SUPERSEDED before the run. Each
     cycle ends by re-reading the queue and REPORTING the count, so the invariant is legible in the
     log rather than asserted here.

WHY SETTLING AN OLDER MEMBER LOSES NO WORK. The index-watch delta is `{python blobs in scope} MINUS
{blob shas the store has already settled}` — computed from shas, never from the mark ("THE TRAP: THE
MARK IS NOT A RANGE FILTER", index_watch.py's THE DELTA). So whatever an abandoned member would have
indexed is still unsettled, and the head recomputes it into its own delta on the very next run. The
mark is carried forward, not depended upon. This is exactly why running ONLY the newest is safe.

THE CHAIN MUST BE A SOLO KIND, AND THIS SCHEDULE IS WHY. `tg_tickets_pair_completion`
(migrations/0029_ticket_authorization.sql:133-140) REFUSES DONE on a `pair`-pattern ticket unless two
DISTINCT agents hold two DISTINCT roles, and index_watch's runner is deliberately never
ticket.assign'd (its THE AGENT section: assigning it "would hollow out the db's own backstop against
a ticket settling without an adversary"). A pair-kind chain member therefore CANNOT be settled by
any mechanical runner — so a chain of them could never satisfy "exactly one open index-watch". The
lane consequently runs the watch with `--successor-kind` set to a SOLO kind (default `audit`:
pattern solo, purpose "examine delivered work; may spawn patch/refactor tickets" — 0029:43), which
is settleable with no pair and no hollowing. A member that is nonetheless a pair kind (the first one
the schedule meets may still be, having inherited `build` from the genesis ticket) is NOT settled
here: the lane says so in one line and leaves it to its pair. It never fakes a settle, and it never
aims a stop at it — a stop would propagate DOWN the 'spawned' chain to every successor and halt the
very chain it was meant to tidy.

THE AGENT. The lane registers `index-chain-01` (agent.register — a normal agent) and attributes its
journal writes to it. It is deliberately NOT ticket.assign'd, exactly as dispatch-01 journals onto
tickets it routes without being authorized on them (pair_loop.py:573-574,618-619).

Config lives in the repo registry.json (walked up to; refuses to run without it, per
note-for-claude). The `index_watch` block is OPTIONAL — every key below is the default, so the
schedule works against today's registry.json unchanged:

    "dispatch": {"interval_hours": 6, "cap": 3, "timeout": 480,
                 "index_watch": {"enabled": true, "successor_kind": "audit",
                                 "limit": 0, "timeout": 1800}}

    python3 dispatch_schedule.py install       # write + load the LaunchAgent (runs `cycle`)
    python3 dispatch_schedule.py uninstall     # unload + remove it
    python3 dispatch_schedule.py status        # loaded? the chain head? last log lines
    python3 dispatch_schedule.py run-once      # kickstart one CYCLE now (needs `install` first)
    python3 dispatch_schedule.py cycle         # ONE cycle now, in THIS process (what launchd runs)
    python3 dispatch_schedule.py watch         # the index-watch lane ONLY, once
    python3 dispatch_schedule.py watch --ticket N   # ... starting the chain AT #N (seeds a chain)
    python3 dispatch_schedule.py watch --dry-run    # what a cycle WOULD do; writes NOTHING
    python3 dispatch_schedule.py selftest      # prove the chain offline; writes nothing, files nothing

`cycle` and `watch` ACT on the live governed surface: they run the indexer and settle real tickets.
`--dry-run`, `status` and `selftest` do not — they write nothing anywhere and CREATE NO FILES (not
even the lock, and not a __pycache__ entry: see the bytecode note below). Reach for `--dry-run`
first if you want to see what a cycle would do to a live chain. `cycle` and `watch` do create the
lock file below. Output lands in <repo>/logs/dispatch.log (+ .err); both live under the gitignored
logs/ (.gitignore:20).

Exit codes (each prints ONE line, never a traceback):
    0  the cycle ran — INCLUDING "no new blobs" and "nothing in the queue", which are clean no-ops
    2  a precondition failure — no registry.json, index_watch.py not loadable, no CONGRUENCY_API_KEY,
       an unknown command
    3  the watch lane's turn did not fully succeed. Three distinct causes, and the log line says
       which: the run itself failed (a ticket whose run failed is NEVER settled — it stays open for
       the next cycle), a governed route failed, or the run succeeded but the "exactly one open"
       bound is still not met (pair-kind members this lane must not settle remain open).
    4  HALTED — an active stop ticket aims at the chain head or an ancestor; nothing was run,
       settled or spawned
    5  another cycle holds the lock — this one did nothing (the bound working, not an error case
       that needs a human)
    1  `selftest`: at least one check FAILED. `status`: the LaunchAgent is not loaded.

Pure-python stdlib, one file, no shell scripts.
"""
# NO BYTECODE CACHE — set BEFORE index_watch is imported below. Python writes a module's .pyc while
# importing it, so setting this inside index_watch (as it does, for its own imports) is too late to
# stop `tools/__pycache__/index_watch.*.pyc` being minted in the repo tree by THIS module's import.
# `selftest` promises it creates no files; that promise is only true if it holds here.
import sys

sys.dont_write_bytecode = True

import argparse
import fcntl
import importlib.util
import json
import os
import plistlib
import shutil
import subprocess
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def find_root():
    """Walk UP to registry.json — the registry gate every package tool obeys (note-for-claude)."""
    d = HERE
    while True:
        if os.path.isfile(os.path.join(d, "registry.json")):
            return d
        nxt = os.path.dirname(d)
        if nxt == d:
            raise SystemExit("registry.json not found walking up from %s — refusing to run "
                             "(note-for-claude)" % HERE)
        d = nxt


ROOT = find_root()
LABEL = "com.congruency.dispatch"
PLIST = os.path.expanduser("~/Library/LaunchAgents/%s.plist" % LABEL)
TOOLS = os.path.join(ROOT, "checkouts", "current", "congruency", "tools")
PAIR_LOOP = os.path.join(TOOLS, "pair_loop.py")
INDEX_WATCH = os.path.join(TOOLS, "index_watch.py")
LOGS = os.path.join(ROOT, "logs")
LOCK = os.path.join(LOGS, "dispatch_schedule.lock")
SELF = os.path.abspath(__file__)

CHAIN_AGENT = "index-chain-01"       # the registered agent this lane's journal writes are attributed to
DEFAULT_KIND = "audit"               # a SOLO kind — see "THE CHAIN MUST BE A SOLO KIND" above

# index_watch.py's own exit codes, for a legible log (its module docstring, "Exit codes").
WATCH_EXITS = {0: "completed", 1: "coverage/verification failure", 2: "precondition failure",
               3: "embedding proxy unreachable", 4: "a governed route failed", 5: "HALTED by a stop"}


class Fault(Exception):
    """A precondition failure — reported as one line, exit 2."""


# ── index_watch.py, reused as-is (its constants, its governed surface, its runner) ────────────────
def load_watch(path=INDEX_WATCH):
    """Import tools/index_watch.py as a module.

    Everything this schedule needs to recognise, read and run a chain member already exists there
    and is imported rather than restated: the successor TITLE and the two machine-readable body
    lines it writes (SUCCESSOR_TITLE / BODY_PRED / BODY_MARK), the governed REST surface (Gov) and
    its api-key lookup, and — for `selftest` — the real Watch plus its throwaway-corpus scaffolding.
    Restating any of them here would let this file drift out of agreement with the tool it drives,
    which is precisely the failure that would make the chain silently stop matching its own tickets.
    """
    if not os.path.isfile(path):
        raise Fault("no index_watch.py at %s — the schedule drives it and cannot run without it" % path)
    spec = importlib.util.spec_from_file_location("index_watch", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        raise Fault("index_watch.py at %s did not load (%r)" % (path, e))
    return mod


def config():
    """The `dispatch` block of registry.json, with the OPTIONAL `index_watch` sub-block."""
    with open(os.path.join(ROOT, "registry.json")) as fh:
        reg = json.load(fh)
    c = reg.get("dispatch") or {}
    w = c.get("index_watch") or {}
    return {"interval_hours": float(c.get("interval_hours", 6)),
            "cap": int(c.get("cap", 3)),
            "timeout": int(c.get("timeout", 480)),
            "watch_enabled": bool(w.get("enabled", True)),
            "successor_kind": str(w.get("successor_kind", DEFAULT_KIND)),
            "watch_limit": int(w.get("limit", 0)),
            "watch_timeout": int(w.get("timeout", 1800))}


# ── the bound, mechanism 1: one watch run at a time on this host ──────────────────────────────────
def acquire(path=LOCK):
    """An exclusive, NON-blocking flock. Returns the open handle (hold it for the turn) or None if
    another cycle holds it. The lock is released when the handle closes or the process exits — so a
    crashed cycle never wedges the chain."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fh = open(path, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


# ── recognising a chain member ────────────────────────────────────────────────────────────────────
def is_member(iw, t):
    """Is this queue row an index-watch ticket?

    The signals are the three marks index_watch.py's spawn writes and nothing else writes: the
    successor TITLE it mints (SUCCESSOR_TITLE), and the two machine-readable body lines its next run
    parses back out (BODY_PRED / BODY_MARK — index_watch.py's THE MARK). All three are read from the
    imported module, so if that tool changes them, this recogniser changes with it.

    Deliberately NOT matched: the genesis `build` ticket that authored the tool. It carries none of
    these marks (nothing spawned it), it is a pair ticket whose work is the tool rather than a run,
    and its pair settles it. The chain this schedule drives is the tickets index_watch itself files.
    Point the lane at any ticket explicitly with `watch --ticket N`.
    """
    title, body = (t.get("title") or ""), (t.get("body") or "")
    return (title.startswith(iw.SUCCESSOR_TITLE.split("%")[0])
            or iw.BODY_PRED in body or iw.BODY_MARK in body)


def open_members(iw, gov):
    """Every OPEN chain member, oldest first — read from the dispatch queue itself (ticket.queue,
    migrations/0032_dispatch_routes.sql), so "open" here is the same "open" dispatch-01 sees."""
    return [t for t in gov.rows("ticket.queue", {}) if is_member(iw, t)]


def patterns(gov):
    """{kind: 'pair'|'solo'} from the kind.roster route (migrations/0029_ticket_authorization.sql:221-226,
    over the ticket_kinds table at :27-45) — READ from the db, never assumed by this file."""
    return {k["kind"]: k.get("pattern") for k in gov.rows("kind.roster", {})}


# ── settling a chain member ───────────────────────────────────────────────────────────────────────
def settle(iw, gov, tid, kind, pats, note, say):
    """Drive one chain member to DONE through `process_status`, then journal WHY.

    ORDER MATTERS: the status change is attempted FIRST and the journal note is appended only after
    it succeeded. The journal is append-only (tg_ticket_events_no_update, 0029:142-143), so a note
    written before a refused settle would be a permanent, uncorrectable lie about what happened.

    A pair-kind member is not attempted at all: tg_tickets_pair_completion (0029:133-140) would
    refuse it, and this lane assigns no agents (see THE AGENT). Returns True only if it really
    settled.
    """
    if pats.get(kind) != "solo":
        say("  settle : #%s NOT settled — kind %r is a %s kind; DONE needs two distinct agents in two "
            "distinct roles (tg_tickets_pair_completion) and this lane assigns none. Its pair settles "
            "it; the chain continues in %r from its successor."
            % (tid, kind, pats.get(kind) or "unknown", DEFAULT_KIND))
        return False
    try:
        gov.rest("process_status", {"id": int(tid), "status": "DONE"})
    except iw.GovError as e:
        say("  settle : #%s NOT settled — %s" % (tid, e))
        return False
    try:
        gov.rest("ticket.progress", {"ticket_id": int(tid), "agent_id": CHAIN_AGENT,
                                     "note": note, "steps_remaining": 0})
    except iw.GovError as e:
        say("  settle : #%s is DONE, but its progress note did not land (%s)" % (tid, e))
    say("  settle : #%s DONE — %s" % (tid, note))
    return True


def register(iw, gov):
    """The lane's agent: registered (so its writes are attributed), never ticket.assign'd."""
    gov.rest("agent.register", {
        "agent_id": CHAIN_AGENT, "parent": "dispatch_schedule",
        "tools": json.dumps(["ticket.queue", "ticket.stops", "kind.roster", "ticket.progress",
                             "process_status", "index_watch.py"]),
        "prompt": "You are %s, the index-watch chain lane of the dispatch schedule. Your one duty, "
                  "once per scheduler cycle: check the brake, select the newest OPEN index-watch "
                  "ticket, run index_watch.py against it (the run spawns its own successor), and "
                  "settle the member you ran plus any older superseded one, so exactly one index-"
                  "watch is ever open. You route and settle; you never index, author or judge work "
                  "product, and you never erase." % CHAIN_AGENT})
    return CHAIN_AGENT


# ── LANE 1: the index-watch chain ─────────────────────────────────────────────────────────────────
def watch_lane(iw, gov, run_watch, say, ticket=0, dry=False):
    """ONE turn of the chain, in the order the code executes it. Returns a report dict.

        1. SELECT     the HEAD: the newest OPEN index-watch ticket (`--ticket N` overrides).
        2. BRAKE      ticket.stops on the head — an active stop aimed at it or ANY ANCESTOR halts
                      the turn before anything acts. Because every member is 'spawned' from the
                      previous one, every earlier member IS an ancestor: one stop aimed anywhere in
                      the chain halts the whole chain, and that is the ticket's brake.
        3. RECONCILE  settle every OPEN member older than the head — superseded, and losing nothing
                      (the head's delta is sha-computed and subsumes theirs).
        4. RUN        index_watch.py against the head. The run indexes the delta and SPAWNS the
                      successor itself.
        5. SETTLE     the head — only if the run completed, and therefore only AFTER its successor
                      exists. The chain is never left without an open member.
        6. VERIFY     re-read the queue and REPORT how many members are open. The ACCEPTANCE says
                      exactly one; this prints what is actually true.

    `run_watch(tid) -> exit code` is injected: in production it is a subprocess of index_watch.py;
    in `selftest` it is the real Watch driven against a throwaway corpus. Both drive THIS function.

    `dry=True` stops after step 2 and REPORTS what steps 3-5 would do. It WRITES NOTHING: no agent is
    registered, nothing is run, settled or spawned, and no file is created (not even the lock). Only
    READ routes are called — ticket.queue, ticket.stops, kind.roster, and a ticket row read if
    `--ticket` named one outside the queue. This mirrors index_watch.py's own --dry-run, and is the
    safe way to look at a live chain.
    """
    rep = {"head": 0, "halted": False, "ran": None, "settled": [], "superseded": [],
           "open_after": [], "ok": True, "dry": bool(dry)}

    # step 1: SELECT the head
    members = open_members(iw, gov)
    if ticket:
        head = int(ticket)
        say("  select : #%s (--ticket override)" % head)
    elif not members:
        say("  select : no OPEN index-watch ticket — the chain is not running. Start it with "
            "`dispatch_schedule.py watch --ticket N` against an index-watch ticket; its run spawns "
            "the successor and every cycle after this one is hands-off.")
        return rep
    else:
        head = int(members[-1]["id"])       # ticket.queue is ORDER BY id: the last is the newest
        say("  select : head #%s (newest of %d open index-watch ticket(s): %s)"
            % (head, len(members), ", ".join("#%s" % m["id"] for m in members)))
    rep["head"] = head

    # step 2: the BRAKE — before anything acts
    stops = gov.rows("ticket.stops", {"ticket_id": head})
    n_stops = int(stops[0].get("active_stops", 0)) if stops else 0
    if n_stops > 0:
        rep["halted"] = True
        say("  brake  : HALT — %d active stop ticket(s) aim at #%s or an ancestor; the chain "
            "authorizes nothing. Nothing was run, settled or spawned. Release the stop with a "
            "'starts' edge to resume." % (n_stops, head))
        return rep
    say("  brake  : no active stops on #%s or its ancestors" % head)

    pats = patterns(gov)
    by_id = {int(m["id"]): m for m in members}
    older = [m for m in members if int(m["id"]) != head]

    def head_kind():
        """The head's kind. `--ticket N` can name a ticket that is not in the queue listing, so fall
        back to reading its row rather than reporting a confident None."""
        if head in by_id:
            return by_id[head].get("kind")
        return (gov.ticket_row(head) or {}).get("kind")

    if dry:
        settleable = [int(m["id"]) for m in older if pats.get(m.get("kind")) == "solo"]
        stuck = [int(m["id"]) for m in older if pats.get(m.get("kind")) != "solo"]
        hk = head_kind()
        say("  DRY-RUN: nothing below is done; this is what a real cycle WOULD do.")
        say("  would  : run index_watch.py --ticket %s (it would index the delta and spawn the "
            "successor, kind %r)" % (head, DEFAULT_KIND))
        if pats.get(hk) == "solo":
            say("  would  : settle #%s once that run completed" % head)
        else:
            say("  would  : NOT settle #%s — kind %r is a %s kind; only its pair can settle it"
                % (head, hk, pats.get(hk) or "unknown"))
        say("  would  : settle %d superseded older member(s): %s"
            % (len(settleable), ", ".join("#%s" % i for i in settleable) or "none"))
        if stuck:
            say("  would  : leave %d pair-kind member(s) open (%s) — only their pairs can settle them"
                % (len(stuck), ", ".join("#%s" % i for i in stuck)))
        rep["open_after"] = [int(m["id"]) for m in members]
        return rep

    register(iw, gov)

    # step 3: RECONCILE — older open members are superseded by the head. A pair-kind member is not
    # attempted (tg_tickets_pair_completion would refuse it) and is summarised in one line rather
    # than one refusal per member per cycle.
    stuck = []
    for m in older:
        mid = int(m["id"])
        if pats.get(m.get("kind")) != "solo":
            stuck.append(mid)
            continue
        if settle(iw, gov, mid, m.get("kind"), pats,
                  "index-chain: SUPERSEDED by newer index-watch #%s, which this schedule ran. Nothing "
                  "is lost: the index-watch delta is computed from blob shas against the store, never "
                  "from a mark, so any blob this ticket would have indexed is still unsettled and #%s "
                  "picks it up. Settled by %s to hold the bound of one open index-watch."
                  % (head, head, CHAIN_AGENT), say):
            rep["superseded"].append(mid)
    if stuck:
        say("  reconc : %d older member(s) left open — %s are pair kind(s); DONE needs two distinct "
            "agents in two distinct roles (tg_tickets_pair_completion) and this lane assigns none. "
            "Their pairs settle them. No stop is aimed at them: they are ANCESTORS of the head, and "
            "a stop would propagate down the 'spawned' chain and halt the live chain itself."
            % (len(stuck), ", ".join("#%s" % i for i in stuck)))

    # step 4: RUN the head — the run spawns the successor itself
    rc = run_watch(head)
    rep["ran"] = rc
    say("  run    : index_watch.py --ticket %s -> exit %s (%s)"
        % (head, rc, WATCH_EXITS.get(rc, "unknown")))
    if rc != 0:
        rep["ok"] = False
        say("  settle : #%s NOT settled — its run did not complete, so it may have spawned no "
            "successor; settling it could leave the chain with no open member. It stays open and "
            "the next cycle retries it." % head)
    else:
        # step 5: SETTLE the head — its successor exists (the run filed it before returning 0)
        if settle(iw, gov, head, head_kind(), pats,
                  "index-chain: RAN and settled by %s on the dispatch schedule. Its successor was "
                  "spawned by the run itself (index_watch.py step 8) before this settle, so the "
                  "chain is never without an open member." % CHAIN_AGENT, say):
            rep["settled"].append(head)

    # step 6: VERIFY — report the invariant rather than assert it
    still = open_members(iw, gov)
    rep["open_after"] = [int(m["id"]) for m in still]
    solo_open = [int(m["id"]) for m in still if pats.get(m.get("kind")) == "solo"]
    pair_open = [int(m["id"]) for m in still if pats.get(m.get("kind")) != "solo"]
    if len(still) == 1:
        say("  chain  : 1 open index-watch (#%s) — the bound holds; it is primed for the next delta"
            % rep["open_after"][0])
    elif len(solo_open) == 1 and pair_open:
        # The honest report for a chain that predates this schedule: its members inherited a pair
        # kind and no mechanical runner can settle them. The bound holds for the chain this
        # schedule owns; the legacy members are named, not hidden, and not spun as success.
        rep["ok"] = False
        say("  chain  : %d open index-watch ticket(s) — 1 settleable head (#%s), plus %d PAIR-kind "
            "member(s) (%s) this schedule cannot settle and must not stop. The ACCEPTANCE's 'exactly "
            "one open' is NOT met until those settle through their pairs (the dispatch lane can "
            "route them); every member spawned from now on is kind %r and settles here."
            % (len(still), solo_open[0], len(pair_open), ", ".join("#%s" % i for i in pair_open),
               DEFAULT_KIND))
    else:
        rep["ok"] = False
        say("  chain  : %d open index-watch ticket(s) (%s) — the bound wants exactly 1"
            % (len(still), ", ".join("#%s" % i for i in rep["open_after"]) or "none"))
    return rep


def subprocess_watch(cfg, say):
    """Production `run_watch`: index_watch.py in its own process, output straight into the log."""
    def run(tid):
        cmd = [sys.executable, INDEX_WATCH, "--ticket", str(tid)]
        if cfg["successor_kind"]:
            cmd += ["--successor-kind", cfg["successor_kind"]]
        if cfg["watch_limit"]:
            cmd += ["--limit", str(cfg["watch_limit"])]
        say("  run    : %s" % " ".join(cmd))
        try:
            return subprocess.run(cmd, cwd=ROOT, timeout=cfg["watch_timeout"]).returncode
        except subprocess.TimeoutExpired:
            say("  run    : TIMEOUT after %ss — the head is left open for the next cycle"
                % cfg["watch_timeout"])
            return -1
    return run


def do_watch(a, cfg, say):
    """The watch lane against the live governed surface. Returns an exit code."""
    iw = load_watch()
    key = iw._secret("CONGRUENCY_API_KEY")
    if not key and not a.dry_run:
        raise Fault("no CONGRUENCY_API_KEY (env or .secrets/ats.env) — settling and journaling go "
                    "through token routes, and the writes ARE the work")
    gov = iw.Gov(key=key)
    kind = a.successor_kind or cfg["successor_kind"]
    if a.limit >= 0:
        cfg = dict(cfg, watch_limit=a.limit)
    cfg = dict(cfg, successor_kind=kind)
    say("== watch == the index-watch chain (successor kind %r, limit %s)%s"
        % (kind, cfg["watch_limit"] or "none", " — DRY-RUN, nothing is written" if a.dry_run else ""))
    try:
        rep = watch_lane(iw, gov, subprocess_watch(cfg, say), say, ticket=a.ticket, dry=a.dry_run)
    except iw.GovError as e:
        say("== watch == a governed route failed: %s" % e)
        return 3
    if rep["halted"]:
        return 4
    return 0 if rep["ok"] else 3


# ── LANE 2: dispatch-01 routes the queue (pre-existing behaviour, unchanged) ──────────────────────
def do_dispatch(cfg, say):
    """`pair_loop.py --dispatch <cap>`: dispatch-01 decides run/skip/stop and executes. The BOUNDS
    are the safety case: the per-run cap, the stop-ticket brake pair_loop checks before acting, and
    the SQL governance that refuses erasure no matter what a scheduled agent does."""
    say("== dispatch == dispatch-01 routes up to %d queue ticket(s)" % cfg["cap"])
    cmd = [sys.executable, PAIR_LOOP, "--dispatch", str(cfg["cap"]), "--timeout", str(cfg["timeout"])]
    say("  run    : %s" % " ".join(cmd))
    rc = subprocess.run(cmd, cwd=ROOT).returncode
    say("== dispatch == exit %s" % rc)
    return rc


# ── ONE CYCLE = lane 1 then lane 2 ────────────────────────────────────────────────────────────────
def do_cycle(a, cfg, say):
    """What launchd runs. The watch lane FIRST (it settles what it ran, so dispatch-01 never sees
    it), then the dispatch lane. The flock spans BOTH so one cycle is one cycle.

    --dry-run takes NO lock and creates no lock file: it changes nothing, so it needs no
    exclusivity, and an inspection you cannot run while a cycle is in flight would be a poor
    inspection.
    """
    lock = None if a.dry_run else acquire()
    if lock is None and not a.dry_run:
        say("== cycle == another cycle holds %s — this one did nothing (the bound: one index-watch "
            "in flight at a time)" % LOCK)
        return 5
    try:
        say("== cycle == %s — repo %s" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), ROOT))
        rc = 0
        if a.no_watch or not cfg["watch_enabled"]:
            say("== watch == SKIPPED (%s)"
                % ("--no-watch" if a.no_watch else "registry.json dispatch.index_watch.enabled=false"))
        else:
            rc = do_watch(a, cfg, say)
        if a.dry_run:
            # --dry-run writes nothing, and dispatch-01 routing the queue is emphatically a write:
            # it spawns pairs that branch, commit and settle tickets. Reported, never run.
            say("== dispatch == NOT RUN (--dry-run) — a real cycle would here run: %s"
                % " ".join([sys.executable, PAIR_LOOP, "--dispatch", str(cfg["cap"]),
                            "--timeout", str(cfg["timeout"])]))
        elif not a.no_dispatch:
            do_dispatch(cfg, say)
        else:
            say("== dispatch == SKIPPED (--no-dispatch)")
        say("== cycle == done (watch exit %s)" % rc)
        return rc
    finally:
        if lock is not None:
            lock.close()


# ── the LaunchAgent ───────────────────────────────────────────────────────────────────────────────
def build_plist(c):
    python3 = sys.executable or shutil.which("python3")
    claude = shutil.which("claude")
    if not claude:
        raise SystemExit("`claude` CLI not on PATH — the pairs of the dispatch lane cannot spawn; "
                         "aborting install")
    path = ":".join(dict.fromkeys([os.path.dirname(claude), "/usr/local/bin", "/usr/bin", "/bin"]))
    os.makedirs(LOGS, exist_ok=True)
    return {
        "Label": LABEL,
        "ProgramArguments": [python3, SELF, "cycle"],
        "WorkingDirectory": ROOT,
        "StartInterval": int(c["interval_hours"] * 3600),
        "RunAtLoad": False,
        "StandardOutPath": os.path.join(LOGS, "dispatch.log"),
        "StandardErrorPath": os.path.join(LOGS, "dispatch.err"),
        "EnvironmentVariables": {"PATH": path, "HOME": os.path.expanduser("~")},
    }


def domain():
    return "gui/%d" % os.getuid()


def install(cfg):
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    with open(PLIST, "wb") as fh:
        plistlib.dump(build_plist(cfg), fh)
    subprocess.run(["launchctl", "bootout", domain(), PLIST], capture_output=True)  # reload-safe
    r = subprocess.run(["launchctl", "bootstrap", domain(), PLIST], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("launchctl bootstrap failed: %s" % (r.stderr or r.stdout).strip())
    print("installed %s: one cycle every %gh — the index-watch chain (%s) then dispatch-01 (cap %d); "
          "log %s" % (LABEL, cfg["interval_hours"],
                      "enabled, successor kind %r" % cfg["successor_kind"] if cfg["watch_enabled"]
                      else "disabled", cfg["cap"], os.path.join(LOGS, "dispatch.log")))
    return 0


def uninstall():
    subprocess.run(["launchctl", "bootout", domain(), PLIST], capture_output=True)
    if os.path.exists(PLIST):
        os.remove(PLIST)
    print("uninstalled %s — the chain stops advancing; open tickets are untouched" % LABEL)
    return 0


def chain_line():
    """One line on the chain's live state for `status`. The surface may legitimately be down; that
    is an ANSWER about the chain, not a crash of the status command."""
    try:
        iw = load_watch()
        gov = iw.Gov(key=iw._secret("CONGRUENCY_API_KEY"))
        members = open_members(iw, gov)
    except (Fault, Exception) as e:  # noqa: BLE001
        return "chain: unreadable — %s" % str(e).split("\n")[0][:120]
    if not members:
        return "chain: no open index-watch ticket (not running — see `watch --ticket N`)"
    return "chain: %d open index-watch ticket(s) — head #%s%s" % (
        len(members), members[-1]["id"],
        "" if len(members) == 1 else " (the bound wants exactly 1: %s)"
        % ", ".join("#%s" % m["id"] for m in members))


def status():
    r = subprocess.run(["launchctl", "print", "%s/%s" % (domain(), LABEL)], capture_output=True, text=True)
    loaded = r.returncode == 0
    print("%s: %s" % (LABEL, "LOADED" if loaded else "not loaded"))
    if loaded:
        for ln in r.stdout.splitlines():
            if any(k in ln for k in ("state =", "runs =", "last exit", "interval")):
                print("  " + ln.strip())
    print("  " + chain_line())
    log = os.path.join(LOGS, "dispatch.log")
    if os.path.isfile(log):
        with open(log) as fh:
            tail = fh.readlines()[-8:]
        print("-- %s (tail) --" % log)
        for ln in tail:
            print("  " + ln.rstrip())
    return 0 if loaded else 1


def run_once():
    r = subprocess.run(["launchctl", "kickstart", "-k", "%s/%s" % (domain(), LABEL)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("kickstart failed (is it installed? run `install` first): %s"
                         % (r.stderr or r.stdout).strip())
    print("kickstarted %s — watch %s" % (LABEL, os.path.join(LOGS, "dispatch.log")))
    return 0


# ── selftest: the chain, proven offline ───────────────────────────────────────────────────────────
# The real pair/solo patterns of migrations/0029_ticket_authorization.sql:35-45 — the fact the settle
# turns on. index_watch's own FakeGov answers kind.roster with 'pair' for everything, which would
# make every settle look refused; this is the real table.
PATTERNS = {"build": "pair", "bug": "pair", "documentation": "pair", "bet": "pair",
            "design": "solo", "spec": "solo", "test": "solo", "rfc-investigation": "solo",
            "audit": "solo", "stop": "solo", "start": "solo"}


def chain_gov(iw):
    """index_watch's own FakeGov, extended with the routes the SCHEDULE calls that a watch run never
    does: ticket.queue (where the head is selected from), process_status (the settle), and a
    kind.roster carrying the REAL patterns.

    process_status enforces tg_tickets_pair_completion (0029:133-140) exactly as the db does, so the
    selftest proves the settle against the real rule — including that a pair-kind member is refused.
    """

    class ChainGov(iw.FakeGov):
        def __init__(self, tickets=None, active_stops=0):
            iw.FakeGov.__init__(self, tickets=tickets, kinds=tuple(sorted(PATTERNS)),
                                active_stops=active_stops)
            self.agent_roles = {}      # ticket_id -> {(agent_id, role)}, what ticket.assign would fill

        def rest(self, route, obj=None, method=None):
            obj = obj or {}
            if route == "ticket.queue":
                self.calls.append((route, dict(obj)))
                return {"rows": [dict(t) for t in sorted(self.tickets.values(), key=lambda r: r["id"])
                                 if str(t.get("status") or "").upper() in ("OPEN", "REQUESTED")]}
            if route == "kind.roster":
                self.calls.append((route, dict(obj)))
                return {"rows": [{"kind": k, "pattern": p} for k, p in sorted(PATTERNS.items())]}
            if route == "process_status":
                self.calls.append((route, dict(obj)))
                tid, st = int(obj["id"]), str(obj["status"]).upper()
                t = self.tickets[tid]
                pairs = self.agent_roles.get(tid) or set()
                if st == "DONE" and PATTERNS.get(t.get("kind")) == "pair" and (
                        len({a for a, _ in pairs}) < 2 or len({r for _, r in pairs}) < 2):
                    raise iw.GovError("a pair ticket is an adversarial network: DONE requires two "
                                      "DISTINCT agents in two DISTINCT roles")
                t["status"] = st
                return {"affected": 1}
            return iw.FakeGov.rest(self, route, obj, method)

    return ChainGov


def selftest(quiet_watch=True):
    """Drive REAL index_watch runs, through THIS module's watch_lane, over a throwaway omni-git
    corpus — several cycles with intermittent new commits — and CHECK the ticket's ACCEPTANCE.

    Nothing live is touched: no congruency db (a recording stand-in answers every route), no vector
    store but a temp one, no litellm proxy (a deterministic local embedder), no network, no ticket
    filed, no LaunchAgent, and no file outside the temp dir that is deleted at the end.
    """
    checks = []

    def ck(name, cond, detail=""):
        checks.append(bool(cond))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name,
                                ("  — %s" % detail) if detail and not cond else ""))

    def hush(_msg):
        pass

    iw = load_watch()
    cs = iw.load_indexer()
    base = tempfile.mkdtemp(prefix="dispatch_schedule-selftest-")
    try:
        chunker = cs.load_chunker(cs.CODEBEAN)
        omni_db, omni_git, shas = iw._st_corpus(base)
        store = os.path.join(base, "code_sim.db")
        print("== selftest == throwaway corpus %s (no live db, no network, no ticket filed)" % base)
        ChainGov = chain_gov(iw)

        # The seed: a chain member exactly as index_watch spawns them — its minted title, kind
        # `audit` (the solo kind the schedule keeps the chain in), REQUESTED as ticket.create leaves
        # it. No mark anywhere, so its run is GENESIS: the whole corpus is its delta.
        seed = {300: {"id": 300, "title": iw.SUCCESSOR_TITLE % 197, "body": "",
                      "kind": "audit", "status": "REQUESTED", "component": "congruency"}}
        gov = ChainGov(tickets=seed)

        def run_watch(tid):
            w = iw.Watch(cs, gov, omni_db, omni_git, store, chunker, iw._fake_embed, "nomic-embed",
                         cs.DOC_PREFIX, cs.MAX_CHARS, component="congruency")
            try:
                w.run(tid, spawn=True, successor_kind="audit", verbose=False)
                return 0
            except iw.Halted:
                return 5

        def cycle(ticket=0):
            return watch_lane(iw, gov, run_watch, hush if quiet_watch else print, ticket=ticket)

        def opens():
            return [int(m["id"]) for m in open_members(iw, gov)]

        def searchable(sha):
            con = cs.ro_connect(store)
            try:
                return con.execute("SELECT repo, path, vector FROM code_sim_index WHERE blob_sha = ?",
                                   (sha,)).fetchall()
            finally:
                con.close()

        def settled_shas():
            con = cs.ro_connect(store)
            try:
                return {r[0] for r in con.execute("SELECT sha FROM blobs")}
            finally:
                con.close()

        # ── the recogniser: what the lane will and will not pick up ──
        print("-- the recogniser: which tickets are chain members")
        ck("a spawned successor's TITLE identifies it", is_member(iw, {"title": iw.SUCCESSOR_TITLE % 9}))
        ck("...so does the machine-readable predecessor line in its body",
           is_member(iw, {"body": "%s 9" % iw.BODY_PRED}))
        ck("...and the mark line", is_member(iw, {"body": "%s {}" % iw.BODY_MARK}))
        ck("an unrelated ticket is NOT a member",
           not is_member(iw, {"title": "Build: something else", "body": "index the docs"}))

        # ── cycle 1: genesis — the chain head indexes the whole corpus ──
        print("-- cycle 1: genesis (the whole corpus is the delta)")
        r1 = cycle()
        ck("the head was selected", r1["head"] == 300, str(r1["head"]))
        ck("the brake let it through", not r1["halted"])
        ck("the run completed", r1["ran"] == 0, str(r1["ran"]))
        ck("ACCEPTANCE: every in-scope blob is now fingerprinted (settled in the store)",
           settled_shas() == set(shas.values()), "%d settled" % len(settled_shas()))
        ck("ACCEPTANCE: an indexed blob is omni-indexed + searchable ({repo,path} + vector)",
           len(searchable(shas["a"])) > 0 and all(r[0] and r[1] and r[2] for r in searchable(shas["a"])),
           str(searchable(shas["a"])[:1]))
        ck("the head was SETTLED (it left the queue)", r1["settled"] == [300], str(r1["settled"]))
        ck("...via the governed process_status route, to DONE",
           any(c[1].get("id") == 300 and c[1].get("status") == "DONE"
               for c in gov.calls if c[0] == "process_status"))
        ck("ACCEPTANCE: exactly ONE open index-watch remains", len(opens()) == 1, str(opens()))
        s1 = opens()[0]
        ck("...and it is the SUCCESSOR the run spawned, not the one we ran", s1 != 300 and s1 > 300,
           str(s1))
        ck("...linked to its predecessor by a 'spawned' edge", (300, s1, "spawned") in gov.edges,
           str(gov.edges))
        ck("...and it is kinded with the SOLO kind, so the schedule can settle it too",
           gov.tickets[s1]["kind"] == "audit", str(gov.tickets[s1]["kind"]))
        ck("the settle happened AFTER the spawn (the chain is never without an open member)",
           [c[0] for c in gov.calls].index("ticket.create")
           < [c[0] for c in gov.calls].index("process_status"))
        ck("the lane registered its agent", CHAIN_AGENT in gov.agents, str(gov.agents))
        ck("...and is NOT ticket.assign'd on the ticket (it authorizes nothing)",
           not gov.routes("ticket.assign"))

        # ── cycle 2: no new commits — a clean no-op that still advances the chain ──
        print("-- cycle 2: no new commits (a no-op that still perpetuates the chain)")
        before = set(settled_shas())
        r2 = cycle()
        ck("the head is the successor cycle 1 spawned", r2["head"] == s1, str(r2["head"]))
        ck("the no-op run completed", r2["ran"] == 0, str(r2["ran"]))
        ck("nothing was re-indexed (idempotent on blob sha)", settled_shas() == before)
        ck("ACCEPTANCE: still exactly ONE open index-watch", len(opens()) == 1, str(opens()))
        s2 = opens()[0]
        ck("...and the chain still advanced (a NEW successor, no human step)", s2 != s1 and s2 > s1,
           str(s2))

        # ── cycle 3: an intermittent new commit — the whole point ──
        print("-- cycle 3: a new commit lands between cycles (the delta must find it)")
        new_sha = iw._st_commit_new_code(omni_db, omni_git)
        ck("the new blob is NOT yet fingerprinted", new_sha not in settled_shas())
        r3 = cycle()
        ck("the run completed", r3["ran"] == 0, str(r3["ran"]))
        ck("ACCEPTANCE: the newly committed blob is now fingerprinted, with NO manual step",
           new_sha in settled_shas())
        ck("ACCEPTANCE: ...and omni-indexed + searchable at its {repo, path}, with a vector",
           [(r[0], r[1]) for r in searchable(new_sha)] == [("repo-one", "pkg/mod_new.py")]
           and all(r[2] for r in searchable(new_sha)), str(searchable(new_sha)))
        ck("ACCEPTANCE: still exactly ONE open index-watch", len(opens()) == 1, str(opens()))
        s3 = opens()[0]
        ck("...and it is a fresh successor primed for the next delta", s3 != s2 and s3 > s2, str(s3))
        ck("...carrying the mark forward in its body", iw.BODY_MARK in (gov.tickets[s3]["body"] or ""))

        # ── cycle 4: quiet again — the chain does not die ──
        print("-- cycle 4: quiet again (the chain is perpetual)")
        r4 = cycle()
        ck("the chain ran a 4th cycle unattended", r4["ran"] == 0 and r4["settled"] == [s3],
           "%s %s" % (r4["ran"], r4["settled"]))
        ck("ACCEPTANCE: still exactly ONE open index-watch", len(opens()) == 1, str(opens()))
        ck("ACCEPTANCE: after 4 cycles the WHOLE corpus is fingerprinted, nothing dropped",
           settled_shas() == set(shas.values()) | {new_sha},
           "%d of %d" % (len(settled_shas()), len(shas) + 1))
        ck("every cycle settled exactly the member it ran", len(gov.routes("process_status")) == 4,
           str(gov.routes("process_status")))

        # ── the brake: a stop aimed at the chain halts it ──
        print("-- the brake: a stop ticket aimed at the chain halts it")
        head_before = opens()[0]
        settled_before, calls_before = set(settled_shas()), len(gov.calls)
        gov.active_stops = 1                    # what ticket.stops answers for the head or an ancestor
        r5 = cycle()
        ck("the cycle HALTED", r5["halted"], str(r5))
        ck("...nothing was run", r5["ran"] is None, str(r5["ran"]))
        ck("...nothing was settled", not r5["settled"] and not r5["superseded"], str(r5))
        ck("...nothing was indexed", settled_shas() == settled_before)
        ck("...no successor was spawned (a stop the chain outran would be no stop at all)",
           opens() == [head_before], str(opens()))
        ck("...and the ONLY routes it called were the queue read and the brake itself",
           {c[0] for c in gov.calls[calls_before:]} == {"ticket.queue", "ticket.stops"},
           str({c[0] for c in gov.calls[calls_before:]}))

        # ── the release: the chain resumes, unattended ──
        print("-- the release: a 'starts' edge releases the stop and the chain resumes")
        gov.active_stops = 0
        r6 = cycle()
        ck("the chain resumed on the very next cycle", r6["ran"] == 0 and not r6["halted"], str(r6))
        ck("ACCEPTANCE: exactly ONE open index-watch again", len(opens()) == 1, str(opens()))

        # ── reconcile: a crashed cycle left two open; the bound is restored ──
        print("-- reconcile: two open members (a cycle that spawned but never settled)")
        stray = opens()[0]
        extra = gov.rest("ticket.create", {"component": "congruency", "body": "%s %d" % (iw.BODY_PRED, stray),
                                           "title": iw.SUCCESSOR_TITLE % stray, "severity": "normal",
                                           "patch": ""})
        eid = int(extra["rowid"])
        gov.rest("ticket.kind", {"id": eid, "kind": "audit"})
        ck("two index-watch tickets are open (the bound is broken)", len(opens()) == 2, str(opens()))
        r7 = cycle()
        ck("the lane ran the NEWEST of them", r7["head"] == eid, "%s vs %s" % (r7["head"], eid))
        ck("...and settled the older one as SUPERSEDED", r7["superseded"] == [stray], str(r7["superseded"]))
        ck("ACCEPTANCE: the bound is restored — exactly ONE open index-watch", len(opens()) == 1,
           str(opens()))
        ck("...and no blob was lost to the reconcile (the delta is sha-computed, not mark-filtered)",
           settled_shas() == set(shas.values()) | {new_sha})

        # ── the settle gate: a pair-kind member cannot be settled mechanically ──
        print("-- the settle gate: why the chain is a SOLO kind")
        pair_seed = {400: {"id": 400, "title": iw.SUCCESSOR_TITLE % 197, "body": "",
                           "kind": "build", "status": "REQUESTED", "component": "congruency"}}
        gov2 = ChainGov(tickets=pair_seed)
        store2 = os.path.join(base, "code_sim2.db")

        def run_watch2(tid):
            w = iw.Watch(cs, gov2, omni_db, omni_git, store2, chunker, iw._fake_embed, "nomic-embed",
                         cs.DOC_PREFIX, cs.MAX_CHARS, component="congruency")
            w.run(tid, spawn=True, successor_kind="audit", verbose=False)
            return 0

        r8 = watch_lane(iw, gov2, run_watch2, hush)
        ck("a pair-kind member RUNS and spawns its successor", r8["ran"] == 0 and len(gov2.edges) == 1,
           str(gov2.edges))
        ck("...but is NOT settled (tg_tickets_pair_completion refuses DONE without a pair)",
           r8["settled"] == [], str(r8["settled"]))
        ck("...the lane did not even attempt the settle, and never faked one",
           not any(c[1].get("status") == "DONE" for c in gov2.calls if c[0] == "process_status"))
        ck("...and it is REPORTED, not hidden: the bound is not yet met", not r8["ok"], str(r8["ok"]))
        ck("...while the successor it spawned IS the solo kind, so the chain settles from there on",
           gov2.tickets[int(gov2.edges[0][1])]["kind"] == "audit")
        # prove the stand-in really enforces the rule it claims to mirror
        try:
            gov2.rest("process_status", {"id": 400, "status": "DONE"})
            refused = False
        except iw.GovError:
            refused = True
        ck("...and that refusal is the REAL rule: DONE on a pair kind aborts without two agents/roles",
           refused)

        # ── --dry-run: the docstring says it writes NOTHING; prove it ──
        print("-- --dry-run: reports the plan, writes nothing")
        dry_head = opens()[0]
        dry_settled, dry_calls, dry_tickets = set(settled_shas()), len(gov.calls), len(gov.tickets)
        rd = watch_lane(iw, gov, run_watch, hush, dry=True)
        ck("--dry-run names the head it WOULD run", rd["head"] == dry_head, str(rd["head"]))
        ck("...runs nothing", rd["ran"] is None, str(rd["ran"]))
        ck("...settles nothing", not rd["settled"] and not rd["superseded"], str(rd))
        ck("...indexes nothing", settled_shas() == dry_settled)
        ck("...spawns nothing (no ticket is filed)", len(gov.tickets) == dry_tickets)
        ck("...and calls ONLY read routes — no agent.register, no process_status, no write at all",
           {c[0] for c in gov.calls[dry_calls:]} <= {"ticket.queue", "ticket.stops", "kind.roster"},
           str({c[0] for c in gov.calls[dry_calls:]}))
        ck("...leaving the chain exactly as it found it", opens() == [dry_head], str(opens()))

        # ── no chain, and the explicit override ──
        print("-- edges: an empty chain, and the --ticket override")
        empty = ChainGov(tickets={500: {"id": 500, "title": "Build: unrelated", "body": "",
                                        "kind": "build", "status": "OPEN"}})
        r9 = watch_lane(iw, empty, lambda t: 0, hush)
        ck("no open index-watch => nothing is run and nothing is settled",
           r9["head"] == 0 and r9["ran"] is None and not r9["settled"], str(r9))
        ck("...and an unrelated open ticket was not mistaken for one", not r9["open_after"], str(r9))

        # ── the lock: one watch in flight at a time ──
        print("-- the bound: one cycle at a time (flock)")
        lk = os.path.join(base, "x.lock")
        h1 = acquire(lk)
        ck("the first cycle takes the lock", h1 is not None)
        ck("...and a second cycle is refused it (it would do nothing)", acquire(lk) is None)
        h1.close()
        h2 = acquire(lk)
        ck("...and the lock is released when the cycle ends (a crash never wedges the chain)",
           h2 is not None)
        if h2:
            h2.close()

        # ── the run-failure guard ──
        print("-- a failed run is never settled")
        gov3 = ChainGov(tickets={600: {"id": 600, "title": iw.SUCCESSOR_TITLE % 1, "body": "",
                                       "kind": "audit", "status": "REQUESTED"}})
        r10 = watch_lane(iw, gov3, lambda t: 3, hush)      # exit 3 = the proxy was unreachable
        ck("a run that failed leaves its ticket OPEN for the next cycle",
           r10["settled"] == [] and 600 in r10["open_after"], str(r10))
        ck("...and the failure is reported, not swallowed", not r10["ok"])

    finally:
        shutil.rmtree(base, ignore_errors=True)
    ok = sum(1 for c in checks if c)
    print("\n== selftest == %d/%d checks passed" % (ok, len(checks)))
    print("== selftest == throwaway corpus removed (the live db, the proxy and the network were "
          "never touched)")
    return 0 if ok == len(checks) else 1


# ── CLI ───────────────────────────────────────────────────────────────────────────────────────────
def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)     # progress visible when redirected to the log
    ap = argparse.ArgumentParser(
        prog="dispatch_schedule.py",
        description="the dispatch schedule: one timer, two lanes — the self-repopulating index-watch "
                    "chain (one link per cycle, exactly one open at a time, a stop ticket is the "
                    "brake) and dispatch-01 routing the queue.")
    ap.add_argument("command", choices=["install", "uninstall", "status", "run-once", "cycle",
                                        "watch", "selftest"],
                    help="install/uninstall/status/run-once manage the LaunchAgent; `cycle` is one "
                         "full cycle in this process (what launchd runs); `watch` is the index-watch "
                         "lane alone; `selftest` proves the chain offline")
    ap.add_argument("--ticket", type=int, default=0,
                    help="watch/cycle: run the chain from THIS ticket instead of the newest open "
                         "index-watch (how a chain is seeded)")
    ap.add_argument("--successor-kind", default="",
                    help="watch/cycle: kind for the spawned successor (default: registry.json's "
                         "dispatch.index_watch.successor_kind, else %r). Must be a SOLO kind in "
                         "kind.roster or the chain cannot settle itself." % DEFAULT_KIND)
    ap.add_argument("--limit", type=int, default=-1,
                    help="watch/cycle: index at most N new blobs this run (default: registry.json's "
                         "dispatch.index_watch.limit, else no cap). Deferred blobs are picked up by "
                         "the next cycle — a cap never loses one.")
    ap.add_argument("--dry-run", action="store_true",
                    help="watch/cycle: report what the cycle WOULD run and settle, then stop. Writes "
                         "NOTHING: no agent registered, nothing run, settled or spawned — only the "
                         "read routes are called. The safe way to look at a live chain.")
    ap.add_argument("--no-watch", action="store_true", help="cycle: skip the index-watch lane")
    ap.add_argument("--no-dispatch", action="store_true", help="cycle: skip the dispatch-01 lane")
    a = ap.parse_args()

    if a.command == "selftest":
        return selftest()
    if a.command == "uninstall":
        return uninstall()
    if a.command == "status":
        return status()
    if a.command == "run-once":
        return run_once()

    cfg = config()
    if a.command == "install":
        return install(cfg)
    if a.command == "cycle":
        return do_cycle(a, cfg, print)

    # `watch`: the lane alone, under the same lock the cycle uses (--dry-run changes nothing, so it
    # takes no lock and creates no lock file)
    lock = None if a.dry_run else acquire()
    if lock is None and not a.dry_run:
        print("another cycle holds %s — doing nothing (the bound: one index-watch in flight at a "
              "time)" % LOCK)
        return 5
    try:
        return do_watch(a, cfg, print)
    finally:
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as e:
        print("dispatch_schedule: %s" % e)      # one line, never a traceback
        sys.exit(2)
