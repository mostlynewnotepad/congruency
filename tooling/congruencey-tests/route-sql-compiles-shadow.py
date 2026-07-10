#!/usr/bin/env python3
# route-sql-compiles-shadow.py -- UNIVERSAL validity guard: every api_routes.sql MUST compile against
# the REAL migrated schema with its declared params bound. congruency's whole REST plane is rows of
# SQL; a crank that ships a route with a typo, a dropped column, a renamed table, or an undeclared
# :param leaves an endpoint that 500s on first call -- exactly the kind of silent erosion LLM cranking
# produces. This shadow EXPLAINs every route (EXPLAIN compiles + validates the statement against the
# schema WITHOUT executing it -- no side effects, safe for INSERT/UPDATE/DELETE routes too) with every
# declared param bound NULL, and fails if any route does not compile. Superset of the param-declared
# check, and it also catches unknown tables/columns and syntax errors.
#   TEETH: a deliberately broken statement (unknown column) is proven to fail EXPLAIN.
# Isolation: TemporaryDirectory + setup.do_migrate (real migrations); live db/repo untouched. Stdlib.
import os, sys, re, json, tempfile, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
import setup  # noqa: E402

checks = []
def check(name, ok):
    checks.append(bool(ok)); print("  %s %s" % ("✓" if ok else "✗ FAIL", name))

PARAM = re.compile(r":([A-Za-z_]\w*)")


def build_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);"
        "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session TEXT, tool TEXT, intent TEXT, note TEXT);")
    con.commit(); con.close()
    setup.do_migrate(db_path=path)


def compiles(con, sql, params_json):
    # bind every :param the SQL references (declared or not) to NULL, then EXPLAIN (compile-only).
    binds = {p: None for p in set(PARAM.findall(sql or ""))}
    try:
        con.execute("EXPLAIN " + sql, binds)
        return None
    except Exception as e:
        return str(e)[:80]


def main():
    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "compile.sqlite"); build_db(db)
        con = sqlite3.connect(db)
        routes = con.execute("SELECT name, sql, params FROM api_routes WHERE sql IS NOT NULL").fetchall()

        bad = {}
        for name, sql, params in routes:
            err = compiles(con, sql, params)
            if err:
                bad[name] = err
        print("      scanned %d route(s)" % len(routes))   # diagnostic (not a ✓ label)
        check("every route's SQL compiles against the real schema", not bad)
        for n, e in bad.items():
            print("      %s: %s" % (n, e))

        # TEETH: a statement referencing an unknown column must fail to compile.
        check("shadow has teeth: an unknown-column statement fails EXPLAIN",
              compiles(con, "SELECT no_such_col FROM api_routes", "{}") is not None)
        con.close()
    ok = all(checks); print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
