#!/usr/bin/env python3
"""forge_refactor_ticketer.py — enumerate EVERY unique module in the forge and file ONE
behavior-preserving rewrite build-ticket per UNIQUE module (ticket #201, per the refactor
standard #200).

WHY A SCRIPT. The forge is 262 bare repos holding 31,421 files at their tips, 25,175 of them source.
Hand-filing a rewrite ticket per module is thousands of tickets, so nothing here is hand-filed: this
instrument walks the forge, DEDUPLICATES to unique modules, and files one ticket per unique module —
batched, idempotent, and self-repopulating. The dedup is the point, and it is not theoretical: the
five `audio_tagger` mirrors carry 18 source files between them that are only 5 distinct modules, so
this tool files 5 tickets there and not 18.

TERMS (defined here because the artifact stands alone):
  forge repo   — a bare git repository under config/forge/remotes/*.git (the forge's mirror store).
                 "Bare" = no working tree; its files are read with git plumbing, never checked out.
  tip          — the commit this tool enumerates a repo at. Normally HEAD; see THE TIP below, which
                 is a documented, evidenced deviation, not a shortcut.
  module       — one source blob at a repo's tip whose extension is in --ext (default: the code
                 languages listed in SOURCE_EXT; .pyc/.json/.md/.txt and other non-source are not
                 modules and are never enumerated).
  module-sha   — THE DEDUP KEY, 16 hex chars. Two files with the same module-sha are the same module
                 and share ONE ticket. See IDENTITY below for how it is computed.
  module key   — `forge-rw:<module-sha>`, carried verbatim in the ticket TITLE in square brackets.
                 The title is one of the three idempotency sources; see IDEMPOTENCY.
  ledger       — this tool's OWN sqlite db (never the CMS state db) recording every module-sha it has
                 filed a ticket for, plus every location that module was found at, plus each chain's
                 high-water-mark. See THE LEDGER.
  chain        — a drain sequence of successor tickets, named by --subset (or "all"). #196's
                 self-repopulating pattern; see BATCHED + SELF-REPOPULATING.
  #std         — ticket #200, "the FORGE-wide refactor standard". Every rewrite ticket this tool
                 files quotes #200's four requirements and hangs off #200 by a `spawned` edge.

THE TIP — HEAD, WITH AN EVIDENCED FALLBACK. The ticket says "at HEAD", and HEAD is what this tool
asks for first. But HEAD RESOLVES IN ONLY 80 OF THE 262 FORGE REPOS. In 179 of the other 182 the
`HEAD` file says `ref: refs/heads/master` while the only branch the mirror actually carries is
`refs/heads/main` — a dangling symbolic HEAD, so `git rev-parse HEAD` exits 128 and `ls-tree HEAD`
enumerates nothing; the remaining 3 carry no branch at all and are genuinely empty. A tool that took
HEAD literally would silently enumerate 80 repos, report success, and leave 179 repos' modules with
no rewrite ticket — under-enumeration is exactly what "enumerate EVERY unique module" forbids, and it
would be invisible in the output. So tip resolution is, per repo:

    1. HEAD                     — when `git rev-parse --verify HEAD` resolves (80 repos today)
    2. refs/heads/main          — else, when it exists
    3. refs/heads/master        — else, when it exists
    4. the first refs/heads/*   — else, in lexicographic order (deterministic across runs)
    5. nothing                  — a repo carrying NO branch at all is EMPTY: it is reported as
                                  skipped with its reason, never silently dropped

Measured over the live forge: 80 repos resolve at HEAD, 179 more resolve by fallback, 3 carry no ref
at all. The fallback is the difference between 10,776 and 31,421 enumerable files (7,755 vs 16,975
.py). Every ticket records which ref its module was read from, so no ticket claims "HEAD" when the
module came from a fallback ref.

IDENTITY — HOW TWO FILES BECOME ONE TICKET (the ticket's "content sha256 + AST-normalized identity",
reusing codebean #183 rather than inventing a second definition of sameness):

  * a Python blob that PARSES  ->  AST-NORMALIZED identity.
        module-sha = sha256("ast:" + codebean._ast_norm(source))[:16]
    `_ast_norm` is codebean's own normalizer (codebean_mcp/prototype/code_wrapper.py) —
    `ast.dump(ast.parse(ast.unparse(ast.parse(src))))` — so two copies that differ only in
    comments, blank lines, quoting or spacing normalize to the SAME string and share one ticket.
    A docstring is real content and does NOT normalize away: two modules whose docstrings differ are
    genuinely different modules and get their own tickets. This is #194's rule ("grouped by
    AST-normalized function/module (codebean lower_*, #183)"), executed with #183's own function.
  * anything else (non-Python, non-UTF-8, or Python that does NOT parse — the forge holds python-2
    and truncated files) -> CONTENT SHA256 identity.
        module-sha = sha256("raw:" + bytes)[:16]
    Exact byte-copies still share one ticket; near-copies do not, because no AST is definable for
    them. That limit is stated on every ticket it applies to rather than papered over.

  The "ast:"/"raw:" prefixes keep the two namespaces disjoint, so an AST identity can never collide
  with a content identity. 16 hex = 64 bits: over ~20k modules the birthday probability of any
  collision is ~1e-11.

  #193 (the universal resolver) and #194 (the dedup engine) are both still REQUESTED — no resolver
  module exists to import today. This tool therefore reuses what IS built: the omni-git blob index
  and codebean's `_ast_norm`. It does NOT rebuild either, and when #193/#194 ship they can consume
  this tool's ledger, which already stores the cluster (canonical + every duplicate location) in
  #194's shape.

THE OMNI-GIT BLOB INDEX — REUSED, NOT REBUILT. `omni_index.db` (built by jazz-forge's omni_index.py;
resolved exactly as the CMS reader resolves it — OmniExplorer.php:34-36, `getenv('OMNI_INDEX_DB') ?:
$HOME/code/installed/jazz-project/config/forge/omni_index.db`) holds one `occ` row per OCCURRENCE:
(sha, path, ext, size, ref, repo, ts). `occ.sha` is the GIT BLOB SHA1 — the same address
`git ls-tree` prints — so a module's blob sha1 joins straight onto `occ` and yields the other places
that exact blob has appeared, historically. That is how a ticket's source-location list reaches
beyond today's tips into the corpus's past. Because `occ` carries one row per SNAPSHOT, the join is
reduced to the DISTINCT {repo, path} pairs (a file recurring across 40 snapshots is one location, not
forty), each shown with the index's own `ts` for its first row — `ts` is usually a snapshot stamp
(20260703T062230Z) but ~5k rows carry a source label like 'gitlab' instead, so it is labelled
`occ.ts` and never presented as if it were always a date. Measured: ~86% of tip blobs are present in
`occ`; a blob that is absent simply contributes no extra locations (the index is enrichment, and this
tool runs fine with it missing entirely). It is opened `immutable=1` and NEVER written.

BEHAVIORAL EXEMPLARS (#200's "verified, not asserted"). For each module it files, this tool captures:
  * THE CALLABLE SURFACE — every top-level function and class method, lowered with codebean's
    `lower_node` (#183), giving each callable's real name/params/returns. This is the contract the
    rewrite must reproduce, and it is captured for every parseable Python module.
  * IO EXEMPLARS — concrete (input, output) pairs mined with criteria_miner's `mine` (the tool #200
    names), which runs the ORIGINAL as the oracle and records what it returned. The rewrite is
    accepted when it reproduces these pairs.
  criteria_miner mines ONLY obviously-pure functions and enforces that itself: it refuses any
  function whose source so much as mentions a world-touching or non-deterministic name (open/os/
  subprocess/socket/random/time/...), refuses methods and no-arg functions, execs the function alone
  in an isolated namespace (never importing the module), bounds every call with a 0.5s timer,
  discards any exemplar that does not round-trip through JSON, and returns nothing at all unless it
  got >= 2 exemplars. Mining therefore executes ONLY functions the corpus itself proves inert, and
  only for the <= --batch modules this run actually files. `--no-exemplars` skips it entirely; a
  module with nothing minable is filed with its callable surface and says so — it is never dropped.
  criteria_miner's own honest limit is carried onto each ticket: mined exemplars cover the SAMPLED
  inputs, so they are a strong refactor-drift net, not a proof of total equivalence.

THE LEDGER — WHAT IT WRITES. Its own sqlite db, a SIBLING of omni_index.db by default
(`forge_refactor_ledger.db`; --ledger or $FORGE_REFACTOR_LEDGER overrides). Four tables, all
IF NOT EXISTS, nothing ever deleted:
    modules      (module_sha PK, ident_kind, ext, ticket_id, title, canonical repo/path/blob, ...)
                 -- the idempotency ledger the ticket requires: one row per module-sha ever filed
    locations    (module_sha, repo, path, blob_sha, origin)  -- the cluster: every place it lives,
                 origin 'tip' (found by a scan) or 'omni' (joined from the blob index)
    chain_state  (chain PK, hwm_repo, ...)                   -- the HIGH-WATER-MARK per drain chain
    runs         (ts, chain, scanned, filed, hwm)            -- one append-only row per filing run
THE CLUSTER KEEPS COMPLETING. A batch is bounded, so a module's ticket is filed knowing only the
copies scanned up to that point; later runs meet the rest. A --file-tickets run therefore records the
locations of copies of ALREADY-ticketed modules too — it does not re-file them (that is the whole
point), it records where they are. So `locations` converges on every copy in the forge as the drain
proceeds, and `modules.copies` is re-counted from those rows so the two never disagree. This is the
cluster in #194's shape (canonical + every duplicate location), which #193/#194 can consume when they
ship.
The ledger is written ONLY by a --file-tickets run, and each ticket's row is written AFTER that
ticket is filed, so a crash mid-batch cannot record a ticket that does not exist. It is the only db
this tool writes: the CMS state db, omni_index.db and omni.git are opened read-only or not at all.

IDEMPOTENCY — A RE-RUN FILES ZERO DUPLICATES. A module is "already ticketed" if its key appears in
ANY of three sources, and the union is what makes it airtight:
  (1) THE LEDGER (`modules.module_sha`) — this tool's own record, all statuses, forever.
  (2) THE STATE DB (`tickets.title`, EVERY status) via `immutable=1`. This sees tickets whose status
      has since gone CLOSED/DONE, which `ticket.queue` (OPEN/REQUESTED only) cannot. `immutable=1`
      rather than `mode=ro` because the state db is WAL-journalled and `mode=ro` spins up
      `-wal`/`-shm` sidecar files on every open; `immutable=1` creates ZERO files.
  (3) THE LIVE `ticket.queue` ROUTE over HTTP. `immutable=1` deliberately ignores the `-wal`, so a
      row committed but not yet checkpointed is invisible to (2). Every ticket filed here is born
      REQUESTED (ticket.create hardcodes it) and REQUESTED is exactly what ticket.queue returns — so
      (3) covers precisely the window (2) can miss.
  With --file-tickets an unreadable ticket.queue is FATAL: the run refuses to file rather than risk
  duplicates. Sources (2) and (3) also mean a ticket filed by a DIFFERENT machine's run, or a ledger
  that was lost, still suppresses a duplicate.

THE HIGH-WATER-MARK IS A BOOKMARK, NOT THE GUARANTEE — AND THE DIFFERENCE IS TESTABLE. Walking 262
repos every run to re-derive work already done is waste, so each chain records `hwm_repo`: the last
repo it has FULLY drained. The next run resumes at the repo after it. The mark advances ONLY past a
repo whose every module was filed or already ticketed — a run that fills its batch mid-repo leaves
the mark BEFORE that repo, so the repo is finished next run rather than skipped. Correctness never
rests on the bookmark: `--rescan` ignores the high-water-mark and re-walks from the first repo, and a
re-run with --rescan STILL files zero, because the module-sha union above is what suppresses a
duplicate. That is the honest way to prove the idempotency claim — it exercises the ledger, not the
bookmark. (See ACCEPTANCE at the bottom.)

BATCHED + SELF-REPOPULATING, AND THE CHAIN DOES NOT STALL (#196, and #245's fix). Append-only
governance means a ticket cannot reopen, so the work perpetuates by SPAWNING a successor. Successors
are GENERATION-NUMBERED — `[forge-rw:successor:<chain>:g<N>]` — and a run's own generation keeps it
alive:

    a run with nothing open (a human/dispatch starts it) -> files a batch -> spawns successor g1
    the pair executing g1 runs this tool again
      -> it READS THE QUEUE, sees g1 is the highest OPEN successor of this chain, concludes it IS
         g1's own run: it does not count itself, and spawns g2
    g1 settles; later the pair executing g2 runs -> spawns g3 ... until the forge is drained.

A run at generation N declines to spawn ONLY IF an OPEN successor of generation > N already exists.
It ignores its own generation and any stale open predecessor (gen <= N), because a predecessor will
never file anything again — that is precisely the stall a "does ANY open successor exist?" test
causes: the run launched from the successor's own body always sees itself, never spawns, and the
chain dies with everything past the first batch un-ticketed. THE GENERATION IS DERIVED FROM THE
QUEUE, not demanded on the command line: defaulting to 0 while g1 sat OPEN made `1 > 0` fire the
decline branch and killed the chain after its first successor (#245, reproduced end-to-end before it
was fixed there). `--gen N` remains an explicit OVERRIDE so re-running an OLD generation's command
still declines. Successor numbers are MONOTONIC — one past the highest this chain has EVER used (the
db, all statuses, UNION the live queue) — so a settled g1's number is never re-minted.

THE BRAKE. `ticket.stops` is checked FIRST, before anything is enumerated or filed — the same brake
pair_loop.py checks first (pair_loop.py:1001-1006). The route counts active (unreleased) stop tickets
aimed at a ticket OR ANY ANCESTOR through `spawned` edges, and every successor of this chain hangs
off #201 by exactly such an edge — so ONE stop ticket aimed at #201 halts the whole drain chain, and
a stop aimed at a single successor halts that one. An active stop prints HALT and exits 3, filing
nothing.

SAFE BY DEFAULT: run with no flags this tool only REPORTS — it writes to no db and CREATES NO FILE
(verified before/after in isolation: the forge dir, the state dir and the ledger's directory gain
nothing, no `-wal`/`-shm` appears, and no ledger is brought into being by a read). Module source is
read through `git cat-file` into memory and normalized/mined AS TEXT — codebean's `_ast_norm`,
`lower_node` and criteria_miner's `mine` all take source, so not even a temp file is created. It
writes exactly three things, each only when asked: --file-tickets POSTs through the governed rest.php
routes (ticket.create -> ticket.kind -> edge.record) with X-Api-Key from ../.secrets/ats.env (the
same source pair_loop.py reads) and records what it filed in the ledger; --json writes the one path
you name; and it appends to the registry's bug_reports sink if it hits an unexpected exception (the
Variant-A report note-for-claude mandates: filename / function / time-of-occurance /
methods-to-reproduce / possible-cause). Pure-python stdlib + git plumbing, registry-gated (a tool
that cannot see registry.json throws).

Every invocation below is written from the REPO ROOT — the directory that holds registry.json — and
runs as written from there (`tools/forge_refactor_ticketer.py` would NOT: the tool lives under
checkouts/current/congruency, so that shorter form only resolves from the CMS app root):

    python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py
        # report the next batch; writes NOTHING
    python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py --subset audio_tagger
        # only repos whose name contains 'audio_tagger' (also names the drain chain)
    python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py --file-tickets --batch 5
        # file a bounded batch, record the high-water-mark, spawn the successor
    python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py --subset audio_tagger \
            --file-tickets --rescan
        # the idempotency proof: re-walk from repo 1, ignore the bookmark -> files ZERO
    python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py --json /tmp/mods.json
        # dump the enumeration (keys, locations, exemplars, bodies) as JSON

ACCEPTANCE (#201) — a SUBSET of the forge, end to end. #201'S OWN ACCEPTANCE RUN IS ON THE RECORD, so
read it before re-running it: `--subset audio_tagger` filed FIVE rewrite tickets — #259, #260, #262,
#263, #265 — for the 18 source files those five repos carry at their tips. THIRTEEN of the eighteen
collapsed as copies: audio_tagger/tagger.py, for instance, is identical in all five repos and holds
ONE ticket (#260), not five. Successors #261 and #264 were filed, each edged `spawned` from #201.
THAT CHAIN IS NOW DRAINED, which is exactly why re-running it is step B.

  A CAVEAT WORTH READING, because it is the honest shape of a BOUNDED batch: that run used --batch 2,
  so #260 was filed while only the FIRST of the five repos had been scanned — and its body therefore
  says this module is "unique to audio_tagger among the repos scanned so far", because at filing time
  that was true. The other four copies were met by later runs, which correctly did NOT re-file them
  and recorded their locations in the ledger instead (`locations` now holds all five tips for that
  module-sha — see THE CLUSTER KEEPS COMPLETING). A ticket's body is a SNAPSHOT of what was known
  when it was filed; the LEDGER is the live cluster. Run with a --batch large enough to cover a
  subset in one pass (as step A does) and the body carries every copy from the start.

    A. FILE A BATCH — on a chain nobody has drained yet:
           python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py \
               --subset artifact_tree_gen --file-tickets --batch 4
       -> one build ticket per UNIQUE module, each referencing its source repo(s)/path(s), #200, the
          control-config + installable requirements, and its captured IO exemplars; each edged
          `spawned` from #200; then a successor edged `spawned` from #201, primed for the next batch.
          (Run it WITHOUT --file-tickets first to see the same batch and write nothing.)
    B. A RE-RUN FILES ZERO — on the drained chain, with --rescan so what is tested is the LEDGER and
       not the bookmark:
           python3 checkouts/current/congruency/tools/forge_refactor_ticketer.py \
               --subset audio_tagger --file-tickets --batch 20 --rescan
       -> it re-walks all five repos, re-identifies all eighteen files, collapses every one, and
          prints "== nothing new == every unique module enumerated is already ticketed; filed 0,
          spawned 0." ZERO duplicates. (It still RECORDS any copy location it had not seen before —
          see THE CLUSTER KEEPS COMPLETING — which is knowledge, not a duplicate.)

Exit 0 on a clean run (including "nothing new to file", the expected result of a re-run). Exit 2 with
a one-line message (never a traceback) on a bad invocation or an unusable environment. Exit 3 when an
active stop ticket brakes the chain.
"""
import argparse
import ast
import contextlib
import glob
import hashlib
import importlib.util
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
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
# This tool's own path relative to the repo root. Derived, never hardcoded, so the invocation printed
# into a spawned successor ticket keeps running as written even if the tool is moved.
SELF_FROM_ROOT = os.path.relpath(os.path.abspath(__file__), ROOT)
STATE = os.path.join(ROOT, "checkouts", "current", "state")
CONG_DB = os.path.join(STATE, "congruency.sqlite")

