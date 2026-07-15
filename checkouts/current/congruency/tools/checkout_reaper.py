#!/usr/bin/env python3
"""checkout_reaper.py — the checkout REAPER: scan checkout roots, CLASSIFY every tree, and reclaim
the idle ones commit -> push -> VERIFY -> remove (ticket #217, under RFC #216).

THE INVARIANT, quoted from RFC #216, which is its only source in this repository: "code is never
left stranded in a checked-out location (anywhere under ~/code/ or any configured checkout root).
Code is allowed OUT of the forge in EXACTLY two cases: (1) it is a DEPLOYED production app/utility/
script, or (2) an AGENT is ACTIVELY working on it. In every other case the checkout is reclaimed."

THE ONE RULE THAT OUTRANKS THE INVARIANT, quoted from ticket #217: "NEVER remove without a verified
push." Reclaiming is not deleting. A tree is removed only after its work is a commit, that commit is
on the forge, and THE FORGE ITSELF has been asked and has confirmed it (see THE VERIFY). Every
failure anywhere in that chain ABORTS the removal and leaves the tree exactly as it was found. This
file would rather leak a stranded checkout forever than lose one line of work.

TERMS, each defined at first use, because whoever reads this file did not watch it being written:

  * THE FORGE is this project's git home: a set of bare repositories (`git init --bare` — a repo with
    no working tree, which is what you push TO) that every checkout has as a remote. A REMOTE is a
    named URL git pushes to; the one this file uses is named `forge` by default (config `remote`).
  * A CHECKOUT (or TREE) is a directory with a `.git` in it — a working copy of a repo, on disk,
    outside the forge. That is the thing this file reclaims.
  * A LINKED WORKTREE is a second working tree of one repo, made by `git worktree add`. Its `.git` is
    a FILE ("gitdir: ...") pointing back into the parent repo, not a directory. The pair-loop's live
    worker trees are exactly this. This file NEVER removes one — see THE PROTECTED SET.
  * TRACKED / UNTRACKED / IGNORED: git has the file in its index; git does not; .gitignore names it.
    The difference is safety-critical here — see THE IGNORED-FILE RULE.
  * A LEASE is a live heartbeat that says "an agent is working here, hold off" (ticket #218). A
    heartbeat is a row {path/component, ts/last_seen, ttl}: it is LIVE while `now - ts <= ttl`, and
    it LAPSES the moment its holder stops renewing it. This is the DEAD-MAN'S SWITCH pattern this
    repo already runs (tracker/store.py:112-136, tracker/SIGNALS.md §4): "The default condition is
    error. The functional component holds it back." Here the default condition is RECLAIM, and a
    live lease is what holds it back. A crashed agent simply stops renewing, and its tree is
    reclaimed with no manual cleanup.
  * THE DEPLOYED REGISTRY is the allowlist of code permitted to live outside the forge forever —
    deployed apps/utilities/scripts (ticket #219). Registration is a deliberate, auditable act.
  * THE DB ERROR CHANNEL is the `signals` table — "a DB error channel that any process writes to and
    anyone can query" (tracker/SIGNALS.md:15). This file writes one signal per reclaim and one per
    refusal, through tracker/store.py's own `raise_signal()` (store.py:80-86). It never opens that
    table by hand — see REUSE, NOT REINVENTION.

════════════════════════════════════════════════════════════════════════════════════════════════════
READ THIS BEFORE ANYTHING ELSE: TWO SYSTEMS THIS FILE CONSUMES DO NOT EXIST YET
════════════════════════════════════════════════════════════════════════════════════════════════════
Ticket #217 names two sibling systems by reference — "the deployed-app registry #registry" and "a
live lease/heartbeat #lease". Both are SEPARATE, UNBUILT tickets, and this was verified against the
live ticket db, not assumed:

    #218  Build: active-work LEASE/heartbeat ...............................  status ACTIVE  (in flight)
    #219  Build: DEPLOYED-app registry .....................................  status REQUESTED (not started)

Neither has landed a table, a file, or a tool. This file therefore CONSUMES A CONTRACT rather than an
implementation, and the contract is quoted from those tickets' own bodies (see THE LEASE CONTRACT and
THE REGISTRY CONTRACT). Two consequences, and they are the most important behavior in this file:

  1. IT DOES NOT CREATE THEIR TABLES. #218 is being built in parallel, right now. If this file
     created a `checkout_leases` table with a schema it invented, it would collide with the one #218
     is about to land. store.py refuses the identical temptation for the identical reason and says so
     in its schema: "`tickets` is intentionally NOT created here — jazz owns the tickets table ...
     Recreating a divergent `tickets` here would collide with jazz's" (store.py:50-52). This file
     only ever READS the lease and registry sources, tolerantly, and treats an absent one as absent.

  2. IT REFUSES TO REAP UNTIL THE LEASE SYSTEM EXISTS. This is THE SAFETY GATE, and it is the single
     most important decision in this file, so it is stated plainly: a lease is the ONLY mechanism by
     which an agent can say "I am working here." If no lease source exists at all, then no agent CAN
     hold one, so every tree — including one with an agent live in it — classifies IDLE and would be
     reclaimed. On this host that is not hypothetical: #218 is ACTIVE, meaning a pair is at work in a
     checkout as this runs. So `reap` REFUSES to remove anything while no lease source exists: it
     reports what it WOULD do, writes a REAPER_NO_LEASE_SOURCE signal, and exits 4. The moment #218
     lands its table, the reaper arms itself with no change to this file. `--force-unleased` overrides
     the gate; it is documented in --help as dangerous and it is not what you want.

     What counts as EVIDENCE that the lease system exists is a strictly harder question than "does a
     table exist", and getting it wrong makes the gate disarm ITSELF — this daemon's own heartbeat
     would otherwise create the very table the gate looks for. lease_sources() is where that is
     reasoned out, and it is worth reading before touching the gate.

Ticket #217 also says "Implement the reaper as a durable process_manager service." THERE IS NO
process_manager IN THIS REPOSITORY, and there is none on this host (no such table, module, binary, or
LaunchAgent — checked). The name comes from RFC #205's mitigation M1 — "(M1) move the runner to a
DURABLE SERVICE (process_manager, like kokoro/litellm) so agents survive session teardown" — and #205
is still status REQUESTED: it is a proposal, not a system. Rather than import a fiction, this file is
durable in the ONE way this repo actually is: a macOS LaunchAgent, exactly as tools/dispatch_schedule.py
does it (its build_plist/install/uninstall/status, dispatch_schedule.py:967-1058). `install` registers
`checkout_reaper.py run` on a timer under launchd, which is session-independent and survives logout,
teardown and reboot — the durability M1 asks for. If a real process_manager ever lands, `run` is the
one-cycle entry point it should call, and nothing else here changes.

════════════════════════════════════════════════════════════════════════════════════════════════════

THE CLASSIFY -> RECLAIM STATE MACHINE. Every discovered tree lands in exactly one class. Only IDLE is
ever touched; the report always names the class and the REASON, so a refusal is never a mystery:

    PROTECTED     — structurally unsafe to remove, regardless of leases. THE PROTECTED SET, below.
    DEPLOYED      — in the deployed registry with deployed=true (#219). Skip.
    ACTIVE        — holds a LIVE lease (#218). Skip.
    UNRECLAIMABLE — no `.git`, or no forge remote, or nothing pushable. CANNOT be given a verified
                    push, therefore MUST NOT be removed (THE ONE RULE). Reported + signalled, kept.
    IDLE          — none of the above. Reclaim.

RECLAIM, strictly ordered — the order IS the safety, and it is the order ticket #217 states (a-d):

    (a) COMMIT   every uncommitted change (`git add -A` + a commit carrying reaper provenance).
                 Nothing to commit is not a failure — a clean tree just skips to (b).
    (b) PUSH     every local branch and tag to the forge remote (`--all`, then `--tags`). Never
                 forced: a rejected push is a push that would rewrite history, and history here is
                 append-only. A rejected push aborts.
    (c) VERIFY   ASK THE FORGE. `git ls-remote <remote>` and compare, ref by ref, the sha the remote
                 reports against the local sha. See THE VERIFY.
    (d) REMOVE   only now, and only after THE REMOVAL GUARD re-checks the path from scratch.

THE VERIFY — why (c) exists at all, given (b) already returned success. A push's exit code says the
local git client believed it succeeded. It does not say the bytes are on the forge: a push can report
success against a remote that silently discarded the update, a hook can reject after the fact, a
mirror can lie, a URL can point at a stale copy. (c) throws that trust away and asks the REMOTE what
it has, then compares shas — the sha IS the content hash, so an equal sha is proof the content
landed. Removal is gated on THAT answer and nothing else. If ls-remote cannot be reached, verify
FAILS (it does not pass by default) and the tree is kept.

THE PROTECTED SET — trees this file will not remove even if they are idle, unleased and unregistered.
Each is a way a "reclaim" would destroy something a push cannot restore:

  * THIS REPOSITORY (the tree this file is running out of). Reaping your own root mid-run.
  * THE PAIR WORKTREES DIRECTORY, read from registry.json's own `branch_per_ticket.worktrees`
    (registry.json:24-27), not hardcoded. These are "LIVE PAIR WORKTREES, mid-ticket"
    (clean_recheckout.py:88); a pair is running in one of them right now.
  * ANY LINKED WORKTREE (`.git` is a file, not a directory). `shutil.rmtree` on one leaves a stale
    admin entry in the parent repo; `git worktree remove` is the only correct removal, and that is a
    different operation than this file performs.
  * ANY ROOT ITSELF, `$HOME`, and `/`. A root holds checkouts; it is not one.
  * ANYTHING NOT INSIDE A CONFIGURED ROOT, re-checked at the moment of removal.

THE IGNORED-FILE RULE — the paragraph to read before trusting this file with a directory. `git add -A`
stages tracked and untracked files; it does NOT stage IGNORED ones, and removing the tree DELETES
them. That is not a bug, it is what .gitignore means: the repo's own written declaration that a path
is not part of any commit and is regenerated by running things (pair_loop.py:227-229 says exactly
that of the same class of file). But it means a reclaim is NOT lossless for ignored paths — a venv, a
build dir, `logs/`, and in this repo `checkouts/current/state/congruency.sqlite`, THE STATE DATABASE,
are all ignored. `scan` prints an `ignored=N` count for every reclaimable tree so you are told before
anything happens, and a tree whose ignored set is non-empty still reclaims — .gitignore already said
those bytes are disposable. If that is wrong for a given tree, the tree does not belong under a reap
root, or it belongs in the deployed registry.

REUSE, NOT REINVENTION. The signals channel and the dead-man's switch already exist and are already
correct; this file imports tracker/store.py by path and calls `raise_signal()` and `beat()` rather
than restating them (the same technique dispatch_schedule.py uses to drive index_watch.py without
drifting from it, dispatch_schedule.py:250-267). That also means this file honors store.py's own db
precedence — $PROJECT_DB > $JAZZ_DB > ~/.jazz/congruency.sqlite (store.py:34-43) — instead of
inventing a second answer to "which db". It does NOT call store.check_deadman(): firing OTHER
components' dead-man switches is the signals daemon's job (SIGNALS.md §6), not the reaper's. The
reaper reads lease freshness itself and beats its own heartbeat so that IT, too, is watched.

COMMANDS (every one runs as written; `scan` is the default and mutates nothing):

    python3 tools/checkout_reaper.py scan                 # classify every tree, change NOTHING
    python3 tools/checkout_reaper.py scan --json          # the same, machine-readable
    python3 tools/checkout_reaper.py reap --dry-run       # name what WOULD be reclaimed
    python3 tools/checkout_reaper.py reap                 # commit -> push -> verify -> remove
    python3 tools/checkout_reaper.py run                  # ONE durable cycle (what launchd runs)
    python3 tools/checkout_reaper.py watch --interval 900 # the same cycle, foreground loop
    python3 tools/checkout_reaper.py install              # register the LaunchAgent (durable)
    python3 tools/checkout_reaper.py status               # the LaunchAgent + the sources + the beat
    python3 tools/checkout_reaper.py uninstall            # remove the LaunchAgent
    python3 tools/checkout_reaper.py selftest             # PROVE all four ACCEPTANCE criteria

`selftest` is the artifact's own proof and needs no argument, no network, and no live db: it builds
real git repos and a real bare forge in a temp dir, points the reaper's db at a temp file, and proves
ticket #217's ACCEPTANCE point by point — an idle tree with uncommitted edits is committed, pushed,
removed AND RECOVERED BACK from the forge (the recovered file's bytes are compared); a leased tree and
a registered deployed tree are untouched; and a push failure aborts the removal with the tree and its
edits intact. It removes its temp dir and touches nothing else.

CONFIG — registry.json, optional `reaper` block. Every key has a default, so this file runs with the
registry.json that exists today (which has no `reaper` block; adding one is a config act, and this
file's mandate is to touch only itself). Defaults in brackets:

    "reaper": {
      "roots":      ["~/code"],   # the checkout roots to scan
      "depth":      3,            # how deep under a root to look for a `.git`
      "remote":     "forge",      # the remote reclaim pushes to and verifies against
      "lease_ttl":  900,          # fallback ttl (seconds) for a lease row that carries none
      "beat_ttl":   3600,         # this daemon's own heartbeat ttl
      "interval_hours": 1.0,      # LaunchAgent timer
      "deployed_apps": {}         # THE REGISTRY CONTRACT (#219) — see below
    }

THE REGISTRY CONTRACT (#219), quoted: "path -> {name, kind=app|utility|script, deployed=true}", a
"control-config object". registry.json IS this repo's control config — the file every registry-gated
tool walks up to find (registry.json:2) — so that is where this file reads it from, under
`reaper.deployed_apps`. A tree is DEPLOYED iff its real path is a key (or is inside one) whose object
has `deployed` true. Setting deployed=false or removing the key makes it reapable next cycle, which
is #219's acceptance. A `deployed_apps` TABLE in the db (path, deployed) is also honored if #219
lands one instead; both sources union.

THE LEASE CONTRACT (#218), quoted: "a LEASE (a heartbeat record: path, holder, ts, ttl)", which
"Mirrors tracker/store.py's heartbeat/check_deadman". #218 has not landed, so its exact spelling is
not yet knowable, and this file reads BOTH shapes that sentence can produce:

    1. a `checkout_leases` table with #218's named fields (path, holder, ts, ttl); or
    2. the EXISTING `heartbeat` table (store.py:56-57), for rows whose `component` is
       "checkout:<abspath>" — the "mirrors store.py's heartbeat" reading. The prefix is what keeps
       these rows from colliding with the real components already in that table (`ticket_reader`,
       `signals-mcp`).

Reading both is not indecision, it is the fail-safe direction: an EXTRA lease source can only ever
cause MORE skipping, never more reaping. Misreading a lease as live costs one un-reaped tree, which
this file leaks safely; missing one destroys an agent's work. When the two disagree, live wins.

EXIT CODES: 0 clean · 1 a reclaim failed (tree kept) · 2 precondition failure (one line, never a
traceback) · 3 another cycle holds the lock · 4 REFUSED: no lease source, nothing was touched.
"""
import argparse
import fcntl
import importlib.util
import json
import os
import plistlib
import shutil
import socket
import sqlite3
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TICKET = 217
AGENT = "checkout-reaper"          # the component name this daemon beats under
LABEL = "com.congruency.reaper"    # the LaunchAgent Label (dispatch_schedule.py's is .dispatch)
PLIST = os.path.expanduser("~/Library/LaunchAgents/%s.plist" % LABEL)

