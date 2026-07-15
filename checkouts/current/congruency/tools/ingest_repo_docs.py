#!/usr/bin/env python3
"""ingest_repo_docs.py — fill `repo_docs` from the registered repos' bare forge remotes.

WHY. tag_selfcheck.py WARNs that the table `repo_docs` is EMPTY, so ?page=repodocs renders "No repo
documentation ingested yet" and SemanticSearch's keyword axis has nothing to match (ticket #161).
The docs were ingested at the retired forge home by jazz-forge's pipeline and never followed the
repathing; no ingester existed in this repo's tooling. This is that ingester, built here, minimal and
pure-stdlib: it walks each registered repo's `docs/` + README straight out of its bare git remote and
inserts them into `repo_docs`.

WHAT IT WRITES. One row per (repo, path) in `repo_docs` (ts, repo, path, kind, body) — the same
columns, and the same INSERT shape, as the governed `doc.record` route
(migrations/0017_repo_docs.sql:47-54). Those rows are exactly what <<<RepoDocs>>> (?page=repodocs)
and <<<SemanticSearch>>>'s keyword axis (?page=search) read back. It writes NOTHING else: no other
table is touched, and the only file it opens for writing is the db itself (an ingest run leaves no
new file behind; --dry-run and --stats create none at all — see the last paragraph). It never writes
to a git remote: every remote is read with read-only plumbing.

WHERE IT WRITES. The db the CMS itself reads: `checkouts/current/state/congruency.sqlite`. That is
the value boot/configure.php:42 derives for the CONGRUENCY_SQLITE constant RepoDocs.php opens ("state
is a sibling of the app root"), and the same db tag_selfcheck.py:88 checks. Note this is deliberately
NOT the path tools/ingest_self.py resolves (install.json's CONGRUENCY_SQLITE, else ~/.jazz/…): that
override file does not exist in this checkout, so that tool's fallback names a DIFFERENT db, and
writing there would leave ?page=repodocs just as empty. --db overrides the choice.

WHAT COUNTS AS A DOC (the ticket's scope: "docs/ + README" — the same scope 0017_repo_docs.sql and
RepoDocs.php state):
  * every blob under the repo's top-level `docs/` directory, and
  * every blob whose filename starts with README, at any depth (case-insensitive, so `Readme.md`
    counts) — a README is that repo's documentation wherever it sits.
Nothing outside those two categories is ever ingested. Of those, only TEXT is kept: the extension
must be one this CMS can render (.md/.markdown -> kind 'md'; .txt/.rst/no-extension -> kind 'text'),
AND the blob must decode as UTF-8. Both filters matter — the corpus really does hold ~450 KB PDFs
under docs/, and RepoDocs would dump one into a <pre> while SemanticSearch LIKE-scanned it. The two
`kind` values are the vocabulary the readers already speak: RepoDocs.php:84 renders markdown only for
kind 'md', and SemanticSearch.php's type facet offers exactly 'md' and 'text'.

WHICH COMMIT IT READS. `repos.head_commit` when it resolves to a commit in that remote, else HEAD,
else refs/heads/{main,master,source,trunk}, else the first branch under refs/heads/. The fallback is
not decoration: 183 of the 263 registered repos store the literal string 'HEAD' as their head_commit,
and in those bare remotes HEAD is a symref to refs/heads/master — a branch that does not exist (the
real branch is `main`). Resolving only `head_commit`/HEAD would silently skip ~70% of the corpus. A
repo with no commit at all (a bare remote with zero refs) is reported SKIP with its reason, never a
crash — that is an empty repo, not a failure. Trees and blobs are read with the same read-only
plumbing TreeView.php uses on these remotes (`git --git-dir=<forge_remote> ls-tree` / `cat-file
blob`); this tool never writes to a remote.

IDEMPOTENT, APPEND-ONLY. `repo_docs` keeps revisions — RepoDocs.php:79 reads a doc back with
`ORDER BY id DESC LIMIT 1`, so the NEWEST row for a (repo, path) is the live one. This tool compares
each doc against that newest stored row and inserts only when the body is NEW or CHANGED; an
unchanged doc is skipped. So a second run inserts 0 rows and ?page=repodocs lists each doc exactly
once. It never deletes or rewrites a row: history is append-only, a changed doc appends a revision.

    python3 tools/ingest_repo_docs.py              # ingest every registered repo (default)
    python3 tools/ingest_repo_docs.py --dry-run    # report what WOULD be ingested; writes nothing
    python3 tools/ingest_repo_docs.py --repo NAME  # limit to one registered repo
    python3 tools/ingest_repo_docs.py --stats      # print repo_docs row counts and exit; writes nothing
    python3 tools/ingest_repo_docs.py --db PATH    # ingest into a different db file
    python3 tools/ingest_repo_docs.py --json OUT   # also write the per-doc report as JSON

--dry-run and --stats open the db read-only through the URI flag `immutable=1` (NOT `mode=ro`, which
on a WAL-journalled db spins up -wal/-shm sidecars on every open) and create NO files.

Exit 0 when the ingest completed — including "nothing new to ingest" and including repos skipped as
empty, which is a permanent, unremarkable property of a bare remote and not a fault. Exit 1 only if a
`repos` row is MIS-REGISTERED (no forge_remote, or one absent from disk) — a real integrity fault
that a run cannot fix. Exit 2 on a precondition failure (no db, no `repos`/`repo_docs` table, unknown
--repo); each of those prints one line, never a traceback. Pure-python stdlib, one file.
Registry-gated per note-for-claude: it walks UP to registry.json and refuses to run without it.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time


# ── registry gate (note-for-claude: a tool that cannot see the registry throws) ───────────────────
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

# The db the CMS reads: boot/configure.php:42 derives CONGRUENCY_SQLITE as a `state` dir sibling to
# the app root (checkouts/current/congruency) — i.e. checkouts/current/state/congruency.sqlite.
STATE = os.path.join(ROOT, "checkouts", "current", "state")
CONG_DB = os.path.join(STATE, "congruency.sqlite")

# Text extensions this CMS can render, mapped to the `kind` vocabulary its readers already speak:
# RepoDocs.php:84 renders markdown for 'md' and <pre> otherwise; SemanticSearch.php's type facet
# offers exactly 'md' and 'text'. An extension outside this map (e.g. .pdf) is not a text doc.
KIND_BY_EXT = {".md": "md", ".markdown": "md", ".txt": "text", ".rst": "text", "": "text"}

DOCS_PREFIX = "docs/"          # the repo's top-level documentation directory
README_STEM = "README"         # matched case-insensitively against the file's basename

# Tip resolution, in order, after `repos.head_commit`. 183 of the 263 registered repos store the
# literal 'HEAD' and their remote's HEAD symrefs a refs/heads/master that does not exist.
FALLBACK_REFS = ("HEAD", "refs/heads/main", "refs/heads/master", "refs/heads/source", "refs/heads/trunk")


# ── read-only sqlite (immutable=1: reads committed data, creates NO -wal/-shm sidecars) ───────────
def ro_connect(path):
    return sqlite3.connect("file:%s?immutable=1" % path, uri=True)


def table_names(con):
    return {r[0].lower() for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


# ── git plumbing (read-only, against the bare forge remote — as TreeView.php reads them) ──────────
def git(gitdir, *args):
    return subprocess.run(["git", "--git-dir", gitdir] + list(args), capture_output=True, text=True)


def rev_parse(gitdir, ref):
    """The commit sha `ref` names in this remote, or None. `^{commit}` makes a tag or a
    non-commit ref fail here rather than surface later as an unreadable tree."""
    if not ref:
        return None
    r = git(gitdir, "rev-parse", "--verify", "--quiet", "%s^{commit}" % ref)
    return r.stdout.strip() or None


def first_branch(gitdir):
    r = git(gitdir, "for-each-ref", "--format=%(refname)", "refs/heads/")
    for ref in r.stdout.split():
        if rev_parse(gitdir, ref):
            return ref
    return None


def resolve_tip(gitdir, head_commit):
    """(sha, ref_used) for the commit to read docs from, or (None, None) if the remote has none.

    `repos.head_commit` first — it is congruency's recorded provenance for the repo's source — then
    the fallbacks. The literal 'HEAD' is not tried as a stored value (it is the placeholder those 183
    rows carry, not a sha); it is covered by FALLBACK_REFS anyway."""
    cands = []
    if head_commit and head_commit != "HEAD":
        cands.append(head_commit)
    cands.extend(FALLBACK_REFS)
    for ref in cands:
        sha = rev_parse(gitdir, ref)
        if sha:
            return sha, ref
    ref = first_branch(gitdir)
    if ref:
        return rev_parse(gitdir, ref), ref
    return None, None


def ls_tree(gitdir, sha):
    """[(blob_hash, path)] for every blob in the tree at `sha`."""
    r = git(gitdir, "ls-tree", "-r", sha)
    out = []
    for line in r.stdout.splitlines():
        meta, _, path = line.partition("\t")        # "<mode> blob <hash>\t<path>"
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob" and path:
            out.append((parts[2], path))
    return out


def blob_text(gitdir, blob_hash):
    """The blob decoded as UTF-8, or None if it is binary / unreadable.

    The bytes are read raw (no text=True): universal-newline translation would strip \\r and mutate
    the body away from what the repo actually holds. A UTF-8 decode failure is the binary guard —
    repo_docs bodies are served as markdown or <pre>, so a PDF has no business in the table."""
    r = subprocess.run(["git", "--git-dir", gitdir, "cat-file", "blob", blob_hash], capture_output=True)
    if r.returncode != 0:
        return None
    try:
        return r.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ── doc selection ─────────────────────────────────────────────────────────────────────────────────
def is_doc_path(path):
    """True for the ticket's scope — a blob under the top-level docs/, or any README* file."""
    return path.startswith(DOCS_PREFIX) or os.path.basename(path).upper().startswith(README_STEM)


