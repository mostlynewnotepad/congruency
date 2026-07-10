#!/usr/bin/env python3
# route-params-declared-shadow.py -- UNIVERSAL structural guard for the ROOT CAUSE behind the
# sql-null-vs-empty family: rest.php only binds params that a route DECLARES in its params JSON, and
# binds a declared-but-omitted param as NULL. Therefore every `:param` that appears in a route's SQL
# MUST be declared in that route's params -- an UNDECLARED `:param` is never bound, so sqlite raises
# "no such parameter" and the route hard-fails at runtime. A degenerate refactor that adds a `:filter`
# to the SQL but forgets the params entry ships a route that 500s on every call. This shadow scans
# every migrated route and fails if any SQL references a `:param` not present in its declared params.
#   TEETH: proven to flag a synthetic route whose SQL uses an undeclared :param.
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
# sqlite bound params are :name / @name / $name; congruency routes use :name. Ignore ::cast (none in sqlite).


def declared_ok(sql, params_json):
    used = set(PARAM.findall(sql or ""))
    decl = set(json.loads(params_json or "{}").keys())
    return used - decl  # undeclared params referenced in SQL


def build_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);"
        "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session TEXT, tool TEXT, intent TEXT, note TEXT);")
    con.commit(); con.close()
    setup.do_migrate(db_path=path)


def main():
    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "decl.sqlite"); build_db(db)
        con = sqlite3.connect(db)
        routes = con.execute("SELECT name, sql, params FROM api_routes").fetchall()
        con.close()

        bad = {}
        for name, sql, params in routes:
            miss = declared_ok(sql, params)
            if miss:
                bad[name] = sorted(miss)
        check("every :param used in a route's SQL is declared in its params (%d routes scanned)" % len(routes),
              not bad)
        if bad:
            for n, m in bad.items():
                print("      %s: undeclared %s" % (n, m))

        # TEETH: a synthetic route referencing an undeclared :filter must be flagged.
        check("shadow has teeth: an undeclared :param is detected",
              declared_ok("SELECT * FROM t WHERE c=:filter", '{"other":"str"}') == {"filter"})

    ok = all(checks); print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
