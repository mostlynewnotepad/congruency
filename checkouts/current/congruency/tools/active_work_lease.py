#!/usr/bin/env python3
"""active_work_lease.py — the heartbeat that holds the reaper off a checkout an agent is working in.

An agent (or a human) actively working a CHECKOUT acquires a LEASE and renews it while working. The
REAPER treats a checkout as ACTIVE only while its lease is LIVE; when the lease LAPSES (no renewal
within its ttl) the DEAD-MAN'S SWITCH fires and the reaper RECLAIMS the checkout: commit -> push ->
remove. A crashed agent renews nothing, so its checkout is reclaimed automatically — no human ever
has to sweep up after a process that died (ticket #218).

TERMS, each defined at first use, because whoever reads this file did not watch it being written:

  * A CHECKOUT is a working directory driven by this repo's git: a `git worktree`. pair_loop.py opens
    one per ticket under the registry's `branch_per_ticket.worktrees` directory (registry.json; read
    by pair_loop.forge_for(), pair_loop.py:596-599) and reaps it on a successful merge
    (pair_loop.reap_worktree(), pair_loop.py:585-594).
  * THE MAIN WORKING TREE is the checkout the repo was cloned into; every other one is a LINKED
    worktree driven by the same shared .git. It is never a candidate here — and note it is NOT
    simply "the directory this tool was pointed at", which is the assumption THE SAFETY RULES exists
    to kill.
  * A LEASE is a heartbeat record — (path, holder, ts, ttl) — asserting "an agent is working in this
    checkout right now". `path` is the checkout, `holder` names who holds it (an agent id), `ts` is
    the last renewal, `ttl` is how many seconds a renewal is good for.
  * A lease is LIVE while `now - ts <= ttl`, and LAPSED once `now - ts > ttl`. LIVE is the only state
    that means ACTIVE. A checkout with NO lease row at all is NOT active — see FAIL-SAFE.
  * THE DEAD-MAN'S SWITCH is the fail-safe: silence means dead. It FIRES on a lapse — the lease's
    state flips to 'error' and an error signal is filed on the signals table — and firing is what
    makes the checkout reapable.
  * To RECLAIM a checkout is to commit -> push -> remove it. Reclaim never erases work; see PRESERVE
    FIRST, which is the most safety-critical paragraph in this file.

THE TTL IS ACCURATE TO ±1 SECOND, AND THAT IS ON PURPOSE. `ts` is stored at SECOND resolution,
because it is store.py's format (store.py:66-67) and sharing that spelling is the point of the mirror.
Writing a lease at 12:00:00.9 stores "12:00:00", so its measured age runs up to 1s AHEAD of its true
age and a lease LAPSES anywhere in [ttl-1, ttl] seconds after its last renewal. The error only ever
makes a lease look OLDER than it is, never younger — it can retire a live lease a second early, never
keep a dead one alive a second late, which is the direction a fail-safe must round. Two consequences
you must not design around: never set a ttl of 1 or 2 (a third of it is noise), and never renew at
the ttl — `hold` beats every ttl/3 so two whole beats can be lost before anything lapses.

WHAT THIS MIRRORS. tracker/store.py's dead-man's switch, deliberately and line for line where it can:

    store.py                                    this file
    heartbeat(component, last_seen, ttl, state) active_work_lease(path, holder, ts, ttl, state)
    beat(component, ttl=60)                     acquire()/renew() — same UPSERT, same state='ok'
    check_deadman()                             check_deadman() — same age math, same fire-once guard
    raise_signal('error', 'deadman', ...)       raise_signal('error', 'active_work_lease', ...)

The mirror is exact where it matters: the timestamp format is store.py's `%Y-%m-%dT%H:%M:%S` LOCAL
time (store.py:66-67), and a lease's age is `time.time() - time.mktime(time.strptime(ts, ...))`,
which is store.py:127 verbatim. check_deadman() fires ONCE per lapse (`state != 'error'`, store.py:128)
so a repeated sweep does not re-file the same signal. Sharing store.py's timestamp spelling is what
lets both layers live in one db and be read by one pair of eyes.

WHY A SEPARATE TABLE, IN STORE.PY'S DB. The lease is durable OPERATIONAL state: it is not rebuildable
from the ledger, so it belongs in the install-level db that survives a repo re-clone — store.py makes
exactly that argument for `heartbeat` (store.py:5-9), and this file resolves the SAME db by the SAME
precedence ($PROJECT_DB > $JAZZ_DB > ~/.jazz/congruency.sqlite, store.py:34-43). It does NOT reuse
store.py's `heartbeat` table: that table is keyed by `component` and is store.py's own, and store.py
warns in its schema that recreating another layer's table in this db collides with it (store.py:50-52).
So this layer owns `active_work_lease` and touches no other table but `signals`, whose DDL here is
store.py's own, character for character, under CREATE TABLE IF NOT EXISTS — so whichever layer runs
first creates it and the other finds it already there. Firing on store.py's signals table is what
makes a lapse visible to `store.py signals --level error`, the repo's existing error channel.

FAIL-SAFE — a checkout with no lease is NOT active. store.py's switch DEFAULTS to error and the
component must beat to hold it back ("Silence == failure", store.py:20-21). The same direction holds
here, and the ticket states it as the rule: a checkout is active ONLY while its lease is live. So a
checkout whose agent never took a lease is reapable. That is safe ONLY because reclaim preserves —
read on.

PRESERVE FIRST — how reclaim obeys "produce, don't erase". This repo's governance is append-only
("History is append-only: never delete or rewrite anything that exists; produce, don't erase",
pair_loop.py:604-605). A reaper that deleted an abandoned checkout would destroy uncommitted work, so
this one never deletes before it has preserved. Reclaim is three ordered steps and the order is the
guarantee:

    1. COMMIT  `git add -A` + commit, IN the checkout, on whatever branch it is on. Everything the
               agent left becomes a real commit. Nothing is staged selectively — see WHY add -A.
    2. PUSH    `git push <remote> HEAD:refs/heads/<branch>`, so the work leaves this machine.
    3. REMOVE  `git worktree remove --force` + `git worktree prune` — the same two calls
               pair_loop.reap_worktree() makes (pair_loop.py:585-594).

Removing a worktree does NOT delete its branch: pair_loop keeps the branch as the ticket's trace
("the BRANCH is kept as the ticket's trace", pair_loop.py:584) and so does this. That is why step 3
is safe even when step 2 fails: the commit from step 1 is on a branch in the shared object store, a
ref that `git gc` will never reclaim. A push failure is REPORTED and reclaim continues — refusing to
remove would leave a dead agent's checkout on disk forever, which is the thing this ticket exists to
prevent. But a commit reachable from NO ref would be a dangling object git may collect, so when a
checkout is on a DETACHED HEAD (no branch to hold the commit) reclaim first writes the commit to a
permanent rescue ref, `refs/active-work-lease/reclaimed/<stamp>`, and only then removes. This mirrors
clean_recheckout.py's drift-preservation, which parks discarded drift under `refs/policy1/drift/<stamp>`
"a ref, not a dangling object, so `git gc` will never reclaim it" (clean_recheckout.py:72-73).

WHY add -A, when pair_loop refuses to. pair_loop.commit_deliverable() never runs `add -A` on purpose:
"the scope is bounded either way, because the worker's mandate is bounded either way"
(pair_loop.py:463). That is a rule about a WORKER's deliverable — a bounded mandate deserves a bounded
commit. Reclaim is the opposite job: the agent is gone and nobody will ever say which of its files
mattered, so the only safe scope is all of them. `add -A` does NOT add ignored files (that needs -f,
which this file never passes), which keeps reclaim consistent with clean_recheckout.py's IGNORED-FILE
RULE: .gitignore is the repo's own declaration that a path is not part of any commit
(clean_recheckout.py:78-85).

THE SAFETY RULES — what the reaper will never touch:
  * The MAIN WORKING TREE is never a candidate, whatever its lease says — and it is identified by
    ASKING GIT (Git.main_worktree()), never assumed to be the root this tool was pointed at. Run the
    reaper from inside a pair worktree and `--root` IS that worktree; the main tree is then just
    another entry in `git worktree list` and a guard that only protected the root would hand it a
    commit -> push it never asked for. `git worktree remove` refuses the main tree by itself, but it
    refuses at step 3 — after the commit and the push have already happened — so the refusal is made
    here, before step 1, where it still prevents something.
  * The root the reaper was pointed at is never a candidate either.
  * A checkout the reaper is itself running inside is never a candidate (it would saw off its branch).
  * A directory that is not a REGISTERED worktree is never removed. `git worktree remove` is the only
    removal this file performs; there is no rmtree in it. An unregistered directory is reported, not
    erased.
  * Reaping is DRY-RUN BY DEFAULT and reclaims nothing without --apply — the same reason
    clean_recheckout.py's default is its guard and not its enforcement (clean_recheckout.py:48-52).
    The dry run writes NOTHING AT ALL: it does not even fire the switch, it only reports which leases
    would fire it. --selftest proves that by hashing the db before and after one.

ADOPTION — READ THIS BEFORE YOU EVER TYPE --apply ON A REAL REPO. Nothing in this repository takes a
lease yet. This file is the lease layer itself (ticket #218); it is not wired into pair_loop.py, and
pair_loop.open_worktree() (pair_loop.py:430-453) acquires nothing. So TODAY every pair worktree on
this machine has no lease row, and under the ticket's rule as written — active ONLY while a lease is
live — the reaper's default reads all of them as reclaimable. A `reap --apply` right now would commit,
push and remove the checkouts of pairs that are alive and working in them. That is why:

  * the reaper is DRY-RUN BY DEFAULT and --apply is a deliberate act;
  * `--unleased skip` exists, and is the correct setting until the agents that OPEN checkouts also
    take leases. It reclaims lapsed and released leases — the dead-man's switch, the thing this
    ticket is for — while leaving never-enrolled checkouts alone;
  * the honest sequence is: teach the checkout-openers to `acquire` and the workers to `hold` FIRST,
    confirm `leases` lists them, and only then let the reaper --apply with the default.

Wiring pair_loop to it is not this ticket's deliverable and is deliberately not done here (#218
authorizes this file and nothing else). The two-line shape it would take: acquire in open_worktree()
after the worktree exists, release in reap_worktree() after it is gone.

Usage — the agent's side (hold the lease while working):
    python3 active_work_lease.py acquire <checkout> --holder agent-7 [--ttl 60] [--steal]
    python3 active_work_lease.py renew   <checkout> --holder agent-7
    python3 active_work_lease.py release <checkout> --holder agent-7
    python3 active_work_lease.py hold    <checkout> --holder agent-7 [--ttl 60] [--every N]

`hold` is the whole protocol in one foreground command: it acquires, then renews every --every
seconds until you stop it, and releases on a clean exit (SIGINT/SIGTERM). If the process is KILLED
(SIGKILL, a panic, a yanked power cord) it releases nothing — the lease lapses on its own and the
reaper reclaims. That is the dead-man's switch working as designed, and --selftest proves it by
SIGKILLing a real `hold` subprocess.

Usage — the reaper's side:
    python3 active_work_lease.py leases [--json]     # every lease, live or lapsed
    python3 active_work_lease.py check               # fire the dead-man's switch for lapsed leases
    python3 active_work_lease.py reap [--remote origin]          # DRY RUN: says what it would do
    python3 active_work_lease.py reap --apply [--remote origin]  # actually commit -> push -> remove
    python3 active_work_lease.py reap --apply --unleased skip    # ADOPTION: lapsed leases only
    python3 active_work_lease.py --selftest          # prove all of it in a THROWAWAY repo + db

--db PATH overrides the db for any command ($PROJECT_DB / $JAZZ_DB also work, store.py's precedence).
--selftest touches neither the real db nor this repo: it builds its own temp repo, a `file://` bare
remote and a temp db, and removes them when it is done. Exit 0 if every check passed, 1 if any failed.
Errors are one-line messages, never a traceback; exit 2 for a usage/precondition failure.
"""
import argparse
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time


