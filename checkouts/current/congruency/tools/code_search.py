#!/usr/bin/env python3
"""code_search.py — code.search: a code SECTION (or a path:line-range) -> similar code across the
forge, each hit carrying {path, line-range, repository, associated tickets, score}. CLI + MCP
(ticket #190).

WHAT IT DOES, IN ONE PASS. You give it code — raw text, or a file and a line-range. It embeds that
code with nomic-embed-text through the litellm proxy and scores it against the vector index built by
tools/code_sim_indexer.py (#189); INDEPENDENTLY it scores it lexically against every python blob in
the omni-git object store; it fuses the two rankings; and for every hit it joins the hit's location
back to the tickets that authorized work there. It WRITES NOTHING (see NO SIDE EFFECTS below).

    python3 tools/code_search.py --text 'def add(a, b): return a + b'
    python3 tools/code_search.py --path tools/ticket_status.py:49-60      # a path:line-range
    cat snippet.py | python3 tools/code_search.py --stdin
    python3 tools/code_search.py --path X.py:1-20 --json                  # machine-readable
    python3 tools/code_search.py --mcp                                    # serve as an MCP tool
    python3 tools/code_search.py --selftest                               # prove the logic; no net/db
    python3 tools/code_search.py --sources                                # what it reads; writes nothing

TERMS, DEFINED AT FIRST USE (this file assumes you have read nothing else):

  * A CHUNK is one callable — a top-level function, or a method of a top-level class. That is
    codebean's definition, adopted by #189 (code_sim_indexer.py:54-61) and mirrored here by `spans`
    below so the two agree on what a unit of code is.
  * A LINE-RANGE is `line_start-line_end`, the callable's REAL span in the file it came from.
    `line_start` is the `def` line; a decorator above it is not counted (Python's own `ast`
    convention, the same rule #189 records: code_sim_indexer.py:58-60).
  * A BLOB SHA is git's content address — a hash OF the bytes. Two files with the same sha are
    byte-identical. The forge corpus is deduplicated on it.
  * THE INDEX (the ticket's "#b_index") is `code_sim.db`, the vector store #189 built: tables
    `chunks` (line-range + text + vector per callable) and `occurrences` (every {repo, path} a blob
    appears at), joined by the `code_sim_index` view (code_sim_indexer.py:388-427).
  * OMNI-GIT is the forge corpus: `omni_index.db` (tables `occ(sha, path, ext, size, ref, repo, ts)`
    and `blob(sha, path, ext, size, is_text)`) naming blobs that live in the bare object store
    `archives/omni.git`. Both are read-only here.
  * A TICKET_WORK is a permanent-UID row on a ticket's manifest; its `ref` column is "where the item
    lives (path, route, version-tag)" (migrations/0029_ticket_authorization.sql:86-93). That column
    is what a hit location is joined against.
  * MEMGRAPH is `mem_graph.db`: `node(id, kind, label, attrs)` + `edge(src, dst, kind, weight, ...)`.
    The node ids this tool uses are `file:<repo>:<path>` and `blob:<sha>`; the edge kinds are
    `has_version` (file -> blob) and `similar_to` (file -> file, weighted).

THE TWO CHANNELS, AND WHY BOTH ARE NEEDED.

  1. VECTOR (the ticket's "ANN over the index"). The query is embedded as "search_query: <code>" and
     scored against every chunk vector in the index. nomic-embed-text is a task-prefixed model:
     content is indexed as "search_document: " and a query asked as "search_query: " — #189 wrote the
     document half (code_sim_indexer.py:71-75) and SemanticSearch.php:264 already sends the query
     half, so this tool sends the query half too. Vectors are L2-normalized on both sides, so cosine
     similarity IS the dot product.

     HONEST NAMING: this is an EXACT cosine scan, not an approximate one. "ANN" (approximate nearest
     neighbour) names a family of methods that approximate exactly this ranking to go faster on huge
     stores; at the index's real size an exact scan computes the same top-K that an ANN structure
     approximates, with no error, so it satisfies the ticket's requirement rather than weakening it.
     Cost is linear in the store: today's index is 8 chunks and the scan is instant; the scan loads
     one 768-float vector per chunk, so a store of ~100k chunks would cost seconds and hundreds of MB
     — at that size this function is where an ANN structure would be swapped in. `--sources` prints
     the live chunk count so you always know which regime you are in.

  2. LEXICAL over omni-git (the ticket's "omni-git lexical match"). The index is INCOMPLETE by
     construction — #189 embeds blob-by-blob and today holds 7 of the corpus's 4,989 distinct python
     blobs. A vector-only search would therefore be blind to 99.8% of the corpus and would silently
     report that near-duplicates do not exist. The lexical channel closes that gap: it reads EVERY
     python blob in omni-git and scores it directly, so a near-duplicate is found whether or not
     anyone has embedded it yet. This is not a fallback; it is half the answer.

     Content comes from omni-git through ONE read-only plumbing call — `git cat-file --batch`, which
     streams every blob over a single pipe (measured: 4,989 blobs, 6.1 MB, 0.23s end-to-end,
     including tokenizing). There is no sampling, no cap and no truncation in the scan itself.

LEXICAL SCORING, AND THE PRUNE THAT PROVABLY LOSES NOTHING. Code is tokenized into identifiers
(`[A-Za-z_][A-Za-z0-9_]*`), and python KEYWORDS plus `self`/`cls` are dropped: they occur in nearly
every file, so keeping them would score every blob alike and drown the signal. Two set measures over
the query's token set Q:

    containment(Q, B) = |Q & B| / |Q|          -- how much of the query appears in blob B
    jaccard(Q, C)     = |Q & C| / |Q | C|      -- how much query and chunk C AGREE, both ways

Scoring is done per CHUNK (jaccard), because that is the unit the ticket's line-range describes; but
chunking all 4,989 blobs with `ast` would be wasteful. So blobs are first pruned by containment. That
prune is ADMISSIBLE — it cannot drop a chunk that would have ranked — and here is the proof. For any
chunk C of blob B, the lexical text of C is a LINE-SLICE of B, so tokens(C) is a subset of tokens(B).
Then:

    jaccard(Q, C) = |Q & C| / |Q | C|  <=  |Q & C| / |Q|      (because |Q | C| >= |Q|)
                                      <=  |Q & B| / |Q|      (because C subset B, so Q&C subset Q&B)
                                      =   containment(Q, B)

So a blob's containment is an UPPER BOUND on the jaccard of every chunk inside it: any chunk scoring
jaccard >= t necessarily lives in a blob scoring containment >= t. Pruning at
`--lexical-min-containment` (default 0.30) therefore loses no chunk that could score at or above that
threshold. `--selftest` re-proves this bound empirically on a fixture rather than trusting this
comment. (`--lexical-max-blobs`, default 400, is a second, purely defensive cap on how many surviving
blobs get parsed; when it actually binds, the run SAYS SO on stderr rather than quietly truncating.)

FUSION — every returned hit carries TWO real scores, never an assumed one. The channels disagree
about which chunks they can see: the vector channel sees only indexed chunks, the lexical channel
only chunks it parsed. Rather than score a hit on a channel that never looked at it, the top
`--rerank-pool` (default 60) candidates are COMPLETED: a candidate with no vector yet is embedded
now, in one batched call, as "search_document: <text>" — the same prefix #189 indexed it under — so
it gets a true cosine. Every hit that is printed therefore has a measured cosine AND a measured
jaccard, and the score is their weighted mean:

    score = --w-vector * cosine + --w-lexical * jaccard        (defaults 0.65 / 0.35, summing to 1)

The mean is taken over the channels that ACTUALLY MEASURED the hit, and a channel that never looked
is renormalized away rather than contributing a fabricated zero. That matters under --lexical-only,
where no cosine exists at all: there the score IS the jaccard, so an exact match scores 1.0 rather
than 0.35 (0.65 x a cosine nobody measured) — a number the printed formula could not explain. The
header always prints the arithmetic actually in force, so it cannot describe a formula the hits did
not use.

`channels` on each hit records which channel SURFACED it (provenance for recall), which is a separate
question from what each channel SCORED it. Both are printed. A backfilled chunk is embedded from its
raw line-slice, whereas #189 embedded the `ast.unparse` re-print of the same callable
(code_sim_indexer.py:55-57): the two differ in formatting only — where the corpus holds both forms of
one callable they are in fact byte-identical, and the backfilled vector then reproduces the indexed
one exactly — and the hit says `backfilled` either way, so the distinction is never hidden.
`--lexical-only` skips embedding altogether — the whole vector channel, query included — so the tool
still answers when the litellm proxy is down.

TICKET ASSOCIATION — the ticket's "join hit location -> ticket_works/memgraph edges". A hit is
{repo, path}; a ticket_work is a `ref` string. Four independent joins are tried, and EVERY resulting
association names the `via` that produced it and the work's permanent UID, so each one can be checked
by hand:

  via=path            ref and path are the same file: equal after normalization, or one is a suffix
                      of the other ON A PATH-COMPONENT BOUNDARY sharing at least MIN_SUFFIX (2)
                      components. Two components are required because one is not evidence — a bare
                      `__init__.py` matches hundreds of unrelated files, and this join would then
                      manufacture confident nonsense. (Real match today: ticket_works.ref
                      `checkouts/current/congruency/tools/ingest_self.py` vs the same path in the
                      omni repos `testmonkeyalpha-group/congruency` and
                      `testmonkeyalpha-group/jazz-forge/congruency`.)
  via=repo-mark       a `mark` work row (kind='mark') whose JSON ref carries "repo": <the hit's
                      repo>. That is index_watch.py's high-water-mark (#197): it records that this
                      ticket's scope WAS this repo. It associates a ticket to the repo, not to the
                      exact line, and the printed evidence says so. (Real today: repo
                      `forge__bootappliance` -> tickets #269, #268, #276; repo
                      `testmonkeyalpha-group/chain` -> tickets #275, #267.)
  via=memgraph:has_version   the hit's `file:<repo>:<path>` node -> `has_version` -> `blob:<sha>` ->
                      back along `has_version` to OTHER file nodes holding that same blob. Those are
                      alias locations of byte-identical content; each alias path is then run through
                      the via=path rule. This reaches a ticket that named the file by a path the hit
                      does not use.
  via=memgraph:similar_to    the hit's file node's `similar_to` neighbours (a weighted file<->file
                      edge memgraph already computed), each neighbour path run through the via=path
                      rule. This is the weakest join and is reported last; the edge weight is printed.

Memgraph holds NO ticket nodes (its kinds are file/path/blob/snap/event/mem/shadow), so it cannot
name a ticket by itself — its edges serve here strictly as location aliases feeding the path rule.
Tickets are read from the congruency sqlite, whose `ticket_works` is the only table that binds a
ticket to a location.

WHERE THE STATE DB COMES FROM (and why a worktree still works). Default
`<repo>/checkouts/current/state/congruency.sqlite`, the same path ticket_status.py:46 resolves. But
pair-loop workers run inside a git WORKTREE (registry.json `branch_per_ticket.worktrees`), where that
file does not exist — it is not tracked, so it lives only in the main checkout. A worktree's `.git` is
a FILE reading `gitdir: <main>/.git/worktrees/<name>`; this tool parses that pointer (no git
subprocess) to find the main checkout and looks there too. Order: --state-db, then
CONGRUENCY_SQLITE_DB, then this repo, then the main checkout behind a worktree pointer. `--sources`
prints which one was resolved and how. If none exists, hits are still returned in full and their
tickets read `(none)` — the tool degrades, it does not crash.

NO SIDE EFFECTS — this tool WRITES NOTHING AND CREATES NO FILES. Every sqlite database (the index,
the omni index, memgraph, the congruency state db) is opened through the URI flag `immutable=1`, NOT
`mode=ro`: these are WAL-journalled databases, and `mode=ro` makes sqlite spin up `-wal`/`-shm`
sidecar files on every open — a created file, which this tool promises not to do (the trap #153 was
reworked for; the resolution is ticket_status.py:49-60). `immutable=1` reads the identical committed
data and touches nothing. omni-git is read with `git cat-file`, a read-only plumbing command, and
`GIT_DIR`-scoped so no repository discovery walks out of it. A database that does not exist is
reported as absent, never brought into being. The only network call is the embedding POST to the
litellm proxy. `--selftest` proves the no-files claim by listing a directory before and after a run.

Exit 0 on a completed search — INCLUDING a search that found nothing, which is an answer, not a
failure. Exit 1 when --selftest fails a check. Exit 2 on a precondition failure (no query, an
unreadable --path, a bad line-range, no omni index, no index store, an empty query after
tokenization). Exit 3 when the litellm proxy cannot be reached or answers unusably (use
--lexical-only to search without it). Each prints ONE line, never a traceback.

Pure-python stdlib, one file — the repo is stdlib-only (DEPENDENCIES.md). Registry-gated per
note-for-claude: it walks UP to registry.json and refuses to run without it; any unexpected exception
files a timestamped bug report to the registry's `bug_reports` sink.
"""
import argparse
import ast
import json
import keyword
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request


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
HOME = os.path.expanduser("~")


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks).

    note-for-claude: every tool files a timestamped report when an exception is thrown — filename,
    function name, time of occurrence, methods to reproduce, possible cause.

    `bug_reports` is read defensively: a non-string value there would raise INSIDE this handler and
    replace the original exception with a confusing one, so a bad config falls back to the default
    sink rather than destroying the report it was called to file."""
    try:
        sink_rel = REGISTRY.get("bug_reports", "logs/bug_reports.jsonl")
        if not isinstance(sink_rel, str) or not sink_rel:
            sink_rel = "logs/bug_reports.jsonl"
        sink = os.path.join(ROOT, sink_rel)
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "code_search.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:], "note": "code.search (ticket #190)",
            }) + "\n")
    except Exception:  # noqa: BLE001 — a failed report must never mask the failure it reports
        pass


# ── where everything lives (env-overridable; defaults mirror #189's resolution) ───────────────────
# The omni-git index. Same fallback #189 uses (code_sim_indexer.py:157-159), which is itself the one
# OmniExplorer.php:36 uses when OMNI_INDEX_DB is unset.
OMNI_DB = os.environ.get("OMNI_INDEX_DB") or os.path.join(
    HOME, "code/installed/jazz-project/config/forge/omni_index.db")
# The bare object store the index's shas live in (code_sim_indexer.py:161).
OMNI_GIT = os.environ.get("OMNI_GIT") or os.path.join(os.path.dirname(OMNI_DB), "archives", "omni.git")
# The vector index #189 writes (code_sim_indexer.py:163).
STORE = os.environ.get("CODE_SIM_DB") or os.path.join(os.path.dirname(OMNI_DB), "code_sim.db")
# memgraph (0028_memgraph_page.sql's store), a sibling of the omni index.
MEMGRAPH = os.environ.get("MEM_GRAPH_DB") or os.path.join(os.path.dirname(OMNI_DB), "mem_graph.db")

# The litellm proxy (#184): `nomic-embed` is the proxy's name for ollama/nomic-embed-text
# (code_sim_indexer.py:167-173).
LITELLM = os.environ.get("LITELLM_BASE") or "http://127.0.0.1:4000"
LITELLM_KEY = os.environ.get("LITELLM_API_KEY") or ""
MODEL = "nomic-embed"

QUERY_PREFIX = "search_query: "        # nomic-embed-text's query half (SemanticSearch.php:264)
DOC_PREFIX = "search_document: "       # ... and its document half (code_sim_indexer.py:71-75)

PY_EXT = ".py"          # omni stores the extension WITH its leading dot
MAX_CHARS = 8000        # ~2048 tokens: ollama's default embedding context (code_sim_indexer.py:180)
TIMEOUT = 120

TOP = 10
W_VECTOR = 0.65
W_LEXICAL = 0.35
MIN_CONTAINMENT = 0.30
MAX_BLOBS = 400
RERANK_POOL = 60
MIN_SUFFIX = 2          # path-join evidence floor: one shared component is not evidence

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Keywords occur in nearly every python file, so they carry no discriminating signal; `self`/`cls`
# are the same by convention. Dropped from both sides of every comparison.
STOP_TOKENS = set(keyword.kwlist) | set(getattr(keyword, "softkwlist", [])) | {"self", "cls"}


class Fault(Exception):
    """A precondition failure — reported as one line, exit 2."""


class EmbedError(Exception):
    """The embedding proxy is unreachable or answered unusably — one line, exit 3."""


# ── read-only sqlite (immutable=1: reads committed data, creates NO -wal/-shm sidecars) ───────────
def ro_connect(path):
    """Open a db strictly read-only. See NO SIDE EFFECTS in the module docstring for why this is
    `immutable=1` and not `mode=ro` (the rework #153 was forced into: ticket_status.py:49-60)."""
    return sqlite3.connect("file:%s?immutable=1" % path, uri=True)


def ro_connect_if_exists(path):
    """The db, or None when it does not exist — an absent db is never brought into being."""
    return ro_connect(path) if path and os.path.isfile(path) else None


# ── the state db: this repo, or the main checkout behind a worktree pointer ───────────────────────
def main_worktree_root(root):
    """The MAIN checkout's root when `root` is a git worktree, else None.

    A worktree's `.git` is a FILE containing `gitdir: <main>/.git/worktrees/<name>`; the main
    checkout is the path before `/.git/worktrees/`. Parsed as text — no git subprocess, no writes."""
    dotgit = os.path.join(root, ".git")
    if not os.path.isfile(dotgit):
        return None                                    # a normal checkout (.git is a dir), or no git
    try:
        with open(dotgit) as fh:
            line = fh.read().strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    gitdir = line.split(":", 1)[1].strip()
    marker = os.sep + ".git" + os.sep + "worktrees" + os.sep
    if marker not in gitdir:
        return None
    return gitdir.split(marker)[0]


def resolve_state_db(explicit):
    """(path, how) for the congruency sqlite, or (None, why-not). Never creates anything.

    Order: --state-db, CONGRUENCY_SQLITE_DB, this repo, the main checkout behind a worktree pointer.
    The third is ticket_status.py:46's default; the fourth is what makes a pair-loop worktree work,
    where the untracked state db exists only in the main checkout."""
    if explicit:
        return (explicit, "--state-db") if os.path.isfile(explicit) else (None, "--state-db %s does not exist" % explicit)
    env = os.environ.get("CONGRUENCY_SQLITE_DB")
    if env:
        return (env, "CONGRUENCY_SQLITE_DB") if os.path.isfile(env) else (None, "CONGRUENCY_SQLITE_DB %s does not exist" % env)
    here = os.path.join(ROOT, "checkouts", "current", "state", "congruency.sqlite")
    if os.path.isfile(here):
        return here, "this repo (%s)" % ROOT
    main = main_worktree_root(ROOT)
    if main:
        there = os.path.join(main, "checkouts", "current", "state", "congruency.sqlite")
        if os.path.isfile(there):
            return there, "the main checkout behind this worktree's .git pointer (%s)" % main
    return None, "not found at %s (and no main checkout behind a worktree pointer has one)" % here


# ── tokens + the two set measures ─────────────────────────────────────────────────────────────────
def tokens(text):
    """The identifier set of `text`, minus python keywords and self/cls. A SET: this is set-overlap
    scoring, so repetition inside one file is deliberately not a signal."""
    return {t for t in TOKEN_RE.findall(text) if t not in STOP_TOKENS}


def containment(q, b):
    """|q & b| / |q| — how much of the query's vocabulary blob `b` contains. Upper-bounds the jaccard
    of every chunk inside `b`; see the admissibility proof in the module docstring."""
    return len(q & b) / len(q) if q else 0.0


def jaccard(q, c):
    """|q & c| / |q | c| — two-way agreement between the query and one chunk."""
    u = len(q | c)
    return len(q & c) / u if u else 0.0


# ── chunking: #189's selection rule, mirrored so both agree on what a unit of code is ─────────────
def spans(tree):
    """[(namespace, name, line_start, line_end)] — every top-level function, and every method of a
    top-level class, in module-body order.

    This mirrors code_sim_indexer.py:233-245 (`_spans`), which in turn mirrors codebean's
    `lower_module_all` selection rule (code_wrapper.py:107-116). It is duplicated rather than
    imported because #189 loads codebean's chunker to get the chunk TEXT, and this tool needs only
    the SPANS — and must not depend on codebean's optional FastMCP import chain to answer a query.
    `namespace` is the enclosing class for a method, '' for a top-level function."""
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(("", node.name, node.lineno, node.end_lineno))
        elif isinstance(node, ast.ClassDef):
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append((node.name, m.name, m.lineno, m.end_lineno))
    return out


def chunk_source(text):
    """[{namespace, symbol, line_start, line_end, text}] for one module's source, or [] if it does
    not parse (the corpus holds python-2 and partial files; that is a fact about the corpus, not an
    error).

    `text` per chunk is the RAW LINE-SLICE of the source — not a re-print. That keeps tokens(chunk)
    a genuine subset of tokens(blob), which is what makes the containment prune provably admissible
    (see the proof in the module docstring)."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    lines = text.splitlines()
    out = []
    for ns, name, lo, hi in spans(tree):
        if not (1 <= lo <= hi <= len(lines)):
            continue                                   # defensive: never slice outside the file
        out.append({"namespace": ns, "symbol": name, "line_start": lo, "line_end": hi,
                    "text": "\n".join(lines[lo - 1:hi])})
    return out


# ── the query: raw text, stdin, or path:line-range ────────────────────────────────────────────────
LINE_RANGE_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


def parse_path_arg(arg):
    """('file.py:10-20') -> (path, lo, hi); ('file.py') -> (path, None, None).

    Split on the LAST colon and only when the tail really is a line-range, so a path that merely
    contains a colon is not mangled into a bogus range."""
    if ":" in arg:
        head, tail = arg.rsplit(":", 1)
        m = LINE_RANGE_RE.match(tail)
        if m and head:
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.group(2) else lo
            return head, lo, hi
    return arg, None, None


def load_query_from_path(arg):
    """(code, description) for a --path argument. Raises Fault with a one-line reason on any
    problem."""
    path, lo, hi = parse_path_arg(arg)
    if not os.path.isfile(path):
        raise Fault("no such file to read the query from: %s" % path)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as e:
        raise Fault("cannot read %s as UTF-8 text: %s" % (path, e))
    if lo is None:
        return text, "%s (whole file, %d lines)" % (path, len(text.splitlines()))
    lines = text.splitlines()
    if lo < 1 or hi < lo:
        raise Fault("bad line-range %d-%d in %r — expected START-END with 1 <= START <= END"
                    % (lo, hi, arg))
    if lo > len(lines):
        raise Fault("line-range %d-%d is past the end of %s (%d lines)" % (lo, hi, path, len(lines)))
    return "\n".join(lines[lo - 1:min(hi, len(lines))]), "%s:%d-%d" % (path, lo, min(hi, len(lines)))


def load_query(a):
    """(code, description). Exactly one of --text / --stdin / --path is required."""
    given = [n for n, v in (("--text", a.text), ("--stdin", a.stdin), ("--path", a.path)) if v]
    if len(given) != 1:
        raise Fault("give exactly one of --text 'CODE' | --stdin | --path FILE[:START-END] "
                    "(got %s)" % (", ".join(given) if given else "none"))
    if a.text:
        return a.text, "--text (%d chars)" % len(a.text)
    if a.stdin:
        text = sys.stdin.read()
        if not text.strip():
            raise Fault("--stdin read an empty query; pipe the code section in")
        return text, "--stdin (%d chars)" % len(text)
    return load_query_from_path(a.path)


# ── the embedder: litellm proxy, OpenAI-compatible POST /v1/embeddings ────────────────────────────
def l2(vec):
    """The vector scaled to unit length, so cosine similarity is a dot product. A zero vector is
    returned unchanged rather than dividing by zero. (Same guard as code_sim_indexer.py:343-347: the
    proxy already returns unit-norm vectors, so this is a no-op on them and a correctness guard if a
    backend ever does not.)"""
    n = sum(x * x for x in vec) ** 0.5
    return [x / n for x in vec] if n else list(vec)


def embed(base, model, key, inputs, timeout):
    """[unit-norm vector] for `inputs`, in the SAME order. Raises EmbedError on any failure.

    Mirrors code_sim_indexer.py:350-377 — same endpoint, same ordering discipline (`index` echoes the
    input position, so sort by it rather than trusting arrival order) — because a query vector that
    was built differently from the indexed vectors would not be comparable to them."""
    body = json.dumps({"model": model, "input": inputs}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(base.rstrip("/") + "/v1/embeddings", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            doc = json.load(r)
    except urllib.error.HTTPError as e:
        raise EmbedError("litellm %s returned HTTP %s: %s"
                         % (base, e.code, (e.read() or b"")[:200].decode("utf-8", "replace")))
    except Exception as e:
        raise EmbedError("litellm %s unreachable (%r) — is the proxy up? (or use --lexical-only)"
                         % (base, e))
    data = doc.get("data")
    if not isinstance(data, list) or len(data) != len(inputs):
        raise EmbedError("litellm returned %s embeddings for %d inputs"
                         % (len(data) if isinstance(data, list) else "no", len(inputs)))
    out = []
    for d in sorted(data, key=lambda d: d.get("index", 0)):
        v = d.get("embedding")
        if not isinstance(v, list) or not v:
            raise EmbedError("litellm returned an empty embedding for model %r" % model)
        out.append(l2(v))
    return out


def dot(a, b):
    """Cosine similarity of two L2-normalized vectors. Mismatched dimensions mean the vectors came
    from different models and are not comparable — say so rather than silently scoring 0."""
    if len(a) != len(b):
        raise Fault("vector dimension mismatch: query is %d-dim but the index holds %d-dim vectors "
                    "— they are different models; index and query with the same --model" % (len(a), len(b)))
    return sum(x * y for x, y in zip(a, b))


# ── channel 1: the vector index (#b_index) ────────────────────────────────────────────────────────
def vector_hits(store_con, qvec, model, repo):
    """Every indexed chunk scored by cosine against the query, fanned out over its {repo, path}
    occurrences — the ticket's tuple. An EXACT scan (see the honest-naming note in the docstring).

    Cosine is computed ONCE per chunk and then fanned out, because one blob recurs at many paths
    (#189 measured ~16.7x fan-out: code_sim_indexer.py:37-39) and the score does not depend on where
    the identical bytes happen to live."""
    hits = []
    rows = store_con.execute(
        "SELECT sha, chunk_seq, namespace, symbol, line_start, line_end, text, vector, truncated "
        "FROM chunks WHERE model = ?", (model,)).fetchall()
    for sha, seq, ns, sym, lo, hi, text, vecjson, trunc in rows:
        try:
            vec = json.loads(vecjson) if vecjson else None
        except ValueError:
            vec = None
        if not vec:
            continue                                   # a half-written row scores nothing, not zero
        cos = dot(qvec, vec)
        sql = "SELECT repo, path FROM occurrences WHERE sha = ?"
        args = [sha]
        if repo:
            sql += " AND repo = ?"
            args.append(repo)
        for orepo, opath in store_con.execute(sql, args):
            hits.append({"repo": orepo, "path": opath, "line_start": lo, "line_end": hi,
                         "blob_sha": sha, "chunk_seq": seq, "namespace": ns or "", "symbol": sym or "",
                         "text": text or "", "vector_score": cos, "lexical_score": None,
                         "channels": ["vector"], "indexed": True, "backfilled": False,
                         "truncated": bool(trunc)})
    return hits


# ── channel 2: the omni-git lexical scan ──────────────────────────────────────────────────────────
def cat_file_batch(gitdir, shas):
    """{sha: text} for `shas`, read from omni-git through ONE read-only `git cat-file --batch`.

    Read as BYTES and decoded per blob (no text=True): universal-newline translation would mutate the
    bytes away from what the corpus actually holds, and one non-UTF-8 blob must not poison the stream
    — it is simply skipped. GIT_DIR is passed explicitly so no repository discovery walks out of the
    object store."""
    if not shas:
        return {}
    proc = subprocess.Popen(["git", "--git-dir", gitdir, "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        out, _ = proc.communicate(("\n".join(shas) + "\n").encode("ascii"), timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise Fault("reading blobs from %s timed out after 300s" % gitdir)
    result = {}
    i = 0
    n = len(out)
    while i < n:
        j = out.find(b"\n", i)
        if j < 0:
            break
        header = out[i:j].split()
        # "<sha> missing" for an unknown object; "<sha> <type> <size>" otherwise.
        if len(header) < 3:
            i = j + 1
            continue
        try:
            size = int(header[2])
        except ValueError:
            i = j + 1
            continue
        body = out[j + 1:j + 1 + size]
        i = j + 1 + size + 1                           # +1 for the LF git writes after each object
        if header[1] != b"blob":
            continue
        try:
            result[header[0].decode("ascii")] = body.decode("utf-8")
        except UnicodeDecodeError:
            continue                                   # not a text blob: out of scope, not an error
    return result


def lexical_hits(omni_con, gitdir, qtokens, repo, min_containment, max_blobs, note):
    """Chunk-level lexical hits over the WHOLE python corpus in omni-git.

    Three steps: read every candidate blob (one batched plumbing call); prune by containment (an
    admissible upper bound on chunk jaccard — see the proof in the module docstring); chunk and score
    what survives. `note` is called with a one-line message if the defensive --lexical-max-blobs cap
    actually binds, so a truncated scan can never be mistaken for a complete one."""
    sql = ("SELECT DISTINCT o.sha FROM occ o JOIN blob b ON b.sha = o.sha "
           "WHERE o.ext = ? AND b.is_text = 1")
    args = [PY_EXT]
    if repo:
        sql += " AND o.repo = ?"
        args.append(repo)
    shas = [r[0] for r in omni_con.execute(sql, args)]
    if not shas:
        return [], 0

    texts = cat_file_batch(gitdir, shas)

    # prune: containment upper-bounds the jaccard of every chunk inside the blob, so nothing that
    # could score >= min_containment is dropped here.
    scored = []
    for sha, text in texts.items():
        c = containment(qtokens, tokens(text))
        if c >= min_containment:
            scored.append((c, sha))
    scored.sort(key=lambda x: (-x[0], x[1]))
    if len(scored) > max_blobs:
        note("lexical: %d blobs passed containment >= %.2f; parsing the top %d by containment "
             "(--lexical-max-blobs). %d blob(s) were NOT parsed."
             % (len(scored), min_containment, max_blobs, len(scored) - max_blobs))
        scored = scored[:max_blobs]

    hits = []
    for _c, sha in scored:
        for ch in chunk_source(texts[sha]):
            j = jaccard(qtokens, tokens(ch["text"]))
            if j <= 0:
                continue
            osql = "SELECT DISTINCT repo, path FROM occ WHERE sha = ? AND ext = ?"
            oargs = [sha, PY_EXT]
            if repo:
                osql += " AND repo = ?"
                oargs.append(repo)
            for orepo, opath in omni_con.execute(osql, oargs):
                hits.append({"repo": orepo, "path": opath,
                             "line_start": ch["line_start"], "line_end": ch["line_end"],
                             "blob_sha": sha, "chunk_seq": None, "namespace": ch["namespace"],
                             "symbol": ch["symbol"], "text": ch["text"],
                             "vector_score": None, "lexical_score": j, "channels": ["lexical"],
                             "indexed": False, "backfilled": False, "truncated": False})
    return hits, len(shas)


# ── fusion ────────────────────────────────────────────────────────────────────────────────────────
def hit_key(h):
    """A location IS {repo, path, line-range}: the same callable found by both channels is ONE hit."""
    return (h["repo"], h["path"], h["line_start"], h["line_end"])


def merge(vhits, lhits):
    """One hit per location, carrying whatever each channel measured about it."""
    out = {}
    for h in list(vhits) + list(lhits):
        k = hit_key(h)
        if k not in out:
            out[k] = dict(h)
            continue
        cur = out[k]
        if h["vector_score"] is not None:
            cur["vector_score"] = h["vector_score"]
            cur["indexed"] = True
        if h["lexical_score"] is not None:
            cur["lexical_score"] = h["lexical_score"]
        for c in h["channels"]:
            if c not in cur["channels"]:
                cur["channels"].append(c)
        if cur.get("chunk_seq") is None and h.get("chunk_seq") is not None:
            cur["chunk_seq"] = h["chunk_seq"]
    return list(out.values())


def fuse(h, wv, wl):
    """The score: a weighted mean over the channels that ACTUALLY MEASURED this hit.

    A channel that never looked at a hit contributes nothing and its weight is renormalized away —
    it does NOT contribute a fabricated zero. That distinction is the whole point: under
    --lexical-only there is no cosine at all, and scoring a perfect lexical match as 0.35 (0.65 x a
    cosine nobody measured) would be a number the tool's own printed formula does not explain. So
    with both channels present this is the plain 0.65*cosine + 0.35*jaccard; with one present it is
    that channel's own score; with none it is 0 rather than a crash. `score_formula` below renders
    whichever of those is in force, so the header never describes an arithmetic the hits did not
    use."""
    parts = []
    if h["vector_score"] is not None:
        parts.append((wv, h["vector_score"]))
    if h["lexical_score"] is not None:
        parts.append((wl, h["lexical_score"]))
    tw = sum(w for w, _ in parts)
    return sum(w * s for w, s in parts) / tw if tw else 0.0


def score_formula(wv, wl, lexical_only):
    """The arithmetic `fuse` is actually applying, in words — kept beside it so the two cannot
    drift apart (a printed formula is a claim about behaviour)."""
    return "jaccard (lexical-only: no cosine is measured)" if lexical_only \
        else "%s*cosine + %s*jaccard" % (wv, wl)


def complete(hits, qtokens, base, model, key, timeout, max_chars, pool, do_embed, note):
    """Give every candidate in the top `pool` a real score on BOTH channels, then score and rank.

    A hit missing its lexical score gets it computed locally (free). A hit missing its VECTOR score
    is embedded now — as "search_document: <text>", the prefix #189 indexed under
    (code_sim_indexer.py:71-75) — in ONE batched call, so its cosine is comparable to the indexed
    ones. Candidates OUTSIDE the pool are not embedded, so they stay scored on whichever channel did
    measure them (`fuse` renormalizes over exactly those); they are not forced below the completed
    ones, they simply compete on less evidence. `note` says so whenever the pool actually binds, so
    a partially-completed ranking is never mistaken for a fully-measured one."""
    for h in hits:
        if h["lexical_score"] is None:
            h["lexical_score"] = jaccard(qtokens, tokens(h["text"] or ""))

    hits.sort(key=lambda h: (-fuse(h, W_VECTOR, W_LEXICAL), h["repo"], h["path"]))
    head, tail = hits[:pool], hits[pool:]
    if tail:
        note("fusion: %d candidate(s) beyond --rerank-pool %d were not vector-completed; they are "
             "ranked on the channel(s) that did measure them." % (len(tail), pool))

    todo = [h for h in head if h["vector_score"] is None] if do_embed else []
    if todo:
        vecs = embed(base, model, key, [DOC_PREFIX + (h["text"] or "")[:max_chars] for h in todo],
                     timeout)
        for h, v in zip(todo, vecs):
            h["_vec"] = v
    return head, tail


# ── ticket association: hit location -> ticket_works / memgraph edges ─────────────────────────────
def norm_path(p):
    """A path reduced to its comparable form: forward slashes, no './', no leading '/'."""
    p = (p or "").replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def path_match(ref, path):
    """(matched, shared_components) for a ticket_works.ref against a hit path.

    They match when they are the same file: equal after normalization, or one is a suffix of the
    other ON A PATH-COMPONENT BOUNDARY sharing at least MIN_SUFFIX components. The boundary matters
    — a plain string suffix would match `.../my_utils.py` against `utils.py`. The floor matters
    because one shared component is not evidence: a bare `__init__.py` is shared by hundreds of
    unrelated files, and matching on it would manufacture confident nonsense."""
    r, p = norm_path(ref), norm_path(path)
    if not r or not p:
        return False, 0
    rp, pp = r.split("/"), p.split("/")
    if rp == pp:
        return True, len(pp)
    n = min(len(rp), len(pp))
    if n < MIN_SUFFIX:
        return False, 0
    shared = 0
    for i in range(1, n + 1):
        if rp[-i] == pp[-i]:
            shared = i
        else:
            break
    return (shared >= MIN_SUFFIX and (shared == len(rp) or shared == len(pp))), shared


def load_works(state_con):
    """([(uid, ticket_id, kind, ref, note)], {repo: [(uid, ticket_id)]}) from the manifest.

    The second is the repo index built from `mark` work rows: index_watch.py (#197) records a
    high-water-mark whose JSON ref carries the repo that ticket's scope covered. A mark's ref is JSON,
    not a path — anything unparseable is simply not a mark for this purpose."""
    works, by_repo = [], {}
    for uid, tid, kind, ref, note in state_con.execute(
            "SELECT uid, ticket_id, kind, ref, note FROM ticket_works ORDER BY uid"):
        works.append((uid, tid, kind, ref, note))
        if kind == "mark" and ref:
            try:
                d = json.loads(ref)
            except (ValueError, TypeError):
                continue
            if isinstance(d, dict) and isinstance(d.get("repo"), str):
                by_repo.setdefault(d["repo"], []).append((uid, tid))
    return works, by_repo


def memgraph_aliases(mg_con, repo, path):
    """[(alias_path, via, detail)] — other locations memgraph says hold this hit's content.

    Two edge walks, both read-only:
      has_version — file:<repo>:<path> -> blob:<sha> -> back to every OTHER file node holding that
                    same blob. Byte-identical content under a different path.
      similar_to  — the file node's weighted similar-file neighbours, which memgraph already
                    computed. The weakest signal; its weight is carried through so it can be judged.
    A file-node id is 'file:<repo>:<path>', so the path is everything after the SECOND colon (a path
    may itself contain colons; the repo may not)."""
    if mg_con is None:
        return []
    node = "file:%s:%s" % (repo, path)
    out = []
    shas = [r[0] for r in mg_con.execute(
        "SELECT dst FROM edge WHERE src = ? AND kind = 'has_version'", (node,))]
    for blob in shas:
        for (other,) in mg_con.execute(
                "SELECT DISTINCT src FROM edge WHERE dst = ? AND kind = 'has_version' AND src != ?",
                (blob, node)):
            parts = other.split(":", 2)
            if len(parts) == 3 and parts[0] == "file":
                out.append((parts[2], "memgraph:has_version",
                            "same blob %s at %s" % (blob.replace("blob:", "")[:12], parts[1])))
    for other, w in mg_con.execute(
            "SELECT DISTINCT dst, weight FROM edge WHERE src = ? AND kind = 'similar_to'", (node,)):
        parts = other.split(":", 2)
        if len(parts) == 3 and parts[0] == "file":
            out.append((parts[2], "memgraph:similar_to",
                        "similar_to %s (weight %.4f)" % (parts[1], w if w is not None else float("nan"))))
    for other, w in mg_con.execute(
            "SELECT DISTINCT src, weight FROM edge WHERE dst = ? AND kind = 'similar_to'", (node,)):
        parts = other.split(":", 2)
        if len(parts) == 3 and parts[0] == "file":
            out.append((parts[2], "memgraph:similar_to",
                        "similar_to %s (weight %.4f)" % (parts[1], w if w is not None else float("nan"))))
    return out


# via -> (rank, confidence): the order associations are reported in. `path` is a direct hit on the
# file a ticket named; the rest are progressively more indirect, and every row says which it is.
VIA_RANK = {"path": 0, "memgraph:has_version": 1, "repo-mark": 2, "memgraph:similar_to": 3}


def associate(hit, works, by_repo, mg_con, tickets):
    """[association] for one hit — the ticket's "join hit location -> ticket_works/memgraph edges".

    ONE row per ticket, carrying its STRONGEST join: several joins often reach the same ticket (a
    direct path match, and the memgraph alias of that same file), and listing the ticket once per
    join would read as a duplicate while adding nothing. The weaker joins are not discarded — they
    are listed in `also_via`, so corroboration is visible and every route stays auditable. Each row
    names the `via` that produced it, the permanent work UID it came from, and the evidence, so it
    can be checked by hand."""
    found = {}

    def add(uid, tid, via, evidence):
        prev = found.get(tid)
        if prev is not None:
            if VIA_RANK.get(prev["via"], 9) <= VIA_RANK.get(via, 9):
                if via != prev["via"] and via not in prev["also_via"]:
                    prev["also_via"].append(via)      # a weaker route that corroborates this one
                return
            also = prev["also_via"] + ([prev["via"]] if prev["via"] != via else [])
        else:
            also = []
        t = tickets.get(tid) or {}
        found[tid] = {"ticket_id": tid, "work_uid": uid, "via": via, "evidence": evidence,
                      "also_via": [v for v in also if v != via],
                      "title": t.get("title"), "status": t.get("status"), "kind": t.get("kind")}

    # via=path — the ticket named this very file.
    for uid, tid, _kind, ref, _note in works:
        if not ref or not isinstance(ref, str) or ref.startswith("{"):
            continue                                   # a JSON mark is not a path
        ok, shared = path_match(ref, hit["path"])
        if ok:
            add(uid, tid, "path", "ticket_works.ref %s (shares %d path component(s))" % (ref, shared))

    # via=memgraph — alias locations of the same content, each run through the path rule.
    for alias, via, detail in memgraph_aliases(mg_con, hit["repo"], hit["path"]):
        for uid, tid, _kind, ref, _note in works:
            if not ref or not isinstance(ref, str) or ref.startswith("{"):
                continue
            ok, _shared = path_match(ref, alias)
            if ok:
                add(uid, tid, via, "%s -> %s matches ticket_works.ref %s" % (detail, alias, ref))

    # via=repo-mark — a ticket whose recorded scope WAS this repo (index_watch.py's mark, #197).
    for uid, tid in by_repo.get(hit["repo"], []):
        add(uid, tid, "repo-mark",
            "ticket_works uid=%d (kind=mark) records repo=%s as this ticket's indexed scope "
            "(repo-level, not line-level)" % (uid, hit["repo"]))

    return sorted(found.values(), key=lambda a: (VIA_RANK.get(a["via"], 9), a["ticket_id"]))


def load_tickets(state_con):
    return {r[0]: {"kind": r[1], "status": r[2], "title": r[3]}
            for r in state_con.execute("SELECT id, kind, status, title FROM tickets")}


# ── the search ────────────────────────────────────────────────────────────────────────────────────
def search(a, code, note):
    """Run both channels, fuse, associate. Returns a report dict. Writes nothing."""
    qtokens = tokens(code)
    if not qtokens:
        raise Fault("the query has no identifiers once python keywords are dropped — there is "
                    "nothing to match on. Paste a code section, not a comment or a blank range.")

    if not os.path.isfile(a.omni_db):
        raise Fault("no omni-git index at %s — set OMNI_INDEX_DB or pass --omni-db" % a.omni_db)
    if not os.path.isdir(a.omni_git):
        raise Fault("no omni-git object store at %s — set OMNI_GIT or pass --omni-git" % a.omni_git)

    do_embed = not a.lexical_only
    qvec = None
    if do_embed:
        if not os.path.isfile(a.store):
            raise Fault("no vector index at %s — run tools/code_sim_indexer.py first, or pass "
                        "--lexical-only to search omni-git without it" % a.store)
        qvec = embed(a.litellm, a.model, LITELLM_KEY, [QUERY_PREFIX + code[:a.max_chars]],
                     a.timeout)[0]

    omni = ro_connect(a.omni_db)
    store = ro_connect_if_exists(a.store)
    mg = ro_connect_if_exists(a.memgraph)
    state_path, state_how = resolve_state_db(a.state_db)
    state = ro_connect_if_exists(state_path)
    try:
        vhits = []
        if do_embed and store is not None:
            vhits = vector_hits(store, qvec, a.model, a.repo)
        lhits, scanned = lexical_hits(omni, a.omni_git, qtokens, a.repo, a.lexical_min_containment,
                                      a.lexical_max_blobs, note)

        hits = merge(vhits, lhits)
        head, _tail = complete(hits, qtokens, a.litellm, a.model, LITELLM_KEY, a.timeout,
                               a.max_chars, a.rerank_pool, do_embed, note)
        for h in head:
            if h.get("_vec") is not None:
                h["vector_score"] = dot(qvec, h.pop("_vec"))
                h["backfilled"] = True
        for h in hits:
            h.pop("_vec", None)
            h["score"] = fuse(h, a.w_vector, a.w_lexical)
            h["complete"] = h["vector_score"] is not None and h["lexical_score"] is not None
        hits.sort(key=lambda h: (-h["score"], h["repo"], h["path"], h["line_start"]))
        top = hits[:a.top]

        works, by_repo, tickets = [], {}, {}
        if state is not None:
            works, by_repo = load_works(state)
            tickets = load_tickets(state)
        for h in top:
            h["tickets"] = associate(h, works, by_repo, mg, tickets)

        return {
            "query": {"chars": len(code), "tokens": len(qtokens),
                      "prefix": QUERY_PREFIX if do_embed else None,
                      "model": a.model if do_embed else None,
                      "mode": "lexical-only" if a.lexical_only else "vector+lexical"},
            "scope": {"repo": a.repo or None, "top": a.top,
                      "weights": {"vector": a.w_vector, "lexical": a.w_lexical},
                      "score_formula": score_formula(a.w_vector, a.w_lexical, a.lexical_only)},
            "corpus": {"omni_db": a.omni_db, "omni_git": a.omni_git,
                       "python_blobs_scanned": scanned,
                       "store": a.store if do_embed else None,
                       "indexed_chunks": (store.execute("SELECT COUNT(*) FROM chunks WHERE model=?",
                                                        (a.model,)).fetchone()[0]
                                          if (store is not None and do_embed) else 0),
                       "memgraph": a.memgraph if mg is not None else None,
                       "state_db": state_path, "state_db_via": state_how,
                       "ticket_works": len(works)},
            "candidates": len(hits),
            "hits": top,
        }
    finally:
        for c in (omni, store, mg, state):
            if c is not None:
                c.close()


# ── rendering ─────────────────────────────────────────────────────────────────────────────────────
def render(rep, desc, show_text):
    q, c, s = rep["query"], rep["corpus"], rep["scope"]
    print("=== code.search — %s ===" % desc)
    print("  query   : %d chars, %d distinct identifiers, mode=%s%s"
          % (q["chars"], q["tokens"], q["mode"],
             "" if not q["model"] else " (%s, prefix %r)" % (q["model"], q["prefix"])))
    print("  vector  : %s" % ("%d indexed chunk(s) in %s" % (c["indexed_chunks"], c["store"])
                              if c["store"] else "not used (--lexical-only): no cosine is measured"))
    print("  lexical : %d python blob(s) scanned from %s" % (c["python_blobs_scanned"], c["omni_git"]))
    print("  tickets : %s" % (("%d work row(s) from %s [via %s]"
                               % (c["ticket_works"], c["state_db"], c["state_db_via"]))
                              if c["state_db"] else "(none) — no state db: %s" % c["state_db_via"]))
    print("  memgraph: %s" % (c["memgraph"] or "(none)"))
    print("  score   = %s  |  %d candidate(s), showing top %d%s\n"
          % (s["score_formula"], rep["candidates"], min(s["top"], len(rep["hits"])),
             "  [--repo %s]" % s["repo"] if s["repo"] else ""))

    if not rep["hits"]:
        print("  no hits — nothing in the index or the omni-git corpus matched this section.")
        print("\n=== 0 hit(s) ===")
        return

    for i, h in enumerate(rep["hits"], 1):
        print("  %2d. score %.4f   (cosine %s, jaccard %s)   [%s]%s"
              % (i, h["score"],
                 "%.4f" % h["vector_score"] if h["vector_score"] is not None else "  n/a ",
                 "%.4f" % h["lexical_score"] if h["lexical_score"] is not None else "  n/a ",
                 "+".join(h["channels"]),
                 "  backfilled" if h["backfilled"] else ("  indexed" if h["indexed"] else "")))
        print("      path      : %s:%d-%d" % (h["path"], h["line_start"], h["line_end"]))
        print("      repository: %s" % h["repo"])
        print("      symbol    : %s%s   (blob %s)"
              % (h["namespace"] + "." if h["namespace"] else "", h["symbol"] or "(none)",
                 (h["blob_sha"] or "")[:12]))
        if h["tickets"]:
            for t in h["tickets"]:
                print("      ticket    : #%-4s [%s/%s] %s"
                      % (t["ticket_id"], t["kind"] or "?", t["status"] or "?",
                         (t["title"] or "(no title)")[:64]))
                print("                  via=%s%s  work uid=%s — %s"
                      % (t["via"],
                         " (also %s)" % ", ".join(t["also_via"]) if t.get("also_via") else "",
                         t["work_uid"], t["evidence"]))
        else:
            print("      ticket    : (none)")
        if show_text:
            for ln in (h["text"] or "").splitlines()[:12]:
                print("      | %s" % ln)
        print()
    print("=== %d hit(s) ===" % len(rep["hits"]))


def print_sources(a):
    """What this tool reads, and whether each is there. Writes nothing, creates nothing."""
    state_path, how = resolve_state_db(a.state_db)
    print("=== code.search — sources (all read-only; this command writes nothing) ===\n")
    rows = [("vector index (#b_index)", a.store, "the chunks+vectors tools/code_sim_indexer.py wrote"),
            ("omni-git index", a.omni_db, "occ/blob: which blob lives at which {repo, path}"),
            ("omni-git objects", a.omni_git, "blob content, read via `git cat-file --batch`"),
            ("memgraph", a.memgraph, "file/blob nodes + has_version/similar_to edges"),
            ("congruency state db", state_path or "(not found)", "tickets + ticket_works [%s]" % how)]
    for name, path, why in rows:
        there = bool(path) and (os.path.isdir(path) if path.endswith(".git") else os.path.isfile(path))
        print("  %-24s %-6s %s" % (name, "OK" if there else "ABSENT", path))
        print("  %-24s        %s" % ("", why))
    con = ro_connect_if_exists(a.store)
    if con is not None:
        n = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        b = con.execute("SELECT COUNT(*) FROM blobs").fetchone()[0]
        print("\n  index holds %d chunk(s) over %d blob(s) — the vector channel scans all of them "
              "exactly." % (n, b))
        con.close()
    con = ro_connect_if_exists(a.omni_db)
    if con is not None:
        n = con.execute("SELECT COUNT(DISTINCT o.sha) FROM occ o JOIN blob b ON b.sha=o.sha "
                        "WHERE o.ext='.py' AND b.is_text=1").fetchone()[0]
        print("  omni-git holds %d distinct python blob(s) — the lexical channel scans all of them." % n)
        con.close()
    return 0


# ── MCP: JSON-RPC 2.0 over stdio, one object per line (mirrors tools/ticket_api_mcp.py) ───────────
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_NAME = "congruency-code-search"
SERVER_VERSION = "1.0.0"

MCP_TOOL = {
    "name": "code_search",
    "description": ("Find code similar to a section across the whole forge corpus. Give EITHER `text` "
                    "(a raw code section) OR `path` (a repo-relative file, optionally 'file.py:10-20' "
                    "for a line-range). Returns ranked hits, each with {path, line_start, line_end, "
                    "repository, tickets, score}: `score` = 0.65*cosine + 0.35*jaccard, fusing a "
                    "vector search over the embedded index with a lexical scan of every python blob "
                    "in omni-git. `tickets` are joined from ticket_works/memgraph and each names the "
                    "`via` that produced it. Read-only: writes nothing."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "the code section to search for (raw text)"},
            "path": {"type": "string",
                     "description": "repo-relative file, optionally with a line-range: 'a/b.py:10-20'"},
            "repo": {"type": "string", "description": "limit hits to one repository in the corpus"},
            "top": {"type": "integer", "description": "how many hits to return (1..100, default 10)"},
            "lexical_only": {"type": "boolean",
                             "description": "skip embedding entirely; search omni-git lexically "
                                            "(use when the litellm proxy is down)"},
        },
        "required": [],
    },
}


class Refused(Exception):
    """A tool call the server refuses. Carries the JSON-RPC error code the caller sees."""

    def __init__(self, message, code=-32602):
        super().__init__(message)
        self.code = code


def safe_path(root, rel):
    """Resolve a repo-relative path under `root`, REFUSING any escape (absolute, ../, symlink out).

    The MCP surface is reachable by an agent, so its `path` is guarded to the repo the way
    ticket_api_mcp.py:211-222 guards its file ops. The CLI is not guarded: a person running it in
    their own shell can already read any file they name."""
    if not isinstance(rel, str) or not rel:
        raise Refused("path must be a non-empty repo-relative string")
    body, lo, hi = parse_path_arg(rel)
    if os.path.isabs(body):
        raise Refused("path must be repo-relative, not absolute: %r" % body)
    r = os.path.realpath(root)
    p = os.path.realpath(os.path.join(r, body))
    if p != r and not p.startswith(r + os.sep):
        raise Refused("refused: path escapes the repo root: %r" % body)
    return p if lo is None else "%s:%d-%d" % (p, lo, hi)


def mcp_search(ctx, args):
    """The `code_search` tool body: validate, then run the very same search() the CLI runs."""
    text, path = args.get("text"), args.get("path")
    if bool(text) == bool(path):
        raise Refused("give exactly one of `text` (a code section) or `path` (a repo-relative file, "
                      "optionally with a line-range)")
    top = args.get("top", TOP)
    if not isinstance(top, int) or not (1 <= top <= 100):
        raise Refused("top must be an integer 1..100")
    repo = args.get("repo")
    if repo is not None and not isinstance(repo, str):
        raise Refused("repo must be a string")
    lex = args.get("lexical_only", False)
    if not isinstance(lex, bool):
        raise Refused("lexical_only must be a boolean")

    a = argparse.Namespace(**vars(ctx["defaults"]))
    a.repo, a.top, a.lexical_only = repo or "", top, lex
    if path:
        code, desc = load_query_from_path(safe_path(ctx["root"], path))
    else:
        if not isinstance(text, str):
            raise Refused("text must be a string")
        code, desc = text, "text (%d chars)" % len(text)
    rep = search(a, code, note=lambda m: sys.stderr.write("code_search: %s\n" % m))
    rep["query"]["source"] = desc
    return rep


def handle_request(ctx, req):
    """Handle one JSON-RPC request; return the response dict, or None for a notification."""
    rid, method = req.get("id"), req.get("method")
    params = req.get("params") or {}
    is_notification = "id" not in req

    def ok(result):
        return None if is_notification else {"jsonrpc": "2.0", "id": rid, "result": result}

    def err(code, message):
        return None if is_notification else {"jsonrpc": "2.0", "id": rid,
                                             "error": {"code": code, "message": message}}

    try:
        if method == "initialize":
            want = params.get("protocolVersion")
            return ok({"protocolVersion": want if want in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                       "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}})
        if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
            return None
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": [MCP_TOOL]})
        if method == "tools/call":
            name = params.get("name")
            if name != MCP_TOOL["name"]:
                return err(-32601, "refused: this server exposes only %r (asked for %r)"
                           % (MCP_TOOL["name"], name))
            rep = mcp_search(ctx, params.get("arguments") or {})
            return ok({"content": [{"type": "text", "text": json.dumps(rep, indent=2)}],
                       "isError": False})
        return err(-32601, "method not found: %r" % method)
    except Refused as e:
        return err(e.code, str(e))
    except Fault as e:
        return err(-32602, "code_search: %s" % e)
    except EmbedError as e:
        return err(-32603, "code_search: %s" % e)
    except Exception as e:  # noqa: BLE001 — never crash the server on one bad call
        bug_report("handle_request", e, "MCP %s with params %r" % (method, params), e)
        return err(-32603, "internal error in %s: %s" % (method, e))


def serve(ctx):
    """Read JSON-RPC lines on stdin, write responses on stdout. Stdout carries the protocol ONLY —
    every diagnostic goes to stderr, because a stray byte on stdout corrupts the protocol."""
    sys.stderr.write("code_search: serving MCP tool %r over stdio (root=%s)\n"
                     % (MCP_TOOL["name"], ctx["root"]))
    sys.stderr.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        resp = handle_request(ctx, req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


# ── --selftest: prove the logic with NO network, NO db, and NO writes ─────────────────────────────
SELFTEST_SRC = '''\
import os


@decorated
def top_level(alpha, beta=1) -> int:
    """doc"""
    return alpha + beta


class Widget:
    ATTR = 1

    def __init__(self, xray):
        self.xray = xray

    async def fetch(self, url):
        return await get(url)


def after(*args, **kw):
    pass
'''


def selftest():
    """Prove every claim this file makes that can be proven without the live corpus. Writes nothing;
    proves that too, before/after, in isolation (Theme 3 of docs/PLAYBOOK.md)."""
    import shutil
    import tempfile

    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name,
                                ("  — %s" % detail) if detail and not cond else ""))

    base = tempfile.mkdtemp(prefix="code_search-selftest-")
    try:
        print("== selftest == no network, no db, no writes (throwaway root %s)\n" % base)

        # ── t: tokenizing ─────────────────────────────────────────────────────────────────────────
        print("-- t: tokens")
        ck("t1: identifiers are extracted, keywords are dropped",
           tokens("def add(alpha, beta): return alpha + beta") == {"add", "alpha", "beta"},
           str(tokens("def add(alpha, beta): return alpha + beta")))
        ck("t2: self/cls are dropped (they carry no signal in this corpus)",
           "self" not in tokens("def m(self, cls): pass") and "cls" not in tokens("def m(self, cls): pass"))
        ck("t3: numbers and punctuation are not identifiers", tokens("x = 1 + 2 * 3") == {"x"})
        ck("t4: a query of only keywords tokenizes to nothing (main() turns this into exit 2)",
           tokens("if not None: return True") == set())

        # ── m: the set measures, and the ADMISSIBILITY BOUND the prune rests on ────────────────────
        print("-- m: containment / jaccard")
        q, b = {"a", "b"}, {"a", "b", "c", "d"}
        ck("m1: containment(q,b) = |q&b|/|q|", containment(q, b) == 1.0, str(containment(q, b)))
        ck("m2: jaccard(q,c) = |q&c|/|q|c|", jaccard(q, b) == 0.5, str(jaccard(q, b)))
        ck("m3: containment of an empty query is 0, not a crash", containment(set(), b) == 0.0)
        ck("m4: jaccard of two empty sets is 0, not a division by zero", jaccard(set(), set()) == 0.0)

        # The whole prune rests on: jaccard(Q, chunk) <= containment(Q, blob) for every chunk of the
        # blob. Proven empirically here on a real blob against many queries, not asserted in a comment.
        btoks = tokens(SELFTEST_SRC)
        chunks = chunk_source(SELFTEST_SRC)
        worst = None
        for probe in ("alpha beta top_level", "Widget fetch url get", "xray ATTR", "after args kw",
                      "def top_level(alpha, beta=1): return alpha + beta", "os import", "zzz_unrelated"):
            qt = tokens(probe)
            if not qt:
                continue
            cont = containment(qt, btoks)
            for ch in chunks:
                j = jaccard(qt, tokens(ch["text"]))
                if j > cont + 1e-12:
                    worst = (probe, ch["symbol"], j, cont)
        ck("m5: BOUND — every chunk's jaccard <= its blob's containment, so pruning by containment "
           "cannot drop a chunk that would have ranked", worst is None, str(worst))
        ck("m6: a chunk's tokens really are a subset of its blob's tokens (why the bound holds)",
           all(tokens(ch["text"]) <= btoks for ch in chunks))

        # ── c: chunking mirrors #189's selection rule ─────────────────────────────────────────────
        print("-- c: chunking (mirrors code_sim_indexer.py:233-245)")
        got = [(c["namespace"], c["symbol"]) for c in chunks]
        expect = [("", "top_level"), ("Widget", "__init__"), ("Widget", "fetch"), ("", "after")]
        ck("c1: selection+order is #189's (top-level fns AND class methods, in body order)",
           got == expect, str(got))
        src_lines = SELFTEST_SRC.splitlines()
        ck("c2: every line-range lands on its callable's def line (decorators excluded, per ast)",
           all(c["symbol"] in src_lines[c["line_start"] - 1] for c in chunks),
           str([(c["symbol"], c["line_start"], src_lines[c["line_start"] - 1]) for c in chunks]))
        ck("c3: every line-range is inside the file",
           all(1 <= c["line_start"] <= c["line_end"] <= len(src_lines) for c in chunks))
        ck("c4: chunk text is the RAW line-slice of the source (not a re-print)",
           all(c["text"] == "\n".join(src_lines[c["line_start"] - 1:c["line_end"]]) for c in chunks))
        ck("c5: an unparseable module yields no chunks rather than raising",
           chunk_source("def broken(:\n  ???") == [])
        ck("c6: a module with no callables yields no chunks", chunk_source("X = 1\nimport os\n") == [])

        # ── p: the path join, and the evidence floor that keeps it honest ─────────────────────────
        print("-- p: ticket path join")
        ck("p1: identical paths match",
           path_match("a/b/c.py", "a/b/c.py")[0])
        ck("p2: a ref matches a hit path it is a suffix of",
           path_match("checkouts/current/congruency/tools/ingest_self.py", "tools/ingest_self.py")[0])
        ck("p3: a hit path matches a ref it is a suffix of",
           path_match("tools/ingest_self.py", "checkouts/current/congruency/tools/ingest_self.py")[0])
        ck("p4: FLOOR — a bare __init__.py does NOT match (1 shared component is not evidence)",
           not path_match("x/y/__init__.py", "__init__.py")[0])
        ck("p5: but 2 shared components DO match", path_match("x/coupler/__init__.py", "coupler/__init__.py")[0])
        ck("p6: matching is on a component BOUNDARY, not a raw string suffix",
           not path_match("a/my_utils.py", "b/utils.py")[0])
        ck("p7: unrelated paths do not match", not path_match("a/b/c.py", "d/e/f.py")[0])
        ck("p8: a partial tail does not match (must reach the end of one side)",
           not path_match("a/b/c.py", "z/b/c.py")[0] or path_match("a/b/c.py", "z/b/c.py")[1] >= MIN_SUFFIX)
        ck("p9: normalization: ./ and leading / are ignored",
           path_match("./a/b/c.py", "/a/b/c.py")[0])
        ck("p10: an empty ref matches nothing", not path_match("", "a/b.py")[0])

        # ── q: query parsing ──────────────────────────────────────────────────────────────────────
        print("-- q: query parsing")
        ck("q1: 'f.py:10-20' parses to a range", parse_path_arg("f.py:10-20") == ("f.py", 10, 20))
        ck("q2: 'f.py:10' is the single line 10", parse_path_arg("f.py:10") == ("f.py", 10, 10))
        ck("q3: a bare path has no range", parse_path_arg("a/f.py") == ("a/f.py", None, None))
        ck("q4: a colon that is not a line-range is left in the path",
           parse_path_arg("weird:name.py") == ("weird:name.py", None, None))
        probe = os.path.join(base, "q.py")
        open(probe, "w").write("l1\nl2\nl3\nl4\nl5\n")
        code, _d = load_query_from_path(probe + ":2-4")
        ck("q5: a line-range reads exactly those lines", code == "l2\nl3\nl4", repr(code))
        for bad, why in ((probe + ":9-99", "past EOF"), (probe + ":4-2", "END < START"),
                         (os.path.join(base, "nope.py"), "no such file")):
            try:
                load_query_from_path(bad)
                ck("q6: %s is refused with a one-line Fault" % why, False, "no Fault raised")
            except Fault:
                ck("q6: %s is refused with a one-line Fault" % why, True)

        # ── f: fusion arithmetic ──────────────────────────────────────────────────────────────────
        print("-- f: fusion")
        ck("f1: with both channels measured, score = w_v*cosine + w_l*jaccard",
           abs(fuse({"vector_score": 1.0, "lexical_score": 0.0}, 0.65, 0.35) - 0.65) < 1e-12)
        ck("f2: a hit measured by BOTH channels uses both weights",
           abs(fuse({"vector_score": 1.0, "lexical_score": 1.0}, 0.65, 0.35) - 1.0) < 1e-12)
        ck("f3: fuse() renormalizes over the channels PRESENT (a channel that never looked does not "
           "contribute a fabricated zero)",
           abs(fuse({"vector_score": None, "lexical_score": 0.8}, 0.65, 0.35) - 0.8) < 1e-12)
        ck("f4: fuse() of a hit no channel measured is 0, not a crash",
           fuse({"vector_score": None, "lexical_score": None}, 0.65, 0.35) == 0.0)
        # The printed formula is a claim about the arithmetic; under --lexical-only there is no
        # cosine, so a perfect lexical match must score 1.0 — NOT 0.35 (0.65 x a cosine nobody
        # measured), which no printed formula would explain.
        ck("f4b: under --lexical-only a PERFECT lexical match scores 1.0, not 0.35",
           fuse({"vector_score": None, "lexical_score": 1.0}, 0.65, 0.35) == 1.0)
        ck("f4c: the printed formula matches the arithmetic in force, in BOTH modes",
           score_formula(0.65, 0.35, False) == "0.65*cosine + 0.35*jaccard"
           and "jaccard" in score_formula(0.65, 0.35, True)
           and "cosine" not in score_formula(0.65, 0.35, True).split(":")[0],
           score_formula(0.65, 0.35, True))
        merged = merge(
            [{"repo": "r", "path": "p.py", "line_start": 1, "line_end": 2, "vector_score": 0.9,
              "lexical_score": None, "channels": ["vector"], "indexed": True, "backfilled": False,
              "chunk_seq": 3, "text": "t", "blob_sha": "s", "namespace": "", "symbol": "f",
              "truncated": False}],
            [{"repo": "r", "path": "p.py", "line_start": 1, "line_end": 2, "vector_score": None,
              "lexical_score": 0.5, "channels": ["lexical"], "indexed": False, "backfilled": False,
              "chunk_seq": None, "text": "t", "blob_sha": "s", "namespace": "", "symbol": "f",
              "truncated": False}])
        ck("f5: one location found by both channels merges into ONE hit carrying both scores",
           len(merged) == 1 and merged[0]["vector_score"] == 0.9 and merged[0]["lexical_score"] == 0.5
           and sorted(merged[0]["channels"]) == ["lexical", "vector"], json.dumps(merged))
        ck("f6: the same callable at a DIFFERENT path stays a separate hit",
           len(merge([dict(merged[0])], [dict(merged[0], path="other.py")])) == 2)
        ck("f7: dot() of a unit vector with itself is 1", abs(dot([0.6, 0.8], [0.6, 0.8]) - 1.0) < 1e-12)
        try:
            dot([1.0], [1.0, 0.0])
            ck("f8: mismatched vector dims raise a Fault (different models are not comparable)", False)
        except Fault:
            ck("f8: mismatched vector dims raise a Fault (different models are not comparable)", True)
        ck("f9: l2() normalizes to unit length", abs(sum(x * x for x in l2([3.0, 4.0])) - 1.0) < 1e-12)
        ck("f10: l2() of a zero vector does not divide by zero", l2([0.0, 0.0]) == [0.0, 0.0])

        # ── s: state-db resolution ────────────────────────────────────────────────────────────────
        print("-- s: state db resolution")
        p, how = resolve_state_db(os.path.join(base, "absent.sqlite"))
        ck("s1: an explicit --state-db that does not exist resolves to None with a reason",
           p is None and "does not exist" in how, str(how))
        fake = os.path.join(base, "real.sqlite")
        sqlite3.connect(fake).close()
        p, how = resolve_state_db(fake)
        ck("s2: an explicit --state-db that exists is used", p == fake and how == "--state-db")
        wt = os.path.join(base, "wt")
        os.makedirs(os.path.join(wt, "checkouts", "current", "state"))
        open(os.path.join(wt, ".git"), "w").write("gitdir: /main/repo/.git/worktrees/t190\n")
        ck("s3: a worktree's .git pointer resolves to the MAIN checkout (why a pair-loop worker "
           "still finds the untracked state db)", main_worktree_root(wt) == "/main/repo",
           str(main_worktree_root(wt)))
        open(os.path.join(wt, ".git"), "w").write("gitdir: /main/repo/.git\n")
        ck("s4: a plain gitdir (not a worktree) yields no main-checkout guess",
           main_worktree_root(wt) is None)
        ck("s5: a directory .git (a normal checkout) yields no main-checkout guess",
           main_worktree_root(base) is None)

        # ── mc: the MCP surface ───────────────────────────────────────────────────────────────────
        print("-- mc: MCP protocol + path guard")
        ctx = {"root": base, "defaults": argparse.Namespace()}
        init = handle_request(ctx, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                    "params": {"protocolVersion": "2024-11-05"}})
        ck("mc1: initialize echoes the client's protocol version",
           init["result"]["protocolVersion"] == "2024-11-05", json.dumps(init))
        ck("mc2: an unknown protocol version falls back to a supported one",
           handle_request(ctx, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": {"protocolVersion": "1999-01-01"}}
                          )["result"]["protocolVersion"] in PROTOCOL_VERSIONS)
        lst = handle_request(ctx, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        ck("mc3: tools/list advertises code_search with a well-formed inputSchema",
           [t["name"] for t in lst["result"]["tools"]] == ["code_search"]
           and lst["result"]["tools"][0]["inputSchema"]["type"] == "object", json.dumps(lst))
        ck("mc4: a notification gets NO response (JSON-RPC requires silence)",
           handle_request(ctx, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None)
        ck("mc5: an unknown method is an error, not a crash",
           handle_request(ctx, {"jsonrpc": "2.0", "id": 3, "method": "nope"})["error"]["code"] == -32601)
        ck("mc6: an unknown tool name is refused",
           handle_request(ctx, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                "params": {"name": "rm_rf"}})["error"]["code"] == -32601)
        r = handle_request(ctx, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                                 "params": {"name": "code_search", "arguments": {}}})
        ck("mc7: neither text nor path is refused, not crashed",
           "error" in r and "exactly one" in r["error"]["message"], json.dumps(r))
        r = handle_request(ctx, {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                                 "params": {"name": "code_search",
                                            "arguments": {"text": "x", "path": "y.py"}}})
        ck("mc8: BOTH text and path is refused (they are alternatives)", "error" in r)
        for bad, why in (({"text": "x", "top": 0}, "top below range"),
                         ({"text": "x", "top": "ten"}, "top not an integer"),
                         ({"text": "x", "lexical_only": "yes"}, "lexical_only not a boolean"),
                         ({"text": "x", "repo": 7}, "repo not a string")):
            r = handle_request(ctx, {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                     "params": {"name": "code_search", "arguments": bad}})
            ck("mc9: %s is refused" % why, "error" in r, json.dumps(r))
        for bad in ("../escape.py", "/etc/hosts", "a/../../out.py"):
            try:
                safe_path(base, bad)
                ck("mc10: MCP path %r escaping the repo root is refused" % bad, False, "not refused")
            except Refused:
                ck("mc10: MCP path %r escaping the repo root is refused" % bad, True)
        ck("mc11: a guarded path keeps its line-range",
           safe_path(base, "q.py:2-4") == os.path.realpath(os.path.join(base, "q.py")) + ":2-4",
           safe_path(base, "q.py:2-4"))

        # ── w: NO SIDE EFFECTS — proven before/after, in isolation (PLAYBOOK Theme 3) ─────────────
        print("-- w: writes nothing")
        dbdir = os.path.join(base, "dbs")
        os.makedirs(dbdir)
        dbp = os.path.join(dbdir, "wal.sqlite")
        con = sqlite3.connect(dbp)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE t (x)")
        con.execute("INSERT INTO t VALUES (1)")
        con.commit()
        con.close()
        # A WAL db checkpointed and closed still leaves -wal/-shm on disk from the writer; clear them
        # so the ONLY thing that could recreate them is the read below.
        for suffix in ("-wal", "-shm"):
            if os.path.exists(dbp + suffix):
                os.remove(dbp + suffix)
        before = sorted(os.listdir(dbdir))
        c = ro_connect(dbp)
        c.execute("SELECT * FROM t").fetchall()
        c.close()
        after = sorted(os.listdir(dbdir))
        ck("w1: ro_connect() on a WAL db creates NO -wal/-shm sidecar (immutable=1, not mode=ro — "
           "the #153 trap)", before == after == ["wal.sqlite"], "%s -> %s" % (before, after))
        ck("w2: ro_connect_if_exists() does NOT bring an absent db into being",
           ro_connect_if_exists(os.path.join(dbdir, "ghost.sqlite")) is None
           and not os.path.exists(os.path.join(dbdir, "ghost.sqlite")))
        ck("w3: a read-only connection REFUSES a write",
           _refuses_write(dbp), "a write through ro_connect() was NOT refused")

        # ── i: internal consistency of the documented defaults ────────────────────────────────────
        print("-- i: documented defaults agree with the code")
        ck("i1: the default weights sum to 1 (so `score` is on the same 0..1 scale as its parts)",
           abs(W_VECTOR + W_LEXICAL - 1.0) < 1e-12, "%s + %s" % (W_VECTOR, W_LEXICAL))
        ck("i2: the query prefix is nomic-embed-text's query half, the doc prefix its document half "
           "(#189 indexed under the doc half)",
           QUERY_PREFIX == "search_query: " and DOC_PREFIX == "search_document: ")
        # A docstring is a claim about behaviour (#153): the MCP description states the formula in
        # words, so assert the words match the constants rather than letting them drift apart.
        ck("i3: the MCP tool's advertised score formula matches the code's actual defaults",
           "%s*cosine + %s*jaccard" % (W_VECTOR, W_LEXICAL) in MCP_TOOL["description"],
           MCP_TOOL["description"])
        ck("i4: MIN_SUFFIX is the floor the docstring claims (2)", MIN_SUFFIX == 2)
        ck("i5: omni's extension is stored WITH its dot, as #189 records", PY_EXT == ".py")

        print("\n== selftest == %d/%d checks passed" % (sum(1 for _, c_, _ in checks if c_), len(checks)))
        for name, cond, detail in checks:
            if not cond:
                print("   FAILED: %s  — %s" % (name, detail))
        return 0 if all(c_ for _, c_, _ in checks) else 1
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _refuses_write(dbp):
    """True when a write through ro_connect() is refused by sqlite (used by --selftest w3)."""
    c = ro_connect(dbp)
    try:
        c.execute("INSERT INTO t VALUES (2)")
        c.commit()
        return False
    except sqlite3.Error:
        return True
    finally:
        c.close()


# ── main ──────────────────────────────────────────────────────────────────────────────────────────
def build_parser():
    ap = argparse.ArgumentParser(
        description="code.search — a code section (or path:line-range) -> similar code across the "
                    "forge, each hit with {path, line-range, repository, associated tickets, score}. "
                    "Fuses a vector search over the embedded index with a lexical scan of every "
                    "python blob in omni-git. Read-only: writes nothing, creates no files.",
        epilog="examples: --text 'def add(a,b): return a+b' | --path tools/x.py:10-40 | --stdin | "
               "--mcp (serve as an MCP tool) | --selftest | --sources")
    g = ap.add_argument_group("the query (give exactly one)")
    g.add_argument("--text", default="", help="the code SECTION to search for, as raw text")
    g.add_argument("--stdin", action="store_true", help="read the code section from stdin")
    g.add_argument("--path", default="",
                   help="a file to read the section from: FILE, or FILE:START-END for a line-range")
    g = ap.add_argument_group("scope + ranking")
    g.add_argument("--repo", default="", help="limit hits to one repository in the corpus")
    g.add_argument("--top", type=int, default=TOP, help="how many hits to show (default: %d)" % TOP)
    g.add_argument("--w-vector", type=float, default=W_VECTOR,
                   help="weight of the cosine channel (default: %s)" % W_VECTOR)
    g.add_argument("--w-lexical", type=float, default=W_LEXICAL,
                   help="weight of the lexical channel (default: %s)" % W_LEXICAL)
    g.add_argument("--lexical-only", action="store_true",
                   help="skip embedding entirely and search omni-git lexically (works with the "
                        "litellm proxy down)")
    g.add_argument("--lexical-min-containment", type=float, default=MIN_CONTAINMENT,
                   help="prune blobs below this containment before chunking; provably cannot drop a "
                        "chunk scoring at or above it (default: %s)" % MIN_CONTAINMENT)
    g.add_argument("--lexical-max-blobs", type=int, default=MAX_BLOBS,
                   help="defensive cap on blobs parsed after the prune; says so when it binds "
                        "(default: %d)" % MAX_BLOBS)
    g.add_argument("--rerank-pool", type=int, default=RERANK_POOL,
                   help="how many candidates get vector-completed (default: %d)" % RERANK_POOL)
    g = ap.add_argument_group("sources (all read-only)")
    g.add_argument("--store", default=STORE, help="the vector index (default: %s)" % STORE)
    g.add_argument("--omni-db", default=OMNI_DB, help="the omni-git index (default: %s)" % OMNI_DB)
    g.add_argument("--omni-git", default=OMNI_GIT, help="the omni-git objects (default: %s)" % OMNI_GIT)
    g.add_argument("--memgraph", default=MEMGRAPH, help="memgraph (default: %s)" % MEMGRAPH)
    g.add_argument("--state-db", default="",
                   help="the congruency sqlite holding tickets/ticket_works (default: this repo's, "
                        "else the main checkout behind a worktree pointer)")
    g.add_argument("--litellm", default=LITELLM, help="litellm proxy base url (default: %s)" % LITELLM)
    g.add_argument("--model", default=MODEL, help="litellm model name (default: %s)" % MODEL)
    g.add_argument("--max-chars", type=int, default=MAX_CHARS,
                   help="embed at most N chars (default: %d)" % MAX_CHARS)
    g.add_argument("--timeout", type=int, default=TIMEOUT, help="embed timeout secs (default: %d)" % TIMEOUT)
    g = ap.add_argument_group("output + modes")
    g.add_argument("--json", action="store_true", help="print the report as JSON instead of a table")
    g.add_argument("--show-text", action="store_true", help="print the first 12 lines of each hit")
    g.add_argument("--mcp", action="store_true", help="serve as an MCP tool over stdio (JSON-RPC 2.0)")
    g.add_argument("--root", default=ROOT, help="repo root the MCP `path` param is confined to")
    g.add_argument("--sources", action="store_true", help="print what this tool reads; writes nothing")
    g.add_argument("--selftest", action="store_true", help="prove the logic; no network, no db, no writes")
    return ap


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    ap = build_parser()
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if a.sources:
        return print_sources(a)
    if a.mcp:
        return serve({"root": a.root, "defaults": a})
    if a.top < 1:
        raise Fault("--top must be at least 1 (got %d)" % a.top)

    code, desc = load_query(a)
    # Diagnostics go to stderr so that `--json` on stdout stays machine-readable.
    note = lambda m: sys.stderr.write("code_search: %s\n" % m)   # noqa: E731
    rep = search(a, code, note)
    rep["query"]["source"] = desc
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        render(rep, desc, a.show_text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as e:
        print("code_search: %s" % e)
        sys.exit(2)
    except EmbedError as e:
        print("code_search: %s" % e)
        sys.exit(3)
    except BrokenPipeError:
        os._exit(0)                                    # `| head` closed the pipe; not an error
    except KeyboardInterrupt:
        print("code_search: interrupted")
        sys.exit(130)
    except Exception as e:  # noqa: BLE001 — one-line message, never a traceback (+ a filed report)
        bug_report("main", e, "python3 tools/code_search.py %s" % " ".join(sys.argv[1:]), e)
        print("code_search: %s" % e)
        sys.exit(2)
