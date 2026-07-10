#!/usr/bin/env python3
# api-surface-shadow.py — the API-surface requests-test. Spins an EPHEMERAL congruency server
# (php -S boot/router.php, exactly as tools/serve.py does) against an ISOLATED temp sqlite built from
# the REAL migrations, then drives the LIVE HTTP API surface with urllib and asserts it behaves to
# contract: named-route dispatch + shape (rows / 404), a ticket+mandate write->read round-trip, HTTP
# token-auth enforcement (CONGRUENCY_AUTH_OVERRIDE forced OFF), and the security denylist (api_keys /
# Login_Password unreachable via ?api=<table> while normal tables stay reachable). Isolation: a
# TemporaryDirectory holds the db + the config override; the live db/repo are never touched. This is
# the requests-test that proves the surface — a route/shape/denylist regression turns it red and
# cannot mint. Stdlib-only (imports setup for do_migrate).
import os
import sys
import json
import time
import socket
import sqlite3
import tempfile
import subprocess
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # tooling/congruencey-tests -> repo root
SOURCE = os.path.join(REPO, "checkouts", "current", "congruency")   # the CMS app root (serve.py SOURCE)
ROUTER = os.path.join("boot", "router.php")            # relative to SOURCE (cwd at serve time)
PHP = os.path.join(REPO, "tooling", "congruencey-harness", "php", "php")
API_KEY = "SURFACE-KEY-7c3f9a"
DENY_PW = "SECRET-PW-DENY-77"
PORT = 0

sys.path.insert(0, REPO)
import setup  # noqa: E402  — do_migrate finds REPO/migrations via setup.HERE (cwd-independent)

checks = []
def check(name, ok):
    checks.append(bool(ok))
    print("  %s %s" % ("\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m", name))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def build_db(path):
    # pre-seed the base tables the first migration needs (api_routes to INSERT routes into; memories,
    # referenced by the agent routes), plus the seed-only tables the live surface carries but the
    # migrations do not create: api_keys (token auth) and Login_Password (a denylisted secret table).
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE api_routes (name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);"
        "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session TEXT, tool TEXT, intent TEXT, note TEXT);"
        "CREATE TABLE api_keys (key TEXT, label TEXT, scope TEXT);"
        "CREATE TABLE Login_Password (id INTEGER PRIMARY KEY, username TEXT, password TEXT);")
    con.execute("INSERT INTO api_keys (key, label, scope) VALUES (?,?,?)", (API_KEY, "surfacetest", "write"))
    con.execute("INSERT INTO Login_Password (username, password) VALUES (?,?)", ("admin", DENY_PW))
    con.commit(); con.close()

    # apply the REAL forward-only migrations -> full schema + every api_routes row (the live surface).
    setup.do_migrate(db_path=path)

    # tickets.recent is a SEED route (no migration creates it); the live surface has it, so the shadow
    # supplies it to reconstruct the full surface — exactly as it supplies the seed tables above. Also
    # seed one repos row so 'reachable' is a positive assertion (rows returned).
    con = sqlite3.connect(path)
    con.execute(
        "INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) VALUES (?,?,?,?,?,?)",
        ("tickets.recent", "GET",
         "SELECT id, component, title, severity, status FROM tickets WHERE status=:status ORDER BY id DESC LIMIT :n",
         "public", '{"status":"str","n":"int"}', "recent tickets by status"))
    con.execute("INSERT INTO repos (name, forge_remote, head_commit, ts) VALUES (?,?,?,?)",
                ("surfacerepo", "forge://x", "deadbeef", 0))
    con.commit(); con.close()