# ── the db: store.py's, resolved store.py's way (store.py:34-43) ──────────────────────────────────
def default_db():
    """The db store.py uses: $PROJECT_DB > $JAZZ_DB > ~/.jazz/congruency.sqlite (store.py:34-43).

    The lease lives beside store.py's heartbeat for store.py's own stated reason: it is durable
    operational state that is NOT rebuildable from the ledger, so it must survive a repo re-clone
    (store.py:5-9). It is emphatically not the pair-loop STATE db
    (checkouts/current/state/congruency.sqlite, ticket_status.py:46) — that one is untracked and so
    is absent from every pair worktree, which is exactly the wrong place for a reaper's memory.
    """
    env = os.environ.get("PROJECT_DB") or os.environ.get("JAZZ_DB")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(os.path.expanduser("~"), ".jazz", "congruency.sqlite")


# `signals` is store.py's DDL verbatim (store.py:53-55) under IF NOT EXISTS: whichever layer opens
# the db first creates it, the other finds it. `active_work_lease` is this layer's own — store.py's
# `heartbeat` is keyed by component and belongs to store.py; recreating another layer's table in this
# shared db is the collision store.py warns about (store.py:50-52).
SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, level TEXT, source TEXT,
    code TEXT, message TEXT, ref TEXT, status TEXT DEFAULT 'open');
CREATE TABLE IF NOT EXISTS active_work_lease (
    path TEXT PRIMARY KEY, holder TEXT, ts TEXT, ttl INTEGER, state TEXT);
"""

SOURCE = "active_work_lease"


def _now():
    """store.py:66-67 verbatim — LOCAL time, second resolution, no zone suffix. Shared spelling is
    what lets a human read both layers' timestamps in one db without converting."""
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _con(db):
    con = sqlite3.connect(db, timeout=5)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _open(db=None):
    """Resolve the db, make sure its directory exists, and connect."""
    db = db or default_db()
    d = os.path.dirname(db)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)   # a first run on a fresh install has no ~/.jazz yet
    return _con(db)


def key(path):
    """The lease's primary key: the checkout's REAL path.

    realpath, not abspath: on macOS /var is a symlink to /private/var, so `git worktree list` reports
    the resolved path while tempfile hands back the unresolved one. Keying on the raw string would
    file two leases for one checkout and the reaper would honour neither. pair_loop's own selftest
    hits this and resolves both sides for the same reason (pair_loop.py:1095-1097).
    """
    return os.path.realpath(os.path.expanduser(path))


def age_of(ts):
    """Seconds since `ts`. store.py:127's arithmetic verbatim.

    A malformed/unparseable ts returns +inf — LAPSED. Fail-safe: an unreadable heartbeat is not a
    live one, and it must never crash the sweep (store.py's switch defaults to error, store.py:20-21).
    """
    try:
        return time.time() - time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return float("inf")


# ── signals — store.py's error channel, store.py:80-86 ────────────────────────────────────────────
def raise_signal(level, code, message="", ref="", db=None):
    con = _open(db)
    con.execute("INSERT INTO signals (ts, level, source, code, message, ref, status) "
                "VALUES (?,?,?,?,?,?, 'open')",
                (_now(), level, SOURCE, code, str(message)[:500], str(ref)))
    con.commit()
    con.close()


