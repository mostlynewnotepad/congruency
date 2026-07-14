#!/usr/bin/env python3
"""ingest_self.py -- mirror the running source + docs into the CMS DB, content-addressed by git blob hash.

On each crank (post-commit) this pushes the running source into the CMS DB (CONGRUENCY_SQLITE, the unified
~/.jazz/congruency.sqlite) so the CMS can render its own source and documentation. Content is deduped by
git blob hash; a reverse-lookup (path @ commit) names each blob and gives every file its version history;
`is_current=1` flags the blob for each path in the checked-out HEAD tree = the RUNNING source. Code and
docs live in separate tables.

    python3 tools/ingest_self.py             # --head (default): ingest the HEAD tree + re-flag current
    python3 tools/ingest_self.py --backfill  # walk source history into the archive, then flag current
    python3 tools/ingest_self.py --stats     # print row counts
    python3 tools/ingest_self.py --ensure-pages  # create tables + the source/docs entry Documents

Registry-gated, python-only, best-effort (never blocks a commit); Variant-A bug report on exception.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = None   # repo root (dir of registry.json); set in main()

CODE_EXT = (".php", ".py")
DOC_EXT = (".md", ".txt")
DOC_TXT_PREFIXES = ("checkouts/current/doc/",)   # .txt is a doc ONLY here (legacy 2006 CMS docs) — not stray prompts/cookie jars
IGNORE_SUBSTR = ("tooling/congruencey/", "tooling/tournament-", "/vendor/", "/node_modules/")
CODE_PREFIXES = (
    "checkouts/current/lib/", "checkouts/current/invocators/", "checkouts/current/boot/",
    "checkouts/current/www/", "checkouts/current/bin/",
    "checkouts/current/tools/", "checkouts/current/versioning/", "tracker/",
)
MAIN_EXTRAS = ("deploy.py", "install.py")            # deploy/stand-up-teardown tooling (lives on `main`)
LANG = {".php": "php", ".py": "python", ".md": "markdown", ".txt": "text"}

DDL = [
    "CREATE TABLE IF NOT EXISTS code_blobs (hash TEXT PRIMARY KEY, lang TEXT, bytes INTEGER, body TEXT)",
    "CREATE TABLE IF NOT EXISTS code_refs  (hash TEXT, path TEXT, commit_sha TEXT, ts REAL, is_current INTEGER DEFAULT 0)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_code_refs ON code_refs(hash, path, commit_sha)",
    "CREATE TABLE IF NOT EXISTS doc_blobs  (hash TEXT PRIMARY KEY, kind TEXT, bytes INTEGER, body TEXT)",
    "CREATE TABLE IF NOT EXISTS doc_refs   (hash TEXT, path TEXT, commit_sha TEXT, ts REAL, is_current INTEGER DEFAULT 0)",
    # abstract tagging: a `tag` applied to an opaque `target` ref ("source:<hash>" / "page:<id>" / "doc:<hash>" / "ticket:<id>")
    "CREATE TABLE IF NOT EXISTS annotations (id INTEGER PRIMARY KEY AUTOINCREMENT, tag TEXT, target TEXT, note TEXT, ts REAL, meta TEXT)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_doc_refs ON doc_refs(hash, path, commit_sha)",
]


# ------------------------------------------------------------------ registry / db
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


def load_registry():
    path = find_registry()
    reg = json.load(open(path))
    reg["__root__"] = os.path.dirname(path)
    return reg


def bug_report(reg, exc, tb, note="ingest_self"):
    root = (reg or {}).get("__root__") or ROOT or HERE
    path = os.path.join(root, (reg or {}).get("bug_reports", "logs/bug_reports.jsonl"))
    frames = traceback.extract_tb(exc.__traceback__)
    last = frames[-1] if frames else None
    entry = {"filename": os.path.basename(__file__), "function": last.name if last else "?",
             "time-of-occurance": datetime.now().isoformat(),
             "methods-to-reproduce": "python3 tools/ingest_self.py " + " ".join(sys.argv[1:]),
             "possible-cause": "%s: %s" % (type(exc).__name__, exc),
             "traceback": tb.strip().splitlines()[-6:], "note": note}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "a").write(json.dumps(entry) + "\n")
    except OSError:
        pass
    return path


def db_path(reg):
    """The CMS DB the app reads: install.json's CONGRUENCY_SQLITE, else the jazz default."""
    cfg = os.path.join(reg["__root__"], "checkouts", "current", "install.json")
    try:
        j = json.load(open(cfg))
        if j.get("CONGRUENCY_SQLITE"):
            return os.path.expanduser(j["CONGRUENCY_SQLITE"])
    except Exception:  # noqa: BLE001
        pass
    return os.path.join(os.path.expanduser("~"), ".jazz", "congruency.sqlite")


# ------------------------------------------------------------------ git
def git(*args):
    return subprocess.run(["git"] + list(args), cwd=ROOT, capture_output=True, text=True)


def resolve(ref):
    return git("rev-parse", ref).stdout.strip()


