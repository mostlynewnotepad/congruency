#!/usr/bin/env python3
"""tag_selfcheck.py — self-check every dev tag's disk/db dependencies, on an ongoing basis.

WHY (the pattern, twice now): a tag references content on disk or in a table that no test
exercises, and it silently degrades. OmniExplorer/ForgeView/ShadowForge/MemGraph were pointed
at a RETIRED forge home and rendered a graceful "not found" instead of data; RepoDocs renders
"No repo documentation ingested yet" because its backing table `repo_docs` is empty. Neither
is a PHP crash, so a render-only harness (tagcheck.py / tag_test_harness.py) calls them clean.
This tool checks the *dependencies themselves*, standalone, so those quiet failures surface.

WHAT IT CHECKS. It enumerates every tag under invocators/tags/dev/*.php (a *.php file whose
source contains `Tag_Interface`, keyed by basename-minus-.php — the same universe the gallery
lists, so ?tag=NAME resolves for each) and, per tag, extracts and verifies three dependency
kinds:

  (1) EXTERNAL SQLITE DBS — the `getenv('X') ?: $HOME/<default>` pattern the four forge-reflection
      tags use (ForgeView/OMNI/ShadowForge/MemGraph). Both the env-var name AND the default path
      are parsed. The dep is VERIFIED by resolving the path (getenv override, else default) and
      requiring the file to EXIST and OPEN as sqlite read-only. Read-only means the URI flag
      `immutable=1`, NOT `mode=ro`: a WAL-journalled db opened `mode=ro` spins up `-wal`/`-shm`
      sidecar files on every open (a forbidden write); `immutable=1` reads the identical committed
      data and creates ZERO files. This tool creates no files and writes to no db it checks.

  (2) SQL TABLES — every table name after FROM/JOIN in the tag's SQL string literals. Tables of a
      forge tag are verified against ITS external db; tables of every other tag against
      CONGRUENCY_SQLITE (checkouts/current/state/congruency.sqlite). A referenced table that does
      not exist is a FAIL. A table whose being EMPTY makes the tag render its empty-state
      (repo_docs, repos, code_blobs) is reported WARN, naming the tag, when it is empty — the tag
      is not broken, but it has nothing to show.

  (3) DB-STORED DISK PATHS — repos.forge_remote, the bare-git remotes TreeView reads trees/blobs
      from (any tag that SELECTs forge_remote from repos). Every stored path must EXIST on disk.

Then it RENDERS every tag standalone over HTTP (?page=tags&tag=NAME on 127.0.0.1:8899) and FAILs
any whose body contains a PHP Fatal / Warning / Parse error. Note: the render check flags PHP
ENGINE errors only — NOT the graceful "cy-form-error"/"not found" degradation, which is a tag
behaving correctly against an absent dependency and is already caught by (1)-(3) above. If no
server answers on the base URL, the tool boots an ephemeral one (php -S with boot/router.php, the
serve.py bootstrap) and tears it down when done.

OUTPUT. A labeled report — one row per (tag, dependency, status, detail), status in
{OK, WARN, FAIL}. Exit 1 if ANY row is FAIL; exit 0 otherwise (WARN-only still exits 0, with the
warnings listed). --file-tickets POSTs one de-duped bug ticket per FAIL through the governed
rest.php ticket.create route (X-Api-Key from ../.secrets/ats.env relative to the repo root, the
same source pair_loop.py uses), skipping any FAIL whose ticket title already exists among the
open (OPEN/REQUESTED) tickets.

Pure-python stdlib, one file, read-only against every db it opens. Registry-gated per
note-for-claude: it walks UP to registry.json and refuses to run if it cannot find it.

    python3 tools/tag_selfcheck.py                 # check against http://127.0.0.1:8899
    python3 tools/tag_selfcheck.py --base URL      # reuse a server already running there
    python3 tools/tag_selfcheck.py --file-tickets  # also file a de-duped bug ticket per FAIL
    python3 tools/tag_selfcheck.py --json out.json  # also dump a machine-readable report
"""
import argparse
import glob
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request