# ── the lease: acquire / renew / release / read ───────────────────────────────────────────────────
def lease_of(path, db=None):
    """The lease row for `path` as a dict with `age`/`live` computed, or None if there is none."""
    con = _open(db)
    r = con.execute("SELECT * FROM active_work_lease WHERE path=?", (key(path),)).fetchone()
    con.close()
    return _decorate(r) if r else None


def _decorate(r):
    d = dict(r)
    d["age"] = age_of(d["ts"])
    d["live"] = d["age"] <= d["ttl"]
    return d


def leases(db=None):
    """Every lease, newest renewal first, each with `age`/`live` computed."""
    con = _open(db)
    rows = [_decorate(r) for r in con.execute("SELECT * FROM active_work_lease ORDER BY ts DESC")]
    con.close()
    return rows


def is_active(path, db=None):
    """The reaper's one question: is an agent working here RIGHT NOW?

    True only while a lease is LIVE. No lease, a lapsed lease, or a released lease all answer False —
    the fail-safe direction (see FAIL-SAFE in the module docstring).
    """
    lz = lease_of(path, db)
    return bool(lz and lz["live"] and lz["state"] != "released")


def acquire(path, holder, ttl=60, steal=False, db=None):
    """Take the lease on `path` for `holder`. The UPSERT is store.py's beat() (store.py:112-119).

    Refuses if a LIVE lease is held by a DIFFERENT holder — that refusal is the only thing separating
    a lease from a shared flag. A LAPSED lease is takeable by anyone: that is what a ttl is for, and
    it is how a crashed agent's checkout becomes someone else's to finish. --steal overrides a live
    lease and is recorded as a warn signal, so a stolen lease is never silent.
    """
    p, ttl = key(path), int(ttl)
    if ttl < 0:
        raise ValueError("ttl must be >= 0 seconds, got %r" % ttl)
    cur = lease_of(p, db)
    if cur and cur["live"] and cur["state"] != "released" and cur["holder"] != holder and not steal:
        return {"ok": False, "path": p, "held_by": cur["holder"],
                "reason": "a LIVE lease on %s is held by %r (renewed %.0fs ago, ttl %ds) — refusing to "
                          "take it from them; wait for it to lapse or pass --steal"
                          % (p, cur["holder"], cur["age"], cur["ttl"])}
    stolen = bool(cur and cur["live"] and cur["state"] != "released" and cur["holder"] != holder)
    con = _open(db)
    con.execute("INSERT INTO active_work_lease (path, holder, ts, ttl, state) VALUES (?,?,?,?, 'ok') "
                "ON CONFLICT(path) DO UPDATE SET holder=excluded.holder, ts=excluded.ts, "
                "ttl=excluded.ttl, state='ok'", (p, holder, _now(), ttl))
    con.commit()
    con.close()
    if stolen:
        raise_signal("warn", "LEASE_STOLEN",
                     "%r took a LIVE lease on %s from %r (--steal)" % (holder, p, cur["holder"]),
                     ref=p, db=db)
    return {"ok": True, "path": p, "holder": holder, "ttl": ttl, "stolen": stolen,
            "took_over_from": cur["holder"] if (cur and cur["holder"] != holder) else None}


def renew(path, holder, ttl=None, db=None):
    """Renew `holder`'s lease — the beat that holds the reaper off.

    Refuses to renew a lease that does not exist or that someone else holds: renewing another agent's
    lease would tell the reaper a lie about who is working. Renewing an already-LAPSED lease succeeds
    and clears the fired switch back to 'ok' (the reaper may not have swept yet), and the result says
    `was_lapsed: True` so a caller that cares can see it came back from the dead.
    """
    p = key(path)
    cur = lease_of(p, db)
    if not cur:
        return {"ok": False, "path": p, "reason": "no lease on %s to renew — acquire it first" % p}
    if cur["holder"] != holder:
        return {"ok": False, "path": p, "held_by": cur["holder"],
                "reason": "the lease on %s is held by %r, not %r — refusing to renew someone else's "
                          "lease" % (p, cur["holder"], holder)}
    t = cur["ttl"] if ttl is None else int(ttl)
    con = _open(db)
    con.execute("UPDATE active_work_lease SET ts=?, ttl=?, state='ok' WHERE path=?", (_now(), t, p))
    con.commit()
    con.close()
    return {"ok": True, "path": p, "holder": holder, "ttl": t,
            "was_lapsed": not cur["live"], "was_state": cur["state"]}


def release(path, holder, db=None):
    """Hand the checkout back: state='released', so the reaper may reclaim it immediately.

    The row is UPDATED, never deleted — the record of who held it and when they let go survives, and
    a released lease is simply not a live one.
    """
    p = key(path)
    cur = lease_of(p, db)
    if not cur:
        return {"ok": False, "path": p, "reason": "no lease on %s to release" % p}
    if cur["holder"] != holder:
        return {"ok": False, "path": p, "held_by": cur["holder"],
                "reason": "the lease on %s is held by %r, not %r — refusing to release someone else's "
                          "lease" % (p, cur["holder"], holder)}
    con = _open(db)
    con.execute("UPDATE active_work_lease SET ts=?, state='released' WHERE path=?", (_now(), p))
    con.commit()
    con.close()
    return {"ok": True, "path": p, "holder": holder}


# ── the dead-man's switch — store.py:122-136, mirrored ────────────────────────────────────────────
def check_deadman(db=None):
    """Fire the switch for every lease that LAPSED: state -> 'error', one error signal each.

    store.py:122-136 mirrored: the same `age > ttl` test, the same `state != 'error'` guard so the
    switch fires ONCE per lapse rather than re-filing a signal on every sweep, and the same shape of
    return (the list of what fired). A 'released' lease is not a lapse — its holder said goodbye, so
    there is nothing dead to switch on — it is simply not active.

    Returns the list of lapsed lease dicts.
    """
    con = _open(db)
    stale = []
    for r in con.execute("SELECT * FROM active_work_lease").fetchall():
        d = _decorate(r)
        if not d["live"] and d["state"] not in ("error", "released"):
            con.execute("UPDATE active_work_lease SET state='error' WHERE path=?", (d["path"],))
            stale.append(d)
    con.commit()
    con.close()
    for d in stale:
        raise_signal("error", "LEASE_LAPSED",
                     "lease on %s held by %r stopped being renewed %.0fs ago (ttl %ds) — dead-man's "
                     "switch fired; the checkout is reapable"
                     % (d["path"], d["holder"], d["age"], d["ttl"]), ref=d["path"], db=db)
    return stale


