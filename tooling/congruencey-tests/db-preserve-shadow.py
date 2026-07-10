#!/usr/bin/env python3
"""db-preserve-shadow.py — the installer must NEVER fabricate/extract a DB over the live one.

The historical data-loss bug: `setup.do_state` extracted a seed `database.tar.xz` over
`state/congruency.sqlite` (a symlink to the live DB), erasing every ticket/memory/api_key. The
source/state split removes ALL seed-extract paths: `do_state` now VERIFIES a present live DB and
KEEPS it (regardless of any flag), HALTS when the DB is absent (restore is explicit, from forge),
and treats a dangling symlink as unsafe. This shadow pins that invariant so re-introducing any
auto-seed / clobber fails the gate loudly.

Isolation: each check runs in its own tempfile state dir with `setup.HERE` monkeypatched. The real
live DB (~/bin/config/congruency/congruency.sqlite) and the repo state dir are NEVER touched.
"""
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
sys.path.insert(0, REPO)
import setup  # noqa: E402  — the installer under test

SENTINEL = "do-not-wipe-me"

checks = []
def check(name, ok):
    checks.append((name, bool(ok)))
    print("  %s %s" % ("\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m", name))


def build_state(root, with_db=False, expect=None):
    """Lay out <root>/checkouts/current/state with a STATE.json (+ optional sentinel db) and point
    setup.HERE at <root>."""
    state = os.path.join(root, "checkouts", "current", "state")
    os.makedirs(state, exist_ok=True)
    with open(os.path.join(state, "STATE.json"), "w") as fh:
        fh.write('{"expect_tables": %s}' % (list(expect or [])).__repr__().replace("'", '"'))
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
        return con.execute("SELECT count(*) FROM tickets WHERE note=?", (SENTINEL,)).fetchone()[0] == 1
    except sqlite3.Error:
        return False
    finally:
        con.close()


def _raises(fn):
    try:
        fn()
        return False
    except Exception:      # noqa: BLE001
        return True


def main():
    orig = setup.HERE
    try:
        # 1. present db + preserve_db=True -> kept (sentinel survives), preserved=True
        with tempfile.TemporaryDirectory() as t:
            state = build_state(t, with_db=True, expect=[])
            res = setup.do_state("x", preserve_db=True)
            check("present db + preserve_db=True: kept (sentinel survives)", sentinel_present(state))
            check("  reports preserved=True (no extract)", res.get("preserved") is True)

        # 2. present db + preserve_db=False -> STILL kept: the flag is no longer a footgun; NEVER clobbers
        with tempfile.TemporaryDirectory() as t:
            state = build_state(t, with_db=True, expect=[])
            setup.do_state("x", preserve_db=False)
            check("present db + preserve_db=False: STILL kept (never clobbers regardless of flag)",
                  sentinel_present(state))

        # 3. absent db -> HALT (refuses to fabricate a seed), even with a decoy tarball present
        with tempfile.TemporaryDirectory() as t:
            state = build_state(t, with_db=False, expect=[])
            open(os.path.join(state, "database.tar.xz"), "wb").close()   # decoy seed
            check("absent db: do_state HALTS (no seed fabricated), even with a tarball present",
                  _raises(lambda: setup.do_state("x", preserve_db=True)))
            check("  nothing extracted — no congruency.sqlite created",
                  not os.path.isfile(os.path.join(state, "congruency.sqlite")))

        # 4. dangling state symlink -> unsafe/absent -> HALT (never write through it)
        with tempfile.TemporaryDirectory() as t:
            state = build_state(t, with_db=False, expect=[])
            os.symlink(os.path.join(t, "no-such-live.sqlite"), os.path.join(state, "congruency.sqlite"))
            check("dangling state symlink: HALTS (never writes through it)",
                  _raises(lambda: setup.do_state("x", preserve_db=True)))

        # 5. uninstall can no longer purge the live db
        check("congruency.sqlite NOT in RUNTIME_PATHS (uninstall won't wipe state)",
              "checkouts/current/state/congruency.sqlite" not in setup.RUNTIME_PATHS)
    finally:
        setup.HERE = orig

    ok = all(v for _, v in checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(v for _, v in checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
