#!/usr/bin/env python3
"""tag_selfcheck.py — the tag asset self-check: every dev tag's disk/db dependencies, verified.

WHY (the pattern this catches, twice over): a tag references content that no test exercises,
so when the content moves or empties the tag silently degrades. OmniExplorer / ForgeView /
ShadowForge / MemGraph once pointed at a *retired* forge home and errored with nothing to
notice; RepoDocs renders "No repo documentation ingested yet" because its backing table is
empty. This tool makes those dependencies explicit and checks them on every run.

WHAT IT CHECKS, per tag under checkouts/current/congruency/invocators/tags/dev/*.php:

  1. EXTERNAL SQLITE (the `getenv('X') ?: getenv('HOME').'/…default'` pattern). Both the env
     name and the default path are parsed. The db path must exist AND open read-only; its
     referenced tables must exist. Resolved exactly as the tag resolves it: env override if
     set in this process's environment, else the HOME-relative default. (ForgeView→FORGE_DB,
     OmniExplorer→OMNI_INDEX_DB, ShadowForge→SHADOW_FORGE_DB, MemGraph→MEM_GRAPH_DB.)

  2. CONGRUENCY_SQLITE TABLES. For a tag that opens `new PDO('sqlite:'.CONGRUENCY_SQLITE)`,
     every table name parsed out of a FROM/JOIN in one of its SQL string-literals must exist
     in the state db. Tables whose being EMPTY makes the tag render its empty-state
     (repo_docs, repos, code_blobs) are reported WARN (not FAIL) with the tag named.

  3. DB-STORED DISK PATHS. Every repos.forge_remote value (the bare-git remotes TreeView reads)
     must exist on disk.

  4. STANDALONE RENDER. Each tag is rendered over HTTP at ?page=tags&tag=NAME on the live
     server (default 127.0.0.1:8899, the same gallery route TagList uses). Output containing a
     PHP Fatal / Parse error / Warning is a FAIL — that is precisely the silent-error class
     above, made loud.

A dependency is one report row: (tag, dependency, status, detail). status is OK / WARN / FAIL.
Exit 0 when nothing FAILs (WARN-only still exits 0, warnings listed); exit 1 when anything
FAILs. --file-tickets POSTs one de-duped bug ticket per FAIL through rest.php ticket.create,
skipping any whose title already exists among open (OPEN/REQUESTED) tickets.

SIDE-EFFECT DISCIPLINE (playbook Theme 3): every sqlite handle is opened with the URI flag
`immutable=1`, never `mode=ro`. The state db is WAL-mode; `mode=ro` would spin up `-wal`/`-shm`
sidecar files in the state directory on every run, `immutable=1` reads the identical committed
bytes and creates NOTHING. The tool never writes to any db and creates no files (the only
POST is the opt-in --file-tickets ticket.create through the governed REST surface). All checks
are reads; the HTTP renders are GETs.

Registry-gated per note-for-claude: walks UP from this file to registry.json and refuses to run
if it cannot see it.

Usage:
    python3 tag_selfcheck.py                 # check + report; exit 0/1
    python3 tag_selfcheck.py --file-tickets  # also file a bug ticket per FAIL (de-duped)
    python3 tag_selfcheck.py --url http://127.0.0.1:8899 --db /path/to/congruency.sqlite
"""
import argparse
import glob
import json
import os
import re
import sqlite3
import sys
import urllib.request


# ── registry gate (note-for-claude: a tool that cannot see the registry throws) ──────────────────
def find_root(start):
    d = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(d, "registry.json")):
            return d
        nxt = os.path.dirname(d)
        if nxt == d:
            raise RuntimeError("registry.json not found walking up from %s — refusing to run" % start)
        d = nxt


ROOT = find_root(os.path.dirname(os.path.abspath(__file__)))
# CONGRUENCY_SQLITE default mirrors boot/configure.php: state is a sibling of the app root, i.e.
# checkouts/current/state/congruency.sqlite (app root = checkouts/current/congruency).
DEFAULT_DB = os.path.join(ROOT, "checkouts", "current", "state", "congruency.sqlite")
TAGS_DIR = os.path.join(ROOT, "checkouts", "current", "congruency", "invocators", "tags", "dev")
DEFAULT_URL = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")

