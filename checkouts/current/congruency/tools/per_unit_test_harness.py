#!/usr/bin/env python3
"""per_unit_test_harness.py — the per-unit test harness for the congruency-go port (#233).

WHAT THIS IS. Every #230 port unit (one api_route, one tag, one ?page=, one ?api CRUD verb, one
rest.php helper, one boot constant group, one render-engine class) must be gated by a real test
suite before it can settle. This tool builds that suite for EVERY unit, runs it against a TARGET
(php or go) over the request/response contract both servers share, and refuses to let a unit settle
with fewer than 10 tests or a single failing test.

TERMS (defined here because this artifact stands alone):
  unit        — the smallest independently portable + diffable piece of congruency. The universe is
                NOT re-invented here: it is imported live from tools/go_port_decomposer.py
                (enumerate_units), the #230 decomposer, so this harness gates exactly the units
                #230 files tickets for. 160 units today (62 route, 45 tag, 26 page, 11 engine,
                6 crud, 5 helper, 5 boot).
  unit key    — that tool's stable id, e.g. `go-port:db:route:agent.roster`.
  shadow suite— one of tooling/congruencey-tests/*-shadow.py: a standalone python suite that
                asserts invariants with its own `check(name, ok)` helper and prints one ✓/✗ line
                per check. 38 suites, 174 check call sites today.
  harvested   — a shadow check bound to a unit because its suite demonstrably exercises that unit
                (see ATTRIBUTION). Harvested tests are PHP-side evidence: they drive PHP internals,
                so they are NOT runnable against the Go target and are never counted as Go-green.
  spec        — a generated, declarative request/response test: {request, expect}. A spec is the
                part that gates BOTH targets, because PHP and Go serve the identical URL surface.
  FLOOR       — 10. A unit cannot settle against a target unless at least 10 specs actually
                INTERROGATED that target (were sent to it over the wire and answered) and not one
                test failed (`--gate`). A skipped test, and a harvested check — which runs its own
                suite in a subprocess and so answers the same whatever the target is — prove
                nothing about the target and never count toward its floor. A mutation run against a
                deliberately wrong target is what forced this rule: 28 harvested checks still
                "passed" there, so a floor that counted them would have greened a broken target.

THE TICKET'S NOUNS, CHECKED AGAINST THIS REPOSITORY (read before you trust the numbers):
  * `shadow_forge/` and `shadow_forge/shadow_index.db` DO NOT EXIST in this repository. There is no
    directory named shadow_forge and no .db file anywhere in the tree (the only databases are
    checkouts/current/state/congruency.sqlite and tooling/congruencey-harness/congruency.sqlite).
    The reusable shadow tests are real, but they live in tooling/congruencey-tests/*-shadow.py.
    `--shadow-index PATH` accepts the index if it is ever produced; absent, `--harvest` says so on
    its own report line and harvests from the suites alone. This tool never pretends to read it.
  * The ticket says "37 suites"; there are 38 (`--harvest` prints the live count, never a constant).
  * The ticket says "the #230 units"; #230's own estimate is ~100, and its decomposer enumerates
    160 live. This tool uses the live enumeration, so the two can never drift apart.

WHY A SPEC GATES BOTH TARGETS. boot/router.php:40 dispatches any request carrying ?api= or ?route=
into congruency_rest_dispatch(); congruency-go/server.go reproduces that same split ("the mux
mirrors boot/router.php: any request carrying ?api or ?route is a REST request", server.go:22).
So one spec — a method, a query, an expectation — is answerable by both servers, and "equivalent"
means: the same spec passes identically on both. That is the equivalence check.

HOW EACH UNIT IS EXERCISED (the surface map mirrors each unit's own #230 probe, not an invention):
  route  -> GET/POST /?route=<name>          (the probe diffs exactly this URL on :8899 vs :8900)
  helper -> GET/POST /?route=<fixture>       ("this engine is reached ONLY via ?route=" — its probe)
  crud   -> /?api=<table>                    (its probe: "THIS UNIT WRITES: give each server its OWN
                                              scratch db and never the live one" — honoured below)
  page   -> GET /?page=<id>                  (the probe diffs exactly this URL)
  tag    -> GET /?page=tags&tag=<Name>       (the PHP gallery surface)
  boot   -> GET /?page=<fixture page>        (its probe: constants "have no URL, so prove them
                                              through the behaviour they DECIDE")
  engine -> GET /?page=<fixture page>        (its probe: "no URL of its own; proven by every class
                                              the render chain resolves")

ATTRIBUTION (how a shadow check is bound to a unit — deliberately conservative). A suite binds to a
unit only through a DISCRIMINATING token, because a loose match is worse than no match: matching the
bare word "read" bound 98 checks to the `crud:read` unit in a trial run, which is a lie. So:
  route name   — must contain a dot (`agent.roster`)          -> matched literally
  helper name  — must start with `congruency_`                -> matched literally
  tag name     — must be CamelCase (an interior capital)      -> matched on a word boundary
  page id      — matched only as `page=<id>`, never bare
  crud verb    — matched only alongside a literal `?api=` in the same suite
  boot/engine  — matched only via the unit's own source basename (e.g. `rest.php`, `configure.php`)
A unit whose token cannot discriminate gets NO harvest rather than a false one; its floor is then
filled entirely by generated specs, which is the honest outcome.

SIDE EFFECTS — what this tool touches, and what it never touches:
  * It NEVER writes to the live state db. It reads it with `immutable=1` (no -wal/-shm sidecars are
    created, the trap #153 was reworked for), and `--run` copies it to a throwaway scratch db under
    a TemporaryDirectory via sqlite's backup API. Write routes and ?api CRUD hit ONLY that scratch
    copy, exactly as every unit's probe demands.
  * WRITE SAFETY on a server it did not boot. 20 of the 62 routes really do INSERT. Against the
    harness's own server that is free (scratch db). Against a server from --base — or the Go port —
    the harness cannot know which db that process opened, and a server left running on this host
    reads the LIVE state db (measured: :8899 answers with X-Powered-By: PHP, :8900 answers the same
    JSON without it, both off the live db). So a write spec there is SKIPped, never sent, unless
    --allow-writes is passed explicitly. A skipped spec never counts toward a floor, so a write
    unit simply cannot be greened against an unknown server by accident.
  * It writes NO file anywhere except a report you explicitly ask for with `--json PATH`, and the
    timestamped bug report note-for-claude mandates on an unhandled exception
    (registry `bug_reports`, logs/bug_reports.jsonl).
  * `--harvest`, `--coverage` and `--plan` do not boot a server, do not need php, and touch nothing.

RUNNING IT (every form below was executed before this file was reported done):
    python3 tools/per_unit_test_harness.py --harvest
    python3 tools/per_unit_test_harness.py --coverage
    python3 tools/per_unit_test_harness.py --plan --unit go-port:db:route:tickets.recent
    python3 tools/per_unit_test_harness.py --run --unit go-port:db:route:tickets.recent --target php
    python3 tools/per_unit_test_harness.py --gate --unit go-port:db:route:tickets.recent --target php
    python3 tools/per_unit_test_harness.py --run --target php --subset db:route      # every route
    python3 tools/per_unit_test_harness.py --gate --unit go-port:tags:tag:TitleTag --target go

  --run/--gate boot an ephemeral PHP themselves (tools/serve.py's recipe: php -S with
  boot/router.php from the app root) against the scratch db, and tear it down. Pass --base URL to
  reuse a server that is already running instead.

EXIT CODES: 0 = every gated unit is green. 1 = a gate failed (a floor breach or a failing test).
2 = a usage/environment error, one line, never a traceback (a missing unit key, no php, no db).
3 = the target is not runnable here (php or the state db absent, or a Go unit that has not landed):
reported as SKIP, never as green — the #282 harness's discipline (equivalence_test.go: "It skips
cleanly — never fails — when the server, the db, the app root or the API key is absent").

Design rules obeyed (note-for-claude): python only, no shell; registry-gated (throws if it cannot
see registry.json); every path derived from __file__; php located via $CONGRUENCEY_PHP, then the
registry's paths.php, then convention; an automatic timestamped bug report on any exception.
"""
import argparse
import ast
import glob
import importlib.util
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.dont_write_bytecode = True          # import go_port_decomposer without leaving a __pycache__

