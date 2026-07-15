#!/usr/bin/env python3
"""dispatch_schedule.py — the dispatch SCHEDULE: dispatch-01's queue lane + the index-watch CHAIN
lane, on one timer, hands-off (ticket #198).

A macOS LaunchAgent runs `dispatch_schedule.py cycle` every `interval_hours`. ONE CYCLE is two lanes,
in the order the code executes them (do_cycle below):

    LANE 1 — THE WATCH (new: ticket #198). Advance the self-repopulating index-watch chain by exactly
             one link: select the newest OPEN index-watch ticket, run it, settle it. The run ITSELF
             spawns the successor (index_watch.py step 8), so the chain never runs dry.
    LANE 2 — THE DISPATCH (pre-existing). `pair_loop.py --dispatch <cap>` — dispatch-01 reads the
             queue and routes up to `cap` tickets to adversarial pairs.

TERMS (defined at first use — this file is read without its author present).

  * THE INDEX-WATCH is tools/index_watch.py: one run reads a high-water-mark, computes the
    new/changed code as an omni-git blob-sha DELTA, AST-chunks+embeds each new blob into the vector
    store, records each on the ticket's permanent manifest, advances the mark, and SPAWNS the next
    index-watch ticket carrying it. This module never re-implements any of that; it only decides
    WHICH ticket to run, WHEN, and settles it afterwards.
  * A BLOB SHA is git's content address: the sha IS a hash of the bytes. A changed file is, by
    definition, a new sha.
  * THE CHAIN is the sequence of index-watch tickets, each SPAWNED by the previous one (a
    parent->child row in `ticket_edges` with kind 'spawned', migrations/0012_ticket_edges.sql:6-12).
    THE HEAD is its newest open member — the only one this schedule runs.
  * OPEN means what the dispatch queue means by it: `ticket.queue` selects
    `upper(status) IN ('OPEN','REQUESTED')` (migrations/0032_dispatch_routes.sql:7). A ticket
    ticket.create mints is REQUESTED, so a freshly spawned successor is open by this definition.
  * A STOP TICKET is a `kind=stop` ticket aimed at a target by a 'stops' edge (the stop ticket is the
    edge's PARENT, the target its CHILD — pair_loop.py:581-584). It HALTS the target; it does NOT
    close it. `ticket.stops` (migrations/0030_pair_loop_routes.sql:21-26) counts active (unreleased)
    stops aimed at a ticket OR ANY ANCESTOR, walking 'spawned' edges UP. So a stop propagates DOWN to
    every descendant, and a 'starts' edge aimed at the stop ticket releases it.
  * HALTED means active_stops > 0. A halted ticket "authorizes nothing until a start ticket releases
    it" (dispatch-01's own registered prompt) and dispatch-01 skips it (pair_loop.py:521-532, "skip
    ... tickets with active_stops > 0"). It is still OPEN — a stop is a brake, not an eraser.
  * IN FLIGHT means OPEN and NOT HALTED: a member that actually authorizes work right now. This is
    the ticket's own primary phrasing of the bound ("one index-watch in flight at a time"), and it is
    the invariant this schedule holds and reports. See THE BOUND below, which states plainly where it
    differs from the ACCEPTANCE's looser restatement and why.
  * TO SETTLE a ticket is to drive it to DONE through the governed `process_status` route — the same
    settle pair_loop.py:1102 and local_graph.py:828 perform. It is what removes a ticket from the
    queue.
  * A GRAFT is the db's own prescribed way to change course on work that must not proceed: STOP the
    old + SPAWN a replacement, never edit or erase. The phrase is the database's, not this file's —
    tg_tickets_immutable_identity raises "append events, or stop+spawn (graft) a successor"
    (migrations/0029_ticket_authorization.sql:111-117), tg_tickets_no_delete raises "tickets are
    never deleted: aim a stop ticket at it" (0029:106), and dispatch-01's registered prompt says "To
    change course: stop + spawn (graft)". The `graft` command below is exactly that pattern.

THE BOUND — one index-watch in flight at a time. Four mechanisms, because "in flight" has several
distinct meanings and only all of them together make the ticket's bound true:

  1. ONE RUN AT A TIME (concurrency). An acting turn holds an exclusive, non-blocking `flock` on
     logs/dispatch_schedule.lock from start to finish. A second cycle that finds the lock held says
     so and does nothing (exit 5). launchd will not run two copies of one Label, but a human running
     `cycle` by hand beside the timer would otherwise overlap; the flock is what actually forbids it
     on this host. (A `--dry-run` changes nothing, so it takes no lock and is never blocked by one.)
  2. ONE LINK PER CYCLE (progress). Exactly one ticket is run per cycle — the HEAD, the newest open
     chain member. Older open members are never run.
  3. EXACTLY ONE IN FLIGHT (the invariant). The head is settled once its successor exists; any
     STRICTLY OLDER open member is settled as SUPERSEDED; and a member that is halted or that this
     lane may not settle is left alone and REPORTED. Each cycle ends by re-reading the queue and
     reporting BOTH counts — in flight and open — so the invariant is legible in the log rather than
     asserted here.
  4. CONVERGENCE, NOT COOPERATION (self-healing). The schedule cannot *prevent* dispatch-01 from also
     routing a chain member — dispatch-01 is an LLM inside pair_loop.py, its DISPATCH_RULES
     (pair_loop.py:521-532) carry no index-watch exclusion, and this ticket's deliverable is this file
     alone. That risk is real and is on the record: #267 has TWO spawned successors (#268 and #277),
     so the chain has already been forked once by something running it twice. So the bound is held by
     CONVERGENCE instead: from either damage mode the next cycle restores it with no manual step —
     a fork (2+ open) is reconciled to 1 by step 4, and a dead chain (0 open, e.g. a pair settled the
     only member without spawning) is RESEEDED by step 2. Both are proven in `selftest`.

WHY "IN FLIGHT" AND NOT "OPEN" — read this before judging the exit code. The ticket states the bound
as "one index-watch in flight at a time" and its ACCEPTANCE restates it as "exactly one open
index-watch exists at any time". Those two agree exactly when no member is halted, and the ticket
itself couples them: the brake is what takes a member out of flight. They come apart here for a
reason that is a FACT ABOUT THE LIVE RECORD, not a choice this file made:

  * The live chain's 8 open members (#266-#269, #275-#278) are all kind `build`, a PAIR pattern.
  * tg_tickets_pair_completion (0029:133-140) REFUSES DONE on a pair-pattern ticket unless
    ticket_agents holds two DISTINCT agents in two DISTINCT roles. No mechanical runner can satisfy
    that without fabricating an adversarial pair that never happened — which is precisely the fraud
    pair_loop.py's own forge_agent refuses ("Assigning a third, always-present agent would satisfy
    that check ... and quietly hollow the backstop out", pair_loop.py:614-621). This lane will not do
    it either: it assigns no agents, ever.
  * They cannot be re-kinded to a solo kind: `kind` is set-once (tg_tickets_immutable_identity,
    0029:111-117 — kind is in the identity tuple).
  * There is no lawful non-DONE exit from the queue for a kinded ticket. The 48 `CLOSED` rows in this
    db are all pre-kind legacy rows (kind IS NULL; `kind` arrived as a nullable column in
    0012_ticket_edges.sql:1); the only kinded terminal rows are two (`build`,`DONE`) settled by real
    pairs. Inventing a status to slip a pair ticket out of the queue would be the same backstop-
    hollowing by another route.
  * A stop halts but never closes — a halted ticket is still OPEN (live proof: #140 is OPEN with stop
    #154 aimed at it).

So "exactly one OPEN index-watch" is not reachable by ANY tool acting alone while those 8 sit open;
only their own adversarial pairs can lawfully settle them. "Exactly one IN FLIGHT" IS reachable, and
`graft` (below) reaches it in one command. This file therefore holds and reports the in-flight bound,
ALWAYS prints the raw open count beside it, and never claims the ACCEPTANCE's literal wording is
satisfied when it is not. Nothing here is hidden or spun; the numbers are printed every cycle.

(Even a perfectly healthy chain cannot make "exactly one open AT ANY INSTANT" true: a run spawns its
successor BEFORE its predecessor is settled, so 2 are briefly open. That order is deliberate and the
alternative is worse — settling first would leave a window with ZERO open members, and a crash there
kills a chain that is supposed to be perpetual. "Exactly one" is therefore an AT-REST invariant,
true between cycles, which is what `selftest` checks after each cycle.)

THE CHAIN MUST BE A SOLO KIND, AND THIS SCHEDULE IS WHY. Because a pair-kind member cannot be settled
mechanically (above), a chain of them could never satisfy the bound. So the lane runs the watch with
`--successor-kind` set to a SOLO kind (default `audit`: pattern solo, purpose "examine delivered work;
may spawn patch/refactor tickets" — 0029:43), which is settleable with no pair and no hollowing. This
also stops the backlog GROWING: a pair that followed a legacy member's own body instruction
(`index_watch.py --ticket N`, no --successor-kind) would inherit `build` at index_watch.py:731
(`kind = successor_kind or own_kind`) and spawn yet another unsettleable member. Every successor this
schedule causes is `audit`, and `graft` halts the legacy members so no pair is ever routed to them.

THE AGENT. The lane registers `index-chain-01` (agent.register — a normal agent) and attributes its
journal writes to it. It is deliberately NOT ticket.assign'd, exactly as dispatch-01 and forge-t<id>
journal onto tickets they touch without being authorized on them (pair_loop.py:573-574,614-621).

Config lives in the repo registry.json (walked up to; refuses to run without it, per note-for-claude).
The `index_watch` block is OPTIONAL — every key below is the default, so the schedule works against
today's registry.json unchanged:

    "dispatch": {"interval_hours": 6, "cap": 3, "timeout": 480,
                 "index_watch": {"enabled": true, "successor_kind": "audit", "reseed": true,
                                 "limit": 0, "timeout": 1800}}

    python3 dispatch_schedule.py install       # write + load the LaunchAgent (runs `cycle`)
    python3 dispatch_schedule.py uninstall     # unload + remove it
    python3 dispatch_schedule.py status        # loaded? the chain? last log lines
    python3 dispatch_schedule.py run-once      # kickstart one CYCLE now (needs `install` first)
    python3 dispatch_schedule.py cycle         # ONE cycle now, in THIS process (what launchd runs)
    python3 dispatch_schedule.py watch         # the index-watch lane ONLY, once
    python3 dispatch_schedule.py watch --ticket N   # ... run THIS member instead of the head
    python3 dispatch_schedule.py watch --dry-run    # what a cycle WOULD do; writes NOTHING
    python3 dispatch_schedule.py graft         # ONE-TIME: halt a chain this lane cannot settle and
                                               #   seed a fresh solo-kinded one (stop+spawn)
    python3 dispatch_schedule.py graft --dry-run    # what the graft WOULD do; writes NOTHING
    python3 dispatch_schedule.py selftest      # prove the chain offline; writes nothing, files nothing

`cycle`, `watch` and `graft` ACT on the live governed surface: they run the indexer, settle real
tickets, and (graft) file real stop tickets. `--dry-run`, `status` and `selftest` do not — they write
nothing anywhere and CREATE NO FILES (not even the lock, and not a __pycache__ entry: see the bytecode
note below). Reach for `--dry-run` first if you want to see what a command would do to a live chain.
Output lands in <repo>/logs/dispatch.log (+ .err); both live under the gitignored logs/ (.gitignore:20).

WHY `graft` IS NOT AUTOMATIC. A cycle never grafts. Filing a stop against live tickets is an
irreversible, append-only governance act on work that ticket #198 does not authorize this schedule to
retire, and an unattended timer must not decide that a human's chain must not proceed. So the cycle
NAMES the remedy in its log and exits 3 until a human runs it once. The ACCEPTANCE's "no manual step"
binds the blob pipeline — "every new blob ends up fingerprinted+omni-indexed with no manual step" —
and that is hands-off from the first cycle, graft or no graft; the graft is a one-time migration of a
mis-kinded chain that predates this schedule, after which the steady state is hands-off forever.

Exit codes (each prints ONE line, never a traceback):
    0  the turn ACTED and the in-flight bound holds — INCLUDING "no new blobs" and "nothing in the
       queue", which are clean no-ops. For `--dry-run` and `graft`, 0 means only that the REPORT (or
       the graft) succeeded: a --dry-run changes nothing, so it can neither hold nor break a bound
       and never exits 3 for one — read the `chain:`/`would :` lines it prints for the live counts.
    2  a precondition failure — no registry.json, index_watch.py not loadable, no CONGRUENCY_API_KEY,
       an unknown command
    3  the watch lane's turn did not fully succeed. Three distinct causes, and the log line says
       which: the run itself failed (a ticket whose run failed is NEVER settled — it stays open for
       the next cycle), a governed route failed, or the run succeeded but MORE THAN ONE index-watch
       is in flight (the log names `graft` as the remedy and why this lane cannot settle them itself)
    4  HALTED — an active stop ticket aims at the chain head or an ancestor; nothing was run, settled
       or spawned
    5  another cycle holds the lock — this one did nothing (the bound working, not an error case that
       needs a human)
    1  `selftest`: at least one check FAILED. `status`: the LaunchAgent is not loaded.

VERIFIED ON THE LIVE RECORD (2026-07-15, read-only, nothing written). `watch --dry-run` selects head
#278 of 8 open members (#266-#269, #275-#278), all kind `build`, and correctly declines to settle it.
`graft --dry-run` finds exactly ONE subtree root, #266, and the live 'spawned' edges confirm one stop
there reaches all 8: #197->#266->#267->{#277, #268->#269->#275->#276->#278}. The stop semantics this
rests on were checked against real rows rather than assumed: #140 (unreleased stop #154 aimed at it)
answers active_stops=1, and #308 (a stop released by a 'starts' edge) answers 0. #266's siblings #198
and #199 — also spawned by #197 — are NOT descendants of #266 and are unaffected, which is why the
graft aims at #266 and never at #197.

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

# The title this schedule mints for a chain ROOT it seeds itself (a reseed or a graft). index_watch's
# own successors are recognised by ITS title/body marks (is_member); a root has no spawning
# predecessor to be named after, so it carries this mark of its own instead of a fabricated
# "successor of #N" title that no 'spawned' edge would back up.
ROOT_TITLE = "Index-watch: chain root seeded by the dispatch schedule%s"

# index_watch.py's own exit codes, for a legible log (its module docstring, "Exit codes").
WATCH_EXITS = {0: "completed", 1: "coverage/verification failure", 2: "precondition failure",
               3: "embedding proxy unreachable", 4: "a governed route failed", 5: "HALTED by a stop"}


class Fault(Exception):
    """A precondition failure — reported as one line, exit 2."""


# ── index_watch.py, reused as-is (its constants, its governed surface, its runner) ────────────────
def load_watch(path=INDEX_WATCH):
    """Import tools/index_watch.py as a module.

    Everything this schedule needs to recognise, read and run a chain member already exists there and
    is imported rather than restated: the successor TITLE and the two machine-readable body lines it
    writes (SUCCESSOR_TITLE / BODY_PRED / BODY_MARK), the predecessor parser, the governed REST
    surface (Gov) and its api-key lookup, and — for `selftest` — the real Watch plus its throwaway-
    corpus scaffolding. Restating any of them here would let this file drift out of agreement with the
    tool it drives, which is precisely the failure that would make the chain silently stop matching
    its own tickets.
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
            "reseed": bool(w.get("reseed", True)),
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

    Four signals, and nothing else writes any of them: the three marks index_watch.py's spawn
    writes — the successor TITLE it mints (SUCCESSOR_TITLE) and the two machine-readable body lines
    its next run parses back out (BODY_PRED / BODY_MARK, index_watch.py's THE MARK) — all read from
    the imported module so that if that tool changes them this recogniser changes with it; plus
    ROOT_TITLE, the title THIS schedule mints for a root it seeds itself (seed_root below), which
    index_watch never writes because a root has no spawning predecessor.

    Deliberately NOT matched: the genesis `build` ticket that authored the tool. It carries none of
    these marks (nothing spawned it), it is a pair ticket whose work is the tool rather than a run,
    and its pair settles it. The chain this schedule drives is the tickets index_watch itself files
    plus the roots this schedule seeds. Point the lane at any ticket explicitly with `watch --ticket N`.
    """
    title, body = (t.get("title") or ""), (t.get("body") or "")
    return (title.startswith(iw.SUCCESSOR_TITLE.split("%")[0])
            or title.startswith(ROOT_TITLE.split("%")[0])
            or iw.BODY_PRED in body or iw.BODY_MARK in body)


def open_members(iw, gov):
    """Every OPEN chain member, oldest first — read from the dispatch queue itself (ticket.queue,
    migrations/0032_dispatch_routes.sql), so "open" here is the same "open" dispatch-01 sees."""
    return [t for t in gov.rows("ticket.queue", {}) if is_member(iw, t)]


def stops_on(gov, tid):
    """active_stops for one ticket — the count of unreleased stop tickets aimed at it OR ANY ANCESTOR
    (ticket.stops, migrations/0030_pair_loop_routes.sql:21-26). >0 means HALTED. This is the same
    per-ticket read pair_loop's own dispatcher does before deciding (pair_loop.py:560-562)."""
    rows = gov.rows("ticket.stops", {"ticket_id": int(tid)})
    return int(rows[0].get("active_stops", 0)) if rows else 0


def annotate(gov, members):
    """Stamp each member with its live active_stops, so one read per member serves every later step
    (head selection, reconcile, and the in-flight count all need it)."""
    for m in members:
        m["active_stops"] = stops_on(gov, int(m["id"]))
    return members


def in_flight(members):
    """The members that actually authorize work right now: OPEN and NOT HALTED. This is the bound the
    ticket states ("one index-watch in flight at a time") and the one this schedule holds."""
    return [m for m in members if not int(m.get("active_stops") or 0)]


def patterns(gov):
    """{kind: 'pair'|'solo'} from the kind.roster route (migrations/0029_ticket_authorization.sql:221-226,
    over the ticket_kinds table at :27-45) — READ from the db, never assumed by this file."""
    return {k["kind"]: k.get("pattern") for k in gov.rows("kind.roster", {})}


# ── settling a chain member ───────────────────────────────────────────────────────────────────────
def settle(iw, gov, tid, kind, pats, note, say):
    """Drive one chain member to DONE through `process_status`, then journal WHY.

    ORDER MATTERS: the status change is attempted FIRST and the journal note is appended only after it
    succeeded. The journal is append-only (tg_ticket_events_no_update, 0029:142-143), so a note
    written before a refused settle would be a permanent, uncorrectable lie about what happened.

    A pair-kind member is not attempted at all: tg_tickets_pair_completion (0029:133-140) would refuse
    it, and this lane assigns no agents (see THE AGENT). Returns True only if it really settled.
    """
    if pats.get(kind) != "solo":
        say("  settle : #%s NOT settled — kind %r is a %s kind; DONE needs two distinct agents in two "
            "distinct roles (tg_tickets_pair_completion) and this lane assigns none. Only its own "
            "adversarial pair can settle it."
            % (tid, kind, pats.get(kind) or "unknown"))
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
                             "ticket.create", "ticket.kind", "edge.record", "process_status",
                             "index_watch.py"]),
        "prompt": "You are %s, the index-watch chain lane of the dispatch schedule. Your one duty, "
                  "once per scheduler cycle: check the brake, select the newest OPEN index-watch "
                  "ticket, run index_watch.py against it (the run spawns its own successor), and "
                  "settle the member you ran plus any STRICTLY OLDER superseded one, so exactly one "
                  "index-watch is ever in flight. You reseed the chain if it ever empties, and you "
                  "graft (stop+spawn) only when a human asks. You route and settle; you never index, "
                  "author or judge work product, you assign no agents, and you never erase."
                  % CHAIN_AGENT})
    return CHAIN_AGENT