# Signal codes written to the DB error channel. SIGNALS.md §8 tabulates the pre-existing codes; these
# are this file's, and nothing else writes them.
SIG_RECLAIMED = "REAPER_RECLAIMED"            # info  — a tree was committed, pushed, verified, removed
SIG_COMMIT_FAILED = "REAPER_COMMIT_FAILED"    # error — (a) failed; tree kept
SIG_PUSH_FAILED = "REAPER_PUSH_FAILED"        # error — (b) failed; tree kept
SIG_VERIFY_FAILED = "REAPER_VERIFY_FAILED"    # error — (c) failed; tree kept  <- the ONE RULE holding
SIG_REMOVE_FAILED = "REAPER_REMOVE_FAILED"    # error — (d) failed after a verified push
SIG_UNRECLAIMABLE = "REAPER_UNRECLAIMABLE"    # warn  — cannot ever be given a verified push
SIG_NO_LEASE_SOURCE = "REAPER_NO_LEASE_SOURCE"  # error — THE SAFETY GATE refused the run


class Fault(Exception):
    """A precondition failure — reported as one line, exit 2 (never a traceback)."""


# ── the root, the config ──────────────────────────────────────────────────────────────────────────
def find_root(start=HERE):
    """Walk UP for registry.json — the repo's own convention for locating the package root (mirrors
    gates.py:24-32 and dispatch_schedule.py:207-220). Every registry-gated tool refuses to run
    without it."""
    d = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(d, "registry.json")):
            return d
        nxt = os.path.dirname(d)
        if nxt == d:
            raise Fault("registry.json not found walking up from %s — refusing to run "
                        "(note-for-claude)" % start)
        d = nxt