HERE = os.path.dirname(os.path.abspath(__file__))       # checkouts/current/congruency/tools
FLOOR = 10                              # the ticket's floor: >=10 tests per unit, or it cannot settle
FATAL_MARKERS = ("Fatal error", "Parse error", "Uncaught", "PHP Fatal", "Stack trace",
                 "Warning:", "Notice:", "Deprecated:")


# ── registry gate (note-for-claude: a tool that cannot see the registry must throw) ──────────────
def find_registry(start=HERE):
    d = os.path.abspath(start)
    while True:
        cand = os.path.join(d, "registry.json")
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            raise FileNotFoundError("registry.json not found at/above %s" % start)
        d = parent


REGISTRY_PATH = find_registry()
REGISTRY = json.load(open(REGISTRY_PATH, encoding="utf-8"))
ROOT = os.path.dirname(REGISTRY_PATH)                          # the repo root
SOURCE = os.path.join(ROOT, "checkouts", "current", "congruency")   # the CMS app root
STATE = os.path.join(ROOT, "checkouts", "current", "state")
CONG_DB = os.path.join(STATE, "congruency.sqlite")
TOOLS = os.path.join(SOURCE, "tools")
DECOMPOSER = os.path.join(TOOLS, "go_port_decomposer.py")
SHADOW_DIR = os.path.join(ROOT, "tooling", "congruencey-tests")
SHADOW_GLOB = os.path.join(SHADOW_DIR, "*-shadow.py")
GO_DIR = os.path.join(ROOT, "congruency-go")
ROUTER = os.path.join("boot", "router.php")                    # relative to SOURCE (the cwd at boot)
SELF_FROM_ROOT = os.path.relpath(os.path.abspath(__file__), ROOT)
PHP_BASE = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")
GO_BASE = (os.environ.get("CONGRUENCY_GO_URL") or "http://127.0.0.1:8900").rstrip("/")


def bug_report(fn, exc, repro, cause):
    """note-for-claude mandates an automatic timestamped bug report on any exception:
    filename - function name - time of occurrence - methods to reproduce - possible cause."""
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "filename": SELF_FROM_ROOT,
           "function": fn, "reproduce": repro, "possible_cause": str(cause),
           "exception": "%s: %s" % (type(exc).__name__, exc),
           "traceback": traceback.format_exc()}
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        sys.stderr.write("bug report filed: %s\n" % os.path.relpath(sink, ROOT))
    except Exception as e:                                      # noqa: BLE001
        sys.stderr.write("bug report FAILED (%s); the report was:\n%s\n" % (e, json.dumps(rec)))


def die(msg):
    """Usage/environment error: one line, never a traceback (exit 2)."""
    sys.stderr.write("per_unit_test_harness: %s\n" % msg)
    sys.exit(2)


def skip(msg):
    """The target cannot run here. Reported as SKIP, never as green (exit 3)."""
    print("SKIP: %s" % msg)
    sys.exit(3)


def php_bin():
    """php via $CONGRUENCEY_PHP, then the registry's paths.php, then convention (serve.py's rule)."""
    env = os.environ.get("CONGRUENCEY_PHP")
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env
    rel = (REGISTRY.get("paths") or {}).get("php")
    if rel:
        cand = os.path.join(ROOT, rel)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    for cand in ("php", "php8"):
        for d in (os.environ.get("PATH") or "").split(os.pathsep):
            p = os.path.join(d, cand)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return None


def connect_ro(db_path):
    """Read the state db with immutable=1: identical committed data, no locking, and NO -wal/-shm
    sidecar files (mode=ro on this WAL db would create them — the #153 rework)."""
    if not os.path.isfile(db_path):
        return None
    return sqlite3.connect("file:%s?immutable=1" % db_path, uri=True)


