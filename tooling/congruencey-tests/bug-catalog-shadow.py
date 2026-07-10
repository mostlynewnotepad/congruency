#!/usr/bin/env python3
# bug-catalog-shadow.py — proves the unified BUG CATALOG (?page=bugs; 0023_bug_catalog.sql + the
# <<<BugCatalog>>> invocator) is sound, WITHOUT any live services. It records TWO bugs through the
# real bug.record route SQL (a 'congruency' critical bug whose title carries a live '<<<TitleTag>>>'
# + <script>, and a 'corpus' medium pattern with fanout=49) into a tempfile-isolated congruency db
# (setup.do_migrate applies the REAL migrations), then asserts:
#   (facets)  bug.list (no facet) returns BOTH; source=corpus returns ONLY the corpus one; and
#             severity=critical returns ONLY the critical one — the facets are honored (bound).
#   (stats)   bug.stats reflects 2 bugs: 1 critical + 1 medium, 1 congruency + 1 corpus.
#   (render)  ?page=bugs (BugCatalog) shows BOTH titles AND the '<<<TitleTag>>>'/<script> is
#             htmlspecialchars-escaped (raw <<< / <script> absent — escape-first); the critical row
#             is colour-classed (bug-sev-critical).
#   (teeth)   a control renderer that does NOT escape echoes the RAW bug title, leaking the live
#             <<<TitleTag>>> — the shadow must catch such a renderer.
# Isolation: a TemporaryDirectory holds the db; the live db/repo are never touched. Stdlib-only
# (imports setup for do_migrate).
import os
import sys
import tempfile
import sqlite3
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
INVOC = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "BugCatalog.php")

sys.path.insert(0, REPO)
import setup  # noqa: E402 — do_migrate finds REPO/migrations via setup.HERE (cwd-independent)

checks = []
def check(name, ok):
    checks.append(bool(ok))
    print("  %s %s" % ("✓" if ok else "✗ FAIL", name))


def build_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);"
        "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session TEXT, tool TEXT, intent TEXT, note TEXT);")
    con.commit(); con.close()
    setup.do_migrate(db_path=path)


def route_sql(con, name):
    row = con.execute("SELECT sql FROM api_routes WHERE name=?", (name,)).fetchone()
    return row[0] if row else None


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  ✗ FAIL php-not-provisioned")
        return 1
    if not os.path.isfile(INVOC):
        print("  ✗ FAIL BugCatalog-invocator-not-found")
        return 1

    congruency_bug = {
        "bug_id": "BUG-01", "source": "congruency",
        "title": "<<<TitleTag>>><script>alert(1)</script> SQL injection in CatalogDAO",
        "severity": "critical", "location": "lib/Modules/StoreModule/Catalog/DAO/CatalogDAO.php:58",
        "repro": "repro/bug01_catalog_sql_injection.php", "success": "INJECTION CONFIRMED",
        "fanout": 0, "repos": 0, "status": "open", "pattern": "", "meta": "",
    }
    corpus_bug = {
        "bug_id": "PAT-07", "source": "corpus",
        "title": "except: pass swallows exceptions across the corpus",
        "severity": "medium", "location": "(corpus-wide anti-pattern)",
        "repro": "", "success": "", "fanout": 49, "repos": 12, "status": "open",
        "pattern": "py-except-pass", "meta": "",
    }

    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "bugs.sqlite")
        build_db(db)

        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        rec = route_sql(con, "bug.record")
        con.execute(rec, congruency_bug)
        con.execute(rec, corpus_bug)
        con.commit()

        lst = route_sql(con, "bug.list")
        all_rows = con.execute(lst, {"source": "", "severity": ""}).fetchall()
        corpus_rows = con.execute(lst, {"source": "corpus", "severity": ""}).fetchall()
        crit_rows = con.execute(lst, {"source": "", "severity": "critical"}).fetchall()

        stats_rows = con.execute(route_sql(con, "bug.stats")).fetchall()
        con.close()

        all_ids = sorted(r["bug_id"] for r in all_rows)
        returns_both = (all_ids == ["BUG-01", "PAT-07"])
        corpus_only = ([r["bug_id"] for r in corpus_rows] == ["PAT-07"]) and all(r["source"] == "corpus" for r in corpus_rows)
        crit_only = ([r["bug_id"] for r in crit_rows] == ["BUG-01"]) and all(r["severity"] == "critical" for r in crit_rows)

        check("bug.list (no facet) returns both congruency and corpus bugs", returns_both)
        check("bug.list honors the source and severity facets", corpus_only and crit_only)

        sev = {r["value"]: r["n"] for r in stats_rows if r["facet"] == "severity"}
        src = {r["value"]: r["n"] for r in stats_rows if r["facet"] == "source"}
        stats_ok = (sev.get("critical") == 1 and sev.get("medium") == 1 and sum(sev.values()) == 2
                    and src.get("congruency") == 1 and src.get("corpus") == 1 and sum(src.values()) == 2)
        check("bug.stats reflects 2 bugs (1 critical/1 medium, 1 congruency/1 corpus)", stats_ok)

        # render ?page=bugs (BugCatalog) directly — no facet -> both bugs shown.
        harness = os.path.join(t, "render.php")
        with open(harness, "w") as fh:
            fh.write('''<?php
error_reporting(E_ERROR | E_PARSE);
ini_set('display_errors', '0');
interface Tag_Interface { public function get_document(); }
class ArgStub { public function pop() { return null; } }
define('CONGRUENCY_SQLITE', %r);
require %r;
$_GET = array();
$t = new BugCatalog(new ArgStub());
echo $t->get_document();
''' % (db, INVOC))
        out = subprocess.run([PHP, harness], capture_output=True, text=True, timeout=60).stdout

        both_titles = ("&lt;&lt;&lt;TitleTag&gt;&gt;&gt;" in out) and ("except: pass swallows exceptions" in out)
        escaped = ("<<<TitleTag>>>" not in out) and ("<script>" not in out) and ("&lt;script&gt;" in out)
        check("?page=bugs renders both bug titles", both_titles)
        check("bug catalog output is htmlspecialchars-escaped (escape-first)", escaped)
        check("the critical bug row is colour-classed", "bug-sev-critical" in out)

        # teeth: a non-escaping renderer echoes the RAW bug title, leaking the live <<<TitleTag>>>.
        bad = os.path.join(t, "raw.php")
        with open(bad, "w") as fh:
            fh.write('''<?php
$db = new PDO('sqlite:' . %r);
$row = $db->query("SELECT title FROM bugs WHERE severity='critical' LIMIT 1")->fetch(PDO::FETCH_ASSOC);
echo $row['title'];
''' % (db,))
        badout = subprocess.run([PHP, bad], capture_output=True, text=True, timeout=60).stdout
        check("shadow has teeth: a non-escaping renderer leaks the raw <<<", "<<<TitleTag>>>" in badout)

    ok = all(checks)
    print("")
    print("%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
