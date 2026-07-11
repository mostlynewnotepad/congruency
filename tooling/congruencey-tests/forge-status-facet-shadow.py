#!/usr/bin/env python3
# forge-status-facet-shadow.py -- the ForgeView invocator gains a STATUS facet
# (?page=forge&status=<status>) filtering the actions journal to one status, bound as :status.
#   (filter) ?status=<s> returns ONLY actions with that status -- teeth: an ok-only target renders
#     under ?status=ok but must be hidden under ?status=fail (a non-filtering renderer leaks it).
#   (escape-first) EVERY forge value rendered stays htmlspecialchars()'d.
#   (read-only) the reflection opens forge.db with PRAGMA query_only=1 and only SELECTs, so the
#     forge db row count is UNCHANGED after a faceted render.
# Isolation: a throwaway forge.db + PHP harness under a TemporaryDirectory (FORGE_DB pointed at it);
# the live forge db, the live congruency db, and the repo are never touched.
import os
import sys
import subprocess
import tempfile
import sqlite3
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
INVOC = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "ForgeView.php")

checks = []
def check(name, ok):
    checks.append(bool(ok))
    print("  %s %s" % ("\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m", name))


def actions_count(db):
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
    con.close()
    return n


def harness(t, name, getarr):
    p = os.path.join(t, name)
    with open(p, "w") as fh:
        fh.write(textwrap.dedent('''\
            <?php
            error_reporting(E_ERROR | E_PARSE);
            ini_set('display_errors', '0');
            interface Tag_Interface { public function get_document(); }
            class ArgStub { public function pop() { return null; } }
            require %r;
            $_GET = %s;
            $t = new ForgeView(new ArgStub());
            echo $t->get_document();
        ''') % (INVOC, getarr))
    return p


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
                    ("2026-07-10T00:00:00", "run-1", "forge", "seed.run", "ok-only-target", "ok", "ok detail"))
        con.execute("INSERT INTO actions (ts, run_id, actor, action, target, status, detail) VALUES (?,?,?,?,?,?,?)",
                    ("2026-07-10T00:02:00", "run-2", "forge", "xss.try", "fail-target", "fail", "<<<Evil>>><script>alert(1)</script>"))
        con.commit(); con.close()

        before = actions_count(fdb)
        env = dict(os.environ)
        env["FORGE_DB"] = fdb

        def render(name, getarr):
            return subprocess.run([PHP, harness(t, name, getarr)], capture_output=True, text=True, timeout=60, env=env).stdout

        out_fail = render("fail.php", "array('page' => 'forge', 'status' => 'fail')")
        out_ok = render("ok.php", "array('page' => 'forge', 'status' => 'ok')")
        after = actions_count(fdb)

        check("status facet filters actions to the bound status (fail shows fail-target, hides the ok-only target)",
              ("fail-target" in out_fail) and ("ok-only-target" not in out_fail))
        check("shadow has teeth: the ok-only target renders under ?status=ok (so its absence above is filtering)",
              "ok-only-target" in out_ok)
        check("forge data is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out_fail) and ("<<<Evil>>>" not in out_fail)
              and ("&lt;script&gt;" in out_fail) and ("<script>" not in out_fail))
        check("the status facet never writes to forge.db (read-only)",
              before == after)

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
