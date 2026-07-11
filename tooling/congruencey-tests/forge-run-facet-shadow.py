#!/usr/bin/env python3
# forge-run-facet-shadow.py -- the ForgeView invocator gains a RUN facet (?page=forge&run=<run_id>)
# that filters the append-only actions journal to one forge run, bound as :run. Three invariants:
#   (filter) ?page=forge&run=<id> returns ONLY that run's actions; other runs' targets are excluded
#     -- teeth: without the filter every run's target renders (proven by the default view).
#   (escape-first) EVERY forge value rendered stays htmlspecialchars()'d, so a stored <<<Tag>>> /
#     <script> in an action detail is inert.
#   (read-only) the reflection opens forge.db with PRAGMA query_only=1 and only SELECTs, so the
#     forge db row count is UNCHANGED after a faceted render.
# Isolation: a throwaway forge.db + PHP harnesses under a TemporaryDirectory (FORGE_DB pointed at
# it); the live forge db, the live congruency db, and the repo are never touched.
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


def render(harness_path, env):
    return subprocess.run([PHP, harness_path], capture_output=True, text=True, timeout=60, env=env).stdout


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
                    ("2026-07-10T00:00:00", "run-1", "forge", "seed.run", "alpha-only", "ok", "run-1 detail"))
        con.execute("INSERT INTO actions (ts, run_id, actor, action, target, status, detail) VALUES (?,?,?,?,?,?,?)",
                    ("2026-07-10T00:01:00", "run-1", "forge", "build.step", "beta-only", "ok", "run-1 detail"))
        con.execute("INSERT INTO actions (ts, run_id, actor, action, target, status, detail) VALUES (?,?,?,?,?,?,?)",
                    ("2026-07-10T00:02:00", "run-2", "forge", "xss.try", "gamma-target", "fail", "<<<Evil>>><script>alert(1)</script>"))
        con.commit(); con.close()

        before = actions_count(fdb)

        env = dict(os.environ)
        env["FORGE_DB"] = fdb

        # faceted render: run=run-2 -> ONLY run-2's action/target; run-1's targets excluded.
        out = render(harness(t, "facet.php", "array('page' => 'forge', 'run' => 'run-2')"), env)

        after = actions_count(fdb)

        check("run facet filters actions to the bound run_id (other runs' targets excluded)",
              ("gamma-target" in out) and ("alpha-only" not in out) and ("beta-only" not in out))
        check("forge data is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out) and ("<<<Evil>>>" not in out)
              and ("&lt;script&gt;" in out) and ("<script>" not in out))
        check("the run facet never writes to forge.db (read-only)",
              before == after)

        # default (no facet) render -> every run's target present, proving the exclusion above is
        # the facet at work, not an empty table (two-sided teeth: a non-filtering renderer fails
        # the filter check because these very rows DO render without the facet).
        allout = render(harness(t, "default.php", "array('page' => 'forge')"), env)
        check("shadow has teeth: without the run filter every run's target renders (alpha-only + gamma-target)",
              ("alpha-only" in allout) and ("gamma-target" in allout))

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