# ── registry gate (note-for-claude: a tool that cannot see the registry throws) ──────────────────
def find_registry(start):
    d = os.path.abspath(start)
    while True:
        p = os.path.join(d, "registry.json")
        if os.path.isfile(p):
            return d, json.load(open(p))
        nxt = os.path.dirname(d)
        if nxt == d:
            raise RuntimeError("registry.json not found walking up from %s — refusing to run" % start)
        d = nxt


ROOT, REGISTRY = find_registry(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "checkouts", "current", "congruency")   # the CMS app root (php cwd at serve time)
DEV_TAGS = os.path.join(SOURCE, "invocators", "tags", "dev")
ROUTER = os.path.join("boot", "router.php")                          # relative to SOURCE
STATE = os.path.join(ROOT, "checkouts", "current", "state")
CONG_DB = os.path.join(STATE, "congruency.sqlite")

# Tables whose EMPTINESS is a known empty-state (the tag renders "nothing yet", not a crash).
EMPTY_STATE_TABLES = {"repo_docs", "repos", "code_blobs"}

# PHP ENGINE error markers for the render check. Deliberately NOT "cy-form-error"/"error:" — those
# are the graceful degradation a tag shows against a missing dependency (checked as WARN/FAIL in the
# dependency pass), not a code fault. These strings mean the PHP interpreter itself faulted.
PHP_ERR = ("PHP Fatal", "Fatal error", "Parse error", "Uncaught", "Stack trace",
           "Warning:", "Notice:", "Deprecated:")

BASE_DEFAULT = "http://127.0.0.1:8899"