ROOT = find_root()
LOGS = os.path.join(ROOT, "logs")
LOCK = os.path.join(LOGS, "checkout_reaper.lock")
SELF = os.path.abspath(__file__)

DEFAULTS = {"roots": ["~/code"], "depth": 3, "remote": "forge", "lease_ttl": 900,
            "beat_ttl": 3600, "interval_hours": 1.0, "deployed_apps": {}}


def registry():
    with open(os.path.join(ROOT, "registry.json")) as fh:
        return json.load(fh)


def config(reg=None):
    """The optional `reaper` block of registry.json, defaulted. registry.json has no `reaper` block
    today; every key below therefore falls back to DEFAULTS, and the tool runs as-shipped."""
    reg = registry() if reg is None else reg
    c = dict(DEFAULTS)
    c.update(reg.get("reaper") or {})
    c["roots"] = [os.path.abspath(os.path.expanduser(r)) for r in (c.get("roots") or [])]
    c["depth"] = int(c.get("depth", 3))
    c["lease_ttl"] = int(c.get("lease_ttl", 900))
    c["beat_ttl"] = int(c.get("beat_ttl", 3600))
    c["interval_hours"] = float(c.get("interval_hours", 1.0))
    # THE PROTECTED SET's pair-worktree entry, read from the registry rather than hardcoded.
    wt = ((reg.get("branch_per_ticket") or {}).get("worktrees") or "").strip()
    c["worktrees_dir"] = os.path.abspath(os.path.expanduser(wt)) if wt else ""
    return c