HOME = os.path.expanduser("~")

# The omni-git index — resolved exactly as the CMS reader resolves it (OmniExplorer.php:34-36:
# getenv('OMNI_INDEX_DB') ?: $HOME/code/installed/jazz-project/config/forge/omni_index.db), which is
# also what tools/code_sim_indexer.py:156-159 does. Never written.
OMNI_DB = os.environ.get("OMNI_INDEX_DB") or os.path.join(
    HOME, "code/installed/jazz-project/config/forge/omni_index.db")
FORGE_DIR = os.path.dirname(OMNI_DB)
# The forge's bare mirror store: the *.git the ticket names as config/forge/remotes/*.git.
REMOTES = os.environ.get("FORGE_REMOTES") or os.path.join(FORGE_DIR, "remotes")
# This tool's OWN ledger — a sibling of the index it is derived from, the way code_sim.db is.
LEDGER = os.environ.get("FORGE_REFACTOR_LEDGER") or os.path.join(FORGE_DIR, "forge_refactor_ledger.db")
# codebean (#183) — the package dir holding prototype/code_wrapper.py + prototype/criteria_miner.py.
CODEBEAN = os.environ.get("CODEBEAN_MCP") or os.path.join(HOME, "code/installed/jazz-project/codebean_mcp")

# The congruency server carrying the governed routes.
BASE = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")