def ls_tree(ref):
    for line in git("ls-tree", "-r", ref).stdout.splitlines():
        meta, _, path = line.partition("\t")          # "<mode> blob <hash>\t<path>"
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            yield parts[2], path


def blob_body(h):
    """Return (body, nbytes): git blob `h` decoded losslessly, and its TRUE raw byte length.

    Read the RAW blob bytes -- NOT via git() (text=True), whose universal-newline translation strips
    \\r and would mutate the content so it no longer hashes to its git blob id.

    A valid UTF-8 blob decodes so that body.encode("utf-8") == the raw bytes; hence git_blob_sha(body)
    == h and db_verify.py's content-address check passes. Every in-scope file today is UTF-8 text, so
    this is the path they all take -- nothing about their storage changes.

    A non-utf8 / binary blob decodes latin-1 (ISO-8859-1) instead of the old errors="replace". latin-1
    is a total byte<->codepoint bijection (0x00..0xFF <-> U+0000..U+00FF), so the exact bytes survive
    and are recoverable via body.encode("latin-1") -- where "replace" discarded them irreversibly
    (mapping every bad byte to U+FFFD). sqlite stores such a body verbatim, embedded NUL included. The
    git blob id is a hash of the raw bytes re-encoded strict UTF-8, so a genuinely non-utf8 body cannot
    match that specific check without editing db_verify.py; latin-1's job is FIDELITY -- keep the bytes
    intact for later recovery/rehash if scope ever widens past text -- not to spoof that hash.

    nbytes is the raw blob length regardless of codec, so the stored `bytes` column is the file's true
    size, not a re-encoded approximation.
    """
    r = subprocess.run(["git", "cat-file", "blob", h], cwd=ROOT, capture_output=True)
    if r.returncode != 0:
        return "", 0
    raw = r.stdout
    try:
        body = raw.decode("utf-8")
    except UnicodeDecodeError:
        body = raw.decode("latin-1")   # lossless: byte-exact, recoverable via body.encode("latin-1")
    return body, len(raw)


# ------------------------------------------------------------------ classify / write
def in_scope(path):
    if any(s in path for s in IGNORE_SUBSTR):
        return None
    ext = os.path.splitext(path)[1]
    if ext in CODE_EXT and any(path.startswith(p) for p in CODE_PREFIXES):
        return "code"
    if ext == ".md":
        return "doc"
    # .txt ONLY from the doc dir (the legacy 2006 CMS docs) — NOT stray prompts / cookie jars (e.g. wiz.txt)
    if ext == ".txt" and any(path.startswith(p) for p in DOC_TXT_PREFIXES):
        return "doc"
    return None


def have_blob(db, domain, h):
    tbl = "code_blobs" if domain == "code" else "doc_blobs"
    return db.execute("SELECT 1 FROM %s WHERE hash=?" % tbl, (h,)).fetchone() is not None


def store_blob(db, domain, h, path, body, nbytes):
    lang = LANG.get(os.path.splitext(path)[1], "text")
    if domain == "code":
        db.execute("INSERT OR IGNORE INTO code_blobs(hash,lang,bytes,body) VALUES(?,?,?,?)", (h, lang, nbytes, body))
    else:
        db.execute("INSERT OR IGNORE INTO doc_blobs(hash,kind,bytes,body) VALUES(?,?,?,?)", (h, lang, nbytes, body))


def add_ref(db, domain, h, path, commit_sha, ts):
    tbl = "code_refs" if domain == "code" else "doc_refs"
    db.execute("INSERT OR IGNORE INTO %s(hash,path,commit_sha,ts,is_current) VALUES(?,?,?,?,0)" % tbl,
               (h, path, commit_sha, ts))


def ingest_ref(db, ref, ts, main_extras=True):
    """Ingest every in-scope blob at `ref`; return [(domain, path, hash)] for current-flagging."""
    sha = resolve(ref)
    seen = []
    for h, path in ls_tree(ref):
        dom = in_scope(path)
        if not dom:
            continue
        if not have_blob(db, dom, h):
            body, nbytes = blob_body(h)
            store_blob(db, dom, h, path, body, nbytes)
        add_ref(db, dom, h, path, sha, ts)
        seen.append((dom, path, h, sha))
    if main_extras:
        main_sha = resolve("main")
        for name in MAIN_EXTRAS:
            r = git("ls-tree", "main", "--", name)
            parts = r.stdout.split()
            if r.returncode == 0 and len(parts) >= 3 and parts[1] == "blob":
                h, path = parts[2], "main:" + name
                if not have_blob(db, "code", h):
                    body, nbytes = blob_body(h)
                    store_blob(db, "code", h, path, body, nbytes)
                add_ref(db, "code", h, path, main_sha, ts)
                seen.append(("code", path, h, main_sha))
    return seen


