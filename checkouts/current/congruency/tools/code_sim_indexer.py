#!/usr/bin/env python3
"""code_sim_indexer.py — the forge code-similarity indexer: AST-chunk + embed the forge corpus
into a vector store, incrementally (ticket #189).

WHAT IT DOES, IN ONE PASS. It walks the forge corpus, cuts each Python module into AST chunks (one
chunk per callable), embeds each chunk with nomic-embed-text through the litellm proxy, and writes
{repo, path, line-range, chunk, vector} into a sqlite vector store. Re-running is a near-no-op: a
blob already in the store is neither re-read nor re-embedded.

THE FOUR PIECES IT BUILDS ON (each resolved from an env var, else a default named below):

  1. THE CORPUS INDEX — `omni_index.db`, the omni-git index built by jazz-forge's omni_index.py. It
     is a SEPARATE sqlite database from the CMS's CONGRUENCY_SQLITE, and this tool only ever READS
     it. Two tables matter (its schema as it exists today):
         occ (sha, path, ext, size, ref, repo, ts)   -- one row per OCCURRENCE: this blob appeared
                                                        at this path, in this repo, at this snapshot
         blob (sha, path, ext, size, is_text)        -- one row per DISTINCT blob; is_text=0 marks
                                                        a blob that is not text
     A "blob sha" is git's content address: the sha IS a hash of the bytes, so two files with the
     same sha are byte-identical, and one sha can never mean two different contents. That property
     is the whole basis of this tool's incrementality.
  2. THE CORPUS CONTENT — `archives/omni.git`, a single bare git object store holding every blob the
     index names (`occ.ref` values are refs inside it, e.g.
     refs/archives/20260701T122754Z/claude-code-agent/heads/main). Content is read with read-only
     git plumbing (`git --git-dir=<omni.git> cat-file blob <sha>`); this tool never writes to it.
  3. THE CHUNKER — codebean's `lower_module_all` (ticket #183), reused as-is by loading
     codebean_mcp/prototype/code_wrapper.py. It returns [(namespace, Function, original_src)] for
     every callable in a module: top-level functions AND class methods, one nesting level, where
     `namespace` is the enclosing class name for a method or '' for a top-level function. That
     definition of "a chunk" is codebean's, not this tool's — see CHUNKS below.
  4. THE EMBEDDER — the litellm proxy (ticket #184). config/litellm/litellm_config.yaml declares
        model_name: nomic-embed  ->  litellm_params.model: ollama/nomic-embed-text
     so `nomic-embed` is the proxy's NAME for nomic-embed-text, and that alias is this tool's
     default --model. It is called at the proxy's OpenAI-compatible POST /v1/embeddings, which
     returns 768-dim vectors.

WHY IT IS KEYED ON THE BLOB SHA (the ticket's "only re-embed changed blobs"). The corpus is
massively redundant: today `occ` holds 83,180 .py occurrence rows over only 4,990 DISTINCT .py blob
shas — a ~16.7x fan-out, because the same file recurs across snapshots, branches and forks.
Embedding per occurrence would do ~16x redundant work. So the unit of work here is the BLOB, not the
file: each distinct sha is chunked and embedded ONCE, and `occurrences` records every {repo, path}
that sha appears at. The ledger table `blobs` records each (sha, model) this tool has already
settled; the first thing the indexer does with a candidate sha is look it up in that ledger, and a
hit skips the blob BEFORE any git read and before any embed call. That is what makes a re-run a
near-no-op, and it is why "changed blobs" needs no mtime, no timestamp and no diff: a changed file
is, by definition, a new sha.

SCOPE — PYTHON ONLY, AND WHY. `lower_module_all` is a Python `ast` importer, so a chunk is only
definable for a Python module. The corpus is polyglot (.py 83,180 / .js 6,034 / .json 3,199 / .md
2,535 / .php 2,046 occurrences ...), and this tool indexes the `.py` slice of it: `occ.ext = '.py'`
AND `blob.is_text = 1`. Everything else is out of scope and is never read. (`ext` is stored WITH its
leading dot — '.py', not 'py'.)

CHUNKS — WHAT A ROW IS. One row per callable per blob:
  * `text` is codebean's `original_src` = `ast.unparse(node)` — the canonically re-printed source of
    that callable, always parseable and dedented (a raw indented method segment would not even
    parse). It is NOT a verbatim byte-slice of the file; it is deliberately codebean's form.
  * `line_start`/`line_end` are the callable's REAL span in the original blob (`node.lineno` /
    `node.end_lineno`), so a chunk stays traceable to the file it came from. `line_start` is the
    `def` line; a decorator above it is not counted (that is Python's own ast convention).
  * A module with no callables yields 0 chunks — recorded in the ledger as settled, not retried.

HOW THE LINE-RANGE IS OBTAINED WITHOUT FORKING THE CHUNKER. `lower_module_all` returns no line
numbers, but the ticket requires a line-range. Rather than reimplement it (and drift from it), this
tool CALLS it, then walks the same AST with the same node-selection rule to collect spans, and pairs
the two lists positionally. Both reads go through the SAME temp file, so neither can see different
text than the other. The pairing is CHECKED, not assumed: the lists must have equal length and agree
on every (namespace, name) pair, or the blob is refused with a one-line error rather than silently
stapling the wrong line-range onto a chunk. `--selftest` exercises exactly this on a fixture.

THE `search_document: ` PREFIX. nomic-embed-text is a task-prefixed model: indexed content is
embedded as "search_document: <text>" and a query as "search_query: <text>". The repo's existing
reader already speaks the query half — SemanticSearch.php:264 embeds 'search_query: ' . $q — so this
tool writes the document half, and records the prefix it used in `blobs.prefix` so a searcher can
tell. --prefix overrides it (pass --prefix '' to disable).

TRUNCATION. Ollama's default embedding context is 2048 tokens (~8k chars), so a very long callable
would be silently truncated by the backend. This tool makes that visible instead: a chunk longer
than --max-chars (default 8000) is embedded on its first --max-chars characters, `truncated` is set
to 1, and `embed_chars` records how much was embedded — while `text` still stores the FULL chunk.
Nothing is silently dropped.

VECTORS. Stored the way this repo already stores them (migrations/0019_vector_store.sql:9-20): a
JSON float array in a TEXT column, beside `dim` and `model`. They are L2-normalized, so cosine
similarity between two chunks is their dot product. (The proxy already returns unit-norm vectors;
normalizing is a no-op on those and a correctness guard if a backend ever does not.)

WHAT IT WRITES — the store, and ONLY the store. Default `code_sim.db`, a SIBLING of omni_index.db
(--store overrides). Four objects, all IF NOT EXISTS:
    blobs (sha, model, ...)                 -- the ledger: a settled (sha, model). The skip check.
    chunks (sha, model, chunk_seq, ...)     -- one row per AST chunk: line-range, text, vector
    occurrences (sha, repo, path)           -- every {repo, path} a blob appears at
    code_sim_index (VIEW)                   -- {repo, path, line_start, line_end, chunk, vector}:
                                               the ticket's tuple, chunks JOINed onto occurrences
Writes are idempotent by construction: `chunks` is INSERT OR REPLACE on (sha, model, chunk_seq), and
a sha's content — hence its chunking — is invariant, so a re-index rewrites identical rows;
`occurrences` is INSERT OR IGNORE. NOTHING is ever deleted, and no other file or database is written
to. The omni index, omni.git and the CMS database are never written to at all.

--dry-run, --stats, --verify, --selftest and --list-repos WRITE NOTHING AND CREATE NO FILES: they
open the store read-only through the URI flag `immutable=1` (NOT `mode=ro`, which on a
WAL-journalled db spins up -wal/-shm sidecar files on every open), and when the store does not exist
yet they report an empty one rather than bringing it into being.

    python3 tools/code_sim_indexer.py --repo NAME              # index one repo's python blobs
    python3 tools/code_sim_indexer.py --repo NAME --limit 20   # ... a subset of them
    python3 tools/code_sim_indexer.py --dry-run --repo NAME    # what WOULD be indexed; writes nothing
    python3 tools/code_sim_indexer.py --stats                  # store coverage; writes nothing
    python3 tools/code_sim_indexer.py --verify                 # row counts vs chunk counts; writes nothing
    python3 tools/code_sim_indexer.py --selftest               # prove the chunker pairing; writes nothing
    python3 tools/code_sim_indexer.py --list-repos             # repos in the corpus; writes nothing

Exit 0 when the run completed — including "nothing new to index", which is the expected result of a
second run. Exit 1 when --verify finds the store INCONSISTENT (row counts do NOT match chunk
counts), or when a blob could not be paired to its line-ranges. Exit 2 on a precondition failure (no
omni index, no omni.git, codebean not loadable, unknown --repo, or --verify against a store that
does not exist — an absent store is nothing to verify, not an inconsistent one). Exit 3 when the
litellm proxy cannot be reached or answers unusably. Each of those prints ONE line, never a
traceback. Pure-python stdlib, one file. Registry-gated per note-for-claude: it walks UP to
registry.json and refuses to run without it.
"""
import argparse
import ast
import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


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