FACTORY_TICKET = 201        # the ticket that authorizes this factory; parent of every successor
STD_TICKET = 200            # #std — the refactor standard; parent of every rewrite ticket

# A module key is `forge-rw:` + EXACTLY 16 hex chars. A successor key is
# `forge-rw:successor:<chain>:g<N>` — "successor" is not 16 hex chars, so the two patterns are
# disjoint by construction and a chain marker can never be mistaken for a module.
KEY_RE = re.compile(r"\[forge-rw:([0-9a-f]{16})\]")
SUCC_RE = re.compile(r"\[forge-rw:successor:(.+):g(\d+)\]")   # greedy: a chain may contain colons

# What counts as a source module. The forge's resolved tips hold 31,421 files, of which these
# extensions are 25,175 — the CODE among them (.py 16,975, .php 7,197, .js 307, .sh 239, .sql 140,
# .tsx 116, then a long tail). Every count here is measured at the tips THIS tool resolves (i.e. with
# the HEAD fallback above), so they are comparable with each other. Deliberately NOT source: .pyc
# (bytecode, not source), .json/.yml/.toml (data), .md/.txt (prose), .bin/.mp3/.pdf (assets).
# --ext overrides the whole set.
SOURCE_EXT = (".py", ".php", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh", ".bash",
              ".rb", ".pl", ".go", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".lua", ".r",
              ".sql", ".sol")
PY_EXT = (".py",)

MAX_BODY_LOCATIONS = 40     # locations printed per ticket; any excess is COUNTED, never hidden
MAX_BODY_CALLABLES = 40
MAX_BODY_EXEMPLAR_FNS = 8
MAX_BODY_EXEMPLARS = 6
GIT_TIMEOUT = 60


class Fault(Exception):
    """A precondition failure — reported as one line, exit 2."""


# ── Variant-A bug report (note-for-claude: every tool auto-files a timestamped report) ───────────
def bug_report(fn, exc, repro, cause):
    """Filename / function / time-of-occurance / methods-to-reproduce / possible-cause, to the
    registry's bug_reports sink. Best-effort: a failing bug report never masks the real error."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "forge_refactor_ticketer.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:],
                "note": "forge_refactor_ticketer (#%d) — forge rewrite-ticket factory per #%d"
                        % (FACTORY_TICKET, STD_TICKET),
            }) + "\n")
    except Exception:                                     # noqa: BLE001
        pass


def step(msg):
    """Per-step telemetry: one labeled line per step of the run, so a scheduled run's log shows what
    it enumerated, what it skipped and why, and what it filed."""
    print("== step == %s" % msg)


def die(msg):
    print("forge_refactor_ticketer: %s" % msg)
    sys.exit(2)


# ── read-only sqlite (immutable=1: reads committed data, creates NO -wal/-shm sidecars) ──────────
def connect_ro(db_path, what):
    if not os.path.isfile(db_path):
        raise Fault("%s not found at %s" % (what, db_path))
    return sqlite3.connect("file:%s?immutable=1" % db_path, uri=True)


# ── REST (every write goes through the governed surface, as pair_loop.py does) ───────────────────
def api_key():
    """CONGRUENCY_API_KEY from ../.secrets/ats.env relative to the repo root (as pair_loop.py reads
    it), or the environment."""
    path = os.path.join(os.path.dirname(ROOT), ".secrets", "ats.env")
    if os.path.isfile(path):
        for line in open(path):
            if line.strip().startswith("CONGRUENCY_API_KEY="):
                return line.strip().split("=", 1)[1]
    return os.environ.get("CONGRUENCY_API_KEY")


def rest(base, route, obj=None, method=None, key=None, timeout=20):
    """One governed route call. Returns the decoded JSON; raises on transport failure or on a route
    that answered with an {"error": ...} envelope."""
    url = base + "/rest.php?route=" + route
    if obj is not None and (method or "POST") == "GET":
        url += "&" + "&".join("%s=%s" % (k, urllib.request.quote(str(v))) for k, v in obj.items())
        obj = None
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json", "X-Api-Key": key or ""})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode())
    if isinstance(out, dict) and "error" in out:
        raise RuntimeError("route %s refused: %s" % (route, out["error"]))
    return out


# ── codebean (#183): the AST normalizer, the lowering, and criteria_miner's exemplars ────────────
def load_prototype(name, filename):
    """Load one codebean prototype module BY PATH, or raise Fault with a one-line reason.

    By path rather than as a package: codebean_mcp/__init__.py pulls in the FastMCP server (an
    optional dependency this tool does not need) — the same reason code_wrapper.py itself loads
    model.py by path. Two things this loader must get right, both learned from
    tools/code_sim_indexer.py's loader:
      * the module is registered in sys.modules BEFORE exec_module — code_wrapper.py declares a
        @dataclass, and dataclasses resolves a field's type through sys.modules[cls.__module__],
        which is None for an unregistered module;
      * its import-time stdout is captured — code_wrapper.py PRINTS a '[telemetry] unavailable'
        notice when jazz_telemetry is absent, which is not this tool's output.
    """
    src = os.path.join(CODEBEAN, "prototype", filename)
    if not os.path.isfile(src):
        raise Fault("codebean's %s not found at %s — set CODEBEAN_MCP or pass --codebean"
                    % (filename, src))
    spec = importlib.util.spec_from_file_location(name, src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            spec.loader.exec_module(mod)
    except Exception as e:
        raise Fault("codebean's %s at %s failed to load: %r" % (filename, src, e))
    return mod


def load_codebean():
    """(code_wrapper, criteria_miner). code_wrapper gives `_ast_norm` (the AST-normalized identity)
    and `lower_node` (the callable surface); criteria_miner gives `mine` (the IO exemplars). Both
    are checked for the exact names this tool calls, so a codebean that has moved on fails with one
    line here rather than mis-identifying a module."""
    cw = load_prototype("frt_code_wrapper", "code_wrapper.py")
    for attr in ("_ast_norm", "lower_node"):
        if not hasattr(cw, attr):
            raise Fault("codebean's code_wrapper.py defines no %s — wrong codebean version? The "
                        "AST-normalized module identity is defined by that function, so this tool "
                        "refuses to guess at it" % attr)
    cm = load_prototype("frt_criteria_miner", "criteria_miner.py")
    if not hasattr(cm, "mine"):
        raise Fault("codebean's criteria_miner.py defines no mine() — wrong codebean version?")
    return cw, cm


# ── git plumbing (bare repos, read-only: ls-tree + cat-file only) ────────────────────────────────
def git(repo, *args, **kw):
    """(returncode, stdout). `text=False` returns bytes (blob content must not be decoded here)."""
    text = kw.get("text", True)
    try:
        r = subprocess.run(["git", "--git-dir", repo] + list(args), capture_output=True,
                           text=text, timeout=GIT_TIMEOUT)
    except FileNotFoundError:
        raise Fault("git not found on PATH — this tool reads the forge's bare repos with git plumbing")
    except subprocess.TimeoutExpired:
        return 1, ("" if text else b"")
    return r.returncode, r.stdout


def forge_repos(subset):
    """Every bare repo under REMOTES, sorted (the deterministic drain order the high-water-mark
    indexes into), optionally filtered to those whose NAME contains `subset`."""
    if not os.path.isdir(REMOTES):
        raise Fault("forge remotes not found at %s — set FORGE_REMOTES (the ticket names "
                    "config/forge/remotes/*.git)" % REMOTES)
    repos = sorted(glob.glob(os.path.join(REMOTES, "*.git")))
    if not repos:
        raise Fault("no *.git under %s — nothing to enumerate" % REMOTES)
    if subset:
        repos = [r for r in repos if subset in repo_name(r)]
    return repos


def repo_name(path):
    return os.path.basename(path)[:-4] if path.endswith(".git") else os.path.basename(path)


def resolve_tip(repo):
    """(ref, how) — the commit-ish this repo is enumerated at, or (None, reason).

    HEAD first, exactly as the ticket says. The fallback exists because 182 of the forge's 262 repos
    carry `ref: refs/heads/master` in HEAD while their only branch is refs/heads/main, so HEAD does
    not resolve and a literal reading would enumerate nothing there. See THE TIP in the module
    docstring — this is an evidenced deviation, and every ticket records which ref it used."""
    rc, _ = git(repo, "rev-parse", "--verify", "--quiet", "HEAD")
    if rc == 0:
        return "HEAD", "HEAD"
    rc, out = git(repo, "for-each-ref", "--format=%(refname)", "refs/heads/")
    heads = [h for h in (out or "").splitlines() if h.strip()]
    if not heads:
        return None, "no branch at all (empty mirror)"
    for pref in ("refs/heads/main", "refs/heads/master"):
        if pref in heads:
            return pref, "fallback (HEAD dangles)"
    return sorted(heads)[0], "fallback (HEAD dangles)"


def tip_blobs(repo, ref, exts):
    """[(blob_sha, path)] — every source blob at `ref`, in ls-tree order."""
    rc, out = git(repo, "ls-tree", "-r", ref)
    if rc != 0:
        return None
    found = []
    for line in (out or "").splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) < 3 or parts[1] != "blob":
            continue
        if os.path.splitext(path)[1].lower() in exts:
            found.append((parts[2], path))
    return found


def blob_bytes(repo, sha):
    rc, raw = git(repo, "cat-file", "blob", sha, text=False)
    return None if rc != 0 else raw


# ── identity: the module-sha (see IDENTITY in the module docstring) ──────────────────────────────
def module_identity(cw, raw, path):
    """(module_sha, ident_kind, text). AST-normalized for a Python blob that PARSES; content sha256
    for everything else. The 'ast:'/'raw:' prefixes keep the two namespaces disjoint."""
    text = None
    if os.path.splitext(path)[1].lower() in PY_EXT:
        try:
            text = raw.decode("utf-8")
            norm = cw._ast_norm(text)
            return hashlib.sha256(("ast:" + norm).encode("utf-8")).hexdigest()[:16], "ast", text
        except (UnicodeDecodeError, SyntaxError, ValueError, RecursionError):
            pass                                          # python-2 / truncated / not really python
    if text is None:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None
    return hashlib.sha256(b"raw:" + raw).hexdigest()[:16], "sha256", text


def module_key(module_sha):
    return "forge-rw:%s" % module_sha


# ── the omni-git blob index: extra locations for a blob, joined on the git blob sha1 ─────────────
def omni_locations(omni, blob_sha, seen):
    """[(repo, path, ts)] — every OTHER {repo, path, snapshot} this exact blob has appeared at, from
    omni_index.db's `occ`. Enrichment only: no index (or no row) simply means no extra locations."""
    if omni is None:
        return []
    out = []
    try:
        rows = omni.execute(
            "SELECT repo, path, ts FROM occ WHERE sha=? ORDER BY repo, path, ts", (blob_sha,))
    except sqlite3.Error:
        return []
    for repo, path, ts in rows:
        if (repo, path) in seen:
            continue
        seen.add((repo, path))
        out.append((repo or "", path or "", ts or ""))
    return out


