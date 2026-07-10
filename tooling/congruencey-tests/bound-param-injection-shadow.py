#!/usr/bin/env python3
# bound-param-injection-shadow.py -- regression guard for the SQL-INJECTION spec (the class behind
# congruency BUG-01: a validated value discarded and the raw input interpolated). congruency's REST
# plane is data-driven: routes MUST parameterise user input via bound :params, never string-build the
# SQL from request values. This shadow drives the user-facing param routes (search.text, bug.list)
# with classic injection payloads and asserts the payloads are inert DATA: the query runs without
# error, returns ONLY rows that literally contain the payload (i.e. none), and the tables still exist
# afterwards (no `; DROP TABLE`). If a future refactor interpolates a param, the payload would return
# every row or drop a table -- this shadow fails.
#   TEETH: an INTERPOLATED control query with the same payload returns all rows / errors, proving the
#   assertions depend on the input being bound, not concatenated.
# Isolation: TemporaryDirectory + setup.do_migrate (real migrations); live db/repo untouched. Stdlib.
import os, sys, json, tempfile, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
import setup  # noqa: E402

checks = []
def check(name, ok):
    checks.append(bool(ok)); print("  %s %s" % ("✓" if ok else "✗ FAIL", name))


def build_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);"
        "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session TEXT, tool TEXT, intent TEXT, note TEXT);")
    con.commit(); con.close()
    setup.do_migrate(db_path=path)


def run_route(con, name, request):
    # bind declared params exactly as rest.php does (present->value, omitted->NULL)
    row = con.execute("SELECT sql, params FROM api_routes WHERE name=?", (name,)).fetchone()
    if not row:
        return None
    sql, decl = row[0], json.loads(row[1] or "{}")
    binds = {}
    for p, ty in decl.items():
        if (":" + p) not in sql:
            continue
        if p in request:
            v = request[p]; t = str(ty).lower()
            v = int(v) if t == "int" else float(v) if t in ("float", "real") else str(v)
        else:
            v = None
        binds[p] = v
    return con.execute(sql, binds).fetchall()


def main():
    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "inj.sqlite"); build_db(db)
        con = sqlite3.connect(db); con.row_factory = sqlite3.Row
        con.execute("INSERT INTO repo_docs (ts, repo, path, kind, body) VALUES (0,'rA','d.md','md','ordinary content')")
        con.execute("INSERT INTO bugs (bug_id, source, title, severity, location, repro, success, fanout, repos, status, pattern, meta)"
                    " VALUES ('B','congruency','t','critical','l','','',0,0,'open','','')")
        con.commit()

        OR = "x' OR '1'='1"
        DROP = "x'; DROP TABLE bugs; --"

        # search.text: payload as q must return 0 rows (no body literally contains it) and not error.
        try:
            r1 = run_route(con, "search.text", {"q": OR})
            ok1 = r1 is not None and len(r1) == 0
        except Exception as e:
            ok1 = False; print("      search.text raised:", str(e)[:60])
        check("search.text treats an OR-injection payload as an inert literal (0 rows, no error)", ok1)

        # bug.list: payload as the source facet must return 0 rows (no source equals the literal).
        try:
            r2 = run_route(con, "bug.list", {"source": OR})
            ok2 = r2 is not None and len(r2) == 0
        except Exception as e:
            ok2 = False; print("      bug.list raised:", str(e)[:60])
        check("bug.list treats an OR-injection payload as an inert literal (0 rows, no error)", ok2)

        # a DROP payload through search.text must NOT drop the bugs table.
        try:
            run_route(con, "search.text", {"q": DROP})
        except Exception:
            pass
        still = con.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='bugs'").fetchone()[0]
        check("a `; DROP TABLE` payload cannot drop a table (input is bound, not executed)", still == 1)

        # TEETH: an INTERPOLATED query with the OR payload returns the row; the BOUND form returns none.
        interp = con.execute("SELECT * FROM bugs WHERE source='%s'" % OR).fetchall()
        bound = con.execute("SELECT * FROM bugs WHERE source=:s", {"s": OR}).fetchall()
        check("shadow has teeth: interpolation leaks the row (%d) while binding does not (%d)" % (len(interp), len(bound)),
              len(interp) == 1 and len(bound) == 0)

        con.close()
    ok = all(checks); print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