# ── seeding a chain root ──────────────────────────────────────────────────────────────────────────
def seed_root(iw, gov, say, supersedes=(), predecessor=0, component="congruency", reason=""):
    """File a fresh chain ROOT: ticket.create + ticket.kind(<solo kind>) + a 'supersedes' edge per
    superseded ticket. Returns the new ticket id.

    NO 'spawned' EDGE IS RECORDED, and that is the whole point. `ticket.stops` walks ONLY 'spawned'
    edges upward (0030:21-26), so a root linked by 'spawned' to a stopped chain would inherit that
    chain's halt and never run. A 'supersedes' edge records the same provenance — it is the original
    edge kind, and its direction is "a superseding ticket OWNS the predecessor it replaced"
    (0012_ticket_edges.sql:1-4), so parent=the new root, child=the ticket it replaces — without
    propagating the brake.

    NOTHING IS LOST BY STARTING A NEW ROOT. The index-watch delta is `{blobs in scope} MINUS {blob
    shas the store has already settled}` — computed from shas, never from the mark ("THE TRAP: THE
    MARK IS NOT A RANGE FILTER", index_watch.py's THE DELTA; resolve_mark's own docstring calls a
    markless run "GENESIS (the whole scope is new)"). A root with no mark therefore recomputes the
    whole scope and indexes exactly what the store is missing — idempotent, never duplicated. When a
    predecessor IS given, its `index-watch-predecessor:` line is carried so resolve_mark reads that
    ticket's recorded mark and the frontier stays monotone; that is an optimisation, not a
    correctness requirement.
    """
    body = ("Run the index-watch. This ticket is a CHAIN ROOT seeded by dispatch_schedule.py "
            "(ticket #198), not a spawned successor.\n\n"
            "    python3 checkouts/current/congruency/tools/index_watch.py --ticket <this ticket's id>"
            " --successor-kind %s\n\n"
            "%s\n"
            "It is kinded %r — a SOLO pattern — so the dispatch schedule can settle it mechanically "
            "once its run has spawned the next member. It carries NO 'spawned' edge to the chain it "
            "replaces, deliberately: ticket.stops walks 'spawned' edges upward, so a spawned link "
            "would inherit that chain's halt. Provenance is recorded with 'supersedes' edges instead.\n"
            "%s"
            % (DEFAULT_KIND, reason or "It starts the chain fresh.", DEFAULT_KIND,
               ("\n%s %d\n" % (iw.BODY_PRED, int(predecessor))) if predecessor else
               "\nNo mark is carried: this run is GENESIS. Nothing is lost — the index-watch delta is "
               "computed from blob shas against the store, never from a mark, so a genesis run "
               "indexes exactly what the store is missing.\n"))
    title = ROOT_TITLE % ((" (supersedes #%s)" % ", #".join(str(s) for s in supersedes))
                          if supersedes else " (genesis)")
    out = gov.rest("ticket.create", {"component": component, "title": title, "severity": "normal",
                                     "body": body, "patch": ""})
    try:
        sid = int(out.get("rowid") or 0)
    except (TypeError, ValueError):
        sid = 0
    if not sid:
        raise iw.GovError("ticket.create returned no rowid (%r) — the chain root was not filed" % out)
    gov.rest("ticket.kind", {"id": sid, "kind": DEFAULT_KIND})
    for old in supersedes:
        gov.rest("edge.record", {"parent_id": sid, "child_id": int(old), "kind": "supersedes"})
    gov.rest("ticket.progress", {
        "ticket_id": sid, "agent_id": CHAIN_AGENT,
        "note": "index-chain: SEEDED as a chain root by %s (kind %s, solo — settleable without a "
                "pair). %s%s The next cycle runs it and it spawns its own successor."
                % (CHAIN_AGENT, DEFAULT_KIND, reason or "",
                   (" Supersedes #%s." % ", #".join(str(s) for s in supersedes)) if supersedes else
                   " Genesis: no mark carried; the delta is sha-computed, so nothing is lost.")})
    say("  seed   : chain root #%s filed (kind %s)%s" % (
        sid, DEFAULT_KIND,
        (", 'supersedes' edge(s) -> #%s" % ", #".join(str(s) for s in supersedes)) if supersedes
        else " — GENESIS, no mark carried (the delta is sha-computed; nothing is lost)"))
    return sid


