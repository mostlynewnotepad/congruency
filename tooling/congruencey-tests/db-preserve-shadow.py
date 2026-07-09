#!/usr/bin/env python3
"""db-preserve-shadow.py — the install must REMEMBER an existing live db, never wipe it.

This is the golden-vector guard for crank 4.089. `setup.py:do_state` used to unconditionally
extract the seed `database.tar.xz` over `state/congruency.sqlite` — running `install` against a
tree whose state dir holds (or is bind-mounted from) the live db would erase every ticket, memory,
and api_key. The `preserve_db` guard fixes that. This shadow pins the guarantee so re-introducing
the wipe fails the install gate loudly.

Isolation: every check runs in its own tempfile state dir with `setup.HERE` monkeypatched to it.
The real live db (~/bin/config/congruency/congruency.sqlite) and the repo's own state dir are
NEVER touched. Structure + exit code mirror the jazz_wallet shadows: a list of (name, ok) checks,
exit 0 iff all pass.
"""
import os
import shutil
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
sys.path.insert(0, REPO)
import setup  # noqa: E402  — the installer under test

REAL_TARBALL = os.path.join(REPO, "checkouts", "current", "state", "database.tar.xz")
SENTINEL = "do-not-wipe-me-4089"

checks = []
def check(name, ok):
    checks.append((name, bool(ok)))
    print("  %s %s" % ("\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m", name))


def build_state(root, with_db=False, expect=None):
    """Lay out <root>/checkouts/current/state with a STATE.json (+ optional sentinel db + the
    real seed tarball) and point setup.HERE at <root>."""
    state = os.path.join(root, "checkouts", "current", "state")
    os.makedirs(state, exist_ok=True)
    with open(os.path.join(state, "STATE.json"), "w") as fh:
        fh.write('{"expect_tables": %s}' % (list(expect or [])).__repr__().replace("'", '"'))
    if os.path.isfile(REAL_TARBALL):
        shutil.copy(REAL_TARBALL, os.path.join(state, "database.tar.xz"))
    if with_db:
        con = sqlite3.connect(os.path.join(state, "congruency.sqlite"))
        con.execute("CREATE TABLE tickets(id INTEGER PRIMARY KEY, note TEXT)")
        con.execute("INSERT INTO tickets(note) VALUES (?)", (SENTINEL,))
        con.commit(); con.close()
    setup.HERE = root
    return state


def sentinel_present(state):
    db = os.path.join(state, "congruency.sqlite")
    if not os.path.isfile(db):
        return False
    con = sqlite3.connect(db)
    try:
        return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tickets'").fetchall()) and \
            con.execute("SELECT count(*) FROM tickets WHERE note=?", (SENTINEL,)).fetchone()[0] == 1
    except sqlite3.Error:
        return False
    finally:
        con.close()


def main():
    orig_here = setup.HERE
    try:
        # 1. PRESERVE: an existing db with a sentinel row survives do_state(preserve_db=True)
        with tempfile.TemporaryDirectory() as t:
            state = build_state(t, with_db=True, expect=[])
            res = setup.do_state("4.089", preserve_db=True)
            check("preserve_db=True keeps the existing live db (sentinel survives)", sentinel_present(state))
            check("preserve path reports preserved=True, no extract", res.get("preserved") is True)

        # 2. GUARD PROOF: preserve_db=False still wipes (extracts the seed over it) — this is exactly
        #    the destructive behavior the guard protects against, so it MUST still happen when off.
        with tempfile.TemporaryDirectory() as t:
            state = build_state(t, with_db=True, expect=[])
            if os.path.isfile(REAL_TARBALL):
                setup.do_state("4.089", preserve_db=False)
                check("preserve_db=False extracts the seed (sentinel gone — proves the guard is load-bearing)",
                      not sentinel_present(state))
            else:
                check("real seed tarball available for the guard-proof check", False)

        # 3. FRESH INSTALL: no db present -> extract the seed even with preserve_db on (real CMS tables land)
        with tempfile.TemporaryDirectory() as t:
            state = build_state(t, with_db=False, expect=["Products", "orders"])
            if os.path.isfile(REAL_TARBALL):
                res = setup.do_state("4.089", preserve_db=True)
                check("fresh install (no db) still extracts the seed", res.get("preserved") is False)
                check("extracted seed carries the CMS tables (Products, orders)",
                      {"Products", "orders"}.issubset(set(res.get("tables", []))))
            else:
                check("real seed tarball available for the fresh-install check", False)

        # 4. uninstall can no longer purge the live db (removed from RUNTIME_PATHS)
        check("congruency.sqlite is NOT in RUNTIME_PATHS (uninstall won't wipe state)",
              "checkouts/current/state/congruency.sqlite" not in setup.RUNTIME_PATHS)
    finally:
        setup.HERE = orig_here

    ok = all(v for _, v in checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(v for _, v in checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
