#!/usr/bin/env python3
# shadowforge-shadow-facet-shadow.py -- the ShadowForge invocator gains an inverse SHADOW facet
# (?page=shadowforge&shadow=<name>) listing every file a shadow-doc covers, bound as :shadow.
#   (filter) ?shadow=<name> returns ONLY files covered by that shadow-doc -- teeth: a file covered by
#     a different shadow renders under its own ?shadow but is hidden here (non-filtering renderer leaks it).
#   (escape-first) EVERY covered-file path stays htmlspecialchars()'d.
#   (read-only) the reflection opens shadow_index.db with PRAGMA query_only=1 and only SELECTs, so the
#     sf_shadow row count is UNCHANGED after a faceted render.
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


def shadow_count(db):
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM sf_shadow").fetchone()[0]
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
        con.execute("INSERT INTO sf_shadow VALUES (?,?,?,?)", ("test/cov_test.py", "sh1", "src/a.py", "[]"))
        con.execute("INSERT INTO sf_shadow VALUES (?,?,?,?)", ("test/cov_test.py", "sh1", evil, "[]"))
        con.execute("INSERT INTO sf_shadow VALUES (?,?,?,?)", ("test/other_test.py", "sh2", "src/only-other.py", "[]"))
        con.commit(); con.close()

        before = shadow_count(sdb)
        env = dict(os.environ)
        env["SHADOW_FORGE_DB"] = sdb

        def render(getarr):
            hp = os.path.join(t, "render.php")
            with open(hp, "w") as fh:
                fh.write(harness_tpl.replace("__INVOC__", INVOC).replace("__GET__", getarr))
            return subprocess.run([PHP, hp], capture_output=True, text=True, timeout=60, env=env).stdout

        out_cov = render("array('shadow' => 'test/cov_test.py')")
        out_other = render("array('shadow' => 'test/other_test.py')")
        after = shadow_count(sdb)

        check("shadow facet lists files covered by the bound shadow-doc (cov shows src/a.py, hides only-other)",
              ("src/a.py" in out_cov) and ("src/only-other.py" not in out_cov))
        check("shadow has teeth: only-other renders under its own ?shadow (so its absence above is filtering)",
              "src/only-other.py" in out_other)
        check("shadow-forge covered-file path is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out_cov) and ("<<<Evil>>>" not in out_cov)
              and ("&lt;script&gt;" in out_cov) and ("<script>" not in out_cov))
        check("the shadow facet never writes to the index (read-only)",
              before == after)

    ok = all(checks)
    print("")
    print(("PASS" if ok else "FAIL") + "  (" + str(sum(checks)) + "/" + str(len(checks)) + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