# ── PHP lexer: strings + de-commented code, in ONE left-to-right pass ─────────────────────────────
def lex(src):
    """Walk PHP source once, tracking string vs. comment state, and return
    (code_without_comments, [string_literal_contents...]). Doing both in one pass is what keeps an
    apostrophe in prose (e.g. a /* wizard's tail */ comment) from desyncing quote pairing — a naive
    regex for 'single-quoted' strings pairs that stray ' with a real code quote and swallows whole
    SQL statements. Line comments: // and #. Block comments: /* */. String escapes: \\<any>."""
    code, lits = [], []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            i += 2
            while i < n and src[i] != "\n":
                i += 1
        elif c == "#":
            i += 1
            while i < n and src[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                i += 1
            i += 2
        elif c == "'" or c == '"':
            q = c
            j = i + 1
            buf = []
            while j < n:
                if src[j] == "\\" and j + 1 < n:      # escape: consume the escaped char verbatim
                    buf.append(src[j + 1])
                    j += 2
                    continue
                if src[j] == q:
                    break
                buf.append(src[j])
                j += 1
            lits.append("".join(buf))
            code.append(src[i:j + 1])                 # keep the whole literal in the de-commented code
            i = j + 1
        else:
            code.append(c)
            i += 1
    return "".join(code), lits


GETENV = re.compile(r"getenv\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\)")
HOME_DEFAULT = re.compile(r"getenv\(\s*['\"]HOME['\"]\s*\)\s*\.\s*(['\"])(.*?)\1", re.S)
FROM_JOIN = re.compile(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)
SELECT = re.compile(r"\bSELECT\b", re.I)


def tables_of(literals):
    """Table names after FROM/JOIN, taken ONLY from string literals that contain SELECT (so HTML
    prose that happens to read 'straight from its forge remote' is never mistaken for a table)."""
    t = set()
    for lit in literals:
        if SELECT.search(lit):
            for name in FROM_JOIN.findall(lit):
                t.add(name)
    return t


def external_db(code):
    """The `getenv('X') ?: $HOME/<default>` external-db pattern, or None. Env vars other than HOME
    name the db; getenv('HOME') . '<suffix>' is the default path. Resolves the same way the tag
    does: the env override if set, else the default path."""
    envs = [e for e in GETENV.findall(code) if e != "HOME"]
    if not envs:
        return None
    env = envs[0]
    m = HOME_DEFAULT.search(code)
    default = (os.environ.get("HOME", "") + m.group(2)) if m else None
    resolved = os.environ.get(env) or default
    return {"env": env, "default": default, "path": resolved}


# ── tag discovery (mirrors TagList::scan, scoped to dev/ per the ticket) ──────────────────────────
def discover():
    tags = {}
    for path in sorted(glob.glob(os.path.join(DEV_TAGS, "*.php"))):
        src = open(path, "r", errors="replace").read()
        if "Tag_Interface" not in src:
            continue
        tags[os.path.basename(path)[:-4]] = src
    return tags


# ── read-only sqlite (immutable=1: reads committed data, creates NO -wal/-shm sidecars) ───────────
def ro_connect(path):
    return sqlite3.connect("file:%s?immutable=1" % path, uri=True)


def table_names(path):
    con = ro_connect(path)
    try:
        return {r[0].lower() for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def table_count(con, table):
    return con.execute('SELECT COUNT(*) FROM "%s"' % table.replace('"', '')).fetchone()[0]


# ── dependency verification ───────────────────────────────────────────────────────────────────────
def check_dependencies(tags, cong_con, cong_tables):
    """Return report rows: {tag, dep, status, detail}. status in OK / WARN / FAIL."""
    rows = []
    for tag in sorted(tags):
        code, lits = lex(tags[tag])
        sql_tables = tables_of(lits)
        ext = external_db(code)

        if ext:
            # (1) external db: resolve, require exists + opens read-only via immutable=1
            path = ext["path"]
            opened = None
            if not path:
                rows.append({"tag": tag, "dep": "external db %s" % ext["env"],
                             "status": "FAIL", "detail": "could not resolve a path (no env, no default)"})
            elif not os.path.isfile(path):
                rows.append({"tag": tag, "dep": "external db %s -> %s" % (ext["env"], path),
                             "status": "FAIL", "detail": "path does not exist on disk"})
            else:
                try:
                    opened = table_names(path)
                    rows.append({"tag": tag, "dep": "external db %s -> %s" % (ext["env"], path),
                                 "status": "OK", "detail": "exists, opens read-only (immutable=1)"})
                except sqlite3.Error as e:
                    rows.append({"tag": tag, "dep": "external db %s -> %s" % (ext["env"], path),
                                 "status": "FAIL", "detail": "will not open as sqlite: %s" % e})
            # (2) its SQL tables live in the external db
            label = os.path.basename(path) if path else ext["env"]
            for tbl in sorted(sql_tables):
                if tbl.lower().startswith("sqlite_"):
                    rows.append({"tag": tag, "dep": "table %s in %s" % (tbl, label),
                                 "status": "OK", "detail": "sqlite internal catalog (always present)"})
                elif opened is None:
                    rows.append({"tag": tag, "dep": "table %s in %s" % (tbl, label),
                                 "status": "FAIL", "detail": "db unavailable — cannot verify table"})
                elif tbl.lower() in opened:
                    rows.append({"tag": tag, "dep": "table %s in %s" % (tbl, label),
                                 "status": "OK", "detail": "present"})
                else:
                    rows.append({"tag": tag, "dep": "table %s in %s" % (tbl, label),
                                 "status": "FAIL", "detail": "missing from the external db"})
        else:
            # (2) SQL tables of every other tag live in CONGRUENCY_SQLITE
            for tbl in sorted(sql_tables):
                if tbl.lower().startswith("sqlite_"):
                    rows.append({"tag": tag, "dep": "table %s" % tbl,
                                 "status": "OK", "detail": "sqlite internal catalog (always present)"})
                    continue
                if tbl.lower() not in cong_tables:
                    rows.append({"tag": tag, "dep": "table %s" % tbl,
                                 "status": "FAIL", "detail": "missing from congruency.sqlite"})
                    continue
                if tbl.lower() in EMPTY_STATE_TABLES and table_count(cong_con, tbl) == 0:
                    rows.append({"tag": tag, "dep": "table %s" % tbl, "status": "WARN",
                                 "detail": "empty — %s renders its empty-state" % tag})
                else:
                    rows.append({"tag": tag, "dep": "table %s" % tbl, "status": "OK", "detail": "present"})

        # (3) db-stored disk paths: repos.forge_remote (TreeView reads its bare git remote from here)
        if not ext and "repos" in {t.lower() for t in sql_tables} and re.search(r"\bforge_remote\b", code):
            remotes = [r[0] for r in cong_con.execute("SELECT forge_remote FROM repos")]
            missing = [r for r in remotes if not (r and os.path.exists(r))]
            if not remotes:
                rows.append({"tag": tag, "dep": "repos.forge_remote paths", "status": "WARN",
                             "detail": "no repos registered — nothing to browse"})
            elif missing:
                rows.append({"tag": tag, "dep": "repos.forge_remote paths (%d)" % len(remotes), "status": "FAIL",
                             "detail": "%d path(s) absent on disk, e.g. %s"
                                       % (len(missing), ", ".join(str(m) for m in missing[:3]))})
            else:
                rows.append({"tag": tag, "dep": "repos.forge_remote paths (%d)" % len(remotes),
                             "status": "OK", "detail": "all present on disk"})
    return rows


# ── HTTP render check ─────────────────────────────────────────────────────────────────────────────
def http_get(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                            # noqa: BLE001  (connection refused, etc.)
        return None, "%r" % e


def check_renders(tags, base):
    rows = []
    for tag in sorted(tags):
        st, body = http_get("%s/?page=tags&tag=%s" % (base, tag))
        markers = [m for m in PHP_ERR if m in body]
        if st == 200 and not markers:
            rows.append({"tag": tag, "dep": "render ?page=tags&tag=%s" % tag,
                         "status": "OK", "detail": "HTTP 200, no PHP error"})
        else:
            detail = ("HTTP %s" % st) + ((" — " + ", ".join(markers)) if markers else "")
            rows.append({"tag": tag, "dep": "render ?page=tags&tag=%s" % tag, "status": "FAIL", "detail": detail})
    return rows


# ── ephemeral server (only if the base URL answers nothing) ───────────────────────────────────────
def server_up(base):
    try:
        urllib.request.urlopen(base + "/?page=tags", timeout=4)
        return True
    except urllib.error.HTTPError:
        return True                                   # answered with any code => it is up
    except Exception:                                 # noqa: BLE001
        return False


def find_php():
    env = os.environ.get("CONGRUENCEY_PHP")
    if env and os.path.isfile(env):
        return env
    rel = (REGISTRY.get("paths", {}) or {}).get("php", "tooling/congruencey-harness/php/php")
    cand = os.path.join(ROOT, rel)
    if os.path.isfile(cand):
        return cand
    raise RuntimeError("php not found (checked $CONGRUENCEY_PHP and %s); provision it first "
                       "(tools/provision_php.py)" % cand)


def boot_server():
    """php -S on a free port with boot/router.php, cwd=SOURCE (the serve.py bootstrap). Returns
    (proc, base). Needs the live state db so the tags have something to read."""
    if not os.path.isfile(CONG_DB):
        raise RuntimeError("no state db at %s — restore it, or point --base at a running server" % CONG_DB)
    php = find_php()
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    base = "http://127.0.0.1:%d" % port
    proc = subprocess.Popen([php, "-S", "127.0.0.1:%d" % port, ROUTER], cwd=SOURCE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 15
    while time.time() < deadline:
        if server_up(base):
            return proc, base
        time.sleep(0.25)
    proc.terminate()
    raise RuntimeError("ephemeral php server did not become ready on %s" % base)


# ── --file-tickets: one de-duped bug ticket per FAIL, through the governed route ──────────────────
def api_key():
    """CONGRUENCY_API_KEY from ../.secrets/ats.env relative to the repo root (as pair_loop reads it),
    or the environment."""
    path = os.path.join(os.path.dirname(ROOT), ".secrets", "ats.env")
    if os.path.isfile(path):
        for line in open(path):
            if line.strip().startswith("CONGRUENCY_API_KEY="):
                return line.strip().split("=", 1)[1]
    return os.environ.get("CONGRUENCY_API_KEY")


def open_ticket_titles(base):
    st, body = http_get(base + "/rest.php?route=ticket.queue")
    if st != 200:
        return None                                   # cannot enumerate — caller decides
    try:
        return {r.get("title", "") for r in json.loads(body).get("rows", [])}
    except ValueError:
        return None


def ticket_title(row):
    return "tag-selfcheck FAIL: %s — %s" % (row["tag"], row["dep"])


def file_tickets(base, fails):
    key = api_key()
    if not key:
        print("== file-tickets == no CONGRUENCY_API_KEY (../.secrets/ats.env or env) — cannot POST; skipped")
        return
    existing = open_ticket_titles(base)
    if existing is None:
        print("== file-tickets == could not read open tickets (ticket.queue) — refusing to risk duplicates")
        return
    filed = skipped = 0
    for row in fails:
        title = ticket_title(row)
        if title in existing:
            skipped += 1
            continue
        payload = {"component": "congruency", "severity": "normal", "patch": "",
                   "title": title,
                   "body": "tag_selfcheck.py found a failing dependency.\n\ntag: %s\ndependency: %s\ndetail: %s"
                           % (row["tag"], row["dep"], row["detail"])}
        req = urllib.request.Request(base + "/rest.php?route=ticket.create",
                                     data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Api-Key": key})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                out = json.loads(r.read().decode())
            if "error" in out:
                print("== file-tickets == ticket.create refused for %r: %s" % (title, out["error"]))
                continue
            existing.add(title)
            filed += 1
            print("== filed == #%s %s" % (out.get("rowid", "?"), title))
        except Exception as e:                         # noqa: BLE001
            print("== file-tickets == POST failed for %r: %s" % (title, e))
    print("== file-tickets == %d filed, %d skipped (title already open)" % (filed, skipped))


# ── report ────────────────────────────────────────────────────────────────────────────────────────
def render_report(rows):
    order = {"FAIL": 0, "WARN": 1, "OK": 2}
    rows = sorted(rows, key=lambda r: (r["tag"], order[r["status"]], r["dep"]))
    n_fail = sum(1 for r in rows if r["status"] == "FAIL")
    n_warn = sum(1 for r in rows if r["status"] == "WARN")
    n_ok = sum(1 for r in rows if r["status"] == "OK")
    tags = len({r["tag"] for r in rows})
    print("=== tag_selfcheck — %d tags, %d OK, %d WARN, %d FAIL ===\n" % (tags, n_ok, n_warn, n_fail))
    print("  %-6s %-16s %-44s %s" % ("STATUS", "TAG", "DEPENDENCY", "DETAIL"))
    print("  " + "-" * 100)
    for r in rows:
        print("  %-6s %-16s %-44s %s" % (r["status"], r["tag"], r["dep"], r["detail"]))
    if n_warn:
        print("\n  WARN (empty-state / nothing to show — not a failure):")
        for r in rows:
            if r["status"] == "WARN":
                print("    %s — %s: %s" % (r["tag"], r["dep"], r["detail"]))
    print()
    return n_fail, n_warn, n_ok


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(description="self-check every dev tag's disk/db dependencies")
    ap.add_argument("--base", default=BASE_DEFAULT,
                    help="server to render/REST against (default %s); an ephemeral one is booted if it is down" % BASE_DEFAULT)
    ap.add_argument("--file-tickets", action="store_true",
                    help="POST one de-duped bug ticket per FAIL via rest.php ticket.create")
    ap.add_argument("--json", metavar="PATH", default="", help="also write the report rows as JSON")
    a = ap.parse_args()

    if not os.path.isfile(CONG_DB):
        print("tag_selfcheck: no state db at %s — cannot verify tables (restore state first)" % CONG_DB)
        return 2

    tags = discover()
    if not tags:
        print("tag_selfcheck: no Tag_Interface tags under %s" % DEV_TAGS)
        return 2

    cong_con = ro_connect(CONG_DB)
    try:
        cong_tables = {r[0].lower() for r in cong_con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        rows = check_dependencies(tags, cong_con, cong_tables)
    finally:
        cong_con.close()

    base = a.base.rstrip("/")
    proc = None
    try:
        if not server_up(base):
            print("== render == no server on %s; booting an ephemeral one" % base)
            proc, base = boot_server()
        rows += check_renders(tags, base)

        n_fail, n_warn, _ = render_report(rows)
        fails = [r for r in rows if r["status"] == "FAIL"]
        if a.file_tickets and fails:
            file_tickets(base, fails)
    finally:
        if proc:
            proc.terminate()

    if a.json:
        json.dump({"base": base, "rows": rows}, open(a.json, "w"), indent=2)
        print("JSON: %s" % a.json)

    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