# The omni-git index. Same resolution the CMS reader uses: OmniExplorer.php:36 falls back to
# $HOME/code/installed/jazz-project/config/forge/omni_index.db when OMNI_INDEX_DB is unset.
OMNI_DB = os.environ.get("OMNI_INDEX_DB") or os.path.join(
    HOME, "code/installed/jazz-project/config/forge/omni_index.db")
# The bare object store the index's shas live in: a sibling `archives/omni.git` of the index.
OMNI_GIT = os.environ.get("OMNI_GIT") or os.path.join(os.path.dirname(OMNI_DB), "archives", "omni.git")
# The store this tool writes: a sibling of the index it is derived from.
STORE = os.environ.get("CODE_SIM_DB") or os.path.join(os.path.dirname(OMNI_DB), "code_sim.db")
# codebean (ticket #183) — the package dir holding prototype/code_wrapper.py.
CODEBEAN = os.environ.get("CODEBEAN_MCP") or os.path.join(HOME, "code/installed/jazz-project/codebean_mcp")

# The litellm proxy (ticket #184). config/litellm/litellm_config.yaml routes model_name `nomic-embed`
# to litellm_params.model `ollama/nomic-embed-text` — so `nomic-embed` is the proxy's name for the
# model the ticket names. The proxy accepts an unauthenticated call; LITELLM_API_KEY is sent as a
# bearer token when it is set.
LITELLM = os.environ.get("LITELLM_BASE") or "http://127.0.0.1:4000"
LITELLM_KEY = os.environ.get("LITELLM_API_KEY") or ""
MODEL = "nomic-embed"