# ── git, scoped to one repo so --selftest can drive a throwaway (mirrors pair_loop.Forge) ─────────
class Git:
    """The git this file performs, against one repo root. Mirrors pair_loop.Forge's plumbing
    (pair_loop.py:301-317): git() raises on failure, git_ok() returns (ok, output) for the paths
    where a failure is an OUTCOME (a rejected push) rather than a fault."""

    def __init__(self, root):
        self.root = os.path.abspath(root)

    def _run(self, args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True, text=True)

    def git(self, *args, cwd=None):
        r = self._run(list(args), cwd)
        if r.returncode != 0:
            raise RuntimeError("git %s failed (exit %s): %s"
                               % (" ".join(args[:3]), r.returncode, (r.stderr or r.stdout).strip()[-300:]))
        return r.stdout

    def git_ok(self, *args, cwd=None):
        r = self._run(list(args), cwd)
        return r.returncode == 0, (r.stdout + r.stderr).strip()

    def registered_worktrees(self):
        """`git worktree list --porcelain` parsed into [{path, branch}] (branch '' if detached).
        pair_loop.registered_worktrees() (pair_loop.py:419-428), with path realpath'd to match key()."""
        out, cur, res = self.git("worktree", "list", "--porcelain"), {}, []
        for line in out.splitlines():
            if line.startswith("worktree "):
                cur = {"path": os.path.realpath(line[9:]), "branch": ""}
                res.append(cur)
            elif line.startswith("branch ") and cur:
                cur["branch"] = line[7:].replace("refs/heads/", "", 1)
        return res

    def main_worktree(self):
        """The repo's MAIN working tree — the one `git worktree remove` itself refuses to remove.

        This is NOT `self.root`: run this tool from inside a linked worktree (a pair worktree is one)
        and root IS that worktree, while the main tree is somewhere else entirely and shows up in the
        sweep as just another candidate. Protecting only root would leave the real main tree exposed
        to a commit -> push it never asked for.

        Asked of git two independent ways, and they must agree:
          * `git rev-parse --git-common-dir` is the SHARED .git every worktree is driven by; its
            parent is the main tree. (It can come back relative — ".git" — when cwd is the main tree,
            so it is resolved against root.)
          * `git worktree list --porcelain` documents the main tree as the FIRST entry.
        If the two ever disagree, both are protected: over-protecting a checkout costs a stray
        directory, under-protecting one costs the user's working tree.
        """
        common = self.git("rev-parse", "--git-common-dir").strip()
        if not os.path.isabs(common):
            common = os.path.join(self.root, common)
        by_common = os.path.realpath(os.path.dirname(os.path.abspath(common)))
        listed = self.registered_worktrees()
        by_order = listed[0]["path"] if listed else by_common
        return {by_common, by_order}

    def remotes(self):
        return [r for r in self.git("remote").split() if r]

    def dirty(self, cwd):
        """Every path git would commit: tracked modifications AND untracked files, `-z` so a path
        holding a space or a non-ascii byte is emitted verbatim rather than C-quoted (the reason
        pair_loop.porcelain() takes -z, pair_loop.py:355-368). Ignored files never appear: that
        needs --ignored, which is not passed."""
        raw = self.git("status", "--porcelain", "-z", "-uall", cwd=cwd).split("\0")
        out, i = [], 0
        while i < len(raw):
            e = raw[i]
            i += 1
            if not e:
                continue
            if "R" in e[:2] or "C" in e[:2]:
                i += 1          # drop the rename/copy source field that follows
            out.append(e[3:])
        return out


# ── reclaim: commit -> push -> remove ─────────────────────────────────────────────────────────────
def reclaim(g, path, remote="origin", message=None):
    """Reclaim ONE checkout: commit -> push -> remove, in that order, preserving before removing.

    Returns a dict reporting each step. Never raises for an expected outcome (nothing to commit, no
    remote, a rejected push) — those are reported and the reclaim continues, because leaving a dead
    agent's checkout on disk is the failure this exists to prevent. See PRESERVE FIRST in the module
    docstring for why removing after a failed push still loses nothing.
    """
    p = key(path)
    res = {"path": p, "committed": False, "pushed": False, "removed": False,
           "sha": None, "branch": None, "ref": None, "files": [], "notes": []}

    wts = {w["path"]: w for w in g.registered_worktrees()}
    if p not in wts:
        res["notes"].append("not a registered git worktree of %s — refusing to remove a directory "
                            "git does not know about (nothing is erased by hand here)" % g.root)
        return res
    # The protected checkouts are refused HERE, before step 1, and not left to `git worktree remove`
    # to reject at step 3: by then the commit and the PUSH would already have happened, which is a
    # side effect on somebody's working tree that no lease ever authorized. Refuse before acting.
    if p in g.main_worktree() or p == os.path.realpath(g.root):
        res["notes"].append("this is a PROTECTED checkout (the repo's main working tree, or the root "
                            "this reaper was pointed at) — never reclaimed, whatever its lease says")
        return res

    branch = wts[p]["branch"] or None
    res["branch"] = branch

    # 1. COMMIT — everything the departed agent left. add -A, never -f: ignored files stay ignored.
    files = g.dirty(p)
    if files:
        res["files"] = files
        ok, out = g.git_ok("add", "-A", cwd=p)
        if not ok:
            res["notes"].append("git add -A failed: %s" % out[-200:])
        else:
            msg = message or ("active_work_lease: reclaimed abandoned checkout %s (lease lapsed; "
                              "dead-man's switch fired)" % os.path.basename(p))
            ok, out = g.git_ok("commit", "--quiet", "-m", msg, cwd=p)
            if ok:
                res["committed"] = True
                res["sha"] = g.git("rev-parse", "HEAD", cwd=p).strip()
            else:
                res["notes"].append("git commit failed: %s" % out[-200:])
    else:
        res["notes"].append("nothing uncommitted to preserve (the checkout was already clean)")
        res["sha"] = g.git("rev-parse", "HEAD", cwd=p).strip()

    # A commit on no branch is a dangling object git may collect. Give it a permanent ref BEFORE the
    # worktree goes, exactly as clean_recheckout.py parks drift (clean_recheckout.py:72-73).
    if branch is None and res["sha"]:
        ref = "refs/active-work-lease/reclaimed/%s-%s" % (os.path.basename(p), time.strftime("%Y%m%d-%H%M%S"))
        ok, out = g.git_ok("update-ref", ref, res["sha"])
        if ok:
            res["ref"] = ref
            res["notes"].append("DETACHED HEAD: the commit is held by the permanent ref %s (git gc "
                                "will never reclaim it); recover it with `git checkout %s`" % (ref, ref))
        else:
            res["notes"].append("DETACHED HEAD and update-ref failed (%s) — REFUSING to remove: the "
                                "commit would be unreachable" % out[-200:])
            return res

    # 2. PUSH — get the work off this machine. A failure here is reported, not fatal (step 1 already
    #    preserved it on a local ref that survives the removal).
    if remote is None:
        res["notes"].append("push skipped: --remote none")
    elif remote not in g.remotes():
        res["notes"].append("push skipped: no remote named %r in %s (remotes: %s). The work is safe "
                            "on the local ref above." % (remote, g.root, ", ".join(g.remotes()) or "none"))
    elif not res["sha"]:
        res["notes"].append("push skipped: nothing to push")
    else:
        target = "refs/heads/%s" % branch if branch else res["ref"]
        ok, out = g.git_ok("push", remote, "%s:%s" % (res["sha"], target), cwd=p)
        res["pushed"] = ok
        if not ok:
            res["notes"].append("push to %r REJECTED (%s) — reclaiming anyway; the work is preserved "
                                "on %s in this repo" % (remote, out.splitlines()[-1][:160] if out else "?",
                                                        branch or res["ref"]))

    # 3. REMOVE — pair_loop.reap_worktree()'s two calls (pair_loop.py:585-594). --force because an
    #    ignored file (a venv, a .env) would otherwise refuse; ignored files are regenerable by
    #    declaration (clean_recheckout.py's IGNORED-FILE RULE) and were never in scope to commit.
    ok, out = g.git_ok("worktree", "remove", "--force", p)
    g.git_ok("worktree", "prune")
    res["removed"] = not os.path.exists(p)
    if not res["removed"]:
        res["notes"].append("worktree remove failed: %s" % out[-200:])
    return res