def reflag_current(db, seen):
    db.execute("UPDATE code_refs SET is_current=0")
    db.execute("UPDATE doc_refs  SET is_current=0")
    for dom, path, h, csha in seen:
        tbl = "code_refs" if dom == "code" else "doc_refs"
        db.execute("UPDATE %s SET is_current=1 WHERE hash=? AND path=? AND commit_sha=?" % tbl, (h, path, csha))


def ensure_pages(db):
    """Create the two entry-page Documents (source, docs) in the live DB if absent (idempotent)."""
    def next_tid():
        row = db.execute("SELECT COALESCE(MAX(TemplateID),0)+1 FROM Document_Templates").fetchone()
        return row[0] if row else 1
    # the site's one stylesheet is the <<<Style>>> tag; every page just embeds it + the <<<SiteMap>>> nav
    pages = {
        "source":      ("Source · Congruency", "The CMS's own running source", "<<<SourceList>>>"),
        "docs":        ("Documentation · Congruency", "The CMS's own documentation", "<<<DocList>>>"),
        "annotations": ("Annotations · Congruency", "The tag->target layer (flags + categories)", "<<<Annotations>>>"),
        "database":    ("Database · Congruency", "The unified DB — every table, row counts, browsable", "<<<DatabaseInfo>>>"),
    }
    for did, (title, desc, tag) in pages.items():
        if db.execute("SELECT 1 FROM Documents WHERE DocumentID=?", (did,)).fetchone():
            continue
        tid = next_tid()
        body = "<!DOCTYPE html>\n<html>\n<head>\n<<<TitleTag>>>\n<<<Style>>>\n</head>\n<body>\n<nav><<<SiteMap>>></nav>\n<h1>%s</h1>\n%s\n</body>\n</html>\n" % (title, tag)
        db.execute("INSERT INTO Document_Templates(TemplateID, Content) VALUES(?,?)", (tid, body))
        db.execute("INSERT INTO Documents(DocumentID, TemplateID, Title, Description, ContentID) VALUES(?,?,?,?,?)",
                   (did, tid, title, desc, tid))


def stats(db):
    for t in ("code_blobs", "code_refs", "doc_blobs", "doc_refs"):
        try:
            n = db.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
        except sqlite3.Error:
            n = "-"
        cur = ""
        if t.endswith("_refs"):
            c = db.execute("SELECT COUNT(*) FROM %s WHERE is_current=1" % t).fetchone()[0]
            cur = "  (current: %d)" % c
        print("  %-11s %s%s" % (t, n, cur))


# ------------------------------------------------------------------ main
def main():
    global ROOT
    ap = argparse.ArgumentParser(description="mirror the running source + docs into the CMS DB (content-addressed)")
    ap.add_argument("--head", action="store_true", help="ingest the HEAD tree + re-flag current (default)")
    ap.add_argument("--backfill", action="store_true", help="walk source history into the archive")
    ap.add_argument("--ensure-pages", action="store_true", help="create tables + the source/docs entry Documents")
    ap.add_argument("--stats", action="store_true", help="print row counts and exit")
    a = ap.parse_args()

    reg = load_registry()
    ROOT = reg["__root__"]
    db = sqlite3.connect(db_path(reg), timeout=15)
    try:
        for stmt in DDL:
            db.execute(stmt)

        if a.stats:
            stats(db)
            return 0

        if a.ensure_pages:
            ensure_pages(db)
            db.commit()
            print("ensure-pages: entry Documents ensured (source/docs/annotations/database); tables created")
            return 0

        try:
            ensure_pages(db)   # self-healing: the source/docs entry Documents exist (idempotent)
        except Exception:  # noqa: BLE001  (a bare/fresh DB without the CMS Documents table)
            pass

        if a.backfill:
            seen_hashes_before = db.execute("SELECT COUNT(*) FROM code_blobs").fetchone()[0]
            for line in git("rev-list", "--timestamp", "source").stdout.splitlines():
                parts = line.split()
                if len(parts) != 2:
                    continue
                ts, sha = float(parts[0]), parts[1]
                ingest_ref(db, sha, ts, main_extras=False)
            # current main extras + flag HEAD as running source
            seen = ingest_ref(db, "HEAD", float(git("log", "-1", "--format=%ct", "HEAD").stdout.strip() or 0), main_extras=True)
            reflag_current(db, seen)
            db.commit()
            added = db.execute("SELECT COUNT(*) FROM code_blobs").fetchone()[0] - seen_hashes_before
            print("backfill: walked source history (+%d new code blobs)" % added)
            stats(db)
            return 0

        # default: --head
        ts = float(git("log", "-1", "--format=%ct", "HEAD").stdout.strip() or 0)
        seen = ingest_ref(db, "HEAD", ts, main_extras=True)
        reflag_current(db, seen)
        db.commit()
        print("ingest_self: HEAD tree mirrored (%d in-scope files); running source flagged" % len(seen))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001  -- best-effort: never crash a commit hook
        try:
            reg = load_registry()
        except Exception:  # noqa: BLE001
            reg = None
        bug_report(reg, e, traceback.format_exc())
        sys.stderr.write("[ingest_self] %r\n" % e)
        sys.exit(0)
