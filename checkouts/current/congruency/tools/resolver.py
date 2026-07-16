#!/usr/bin/env python3
"""resolver.py — THE UNIVERSAL RESOLVER (ticket #193): hand it any identifier, get back one
normalized, de-overlapped match collection.

WHAT IT IS FOR. The forge corpus is massively duplicated: the same source file recurs across
snapshots, branches, forks and repos (omni's `occ` holds 110,483 occurrence rows over only 6,754
DISTINCT blobs). So one piece of source has MANY names — a symbol name, a file-name, a path, a git
blob hash, a content sha256, a graph node id — and each of those lives in a DIFFERENT index. This
tool removes the need to know which index answers which question: it DETECTS the identifier's kind,
FANS OUT to every backing index that can answer it, and MERGES the answers into ONE collection of
    {repo, path, line-range, identifier-kind, associated tickets, score}
with no two matches overlapping on the same {repo, path}.

Not everything this corpus holds is source, so the collection has a SECOND kind of match: a registered
forge ARTIFACT — a VM image, a wheel, a seed — which has a path but no repo and no line-range. See AN
ARTIFACT HIT IS A MATCH below for its exact shape and for why it does not borrow the source one.

    python3 tools/resolver.py '_emit_in_subprocess.py'          # by file-name
    python3 tools/resolver.py 000eaf4b49499a7674824c7710da623d9c475bbc     # by git blob hash
    python3 tools/resolver.py <64-hex>                          # by content sha256: source, OR a
                                                                #   registered forge artifact (a VM
                                                                #   image, a wheel, a seed)
    python3 tools/resolver.py '_emit_in_subprocess'             # by name (symbol)
    python3 tools/resolver.py --like '_emit_in_subprocess.py'   # by similarity to that source
    python3 tools/resolver.py 'retry a subprocess call'         # by similarity to free text
    python3 tools/resolver.py '#193'                            # a ticket's recorded works
    python3 tools/resolver.py --acceptance                      # PROVE the ticket's acceptance
    python3 tools/resolver.py --indexes                         # the backing indexes + coverage
    python3 tools/resolver.py --mcp                             # serve as an MCP tool over stdio
    ... [--kind K] [--json] [--limit N] [--min-score F] [--repo NAME] [--no-git-fanout]

────────────────────────────────────────────────────────────────────────────────────────────────
THE LOAD-BEARING IDEA: RESOLUTION PIVOTS ON THE BLOB IDENTITY.

A BLOB SHA is git's content address: the sha IS a hash of the bytes, so two files with the same sha
are byte-identical and one sha can never mean two different contents. Every identifier this tool
accepts is therefore resolved in TWO steps:

    step 1  identifier ──(the index that knows that kind of name)──> a SET OF BLOB SHAS
    step 2  each sha ──(omni-git's occurrence table)──> EVERY {repo, path} that sha appears at,
            each carrying the line-range of the callable(s) inside it

Step 2 is the same for every kind. That is precisely WHY the ticket's acceptance holds: a name, a
file-name, a content sha256, a git blob hash and a similarity query all pivot through the SAME blob
identity, so they cannot disagree about where that blob lives. The collection is not "what matched
your string" — it is "every place the source you named actually is". That is also why a file-name
query returns paths whose basename is NOT the queried name: those are other occurrences of the same
identified blob, which is the answer you wanted from a corpus this duplicated.

THE ONE DEGENERATE CASE, NAMED SO IT IS NOT MISTAKEN FOR A BUG. Pivoting on content means EMPTY
files all share ONE identity: git hashes every zero-byte file to the same blob
(e69de29bb2d1d6434b8b29ae775ad8c2e48c5391), which in this corpus occupies 57 distinct paths. So
resolving the file-name `__init__.py` reaches that blob and reports its other occurrences too —
including `scratchpad.js` and `logs/coordinator.err`. That is not a mis-match: those files ARE
byte-identical, all of them empty. Such a match is rendered with the line-range `(empty)` and the
symbol `(empty file)`, precisely so it reads as what it is. A zero-byte blob is the one identity in
a content-addressed corpus that says nothing about the source, and it is labelled rather than hidden.

────────────────────────────────────────────────────────────────────────────────────────────────
AN ARTIFACT HIT IS A MATCH (ticket #461), AND IT DOES NOT PRETEND TO BE SOURCE.

The blob identity above is how SOURCE is resolved. A forge ARTIFACT is resolved differently and is
the one thing in this collection that is not source: it is content-addressed by sha256 in the forge
ledger's `artifacts` table, it is not an omni blob, and it has no callable inside it to point at. A
586MB VM image has a path; it has no repo, and there is no line 1 of it.

Until #461 that made it a second-class answer: the forge-artifacts probe printed the artifact's path
as a side-note and the summary, counting only blobs, said "no match" — both in the same output. A
resolver that prints the answer and then denies finding it is worse than one that finds nothing,
because it teaches the reader to distrust the summary. So an artifact is a MATCH now, and the shape
was widened rather than faked. An ARTIFACT match is:

    {identifier_kind : the REGISTERED kind — 'forge-vm', 'forge-source', 'xz', ... — when every
                       registration of that sha agrees on one; else the generic 'artifact'. Read from
                       the FORGE ledger only, so it does not change when the state db is absent.
     level           : 'artifact'  (source matches are 'chunk' or 'file')
     path            : the PRIMARY registered location
     locations       : EVERY registered location of that sha, primary first
     sha256          : the content address — the identity the whole match hangs off
     score           : 1.0, exactly as the other probes score an exact content hit
     via             : the probe(s) that reached it
     tickets         : the MINTING ticket(s), from ticket_artifacts (see ASSOCIATED TICKETS)
     artifact        : {registrations, names, versions, kinds, size} — the ledger's own record}

    ABSENT: `repo`, `line_start`, `line_end`, `symbol`, `namespace`, `blob_sha`. Not null, not zero,
    not "" — NOT PRESENT. A VM has no repo and no lines, and every one of those fields already MEANS
    something specific in a source match (a null `line_end` means "named by the index, absent from
    the object store", which the renderer prints as `1-?`). Borrowing one would not be a placeholder,
    it would be a false statement about a VM image. The rule is simply: a field with no value is not
    emitted. READ THE COLLECTION BY BRANCHING ON `level` — never by assuming every match has lines.

    A CONSUMER WRITTEN BEFORE #461 WILL NOT KNOW THAT, and one exists: tools/source_dedup.py (#194)
    reads `m["repo"], m["path"], m["line_start"], m["line_end"], m["blob_sha"]` off every match
    unconditionally (source_dedup.py:454-455). Handed an ARTIFACT's sha256 it now exits 2 with
    "unexpected error: 'repo'"; before #461 it printed "0 unit(s)" for the same query. Both measured,
    both wrong answers to "what source duplicates this VM image?", and the fix belongs in that file
    — this one is scoped to the resolver. Filling those fields with nulls to keep it quiet would be
    worse, not better: source_dedup.py:659-667 renders a null `line_end` as the line-range `1-?`, so
    the engine would report a 586MB VM image as source spanning line 1 to unknown. A loud stop beats
    a quiet fiction. Its SOURCE work is untouched, and that is measured rather than hoped: the
    collection this file returns for a source identifier is byte-identical to the pre-#461 one (see
    WHAT DID NOT CHANGE), and that collection is source_dedup's only input.

    THE FULL PRICE OF THAT STOP, so it is not discovered later as a surprise: source_dedup catches
    every unexpected error and APPENDS a report to `logs/bug_reports.jsonl` under its registry root
    (source_dedup.py's `except Exception` handler, the sink registry.json's `bug_reports` names), so
    it exits 2 with "(a bug report was filed to logs/bug_reports.jsonl)" and that file grows by one
    line per artifact-sha query put through it. THAT WRITE IS source_dedup's, NOT THIS FILE'S: the
    resolver resolves the same sha256 with no write and no file at all (WHAT IT WRITES below states
    this file's own single exception, and it is the identical registry contract, not this one), and
    the log is git-ignored so it enters no commit either way. It is recorded here because a reader
    who runs the crash above will see that sentence and deserves to know which tool wrote the line
    and where, rather than suspecting this one.

WHEN AN ARTIFACT MATCH CAN APPEAR AT ALL — the whole list, so no reader has to guess. Only two probes
read the ledger, and a match appears only if one of them HITS:
  * `forge-artifacts` (the sha256 kind): the identifier IS the artifact's content address. This is
    the case #461 was filed for.
  * `string-index` (the uuid and node kinds): the identifier equals a registered `name`, `version`,
    `filename` or sha256, looked up as an opaque string. In the live corpus this is reachable only by
    forcing the kind (`--kind node noble-arm64-base`), because a bare artifact name is shaped like
    free text and detects as `text` — a similarity query, which never yields an artifact match.
Any other identifier — a symbol, a file-name, a path, a ticket, a git blob hash, free text — cannot
produce one, because no probe it dispatches to reads the ledger.

ONE SHA, MANY LOCATIONS, ONE ARTIFACT. The ledger is content-addressed, so the same bytes registered
twice are ONE artifact with SEVERAL locations — the reasoning ArtifactRegistry.php:43-48 gives for
the ticket-side table, and the way #455 already registers a VM (`meta.locations`). N registrations at
N locations therefore collapse to ONE match carrying N locations, never N matches. That collapse
mirrors what de_overlap() does for source — one match per REGION there, one match per CONTENT ADDRESS
here — and it spans BOTH sources of a location: the `filename` column and `meta.locations`.

WHAT DID NOT CHANGE, DELIBERATELY. #461 is additive: it makes an artifact representable and leaves
SOURCE resolution alone. Artifacts are appended AFTER the source collection is complete and are never
fed through expand/de_overlap/attach_tickets, which read {repo, path, line-range, blob sha}, so no
source match — and no source match's ORDER — can move. Stated exactly, because "nothing changed" is a
claim worth being precise about:

  * A SOURCE identifier of ANY kind returns the byte-identical collection it returned before #461.
    Measured against the pre-#461 file over every kind (name, file-name, path, uuid, node, git-hash,
    ticket-ref, work-uid, sha256-of-source, --like, --kind, --repo, --min-score, and the degenerate
    empty blob), with the state db both present and absent: identical in all of them.
  * A SIMILARITY query (--like, or free text) never yields an artifact match, whatever the
    identifier: it asks what is LIKE the identifier, and a registered artifact is not a similarity
    answer — it is the thing itself, reached by content address, with no vector to rank.
  * The ONE behaviour that does change, besides the sha256 kind #461 is about: a uuid- or node-kind
    query whose string happens to equal a registered artifact's name/version/filename now returns
    that artifact as a match, where before it was printed as a side-note beside "no match". Same fix,
    same reason — see WHEN AN ARTIFACT MATCH CAN APPEAR. No naturally-detected uuid or node id in the
    live corpus does this; reaching it takes an explicit --kind override.

There is no `artifacts` side-channel any more, in prose or in --json: that channel WAS the bug. What
the probe finds is in the collection, or the probe found nothing. `--acceptance` proves it live.

THE ONE ARTIFACT THIS PROBE CANNOT REACH, named so it is not mistaken for a bug: a `ticket_artifacts`
row whose `forge_sha` is 40 hex rather than 64 (row 21 today, #459's 'forge-source'). 40 hex is a git
blob sha, so it is detected as `git-blob` and dispatches to the blob probes, which do not include
forge-artifacts (see THE IDENTIFIER KINDS). That is a property of the recorded identifier, not of
this normalization, and #461 requires the git-hash mode to behave exactly as it did before.

────────────────────────────────────────────────────────────────────────────────────────────────
THE IDENTIFIER KINDS, AND THE INDEX EACH ONE DISPATCHES TO.

`--kind` overrides detection; `--kind auto` (the default) detects from the identifier's shape. An
AMBIGUOUS identifier fans out to EVERY probe that could answer it, so a mis-detection cannot hide a
match — detection picks the label, never the reach.

  git-blob   40 hex chars      -> the omni-git index (`blob`/`occ`), the #189 store's `occurrences`,
                                  the mem-graph `blob:<sha>` node, AND the git object db across the
                                  bare repos (see THE GIT OBJECT DB below).
  sha256     64 hex chars      -> the CONTENT-SHA256 index (built in memory, see below) and
                                  forge.db's `artifacts.sha256` content-address table.
  uuid       8-4-4-4-12        -> the uuid/string index (see THE UUID/STRING INDEX below).
  node       blob:|file:|path:|snap:|mem:|event:|shadow: prefixed
                               -> the mem-graph `node` table, by id, and the uuid/string index.
  ticket     '#N' or ticket:N  -> `ticket_works`: the works ticket N recorded, resolved to source.
  work-uid   uid:N             -> `ticket_works` by its permanent UID.
  path       contains '/'      -> omni `occ.path`, the #189 store's `occurrences.path`, the
                                  mem-graph `path:`/`file:` nodes.
  file-name  a basename with an extension  -> the same three, matched on the path's basename
                                  (+ the `name` probes, since a bare stem is often a symbol too).
  name       a bare identifier  -> the #189 store's `chunks.symbol`/`namespace`, omni's path
                                  basename-minus-extension, and mem-graph node labels.
  text       anything else      -> similarity (#190) — see THE SIMILARITY below.

────────────────────────────────────────────────────────────────────────────────────────────────
THE BACKING INDEXES (every one is opened READ-ONLY; NOTHING here is ever rebuilt).

  * THE OMNI-GIT INDEX — `omni_index.db` (~51MB), built by jazz-forge's omni_index.py. Two tables
    matter, and this is their schema as it exists today:
        occ  (sha, path, ext, size, ref, repo, ts)   -- one row per OCCURRENCE: this blob appeared
                                                        at this path, in this repo, in this snapshot
        blob (sha, path, ext, size, is_text)         -- one row per DISTINCT blob
    Resolved exactly as tools/code_sim_indexer.py resolves it (code_sim_indexer.py:158-159): the env
    var OMNI_INDEX_DB, else $HOME/code/installed/jazz-project/config/forge/omni_index.db — the same
    fallback the CMS reader uses (invocators/tags/dev/OmniExplorer.php:34-36).
  * THE OMNI-GIT OBJECT STORE — `archives/omni.git`, a bare git object store holding the blob bytes
    the index names. Read with read-only plumbing (`git --git-dir=<omni.git> cat-file`), never
    written (code_sim_indexer.py:161, :328-339).
  * THE #189 VECTOR STORE — `code_sim.db`, the store tools/code_sim_indexer.py builds (ticket #189)
    and this tool READS. Its `code_sim_index` VIEW is the tuple {repo, path, line_start, line_end,
    chunk, vector, blob_sha, namespace, symbol, chunk_seq, dim, model} (code_sim_indexer.py:423-426)
    — the surface index_watch.py names as "#190/#193's read" (index_watch.py:42-46, :1344). It is the
    source of every LINE-RANGE and every VECTOR below. It is NEVER written to here.
  * THE MEM-GRAPH — `mem_graph.db`, node(id, kind, label, attrs, ts) + edge(src, dst, kind, weight,
    ts, attrs). Node ids are strings: `blob:<sha>`, `file:<repo>:<path>`, `path:<p>`, `snap:<ref>`,
    `mem:<era>:<name>`, `event:<n>`, `shadow:<path>`. Resolved as the CMS reader resolves it
    (invocators/tags/dev/MemGraph.php:39-41): MEM_GRAPH_DB, else
    $HOME/code/installed/jazz-project/config/forge/mem_graph.db.
  * THE FORGE LEDGER — `forge.db`, whose `artifacts` table is a content-address index keyed by
    `sha256` (its own column), and this is its schema as it exists today:
        artifacts (id, ts, name, version, sha256, kind, size, filename, source_repo, source_commit,
                   meta)                            -- one row per REGISTRATION, NOT per artifact
    `filename` is the location that registration recorded; `meta` is free-form JSON whose
    `locations` list (written by #455's tools/vm_registry.py) names the OTHER locations of the same
    content address. Both feed an artifact match's `locations`. Resolved as ForgeView.php:32-34 does:
    FORGE_DB, else $HOME/code/installed/jazz-project/config/forge/forge.db.
  * THE CONGRUENCY STATE DB — `ticket_works (uid, ts, ticket_id, kind, ref, note)`
    (migrations/0029_ticket_authorization.sql:86-93), the source of ASSOCIATED TICKETS, and
    `ticket_artifacts (id, ts, ticket_id, name, version, forge_sha, kind)`
    (migrations/0014_ticket_artifacts.sql:7-15), the source of an artifact's MINTING TICKET. Default
    <repo>/checkouts/current/state/congruency.sqlite (the path ticket_status.py:46 and
    tag_selfcheck.py:88 both use); CONGRUENCY_SQLITE or --congruency-db override. This file is
    git-ignored (.gitignore:11) and so is ABSENT from a pair worktree: when it is missing, every
    match's `tickets` is simply empty — an artifact's minting ticket included, which a note on the
    resolution says in words — and `--indexes` says the index is absent. Nothing else about a
    resolution changes, and the tool never creates it.

THE CONTENT-SHA256 INDEX — built IN MEMORY, per run, and only when it is needed. No index in this
corpus is keyed by sha256: omni is keyed by git's blob sha1 (a hash of "blob <len>\0" + the bytes,
not of the bytes). So a sha256 query is answered by streaming every blob the index names out of
omni.git through ONE `git cat-file --batch` and sha256-ing the bytes. Measured on the live corpus:
6,295 text blobs in 0.07s. That is why this needs no cache, no sidecar and no rebuild — the ticket
says do NOT rebuild the corpus, and this builds NOTHING on disk. (`--all-blobs` widens the stream
from text blobs to every blob, for a sha256 of a binary.)

THE GIT OBJECT DB ACROSS BARE REPOS. Besides omni.git, the forge keeps ~262 BARE repositories at
config/forge/remotes/*.git — the same paths `repos.forge_remote` records in the congruency db
(the column tag_selfcheck.py checks, tag_selfcheck.py:31-33). For a git-blob identifier this tool
asks each one whether it HAS that object (`git --git-dir=<bare> cat-file -e <sha>^{blob}`), which
names the repos whose object db can serve those bytes. Discovered by globbing the remotes dir UNION
whatever `repos.forge_remote` lists, so it works with or without the congruency db. It costs ~2.6s
over the full set and is the only slow path here; `--no-git-fanout` skips it, and it runs ONLY for a
git-blob/sha256 identifier — never for a name, path or similarity query.

THE UUID/STRING INDEX. An OPAQUE identifier — a uuid, or any bare token that is not a hash, a path
or a python name — is looked up AS A STRING across the three places this corpus stores opaque ids:
mem-graph `node.id` and `node.label`, forge `artifacts` (matched on `name`, `version`, `filename` or
`sha256` — the columns the query actually binds), and `ticket_works.ref`. A forge hit here is an
ARTIFACT and becomes an artifact match, exactly as it does on the sha256 path (#461). Stated plainly
because the artifact must not over-promise: the live corpus holds NO uuid-shaped identifier today, so
a uuid query correctly resolves to an EMPTY collection. The kind is detected, the index is queried,
and "no match" is the honest answer — not a crash and not a pretence.

THE SIMILARITY (#190). Two independent similarity indexes are fanned out to and merged:
  1. THE #189 VECTORS — `chunks.vector`, a JSON float array, L2-normalized, so cosine similarity is
     a plain dot product (code_sim_indexer.py:83-86, :343-347). Two ways in:
       --like IDENT : resolve IDENT to its blob(s), take THEIR STORED vectors, and rank the store by
                      cosine. Needs NO network — the vectors are already in the store.
       free text    : embed the text through the litellm proxy (#184) and rank the store by cosine.
                      nomic-embed-text is task-prefixed: a QUERY is embedded as 'search_query: '
                      while #189 stored documents as 'search_document: ' (code_sim_indexer.py:71-75;
                      the repo's existing reader already sends the query half,
                      invocators/tags/dev/SemanticSearch.php:264). This is the ONLY path that
                      touches the network; if the proxy is down it exits 3 with one line.
  2. THE MEM-GRAPH `similar_to` EDGES — precomputed file<->file near-duplicate edges carrying a
     cosine weight. A second opinion from a different index, merged in with its weight as the score.
`--min-score` filters both (default 0.0 for an exact-identifier query, 0.5 for a similarity query).

THE SCORE. 1.0 for an EXACT identity resolution (the identifier IS that blob's hash / that path /
that symbol / that node id / that artifact's content address). For a similarity resolution it is the
cosine (dot product of unit vectors, or the mem-graph edge weight). So a score below 1.0 means "this
is like what you asked for", and 1.0 means "this IS what you asked for".

THE LINE-RANGE. From the #189 store: `chunks.line_start`/`line_end` is a callable's REAL span in the
original blob (its `def` line to its last line — code_sim_indexer.py:54-61), so a match points at
the callable, not just the file. A blob the #189 store has NOT indexed has no chunk rows, so it
yields ONE file-level match spanning 1..<the blob's line count>, counted by reading the blob out of
omni.git. The two levels are marked `chunk` and `file` in the `level` field.

DE-OVERLAPPED — what that means here, exactly. Because several indexes answer at once, the same
region of the same file can be reached twice. After the merge, within each {repo, path}:
  1. SUBSUME — if any chunk-level match exists for that path, the file-level match for that path is
     DROPPED. The file-level span (1..n) strictly contains every chunk span, so keeping both would
     report the same region at two precisions; the chunk is the more precise, and it carries the
     symbol.
  2. MERGE — any two remaining matches whose [line_start, line_end] intervals OVERLAP collapse into
     ONE match spanning min(start)..max(end), taking the MAX score and the UNION of their `via`
     provenance. Distinct callables in one file do not overlap and so stay distinct.
The guarantee this yields, and which --acceptance checks: NO TWO source matches in the returned
collection share a {repo, path} and overlap in lines. The ARTIFACT matches carry the same guarantee
in their own terms — no two share a sha256, because one content address IS one artifact — and they
have no {repo, path, line-range} to overlap on, so they are collapsed by artifact_matches() rather
than passed through this function.

ASSOCIATED TICKETS. For a SOURCE match, the tickets whose `ticket_works.ref` names it, by either of
the two conventions actually in the table: `omni-blob:<sha>` — the ref index_watch.py:214 writes for
an indexed blob — matched against the match's blob sha; or a repo-relative PATH, matched when ref ==
path, or one is a '/'-delimited suffix of the other. Basename-only matching is deliberately NOT
done: it would attach every ticket that ever touched an `__init__.py` to all 180 of them.

For an ARTIFACT match the ticket is the MINTING one, and it comes from a different table in a
different FILE: `ticket_artifacts.forge_sha` in the congruency state db, joined on the sha256 content
address (the join minting_tickets() below performs). The forge ledger's `artifacts` and congruency's
`ticket_artifacts` are two registries that meet on nothing but that address — tools/vm_registry.py:
96-109 documents the split, and before #461 resolver.py did not read the ticket-side table at all.
Each entry is {ticket, artifact_id, kind}, where a source match's is {ticket, uid, kind}: both name
the ticket, and each names the row it came from in its own table's terms.

WHAT IT WRITES: NOTHING. Every database is opened through the sqlite URI flag `immutable=1`, never
`mode=ro` — the state db is WAL-journalled, and `mode=ro` on a WAL db spins up `congruency.sqlite-shm`
and `-wal` sidecar files in the state directory on every open, which is a file this tool must not
create (the #153 lesson, fixed the same way at ticket_status.py:49-60). `immutable=1` promises sqlite
the file will not change, so it reads the identical committed data with no locking and creates ZERO
files. omni.git and every bare repo are read with `cat-file` plumbing only. Bytecode caching is
disabled before any import-by-path, so no `__pycache__` is minted beside the sources this tool
loads. THE ONE FILE THIS TOOL CAN EVER CREATE is the note-for-claude bug report
(logs/bug_reports.jsonl, git-ignored per .gitignore:20-21) written when an UNEXPECTED exception is
thrown — the registry's contract for every tool in this package.

IT REUSES #189 RATHER THAN REIMPLEMENTING IT — the same reason index_watch.py:56-62 gives. The corpus
paths, the read-only connect, the occurrence lookup, the blob read, the vector normalization and the
embedder all come from the sibling tools/code_sim_indexer.py, loaded as a module (load_indexer()
below, the loader pattern of index_watch.py:241-264). A parallel reimplementation could drift from
#189 and silently resolve against a different corpus than the one #189 indexed.

Exit codes (each prints ONE line, never a traceback):
    0  the resolution completed — INCLUDING an empty collection, which is an answer, not a failure
       (--acceptance: every check PASSED)
    1  --acceptance: at least one check FAILED
    2  a precondition failure — no omni index, no omni.git, no #189 store, an unknown --kind, or an
       --acceptance with no qualifying specimen in the live corpus
    3  a free-text similarity query needed the litellm proxy and it was unreachable or answered
       unusably (mirrors code_sim_indexer.py's exit 3)
Pure-python stdlib, one file. Registry-gated per note-for-claude: it walks UP to registry.json and
refuses to run without it.
"""
import argparse
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
import threading
import time
import traceback