# ── behavioral exemplars: codebean lower_node (#183) + criteria_miner IO pairs (#200) ────────────
def capture_behavior(cw, cm, text, mine):
    """{'callables': [...], 'exemplars': [...], 'note': str} for one module's source.

    callables — every top-level function and class method, lowered with codebean's `lower_node`, so
      each carries its REAL name/params/returns: the contract the rewrite must reproduce.
    exemplars — criteria_miner `mine` specs for the pure top-level functions, i.e. concrete
      (input, output) pairs with the ORIGINAL as the oracle. This mirrors criteria_miner's own
      mine_module loop (top-level FunctionDef -> mine(src, node)) but passes the SOURCE TEXT rather
      than a path, so no temp file is ever created.

    Never raises on corpus input: a module that does not parse yields no capture and says why."""
    cap = {"callables": [], "exemplars": [], "note": ""}
    if text is None:
        cap["note"] = ("not UTF-8 text, so no AST could be built: the rewrite's behavior must be "
                       "established by reading the original bytes.")
        return cap
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError) as e:
        cap["note"] = ("this blob is not parseable as python 3 (%s), so no AST surface or IO "
                       "exemplar could be captured: the rewrite's behavior must be established by "
                       "reading the original source." % e.__class__.__name__)
        return cap
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cap["callables"].append(("", _lower(cw, node)))
        elif isinstance(node, ast.ClassDef):
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cap["callables"].append((node.name, _lower(cw, m)))
    if not mine:
        cap["note"] = "IO-exemplar mining was disabled for this run (--no-exemplars)."
        return cap
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):         # mine() refuses async itself; skip early
            continue
        try:
            spec = cm.mine(text, node)
        except BaseException:                             # noqa: BLE001  — mined code may do anything
            continue
        if spec:
            cap["exemplars"].append(spec)
    return cap


def _lower(cw, node):
    """One callable's signature via codebean's `lower_node`, degraded to the bare ast facts if
    codebean refuses it — a callable is never dropped from the surface."""
    try:
        f = cw.lower_node(node)
        return {"name": f.name, "params": f.params, "returns": f.returns or "",
                "is_async": bool(getattr(f, "is_async", False))}
    except Exception:                                     # noqa: BLE001
        return {"name": node.name, "params": ast.unparse(node.args), "returns": "",
                "is_async": isinstance(node, ast.AsyncFunctionDef)}


# ── the ledger (this tool's OWN db; see THE LEDGER in the module docstring) ──────────────────────
LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS modules (
  module_sha  TEXT PRIMARY KEY,
  ident_kind  TEXT,
  ext         TEXT,
  ticket_id   INTEGER,
  title       TEXT,
  repo        TEXT,
  path        TEXT,
  blob_sha    TEXT,
  ref         TEXT,
  size        INTEGER,
  copies      INTEGER,
  filed_ts    REAL
);
-- `modules.copies` is the number of LOCATIONS recorded for that module-sha below (tip copies +
-- historical omni occurrences), i.e. it always equals the count of this module's `locations` rows.
-- A LATER run that meets another copy of an already-ticketed module adds its location here and
-- re-counts, so the cluster keeps completing as the forge drains — see ledger_record_locations().
CREATE TABLE IF NOT EXISTS locations (
  module_sha  TEXT,
  repo        TEXT,
  path        TEXT,
  blob_sha    TEXT,
  origin      TEXT,
  ts          TEXT,
  PRIMARY KEY (module_sha, repo, path, origin)
);
CREATE TABLE IF NOT EXISTS chain_state (
  chain     TEXT PRIMARY KEY,
  hwm_repo  TEXT,
  updated   REAL
);
CREATE TABLE IF NOT EXISTS runs (
  ts       REAL,
  chain    TEXT,
  scanned  INTEGER,
  filed    INTEGER,
  hwm_repo TEXT
);
"""


def ledger_rw():
    """The ledger, opened read-WRITE and created if absent. Called ONLY on a --file-tickets run —
    a report must never bring the ledger into being."""
    d = os.path.dirname(LEDGER)
    if d and not os.path.isdir(d):
        raise Fault("ledger directory %s does not exist — pass --ledger PATH" % d)
    con = sqlite3.connect(LEDGER)
    con.executescript(LEDGER_SCHEMA)
    con.commit()
    return con


def ledger_keys_and_hwm(chain):
    """(keys, hwm_repo) read from the ledger WITHOUT creating it, and without -wal/-shm sidecars.

    An absent ledger is an empty one — a fresh chain, not an error. `immutable=1` on a db that does
    not exist would raise, so the file's existence is checked first."""
    if not os.path.isfile(LEDGER):
        return set(), None
    try:
        con = sqlite3.connect("file:%s?immutable=1" % LEDGER, uri=True)
        keys = set(module_key(r[0]) for r in con.execute("SELECT module_sha FROM modules"))
        row = con.execute("SELECT hwm_repo FROM chain_state WHERE chain=?", (chain,)).fetchone()
        con.close()
        return keys, (row[0] if row else None)
    except sqlite3.Error as e:
        raise Fault("ledger at %s is unreadable (%s) — pass --ledger PATH or move it aside" % (LEDGER, e))


def ledger_record(con, m, tid):
    """Record ONE filed module. Called after its ticket exists, so a crash mid-batch can never leave
    the ledger claiming a ticket that was never created."""
    con.execute(
        "INSERT OR REPLACE INTO modules (module_sha, ident_kind, ext, ticket_id, title, repo, path, "
        "blob_sha, ref, size, copies, filed_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (m["sha"], m["ident_kind"], m["ext"], tid, m["title"], m["repo"], m["path"], m["blob_sha"],
         m["ref"], m["size"], len(m["locations"]), time.time()))
    for loc in m["locations"]:
        con.execute("INSERT OR IGNORE INTO locations (module_sha, repo, path, blob_sha, origin, ts) "
                    "VALUES (?,?,?,?,?,?)",
                    (m["sha"], loc["repo"], loc["path"], loc.get("blob_sha", ""), loc["origin"],
                     loc.get("ts", "")))
    con.commit()


def ledger_record_locations(con, extras):
    """Record copy locations of modules that were ALREADY ticketed (by an earlier run, or earlier in
    this one). Returns how many were NEW.

    Why this exists: a batch is bounded, so a module's ticket is filed knowing only the copies seen
    up to that point — later runs meet the rest. Without this, the cluster would freeze at whatever
    the filing run happened to have scanned, and the ledger's claim to hold every duplicate location
    would be false. `modules.copies` is re-counted from the rows so the two never disagree."""
    n, touched = 0, set()
    for sha, repo, path, blob_sha in extras:
        cur = con.execute("INSERT OR IGNORE INTO locations (module_sha, repo, path, blob_sha, "
                          "origin, ts) VALUES (?,?,?,?,'tip','')", (sha, repo, path, blob_sha))
        n += cur.rowcount
        touched.add(sha)
    for sha in touched:
        con.execute("UPDATE modules SET copies=(SELECT COUNT(*) FROM locations WHERE module_sha=?) "
                    "WHERE module_sha=?", (sha, sha))
    con.commit()
    return n


