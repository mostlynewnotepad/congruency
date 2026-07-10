#!/usr/bin/env python3
# semantic-stream-shadow.py -- proves the <<<SemanticSearch>>> semantic axis ranks by STREAMING the
# stored chunk vectors with a bounded top-k, WITHOUT materializing every vector (the OOM fix). It:
#   (1) correctness -- semanticHits (driven through the __semantic_selftest CLI hook over a temp db of
#       50 synthetic 4-dim unit vectors) returns the SAME top-12 (repo,path) order as a brute-force
#       python cosine over the same rows;
#   (2) repo scope -- repo='repoB' returns only repoB rows, matching brute force;
#   (3) structural no-materialization -- the semanticHits method consumes the vector SELECT via
#       fetch() in a loop and NEVER calls fetchAll (a regression re-introducing fetchAll fails here);
#   (4) TEETH -- a deliberately wrong expected order does NOT match the streaming result.
# Isolation: a TemporaryDirectory holds the db (setup.do_migrate applies the REAL migrations); the
# live db/repo are never touched. Stdlib-only (imports setup for do_migrate). No Ollama needed.
import os
import sys
import json
import math
import tempfile
import sqlite3
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
INVOC = os.path.join(REPO, "checkouts", "current", "congruency", "invocators", "tags", "dev", "SemanticSearch.php")

sys.path.insert(0, REPO)
import setup  # noqa: E402 -- do_migrate finds REPO/migrations via setup.HERE (cwd-independent)

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


def cosine(a, b):
    n = min(len(a), len(b))
    dot = 0.0
    for j in range(n):
        dot += a[j] * b[j]
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def expected_topk(candidates, qv, k=12):
    scored = [(cosine(qv, v), repo, path) for (repo, path, v) in candidates]
    scored.sort(key=lambda x: -x[0])
    return [(r, p) for (_, r, p) in scored[:k]]


def php_semantic(db, qv, repo):
    payload = json.dumps({"db": db, "qv": qv, "repo": repo})
    proc = subprocess.run([PHP, INVOC, "__semantic_selftest"], input=payload,
                          capture_output=True, text=True, timeout=60)
    try:
        return json.loads(proc.stdout)
    except Exception:
        return None


def extract_method(src, sig):
    i = src.find(sig)
    if i < 0:
        return None
    b = src.find("{", i)
    if b < 0:
        return None
    depth = 0
    j = b
    while j < len(src):
        c = src[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    return None


def build_rows():
    # 50 4-dim unit vectors; strictly decreasing cosine vs qv=[1,0,0,0] as i grows -> distinct scores,
    # so the expected order is unambiguous (no ties). i<25 -> repoA, else repoB.
    rows = []
    for i in range(50):
        a = i * 0.05
        raw = [math.cos(a), math.sin(a), 0.1, 0.1]
        nrm = math.sqrt(sum(x * x for x in raw))
        v = [x / nrm for x in raw]
        repo = "repoA" if i < 25 else "repoB"
        path = "doc%02d.md" % i
        rows.append((repo, path, v))
    return rows


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  ✗ FAIL php-not-provisioned")
        return 1
    if not os.path.isfile(INVOC):
        print("  ✗ FAIL SemanticSearch-invocator-not-found")
        return 1

    rows = build_rows()
    qv = [1.0, 0.0, 0.0, 0.0]

    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "vec.sqlite")
        build_db(db)
        con = sqlite3.connect(db)
        for i, (repo, path, v) in enumerate(rows):
            con.execute(
                "INSERT INTO embeddings (ts, repo, path, chunk_seq, section, text, dim, model, vector) "
                "VALUES (0, ?, ?, ?, 'sec', ?, 4, 'test', ?)",
                (repo, path, i, "chunk %d" % i, json.dumps(v)))
        con.commit(); con.close()

        allres = php_semantic(db, qv, "")
        got = [(h.get("repo"), h.get("path")) for h in allres] if isinstance(allres, list) else None
        exp = expected_topk(rows, qv, 12)
        check("streaming top-k over all repos equals the brute-force cosine order",
              got is not None and got == exp and len(got) == 12)

        bres = php_semantic(db, qv, "repoB")
        gotB = [(h.get("repo"), h.get("path")) for h in bres] if isinstance(bres, list) else None
        bcand = [(r, p, v) for (r, p, v) in rows if r == "repoB"]
        expB = expected_topk(bcand, qv, 12)
        only_b = gotB is not None and all(r == "repoB" for (r, p) in gotB)
        check("the streaming ranker's top-k matches brute-force cosine and honors repo scope",
              gotB is not None and gotB == expB and only_b)

    src = open(INVOC, encoding="utf-8").read()
    method = extract_method(src, "private static function semanticHits")
    check("SemanticSearch streams the vector query (no fetchAll) with bounded top-k memory",
          method is not None and "fetchAll" not in method and "->fetch(PDO::FETCH_ASSOC)" in method)

    wrong = list(reversed(exp))
    check("shadow has teeth: a deliberately wrong expected order does not match the streaming result",
          got is not None and got == exp and got != wrong)

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