def http(method, qs, body=None, key=None, timeout=10):
    url = "http://127.0.0.1:%d/%s" % (PORT, qs)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if key is not None:
        req.add_header("X-Api-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 — connection refused during startup poll, etc.
        return None, repr(e)


def decode(body):
    try:
        return json.loads(body)
    except Exception:  # noqa: BLE001
        return None


def main():
    global PORT
    if not (os.path.isfile(PHP) and os.access(PHP, os.X_OK)):
        print("  \033[31m✗ FAIL\033[0m php-not-provisioned")
        return 1
    if not os.path.isfile(os.path.join(SOURCE, ROUTER)):
        print("  \033[31m✗ FAIL\033[0m router-not-found")
        return 1

    with tempfile.TemporaryDirectory() as t:
        db = os.path.join(t, "surface.sqlite")
        build_db(db)

        # config override honored by boot/configure.php ($CONGRUENCY_CONFIG): point the CMS at the
        # temp db and FORCE auth enforcement (override OFF, so token routes require a key).
        cfg = os.path.join(t, "config.json")
        with open(cfg, "w") as fh:
            json.dump({"CONGRUENCY_SQLITE": db, "CONGRUENCY_AUTH_OVERRIDE": False}, fh)

        PORT = free_port()
        env = dict(os.environ)
        env["CONGRUENCY_CONFIG"] = cfg
        logpath = os.path.join(t, "serve.log")
        log = open(logpath, "w")
        proc = subprocess.Popen([PHP, "-S", "127.0.0.1:%d" % PORT, ROUTER],
                                cwd=SOURCE, env=env, stdout=log, stderr=log, text=True)
        try:
            # poll the ephemeral server until repo.list answers 200 (or ~20s timeout).
            up = False
            deadline = time.time() + 20.0
            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                st, _b = http("GET", "?route=repo.list", timeout=3)
                if st == 200:
                    up = True
                    break
                time.sleep(0.4)
            if not up:
                try:
                    log.flush()
                    tail = open(logpath).read()[-800:]
                except Exception:  # noqa: BLE001
                    tail = ""
                print("  \033[31m✗ FAIL\033[0m ephemeral server never came up:\n%s" % tail)
                check("live API dispatches routes and 404s unknown ones", False)
                check("ticket + mandate round-trip through the live API", False)
                check("token routes are auth-enforced over HTTP", False)
                check("denylist holds: api_keys/passwords unreachable, normal tables reachable (two-sided)", False)
                return 1

            # 1. dispatch + shape: a named route returns rows; an unknown route 404s.
            s_list, b_list = http("GET", "?route=repo.list")
            d_list = decode(b_list)
            repo_ok = (s_list == 200) and isinstance(d_list, dict) and isinstance(d_list.get("rows"), list)
            s_nope, _b_nope = http("GET", "?route=nope")
            nope_404 = (s_nope == 404)
            check("live API dispatches routes and 404s unknown ones", repo_ok and nope_404)

            # 2. ticket + mandate round-trip through the live API (write with a key, then read back).
            s_c, b_c = http("POST", "?route=ticket.create",
                            {"component": "surfacetest", "title": "surface-test-ticket",
                             "severity": "info", "body": "surface body", "patch": ""}, key=API_KEY)
            d_c = decode(b_c) or {}
            try:
                tid = int(d_c.get("rowid"))
            except Exception:  # noqa: BLE001
                tid = None
            s_tr, b_tr = http("GET", "?route=tickets.recent&status=REQUESTED&n=5")
            d_tr = decode(b_tr)
            rows_tr = d_tr.get("rows", []) if isinstance(d_tr, dict) else []
            ticket_appears = (s_c == 200) and (tid is not None) and any(
                (r.get("id") == tid or r.get("title") == "surface-test-ticket") for r in rows_tr)

            s_mr, _b_mr = http("POST", "?route=mandate.record",
                               {"ticket_id": tid, "seq": 1, "clause": "SURFACE-CLAUSE", "digest": "x"}, key=API_KEY)
            s_ml, b_ml = http("GET", "?route=mandate.list&ticket_id=%s" % (tid,))
            d_ml = decode(b_ml)
            rows_ml = d_ml.get("rows", []) if isinstance(d_ml, dict) else []
            clause_appears = (s_mr == 200) and any(r.get("clause") == "SURFACE-CLAUSE" for r in rows_ml)
            check("ticket + mandate round-trip through the live API", ticket_appears and clause_appears)

            # 3. token routes are auth-enforced over HTTP: the same write WITHOUT a key -> 401.
            s_noauth, _b_noauth = http("POST", "?route=ticket.create",
                                       {"component": "surfacetest", "title": "nope",
                                        "severity": "info", "body": "x", "patch": ""})
            check("token routes are auth-enforced over HTTP", s_noauth == 401)

            # 4. denylist (two-sided): the secret tables are unreachable; a normal table is reachable.
            s_ak, b_ak = http("GET", "?api=api_keys")
            ak_refused = (s_ak == 404) and ("unknown table" in b_ak) and (API_KEY not in b_ak)
            s_lp, b_lp = http("GET", "?api=Login_Password")
            lp_refused = (s_lp == 404) and ("unknown table" in b_lp) and (DENY_PW not in b_lp)
            s_rp, b_rp = http("GET", "?api=repos")
            d_rp = decode(b_rp)
            repos_reachable = (s_rp == 200) and isinstance(d_rp, dict) \
                and isinstance(d_rp.get("rows"), list) and ("unknown table" not in b_rp)
            check("denylist holds: api_keys/passwords unreachable, normal tables reachable (two-sided)",
                  ak_refused and lp_refused and repos_reachable)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                proc.kill()
            try:
                log.close()
            except Exception:  # noqa: BLE001
                pass

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
