#!/usr/bin/env python3
"""ticket-authorization-shadow.py — the ticket IS an authorization; history CANNOT be erased.

Crank (0029_ticket_authorization.sql) turns the ticket spec into schema: kinds (pair/solo),
lifecycle-as-data, an append-only journal, a permanent-UID manifest, and agent authorization —
with the governance enforced by SQL triggers because a rule in a docstring has already failed to
bind (the dispatch agent erased ledger rows; the id gaps are in the live db). This shadow pins:

  · additive — pre-existing tickets/api_routes/memories rows survive the migration untouched;
  · erasure REFUSED — DELETE on tickets/ticket_events/ticket_works aborts; identity UPDATE aborts;
  · lifecycle updates still WORK — status flips succeed and are auto-journaled (append-only);
  · authorization — only REGISTERED agents assign; ACTIVE needs an agent; pair-DONE needs two
    distinct agents in two distinct roles;
  · manifest — work UIDs mint mechanically and cannot be updated or deleted;
  · agent.roster honors its documented contract: omit n -> ALL rows (the NULL-LIMIT fix).

Isolation: throwaway sqlite in a tempfile; applies the REAL migrations via setup.do_migrate.
The live db is never touched. Structure + exit code mirror the other shadows.
"""
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
import setup  # noqa: E402

checks = []
def check(name, ok):
    checks.append((name, bool(ok)))
    print("  %s %s" % ("\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m", name))


def refused(con, sql, *params):
    """True iff the statement is REFUSED by a governance trigger (sqlite3.IntegrityError/RAISE)."""
    try:
        con.execute(sql, params)
        return False
    except sqlite3.Error:
        return True


def seed_db(path):
    """A minimal pre-migration db: memories + api_routes + a legacy ticket (pre-0029 world)."""
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session TEXT, tool TEXT, intent TEXT, note TEXT);"
        "CREATE INDEX idx_memories_session ON memories(session);"
        "CREATE TABLE api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);")
    con.execute("INSERT INTO api_routes (name,method,sql,auth) VALUES ('tickets.recent','GET','SELECT 1','public')")
    con.commit(); con.close()


