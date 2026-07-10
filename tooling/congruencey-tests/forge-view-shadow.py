#!/usr/bin/env python3
# forge-view-shadow.py — the ForgeView invocator (?page=forge) reflects forge's OWN sqlite
# (~/bin/config/forge/forge.db, a SEPARATE db from CONGRUENCY_SQLITE) read-only: the append-only
# actions journal + the content-addressed artifacts registry. Two invariants, both two-sided:
#   (escape-first) EVERY forge value rendered is htmlspecialchars()'d, so a stored <<<Tag>>> /
#     <script> in an action detail stays inert -- teeth: a non-escaping renderer leaks the raw <<<.
#   (read-only) the reflection opens forge.db with PRAGMA query_only=1 and only SELECTs, so the
#     forge db row count is UNCHANGED after a render -- the page can never mutate forge.
# Isolation: a throwaway forge.db + PHP harnesses under a TemporaryDirectory (FORGE_DB pointed at
# it); the live forge db, the live congruency db, and the repo are never touched.
import os
import sys
import subprocess
import tempfile
import sqlite3
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
INVOC = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "ForgeView.php")

checks = []
def check(name, ok):
    checks.append(bool(ok))
    print("  %s %s" % ("\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m", name))


def counts(db):
    con = sqlite3.connect(db)
    a = con.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
    b = con.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    con.close()
    return (a, b)


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  \033[31m✗ FAIL\033[0m php-not-provisioned")
        return 1

    with tempfile.TemporaryDirectory() as t:
        fdb = os.path.join(t, "forge.db")
        con = sqlite3.connect(fdb)
        con.execute("CREATE TABLE actions (id INTEGER PRIMARY KEY, ts TEXT, run_id TEXT, actor TEXT, action TEXT, target TEXT, status TEXT, detail TEXT, meta TEXT, duration_ms INTEGER, exit_code INTEGER, git_sha TEXT, version TEXT)")
        con.execute("CREATE TABLE artifacts (id INTEGER PRIMARY KEY, ts TEXT, name TEXT, version TEXT, sha256 TEXT, kind TEXT, size INTEGER, filename TEXT, source_repo TEXT, source_commit TEXT, meta TEXT)")
        con.execute("INSERT INTO actions (ts, run_id, actor, action, target, status, detail) VALUES (?,?,?,?,?,?,?)",
                    ("2026-07-10T00:00:00", "run-1", "forge", "seed.run", "alpha", "ok", "seeded"))
        con.execute("INSERT INTO actions (ts, run_id, actor, action, target, status, detail) VALUES (?,?,?,?,?,?,?)",
                    ("2026-07-10T00:01:00", "run-1", "forge", "xss.try", "beta-target", "fail", "<<<Evil>>><script>alert(1)</script>"))
        con.execute("INSERT INTO artifacts (ts, name, version, sha256, kind, size, source_repo, source_commit) VALUES (?,?,?,?,?,?,?,?)",
                    ("2026-07-10T00:02:00", "omni-corpus", "1", "abcdef012345aabbcc", "tar", 4096, "jazz-forge", "deadbeefcafe0011"))
        con.commit(); con.close()

        before = counts(fdb)

        harness = os.path.join(t, "render.php")
        with open(harness, "w") as fh:
            fh.write(textwrap.dedent('''\
                <?php
                error_reporting(E_ERROR | E_PARSE);
                ini_set('display_errors', '0');
                interface Tag_Interface { public function get_document(); }
                class ArgStub { public function pop() { return null; } }
                require %r;
                $_GET = array();
                $t = new ForgeView(new ArgStub());
                echo $t->get_document();
            ''') % (INVOC,))

        env = dict(os.environ)
        env["FORGE_DB"] = fdb
        out = subprocess.run([PHP, harness], capture_output=True, text=True, timeout=60, env=env).stdout

        after = counts(fdb)

        check("recent actions render includes the action and target",
              ("xss.try" in out) and ("beta-target" in out))
        check("forge data is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out) and ("<<<Evil>>>" not in out)
              and ("&lt;script&gt;" in out) and ("<script>" not in out))
        check("the forge reflection never writes to forge.db (read-only)",
              before == after)

        # teeth: a non-escaping renderer echoes the RAW forge detail, leaking the live <<<Tag>>> --
        # the shadow must catch such a renderer (two-sided arena discipline).
        bad = os.path.join(t, "raw.php")
        with open(bad, "w") as fh:
            fh.write(textwrap.dedent('''\
                <?php
                $db = new PDO('sqlite:' . %r);
                $row = $db->query("SELECT detail FROM actions ORDER BY id DESC LIMIT 1")->fetch(PDO::FETCH_ASSOC);
                echo $row['detail'];
            ''') % (fdb,))
        badout = subprocess.run([PHP, bad], capture_output=True, text=True, timeout=60).stdout

        check("shadow has teeth: a non-escaping renderer leaks the raw <<<",
              "<<<Evil>>>" in badout)

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