def chain_roots(iw, members):
    """The ROOT of each open chain subtree — the tickets a stop must be aimed at to halt every open
    member. Stopping a root halts its whole subtree with ONE stop ticket, because ticket.stops walks
    'spawned' edges up from each descendant and finds it (0030:21-26).

    A member is a root when NO 'spawned' edge can carry a stop down to it from another open member.
    Two cases, and both matter:

      * its `index-watch-predecessor:` is absent, or names a ticket that is not itself open — read
        from the body line index_watch writes and parses (predecessor_from_body), so this agrees with
        the tool rather than guessing from ids. On the live chain this is #266, whose predecessor #197
        is settled. (Verified: the live 'spawned' edges match these body lines exactly.)
      * it is a root THIS schedule seeded (ROOT_TITLE). seed_root deliberately records NO 'spawned'
        edge — that is precisely what keeps a fresh root out of the halt it was filed beside — so no
        stop can ever reach it from above, even though its body names a predecessor to carry the mark
        forward. Judging it by its predecessor line alone would wrongly call it a descendant and leave
        it unstopped, which would break `graft --force` on an already-grafted chain.
    """
    ids = {int(m["id"]) for m in members}
    roots = []
    for m in members:
        if (m.get("title") or "").startswith(ROOT_TITLE.split("%")[0]):
            roots.append(int(m["id"]))
            continue
        pred = iw.predecessor_from_body(m.get("body") or "")
        if pred is None or int(pred) not in ids:
            roots.append(int(m["id"]))
    return roots


