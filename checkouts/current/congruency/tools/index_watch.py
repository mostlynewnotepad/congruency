#!/usr/bin/env python3
"""index_watch.py — the SELF-REPOPULATING index-watch runner (ticket #197).

One run of the watch, in the order the code executes it:

    1. BRAKE      ticket.stops — an active (unreleased) stop ticket aimed at this ticket or any
                  ancestor halts the run before anything acts (the pattern pair_loop.py:1001-1006
                  uses). ticket.stops is then the ONLY call the run makes: nothing is registered,
                  indexed, recorded or spawned, and the store is not even created. Exit 5.
    2. REGISTER   agent.register — the runner is a NORMAL registered agent (`index-watch-t<id>`),
                  and every write below is attributed to it. See "THE AGENT" for why it is
                  registered but never ticket.assign'd.
    3. MARK       read the last HIGH-WATER-MARK from the PREDECESSOR ticket's manifest
                  (ticket.manifest, the `mark` work row). See "THE MARK" for what it is and how
                  the predecessor is found. No mark anywhere => GENESIS (the whole scope is new).
    4. DELTA      compute the new/changed blobs as an omni-git SHA DELTA: the distinct python
                  blobs in scope MINUS the blob shas the vector store has already settled. A
                  changed file is, by definition, a new sha. See "THE DELTA".
    5. INDEX      for each new blob: AST-chunk + embed it into the vector store (#189), and
                  CONFIRM its omni-git occ/blob coverage. See "THE INDEXING".
    6. RECORD     work.record each indexed blob onto this ticket's PERMANENT manifest (one work
                  UID per blob sha), then ticket.progress the count.
    7. ADVANCE    work.record the NEW high-water-mark onto the same manifest (a `mark` work row).
    8. SPAWN      ticket.create + ticket.kind + edge.record('spawned') — the SUCCESSOR index-watch
                  ticket, its body CARRYING the new mark, primed for the next delta. This happens
                  on EVERY completed run, including a run that indexed nothing: that is what makes
                  the pattern self-repopulating (an append-only ticket cannot reopen, so it
                  perpetuates by spawning).

TERMS (defined at first use, because this file is read without its author present).

  * A BLOB SHA is git's content address: the sha IS a hash of the bytes, so two files with the same
    sha are byte-identical and one sha can never mean two different contents. Every idempotency
    claim below rests on that property alone.
  * THE OMNI-GIT INDEX is `omni_index.db`, a sqlite database SEPARATE from the CMS's congruency
    sqlite, built by jazz-forge's omni_index.py. This tool only ever READS it. Two tables matter:
        occ  (sha, path, ext, size, ref, repo, ts)  -- one row per OCCURRENCE: this blob appeared
                                                       at this path, in this repo, in this snapshot
        blob (sha, path, ext, size, is_text)        -- one row per DISTINCT blob
    Its content lives in `archives/omni.git`, a bare git object store, read with read-only plumbing
    (`git --git-dir=<omni.git> cat-file blob <sha>`) and never written to.
  * THE VECTOR STORE is `code_sim.db`, the store ticket #189's tools/code_sim_indexer.py builds and
    ticket #190 (code.search) / #193 (the universal resolver) will read. Its `code_sim_index` VIEW
    is the searchable tuple {repo, path, line_start, line_end, chunk, vector}
    (code_sim_indexer.py:423-426). "Searchable" in this tool's ACCEPTANCE means exactly: the blob's
    chunks are rows of that view, carrying vectors, at the {repo, path} omni says they live at.
  * A MANIFEST is a ticket's permanent list of the works it authorized, one mechanical never-reissued
    UID per item (`ticket_works`, migrations/0029_ticket_authorization.sql:86-94). It is append-only:
    tg_ticket_works_no_update / tg_ticket_works_no_delete (0029:147-150) refuse any edit or delete.
  * THE JOURNAL is a ticket's append-only event log (`ticket_events`, 0029:73-83); a progress report
    is APPENDED to it, never edited (tg_ticket_events_no_update, 0029:142-143).
  * A SPAWNED EDGE is a parent->child row in `ticket_edges` with kind 'spawned'
    (migrations/0012_ticket_edges.sql:6-12) — the graph edge that makes ticket #N the parent of the
    successor it filed.

THIS TOOL REUSES #189 RATHER THAN REIMPLEMENTING IT. The corpus scoping, the AST chunker, the
embedder, the store schema and the store writes are all imported from the sibling
tools/code_sim_indexer.py and called as they are (load_indexer() below). That is deliberate and it
is the load-bearing reason the ACCEPTANCE holds: blobs this watch indexes are chunked, embedded and
stored by the SAME code that built the rest of the store, so they are indistinguishable from it to
whatever reads it. A parallel reimplementation here could drift from #189 and make "searchable"
false in ways no test here would see.

THE AGENT. The runner registers `index-watch-t<ticket>` through agent.register (a normal agent: an
id, a parent, a prompt and its tools — migrations/0001_agents.sql:8-25), and every governed write is
attributed to it. It is deliberately NOT ticket.assign'd. That is not an oversight: ticket #197 is a
`build` ticket, and `build` is a PAIR kind (0029:35), so tg_tickets_pair_completion (0029:133-140)
refuses DONE unless two DISTINCT agents hold two DISTINCT roles on it. Assigning a third,
always-present agent would help satisfy that check and quietly hollow out the db's own backstop
against a ticket settling without an adversary. This is exactly the reasoning pair_loop.py's
forge_agent() gives for keeping the forge off ticket_agents (pair_loop.py:614-625), and dispatch-01
journals onto tickets the same way (pair_loop.py:573-574). Registering and attributing is the whole
requirement; authorizing is the pair's business.

THE MARK — what a high-water-mark is here, and the trap it must not fall into.
The mark is a JSON cursor recorded as a `mark` work row on the ticket's manifest: `ref` carries the
mark itself (a mark has no path — the mark IS the recorded item) and `note` carries a human
sentence, so `ticket.manifest` and tools/ticket_status.py both render it directly. It holds the
corpus FRONTIER this ticket saw: the snapshot labels in scope, the in-scope blob count, the settled
count, the model, and the store it was measured against.

  * FINDING THE PREDECESSOR. The successor's body (spawned in step 8) carries two machine-readable
    lines — `index-watch-predecessor: <id>` and `index-watch-mark: <json>`. A run parses its OWN
    ticket body for the predecessor id and reads THAT ticket's manifest for the mark, which is the
    ticket's requirement ("read the last high-water-mark from the predecessor ticket's manifest").
    `--predecessor N` overrides the parse. If this ticket's own manifest already carries a mark (it
    has run before), that later mark wins, so re-runs stay monotone. No mark anywhere = GENESIS.
  * THE TRAP: THE MARK IS NOT A RANGE FILTER, AND MUST NOT BE. The obvious design — "index the
    occurrences newer than the last mark's timestamp" — is WRONG against this corpus, and silently
    so. `occ.ts` is a snapshot LABEL, not an ordered timestamp: the live index holds 28 distinct
    values, and beside stamps like '20260701T122754Z' it holds the labels 'test' and 'gitlab'
    (verify with: SELECT DISTINCT ts FROM occ). A `ts > mark` window over that column drops every
    blob whose label does not happen to sort after the mark, and reports a clean no-op while doing
    it. A second, kind-independent trap: any mark-shaped window skips a blob that was in an
    already-seen snapshot but never actually got indexed (an interrupted run, or a prior `--limit`).
    So the mark NEVER filters the delta. It is the durable record of the frontier, the thing carried
    to the successor, and what the run diffs against to name which snapshots are new. The delta
    itself is computed from shas, which cannot lie (see THE DELTA).

THE DELTA — new/changed blobs, via the omni-git sha delta.
    delta = {distinct python blobs in scope, per omni-git} MINUS {blob shas the store has settled}
The in-scope set is code_sim_indexer.select_blobs() — `occ.ext = '.py'` AND `blob.is_text = 1`
(code_sim_indexer.py:290-304), reused verbatim so this watch's scope IS #189's scope. The settled set
is code_sim_indexer.settled() — the store's `blobs` ledger for this model (code_sim_indexer.py:436-441).
Both halves are keyed on the blob sha, so the delta is exactly "the blobs whose bytes the store has
never seen": it cannot miss a changed file (a change is a new sha) and it cannot re-do an unchanged
one. This is what "idempotent on sha" means here, and it is why re-running with no new code is a
clean no-op — not because a mark said so, but because every sha is already settled.
PYTHON ONLY, and why: #189's chunker is a python `ast` importer, so a chunk is only definable for a
python module; the polyglot remainder of the corpus is out of scope and is never read. (`ext` is
stored WITH its leading dot — '.py', not 'py'.)
`--limit N` caps how many of the delta THIS run indexes, never the delta itself and never the
frontier the mark records. Whatever it defers is still unsettled, so the next watch recomputes it
into its own delta and picks it up — and the run says so rather than reporting a quiet success over
a truncated set.

THE INDEXING. Per new blob, through #189's own functions: read it from omni.git (blob_text), AST-chunk
it into one chunk per callable (chunk_text, which is codebean's lower_module_all plus the checked
line-range pairing), embed each chunk with nomic-embed-text through the litellm proxy, and write the
ledger + chunk rows (store_blob). Then CONFIRM omni-git coverage: every indexed sha must have a `blob`
row AND at least one `occ` row in the omni index, and its {repo, path} occurrences are written to the
store so the `code_sim_index` view resolves. Coverage is CONFIRMED, never repaired: omni_index.py owns
that database and this tool never writes to it. A gap is reported and exits 1 rather than being
papered over. A blob that is unreadable or unparseable is recorded as settled (not retried) — that is
a fact about the corpus, not a failure of the run, and it is #189's behavior, kept.

WHAT IT WRITES, AND NOTHING ELSE.
  * The congruency db: ONLY through the governed REST routes (agent.register, work.record,
    ticket.progress, ticket.create, ticket.kind, edge.record). This tool holds no SQL pen — it opens
    the congruency sqlite never, not even to read; the mark, the manifest and the ticket body all
    arrive over the same governed surface.
  * The vector store `code_sim.db`: through #189's writers, INSERT OR REPLACE on (sha, model,
    chunk_seq) and INSERT OR IGNORE on occurrences. Nothing is ever deleted.
  * NOTHING ELSE. The omni index, omni.git, and every other database and file are never written to.
    --dry-run / --status / --selftest write NOTHING AT ALL and CREATE NO FILES: they open sqlite
    read-only through the URI flag `immutable=1` (NOT `mode=ro`, which on a WAL-journalled db spins
    up -wal/-shm sidecar files on every open), and an absent store is reported as empty rather than
    brought into being.

    python3 tools/index_watch.py --ticket 197              # run the watch (the real thing)
    python3 tools/index_watch.py --ticket 197 --limit 5    # ... indexing at most 5 new blobs
    python3 tools/index_watch.py --ticket 197 --dry-run    # the delta + what WOULD happen; writes nothing
    python3 tools/index_watch.py --status --ticket 197     # the mark + store coverage; writes nothing
    python3 tools/index_watch.py --selftest                # prove the whole flow offline; writes nothing
    ... [--repo NAME] [--predecessor N] [--successor-kind KIND] [--no-spawn] [--store PATH]

--selftest builds a THROWAWAY omni-git corpus (a bare object store + an index over it) and a
throwaway vector store in a temp dir, drives genesis -> re-run -> new-code -> successor-chain
through them against a recording stand-in for the governed surface and a deterministic local
embedder, CHECKS each of the ticket's acceptance claims, then deletes the temp dir. It never touches
this repo, the live databases, the litellm proxy or the network, and files no ticket.

Exit codes:
    0  the run completed — INCLUDING "no new blobs", the clean no-op, which still spawns the successor
       (--selftest: every check passed)
    1  a coverage/verification failure: an indexed sha lacks omni-git occ/blob coverage, or a blob's
       chunks could not be paired to their line-ranges. Nothing is spawned.
       (--selftest: at least one check FAILED)
    2  a precondition failure — no omni index, no omni.git object store, codebean not loadable, no
       CONGRUENCY_API_KEY, unknown --repo, unknown --successor-kind, or no such ticket
    3  the litellm embedding proxy is unreachable or answered unusably (mirrors code_sim_indexer.py)
    4  a governed route failed or the congruency REST surface is unreachable — the writes ARE the
       work, so a run that cannot record is a failed run, never a silent success
    5  HALTED — an active (unreleased) stop ticket aims at this ticket or an ancestor; nothing was done
Each prints ONE line, never a traceback. Pure-python stdlib, one file. Registry-gated per
note-for-claude: it walks UP to registry.json and refuses to run without it.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.request

# NO BYTECODE CACHE. This tool loads code_sim_indexer.py (and, through it, codebean's chunker) from
# SOURCE via importlib. Python's default is to cache the compiled bytecode beside the source, so
# every run would mint `checkouts/current/congruency/tools/__pycache__/code_sim_indexer.*.pyc` —
# creating a file in the repo tree, which contradicts this module's own "writes NOTHING AT ALL and
# CREATES NO FILES" guarantee for --status/--dry-run/--selftest. (`__pycache__/` and `*.pyc` are
# gitignored (.gitignore:4-5), so it would never be committed — but "gitignored" is not "not
# created", and the guarantee is about the filesystem, not about git.) Set before any of those loads
# happen, so the guarantee holds on every path; the cost is one re-parse per run of a one-shot CLI.
sys.dont_write_bytecode = True


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


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT, REGISTRY = find_registry(HERE)

CONG = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")

MARK_KIND = "mark"            # the ticket_works.kind of a high-water-mark row
BLOB_KIND = "code"            # the ticket_works.kind of an indexed-blob row
BLOB_REF = "omni-blob:%s"     # ticket_works.ref of an indexed blob: its omni-git content address
MARK_V = 1                    # the mark's schema version (carried in the JSON as "v")
AGENT = "index-watch-t%d"     # the registered runner for ticket N
DEFAULT_SUCCESSOR_KIND = ""   # "" = inherit the predecessor ticket's own kind

# The two machine-readable lines the successor's body carries, and this runner parses back out.
BODY_PRED = "index-watch-predecessor:"
BODY_MARK = "index-watch-mark:"


class Fault(Exception):
    """A precondition failure — reported as one line, exit 2."""


class GovError(Exception):
    """A governed route failed or the REST surface is unreachable — one line, exit 4."""


class CoverageError(Exception):
    """An indexed sha lacks omni-git occ/blob coverage — one line, exit 1."""


class Halted(Exception):
    """The brake: an active stop ticket aims at this ticket or an ancestor — one line, exit 5."""


# ── #189's indexer, reused as-is (the scope, the chunker, the embedder, the store) ────────────────
def load_indexer(path=None):
    """The sibling tools/code_sim_indexer.py (ticket #189), loaded as a module.

    Loaded by path rather than imported by name because `tools/` is not a package: this mirrors how
    code_sim_indexer.py itself loads codebean's chunker (code_sim_indexer.py:203-230). Importing it
    runs only its registry gate and its constants — it opens nothing and writes nothing at import.
    """
    src = path or os.path.join(HERE, "code_sim_indexer.py")
    if not os.path.isfile(src):
        raise Fault("tools/code_sim_indexer.py (ticket #189) not found at %s — the watch indexes "
                    "through it and will not reimplement it" % src)
    spec = importlib.util.spec_from_file_location("cs_indexer", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        raise Fault("code_sim_indexer.py at %s failed to load: %r" % (src, e))
    for fn in ("select_blobs", "settled", "chunk_text", "blob_text", "store_blob",
               "store_occurrences", "open_store", "ro_connect", "load_chunker", "embed_all",
               "occurrences_of", "omni_tables", "l2"):
        if not hasattr(mod, fn):
            raise Fault("%s defines no %s — wrong code_sim_indexer version?" % (src, fn))
    return mod


# ── the governed surface: every db write goes through a token route, never SQL ────────────────────
def _secret(name):
    """CONGRUENCY_API_KEY from the environment, else the nearest `.secrets/ats.env` at or above the
    repo root.

    pair_loop.py:141-147 reads exactly one candidate — `<dirname(ROOT)>/.secrets/ats.env` — which
    resolves for the deployed layout (ROOT `.../jazz-project/congruency` -> `.../jazz-project/
    .secrets/ats.env`) but not from a pair worktree, whose ROOT is nested one level deeper
    (registry.json's branch_per_ticket.worktrees puts them under `.../congruency-pair-worktrees/
    ticket-<id>`). Walking UP is the same idiom the registry gate itself uses (find_registry above),
    finds the identical file in the deployed layout, and additionally works from a worktree — so
    this tool runs the same way wherever it is checked out.
    """
    env = os.environ.get(name)
    if env:
        return env
    d = ROOT
    while True:
        path = os.path.join(d, ".secrets", "ats.env")
        if os.path.isfile(path):
            for line in open(path):
                if line.strip().startswith(name + "="):
                    return line.strip().split("=", 1)[1]
        nxt = os.path.dirname(d)
        if nxt == d:
            return None
        d = nxt


class Gov:
    """The governed REST surface (rest.php): GET routes read, token POST routes write.

    Mirrors pair_loop.py's rest()/rows() (pair_loop.py:174-190) — POST routes answer
    {"affected": n, "rowid": "<id>"} and GET routes answer {"rows": [...]} (boot/rest.php:111-114).
    Every failure is raised as GovError so a run that cannot record never reports success.
    """

    def __init__(self, base=CONG, key=None, timeout=20):
        self.base, self.key, self.timeout = base.rstrip("/"), key, timeout

    def rest(self, route, obj=None, method=None):
        url = self.base + "/rest.php?route=" + route
        if obj is not None and (method or "POST") == "GET":
            url += "&" + "&".join("%s=%s" % (k, urllib.request.quote(str(v))) for k, v in obj.items())
            obj = None
        data = json.dumps(obj).encode() if obj is not None else None
        req = urllib.request.Request(
            url, data=data, method=method or ("POST" if data else "GET"),
            headers={"Content-Type": "application/json", "X-Api-Key": self.key or ""})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise GovError("route %s returned HTTP %s: %s"
                           % (route, e.code, (e.read() or b"")[:200].decode("utf-8", "replace")))
        except Exception as e:  # noqa: BLE001
            raise GovError("congruency REST at %s unreachable (%r) — is the server up?"
                           % (self.base, e))
        if isinstance(out, dict) and "error" in out:
            raise GovError("route %s failed: %s" % (route, out["error"]))
        return out

    def rows(self, route, params=None):
        return self.rest(route, params or {}, method="GET").get("rows", [])

    def ticket_row(self, tid):
        """One ticket's row (title, body, kind, status) over the public read surface — the same
        ?api=tickets&id=N read pair_loop.py:990-992 does. Returns {} when there is no such ticket.

        A 404 is an ANSWER, not a failure: the server replied, and what it said is "no such ticket".
        That must surface as the precondition failure it is (Fault -> exit 2, "no ticket #N"), not as
        "the REST surface is unreachable" (GovError -> exit 4), which would be a false report about a
        server that is plainly up. Only a real transport failure is a GovError.
        """
        url = self.base + "/rest.php?api=tickets&id=%d" % int(tid)
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as r:
                out = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
            raise GovError("reading ticket #%s returned HTTP %s: %s"
                           % (tid, e.code, (e.read() or b"")[:200].decode("utf-8", "replace")))
        except Exception as e:  # noqa: BLE001
            raise GovError("congruency REST at %s unreachable (%r) — is the server up?" % (self.base, e))
        return out.get("row") or {}


# ── the mark ──────────────────────────────────────────────────────────────────────────────────────
def mark_digest(mark):
    """A short stable fingerprint of a mark's frontier — what the run prints and journals, so two
    marks can be compared at a glance without reading the whole JSON."""
    payload = json.dumps({"snapshots": sorted(mark.get("snapshots") or []),
                          "in_scope": mark.get("in_scope")}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def parse_mark(ref):
    """A mark work row's `ref` back into a dict, or None when it is not a mark this tool wrote."""
    try:
        m = json.loads(ref)
    except (TypeError, ValueError):
        return None
    return m if isinstance(m, dict) and m.get("v") == MARK_V else None


def latest_mark(gov, tid):
    """The LAST mark on a ticket's manifest, or None. Last = highest work UID: the UID is mechanical
    and never reissued (0029:87), so the highest is the most recently minted."""
    best = None
    for row in gov.rows("ticket.manifest", {"ticket_id": int(tid)}):
        if row.get("kind") != MARK_KIND:
            continue
        m = parse_mark(row.get("ref") or "")
        if m is None:
            continue
        if best is None or int(row.get("uid") or 0) > best[0]:
            best = (int(row.get("uid") or 0), m)
    return best[1] if best else None


def predecessor_from_body(body):
    """The `index-watch-predecessor: <id>` line a spawning run wrote into this ticket's body, or
    None. This is how a fresh successor finds the ticket whose manifest holds its starting mark."""
    m = re.search(r"^\s*%s\s*(\d+)\s*$" % re.escape(BODY_PRED), body or "", re.M)
    return int(m.group(1)) if m else None


def resolve_mark(gov, tid, body, predecessor=None):
    """(mark, source) — the high-water-mark this run starts from, and where it came from.

    Order, and why: this ticket's OWN manifest first (if it has run before, that mark is the later
    one and re-runs must stay monotone), then the PREDECESSOR ticket's manifest (the steady-state
    path the ticket specifies: a fresh successor carries no mark of its own and reads the one its
    predecessor recorded), then GENESIS (nothing has ever indexed — the whole scope is new).
    """
    own = latest_mark(gov, tid)
    if own is not None:
        return own, "this ticket's own manifest (#%d has run before)" % tid
    pid = predecessor if predecessor is not None else predecessor_from_body(body)
    if pid is not None:
        prev = latest_mark(gov, pid)
        if prev is not None:
            return prev, "the predecessor ticket #%d's manifest" % pid
        return None, ("the predecessor ticket #%d's manifest carries no mark — GENESIS" % pid)
    return None, "no predecessor and no mark on this ticket — GENESIS (the whole scope is new)"


def build_mark(tid, snapshots, in_scope, settled_n, model, store, omni_db, repo=""):
    """The frontier this run saw, as the JSON recorded on the manifest.

    `repo` is part of it because the frontier is only meaningful WITH the scope it was measured over:
    a --repo-scoped run records the frontier of that repo (in_scope=1), and a reader of the manifest
    must be able to tell that from a whole-corpus frontier of the same shape. A scope mismatch
    between a mark and the run that reads it is harmless — the mark never filters the delta (see THE
    MARK) — but it must not be illegible.
    """
    return {"v": MARK_V, "ticket": int(tid), "repo": repo or None, "snapshots": sorted(snapshots),
            "in_scope": int(in_scope), "settled": int(settled_n), "model": model, "store": store,
            "omni_db": omni_db, "ts": int(time.time())}


# ── the corpus: read-only reads of the omni-git index ─────────────────────────────────────────────
def snapshots_in_scope(ocon, ext, repo):
    """The distinct snapshot LABELS the in-scope corpus holds (`occ.ts`).

    A label, not a timestamp: the live index holds 'test' and 'gitlab' beside 20260701T122754Z-style
    stamps, so these are collected as a SET and diffed as a set — never range-compared. See THE MARK.
    """
    sql, args = "SELECT DISTINCT ts FROM occ WHERE ext = ?", [ext]
    if repo:
        sql += " AND repo = ?"
        args.append(repo)
    return sorted(str(r[0]) for r in ocon.execute(sql, args) if r[0] is not None)


def coverage_gaps(ocon, shas, ext):
    """[(sha, has_blob_row, n_occ_rows)] for every sha WITHOUT omni-git occ/blob coverage.

    The ticket's "confirm omni-git occ/blob coverage": an indexed blob must have a `blob` row (it is
    a distinct known blob) AND at least one `occ` row (it is known to appear somewhere). Confirmed,
    never repaired — omni_index.py owns that database and this tool never writes to it.
    """
    gaps = []
    for sha in shas:
        has_blob = ocon.execute("SELECT 1 FROM blob WHERE sha = ? LIMIT 1", (sha,)).fetchone() is not None
        n_occ = ocon.execute("SELECT COUNT(*) FROM occ WHERE sha = ? AND ext = ?", (sha, ext)).fetchone()[0]
        if not has_blob or not n_occ:
            gaps.append((sha, has_blob, n_occ))
    return gaps


# ── the successor: the ticket that keeps the watch alive ──────────────────────────────────────────
SUCCESSOR_TITLE = "Index-watch: fingerprint the next code delta (successor of #%d)"

SUCCESSOR_BODY = """Run the index-watch. This ticket was SPAWNED by index-watch ticket #%(pred)d and is primed
for the NEXT delta of new/changed code.

    python3 checkouts/current/congruency/tools/index_watch.py --ticket %(self)s

On run it will: read the high-water-mark below from #%(pred)d's manifest, compute the new/changed
blobs as an omni-git sha delta, AST-chunk+embed each into the vector store (#189) and confirm its
omni-git occ/blob coverage, work.record every indexed blob onto this ticket's permanent manifest,
ticket.progress the count, advance the mark, and SPAWN its own successor. Idempotent on blob sha: a
run with no new code is a clean no-op that still spawns the next watch.

Predecessor's run: %(summary)s

%(pred_line)s %(pred)d
%(mark_line)s %(mark)s
"""


def successor_body(tid, sid, mark, summary):
    """The successor's body — human instructions plus the two machine-readable lines the next run
    parses back out (predecessor_from_body / the mark it carries)."""
    return SUCCESSOR_BODY % {"pred": int(tid), "self": (str(sid) if sid else "<this ticket's id>"),
                             "summary": summary, "pred_line": BODY_PRED, "mark_line": BODY_MARK,
                             "mark": json.dumps(mark, sort_keys=True)}


def spawn_successor(gov, tid, kind, mark, component, summary):
    """ticket.create + ticket.kind + a 'spawned' edge — the next watch, carrying the new mark.

    The body is written twice on purpose: ticket.create mints the id, and the body must name that
    id in its own run command, which cannot be known before the row exists. `tickets.body` is
    IMMUTABLE (tg_tickets_immutable_identity, 0029:111-117 — body is in the identity tuple), so the
    id is NOT patched in afterwards; the created body says "--ticket <this ticket's id>" and the two
    machine-readable lines (which is all the next run parses) are exact from the start.
    """
    body = successor_body(tid, None, mark, summary)
    out = gov.rest("ticket.create", {"component": component, "title": SUCCESSOR_TITLE % int(tid),
                                     "severity": "normal", "body": body, "patch": ""})
    try:
        sid = int(out.get("rowid") or 0)
    except (TypeError, ValueError):
        sid = 0
    if not sid:
        raise GovError("ticket.create returned no rowid (%r) — the successor was not filed" % out)
    gov.rest("ticket.kind", {"id": sid, "kind": kind})
    gov.rest("edge.record", {"parent_id": int(tid), "child_id": sid, "kind": "spawned"})
    return sid


# ── the watch ─────────────────────────────────────────────────────────────────────────────────────
class Watch:
    """One run of the index-watch, against one corpus, one store and one governed surface.

    Every collaborator is injected (gov, the corpus paths, the chunker, the embed function), which
    is what lets --selftest drive the identical code path against a throwaway corpus, a recording
    stand-in for the governed surface and a local embedder — no live db, no network.
    """

    def __init__(self, cs, gov, omni_db, omni_git, store, chunker, embed_fn, model,
                 prefix, max_chars, ext=".py", repo="", component="congruency"):
        self.cs, self.gov = cs, gov
        self.omni_db, self.omni_git, self.store = omni_db, omni_git, store
        self.chunker, self.embed_fn, self.model = chunker, embed_fn, model
        self.prefix, self.max_chars = prefix, max_chars
        self.ext, self.repo, self.component = ext, repo, component

    # ── steps 4-5: the delta, and indexing it ────────────────────────────────
    def delta(self, ocon, limit=0):
        """(candidates, todo, capped) — the FULL in-scope corpus, the blobs the store has never
        settled, and the slice of those this run will actually index.

        Both halves come from #189: select_blobs() is its scope (occ.ext='.py' AND blob.is_text=1),
        settled() is its ledger. The delta is a set difference on the blob SHA, so it cannot miss a
        changed file (a change is a new sha) and cannot re-do an unchanged one.

        `limit` caps `capped`, NEVER `candidates`: the mark records the corpus FRONTIER, so it must
        be measured over the whole scope however few blobs one run chooses to index — a mark that
        counted only the capped slice would report a 4989-blob corpus as a 3-blob one and hand that
        lie to the successor. (#189's own --limit caps the in-scope query itself, which is right for
        a one-shot indexer and wrong for a watch that records a frontier.) Capping is SAFE precisely
        because the mark never filters the delta: whatever the cap leaves behind is still unsettled,
        so the next run recomputes it into its own delta and picks it up. It is never silent — the
        run reports what the cap deferred.
        """
        candidates = self.cs.select_blobs(ocon, self.repo, 0)
        scon = self.cs.ro_connect(self.store) if os.path.isfile(self.store) else None
        try:
            done = self.cs.settled(scon, self.model)
        finally:
            if scon is not None:
                scon.close()
        todo = [(s, sz) for s, sz in candidates if s not in done]
        return candidates, todo, (todo[:limit] if limit else todo)

    def index_blob(self, con, sha, size):
        """Chunk + embed + store ONE blob, through #189's own functions. Returns its report dict."""
        text = self.cs.blob_text(self.omni_git, sha)
        if text is None:
            self.cs.store_blob(con, sha, self.model, self.ext, size, [], "unreadable", self.prefix, 0)
            return {"sha": sha, "status": "unreadable", "chunks": 0, "embedded": 0}
        chunks, status = self.cs.chunk_text(self.chunker, text)
        if status == "unparseable":
            self.cs.store_blob(con, sha, self.model, self.ext, size, [], status, self.prefix, 0)
            return {"sha": sha, "status": "unparseable", "chunks": 0, "embedded": 0}

        dim = 0
        if chunks:
            payload, meta = [], []
            for c in chunks:
                body = c["text"][:self.max_chars]
                payload.append(self.prefix + body)
                meta.append((len(body), 1 if len(c["text"]) > self.max_chars else 0))
            vecs = self.embed_fn(payload)
            for c, v, (ec, tr) in zip(chunks, vecs, meta):
                c["vector"], c["embed_chars"], c["truncated"] = v, ec, tr
            dim = len(vecs[0])
        self.cs.store_blob(con, sha, self.model, self.ext, size, chunks, status, self.prefix, dim)
        return {"sha": sha, "status": status, "chunks": len(chunks),
                "embedded": len(chunks) if chunks else 0, "dim": dim}

    # ── the run ──────────────────────────────────────────────────────────────
    def register(self, tid):
        """Step 2: the runner is a NORMAL registered agent, and every write below is attributed to
        it. Registered but never ticket.assign'd — see THE AGENT in the module docstring."""
        aid = AGENT % int(tid)
        self.gov.rest("agent.register", {
            "agent_id": aid, "parent": "index_watch",
            "tools": json.dumps(["ticket.manifest", "work.record", "ticket.progress", "ticket.create",
                                 "ticket.kind", "edge.record", "code_sim_indexer"]),
            "prompt": "You are %s, the index-watch runner of ticket #%d. Your one duty: fingerprint "
                      "the delta of new/changed code — read the high-water-mark from the "
                      "predecessor's manifest, compute the new blobs as an omni-git sha delta, "
                      "AST-chunk+embed each into the vector store (#189), confirm its omni-git "
                      "occ/blob coverage, record every indexed blob on this ticket's permanent "
                      "manifest, advance the mark, and spawn the next index-watch ticket carrying "
                      "it. You index and record; you never author or judge work product, and you "
                      "never erase." % (aid, int(tid))})
        return aid

    def brake(self, tid):
        """Step 1: an active (unreleased) stop ticket aimed at this ticket OR ANY ANCESTOR halts the
        run before anything acts — nothing is registered, indexed, recorded or spawned.

        ticket.stops walks 'spawned' edges up and excludes stops released by a 'starts' edge
        (migrations/0030_pair_loop_routes.sql:21-26). It is checked FIRST, exactly as pair_loop.py's
        `# ── brake ──` block does (pair_loop.py:1001-1006). This matters more for a watch than for a
        one-shot: a watch SPAWNS, so a stop that did not halt it before the spawn would be outrun by
        the very successor it was aimed at.
        """
        stops = self.gov.rows("ticket.stops", {"ticket_id": int(tid)})
        n = int(stops[0].get("active_stops", 0)) if stops else 0
        if n > 0:
            raise Halted("%d active stop ticket(s) aim at #%s or an ancestor — the ticket authorizes "
                         "nothing; nothing was registered, indexed, recorded or spawned" % (n, tid))
        return n

    def run(self, tid, limit=0, spawn=True, successor_kind="", predecessor=None, verbose=True):
        """Steps 1-8 of the module docstring, in that order. Returns the run report."""
        def say(msg):
            if verbose:
                print(msg)

        # step 1: the BRAKE — before anything acts
        self.brake(tid)

        row = self.gov.ticket_row(tid)
        if not row:
            raise Fault("no ticket #%s on the congruency surface — nothing to run the watch for" % tid)
        body, own_kind = row.get("body") or "", row.get("kind") or ""

        # step 2: register the runner — every write below is attributed to it
        self.register(tid)

        # step 3: the mark
        mark, source = resolve_mark(self.gov, tid, body, predecessor)
        say("  mark   : %s" % (("%s (%d snapshot(s), %d blob(s) in scope at that run)"
                                % (mark_digest(mark), len(mark.get("snapshots") or []),
                                   mark.get("in_scope") or 0)) if mark else "GENESIS — none"))
        say("  from   : %s" % source)

        ocon = self.cs.ro_connect(self.omni_db)
        try:
            # step 4: the delta
            snaps = snapshots_in_scope(ocon, self.ext, self.repo)
            new_snaps = sorted(set(snaps) - set(mark.get("snapshots") or [])) if mark else snaps
            candidates, todo, capped = self.delta(ocon, limit)
            deferred = len(todo) - len(capped)
            say("  corpus : %d snapshot(s) in scope, %d new since the mark%s"
                % (len(snaps), len(new_snaps),
                   (": " + ", ".join(new_snaps[:6]) + (" ..." if len(new_snaps) > 6 else ""))
                   if new_snaps else ""))
            say("  delta  : %d blob(s) in scope, %d already settled, %d NEW"
                % (len(candidates), len(candidates) - len(todo), len(todo)))
            if deferred:
                say("  limit  : --limit %d — indexing %d of the %d new blob(s); the other %d stay in "
                    "the delta and the NEXT watch picks them up (the mark never filters, so nothing "
                    "is lost)" % (limit, len(capped), len(todo), deferred))

            # step 5: index the delta, confirming omni-git coverage for each
            indexed, n_chunks, n_embed = [], 0, 0
            if capped:
                con = self.cs.open_store(self.store)
                try:
                    for sha, size in capped:
                        rep = self.index_blob(con, sha, size)
                        indexed.append(rep)
                        n_chunks += rep["chunks"]
                        n_embed += rep["embedded"]
                        say("    OK   %s  %2d chunk(s)%s" % (sha[:12], rep["chunks"],
                            "" if rep["status"] == "indexed" else "  (%s)" % rep["status"]))
                    gaps = coverage_gaps(ocon, [r["sha"] for r in indexed], self.ext)
                    if gaps:
                        raise CoverageError(
                            "%d indexed blob(s) lack omni-git occ/blob coverage (e.g. %s: blob row=%s, "
                            "occ rows=%d) — the omni index is incomplete for them; omni_index.py owns "
                            "that db and this tool will not write to it" % (len(gaps), gaps[0][0][:12],
                                                                            gaps[0][1], gaps[0][2]))
                    occs = self.cs.occurrences_of(ocon, [r["sha"] for r in indexed], self.repo)
                    self.cs.store_occurrences(con, occs)
                    con.commit()
                finally:
                    con.close()
                say("  coverage: every indexed blob has omni-git occ+blob rows; %d {repo, path} "
                    "occurrence(s) recorded" % len(occs))

            new_mark = build_mark(tid, snaps, len(candidates), len(candidates) - len(todo) + len(indexed),
                                  self.model, self.store, self.omni_db, self.repo)
        finally:
            ocon.close()

        # step 6: work.record each indexed blob (permanent manifest), then ticket.progress the count
        already = {r.get("ref") for r in self.gov.rows("ticket.manifest", {"ticket_id": int(tid)})
                   if r.get("kind") == BLOB_KIND}
        recorded = []
        for rep in indexed:
            ref = BLOB_REF % rep["sha"]
            if ref in already:
                continue     # idempotent on sha: this ticket's manifest already names this blob
            self.gov.rest("work.record", {
                "ticket_id": int(tid), "kind": BLOB_KIND, "ref": ref,
                "note": "index-watch: %d chunk(s) embedded (%s, model %s) into %s; status %s"
                        % (rep["chunks"], self.ext, self.model, os.path.basename(self.store),
                           rep["status"])})
            recorded.append(ref)

        summary = ("%d blob(s) indexed -> %d chunk(s) embedded; %d already current; %d in scope; "
                   "%d snapshot(s), %d new since the previous mark%s"
                   % (len(indexed), n_chunks, len(candidates) - len(todo), len(candidates),
                      len(snaps), len(new_snaps),
                      "; %d new blob(s) DEFERRED to the next watch by --limit %d" % (deferred, limit)
                      if deferred else ""))
        self.gov.rest("ticket.progress", {
            "ticket_id": int(tid), "agent_id": AGENT % int(tid),
            "note": "index-watch: %s. Mark advanced to %s (from %s)."
                    % (summary, mark_digest(new_mark), mark_digest(mark) if mark else "GENESIS")})
        say("  record : %d blob(s) work.record'd onto #%d's manifest%s; progress appended"
            % (len(recorded), tid,
               " (%d already recorded)" % (len(indexed) - len(recorded)) if len(indexed) != len(recorded) else ""))

        # step 7: advance the high-water-mark on the same permanent manifest
        self.gov.rest("work.record", {
            "ticket_id": int(tid), "kind": MARK_KIND, "ref": json.dumps(new_mark, sort_keys=True),
            "note": "index-watch high-water-mark %s: %s" % (mark_digest(new_mark), summary)})
        say("  mark   : advanced to %s (%d snapshot(s), %d blob(s) in scope, %d settled)"
            % (mark_digest(new_mark), len(snaps), new_mark["in_scope"], new_mark["settled"]))

        # step 8: SPAWN the successor, carrying the new mark — on EVERY completed run, no-op included
        sid = None
        if spawn:
            kind = successor_kind or own_kind
            if not kind:
                raise Fault("ticket #%s has no kind to inherit and no --successor-kind was given — "
                            "the successor must be kinded (see kind.roster)" % tid)
            known = {k["kind"] for k in self.gov.rows("kind.roster", {})}
            if kind not in known:
                raise Fault("successor kind %r is not in ticket_kinds (kind.roster: %s) — ticket.kind "
                            "requires a known kind" % (kind, ", ".join(sorted(known))))
            sid = spawn_successor(self.gov, tid, kind, new_mark, self.component, summary)
            self.gov.rest("ticket.progress", {
                "ticket_id": int(tid), "agent_id": AGENT % int(tid),
                "note": "index-watch: SPAWNED successor ticket #%d (kind %s, 'spawned' edge #%d -> #%d) "
                        "carrying mark %s — the watch repopulates itself"
                        % (sid, kind, int(tid), sid, mark_digest(new_mark))})
            say("  spawn  : successor ticket #%d (kind %s) filed, 'spawned' edge #%d -> #%d, carrying "
                "mark %s" % (sid, kind, tid, sid, mark_digest(new_mark)))
        else:
            say("  spawn  : SKIPPED (--no-spawn) — no successor filed")

        return {"ticket": int(tid), "mark_from": source, "mark_before": mark, "mark_after": new_mark,
                "in_scope": len(candidates), "already_current": len(candidates) - len(todo),
                "delta": len(todo), "deferred": deferred, "indexed": len(indexed),
                "chunks": n_chunks, "embedded": n_embed, "recorded": len(recorded),
                "snapshots": len(snaps), "new_snapshots": new_snaps, "successor": sid,
                "blobs": indexed, "no_op": not todo}


# ── --status / --dry-run: read-only reports (write nothing, create nothing) ───────────────────────
def store_coverage(cs, store, model):
    """(blobs, chunks, view_rows) settled in the store for `model`. An absent store is empty, never
    created: opened with immutable=1, which creates no -wal/-shm sidecars (see the docstring)."""
    if not os.path.isfile(store):
        return 0, 0, 0
    con = cs.ro_connect(store)
    try:
        b = con.execute("SELECT COUNT(*) FROM blobs WHERE model = ?", (model,)).fetchone()[0]
        c = con.execute("SELECT COUNT(*) FROM chunks WHERE model = ?", (model,)).fetchone()[0]
        v = con.execute("SELECT COUNT(*) FROM code_sim_index WHERE model = ?", (model,)).fetchone()[0]
        return b, c, v
    finally:
        con.close()


def do_status(cs, gov, a):
    """The mark + the delta + store coverage, as one report. Writes nothing, creates nothing."""
    row = gov.ticket_row(a.ticket)
    if not row:
        raise Fault("no ticket #%s on the congruency surface" % a.ticket)
    mark, source = resolve_mark(gov, a.ticket, row.get("body") or "", a.predecessor)
    print("=== index-watch status — ticket #%s ===" % a.ticket)
    print("  title  : %s" % (row.get("title") or "(none)"))
    print("  kind   : %s   status: %s" % (row.get("kind") or "(none)", row.get("status") or "(none)"))
    print("  corpus : %s" % a.omni_db)
    print("  store  : %s%s" % (a.store, "" if os.path.isfile(a.store) else "  (does not exist yet)"))
    print("  model  : %s" % a.model)
    print("\n  MARK   : %s" % (mark_digest(mark) if mark else "GENESIS — none"))
    print("  from   : %s" % source)
    if mark:
        print("  frontier: %d snapshot(s), %d blob(s) in scope, %d settled, over %s, at %s"
              % (len(mark.get("snapshots") or []), mark.get("in_scope") or 0, mark.get("settled") or 0,
                 "repo %r" % mark["repo"] if mark.get("repo") else "the whole corpus",
                 time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mark.get("ts") or 0))))

    if not os.path.isfile(a.omni_db):
        print("\n  (no omni-git index at %s — delta not computed)" % a.omni_db)
        return 0
    ocon = cs.ro_connect(a.omni_db)
    try:
        snaps = snapshots_in_scope(ocon, cs.PY_EXT, a.repo)
        new_snaps = sorted(set(snaps) - set(mark.get("snapshots") or [])) if mark else snaps
        candidates = cs.select_blobs(ocon, a.repo, 0)
        scon = cs.ro_connect(a.store) if os.path.isfile(a.store) else None
        try:
            done = cs.settled(scon, a.model)
        finally:
            if scon is not None:
                scon.close()
        todo = [s for s, _ in candidates if s not in done]
    finally:
        ocon.close()
    b, c, v = store_coverage(cs, a.store, a.model)
    print("\n  DELTA  : %d blob(s) in scope, %d settled in the store, %d NEW to index"
          % (len(candidates), len(candidates) - len(todo), len(todo)))
    print("  snapshots: %d in scope, %d new since the mark%s"
          % (len(snaps), len(new_snaps), (": " + ", ".join(new_snaps[:6])) if new_snaps else ""))
    print("  store    : %d settled blob(s), %d chunk(s), %d searchable code_sim_index row(s)"
          % (b, c, v))
    print("\n=== nothing was written and no file was created ===")
    return 0


def do_dry_run(cs, gov, a):
    """The delta and what a real run WOULD do. Writes nothing, creates nothing, spawns nothing."""
    row = gov.ticket_row(a.ticket)
    if not row:
        raise Fault("no ticket #%s on the congruency surface" % a.ticket)
    mark, source = resolve_mark(gov, a.ticket, row.get("body") or "", a.predecessor)
    # The identical delta the real run computes — same code path, same scope, same cap semantics.
    watch = Watch(cs, gov, a.omni_db, a.omni_git, a.store, None, None, a.model,
                  cs.DOC_PREFIX, cs.MAX_CHARS, repo=a.repo, component=a.component)
    ocon = cs.ro_connect(a.omni_db)
    try:
        snaps = snapshots_in_scope(ocon, cs.PY_EXT, a.repo)
        new_snaps = sorted(set(snaps) - set(mark.get("snapshots") or [])) if mark else snaps
        candidates, todo, capped = watch.delta(ocon, a.limit)
        gaps = coverage_gaps(ocon, [s for s, _ in capped], cs.PY_EXT)
    finally:
        ocon.close()
    print("=== index-watch — DRY-RUN (nothing is written) — ticket #%s ===" % a.ticket)
    print("  mark   : %s" % (mark_digest(mark) if mark else "GENESIS — none"))
    print("  from   : %s" % source)
    print("  corpus : %d snapshot(s) in scope, %d new since the mark" % (len(snaps), len(new_snaps)))
    print("  delta  : %d blob(s) in scope, %d already settled, %d NEW"
          % (len(candidates), len(candidates) - len(todo), len(todo)))
    if len(todo) != len(capped):
        print("  limit  : --limit %d — WOULD index %d of them; the other %d stay in the delta for "
              "the next watch" % (a.limit, len(capped), len(todo) - len(capped)))
    for sha, size in capped[:20]:
        print("    WOULD index  %s  %6d bytes" % (sha[:12], size or 0))
    if len(capped) > 20:
        print("    ... and %d more" % (len(capped) - 20))
    print("  coverage: %s" % ("every blob it would index has omni-git occ+blob rows"
                              if not gaps else "%d blob(s) LACK omni-git coverage" % len(gaps)))
    kind = a.successor_kind or row.get("kind") or "(none — would fail)"
    print("  WOULD work.record %d blob(s) + 1 mark onto #%s's manifest, ticket.progress the count,\n"
          "  and %s"
          % (len(capped), a.ticket,
             "SPAWN a successor ticket (kind %s) carrying the new mark" % kind if not a.no_spawn
             else "spawn NO successor (--no-spawn)"))
    print("\n=== would index %d blob(s); %d already current — nothing written, no file created ==="
          % (len(capped), len(candidates) - len(todo)))
    return 0


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# --selftest: prove the whole watch offline, in a THROWAWAY corpus
# ══════════════════════════════════════════════════════════════════════════════════════════════════
class FakeGov:
    """A recording stand-in for the governed REST surface.

    It answers the same shapes rest.php does (POST -> {"affected","rowid"}, GET -> {"rows":[...]})
    and keeps tickets, works and edges in memory, so --selftest drives the REAL Watch.run() — the
    same ordering, the same routes, the same arguments — against no database and no network. Every
    call is appended to `self.calls`, which is what the checks assert against.
    """

    def __init__(self, tickets=None, kinds=("build", "test", "documentation"), active_stops=0):
        self.tickets = dict(tickets or {})
        self.works, self.edges, self.calls, self.agents = [], [], [], []
        self.kinds = list(kinds)
        self.active_stops = active_stops      # what ticket.stops answers: >0 => the brake HALTS
        self._next = max(list(self.tickets) or [100]) + 1

    def routes(self, name):
        return [obj for route, obj in self.calls if route == name]

    def rest(self, route, obj=None, method=None):
        obj = obj or {}
        self.calls.append((route, dict(obj)))
        if route == "agent.register":
            self.agents.append(obj["agent_id"])
            return {"affected": 1}
        if route == "work.record":
            self.works.append({"uid": len(self.works) + 1, "ticket_id": int(obj["ticket_id"]),
                               "kind": obj.get("kind"), "ref": obj.get("ref"), "note": obj.get("note")})
            return {"affected": 1}
        if route == "ticket.progress":
            return {"affected": 1}
        if route == "ticket.create":
            tid = self._next
            self._next += 1
            self.tickets[tid] = {"id": tid, "title": obj.get("title"), "body": obj.get("body"),
                                 "kind": None, "status": "REQUESTED"}
            return {"affected": 1, "rowid": str(tid)}
        if route == "ticket.kind":
            tid = int(obj["id"])
            if self.tickets[tid]["kind"] is not None:
                raise GovError("ticket.kind is set-once")     # mirrors tg_tickets_immutable_identity
            self.tickets[tid]["kind"] = obj["kind"]
            return {"affected": 1}
        if route == "edge.record":
            self.edges.append((int(obj["parent_id"]), int(obj["child_id"]), obj["kind"]))
            return {"affected": 1}
        if route == "ticket.manifest":
            return {"rows": [w for w in self.works if w["ticket_id"] == int(obj["ticket_id"])]}
        if route == "ticket.stops":
            return {"rows": [{"active_stops": self.active_stops}]}
        if route == "kind.roster":
            return {"rows": [{"kind": k, "pattern": "pair"} for k in self.kinds]}
        raise GovError("FakeGov: unexpected route %s" % route)

    def rows(self, route, params=None):
        return self.rest(route, params or {}, method="GET").get("rows", [])

    def ticket_row(self, tid):
        return dict(self.tickets.get(int(tid)) or {})


def _fake_embed(texts):
    """A deterministic 8-dim unit vector per text — no proxy, no network. Same shape the real
    embedder returns (an L2-normalized float list), so the store rows are structurally identical."""
    out = []
    for t in texts:
        h = hashlib.sha256(t.encode("utf-8")).digest()[:8]
        n = sum((b / 255.0) ** 2 for b in h) ** 0.5 or 1.0
        out.append([(b / 255.0) / n for b in h])
    return out


_ST_MOD_A = '''\
import os


def alpha(a, b=1):
    """the first callable"""
    return a + b


class Widget:
    def __init__(self, x):
        self.x = x

    def render(self):
        return str(self.x)
'''

_ST_MOD_B = '''\
def beta(n):
    return n * 2
'''

_ST_MOD_NEW = '''\
def gamma(items):
    """freshly committed code — the delta must find this"""
    return [i for i in items if i]
'''

_ST_BROKEN = "def oops(:\n"          # not parseable as python: a corpus fact, not a run failure


def _st_corpus(base):
    """A throwaway omni-git corpus: a bare object store holding real blobs, and an index over it.

    Faithful to the real thing in the ways that matter here: `git hash-object -w` computes the SAME
    content address the real corpus is keyed on, and the occ/blob tables carry the real schema
    (code_sim_indexer.py:14-19). Snapshot labels deliberately include a NON-timestamp label
    ('gitlab'), because the live index holds exactly such labels — a mark that range-compared `ts`
    would break on it.
    """
    omni_git = os.path.join(base, "omni.git")
    subprocess.run(["git", "init", "--bare", "--quiet", omni_git], check=True, capture_output=True)

    def add(text):
        r = subprocess.run(["git", "--git-dir", omni_git, "hash-object", "-w", "--stdin"],
                           input=text.encode(), capture_output=True, check=True)
        return r.stdout.decode().strip()

    shas = {k: add(v) for k, v in (("a", _ST_MOD_A), ("b", _ST_MOD_B), ("broken", _ST_BROKEN))}
    omni_db = os.path.join(base, "omni_index.db")
    con = sqlite3.connect(omni_db)
    con.executescript("CREATE TABLE occ (sha TEXT, path TEXT, ext TEXT, size INTEGER, ref TEXT, "
                      "repo TEXT, ts TEXT);"
                      "CREATE TABLE blob (sha TEXT, path TEXT, ext TEXT, size INTEGER, is_text INTEGER);")
    rows = [
        # the SAME blob at two paths in two repos: the fan-out the real corpus has, and the reason
        # the unit of work is the BLOB, not the file. It must be embedded ONCE, with 2 occurrences.
        (shas["a"], "pkg/mod_a.py", ".py", len(_ST_MOD_A), "refs/x", "repo-one", "20260701T000000Z"),
        (shas["a"], "vendor/mod_a.py", ".py", len(_ST_MOD_A), "refs/x", "repo-two", "gitlab"),
        (shas["b"], "pkg/mod_b.py", ".py", len(_ST_MOD_B), "refs/x", "repo-one", "20260701T000000Z"),
        (shas["broken"], "pkg/broken.py", ".py", len(_ST_BROKEN), "refs/x", "repo-one", "20260701T000000Z"),
    ]
    con.executemany("INSERT INTO occ VALUES (?,?,?,?,?,?,?)", rows)
    con.executemany("INSERT INTO blob VALUES (?,?,?,?,1)",
                    [(s, p, e, sz) for s, p, e, sz, _, _, _ in rows])
    con.commit()
    con.close()
    return omni_db, omni_git, shas


def _st_commit_new_code(omni_db, omni_git):
    """"Commit new code": a new blob lands in the object store and a NEW snapshot indexes it —
    exactly what omni_index.py does to the real index when new code appears."""
    r = subprocess.run(["git", "--git-dir", omni_git, "hash-object", "-w", "--stdin"],
                       input=_ST_MOD_NEW.encode(), capture_output=True, check=True)
    sha = r.stdout.decode().strip()
    con = sqlite3.connect(omni_db)
    con.execute("INSERT INTO occ VALUES (?,?,?,?,?,?,?)",
                (sha, "pkg/mod_new.py", ".py", len(_ST_MOD_NEW), "refs/y", "repo-one", "20260715T000000Z"))
    con.execute("INSERT INTO blob VALUES (?,?,?,?,1)", (sha, "pkg/mod_new.py", ".py", len(_ST_MOD_NEW)))
    con.commit()
    con.close()
    return sha


def selftest(cs, codebean):
    """Drive genesis -> re-run -> new-code -> successor-chain through a throwaway corpus and CHECK
    each of the ticket's acceptance claims. One PASS/FAIL line per check; 0 only if all passed."""
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name,
                                ("  — %s" % detail) if detail and not cond else ""))

    base = tempfile.mkdtemp(prefix="index_watch-selftest-")
    try:
        chunker = cs.load_chunker(codebean)
        omni_db, omni_git, shas = _st_corpus(base)
        store = os.path.join(base, "code_sim.db")
        print("== selftest == throwaway corpus %s (no live db, no network, no ticket filed)" % base)

        gov = FakeGov(tickets={197: {"id": 197, "title": "index-watch", "body": "",
                                     "kind": "build", "status": "ACTIVE"}})

        def watch():
            return Watch(cs, gov, omni_db, omni_git, store, chunker, _fake_embed, "nomic-embed",
                         cs.DOC_PREFIX, cs.MAX_CHARS, component="congruency")

        def searchable(sha):
            """The ACCEPTANCE's "searchable": rows of the code_sim_index view (#190/#193's read
            surface) for this blob, each with a {repo, path} and a vector."""
            con = cs.ro_connect(store)
            try:
                return con.execute("SELECT repo, path, line_start, line_end, chunk, vector FROM "
                                   "code_sim_index WHERE blob_sha = ?", (sha,)).fetchall()
            finally:
                con.close()

        # ── genesis: no predecessor, no mark — the whole scope is the delta ──
        print("-- genesis: no mark anywhere; the whole scope is new")
        r1 = watch().run(197, verbose=False)
        ck("genesis reports GENESIS (no mark to read)", r1["mark_before"] is None, str(r1["mark_from"]))
        ck("the delta is the whole in-scope corpus", r1["in_scope"] == 3 and r1["indexed"] == 3,
           "in_scope=%d indexed=%d" % (r1["in_scope"], r1["indexed"]))
        ck("the non-python-parseable blob is settled, not retried or crashed",
           any(b["status"] == "unparseable" for b in r1["blobs"]),
           str([b["status"] for b in r1["blobs"]]))
        ck("chunks were embedded", r1["chunks"] > 0 and r1["embedded"] == r1["chunks"],
           "chunks=%d embedded=%d" % (r1["chunks"], r1["embedded"]))

        # ACCEPTANCE (i): the new blobs are searchable via the store #190/#193 read
        rows_a = searchable(shas["a"])
        ck("ACCEPTANCE: an indexed blob is SEARCHABLE (rows in the code_sim_index view)", len(rows_a) > 0,
           "%d rows" % len(rows_a))
        ck("...every searchable row carries a {repo, path} and a vector",
           all(r[0] and r[1] and r[5] for r in rows_a), str(rows_a[:1]))
        ck("...the row's line-range spans the callable in the original blob",
           all(1 <= r[2] <= r[3] <= len(_ST_MOD_A.splitlines()) for r in rows_a),
           str([(r[2], r[3]) for r in rows_a]))
        ck("...one blob at two {repo, path}s fans out (the same sha, both places)",
           {(r[0], r[1]) for r in rows_a} == {("repo-one", "pkg/mod_a.py"), ("repo-two", "vendor/mod_a.py")},
           str(sorted({(r[0], r[1]) for r in rows_a})))
        con = cs.ro_connect(store)
        n_blob_rows = con.execute("SELECT COUNT(*) FROM blobs WHERE sha = ?", (shas["a"],)).fetchone()[0]
        con.close()
        ck("...but it was EMBEDDED ONCE (the unit of work is the blob, not the file)", n_blob_rows == 1,
           "%d ledger rows" % n_blob_rows)

        # the manifest, the progress, the mark
        works = [w for w in gov.works if w["ticket_id"] == 197]
        blob_works = [w for w in works if w["kind"] == BLOB_KIND]
        mark_works = [w for w in works if w["kind"] == MARK_KIND]
        ck("every indexed blob got a permanent work UID on the manifest", len(blob_works) == 3,
           "%d work rows" % len(blob_works))
        ck("...each work row's ref is the blob's content address",
           {w["ref"] for w in blob_works} == {BLOB_REF % s for s in shas.values()},
           str([w["ref"] for w in blob_works]))
        ck("the count was ticket.progress'd", any("3 blob(s) indexed" in (c[1].get("note") or "")
                                                  for c in gov.calls if c[0] == "ticket.progress"),
           str([c[1].get("note") for c in gov.calls if c[0] == "ticket.progress"][:1]))
        ck("the high-water-mark was advanced onto the manifest", len(mark_works) == 1,
           "%d mark rows" % len(mark_works))
        ck("...and the mark parses back as a v%d mark" % MARK_V,
           parse_mark(mark_works[0]["ref"]) is not None, mark_works[0]["ref"][:80])
        ck("the runner registered as a normal agent (agent.register)", gov.agents == [AGENT % 197],
           str(gov.agents))
        ck("...and every governed write is attributed to it",
           all(c[1].get("agent_id") == AGENT % 197 for c in gov.calls if c[0] == "ticket.progress"),
           str([c[1].get("agent_id") for c in gov.calls if c[0] == "ticket.progress"]))
        ck("...but it is NOT ticket.assign'd (that would hollow the pair-completion backstop)",
           not gov.routes("ticket.assign"), str(gov.routes("ticket.assign")))

        # ACCEPTANCE (ii): a successor exists, primed for the next delta
        sid1 = r1["successor"]
        ck("ACCEPTANCE: a SUCCESSOR ticket was filed", bool(sid1), str(sid1))
        ck("...it is kinded (inheriting the predecessor's kind)", gov.tickets[sid1]["kind"] == "build",
           str(gov.tickets[sid1]["kind"]))
        ck("...a 'spawned' edge points #197 -> the successor", (197, sid1, "spawned") in gov.edges,
           str(gov.edges))
        ck("...its body CARRIES the new mark", BODY_MARK in (gov.tickets[sid1]["body"] or ""))
        ck("...its body names #197 as the predecessor",
           predecessor_from_body(gov.tickets[sid1]["body"]) == 197,
           str(predecessor_from_body(gov.tickets[sid1]["body"])))
        ck("...and it tells its runner exactly how to run (an executable command)",
           "index_watch.py --ticket" in (gov.tickets[sid1]["body"] or ""))

        # ── the successor reads ITS PREDECESSOR'S manifest for the mark ──
        print("-- the chain: the successor starts from the predecessor's mark")
        r2 = watch().run(sid1, verbose=False)
        ck("the successor read the mark from #197's MANIFEST", "predecessor ticket #197" in r2["mark_from"],
           r2["mark_from"])
        ck("...and it is the mark #197 recorded",
           mark_digest(r2["mark_before"]) == mark_digest(r1["mark_after"]),
           "%s vs %s" % (mark_digest(r2["mark_before"]), mark_digest(r1["mark_after"])))

        # ACCEPTANCE (iii): no new code -> a clean no-op that STILL spawns
        ck("ACCEPTANCE: with no new code the run is a NO-OP (0 blobs indexed)",
           r2["indexed"] == 0 and r2["no_op"], "indexed=%d" % r2["indexed"])
        ck("...every blob was already settled (idempotent on sha)", r2["already_current"] == 3,
           "%d" % r2["already_current"])
        ck("...it recorded NO blob works (nothing was indexed to record)", r2["recorded"] == 0)
        ck("...but it STILL spawned the next watch", bool(r2["successor"]), str(r2["successor"]))
        ck("...the no-op run still exits cleanly with a mark of its own",
           any(w["kind"] == MARK_KIND for w in gov.works if w["ticket_id"] == sid1))
        ck("...and no blob was re-embedded (the store is unchanged in blob count)",
           store_coverage(cs, store, "nomic-embed")[0] == 3,
           str(store_coverage(cs, store, "nomic-embed")))

        # ── ACCEPTANCE (iv): commit new code -> run -> the new blob is searchable ──
        print("-- commit new code: the delta finds ONLY it, and it becomes searchable")
        sid2 = r2["successor"]
        new_sha = _st_commit_new_code(omni_db, omni_git)
        r3 = watch().run(sid2, verbose=False)
        ck("ACCEPTANCE: the run indexes exactly the ONE new blob", r3["indexed"] == 1,
           "indexed=%d" % r3["indexed"])
        ck("...and it is the blob that was committed",
           [b["sha"] for b in r3["blobs"]] == [new_sha], str([b["sha"] for b in r3["blobs"]]))
        rows_new = searchable(new_sha)
        ck("ACCEPTANCE: the newly committed code is SEARCHABLE", len(rows_new) == 1,
           "%d rows" % len(rows_new))
        ck("...at the right repo+path, with a vector",
           rows_new and rows_new[0][0] == "repo-one" and rows_new[0][1] == "pkg/mod_new.py"
           and rows_new[0][5], str(rows_new[:1]))
        ck("...and its chunk is the new callable", rows_new and "gamma" in rows_new[0][4],
           str(rows_new[0][4])[:60] if rows_new else "")
        ck("the new snapshot label was noticed against the mark",
           "20260715T000000Z" in r3["new_snapshots"], str(r3["new_snapshots"]))
        ck("...and the non-timestamp label 'gitlab' never broke the frontier (it is a set, not a range)",
           "gitlab" in (r3["mark_after"]["snapshots"] or []), str(r3["mark_after"]["snapshots"]))
        ck("the new blob got its own permanent work UID",
           any(w["ref"] == BLOB_REF % new_sha for w in gov.works if w["ticket_id"] == sid2))
        ck("ACCEPTANCE: and the chain continues — a successor exists for the NEXT delta",
           bool(r3["successor"]), str(r3["successor"]))
        ck("...linked by a 'spawned' edge", (sid2, r3["successor"], "spawned") in gov.edges)

        # ── re-running the SAME ticket is idempotent on sha (no duplicate manifest rows) ──
        print("-- idempotence: re-running the same ticket re-records nothing")
        before = len([w for w in gov.works if w["ticket_id"] == sid2 and w["kind"] == BLOB_KIND])
        r4 = watch().run(sid2, verbose=False)
        after = len([w for w in gov.works if w["ticket_id"] == sid2 and w["kind"] == BLOB_KIND])
        ck("a re-run indexes nothing", r4["indexed"] == 0, "indexed=%d" % r4["indexed"])
        ck("...and mints no duplicate blob work UID", before == after, "%d -> %d" % (before, after))
        ck("...and reads its own later mark, not the predecessor's",
           "own manifest" in r4["mark_from"], r4["mark_from"])
        ck("...and still spawns (the watch never dies)", bool(r4["successor"]))

        # ── --limit caps the WORK, never the frontier the mark records ──
        # The regression this guards: a mark measured over the capped slice reported the corpus as
        # 3 blobs when it held 4989, and handed that lie to the successor.
        print("-- --limit: caps the work, never the mark's frontier")
        store2 = os.path.join(base, "code_sim2.db")
        gov2 = FakeGov(tickets={300: {"id": 300, "title": "watch", "body": "", "kind": "build",
                                      "status": "ACTIVE"}})
        w2 = Watch(cs, gov2, omni_db, omni_git, store2, chunker, _fake_embed, "nomic-embed",
                   cs.DOC_PREFIX, cs.MAX_CHARS, component="congruency")
        rA = w2.run(300, limit=1, verbose=False)
        ck("--limit 1 indexes exactly 1 blob", rA["indexed"] == 1, "indexed=%d" % rA["indexed"])
        ck("...the mark still records the FULL corpus frontier, not the capped slice",
           rA["mark_after"]["in_scope"] == 4, "mark in_scope=%d" % rA["mark_after"]["in_scope"])
        ck("...and the cap is REPORTED, not silent", rA["deferred"] == 3, "deferred=%d" % rA["deferred"])
        rB = w2.run(rA["successor"], verbose=False)
        ck("...the deferred blobs are picked up by the NEXT watch (nothing is lost to a cap)",
           rB["indexed"] == 3 and rB["deferred"] == 0,
           "indexed=%d deferred=%d" % (rB["indexed"], rB["deferred"]))
        ck("...and the corpus is then fully settled", rB["mark_after"]["settled"] == 4,
           "settled=%d" % rB["mark_after"]["settled"])

        # ── the brake: a stop ticket halts the watch BEFORE it acts (and before it spawns) ──
        print("-- the brake: an active stop halts everything, including the spawn")
        stopped = FakeGov(tickets={400: {"id": 400, "title": "watch", "body": "", "kind": "build",
                                         "status": "ACTIVE"}}, active_stops=1)
        w3 = Watch(cs, stopped, omni_db, omni_git, os.path.join(base, "code_sim3.db"), chunker,
                   _fake_embed, "nomic-embed", cs.DOC_PREFIX, cs.MAX_CHARS, component="congruency")
        halted = False
        try:
            w3.run(400, verbose=False)
        except Halted:
            halted = True
        ck("an active stop ticket HALTS the run", halted)
        ck("...nothing was registered", stopped.agents == [], str(stopped.agents))
        ck("...nothing was recorded on the manifest", stopped.works == [], str(stopped.works))
        ck("...and NO successor was spawned (a stop the watch outran would be no stop at all)",
           stopped.edges == [] and not stopped.routes("ticket.create"), str(stopped.edges))
        ck("...and the store was never even created",
           not os.path.exists(os.path.join(base, "code_sim3.db")))

        # ── --no-spawn / coverage guard ──
        print("-- guards")
        gaps = coverage_gaps(sqlite3.connect(omni_db), [new_sha, "0" * 40], ".py")
        ck("coverage confirmation CATCHES a sha the omni index does not cover",
           [g[0] for g in gaps] == ["0" * 40], str(gaps))
        r5 = watch().run(sid2, spawn=False, verbose=False)
        ck("--no-spawn files no successor", r5["successor"] is None)

        bad = [n for n, ok, _ in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s"
              % (len(checks) - len(bad), len(checks), "" if not bad else "; FAILED: " + "; ".join(bad)))
        return 1 if bad else 0
    finally:
        shutil.rmtree(base, ignore_errors=True)
        print("== selftest == throwaway corpus removed (the live db, the proxy and the network were "
              "never touched)")


