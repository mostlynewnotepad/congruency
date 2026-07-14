#!/usr/bin/env python3
"""ticket_status.py — one-glance, READ-ONLY rollup of a single ticket: "how far from done?"

Answers, for one ticket id, from the congruency sqlite:
    header    — id, kind, status, title
    crew      — the agents authorized on it (agent_id + role), in assignment order
    journal   — the append-only event log (localtime datetime, agent, event, note), in order
    manifest  — every permanent-UID work the ticket authorized (UID, kind, ref)
    lessons   — harvested lesson events, if any
    PROGRESS  — 'steps remaining: X of Y', X = the latest steps_remaining reported on the
                journal, Y = the total lifecycle steps for the ticket's kind (version 1)

The db is opened STRICTLY read-only via the sqlite URI `immutable=1` flag: the tool never
writes to the db and creates NO files. (mode=ro alone is not enough — the state db is in WAL
journal mode, and mode=ro reads it by spinning up `-wal`/`-shm` sidecar files in the state
directory; immutable=1 reads the identical committed data and touches nothing.) Any missing
piece prints '(none)' rather than crashing. Exit 0 if the ticket exists; exit 2 with a
one-line message (never a traceback) for a missing ticket id.

Usage:
    python3 ticket_status.py <ticket_id> [--db PATH]

The default db is <repo>/checkouts/current/state/congruency.sqlite, where <repo> is found by
walking UP from this tool's own location to registry.json (note-for-claude: a tool that cannot
see the registry throws).
"""
import argparse
import os
import sqlite3
import sys


# ── registry gate (note-for-claude: a tool that cannot see the registry throws) ──────────────────
def find_root(start):
    d = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(d, "registry.json")):
            return d
        nxt = os.path.dirname(d)
        if nxt == d:
            raise RuntimeError("registry.json not found walking up from %s — refusing to run" % start)
        d = nxt


ROOT = find_root(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "checkouts", "current", "state", "congruency.sqlite")


def connect_ro(db_path):
    """Open the db STRICTLY read-only: never writes, never creates a file.

    Uses the sqlite URI `immutable=1` flag rather than `mode=ro`. The state db is in WAL
    journal mode; opening a WAL db with `mode=ro` forces sqlite to create `-wal`/`-shm`
    sidecar files in the state directory (a forbidden side effect). `immutable=1` promises
    sqlite the file will not change, so it reads the committed data with no locking and
    creates zero files."""
    if not os.path.isfile(db_path):
        print("ticket_status: database not found: %s" % db_path)
        sys.exit(2)
    return sqlite3.connect("file:%s?immutable=1" % db_path, uri=True)


def rows(con, sql, params=()):
    return con.execute(sql, params).fetchall()


def val(x):
    """Render a possibly-NULL cell for display."""
    return "(none)" if x is None or x == "" else str(x)


def section(title):
    print("\n%s" % title)
    print("-" * len(title))


def main():
    ap = argparse.ArgumentParser(description="one-glance READ-ONLY rollup of a single ticket")
    ap.add_argument("ticket_id", type=int, help="the ticket id to report on")
    ap.add_argument("--db", default=DEFAULT_DB, help="path to the congruency sqlite (default: repo state db)")
    a = ap.parse_args()

    con = connect_ro(a.db)
    tid = a.ticket_id

    # ── ticket header (exists? or exit 2, no traceback) ──────────────────────────────────────────
    hdr = rows(con, "SELECT id, kind, status, title FROM tickets WHERE id = ?", (tid,))
    if not hdr:
        print("ticket_status: no ticket with id %d" % tid)
        return 2
    tid_, kind, status, title = hdr[0]

    print("TICKET #%s" % val(tid_))
    print("  kind:   %s" % val(kind))
    print("  status: %s" % val(status))
    print("  title:  %s" % val(title))

    # ── crew: authorized agents, in assignment order ─────────────────────────────────────────────
    section("CREW")
    crew = rows(con, "SELECT agent_id, role FROM ticket_agents WHERE ticket_id = ? ORDER BY ts, rowid", (tid,))
    if crew:
        for agent_id, role in crew:
            print("  %-28s %s" % (val(agent_id), val(role)))
    else:
        print("  (none)")

    # ── journal: append-only events, in order ────────────────────────────────────────────────────
    section("JOURNAL")
    journal = rows(con,
                   "SELECT datetime(ts, 'unixepoch', 'localtime'), agent_id, event, note "
                   "FROM ticket_events WHERE ticket_id = ? ORDER BY ts, id", (tid,))
    if journal:
        for dt, agent_id, event, note in journal:
            print("  %s  %-26s %-9s %s" % (val(dt), val(agent_id), val(event), val(note)))
    else:
        print("  (none)")

    # ── manifest: permanent-UID works ────────────────────────────────────────────────────────────
    section("MANIFEST")
    manifest = rows(con, "SELECT uid, kind, ref FROM ticket_works WHERE ticket_id = ? ORDER BY uid", (tid,))
    if manifest:
        for uid, mkind, ref in manifest:
            print("  UID %-4s %-8s %s" % (val(uid), val(mkind), val(ref)))
    else:
        print("  (none)")

    # ── lessons: harvested lesson events, if any ─────────────────────────────────────────────────
    section("LESSONS")
    lessons = rows(con,
                   "SELECT datetime(ts, 'unixepoch', 'localtime'), agent_id, note "
                   "FROM ticket_events WHERE ticket_id = ? AND event = 'lesson' ORDER BY ts, id", (tid,))
    if lessons:
        for dt, agent_id, note in lessons:
            print("  %s  %-26s %s" % (val(dt), val(agent_id), val(note)))
    else:
        print("  (none)")

    # ── progress: steps remaining X of Y ─────────────────────────────────────────────────────────
    section("PROGRESS")
    latest = rows(con,
                  "SELECT steps_remaining FROM ticket_events "
                  "WHERE ticket_id = ? AND steps_remaining IS NOT NULL "
                  "ORDER BY ts DESC, id DESC LIMIT 1", (tid,))
    x = latest[0][0] if latest else None
    total = rows(con,
                 "SELECT COUNT(*) FROM ticket_lifecycles WHERE kind = ? AND version = 1", (kind,))
    y = total[0][0] if total else 0
    print("  steps remaining: %s of %s" % (val(x), val(y) if y else "(none)"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
