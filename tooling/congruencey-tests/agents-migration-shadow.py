#!/usr/bin/env python3
"""agents-migration-shadow.py — the agent-provenance migration is ADDITIVE and correct.

Crank 4.090 adds the `agents` registry + the agent.register/agent.trail/agent.roster routes via a
forward-only migration applied to the live db. This shadow pins two guarantees:
  · additive — pre-existing rows (memories, api_routes) survive the migration untouched;
  · correct — the routes land, and the real route SQL actually registers an agent and returns
    that agent's propagation trail from `memories`.

Isolation: builds a throwaway sqlite in a tempfile (mirroring the live schema just enough), applies
the REAL migrations from the repo via setup.do_migrate(db_path=...). The live db is never touched.
Structure + exit code mirror the other shadows.
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


def seed_db(path):
    """A minimal pre-migration db: memories (with a sentinel event) + a non-empty api_routes."""
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session TEXT, tool TEXT, intent TEXT, note TEXT);"
        "CREATE INDEX idx_memories_session ON memories(session);"
        "CREATE TABLE api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);")
    con.execute("INSERT INTO memories (ts,session,tool,intent,note) VALUES ('100','agent-7','disks','recon before flash','ok')")
    con.execute("INSERT INTO api_routes (name,method,sql,auth) VALUES ('tickets.recent','GET','SELECT 1','public')")
    con.commit(); con.close()


def route_sql(con, name):
    r = con.execute("SELECT sql FROM api_routes WHERE name=?", (name,)).fetchone()
    return r[0] if r else None


def main():
    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "congruency.sqlite")
        seed_db(db)

        res = setup.do_migrate(db_path=db)
        check("migration applied (0001_agents.sql)", "0001_agents.sql" in res.get("applied", []))

        con = sqlite3.connect(db)
        try:
            tabs = {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            check("agents table created", "agents" in tabs)
            routes = {x[0] for x in con.execute("SELECT name FROM api_routes")}
            check("agent.register + agent.trail + agent.roster routes present",
                  {"agent.register", "agent.trail", "agent.roster"}.issubset(routes))

            # ADDITIVE: the pre-existing rows survived
            check("pre-existing memories row preserved",
                  con.execute("SELECT count(*) FROM memories WHERE session='agent-7'").fetchone()[0] == 1)
            check("pre-existing api_routes row (tickets.recent) preserved",
                  con.execute("SELECT count(*) FROM api_routes WHERE name='tickets.recent'").fetchone()[0] == 1)

            # CORRECT: drive the real route SQL — register agent-7, then read its trail
            reg = route_sql(con, "agent.register")
            st = con.execute(reg, {"agent_id": "agent-7", "parent": "root",
                                   "prompt": "crank a pi image", "tools": "build,verify,disks,flash,base"})
            con.commit()
            check("agent.register SQL inserts the spawn",
                  con.execute("SELECT count(*) FROM agents WHERE agent_id='agent-7'").fetchone()[0] == 1)
            trail = con.execute(route_sql(con, "agent.trail"), {"agent_id": "agent-7"}).fetchall()
            check("agent.trail SQL returns the agent's propagation trail (the seeded event)",
                  len(trail) == 1 and trail[0][1] == "disks")
        finally:
            con.close()

        # IDEMPOTENT: a second migrate is a no-op and disturbs nothing
        res2 = setup.do_migrate(db_path=db)
        check("re-running migrate is a no-op (nothing re-applied)", res2.get("applied", []) == [])

    ok = all(v for _, v in checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(v for _, v in checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