# NO BYTECODE CACHE. This tool loads code_sim_indexer.py from SOURCE via importlib; python's default
# is to cache the compiled bytecode beside the source, which would mint
# checkouts/current/congruency/tools/__pycache__/code_sim_indexer.*.pyc — a file, contradicting this
# module's own "writes NOTHING" guarantee. (It is git-ignored (.gitignore:4-5), but "git-ignored" is
# not "not created", and the guarantee is about the filesystem.) Set before any import-by-path
# happens, so the guarantee holds on every path. Same reasoning as index_watch.py:183-191.
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
HOME = os.path.expanduser("~")

# The congruency state db — ticket_works, the ASSOCIATED-TICKETS index. Same path ticket_status.py:46
# and tag_selfcheck.py:88 use. Git-ignored (.gitignore:11), hence absent from a pair worktree; that is
# handled, not assumed away (see attach_tickets()).
CONGRUENCY_DB = os.environ.get("CONGRUENCY_SQLITE") or os.path.join(
    ROOT, "checkouts", "current", "state", "congruency.sqlite")

# The mem-graph and the forge ledger, resolved exactly as the CMS tags resolve them
# (MemGraph.php:39-41, ForgeView.php:32-34).
MEM_GRAPH_DB = os.environ.get("MEM_GRAPH_DB") or os.path.join(
    HOME, "code/installed/jazz-project/config/forge/mem_graph.db")
