#!/usr/bin/env python3
# null-facet-shadow.py -- regression guard for the sql-null-vs-empty optional-facet bug. When a facet
# param is OMITTED from a ?route= request, boot/rest.php binds the missing :param as NULL (see
# congruency_rest_route: `$val = array_key_exists($pname,$input) ? $input[$pname] : null;`). The OLD
# optional-facet guard `(:x='' OR col=:x)` then evaluates to NULL (NULL='' -> NULL) and the WHERE
# filters out EVERY row -- search.text and bug.list returned ZERO rows unless the caller passed an
# explicit empty string. The fix rewrites every optional-facet guard to `COALESCE(:x,'')=''` so a
# NULL (omitted) facet and an empty-string facet both mean "no filter". This shadow reproduces the
# omitted-facet request FAITHFULLY (it binds absent declared params as NULL, exactly as rest.php
# does) against the MIGRATED route SQL, and is KEPT as a permanent regression guard.
#   TEETH: with the OLD guard bound NULL a control query returns 0 rows (COALESCE returns 1) -- so the
#   assertions genuinely depend on the fix; a naive revert of the migration fails this shadow.
# Isolation: a TemporaryDirectory holds the db (setup.do_migrate applies the REAL migrations); the
# live db/repo are never touched. Stdlib-only (imports setup for do_migrate).
import os
import sys
import json
import tempfile
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root

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


def run_route(con, name, request):
    # Drive a ?route= GET exactly as boot/rest.php does: bind every DECLARED param the SQL uses, taking
    # its value from the request when the key is PRESENT and binding NULL when the key is OMITTED (the
    # root cause). This is what a browser GET without the facet key produces.
    row = con.execute("SELECT sql, params FROM api_routes WHERE name=?", (name,)).fetchone()
    if not row:
        return None
    sql, params_json = row[0], row[1]
    decl = json.loads(params_json or "{}")
    binds = {}
    for pname, ptype in decl.items():
        if (":" + pname) not in sql:
            continue
        if pname in request:
            v = request[pname]
            t = str(ptype).lower()
            if t == "int":
                v = int(v)
            elif t in ("float", "real"):
                v = float(v)
            else:
                v = str(v)
        else:
            v = None   # OMITTED declared param -> bound NULL, exactly as rest.php does
        binds[pname] = v
    return con.execute(sql, binds).fetchall()


def main():
    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "nullfacet.sqlite")
        build_db(db)
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row

        # seed: one repo_doc containing 'relocated', two bugs (corpus/medium + congruency/critical).
        con.execute("INSERT INTO repo_docs (ts, repo, path, kind, body) VALUES (0, 'rA', 'd1.md', 'md', ?)",
                    ("the forge relocated OUT of ~/code",))
        con.executemany(
            "INSERT INTO bugs (bug_id, source, title, severity, location, repro, success, fanout, repos, status, pattern, meta)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("PAT-01", "corpus", "corpus consistent-bug pattern", "medium", "(corpus-wide)", "", "", 12, 4, "open", "some-pat", ""),
                ("BUG-01", "congruency", "a reproduced congruency bug", "critical", "lib/x.php:1", "repro/x.php", "CONFIRMED", 0, 0, "open", "", ""),
            ])
        con.commit()

        # (a) LIVE-01: search.text with q='relocated' and the repo facet OMITTED returns the d1.md row.
        rows = run_route(con, "search.text", {"q": "relocated"})
        paths = [r["path"] for r in rows] if rows is not None else []
        check("search.text returns matches when the repo facet is omitted",
              rows is not None and "d1.md" in paths)

        # (b) LIVE-02: bug.list with source='corpus' and the severity facet OMITTED returns ONLY the
        #     corpus bug (a facet is honored while the other facet is omitted).
        rows = run_route(con, "bug.list", {"source": "corpus"})
        ids = sorted(r["bug_id"] for r in rows) if rows is not None else []
        check("bug.list honors a facet when the other facet is omitted",
              ids == ["PAT-01"] and all(r["source"] == "corpus" for r in rows))

        # (c) bug.list with NO facets at all returns BOTH bugs.
        rows = run_route(con, "bug.list", {})
        ids = sorted(r["bug_id"] for r in rows) if rows is not None else []
        check("bug.list with no facets returns all rows",
              ids == ["BUG-01", "PAT-01"])

        # TEETH: the OLD guard `(:x='' OR col=:x)` bound NULL returns 0 rows (COALESCE returns 1) --
        # proving the assertions above depend on the COALESCE fix; a naive revert fails this shadow.
        con.execute("CREATE TABLE _teeth (col TEXT)")
        con.execute("INSERT INTO _teeth (col) VALUES ('a')")
        old_rows = con.execute("SELECT col FROM _teeth WHERE (:x='' OR col=:x)", {"x": None}).fetchall()
        new_rows = con.execute("SELECT col FROM _teeth WHERE (COALESCE(:x,'')='' OR col=:x)", {"x": None}).fetchall()
        check("shadow has teeth: the OLD guard zeroes on a NULL-bound facet; COALESCE does not",
              len(old_rows) == 0 and len(new_rows) == 1)

        con.close()

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
