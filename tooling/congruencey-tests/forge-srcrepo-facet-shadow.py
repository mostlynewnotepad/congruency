#!/usr/bin/env python3
# forge-srcrepo-facet-shadow.py -- the ForgeView invocator gains a SOURCE-REPO facet
# (?page=forge&srcrepo=<repo>) filtering the artifacts registry to one source repository, bound as
# :srcrepo.
#   (filter) ?srcrepo=<r> returns ONLY artifacts from that repo -- teeth: an artifact from a different
#     repo renders under its own ?srcrepo but is hidden here (a non-filtering renderer leaks it).
#   (escape-first) EVERY forge value rendered (including source_repo) stays htmlspecialchars()'d.
#   (read-only) the reflection opens forge.db with PRAGMA query_only=1 and only SELECTs, so the forge
#     db row count is UNCHANGED after a faceted render.
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


def artifacts_count(db):
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
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

    evil = "<<<Evil>>><script>alert(1)</script>"

    with tempfile.TemporaryDirectory() as t:
        fdb = os.path.join(t, "forge.db")
        con = sqlite3.connect(fdb)
        con.execute("CREATE TABLE actions (id INTEGER PRIMARY KEY, ts TEXT, run_id TEXT, actor TEXT, action TEXT, target TEXT, status TEXT, detail TEXT, meta TEXT, duration_ms INTEGER, exit_code INTEGER, git_sha TEXT, version TEXT)")
        con.execute("CREATE TABLE artifacts (id INTEGER PRIMARY KEY, ts TEXT, name TEXT, version TEXT, sha256 TEXT, kind TEXT, size INTEGER, filename TEXT, source_repo TEXT, source_commit TEXT, meta TEXT)")
        con.execute("INSERT INTO artifacts (ts, name, version, sha256, kind, size, source_repo) VALUES (?,?,?,?,?,?,?)",
                    ("2026-07-10T00:00:00", "art-x", "1", "aaaa1111", "tar", 4096, "repoX"))
        con.execute("INSERT INTO artifacts (ts, name, version, sha256, kind, size, source_repo) VALUES (?,?,?,?,?,?,?)",
                    ("2026-07-10T00:01:00", "art-y-only", "1", "bbbb2222", "tar", 128, "repoY"))
        con.execute("INSERT INTO artifacts (ts, name, version, sha256, kind, size, source_repo) VALUES (?,?,?,?,?,?,?)",
                    ("2026-07-10T00:02:00", "art-evil", "1", "cccc3333", "tar", 7, evil))
        con.commit(); con.close()

        before = artifacts_count(fdb)
        env = dict(os.environ)
        env["FORGE_DB"] = fdb

        def render(name, getarr):
            return subprocess.run([PHP, harness(t, name, getarr)], capture_output=True, text=True, timeout=60, env=env).stdout

        out_x = render("x.php", "array('page' => 'forge', 'srcrepo' => 'repoX')")
        out_y = render("y.php", "array('page' => 'forge', 'srcrepo' => 'repoY')")
        out_evil = render("e.php", "array('page' => 'forge', 'srcrepo' => '<<<Evil>>><script>alert(1)</script>')")
        after = artifacts_count(fdb)

        check("srcrepo facet filters artifacts to the bound repo (repoX shows art-x, hides art-y-only)",
              ("art-x" in out_x) and ("art-y-only" not in out_x))
        check("shadow has teeth: art-y-only renders under ?srcrepo=repoY (so its absence above is filtering)",
              "art-y-only" in out_y)
        check("forge source_repo is htmlspecialchars-escaped (escape-first)",
              ("&lt;&lt;&lt;Evil" in out_evil) and ("<<<Evil>>>" not in out_evil)
              and ("&lt;script&gt;" in out_evil) and ("<script>" not in out_evil))
        check("the srcrepo facet never writes to forge.db (read-only)",
              before == after)

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