# ── the reaper ────────────────────────────────────────────────────────────────────────────────────
def reap(root, remote="origin", apply=False, db=None, only=None, unleased="reclaim"):
    """Sweep every registered checkout: SKIP the ones with a live lease, RECLAIM the rest.

    With apply=True the dead-man's switch fires FIRST (check_deadman()), so every lapse is on the
    record before anything acts on it.

    A DRY RUN (the default) WRITES NOTHING — not the db, not the tree, not a ref. It reports the
    identical decision the real sweep would make, and the leases it lists under "fired" are the ones
    that WOULD fire the switch, computed by reading. A dry run that fired the switch, or that left
    signals behind, would be a dry run in name only.

    `only` limits the sweep to one checkout path.

    `unleased` decides the fate of a checkout with NO lease row at all:
      "reclaim" (default) — the ticket's rule as written: a checkout is ACTIVE only while its lease
                            is live, so no lease means not active. The fail-safe reading.
      "skip"              — THE ADOPTION SETTING. In a repo where the agents do not take leases yet,
                            "no lease" means "never enrolled", not "abandoned", and reclaiming those
                            would reap live work. See ADOPTION in the module docstring.
    A LAPSED or RELEASED lease is reclaimed under either setting — that is the dead-man's switch, and
    it is not what this flag is about.

    Returns {"fired": [...], "skipped": [...], "reclaimed": [...], "dry_run": bool}.
    """
    if unleased not in ("reclaim", "skip"):
        raise ValueError("unleased must be 'reclaim' or 'skip', got %r" % unleased)
    g = Git(root)
    fired = (check_deadman(db) if apply
             else [d for d in leases(db) if not d["live"] and d["state"] not in ("error", "released")])
    here = os.path.realpath(os.getcwd())
    # The main working tree AND the root we were pointed at. `root` is not necessarily the main tree:
    # run this from a pair worktree and root is that worktree, while the main tree is just another
    # entry in the sweep. See Git.main_worktree().
    protected = g.main_worktree() | {os.path.realpath(g.root)}
    out = {"fired": [{"path": d["path"], "holder": d["holder"], "age": round(d["age"], 1),
                      "ttl": d["ttl"]} for d in fired],
           "skipped": [], "reclaimed": [], "dry_run": not apply}

    for wt in g.registered_worktrees():
        p = wt["path"]
        if only and p != key(only):
            continue
        if p in protected:
            out["skipped"].append({"path": p, "why": "PROTECTED: the repo's main working tree, or "
                                                     "the root this reaper was pointed at"})
            continue
        if p == here or here.startswith(p + os.sep):
            out["skipped"].append({"path": p, "why": "the reaper is running inside this checkout"})
            continue
        lz = lease_of(p, db)
        if lz and lz["live"] and lz["state"] != "released":
            out["skipped"].append({"path": p, "why": "ACTIVE: lease held by %r, renewed %.0fs ago "
                                                     "(ttl %ds)" % (lz["holder"], lz["age"], lz["ttl"])})
            continue
        if lz is None and unleased == "skip":
            out["skipped"].append({"path": p, "why": "no lease, and --unleased skip: treating it as "
                                                     "NOT YET ENROLLED rather than abandoned"})
            continue
        if lz is None:
            why = "no lease (a checkout is ACTIVE only while a lease is live)"
        elif lz["state"] == "released":
            why = "lease RELEASED by %r" % lz["holder"]
        else:
            why = "lease LAPSED: %r stopped renewing %.0fs ago (ttl %ds)" % (lz["holder"], lz["age"], lz["ttl"])
        if not apply:
            out["reclaimed"].append({"path": p, "why": why, "would": "commit -> push -> remove"})
            continue
        r = reclaim(g, p, remote=remote)
        r["why"] = why
        out["reclaimed"].append(r)
        if r["removed"] and lz is not None:
            con = _open(db)
            con.execute("UPDATE active_work_lease SET state='reclaimed' WHERE path=?", (p,))
            con.commit()
            con.close()
    return out


# ── `hold`: the agent's protocol in one command ───────────────────────────────────────────────────
def hold(path, holder, ttl=60, every=None, db=None, steal=False, beats=None):
    """Acquire, then renew every `every` seconds until stopped; release on a CLEAN exit.

    `every` defaults to ttl/3 (min 1s) so two consecutive renewals can be lost before the lease
    lapses — a heartbeat that renewed exactly at ttl would lapse on the first scheduling hiccup.
    SIGINT/SIGTERM release the lease and exit 0. SIGKILL cannot be caught, so nothing is released and
    the lease lapses on its own: that is the dead-man's switch, and it is what makes a crashed agent's
    checkout reclaimable with no manual cleanup. `beats` (an int) stops after that many renewals —
    used by --selftest; None means run until signalled.
    """
    ttl = int(ttl)
    every = max(1, ttl // 3) if every is None else max(1, int(every))
    a = acquire(path, holder, ttl=ttl, steal=steal, db=db)
    if not a["ok"]:
        print("active_work_lease: %s" % a["reason"], file=sys.stderr)
        return 2
    print("holding lease on %s as %r (ttl %ds, renewing every %ds) — Ctrl-C to release"
          % (a["path"], holder, ttl, every), flush=True)

    stop = {"now": False}

    def _stop(signum, _frame):
        stop["now"] = True
        print("\nactive_work_lease: signal %d — releasing the lease" % signum, flush=True)

    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, _stop)

    n = 0
    while not stop["now"] and (beats is None or n < beats):
        time.sleep(every)
        if stop["now"]:
            break
        r = renew(path, holder, db=db)
        n += 1
        if not r["ok"]:
            print("active_work_lease: lease lost — %s" % r["reason"], file=sys.stderr)
            return 1
        print("  renewed %s at %s (beat %d)" % (r["path"], _now(), n), flush=True)
    release(path, holder, db=db)
    print("released %s" % key(path), flush=True)
    return 0


# ── selftest ──────────────────────────────────────────────────────────────────────────────────────
def _sha(path):
    """Every byte of a file, hashed — the isolation check's "did anything change?"."""
    import hashlib
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _st_git(repo, *args):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("selftest git %s failed: %s" % (" ".join(args[:2]), r.stderr.strip()))
    return r.stdout


def _st_repo(base):
    """A throwaway repo with a `file://` bare REMOTE — never this repo, never a network remote.

    (This repo's `origin` is a real gitlab url; a selftest that pushed to it would be a side effect
    on somebody else's server. Everything here is local and is deleted at the end.)
    """
    bare = os.path.join(base, "remote.git")
    _st_git(base, "init", "--quiet", "--bare", "-b", "main", bare)
    repo = os.path.join(base, "repo")
    os.makedirs(repo)
    _st_git(repo, "init", "--quiet", "-b", "main", ".")
    _st_git(repo, "config", "user.email", "active_work_lease@selftest")
    _st_git(repo, "config", "user.name", "active_work_lease selftest")
    open(os.path.join(repo, "registry.json"), "w").write('{"schema": 1, "package": "selftest"}\n')
    _st_git(repo, "add", "-A")
    _st_git(repo, "commit", "--quiet", "-m", "init")
    _st_git(repo, "remote", "add", "origin", "file://" + os.path.realpath(bare))
    _st_git(repo, "push", "--quiet", "origin", "main")
    return repo