def ledger_mark(con, chain, hwm, scanned, filed):
    if hwm:
        con.execute("INSERT OR REPLACE INTO chain_state (chain, hwm_repo, updated) VALUES (?,?,?)",
                    (chain, hwm, time.time()))
    con.execute("INSERT INTO runs (ts, chain, scanned, filed, hwm_repo) VALUES (?,?,?,?,?)",
                (time.time(), chain, scanned, filed, hwm or ""))
    con.commit()


# ── idempotency sources (2) and (3): the state db, and the live queue ────────────────────────────
def keys_from_titles(titles):
    found = set()
    for t in titles:
        found.update("forge-rw:%s" % s for s in KEY_RE.findall(t or ""))
    return found


def db_titles(db_path):
    """Every ticket title, EVERY status. None when the state db is not there — a legitimate state
    for a worktree (the db is not tracked in git), and the queue still covers OPEN/REQUESTED."""
    try:
        con = connect_ro(db_path, "state db")
    except Fault:
        return None
    try:
        return [(t or "") for (t,) in con.execute("SELECT title FROM tickets")]
    except sqlite3.Error:
        return None


def queue_rows(base, key):
    """Every OPEN/REQUESTED ticket from the LIVE ticket.queue route. None if unreadable."""
    try:
        return rest(base, "ticket.queue", method="GET", key=key).get("rows", [])
    except Exception as e:                                # noqa: BLE001
        step("ticket.queue unreadable at %s (%s)" % (base, e))
        return None


# ── the brake: ticket.stops, checked FIRST (pair_loop.py:1001-1006) ──────────────────────────────
def active_stops(base, key, tid):
    """Active (unreleased) stop tickets aimed at `tid` or any ancestor through `spawned` edges.
    None when the route cannot be read."""
    try:
        rows = rest(base, "ticket.stops", {"ticket_id": tid}, method="GET", key=key).get("rows", [])
    except Exception:                                     # noqa: BLE001
        return None
    return int(rows[0].get("active_stops", 0)) if rows else 0


def brake(base, key, tid, label):
    """True when the chain is braked (and it says so). Every successor hangs off the factory ticket
    by a `spawned` edge and ticket.stops walks that ancestry, so ONE stop aimed at the factory halts
    the whole chain. An unreadable route is not a brake: it returns False, and a --file-tickets run
    has already died on the unreadable queue before reaching here."""
    n = active_stops(base, key, tid)
    if n is None:
        return False
    if n > 0:
        print("== HALT == %d active stop ticket(s) aim at %s #%d — the ticket authorizes nothing"
              % (n, label, tid))
        return True
    step("brake: no active stops on %s #%d" % (label, tid))
    return False


# ── the successor chain (#196; the generation rules are #245's fix — see the module docstring) ───
def chain_of(subset):
    return subset or "all"


def successor_key(subset, gen):
    return "forge-rw:successor:%s:g%d" % (chain_of(subset), gen)


def max_open_generation(titles, subset):
    """The highest successor GENERATION currently OPEN for this chain, or -1 if none. It both
    DERIVES this run's generation and guards the spawn — see this_generation() and the docstring."""
    hi, chain = -1, chain_of(subset)
    for t in titles:
        m = SUCC_RE.search(t or "")
        if m and m.group(1) == chain:
            hi = max(hi, int(m.group(2)))
    return hi


def max_generation_ever(all_titles, subset):
    """The highest generation this chain has EVER used (db, all statuses, UNION the live queue), or
    -1. Successors are minted one past this, so a settled g1's number is never re-used."""
    hi, chain = -1, chain_of(subset)
    for t in all_titles:
        m = SUCC_RE.search(t or "")
        if m and m.group(1) == chain:
            hi = max(hi, int(m.group(2)))
    return hi


def this_generation(explicit, open_hi):
    """This run's own generation. An explicit --gen wins. Otherwise DERIVED: the highest OPEN
    successor of this chain is the ticket a pair is running this tool from, so that is this run's
    generation; with none open the chain is fresh and this run is 0 (#245)."""
    if explicit is not None:
        return explicit
    return open_hi if open_hi >= 0 else 0


def successor_ticket_id(rows, subset):
    """The ticket id of this chain's highest OPEN successor, so the brake can be aimed at it too."""
    best, chain = None, chain_of(subset)
    hi = -1
    for r in rows or []:
        m = SUCC_RE.search(r.get("title") or "")
        if m and m.group(1) == chain and int(m.group(2)) > hi:
            hi, best = int(m.group(2)), r.get("id")
    return best


# ── the scan: bounded, resumable, deduplicating ──────────────────────────────────────────────────
def scan(cw, omni, repos, start_at, exts, batch, done):
    """Walk repos from `start_at`, building this run's batch of UN-TICKETED unique modules.

    Returns (todo, new_hwm, scanned, skipped, dupes_collapsed, extras). What is left for the
    successor is derived from `new_hwm` by the caller, not counted here — the scan is bounded and so
    has NOT seen the repos past its stopping point.

    The scan is BOUNDED: it stops as soon as `batch` new modules are found, so a run never reads the
    whole forge. The high-water-mark advances ONLY past a repo whose every module was filed or
    already ticketed — a repo the batch cut short is left BEFORE the mark, so it is finished next
    run rather than skipped. `done` is the union of the three idempotency sources and is added to as
    the scan runs, so a module recurring later in the SAME run collapses into the first ticket.

    `extras` is [(module_sha, repo, path, blob_sha)] for every copy of an ALREADY-ticketed module
    met this scan. They are not re-filed (that is the whole point), but they ARE new knowledge about
    where that module lives, so a --file-tickets run records them — see ledger_record_locations()."""
    todo, scanned, skipped, dupes, extras = [], [], [], 0, []
    new_hwm = None
    by_key = {}
    for repo in repos[start_at:]:
        name = repo_name(repo)
        if len(todo) >= batch:
            break
        ref, how = resolve_tip(repo)
        if ref is None:
            skipped.append((name, how))
            new_hwm = name                                # an empty mirror IS fully drained
            continue
        blobs = tip_blobs(repo, ref, exts)
        if blobs is None:
            skipped.append((name, "ls-tree failed at %s" % ref))
            continue                                      # NOT drained: do not advance the mark
        scanned.append((name, ref, how, len(blobs)))
        complete = True
        for blob_sha, path in blobs:
            raw = blob_bytes(repo, blob_sha)
            if raw is None:
                continue
            sha, kind, text = module_identity(cw, raw, path)
            key = module_key(sha)
            if key in done:                               # already ticketed, or already in this batch
                dupes += 1
                if key in by_key:                         # a copy of something THIS run is filing:
                    _add_location(by_key[key], name, path, blob_sha, "tip")   # goes in its body
                else:                                     # a copy of something filed EARLIER:
                    extras.append((sha, name, path, blob_sha))                # goes in the ledger
                continue
            if len(todo) >= batch:
                complete = False
                break
            m = {"sha": sha, "ident_kind": kind, "ext": os.path.splitext(path)[1].lower(),
                 "repo": name, "path": path, "blob_sha": blob_sha, "ref": ref, "ref_how": how,
                 "size": len(raw), "text": text, "locations": []}
            _add_location(m, name, path, blob_sha, "tip")
            for orepo, opath, ots in omni_locations(omni, blob_sha,
                                                    set((l["repo"], l["path"]) for l in m["locations"])):
                m["locations"].append({"repo": orepo, "path": opath, "blob_sha": blob_sha,
                                       "origin": "omni", "ts": ots})
            todo.append(m)
            by_key[key] = m
            done.add(key)
        if complete:
            new_hwm = name
        else:
            break                                         # batch filled mid-repo: mark stays BEFORE it
    return todo, new_hwm, scanned, skipped, dupes, extras


def _add_location(m, repo, path, blob_sha, origin):
    if any(l["repo"] == repo and l["path"] == path for l in m["locations"]):
        return
    m["locations"].append({"repo": repo, "path": path, "blob_sha": blob_sha, "origin": origin,
                           "ts": ""})


# ── the per-module ticket ────────────────────────────────────────────────────────────────────────
def module_title(m):
    return ("Rewrite %s:%s as behavior-preserving, installable, control-config'd Python [%s]"
            % (m["repo"], m["path"], module_key(m["sha"])))


