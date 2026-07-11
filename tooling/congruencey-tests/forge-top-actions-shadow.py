#!/usr/bin/env python3
# forge-top-actions-shadow.py -- the ForgeView summary gains a top-actions breakdown: the most
# frequent action verbs, each linking to the bound ?action= facet with its count.
#   (correct counts) GROUP BY action over actions -- teeth: seed.run (2) and a second verb (1) render
#     with their OWN counts, not a constant.
#   (bound link) each verb links to ?page=forge&action=<verb> (urlencoded).
#   (escape-first) a stored <<<Tag>>> / <script> in an action verb stays htmlspecialchars()'d.
#   (read-only) the reflection opens forge.db with PRAGMA query_only=1 and only SELECTs, so the forge
#     db row count is UNCHANGED after a render.
# Isolation: a throwaway forge.db + PHP harness under a TemporaryDirectory (FORGE_DB pointed at it);
# the live forge db, the live congruency db, and the repo are never touched.
import os
import sys
import subprocess
import tempfile
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
INVOC = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "ForgeView.php")

harness_tpl = '''<?php
error_reporting(E_ERROR | E_PARSE);
ini_set('display_errors', '0');
interface Tag_Interface { public function get_document(); }
class ArgStub { public function pop() { return null; } }
require '__INVOC__';
$_GET = __GET__;
$t = new ForgeView(new ArgStub());
echo $t->get_document();
'''

checks = []
def check(name, ok):
    checks.append(bool(ok))
    mark = "\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m"
    print("  " + mark + " " + name)


def actions_count(db):
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
    con.close()
    return n


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  \033[31m✗ FAIL\033[0m php-not-provisioned")
        return 1

    evil = "<<<Evil>>><script>alert(1)</script>"

    with tempfile.TemporaryDirectory() as t:
        fdb = os.path.join(t, "forge.db")
        con = sqlite3.connect(fdb)
        con.execute("CREATE TABLE actions (id INTEGER PRIMARY KEY, ts TEXT, run_id TEXT, actor TEXT, action TEXT, target TEXT, status TEXT, detail TEXT, meta TEXT, duration_ms INTEGER, exit_code INTEGER, git_sha TEXT, version TEXT)")
        con.execute("CREATE TABLE artifacts (id INTEGER PRIMARY KEY, ts TEXT, name TEXT, version TEXT, sha256 TEXT, kind TEXT, size INTEGER, filename TEXT, source_repo TEXT, source_commit TEXT, meta TEXT)")
        con.execute("INSERT INTO actions (ts, run_id, action, target, status, detail) VALUES (?,?,?,?,?,?)", ("2026-07-10T00:00:00", "r1", "seed.run", "t1", "ok", "d"))
        con.execute("INSERT INTO actions (ts, run_id, action, target, status, detail) VALUES (?,?,?,?,?,?)", ("2026-07-10T00:01:00", "r1", "seed.run", "t2", "ok", "d"))
        con.execute("INSERT INTO actions (ts, run_id, action, target, status, detail) VALUES (?,?,?,?,?,?)", ("2026-07-10T00:02:00", "r2", evil, "t3", "fail", "d"))
        con.commit(); con.close()

        before = actions_count(fdb)
        env = dict(os.environ)
        env["FORGE_DB"] = fdb

        hp = os.path.join(t, "render.php")
        with open(hp, "w") as fh:
            fh.write(harness_tpl.replace("__INVOC__", INVOC).replace("__GET__", "array()"))
        out = subprocess.run([PHP, hp], capture_output=True, text=True, timeout=60, env=env).stdout

        after = actions_count(fdb)

        check("top-actions breakdown links each verb to its bound ?action= facet with the correct count (seed.run=2)",
              "<a href='?page=forge&action=seed.run'>seed.run</a>&nbsp;2" in out)
        check("shadow has teeth: the counts are per-verb, not constant (the second verb shows count 1)",
              "</a>&nbsp;1" in out)
        check("forge action verb is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out) and ("<<<Evil>>>" not in out)
              and ("&lt;script&gt;" in out) and ("<script>" not in out))
        check("the forge view never writes to forge.db (read-only)",
              before == after)

    ok = all(checks)
    print("")
    print(("PASS" if ok else "FAIL") + "  (" + str(sum(checks)) + "/" + str(len(checks)) + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