# ── main ──────────────────────────────────────────────────────────────────────────────────────────
def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)   # progress visible when redirected
    cs = load_indexer()

    ap = argparse.ArgumentParser(
        description="the self-repopulating index-watch: delta-detect new/changed blobs via the "
                    "omni-git sha delta, AST-chunk+embed them into the vector store (#189), record "
                    "them on the ticket's permanent manifest, advance the high-water-mark, and spawn "
                    "the next index-watch ticket carrying it.")
    ap.add_argument("--ticket", type=int, help="the index-watch ticket to run (required unless --selftest)")
    ap.add_argument("--predecessor", type=int, default=None,
                    help="read the starting mark from THIS ticket's manifest (default: the "
                         "'index-watch-predecessor:' line in this ticket's body)")
    ap.add_argument("--successor-kind", default=DEFAULT_SUCCESSOR_KIND,
                    help="kind for the spawned successor (default: inherit this ticket's kind; must "
                         "exist in kind.roster)")
    ap.add_argument("--no-spawn", action="store_true",
                    help="do everything EXCEPT filing the successor (the watch does not repopulate)")
    ap.add_argument("--repo", default="", help="limit the corpus scope to one repo")
    ap.add_argument("--limit", type=int, default=0, help="index at most N new blobs this run")
    ap.add_argument("--store", default=cs.STORE, help="vector store (default: %s)" % cs.STORE)
    ap.add_argument("--omni-db", default=cs.OMNI_DB, help="omni-git index (default: %s)" % cs.OMNI_DB)
    ap.add_argument("--omni-git", default=cs.OMNI_GIT, help="omni-git object store (default: %s)" % cs.OMNI_GIT)
    ap.add_argument("--codebean", default=cs.CODEBEAN, help="codebean_mcp dir (default: %s)" % cs.CODEBEAN)
    ap.add_argument("--litellm", default=cs.LITELLM, help="litellm proxy base url (default: %s)" % cs.LITELLM)
    ap.add_argument("--model", default=cs.MODEL, help="litellm model name (default: %s)" % cs.MODEL)
    ap.add_argument("--component", default="congruency", help="component for the spawned successor")
    ap.add_argument("--dry-run", action="store_true", help="report the delta; write nothing, spawn nothing")
    ap.add_argument("--status", action="store_true", help="report the mark + coverage; write nothing")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the whole watch in a THROWAWAY corpus, then exit (no live db, no "
                         "network, no ticket filed; nothing is written)")
    ap.add_argument("--json", metavar="PATH", default="", help="also write the run report as JSON")
    a = ap.parse_args()

    # --selftest needs only the chunker: no corpus, no store, no proxy, no db, no ticket.
    if a.selftest:
        return selftest(cs, a.codebean)
    if not a.ticket:
        ap.error("--ticket N is required (or --selftest)")

    gov = Gov(key=_secret("CONGRUENCY_API_KEY"))

    # --status / --dry-run: read-only, and never bring the store into being.
    if a.status or a.dry_run:
        if not os.path.isfile(a.omni_db) and a.dry_run:
            raise Fault("no omni-git index at %s — set OMNI_INDEX_DB or pass --omni-db" % a.omni_db)
        return do_status(cs, gov, a) if a.status else do_dry_run(cs, gov, a)

    # ── preconditions for a real run ──────────────────────────────────────────
    if not gov.key:
        raise Fault("no CONGRUENCY_API_KEY (env or .secrets/ats.env) — every write here goes through "
                    "a token route and the writes ARE the work")
    if not os.path.isfile(a.omni_db):
        raise Fault("no omni-git index at %s — set OMNI_INDEX_DB or pass --omni-db" % a.omni_db)
    if not os.path.isdir(a.omni_git):
        raise Fault("no omni-git object store at %s — set OMNI_GIT or pass --omni-git" % a.omni_git)
    ocon = cs.ro_connect(a.omni_db)
    try:
        have = cs.omni_tables(ocon)
        for t in ("occ", "blob"):
            if t not in have:
                raise Fault("table `%s` missing from %s — not an omni-git index" % (t, a.omni_db))
        if a.repo and ocon.execute("SELECT 1 FROM occ WHERE repo = ? LIMIT 1", (a.repo,)).fetchone() is None:
            raise Fault("no repo named %r in the corpus" % a.repo)
    finally:
        ocon.close()

    chunker = cs.load_chunker(a.codebean)

    def embed_fn(texts):
        return cs.embed_all(a.litellm, a.model, cs.LITELLM_KEY, texts, cs.BATCH, cs.TIMEOUT)

    watch = Watch(cs, gov, a.omni_db, a.omni_git, a.store, chunker, embed_fn, a.model,
                  cs.DOC_PREFIX, cs.MAX_CHARS, repo=a.repo, component=a.component)

    print("=== index-watch — ticket #%s — agent %s ===" % (a.ticket, AGENT % a.ticket))
    print("  corpus : %s" % a.omni_db)
    print("  blobs  : %s" % a.omni_git)
    print("  store  : %s%s" % (a.store, "" if os.path.isfile(a.store) else " (will be created)"))
    print("  model  : %s via %s\n" % (a.model, a.litellm))

    rep = watch.run(a.ticket, limit=a.limit, spawn=not a.no_spawn,
                    successor_kind=a.successor_kind, predecessor=a.predecessor)

    print("\n=== indexed %d blob(s) -> %d chunk(s) embedded; %d already current (not re-read, not "
          "re-embedded); %s mark %s -> %s%s ==="
          % (rep["indexed"], rep["chunks"], rep["already_current"],
             "%d new blob(s) DEFERRED to the next watch by --limit %d;" % (rep["deferred"], a.limit)
             if rep["deferred"] else "",
             mark_digest(rep["mark_before"]) if rep["mark_before"] else "GENESIS",
             mark_digest(rep["mark_after"]),
             "; successor #%s primed for the next delta" % rep["successor"] if rep["successor"] else ""))
    if rep["no_op"]:
        print("  No new code — this run was a clean NO-OP. The successor was spawned anyway: that is "
              "what makes the watch self-repopulating.")
    print("  Read the searchable rows back with:  SELECT repo, path, line_start, line_end, chunk, "
          "vector FROM code_sim_index;   (the surface #190/#193 read)")
    print("  Read the record back with:  python3 tools/ticket_status.py %s" % a.ticket)

    if a.json:
        json.dump(rep, open(a.json, "w"), indent=2)
        print("  JSON: %s" % a.json)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Halted as e:
        print("== HALT == %s" % e)
        sys.exit(5)
    except Fault as e:
        print("index_watch: %s" % e)
        sys.exit(2)
    except CoverageError as e:
        print("index_watch: omni-git coverage gap — %s" % e)
        sys.exit(1)
    except GovError as e:
        print("index_watch: governed route failed — %s" % e)
        sys.exit(4)
    except KeyboardInterrupt:
        print("index_watch: interrupted — the store keeps every blob committed so far; nothing was "
              "spawned")
        sys.exit(130)
    except Exception as e:  # noqa: BLE001  -- one line, never a traceback
        cls = e.__class__.__name__
        if cls == "PairError":       # code_sim_indexer's: a blob's chunks vs its line-ranges
            print("index_watch: chunker/line-range disagreement — %s" % e)
            sys.exit(1)
        if cls == "EmbedError":      # code_sim_indexer's: the litellm proxy
            print("index_watch: %s" % e)
            sys.exit(3)
        raise