def locations_block(m):
    tip = [l for l in m["locations"] if l["origin"] == "tip"]
    omni = [l for l in m["locations"] if l["origin"] == "omni"]
    out = []
    out.append("CANONICAL SOURCE (the location this ticket is named for):\n"
               "  repo : %s\n  path : %s\n  ref  : %s (%s)\n  blob : %s (git blob sha1)\n"
               "  read it, from anywhere:\n"
               "    git --git-dir=%s/%s.git cat-file blob %s"
               % (m["repo"], m["path"], m["ref"], m["ref_how"], m["blob_sha"],
                  REMOTES, m["repo"], m["blob_sha"]))
    others = [l for l in tip if not (l["repo"] == m["repo"] and l["path"] == m["path"])]
    if others:
        shown = others[:MAX_BODY_LOCATIONS]
        out.append("THE SAME MODULE ALSO LIVES AT THESE FORGE TIPS — %d copy/copies. They SHARE THIS\n"
                   "ticket: this module is rewritten ONCE, and every location below is satisfied by\n"
                   "that one rewrite. Do not file a ticket per copy.\n%s%s"
                   % (len(others),
                      "\n".join("  %s:%s" % (l["repo"], l["path"]) for l in shown),
                      "" if len(others) <= MAX_BODY_LOCATIONS else
                      "\n  ... and %d more (the full list is in the ticketer's ledger `locations`\n"
                      "      table, keyed by module-sha %s)" % (len(others) - MAX_BODY_LOCATIONS, m["sha"])))
    else:
        out.append("THE SAME MODULE ALSO LIVES AT THESE FORGE TIPS: none — this module is unique to\n"
                   "%s among the repos scanned so far." % m["repo"])
    if omni:
        shown = omni[:MAX_BODY_LOCATIONS]
        # One line per DISTINCT (repo, path) the blob occurs at — occ holds one row per snapshot, so
        # a file recurring across snapshots would otherwise repeat identically. `occ.ts` is shown
        # verbatim and labelled: it is USUALLY a snapshot stamp (20260703T062230Z) but ~5k rows carry
        # a source label such as 'gitlab' instead, so it is not presented as if it were always a date.
        out.append("HISTORICAL OCCURRENCES of this exact blob — every DISTINCT {repo, path} the\n"
                   "omni-git index (`occ`, joined on the git blob sha1) records this byte-identical\n"
                   "file at, with the index's own `ts` for the first row of each. Context for the\n"
                   "rewrite, not extra work:\n%s%s"
                   % ("\n".join("  %s:%s   [occ.ts %s]" % (l["repo"], l["path"], l["ts"] or "(none)")
                                for l in shown),
                      "" if len(omni) <= MAX_BODY_LOCATIONS else
                      "\n  ... and %d more" % (len(omni) - MAX_BODY_LOCATIONS)))
    else:
        out.append("HISTORICAL OCCURRENCES (omni-git `occ`): none recorded for this blob — either it\n"
                   "is newer than the index's last snapshot, or the index does not cover its repo.")
    return "\n\n".join(out)


def identity_block(m):
    if m["ident_kind"] == "ast":
        how = ("AST-NORMALIZED — codebean's `_ast_norm` (#183), i.e.\n"
               "             ast.dump(ast.parse(ast.unparse(ast.parse(src)))).\n"
               "             Copies of this module that differ only in comments, blank lines,\n"
               "             quoting or spacing carry the SAME module-sha and are covered by THIS\n"
               "             ticket. A differing docstring is real content, so a module whose\n"
               "             docstring differs is a DIFFERENT module with its own ticket.")
    else:
        how = ("CONTENT SHA256 of the raw bytes. This blob is not parseable python (it is\n"
               "             non-Python source, python-2, or a truncated file), so no AST identity\n"
               "             is definable for it: only BYTE-IDENTICAL copies share this ticket. A\n"
               "             near-copy of this module elsewhere in the forge will get its own\n"
               "             ticket — a known and stated limit of this identity, not an oversight.")
    return ("MODULE KEY : %s\n"
            "             (the ticketer's idempotency marker — it lives in this ticket's TITLE. Do\n"
            "              not edit the title, or the module will be re-filed as a duplicate.)\n"
            "IDENTITY   : %s\n"
            "SIZE       : %d bytes\n"
            "EXTENSION  : %s"
            % (module_key(m["sha"]), how, m["size"], m["ext"] or "(none)"))


def behavior_block(m):
    cap = m["capture"]
    out = []
    if cap["callables"]:
        shown = cap["callables"][:MAX_BODY_CALLABLES]
        lines = []
        for ns, f in shown:
            sig = "%s%s(%s)%s" % ("async " if f["is_async"] else "",
                                  ("%s.%s" % (ns, f["name"])) if ns else f["name"],
                                  f["params"], (" -> %s" % f["returns"]) if f["returns"] else "")
            lines.append("  %s" % sig)
        out.append("THE CALLABLE SURFACE — every callable in the original, lowered with codebean's\n"
                   "`lower_node` (#183). The rewrite must present THIS surface (same names, same\n"
                   "parameters, same defaults) so callers of the original keep working:\n%s%s"
                   % ("\n".join(lines),
                      "" if len(cap["callables"]) <= MAX_BODY_CALLABLES else
                      "\n  ... and %d more callable(s) — read the source above for the full surface"
                      % (len(cap["callables"]) - MAX_BODY_CALLABLES)))
    elif not cap["note"]:
        out.append("THE CALLABLE SURFACE: this module defines no top-level function or method. Its\n"
                   "behavior is whatever its module-level code does — read the source above.")

    if cap["exemplars"]:
        shown = cap["exemplars"][:MAX_BODY_EXEMPLAR_FNS]
        blocks = []
        for spec in shown:
            ex = spec["exemplars"][:MAX_BODY_EXEMPLARS]
            # repr(), not json.dumps(): the rewrite is PYTHON, so an exemplar must read as python.
            # criteria_miner already guarantees every value round-trips through JSON, so each one is
            # a plain int/float/str/bool/None/list/dict whose repr IS a valid python literal — json
            # would render True as `true` and None as `null`, which is not what a pair would type.
            rows = ["      %s(%s) == %r" % (spec["name"], ", ".join(repr(a) for a in args), outv)
                    for args, outv in ex]
            more = ("\n      ... %d more exemplar(s) for this function — re-mine them with\n"
                    "          criteria_miner.mine() on the source above"
                    % (len(spec["exemplars"]) - len(ex))) if len(spec["exemplars"]) > len(ex) else ""
            blocks.append("  %s(%s) — %d exemplar(s) captured:\n%s%s"
                          % (spec["name"], spec["params"], len(spec["exemplars"]),
                             "\n".join(rows), more))
        omitted = ("\n  ... and %d more mined function(s) — re-mine the source above to see them."
                   % (len(cap["exemplars"]) - len(shown))) if len(cap["exemplars"]) > len(shown) else ""
        out.append("CAPTURED BEHAVIORAL EXEMPLARS — real (input, output) pairs mined from THIS module\n"
                   "with criteria_miner (#200's \"verified, not asserted\"), running the ORIGINAL as the\n"
                   "oracle. THE REWRITE MUST REPRODUCE EVERY PAIR BELOW, exactly:\n\n%s%s\n\n"
                   "  HONEST LIMIT (criteria_miner's own): these cover the SAMPLED inputs, probed\n"
                   "  around the function's own branch constants. They are a strong refactor-drift net,\n"
                   "  NOT a proof of total equivalence — so treat them as the FLOOR of this ticket's\n"
                   "  equivalence evidence and add the edge cases they miss (see ACCEPTANCE)."
                   % ("\n\n".join(blocks), omitted))
    else:
        why = cap["note"] or ("no function in this module is minable — criteria_miner mines only\n"
                              "  self-contained pure functions (it refuses anything that mentions a\n"
                              "  world-touching or non-deterministic name, plus methods and no-arg\n"
                              "  functions), and nothing here qualified")
        out.append("CAPTURED BEHAVIORAL EXEMPLARS: none. %s\n"
                   "  This does NOT weaken the ticket's bar — it MOVES the work: you must write the\n"
                   "  equivalence exemplars by hand from the original's behavior before rewriting, and\n"
                   "  they are what settles this ticket." % why)
    return "\n\n".join(out)


def module_body(m):
    return (
        "Rewrite ONE unique forge module as entirely new, behavior-preserving, installable,\n"
        "control-config'd Python, per the FORGE-wide refactor standard #%d (#std).\n"
        "\n"
        "This ticket covers ONE module — the one identified below — and nothing else. It was filed\n"
        "against the module's DEDUPLICATED identity, so if that module was copy-pasted across the\n"
        "forge, every copy is covered by this single ticket.\n"
        "\n"
        "%s\n"
        "\n"
        "%s\n"
        "\n"
        "%s\n"
        "\n"
        "THE STANDARD — #%d's four requirements, which this ticket exists to enforce. All four are\n"
        "the standard's own words; none is optional:\n"
        "  1. BEHAVIOR-PRESERVING, VERIFIED NOT ASSERTED — the deliverable is ENTIRELY NEW source\n"
        "     code (rewritten, not copied). It must reproduce the ORIGINAL's behavior, and the proof\n"
        "     is the exemplars above (captured via codebean lower_* #183 + criteria_miner\n"
        "     IO-exemplars, exactly as #%d specifies).\n"
        "  2. A PYTHON MODULE — regardless of the source language. This module's source is `%s`;\n"
        "     the rewrite is Python either way.\n"
        "  3. INSTALLABLE — a proper package: pyproject.toml, `pip install -e .` works, console\n"
        "     entry points where applicable.\n"
        "  4. CONTROL-CONFIG'D — NO hardcoded paths or params. A JSON/registry config object drives\n"
        "     it (the install.json / registry.json idiom of this repo), and per note-for-claude a\n"
        "     tool that cannot see its config THROWS rather than guessing a default.\n"
        "\n"
        "ACCEPTANCE (#%d's, per rewrite ticket) — this ticket settles when ALL of:\n"
        "  a. the new source reproduces every captured exemplar above, plus the edge cases you add\n"
        "     for what sampling cannot reach (paste the runs as evidence);\n"
        "  b. it presents the callable surface above, so existing callers keep working;\n"
        "  c. `pip install -e .` installs it clean from its own pyproject.toml;\n"
        "  d. it runs off a config object with ZERO hardcoded settings, and throws without one.\n"
        "\n"
        "Kind is `build` (a pair: coder + adversarial tester). This ticket hangs off #%d by a\n"
        "`spawned` edge, so a stop ticket aimed at #%d brakes every rewrite in this programme.\n"
        "\n"
        "Filed mechanically by %s under ticket #%d, from the forge bare repos at\n"
        "%s."
        % (STD_TICKET, identity_block(m), locations_block(m), behavior_block(m), STD_TICKET,
           STD_TICKET, m["ext"] or "(no extension)", STD_TICKET, STD_TICKET, STD_TICKET,
           SELF_FROM_ROOT, FACTORY_TICKET, REMOTES))