FORGE_DB = os.environ.get("FORGE_DB") or os.path.join(
    HOME, "code/installed/jazz-project/config/forge/forge.db")

DEFAULT_LIMIT = 50           # matches printed/returned unless --limit says otherwise
SIM_MIN_SCORE = 0.5          # the default floor for a SIMILARITY query (an exact query floors at 0)
GIT_FANOUT_TIMEOUT = 10      # seconds per bare-repo `cat-file -e` probe

MCP_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")   # newest first, as ticket_api_mcp.py:107
MCP_SERVER_NAME = "congruency-resolver"
MCP_SERVER_VERSION = "1.0.0"

KINDS = ("git-blob", "sha256", "uuid", "node", "ticket", "work-uid", "path", "file-name", "name", "text")

# The mem-graph's node-id namespaces (the `kind` column's values, prefixing every id).
NODE_PREFIXES = ("blob", "file", "path", "snap", "mem", "event", "shadow")

# Extensions that make a dotted token a FILE-NAME rather than a `Class.method` name. Kept to the
# corpus's own text kinds; an unknown suffix falls through to the name/file-name double probe, so a
# miss here costs nothing but the label (see detect_kind).
FILE_EXTS = {"py", "js", "ts", "tsx", "jsx", "json", "md", "php", "sh", "go", "rs", "c", "h", "cc",
             "cpp", "hpp", "java", "rb", "pl", "yml", "yaml", "txt", "sql", "html", "htm", "css",
             "toml", "ini", "cfg", "conf", "xml", "lock", "bundle", "sqlite", "db"}

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class Fault(Exception):
    """A precondition failure — reported as one line, exit 2."""


class EmbedError(Exception):
    """The litellm proxy is unreachable or answered unusably — one line, exit 3."""


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks).
    note-for-claude: every tool files a timestamped report when an exception is thrown. This is the
    ONLY file this tool can ever create, and only on an unexpected exception."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "resolver.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:],
                "note": "the universal resolver (#193)",
            }) + "\n")
    except Exception:  # noqa: BLE001 — a failed bug report must never mask the original fault
        pass


# ── #189's indexer, reused as-is (the corpus paths, the reads, the vectors, the embedder) ─────────
def load_indexer(path=None):
    """The sibling tools/code_sim_indexer.py (ticket #189), loaded as a module.

    Loaded by path rather than imported by name because `tools/` is not a package — the loader
    pattern of index_watch.py:241-264. Importing it runs only its registry gate and its constants: it
    opens nothing and writes nothing at import.
    """
    src = path or os.path.join(HERE, "code_sim_indexer.py")
    if not os.path.isfile(src):
        raise Fault("tools/code_sim_indexer.py (ticket #189) not found at %s — the resolver reads "
                    "the store IT builds and will not reimplement it" % src)
    spec = importlib.util.spec_from_file_location("cs_indexer", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        raise Fault("code_sim_indexer.py at %s failed to load: %r" % (src, e))
    for name in ("OMNI_DB", "OMNI_GIT", "STORE", "LITELLM", "LITELLM_KEY", "MODEL", "PY_EXT",
                 "ro_connect", "l2", "embed_all", "omni_tables"):
        if not hasattr(mod, name):
            raise Fault("%s defines no %s — wrong code_sim_indexer version?" % (src, name))
    return mod


# ── read-only sqlite: immutable=1 reads committed data and creates NO -wal/-shm sidecars ─────────
def open_ro(path):
    """The db read-only, or None when it does not exist. An absent index is a fact to report, never
    a file to bring into being."""
    if not path or not os.path.isfile(path):
        return None
    return sqlite3.connect("file:%s?immutable=1" % path, uri=True)


def table_exists(con, name):
    if con is None:
        return False
    return con.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=? LIMIT 1",
                       (name,)).fetchone() is not None


# ── identifier detection ─────────────────────────────────────────────────────────────────────────
def detect_kind(q):
    """The identifier's kind, from its shape alone. `--kind` overrides this; and an ambiguous
    identifier still fans out to every probe that could answer it (probes_for), so detection picks
    the LABEL, never the reach."""
    s = (q or "").strip()
    if re.fullmatch(r"#\d+", s) or re.fullmatch(r"ticket:\d+", s, re.I):
        return "ticket"
    if re.fullmatch(r"uid:\d+", s, re.I):
        return "work-uid"
    if UUID_RE.fullmatch(s):
        return "uuid"
    if re.fullmatch(r"[0-9a-fA-F]{40}", s):
        return "git-blob"
    if re.fullmatch(r"[0-9a-fA-F]{64}", s):
        return "sha256"
    if s.split(":", 1)[0] in NODE_PREFIXES and ":" in s:
        return "node"
    if "/" in s:
        return "path"
    if re.fullmatch(r"[A-Za-z_]\w*", s):
        return "name"
    if "." in s and re.fullmatch(r"[\w.\-]+", s):
        # dotted: a file-name if the suffix is a known extension, else a Class.method-shaped name.
        return "file-name" if s.rsplit(".", 1)[-1].lower() in FILE_EXTS else "name"
    return "text"


def probes_for(kind):
    """The probe names a given kind fans out to. An ambiguous kind lists EVERY probe that could
    answer it — a file-name is often also a symbol stem, and vice versa."""
    return {
        "git-blob":  ["omni-blob", "store-occ", "memgraph-node", "git-object-db"],
        "sha256":    ["content-sha256", "forge-artifacts", "git-object-db"],
        "uuid":      ["string-index"],
        "node":      ["memgraph-node", "string-index"],
        "ticket":    ["ticket-works"],
        "work-uid":  ["ticket-works"],
        "path":      ["omni-path", "store-path", "memgraph-node"],
        "file-name": ["omni-basename", "store-basename", "memgraph-label", "store-symbol"],
        "name":      ["store-symbol", "omni-stem", "memgraph-label"],
        "text":      ["similarity"],
    }.get(kind, [])


