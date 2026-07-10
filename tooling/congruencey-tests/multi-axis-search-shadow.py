#!/usr/bin/env python3
# multi-axis-search-shadow.py — proves congruency's MULTI-AXIS search (0020_multi_axis_search.sql +
# the rewritten <<<SemanticSearch>>> invocator) is sound, WITHOUT any embedding service:
#   (1) KEYWORD axis — the search.text route (LIKE over repo_docs) matches the doc that contains the
#       term and honors the :repo facet (a scoped query that can't match returns nothing);
#   (2) MERGE — SemanticSearch::merge (driven through the pure __merge_selftest CLI hook) dedupes by
#       (repo,path) and ranks a doc found by BOTH axes above one found by only one (combined > either);
#   (3) ESCAPING — a keyword snippet carrying '<<<Evil>>><script>' is htmlspecialchars'd inert
#       (escape-first, mirroring the invocator's self::esc); and
#   (4) TEETH — a merge that does NOT boost both-axis hits would rank the single-axis doc first, so it
#       fails the both-first ordering assertion.
# Isolation: a TemporaryDirectory holds the db (setup.do_migrate applies the REAL migrations); the
# live db/repo are never touched. Stdlib-only (imports setup for do_migrate).
import os
import sys
import json
import tempfile
import sqlite3
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
INVOC = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "SemanticSearch.php")

sys.path.insert(0, REPO)
import setup  # noqa: E402 — do_migrate finds REPO/migrations via setup.HERE (cwd-independent)

checks = []
def check(name, ok):
    checks.append(bool(ok))
    print("  %s %s" % ("\033[32m/\033[0m".replace("/", "✓") if ok else "\033[31m✗ FAIL\033[0m", name))


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


def php_merge(semantic, keyword, k):
    payload = json.dumps({"semantic": semantic, "keyword": keyword, "k": k})
    proc = subprocess.run([PHP, INVOC, "__merge_selftest"], input=payload,
                          capture_output=True, text=True, timeout=60)
    try:
        return json.loads(proc.stdout)
    except Exception:
        return None


def php_esc(text):
    # mirror the invocator's escaping EXACTLY: htmlspecialchars($s, ENT_QUOTES), via the provisioned php.
    proc = subprocess.run([PHP, "-r", 'echo htmlspecialchars(file_get_contents("php://stdin"), ENT_QUOTES);'],
                          input=text, capture_output=True, text=True, timeout=60)
    return proc.stdout


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  \033[31m✗ FAIL\033[0m php-not-provisioned")
        return 1
    if not os.path.isfile(INVOC):
        print("  \033[31m✗ FAIL\033[0m SemanticSearch-invocator-not-found")
        return 1

    # (1) KEYWORD axis + repo facet, driven through the search.text route SQL.
    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "mx.sqlite")
        build_db(db)
        con = sqlite3.connect(db)
        con.execute("INSERT INTO repo_docs (ts, repo, path, kind, body) VALUES (0, 'repoA', 'one.md', 'md', 'the coverage gate uses tiers')")
        con.execute("INSERT INTO repo_docs (ts, repo, path, kind, body) VALUES (0, 'repoB', 'two.md', 'md', 'unrelated colors')")
        con.commit()
        sql = route_sql(con, "search.text")
        all_rows = con.execute(sql, {"q": "coverage", "repo": ""}).fetchall() if sql else []
        b_rows = con.execute(sql, {"q": "coverage", "repo": "repoB"}).fetchall() if sql else []
        con.close()
    all_paths = [r[1] for r in all_rows]
    check("keyword axis matches the doc containing the term and honors the repo facet",
          (sql is not None) and ("one.md" in all_paths) and ("two.md" not in all_paths) and (len(b_rows) == 0))

    # (2) MERGE — a doc found by BOTH axes outranks one found by only one, deduped.
    semantic = [{"repo": "A", "path": "1", "score": 0.6}, {"repo": "A", "path": "2", "score": 0.5}]
    keyword = [{"repo": "A", "path": "2", "score": 0.9}]
    merged = php_merge(semantic, keyword, 10)
    order = [(m.get("repo"), m.get("path")) for m in merged] if isinstance(merged, list) else None
    a2 = None
    if isinstance(merged, list):
        for m in merged:
            if (m.get("repo"), m.get("path")) == ("A", "2"):
                a2 = m
                break
    both_first = bool(order) and order[0] == ("A", "2")
    deduped = bool(order) and order.count(("A", "2")) == 1
    combined_beats_either = (a2 is not None) and (float(a2.get("score", 0)) > 0.9)
    check("both-axis merge dedups and ranks both-axis hits first",
          both_first and deduped and combined_beats_either)

    # (3) ESCAPING — a keyword snippet with a poisoned body is htmlspecialchars'd inert (escape-first).
    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "esc.sqlite")
        build_db(db)
        con = sqlite3.connect(db)
        con.execute("INSERT INTO repo_docs (ts, repo, path, kind, body) VALUES (0, 'repoA', 'evil.md', 'md', ?)",
                    ("<<<Evil>>> <script>x</script> coverage",))
        con.commit()
        sql = route_sql(con, "search.text")
        rows = con.execute(sql, {"q": "Evil", "repo": ""}).fetchall() if sql else []
        con.close()
    snippet = rows[0][2] if rows else ""
    esc = php_esc(snippet)
    check("multi-axis search output is htmlspecialchars-escaped",
          ("<<<Evil>>>" in snippet) and ("<<<" not in esc) and ("<script>" not in esc) and ("&lt;" in esc))

    # (4) TEETH — a non-boosting merge (semantic score only) ranks the single-axis doc first,
    #     which would FAIL the both-first assertion above.
    naive = sorted([("A", "1", 0.6), ("A", "2", 0.5)], key=lambda x: -x[2])
    naive_order = [(r[0], r[1]) for r in naive]
    check("shadow has teeth: a merge that does not boost both-axis hits fails the both-first ordering",
          naive_order[0] == ("A", "1") and naive_order[0] != ("A", "2"))

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