def kind_of(path):
    """The `kind` for a doc path, or None when it is not a text type this CMS renders."""
    return KIND_BY_EXT.get(os.path.splitext(path)[1].lower())


# ── ingest ────────────────────────────────────────────────────────────────────────────────────────
def newest_body(con, repo, path):
    """The body of the live row for (repo, path) — the NEWEST, which is the row RepoDocs.php:79
    reads back with `ORDER BY id DESC LIMIT 1` — or None if the doc has never been ingested."""
    row = con.execute("SELECT body FROM repo_docs WHERE repo=? AND path=? ORDER BY id DESC LIMIT 1",
                      (repo, path)).fetchone()
    return row[0] if row else None


def collect(repo, gitdir, head_commit):
    """Every ingestable doc of one repo: (rows, skipped, problem).

    rows: [{repo, path, kind, body}] — the text docs found at the repo's tip. Empty when the repo
      simply has no docs/ or README, which is ordinary and leaves `problem` None.
    skipped: [(path, reason)] — in-scope docs deliberately left out (non-text type / binary).
    problem: None, or (severity, one-line reason) when the repo could not be READ at all.
      severity 'empty' — the remote is readable but holds no commit to read. Unremarkable and
        permanent (a bare remote with zero refs); reported, but NOT an error.
      severity 'broken' — the registration itself is wrong: no forge_remote, or one that is not on
        disk. That is a real integrity fault (the same one tag_selfcheck.py FAILs on when it checks
        repos.forge_remote paths), so it sets the exit code."""
    if not gitdir:
        return [], [], ("broken", "no forge_remote registered")
    if not os.path.isdir(gitdir):
        return [], [], ("broken", "forge_remote missing on disk: %s" % gitdir)
    sha, _ref = resolve_tip(gitdir, head_commit)
    if not sha:
        return [], [], ("empty", "no commit to read (remote has no resolvable ref)")

    rows, skipped = [], []
    for blob_hash, path in ls_tree(gitdir, sha):
        if not is_doc_path(path):
            continue
        kind = kind_of(path)
        if kind is None:
            skipped.append((path, "not a text doc type"))
            continue
        body = blob_text(gitdir, blob_hash)
        if body is None:
            skipped.append((path, "binary (not UTF-8)"))
            continue
        rows.append({"repo": repo, "path": path, "kind": kind, "body": body})
    return rows, skipped, None