def successor_body(chain_repos_left, batch, subset, gen, hwm):
    # The command must be the one that continues exactly this chain, so a subset run's successor
    # carries the same --subset. --gen PINS the run launched from THIS body to generation `gen`, so
    # it does not mistake this very ticket for a successor someone else already filed, and goes on to
    # spawn gen+1. It is belt and braces, NOT the mechanism: a run without the flag derives the same
    # generation from the queue (#245). The path is repo-root-relative on purpose: this ticket is
    # executed from the repo root (dispatch runs tools with cwd=ROOT).
    cmd = "python3 %s --file-tickets --batch %d --gen %d%s" % (
        SELF_FROM_ROOT, batch, gen, "" if not subset else " --subset %s" % subset)
    return (
        "Self-repopulating successor (the #196 pattern: append-only governance means a ticket cannot\n"
        "reopen, so the work perpetuates by spawning its successor).\n"
        "\n"
        "UNIT KEY        : %s\n"
        "CHAIN           : %s\n"
        "GENERATION      : %d\n"
        "HIGH-WATER-MARK : %s\n"
        "\n"
        "%d forge repo(s) past the high-water-mark are still un-enumerated. Run the ticketer again to\n"
        "file the next batch of at most %d unique module(s), resuming from the mark:\n"
        "\n"
        "    %s\n"
        "\n"
        "The `--gen %d` pins the run to THIS ticket's generation, so it will not mistake this very\n"
        "ticket for a successor someone else already filed; it then spawns generation %d, and the\n"
        "chain continues after this ticket settles.\n"
        "\n"
        "DROPPING THE FLAG DOES NOT KILL THE CHAIN (it used to — see #245). With no --gen the ticketer\n"
        "DERIVES its generation from the queue: the highest OPEN successor of this chain is normally\n"
        "this very ticket, so a plain `--file-tickets --batch %d` reaches the same conclusion and\n"
        "spawns the next generation anyway. Keep the flag regardless — it is what makes a run started\n"
        "from a STALE copy of this line (one the chain has already moved past, because a NEWER\n"
        "successor is open) correctly DECLINE, instead of adding a redundant successor.\n"
        "\n"
        "It is IDEMPOTENT: it re-files nothing already ticketed — a module already carrying a rewrite\n"
        "ticket is skipped by its module-sha, whether this chain filed it or another did. Run it with\n"
        "no --file-tickets first to see the next batch without writing anything. A stop ticket aimed\n"
        "at #%d (or at this ticket) is the brake for this chain.\n"
        "\n"
        "Filed mechanically by %s under ticket #%d."
        % (successor_key(subset, gen), chain_of(subset), gen, hwm or "(none — chain is fresh)",
           chain_repos_left, batch, cmd, gen, gen + 1, batch, FACTORY_TICKET, SELF_FROM_ROOT,
           FACTORY_TICKET))


# ── filing ───────────────────────────────────────────────────────────────────────────────────────
def file_ticket(base, key, title, body, kind="build"):
    """ticket.create -> ticket.kind, through the governed routes. Returns the new ticket id."""
    out = rest(base, "ticket.create", {"component": "forge-refactor", "severity": "normal",
                                       "patch": "", "title": title, "body": body}, key=key)
    tid = int(out.get("rowid") or 0)
    if not tid:
        raise RuntimeError("ticket.create returned no rowid for %r" % title)
    rest(base, "ticket.kind", {"id": tid, "kind": kind}, key=key)   # set-once; refused if kinded
    return tid


def file_batch(base, key, todo, repos_left, batch, subset, gen, ever_hi, spawn, chain, new_hwm,
               scanned_n):
    """File this run's batch, record it in the ledger, then keep the chain alive."""
    con = ledger_rw()
    filed = []
    for m in todo:
        try:
            tid = file_ticket(base, key, m["title"], m["body"])
            rest(base, "edge.record", {"parent_id": STD_TICKET, "child_id": tid, "kind": "spawned"},
                 key=key)
            ledger_record(con, m, tid)
        except Exception as e:                            # noqa: BLE001
            step("FAILED to file %s: %s" % (module_key(m["sha"]), e))
            bug_report("file_batch", e, "python3 %s --file-tickets" % SELF_FROM_ROOT, e)
            break
        filed.append((tid, m))
        print("== filed == #%-5s %s" % (tid, m["title"]))
    step("%d rewrite ticket(s) filed, each edged `spawned` from #%d (#std)" % (len(filed), STD_TICKET))

    # The mark is recorded from what was actually scanned, and only when something was filed — a run
    # that filed nothing has proven nothing about the repos it walked.
    if filed:
        ledger_mark(con, chain, new_hwm, scanned_n, len(filed))
        step("ledger: high-water-mark for chain %r is now %r" % (chain, new_hwm or "(unset)"))
    con.close()

    if not filed:
        step("nothing filed — no successor spawned (every ticket.create failed; the chain needs a "
             "re-run once the route works)")
        return filed
    if repos_left <= 0:
        step("every repo in chain %r is enumerated — the chain is drained; no successor spawned" % chain)
        return filed
    if not spawn:
        step("--no-spawn — successor withheld (%d repo(s) still un-enumerated)" % repos_left)
        return filed

    rows = queue_rows(base, key)
    if rows is None:
        # Unreadable queue AFTER filing. Spawn anyway: a duplicate successor is visible and harmless
        # (the next run files nothing new and stops), whereas a missing successor silently ends the
        # chain — the failure this whole generation scheme exists to prevent.
        step("ticket.queue unreadable after filing — spawning generation %d anyway (a stacked "
             "successor is recoverable; a dead chain is not)" % (max(ever_hi, gen) + 1))
    else:
        hi = max_open_generation([r.get("title") or "" for r in rows], subset)
        if hi > gen:
            step("chain %r already has an OPEN successor at generation %d (> this run's generation "
                 "%d) — not stacking another. %d repo(s) stay un-enumerated for IT to file; this run "
                 "did not end the chain" % (chain, hi, gen, repos_left))
            return filed
        ever_hi = max(ever_hi, hi)
        step("chain %r: highest open successor generation is %d, this run is generation %d — "
             "spawning generation %d" % (chain, hi, gen, max(ever_hi, gen) + 1))
    nxt = max(ever_hi, gen) + 1                           # monotonic: never re-mint a used number
    try:
        sid = file_ticket(base, key,
                          "Continue the forge refactor decomposition: %d repo(s) left [%s]"
                          % (repos_left, successor_key(subset, nxt)),
                          successor_body(repos_left, batch, subset, nxt, new_hwm))
        rest(base, "edge.record", {"parent_id": FACTORY_TICKET, "child_id": sid, "kind": "spawned"},
             key=key)
        print("== spawned == #%s successor generation %d (spawned edge from #%d) — %d repo(s) left"
              % (sid, nxt, FACTORY_TICKET, repos_left))
    except Exception as e:                                # noqa: BLE001
        step("successor spawn FAILED: %s" % e)
        bug_report("file_batch", e, "python3 %s --file-tickets" % SELF_FROM_ROOT, e)
    return filed


# ── report ───────────────────────────────────────────────────────────────────────────────────────
def report(todo, scanned, skipped, repos, chain, batch, hwm, start_at, dupes, repos_left):
    print("== forge refactor ticketer ==  chain %r: %d repo(s) in scope, resuming at #%d of them "
          "(high-water-mark: %s)" % (chain, len(repos), start_at + 1, hwm or "none — fresh chain"))
    # Repo names run to 55+ chars in this forge, so every padded column comes FIRST and the
    # unbounded name/path comes LAST — a table that only lines up for short names is worse than none.
    if scanned:
        print("\n-- repos enumerated this run")
        for name, ref, how, n in scanned:
            print("   %4d source file(s)  %-23s %-18s %s" % (n, how, ref, name))
    if skipped:
        print("\n-- repos SKIPPED this run (reported, never silently dropped)")
        for name, why in skipped:
            print("   %-42s %s" % (why, name))
    print("\n-- unique modules this run would file (%d; --batch %d)" % (len(todo), batch))
    for m in todo:
        copies = len([l for l in m["locations"] if l["origin"] == "tip"])
        print("   [%-6s] %s  %-28s %s:%s"
              % (m["ident_kind"], module_key(m["sha"]),
                 "" if copies < 2 else "(+%d copy/copies -> 1 ticket)" % (copies - 1),
                 m["repo"], m["path"]))
    print("\n== totals == scanned %d repo(s) -> %d unique un-ticketed module(s) to file; %d file(s) "
          "collapsed into an existing/earlier ticket by module-sha (the dedup); %d repo(s) left for "
          "the successor" % (len(scanned), len(todo), dupes, repos_left))


