#!/usr/bin/env python3
# omni-explorer-shadow.py — the OmniExplorer invocator (?page=omni) reflects the omni-git INDEX
# (~/bin/config/forge/omni_index.db, a SEPARATE db from CONGRUENCY_SQLITE) read-only: the occ table
# maps each file path to every (repo,ts) OCCURRENCE across snapshots. Three invariants:
#   (file -> repos@times) a path lookup lists every repo/snapshot the file appears in -- teeth via a
#     path present in TWO repos: both must show.
#   (escape-first) EVERY omni value rendered is htmlspecialchars()'d, so a stored <<<Tag>>> /
#     <script> in a path stays inert -- teeth: a non-escaping renderer leaks the raw <<<.
#   (read-only) the reflection opens omni_index.db with PRAGMA query_only=1 and only SELECTs, so the
#     index row count is UNCHANGED after a render -- the page can never mutate the index.
# Isolation: a throwaway omni_index.db + PHP harnesses under a TemporaryDirectory (OMNI_INDEX_DB
# pointed at it); the live index, the live congruency db, and the repo are never touched.
import os
import sys
import subprocess
import tempfile
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
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

raw_tpl = '''<?php
$db = new PDO('sqlite:' . '__ODB__');
$row = $db->query("SELECT path FROM occ WHERE path LIKE '%Evil%' LIMIT 1")->fetch(PDO::FETCH_ASSOC);
echo $row['path'];
'''

checks = []
def check(name, ok):
    checks.append(bool(ok))
    mark = "✓" if ok else "✗ FAIL"
    print("  " + mark + " " + name)


def occ_count(db):
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM occ").fetchone()[0]
    con.close()
    return n


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  ✗ FAIL php-not-provisioned")
        return 1

    with tempfile.TemporaryDirectory() as t:
        odb = os.path.join(t, "omni_index.db")
        con = sqlite3.connect(odb)
        con.execute("CREATE TABLE occ (sha TEXT, path TEXT, ext TEXT, size INTEGER, ref TEXT, repo TEXT, ts TEXT)")
        con.execute("CREATE TABLE blob (sha TEXT PRIMARY KEY, path TEXT, ext TEXT, size INTEGER, is_text INTEGER)")
        con.execute("CREATE INDEX i_occ_sha ON occ(sha)")
        con.execute("CREATE INDEX i_occ_path ON occ(path)")
        con.execute("CREATE INDEX i_occ_repo ON occ(repo)")
        # SAME path 'src/app.py' in TWO repos at different snapshots -> file maps to many (repo,ts)
        con.execute("INSERT INTO occ (sha, path, ext, size, ref, repo, ts) VALUES (?,?,?,?,?,?,?)",
                    ("aaaaaaaaaa1111", "src/app.py", "py", 100, "refs/heads/main", "repoA", "2026-07-01T00:00:00"))
        con.execute("INSERT INTO occ (sha, path, ext, size, ref, repo, ts) VALUES (?,?,?,?,?,?,?)",
                    ("bbbbbbbbbb2222", "src/app.py", "py", 120, "refs/heads/main", "repoB", "2026-07-02T00:00:00"))
        # a path carrying a live <<<Tag>>> / <script> -> must be ESCAPED when rendered
        evil = "<<<Evil>>><script>alert(1)</script>"
        con.execute("INSERT INTO occ (sha, path, ext, size, ref, repo, ts) VALUES (?,?,?,?,?,?,?)",
                    ("cccccccccc3333", evil, "", 7, "refs/heads/main", "repoC", "2026-07-03T00:00:00"))
        con.execute("INSERT INTO blob (sha, path, ext, size, is_text) VALUES (?,?,?,?,?)",
                    ("aaaaaaaaaa1111", "src/app.py", "py", 100, 1))
        con.execute("INSERT INTO blob (sha, path, ext, size, is_text) VALUES (?,?,?,?,?)",
                    ("bbbbbbbbbb2222", "src/app.py", "py", 120, 1))
        con.execute("INSERT INTO blob (sha, path, ext, size, is_text) VALUES (?,?,?,?,?)",
                    ("cccccccccc3333", evil, "", 7, 1))
        con.commit(); con.close()

        before = occ_count(odb)

        env = dict(os.environ)
        env["OMNI_INDEX_DB"] = odb

        def render(getarr):
            hp = os.path.join(t, "render.php")
            src = harness_tpl.replace("__INVOC__", INVOC).replace("__GET__", getarr)
            with open(hp, "w") as fh:
                fh.write(src)
            return subprocess.run([PHP, hp], capture_output=True, text=True, timeout=60, env=env).stdout

        out_path = render("array('path' => 'src/app.py')")
        out_over = render("array()")

        after = occ_count(odb)

        check("path lookup lists every repo/snapshot the file appears in",
              ("repoA" in out_path) and ("repoB" in out_path))
        check("omni data is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out_over) and ("<<<Evil>>>" not in out_over)
              and ("&lt;script&gt;" in out_over) and ("<script>" not in out_over))
        check("the omni explorer never writes to the index (read-only)",
              before == after)

        # teeth: a non-escaping renderer echoes the RAW omni path, leaking the live <<<Tag>>> --
        # the shadow must catch such a renderer (two-sided arena discipline).
        bp = os.path.join(t, "raw.php")
        with open(bp, "w") as fh:
            fh.write(raw_tpl.replace("__ODB__", odb))
        badout = subprocess.run([PHP, bp], capture_output=True, text=True, timeout=60).stdout

        check("shadow has teeth: a non-escaping renderer leaks the raw <<<",
              "<<<Evil>>>" in badout)

    ok = all(checks)
    print("")
    print(("PASS" if ok else "FAIL") + "  (" + str(sum(checks)) + "/" + str(len(checks)) + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
