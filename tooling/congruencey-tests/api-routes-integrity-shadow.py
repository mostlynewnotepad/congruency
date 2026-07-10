#!/usr/bin/env python3
# api-routes-integrity-shadow.py -- UNIVERSAL integrity guard for the api_routes control table (the
# heart of the data-driven REST plane). Every route row MUST be well-formed, or the dispatcher in
# boot/rest.php mis-handles it: a bad method routes a write as a read (or vice-versa), a non-JSON or
# malformed params string breaks binding, and an unknown auth class silently downgrades authorization
# (a real security risk -- an admin route that falls through to public). This shadow asserts, for every
# migrated route: method in {GET,POST,PUT,PATCH,DELETE}; sql non-empty; params is valid JSON mapping
# names->type-strings; auth in {public,token,admin} (or empty=default). It future-proofs the whole
# route surface against a crank that ships a malformed control row.
#   TEETH: proven to reject a bad method, non-JSON params, and an unknown auth class.
# Isolation: TemporaryDirectory + setup.do_migrate (real migrations); live db/repo untouched. Stdlib.
import os, sys, json, tempfile, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
import setup  # noqa: E402

checks = []
def check(name, ok):
    checks.append(bool(ok)); print("  %s %s" % ("✓" if ok else "✗ FAIL", name))

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
AUTHS = {"", "public", "token", "admin", None}


def row_issue(name, method, sql, auth, params):
    if (method or "").upper() not in METHODS:
        return "bad method %r" % method
    if not (sql or "").strip():
        return "empty sql"
    if auth not in AUTHS:
        return "unknown auth %r" % auth
    try:
        p = json.loads(params or "{}")
        if not isinstance(p, dict) or not all(isinstance(v, str) for v in p.values()):
            return "params not a name->str map"
    except Exception:
        return "params not valid JSON"
    return None


def build_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);"
        "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session TEXT, tool TEXT, intent TEXT, note TEXT);")
    con.commit(); con.close()
    setup.do_migrate(db_path=path)


def main():
    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "integ.sqlite"); build_db(db)
        con = sqlite3.connect(db)
        routes = con.execute("SELECT name, method, sql, auth, params FROM api_routes").fetchall()
        con.close()

        bad = {}
        for name, method, sql, auth, params in routes:
            iss = row_issue(name, method, sql, auth, params)
            if iss:
                bad[name] = iss
        check("every api_routes row is well-formed: method/sql/auth/params (%d routes)" % len(routes), not bad)
        for n, i in bad.items():
            print("      %s: %s" % (n, i))

        check("shadow has teeth: rejects bad method / non-JSON params / unknown auth",
              row_issue("x", "FETCH", "SELECT 1", "public", "{}") is not None and
              row_issue("x", "GET", "SELECT 1", "public", "{not json}") is not None and
              row_issue("x", "GET", "SELECT 1", "root", "{}") is not None)

    ok = all(checks); print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