# Tables whose emptiness the tags treat as a first-class empty-state (a render, not a crash):
#   repo_docs  -> RepoDocs "No repo documentation ingested yet." / SemanticSearch has no docs
#   repos      -> TreeView "No repos registered."
#   code_blobs -> SourceList shows no sources
EMPTY_STATE_TABLES = {"repo_docs", "repos", "code_blobs"}

OK, WARN, FAIL = "OK", "WARN", "FAIL"

# A displayed PHP engine error: the error word, then " … on line N" (plain or html_errors form).
# Requiring the "on line N" anchor keeps prose like a stray "Warning:" in tag content from matching.
RE_PHP_ERR = re.compile(
    r"(?is)(?:<b>\s*)?(?:php\s+)?"
    r"(fatal error|parse error|warning|catchable fatal error|recoverable fatal error)"
    r"(?:\s*</b>)?\s*:.{0,300}?\bon line\b\s*(?:<b>)?\s*\d+")

# FROM/JOIN table name — parsed ONLY from string-literals that actually contain SELECT, so English
# prose such as "read straight from its forge remote" never registers as a table reference.
RE_FROM = re.compile(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)
RE_SELECT = re.compile(r"\bSELECT\b", re.I)
# the tag opens the state db (as opposed to merely mentioning it in a comment)
RE_CONG_PDO = re.compile(r"new\s+PDO\(\s*(['\"])sqlite:\1\s*\.\s*CONGRUENCY_SQLITE", re.I)
# the external-db default: getenv('HOME') . '/…something.db'
RE_DEFAULT = re.compile(r"getenv\(\s*'HOME'\s*\)\s*\.\s*'([^']+\.db)'")
# any getenv('NAME') other than HOME — the env override for the external db
RE_ENV = re.compile(r"getenv\(\s*'([A-Za-z0-9_]+)'\s*\)")


# ── parse one tag file into its declared dependencies ────────────────────────────────────────────
def scan_php(src):
    """Split PHP source into (code, literals): a quote/comment-aware pass so an apostrophe inside a
    "…" string, or a quote inside a // or /* */ comment, can never mis-pair. `code` has comments
    blanked (string literals kept verbatim), so the getenv/new-PDO patterns match only real code;
    `literals` is the list of string-literal contents, from which SQL table names are read."""
    code, literals = [], []
    i, n = 0, len(src)
    while i < n:
        c, two = src[i], src[i:i + 2]
        if two == "//" or c == "#":
            j = src.find("\n", i)
            j = n if j < 0 else j
            code.append(" " * (j - i)); i = j; continue
        if two == "/*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            code.append(" " * (j - i)); i = j; continue
        if c == "'" or c == '"':
            q, start, i, buf = c, i, i + 1, []
            while i < n:
                d = src[i]
                if d == "\\" and i + 1 < n:
                    buf.append(src[i + 1]); i += 2; continue
                if d == q:
                    i += 1; break
                buf.append(d); i += 1
            literals.append("".join(buf))
            code.append(src[start:i]); continue
        code.append(c); i += 1
    return "".join(code), literals


def sql_tables(literals):
    """Distinct FROM/JOIN table names, taken only from string-literals that actually contain SELECT."""
    tables = set()
    for s in literals:
        if RE_SELECT.search(s):
            for t in RE_FROM.findall(s):
                tables.add(t)
    return tables


def parse_tag(path):
    src = open(path, encoding="utf-8", errors="replace").read()
    name = os.path.basename(path)[:-4]
    code, literals = scan_php(src)
    tables = sql_tables(literals)
    defaults = RE_DEFAULT.findall(code)
    envs = [e for e in RE_ENV.findall(code) if e != "HOME"]
    external = None
    if defaults:
        # each of the four external tags declares exactly one override env + one default .db path
        external = {"env": envs[0] if envs else None, "default": getenv_home(defaults[0])}
    return {
        "name": name,
        "external": external,                        # {env, default} or None
        "uses_cong": bool(RE_CONG_PDO.search(code)),  # opens CONGRUENCY_SQLITE
        "tables": tables,                            # FROM/JOIN names from its SQL
        "reads_forge_remote": ("forge_remote" in code and "repos" in tables),
    }


