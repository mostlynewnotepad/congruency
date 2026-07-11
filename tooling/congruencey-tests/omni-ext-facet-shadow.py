#!/usr/bin/env python3
# omni-ext-facet-shadow.py -- the OmniExplorer invocator gains an EXTENSION facet
# (?page=omni&ext=<extension>) that lists files carrying one extension across repos, bound as :ext.
#   (filter) ?ext=<ext> returns ONLY files of that extension -- teeth: an md-only path renders under
#     ?ext=md but must be hidden under ?ext=py (a non-filtering renderer leaks it).
#   (escape-first) EVERY omni value rendered stays htmlspecialchars()'d, so a stored <<<Tag>>> /
#     <script> in a path is inert.
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

    with tempfile.TemporaryDirectory() as t:
        odb = os.path.join(t, "omni_index.db")
        con = sqlite3.connect(odb)
        con.execute("CREATE TABLE occ (sha TEXT, path TEXT, ext TEXT, size INTEGER, ref TEXT, repo TEXT, ts TEXT)")
        con.execute("CREATE TABLE blob (sha TEXT PRIMARY KEY, path TEXT, ext TEXT, size INTEGER, is_text INTEGER)")
        evil = "<<<Evil>>><script>alert(1)</script>"
        rows = [
            ("aaaa1", "src/app.py", "py", 100, "refs/heads/main", "repoA", "2026-07-01T00:00:00"),
            ("bbbb2", "lib/util.py", "py", 120, "refs/heads/main", "repoB", "2026-07-02T00:00:00"),
            ("cccc3", "docs/readme.md", "md", 50, "refs/heads/main", "repoA", "2026-07-03T00:00:00"),
            ("dddd4", evil, "py", 7, "refs/heads/main", "repoC", "2026-07-04T00:00:00"),
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

        out_py = render("array('ext' => 'py')")
        out_md = render("array('ext' => 'md')")

        after = occ_count(odb)

        check("ext facet filters files to the bound extension (py shows lib/util.py, hides the md-only path)",
              ("lib/util.py" in out_py) and ("docs/readme.md" not in out_py))
        check("shadow has teeth: the md-only path renders under ?ext=md (so its absence above is filtering)",
              "docs/readme.md" in out_md)
        check("omni path data is htmlspecialchars-escaped (escape-first)",
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
