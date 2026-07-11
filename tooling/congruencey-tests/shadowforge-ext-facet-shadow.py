#!/usr/bin/env python3
# shadowforge-ext-facet-shadow.py -- the ShadowForge deficit backlog gains an EXTENSION facet
# (?page=shadowforge&ext=<ext>) filtering deficits by file extension via a NULL-safe LEFT JOIN to
# sf_file, bound as :ext.
#   (filter) ?ext=<e> returns ONLY deficits for files of that extension -- teeth: an md deficit renders
#     under ?ext=md but must be hidden under ?ext=py (a non-filtering renderer leaks it).
#   (escape-first) EVERY deficit path stays htmlspecialchars()'d.
#   (read-only) the reflection opens shadow_index.db with PRAGMA query_only=1 and only SELECTs, so the
#     deficit row count is UNCHANGED after a faceted render.
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
        con.execute("INSERT INTO sf_file VALUES (?,?,?,?,?,?,?)", ("s1", "src/a.py", "repoA", "py", 0, 0, ""))
        con.execute("INSERT INTO sf_file VALUES (?,?,?,?,?,?,?)", ("s2", "docs/x.md", "repoA", "md", 0, 0, ""))
        con.execute("INSERT INTO sf_file VALUES (?,?,?,?,?,?,?)", ("s3", evil, "repoA", "py", 0, 0, ""))
        con.execute("INSERT INTO sf_deficit VALUES (?,?,?,?)", ("src/a.py", "repoA", "no-test", "no test for a"))
        con.execute("INSERT INTO sf_deficit VALUES (?,?,?,?)", ("docs/x.md", "repoA", "no-spec", "no spec for x"))
        con.execute("INSERT INTO sf_deficit VALUES (?,?,?,?)", (evil, "repoA", "no-test", "evil path deficit"))
        con.commit(); con.close()

        before = deficit_count(sdb)
        env = dict(os.environ)
        env["SHADOW_FORGE_DB"] = sdb

        def render(getarr):
            hp = os.path.join(t, "render.php")
            with open(hp, "w") as fh:
                fh.write(harness_tpl.replace("__INVOC__", INVOC).replace("__GET__", getarr))
            return subprocess.run([PHP, hp], capture_output=True, text=True, timeout=60, env=env).stdout

        out_py = render("array('ext' => 'py')")
        out_md = render("array('ext' => 'md')")
        after = deficit_count(sdb)

        check("ext facet filters deficits by file extension (py shows src/a.py, hides the md deficit)",
              ("src/a.py" in out_py) and ("docs/x.md" not in out_py))
        check("shadow has teeth: the md deficit renders under ?ext=md (so its absence above is filtering)",
              "docs/x.md" in out_md)
        check("shadow-forge deficit path is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out_py) and ("<<<Evil>>>" not in out_py)
              and ("&lt;script&gt;" in out_py) and ("<script>" not in out_py))
        check("the ext facet never writes to the index (read-only)",
              before == after)

    ok = all(checks)
    print("")
    print(("PASS" if ok else "FAIL") + "  (" + str(sum(checks)) + "/" + str(len(checks)) + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