def ingest(con, rows, dry_run):
    """Insert the NEW/CHANGED docs; skip the unchanged. Returns (inserted, updated, unchanged).

    Append-only: an unchanged doc is left alone, a changed doc APPENDS a revision (which
    RepoDocs.php:79 then reads as the live one). No row is ever deleted or rewritten."""
    inserted = updated = unchanged = 0
    ts = int(time.time())                     # epoch seconds — what doc.record's strftime('%s','now') stores
    for r in rows:
        prev = newest_body(con, r["repo"], r["path"])
        if prev is not None and prev == r["body"]:
            unchanged += 1
            continue
        if not dry_run:
            # the same INSERT the governed doc.record route runs (0017_repo_docs.sql:49-50)
            con.execute("INSERT INTO repo_docs (ts, repo, path, kind, body) VALUES (?,?,?,?,?)",
                        (ts, r["repo"], r["path"], r["kind"], r["body"]))
        if prev is None:
            inserted += 1
        else:
            updated += 1
    return inserted, updated, unchanged


# ── report ────────────────────────────────────────────────────────────────────────────────────────
def print_stats(con):
    docs = con.execute("SELECT COUNT(*) FROM repo_docs").fetchone()[0]
    repos = con.execute("SELECT COUNT(DISTINCT repo) FROM repo_docs").fetchone()[0]
    pairs = con.execute("SELECT COUNT(*) FROM (SELECT DISTINCT repo, path FROM repo_docs)").fetchone()[0]
    print("repo_docs: %d rows — %d distinct docs (repo/path) across %d repos" % (docs, pairs, repos))
    if docs:
        print("\n  %-40s %s" % ("REPO", "DOCS"))
        print("  " + "-" * 52)
        for name, n in con.execute("SELECT repo, COUNT(DISTINCT path) FROM repo_docs "
                                   "GROUP BY repo ORDER BY repo"):
            print("  %-40s %d" % (name, n))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(
        description="ingest every registered repo's docs/ + README (read from its bare forge remote) into repo_docs")
    ap.add_argument("--db", default=CONG_DB, help="db to ingest into (default: %s)" % CONG_DB)
    ap.add_argument("--repo", default="", help="limit to one registered repo (default: all)")
    ap.add_argument("--dry-run", action="store_true", help="report what WOULD be ingested; write nothing")
    ap.add_argument("--stats", action="store_true", help="print repo_docs row counts and exit; write nothing")
    ap.add_argument("--json", metavar="PATH", default="", help="also write the per-doc report as JSON")
    a = ap.parse_args()

    if not os.path.isfile(a.db):
        print("ingest_repo_docs: no db at %s — restore state first, or pass --db" % a.db)
        return 2

    # --stats / --dry-run never write: immutable=1 reads the committed data and creates no sidecars.
    read_only = a.stats or a.dry_run
    con = ro_connect(a.db) if read_only else sqlite3.connect(a.db, timeout=15)
    try:
        have = table_names(con)
        for t in ("repos", "repo_docs"):
            if t not in have:
                print("ingest_repo_docs: table `%s` missing from %s — run the migrations first" % (t, a.db))
                return 2

        if a.stats:
            print_stats(con)
            return 0

        if a.repo:
            registered = con.execute("SELECT name, forge_remote, head_commit FROM repos WHERE name=?",
                                     (a.repo,)).fetchall()
            if not registered:
                print("ingest_repo_docs: no registered repo named %r (see the repos table)" % a.repo)
                return 2
        else:
            registered = con.execute("SELECT name, forge_remote, head_commit FROM repos ORDER BY name").fetchall()

        mode = "DRY-RUN (nothing is written)" if a.dry_run else "ingesting"
        print("=== ingest_repo_docs — %s — %d registered repo(s) -> %s ===\n" % (mode, len(registered), a.db))

        tot_ins = tot_upd = tot_unc = tot_skip = 0
        with_docs = 0
        empty, broken, report = [], [], []
        for name, remote, head in registered:
            rows, skipped, problem = collect(name, remote, head)
            if problem:
                severity, why = problem
                (broken if severity == "broken" else empty).append((name, why))
                print("  SKIP  %-40s %s" % (name, why))
                continue
            ins, upd, unc = ingest(con, rows, a.dry_run)
            tot_ins += ins
            tot_upd += upd
            tot_unc += unc
            tot_skip += len(skipped)
            if rows or skipped:
                with_docs += 1
                bits = []
                if ins:
                    bits.append("%d new" % ins)
                if upd:
                    bits.append("%d changed" % upd)
                if unc:
                    bits.append("%d unchanged" % unc)
                if skipped:
                    bits.append("%d not-text" % len(skipped))
                print("  OK    %-40s %s" % (name, ", ".join(bits) or "no docs"))
            report.append({"repo": name, "docs": [{"path": r["path"], "kind": r["kind"],
                                                   "bytes": len(r["body"])} for r in rows],
                           "skipped": [{"path": p, "reason": why} for p, why in skipped]})

        if not a.dry_run:
            con.commit()

        verb = "would ingest" if a.dry_run else "ingested"
        print("\n=== %s: %d new, %d changed, %d unchanged (already current); "
              "%d in-scope file(s) skipped as not-text; %d repo(s) with docs, "
              "%d empty, %d mis-registered ==="
              % (verb, tot_ins, tot_upd, tot_unc, tot_skip, with_docs, len(empty), len(broken)))
        if empty:
            print("\n  empty remotes (readable, but hold no commit — nothing to ingest; not an error):")
            for name, why in empty:
                print("    %-40s %s" % (name, why))
        if broken:
            print("\n  MIS-REGISTERED repos (the repos row points at no usable remote — fix the registration):")
            for name, why in broken:
                print("    %-40s %s" % (name, why))
        if not a.dry_run and (tot_ins or tot_upd):
            print("\n  ?page=repodocs and ?page=search now have documentation to show.")

        if a.json:
            json.dump({"db": a.db, "dry_run": a.dry_run, "repos": report,
                       "empty": [{"repo": n, "reason": w} for n, w in empty],
                       "mis_registered": [{"repo": n, "reason": w} for n, w in broken]},
                      open(a.json, "w"), indent=2)
            print("JSON: %s" % a.json)

        return 1 if broken else 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