# ── the unit universe: imported live from #230's decomposer, never re-invented ───────────────────
def load_decomposer():
    if not os.path.isfile(DECOMPOSER):
        die("the #230 decomposer is missing: %s" % os.path.relpath(DECOMPOSER, ROOT))
    spec = importlib.util.spec_from_file_location("go_port_decomposer", DECOMPOSER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_units(db_path):
    """Return (units, fixtures, go_registered_tags). The universe IS enumerate_units()'s — the same
    call --file-tickets files #230's per-unit tickets from, so a unit gated here is a unit ticketed
    there. Needs the state db read-only for the api_routes rows and the page/tag map."""
    con = connect_ro(db_path)
    if con is None:
        shown = os.path.relpath(db_path, ROOT) if db_path.startswith(ROOT) else db_path
        die("state db not found: %s\n"
            "  The unit universe is read from it (the api_routes rows and the page/tag map), and it\n"
            "  is git-ignored — so a fresh pair worktree does not have one. Point --db at a real\n"
            "  state db, e.g. the main checkout's checkouts/current/state/congruency.sqlite." % shown)
    G = load_decomposer()
    try:
        enc, deny = G.rest_encoding()
        fx = G.fixtures(con, deny)
        units, tags_by_page, emits, registered, harness = G.enumerate_units(con, enc, deny, fx)
    except SystemExit:
        raise
    except Exception as e:                                       # noqa: BLE001
        die("the #230 decomposer could not enumerate units (%s: %s).\n"
            "  Reproduce: python3 %s --json /dev/null" % (type(e).__name__, e,
                                                          os.path.relpath(DECOMPOSER, ROOT)))
    con.close()
    return units, fx, set(registered)


# ── HARVEST ─────────────────────────────────────────────────────────────────────────────────────
def shadow_suites():
    return sorted(glob.glob(SHADOW_GLOB))


def suite_checks(path):
    """Every `check(<name>, ...)` call site in one shadow suite, via AST (not a regex: a regex also
    counts the suite's own `def check(` and the word inside comments). Returns [(name, lineno)]."""
    try:
        tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
    except SyntaxError:
        return []
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "check" and n.args:
            a = n.args[0]
            name = a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else "<expr>"
            out.append((name, n.lineno))
    return sorted(out, key=lambda t: t[1])


def discriminating_hit(unit, src):
    """True iff `src` (a whole shadow suite) carries a token that can ONLY mean this unit.
    Conservative by construction — see ATTRIBUTION in the module docstring."""
    name, utype = str(unit["name"]), unit["utype"]
    if utype in ("route",):
        return "." in name and name in src
    if utype == "helper":
        return name.startswith("congruency_") and name in src
    if utype == "tag":
        if not re.search(r"[a-z][A-Z]", name):          # must be CamelCase to discriminate
            return False
        return re.search(r"(?<![\w.])%s(?![\w])" % re.escape(name), src) is not None
    if utype == "page":
        return re.search(r"page=%s(?![\w-])" % re.escape(name), src) is not None
    if utype == "crud":
        return "?api=" in src and re.search(r"(?<![\w])%s(?![\w])" % re.escape(name), src) is not None
    if utype in ("boot", "engine"):
        base = os.path.basename(str(unit.get("source") or ""))
        return bool(base) and base.endswith(".php") and base in src
    return False


def harvest(units):
    """Map every shadow check to the unit(s) it exercises. Returns (by_unit, stats)."""
    suites = shadow_suites()
    by_unit = {u["key"]: [] for u in units}
    checks_by_suite = {}
    for path in suites:
        checks_by_suite[path] = suite_checks(path)
    for path in suites:
        src = open(path, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(path, ROOT)
        for u in units:
            if discriminating_hit(u, src):
                for (name, lineno) in checks_by_suite[path]:
                    by_unit[u["key"]].append({"origin": "harvested", "suite": rel,
                                              "check": name, "line": lineno,
                                              "id": "shadow:%s#%d" % (os.path.basename(path), lineno)})
    stats = {"suites": len(suites),
             "checks": sum(len(v) for v in checks_by_suite.values()),
             "bound_units": sum(1 for v in by_unit.values() if v)}
    return by_unit, stats, checks_by_suite


def shadow_index(path):
    """The ticket names shadow_forge/shadow_index.db as a harvest source. It does not exist in this
    repository (see the module docstring). Report the truth; never fabricate rows from it."""
    if not path:
        for cand in (os.path.join(ROOT, "shadow_forge", "shadow_index.db"),
                     os.path.join(SHADOW_DIR, "shadow_index.db")):
            if os.path.isfile(cand):
                path = cand
                break
    if not path or not os.path.isfile(path):
        return {"present": False, "path": path or "shadow_forge/shadow_index.db", "tests": 0}
    con = connect_ro(path)
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {"present": True, "path": path, "tables": tables, "tests": 0}
    finally:
        con.close()


# ── GENERATE: the behaviour battery, derived from each unit's LIVE contract ──────────────────────
INJECTIONS = [("sql-comment", "' OR 1=1 --"),
              ("sql-drop", "x'); DROP TABLE tickets; --"),
              ("sql-union", "' UNION SELECT name,sql FROM sqlite_master --")]
XSS = "<script>alert(1)</script>"


WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def route_params(unit, con):
    """The route's REAL declared method/auth/params/sql, read from the api_routes row this unit was
    enumerated from. Returns (method, auth, params, sql)."""
    row = con.execute("SELECT method, auth, params, sql FROM api_routes WHERE name=?",
                      (unit["name"],)).fetchone() if con else None
    if not row:
        return "GET", "public", {}, ""
    method, auth = (row[0] or "GET").upper(), row[1] or "public"
    try:
        params = json.loads(row[2] or "{}") or {}
    except ValueError:
        params = {}
    return method.split(",")[0].strip(), auth, params, (row[3] or "")


def is_write(method, sql):
    """A write route is one whose SQL mutates. Read it off the SQL's own first keyword rather than
    guessing from the method, because that is what actually decides whether a second identical call
    can answer identically."""
    head = sql.strip().lstrip("(").split(None, 1)
    verb = head[0].upper() if head else ""
    return verb in ("INSERT", "UPDATE", "DELETE", "REPLACE") or method in WRITE_METHODS


def route_req(name, method, params):
    """Build (query, body) for one route call the way boot/rest.php actually binds params:

        $input = $_GET;
        if (POST|PUT|PATCH|DELETE) { $body = json_decode(php://input); $input = merge($input,$body); }
                                                                              (boot/rest.php:80-84)

    So the SELECTOR is always ?route=<name> in the query, and a write route's params travel in the
    JSON BODY. This is not a stylistic choice — it is required for correctness: `telemetry.record`
    declares a param literally NAMED `route` ({"kind","route","message","detail"}), so putting its
    params in the query would overwrite the selector and the dispatch would answer 404 'unknown
    route' for a route that exists. Measured exactly that before this split. It also matches the
    governed call in tools/go_port_decomposer.py's rest(), which posts its object as a JSON body."""
    if method in WRITE_METHODS:
        return {"route": name}, dict(params)
    q = {"route": name}
    q.update(params)
    return q, None


def sample(kind):
    return 1 if str(kind).startswith("int") else "x"


SQL_ERROR_MARKERS = ("SQLSTATE", "syntax error", "unrecognized token", "no such column",
                     "SQLite3::", "PDOException")


def spec(uid, kind, method, query, expect, note, body=None, baseline=None):
    """One declarative test. `baseline` is a second request the runner may send for a DIFFERENTIAL
    expectation (see no_new_sql_error) — it is what makes an injection check fair."""
    t = {"origin": "generated", "id": uid, "kind": kind, "note": note,
         "request": {"method": method, "query": query, "body": body}, "expect": expect}
    if baseline is not None:
        t["baseline"] = {"method": method, "query": baseline, "body": body}
    return t


def injection_spec(uid, method, query, baseline_query, note, extra=None):
    """An injection test with TEETH but no false positives.

    Asserting `not_contains: "SQLSTATE"` on a rendered page is UNSOUND, and this repository proves
    it: ?page=tickets renders ticket bodies, and real tickets discuss driver errors — so the page
    carries the literal text "SQLSTATE" and "syntax error" whatever you send it. Measured: the
    injected and the BENIGN request both return the identical 1,067,283 bytes containing those
    words. A marker check there fails a page that is behaving perfectly.

    So the expectation is DIFFERENTIAL instead: send the same request with a benign value for the
    same param, and fail only on a SQL-error marker the payload INTRODUCED (a count the baseline
    does not have). Content the page always carries cancels out; a genuine leak does not. Paired
    with tables_intact — which independently proves a DROP payload did not execute — this is the
    real invariant: the payload changes no SQL, and reveals no SQL."""
    exp = {"no_fatal": True, "no_new_sql_error": True, "tables_intact": ["tickets", "api_routes"]}
    exp.update(extra or {})
    return spec(uid, "injection", method, query, exp, note, baseline=baseline_query)


def route_specs(unit, con):
    """>=10 request/response specs for one route unit, every one derived from the row's own
    method/auth/params/sql. Both servers answer the identical URL, so each spec gates both."""
    name = unit["name"]
    method, auth, params, sql = route_params(unit, con)
    ok = dict((k, sample(v)) for k, v in params.items())
    writes = is_write(method, sql)

    def req(over=None, drop=False):
        p = {} if drop else dict(ok)
        p.update(over or {})
        return route_req(name, method, p)

    def sp(uid, kind, over, expect, note, drop=False):
        q, b = req(over, drop)
        return spec(uid, kind, method, q, expect, note, body=b)

    def mark_writes(specs):
        """Flag every spec whose request actually EXECUTES this route's mutating SQL. A spec that
        resolves a different route name (error-unknown-route / error-case-sensitive -> 404) or uses
        the wrong method (error-method -> 405) is refused BEFORE any SQL runs, so it writes
        nothing. The runner refuses to send a flagged spec to a server it did not boot itself
        (see WRITE SAFETY)."""
        if not writes:
            return specs
        for s in specs:
            if s["request"]["method"] == method and (s["request"]["query"] or {}).get("route") == name:
                s["writes"] = True
        return specs

    out = []
    # contract — the shape rest.php promises: {"route": <name>, "rows"|"affected"|"rowid": ...}
    if writes:
        # A write route's params are FK-bound to real data (ticket.assign takes an agent_id that
        # must exist), and this harness synthesises values from the declared TYPES, which are all
        # the api_routes row gives it. A synthetic "x" can therefore be legitimately refused by a
        # real constraint — measured: ticket.assign answers 500 on a fresh scratch db, and that is
        # the route working, not failing. So the unit-scoped claim a synthetic value CAN prove is
        # that the dispatch RESOLVES this route and answers a JSON envelope without a PHP fatal.
        # It keeps its teeth: a 404/405 (route gone, or the method contract broken) still fails.
        out.append(sp("contract-resolves", "contract", None,
                      {"status_not": [404, 405], "json": True, "no_fatal": True,
                       "content_type": "json"},
                      "the dispatch resolves this write route and answers a JSON envelope (a "
                      "synthetic param may be refused by a real constraint; a 404/405 may not)"))
    else:
        out.append(sp("contract-ok", "contract", None,
                      {"status": [200], "json": True, "no_fatal": True, "json_eq": {"route": name},
                       "content_type": "json"},
                      "the route answers its own name with the declared params bound"))
    out.append(sp("contract-content-type", "contract", None,
                  {"json": True, "content_type": "json", "no_fatal": True},
                  "the reply is JSON, not HTML"))
    if writes:
        # A write route CANNOT be byte-deterministic: each INSERT answers a fresh rowid, and
        # asserting otherwise fails a route that is behaving exactly right (measured on all 19 of
        # them). The sound invariant is that the reply SHAPE is stable — the same JSON keys.
        out.append(sp("contract-shape-stable", "contract", None,
                      {"json_keys_stable": True, "no_fatal": True},
                      "a write answers a stable JSON shape (its rowid/affected legitimately move, "
                      "so the bytes cannot be asserted identical)"))
    else:
        out.append(sp("contract-deterministic", "contract", None,
                      {"deterministic": True, "no_fatal": True},
                      "two identical reads answer identically (the equivalence precondition)"))
    # error — rest.php:66,70 are the literal contract
    q_unknown, b_unknown = route_req(name + ".__nope__", method, ok)
    out.append(spec("error-unknown-route", "error", method, q_unknown,
                    {"status": [404], "json": True, "error": True, "no_fatal": True},
                    "an unknown route is 404 + an error envelope (rest.php:66)", body=b_unknown))
    variant = name.upper() if name.upper() != name else name + "__X"
    q_case, b_case = route_req(variant, method, ok)
    out.append(spec("error-case-sensitive", "error", method, q_case,
                    {"status": [404], "json": True, "error": True, "no_fatal": True},
                    "route lookup is exact; a case/suffix variant does not resolve", body=b_case))
    other = "GET" if method in WRITE_METHODS else "POST"
    # The selector ONLY — no params. rest.php checks the method (:69-71) BEFORE it binds any param
    # (:80-84), so params cannot change this verdict; and sending them would reintroduce the very
    # collision route_req() exists to avoid (telemetry.record's param named `route` would overwrite
    # the selector in the query and turn an expected 405 into a 404 'unknown route').
    out.append(spec("error-method", "error", other, {"route": name},
                    {"status": [405, 401, 400], "json": True, "error": True, "no_fatal": True},
                    "the declared method is enforced (rest.php:70 -> 405 method not allowed)"))
    out.append(sp("edge-missing-params", "edge", None,
                  {"json": True, "no_fatal": True},
                  "omitting every param must not crash the engine", drop=True))
    # injection — the consumer params are bound (prepared); prove it end-to-end
    key = sorted(params)[0] if params else "id"
    for (tag, payload) in INJECTIONS:
        q, b = req({key: payload})
        bq, bb = req({key: sample(params.get(key, "str"))})
        t = spec("injection-" + tag, "injection", method, q,
                 {"no_fatal": True, "no_new_sql_error": True, "json": True,
                  "tables_intact": ["tickets", "api_routes"]},
                 "a bound :param cannot escape its placeholder (payload on %s: %s)" % (key, payload),
                 body=b)
        t["baseline"] = {"method": method, "query": bq, "body": bb}
        out.append(t)
    # edge — the declared types, pushed to their boundaries
    for k, ty in sorted(params.items()):
        cases = (("nonnumeric", "abc"), ("zero", 0), ("negative", -1), ("huge", 9007199254740993)) \
            if str(ty).startswith("int") else \
            (("empty", ""), ("unicode", "ünïcodé-✓"), ("long", "A" * 512))
        for label, v in cases:
            out.append(sp("edge-%s-%s-%s" % ("int" if str(ty).startswith("int") else "str", k, label),
                          "edge", {k: v}, {"json": True, "no_fatal": True},
                          "param %s at %s must not crash" % (k, label)))
    out.append(sp("edge-extra-param", "edge", {"__unexpected__": "1"},
                  {"json": True, "no_fatal": True},
                  "an undeclared param is ignored, not bound"))
    return mark_writes(out)


def html_specs(unit, url_query, subject):
    """The shared battery for every HTML surface (page / tag / boot / engine)."""
    out = []
    out.append(spec("contract-ok", "contract", "GET", dict(url_query),
                    {"status": [200], "no_fatal": True, "content_type": "html"},
                    "%s renders with HTTP 200 and no PHP fatal/warning" % subject))
    out.append(spec("contract-nonempty", "contract", "GET", dict(url_query),
                    {"min_bytes": 1, "no_fatal": True}, "%s renders a non-empty body" % subject))
    out.append(spec("contract-deterministic", "contract", "GET", dict(url_query),
                    {"deterministic": True, "no_fatal": True},
                    "two identical renders are byte-identical (the equivalence precondition)"))
    out.append(spec("contract-tags-expanded", "contract", "GET", dict(url_query),
                    {"not_contains": ["<<<"], "no_fatal": True},
                    "every <<<Tag>>> invocator is expanded; no raw marker survives"))
    out.append(spec("recursion-parity-bounded", "recursion-parity", "GET", dict(url_query),
                    {"max_bytes": 8 * 1024 * 1024, "no_fatal": True},
                    "the recursive re-parse is depth-bounded: output is finite (the depth cap the "
                    "engine enforces; an un-capped re-parse would not terminate)"))
    out.append(spec("recursion-parity-stable", "recursion-parity", "GET",
                    dict(url_query, fresh="1"),
                    {"status": [200], "no_fatal": True, "not_contains": ["<<<"]},
                    "a POM rebuild (?fresh=1) re-scans the tag dir and still terminates expanded"))
    for (tag, payload) in INJECTIONS:
        out.append(injection_spec("injection-" + tag, "GET", dict(url_query, q=payload),
                                  dict(url_query, q="benign"),
                                  "a query param cannot reach the SQL (payload: %s)" % payload))
    out.append(spec("injection-xss-escaped", "injection", "GET", dict(url_query, q=XSS),
                    {"no_fatal": True, "not_contains": [XSS]},
                    "a reflected param is escaped, never echoed as live markup"))
    out.append(spec("error-unknown-param", "error", "GET", dict(url_query, __unexpected__="1"),
                    {"status": [200], "no_fatal": True},
                    "an undeclared query param is ignored, not fatal"))
    return out


def crud_specs(unit, fx):
    table = fx.get("table") or "tickets"
    verb = unit["name"]
    out = []
    out.append(spec("contract-tables", "contract", "GET", {"api": "tables"},
                    {"status": [200], "json": True, "no_fatal": True, "json_key": "tables",
                     "content_type": "json"},
                    "?api=tables lists the CRUD surface this verb dispatches on"))
    out.append(spec("contract-list", "contract", "GET", {"api": table},
                    {"status": [200], "json": True, "no_fatal": True, "content_type": "json"},
                    "?api=%s answers JSON rows" % table))
    out.append(spec("contract-deterministic", "contract", "GET", {"api": table, "limit": 5},
                    {"deterministic": True, "no_fatal": True},
                    "two identical reads answer identically"))
    out.append(spec("error-unknown-table", "error", "GET", {"api": "__no_such_table__"},
                    {"status": [400, 404], "json": True, "error": True, "no_fatal": True},
                    "a table outside the allowlist is refused, never queried"))
    out.append(spec("error-denylisted", "error", "GET", {"api": "api_keys"},
                    {"json": True, "error": True, "no_fatal": True},
                    "an admin-denylisted table is refused (rest.php's denylist)"))
    for (tag, payload) in INJECTIONS:
        out.append(spec("injection-table-" + tag, "injection", "GET", {"api": payload},
                        {"json": True, "error": True, "no_fatal": True,
                         "tables_intact": ["tickets", "api_routes"]},
                        "the table name is validated against sqlite_master, never interpolated"))
        out.append(injection_spec("injection-filter-" + tag, "GET", {"api": table, "id": payload},
                                  {"api": table, "id": 1},
                                  "a filter value is bound, never interpolated",
                                  extra={"json": True}))
    out.append(spec("edge-limit-zero", "edge", "GET", {"api": table, "limit": 0},
                    {"json": True, "no_fatal": True}, "limit=0 must not crash"))
    out.append(spec("edge-limit-nonnumeric", "edge", "GET", {"api": table, "limit": "abc"},
                    {"json": True, "no_fatal": True}, "a non-numeric limit must not crash"))
    out.append(spec("edge-order-injection", "edge", "GET", {"api": table, "order": "id.'; --"},
                    {"json": True, "no_fatal": True, "tables_intact": ["tickets", "api_routes"]},
                    "the order column is validated against table_info, never interpolated"))
    return out


def specs_for(unit, con, fx):
    """The generated request/response battery for one unit, by its surface (the map is each unit's
    own #230 probe — see the module docstring)."""
    t = unit["utype"]
    if t == "route":
        return route_specs(unit, con)
    if t == "helper":
        u2 = dict(unit)
        u2["name"] = fx.get("route") or "agent.prompt"      # helpers are reached ONLY via ?route=
        out = route_specs(u2, con)
        for s in out:
            s["note"] = "%s (exercised through ?route=%s, the only surface that runs it)" % (
                s["note"], u2["name"])
        return out
    if t == "crud":
        return crud_specs(unit, fx)
    if t == "tag":
        return html_specs(unit, {"page": "tags", "tag": unit["name"]}, "tag <<<%s>>>" % unit["name"])
    if t == "page":
        return html_specs(unit, {"page": unit["name"]}, "?page=%s" % unit["name"])
    # boot / engine: no URL of their own -> the page surface whose behaviour they decide
    page = fx.get("page") or "about"
    return html_specs(unit, {"page": page},
                      "%s (no URL of its own; proven through ?page=%s, the chain it decides)"
                      % (unit["name"], page))


def suite_for(unit, harvested, con, fx):
    """One unit's full suite = its shadow-derived (harvested) tests + its generated specs.

    THE COVERAGE RULE, and why it is stricter than "generate only the gap". The ticket says: count
    the harvested tests, and where the count is under 10, generate the missing ones. Filling only
    the gap would leave a unit with 8 harvested + 2 generated — and since a harvested shadow check
    drives PHP internals and can never run against Go (run_unit reports it php-only), that unit
    would face the Go target with 2 tests. A Go gate of 2 tests is a vacuous gate. So every unit
    gets its FULL generated battery, which is >= FLOOR (10) specs by construction for every
    surface. The ticket's floor is therefore met by target-runnable specs ALONE, for every unit and
    every target, and the harvested tests are additional PHP-side evidence layered on top — never a
    substitute for it. `--coverage` prints the two counts separately so the split is legible, and
    asserts the invariant: the generated battery alone never falls under the floor.
    """
    return list(harvested) + specs_for(unit, con, fx)


# ── RUN: one runner, two targets, the shared request/response contract ───────────────────────────
class Server(object):
    """An ephemeral PHP original booted the way tools/serve.py boots it (php -S with boot/router.php
    from the app root), pointed by $CONGRUENCY_CONFIG at a SCRATCH db so no unit's writes can ever
    reach the live one."""

    def __init__(self, php, db_path, tmp):
        self.php, self.db_path, self.tmp = php, db_path, tmp
        self.proc = None
        self.base = None

    def _port(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p

    def scratch_db(self):
        """A throwaway copy of the state db via sqlite's backup API — the source is opened
        immutable=1, so the live file is read and never locked, and no sidecar is created."""
        dst = os.path.join(self.tmp, "scratch.sqlite")
        src = connect_ro(self.db_path)
        out = sqlite3.connect(dst)
        with out:
            src.backup(out)
        out.close()
        src.close()
        return dst

    def start(self):
        db = self.scratch_db()
        cfg = os.path.join(self.tmp, "install.json")
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({"CONGRUENCY_SQLITE": db, "USELOG_DEBUG": False}, fh)
        port = self._port()
        env = dict(os.environ, CONGRUENCY_CONFIG=cfg)
        self.log = open(os.path.join(self.tmp, "server.log"), "w+", encoding="utf-8")
        self.proc = subprocess.Popen([self.php, "-S", "127.0.0.1:%d" % port, ROUTER],
                                     cwd=SOURCE, env=env, stdout=self.log, stderr=self.log)
        self.base = "http://127.0.0.1:%d" % port
        for _ in range(120):
            if self.proc.poll() is not None:
                self.log.seek(0)
                die("the PHP server exited at boot (rc=%s):\n%s" % (self.proc.returncode,
                                                                    self.log.read()[:800]))
            try:
                with socket.create_connection(("127.0.0.1", port), 0.25):
                    return self.base
            except OSError:
                time.sleep(0.05)
        self.stop()
        die("the PHP server did not answer on 127.0.0.1:%d within 6s" % port)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def lower_headers(h):
    """Header names are case-INSENSITIVE (RFC 9110 §5.1), and this app proves it: the ?page= HTML
    surface answers with `Content-type` while the ?route=/?api= JSON surface answers with
    `Content-Type` (both verified against the live server). dict(resp.headers) keeps whatever case
    the server sent, so every lookup here goes through one lower-cased copy — matching on a single
    spelling would false-FAIL every HTML unit for a reason that has nothing to do with the port."""
    return dict((str(k).lower(), v) for k, v in (h or {}).items())


def send(base, req, timeout=20):
    """One request over the contract both targets serve. Returns (status, headers, body-bytes),
    headers lower-cased."""
    q = dict((k, v) for k, v in (req.get("query") or {}).items() if v is not None)
    url = base + "/?" + urllib.parse.urlencode(q, doseq=False)
    data = json.dumps(req["body"]).encode() if req.get("body") is not None else None
    r = urllib.request.Request(url, data=data, method=req.get("method") or "GET",
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.getcode(), lower_headers(resp.headers), resp.read()
    except urllib.error.HTTPError as e:                     # 4xx/5xx are answers, not failures
        return e.code, lower_headers(e.headers), e.read()
    except Exception as e:                                  # noqa: BLE001
        return None, {}, ("<transport-failure> %s: %s" % (type(e).__name__, e)).encode()


def evaluate(base, t, status, headers, body):
    """Check one test's expectations against one response. Returns [] if green, else the reasons."""
    exp = t["expect"]
    text = body.decode("utf-8", "replace")
    bad = []
    if status is None:
        return ["transport failure: %s" % text[:120]]
    if "status" in exp and status not in exp["status"]:
        bad.append("status %s not in %s" % (status, exp["status"]))
    if "status_not" in exp and status in exp["status_not"]:
        bad.append("status %s is one of the forbidden %s" % (status, exp["status_not"]))
    if exp.get("no_fatal"):
        for m in FATAL_MARKERS:
            if m in text:
                bad.append("PHP fatal/warning marker in body: %r" % m)
                break
    doc = None
    if exp.get("json") or "json_eq" in exp or "json_key" in exp or "error" in exp:
        try:
            doc = json.loads(text)
        except ValueError:
            bad.append("body is not JSON: %r" % text[:80])
    if doc is not None:
        if "error" in exp:
            has = isinstance(doc, dict) and "error" in doc
            if has != bool(exp["error"]):
                bad.append("error envelope present=%s, expected=%s" % (has, bool(exp["error"])))
        for k, v in (exp.get("json_eq") or {}).items():
            if not isinstance(doc, dict) or doc.get(k) != v:
                bad.append("json[%r]=%r, expected %r" % (k, (doc or {}).get(k), v))
        if "json_key" in exp and not (isinstance(doc, dict) and exp["json_key"] in doc):
            bad.append("json key %r missing" % exp["json_key"])
    if "content_type" in exp:
        ct = headers.get("content-type") or ""          # already lower-cased by send()
        if exp["content_type"] not in ct:
            bad.append("content-type %r lacks %r" % (ct, exp["content_type"]))
    for s in (exp.get("contains") or []):
        if s not in text:
            bad.append("body lacks %r" % s)
    for s in (exp.get("not_contains") or []):
        if s in text:
            bad.append("body contains forbidden %r" % s)
    if "min_bytes" in exp and len(body) < exp["min_bytes"]:
        bad.append("body %dB < min %dB" % (len(body), exp["min_bytes"]))
    if "max_bytes" in exp and len(body) > exp["max_bytes"]:
        bad.append("body %dB > max %dB (unbounded recursion)" % (len(body), exp["max_bytes"]))
    if exp.get("no_new_sql_error"):
        # Differential: only a marker the PAYLOAD introduced counts. Markers the surface always
        # carries (?page=tickets renders ticket bodies that discuss driver errors) cancel out.
        base_req = t.get("baseline")
        if not base_req:
            bad.append("no_new_sql_error needs a baseline request (harness bug)")
        else:
            bs, bh, bb = send(base, base_req)
            btext = bb.decode("utf-8", "replace")
            for m in SQL_ERROR_MARKERS:
                if text.count(m) > btext.count(m):
                    bad.append("payload introduced SQL-error marker %r (%d occurrence(s) vs %d "
                               "with a benign value)" % (m, text.count(m), btext.count(m)))
    if exp.get("json_keys_stable"):
        # The write-route analogue of determinism: the bytes legitimately move (a fresh rowid), the
        # SHAPE must not.
        s2, h2, b2 = send(base, t["request"])
        try:
            k1 = sorted(json.loads(text).keys())
            k2 = sorted(json.loads(b2.decode("utf-8", "replace")).keys())
            if k1 != k2:
                bad.append("reply shape moved between two calls: %s vs %s" % (k1, k2))
        except (ValueError, AttributeError):
            bad.append("a write route must answer a JSON object twice; got %r" % text[:80])
    if exp.get("deterministic"):
        s2, h2, b2 = send(base, t["request"])
        if b2 != body:
            bad.append("two identical requests differed (%dB vs %dB)" % (len(body), len(b2)))
    for tbl in (exp.get("tables_intact") or []):
        st, hh, bb = send(base, {"method": "GET", "query": {"api": "tables"}})
        try:
            names = json.loads(bb.decode("utf-8", "replace")).get("tables") or []
        except (ValueError, AttributeError):
            names = []
        if names and tbl not in names:
            bad.append("table %r is GONE after the payload (injection executed)" % tbl)
    return bad


_SUITE_CACHE = {}


def suite_run(rel):
    """Execute one shadow suite ONCE per process and cache its output. A suite prints every one of
    its checks in a single run, so running it once per harvested check would re-run the same suite
    dozens of times (ticket-authorization-shadow.py carries 21 checks) for identical output."""
    if rel in _SUITE_CACHE:
        return _SUITE_CACHE[rel]
    path = os.path.join(ROOT, rel)
    try:
        r = subprocess.run([sys.executable, path], cwd=os.path.dirname(path),
                           capture_output=True, text=True, timeout=600)
        got = (r.returncode, (r.stdout or "") + (r.stderr or ""))
    except subprocess.TimeoutExpired:
        got = (124, "<timed out>")
    _SUITE_CACHE[rel] = got
    return got


def run_harvested(t):
    """Run a harvested shadow check against PHP by executing its suite and reading that check's own
    ✓/✗ line. Returns (verdict, reasons). It drives PHP internals, so it is php-only: --target go
    reports it, never greens it.

    A suite whose php is not provisioned is SKIPped, never failed: the shadow suites resolve php at
    the in-repo path (tooling/congruencey-harness/php/php) which is git-ignored and therefore absent
    from a fresh worktree. That is an environment fact, not a defect in the unit under test — the
    #282 harness's discipline (skip cleanly, never false-green and never false-fail)."""
    rc, out = suite_run(t["suite"])
    if "php-not-provisioned" in out:
        return "SKIP", ["php not provisioned for %s: the suite resolves php at the git-ignored "
                        "in-repo path; provision it (tools/provision_php.py) to run this test"
                        % os.path.basename(t["suite"])]
    if rc == 124:
        return "FAIL", ["shadow suite timed out: %s" % t["suite"]]
    name = t["check"]
    if name == "<expr>":                      # a computed check name: fall back to the suite verdict
        return ("PASS", []) if rc == 0 else ("FAIL", ["suite %s exited %d" % (t["suite"], rc)])
    # the suites print one line per check as "  <marker> <name>", so the name ENDS the line; an
    # endswith match cannot collide the way a substring match can (one check name prefixing another)
    for line in out.splitlines():
        if line.rstrip().endswith(name):
            if "FAIL" in line or "✗" in line:
                return "FAIL", ["shadow check FAILED: %s" % line.strip()]
            return "PASS", []
    return "FAIL", ["shadow check %r not reported by %s (exit %d)" % (name, t["suite"], rc)]


def run_unit(unit, tests, target, base, verbose, owns_server=False, allow_writes=False):
    """Run one unit's suite against one target. Returns (passed, failed, skipped, on_target, rows).

    WRITE SAFETY. A write-route spec really does INSERT. When this harness boots the server itself
    it points it at a throwaway scratch db, so those writes are free. When the server comes from
    --base (or is the Go port), the harness CANNOT know which db that process opened — and the
    servers a developer leaves running read the LIVE state db. So a write spec is SKIPped there
    unless --allow-writes says otherwise. Every #230 write unit's own probe demands exactly this:
    "THIS UNIT WRITES: give each server its OWN scratch db and never the live one"."""
    rows = []
    for t in tests:
        if t["origin"] == "harvested":
            if target == "go":
                rows.append((t, "SKIP", ["php-only: a shadow check drives PHP internals; it cannot "
                                         "gate the Go target"]))
                continue
            verdict, bad = run_harvested(t)
            rows.append((t, verdict, bad))
            continue
        if t.get("writes") and not owns_server and not allow_writes:
            rows.append((t, "SKIP", ["this spec WRITES and the server was not booted by this "
                                     "harness, so its db is unknown (a running server reads the "
                                     "LIVE db). Point it at a scratch db and pass --allow-writes"]))
            continue
        status, headers, body = send(base, t["request"])
        bad = evaluate(base, t, status, headers, body)
        rows.append((t, "PASS" if not bad else "FAIL", bad))
    for (t, verdict, bad) in rows:
        if verdict == "PASS" and not verbose:
            continue
        tid = t.get("id") or t.get("check")
        print("    %-4s %-34s %s" % (verdict, tid, "" if not bad else "| " + "; ".join(bad)))
    p = sum(1 for r in rows if r[1] == "PASS")
    f = sum(1 for r in rows if r[1] == "FAIL")
    s = sum(1 for r in rows if r[1] == "SKIP")
    # Tests that actually interrogated THIS target. Only a generated spec does: it is the only kind
    # sent over the wire to `base`. A harvested shadow check runs its suite in a subprocess against
    # the php the SUITE resolves for itself, so it answers the same way whatever --base points at —
    # a mutation run against a deliberately wrong target proved exactly that (28 harvested checks
    # still "passed"). Counting one toward a target's floor would be counting a test that never
    # touched the target, so the floor counts these and only these.
    on_target = sum(1 for r in rows if r[0]["origin"] == "generated" and r[1] in ("PASS", "FAIL"))
    return p, f, s, on_target, rows


# ── the unit -> Go landing map (a Go gate only applies "per Go unit as it lands") ────────────────
def go_landed(unit, registered):
    if unit["utype"] == "tag":
        return unit["name"] in registered
    return os.path.isdir(GO_DIR)        # the route/page/crud surface is served by congruency-go


# ── reports ─────────────────────────────────────────────────────────────────────────────────────
def select(units, subset, key):
    if key:
        out = [u for u in units if u["key"] == key]
        if not out:
            die("no such unit: %s\n  List them with: python3 %s --coverage" % (key, SELF_FROM_ROOT))
        return out
    if subset:
        return [u for u in units if subset in u["key"]]
    return units


def main():
    ap = argparse.ArgumentParser(
        prog="per_unit_test_harness.py",
        description="The per-unit test harness for the congruency-go port (#233): harvest the "
                    "reusable tests from the shadow suites, enforce >=10 per unit, and run one "
                    "unit's suite against a TARGET (php|go) over the request/response contract "
                    "both servers share. A unit with <10 tests or a failing test cannot settle.",
        epilog="Exit: 0 green | 1 a gate failed | 2 usage/environment error | 3 target not runnable "
               "here (SKIP, never green).")
    ap.add_argument("--harvest", action="store_true",
                    help="map every shadow check to the unit it exercises and report the map")
    ap.add_argument("--coverage", action="store_true",
                    help="per-unit counts: harvested + generated vs the floor of %d" % FLOOR)
    ap.add_argument("--plan", action="store_true", help="print one unit's whole suite, run nothing")
    ap.add_argument("--run", action="store_true", help="run the suite against --target")
    ap.add_argument("--gate", action="store_true",
                    help="run, then exit 1 unless every selected unit has >=%d tests and zero "
                         "failures (the settle gate)" % FLOOR)
    ap.add_argument("--unit", metavar="KEY", help="one unit key, e.g. go-port:db:route:agent.roster")
    ap.add_argument("--subset", default="", metavar="SPEC",
                    help="every unit whose key contains SPEC, e.g. 'db:route', 'tags:tag:'")
    ap.add_argument("--target", default="php", choices=("php", "go"),
                    help="which implementation answers the requests (default php)")
    ap.add_argument("--base", metavar="URL",
                    help="reuse a server already running instead of booting one "
                         "(php default %s, go default %s)" % (PHP_BASE, GO_BASE))
    ap.add_argument("--db", default=CONG_DB, metavar="PATH",
                    help="the state db to enumerate units from and to copy a scratch from "
                         "(read-only, immutable=1; default %s)" % os.path.relpath(CONG_DB, ROOT))
    ap.add_argument("--shadow-index", metavar="PATH",
                    help="the ticket's shadow_forge/shadow_index.db, if it is ever produced; it "
                         "does not exist in this repository and the harvest says so")
    ap.add_argument("--allow-writes", action="store_true",
                    help="permit write-route specs against a server this harness did NOT boot "
                         "(--base / the Go port). Refused by default: such a server's db is "
                         "unknown, and the servers left running read the LIVE state db. Pass this "
                         "only when you know the target opened a scratch db.")
    ap.add_argument("--json", metavar="PATH", help="also write the full report as JSON to PATH")
    ap.add_argument("-v", "--verbose", action="store_true", help="print PASS lines too")
    a = ap.parse_args()

    if not (a.harvest or a.coverage or a.plan or a.run or a.gate):
        ap.print_help()
        return 0
    if (a.plan or a.run or a.gate) and not (a.unit or a.subset):
        die("--plan/--run/--gate need --unit KEY or --subset SPEC")

    units, fx, registered = load_units(a.db)
    by_unit, stats, checks_by_suite = harvest(units)
    idx = shadow_index(a.shadow_index)
    con = connect_ro(a.db)

    if a.harvest:
        print("HARVEST — the reusable tests, pulled from the shadow suites")
        print("  suites parsed        : %d  (%s/*-shadow.py)" % (stats["suites"],
                                                                 os.path.relpath(SHADOW_DIR, ROOT)))
        print("  check call sites     : %d  (AST-counted, not a regex)" % stats["checks"])
        print("  shadow_index.db      : %s" % ("parsed: %s" % idx["path"] if idx["present"] else
                                               "ABSENT — %s does not exist in this repository; "
                                               "harvesting from the suites alone" % idx["path"]))
        print("  units enumerated     : %d  (live, from tools/go_port_decomposer.py)" % len(units))
        print("  units with harvest   : %d" % stats["bound_units"])
        print("  units needing fill   : %d  (harvest < %d)"
              % (sum(1 for u in units if len(by_unit[u["key"]]) < FLOOR), FLOOR))
        print()
        for u in units:
            h = by_unit[u["key"]]
            if not h:
                continue
            suites = sorted(set(x["suite"] for x in h))
            print("  %-44s %2d test(s) from %s" % (u["key"], len(h),
                                                   ", ".join(os.path.basename(s) for s in suites)))

    if a.coverage:
        print("COVERAGE — every unit maps to its tests; gaps are filled to the floor of %d" % FLOOR)
        print("  'generated' alone must clear the floor: harvested shadow checks are php-only and")
        print("  cannot gate Go, so they are never counted toward a target's teeth (see suite_for).")
        print("  %-44s %8s %9s %6s %s" % ("unit", "harvest", "generated", "total", "floor"))
        bad = 0
        for u in units:
            h = by_unit[u["key"]]
            tests = suite_for(u, h, con, fx)
            g = len(tests) - len(h)
            under = g < FLOOR or len(tests) < FLOOR
            if under:
                bad += 1
            print("  %-44s %8d %9d %6d %s" % (u["key"], len(h), g, len(tests),
                                              "UNDER" if under else "ok"))
        print("\n  %d unit(s) below the floor of %d (counting generated specs alone)" % (bad, FLOOR))
        if bad:
            return 1

    if a.plan:
        for u in select(units, a.subset, a.unit):
            tests = suite_for(u, by_unit[u["key"]], con, fx)
            print("PLAN %s — %d test(s) (floor %d)" % (u["key"], len(tests), FLOOR))
            for t in tests:
                if t["origin"] == "harvested":
                    print("  harvested  %-30s %s:%d" % (t["check"][:30], t["suite"], t["line"]))
                else:
                    q = urllib.parse.urlencode(t["request"]["query"])
                    print("  %-10s %-30s %s /?%s" % (t["kind"], t["id"], t["request"]["method"], q))
                    print("             expect %s" % json.dumps(t["expect"]))

    report = {"units": [], "target": a.target, "floor": FLOOR, "harvest": stats,
              "shadow_index": idx}
    rc = 0
    if a.run or a.gate:
        chosen = select(units, a.subset, a.unit)
        target_base, server, tmpdir = a.base, None, None
        if a.target == "go":
            unlanded = [u["key"] for u in chosen if not go_landed(u, registered)]
            if unlanded and len(unlanded) == len(chosen):
                skip("the Go port has not landed for %s (a Go gate applies per unit as it lands). "
                     "Registered Go tags: %d." % (", ".join(unlanded[:3]), len(registered)))
            target_base = a.base or GO_BASE
            sp_url = urllib.parse.urlsplit(target_base)
            try:
                socket.create_connection((sp_url.hostname, int(sp_url.port or 80)), 2).close()
            except OSError:
                skip("no Go server answering at %s — start congruency-go, or pass --base URL. "
                     "(This harness boots the PHP original itself; it does not build Go.)" % target_base)
        elif not target_base:
            php = php_bin()
            if not php:
                skip("no php: set $CONGRUENCEY_PHP, or provision the registry's paths.php (%s). "
                     "It is git-ignored, so a fresh worktree does not have one."
                     % (REGISTRY.get("paths") or {}).get("php"))
            if not os.path.isfile(a.db):
                skip("no state db at %s to copy a scratch from; pass --db PATH." % a.db)
            tmpdir = tempfile.TemporaryDirectory()
            server = Server(php, a.db, tmpdir.name)
            target_base = server.start()
            print("booted the PHP original on %s (scratch db; the live db is never written)"
                  % target_base)
        try:
            for u in chosen:
                tests = suite_for(u, by_unit[u["key"]], con, fx)
                print("  %s — %d test(s) against %s" % (u["key"], len(tests), a.target))
                p, f, s, on_target, rows = run_unit(u, tests, a.target, target_base, a.verbose,
                                                    owns_server=(server is not None),
                                                    allow_writes=a.allow_writes)
                # A unit settles against a target only if >=FLOOR tests actually INTERROGATED that
                # target and nothing failed. A skipped test, or a harvested check that never touched
                # the target, proves nothing about it and never counts (see run_unit).
                floor_ok = on_target >= FLOOR
                green = (f == 0) and floor_ok
                print("    => %d passed, %d failed, %d skipped | floor %d on-target/%d %s | %s"
                      % (p, f, s, on_target, FLOOR, "ok" if floor_ok else "UNDER",
                         "GREEN" if green else "NOT GREEN"))
                report["units"].append({"unit": u["key"], "tests": len(tests),
                                        "on_target": on_target, "passed": p, "failed": f,
                                        "skipped": s, "floor_ok": floor_ok, "green": green})
                if a.gate and not green:
                    rc = 1
                    reason = ("only %d test(s) interrogated %s, floor is %d"
                              % (on_target, a.target, FLOOR) if not floor_ok
                              else "%d failing test(s)" % f)
                    print("    GATE: %s CANNOT SETTLE against %s — %s" % (u["key"], a.target, reason))
        finally:
            if server:
                server.stop()
            if tmpdir:
                tmpdir.cleanup()
        if a.gate and rc == 0:
            print("GATE: every selected unit is green against %s and meets the floor of %d"
                  % (a.target, FLOOR))

    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)
        print("report written: %s" % a.json)
    if con:
        con.close()
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:                                     # noqa: BLE001
        bug_report("main", exc, " ".join([sys.executable, os.path.abspath(__file__)] + sys.argv[1:]),
                   exc)
        sys.stderr.write("per_unit_test_harness: %s: %s\n" % (type(exc).__name__, exc))
        sys.exit(2)