# ── omni.git: one streamed batch read of many blobs (never a write) ──────────────────────────────
def batch_blobs(gitdir, shas):
    """{sha: bytes} for the given shas, in ONE `git cat-file --batch`.

    The feeder runs on a THREAD deliberately: git interleaves reading stdin with writing stdout, so
    writing the whole sha list up front while not draining stdout deadlocks once the 64KB pipe
    buffer fills (6,295 shas is ~258KB of input). Reading raw (no text mode) because
    universal-newline translation would mutate the bytes away from what the corpus holds — and these
    bytes get hashed, so a mutation would be a WRONG ANSWER, not a cosmetic one.
    """
    shas = [s for s in dict.fromkeys(shas) if s]
    if not shas:
        return {}
    p = subprocess.Popen(["git", "--git-dir", gitdir, "cat-file", "--batch"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def feed():
        try:
            p.stdin.write(("\n".join(shas) + "\n").encode())
            p.stdin.close()
        except Exception:  # noqa: BLE001 — a broken pipe just ends the stream; the reader sees EOF
            pass

    t = threading.Thread(target=feed, daemon=True)
    t.start()
    out, got = p.stdout, {}
    try:
        for _ in range(len(shas)):
            hdr = out.readline()
            if not hdr:
                break
            parts = hdr.split()
            if len(parts) >= 2 and parts[-1] in (b"missing", b"ambiguous"):
                continue                                    # not in this object store — a fact
            if len(parts) < 3:
                continue
            try:
                size = int(parts[2])
            except ValueError:
                continue
            body = out.read(size)
            out.read(1)                                     # the trailing newline git emits
            got[parts[0].decode()] = body
    finally:
        try:
            p.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        p.wait(timeout=30)
        t.join(timeout=5)
    return got


def sha256_index(ocon, gitdir, all_blobs=False):
    """{sha256_hex: git_blob_sha} over the blobs the omni index names — built IN MEMORY, per run.

    No index in this corpus is keyed by sha256 (omni is keyed on git's blob sha1, which hashes
    "blob <len>\\0" + the bytes, not the bytes), so this is how a content sha256 is answered. It
    creates no file and rebuilds nothing: one streamed pass over omni.git. Measured on the live
    corpus: 6,295 text blobs in 0.07s. Default scope is `is_text=1` — the corpus's source; pass
    --all-blobs to include binaries.
    """
    sql = "SELECT sha FROM blob" + ("" if all_blobs else " WHERE is_text = 1")
    shas = [r[0] for r in ocon.execute(sql)]
    return {hashlib.sha256(body).hexdigest(): sha for sha, body in batch_blobs(gitdir, shas).items()}


# ── the git object db across the bare repos ──────────────────────────────────────────────────────
def bare_repos(ccon):
    """[(name, gitdir)] — every bare repo whose object db might serve a blob.

    The UNION of two sources, so this works with or without the congruency db: the forge's remotes
    directory globbed from disk (config/forge/remotes/*.git — a sibling of the omni index), and
    whatever `repos.forge_remote` records (the column tag_selfcheck.py:31-33 verifies). Only paths
    that exist on disk are returned.
    """
    found = {}
    for d in sorted(glob.glob(os.path.join(HOME, "code/installed/jazz-project/config/forge/remotes/*.git"))):
        if os.path.isdir(d):
            found[os.path.realpath(d)] = os.path.basename(d)[:-4]
    if ccon is not None and table_exists(ccon, "repos"):
        for name, remote in ccon.execute("SELECT name, forge_remote FROM repos WHERE forge_remote IS NOT NULL"):
            if remote and os.path.isdir(remote):
                found[os.path.realpath(remote)] = name
    return sorted((n, d) for d, n in found.items())


def repos_holding(sha, repos):
    """The bare repos whose object db HAS this blob. `cat-file -e <sha>^{blob}` asks the object db
    the question directly and writes nothing; ^{blob} makes a non-blob object of the same sha a
    miss rather than a false hit."""
    out = []
    for name, gitdir in repos:
        try:
            r = subprocess.run(["git", "--git-dir", gitdir, "cat-file", "-e", "%s^{blob}" % sha],
                               capture_output=True, timeout=GIT_FANOUT_TIMEOUT)
            if r.returncode == 0:
                out.append(name)
        except (subprocess.TimeoutExpired, OSError):
            continue                                        # an unreadable repo is skipped, not fatal
    return out


# ── the probes: identifier -> {sha: (score, via)} ────────────────────────────────────────────────
def _add(hits, sha, score, via):
    if not sha:
        return
    cur = hits.get(sha)
    if cur is None:
        hits[sha] = [score, {via}]
    else:
        cur[0] = max(cur[0], score)
        cur[1].add(via)


def _in_chunks(seq, n=400):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]                                  # sqlite caps host parameters


def resolve_to_shas(q, kind, src, opts, artifacts=None):
    """{sha: [score, {via}]} — step 1: the identifier, through every index that knows its kind.

    `via` names the index that reached it, so the collection can say HOW each match was found.
    `artifacts` is an OUT list of raw forge-ledger REGISTRATION rows (forge_artifact_rows below): a
    forge artifact is content-addressed by sha256 but is not an omni blob, so it never becomes a
    `sha` here. It is normalized into its own kind of match by artifact_matches() — see AN ARTIFACT
    HIT IS A MATCH in the module docstring. Passed in explicitly rather than stashed on `opts`, so
    two resolutions sharing an options dict cannot accumulate each other's findings.
    """
    artifacts = [] if artifacts is None else artifacts
    hits, probes = {}, probes_for(kind)
    s = q.strip()
    ocon, scon, gcon, fcon, ccon = src["omni"], src["store"], src["graph"], src["forge"], src["cong"]

    # ── exact blob identity ──────────────────────────────────────────────────────────────────────
    if "omni-blob" in probes and ocon is not None:
        low = s.lower()
        if ocon.execute("SELECT 1 FROM blob WHERE sha = ? LIMIT 1", (low,)).fetchone():
            _add(hits, low, 1.0, "omni-git:blob")
        if ocon.execute("SELECT 1 FROM occ WHERE sha = ? LIMIT 1", (low,)).fetchone():
            _add(hits, low, 1.0, "omni-git:occ")
    if "store-occ" in probes and scon is not None:
        if scon.execute("SELECT 1 FROM occurrences WHERE sha = ? LIMIT 1", (s.lower(),)).fetchone():
            _add(hits, s.lower(), 1.0, "code_sim:occurrences")

    # ── content sha256 -> the git blob that hashes to it ─────────────────────────────────────────
    if "content-sha256" in probes and ocon is not None and src["omni_git"]:
        sha = sha256_index(ocon, src["omni_git"], opts.get("all_blobs")).get(s.lower())
        if sha:
            _add(hits, sha, 1.0, "content-sha256")
    if "forge-artifacts" in probes:
        artifacts.extend(forge_artifact_rows(fcon, "lower(sha256) = ?", (s.lower(),), "forge-artifacts"))

    # ── the mem-graph node id / the uuid-or-string index ─────────────────────────────────────────
    if "memgraph-node" in probes and gcon is not None:
        for nid, kindc in gcon.execute("SELECT id, kind FROM node WHERE id = ?", (s,)):
            if kindc == "blob":
                _add(hits, nid.split(":", 1)[1], 1.0, "mem-graph:node")
        # a blob sha also has a `blob:<sha>` node; a path also has `file:<repo>:<path>` nodes
        if kind == "git-blob" and gcon.execute("SELECT 1 FROM node WHERE id = ? LIMIT 1",
                                               ("blob:" + s.lower(),)).fetchone():
            _add(hits, s.lower(), 1.0, "mem-graph:node")

    if "string-index" in probes:
        # An opaque token, looked up as a STRING wherever this corpus stores opaque ids. The live
        # corpus holds no uuid-shaped id, so a uuid query resolves empty — the honest answer.
        if gcon is not None:
            for (nid,) in gcon.execute("SELECT id FROM node WHERE id = ? OR label = ? LIMIT 200", (s, s)):
                if nid.startswith("blob:"):
                    _add(hits, nid.split(":", 1)[1], 1.0, "string-index:mem-graph")
                elif nid.startswith("file:"):
                    for sha in _shas_for_path(ocon, nid.split(":", 2)[2]):
                        _add(hits, sha, 1.0, "string-index:mem-graph")
        artifacts.extend(forge_artifact_rows(
            fcon, "name = ? OR version = ? OR filename = ? OR lower(sha256) = ? LIMIT 50",
            (s, s, s, s.lower()), "string-index:forge-artifacts"))
        if ccon is not None and table_exists(ccon, "ticket_works"):
            for ref, tid in ccon.execute("SELECT ref, ticket_id FROM ticket_works WHERE ref = ? LIMIT 50", (s,)):
                for sha in _shas_for_ref(ocon, ref):
                    _add(hits, sha, 1.0, "string-index:ticket_works")

    # ── a ticket's recorded works, resolved to source ────────────────────────────────────────────
    if "ticket-works" in probes and ccon is not None and table_exists(ccon, "ticket_works"):
        if kind == "ticket":
            tid = int(re.sub(r"\D", "", s))
            rows = ccon.execute("SELECT ref FROM ticket_works WHERE ticket_id = ?", (tid,)).fetchall()
        else:
            uid = int(re.sub(r"\D", "", s))
            rows = ccon.execute("SELECT ref FROM ticket_works WHERE uid = ?", (uid,)).fetchall()
        for (ref,) in rows:
            for sha in _shas_for_ref(ocon, ref):
                _add(hits, sha, 1.0, "ticket_works")

    # ── path / file-name / name ──────────────────────────────────────────────────────────────────
    if "omni-path" in probes and ocon is not None:
        for (sha,) in ocon.execute("SELECT DISTINCT sha FROM occ WHERE path = ?", (s,)):
            _add(hits, sha, 1.0, "omni-git:occ.path")
        for (sha,) in ocon.execute("SELECT DISTINCT sha FROM occ WHERE path LIKE ? LIMIT 500", ("%/" + s,)):
            _add(hits, sha, 1.0, "omni-git:occ.path")       # a '/'-suffix of a longer stored path
    if "store-path" in probes and scon is not None:
        for (sha,) in scon.execute("SELECT DISTINCT sha FROM occurrences WHERE path = ? OR path LIKE ?",
                                   (s, "%/" + s)):
            _add(hits, sha, 1.0, "code_sim:occurrences.path")
    if "omni-basename" in probes and ocon is not None:
        for (sha,) in ocon.execute("SELECT DISTINCT sha FROM occ WHERE path = ? OR path LIKE ? LIMIT 2000",
                                   (s, "%/" + s)):
            _add(hits, sha, 1.0, "omni-git:occ.basename")
    if "store-basename" in probes and scon is not None:
        for (sha,) in scon.execute("SELECT DISTINCT sha FROM occurrences WHERE path = ? OR path LIKE ?",
                                   (s, "%/" + s)):
            _add(hits, sha, 1.0, "code_sim:occurrences.basename")
    if "omni-stem" in probes and ocon is not None:
        # the shred corpus names a file after the callable it holds: <name>.py
        for (sha,) in ocon.execute("SELECT DISTINCT sha FROM occ WHERE path = ? OR path LIKE ? LIMIT 2000",
                                   (s + ".py", "%/" + s + ".py")):
            _add(hits, sha, 1.0, "omni-git:occ.stem")
    if "store-symbol" in probes and scon is not None:
        stem = s.rsplit(".", 1)[0] if "." in s else s
        for (sha,) in scon.execute(
                "SELECT DISTINCT sha FROM chunks WHERE symbol = ? OR namespace = ? OR symbol = ? OR namespace = ?",
                (s, s, stem, stem)):
            _add(hits, sha, 1.0, "code_sim:chunks.symbol")
    if "memgraph-label" in probes and gcon is not None:
        stem = s if "." in s else s + ".py"
        for nid, kindc in gcon.execute("SELECT id, kind FROM node WHERE label IN (?,?) LIMIT 500", (s, stem)):
            if kindc == "blob":
                _add(hits, nid.split(":", 1)[1], 1.0, "mem-graph:label")
            elif kindc in ("file", "path") and ocon is not None:
                p = nid.split(":", 2)[2] if kindc == "file" else nid.split(":", 1)[1]
                for sha in _shas_for_path(ocon, p):
                    _add(hits, sha, 1.0, "mem-graph:label")
    return hits


def _shas_for_path(ocon, path):
    if ocon is None or not path:
        return []
    return [r[0] for r in ocon.execute(
        "SELECT DISTINCT sha FROM occ WHERE path = ? OR path LIKE ? LIMIT 200", (path, "%/" + path))]


def _shas_for_ref(ocon, ref):
    """A ticket_works.ref -> blob shas. Two conventions live in that column: `omni-blob:<sha>`, the
    ref index_watch.py:214 records for an indexed blob, and a repo-relative path."""
    if not ref:
        return []
    if ref.startswith("omni-blob:"):
        return [ref.split(":", 1)[1]]
    return _shas_for_path(ocon, ref)


# ── the similarity probes (#190): the #189 vectors, and the mem-graph's similar_to edges ─────────
def store_vectors(scon, model):
    """[(sha, chunk_seq, vector)] for every chunk in the store under `model`. The store holds JSON
    float arrays, L2-normalized by #189 (code_sim_indexer.py:83-86), so cosine IS the dot product."""
    if scon is None:
        return []
    out = []
    for sha, seq, vec in scon.execute(
            "SELECT sha, chunk_seq, vector FROM chunks WHERE model = ? AND vector IS NOT NULL", (model,)):
        try:
            v = json.loads(vec)
        except (TypeError, ValueError):
            continue
        if v:
            out.append((sha, seq, v))
    return out


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def embed_query(cs, text, opts):
    """The query embedded through the litellm proxy (#184), via #189's own embed_all.

    nomic-embed-text is task-prefixed: a QUERY is 'search_query: ' while #189 stored documents as
    'search_document: ' (code_sim_indexer.py:71-75; SemanticSearch.php:264 already sends the query
    half). Raises EmbedError -> exit 3, mirroring code_sim_indexer.py.
    """
    try:
        vecs = cs.embed_all(opts["litellm"], opts["model"], cs.LITELLM_KEY,
                            ["search_query: " + text], 1, opts["timeout"])
    except Exception as e:  # noqa: BLE001 — cs.EmbedError and transport faults alike
        raise EmbedError(str(e))
    if not vecs:
        raise EmbedError("litellm returned no embedding for the query")
    return cs.l2(vecs[0])


def similar_shas(src, opts, query_vectors, exclude=()):
    """{sha: [score, {via}]} — the blobs whose chunks are nearest the query vector(s), by cosine
    over the #189 store. A blob's score is its BEST chunk's cosine."""
    hits = {}
    for sha, _seq, v in store_vectors(src["store"], opts["model"]):
        if sha in exclude:
            continue
        best = max((dot(qv, v) for qv in query_vectors), default=0.0)
        if best >= opts["min_score"]:
            _add(hits, sha, best, "code_sim:vector")
    return hits


def graph_similar(src, shas, opts):
    """{sha: [score, {via}]} — near-duplicates via the mem-graph's precomputed `similar_to` edges: a
    SECOND similarity index, fanned out to alongside the #189 vectors. The edge weight is a cosine,
    used as the score."""
    gcon, ocon = src["graph"], src["omni"]
    hits = {}
    if gcon is None or ocon is None or not shas:
        return hits
    files = set()
    for part in _in_chunks(shas):
        q = ",".join("?" * len(part))
        for repo, path in ocon.execute(
                "SELECT DISTINCT repo, path FROM occ WHERE sha IN (%s) LIMIT 400" % q, list(part)):
            files.add("file:%s:%s" % (repo, path))
    for part in _in_chunks(sorted(files), 200):
        q = ",".join("?" * len(part))
        for src_id, dst_id, w in gcon.execute(
                "SELECT src, dst, weight FROM edge WHERE kind='similar_to' AND (src IN (%s) OR dst IN (%s))"
                % (q, q), list(part) + list(part)):
            other = dst_id if src_id in part else src_id
            if not other.startswith("file:") or float(w or 0) < opts["min_score"]:
                continue
            for sha in _shas_for_path(ocon, other.split(":", 2)[2]):
                _add(hits, sha, float(w or 0), "mem-graph:similar_to")
    return hits


# ── step 2: a sha -> every {repo, path} it occurs at, with line-ranges ───────────────────────────
def expand(src, hits, opts):
    """The normalized matches for the resolved shas: every occurrence of every blob.

    Line-ranges come from the #189 store's chunks (the callable's real span,
    code_sim_indexer.py:54-61) — one `chunk` match per callable per occurrence. A blob the store has
    not indexed has no chunks, so it yields ONE `file`-level match spanning 1..<line count>, counted
    by reading the blob out of omni.git.
    """
    ocon, scon = src["omni"], src["store"]
    shas = list(hits)
    occ_by_sha, chunks_by_sha = {}, {}
    for part in _in_chunks(shas):
        q = ",".join("?" * len(part))
        if ocon is not None:
            sql = "SELECT DISTINCT sha, repo, path FROM occ WHERE sha IN (%s)" % q
            args = list(part)
            if opts.get("repo"):
                sql += " AND repo = ?"
                args.append(opts["repo"])
            for sha, repo, path in ocon.execute(sql, args):
                occ_by_sha.setdefault(sha, set()).add((repo, path))
        if scon is not None:
            # the store records occurrences too; union them so a blob is placed even if omni is
            # scoped away, and so the two indexes cannot silently disagree about where it lives
            sql = "SELECT DISTINCT sha, repo, path FROM occurrences WHERE sha IN (%s)" % q
            args = list(part)
            if opts.get("repo"):
                sql += " AND repo = ?"
                args.append(opts["repo"])
            for sha, repo, path in scon.execute(sql, args):
                occ_by_sha.setdefault(sha, set()).add((repo, path))
            for sha, seq, ns, sym, lo, hi in scon.execute(
                    "SELECT sha, chunk_seq, namespace, symbol, line_start, line_end FROM chunks "
                    "WHERE sha IN (%s) AND model = ?" % q, list(part) + [opts["model"]]):
                chunks_by_sha.setdefault(sha, []).append((seq, ns, sym, lo, hi))

    # file-level matches need the blob's line count; one batched read for exactly those blobs
    need = [s for s in shas if s in occ_by_sha and not chunks_by_sha.get(s)]
    nlines = {}
    if need and src["omni_git"]:
        for sha, body in batch_blobs(src["omni_git"], need).items():
            nlines[sha] = body.count(b"\n") + (0 if body.endswith(b"\n") or not body else 1)

    matches = []
    for sha, (score, via) in hits.items():
        for repo, path in sorted(occ_by_sha.get(sha, ())):
            if chunks_by_sha.get(sha):
                for seq, ns, sym, lo, hi in sorted(chunks_by_sha[sha]):
                    matches.append({"repo": repo, "path": path, "line_start": lo, "line_end": hi,
                                    "level": "chunk", "symbol": sym, "namespace": ns or "",
                                    "chunk_seq": seq, "blob_sha": sha, "score": round(score, 6),
                                    "via": sorted(via), "tickets": []})
            else:
                # None = the blob is named by the index but absent from the object store (rendered
                # '1-?'); 0 = a ZERO-BYTE blob, which has no lines at all (rendered '(empty)').
                # These are different facts and are kept distinct rather than collapsed to a falsy 0.
                n = nlines.get(sha)
                matches.append({"repo": repo, "path": path,
                                "line_start": 0 if n == 0 else 1, "line_end": n,
                                "level": "file", "symbol": None,
                                "namespace": "", "chunk_seq": None, "blob_sha": sha,
                                "score": round(score, 6), "via": sorted(via), "tickets": []})
    return matches


# ── de-overlap ───────────────────────────────────────────────────────────────────────────────────
def de_overlap(matches):
    """One match per region: no two returned matches share a {repo, path} AND overlap in lines.

    1. SUBSUME — a file-level match is dropped when a chunk-level match exists for the same
       {repo, path}: the file span (1..n) strictly contains every chunk span, so both would report
       the same region at two precisions, and the chunk is the more precise (it carries the symbol).
    2. MERGE — two remaining matches whose [line_start, line_end] intervals OVERLAP collapse into one
       spanning min(start)..max(end), keeping the MAX score and the UNION of `via`/`blob_sha`.
       Distinct callables in one file do not overlap, so they stay distinct.
    """
    by_file = {}
    for m in matches:
        by_file.setdefault((m["repo"], m["path"]), []).append(m)

    out = []
    for _key, group in by_file.items():
        if any(m["level"] == "chunk" for m in group):
            group = [m for m in group if m["level"] == "chunk"]          # 1. subsume
        group.sort(key=lambda m: (m["line_start"] or 0, m["line_end"] or 0))
        cur = None
        for m in group:                                                  # 2. merge
            lo = m["line_start"] or 0
            hi = m["line_end"] if m["line_end"] is not None else lo
            if cur is None:
                cur = dict(m, via=list(m["via"]), _lo=lo, _hi=hi, blob_shas={m["blob_sha"]})
                continue
            if lo <= cur["_hi"] and hi >= cur["_lo"]:                    # overlapping intervals
                cur["_lo"], cur["_hi"] = min(cur["_lo"], lo), max(cur["_hi"], hi)
                cur["line_start"], cur["line_end"] = cur["_lo"], cur["_hi"]
                cur["score"] = max(cur["score"], m["score"])
                cur["via"] = sorted(set(cur["via"]) | set(m["via"]))
                cur["blob_shas"].add(m["blob_sha"])
                if cur.get("symbol") and m.get("symbol") and cur["symbol"] != m["symbol"]:
                    cur["symbol"] = "%s+%s" % (cur["symbol"], m["symbol"])
                cur["symbol"] = cur.get("symbol") or m.get("symbol")
            else:
                out.append(cur)
                cur = dict(m, via=list(m["via"]), _lo=lo, _hi=hi, blob_shas={m["blob_sha"]})
        if cur is not None:
            out.append(cur)

    for m in out:
        m.pop("_lo", None)
        m.pop("_hi", None)
        m["blob_shas"] = sorted(m.pop("blob_shas"))
    out.sort(key=lambda m: (-m["score"], m["repo"], m["path"], m["line_start"] or 0))
    return out


# ── associated tickets ───────────────────────────────────────────────────────────────────────────
def attach_tickets(ccon, matches):
    """Fill each match's `tickets` from ticket_works (0029:86-93), by the two conventions actually in
    that column: `omni-blob:<sha>` (index_watch.py:214) against the match's blob sha, and a
    repo-relative path where ref == path or one is a '/'-delimited suffix of the other.

    Basename-only matching is deliberately NOT done — it would staple every ticket that ever touched
    an `__init__.py` onto all 180 of them. An ABSENT db (the normal case in a pair worktree, where
    the state db is git-ignored, .gitignore:11) leaves every `tickets` empty and is not an error.
    """
    if ccon is None or not table_exists(ccon, "ticket_works") or not matches:
        return matches
    rows = ccon.execute("SELECT ticket_id, uid, kind, ref FROM ticket_works WHERE ref IS NOT NULL").fetchall()
    by_sha, paths = {}, []
    for tid, uid, kind, ref in rows:
        if ref.startswith("omni-blob:"):
            by_sha.setdefault(ref.split(":", 1)[1], []).append({"ticket": tid, "uid": uid, "kind": kind})
        else:
            paths.append((ref, {"ticket": tid, "uid": uid, "kind": kind}))
    for m in matches:
        found, seen = [], set()
        for sha in m.get("blob_shas", [m["blob_sha"]]):
            for t in by_sha.get(sha, []):
                if t["uid"] not in seen:
                    seen.add(t["uid"])
                    found.append(t)
        for ref, t in paths:
            p = m["path"]
            if (ref == p or ref.endswith("/" + p) or p.endswith("/" + ref)) and t["uid"] not in seen:
                seen.add(t["uid"])
                found.append(t)
        m["tickets"] = sorted(found, key=lambda t: t["uid"])
    return matches


# ── the forge artifacts: an artifact hit IS a match (ticket #461) ────────────────────────────────
# The forge ledger's `artifacts` columns this reads. `id` orders the registrations; `sha256` is the
# identity everything else hangs off (the schema is quoted in THE FORGE LEDGER above).
ARTIFACT_COLS = ("id", "name", "version", "sha256", "kind", "size", "filename", "meta")


def forge_artifact_rows(fcon, where, args, via):
    """The forge ledger's `artifacts` REGISTRATION rows matching `where`, each tagged with the probe
    that reached it.

    One ROW is one REGISTRATION, not one artifact: the ledger is content-addressed, so the same
    bytes registered twice are ONE artifact with SEVERAL locations — the reasoning
    ArtifactRegistry.php:43-48 spells out for the ticket-side table. artifact_matches() does that
    collapse; this only reads. An absent ledger, or a ledger with no `artifacts` table, is no rows —
    a fact to report, never a file to bring into being.
    """
    if fcon is None or not table_exists(fcon, "artifacts"):
        return []
    sql = "SELECT %s FROM artifacts WHERE %s" % (", ".join(ARTIFACT_COLS), where)
    return [dict(zip(ARTIFACT_COLS, r), via=via) for r in fcon.execute(sql, args)]


def _meta_locations(meta):
    """The `locations` list #455's tools/vm_registry.py records in an artifact's `meta` JSON — the
    OTHER places one content address is registered at, beyond its `filename`. (Live example: the
    meta of `noble-arm64-base` carries both config/vm/noble-arm64-base.img and
    config/forge/large-blobs/<sha>.) `meta` is a free-form JSON extras column, so anything that is
    not a list of non-empty strings under `locations` yields NO locations: a malformed extra field
    must never turn a real registration into a crash, and must never invent a location either.
    """
    if not meta:
        return []
    try:
        d = json.loads(meta)
    except (TypeError, ValueError):
        return []
    locs = d.get("locations") if isinstance(d, dict) else None
    if not isinstance(locs, list):
        return []
    return [x for x in locs if isinstance(x, str) and x]


def minting_tickets(ccon, sha):
    """The ticket(s) that MINTED this content address: `ticket_artifacts (id, ts, ticket_id, name,
    version, forge_sha, kind)` in the CONGRUENCY state db (migrations/0014_ticket_artifacts.sql:7-15
    — the table the `artifact.record` route writes, :18-26).

    THIS IS A JOIN ACROSS TWO DATABASE FILES, and that is the only way to get the minting ticket.
    The forge ledger's `artifacts` (config/forge/forge.db) and congruency's `ticket_artifacts` are
    different tables in different files — tools/vm_registry.py:96-109 documents the split in full.
    They meet on nothing but the sha256 content address, which is exactly what this joins on.

    An ABSENT state db yields NO tickets — the normal case in a pair worktree, where the db is
    git-ignored (.gitignore:11) and so is simply not there. That is the same answer a SOURCE match
    gets in the same worktree (attach_tickets), it is reported by the `tickets index:` line and by a
    note on the resolution, and it is never faked.
    """
    if ccon is None or not table_exists(ccon, "ticket_artifacts") or not sha:
        return []
    out = []
    for aid, tid, kind in ccon.execute(
            "SELECT id, ticket_id, kind FROM ticket_artifacts WHERE lower(forge_sha) = ? ORDER BY id",
            (sha,)):
        if tid is None:
            continue
        t = {"ticket": tid, "artifact_id": aid}
        if kind:
            t["kind"] = kind
        out.append(t)
    return out


def artifact_matches(rows, ccon):
    """ONE match per registered ARTIFACT — the #461 normalization, and the whole point of this file.

    Before #461 a forge-artifacts hit was printed as a side-note while the summary said "no match",
    so the resolver announced an answer and denied it in the same breath. It is a match now. It is
    NOT given a source's shape to get there: a VM image has no repo and no line-range, so those
    fields are ABSENT rather than zeroed. The shape is stated in AN ARTIFACT HIT IS A MATCH above.

    THE COLLAPSE, and why it mirrors de_overlap(). de_overlap gives back one match per REGION of
    source, however many indexes reached it. This gives back one match per CONTENT ADDRESS, however
    many times the ledger registered it: N registrations of one sha at N locations are ONE artifact
    carrying N locations, never N matches. That is what content addressing means, and it is how
    #455 already registers a VM (its `meta.locations`).

    `identifier_kind` is the REGISTERED kind (forge-vm, forge-source, xz, ...) when every
    registration of the sha agrees on one, and the generic 'artifact' when they disagree or none
    recorded one — both spellings the ticket names. It is read from the FORGE ledger alone, never
    from ticket_artifacts, so it does not change when the state db is absent.
    """
    by_sha = {}
    for r in rows:
        sha = (r.get("sha256") or "").strip().lower()
        if sha:
            by_sha.setdefault(sha, []).append(r)

    out = []
    for sha in sorted(by_sha):
        regs = sorted(by_sha[sha], key=lambda r: (r["id"] is None, r["id"]))
        locations, names, versions, kinds, vias, size = [], [], [], [], set(), None
        for r in regs:
            for loc in [r.get("filename")] + _meta_locations(r.get("meta")):
                if loc and loc not in locations:
                    locations.append(loc)
            for seq, val in ((names, r.get("name")), (versions, r.get("version")), (kinds, r.get("kind"))):
                if val and val not in seq:
                    seq.append(val)
            vias.add(r["via"])
            if size is None and isinstance(r.get("size"), int):
                size = r["size"]

        # EVERY FIELD IS EMITTED ONLY WHEN IT HAS A VALUE. There is no repo and no line-range here,
        # so there is no `repo`, `line_start` or `line_end` key at all — a null line_end already
        # MEANS something else in this collection ("named by the index, absent from the object
        # store", expand() below), and reusing it for a VM would be a lie the renderer would print
        # as `1-?`.
        art = {"registrations": len(regs)}
        for key, val in (("names", names), ("versions", versions), ("kinds", kinds)):
            if val:
                art[key] = val
        if size is not None:
            art["size"] = size

        m = {"identifier_kind": kinds[0] if len(kinds) == 1 else "artifact",
             "level": "artifact", "sha256": sha, "score": 1.0, "via": sorted(vias),
             "tickets": minting_tickets(ccon, sha), "artifact": art}
        if locations:
            m["path"] = locations[0]          # the primary location; `locations` carries them all
            m["locations"] = locations
        out.append(m)
    out.sort(key=lambda m: (m.get("path") or "", m["sha256"]))
    return out


# ── the resolution ───────────────────────────────────────────────────────────────────────────────
def open_sources(a, cs):
    """Every backing index, opened READ-ONLY. An absent one is None and is reported, never created."""
    if not os.path.isfile(a.omni_db):
        raise Fault("no omni-git index at %s — set OMNI_INDEX_DB or pass --omni-db "
                    "(the resolver reads the corpus, it never builds it)" % a.omni_db)
    if not os.path.isdir(a.omni_git):
        raise Fault("no omni-git object store at %s — set OMNI_GIT or pass --omni-git" % a.omni_git)
    ocon = open_ro(a.omni_db)
    tables = cs.omni_tables(ocon)
    for t in ("occ", "blob"):
        if t not in tables:
            raise Fault("%s has no `%s` table — wrong omni index?" % (a.omni_db, t))
    return {"omni": ocon, "omni_git": a.omni_git, "store": open_ro(a.store),
            "graph": open_ro(a.mem_graph_db), "forge": open_ro(a.forge_db),
            "cong": open_ro(a.congruency_db)}


def resolve(q, src, cs, opts):
    """The whole flow: detect -> fan out -> merge -> expand -> de-overlap -> attach tickets, then
    append any ARTIFACT the fan-out reached (#461) — which travels its own path, because it has no
    {repo, path, line-range, blob sha} for the four steps before it to work on."""
    kind = opts["kind"] if opts["kind"] and opts["kind"] != "auto" else detect_kind(q)
    if kind not in KINDS and kind != "similarity":
        raise Fault("unknown identifier kind %r — kinds are: auto, %s" % (kind, ", ".join(KINDS)))
    notes, artifacts, arts = [], [], []

    if opts["like"]:
        # "more like this": resolve the identifier first, then rank the store by ITS stored vectors.
        seed = resolve_to_shas(q, kind, src, opts, artifacts)
        if not seed:
            notes.append("--like: %r resolved to no blob, so there is nothing to be similar to" % q)
            hits = {}
        else:
            vecs = [v for sha, _seq, v in store_vectors(src["store"], opts["model"]) if sha in seed]
            if not vecs:
                notes.append("--like: %r resolved to %d blob(s), none of which the #189 store has "
                             "indexed — no vector to compare" % (q, len(seed)))
                hits = {}
            else:
                hits = similar_shas(src, opts, vecs)
                for sha, (sc, via) in graph_similar(src, list(seed), opts).items():
                    _add(hits, sha, sc, sorted(via)[0])
                for sha in seed:                                   # the seed itself is its own match
                    _add(hits, sha, 1.0, "code_sim:vector")
        kind_label = "similarity"
    elif kind == "text":
        vec = embed_query(cs, q, opts)
        hits = similar_shas(src, opts, [vec])
        for sha, (sc, via) in graph_similar(src, list(hits), opts).items():
            _add(hits, sha, sc, sorted(via)[0])
        kind_label = "similarity"
    else:
        hits = resolve_to_shas(q, kind, src, opts, artifacts)
        kind_label = kind
        # AN ARTIFACT HIT IS A MATCH (#461) — and ONLY here, on the EXACT path. The two similarity
        # branches above deliberately leave `arts` empty: a similarity query asks what is LIKE the
        # identifier, and a registered artifact is not a similarity answer — it is the thing itself,
        # reached by content address, with no vector to rank. Their collections are therefore exactly
        # what they were before #461, which is what the ticket requires.
        arts = artifact_matches(artifacts, src["cong"])

    matches = de_overlap(expand(src, hits, opts))
    for m in matches:
        m["identifier_kind"] = kind_label
    matches = attach_tickets(src["cong"], matches)
    # Artifacts are appended AFTER the source collection is complete, and are never fed through
    # expand/de_overlap/attach_tickets: those three read {repo, path, line-range, blob sha}, which an
    # artifact does not have. Appending leaves every source match, and their order, untouched.
    matches = matches + arts
    matches = [m for m in matches if m["score"] >= opts["min_score"]]
    if arts and not table_exists(src["cong"], "ticket_artifacts"):
        notes.append("an artifact's minting ticket comes from `ticket_artifacts` in the congruency "
                     "state db, which is not readable here (it is git-ignored, .gitignore:11, so it "
                     "is absent from a pair worktree) — pass --congruency-db <path>, or set "
                     "CONGRUENCY_SQLITE, to attach it")

    # the git object db across the bare repos: only for a blob-identity query, never for a search
    object_dbs = {}
    if opts["git_fanout"] and kind in ("git-blob", "sha256") and hits:
        repos = bare_repos(src["cong"])
        for sha in list(hits)[:8]:
            object_dbs[sha] = repos_holding(sha, repos)
        notes.append("git object db: probed %d bare repo(s) for %d blob(s)" % (len(repos), len(object_dbs)))

    return {"identifier": q, "identifier_kind": kind_label, "detected_kind": detect_kind(q),
            "probes": probes_for(kind) if not opts["like"] else ["similarity"],
            "blobs_resolved": len(hits), "artifacts_resolved": len(arts),
            "total_matches": len(matches),
            "matches": matches[:opts["limit"]], "truncated": len(matches) > opts["limit"],
            "object_dbs": object_dbs,
            "notes": notes,
            "tickets_index": "present" if src["cong"] is not None else "absent (no congruency db)"}


# ── rendering ────────────────────────────────────────────────────────────────────────────────────
def render(res):
    print("identifier: %r" % res["identifier"])
    print("  kind:     %s%s" % (res["identifier_kind"],
                                "" if res["identifier_kind"] == res["detected_kind"]
                                else " (detected: %s)" % res["detected_kind"]))
    print("  probes:   %s" % ", ".join(res["probes"]))
    # The artifact count appears ONLY when there is one, so a source resolution's summary is the
    # line it has always been. There is no separate "forge artifacts:" line any more: an artifact is
    # in the collection below, counted here, and #461 exists because announcing it beside a "no
    # match" summary taught the reader to distrust both.
    print("  resolved: %d blob(s)%s -> %d de-overlapped match(es)%s"
          % (res["blobs_resolved"],
             " + %d artifact(s)" % res["artifacts_resolved"] if res["artifacts_resolved"] else "",
             res["total_matches"],
             "; showing %d" % len(res["matches"]) if res["truncated"] else ""))
    print("  tickets index: %s" % res["tickets_index"])
    for n in res["notes"]:
        print("  note: %s" % n)
    for sha, repos in (res["object_dbs"] or {}).items():
        print("  object db %s: %s" % (sha[:12], ", ".join(repos) if repos else "(in no bare repo)"))
    if not res["matches"]:
        print("\n  (no match — the collection is empty)")
        return
    # The PATH is printed last and IN FULL, never truncated: two occurrences of one duplicated blob
    # routinely differ only in a leading path segment, and clipping them would render distinct
    # matches as identical-looking rows. Only the repo is abbreviated, and visibly (with a '…').
    print("\n%-6s %-11s %-24s %-8s %s" % ("score", "lines", "symbol", "tickets", "repo :: path"))
    print("-" * 118)
    for m in res["matches"]:
        tix = ",".join("#%s" % t["ticket"] for t in m["tickets"]) or "-"
        if m.get("level") == "artifact":
            # A registered artifact: no repo, no line-range. The columns say so in words rather than
            # borrowing a number that would read as source. Its extra locations follow on their own
            # rows — ONE artifact, several locations, never several matches.
            lines = "(artifact)"
            sym = "/".join(m["artifact"].get("names", [])) or "(unnamed)"
            repo = "(no repo)"
            path = m.get("path") or "(no registered location)"
        else:
            if m["line_end"] == 0:
                lines = "(empty)"                   # a zero-byte blob: no lines to point at
            elif m["line_end"] is None:
                lines = "1-?"                       # named by the index, absent from the object store
            else:
                lines = "%s-%s" % (m["line_start"], m["line_end"])
            sym = (("%s.%s" % (m["namespace"], m["symbol"])) if m.get("namespace") and m.get("symbol")
                   else (m.get("symbol") or ("(empty file)" if m["line_end"] == 0 else "(whole file)")))
            repo = m["repo"] if len(m["repo"]) <= 34 else m["repo"][:33] + "…"
            path = m["path"]
        print("%-6.4f %-11s %-24s %-8s %s :: %s"
              % (m["score"], lines, sym[:24], tix, repo, path))
        for loc in (m.get("locations") or [])[1:]:
            print("%-6s %-11s %-24s %-8s %s :: %s" % ("", "", "(also at)", "", "(no repo)", loc))


def show_indexes(a, src):
    """Every backing index, its resolved path, whether it is present, and what it holds — so the
    tool's reach is legible without reading its code."""
    def count(con, tbl):
        if con is None or not table_exists(con, tbl):
            return "(absent)"
        return con.execute('SELECT COUNT(*) FROM "%s"' % tbl).fetchone()[0]

    print("the resolver's backing indexes (all opened read-only; none is ever built or written)\n")
    rows = [
        ("omni-git index", a.omni_db, src["omni"] is not None,
         "occ=%s blob=%s" % (count(src["omni"], "occ"), count(src["omni"], "blob"))),
        ("omni-git objects", a.omni_git, os.path.isdir(a.omni_git), "bare git object store"),
        ("#189 vector store", a.store, src["store"] is not None,
         "blobs=%s chunks=%s occurrences=%s" % (count(src["store"], "blobs"), count(src["store"], "chunks"),
                                                count(src["store"], "occurrences"))),
        ("mem-graph", a.mem_graph_db, src["graph"] is not None,
         "node=%s edge=%s" % (count(src["graph"], "node"), count(src["graph"], "edge"))),
        ("forge ledger", a.forge_db, src["forge"] is not None, "artifacts=%s" % count(src["forge"], "artifacts")),
        ("congruency (tickets)", a.congruency_db, src["cong"] is not None,
         "ticket_works=%s" % count(src["cong"], "ticket_works")),
    ]
    for name, path, present, detail in rows:
        print("  %-22s %-7s %s" % (name, "present" if present else "ABSENT", detail))
        print("  %-22s %s" % ("", path))
    repos = bare_repos(src["cong"])
    print("  %-22s %-7s %d bare repo(s) (the git object db fan-out for a blob identity)"
          % ("bare repos", "present" if repos else "ABSENT", len(repos)))
    return 0


# ── the acceptance: the ticket's claim, PROVED against the live corpus ───────────────────────────
def find_specimen(src, opts):
    """A blob that can prove the ticket's acceptance, DISCOVERED from the live corpus (never
    hard-coded, so the proof is about the corpus and not about a constant in this file). It must be:

      (a) DUPLICATED   — the ticket says "the SAME piece of duplicated source": >= 2 occurrences;
      (b) INDEXED      — in the #189 store with >= 1 chunk, so it has a name, a line-range and a
                         vector (without a vector there is no similarity leg to run);
      (c) UNAMBIGUOUS  — its path basename belongs to exactly ONE blob in the whole omni corpus, so
                         the file-name identifier denotes THIS source and not a family of files.
                         (`__init__.py`, for instance, is shared by 180 distinct blobs and so names
                         no single piece of source — it is correctly rejected here.)
    Returns (sha, basename, symbol) or None.
    """
    ocon, scon = src["omni"], src["store"]
    if scon is None:
        return None
    for (sha,) in scon.execute("SELECT DISTINCT sha FROM chunks WHERE model = ? ORDER BY sha", (opts["model"],)):
        occ = ocon.execute("SELECT DISTINCT repo, path FROM occ WHERE sha = ?", (sha,)).fetchall()
        if len(occ) < 2:
            continue                                                    # (a) not duplicated
        bns = {p.rsplit("/", 1)[-1] for _r, p in occ}
        if len(bns) != 1:
            continue                                                    # one file-name for the source
        bn = bns.pop()
        n_other = ocon.execute("SELECT COUNT(DISTINCT sha) FROM occ WHERE path = ? OR path LIKE ?",
                               (bn, "%/" + bn)).fetchone()[0]
        if n_other != 1:
            continue                                                    # (c) ambiguous file-name
        syms = [r[0] for r in scon.execute(
            "SELECT symbol FROM chunks WHERE sha = ? AND model = ? ORDER BY chunk_seq", (sha, opts["model"]))]
        if not syms:
            continue                                                    # (b) no chunk
        return sha, bn, syms[0]
    return None


def ledger_oracle(src):
    """THE ACCEPTANCE'S ORACLE: what the two registries SAY, read straight, with this function's own
    reading of the schema —

        {sha256: {"locations": [...], "names": [...], "kinds": [...], "registrations": n,
                  "tickets": [ticket_id, ...]}}

    IT IS DELIBERATELY NOT artifact_matches(). An expectation produced by the code under test cannot
    fail, and this is not hypothetical: with the expectation taken from artifact_matches(), deleting
    the whole `meta.locations` half of a location list left --acceptance green at 31/31, because the
    defect moved both sides of the comparison together. Read straight from the two dbs, the same
    deletion turns it red. Every #461 check below compares the resolver's answer to THIS.

    `locations` is `filename` then `meta.locations`, in registration order, de-duplicated;
    `tickets` is ticket_artifacts joined on the sha256 content address, and is empty when that db is
    absent (a pair worktree), which the caller SKIPS on rather than failing.
    """
    out = {}
    fcon, ccon = src["forge"], src["cong"]
    if fcon is None or not table_exists(fcon, "artifacts"):
        return out
    for sha, name, version, kind, filename, meta in fcon.execute(
            "SELECT lower(sha256), name, version, kind, filename, meta FROM artifacts "
            "WHERE sha256 IS NOT NULL AND sha256 != '' ORDER BY id"):
        e = out.setdefault(sha, {"locations": [], "names": [], "kinds": [], "registrations": 0,
                                 "tickets": []})
        e["registrations"] += 1
        cands = [filename]
        try:
            d = json.loads(meta) if meta else None
        except (TypeError, ValueError):
            d = None
        if isinstance(d, dict) and isinstance(d.get("locations"), list):
            cands += d["locations"]
        for seq, vals in ((e["locations"], cands), (e["names"], [name]), (e["kinds"], [kind])):
            for v in vals:
                if isinstance(v, str) and v and v not in seq:
                    seq.append(v)
    if ccon is not None and table_exists(ccon, "ticket_artifacts"):
        for sha, tid in ccon.execute("SELECT lower(forge_sha), ticket_id FROM ticket_artifacts "
                                     "WHERE forge_sha IS NOT NULL AND ticket_id IS NOT NULL ORDER BY id"):
            if sha in out and tid not in out[sha]["tickets"]:
                out[sha]["tickets"].append(tid)
    return out


def find_artifact_specimens(src):
    """The artifacts that prove #461, DISCOVERED from the live ledger (via ledger_oracle) and never
    hard-coded, so the proof is about the ledger and not about a constant in this file. Returns

        {"any":   (sha, expectation) for a registered artifact — one the ledger says has a MINTING
                  TICKET if any does, since that is the half of the shape only ticket_artifacts
                  can fill;
         "multi": (sha, expectation) for a content address registered at TWO OR MORE locations — the
                  "one sha, many locations, ONE artifact" case. A sha carrying several REGISTRATIONS
                  is preferred over one whose locations all came from a single row's meta, because
                  collapsing two ledger ROWS into one match is the harder half of the claim. None if
                  the ledger holds no multi-location artifact.}

    or None when the forge ledger is absent or holds no registered artifact at all.
    """
    oracle = ledger_oracle(src)
    if not oracle:
        return None
    shas = sorted(oracle)
    with_ticket = [s for s in shas if oracle[s]["tickets"]]
    multi = sorted((s for s in shas if len(oracle[s]["locations"]) >= 2),
                   key=lambda s: (-oracle[s]["registrations"], s))   # the multi-ROW case first
    any_sha = (with_ticket or shas)[0]
    return {"any": (any_sha, oracle[any_sha]),
            "multi": (multi[0], oracle[multi[0]]) if multi else None}


def find_unregistered_sha256(src, opts):
    """A sha256 that is registered NOWHERE and is no blob's content either — derived
    deterministically, then CHECKED against both indexes that could answer it, so "0 matches" is a
    proof and not a coincidence. Returns None in the (impossible in practice) event that 64
    candidates all collide.
    """
    known = sha256_index(src["omni"], src["omni_git"], opts.get("all_blobs")) if src["omni_git"] else {}
    for i in range(64):
        cand = hashlib.sha256(("resolver.py #461 unregistered probe %d" % i).encode()).hexdigest()
        if cand in known:
            continue
        if forge_artifact_rows(src["forge"], "lower(sha256) = ?", (cand,), "probe"):
            continue
        return cand
    return None


def artifact_acceptance(src, cs, opts, checks, results):
    """PROVE ticket #461 on the live ledger: an artifact hit IS a match.

    Every check here is the ticket's own acceptance, run against the live forge ledger:
      * a registered sha256 returns >= 1 match naming its location, with the identifier-kind
        reflecting the artifact and the minting ticket present — and NOT the words "no match";
      * --json carries that match in the collection, not only in prose;
      * a sha registered at several locations is ONE match carrying all of them;
      * a sha registered nowhere is still 0 matches, and still says so;
      * the source legs are untouched — no artifact leaked into them.
    Appends to `checks`; prints what it found. A missing piece SKIPS loudly and is never a pass.
    """
    print("\nTHE FORGE ARTIFACTS (ticket #461: an artifact hit must BE a match)")
    specs = find_artifact_specimens(src)
    if specs is None:
        print("  SKIPPED: the forge ledger is absent or holds no registered artifact, so there is "
              "no artifact to resolve. Every check above still ran.")
        return

    o = dict(opts, kind="auto", like=False, limit=10000, min_score=0.0)

    def artifacts_for(sha):
        """(the resolver's artifact matches for `sha`, its whole result, its RENDERED output)."""
        r = resolve(sha, src, cs, o)
        b = io.StringIO()
        with contextlib.redirect_stdout(b):
            render(r)                    # the REAL rendered output, not a paraphrase of it
        return [x for x in r["matches"] if x.get("level") == "artifact" and x.get("sha256") == sha], \
            r, b.getvalue()

    # ── the headline: the sha that printed its own answer and then denied it ─────────────────────
    sha_a, want = specs["any"]
    art, res, text = artifacts_for(sha_a)
    loc = (want["locations"] or ["(no registered location)"])[0]

    print("  specimen artifact (discovered from the ledger, not hard-coded)")
    print("    sha256:        %s" % sha_a)
    print("    the ledger SAYS: %d registration(s), kind=%s, name=%s"
          % (want["registrations"], ",".join(want["kinds"]) or "(none)",
             ",".join(want["names"]) or "(none)"))
    for x in want["locations"]:
        print("        location: %s" % x)
    print("    the resolver ANSWERS: %d artifact match(es), %d total match(es) in the collection"
          % (len(art), res["total_matches"]))

    checks.append(("#461 artifact: its sha256 returns >= 1 match", len(art) >= 1))
    checks.append(("#461 artifact: EXACTLY one match for the sha (one artifact, not one per "
                   "registration — the ledger holds %d)" % want["registrations"], len(art) == 1))
    checks.append(("#461 artifact: it is COUNTED — total_matches >= 1", res["total_matches"] >= 1))
    checks.append(('#461 artifact: the rendered output does NOT say "no match" (it said both, #461)',
                   "no match" not in text))
    checks.append(("#461 artifact: the rendered output NAMES its location %r" % loc, loc in text))
    if not art:
        return                            # every remaining check reads the match; do not fake them
    m = art[0]

    checks.append(("#461 artifact: identifier-kind %r is the kind the LEDGER registered (%s)"
                   % (m["identifier_kind"], ",".join(want["kinds"]) or "none"),
                   m["identifier_kind"] == (want["kinds"][0] if len(want["kinds"]) == 1 else "artifact")))
    checks.append(("#461 artifact: NO faked source shape — no `repo`, no `line_start`, no `line_end`",
                   not any(k in m for k in ("repo", "line_start", "line_end"))))
    checks.append(("#461 artifact: score is 1.0, as the other probes score an exact content hit",
                   m["score"] == 1.0))
    checks.append(("#461 artifact: --json carries it in `matches`, not on a side channel",
                   any(j.get("sha256") == sha_a and j.get("level") == "artifact"
                       for j in json.loads(json.dumps(res))["matches"])))
    checks.append(("#461 artifact: its locations are EXACTLY the %d the ledger records"
                   % len(want["locations"]),
                   sorted(m.get("locations", [])) == sorted(want["locations"])))

    if table_exists(src["cong"], "ticket_artifacts"):
        checks.append(("#461 artifact: the minting ticket_id(s) from ticket_artifacts are present "
                       "and are EXACTLY what that table records (%s)"
                       % (",".join("#%s" % t for t in want["tickets"]) or "none"),
                       bool(want["tickets"]) and
                       sorted(t["ticket"] for t in m["tickets"]) == sorted(want["tickets"])))
    else:
        print("    minting ticket: SKIPPED — no readable `ticket_artifacts`. The congruency state db "
              "is git-ignored (.gitignore:11) and so is absent from a pair worktree; pass "
              "--congruency-db <path> to run this check.")

    # ── one sha, many locations, ONE artifact ────────────────────────────────────────────────────
    if specs["multi"] is None:
        print("    many locations: SKIPPED — no content address in this ledger is registered at two "
              "or more locations, so the case cannot be proved here.")
    else:
        msha, mwant = specs["multi"]
        mart, _mres, _mtext = artifacts_for(msha)
        locs = mart[0].get("locations", []) if mart else []
        print("    many locations: %s -> %d match(es) carrying %d location(s); the ledger records "
              "%d across %d registration(s)"
              % (msha[:12], len(mart), len(locs), len(mwant["locations"]), mwant["registrations"]))
        for x in mwant["locations"]:
            print("        %s%s" % ("    " if x in locs else "MISSING ", x))
        checks.append(("#461 one sha, many locations: ONE match, not one per location", len(mart) == 1))
        checks.append(("#461 one sha, many locations: that ONE match carries all %d the ledger "
                       "records" % len(mwant["locations"]),
                       sorted(locs) == sorted(mwant["locations"]) and len(locs) >= 2))

    # ── a sha registered nowhere is still nothing, and still says so ─────────────────────────────
    unreg = find_unregistered_sha256(src, opts)
    if unreg is None:
        print("    unregistered sha256: SKIPPED — every candidate collided with the corpus (this "
              "cannot happen in practice; if you are reading it, say so on the ticket).")
    else:
        ures = resolve(unreg, src, cs, o)
        ubuf = io.StringIO()
        with contextlib.redirect_stdout(ubuf):
            render(ures)
        print("    unregistered sha256 %s... -> %d match(es)" % (unreg[:12], ures["total_matches"]))
        checks.append(("#461 a sha256 registered NOWHERE still returns 0 matches (no false positive)",
                       ures["total_matches"] == 0))
        checks.append(('#461 ... and still SAYS so ("no match") — the honest empty answer survives',
                       "no match" in ubuf.getvalue()))

    # ── additive: the source path is untouched ───────────────────────────────────────────────────
    checks.append(("#461 additive: no artifact match leaked into any of the source legs above",
                   not any(x.get("level") == "artifact"
                           for r, _rows in results.values() for x in r["matches"])))


def acceptance(src, cs, opts):
    """PROVE the ticket's ACCEPTANCE on the live corpus, read-only.

    THE CLAIM, stated exactly as it is checked: "the SAME piece of duplicated source is reachable by
    its name, its file-name, its content sha256, its git blob hash, and by similarity — all resolve
    to the same match set." So for each of those five identifiers this checks BOTH halves:
        REACHABLE      — the specimen's rows are PRESENT in the returned collection; and
        SAME MATCH SET — those rows, as {repo, path, line_start, line_end}, are IDENTICAL to the
                         first identifier's.
    A similarity query legitimately ALSO surfaces the specimen's neighbours — that is what
    similarity is for — so what is compared is the specimen's own rows, and the neighbour count is
    printed rather than hidden. The four exact identifiers are additionally checked to return the
    specimen's rows and NOTHING else.

    THEN #461's claim — "an artifact hit must BE a match" — is proved on the live forge ledger by
    artifact_acceptance() below, on a specimen discovered the same way. Every check prints PASS or
    FAIL; exit 1 if any FAILED. A check whose input the host does not have (the litellm proxy, the
    congruency state db, a ledger with no artifact) is SKIPPED in words, never silently, and a SKIP
    is never counted as a pass.
    """
    spec = find_specimen(src, opts)
    if not spec:
        raise Fault("no qualifying specimen in the live corpus: the acceptance needs a blob that is "
                    "duplicated (>=2 occurrences), indexed by #189 (>=1 chunk, so it has a vector), "
                    "and whose file-name belongs to exactly one blob. Index more of the corpus with "
                    "tools/code_sim_indexer.py, then re-run.")
    sha, basename, symbol = spec
    body = batch_blobs(src["omni_git"], [sha]).get(sha)
    if body is None:
        raise Fault("specimen %s is in the index but not in the object store at %s" % (sha, src["omni_git"]))
    content_sha256 = hashlib.sha256(body).hexdigest()

    print("THE SPECIMEN (discovered from the live corpus, not hard-coded)")
    print("  git blob hash:  %s" % sha)
    print("  content sha256: %s" % content_sha256)
    print("  file-name:      %s" % basename)
    print("  name (symbol):  %s" % symbol)
    occ = src["omni"].execute("SELECT DISTINCT repo, path FROM occ WHERE sha = ? ORDER BY repo, path",
                              (sha,)).fetchall()
    print("  duplicated at %d occurrence(s):" % len(occ))
    for repo, path in occ:
        print("      %s :: %s" % (repo, path))

    def rows_of(res):
        """The specimen's OWN rows in a collection, as the comparable match set.

        Keyed on the specimen's BLOB sha, which an artifact match does not carry — so an artifact,
        should one ever share this collection, is filtered out before its (absent) {repo, path,
        line-range} is ever read. The specimen is source; only source rows can be its match set.
        """
        return sorted((m["repo"], m["path"], m["line_start"], m["line_end"])
                      for m in res["matches"] if sha in m.get("blob_shas", []))

    legs = [("name", symbol, dict(opts, kind="auto", like=False)),
            ("file-name", basename, dict(opts, kind="auto", like=False)),
            ("content sha256", content_sha256, dict(opts, kind="auto", like=False)),
            ("git blob hash", sha, dict(opts, kind="auto", like=False)),
            ("similarity (--like, offline)", basename, dict(opts, kind="auto", like=True,
                                                            min_score=SIM_MIN_SCORE))]

    print("\nTHE FIVE IDENTIFIERS")
    checks, reference, results = [], None, {}
    for label, ident, o in legs:
        o = dict(o, limit=10000)
        res = resolve(ident, src, cs, o)
        rows = rows_of(res)
        results[label] = (res, rows)
        if reference is None:
            reference = rows
        checks.append(("%s: REACHABLE — %r resolves to the specimen" % (label, ident), bool(rows)))
        checks.append(("%s: SAME MATCH SET — its rows equal the first identifier's" % label,
                       rows == reference))
        extra = res["total_matches"] - len(rows)
        print("  %-30s -> %d specimen row(s), %d other row(s) [kind=%s, via %s]"
              % (label, len(rows), extra, res["identifier_kind"],
                 ",".join(sorted({v for m in res["matches"] for v in m["via"]})) or "-"))

    # the four exact identifiers must return the specimen and NOTHING else
    for label in ("name", "file-name", "content sha256", "git blob hash"):
        res, rows = results[label]
        checks.append(("%s: the collection is EXACTLY the specimen's match set (no extras)" % label,
                       res["total_matches"] == len(rows)))
    # similarity legitimately returns neighbours; what it must do is RANK the specimen first
    sres, srows = results["similarity (--like, offline)"]
    checks.append(("similarity: the specimen ranks first (score %.4f)"
                   % (sres["matches"][0]["score"] if sres["matches"] else 0.0),
                   bool(sres["matches"]) and sha in sres["matches"][0].get("blob_shas", [])))

    # the similarity leg through the litellm proxy: the REAL #190 path (text -> embed -> cosine).
    # Skipped, loudly, if the proxy is down — never silently, and never counted as a pass.
    chunk_src = None
    if src["store"] is not None:
        row = src["store"].execute("SELECT text FROM chunks WHERE sha = ? AND model = ? ORDER BY chunk_seq "
                                   "LIMIT 1", (sha, opts["model"])).fetchone()
        chunk_src = row[0] if row else None
    if chunk_src:
        try:
            o = dict(opts, kind="text", like=False, min_score=SIM_MIN_SCORE, limit=10000)
            res = resolve(chunk_src, src, cs, o)
            rows = rows_of(res)
            checks.append(("similarity (proxy, text->embed->cosine): REACHABLE", bool(rows)))
            checks.append(("similarity (proxy, text->embed->cosine): SAME MATCH SET", rows == reference))
            print("  %-30s -> %d specimen row(s), %d other row(s) [top score %.4f]"
                  % ("similarity (proxy)", len(rows), res["total_matches"] - len(rows),
                     res["matches"][0]["score"] if res["matches"] else 0.0))
        except EmbedError as e:
            print("  %-30s -> SKIPPED: the litellm proxy is unreachable (%s). The offline "
                  "similarity leg above still ran." % ("similarity (proxy)", e))

    # the de-overlap guarantee, checked on the widest collection the acceptance produced
    widest = max((r for r, _rows in results.values()), key=lambda r: r["total_matches"])
    seen, overlap = {}, False
    for m in widest["matches"]:
        if m.get("level") == "artifact":
            continue        # no {repo, path, line-range} to overlap; its own invariant is checked
        key = (m["repo"], m["path"])
        for lo, hi in seen.get(key, []):
            if (m["line_start"] or 0) <= hi and (m["line_end"] or 0) >= lo:
                overlap = True
        seen.setdefault(key, []).append((m["line_start"] or 0, m["line_end"] or 0))
    checks.append(("de-overlapped: no two matches share a {repo, path} and overlap in lines", not overlap))

    artifact_acceptance(src, cs, opts, checks, results)

    print("\nTHE CHECKS")
    good = True
    for what, ok in checks:
        print("  [%s] %s" % ("PASS" if ok else "FAIL", what))
        good = good and ok
    print("\n%s — %d/%d checks passed" % ("ACCEPTANCE PROVED" if good else "ACCEPTANCE FAILED",
                                          sum(1 for _w, ok in checks if ok), len(checks)))
    return 0 if good else 1


# ── the MCP tool: JSON-RPC 2.0 over stdio, one object per line ───────────────────────────────────
# An MCP server here is a process speaking JSON-RPC 2.0 over stdin/stdout, one JSON object per line,
# implemented with the standard library alone and no `mcp` SDK — the protocol and that choice are
# both tools/ticket_api_mcp.py:6-10, and this mirrors its implementation at :417-493. stdout carries
# the protocol ONLY: a stray byte there corrupts it, so notices go to stderr (ticket_api_mcp.py:419-421).
MCP_TOOLS = {
    "resolve": {
        "description": "The universal resolver: auto-detect an identifier's kind (git blob hash, "
                       "content sha256, uuid, mem-graph node id, ticket, path, file-name, symbol "
                       "name, or free text), fan out to every backing index, and return ONE "
                       "normalized de-overlapped collection of {repo, path, line-range, "
                       "identifier-kind, tickets, score}. A sha256 may also resolve to a registered "
                       "forge ARTIFACT (a VM image, a wheel, a seed); such a match has level="
                       "'artifact', carries `locations` and `sha256`, and has NO repo and NO "
                       "line-range — branch on `level`. Read-only.",
        "properties": {
            "identifier": {"type": "string", "description": "the identifier to resolve"},
            "kind": {"type": "string", "description": "override detection: one of auto, " + ", ".join(KINDS)},
            "like": {"type": "boolean", "description": "resolve the identifier, then return source "
                                                       "SIMILAR to it (needs no network)"},
            "limit": {"type": "integer", "description": "max matches to return (default %d)" % DEFAULT_LIMIT},
            "min_score": {"type": "number", "description": "drop matches scoring below this"},
            "repo": {"type": "string", "description": "restrict matches to one repo"},
        },
        "required": ["identifier"],
    },
    "resolve_indexes": {
        "description": "The backing indexes the resolver reads, each with its resolved path, whether "
                       "it is present, and its row counts. Read-only.",
        "properties": {}, "required": [],
    },
}


def mcp_tool_spec(name):
    t = MCP_TOOLS[name]
    return {"name": name, "description": t["description"],
            "inputSchema": {"type": "object", "properties": t["properties"], "required": list(t["required"])}}


def mcp_call(name, args, ctx):
    if name == "resolve_indexes":
        src, a = ctx["src"], ctx["args"]
        def count(con, tbl):
            return None if (con is None or not table_exists(con, tbl)) else \
                con.execute('SELECT COUNT(*) FROM "%s"' % tbl).fetchone()[0]
        return {"omni_index": {"path": a.omni_db, "present": src["omni"] is not None,
                               "occ": count(src["omni"], "occ"), "blob": count(src["omni"], "blob")},
                "omni_git": {"path": a.omni_git, "present": os.path.isdir(a.omni_git)},
                "code_sim_store": {"path": a.store, "present": src["store"] is not None,
                                   "chunks": count(src["store"], "chunks"),
                                   "occurrences": count(src["store"], "occurrences")},
                "mem_graph": {"path": a.mem_graph_db, "present": src["graph"] is not None,
                              "node": count(src["graph"], "node"), "edge": count(src["graph"], "edge")},
                "forge": {"path": a.forge_db, "present": src["forge"] is not None,
                          "artifacts": count(src["forge"], "artifacts")},
                "congruency_tickets": {"path": a.congruency_db, "present": src["cong"] is not None,
                                       "ticket_works": count(src["cong"], "ticket_works")},
                "bare_repos": len(bare_repos(src["cong"]))}
    ident = args.get("identifier")
    if not ident:
        raise ValueError("missing required parameter 'identifier' for resolve")
    kind = args.get("kind") or "auto"
    if kind != "auto" and kind not in KINDS:
        raise ValueError("unknown kind %r — kinds are: auto, %s" % (kind, ", ".join(KINDS)))
    opts = dict(ctx["opts"], kind=kind, like=bool(args.get("like")),
                limit=int(args.get("limit") or DEFAULT_LIMIT), repo=args.get("repo") or "")
    if args.get("min_score") is not None:
        opts["min_score"] = float(args["min_score"])
    elif args.get("like") or detect_kind(ident) == "text":
        opts["min_score"] = SIM_MIN_SCORE
    return resolve(ident, ctx["src"], ctx["cs"], opts)


def mcp_handle(req, ctx):
    rid = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}
    is_note = "id" not in req

    def ok(result):
        return None if is_note else {"jsonrpc": "2.0", "id": rid, "result": result}

    def err(code, message):
        return None if is_note else {"jsonrpc": "2.0", "id": rid,
                                     "error": {"code": code, "message": message}}
    try:
        if method == "initialize":
            want = params.get("protocolVersion")
            return ok({"protocolVersion": want if want in MCP_PROTOCOL_VERSIONS else MCP_PROTOCOL_VERSIONS[0],
                       "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION}})
        if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
            return None
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": [mcp_tool_spec(n) for n in sorted(MCP_TOOLS)]})
        if method == "tools/call":
            name = params.get("name")
            if name not in MCP_TOOLS:
                return err(-32601, "no such tool: %r (this server offers: %s)"
                           % (name, ", ".join(sorted(MCP_TOOLS))))
            out = mcp_call(name, params.get("arguments") or {}, ctx)
            return ok({"content": [{"type": "text", "text": json.dumps(out, indent=2)}], "isError": False})
        return err(-32601, "method not found: %r" % method)
    except (ValueError, Fault) as e:
        return err(-32602, str(e))
    except EmbedError as e:
        return err(-32603, "the litellm embedding proxy is unreachable: %s" % e)
    except Exception as e:  # noqa: BLE001 — one bad call must never kill the server
        bug_report("mcp_handle", e, "MCP %s params=%r" % (method, params), e)
        return err(-32603, "internal error in %s: %s" % (method, e))


def mcp_serve(ctx):
    """Read JSON-RPC lines on stdin, write responses on stdout. Notices go to STDERR, because stdout
    is the protocol channel and a stray byte there corrupts it (ticket_api_mcp.py:419-421)."""
    sys.stderr.write("resolver: MCP serving tools=%s\n" % ",".join(sorted(MCP_TOOLS)))
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
        resp = mcp_handle(req, ctx)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


# ── main ─────────────────────────────────────────────────────────────────────────────────────────
def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    cs = load_indexer()
    ap = argparse.ArgumentParser(
        description="the universal resolver (#193): auto-detect an identifier's kind, fan out to "
                    "every backing index, return one normalized de-overlapped match collection. "
                    "Read-only: it reuses omni-git and the #189 vector index and rebuilds nothing.",
        epilog="kinds: auto (default), " + ", ".join(KINDS))
    ap.add_argument("identifier", nargs="?", default="",
                    help="what to resolve: a git blob hash, a content sha256, a uuid, a mem-graph "
                         "node id, '#N', a path, a file-name, a symbol name, or free text")
    ap.add_argument("--kind", default="auto", help="override kind detection (default: auto)")
    ap.add_argument("--like", action="store_true",
                    help="resolve the identifier, then return source SIMILAR to it (no network)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help="max matches to return (default: %d)" % DEFAULT_LIMIT)
    ap.add_argument("--min-score", type=float, default=None,
                    help="drop matches below this score (default: 0 exact, %s similarity)" % SIM_MIN_SCORE)
    ap.add_argument("--repo", default="", help="restrict matches to one repo in the corpus")
    ap.add_argument("--all-blobs", action="store_true",
                    help="sha256 over EVERY blob, not just text ones (for a binary's sha256)")
    ap.add_argument("--no-git-fanout", action="store_true",
                    help="skip probing the bare repos' object dbs for a blob identity (~2.6s)")
    ap.add_argument("--json", action="store_true", help="print the collection as JSON")
    ap.add_argument("--indexes", action="store_true", help="print the backing indexes and exit")
    ap.add_argument("--acceptance", action="store_true",
                    help="PROVE #193's and #461's acceptance against the live corpus; writes nothing")
    ap.add_argument("--mcp", action="store_true", help="serve the resolver as an MCP tool over stdio")
    ap.add_argument("--omni-db", default=cs.OMNI_DB, help="omni-git index (default: %s)" % cs.OMNI_DB)
    ap.add_argument("--omni-git", default=cs.OMNI_GIT, help="omni-git objects (default: %s)" % cs.OMNI_GIT)
    ap.add_argument("--store", default=cs.STORE, help="#189 vector store (default: %s)" % cs.STORE)
    ap.add_argument("--mem-graph-db", default=MEM_GRAPH_DB, help="mem-graph (default: %s)" % MEM_GRAPH_DB)
    ap.add_argument("--forge-db", default=FORGE_DB, help="forge ledger (default: %s)" % FORGE_DB)
    ap.add_argument("--congruency-db", default=CONGRUENCY_DB,
                    help="congruency state db, for associated tickets (default: %s)" % CONGRUENCY_DB)
    ap.add_argument("--litellm", default=cs.LITELLM, help="litellm proxy (default: %s)" % cs.LITELLM)
    ap.add_argument("--model", default=cs.MODEL, help="embedding model (default: %s)" % cs.MODEL)
    ap.add_argument("--timeout", type=int, default=120, help="embed timeout secs (default: 120)")
    a = ap.parse_args()

    if a.kind != "auto" and a.kind not in KINDS:
        print("resolver: unknown --kind %r — kinds are: auto, %s" % (a.kind, ", ".join(KINDS)))
        return 2
    if not (a.identifier or a.indexes or a.acceptance or a.mcp):
        ap.error("give an identifier to resolve, or one of --indexes / --acceptance / --mcp")

    src = open_sources(a, cs)
    try:
        if a.indexes:
            return show_indexes(a, src)

        is_sim = a.like or (a.kind == "text") or (a.kind == "auto" and detect_kind(a.identifier) == "text")
        opts = {"kind": a.kind, "like": a.like, "limit": max(1, a.limit),
                "min_score": a.min_score if a.min_score is not None else (SIM_MIN_SCORE if is_sim else 0.0),
                "repo": a.repo, "all_blobs": a.all_blobs, "git_fanout": not a.no_git_fanout,
                "model": a.model, "litellm": a.litellm, "timeout": a.timeout}

        if a.acceptance:
            return acceptance(src, cs, dict(opts, git_fanout=False))
        if a.mcp:
            return mcp_serve({"src": src, "cs": cs, "args": a,
                              "opts": dict(opts, git_fanout=False, min_score=0.0)})

        if src["store"] is None and (is_sim or a.like):
            raise Fault("no #189 vector store at %s — a similarity query has nothing to search; "
                        "build it with tools/code_sim_indexer.py" % a.store)
        res = resolve(a.identifier, src, cs, opts)
        if a.json:
            print(json.dumps(res, indent=2))
        else:
            render(res)
        return 0
    finally:
        for k in ("omni", "store", "graph", "forge", "cong"):
            if src.get(k) is not None:
                src[k].close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as e:
        print("resolver: %s" % e)
        sys.exit(2)
    except EmbedError as e:
        print("resolver: %s" % e)
        sys.exit(3)
    except BrokenPipeError:
        sys.exit(0)                                   # `| head` closed the pipe — not an error
    except KeyboardInterrupt:
        print("resolver: interrupted")
        sys.exit(130)
    except Exception as e:  # noqa: BLE001 — note-for-claude: file a timestamped report, never a traceback
        bug_report("main", e, " ".join(sys.argv), e)
        print("resolver: unexpected error: %s (a bug report was filed to %s)"
              % (e, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl")))
        sys.exit(2)