# nomic-embed-text is task-prefixed: indexed content is "search_document: ", a query is
# "search_query: " (which is what SemanticSearch.php:264 already sends).
DOC_PREFIX = "search_document: "

PY_EXT = ".py"          # omni stores the extension WITH its dot
MAX_CHARS = 8000        # ~2048 tokens: ollama's default embedding context
BATCH = 16
TIMEOUT = 120


class Fault(Exception):
    """A precondition failure — reported as one line, exit 2."""


class EmbedError(Exception):
    """The embedding proxy is unreachable or answered unusably — one line, exit 3."""


class PairError(Exception):
    """A blob's chunks could not be paired to their line-ranges — one line, exit 1."""


# ── read-only sqlite (immutable=1: reads committed data, creates NO -wal/-shm sidecars) ───────────
def ro_connect(path):
    return sqlite3.connect("file:%s?immutable=1" % path, uri=True)


# ── the chunker: codebean's lower_module_all (#183), loaded from the real package ─────────────────
def load_chunker(codebean_dir):
    """codebean's `code_wrapper` module, or raise Fault with a one-line reason.

    Loaded by path rather than imported as a package: codebean_mcp/__init__.py pulls in the FastMCP
    server (an optional dependency this tool does not need) — the same reason code_wrapper.py:33-38
    itself loads model.py by path.

    Two things this loader must get right:
      * the module is registered in sys.modules BEFORE exec_module — code_wrapper.py:61 declares a
        @dataclass, and dataclasses resolves a field's type through sys.modules[cls.__module__],
        which is None for an unregistered module (it raises AttributeError rather than importing);
      * its import-time stdout is captured — code_wrapper.py:47-48 PRINTS a '[telemetry]
        unavailable' notice when jazz_telemetry is absent, which is not this tool's output.
    """
    src = os.path.join(codebean_dir, "prototype", "code_wrapper.py")
    if not os.path.isfile(src):
        raise Fault("codebean's chunker not found at %s — set CODEBEAN_MCP or pass --codebean" % src)
    spec = importlib.util.spec_from_file_location("cb_code_wrapper", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            spec.loader.exec_module(mod)
    except Exception as e:
        raise Fault("codebean's chunker at %s failed to load: %r" % (src, e))
    if not hasattr(mod, "lower_module_all"):
        raise Fault("%s defines no lower_module_all — wrong codebean version?" % src)
    return mod


def _spans(tree):
    """[(namespace, name, line_start, line_end)] under lower_module_all's OWN selection rule
    (code_wrapper.py:107-116): every top-level function, and every method of a top-level class, in
    module-body order. Mirrored here solely to recover the line numbers it does not return."""
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(("", node.name, node.lineno, node.end_lineno))
        elif isinstance(node, ast.ClassDef):
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append((node.name, m.name, m.lineno, m.end_lineno))
    return out


def chunk_text(cw, text):
    """AST-chunk one module's source. Returns (chunks, status):

    chunks: [{chunk_seq, namespace, symbol, line_start, line_end, text}] — codebean's callables,
      each carrying its real span in the original module.
    status: 'indexed' when the module parsed (even to 0 chunks), 'unparseable' when it did not.
      An unparseable blob is a fact about the corpus, not a failure of this run: the forge holds
      python-2 and partial files. It is recorded as settled so it is never re-read.

    The blob is materialized to a temp file because lower_module_all takes a path — and BOTH reads
    (its own, and the AST walked here for spans) go through that one file, so neither can see
    different text than the other."""
    try:
        ast.parse(text)
    except (SyntaxError, ValueError):
        return [], "unparseable"

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "module.py"
        p.write_text(text, encoding="utf-8")
        items = cw.lower_module_all(p)                       # [(namespace, Function, original_src)]
        spans = _spans(ast.parse(p.read_text(encoding="utf-8")))

    # Checked, not assumed: if codebean's selection ever diverges from the mirror above, refuse the
    # blob rather than staple the wrong line-range onto a chunk.
    if len(items) != len(spans):
        raise PairError("lower_module_all returned %d callables but %d spans were found"
                        % (len(items), len(spans)))
    chunks = []
    for seq, ((ns, fn, src), (sns, sname, lo, hi)) in enumerate(zip(items, spans)):
        if ns != sns or fn.name != sname:
            raise PairError("chunk %d is %r/%r but its span is %r/%r" % (seq, ns, fn.name, sns, sname))
        chunks.append({"chunk_seq": seq, "namespace": ns, "symbol": sname,
                       "line_start": lo, "line_end": hi, "text": src})
    return chunks, "indexed"


# ── the corpus: omni_index.db (read-only) + omni.git (read-only plumbing) ─────────────────────────
def omni_tables(con):
    return {r[0].lower() for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def select_blobs(con, repo, limit):
    """[(sha, size)] — the DISTINCT python blobs in scope, in a stable sha order.

    Scope is `occ.ext='.py'` AND `blob.is_text=1`: the chunker is a python ast importer, and a blob
    the index marks non-text is not a python module whatever its extension says."""
    sql = ("SELECT DISTINCT o.sha, b.size FROM occ o JOIN blob b ON b.sha = o.sha "
           "WHERE o.ext = ? AND b.is_text = 1")
    args = [PY_EXT]
    if repo:
        sql += " AND o.repo = ?"
        args.append(repo)
    sql += " ORDER BY o.sha"
    if limit:
        sql += " LIMIT %d" % int(limit)
    return con.execute(sql, args).fetchall()


def occurrences_of(con, shas, repo):
    """[(sha, repo, path)] — every place the given blobs appear, deduped. Scoped to --repo when one
    was given, so the store records what this run actually indexed."""
    out = set()
    shas = list(shas)
    for i in range(0, len(shas), 400):                      # chunked: sqlite caps host parameters
        part = shas[i:i + 400]
        sql = "SELECT DISTINCT sha, repo, path FROM occ WHERE ext = ? AND sha IN (%s)" % (
            ",".join("?" * len(part)))
        args = [PY_EXT] + part
        if repo:
            sql += " AND repo = ?"
            args.append(repo)
        out.update(con.execute(sql, args).fetchall())
    return sorted(out)


def repo_exists(con, repo):
    return con.execute("SELECT 1 FROM occ WHERE repo = ? LIMIT 1", (repo,)).fetchone() is not None


def blob_text(gitdir, sha):
    """The blob decoded as UTF-8, or None when it is absent or not UTF-8.

    Read raw (no text=True): universal-newline translation would mutate the bytes away from what the
    corpus actually holds before they are ever chunked."""
    r = subprocess.run(["git", "--git-dir", gitdir, "cat-file", "blob", sha], capture_output=True)
    if r.returncode != 0:
        return None
    try:
        return r.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ── the embedder: litellm proxy, OpenAI-compatible POST /v1/embeddings ────────────────────────────
def l2(vec):
    """The vector scaled to unit length, so cosine similarity is a dot product. A zero vector is
    returned unchanged rather than dividing by zero."""
    n = sum(x * x for x in vec) ** 0.5
    return [x / n for x in vec] if n else list(vec)


def embed_batch(base, model, key, inputs, timeout):
    """[unit-norm vector] for `inputs`, in the SAME order. Raises EmbedError on any failure."""
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
        raise EmbedError("litellm %s unreachable (%r) — is the proxy up?" % (base, e))
    data = doc.get("data")
    if not isinstance(data, list) or len(data) != len(inputs):
        raise EmbedError("litellm returned %s embeddings for %d inputs"
                         % (len(data) if isinstance(data, list) else "no", len(inputs)))
    # `index` echoes the input position; sort by it rather than trusting arrival order.
    data = sorted(data, key=lambda d: d.get("index", 0))
    vecs = []
    for d in data:
        v = d.get("embedding")
        if not isinstance(v, list) or not v:
            raise EmbedError("litellm returned an empty embedding for model %r" % model)
        vecs.append(l2(v))
    return vecs


def embed_all(base, model, key, texts, batch, timeout):
    out = []
    for i in range(0, len(texts), batch):
        out.extend(embed_batch(base, model, key, texts[i:i + batch], timeout))
    return out


# ── the store ─────────────────────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS blobs (
  sha        TEXT NOT NULL,          -- the omni-git blob sha: the incremental key
  model      TEXT NOT NULL,
  ext        TEXT,
  size       INTEGER,
  n_chunks   INTEGER,
  status     TEXT,                   -- 'indexed' | 'unparseable' | 'unreadable'
  prefix     TEXT,
  indexed_ts INTEGER,
  PRIMARY KEY (sha, model)
);
CREATE TABLE IF NOT EXISTS chunks (
  sha         TEXT NOT NULL,
  model       TEXT NOT NULL,
  chunk_seq   INTEGER NOT NULL,
  namespace   TEXT,                  -- enclosing class for a method, '' for a top-level function
  symbol      TEXT,
  line_start  INTEGER,               -- the callable's real span in the original blob
  line_end    INTEGER,
  text        TEXT,                  -- the FULL chunk (codebean's ast.unparse form)
  embed_chars INTEGER,               -- how much of `text` was actually embedded
  truncated   INTEGER,
  dim         INTEGER,
  vector      TEXT,                  -- JSON float array, L2-normalized (as 0019_vector_store.sql)
  PRIMARY KEY (sha, model, chunk_seq)
);
CREATE TABLE IF NOT EXISTS occurrences (
  sha  TEXT NOT NULL,
  repo TEXT NOT NULL,
  path TEXT NOT NULL,
  PRIMARY KEY (sha, repo, path)
);
CREATE INDEX IF NOT EXISTS idx_occurrences_repo ON occurrences (repo);
CREATE INDEX IF NOT EXISTS idx_chunks_sha ON chunks (sha);
CREATE VIEW IF NOT EXISTS code_sim_index AS
  SELECT o.repo, o.path, c.line_start, c.line_end, c.text AS chunk, c.vector,
         c.sha AS blob_sha, c.namespace, c.symbol, c.chunk_seq, c.dim, c.model
  FROM chunks c JOIN occurrences o ON o.sha = c.sha;
"""


def open_store(path):
    con = sqlite3.connect(path, timeout=30)
    con.executescript(SCHEMA)
    return con


def settled(con, model):
    """The set of shas this store has already settled for `model` — the skip check. Read once per
    run: one query beats one per blob."""
    if con is None:
        return set()
    return {r[0] for r in con.execute("SELECT sha FROM blobs WHERE model = ?", (model,))}


def store_blob(con, sha, model, ext, size, chunks, status, prefix, dim):
    ts = int(time.time())
    con.execute("INSERT OR REPLACE INTO blobs (sha, model, ext, size, n_chunks, status, prefix, indexed_ts) "
                "VALUES (?,?,?,?,?,?,?,?)", (sha, model, ext, size, len(chunks), status, prefix, ts))
    for c in chunks:
        con.execute(
            "INSERT OR REPLACE INTO chunks (sha, model, chunk_seq, namespace, symbol, line_start, "
            "line_end, text, embed_chars, truncated, dim, vector) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (sha, model, c["chunk_seq"], c["namespace"], c["symbol"], c["line_start"], c["line_end"],
             c["text"], c["embed_chars"], c["truncated"], dim, json.dumps(c["vector"])))


def store_occurrences(con, occs):
    con.executemany("INSERT OR IGNORE INTO occurrences (sha, repo, path) VALUES (?,?,?)", occs)


# ── reports ───────────────────────────────────────────────────────────────────────────────────────
def print_stats(con):
    if con is None:
        print("store is empty (it does not exist yet) — nothing indexed")
        return
    blobs = con.execute("SELECT COUNT(*) FROM blobs").fetchone()[0]
    chunks = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    occs = con.execute("SELECT COUNT(*) FROM occurrences").fetchone()[0]
    repos = con.execute("SELECT COUNT(DISTINCT repo) FROM occurrences").fetchone()[0]
    view = con.execute("SELECT COUNT(*) FROM code_sim_index").fetchone()[0]
    print("store: %d blobs, %d chunks, %d occurrences across %d repos "
          "(code_sim_index view: %d rows)" % (blobs, chunks, occs, repos, view))
    rows = con.execute("SELECT model, status, COUNT(*), COALESCE(SUM(n_chunks),0) FROM blobs "
                       "GROUP BY model, status ORDER BY model, status").fetchall()
    if rows:
        print("\n  %-16s %-12s %8s %8s" % ("MODEL", "STATUS", "BLOBS", "CHUNKS"))
        print("  " + "-" * 48)
        for m, s, n, ch in rows:
            print("  %-16s %-12s %8d %8d" % (m, s, n, ch))
    top = con.execute("SELECT repo, COUNT(DISTINCT sha) FROM occurrences GROUP BY repo "
                      "ORDER BY 2 DESC LIMIT 10").fetchall()
    if top:
        print("\n  %-52s %s" % ("REPO", "BLOBS"))
        print("  " + "-" * 62)
        for r, n in top:
            print("  %-52s %d" % (r, n))


def verify(con):
    """The ticket's acceptance check: row counts match chunk counts. Returns (ok, [line]).

    Four invariants, each a way the store could be wrong:
      1. chunk ROWS == the chunk counts the ledger recorded (SUM(blobs.n_chunks));
      2. every ledger blob has exactly the chunk rows it claims;
      3. every chunk row carries a vector and a positive dim (nothing half-embedded);
      4. every chunk row's blob is in the ledger (no orphans)."""
    if con is None:
        return False, ["store is empty (it does not exist yet) — nothing to verify"]
    lines, ok = [], True

    ledger = con.execute("SELECT COALESCE(SUM(n_chunks),0) FROM blobs").fetchone()[0]
    rows = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    good = ledger == rows
    ok &= good
    lines.append("%s chunk rows == ledger chunk counts: %d rows, %d claimed"
                 % ("PASS" if good else "FAIL", rows, ledger))

    bad = con.execute(
        "SELECT COUNT(*) FROM blobs b WHERE b.n_chunks != "
        "(SELECT COUNT(*) FROM chunks c WHERE c.sha = b.sha AND c.model = b.model)").fetchone()[0]
    ok &= bad == 0
    lines.append("%s every blob has exactly the chunk rows it claims: %d mismatched"
                 % ("PASS" if bad == 0 else "FAIL", bad))

    novec = con.execute("SELECT COUNT(*) FROM chunks WHERE vector IS NULL OR vector = '' "
                        "OR dim IS NULL OR dim <= 0").fetchone()[0]
    ok &= novec == 0
    lines.append("%s every chunk row carries a vector: %d without one"
                 % ("PASS" if novec == 0 else "FAIL", novec))

    orphan = con.execute("SELECT COUNT(*) FROM chunks c WHERE NOT EXISTS "
                         "(SELECT 1 FROM blobs b WHERE b.sha = c.sha AND b.model = c.model)").fetchone()[0]
    ok &= orphan == 0
    lines.append("%s every chunk row's blob is in the ledger: %d orphans"
                 % ("PASS" if orphan == 0 else "FAIL", orphan))

    # Reported, not asserted: the view fans chunks out over occurrences, so it is EXPECTED to be
    # larger than `chunks` (one blob appears at many {repo, path}). It is the ticket's row shape.
    view = con.execute("SELECT COUNT(*) FROM code_sim_index").fetchone()[0]
    lines.append("     code_sim_index view: %d {repo, path, line-range, chunk, vector} rows "
                 "(chunks x occurrences)" % view)
    return bool(ok), lines


SELFTEST_SRC = '''\
import os


@decorated
def top_level(a, b=1) -> int:
    """doc"""
    return a + b


class Widget:
    ATTR = 1

    def __init__(self, x):
        self.x = x

    async def fetch(self, url):
        return await get(url)


def after(*args, **kw):
    pass
'''


def _parses(src):
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def selftest(cw):
    """Prove the two claims the chunker rests on, on a fixture with known answers:
      1. the callables and their order are codebean's (top-level fns AND class methods);
      2. every chunk's line-range really spans that callable in the source.
    Writes nothing."""
    chunks, status = chunk_text(cw, SELFTEST_SRC)
    print("=== selftest: codebean lower_module_all pairing ===\n")
    print("  status: %s, %d chunks" % (status, len(chunks)))
    expect = [("", "top_level"), ("Widget", "__init__"), ("Widget", "fetch"), ("", "after")]
    got = [(c["namespace"], c["symbol"]) for c in chunks]
    ok = got == expect
    print("  %s selection+order is codebean's: %s" % ("PASS" if ok else "FAIL", got))

    lines = SELFTEST_SRC.splitlines()
    spans_ok = True
    print("\n  %-10s %-12s %-9s %s" % ("NAMESPACE", "SYMBOL", "LINES", "SOURCE AT line_start"))
    print("  " + "-" * 66)
    for c in chunks:
        head = lines[c["line_start"] - 1].strip()
        good = c["symbol"] in head and 1 <= c["line_start"] <= c["line_end"] <= len(lines)
        spans_ok &= good
        print("  %-10s %-12s %-9s %s" % (c["namespace"] or "-", c["symbol"],
                                         "%d-%d" % (c["line_start"], c["line_end"]), head))
    print("\n  %s every line-range lands on its callable's def line" % ("PASS" if spans_ok else "FAIL"))
    # `text` is codebean's ast.unparse form, not a byte-slice: it must still parse on its own.
    parses = all(_parses(c["text"]) for c in chunks)
    print("  %s every chunk's text is independently parseable" % ("PASS" if parses else "FAIL"))
    good = ok and spans_ok and parses and status == "indexed"
    print("\n=== selftest: %s ===" % ("PASS" if good else "FAIL"))
    return 0 if good else 1


# ── main ──────────────────────────────────────────────────────────────────────────────────────────
def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(
        description="AST-chunk + embed the forge's python corpus (omni-git) into a vector store, "
                    "incrementally: only blobs whose sha is not already in the store are embedded.")
    ap.add_argument("--repo", default="", help="limit to one repo in the corpus (see --list-repos)")
    ap.add_argument("--limit", type=int, default=0, help="index at most N distinct blobs (a subset)")
    ap.add_argument("--store", default=STORE, help="vector store to write (default: %s)" % STORE)
    ap.add_argument("--omni-db", default=OMNI_DB, help="omni-git index (default: %s)" % OMNI_DB)
    ap.add_argument("--omni-git", default=OMNI_GIT, help="omni-git object store (default: %s)" % OMNI_GIT)
    ap.add_argument("--codebean", default=CODEBEAN, help="codebean_mcp dir (default: %s)" % CODEBEAN)
    ap.add_argument("--litellm", default=LITELLM, help="litellm proxy base url (default: %s)" % LITELLM)
    ap.add_argument("--model", default=MODEL, help="litellm model name (default: %s)" % MODEL)
    ap.add_argument("--prefix", default=DOC_PREFIX, help="embed prefix (default: %r)" % DOC_PREFIX)
    ap.add_argument("--max-chars", type=int, default=MAX_CHARS,
                    help="embed at most N chars per chunk (default: %d)" % MAX_CHARS)
    ap.add_argument("--batch", type=int, default=BATCH, help="chunks per embed call (default: %d)" % BATCH)
    ap.add_argument("--timeout", type=int, default=TIMEOUT, help="embed timeout secs (default: %d)" % TIMEOUT)
    ap.add_argument("--reindex", action="store_true", help="re-embed even blobs already in the store")
    ap.add_argument("--dry-run", action="store_true", help="report what WOULD be indexed; write nothing")
    ap.add_argument("--stats", action="store_true", help="print store coverage and exit; write nothing")
    ap.add_argument("--verify", action="store_true", help="check row counts vs chunk counts; write nothing")
    ap.add_argument("--selftest", action="store_true", help="prove the chunker pairing; write nothing")
    ap.add_argument("--list-repos", action="store_true", help="list corpus repos and exit; write nothing")
    ap.add_argument("--json", metavar="PATH", default="", help="also write the run report as JSON")
    a = ap.parse_args()

    # --selftest needs only the chunker: no corpus, no store, no proxy.
    if a.selftest:
        return selftest(load_chunker(a.codebean))

    # --stats / --verify read only the store, and never bring it into being: absent means empty.
    # An absent store is nothing to verify — a precondition failure, NOT an inconsistent store.
    if a.verify and not os.path.isfile(a.store):
        print("code_sim_indexer: no store at %s — nothing to verify; index something first" % a.store)
        return 2
    if a.stats or a.verify:
        scon = ro_connect(a.store) if os.path.isfile(a.store) else None
        try:
            if a.stats:
                print_stats(scon)
                return 0
            ok, lines = verify(scon)
            print("=== verify %s ===\n" % a.store)
            for ln in lines:
                print("  " + ln)
            print("\n=== %s ===" % ("PASS — row counts match chunk counts" if ok else "FAIL"))
            return 0 if ok else 1
        finally:
            if scon is not None:
                scon.close()

    if not os.path.isfile(a.omni_db):
        print("code_sim_indexer: no omni-git index at %s — set OMNI_INDEX_DB or pass --omni-db" % a.omni_db)
        return 2
    ocon = ro_connect(a.omni_db)
    try:
        have = omni_tables(ocon)
        for t in ("occ", "blob"):
            if t not in have:
                print("code_sim_indexer: table `%s` missing from %s — not an omni-git index" % (t, a.omni_db))
                return 2

        if a.list_repos:
            rows = ocon.execute("SELECT repo, COUNT(DISTINCT sha) n FROM occ WHERE ext = ? "
                                "GROUP BY repo ORDER BY n DESC", (PY_EXT,)).fetchall()
            print("%d repo(s) with python blobs in %s\n" % (len(rows), a.omni_db))
            print("  %-52s %s" % ("REPO", "BLOBS"))
            print("  " + "-" * 62)
            for r, n in rows:
                print("  %-52s %d" % (r, n))
            return 0

        if a.repo and not repo_exists(ocon, a.repo):
            print("code_sim_indexer: no repo named %r in the corpus (see --list-repos)" % a.repo)
            return 2
        if not os.path.isdir(a.omni_git):
            print("code_sim_indexer: no omni-git object store at %s — set OMNI_GIT or pass --omni-git"
                  % a.omni_git)
            return 2

        cw = load_chunker(a.codebean)

        candidates = select_blobs(ocon, a.repo, a.limit)
        scon_ro = ro_connect(a.store) if os.path.isfile(a.store) else None
        done = set() if a.reindex else settled(scon_ro, a.model)
        if scon_ro is not None:
            scon_ro.close()
        todo = [(s, sz) for s, sz in candidates if s not in done]

        scope = "repo %r" % a.repo if a.repo else "the whole corpus"
        mode = "DRY-RUN (nothing is written)" if a.dry_run else "indexing"
        print("=== code_sim_indexer — %s — %s ===" % (mode, scope))
        print("  corpus : %s" % a.omni_db)
        print("  blobs  : %s" % a.omni_git)
        print("  store  : %s%s" % (a.store, "" if os.path.isfile(a.store) else " (will be created)"))
        print("  model  : %s via %s%s\n" % (a.model, a.litellm, " [--reindex]" if a.reindex else ""))
        print("  %d python blob(s) in scope, %d already in the store, %d to embed\n"
              % (len(candidates), len(candidates) - len(todo), len(todo)))

        if a.dry_run:
            for sha, size in todo[:20]:
                print("  WOULD  %s  %6d bytes" % (sha[:12], size or 0))
            if len(todo) > 20:
                print("  ... and %d more" % (len(todo) - 20))
            print("\n=== would index %d blob(s); %d already current — nothing written ==="
                  % (len(todo), len(candidates) - len(todo)))
            return 0

        con = open_store(a.store)
        try:
            n_ok = n_unparse = n_unread = n_chunks = n_embed = 0
            report = []
            for sha, size in todo:
                text = blob_text(a.omni_git, sha)
                if text is None:
                    n_unread += 1
                    store_blob(con, sha, a.model, PY_EXT, size, [], "unreadable", a.prefix, 0)
                    print("  SKIP   %s  not readable as UTF-8 from omni.git" % sha[:12])
                    continue
                chunks, status = chunk_text(cw, text)
                if status == "unparseable":
                    n_unparse += 1
                    store_blob(con, sha, a.model, PY_EXT, size, [], status, a.prefix, 0)
                    print("  SKIP   %s  not parseable as python" % sha[:12])
                    continue

                dim = 0
                if chunks:
                    payload, meta = [], []
                    for c in chunks:
                        body = c["text"][:a.max_chars]
                        payload.append(a.prefix + body)
                        meta.append((len(body), 1 if len(c["text"]) > a.max_chars else 0))
                    vecs = embed_all(a.litellm, a.model, LITELLM_KEY, payload, a.batch, a.timeout)
                    for c, v, (ec, tr) in zip(chunks, vecs, meta):
                        c["vector"], c["embed_chars"], c["truncated"] = v, ec, tr
                    dim = len(vecs[0])
                    n_embed += len(vecs)
                store_blob(con, sha, a.model, PY_EXT, size, chunks, status, a.prefix, dim)
                n_ok += 1
                n_chunks += len(chunks)
                report.append({"sha": sha, "size": size, "chunks": len(chunks)})
                print("  OK     %s  %2d chunk(s)%s" % (sha[:12], len(chunks),
                                                       "  (no callables)" if not chunks else ""))

            occs = occurrences_of(ocon, [s for s, _ in candidates], a.repo)
            store_occurrences(con, occs)
            con.commit()

            print("\n=== indexed %d blob(s) -> %d chunk(s), %d embedded; "
                  "%d already current (not re-read, not re-embedded); "
                  "%d unparseable, %d unreadable ==="
                  % (n_ok, n_chunks, n_embed, len(candidates) - len(todo), n_unparse, n_unread))
            print("  %d {repo, path} occurrence(s) recorded for %d blob(s) in scope."
                  % (len(occs), len(candidates)))
            print("  Read the ticket's tuple back with:  SELECT repo, path, line_start, line_end, "
                  "chunk, vector FROM code_sim_index;")
            if not todo:
                print("  Nothing to do — this run was a no-op. That is the incremental contract.")

            if a.json:
                json.dump({"store": a.store, "repo": a.repo or None, "model": a.model,
                           "in_scope": len(candidates), "already_current": len(candidates) - len(todo),
                           "indexed": n_ok, "chunks": n_chunks, "embedded": n_embed,
                           "unparseable": n_unparse, "unreadable": n_unread,
                           "occurrences": len(occs), "blobs": report},
                          open(a.json, "w"), indent=2)
                print("  JSON: %s" % a.json)
            return 0
        finally:
            con.close()
    finally:
        ocon.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as e:
        print("code_sim_indexer: %s" % e)
        sys.exit(2)
    except PairError as e:
        print("code_sim_indexer: chunker/line-range disagreement — %s" % e)
        sys.exit(1)
    except EmbedError as e:
        print("code_sim_indexer: %s" % e)
        sys.exit(3)
    except KeyboardInterrupt:
        print("code_sim_indexer: interrupted — the store keeps every blob committed so far")
        sys.exit(130)