def getenv_home(suffix):
    """Resolve getenv('HOME') . '<suffix>' the way PHP does, using this process's HOME."""
    return (os.environ.get("HOME") or os.path.expanduser("~")) + suffix


def resolve_external(ext):
    """Resolve the external db path: env override if set (non-empty), else the HOME default —
    mirroring `getenv('X') ?: getenv('HOME').'/…default'`."""
    if ext["env"]:
        v = os.environ.get(ext["env"])
        if v:
            return v, "%s (env)" % ext["env"]
    return ext["default"], "%s default" % (ext["env"] or "HOME")


# ── read-only sqlite (immutable=1: no writes, no -wal/-shm sidecars, no files) ────────────────────
_db_cache = {}


def open_ro(path):
    """Open a db strictly read-only. Returns a connection or raises. immutable=1 (not mode=ro) so a
    WAL db is read without creating sidecar files (playbook Theme 3)."""
    if path in _db_cache:
        return _db_cache[path]
    con = sqlite3.connect("file:%s?immutable=1" % path, uri=True)
    con.execute("SELECT 1")   # force sqlite to actually touch the header now, so a bad file raises here
    _db_cache[path] = con
    return con


def db_table_set(con):
    return set(r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"))


def table_count(con, table):
    return con.execute("SELECT COUNT(*) FROM \"%s\"" % table).fetchone()[0]


# ── HTTP render (GET only) ───────────────────────────────────────────────────────────────────────
def http_get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.getcode(), r.read().decode("utf-8", "replace")


# ── the check: build report rows ─────────────────────────────────────────────────────────────────
def run_checks(url, db_path):
    rows = []   # each: dict(tag, dep, status, detail)

    def add(tag, dep, status, detail):
        rows.append({"tag": tag, "dep": dep, "status": status, "detail": detail})

    # the state db, opened once read-only (shared by every CONGRUENCY_SQLITE tag)
    cong_con, cong_tables = None, set()
    if os.path.isfile(db_path):
        try:
            cong_con = open_ro(db_path)
            cong_tables = db_table_set(cong_con)
        except Exception as e:  # noqa: BLE001
            cong_con = None
            add("(state db)", "congruency.sqlite", FAIL, "could not open read-only: %s" % e)
    else:
        add("(state db)", "congruency.sqlite", FAIL, "not found at %s" % db_path)

    # is the render server up? one health GET; if down, renders become WARN (never bogus FAILs)
    server_down = None
    try:
        http_get(url + "/index.php?page=tags")
        server_down = False
    except Exception as e:  # noqa: BLE001
        server_down = True
        server_err = str(e)

    tags = sorted(glob.glob(os.path.join(TAGS_DIR, "*.php")))
    if not tags:
        add("(tags)", TAGS_DIR, FAIL, "no tag files found — wrong tree?")

    for path in tags:
        t = parse_tag(path)
        name = t["name"]

        # 1) external db: path exists + opens read-only, then its tables
        target_con = None
        if t["external"]:
            epath, how = resolve_external(t["external"])
            dep = "db:%s (%s)" % (os.path.basename(epath), how)
            if not os.path.isfile(epath):
                add(name, dep, FAIL, "external db not found at %s" % epath)
            else:
                try:
                    target_con = open_ro(epath)
                    add(name, dep, OK, "opened read-only (immutable=1) at %s" % epath)
                except Exception as e:  # noqa: BLE001
                    add(name, dep, FAIL, "exists but did not open as sqlite: %s" % e)
            target_tables = db_table_set(target_con) if target_con else set()
            target_label = os.path.basename(epath)
        elif t["uses_cong"]:
            target_con = cong_con
            target_tables = cong_tables
            target_label = "congruency.sqlite"
        else:
            target_con, target_tables, target_label = None, set(), None

        # 2) referenced tables exist in the relevant db (+ empty-state WARNs)
        if target_con is not None:
            for tbl in sorted(t["tables"]):
                dep = "table:%s in %s" % (tbl, target_label)
                if tbl.startswith("sqlite_"):
                    # sqlite_master / sqlite_sequence etc. are built-in system tables, always present
                    add(name, dep, OK, "sqlite system table (always present)")
                    continue
                if tbl not in target_tables:
                    add(name, dep, FAIL, "referenced table missing from %s" % target_label)
                    continue
                if tbl in EMPTY_STATE_TABLES:
                    try:
                        n = table_count(target_con, tbl)
                    except Exception as e:  # noqa: BLE001
                        add(name, dep, FAIL, "could not count rows: %s" % e)
                        continue
                    if n == 0:
                        add(name, dep, WARN,
                            "empty (0 rows) — %s renders its empty-state for this table" % name)
                    else:
                        add(name, dep, OK, "present, %d rows" % n)
                else:
                    add(name, dep, OK, "present in %s" % target_label)
        elif t["tables"]:
            # SQL tables parsed but no db handle resolved — surface it rather than skip silently
            add(name, "tables:%s" % ",".join(sorted(t["tables"])), WARN,
                "tag references tables but no db handle was resolved")

        # 3) repos.forge_remote paths on disk (the bare remotes TreeView reads)
        if t["reads_forge_remote"] and cong_con is not None and "repos" in cong_tables:
            try:
                paths = [r[0] for r in cong_con.execute(
                    "SELECT forge_remote FROM repos WHERE forge_remote IS NOT NULL")]
            except Exception as e:  # noqa: BLE001
                paths = None
                add(name, "repos.forge_remote", FAIL, "could not read forge_remote: %s" % e)
            if paths is not None:
                missing = [p for p in paths if not os.path.exists(p)]
                dep = "repos.forge_remote (%d paths)" % len(paths)
                if not paths:
                    add(name, dep, WARN, "no forge_remote paths (repos empty)")
                elif missing:
                    sample = ", ".join(missing[:5]) + (" …" if len(missing) > 5 else "")
                    add(name, dep, FAIL, "%d of %d missing on disk: %s" % (len(missing), len(paths), sample))
                else:
                    add(name, dep, OK, "%d/%d exist on disk" % (len(paths), len(paths)))

        # 4) standalone render over HTTP
        rdep = "render ?page=tags&tag=%s" % name
        if server_down:
            add(name, rdep, WARN, "server unreachable at %s — render check skipped (%s)" % (url, server_err))
        else:
            try:
                code, body = http_get("%s/index.php?page=tags&tag=%s" % (url, name))
            except Exception as e:  # noqa: BLE001
                add(name, rdep, FAIL, "render request failed: %s" % e)
            else:
                m = RE_PHP_ERR.search(body)
                if m:
                    snippet = re.sub(r"\s+", " ", body[m.start():m.end()]).strip()
                    add(name, rdep, FAIL, "PHP error in output: %s" % snippet[:220])
                else:
                    add(name, rdep, OK, "clean (HTTP %s, %d bytes)" % (code, len(body)))

    return rows


# ── report ───────────────────────────────────────────────────────────────────────────────────────
def print_report(rows):
    tw = max([len(r["tag"]) for r in rows] + [3])
    dw = max([len(r["dep"]) for r in rows] + [10])
    dw = min(dw, 46)
    print("TAG SELF-CHECK — %d dependency checks\n" % len(rows))
    print("%-4s  %-*s  %-*s  %s" % ("", tw, "TAG", dw, "DEPENDENCY", "DETAIL"))
    print("%-4s  %-*s  %-*s  %s" % ("----", tw, "-" * tw, dw, "-" * dw, "------"))
    for r in rows:
        print("%-4s  %-*s  %-*s  %s" % (r["status"], tw, r["tag"], dw, r["dep"][:dw], r["detail"]))
    n_ok = sum(1 for r in rows if r["status"] == OK)
    n_warn = sum(1 for r in rows if r["status"] == WARN)
    n_fail = sum(1 for r in rows if r["status"] == FAIL)
    print("\nSUMMARY: %d OK · %d WARN · %d FAIL   (of %d checks)" % (n_ok, n_warn, n_fail, len(rows)))
    if n_warn:
        print("\nWARN (non-fatal — expected empty-state or unreachable render):")
        for r in rows:
            if r["status"] == WARN:
                print("  - %s / %s: %s" % (r["tag"], r["dep"], r["detail"]))
    if n_fail:
        print("\nFAIL:")
        for r in rows:
            if r["status"] == FAIL:
                print("  - %s / %s: %s" % (r["tag"], r["dep"], r["detail"]))
    return n_fail


# ── --file-tickets: one de-duped bug ticket per FAIL, through the governed REST surface ───────────
def secret(name):
    path = os.path.join(os.path.dirname(ROOT), ".secrets", "ats.env")
    if os.path.isfile(path):
        for line in open(path):
            if line.strip().startswith(name + "="):
                return line.strip().split("=", 1)[1]
    return os.environ.get(name)


def rest(url, route, api_key, obj=None):
    u = url + "/rest.php?route=" + route
    if obj is None:
        req = urllib.request.Request(u, method="GET", headers={"X-Api-Key": api_key or ""})
    else:
        req = urllib.request.Request(u, data=json.dumps(obj).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Api-Key": api_key or ""})
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read().decode())
    if isinstance(out, dict) and "error" in out:
        raise RuntimeError("route %s failed: %s" % (route, out["error"]))
    return out


def file_tickets(url, rows):
    fails = [r for r in rows if r["status"] == FAIL]
    if not fails:
        print("\n--file-tickets: no FAILs to file.")
        return
    api_key = secret("CONGRUENCY_API_KEY")
    if not api_key:
        print("\n--file-tickets: no CONGRUENCY_API_KEY (secrets or env) — cannot file; skipping.")
        return
    try:
        open_rows = rest(url, "ticket.queue", api_key).get("rows", [])
    except Exception as e:  # noqa: BLE001
        print("\n--file-tickets: could not read open tickets (ticket.queue): %s — skipping." % e)
        return
    open_titles = set(r.get("title", "") for r in open_rows)

    print("\n--file-tickets: %d FAIL(s); %d open ticket(s) for de-dup." % (len(fails), len(open_rows)))
    filed = set()
    for r in fails:
        title = "tag_selfcheck FAIL: %s / %s" % (r["tag"], r["dep"])
        if title in open_titles or title in filed:
            print("  skip (already open): %s" % title)
            continue
        body = ("tag_selfcheck detected a failing dependency.\n\n"
                "tag:        %s\ndependency: %s\ndetail:     %s\n\n"
                "Reproduce:  python3 checkouts/current/congruency/tools/tag_selfcheck.py"
                % (r["tag"], r["dep"], r["detail"]))
        try:
            out = rest(url, "ticket.create", api_key, {
                "component": "congruency", "severity": "normal",
                "title": title, "body": body, "patch": ""})
            print("  filed #%s: %s" % (out.get("rowid", "?"), title))
            filed.add(title)
        except Exception as e:  # noqa: BLE001
            print("  ERROR filing %r: %s" % (title, e))


def main():
    ap = argparse.ArgumentParser(description="self-check of every dev tag's disk/db dependencies")
    ap.add_argument("--url", default=DEFAULT_URL, help="server base URL for render checks (default %s)" % DEFAULT_URL)
    ap.add_argument("--db", default=DEFAULT_DB, help="path to the congruency state sqlite (default: repo state db)")
    ap.add_argument("--file-tickets", action="store_true", help="POST one de-duped bug ticket per FAIL via rest.php")
    a = ap.parse_args()

    rows = run_checks(a.url.rstrip("/"), a.db)
    n_fail = print_report(rows)
    if a.file_tickets:
        file_tickets(a.url.rstrip("/"), rows)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