def main():
    global LEDGER, REMOTES, CODEBEAN
    ap = argparse.ArgumentParser(
        description="Enumerate every UNIQUE module in the forge's bare repos and file one "
                    "behavior-preserving rewrite build-ticket per unique module, per the refactor "
                    "standard #%d (#201). Reports and writes NOTHING unless --file-tickets."
                    % STD_TICKET)
    ap.add_argument("--file-tickets", action="store_true",
                    help="actually file one build ticket per un-ticketed unique module, through "
                         "rest.php's governed ticket.create/ticket.kind/edge.record routes, and "
                         "record them in the ledger (default: report only, no writes, no files)")
    ap.add_argument("--batch", type=int, default=25, metavar="N",
                    help="file at most N module tickets this run, then spawn a successor for the "
                         "rest (the #196 self-repopulating pattern; default 25)")
    ap.add_argument("--subset", default="", metavar="SPEC",
                    help="only forge repos whose NAME contains SPEC — the acceptance run of #201. It "
                         "also names the drain chain, so a subset drain and a full drain never block "
                         "each other's successors or share a high-water-mark")
    ap.add_argument("--rescan", action="store_true",
                    help="ignore the high-water-mark and re-walk from the first repo in scope. The "
                         "honest idempotency proof: a re-run with --rescan still files ZERO, because "
                         "the module-sha ledger — not the bookmark — is what suppresses duplicates")
    ap.add_argument("--no-exemplars", action="store_true",
                    help="skip criteria_miner IO-exemplar mining (which execs only the pure "
                         "functions criteria_miner itself certifies inert). Tickets are still filed, "
                         "carrying the codebean callable surface and saying exemplars were skipped")
    ap.add_argument("--gen", type=int, default=None, metavar="N",
                    help="OVERRIDE this run's successor GENERATION. By default it is DERIVED from "
                         "the live queue — the highest OPEN successor of this chain (0 if none is "
                         "open, i.e. a fresh chain) — because that successor's ticket is what a pair "
                         "runs this tool from. A run spawns unless an OPEN successor of a HIGHER "
                         "generation already exists, so a successor's own run never mistakes itself "
                         "for its replacement and the chain does not stall after one batch (#245). "
                         "Pass this only to deliberately act as an OLDER generation")
    ap.add_argument("--no-spawn", action="store_true", help="file the batch but spawn no successor")
    ap.add_argument("--ext", default="", metavar="LIST",
                    help="comma-separated source extensions to treat as modules (default: %s)"
                         % ",".join(SOURCE_EXT))
    ap.add_argument("--base", default=BASE, metavar="URL",
                    help="the congruency server carrying the governed routes (default %s)" % BASE)
    ap.add_argument("--db", default=CONG_DB, metavar="PATH",
                    help="state db, read immutable=1 for already-filed titles (default %s)" % CONG_DB)
    ap.add_argument("--ledger", default=LEDGER, metavar="PATH",
                    help="this tool's own module-sha ledger (default %s)" % LEDGER)
    ap.add_argument("--remotes", default=REMOTES, metavar="PATH",
                    help="the forge's bare repo store (default %s)" % REMOTES)
    ap.add_argument("--codebean", default=CODEBEAN, metavar="PATH",
                    help="codebean package dir, for _ast_norm/lower_node/criteria_miner (default %s)"
                         % CODEBEAN)
    ap.add_argument("--json", metavar="PATH", help="also dump this run's enumeration as JSON to PATH")
    a = ap.parse_args()

    LEDGER, REMOTES, CODEBEAN = a.ledger, a.remotes, a.codebean

    if a.batch < 1:
        die("--batch must be 1 or more (got %d)" % a.batch)
    if a.gen is not None and a.gen < 0:
        die("--gen must be 0 or more (got %d)" % a.gen)
    exts = tuple(e if e.startswith(".") else "." + e
                 for e in (x.strip().lower() for x in a.ext.split(",")) if e) or SOURCE_EXT

    key = api_key()
    chain = chain_of(a.subset)

    # ── brake, FIRST — before anything is enumerated or filed (pair_loop.py:1001-1006) ──────────
    rows = queue_rows(a.base, key)
    if rows is None and a.file_tickets:
        die("cannot read the live ticket.queue at %s — refusing to file, to not risk duplicates (is "
            "the server up? try --base URL)" % a.base)
    if rows is not None:
        if brake(a.base, key, FACTORY_TICKET, "this factory"):
            return 3
        sid = successor_ticket_id(rows, a.subset)
        if sid and brake(a.base, key, int(sid), "chain %r's open successor" % chain):
            return 3
    else:
        step("live queue unreachable — reporting only; the brake could not be checked, and nothing "
             "will be written")

    cw, cm = load_codebean()
    step("codebean loaded: _ast_norm + lower_node (#183)%s"
         % ("" if a.no_exemplars else ", criteria_miner.mine (#200 exemplars)"))

    repos = forge_repos(a.subset)
    if not repos:
        die("--subset %r matched no forge repo under %s (it matches a repo NAME substring, e.g. "
            "'audio_tagger')" % (a.subset, REMOTES))

    # ── the three idempotency sources (see IDEMPOTENCY in the module docstring) ─────────────────
    done, hwm = ledger_keys_and_hwm(chain)
    step("%d module-sha(s) already ticketed per the ledger%s" % (len(done), " at " + LEDGER))
    titles = db_titles(a.db)
    if titles is None:
        step("state db not readable at %s — idempotency rests on the ledger + the live queue "
             "(both cover every ticket this factory has filed)" % a.db)
        titles = []
    else:
        from_db = keys_from_titles(titles)
        done |= from_db
        step("%d module key(s) in the state db titles (ALL statuses)" % len(from_db))
    open_hi = max_open_generation([r.get("title") or "" for r in rows or []], a.subset)
    gen = this_generation(a.gen, open_hi)
    ever_hi = max_generation_ever(titles + [r.get("title") or "" for r in rows or []], a.subset)
    if rows is not None:
        live = keys_from_titles([r.get("title") or "" for r in rows])
        done |= live
        step("%d module key(s) in the live queue (OPEN/REQUESTED); chain %r highest open successor "
             "generation = %d, this run is generation %d (%s)"
             % (len(live), chain, open_hi, gen,
                "--gen override" if a.gen is not None else "derived from the queue"))

    # ── resume point ────────────────────────────────────────────────────────────────────────────
    names = [repo_name(r) for r in repos]
    start_at = 0
    if a.rescan:
        step("--rescan: ignoring the high-water-mark %r — re-walking from repo 1. Duplicates are "
             "suppressed by the module-sha union, not by the bookmark" % (hwm or "(none)"))
    elif hwm and hwm in names:
        start_at = names.index(hwm) + 1
    elif hwm:
        step("high-water-mark %r is not among the %d repo(s) in scope (renamed or removed) — "
             "restarting this chain from repo 1; the module-sha union still suppresses duplicates"
             % (hwm, len(repos)))

    try:
        omni = connect_ro(OMNI_DB, "omni-git index")
        step("omni-git index open (read-only, immutable=1): %s" % OMNI_DB)
    except Fault as e:
        omni = None
        step("%s — continuing without historical occurrences (the index is enrichment; tip "
             "locations are unaffected)" % e)

    todo, new_hwm, scanned, skipped, dupes, extras = scan(
        cw, omni, repos, start_at, exts, a.batch, done)
    # A repo is "left" when it is at or past the mark this run ends on. The mark only advances past a
    # fully drained repo, so a repo the batch cut short is counted as left and finished next run.
    end_at = (names.index(new_hwm) + 1) if new_hwm in names else start_at
    repos_left = len(repos) - end_at
    if new_hwm is None:
        new_hwm = hwm if not a.rescan else None

    for m in todo:
        m["capture"] = capture_behavior(cw, cm, m["text"], not a.no_exemplars)
        m["title"] = module_title(m)
        m["body"] = module_body(m)
    step("captured behavior for %d module(s): %d with mined IO exemplars, %d with a callable "
         "surface only" % (len(todo), len([m for m in todo if m["capture"]["exemplars"]]),
                           len([m for m in todo if not m["capture"]["exemplars"]])))

    report(todo, scanned, skipped, repos, chain, a.batch, hwm, start_at, dupes, repos_left)

    if a.json:
        with open(a.json, "w") as fh:
            json.dump([{"key": module_key(m["sha"]), "module_sha": m["sha"],
                        "ident_kind": m["ident_kind"], "repo": m["repo"], "path": m["path"],
                        "ref": m["ref"], "blob_sha": m["blob_sha"], "size": m["size"],
                        "locations": m["locations"], "title": m["title"], "body": m["body"],
                        "callables": m["capture"]["callables"],
                        "exemplars": m["capture"]["exemplars"]} for m in todo], fh, indent=2)
        print("== json == %s" % a.json)

    if not a.file_tickets:
        print("\n== dry == reported only; nothing was written and no file was created. Add "
              "--file-tickets to file the %d rewrite ticket(s) above." % len(todo))
        return 0
    if not key:
        die("no CONGRUENCY_API_KEY (../.secrets/ats.env or the environment) — cannot file")

    # New knowledge about where an ALREADY-ticketed module lives is worth recording even on a run
    # that files nothing: it is what completes the dedup cluster as the forge drains.
    if extras:
        lcon = ledger_rw()
        added = ledger_record_locations(lcon, extras)
        lcon.close()
        step("ledger: %d new copy location(s) of already-ticketed module(s) recorded (%d copy/copies "
             "seen, the rest already known)" % (added, len(extras)))

    if not todo:
        print("\n== nothing new == every unique module enumerated is already ticketed; filed 0, "
              "spawned 0.%s"
              % ("" if repos_left <= 0 else
                 "\n   (%d repo(s) remain past the high-water-mark %r — this run found nothing new "
                 "in\n    the repos it walked. Re-run to continue, or --rescan to re-walk from the "
                 "start.)" % (repos_left, new_hwm or "(none)")))
        return 0

    print()
    file_batch(a.base, key, todo, repos_left, a.batch, a.subset, gen, ever_hi, not a.no_spawn,
               chain, new_hwm, len(scanned))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as f:
        die(str(f))
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("forge_refactor_ticketer: interrupted")
        sys.exit(2)
    except Exception as exc:                              # noqa: BLE001
        bug_report("main", exc, " ".join([sys.executable, os.path.abspath(__file__)] + sys.argv[1:]), exc)
        print("forge_refactor_ticketer: unexpected failure: %s" % exc)
        sys.exit(2)
