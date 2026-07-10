#!/usr/bin/env python3
# facet-guard-lint-shadow.py -- UNIVERSAL, FUTURE-PROOF regression guard for the sql-null-vs-empty
# spec discovered by the bug hunt (LIVE-01 search.text, LIVE-02 bug.list). rest.php binds an OMITTED
# declared param as NULL; the fragile optional-facet guard `(:x='' OR col=:x)` then evaluates to NULL
# and the WHERE zeroes the result. The null-facet-shadow pins the two routes that HAD the bug; THIS
# shadow forbids the anti-pattern from EVER re-appearing in ANY route: it scans every api_routes.sql
# after the real migrations and fails if any route compares a bound :param DIRECTLY to '' (the
# NULL-unsafe form) instead of the NULL-safe `COALESCE(:x,'')=''` / `:x IS NULL`. A brilliant agent
# missed this once and will miss it again; the mint gate now catches it structurally.
#   TEETH: the linter is proven to flag the fragile form and to PASS the COALESCE form.
# Isolation: TemporaryDirectory + setup.do_migrate (real migrations); live db/repo untouched. Stdlib.
import os, sys, re, tempfile, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
import setup  # noqa: E402

checks = []
def check(name, ok):
    checks.append(bool(ok)); print("  %s %s" % ("✓" if ok else "✗ FAIL", name))

# a bound param compared DIRECTLY to an empty string literal -> NULL-unsafe when the param is omitted.
FRAGILE = re.compile(r":\w+\s*=\s*''")
# the COALESCE form wraps the param, so ':x' is followed by ',' not '=' -> not matched by FRAGILE.


def build_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);"
        "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session TEXT, tool TEXT, intent TEXT, note TEXT);")
    con.commit(); con.close()
    setup.do_migrate(db_path=path)


def main():
    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "lint.sqlite"); build_db(db)
        con = sqlite3.connect(db)
        routes = con.execute("SELECT name, sql FROM api_routes WHERE sql IS NOT NULL").fetchall()
        con.close()

        violations = [n for n, sql in routes if FRAGILE.search(sql or "")]
        print("      scanned %d route(s)" % len(routes))   # diagnostic (not a ✓ label -> not a harvested guarantee)
        check("no route uses the NULL-unsafe `:x='' OR ...` optional-facet guard (use COALESCE)",
              not violations)
        if violations:
            print("      VIOLATIONS:", ", ".join(violations))

        # TEETH: the linter must actually detect the fragile form and accept the safe form.
        check("shadow has teeth: FRAGILE flags `(:repo='' OR repo=:repo)` and passes `COALESCE(:repo,'')=''`",
              bool(FRAGILE.search("WHERE (:repo='' OR repo=:repo)")) and
              not FRAGILE.search("WHERE (COALESCE(:repo,'')='' OR repo=:repo)"))

    ok = all(checks); print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