# ── LANE 1: the index-watch chain ─────────────────────────────────────────────────────────────────
def watch_lane(iw, gov, run_watch, say, ticket=0, dry=False, reseed=True):
    """ONE turn of the chain, in the order the code executes it. Returns a report dict.

        1. READ       the open members and each one's active_stops.
        2. RESEED     if NO member is open, file a fresh root and continue with it. A chain that
                      emptied (a pair settled the only member without spawning; a crash between the
                      settle and the spawn) would otherwise need a human, which the ticket forbids.
        3. SELECT     the HEAD: the newest OPEN index-watch ticket (`--ticket N` overrides).
        4. BRAKE      ticket.stops on the head — an active stop aimed at it or ANY ANCESTOR halts the
                      turn before anything acts. Because every member is 'spawned' from the previous
                      one, every earlier member IS an ancestor: one stop aimed anywhere in the chain
                      halts the whole chain, and that is the ticket's brake.
        5. RECONCILE  settle every open member STRICTLY OLDER than the head — superseded, and losing
                      nothing (the head's delta is sha-computed and subsumes theirs). Skips halted
                      members (a stopped ticket authorizes nothing) and pair-kind members (only their
                      pairs may settle them).
        6. RUN        index_watch.py against the head. The run indexes the delta and SPAWNS the
                      successor itself.
        7. SETTLE     the head — only if the run completed, and therefore only AFTER its successor
                      exists. The chain is never left without an open member.
        8. VERIFY     re-read the queue and REPORT how many members are in flight AND how many are
                      open. The bound wants exactly one in flight; this prints what is actually true.

    STRICTLY OLDER, not "everything but the head", and the difference is load-bearing. `--ticket N`
    can name a member that is NOT the newest, and settling a NEWER member as "superseded by #N" would
    be false — and permanently so, because ticket_events is append-only (tg_tickets_events_no_update,
    0029:142-143). A member newer than an overridden head is left untouched and reported instead.

    `run_watch(tid) -> exit code` is injected: in production it is a subprocess of index_watch.py; in
    `selftest` it is the real Watch driven against a throwaway corpus. Both drive THIS function.

    `dry=True` stops after the brake and REPORTS what the later steps would do. It WRITES NOTHING: no
    agent is registered, nothing is seeded, run, settled or spawned, and no file is created (not even
    the lock). Only READ routes are called — ticket.queue, ticket.stops, kind.roster, and a ticket row
    read if `--ticket` named one outside the queue. This mirrors index_watch.py's own --dry-run, and
    is the safe way to look at a live chain.
    """
    rep = {"head": 0, "halted": False, "ran": None, "settled": [], "superseded": [], "seeded": 0,
           "skipped": [], "open_after": [], "in_flight_after": [], "ok": True, "dry": bool(dry)}

    # step 1: READ
    members = annotate(gov, open_members(iw, gov))

    # step 2: RESEED — the chain emptied; restart it rather than ask for a human
    if not members and not ticket:
        if dry:
            say("  select : no OPEN index-watch ticket — a real run would SEED a fresh chain root "
                "(kind %r) here and run it." % DEFAULT_KIND)
            return rep
        if not reseed:
            say("  select : no OPEN index-watch ticket and reseed is disabled "
                "(registry.json dispatch.index_watch.reseed=false) — the chain is not running. Seed "
                "it with `dispatch_schedule.py graft`.")
            rep["ok"] = False
            return rep
        register(iw, gov)
        say("  select : no OPEN index-watch ticket — the chain emptied (a pair settled its only "
            "member without spawning, or a cycle died between the settle and the spawn). RESEEDING "
            "so no human is needed; a genesis run loses nothing.")
        rep["seeded"] = seed_root(iw, gov, say,
                                  reason="The chain had no open member when the dispatch schedule "
                                         "looked, so this root restarts it.")
        members = annotate(gov, open_members(iw, gov))
        if not members:
            say("  select : the seeded root #%s is not in the queue — refusing to guess"
                % rep["seeded"])
            rep["ok"] = False
            return rep

    # step 3: SELECT the head
    if ticket:
        head = int(ticket)
        say("  select : #%s (--ticket override; members newer than it are left untouched)" % head)
    elif not members:
        say("  select : no OPEN index-watch ticket — nothing to do.")
        return rep
    else:
        head = int(members[-1]["id"])       # ticket.queue is ORDER BY id: the last is the newest
        say("  select : head #%s (newest of %d open index-watch ticket(s): %s)"
            % (head, len(members), ", ".join("#%s" % m["id"] for m in members)))
    rep["head"] = head

    # step 4: the BRAKE — before anything acts
    n_stops = stops_on(gov, head)
    if n_stops > 0:
        rep["halted"] = True
        say("  brake  : HALT — %d active stop ticket(s) aim at #%s or an ancestor; the chain "
            "authorizes nothing. Nothing was run, settled or spawned. Release the stop with a "
            "'starts' edge to resume." % (n_stops, head))
        return rep
    say("  brake  : no active stops on #%s or its ancestors" % head)

    pats = patterns(gov)
    by_id = {int(m["id"]): m for m in members}
    older = [m for m in members if int(m["id"]) < head]
    newer = [m for m in members if int(m["id"]) > head]

    def head_kind():
        """The head's kind. `--ticket N` can name a ticket that is not in the queue listing, so fall
        back to reading its row rather than reporting a confident None."""
        if head in by_id:
            return by_id[head].get("kind")
        return (gov.ticket_row(head) or {}).get("kind")

    if dry:
        settleable = [int(m["id"]) for m in older
                      if pats.get(m.get("kind")) == "solo" and not m.get("active_stops")]
        # Name the reason PER member, exactly as the real reconcile below does — "halted, or a pair
        # kind" would leave a reader guessing which of the two applies to which ticket.
        stuck = [(int(m["id"]),
                  "halted by %d active stop(s)" % int(m["active_stops"]) if m.get("active_stops")
                  else "kind %r is a pair kind" % m.get("kind"))
                 for m in older
                 if pats.get(m.get("kind")) != "solo" or m.get("active_stops")]
        hk = head_kind()
        say("  DRY-RUN: nothing below is done; this is what a real cycle WOULD do.")
        say("  would  : run index_watch.py --ticket %s --successor-kind %s (it would index the delta "
            "and spawn the successor)" % (head, DEFAULT_KIND))
        if pats.get(hk) == "solo":
            say("  would  : settle #%s once that run completed" % head)
        else:
            say("  would  : NOT settle #%s — kind %r is a %s kind; only its pair can settle it"
                % (head, hk, pats.get(hk) or "unknown"))
        say("  would  : settle %d strictly-older superseded member(s): %s"
            % (len(settleable), ", ".join("#%s" % i for i in settleable) or "none"))
        if stuck:
            say("  would  : leave %d older member(s) open — %s. A halted ticket authorizes nothing; a "
                "pair kind can only be settled by its own pair (tg_tickets_pair_completion). "
                "`graft` is the supported remedy."
                % (len(stuck), "; ".join("#%s (%s)" % (i, why) for i, why in stuck)))
        if newer:
            say("  would  : leave %d NEWER member(s) untouched (%s) — they are not superseded by #%s"
                % (len(newer), ", ".join("#%s" % m["id"] for m in newer), head))
        rep["open_after"] = [int(m["id"]) for m in members]
        rep["in_flight_after"] = [int(m["id"]) for m in in_flight(members)]
        return rep

    register(iw, gov)

    # step 5: RECONCILE — members strictly OLDER than the head are superseded by it. A halted member
    # authorizes nothing and a pair-kind member would be refused by tg_tickets_pair_completion;
    # neither is attempted, and both are summarised in one line rather than one refusal per cycle.
    stuck = []
    for m in older:
        mid = int(m["id"])
        if m.get("active_stops"):
            stuck.append((mid, "halted by %d active stop(s)" % int(m["active_stops"])))
            continue
        if pats.get(m.get("kind")) != "solo":
            stuck.append((mid, "kind %r is a pair kind" % m.get("kind")))
            continue
        if settle(iw, gov, mid, m.get("kind"), pats,
                  "index-chain: SUPERSEDED by newer index-watch #%s, which this schedule ran. Nothing "
                  "is lost: the index-watch delta is computed from blob shas against the store, never "
                  "from a mark, so any blob this ticket would have indexed is still unsettled and #%s "
                  "picks it up. Settled by %s to hold the bound of one index-watch in flight."
                  % (head, head, CHAIN_AGENT), say):
            rep["superseded"].append(mid)
    if stuck:
        rep["skipped"] = [i for i, _ in stuck]
        say("  reconc : %d older member(s) left open — %s. This lane assigns no agents, so it cannot "
            "settle a pair kind (tg_tickets_pair_completion), and it never settles a halted ticket "
            "(a stop means it authorizes nothing). No stop is aimed at them here: they are ANCESTORS "
            "of the head, and a stop would propagate down the 'spawned' chain and halt the live chain "
            "itself. `dispatch_schedule.py graft` is the supported remedy."
            % (len(stuck), "; ".join("#%s (%s)" % (i, why) for i, why in stuck)))
    if newer:
        say("  reconc : %d member(s) NEWER than #%s left untouched (%s) — an overridden head does not "
            "supersede them, and journaling that it did would be a permanent falsehood on an "
            "append-only journal." % (len(newer), head, ", ".join("#%s" % m["id"] for m in newer)))

    # step 6: RUN the head — the run spawns the successor itself
    rc = run_watch(head)
    rep["ran"] = rc
    say("  run    : index_watch.py --ticket %s -> exit %s (%s)"
        % (head, rc, WATCH_EXITS.get(rc, "unknown")))
    if rc != 0:
        rep["ok"] = False
        say("  settle : #%s NOT settled — its run did not complete, so it may have spawned no "
            "successor; settling it could leave the chain with no open member. It stays open and the "
            "next cycle retries it." % head)
    else:
        # step 7: SETTLE the head — its successor exists (the run filed it before returning 0)
        if settle(iw, gov, head, head_kind(), pats,
                  "index-chain: RAN and settled by %s on the dispatch schedule. Its successor was "
                  "spawned by the run itself (index_watch.py step 8) before this settle, so the chain "
                  "is never without an open member." % CHAIN_AGENT, say):
            rep["settled"].append(head)

    # step 8: VERIFY — report the invariant rather than assert it
    still = annotate(gov, open_members(iw, gov))
    flying = in_flight(still)
    rep["open_after"] = [int(m["id"]) for m in still]
    rep["in_flight_after"] = [int(m["id"]) for m in flying]
    halted = [int(m["id"]) for m in still if m.get("active_stops")]
    if len(flying) == 1:
        say("  chain  : 1 index-watch IN FLIGHT (#%s) — the bound holds; it is primed for the next "
            "delta.%s" % (rep["in_flight_after"][0],
                          (" %d other member(s) are open but HALTED by a stop (%s): they authorize "
                           "nothing, dispatch-01 skips them, and only their own pairs can settle them."
                           % (len(halted), ", ".join("#%s" % i for i in halted))) if halted else ""))
    else:
        rep["ok"] = False
        unsettleable = [int(m["id"]) for m in flying if pats.get(m.get("kind")) != "solo"]
        say("  chain  : %d index-watch ticket(s) IN FLIGHT (%s) — the bound wants exactly 1. %d open "
            "in total%s."
            % (len(flying), ", ".join("#%s" % i for i in rep["in_flight_after"]) or "none",
               len(still), (", %d halted" % len(halted)) if halted else ""))
        if unsettleable:
            say("  chain  : %d of them are a PAIR kind (%s) which NO mechanical runner may settle — "
                "tg_tickets_pair_completion (0029:133-140) refuses DONE without two distinct agents "
                "in two distinct roles, and `kind` is set-once (0029:111-117) so they cannot be "
                "re-kinded. REMEDY, one command, one time: `python3 %s graft` — it halts them with a "
                "stop ticket (the db's own prescribed stop+spawn) and seeds a fresh %r-kinded root, "
                "after which this bound holds every cycle. Run `graft --dry-run` first to see it."
                % (len(unsettleable), ", ".join("#%s" % i for i in unsettleable), SELF, DEFAULT_KIND))
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
        rep = watch_lane(iw, gov, subprocess_watch(cfg, say), say, ticket=a.ticket, dry=a.dry_run,
                         reseed=cfg["reseed"])
    except iw.GovError as e:
        say("== watch == a governed route failed: %s" % e)
        return 3
    if rep["halted"]:
        return 4
    return 0 if rep["ok"] else 3


