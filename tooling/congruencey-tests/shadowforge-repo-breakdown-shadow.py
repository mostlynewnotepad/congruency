#!/usr/bin/env python3
# shadowforge-repo-breakdown-shadow.py -- the ShadowForge summary gains a per-repo deficit breakdown,
# symmetric to the existing by-reason line: each repo links to the bound ?repo= facet with its count.
#   (correct counts) the breakdown is GROUP BY repo over sf_deficit -- teeth: repoA (2 deficits) and
#     the second repo (1 deficit) render with their OWN counts, not a constant.
#   (bound link) each repo links to ?page=shadowforge&repo=<repo> (urlencoded).
#   (escape-first) a stored <<<Tag>>> / <script> in a repo name stays htmlspecialchars()'d.
#   (read-only) the reflection opens shadow_index.db with PRAGMA query_only=1 and only SELECTs, so the
#     deficit row count is UNCHANGED after a render.
# Isolation: a throwaway shadow_index.db + PHP harness under a TemporaryDirectory (SHADOW_FORGE_DB
# pointed at it); the live index, the live congruency db, and the repo are never touched.
import os
import sys
import subprocess
import tempfile
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
INVOC = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "ShadowForge.php")

harness_tpl = '''<?php
error_reporting(E_ERROR | E_PARSE);
ini_set('display_errors', '0');
interface Tag_Interface { public function get_document(); }
class ArgStub { public function pop() { return null; } }
require '__INVOC__';
$_GET = __GET__;
$t = new ShadowForge(new ArgStub());
echo $t->get_document();
'''

checks = []
def check(name, ok):
    checks.append(bool(ok))
    mark = "\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m"
    print("  " + mark + " " + name)


def deficit_count(db):
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM sf_deficit").fetchone()[0]
    con.close()
    return n


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  \033[31m✗ FAIL\033[0m php-not-provisioned")
        return 1

    evil = "<<<Evil>>><script>alert(1)</script>"

    with tempfile.TemporaryDirectory() as t:
        sdb = os.path.join(t, "shadow_index.db")
        con = sqlite3.connect(sdb)
        con.execute("CREATE TABLE sf_file (sha TEXT, path TEXT, repo TEXT, ext TEXT, is_shadow INTEGER, cites_spec INTEGER, spec_refs TEXT)")
        con.execute("CREATE TABLE sf_shadow (shadow TEXT, shadow_sha TEXT, covers TEXT, spec_refs TEXT)")
        con.execute("CREATE TABLE sf_deficit (path TEXT, repo TEXT, reason TEXT, detail TEXT)")
        con.execute("INSERT INTO sf_deficit VALUES (?,?,?,?)", ("src/a.py", "repoA", "no-test", "no test for a"))
        con.execute("INSERT INTO sf_deficit VALUES (?,?,?,?)", ("src/a2.py", "repoA", "no-spec", "no spec for a2"))
        con.execute("INSERT INTO sf_deficit VALUES (?,?,?,?)", ("src/b.py", evil, "no-test", "evil repo deficit"))
        con.commit(); con.close()

        before = deficit_count(sdb)
        env = dict(os.environ)
        env["SHADOW_FORGE_DB"] = sdb

        hp = os.path.join(t, "render.php")
        with open(hp, "w") as fh:
            fh.write(harness_tpl.replace("__INVOC__", INVOC).replace("__GET__", "array()"))
        out = subprocess.run([PHP, hp], capture_output=True, text=True, timeout=60, env=env).stdout

        after = deficit_count(sdb)

        check("by-repo breakdown links each repo to its bound ?repo= facet with the correct count (repoA=2)",
              "<a href='?page=shadowforge&repo=repoA'>repoA</a>&nbsp;2" in out)
        check("shadow has teeth: the counts are per-repo, not constant (the second repo shows count 1)",
              "</a>&nbsp;1" in out)
        check("shadow-forge repo name is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out) and ("<<<Evil>>>" not in out)
              and ("&lt;script&gt;" in out) and ("<script>" not in out))
        check("the shadow forge view never writes to the index (read-only)",
              before == after)

    ok = all(checks)
    print("")
    print(("PASS" if ok else "FAIL") + "  (" + str(sum(checks)) + "/" + str(len(checks)) + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
