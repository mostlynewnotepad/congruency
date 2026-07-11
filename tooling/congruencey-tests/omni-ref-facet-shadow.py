#!/usr/bin/env python3
# omni-ref-facet-shadow.py -- the OmniExplorer invocator gains a REF facet (?page=omni&ref=<ref>)
# that lists every (path, repo) on one git ref/branch, bound as :ref.
#   (filter) ?ref=<ref> returns ONLY files on that ref -- teeth: a file only on another branch renders
#     under its own ?ref but must be hidden here (a non-filtering renderer leaks it).
#   (escape-first) EVERY omni value rendered stays htmlspecialchars()'d.
#   (read-only) the reflection opens omni_index.db with PRAGMA query_only=1 and only SELECTs, so the
#     index row count is UNCHANGED after a faceted render.
# Isolation: a throwaway omni_index.db + PHP harness under a TemporaryDirectory (OMNI_INDEX_DB
# pointed at it); the live index, the live congruency db, and the repo are never touched.
import os
import sys
import subprocess
import tempfile
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
INVOC = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "OmniExplorer.php")

harness_tpl = '''<?php
error_reporting(E_ERROR | E_PARSE);
ini_set('display_errors', '0');
interface Tag_Interface { public function get_document(); }
class ArgStub { public function pop() { return null; } }
require '__INVOC__';
$_GET = __GET__;
$t = new OmniExplorer(new ArgStub());
echo $t->get_document();
'''

checks = []
def check(name, ok):
    checks.append(bool(ok))
    mark = "\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m"
    print("  " + mark + " " + name)


def occ_count(db):
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM occ").fetchone()[0]
    con.close()
    return n


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  \033[31m✗ FAIL\033[0m php-not-provisioned")
        return 1

    main_ref = "refs/heads/main"
    dev_ref = "refs/heads/dev"

    with tempfile.TemporaryDirectory() as t:
        odb = os.path.join(t, "omni_index.db")
        con = sqlite3.connect(odb)
        con.execute("CREATE TABLE occ (sha TEXT, path TEXT, ext TEXT, size INTEGER, ref TEXT, repo TEXT, ts TEXT)")
        con.execute("CREATE TABLE blob (sha TEXT PRIMARY KEY, path TEXT, ext TEXT, size INTEGER, is_text INTEGER)")
        evil = "<<<Evil>>><script>alert(1)</script>"
        rows = [
            ("aaaa1", "src/app.py", "py", 100, main_ref, "repoA", "2026-07-01T00:00:00"),
            ("bbbb2", evil, "", 7, main_ref, "repoA", "2026-07-01T00:00:00"),
            ("cccc3", "lib/dev-only.py", "py", 120, dev_ref, "repoB", "2026-07-02T00:00:00"),
        ]
        for r in rows:
            con.execute("INSERT INTO occ (sha, path, ext, size, ref, repo, ts) VALUES (?,?,?,?,?,?,?)", r)
        con.commit(); con.close()

        before = occ_count(odb)
        env = dict(os.environ)
        env["OMNI_INDEX_DB"] = odb

        def render(getarr):
            hp = os.path.join(t, "render.php")
            phpsrc = harness_tpl.replace("__INVOC__", INVOC).replace("__GET__", getarr)
            with open(hp, "w") as fh:
                fh.write(phpsrc)
            return subprocess.run([PHP, hp], capture_output=True, text=True, timeout=60, env=env).stdout

        out_main = render("array('ref' => '%s')" % main_ref)
        out_dev = render("array('ref' => '%s')" % dev_ref)
        after = occ_count(odb)

        check("ref facet filters files to the bound ref (main shows src/app.py, hides the dev-only path)",
              ("src/app.py" in out_main) and ("lib/dev-only.py" not in out_main))
        check("shadow has teeth: the dev-only path renders under ?ref=dev (so its absence above is filtering)",
              "lib/dev-only.py" in out_dev)
        check("omni path data is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out_main) and ("<<<Evil>>>" not in out_main)
              and ("&lt;script&gt;" in out_main) and ("<script>" not in out_main))
        check("the ref facet never writes to the index (read-only)",
              before == after)

    ok = all(checks)
    print("")
    print(("PASS" if ok else "FAIL") + "  (" + str(sum(checks)) + "/" + str(len(checks)) + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