# ── the GRAFT: stop a chain this lane cannot settle, seed one it can ──────────────────────────────
def graft_lane(iw, gov, say, dry=False, force=False, component="congruency"):
    """The db's own prescribed course-change — STOP the old, SPAWN the replacement — applied once to a
    chain whose members this lane may not settle. Returns a report dict.

    WHY THIS EXISTS. The live chain's open members are kind `build`, a PAIR pattern, so
    tg_tickets_pair_completion (0029:133-140) refuses DONE on them without two distinct agents in two
    distinct roles; `kind` is set-once (0029:111-117) so they cannot be re-kinded; and no lawful
    non-DONE exit from the queue exists for a kinded ticket. They can therefore never be settled by
    this schedule, and while they are IN FLIGHT the bound is broken every cycle. This does not fake a
    settle, does not erase anything, and does not touch their status: it HALTS them exactly the way
    the ticket's own brake halts the chain, and starts a chain that can hold the bound.

    THE STEPS, in the order the code executes them:
      1. READ the open members and their stops; refuse if the bound already holds (unless --force).
      2. STOP each ROOT of the open chain forest — ONE stop ticket per root halts its whole subtree,
         because ticket.stops walks 'spawned' edges up from every descendant and finds it. The stop
         ticket is the edge's PARENT and the target its CHILD, the same direction pair_loop's own
         dispatcher records (pair_loop.py:581-584).
      3. SEED one fresh root, kind `audit` (solo), carrying the newest member's
         `index-watch-predecessor:` line so its mark stays monotone, linked to each stopped root by a
         'supersedes' edge and by NO 'spawned' edge — so the stop it just filed does not halt it too.

    AFTER THIS the halted members are still OPEN and still counted in every "open" report, honestly.
    They authorize nothing, dispatch-01 skips them (pair_loop.py:521-532), and only their own
    adversarial pairs can ever settle them — which is the only lawful end for a pair ticket.
    """
    rep = {"stopped": [], "roots": [], "seeded": 0, "ok": True, "dry": bool(dry)}
    members = annotate(gov, open_members(iw, gov))
    pats = patterns(gov)
    flying = in_flight(members)

    if not members:
        say("  graft  : no open index-watch ticket at all — nothing to stop.")
        if dry:
            say("  would  : seed a fresh chain root (kind %r), GENESIS." % DEFAULT_KIND)
            return rep
        register(iw, gov)
        rep["seeded"] = seed_root(iw, gov, say, reason="The chain had no open member at all.")
        return rep

    healthy = len(flying) == 1 and pats.get(flying[0].get("kind")) == "solo"
    if healthy and not force:
        say("  graft  : REFUSED — the bound already holds: exactly 1 index-watch in flight (#%s, kind "
            "%r, a solo kind this schedule settles itself). Grafting would halt a healthy chain for "
            "nothing. Pass --force if you really mean to replace it."
            % (flying[0]["id"], flying[0].get("kind")))
        return rep

    roots = chain_roots(iw, members)
    rep["roots"] = roots
    newest = int(members[-1]["id"])
    say("  graft  : %d open member(s): %s" % (len(members), ", ".join("#%s" % m["id"] for m in members)))
    say("  graft  : %d subtree root(s) to halt: %s — one stop each halts every descendant, because "
        "ticket.stops walks 'spawned' edges up from them (0030:21-26)."
        % (len(roots), ", ".join("#%s" % r for r in roots)))

    if dry:
        say("  DRY-RUN: nothing below is done; this is what a real graft WOULD do.")
        for r in roots:
            say("  would  : file a kind=stop ticket and aim a 'stops' edge at #%s (halting it and "
                "every member spawned from it)" % r)
        say("  would  : seed a fresh chain root, kind %r (solo), carrying "
            "'index-watch-predecessor: %d' so its mark stays monotone, with 'supersedes' edge(s) to "
            "#%s and NO 'spawned' edge (which would inherit the halt)"
            % (DEFAULT_KIND, newest, ", #".join(str(r) for r in roots)))
        say("  would  : leave every halted member OPEN and untouched — no status change, nothing "
            "erased; only their own pairs can lawfully settle them.")
        return rep

    register(iw, gov)
    for r in roots:
        body = ("The index-watch chain rooted at #%s must not proceed.\n\n"
                "Its members are kind `build` — a PAIR pattern — so tg_tickets_pair_completion "
                "(migrations/0029_ticket_authorization.sql:133-140) refuses DONE on them unless two "
                "DISTINCT agents hold two DISTINCT roles, and `kind` is set-once "
                "(tg_tickets_immutable_identity, 0029:111-117) so they cannot be re-kinded to a solo "
                "kind. No mechanical runner may therefore settle them, and while they are in flight "
                "the index-watch bound of ticket #198 ('one index-watch in flight at a time') is "
                "broken every cycle.\n\n"
                "This stop HALTS this chain — it does not close it, and nothing is erased. Every "
                "member stays OPEN on the record and may still be settled lawfully by its own "
                "adversarial pair; until then dispatch-01 skips it (a stopped ticket authorizes "
                "nothing).\n\n"
                "A replacement chain, kinded `%s` (a solo pattern the dispatch schedule can settle), "
                "is seeded alongside this stop and linked by a 'supersedes' edge. Nothing is lost: "
                "the index-watch delta is computed from blob shas against the store, never from a "
                "mark, so every blob this chain would have indexed is still unsettled and the "
                "replacement picks it up.\n\n"
                "Filed by %s (dispatch_schedule.py graft, ticket #198) — the db's own prescribed "
                "stop+spawn (graft), never an edit or an erase." % (r, DEFAULT_KIND, CHAIN_AGENT))
        out = gov.rest("ticket.create", {
            "component": component, "severity": "normal", "patch": "",
            "title": "STOP: the mis-kinded index-watch chain rooted at #%s is superseded (graft, #198)" % r,
            "body": body})
        sid = int(out.get("rowid") or 0)
        if not sid:
            raise iw.GovError("ticket.create returned no rowid (%r) — the stop was not filed" % out)
        gov.rest("ticket.kind", {"id": sid, "kind": "stop"})
        gov.rest("edge.record", {"parent_id": sid, "child_id": int(r), "kind": "stops"})
        rep["stopped"].append((int(r), sid))
        say("  stop   : #%s filed (kind stop), 'stops' edge #%s -> #%s — #%s and every member spawned "
            "from it are now HALTED (open, authorizing nothing)" % (sid, sid, r, r))

    rep["seeded"] = seed_root(
        iw, gov, say, supersedes=roots, predecessor=newest, component=component,
        reason="It replaces the halted index-watch chain rooted at #%s, whose `build` (pair) kind no "
               "mechanical runner may settle. It carries #%d's mark forward so the frontier stays "
               "monotone." % (", #".join(str(r) for r in roots), newest))

    after = annotate(gov, open_members(iw, gov))
    flying_after = in_flight(after)
    say("  graft  : done — %d open index-watch ticket(s), %d IN FLIGHT (%s). %d member(s) are halted "
        "and stay open on the record until their own pairs settle them."
        % (len(after), len(flying_after), ", ".join("#%s" % m["id"] for m in flying_after) or "none",
           len(after) - len(flying_after)))
    if len(flying_after) != 1:
        rep["ok"] = False
        say("  graft  : the bound is STILL not met (%d in flight, want 1) — reporting it rather than "
            "claiming otherwise." % len(flying_after))
    return rep


def do_graft(a, cfg, say):
    """The graft against the live governed surface. Returns an exit code."""
    iw = load_watch()
    key = iw._secret("CONGRUENCY_API_KEY")
    if not key and not a.dry_run:
        raise Fault("no CONGRUENCY_API_KEY (env or .secrets/ats.env) — filing the stop and seeding "
                    "the root go through token routes, and the writes ARE the work")
    gov = iw.Gov(key=key)
    say("== graft == stop the index-watch chain this lane cannot settle, seed one it can%s"
        % (" — DRY-RUN, nothing is written" if a.dry_run else ""))
    try:
        rep = graft_lane(iw, gov, say, dry=a.dry_run, force=a.force)
    except iw.GovError as e:
        say("== graft == a governed route failed: %s" % e)
        return 3
    say("== graft == %s" % ("reported (nothing written)" if a.dry_run else "complete"))
    return 0 if rep["ok"] else 3


