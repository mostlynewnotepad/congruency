#!/usr/bin/env python3
# rest-dispatch-shadow.py — congruency's data-driven REST layer (boot/rest.php + the api_routes
# table) dispatches NAMED routes, binds ONLY the declared :params (type-coerced, so a route is not
# SQL-injectable), enforces method + token auth (with the live CONGRUENCY_AUTH_OVERRIDE turned OFF),
# and rejects unknown routes. Two-sided on auth: a token route is refused without a key and allowed
# with a valid one. Isolation: a throwaway sqlite DB + a PHP harness under a TemporaryDirectory; the
# live DB and repo are never touched.
#
# NOTE: this php-cli's http_response_code() getter is non-functional (and, once a line is echoed, its
# setter warns "headers already sent"). The harness silences php warnings so they can't pollute a
# captured body, and status is verified from the route's own observable JSON payload (the text it
# emits alongside each code). The parser locates the "CASE " marker within each line so any startup
# output preceding the first line cannot hide it.
import os
import sys
import subprocess
import tempfile
import sqlite3
import json
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
REST = os.path.join(REPO, "checkouts", "current", "congruency", "boot", "rest.php")

checks = []
def check(name, ok):
    checks.append(bool(ok))
    print("  %s %s" % ("\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m", name))


def main():
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  \033[31m✗ FAIL\033[0m php-not-provisioned")
        return 1

    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "rest.sqlite")
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE things (id INTEGER PRIMARY KEY, name TEXT)")
        con.executemany("INSERT INTO things (id, name) VALUES (?,?)", [(1, "alpha"), (2, "beta")])
        con.execute("CREATE TABLE api_keys (key TEXT, label TEXT, scope TEXT)")
        con.execute("INSERT INTO api_keys (key, label, scope) VALUES (?,?,?)", ("K", "test", "write"))
        con.execute("CREATE TABLE api_routes (name TEXT, method TEXT, sql TEXT, auth TEXT, params TEXT)")
        con.executemany(
            "INSERT INTO api_routes (name, method, sql, auth, params) VALUES (?,?,?,?,?)", [
                ("thing.list", "GET",  "SELECT id,name FROM things ORDER BY id", "public", "{}"),
                ("thing.get",  "GET",  "SELECT name FROM things WHERE id=:id",   "public", '{"id":"int"}'),
                ("thing.add",  "POST", "INSERT INTO things(name) VALUES(:name)", "token",  '{"name":"str"}'),
            ])
        con.commit(); con.close()

        # a PHP harness: warnings silenced (so http_response_code's 'headers already sent' can't leak
        # into a captured body); auth ENFORCED (override off); one CASE line per request carrying the
        # captured JSON collapsed (json_decode|json_encode) to one line, each led by a newline so the
        # first line is never fused with any startup output.
        harness = os.path.join(t, "harness.php")
        with open(harness, "w") as fh:
            fh.write(textwrap.dedent('''\
                <?php
                error_reporting(E_ERROR | E_PARSE);            // silence warnings/notices
                ini_set('display_errors', '0');                // ...so they never pollute a captured body
                define('CONGRUENCY_SQLITE', %r);
                define('CONGRUENCY_AUTH_OVERRIDE', false);      // auth ENFORCED (do NOT lean on the live override)
                require %r;
                $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
                $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

                function run_case($db, $id, $method, $get, $key = null) {
                    $_SERVER['REQUEST_METHOD'] = $method;
                    $_GET = $get;
                    if ($key !== null) { $_SERVER['HTTP_X_API_KEY'] = $key; }
                    else { unset($_SERVER['HTTP_X_API_KEY']); }
                    @http_response_code(200);
                    $route = isset($get['route']) ? $get['route'] : '';
                    ob_start();
                    congruency_rest_route($db, $route, strtoupper($method));
                    $body = ob_get_clean();
                    $code = @http_response_code();
                    if (!is_int($code)) { $code = 200; }
                    $decoded = json_decode($body, true);
                    $one = ($decoded === null) ? trim($body) : json_encode($decoded);
                    echo "\nCASE $id $code $one\n";
                }

                run_case($db, 'A', 'GET',  array('route' => 'thing.list'));
                run_case($db, 'B', 'GET',  array('route' => 'thing.get', 'id' => '2'));
                run_case($db, 'C', 'GET',  array('route' => 'thing.get', 'id' => '2 OR 1=1'));
                run_case($db, 'D', 'GET',  array('route' => 'nope'));
                run_case($db, 'E', 'POST', array('route' => 'thing.list'));
                run_case($db, 'F', 'POST', array('route' => 'thing.add', 'name' => 'gamma'));
                run_case($db, 'G', 'POST', array('route' => 'thing.add', 'name' => 'gamma'), 'K');
            ''') % (db, REST))

        proc = subprocess.run([PHP, harness], capture_output=True, text=True, timeout=60)
        cases = {}
        for line in proc.stdout.splitlines():
            i = line.find("CASE ")
            if i < 0:
                continue
            parts = line[i:].split(" ", 3)
            if len(parts) < 3 or not parts[2].isdigit():
                continue
            cases[parts[1]] = (int(parts[2]), parts[3] if len(parts) > 3 else "")

        def body_of(cid):
            return cases.get(cid, (0, ""))[1]

        # 1. a named route dispatches and returns its rows (both rows present)
        check("named route dispatches and returns rows",
              'alpha' in body_of('A') and 'beta' in body_of('A'))

        # 2. declared :params are bound + type-coerced: B binds id=2 (beta); C int-coerces
        #    '2 OR 1=1' -> 2 so it returns EXACTLY one row (beta), not both -> not injectable
        check("declared :params are bound and type-coerced (not injectable)",
              ('beta' in body_of('B')) and ('beta' in body_of('C')) and ('alpha' not in body_of('C')))

        # 3. unknown route -> "unknown route"; wrong method -> "method not allowed"
        check("unknown route 404s and wrong method 405s",
              ('unknown route' in body_of('D')) and ('method not allowed' in body_of('E')))

        # 4. two-sided token auth (override OFF): refused without a key (401 auth-required payload),
        #    allowed with a valid key (the write is applied -> affected:1)
        check("token route refused without key, allowed with key (two-sided)",
              ('API key or admin login required' in body_of('F')) and ('"affected":1' in body_of('G')))

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