def main():
    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "congruency.sqlite")
        seed_db(db)

        res = setup.do_migrate(db_path=db)
        check("migration applied (0029_ticket_authorization.sql)",
              "0029_ticket_authorization.sql" in res.get("applied", []))

        con = sqlite3.connect(db)
        try:
            tabs = {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            check("kernel tables created (kinds, lifecycles, events, works, agents-edge)",
                  {"ticket_kinds", "ticket_lifecycles", "ticket_events", "ticket_works", "ticket_agents"} <= tabs)
            check("pre-existing api_routes row survived (additive)",
                  con.execute("SELECT COUNT(*) FROM api_routes WHERE name='tickets.recent'").fetchone()[0] == 1)

            # a legacy-shaped ticket (0002's defensive CREATE ran) + a pair-kind ticket
            con.execute("INSERT INTO tickets (id, ts, updated, component, title, status, kind) "
                        "VALUES (1, 100, 100, 'congruency', 'legacy row', 'REQUESTED', NULL)")
            con.execute("INSERT INTO tickets (id, ts, updated, component, title, status, kind) "
                        "VALUES (2, 200, 200, 'congruency', 'pair build', 'OPEN', 'build')")
            con.commit()

            # ── erasure refused ─────────────────────────────────────────────────────
            check("DELETE a ticket -> REFUSED", refused(con, "DELETE FROM tickets WHERE id=1"))
            check("rewrite ticket identity (title) -> REFUSED",
                  refused(con, "UPDATE tickets SET title='rewritten history' WHERE id=1"))
            check("re-kind a kinded ticket -> REFUSED",
                  refused(con, "UPDATE tickets SET kind='bug' WHERE id=2"))

            # ── lifecycle still works, and is auto-journaled ────────────────────────
            con.execute("UPDATE tickets SET status='AUTHORIZED', updated=101 WHERE id=1"); con.commit()
            check("status update (existing crankd flow) still WORKS",
                  con.execute("SELECT status FROM tickets WHERE id=1").fetchone()[0] == "AUTHORIZED")
            check("status change auto-journaled to ticket_events",
                  con.execute("SELECT COUNT(*) FROM ticket_events WHERE ticket_id=1 AND event='status' AND status='AUTHORIZED'").fetchone()[0] == 1)
            check("journal rows cannot be edited or erased",
                  refused(con, "UPDATE ticket_events SET note='doctored' WHERE ticket_id=1")
                  and refused(con, "DELETE FROM ticket_events WHERE ticket_id=1"))

            # ── authorization: registered agents only; ACTIVE needs an agent ───────
            check("assign an UNREGISTERED agent -> REFUSED",
                  refused(con, "INSERT INTO ticket_agents (ts,ticket_id,agent_id,role) VALUES (300,2,'ghost-1','coder')"))
            check("ACTIVE without an agent -> REFUSED",
                  refused(con, "UPDATE tickets SET status='ACTIVE' WHERE id=2"))
            con.execute("INSERT INTO agents (agent_id,parent,prompt,tools,status,ts) VALUES ('coder-01',NULL,'full prompt','[]','active',300)")
            con.execute("INSERT INTO agents (agent_id,parent,prompt,tools,status,ts) VALUES ('tester-01',NULL,'full prompt','[]','active',300)")
            con.execute("INSERT INTO ticket_agents (ts,ticket_id,agent_id,role) VALUES (301,2,'coder-01','coder')")
            con.execute("UPDATE tickets SET status='ACTIVE' WHERE id=2"); con.commit()
            check("registered agent assigned -> ACTIVE allowed",
                  con.execute("SELECT status FROM tickets WHERE id=2").fetchone()[0] == "ACTIVE")

            # ── the adversarial pair: DONE needs two distinct agents, two roles ────
            check("pair ticket DONE with only the worker -> REFUSED",
                  refused(con, "UPDATE tickets SET status='DONE' WHERE id=2"))
            con.execute("INSERT INTO ticket_agents (ts,ticket_id,agent_id,role) VALUES (302,2,'tester-01','tester')")
            con.execute("UPDATE tickets SET status='DONE' WHERE id=2"); con.commit()
            check("worker + adversary assigned -> DONE allowed",
                  con.execute("SELECT status FROM tickets WHERE id=2").fetchone()[0] == "DONE")
            check("an authorization cannot be unassigned (history)",
                  refused(con, "DELETE FROM ticket_agents WHERE ticket_id=2"))

            # ── the manifest: permanent mechanical UIDs ─────────────────────────────
            con.execute("INSERT INTO ticket_works (ts,ticket_id,kind,ref) VALUES (303,2,'code','fixes/x.py')")
            con.commit()
            uid = con.execute("SELECT uid FROM ticket_works WHERE ticket_id=2").fetchone()[0]
            check("work UID minted mechanically", isinstance(uid, int) and uid >= 1)
            check("manifest entries cannot be edited or erased",
                  refused(con, "UPDATE ticket_works SET ref='elsewhere' WHERE uid=?", uid)
                  and refused(con, "DELETE FROM ticket_works WHERE uid=?", uid))

            # ── agent.roster: the documented omit-n-for-all contract now holds ─────
            roster_sql = con.execute("SELECT sql FROM api_routes WHERE name='agent.roster'").fetchone()[0]
            rows = con.execute(roster_sql, {"n": None}).fetchall()
            check("agent.roster with n omitted (NULL) returns ALL agents", len(rows) == 2)
            rows = con.execute(roster_sql, {"n": 1}).fetchall()
            check("agent.roster with n=1 returns 1", len(rows) == 1)

            # ── lifecycle-as-data supports steps-until-goal ─────────────────────────
            steps = con.execute("SELECT COUNT(*) FROM ticket_lifecycles WHERE kind='build' AND version=1").fetchone()[0]
            check("build lifecycle enumerated (many steps)", steps >= 6)
        finally:
            con.close()

    failed = [n for n, ok in checks if not ok]
    print("\n%s  (%d/%d)" % ("\033[31mFAIL\033[0m" if failed else "\033[32mPASS\033[0m",
                             len(checks) - len(failed), len(checks)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