# ── LANE 2: dispatch-01 routes the queue (pre-existing behaviour, unchanged) ──────────────────────
def do_dispatch(cfg, say):
    """`pair_loop.py --dispatch <cap>`: dispatch-01 decides run/skip/stop and executes. The BOUNDS are
    the safety case: the per-run cap, the stop-ticket brake pair_loop checks before acting, and the
    SQL governance that refuses erasure no matter what a scheduled agent does.

    The watch lane runs BEFORE this on purpose: it settles the member it ran, so that member has left
    the queue by the time dispatch-01 reads it here. The SUCCESSOR the run spawned is necessarily
    still open — the chain must never be empty — and nothing in DISPATCH_RULES (pair_loop.py:521-532)
    excludes it, so dispatch-01 MAY route it. This file cannot prevent that (pair_loop.py is not its
    deliverable, and dispatch-01 is an LLM). What it does instead is CONVERGE: see THE BOUND
    mechanism 4 — a fork is reconciled and a dead chain is reseeded on the next cycle, with no manual
    step. `graft` removes the risk for halted members entirely, since dispatch-01 skips them.
    """
    say("== dispatch == dispatch-01 routes up to %d queue ticket(s)" % cfg["cap"])
    cmd = [sys.executable, PAIR_LOOP, "--dispatch", str(cfg["cap"]), "--timeout", str(cfg["timeout"])]
    say("  run    : %s" % " ".join(cmd))
    rc = subprocess.run(cmd, cwd=ROOT).returncode
    say("== dispatch == exit %s" % rc)
    return rc


# ── ONE CYCLE = lane 1 then lane 2 ────────────────────────────────────────────────────────────────
def do_cycle(a, cfg, say):
    """What launchd runs. The watch lane FIRST (it settles what it ran, so dispatch-01 never sees it),
    then the dispatch lane. The flock spans BOTH so one cycle is one cycle.

    --dry-run takes NO lock and creates no lock file: it changes nothing, so it needs no exclusivity,
    and an inspection you cannot run while a cycle is in flight would be a poor inspection.
    """
    lock = None if a.dry_run else acquire()
    if lock is None and not a.dry_run:
        say("== cycle == another cycle holds %s — this one did nothing (the bound: one index-watch in "
            "flight at a time)" % LOCK)
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
            # --dry-run writes nothing, and dispatch-01 routing the queue is emphatically a write: it
            # spawns pairs that branch, commit and settle tickets. Reported, never run.
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
    """One line on the chain's live state for `status`. The surface may legitimately be down; that is
    an ANSWER about the chain, not a crash of the status command."""
    try:
        iw = load_watch()
        gov = iw.Gov(key=iw._secret("CONGRUENCY_API_KEY"))
        members = annotate(gov, open_members(iw, gov))
    except (Fault, Exception) as e:  # noqa: BLE001
        return "chain: unreadable — %s" % str(e).split("\n")[0][:120]
    if not members:
        return "chain: no open index-watch ticket (the next cycle reseeds one)"
    flying = in_flight(members)
    halted = [m for m in members if m.get("active_stops")]
    return ("chain: %d in flight (%s), %d open%s%s"
            % (len(flying), ", ".join("#%s" % m["id"] for m in flying) or "none", len(members),
               (", %d halted" % len(halted)) if halted else "",
               "" if len(flying) == 1 else " — the bound wants exactly 1 in flight; see `graft`"))


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
# turns on. index_watch's own FakeGov answers kind.roster with 'pair' for everything, which would make
# every settle look refused; this is the real table.
PATTERNS = {"build": "pair", "bug": "pair", "documentation": "pair", "bet": "pair",
            "design": "solo", "spec": "solo", "test": "solo", "rfc-investigation": "solo",
            "audit": "solo", "stop": "solo", "start": "solo"}