# ── tracker/store.py, imported rather than restated ───────────────────────────────────────────────
def load_store(root=None):
    """Import tracker/store.py by path. The DB error channel (`raise_signal`) and the dead-man's
    switch (`beat`) already exist there and are already correct; restating either would let this file
    drift out of agreement with the daemon that reads the same tables (SIGNALS.md §6). Importing also
    inherits store.py's db precedence, $PROJECT_DB > $JAZZ_DB > ~/.jazz/congruency.sqlite
    (store.py:34-43), so there is exactly one answer to 'which db'."""
    path = os.path.join(root or ROOT, "tracker", "store.py")
    if not os.path.isfile(path):
        raise Fault("no tracker/store.py at %s — the reaper writes its signals through it and "
                    "cannot run without it" % path)
    spec = importlib.util.spec_from_file_location("reaper_store", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        raise Fault("tracker/store.py at %s did not load (%r)" % (path, e))
    return mod


# ── git ───────────────────────────────────────────────────────────────────────────────────────────
def git(args, cwd, timeout=120):
    """Run one git command. Returns (rc, stdout, stderr) — never raises on a non-zero rc, because
    every git failure in this file is a decision point, not an exception."""
    try:
        r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", "git %s timed out after %ds" % (" ".join(args[:2]), timeout)
    except OSError as e:
        return 127, "", "git not runnable: %r" % e
    return r.returncode, r.stdout, r.stderr


def is_git_tree(path):
    return os.path.exists(os.path.join(path, ".git"))


def is_linked_worktree(path):
    """A LINKED WORKTREE's .git is a FILE ('gitdir: ...'), not a directory — see THE PROTECTED SET."""
    return os.path.isfile(os.path.join(path, ".git"))


def local_refs(path):
    """{refname: sha} for every local branch and tag — everything a push must carry and a verify must
    confirm. These are the refs whose loss would be lost WORK."""
    out = {}
    for pat in ("refs/heads/", "refs/tags/"):
        rc, so, _ = git(["for-each-ref", "--format=%(refname) %(objectname)", pat], path)
        if rc != 0:
            continue
        for line in so.strip().splitlines():
            parts = line.split()
            if len(parts) == 2:
                out[parts[0]] = parts[1]
    return out


def remote_refs(path, remote):
    """ASK THE FORGE: {refname: sha} as the REMOTE reports them. (rc, refs, err)."""
    rc, so, se = git(["ls-remote", remote], path)
    if rc != 0:
        return rc, {}, (se or so).strip()
    refs = {}
    for line in so.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            refs[parts[1]] = parts[0]
    return 0, refs, ""


def has_remote(path, remote):
    rc, so, _ = git(["remote"], path)
    return rc == 0 and remote in so.split()


def dirty(path):
    """The uncommitted set: tracked modifications AND untracked files (NOT ignored ones — THE
    IGNORED-FILE RULE). `--porcelain` is the stable, script-readable spelling."""
    rc, so, _ = git(["status", "--porcelain"], path)
    if rc != 0:
        return []
    return [l for l in so.splitlines() if l.strip()]


def ignored(path):
    """The IGNORED set — bytes a reclaim does NOT preserve. Counted and reported, never committed."""
    rc, so, _ = git(["status", "--porcelain", "--ignored=matching"], path)
    if rc != 0:
        return []
    return [l for l in so.splitlines() if l.startswith("!!")]


# ── the classifier's sources ──────────────────────────────────────────────────────────────────────
def _table_exists(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (name,)).fetchone() is not None


def open_db(db_path):
    """A plain read connection with a busy timeout. Deliberately does NOT run store.py's SCHEMA: a
    `scan` must not CREATE the tables it is only reading, and it must never create #218's table at
    all (see IT DOES NOT CREATE THEIR TABLES). Returns None if there is no db file — an absent db is
    an absent source, not a crash."""
    if not db_path or not os.path.isfile(db_path):
        return None
    try:
        con = sqlite3.connect(db_path, timeout=5)
        con.row_factory = sqlite3.Row
        return con
    except sqlite3.Error:
        return None


def lease_sources(con):
    """Evidence that THE LEASE SYSTEM (#218) is INSTALLED — which is what THE SAFETY GATE turns on.
    This asks a strictly harder question than "can I read a lease table", and the difference is a
    trap that bit this file during its own testing:

    THE HEARTBEAT TABLE'S MERE EXISTENCE PROVES NOTHING. `heartbeat` is a SHARED table. store.py
    creates it on any write (store.py:56-57,70-74), the live state db already has one, and — worst
    — THIS DAEMON CREATES IT ITSELF by beating at the end of every cycle. Counting the bare table as
    a lease source would mean: cycle 1 refuses and beats; the beat creates `heartbeat`; cycle 2 sees
    a "lease source", arms itself, and reaps every tree on the host. The gate would disarm itself by
    running. So the heartbeat shape counts ONLY once it holds at least one `checkout:` row — a row
    only a lease holder writes.

    A LAPSED row still counts, deliberately: it proves the mechanism is installed and in use, and it
    must not protect its tree (a lapsed lease is exactly what the reaper is FOR — #218: "stop
    renewing -> after ttl the reaper reclaims it"). Were only LIVE rows to count, the gate would
    slam shut at the precise moment every lease lapsed, i.e. the moment there was work to do.
    """
    if con is None:
        return []
    found = []
    if _table_exists(con, "checkout_leases"):
        found.append("checkout_leases")          # dedicated: only #218 creates this
    if _table_exists(con, "heartbeat"):
        row = con.execute("SELECT 1 FROM heartbeat WHERE component LIKE 'checkout:%' "
                          "LIMIT 1").fetchone()
        if row:
            found.append("heartbeat")
    return found


def live_leases(con, now=None, fallback_ttl=900):
    """{realpath: {holder, ts, ttl, age, source}} for every LIVE lease, from every source that
    exists. A lease is live while `now - ts <= ttl` — the dead-man's-switch test, store.py:127-128.
    Unparseable rows are SKIPPED, never treated as live: a lease you cannot read is not a lease.
    """
    out = {}
    if con is None:
        return out
    now = time.time() if now is None else now

    def put(path, holder, ts, ttl, source):
        if not path or ts is None:
            return
        ttl = int(ttl) if ttl else int(fallback_ttl)
        age = now - ts
        if age > ttl:
            return                                   # LAPSED — the switch has fired; reapable
        rp = os.path.realpath(os.path.expanduser(str(path)))
        prev = out.get(rp)
        if prev is None or age < prev["age"]:        # when sources disagree, the freshest wins
            out[rp] = {"holder": holder or "?", "ts": ts, "ttl": ttl, "age": age, "source": source}

    if _table_exists(con, "checkout_leases"):
        cols = {r["name"] for r in con.execute("PRAGMA table_info(checkout_leases)")}
        if "path" in cols:
            for r in con.execute("SELECT * FROM checkout_leases"):
                put(r["path"], r["holder"] if "holder" in cols else None,
                    _as_epoch(r["ts"]) if "ts" in cols else None,
                    r["ttl"] if "ttl" in cols else None, "checkout_leases")

    if _table_exists(con, "heartbeat"):
        for r in con.execute("SELECT * FROM heartbeat"):
            comp = r["component"] or ""
            if not comp.startswith("checkout:"):
                continue                              # a real component (ticket_reader, ...) — not a lease
            put(comp[len("checkout:"):], comp, _as_epoch(r["last_seen"]), r["ttl"], "heartbeat")
    return out


def _as_epoch(v):
    """store.py stamps time as an ISO string, `time.strftime("%Y-%m-%dT%H:%M:%S")` (store.py:66-67);
    a `ts` column might equally be unix seconds. Accept both, and return None for anything else —
    an unreadable stamp must NOT read as a live lease."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    try:
        return float(s)                       # unix seconds, possibly as text
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return time.mktime(time.strptime(s, fmt))
        except ValueError:
            continue
    return None


def deployed_registry(con, cfg):
    """THE REGISTRY CONTRACT (#219): {realpath: {name, kind, deployed}} for entries with
    deployed=true, unioning the control-config object and a db table if one ever lands."""
    out = {}

    def put(path, name, kind, dep, source):
        if not path or not dep:
            return                                    # deployed=false ⇒ reapable (#219's acceptance)
        rp = os.path.realpath(os.path.expanduser(str(path)))
        out[rp] = {"name": name or os.path.basename(rp), "kind": kind or "app", "source": source}

    for path, obj in (cfg.get("deployed_apps") or {}).items():
        if isinstance(obj, dict):
            put(path, obj.get("name"), obj.get("kind"), obj.get("deployed", True), "registry.json")
        else:
            put(path, None, None, bool(obj), "registry.json")   # "path": true, the terse spelling

    if con is not None and _table_exists(con, "deployed_apps"):
        cols = {r["name"] for r in con.execute("PRAGMA table_info(deployed_apps)")}
        if "path" in cols:
            for r in con.execute("SELECT * FROM deployed_apps"):
                put(r["path"], r["name"] if "name" in cols else None,
                    r["kind"] if "kind" in cols else None,
                    r["deployed"] if "deployed" in cols else 1, "deployed_apps")
    return out


def _covered_by(rp, mapping):
    """A tree is covered by an entry that IS it, or that CONTAINS it — a deployed app's checkout
    exempts the tree it is, and anything vendored inside it."""
    for key, val in mapping.items():
        if rp == key or rp.startswith(key.rstrip(os.sep) + os.sep):
            return key, val
    return None, None


# ── the scanner ───────────────────────────────────────────────────────────────────────────────────
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "site-packages", ".tox",
             ".mypy_cache", ".pytest_cache", "Library"}


def discover(roots, depth):
    """Every checkout under every root, to `depth`. A directory with a `.git` IS a checkout and is
    not descended into — a repo's inner directories are its own business, not separate trees."""
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue

        def walk(d, level):
            if level > depth:
                return
            if is_git_tree(d):
                found.append(d)
                return                       # do not descend INTO a checkout
            try:
                entries = sorted(os.scandir(d), key=lambda e: e.name)
            except OSError:
                return
            for e in entries:
                if e.name in SKIP_DIRS or e.name.startswith("."):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        walk(e.path, level + 1)
                except OSError:
                    continue

        walk(root, 0)
    return found


# ── the classifier ────────────────────────────────────────────────────────────────────────────────
def _covers(outer, inner):
    """True if `outer` IS `inner` or CONTAINS it. Both must already be realpaths."""
    if not outer or not inner:
        return False
    return outer == inner or inner.startswith(outer.rstrip(os.sep) + os.sep)


def protected_reason(rp, cfg):
    """THE PROTECTED SET. Returns a reason string, or None if the path is not protected.

    BOTH DIRECTIONS ARE CHECKED, and that is the point of this function. A tree is protected if it
    is INSIDE something protected, and equally if it CONTAINS something protected — removing a
    parent takes every child with it. This is not hypothetical on this host: `~/code/installed/
    jazz-project` is itself a git repo, and it CONTAINS both the congruency repo and
    `congruency-pair-worktrees/` (the live pair worktrees, mid-ticket). Checking only "is rp inside
    the worktrees dir?" would call that parent reapable and rmtree the lot. Today it survives only
    because it happens to have no 'forge' remote — an accident, not a guarantee, and not one this
    file is willing to rest a deletion on.
    """
    home = os.path.realpath(os.path.expanduser("~"))
    root = os.path.realpath(ROOT)
    wt = os.path.realpath(cfg["worktrees_dir"]) if cfg.get("worktrees_dir") else ""

    if rp == os.sep:
        return "the filesystem root"
    if _covers(rp, home):
        return "$HOME, or a directory containing it"
    if _covers(rp, root) or _covers(root, rp):
        return "this repository (the reaper's own root), or a directory containing it"
    if wt and (_covers(rp, wt) or _covers(wt, rp)):
        return ("the live pair worktrees (registry.json branch_per_ticket.worktrees), or a "
                "directory containing them")
    for r in cfg["roots"]:
        if rp == os.path.realpath(r):
            return "a configured checkout root itself, not a checkout"
    if is_linked_worktree(rp):
        return "a linked git worktree (.git is a file; `git worktree remove` is its only safe removal)"
    if not any(_covers(os.path.realpath(r), rp) for r in cfg["roots"]):
        return "outside every configured checkout root"
    return None


def classify(path, cfg, leases, deployed):
    """One tree -> exactly one class, with the REASON it got there. Pure: reads, never writes."""
    rp = os.path.realpath(path)
    rec = {"path": rp, "name": os.path.basename(rp)}

    reason = protected_reason(rp, cfg)
    if reason:
        return dict(rec, klass="PROTECTED", reason=reason)

    key, dep = _covered_by(rp, deployed)
    if dep:
        return dict(rec, klass="DEPLOYED",
                    reason="registered deployed %s '%s' (%s) via %s" % (dep["kind"], dep["name"],
                                                                        key, dep["source"]))
    key, lease = _covered_by(rp, leases)
    if lease:
        return dict(rec, klass="ACTIVE",
                    reason="live lease held by %s, %ds into a %ds ttl (%s)"
                           % (lease["holder"], int(lease["age"]), lease["ttl"], lease["source"]))

    if not is_git_tree(rp):
        return dict(rec, klass="UNRECLAIMABLE",
                    reason="not a git checkout — it can never be given a VERIFIED PUSH, so it is "
                           "never removed")
    if not has_remote(rp, cfg["remote"]):
        return dict(rec, klass="UNRECLAIMABLE",
                    reason="no '%s' remote — nowhere to push, so nothing to verify, so no removal"
                           % cfg["remote"])
    if not local_refs(rp):
        return dict(rec, klass="UNRECLAIMABLE",
                    reason="no local branches or tags (a repo with no commits) — nothing pushable")

    d, ig = dirty(rp), ignored(rp)
    return dict(rec, klass="IDLE", dirty=len(d), ignored=len(ig),
                reason="no live lease and not in the deployed registry")


def survey(cfg, con):
    """Classify every discovered tree. Returns (records, sources)."""
    leases = live_leases(con, fallback_ttl=cfg["lease_ttl"])
    deployed = deployed_registry(con, cfg)
    sources = {"lease_sources": lease_sources(con), "leases_live": len(leases),
               "deployed_entries": len(deployed)}
    recs = [classify(p, cfg, leases, deployed) for p in discover(cfg["roots"], cfg["depth"])]
    recs.sort(key=lambda r: (r["klass"], r["path"]))
    return recs, sources


# ── RECLAIM: (a) commit -> (b) push -> (c) VERIFY -> (d) remove ───────────────────────────────────
def provenance(rec, cfg):
    """The reaper commit message + provenance ticket #217 asks for. A blind reader of this commit,
    months later, must be able to tell WHAT took the tree and WHY."""
    return ("reaper: reclaim idle checkout '%s'\n"
            "\n"
            "This commit was made by the checkout reaper (ticket #%d, RFC #216), which found this\n"
            "checkout IDLE and captured every uncommitted change so that the work is preserved in\n"
            "the forge BEFORE the working tree was removed. Nothing was discarded: the tree was\n"
            "removed only after this commit was pushed to '%s' and the remote was asked and\n"
            "confirmed it. Recover the tree by cloning it back from the forge.\n"
            "\n"
            "Reaper-Ticket: #%d\n"
            "Reaper-Tool: tools/checkout_reaper.py\n"
            "Reaper-Path: %s\n"
            "Reaper-Host: %s\n"
            "Reaper-Time: %s\n"
            "Reaper-Reason: %s\n"
            % (rec["name"], TICKET, cfg["remote"], TICKET, rec["path"], socket.gethostname(),
               time.strftime("%Y-%m-%dT%H:%M:%S"), rec["reason"]))


def removal_guard(rp, cfg):
    """THE REMOVAL GUARD — re-derive from scratch, at the moment of removal, that this path may be
    removed. Deliberately redundant with the classifier: (d) is the irreversible step, and it does
    not inherit trust from a decision made earlier in the cycle."""
    if not os.path.isdir(rp):
        return "vanished before removal"
    reason = protected_reason(rp, cfg)
    if reason:
        return "PROTECTED at removal time: %s" % reason
    if os.path.realpath(rp) != rp:
        return "path is not fully resolved"
    depth_ok = any(rp.startswith(os.path.realpath(r) + os.sep) and
                   rp != os.path.realpath(r) for r in cfg["roots"])
    if not depth_ok:
        return "not strictly inside a configured root"
    return None


def reclaim(rec, cfg, store, dry_run=False, log=print):
    """RECLAIM one IDLE tree, in ticket #217's order. Returns a result dict; `removed` is true ONLY
    after a verified push. Every failure returns with the tree untouched."""
    rp, res = rec["path"], {"path": rec["path"], "committed": False, "pushed": False,
                            "verified": False, "removed": False, "error": None}
    remote = cfg["remote"]

    if dry_run:
        res["error"] = "dry-run: no action taken"
        return res

    # (a) COMMIT — capture every uncommitted change.
    d = dirty(rp)
    if d:
        rc, _, se = git(["add", "-A"], rp)
        if rc != 0:
            res["error"] = "git add failed: %s" % se.strip()[:200]
            store.raise_signal("error", AGENT, SIG_COMMIT_FAILED, res["error"], ref=rp)
            return res
        # -c keeps identity local to THIS commit: a checkout with no configured user must still be
        # reclaimable, and the reaper must not mutate the tree's config to achieve it.
        rc, so, se = git(["-c", "user.name=checkout-reaper",
                          "-c", "user.email=reaper@congruency.local",
                          "commit", "-m", provenance(rec, cfg)], rp)
        if rc != 0:
            res["error"] = "git commit failed: %s" % (se or so).strip()[:200]
            store.raise_signal("error", AGENT, SIG_COMMIT_FAILED, res["error"], ref=rp)
            return res
        res["committed"] = True
        log("    (a) committed %d uncommitted path(s)" % len(d))
    else:
        log("    (a) tree already clean — nothing to commit")

    # A detached HEAD's commit is on no branch, so `push --all` would not carry it and it would be
    # LOST with the tree. Give it a branch — producing, not erasing.
    rc, so, _ = git(["rev-parse", "--abbrev-ref", "HEAD"], rp)
    if rc == 0 and so.strip() == "HEAD":
        rc, sha, _ = git(["rev-parse", "HEAD"], rp)
        if rc == 0:
            rescue = "reaped/detached-%s-%s" % (time.strftime("%Y%m%d%H%M%S"), sha.strip()[:8])
            git(["branch", rescue], rp)
            log("    (a) detached HEAD rescued onto branch %s" % rescue)

    want = local_refs(rp)
    if not want:
        res["error"] = "nothing pushable (no local refs)"
        store.raise_signal("warn", AGENT, SIG_UNRECLAIMABLE, res["error"], ref=rp)
        return res

    # (b) PUSH — every branch, every tag. Never --force: a rejected push is one that would rewrite
    # history, and this repo's history is append-only.
    # `--tags` is issued ONLY if this repo actually has tags: on a repo with none, `git push --tags`
    # can exit non-zero with "No refs in common and none specified; doing nothing", which is not a
    # failure to push anything — but this file cannot tell that from a real rejection, and reading
    # it as one would abort a reclaim that was fine. Asking git to push nothing is the bug; not
    # asking is the fix.
    pushes = [(["push", remote, "--all"], "branches")]
    if any(r.startswith("refs/tags/") for r in want):
        pushes.append((["push", remote, "--tags"], "tags"))
    for args, what in pushes:
        rc, so, se = git(args, rp, timeout=300)
        if rc != 0:
            res["error"] = "push of %s to '%s' failed: %s" % (what, remote, (se or so).strip()[:200])
            store.raise_signal("error", AGENT, SIG_PUSH_FAILED,
                               "%s — REMOVAL ABORTED, tree kept intact" % res["error"], ref=rp)
            log("    (b) PUSH FAILED — removal aborted, tree kept: %s" % res["error"])
            return res
    res["pushed"] = True
    log("    (b) pushed %d ref(s) to '%s'" % (len(want), remote))

    # (c) VERIFY — ask the FORGE what it has. This is the gate on (d), and nothing else is.
    rc, have, err = remote_refs(rp, remote)
    if rc != 0:
        res["error"] = "cannot read '%s' to verify the push landed: %s" % (remote, err[:200])
        store.raise_signal("error", AGENT, SIG_VERIFY_FAILED,
                           "%s — REMOVAL ABORTED, tree kept intact" % res["error"], ref=rp)
        log("    (c) VERIFY FAILED — removal aborted, tree kept: %s" % res["error"])
        return res
    missing = [r for r, sha in want.items()
               if have.get(r) != sha and have.get(r + "^{}") != sha]   # ^{} = an annotated tag's target
    if missing:
        res["error"] = ("the forge does not have %d of %d ref(s) at the local sha: %s"
                        % (len(missing), len(want), ", ".join(sorted(missing)[:5])))
        store.raise_signal("error", AGENT, SIG_VERIFY_FAILED,
                           "%s — REMOVAL ABORTED, tree kept intact" % res["error"], ref=rp)
        log("    (c) VERIFY FAILED — removal aborted, tree kept: %s" % res["error"])
        return res
    res["verified"] = True
    log("    (c) VERIFIED: the forge reports all %d ref(s) at the local sha" % len(want))

    # (d) REMOVE — only now.
    blocked = removal_guard(rp, cfg)
    if blocked:
        res["error"] = "removal guard refused: %s" % blocked
        store.raise_signal("error", AGENT, SIG_REMOVE_FAILED, res["error"], ref=rp)
        return res
    try:
        shutil.rmtree(rp)
    except OSError as e:
        res["error"] = "rmtree failed after a verified push: %r" % e
        store.raise_signal("error", AGENT, SIG_REMOVE_FAILED, res["error"], ref=rp)
        return res
    res["removed"] = True
    head = want.get("refs/heads/master") or want.get("refs/heads/main") or sorted(want.values())[0]
    store.raise_signal("info", AGENT, SIG_RECLAIMED,
                       "reclaimed idle checkout '%s': %d ref(s) verified on '%s' (head %s), tree "
                       "removed; recover with `git clone %s`" % (rec["name"], len(want), remote,
                                                                 head[:12], remote), ref=rp)
    log("    (d) REMOVED %s — recoverable from '%s'" % (rp, remote))
    return res


# ── the lock ──────────────────────────────────────────────────────────────────────────────────────
def acquire(path=LOCK):
    """An exclusive, NON-blocking flock: one reaper cycle at a time on this host. Released when the
    handle closes or the process exits, so a crashed cycle never wedges the reaper. (Mirrors
    dispatch_schedule.py:289-300.) A read-only `scan` changes nothing and takes no lock."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fh = open(path, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


# ── reporting ─────────────────────────────────────────────────────────────────────────────────────
def report(recs, sources, cfg, out=sys.stdout):
    order = ["IDLE", "ACTIVE", "DEPLOYED", "PROTECTED", "UNRECLAIMABLE"]
    counts = {k: len([r for r in recs if r["klass"] == k]) for k in order}
    print("roots: %s  (depth %d, remote '%s')" % (", ".join(cfg["roots"]) or "(none)", cfg["depth"],
                                                  cfg["remote"]), file=out)
    print("lease sources: %s  ·  live leases: %d  ·  deployed entries: %d"
          % (", ".join(sources["lease_sources"]) or "NONE (see THE SAFETY GATE)",
             sources["leases_live"], sources["deployed_entries"]), file=out)
    print("%d checkout(s): %s" % (len(recs), "  ".join("%s=%d" % (k, counts[k]) for k in order)),
          file=out)
    for k in order:
        for r in [x for x in recs if x["klass"] == k]:
            extra = ""
            if r["klass"] == "IDLE":
                extra = "  [%d uncommitted, %d ignored]" % (r.get("dirty", 0), r.get("ignored", 0))
            print("  %-13s %s%s\n                └─ %s" % (k, r["path"], extra, r["reason"]), file=out)
    return counts


# ── the LaunchAgent: durability, the way this repo actually does it ───────────────────────────────
def build_plist(cfg):
    python3 = sys.executable or shutil.which("python3")
    os.makedirs(LOGS, exist_ok=True)
    return {"Label": LABEL,
            "ProgramArguments": [python3, SELF, "run"],
            "WorkingDirectory": ROOT,
            "StartInterval": int(cfg["interval_hours"] * 3600),
            "RunAtLoad": False,
            "StandardOutPath": os.path.join(LOGS, "checkout_reaper.log"),
            "StandardErrorPath": os.path.join(LOGS, "checkout_reaper.err"),
            "EnvironmentVariables": {"PATH": "/usr/local/bin:/usr/bin:/bin",
                                     "HOME": os.path.expanduser("~")}}


def domain():
    return "gui/%d" % os.getuid()


def install(cfg):
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    with open(PLIST, "wb") as fh:
        plistlib.dump(build_plist(cfg), fh)
    subprocess.run(["launchctl", "bootout", domain(), PLIST], capture_output=True)  # reload-safe
    r = subprocess.run(["launchctl", "bootstrap", domain(), PLIST], capture_output=True, text=True)
    if r.returncode != 0:
        raise Fault("launchctl bootstrap failed: %s" % (r.stderr or r.stdout).strip())
    print("installed %s — `%s run` every %.2fh" % (LABEL, SELF, cfg["interval_hours"]))
    return 0


def uninstall():
    subprocess.run(["launchctl", "bootout", domain(), PLIST], capture_output=True)
    if os.path.exists(PLIST):
        os.unlink(PLIST)
    print("uninstalled %s" % LABEL)
    return 0


# ── commands ──────────────────────────────────────────────────────────────────────────────────────
def cmd_scan(a, cfg, store):
    """READ-ONLY: classify and report. Takes no lock, writes no signal, creates no table."""
    con = open_db(store.DB)
    recs, sources = survey(cfg, con)
    if con:
        con.close()
    if a.json:
        print(json.dumps({"sources": sources, "checkouts": recs, "db": store.DB,
                          "roots": cfg["roots"]}, indent=2))
    else:
        report(recs, sources, cfg)
    return 0


def cmd_reap(a, cfg, store):
    con = open_db(store.DB)
    recs, sources = survey(cfg, con)
    if con:
        con.close()
    counts = report(recs, sources, cfg)
    idle = [r for r in recs if r["klass"] == "IDLE"]

    # THE SAFETY GATE — see READ THIS BEFORE ANYTHING ELSE (2).
    if not sources["lease_sources"] and not a.force_unleased:
        msg = ("REFUSED to reclaim %d idle checkout(s): no lease source exists in %s, so no agent "
               "CAN hold a lease and an actively-worked tree is indistinguishable from a stranded "
               "one. Ticket #218 (the LEASE) is the source and has not landed. Nothing was touched."
               % (len(idle), store.DB))
        if idle:
            store.raise_signal("error", AGENT, SIG_NO_LEASE_SOURCE, msg, ref=",".join(
                r["path"] for r in idle)[:400])
        print("\nREFUSED (exit 4): %s" % msg, file=sys.stderr)
        print("Once #218 lands its lease table the reaper arms itself with no change to this file.\n"
              "To override anyway (DANGEROUS — can reclaim a tree an agent is working in): "
              "--force-unleased", file=sys.stderr)
        return 4

    for r in [x for x in recs if x["klass"] == "UNRECLAIMABLE"]:
        store.raise_signal("warn", AGENT, SIG_UNRECLAIMABLE, r["reason"], ref=r["path"])
    if not idle:
        print("\nnothing to reclaim.")
        return 0

    print("\nreclaiming %d idle checkout(s) — commit -> push -> VERIFY -> remove:" % len(idle))
    failed = 0
    for r in idle:
        print("  %s" % r["path"])
        res = reclaim(r, cfg, store, dry_run=a.dry_run)
        if a.dry_run:
            print("    would reclaim: %d uncommitted, %d ignored (dry-run: nothing done)"
                  % (r.get("dirty", 0), r.get("ignored", 0)))
        elif not res["removed"]:
            failed += 1
    if a.dry_run:
        return 0
    print("\nreclaimed %d of %d; %d kept (see the signals)" % (len(idle) - failed, len(idle), failed))
    return 1 if failed else 0


def cmd_run(a, cfg, store):
    """ONE durable cycle — what the LaunchAgent invokes. Beats the dead-man's switch on a clean
    cycle: this daemon is itself a watched component, so if IT dies, check_deadman() fires for it
    exactly as SIGNALS.md §4 describes."""
    fh = acquire()
    if fh is None:
        print("another reaper cycle holds %s — doing nothing (exit 3)" % LOCK, file=sys.stderr)
        return 3
    try:
        print("── reaper cycle %s ──" % time.strftime("%Y-%m-%dT%H:%M:%S"))
        rc = cmd_reap(a, cfg, store)
        if rc in (0, 4):
            store.beat(AGENT, cfg["beat_ttl"])   # alive and lawful — hold the switch back
        return rc
    finally:
        fh.close()


def cmd_watch(a, cfg, store):
    print("reaper: a cycle every %ds (Ctrl-C to stop)" % a.interval)
    while True:
        try:
            cmd_run(a, cfg, store)
        except Fault as e:
            print("fault: %s" % e, file=sys.stderr)
        except Exception as e:  # noqa: BLE001 — the daemon must never die silently (SIGNALS.md §6)
            store.raise_signal("error", AGENT, "REAPER_CYCLE_EXCEPTION",
                               "%s: %s" % (type(e).__name__, e))
        time.sleep(max(30, a.interval))


def cmd_status(a, cfg, store):
    print("reaper   : %s" % SELF)
    print("root     : %s" % ROOT)
    print("db       : %s%s" % (store.DB, "" if os.path.isfile(store.DB) else "   (absent)"))
    con = open_db(store.DB)
    srcs = lease_sources(con)
    print("lease src: %s" % (", ".join(srcs) or "NONE — `reap` REFUSES (exit 4) until #218 lands"))
    if con:
        if _table_exists(con, "heartbeat"):
            row = con.execute("SELECT * FROM heartbeat WHERE component=?", (AGENT,)).fetchone()
            print("beat     : %s" % (dict(row) if row else "never beaten"))
        con.close()
    print("plist    : %s%s" % (PLIST, "" if os.path.exists(PLIST) else "   (not installed)"))
    r = subprocess.run(["launchctl", "print", "%s/%s" % (domain(), LABEL)],
                       capture_output=True, text=True)
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            if any(k in line for k in ("state =", "runs =", "last exit", "interval =")):
                print("  %s" % line.strip())
    else:
        print("  (launchd does not have %s loaded)" % LABEL)
    return 0


# ── selftest: the artifact proves its own ACCEPTANCE ──────────────────────────────────────────────
def _sh(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def _mkrepo(tmp, name, forge, commit=True):
    """A real git checkout with a real bare forge remote."""
    path = os.path.join(tmp, name)
    os.makedirs(path)
    bare = os.path.join(forge, name + ".git")
    _sh(["git", "init", "-q", "--bare", bare], tmp)
    _sh(["git", "init", "-q"], path)
    _sh(["git", "config", "user.email", "t@t"], path)
    _sh(["git", "config", "user.name", "t"], path)
    _sh(["git", "remote", "add", "forge", bare], path)
    open(os.path.join(path, "kept.txt"), "w").write("original\n")
    if commit:
        _sh(["git", "add", "-A"], path)
        _sh(["git", "commit", "-qm", "init"], path)
        _sh(["git", "push", "-q", "forge", "--all"], path)
    return path, bare


def cmd_selftest(a, cfg_unused, store_unused):
    """PROVE ticket #217's ACCEPTANCE, end to end, in a temp dir. Real git, a real bare forge, a
    temp db. Touches nothing outside its own tempdir and removes it."""
    import tempfile
    # realpath: on macOS /var is a symlink to /private/var, and every record this file emits is
    # keyed by realpath. Comparing a raw mkdtemp path against one would compare two spellings of
    # the same directory and call them different.
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="reaper-selftest-"))
    ok, fail = 0, 0

    def check(name, cond, detail=""):
        nonlocal ok, fail
        print("  %s  %s%s" % ("PASS" if cond else "FAIL", name, ("  — " + detail) if detail else ""))
        if cond:
            ok += 1
        else:
            fail += 1

    try:
        store = load_store()
        store.DB = os.path.join(tmp, "test.sqlite")     # HERMETIC: never the real db
        root = os.path.join(tmp, "code")
        forge = os.path.join(tmp, "forge")
        os.makedirs(root)
        os.makedirs(forge)

        idle, idle_bare = _mkrepo(root, "idle-app", forge)
        leased, _ = _mkrepo(root, "leased-app", forge)
        deployed, _ = _mkrepo(root, "deployed-app", forge)
        broken, _ = _mkrepo(root, "broken-remote-app", forge)

        # the acceptance's "uncommitted edits" — one NEW file and one MODIFIED tracked file
        open(os.path.join(idle, "work.txt"), "w").write("PRECIOUS UNCOMMITTED WORK\n")
        open(os.path.join(idle, "kept.txt"), "w").write("modified\n")
        open(os.path.join(broken, "work.txt"), "w").write("PRECIOUS UNCOMMITTED WORK\n")
        # point the broken tree's forge at a repo that does not exist -> push MUST fail
        _sh(["git", "remote", "set-url", "forge", os.path.join(tmp, "nonexistent.git")], broken)

        # the lease (#218 shape 1) and the deployed registry (#219, control-config shape)
        con = sqlite3.connect(store.DB)
        con.execute("CREATE TABLE checkout_leases (path TEXT, holder TEXT, ts INTEGER, ttl INTEGER)")
        con.execute("INSERT INTO checkout_leases VALUES (?,?,?,?)",
                    (leased, "agent-t218r1", int(time.time()), 900))
        con.execute("INSERT INTO checkout_leases VALUES (?,?,?,?)",     # a LAPSED lease: not live
                    (idle, "crashed-agent", int(time.time()) - 5000, 900))
        con.commit()
        con.close()

        cfg = dict(DEFAULTS)
        cfg.update({"roots": [root], "depth": 2, "remote": "forge", "worktrees_dir": "",
                    "deployed_apps": {deployed: {"name": "deployed-app", "kind": "app",
                                                 "deployed": True}}})

        con = open_db(store.DB)
        recs, sources = survey(cfg, con)
        con.close()
        by = {r["path"]: r for r in recs}

        print("\nCLASSIFY")
        check("an unleased, unregistered tree is IDLE",
              by.get(idle, {}).get("klass") == "IDLE", by.get(idle, {}).get("reason", "?"))
        check("a LAPSED lease does not protect (the dead-man's switch fired)",
              by.get(idle, {}).get("klass") == "IDLE")
        check("a live-leased tree is ACTIVE",
              by.get(leased, {}).get("klass") == "ACTIVE", by.get(leased, {}).get("reason", "?"))
        check("a registered deployed tree is DEPLOYED",
              by.get(deployed, {}).get("klass") == "DEPLOYED",
              by.get(deployed, {}).get("reason", "?"))
        check("a lease source is detected", sources["lease_sources"] == ["checkout_leases"])

        print("\nACCEPTANCE 1 — an idle checkout with uncommitted edits is committed + pushed + removed")
        res = reclaim(by[idle], cfg, store, log=lambda s: None)
        check("committed", res["committed"])
        check("pushed", res["pushed"])
        check("VERIFIED against the forge", res["verified"])
        check("tree removed", res["removed"] and not os.path.exists(idle))

        print("\nACCEPTANCE 1b — and it is RECOVERABLE from the forge (the bytes come back)")
        back = os.path.join(tmp, "recovered")
        r = _sh(["git", "clone", "-q", idle_bare, back], tmp)
        got = ""
        if os.path.isfile(os.path.join(back, "work.txt")):
            got = open(os.path.join(back, "work.txt")).read()
        check("the uncommitted file is in the forge clone", got == "PRECIOUS UNCOMMITTED WORK\n",
              "clone rc=%d, got %r" % (r.returncode, got))
        mod = ""
        if os.path.isfile(os.path.join(back, "kept.txt")):
            mod = open(os.path.join(back, "kept.txt")).read()
        check("the modified tracked file is in the forge clone", mod == "modified\n")
        log = _sh(["git", "log", "-1", "--format=%B"], back).stdout
        check("the reclaim commit carries reaper provenance",
              "Reaper-Ticket: #217" in log and "Reaper-Path:" in log and "reaper: reclaim" in log)

        print("\nACCEPTANCE 2 — an active-lease checkout and a deployed-app checkout are untouched")
        check("leased tree still on disk", os.path.isdir(leased))
        check("leased tree still has its original content",
              open(os.path.join(leased, "kept.txt")).read() == "original\n")
        check("deployed tree still on disk", os.path.isdir(deployed))
        check("deployed tree still has its original content",
              open(os.path.join(deployed, "kept.txt")).read() == "original\n")

        print("\nACCEPTANCE 3 — a push failure ABORTS the removal (work never lost)")
        rec_b = classify(broken, cfg, {}, {})
        check("the broken tree classifies IDLE (so a reclaim is attempted)",
              rec_b["klass"] == "IDLE", rec_b["reason"])
        res_b = reclaim(rec_b, cfg, store, log=lambda s: None)
        check("push failed", not res_b["pushed"] and res_b["error"])
        check("verify never claimed success", not res_b["verified"])
        check("REMOVAL ABORTED — tree still on disk", not res_b["removed"] and os.path.isdir(broken))
        check("the work survives, now committed locally",
              open(os.path.join(broken, "work.txt")).read() == "PRECIOUS UNCOMMITTED WORK\n")

        print("\nTHE ONE RULE — a push that SUCCEEDS but did not land is caught by THE VERIFY")
        # The scenario THE VERIFY exists for, reproduced honestly: the push returns success and the
        # forge does NOT have the refs. A post-receive hook deletes each ref right after it is
        # updated — post-receive runs AFTER the update and its exit code cannot fail the push, so
        # `git push` reports success against a remote that kept nothing. Only asking the remote
        # catches this; trusting (b)'s exit code would delete the tree.
        v, v_bare = _mkrepo(root, "verify-fail-app", forge)
        open(os.path.join(v, "work.txt"), "w").write("PRECIOUS UNCOMMITTED WORK\n")
        hook = os.path.join(v_bare, "hooks", "post-receive")
        os.makedirs(os.path.dirname(hook), exist_ok=True)
        with open(hook, "w") as fh:
            fh.write("#!/bin/sh\nwhile read old new ref; do git update-ref -d \"$ref\"; done\n")
        os.chmod(hook, 0o755)
        rec_v = classify(v, cfg, {}, {})
        res_v = reclaim(rec_v, cfg, store, log=lambda s: None)
        check("the push itself reported SUCCESS", res_v["pushed"],
              "if this fails the test proves nothing about verify")
        check("VERIFY caught that the forge does not have it", not res_v["verified"],
              res_v["error"] or "")
        check("REMOVAL ABORTED — tree still on disk", not res_v["removed"] and os.path.isdir(v))
        check("the work survives", open(os.path.join(v, "work.txt")).read()
              == "PRECIOUS UNCOMMITTED WORK\n")

        print("\nTHE PROTECTED SET")
        cfg_p = dict(cfg)
        cfg_p["worktrees_dir"] = os.path.join(root, "leased-app")
        check("a pair worktree dir is PROTECTED, not reaped",
              classify(leased, cfg_p, {}, {})["klass"] == "PROTECTED")
        check("a configured root itself is PROTECTED", protected_reason(root, cfg) is not None)
        check("$HOME is PROTECTED",
              protected_reason(os.path.realpath(os.path.expanduser("~")), cfg) is not None)
        check("a path outside every root is PROTECTED", protected_reason("/etc", cfg) is not None)
        check("/ is PROTECTED", protected_reason("/", cfg) is not None)

        # BOTH DIRECTIONS — the real hole this found on this host: a git repo that CONTAINS the
        # pair worktrees (or this repo) must never be reaped, or one rmtree takes everything.
        parent = os.path.join(tmp, "parent-repo")
        os.makedirs(os.path.join(parent, "congruency-pair-worktrees", "ticket-999"))
        cfg_c = dict(cfg, roots=[tmp],
                     worktrees_dir=os.path.join(parent, "congruency-pair-worktrees"))
        check("a tree CONTAINING the pair worktrees is PROTECTED",
              protected_reason(parent, cfg_c) is not None, protected_reason(parent, cfg_c) or "")
        check("a tree CONTAINING this repository is PROTECTED",
              protected_reason(os.path.dirname(os.path.realpath(ROOT)),
                               dict(cfg, roots=["/"])) is not None)
        check("the removal guard independently refuses a containing tree",
              removal_guard(parent, cfg_c) is not None)

        print("\nTHE SAFETY GATE — no lease source ⇒ reap REFUSES (exit 4)")
        store2 = load_store()
        store2.DB = os.path.join(tmp, "empty.sqlite")
        sqlite3.connect(store2.DB).close()       # a db with NO lease table at all
        survivor, _ = _mkrepo(root, "gate-app", forge)
        args = argparse.Namespace(json=False, dry_run=False, force_unleased=False)
        rc = cmd_reap(args, dict(cfg, roots=[root]), store2)
        check("exit 4 (REFUSED)", rc == 4)
        check("nothing was reclaimed under the gate", os.path.isdir(survivor))

        print("\nSIGNALS — the DB error channel got one per reclaim")
        sigs = {s["code"] for s in store.signals(status="open")}
        check("a %s signal was written" % SIG_RECLAIMED, SIG_RECLAIMED in sigs)
        check("a %s signal was written" % SIG_PUSH_FAILED, SIG_PUSH_FAILED in sigs)
        check("a %s signal was written" % SIG_VERIFY_FAILED, SIG_VERIFY_FAILED in sigs)
        rec_sig = [s for s in store.signals(status="open") if s["code"] == SIG_RECLAIMED]
        check("the reclaim signal names the tree it took", bool(rec_sig) and rec_sig[0]["ref"] == idle)

        print("\nTHE DEAD-MAN'S SWITCH — the reaper is itself a watched component")
        store.beat(AGENT, 3600)
        con = sqlite3.connect(store.DB)
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM heartbeat WHERE component=?", (AGENT,)).fetchone()
        con.close()
        check("the reaper beats its own heartbeat", row is not None and row["state"] == "ok")

        print("\nHEARTBEAT-SHAPED LEASES (#218 contract, shape 2)")
        store3 = load_store()
        store3.DB = os.path.join(tmp, "hb.sqlite")
        hb, _ = _mkrepo(root, "hb-app", forge)
        con = sqlite3.connect(store3.DB)
        con.execute("CREATE TABLE heartbeat (component TEXT PRIMARY KEY, last_seen TEXT, "
                    "ttl INTEGER, state TEXT)")
        con.execute("INSERT INTO heartbeat VALUES (?,?,?,'ok')",
                    ("checkout:" + hb, time.strftime("%Y-%m-%dT%H:%M:%S"), 900))
        con.execute("INSERT INTO heartbeat VALUES ('ticket_reader',?,60,'ok')",
                    (time.strftime("%Y-%m-%dT%H:%M:%S"),))
        con.commit()
        con.close()
        con = open_db(store3.DB)
        lv = live_leases(con, fallback_ttl=900)
        srcs3 = lease_sources(con)
        con.close()
        check("a checkout: heartbeat row IS a live lease", os.path.realpath(hb) in lv)
        check("a real component row is NOT read as a lease",
              not any("ticket_reader" in k for k in lv))
        check("a checkout: row DOES arm the gate", srcs3 == ["heartbeat"], str(srcs3))

        print("\nTHE GATE DOES NOT DISARM ITSELF (the trap lease_sources() exists for)")
        store4 = load_store()
        store4.DB = os.path.join(tmp, "beat-only.sqlite")
        store4.beat(AGENT, 3600)                 # the reaper's own beat CREATES `heartbeat`
        con = open_db(store4.DB)
        check("the reaper's own beat created the heartbeat table", _table_exists(con, "heartbeat"))
        check("...and it still does NOT count as a lease source", lease_sources(con) == [],
              str(lease_sources(con)))
        con.close()
        survivor2, _ = _mkrepo(root, "gate-app-2", forge)
        args = argparse.Namespace(json=False, dry_run=False, force_unleased=False)
        rc = cmd_reap(args, dict(cfg, roots=[root]), store4)
        check("a beaten-but-leaseless db STILL refuses (exit 4)", rc == 4)
        check("nothing was reclaimed", os.path.isdir(survivor2))
        # the reaper's own component name must never be mistaken for a lease on a path
        con = open_db(store4.DB)
        check("the reaper's own heartbeat is not read as a lease", live_leases(con) == {})
        con.close()

        print("\n%d passed, %d failed" % (ok, fail))
        return 0 if fail == 0 else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── main ──────────────────────────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="checkout_reaper.py",
        description="The checkout REAPER (ticket #217): scan checkout roots, classify every tree, "
                    "and reclaim the idle ones commit -> push -> VERIFY -> remove. A tree is NEVER "
                    "removed without a push the forge itself confirmed.",
        epilog="`scan` (the default) changes nothing. `reap` REFUSES to remove anything while no "
               "lease source exists (ticket #218 has not landed) — run `selftest` to see all of "
               "ticket #217's acceptance criteria proven end-to-end in a temp dir.")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("scan", help="classify every checkout and report; changes NOTHING (default)")
    p.add_argument("--json", action="store_true", help="machine-readable")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("reap", help="reclaim every IDLE checkout: commit -> push -> VERIFY -> remove")
    p.add_argument("--dry-run", action="store_true", help="name what would be reclaimed; do nothing")
    p.add_argument("--force-unleased", action="store_true",
                   help="DANGEROUS: reap even though no lease source exists, i.e. even though an "
                        "agent has no way to protect the tree it is working in")
    p.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_reap)

    p = sub.add_parser("run", help="ONE durable cycle (what the LaunchAgent invokes): lock, reap, beat")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force-unleased", action="store_true")
    p.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("watch", help="the cycle on a foreground loop (a cron/systemd-less runner)")
    p.add_argument("--interval", type=int, default=900, help="seconds between cycles [900]")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force-unleased", action="store_true")
    p.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_watch)

    p = sub.add_parser("install", help="register the LaunchAgent — the durable service")
    p.set_defaults(fn=lambda a, c, s: install(c))
    p = sub.add_parser("uninstall", help="remove the LaunchAgent")
    p.set_defaults(fn=lambda a, c, s: uninstall())
    p = sub.add_parser("status", help="the LaunchAgent, the lease sources, and this daemon's beat")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("selftest", help="prove ticket #217's ACCEPTANCE end-to-end in a temp dir")
    p.set_defaults(fn=cmd_selftest)

    a = ap.parse_args(argv)
    if not a.cmd:
        a = ap.parse_args(["scan"] + (argv or []))

    try:
        store = load_store()
        cfg = config()
        return a.fn(a, cfg, store)
    except Fault as e:
        print("checkout_reaper: %s" % e, file=sys.stderr)   # one line, never a traceback
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