def selftest():
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond)))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name,
                                ("  — %s" % detail) if detail and not cond else ""))

    base_dir = tempfile.mkdtemp(prefix="active_work_lease-selftest-")
    real_db = default_db()
    real_db_before = os.path.exists(real_db) and os.path.getmtime(real_db)
    try:
        repo = _st_repo(base_dir)
        db = os.path.join(base_dir, "state", "selftest.sqlite")   # NOT the real db; dir doesn't exist yet
        g = Git(repo)
        remote_dir = os.path.join(base_dir, "remote.git")
        print("== selftest == throwaway repo %s\n              throwaway db   %s" % (repo, db))

        def new_checkout(name):
            """A checkout an agent works in: a real worktree on its own branch, with real work in it."""
            p = os.path.join(base_dir, "wt-" + name)
            _st_git(repo, "worktree", "add", "--quiet", "-b", "ticket/" + name, p, "main")
            open(os.path.join(p, "work-%s.txt" % name), "w").write("uncommitted work by %s\n" % name)
            return os.path.realpath(p)

        def in_remote(branch, path):
            """Is `path` present on `branch` IN THE BARE REMOTE? Asked of the remote itself, not of
            the local repo — the only honest proof that the push landed."""
            r = subprocess.run(["git", "ls-tree", "-r", "--name-only", branch],
                               cwd=remote_dir, capture_output=True, text=True)
            return r.returncode == 0 and path in r.stdout.split()

        # ── the db layer mirrors store.py ──
        print("-- the lease record (mirrors store.py's heartbeat)")
        ck("a fresh db is created with the lease + signals tables", acquire(repo, "probe", ttl=1, db=db)["ok"])
        con = _con(db)
        cols = [r[1] for r in con.execute("PRAGMA table_info(active_work_lease)")]
        ck("the lease record is (path, holder, ts, ttl) + state", cols == ["path", "holder", "ts", "ttl", "state"], cols)
        ck("store.py's signals table is present (shared error channel)",
           con.execute("SELECT name FROM sqlite_master WHERE name='signals'").fetchone() is not None)
        ck("store.py's own heartbeat table is NOT touched by this layer",
           con.execute("SELECT name FROM sqlite_master WHERE name='heartbeat'").fetchone() is None)
        con.close()
        ck("ts is store.py's format (%Y-%m-%dT%H:%M:%S)",
           time.strptime(lease_of(repo, db)["ts"], "%Y-%m-%dT%H:%M:%S") is not None)

        # ── holding + refusing ──
        print("-- acquire / renew / release")
        a = new_checkout("a")
        ck("acquire returns ok and the lease is LIVE", acquire(a, "agent-1", ttl=30, db=db)["ok"] and is_active(a, db))
        r2 = acquire(a, "agent-2", ttl=30, db=db)
        ck("a second holder is REFUSED a live lease", r2["ok"] is False and r2["held_by"] == "agent-1", r2)
        ck("--steal overrides a live lease", acquire(a, "agent-2", ttl=30, steal=True, db=db)["ok"])
        ck("the steal is on the record as a warn signal",
           any(s["code"] == "LEASE_STOLEN" for s in _signals(db)))
        ck("acquire back", acquire(a, "agent-1", ttl=30, steal=True, db=db)["ok"])
        ck("renewing someone else's lease is REFUSED", renew(a, "agent-9", db=db)["ok"] is False)
        ck("releasing someone else's lease is REFUSED", release(a, "agent-9", db=db)["ok"] is False)
        ck("a path with a symlinked prefix keys to the same lease (realpath)",
           lease_of(a.replace("/private/var", "/var") if a.startswith("/private/var") else a, db) is not None)

        # ── ACCEPTANCE 1: hold a lease -> the reaper SKIPS the checkout ──
        print("-- ACCEPTANCE 1: a held lease holds the reaper off")
        out = reap(repo, remote="origin", apply=True, db=db)
        ck("the reaper SKIPS a checkout with a live lease",
           any(s["path"] == a and "ACTIVE" in s["why"] for s in out["skipped"]), out["skipped"])
        ck("the skipped checkout still exists on disk", os.path.isdir(a))
        ck("the skipped checkout's work is untouched", os.path.isfile(os.path.join(a, "work-a.txt")))
        ck("the MAIN WORKING TREE is never reclaimed",
           any(s["path"] == os.path.realpath(repo) and "PROTECTED" in s["why"] for s in out["skipped"]))

        # THE REGRESSION that the real repo caught: point the reaper at a LINKED worktree (which is
        # what --root is when an agent runs this from inside a pair worktree) and the MAIN working
        # tree must STILL be protected. The first version of this file protected only `root`, so
        # aimed this way it declared the repo's own main checkout reclaimable — commit, push and all.
        ck("git identifies the main working tree from inside a linked worktree",
           os.path.realpath(repo) in Git(a).main_worktree(), Git(a).main_worktree())
        out_a = reap(a, remote="origin", apply=True, db=db)   # a is a LINKED worktree, not the main one
        ck("aimed at a LINKED worktree, the reaper still protects the MAIN working tree",
           any(s["path"] == os.path.realpath(repo) and "PROTECTED" in s["why"] for s in out_a["skipped"]),
           [s["path"] for s in out_a["skipped"]])
        ck("the main working tree is NEVER listed as reclaimable",
           not any(r["path"] == os.path.realpath(repo) for r in out_a["reclaimed"]))
        ck("and reclaim() refuses it directly too (not just the sweep)",
           reclaim(Git(a), repo, remote="origin")["removed"] is False)
        ck("the main working tree is intact after all of that",
           os.path.isfile(os.path.join(repo, "registry.json")))

        # ── ACCEPTANCE 1b: RENEWING holds it off past what would have been a lapse ──
        print("-- ACCEPTANCE 1b: renewal holds it off past the original ttl")
        # Timings leave a FULL SECOND of margin on each side of the ±1s truncation fuzz (see THE TTL
        # IS ACCURATE TO ±1 SECOND): with ttl=5, a beat 3s ago measures at most 4s (live, 1s to
        # spare) and no beat for 6s measures at least 6s (lapsed, 1s to spare). A test that sat
        # inside the fuzz would flake, and a flaky proof proves nothing.
        b = new_checkout("b")
        acquire(b, "agent-b", ttl=5, db=db)
        time.sleep(3)
        renew(b, "agent-b", db=db)          # the beat that saves it
        time.sleep(3)                        # 6s elapsed > ttl=5, but only 3s since the renewal
        out = reap(repo, remote="origin", apply=True, db=db)
        ck("a RENEWED lease is still live after 6s with ttl=5 (age measures from the last beat)",
           is_active(b, db))
        ck("the reaper skips the renewed checkout", any(s["path"] == b for s in out["skipped"]))
        ck("the renewed checkout still exists", os.path.isdir(b))

        # ── ACCEPTANCE 2: stop renewing -> after ttl the reaper reclaims (commit->push->remove) ──
        print("-- ACCEPTANCE 2: stop renewing -> lapse -> reclaim (commit -> push -> remove)")
        ck("before the lapse, the lease is live", is_active(b, db))
        time.sleep(6)                        # stop renewing; ttl=5 -> lapsed, with a second to spare
        ck("after ttl with no renewal the lease is LAPSED", not is_active(b, db))
        fired = check_deadman(db)
        ck("the DEAD-MAN'S SWITCH fires for the lapsed lease", any(d["path"] == b for d in fired), fired)
        ck("the fired lease's state is 'error' (store.py's spelling)", lease_of(b, db)["state"] == "error")
        ck("the lapse is filed as an error signal on store.py's channel",
           any(s["code"] == "LEASE_LAPSED" and s["ref"] == b and s["level"] == "error" for s in _signals(db)))
        ck("the switch fires ONCE per lapse (a second check re-fires nothing)",
           not any(d["path"] == b for d in check_deadman(db)))

        # A dry run is proven in ISOLATION, the way the adversary will: snapshot the state dir and
        # every db byte BEFORE, run it with nothing else touching them, diff AFTER. `b2` is a lease
        # that has LAPSED but whose switch has NOT yet fired — the one case that would tempt a dry
        # run into writing.
        b2 = new_checkout("b2")
        acquire(b2, "agent-b2", ttl=0, db=db)
        time.sleep(1.1)
        state_dir = os.path.dirname(db)
        before_ls, before_hash = sorted(os.listdir(state_dir)), _sha(db)
        dry = reap(repo, remote="origin", apply=False, db=db)
        ck("a DRY RUN names the lapsed checkout as reclaimable",
           any(r["path"] == b for r in dry["reclaimed"]))
        ck("a DRY RUN reclaims NOTHING (the checkout is still there)", os.path.isdir(b) and os.path.isdir(b2))
        ck("a DRY RUN reports the lease that WOULD fire the switch",
           any(d["path"] == b2 for d in dry["fired"]), dry["fired"])
        ck("a DRY RUN does not actually fire it (the lease is still 'ok', not 'error')",
           lease_of(b2, db)["state"] == "ok", lease_of(b2, db)["state"])
        ck("a DRY RUN writes NOTHING to the db (byte-identical before/after)", _sha(db) == before_hash)
        ck("a DRY RUN creates NO file beside the db (no -wal/-shm sidecars)",
           sorted(os.listdir(state_dir)) == before_ls, sorted(os.listdir(state_dir)))

        out = reap(repo, remote="origin", apply=True, db=db)
        got = [r for r in out["reclaimed"] if r["path"] == b]
        ck("the reaper reclaims the lapsed checkout", bool(got), out["reclaimed"])
        got = got[0] if got else {}
        ck("  1. COMMIT: the abandoned work is committed", got.get("committed") and got.get("sha"))
        ck("  2. PUSH:   the commit reached the remote", got.get("pushed"))
        ck("  3. REMOVE: the checkout is gone from disk", got.get("removed") and not os.path.exists(b))
        ck("the abandoned file is IN the remote's branch (push proven at the remote)",
           in_remote("ticket/b", "work-b.txt"), "remote lacks work-b.txt")
        ck("the branch survives the reclaim (the ticket's trace, as pair_loop keeps it)",
           subprocess.run(["git", "show-ref", "--verify", "--quiet", "refs/heads/ticket/b"],
                          cwd=repo).returncode == 0)
        ck("the reclaimed lease is recorded as 'reclaimed'", lease_of(b, db)["state"] == "reclaimed")
        ck("git no longer lists the reclaimed worktree",
           b not in [w["path"] for w in g.registered_worktrees()])
        ck("the checkout that still holds a lease was NOT reclaimed", os.path.isdir(a))

        # ── ACCEPTANCE 3: a CRASHED agent's checkout is reclaimed automatically ──
        print("-- ACCEPTANCE 3: a real crashed agent (SIGKILL) is reclaimed with no manual cleanup")
        c = new_checkout("c")
        env = dict(os.environ, PROJECT_DB=db)
        proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "hold", c,
                                 "--holder", "agent-crash", "--ttl", "5", "--every", "1"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        deadline = time.time() + 10
        while time.time() < deadline and not is_active(c, db):
            time.sleep(0.1)
        ck("a real `hold` subprocess takes the lease", is_active(c, db))
        out = reap(repo, remote="origin", apply=True, db=db)
        ck("while it beats, the reaper skips its checkout", any(s["path"] == c for s in out["skipped"]))

        proc.send_signal(signal.SIGKILL)     # the crash: no release, no cleanup, no goodbye
        proc.wait(timeout=10)
        ck("the crashed agent is dead", proc.poll() is not None)
        ck("the crashed agent's lease is still 'ok' (it never got to release it)",
           lease_of(c, db)["state"] == "ok")
        time.sleep(6)                        # ttl=5 passes with nobody left to renew
        out = reap(repo, remote="origin", apply=True, db=db)
        got = [r for r in out["reclaimed"] if r["path"] == c]
        ck("the crashed agent's checkout is reclaimed AUTOMATICALLY", bool(got), out["reclaimed"])
        got = got[0] if got else {}
        ck("  its unsaved work was committed and pushed", got.get("committed") and got.get("pushed"))
        ck("  its checkout is gone (no manual cleanup)", got.get("removed") and not os.path.exists(c))
        ck("  its work survives in the remote", in_remote("ticket/c", "work-c.txt"))

        # ── --unleased: the adoption setting ──
        print("-- --unleased skip: the adoption setting")
        u = new_checkout("u")                                  # a checkout that never took a lease
        ck("no lease row exists for a never-enrolled checkout", lease_of(u, db) is None)
        dry = reap(repo, remote="origin", apply=False, db=db, unleased="reclaim")
        ck("--unleased reclaim (default) treats an unleased checkout as reclaimable",
           any(r["path"] == u for r in dry["reclaimed"]))
        dry = reap(repo, remote="origin", apply=False, db=db, unleased="skip")
        ck("--unleased skip treats it as NOT YET ENROLLED and skips it",
           any(s["path"] == u and "NOT YET ENROLLED" in s["why"] for s in dry["skipped"]))
        # the setting must not disarm the dead-man's switch — that would defeat the whole ticket
        v = new_checkout("v")
        acquire(v, "agent-v", ttl=0, db=db)
        time.sleep(1.1)
        out = reap(repo, remote="origin", apply=True, db=db, unleased="skip")
        ck("--unleased skip STILL reclaims a LAPSED lease (the switch stays armed)",
           any(r["path"] == v and r["removed"] for r in out["reclaimed"]), out["reclaimed"])
        ck("--unleased skip left the never-enrolled checkout alone", os.path.isdir(u))
        try:
            reap(repo, db=db, unleased="nonsense")
            ck("an invalid --unleased is refused", False, "no error raised")
        except ValueError:
            ck("an invalid --unleased is refused with a message, not a crash", True)

        # ── reclaim's edges ──
        print("-- reclaim's edges")
        d = new_checkout("d")
        _st_git(d, "add", "-A")
        _st_git(d, "commit", "--quiet", "-m", "agent committed its own work")
        acquire(d, "agent-d", ttl=0, db=db)          # ttl=0 -> lapsed immediately
        time.sleep(1.1)
        out = reap(repo, remote="origin", apply=True, db=db)
        got = [r for r in out["reclaimed"] if r["path"] == d][0]
        ck("a CLEAN lapsed checkout is reclaimed without a crash (nothing to commit)",
           got["committed"] is False and got["removed"], got["notes"])
        ck("  a clean checkout still gets pushed (its commits leave the machine)", got["pushed"])

        e = new_checkout("e")
        _st_git(e, "checkout", "--quiet", "--detach")
        acquire(e, "agent-e", ttl=0, db=db)
        time.sleep(1.1)
        out = reap(repo, remote="origin", apply=True, db=db)
        got = [r for r in out["reclaimed"] if r["path"] == e][0]
        ck("a DETACHED-HEAD checkout's commit is parked on a permanent ref before removal",
           got["ref"] and subprocess.run(["git", "show-ref", "--verify", "--quiet", got["ref"]],
                                         cwd=repo).returncode == 0, got["notes"])
        ck("  and it is removed", got["removed"])

        f = new_checkout("f")
        acquire(f, "agent-f", ttl=0, db=db)
        time.sleep(1.1)
        out = reap(repo, remote="nonesuch", apply=True, db=db)
        got = [r for r in out["reclaimed"] if r["path"] == f][0]
        ck("a missing remote does NOT abort the reclaim (work preserved on the branch)",
           got["committed"] and got["pushed"] is False and got["removed"], got["notes"])
        ck("  and the reason is stated, not swallowed", any("no remote named" in n for n in got["notes"]))
        ck("  the work is still recoverable from the branch after removal",
           "work-f.txt" in _st_git(repo, "show", "--name-only", "--format=", "ticket/f"))

        # a plain directory that git does not know about is NEVER erased
        plain = os.path.join(base_dir, "not-a-worktree")
        os.makedirs(plain)
        open(os.path.join(plain, "precious.txt"), "w").write("not git's to delete\n")
        acquire(plain, "agent-x", ttl=0, db=db)
        time.sleep(1.1)
        reap(repo, remote="origin", apply=True, db=db, only=plain)
        ck("a directory that is not a registered worktree is never removed",
           os.path.isfile(os.path.join(plain, "precious.txt")))
        got = reclaim(g, plain, remote="origin")
        ck("  and reclaim says why rather than erasing it",
           got["removed"] is False and any("not a registered git worktree" in n for n in got["notes"]))

        # ── no side effects on the real db ──
        print("-- no side effect on the real db or this repo")
        after = os.path.exists(real_db) and os.path.getmtime(real_db)
        ck("the selftest never created or touched the real db (%s)" % real_db, after == real_db_before)

    finally:
        # the throwaway's worktrees are registered only in the throwaway repo, which goes with it
        shutil.rmtree(base_dir, ignore_errors=True)

    bad = [n for n, ok in checks if not ok]
    print("\n== selftest == %d/%d checks passed%s"
          % (len(checks) - len(bad), len(checks), ("  FAILED: " + "; ".join(bad)) if bad else ""))
    return 1 if bad else 0