def chain_gov(iw):
    """index_watch's own FakeGov, extended with the routes the SCHEDULE calls that a watch run never
    does: ticket.queue (where the head is selected from), process_status (the settle), a kind.roster
    carrying the REAL patterns, and a ticket.stops that answers PER TICKET off real 'stops'/'starts'
    edges instead of one global number.

    Both enforcements mirror the real db, so the selftest proves the code against the real rules:
      * process_status enforces tg_tickets_pair_completion (0029:133-140) — a pair-kind member with
        fewer than two distinct agents in two distinct roles is REFUSED DONE.
      * ticket.stops re-implements the route's own recursive SQL (0030:21-26): it walks 'spawned'
        edges UP from the queried ticket collecting ancestors, counts 'stops' edges whose CHILD is in
        that set, and ignores any whose stop ticket is released by a 'starts' edge. This is what makes
        the graft checkable — that ONE stop at a root really halts every descendant, and really does
        NOT halt a root linked only by 'supersedes'.
    """

    class ChainGov(iw.FakeGov):
        def __init__(self, tickets=None, active_stops=0):
            iw.FakeGov.__init__(self, tickets=tickets, kinds=tuple(sorted(PATTERNS)),
                                active_stops=active_stops)
            self.agent_roles = {}      # ticket_id -> {(agent_id, role)}, what ticket.assign would fill

        def ancestors(self, tid):
            """{tid} + every ancestor reachable by walking 'spawned' edges UP — the route's own
            `WITH RECURSIVE anc(id)` clause."""
            seen, stack = {int(tid)}, [int(tid)]
            while stack:
                cur = stack.pop()
                for p, c, k in self.edges:
                    if k == "spawned" and int(c) == cur and int(p) not in seen:
                        seen.add(int(p))
                        stack.append(int(p))
            return seen

        def active_stops_for(self, tid):
            anc = self.ancestors(tid)
            released = {int(c) for p, c, k in self.edges if k == "starts"}   # 'starts' child = the stop
            n = sum(1 for p, c, k in self.edges
                    if k == "stops" and int(c) in anc and int(p) not in released)
            return n + self.active_stops        # the global knob still drives the brake checks

        def rest(self, route, obj=None, method=None):
            obj = obj or {}
            if route == "ticket.queue":
                self.calls.append((route, dict(obj)))
                return {"rows": [dict(t) for t in sorted(self.tickets.values(), key=lambda r: r["id"])
                                 if str(t.get("status") or "").upper() in ("OPEN", "REQUESTED")]}
            if route == "ticket.stops":
                self.calls.append((route, dict(obj)))
                return {"rows": [{"active_stops": self.active_stops_for(int(obj["ticket_id"]))}]}
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

        # The seed: a chain member exactly as index_watch spawns them — its minted title, kind `audit`
        # (the solo kind the schedule keeps the chain in), REQUESTED as ticket.create leaves it. No
        # mark anywhere, so its run is GENESIS: the whole corpus is its delta.
        seed = {300: {"id": 300, "title": iw.SUCCESSOR_TITLE % 197, "body": "",
                      "kind": "audit", "status": "REQUESTED", "component": "congruency"}}
        gov = ChainGov(tickets=seed)

        def watcher(g, st):
            def run(tid):
                w = iw.Watch(cs, g, omni_db, omni_git, st, chunker, iw._fake_embed, "nomic-embed",
                             cs.DOC_PREFIX, cs.MAX_CHARS, component="congruency")
                try:
                    w.run(tid, spawn=True, successor_kind="audit", verbose=False)
                    return 0
                except iw.Halted:
                    return 5
            return run

        run_watch = watcher(gov, store)

        def cycle(ticket=0, g=None):
            return watch_lane(iw, g or gov, run_watch, hush if quiet_watch else print, ticket=ticket)

        def opens(g=None):
            return [int(m["id"]) for m in open_members(iw, g or gov)]

        def flying(g=None):
            gg = g or gov
            return [int(m["id"]) for m in in_flight(annotate(gg, open_members(iw, gg)))]

        def searchable(sha):
            con = cs.ro_connect(store)
            try:
                return con.execute("SELECT repo, path, vector FROM code_sim_index WHERE blob_sha = ?",
                                   (sha,)).fetchall()
            finally:
                con.close()

        def settled_shas(st=None):
            con = cs.ro_connect(st or store)
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
        ck("...and a root THIS schedule seeded, by its own title",
           is_member(iw, {"title": ROOT_TITLE % " (supersedes #9)"})
           and is_member(iw, {"title": ROOT_TITLE % " (genesis)"}))
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
        ck("...and it is exactly one IN FLIGHT (the bound)", len(flying()) == 1, str(flying()))
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

        # ── THE --ticket OVERRIDE MUST NOT SETTLE NEWER MEMBERS (round-1 finding) ──
        # `older` must be STRICTLY older than the head. "Everything except the head" would settle a
        # LIVE, NEWER member with a permanently false note on an append-only journal.
        print("-- `watch --ticket N` settles only STRICTLY OLDER members, never newer ones")
        govo = ChainGov(tickets={
            650: {"id": 650, "title": iw.SUCCESSOR_TITLE % 1, "body": "", "kind": "audit",
                  "status": "REQUESTED", "component": "congruency"},
            700: {"id": 700, "title": iw.SUCCESSOR_TITLE % 650, "body": "", "kind": "audit",
                  "status": "REQUESTED", "component": "congruency"}})
        ro = watch_lane(iw, govo, lambda t: 0, hush, ticket=650)
        ck("the override ran the ticket it was given", ro["head"] == 650, str(ro["head"]))
        ck("...and the NEWER member #700 was NOT settled", 700 not in ro["superseded"],
           str(ro["superseded"]))
        ck("...#700 is still OPEN and untouched", govo.tickets[700]["status"] == "REQUESTED",
           str(govo.tickets[700]["status"]))
        ck("...no process_status was ever aimed at #700",
           not any(c[1].get("id") == 700 for c in govo.calls if c[0] == "process_status"),
           str(govo.routes("process_status")))
        ck("...and NO 'SUPERSEDED by newer #650' note was journaled onto it (it would be false, and "
           "the journal is append-only)",
           not any(c[1].get("ticket_id") == 700 and "SUPERSEDED" in (c[1].get("note") or "")
                   for c in govo.calls if c[0] == "ticket.progress"),
           str(govo.routes("ticket.progress")))

        # ── SELF-HEALING 1: the chain emptied — reseed, no human ──
        print("-- self-healing: a pair settled the only member without spawning (the chain died)")
        govd = ChainGov(tickets={800: {"id": 800, "title": iw.SUCCESSOR_TITLE % 1, "body": "",
                                       "kind": "audit", "status": "DONE", "component": "congruency"}})
        stored = os.path.join(base, "code_sim_dead.db")
        ck("the chain has NO open member (it is dead)", not opens(govd), str(opens(govd)))
        rd2 = watch_lane(iw, govd, watcher(govd, stored), hush)
        ck("the lane RESEEDED a fresh root with no human step", rd2["seeded"] > 0, str(rd2["seeded"]))
        ck("...kinded with the SOLO kind, so it settles itself",
           govd.tickets[rd2["seeded"]]["kind"] == "audit", str(govd.tickets[rd2["seeded"]]["kind"]))
        ck("...it RAN the reseeded root (genesis) and indexed the corpus",
           rd2["ran"] == 0 and settled_shas(stored) == set(shas.values()) | {new_sha},
           "%s / %d" % (rd2["ran"], len(settled_shas(stored))))
        ck("...the reseeded root was settled once its successor existed",
           rd2["settled"] == [rd2["seeded"]], str(rd2["settled"]))
        ck("ACCEPTANCE: the chain is alive again — exactly ONE in flight", len(flying(govd)) == 1,
           str(flying(govd)))
        ck("...and the root carries NO 'spawned' edge to anything (nothing spawned it)",
           not any(k == "spawned" and int(c) == rd2["seeded"] for _, c, k in govd.edges),
           str(govd.edges))

        # ── SELF-HEALING 2: reseed is refusable ──
        print("-- self-healing: reseed can be turned off (registry.json reseed=false)")
        govn = ChainGov(tickets={810: {"id": 810, "title": iw.SUCCESSOR_TITLE % 1, "body": "",
                                       "kind": "audit", "status": "DONE"}})
        rn = watch_lane(iw, govn, lambda t: 0, hush, reseed=False)
        ck("with reseed disabled, the dead chain is REPORTED, not resurrected",
           rn["seeded"] == 0 and not rn["ok"] and not govn.routes("ticket.create"), str(rn))

        # ── THE GRAFT: a pair-kind chain this lane may not settle ──
        print("-- the graft: stop a chain this lane cannot settle, seed one it can")
        # The live shape, in miniature: a FORKED, `build`-kinded chain (#267 really did spawn both
        # #268 and #277), rooted at a member whose predecessor is not open.
        legacy = {}
        for tid, pred in ((266, 197), (267, 266), (268, 267), (277, 267), (269, 268)):
            legacy[tid] = {"id": tid, "title": iw.SUCCESSOR_TITLE % pred,
                           "body": "%s %d" % (iw.BODY_PRED, pred), "kind": "build",
                           "status": "REQUESTED", "component": "congruency"}
        govg = ChainGov(tickets=legacy)
        for tid, pred in ((267, 266), (268, 267), (277, 267), (269, 268)):
            govg.rest("edge.record", {"parent_id": pred, "child_id": tid, "kind": "spawned"})
        storeg = os.path.join(base, "code_sim_graft.db")

        ck("the legacy chain has 5 open members, all IN FLIGHT (the bound is broken)",
           len(opens(govg)) == 5 and len(flying(govg)) == 5, str(flying(govg)))
        ck("the root of the open forest is #266 (its predecessor #197 is not open)",
           chain_roots(iw, annotate(govg, open_members(iw, govg))) == [266],
           str(chain_roots(iw, annotate(govg, open_members(iw, govg)))))
        # prove the premise the graft exists for: the db really refuses to settle these
        try:
            govg.rest("process_status", {"id": 269, "status": "DONE"})
            refused = False
        except iw.GovError:
            refused = True
        ck("...and NO mechanical runner may settle them: DONE on a pair kind is REFUSED without two "
           "distinct agents in two distinct roles (tg_tickets_pair_completion)", refused)

        # a dry-run first: it must change nothing
        g_tickets, g_calls = len(govg.tickets), len(govg.calls)
        rgd = graft_lane(iw, govg, hush, dry=True)
        ck("graft --dry-run names the roots it WOULD stop", rgd["roots"] == [266], str(rgd["roots"]))
        # NOTE: the window `calls[g_calls:]` — not the whole history. The setup above legitimately
        # recorded the chain's own 'spawned' edges through edge.record, so asserting over every call
        # ever made would fail on the fixture rather than on the dry-run.
        ck("...and files NOTHING in the dry-run window (no ticket, no stop, no edge)",
           len(govg.tickets) == g_tickets
           and not [c for c in govg.calls[g_calls:] if c[0] in ("ticket.create", "edge.record",
                                                                "ticket.kind")],
           str([c[0] for c in govg.calls[g_calls:]]))
        ck("...calling only read routes",
           {c[0] for c in govg.calls[g_calls:]} <= {"ticket.queue", "ticket.stops", "kind.roster"},
           str({c[0] for c in govg.calls[g_calls:]}))

        rg = graft_lane(iw, govg, hush)
        stop_ids = [s for _, s in rg["stopped"]]
        ck("the graft filed ONE stop ticket aimed at the root", len(rg["stopped"]) == 1
           and rg["stopped"][0][0] == 266, str(rg["stopped"]))
        ck("...kinded `stop`", govg.tickets[stop_ids[0]]["kind"] == "stop",
           str(govg.tickets[stop_ids[0]]["kind"]))
        ck("...aimed by a 'stops' edge whose PARENT is the stop and CHILD is the target (the "
           "direction pair_loop records)", (stop_ids[0], 266, "stops") in govg.edges, str(govg.edges))
        ck("ONE stop at the root HALTS every member of the subtree, fork included",
           all(govg.active_stops_for(t) > 0 for t in (266, 267, 268, 269, 277)),
           str({t: govg.active_stops_for(t) for t in (266, 267, 268, 269, 277)}))
        ck("...and every one of them is still OPEN — a stop is a brake, not an eraser; nothing was "
           "erased and no status was touched",
           sorted(opens(govg))[:5] == [266, 267, 268, 269, 277], str(opens(govg)))
        ck("...their status is untouched (still REQUESTED, never faked to DONE)",
           all(govg.tickets[t]["status"] == "REQUESTED" for t in (266, 267, 268, 269, 277)))
        ck("...and the graft never assigned an agent to fake the pair", not govg.routes("ticket.assign"))
        ck("the graft seeded a fresh root", rg["seeded"] > 0, str(rg["seeded"]))
        ck("...kinded `audit` — a SOLO kind this schedule can settle",
           govg.tickets[rg["seeded"]]["kind"] == "audit", str(govg.tickets[rg["seeded"]]["kind"]))
        ck("...linked to the stopped root by a 'supersedes' edge (provenance kept)",
           (rg["seeded"], 266, "supersedes") in govg.edges, str(govg.edges))
        ck("...and by NO 'spawned' edge — which is what keeps the new root OUT of the halt",
           not any(k == "spawned" and int(c) == rg["seeded"] for _, c, k in govg.edges))
        ck("...so the fresh root is NOT halted and CAN run", govg.active_stops_for(rg["seeded"]) == 0,
           str(govg.active_stops_for(rg["seeded"])))
        ck("ACCEPTANCE: exactly ONE index-watch is now IN FLIGHT — the bound holds",
           flying(govg) == [rg["seeded"]], str(flying(govg)))
        ck("...while the open count is honestly still 6, not hidden", len(opens(govg)) == 6,
           str(opens(govg)))
        ck("the graft reports success", rg["ok"], str(rg["ok"]))

        # the grafted chain now runs hands-off, and the halted legacy members stay out of its way
        print("-- after the graft: the chain runs hands-off and the bound holds every cycle")
        rg1 = watch_lane(iw, govg, watcher(govg, storeg), hush)
        ck("the lane selected the fresh root as head (it is the newest open member)",
           rg1["head"] == rg["seeded"], str(rg1["head"]))
        ck("...ran it, and every corpus blob is fingerprinted with no manual step",
           rg1["ran"] == 0 and settled_shas(storeg) == set(shas.values()) | {new_sha},
           "%s / %d" % (rg1["ran"], len(settled_shas(storeg))))
        ck("...settled it once its successor existed", rg1["settled"] == [rg["seeded"]],
           str(rg1["settled"]))
        ck("...and NEVER settled a halted legacy member (a stopped ticket authorizes nothing)",
           not any(t in rg1["superseded"] for t in (266, 267, 268, 269, 277)), str(rg1["superseded"]))
        ck("...it reported them as skipped instead", sorted(rg1["skipped"]) == [266, 267, 268, 269, 277],
           str(rg1["skipped"]))
        ck("ACCEPTANCE: exactly ONE in flight after the cycle", len(flying(govg)) == 1,
           str(flying(govg)))
        ck("...and the lane reports the bound as MET (exit 0), because it is", rg1["ok"], str(rg1["ok"]))
        rg2 = watch_lane(iw, govg, watcher(govg, storeg), hush)
        ck("a second post-graft cycle still holds the bound, unattended",
           rg2["ran"] == 0 and len(flying(govg)) == 1 and rg2["ok"], str(flying(govg)))
        # The brake must still bite on the GRAFTED chain — a chain that outran the ticket's own brake
        # would be worse than no chain. Aim a real stop ticket at the live head and prove it halts.
        live_head = flying(govg)[0]
        brake = int(govg.rest("ticket.create", {"component": "congruency", "severity": "normal",
                                                "patch": "", "title": "STOP: pause the index-chain",
                                                "body": ""})["rowid"])
        govg.rest("ticket.kind", {"id": brake, "kind": "stop"})
        govg.rest("edge.record", {"parent_id": brake, "child_id": live_head, "kind": "stops"})
        shas_before = set(settled_shas(storeg))
        rb = watch_lane(iw, govg, watcher(govg, storeg), hush)
        ck("the brake STILL works on the grafted chain: a stop aimed at its head HALTS it",
           rb["halted"] and rb["ran"] is None, str(rb))
        ck("...nothing was run, settled or indexed under the halt",
           not rb["settled"] and not rb["superseded"] and settled_shas(storeg) == shas_before)
        # ...and a 'starts' edge aimed at the stop ticket releases it, exactly as the route defines
        govg.rest("edge.record", {"parent_id": brake + 1000, "child_id": brake, "kind": "starts"})
        rr = watch_lane(iw, govg, watcher(govg, storeg), hush)
        ck("...and a 'starts' edge releasing that stop resumes the chain unattended",
           not rr["halted"] and rr["ran"] == 0, str(rr))

        # the graft refuses to wreck a healthy chain
        print("-- the graft refuses a healthy chain (and --force overrides)")
        rgh = graft_lane(iw, govg, hush)
        ck("graft on a healthy chain is REFUSED — it would halt a working chain for nothing",
           not rgh["stopped"] and not rgh["seeded"], str(rgh))
        ck("...and it reports that as success, not failure (nothing was wrong)", rgh["ok"])

        # --force on an ALREADY-grafted chain: the previously seeded root carries an
        # `index-watch-predecessor:` line but NO 'spawned' edge, so it is a root in the only sense
        # that governs a stop. Judging roots by the predecessor line alone would leave it unstopped
        # and in flight, and the bound would silently stay broken.
        print("-- graft --force on an already-grafted chain stops the seeded root too")
        live_before = flying(govg)[0]
        rgf = graft_lane(iw, govg, hush, force=True)
        ck("--force overrode the refusal and grafted again", rgf["seeded"] > 0, str(rgf))
        ck("...it recognised the previously-seeded root as a root (no 'spawned' edge can halt it "
           "from above, whatever its predecessor line says)", live_before in rgf["roots"],
           "%s not in %s" % (live_before, rgf["roots"]))
        ck("...so the previously-seeded root is now HALTED, not left in flight",
           govg.active_stops_for(live_before) > 0, str(govg.active_stops_for(live_before)))
        ck("ACCEPTANCE: still exactly ONE index-watch in flight after a --force graft",
           flying(govg) == [rgf["seeded"]], str(flying(govg)))
        ck("...and the --force graft reports the bound as met", rgf["ok"], str(rgf["ok"]))

        # ── the settle gate: a pair-kind member is run but never settled, and never faked ──
        print("-- the settle gate: why the chain must be a SOLO kind")
        pair_seed = {400: {"id": 400, "title": iw.SUCCESSOR_TITLE % 197, "body": "",
                           "kind": "build", "status": "REQUESTED", "component": "congruency"}}
        gov2 = ChainGov(tickets=pair_seed)
        store2 = os.path.join(base, "code_sim2.db")
        r8 = watch_lane(iw, gov2, watcher(gov2, store2), hush)
        ck("a pair-kind member RUNS and spawns its successor", r8["ran"] == 0 and len(gov2.edges) == 1,
           str(gov2.edges))
        ck("...but is NOT settled (tg_tickets_pair_completion refuses DONE without a pair)",
           r8["settled"] == [], str(r8["settled"]))
        ck("...the lane did not even attempt the settle, and never faked one",
           not any(c[1].get("status") == "DONE" for c in gov2.calls if c[0] == "process_status"))
        ck("...and it is REPORTED, not hidden: the bound is not yet met", not r8["ok"], str(r8["ok"]))
        ck("...while the successor it spawned IS the solo kind, so the chain settles from there on",
           gov2.tickets[int(gov2.edges[0][1])]["kind"] == "audit")

        # ── --dry-run: the docstring says it writes NOTHING; prove it ──
        print("-- --dry-run: reports the plan, writes nothing")
        dry_head = opens()[0]
        dry_settled, dry_calls, dry_tickets = set(settled_shas()), len(gov.calls), len(gov.tickets)
        rd = watch_lane(iw, gov, run_watch, hush, dry=True)
        ck("--dry-run names the head it WOULD run", rd["head"] == dry_head, str(rd["head"]))
        ck("...runs nothing", rd["ran"] is None, str(rd["ran"]))
        ck("...settles nothing", not rd["settled"] and not rd["superseded"], str(rd))
        ck("...seeds nothing", rd["seeded"] == 0, str(rd["seeded"]))
        ck("...indexes nothing", settled_shas() == dry_settled)
        ck("...spawns nothing (no ticket is filed)", len(gov.tickets) == dry_tickets)
        ck("...and calls ONLY read routes — no agent.register, no process_status, no write at all",
           {c[0] for c in gov.calls[dry_calls:]} <= {"ticket.queue", "ticket.stops", "kind.roster"},
           str({c[0] for c in gov.calls[dry_calls:]}))
        ck("...leaving the chain exactly as it found it", opens() == [dry_head], str(opens()))

        # ── the --ticket override on an unrelated ticket, and an empty queue ──
        print("-- edges: an unrelated open ticket is not mistaken for a chain member")
        empty = ChainGov(tickets={500: {"id": 500, "title": "Build: unrelated", "body": "",
                                        "kind": "build", "status": "OPEN"}})
        r9 = watch_lane(iw, empty, lambda t: 0, hush, reseed=False)
        ck("an unrelated open ticket is not a member, so the chain reads as empty",
           r9["head"] == 0 and r9["ran"] is None and not r9["settled"], str(r9))
        ck("...and #500 was never touched", empty.tickets[500]["status"] == "OPEN")

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
                    "chain (one link per cycle, exactly one in flight at a time, a stop ticket is the "
                    "brake) and dispatch-01 routing the queue.")
    ap.add_argument("command", choices=["install", "uninstall", "status", "run-once", "cycle",
                                        "watch", "graft", "selftest"],
                    help="install/uninstall/status/run-once manage the LaunchAgent; `cycle` is one "
                         "full cycle in this process (what launchd runs); `watch` is the index-watch "
                         "lane alone; `graft` is the ONE-TIME stop+spawn that replaces a chain this "
                         "lane cannot settle; `selftest` proves the chain offline")
    ap.add_argument("--ticket", type=int, default=0,
                    help="watch/cycle: run THIS member instead of the newest open index-watch. Only "
                         "members STRICTLY OLDER than it are settled as superseded; newer ones are "
                         "left untouched.")
    ap.add_argument("--successor-kind", default="",
                    help="watch/cycle: kind for the spawned successor (default: registry.json's "
                         "dispatch.index_watch.successor_kind, else %r). Must be a SOLO kind in "
                         "kind.roster or the chain cannot settle itself." % DEFAULT_KIND)
    ap.add_argument("--limit", type=int, default=-1,
                    help="watch/cycle: index at most N new blobs this run (default: registry.json's "
                         "dispatch.index_watch.limit, else no cap). Deferred blobs are picked up by "
                         "the next cycle — a cap never loses one.")
    ap.add_argument("--dry-run", action="store_true",
                    help="watch/cycle/graft: report what it WOULD do, then stop. Writes NOTHING: no "
                         "agent registered, nothing seeded, run, settled, stopped or spawned — only "
                         "the read routes are called. The safe way to look at a live chain.")
    ap.add_argument("--force", action="store_true",
                    help="graft: graft even though the bound already holds (halts a healthy chain and "
                         "replaces it — you almost never want this)")
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

    # `watch` and `graft`: under the same lock the cycle uses, so neither can act beside a cycle
    # (--dry-run changes nothing, so it takes no lock and creates no lock file)
    lock = None if a.dry_run else acquire()
    if lock is None and not a.dry_run:
        print("another cycle holds %s — doing nothing (the bound: one index-watch in flight at a "
              "time)" % LOCK)
        return 5
    try:
        return do_graft(a, cfg, print) if a.command == "graft" else do_watch(a, cfg, print)
    finally:
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as e:
        print("dispatch_schedule: %s" % e)      # one line, never a traceback
        sys.exit(2)
