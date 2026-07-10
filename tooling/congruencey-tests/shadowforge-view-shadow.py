#!/usr/bin/env python3
# shadowforge-view-shadow.py — the ShadowForge invocator (?page=shadowforge) reflects the SHADOW FORGE
# index (~/bin/config/forge/shadow_forge/shadow_index.db, a SEPARATE db from CONGRUENCY_SQLITE)
# read-only: sf_deficit is the spec/test backlog (files with no-test and/or no-spec). Invariants:
#   (deficit backlog) the default page lists the deficit rows.
#   (facet, omitted-other) ?reason=no-spec (repo OMITTED) returns ONLY the no-spec row -- proving the
#     NULL-safe COALESCE(:x,'')='' optional-facet guard AND that omitting the other facet still filters.
#   (escape-first) EVERY shadow-forge value rendered is htmlspecialchars()'d, so a stored <<<Tag>>> /
#     <script> in a deficit path stays inert -- teeth: a non-escaping renderer leaks the raw <<<.
#   (read-only) the reflection opens shadow_index.db with PRAGMA query_only=1 and only SELECTs, so the
#     row count is UNCHANGED after a render -- the page can never mutate the shadow index.
# Isolation: a throwaway shadow_index.db + PHP harnesses under a TemporaryDirectory (SHADOW_FORGE_DB
# pointed at it); the live index, the live congruency db, and the repo are never touched.
import os
import sys
import subprocess
import tempfile
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
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

raw_tpl = '''<?php
$db = new PDO('sqlite:' . '__SDB__');
$row = $db->query("SELECT path FROM sf_deficit WHERE path LIKE '%Evil%' LIMIT 1")->fetch(PDO::FETCH_ASSOC);
echo $row['path'];
'''

checks = []
def check(name, ok):
    checks.append(bool(ok))
    mark = "✓" if ok else "✗ FAIL"
    print("  " + mark + " " + name)


def deficit_count(db):
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM sf_deficit").fetchone()[0]
    con.close()
    return n


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  ✗ FAIL php-not-provisioned")
        return 1

    with tempfile.TemporaryDirectory() as t:
        sdb = os.path.join(t, "shadow_index.db")
        con = sqlite3.connect(sdb)
        con.execute("CREATE TABLE sf_file (sha TEXT, path TEXT, repo TEXT, ext TEXT, is_shadow INTEGER, cites_spec INTEGER, spec_refs TEXT)")
        con.execute("CREATE TABLE sf_shadow (shadow TEXT, shadow_sha TEXT, covers TEXT, spec_refs TEXT)")
        con.execute("CREATE TABLE sf_deficit (path TEXT, repo TEXT, reason TEXT, detail TEXT)")
        # sf_file: one spec-cited exemplar, one plain non-shadow file, one shadow-doc file
        con.execute("INSERT INTO sf_file VALUES (?,?,?,?,?,?,?)",
                    ("sha1", "src/cited.py", "repoA", "py", 0, 1, '[\"RFC-0030\"]'))
        con.execute("INSERT INTO sf_file VALUES (?,?,?,?,?,?,?)",
                    ("sha2", "src/plain.py", "repoB", "py", 0, 0, ""))
        con.execute("INSERT INTO sf_file VALUES (?,?,?,?,?,?,?)",
                    ("sha3", "test/cited_test.py", "repoA", "py", 1, 0, ""))
        # a shadow-doc covers the cited file
        con.execute("INSERT INTO sf_shadow VALUES (?,?,?,?)",
                    ("test/cited_test.py", "sha3", "src/cited.py", '[\"RFC-0030\"]'))
        # deficits: two reasons (no-test, no-spec); the no-spec row is the ONLY no-spec, so a
        # ?reason=no-spec facet (repo omitted) must return it ALONE. one path carries a live
        # <<<Tag>>> / <script> -> must be ESCAPED when rendered.
        evil = "<<<Evil>>><script>alert(1)</script>"
        con.execute("INSERT INTO sf_deficit VALUES (?,?,?,?)",
                    ("src/a.py", "repoA", "no-test", "no test for a"))
        con.execute("INSERT INTO sf_deficit VALUES (?,?,?,?)",
                    (evil, "repoA", "no-test", "evil path deficit"))
        con.execute("INSERT INTO sf_deficit VALUES (?,?,?,?)",
                    ("src/b.py", "repoB", "no-spec", "no spec for b"))
        con.commit(); con.close()

        before = deficit_count(sdb)

        env = dict(os.environ)
        env["SHADOW_FORGE_DB"] = sdb

        def render(getarr):
            hp = os.path.join(t, "render.php")
            src = harness_tpl.replace("__INVOC__", INVOC).replace("__GET__", getarr)
            with open(hp, "w") as fh:
                fh.write(src)
            return subprocess.run([PHP, hp], capture_output=True, text=True, timeout=60, env=env).stdout

        out_default = render("array()")
        out_reason  = render("array('reason' => 'no-spec')")

        after = deficit_count(sdb)

        check("deficit backlog lists the rows",
              ("src/a.py" in out_default) and ("src/b.py" in out_default))
        check("the reason facet returns only matching deficits when the other facet is omitted",
              ("src/b.py" in out_reason) and ("src/a.py" not in out_reason))
        check("shadow-forge output is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out_default) and ("<<<Evil>>>" not in out_default)
              and ("&lt;script&gt;" in out_default) and ("<script>" not in out_default))
        check("the shadow forge view never writes to the index (read-only)",
              before == after)

        # teeth: a non-escaping renderer echoes the RAW deficit path, leaking the live <<<Tag>>> --
        # the shadow must catch such a renderer (two-sided arena discipline).
        bp = os.path.join(t, "raw.php")
        with open(bp, "w") as fh:
            fh.write(raw_tpl.replace("__SDB__", sdb))
        badout = subprocess.run([PHP, bp], capture_output=True, text=True, timeout=60).stdout

        check("shadow has teeth: a non-escaping renderer leaks the raw <<<",
              "<<<Evil>>>" in badout)

    ok = all(checks)
    print("")
    print(("PASS" if ok else "FAIL") + "  (" + str(sum(checks)) + "/" + str(len(checks)) + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