def _signals(db=None):
    con = _open(db)
    rows = [dict(r) for r in con.execute("SELECT * FROM signals ORDER BY id DESC")]
    con.close()
    return rows


# ── cli ───────────────────────────────────────────────────────────────────────────────────────────
def _fmt(lz):
    state = lz["state"]
    live = "LIVE" if (lz["live"] and state != "released") else "LAPSED"
    return "  %-6s %-10s %-14s age %5.0fs / ttl %4ds  %s" % (live, state, lz["holder"], lz["age"],
                                                             lz["ttl"], lz["path"])


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="active_work_lease.py",
        description="active-work LEASE/heartbeat: an agent holds a checkout off the reaper; a lapse "
                    "fires the dead-man's switch and the reaper reclaims (commit -> push -> remove).",
        epilog="the db defaults to store.py's: $PROJECT_DB > $JAZZ_DB > ~/.jazz/congruency.sqlite")
    ap.add_argument("--db", help="override the lease db")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the whole lease/lapse/reap cycle in a THROWAWAY repo + db, then exit")
    sub = ap.add_subparsers(dest="cmd")

    def holder_cmd(name, help):
        p = sub.add_parser(name, help=help)
        p.add_argument("path", help="the checkout")
        p.add_argument("--holder", required=True, help="who holds the lease (an agent id)")
        return p

    p = holder_cmd("acquire", "take the lease on a checkout")
    p.add_argument("--ttl", type=int, default=60, help="seconds a renewal is good for (default 60)")
    p.add_argument("--steal", action="store_true", help="take a LIVE lease from its holder (filed as a signal)")
    p = holder_cmd("renew", "renew the lease (the beat that holds the reaper off)")
    p.add_argument("--ttl", type=int, help="also change the ttl")
    holder_cmd("release", "hand the checkout back; the reaper may reclaim it")
    p = holder_cmd("hold", "acquire + renew in the foreground until stopped, then release")
    p.add_argument("--ttl", type=int, default=60, help="seconds a renewal is good for (default 60)")
    p.add_argument("--every", type=int, help="renew interval (default ttl/3, min 1s)")
    p.add_argument("--steal", action="store_true", help="take a LIVE lease from its holder")
    p.add_argument("--beats", type=int, help="stop after N renewals (testing; default: until signalled)")

    p = sub.add_parser("leases", help="list every lease, live or lapsed")
    p.add_argument("--json", action="store_true")
    sub.add_parser("check", help="fire the dead-man's switch for every lapsed lease")
    p = sub.add_parser("reap", help="skip ACTIVE checkouts; reclaim the rest (DRY RUN unless --apply)")
    p.add_argument("--apply", action="store_true", help="actually commit -> push -> remove")
    p.add_argument("--remote", default="origin", help="push target (default origin; 'none' to skip)")
    p.add_argument("--root", help="the repo (default: this tool's repo)")
    p.add_argument("--path", help="reap only this checkout")
    p.add_argument("--unleased", choices=("reclaim", "skip"), default="reclaim",
                   help="a checkout with NO lease: 'reclaim' (default; the ticket's rule — active "
                        "only while a lease is live) or 'skip' (the ADOPTION setting: treat it as "
                        "not-yet-enrolled, and reclaim only lapsed/released leases)")
    p.add_argument("--json", action="store_true")

    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.cmd:
        ap.print_help()
        return 2
    db = a.db

    try:
        if a.cmd in ("acquire", "renew", "release"):
            if a.cmd == "acquire":
                r = acquire(a.path, a.holder, ttl=a.ttl, steal=a.steal, db=db)
            elif a.cmd == "renew":
                r = renew(a.path, a.holder, ttl=a.ttl, db=db)
            else:
                r = release(a.path, a.holder, db=db)
            if not r["ok"]:
                print("active_work_lease: %s" % r["reason"], file=sys.stderr)
                return 1
            print("%s %s for %r%s" % (a.cmd, r["path"], a.holder,
                                      (" (ttl %ds)" % r["ttl"]) if r.get("ttl") is not None else ""))
            return 0

        if a.cmd == "hold":
            return hold(a.path, a.holder, ttl=a.ttl, every=a.every, db=db, steal=a.steal, beats=a.beats)

        if a.cmd == "leases":
            rows = leases(db)
            if a.json:
                print(json.dumps(rows, indent=2))
            elif not rows:
                print("(none)")
            else:
                for lz in rows:
                    print(_fmt(lz))
            return 0

        if a.cmd == "check":
            stale = check_deadman(db)
            for d in stale:
                print("dead-man's switch FIRED: %s (held by %r, %.0fs since the last beat, ttl %ds)"
                      % (d["path"], d["holder"], d["age"], d["ttl"]))
            print("lapsed: %s" % (len(stale) or "none"))
            return 0

        if a.cmd == "reap":
            root = a.root or find_root(os.path.dirname(os.path.abspath(__file__)))
            out = reap(root, remote=(None if a.remote == "none" else a.remote),
                       apply=a.apply, db=db, only=a.path, unleased=a.unleased)
            if a.json:
                print(json.dumps(out, indent=2))
                return 0
            print("reaper over %s%s" % (root, "   [DRY RUN — nothing reclaimed; --apply to act]"
                                              if out["dry_run"] else ""))
            for d in out["fired"]:
                print("  FIRED   %s (held by %r, %.0fs since the last beat)" % (d["path"], d["holder"], d["age"]))
            for s in out["skipped"]:
                print("  SKIP    %s — %s" % (s["path"], s["why"]))
            for r in out["reclaimed"]:
                if out["dry_run"]:
                    print("  WOULD   %s — %s -> %s" % (r["path"], r["why"], r["would"]))
                else:
                    print("  RECLAIM %s — %s\n          commit=%s push=%s remove=%s%s"
                          % (r["path"], r["why"], r["sha"][:8] if r["sha"] else "(none)",
                             r["pushed"], r["removed"],
                             "".join("\n          note: %s" % n for n in r["notes"])))
            if not out["skipped"] and not out["reclaimed"]:
                print("  (no checkouts)")
            return 0
    except (RuntimeError, ValueError) as e:
        print("active_work_lease: %s" % e, file=sys.stderr)   # a one-line message, never a traceback
        return 2
    return 2


# ── registry gate (note-for-claude: a tool that cannot see the registry throws) ───────────────────
def find_root(start):
    d = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(d, "registry.json")):
            return d
        nxt = os.path.dirname(d)
        if nxt == d:
            raise RuntimeError("registry.json not found walking up from %s — refusing to run" % start)
        d = nxt


if __name__ == "__main__":
    sys.exit(main())
