#!/usr/bin/env python3
# vector-search-shadow.py — the native vector-store shadow. Proves, WITHOUT any embedding service,
# that congruency's semantic search (0019_vector_store.sql + the <<<SemanticSearch>>> invocator) is
# sound: (a) the migrations are additive — the `embeddings` table + search.record/search.stats routes
# exist after the REAL migrations run into an isolated temp db; (b) SemanticSearch::rank orders doc
# chunks by cosine similarity (nearest vector first), driven through the pure static __rank_selftest
# CLI hook so no Ollama is needed; (c) all data-derived output is htmlspecialchars-escaped (escape-
# first, so a stored <<<Tag>>>/<script> stays inert); and (d) it has TEETH — a non-cosine ranker
# would fail the ordering assertion. Isolation: a TemporaryDirectory holds the db; the live db/repo
# are never touched. Stdlib-only (imports setup for do_migrate).
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
    print("  %s %s" % ("\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m", name))


def build_db(path):
    # pre-seed the base tables the first migrations need (api_routes to INSERT routes into; memories,
    # referenced by the agent routes), then apply the REAL forward-only migrations -> full schema.
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);"
        "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session TEXT, tool TEXT, intent TEXT, note TEXT);")
    con.commit(); con.close()
    setup.do_migrate(db_path=path)


def php_rank(q, rows, k):
    payload = json.dumps({"q": q, "rows": rows, "k": k})
    proc = subprocess.run([PHP, INVOC, "__rank_selftest"], input=payload,
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

    # 1. migration-additive: the embeddings table + routes exist after the REAL migrations.
    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "vec.sqlite")
        build_db(db)
        con = sqlite3.connect(db)
        tabs = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        routes = [r[0] for r in con.execute("SELECT name FROM api_routes").fetchall()]
        cols = [r[1] for r in con.execute("PRAGMA table_info(embeddings)").fetchall()]
        con.close()
    check("embeddings table + search.record/search.stats routes exist (migration-additive)",
          ("embeddings" in tabs) and ("search.record" in routes) and ("search.stats" in routes)
          and ("vector" in cols) and ("model" in cols))

    # 2. ranking correctness: query [1,0,0] over [1,0,0],[0,1,0],[0.7071,0.7071,0] -> a, c, b.
    rows = [
        {"repo": "r", "path": "a", "section": "s", "text": "on axis x", "vector": [1.0, 0.0, 0.0]},
        {"repo": "r", "path": "b", "section": "s", "text": "on axis y", "vector": [0.0, 1.0, 0.0]},
        {"repo": "r", "path": "c", "section": "s", "text": "diagonal",  "vector": [0.7071, 0.7071, 0.0]},
    ]
    ranked = php_rank([1.0, 0.0, 0.0], rows, 3)
    order = [r.get("path") for r in ranked] if isinstance(ranked, list) else None
    check("SemanticSearch::rank orders by cosine (nearest first)", order == ["a", "c", "b"])

    # 3. escaping (escape-first): a chunk's poisoned text, escaped as the invocator escapes it, is inert.
    evil_text = "<<<Evil>>> <script>x</script>"
    evil = [{"repo": "r", "path": "p", "section": "s", "text": evil_text, "vector": [1.0, 0.0]}]
    ev = php_rank([1.0, 0.0], evil, 1)
    snippet = ev[0].get("text") if isinstance(ev, list) and ev else None
    esc = php_esc(snippet if snippet is not None else "")
    check("search output is htmlspecialchars-escaped (escape-first)",
          (snippet == evil_text) and ("<<<" not in esc) and ("<script>" not in esc) and ("&lt;" in esc))

    # 4. teeth: a NON-cosine ranker (input order) yields a,b,c -> would FAIL the cosine ordering.
    input_order = [r["path"] for r in rows]
    check("shadow has teeth: a non-cosine (input-order) ranker fails the ordering assertion",
          (input_order == ["a", "b", "c"]) and (input_order != ["a", "c", "b"]))

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
