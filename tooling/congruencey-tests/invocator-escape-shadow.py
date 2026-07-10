#!/usr/bin/env python3
# invocator-escape-shadow.py — invocators htmlspecialchars-escape DB-sourced data so a stored
# <<<Tag>>> or <script> can NEVER be re-parsed into a live tag or injected as markup (the XSS /
# tag-injection invariant). Two-sided: PASSES the real escape-first RepoDocs invocator and FAILS a
# non-escaping renderer. Isolation: a throwaway sqlite DB + PHP harnesses under a TemporaryDirectory;
# the live DB and repo are never touched.
import os
import sys
import subprocess
import tempfile
import sqlite3
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
INVOC = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "RepoDocs.php")

checks = []
def check(name, ok):
    checks.append(bool(ok))
    print("  %s %s" % ("\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m", name))


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  \033[31m✗ FAIL\033[0m php-not-provisioned")
        return 1

    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "docs.sqlite")
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE repo_docs (id INTEGER PRIMARY KEY, ts INTEGER, repo TEXT, path TEXT, kind TEXT, body TEXT)")
        con.execute("INSERT INTO repo_docs (ts, repo, path, kind, body) VALUES (?,?,?,?,?)",
                    (0, "r", "d.md", "md", "# doc\n\n<<<SiteMap>>> and <script>alert(1)</script>\n"))
        con.commit(); con.close()

        # the REAL invocator: render RepoDocs (escape-first markdown) against the poisoned DB
        harness = os.path.join(t, "render.php")
        with open(harness, "w") as fh:
            fh.write(textwrap.dedent('''\
                <?php
                define('CONGRUENCY_SQLITE', %r);
                interface Tag_Interface { public function get_document(); }
                class ArgStub { public function pop() { return null; } }
                $_GET['repo'] = 'r';
                $_GET['doc'] = 'd.md';
                require %r;
                $t = new RepoDocs(new ArgStub());
                echo $t->get_document();
            ''') % (db, INVOC))
        out = subprocess.run([PHP, harness], capture_output=True, text=True, timeout=60).stdout

        check("invocator escapes a stored <<<Tag>>> so it stays inert",
              ("&lt;&lt;&lt;SiteMap" in out) and ("<<<SiteMap>>>" not in out))
        check("invocator escapes stored HTML/<script>",
              ("&lt;script&gt;" in out) and ("<script>alert" not in out))

        # teeth: a non-escaping renderer echoes the RAW body, leaking the live <<<Tag>>> — the shadow
        # must FAIL such a renderer (two_sided arena discipline).
        bad = os.path.join(t, "raw.php")
        with open(bad, "w") as fh:
            fh.write(textwrap.dedent('''\
                <?php
                $db = new PDO('sqlite:' . %r);
                $row = $db->query("SELECT body FROM repo_docs ORDER BY id DESC LIMIT 1")->fetch(PDO::FETCH_ASSOC);
                echo $row['body'];
            ''') % (db,))
        badout = subprocess.run([PHP, bad], capture_output=True, text=True, timeout=60).stdout

        check("shadow has teeth: a non-escaping renderer leaks the raw <<<Tag>>>",
              "<<<SiteMap>>>" in badout)

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
