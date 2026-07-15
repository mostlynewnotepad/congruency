#!/usr/bin/env python3
"""source_dedup.py — THE SOURCE DEDUP ENGINE (ticket #194): take the resolver's match collection
and CLUSTER it into `canonical + duplicates`, with a read-only recommendation for each cluster.

WHAT IT IS FOR. The forge corpus is massively duplicated: omni's `occ` holds 110,483 occurrence rows
over only 6,754 DISTINCT blobs. The universal resolver (#193, tools/resolver.py) answers "WHERE is
this source?" — it hands back one normalized, de-overlapped collection of
    {repo, path, line-range, identifier-kind, associated tickets, score}
This tool answers the NEXT question: "which of those are THE SAME SOURCE, which ONE should we keep,
and what should happen to the rest?" It consumes the resolver's collection, groups it into clusters
of duplicates, names ONE canonical per cluster, and lists every other member as a duplicate with its
location and its associated tickets, plus a per-member recommendation.

Every invocation below was run against the LIVE corpus as written, and each names source that is
really in it today (a file-name that matches nothing is not an error — it returns an empty
collection, which is an answer — but an EXAMPLE that matches nothing teaches nothing):

    python3 tools/source_dedup.py '__init__.py'           # cluster every copy of this source
    python3 tools/source_dedup.py 'setup.py'              # ... and see the AST relation fire: below
    python3 tools/source_dedup.py '_emit_in_subprocess'   # ... by symbol name
    python3 tools/source_dedup.py 0028aa50d9965a70cfc2c9c51f3d7941d7542625   # ... by git blob hash
    python3 tools/source_dedup.py <64-hex>                # ... by content sha256
    python3 tools/source_dedup.py 'retry a subprocess call'   # ... by free text (needs the proxy)
    python3 tools/source_dedup.py '__init__.py' --exact-only  # skip the similarity leg (no vectors)
    python3 tools/source_dedup.py --acceptance            # SEED N copies and PROVE the clustering
    ... [--threshold F] [--json] [--limit N] [--repo NAME] [--include-singletons] [--seed-n N]

WHAT `setup.py` FINDS, as a worked example of why this tool is not just `sha256sum | sort | uniq`:
`dz_debug :: dz_debug/setup.py` (263 bytes) and `testmonkeyalpha/dz_debug :: dz_debug/setup.py` (352
bytes) are DIFFERENT blobs with DIFFERENT content sha256s, so the exact relation is blind to them.
They differ by exactly three lines — an SPDX licence header and a copyright comment — which are
comments, so their ASTs are identical and the AST relation clusters them. Note what the proposal then
says: `collapse`, with the rationale that collapsing DISCARDS the comments the canonical lacks. Here
those comments are a licence header. That is the whole reason the ast rationale is worded as a
warning and not as a reassurance.

IT PROPOSES; IT NEVER DISPOSES. Every cluster's recommendation is TEXT — a `collapse` or a `review`
verb and a sentence of reasoning. This tool has no delete path, no rewrite path and no --apply: it
cannot remove, move or edit a single byte of the corpus, because no code here writes to the corpus at
all. "Read-only proposal (no auto-delete)" is the ticket's constraint and it is structural here, not
a promise. (The ONE path in this file that writes anything anywhere is --acceptance, which builds a
throwaway corpus of its own inside a temporary directory and never touches the real one — set out in
full under WHAT IT WRITES below, and proved by --acceptance itself on every run.)

────────────────────────────────────────────────────────────────────────────────────────────────
THE UNIT OF DEDUPLICATION. A "unit" is ONE row of the resolver's collection: one located piece of
source, at a {repo, path, line-range}. The resolver already emits these at two precisions, and this
tool keeps that distinction rather than inventing a third (resolver.py:158-162):

  * `chunk` — a CALLABLE: one function or method, its line-range being its real span in the blob
              (its `def` line to its last line). This is codebean's definition of a callable, taken
              from the #189 store, which built it with codebean's `lower_module_all` (#183).
  * `file`  — a MODULE: a whole blob the #189 store has not indexed, spanning 1..<line count>.

That is the ticket's "function/module" granularity: a blob the store has chunked deduplicates per
FUNCTION; one it has not deduplicates per MODULE.

────────────────────────────────────────────────────────────────────────────────────────────────
THE THREE DUPLICATE RELATIONS — what makes two units members of one cluster.

  1. EXACT (the ticket's "exact via sha") — the two units' blobs are BYTE-IDENTICAL, compared by the
     sha256 of the blob's bytes as read out of omni.git, AND the units are the same callable within
     those bytes (same `chunk_seq`).

     WHY chunk_seq IS PART OF THE KEY, stated because it is the one place a naive "same sha means
     duplicate" rule is WRONG: one blob usually holds SEVERAL callables, and they all share that
     blob's content sha256. Blob 47ec9be3 in the live store, for instance, holds `check` (lines
     38-43) and `main` (lines 46-106). Keying exactness on the blob sha alone would declare `check`
     a duplicate of `main` — two unrelated functions — merely because they share a file. Two
     byte-identical blobs chunk identically (identical bytes parse to an identical AST in an
     identical order), so `chunk_seq` k denotes the SAME callable in both, and (content sha256,
     chunk_seq) is exact identity for a callable. A `file`-level unit uses (content sha256, None).

  2. AST (the ticket's "grouped by AST-normalized function/module") — the two units have the same
     AST-NORMALIZED form, so they are the same code differing only in comments, blank lines and
     formatting. The normalizer is codebean's OWN `_ast_norm` (#183,
     codebean_mcp/prototype/code_wrapper.py:119-121), which is
         ast.dump(ast.parse(ast.unparse(ast.parse(src))))
     Comments and blank lines are not AST nodes, so they vanish; identifier names and literals are
     AST nodes, so they do NOT — a renamed variable is a different AST and is left to relation 3.
     This relation catches what sha256 CANNOT: a reformatted or re-commented copy is a different
     blob with a different sha, but the same code.

     The normalized form is hashed and compared IN MEMORY, within one run, and never stored — so
     `ast.dump`'s output format varying between python versions cannot make two runs disagree: both
     sides of every comparison are always produced by the same interpreter.

     Source of the text that gets normalized: for a `chunk` unit it is the #189 store's `chunks.text`,
     which IS codebean's `original_src` = `ast.unparse(node)` (code_sim_indexer.py:54-57); for a
     `file` unit it is the blob's own source, read from omni.git. Both then go through `_ast_norm`,
     so a key means the same thing whichever way it was obtained.

  3. NEAR (the ticket's "near via similarity threshold (#190)") — the two units' #189 vectors have a
     cosine >= --threshold. The vectors are `chunks.vector` from the #189 store: JSON float arrays,
     L2-normalized by #189, so cosine IS the plain dot product (code_sim_indexer.py:83-86, :343-347).
     Only `chunk` units have a vector; a `file` unit the store never indexed has none and so can
     never join by this relation (it can still join by 1 or 2).

     THE SIMILARITY IS COMPUTED PAIRWISE, HERE — NOT taken from the resolver's `score`. The
     resolver's score measures a match against the QUERY (resolver.py:152-156); clustering needs each
     member against each OTHER member, which is a different number. Using the query score would
     cluster by "how much each resembles what you typed", which is not duplication.

     --threshold DEFAULTS TO 0.85, chosen from measurement rather than taste. Embedded through the
     live proxy with nomic-embed: a copy of a callable with every local variable renamed scores ~0.94
     against its original, an unrelated module (JSON config loading vs subprocess retry) scores 0.61,
     and genuinely different callables in the live #189 store score 0.65-0.69 against each other.
     0.85 sits in the empty band between "the same code, renamed" and "merely related code". Of those
     numbers, --acceptance re-measures the first on every run and PRINTS it (it seeds exactly such a
     renamed copy); the others were measured the same way but are not reproduced by it. Raise the
     threshold for a stricter proposal; lower it to fish for candidates — at 0.5 this corpus's
     callables collapse into one cluster, which is the knob doing its job, not a bug.

CLUSTERS ARE THE CONNECTED COMPONENTS of those three relations taken together (a union-find over the
collection). So the relations COMPOSE: A byte-identical to B, B a reformat of C, C a rename of D puts
all four in one cluster. That is single-linkage, and it can CHAIN — a member can reach the cluster
without itself being near the canonical. This is not hidden: every duplicate is reported with its
OWN relation and cosine TO THE CANONICAL, so a chained member shows its real (possibly low) number,
and one whose relation to the canonical cannot be computed directly is reported as `linked` rather
than being dressed up as a near-duplicate.

────────────────────────────────────────────────────────────────────────────────────────────────
THE CANONICAL — which one the engine says to KEEP.

Chosen by a TOTAL, deterministic order over a cluster's members. The first key that separates two
members decides; the last three keys guarantee there is never a tie, so the same collection always
yields the same canonical:

  1. MOST associated tickets   — the copy the project's own `ticket_works` rows point at is the copy
                                 it actually maintains. (When the tickets index is absent — the
                                 normal case in a pair worktree, see ASSOCIATED TICKETS — every
                                 member scores 0 here and the rule falls through to 2.)
  2. MOST byte-identical peers — the dominant version: keeping what most of the corpus already agrees
                                 on makes the proposal the smallest change.
  3. SHALLOWEST path           — fewest '/' segments, then shortest: `pkg/util/retry.py` is a source
                                 of record, `snapshots/2026/vendor/retry.py` is a copy of one.
  4. (repo, path, line_start)  — lexicographic; breaks every remaining tie deterministically.

Each cluster prints WHY its canonical won, in those terms.

THE RECOMMENDATION, per duplicate — and why it is not one verb for all:
  * exact  -> COLLAPSE. The bytes are identical; replacing it with a reference to the canonical
              cannot change behaviour.
  * ast    -> COLLAPSE. The code is identical; but the AST is not the file, so COMMENTS AND
              FORMATTING ARE NOT IN IT and collapsing this copy discards whatever comments it
              carries that the canonical does not. Said plainly rather than sold as free.
  * near   -> REVIEW, never collapse. A near-duplicate is BY DEFINITION not the same code — a
              renamed variable is also how a deliberate fork begins. Only a human can say whether
              the difference is noise or the point.
  * linked -> REVIEW. It reached the cluster through the relation graph but cannot be compared to
              the canonical directly (no vector on one side). The weakest claim this tool makes, and
              labelled as such.

────────────────────────────────────────────────────────────────────────────────────────────────
HOW THE COLLECTION IS GATHERED. The engine runs the resolver twice and unions the results, because
one resolver call cannot see both kinds of duplicate:
  * the EXACT leg — `resolve(identifier)` — returns every occurrence of the blob(s) the identifier
    names. That finds exact and reformatted copies that share a name or a path, but nothing that was
    renamed.
  * the SIMILARITY leg — `resolve(identifier, like=True)` — ranks the whole #189 store by cosine
    against the identifier's OWN stored vectors. Offline: it needs no network, because the vectors
    are already in the store (resolver.py:138-148). This is what reaches a renamed copy.
Candidates are gathered at min(0.5, --threshold) — the resolver's own similarity floor
(resolver.py:151) — and only then clustered at --threshold, so the collection is wider than the
proposal and a near-duplicate cannot be filtered out before it is ever considered. --exact-only
drops the similarity leg. A FREE-TEXT identifier is already a similarity query (resolver.py:929-934),
so it runs as ONE leg and is the only path here that touches the network.

SINGLETONS — a unit that is nobody's duplicate — are counted but NOT printed: a cluster of one is
not a deduplication finding. --include-singletons shows them.

THE ONE THING THAT IS EXCLUDED, AND WHY IT IS NOT A DUPLICATE. A ZERO-BYTE unit never joins any
cluster. git hashes every empty file to one blob (e69de29b...), which in this corpus occupies 57
distinct paths across 35 repos, so all 57 share one content sha256 — and, as the resolver puts it, "a
zero-byte blob is the one identity in a content-addressed corpus that says nothing about the source"
(resolver.py:44-51). The resolver can hand such a match back LABELLED `(empty)`, because its question
is "where is this blob?" and "at all 57 of these paths" is the true answer. Here the same fact would
become a WRONG ANSWER: clustering on it recommends collapsing an empty `__init__.py`, an empty
`scratchpad.js` and an empty `logs/coordinator.err` into one another. They are not copies of one
piece of source; they are separate files that happen to hold nothing, and there is no deduplication
to propose. The AST relation has the identical trap — a comments-only file normalizes to the same
empty `Module(body=[])` as every other one — and it is closed the same way. Both are reported as
excluded, never silently dropped. See empty_unit() and ast_key() below.

ASSOCIATED TICKETS come from the resolver, which fills them from the congruency state db's
`ticket_works` (migrations/0029_ticket_authorization.sql:86-93) by the two ref conventions actually
in that column: `omni-blob:<sha>` and a repo-relative path (resolver.py:851-882). That db is
git-ignored (.gitignore:11) and so is ABSENT from a pair worktree: when it is missing every
`tickets` list is empty, which changes nothing else about a clustering. --acceptance therefore seeds
its OWN ephemeral ticket_works, so the ticket's "lists the rest as dups with their tickets" is proved
here rather than assumed to hold elsewhere.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT IT WRITES: NOTHING. Every database is opened by the resolver through the sqlite URI flag
`immutable=1`, never `mode=ro` — the state db is WAL-journalled, and `mode=ro` on a WAL db creates
`congruency.sqlite-shm`/`-wal` sidecars in the state directory on every open (the #153 lesson, fixed
the same way at ticket_status.py:49-60). omni.git is read with `cat-file` plumbing only. Bytecode
caching is disabled before any import-by-path, so no `__pycache__` is minted beside the sources this
tool loads. THE ONE FILE THIS TOOL CAN EVER CREATE on a normal run is the note-for-claude bug report
(logs/bug_reports.jsonl, git-ignored per .gitignore:20-21), written only when an UNEXPECTED exception
is thrown — the registry's contract for every tool in this package.

--acceptance IS THE ONE PATH THAT WRITES, AND IT WRITES ONLY INSIDE A TEMPORARY DIRECTORY. It has to:
the ticket says to SEED copies, and there is nothing to seed into otherwise. It builds a COMPLETE
ephemeral corpus (a bare omni.git, an omni_index.db, a #189 store, a ticket_works db) under a
`tempfile.TemporaryDirectory()` which is REMOVED when it returns. It never opens the live corpus, the
live store, the mem-graph, the forge ledger, the state db or this repository for writing — it points
the resolver at the temp dir instead. And it PROVES that: it hashes every seeded file before and
after the engine runs and checks not one byte moved, and checks no -wal/-shm sidecar appeared.

IT REUSES ITS DEPENDENCIES RATHER THAN REIMPLEMENTING THEM — the reason resolver.py:193-197 gives.
The match collection, the corpus paths, the read-only connects and the blob reads come from the
sibling tools/resolver.py (#193); the store schema, the chunker wrapper, the vector normalization and
the embedder come from tools/code_sim_indexer.py (#189) through it; the AST normalizer and the
callable decomposition come from codebean (#183). A parallel reimplementation could drift and
silently dedup against a different corpus than the one #189 indexed.

Exit codes (each prints ONE line, never a traceback):
    0  the clustering completed — INCLUDING "no duplicates found", which is an answer, not a failure
       (--acceptance: every check PASSED)
    1  --acceptance: at least one check FAILED
    2  a precondition failure — no omni index, no omni.git, no resolver, no codebean, an unknown
       --kind, or a --seed-n below the minimum
    3  a free-text query, or --acceptance's similarity leg, needed the litellm embedding proxy and it
       was unreachable (mirrors code_sim_indexer.py and resolver.py's exit 3)
Pure-python stdlib, one file. Registry-gated per note-for-claude: it walks UP to registry.json and
refuses to run without it.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback

# NO BYTECODE CACHE. This tool loads resolver.py, code_sim_indexer.py and codebean from SOURCE via
# importlib; python's default is to cache the compiled bytecode beside the source, which would mint a
# tools/__pycache__/ — a file, contradicting this module's own "writes NOTHING" guarantee. (Those
# paths are git-ignored (.gitignore:4-5), but "git-ignored" is not "not created", and the guarantee is
# about the filesystem.) Set before any import-by-path happens, so it holds on every path. Same
# reasoning as resolver.py:224-230.
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

# The near-duplicate cosine floor. Measured, not guessed — see THE THREE DUPLICATE RELATIONS above:
# a fully-renamed copy scores 0.9302 against its original, unrelated source scores 0.61, and distinct
# callables in the live store score 0.65-0.69. 0.85 is the empty band between those populations.
DEFAULT_THRESHOLD = 0.85
DEFAULT_LIMIT = 200          # matches gathered per resolver leg before clustering
SEED_MIN = 2                 # --acceptance needs at least an original + one duplicate to prove

# The seeded acceptance's ticket ids. Deliberately far above any live ticket: they exist ONLY inside
# the temp-dir db this tool builds and throws away, and are never written to the real state db.
SEED_TICKET_BASE = 9400


class Fault(Exception):
    """A precondition failure — reported as one line, exit 2."""


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks).
    note-for-claude: every tool files a timestamped report when an exception is thrown. This is the
    ONLY file this tool can ever create on a normal run, and only on an unexpected exception."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "source_dedup.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:],
                "note": "the source dedup engine (#194)",
            }) + "\n")
    except Exception:  # noqa: BLE001 — a failed bug report must never mask the original fault
        pass


# ── the dependencies, loaded from source (the loader pattern of resolver.py:314-336) ─────────────
def load_resolver(path=None):
    """The sibling tools/resolver.py (ticket #193), loaded as a module.

    Loaded by path rather than imported by name because `tools/` is not a package. Importing it runs
    only its registry gate and its constants: it opens nothing and writes nothing at import.
    """
    src = path or os.path.join(HERE, "resolver.py")
    if not os.path.isfile(src):
        raise Fault("tools/resolver.py (ticket #193) not found at %s — the dedup engine clusters the "
                    "collection IT produces and will not reimplement it" % src)
    spec = importlib.util.spec_from_file_location("cg_resolver", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        raise Fault("resolver.py at %s failed to load: %r" % (src, e))
    for name in ("resolve", "open_sources", "batch_blobs", "detect_kind", "load_indexer",
                 "SIM_MIN_SCORE", "KINDS", "Fault", "EmbedError"):
        if not hasattr(mod, name):
            raise Fault("%s defines no %s — wrong resolver version?" % (src, name))
    return mod


def load_codebean(cs, codebean_dir):
    """codebean's `code_wrapper` (ticket #183), via #189's OWN loader.

    Reusing cs.load_chunker rather than re-writing the import means this tool cannot load a different
    codebean than the one that built the store it reads. Two things that loader gets right and a
    naive import would not are documented at code_sim_indexer.py:203-230 (sys.modules registration
    before exec_module, and capturing codebean's import-time telemetry print).

    Two names are needed here: `lower_module_all`, the callable decomposition (#183), and `_ast_norm`,
    codebean's own normalizer (code_wrapper.py:119-121) — the AST-normalized grouping the ticket
    names. Both are checked, so a codebean without them is a one-line fault, not an AttributeError.
    """
    cw = cs.load_chunker(codebean_dir)
    for name in ("lower_module_all", "_ast_norm"):
        if not hasattr(cw, name):
            raise Fault("codebean at %s defines no %s — wrong codebean version? (the dedup engine "
                        "groups by codebean's AST-normalized form)" % (codebean_dir, name))
    return cw


# ── the keys: content sha256, the AST-normalized form, the vector ────────────────────────────────
def ast_key(cw, source):
    """sha256 of codebean's AST-NORMALIZED form of `source`, or None when it has no AST identity.

    `_ast_norm` (code_wrapper.py:119-121) is parse -> unparse -> parse -> dump, so comments, blank
    lines and formatting (which are not AST nodes) drop out while names and literals (which are)
    survive. Hashed only to keep the key small; the comparison is over the normalized dump itself.

    None — never joins by the AST relation — in three cases, each a fact rather than a failure:
      * it does not parse. The forge holds python-2, partial files, and plenty of non-python text.
      * it is blank.
      * it PARSES TO AN EMPTY MODULE. A file of nothing but comments and whitespace normalizes to
        the same `Module(body=[])` as every OTHER such file, so keying on it would declare all of
        them duplicates of one another. That is not a shared identity, it is a shared ABSENCE of
        code — the AST relation's version of the zero-byte blob degenerate case that `empty_unit`
        guards for the exact relation.
    """
    if not source or not source.strip():
        return None
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return None
    if not tree.body:
        return None
    try:
        return hashlib.sha256(cw._ast_norm(source).encode("utf-8")).hexdigest()
    except (SyntaxError, ValueError, RecursionError, TypeError):
        return None


def exact_key(unit):
    """The unit's EXACT identity: (the blob's content sha256, the callable's chunk_seq).

    chunk_seq is in the key because one blob holds many callables and they all share its sha — see
    the docstring's EXACT relation. Two byte-identical blobs chunk identically, so chunk_seq k is the
    same callable in both. A file-level unit has no chunk_seq and uses None.

    None — never joins by this relation — for a unit whose blob could not be read out of omni.git (no
    content sha256, so no exact identity: it must not join everything else that also failed to read),
    and for an EMPTY one (see empty_unit).
    """
    if not unit["content_sha256"] or unit["empty"]:
        return None
    return (unit["content_sha256"], unit["chunk_seq"] if unit["level"] == "chunk" else None)


def empty_unit(body):
    """Whether a unit's blob is ZERO-BYTE — in which case it has no dedup identity at all.

    THE ONE DEGENERATE CASE OF A CONTENT-ADDRESSED CORPUS, and it must be excluded here rather than
    merely labelled. git hashes every zero-byte file to one blob (e69de29b...), which in this corpus
    occupies 57 distinct paths across 35 repos, so ALL of them share one content sha256 — and the
    resolver says exactly why that means nothing: "A zero-byte blob is the one identity in a
    content-addressed corpus that says nothing about the source" (resolver.py:44-51).

    The resolver can label such a match `(empty)` and hand it back, because its question is "where is
    this blob?" and the answer is honestly "at all 57 of these paths". THIS tool's question is "what
    should we KEEP, and what should we COLLAPSE?", and there the same fact becomes a WRONG ANSWER: it
    would cluster an empty `__init__.py`, an empty `scratchpad.js` and an empty `logs/coordinator.err`
    and recommend collapsing them into one another. They are not copies of one piece of source; they
    are separate files that happen to contain nothing. Nothing is not source, and there is no
    deduplication to propose. So an empty unit gets no exact key and no AST key, and is reported as
    excluded rather than silently dropped.
    """
    return body is not None and len(body) == 0


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _in_chunks(seq, n=400):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]                                  # sqlite caps host parameters


# ── step 1: gather the resolver's match collection ───────────────────────────────────────────────
def collect(identifier, src, rv, cs, opts):
    """The resolver's collection for `identifier` — this engine's ONLY input.

    Two legs, unioned, because neither alone sees both kinds of duplicate (see HOW THE COLLECTION IS
    GATHERED). Returns (units, legs_run): each unit is a resolver match plus `found_by`, naming the
    leg(s) that reached it. Candidates are gathered at the resolver's similarity floor or the
    clustering threshold, whichever is LOWER, so nothing that could cluster is dropped before it is
    considered.
    """
    kind = opts["kind"] if opts["kind"] and opts["kind"] != "auto" else rv.detect_kind(identifier)
    base = {"kind": opts["kind"], "like": False, "limit": opts["limit"], "min_score": 0.0,
            "repo": opts["repo"], "all_blobs": False, "git_fanout": False, "model": opts["model"],
            "litellm": opts["litellm"], "timeout": opts["timeout"]}
    gather = min(rv.SIM_MIN_SCORE, opts["threshold"])

    legs = []
    if kind == "text":
        # Free text is ALREADY a similarity query in the resolver (resolver.py:929-934): running a
        # separate --like leg over it would embed the same string twice and return the same rows.
        legs.append(("similarity", rv.resolve(identifier, src, cs, dict(base, min_score=gather))))
    else:
        legs.append(("exact", rv.resolve(identifier, src, cs, dict(base))))
        if not opts["exact_only"]:
            legs.append(("similarity", rv.resolve(identifier, src, cs,
                                                  dict(base, like=True, min_score=gather))))

    seen, units = {}, []
    for label, res in legs:
        for m in res["matches"]:
            k = (m["repo"], m["path"], m["line_start"], m["line_end"], m["blob_sha"])
            if k in seen:
                seen[k]["found_by"].add(label)
                continue
            u = dict(m, found_by={label})
            seen[k] = u
            units.append(u)
    for u in units:
        u["found_by"] = sorted(u["found_by"])
    return units, [label for label, _res in legs]


# ── step 2: give every unit its three keys ───────────────────────────────────────────────────────
def enrich(units, src, rv, cs, cw, opts):
    """Fill each unit's content_sha256, ast_key and vector — the inputs to the three relations.

    One batched read of omni.git for the bytes (the content sha256, and the source of a file-level
    unit's AST key), and one batched read of the #189 store for the chunk texts and vectors.
    """
    shas = sorted({u["blob_sha"] for u in units if u["blob_sha"]})
    bodies = rv.batch_blobs(src["omni_git"], shas) if (shas and src["omni_git"]) else {}
    csha = {s: hashlib.sha256(b).hexdigest() for s, b in bodies.items()}

    # the #189 store: `chunks.text` is codebean's ast.unparse form; `chunks.vector` is the #190 vector
    text_by, vec_by = {}, {}
    scon = src["store"]
    if scon is not None and shas:
        for part in _in_chunks(shas):
            q = ",".join("?" * len(part))
            for sha, seq, txt, vec in scon.execute(
                    "SELECT sha, chunk_seq, text, vector FROM chunks WHERE sha IN (%s) AND model = ?"
                    % q, list(part) + [opts["model"]]):
                text_by[(sha, seq)] = txt
                try:
                    v = json.loads(vec) if vec else None
                except (TypeError, ValueError):
                    v = None
                if v:
                    vec_by[(sha, seq)] = v

    # a file-level unit's module source, decoded once per blob (not once per occurrence)
    module_src = {}
    for sha, body in bodies.items():
        try:
            module_src[sha] = body.decode("utf-8")
        except UnicodeDecodeError:
            module_src[sha] = None                          # not utf-8: no AST key, reported as such

    for u in units:
        sha = u["blob_sha"]
        u["content_sha256"] = csha.get(sha)
        u["empty"] = empty_unit(bodies.get(sha))
        if u["level"] == "chunk":
            u["vector"] = vec_by.get((sha, u["chunk_seq"]))
            u["ast_key"] = ast_key(cw, text_by.get((sha, u["chunk_seq"])))
        else:
            # A module the #189 store never indexed: no vector (so it can never join by NEAR), and
            # its AST key is codebean's normalization of the whole module.
            u["vector"] = None
            u["ast_key"] = ast_key(cw, module_src.get(sha))
            if u["symbol"] is None and module_src.get(sha):
                u["symbol"] = _module_symbols(cs, cw, module_src[sha])
        if u["empty"]:
            u["ast_key"] = None                             # see empty_unit: nothing is not source
        u["exact_key"] = exact_key(u)
    return units


def _module_symbols(cs, cw, source):
    """The callables codebean finds in a module, as a display label for a file-level unit.

    Reuses #189's own chunk_text (code_sim_indexer.py:248-282), which calls codebean's
    lower_module_all — so what is named here is exactly what the store WOULD have indexed. Best
    effort: a module that will not chunk is simply labelled '(whole file)' by the renderer.
    """
    try:
        chunks, status = cs.chunk_text(cw, source)
    except Exception:  # noqa: BLE001 — cs.PairError and any parse fault alike: a label is not worth a crash
        return None
    if status != "indexed" or not chunks:
        return None
    names = [c["symbol"] for c in chunks]
    return ",".join(names[:3]) + ("+%d" % (len(names) - 3) if len(names) > 3 else "")


# ── step 3: cluster — the connected components of the three relations ────────────────────────────
class Union:
    """Union-find with path halving. The clusters are its connected components."""

    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def cluster(units, opts):
    """[[unit index]] — the collection's clusters, each a connected component of EXACT | AST | NEAR.

    Relations 1 and 2 are equality on a key, so they are grouped with a dict, not compared pairwise.
    Relation 3 is a real pairwise cosine over the units that have a vector — O(n^2) dot products over
    a collection bounded by --limit, and skipped for any pair already in one component.
    """
    uf = Union()
    for i in range(len(units)):
        uf.find(i)

    for key in ("exact_key", "ast_key"):                    # relations 1 and 2
        groups = {}
        for i, u in enumerate(units):
            if u[key]:
                groups.setdefault(u[key], []).append(i)
        for members in groups.values():
            for j in members[1:]:
                uf.union(members[0], j)

    have_vec = [i for i, u in enumerate(units) if u["vector"]]   # relation 3
    for a in range(len(have_vec)):
        for b in range(a + 1, len(have_vec)):
            i, j = have_vec[a], have_vec[b]
            if uf.find(i) == uf.find(j):
                continue                                    # already one component: nothing to test
            if dot(units[i]["vector"], units[j]["vector"]) >= opts["threshold"]:
                uf.union(i, j)

    groups = {}
    for i in range(len(units)):
        groups.setdefault(uf.find(i), []).append(i)
    return [sorted(m) for m in groups.values()]


# ── step 4: the canonical, the relation to it, and the recommendation ────────────────────────────
def relation_to(u, canon):
    """(relation, similarity) of a member to its cluster's canonical — see THE RECOMMENDATION.

    Tested directly against the canonical, in strength order, rather than reported from the edge that
    happened to pull the member in: what a reader needs is this copy's relationship to the copy they
    are being told to keep.

    The `similarity` half — `similarity_to_canonical` in --json — is 1.0 for `exact` and `ast` BY
    IDENTITY, not by measurement: those relations are an equality on a key and no cosine is ever
    computed for them. It is a measured cosine ONLY for `near`, and None for `linked`. The rendered
    table says `identical` rather than 1.0000 for the first two so the distinction survives printing.
    """
    if u["exact_key"] and u["exact_key"] == canon["exact_key"]:
        return "exact", 1.0
    if u["ast_key"] and u["ast_key"] == canon["ast_key"]:
        return "ast", 1.0
    if u["vector"] and canon["vector"]:
        return "near", round(dot(u["vector"], canon["vector"]), 4)
    # It reached this cluster through the relation graph (single-linkage can chain), but there is no
    # direct comparison to the canonical to report. The weakest claim here, and named as one.
    return "linked", None


ACTION = {
    "exact":  ("collapse", "byte-identical to the canonical — replacing it with a reference to the "
                           "canonical cannot change behaviour"),
    "ast":    ("collapse", "same code as the canonical, differing only in comments/blank lines/"
                           "formatting — collapsing it DISCARDS any comments it carries that the "
                           "canonical does not"),
    "near":   ("review",   "NOT the same code — a near-duplicate is also how a deliberate fork "
                           "begins; reconcile by hand"),
    "linked": ("review",   "reached this cluster through the relation graph, but cannot be compared "
                           "to the canonical directly (no vector on one side)"),
}


def canonical_of(units, members, exact_counts):
    """The member to KEEP, by the total deterministic order documented under THE CANONICAL.

    Returns (index, why). `why` is the winning member's own numbers, so the choice is auditable from
    the output alone rather than by re-reading this function.
    """
    def rank(i):
        u = units[i]
        return (-len(u["tickets"]), -exact_counts.get(u["exact_key"], 1),
                u["path"].count("/"), len(u["path"]), u["repo"], u["path"], u["line_start"] or 0)

    best = min(members, key=rank)
    u = units[best]
    return best, ("%d ticket(s) recorded, %d byte-identical copy/copies, path depth %d"
                  % (len(u["tickets"]), exact_counts.get(u["exact_key"], 1), u["path"].count("/")))


def _loc(u):
    """A unit's location, as the ticket's tuple: {repo, path, line-range, associated tickets}."""
    return {"repo": u["repo"], "path": u["path"],
            "line_start": u["line_start"], "line_end": u["line_end"],
            "lines": lines_of(u), "level": u["level"], "symbol": u["symbol"],
            "namespace": u["namespace"], "blob_sha": u["blob_sha"],
            "content_sha256": u["content_sha256"],
            "tickets": u["tickets"], "found_by": u["found_by"]}


def lines_of(u):
    """The unit's line-range, rendered. The resolver's two sentinels are kept distinct rather than
    collapsed to a falsy 0 (resolver.py:789-791): line_end 0 is a ZERO-BYTE blob (no lines at all),
    line_end None is a blob the index names but the object store does not hold."""
    if u["line_end"] == 0:
        return "(empty)"
    if u["line_end"] is None:
        return "1-?"
    return "%s-%s" % (u["line_start"], u["line_end"])


def build_report(units, groups, opts, legs):
    """The clusters, as the ticket's output: canonical + duplicate locations + a recommendation."""
    exact_counts = {}
    for u in units:
        if u["exact_key"]:
            exact_counts[u["exact_key"]] = exact_counts.get(u["exact_key"], 0) + 1

    clusters, singletons = [], 0
    for members in groups:
        if len(members) < 2 and not opts["include_singletons"]:
            singletons += 1
            continue
        ci, why = canonical_of(units, members, exact_counts)
        canon = units[ci]
        dups = []
        for i in members:
            if i == ci:
                continue
            rel, sim = relation_to(units[i], canon)
            action, rationale = ACTION[rel]
            d = _loc(units[i])
            d.update({"relation": rel, "similarity_to_canonical": sim,
                      "action": action, "rationale": rationale})
            if rel == "near" and sim is not None and sim < opts["threshold"]:
                # Single-linkage chaining, surfaced: this member is in the cluster on the strength of
                # some OTHER member, not of the canonical. Never left for the reader to infer.
                d["note"] = ("joined via a near-duplicate chain — its cosine to the canonical (%.4f) "
                             "is below the --threshold (%.2f)" % (sim, opts["threshold"]))
            dups.append(d)
        dups.sort(key=lambda d: (["exact", "ast", "near", "linked"].index(d["relation"]),
                                 -(d["similarity_to_canonical"] or 0), d["repo"], d["path"]))
        tally = {}
        for d in dups:
            tally[d["relation"]] = tally.get(d["relation"], 0) + 1
        clusters.append({
            "size": len(members), "relations": tally,
            "canonical": dict(_loc(canon), why=why),
            "duplicates": dups,
            "recommendation": {
                "keep": "%s :: %s (%s)" % (canon["repo"], canon["path"], lines_of(canon)),
                "collapse": [d["path"] for d in dups if d["action"] == "collapse"],
                "review": [d["path"] for d in dups if d["action"] == "review"],
                "note": "a read-only proposal: nothing was deleted, moved or rewritten",
            },
        })
    # Biggest, most-collapsible clusters first: that is the order a reader acts in.
    clusters.sort(key=lambda c: (-c["size"], -len(c["recommendation"]["collapse"]),
                                 c["canonical"]["repo"], c["canonical"]["path"]))
    for n, c in enumerate(clusters, 1):
        c["cluster"] = n
    return {"threshold": opts["threshold"], "model": opts["model"], "legs": legs,
            "units": len(units), "clusters": clusters, "singletons": singletons,
            "excluded_empty": sum(1 for u in units if u["empty"]),
            "writes": "nothing — this is a read-only proposal; no file or database was written, "
                      "and nothing was deleted"}


def dedup(identifier, src, rv, cs, cw, opts):
    """The whole flow: collect -> enrich -> cluster -> canonical -> recommend."""
    units, legs = collect(identifier, src, rv, cs, opts)
    units = enrich(units, src, rv, cs, cw, opts)
    report = build_report(units, cluster(units, opts), opts, legs)
    report["identifier"] = identifier
    return report


# ── rendering ────────────────────────────────────────────────────────────────────────────────────
def render(res):
    print("identifier: %r" % res["identifier"])
    print("  collection: %d unit(s) from the resolver (%s leg%s), threshold %.2f, model %s"
          % (res["units"], " + ".join(res["legs"]), "s" if len(res["legs"]) > 1 else "",
             res["threshold"], res["model"]))
    print("  clusters:   %d duplicate cluster(s), %d singleton(s) not shown"
          % (len(res["clusters"]), res["singletons"]))
    if res["excluded_empty"]:
        print("  excluded:   %d zero-byte unit(s) — every empty file shares one content sha256, "
              "which says\n              nothing about the source, so they are not each other's "
              "duplicates (resolver.py:44-51)" % res["excluded_empty"])
    if not res["clusters"]:
        print("\n  (no duplicate cluster — every unit in the collection is nobody's duplicate)")
        return
    for c in res["clusters"]:
        rel = ", ".join("%d %s" % (n, r) for r, n in sorted(c["relations"].items())) or "-"
        print("\n" + "=" * 118)
        print("CLUSTER %d — %d member(s): 1 canonical + %d duplicate(s) [%s]"
              % (c["cluster"], c["size"], c["size"] - 1, rel))
        print("=" * 118)
        k = c["canonical"]
        print("  KEEP (canonical)  %s :: %s" % (k["repo"], k["path"]))
        print("      lines %-11s symbol %-24s tickets %s"
              % (k["lines"], _sym(k), _tix(k["tickets"])))
        print("      chosen because:  %s" % k["why"])
        print("      content sha256:  %s" % (k["content_sha256"] or "(blob not in the object store)"))
        print("\n  %-8s %-9s %-11s %-22s %-14s %s"
              % ("relation", "sameness", "lines", "symbol", "tickets", "repo :: path"))
        print("  " + "-" * 114)
        for d in c["duplicates"]:
            # `identical` rather than a number for exact/ast: those relations are an EQUALITY on a
            # key, not a measurement, and printing 1.0000 under a column headed `cosine` would claim
            # a cosine was computed when none was. Only `near` has a real cosine to report.
            sim = _sameness(d)
            # The PATH is printed last and IN FULL, never truncated: two occurrences of one duplicated
            # blob routinely differ only in a leading path segment, and clipping them would render
            # distinct locations as identical-looking rows (resolver.py:982-984).
            print("  %-8s %-9s %-11s %-22s %-14s %s :: %s"
                  % (d["relation"], sim, d["lines"], _sym(d)[:22], _tix(d["tickets"]),
                     d["repo"], d["path"]))
            if d.get("note"):
                print("           note: %s" % d["note"])
        print("\n  RECOMMENDATION")
        print("      keep      %s" % c["recommendation"]["keep"])
        for act, verb in (("collapse", "collapse"), ("review", "review")):
            rows = [d for d in c["duplicates"] if d["action"] == act]
            if not rows:
                continue
            print("      %-9s %d location(s):" % (verb, len(rows)))
            for d in rows:
                print("           [%s] %s :: %s" % (d["relation"], d["repo"], d["path"]))
                print("                 %s" % d["rationale"])
    print("\n" + "-" * 118)
    print("This is a PROPOSAL. %s" % res["writes"])
    print("Nothing here was applied: this tool has no delete, move or rewrite path.")


def _sameness(d):
    """A duplicate's closeness to the canonical, rendered HONESTLY per relation.

    `exact` and `ast` are an equality on a key — the code IS the canonical's — so they read
    `identical`; a measured cosine was never computed for them and none is shown. `near` is the one
    relation carrying a real number, so it shows it. `linked` has neither and reads `-`.
    """
    if d["relation"] in ("exact", "ast"):
        return "identical"
    if d["similarity_to_canonical"] is None:
        return "-"
    return "%.4f" % d["similarity_to_canonical"]


def _sym(d):
    if d.get("namespace") and d.get("symbol"):
        return "%s.%s" % (d["namespace"], d["symbol"])
    if d.get("symbol"):
        return d["symbol"]
    return "(empty file)" if d.get("line_end") == 0 else "(whole file)"


def _tix(tickets):
    return ",".join("#%s" % t["ticket"] for t in tickets) or "-"


# ── the acceptance: seed N known copies of a module across repos, then PROVE the clustering ──────
#
# The ticket's acceptance is a CONSTRUCTION ("seed N known copies"), not a discovery, so — unlike the
# resolver's --acceptance, which hunts a specimen out of the live corpus — this one builds the corpus
# it proves against. It has to: the live #189 store holds 7 blobs / 8 chunks, which is too thin to
# contain a known-answer duplicate family, and seeding into the live corpus is exactly the write this
# tool must never do. So the whole corpus is built inside a tempfile.TemporaryDirectory() and thrown
# away, and the live corpus is never opened at all on this path.
#
# The seeds below are ONE callable per module on purpose: the corpus's own shredded shape (its files
# are named after the single callable they hold — see the live store's `_emit_in_subprocess.py`), and
# it makes "N copies of a module" and "N copies of a function" the same statement, so the acceptance
# proves one cluster of N rather than N/2 clusters of 2.

SEED_ORIGINAL = '''\
"""Retry a flaky subprocess call with exponential backoff."""
import subprocess
import time


def call_with_retry(cmd, attempts=3, delay=0.5):
    """Run cmd, retrying on a non-zero exit up to `attempts` times.

    Returns the first successful CompletedProcess, or the last failure.
    """
    last = None
    for i in range(attempts):
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0:
            return result
        last = result
        time.sleep(delay * (2 ** i))
    return last
'''

# AST-IDENTICAL to SEED_ORIGINAL: comments and blank lines only, which are not AST nodes. Different
# bytes -> a different blob sha -> a different content sha256, so the EXACT relation CANNOT see it and
# only the AST relation can. That is precisely what this copy is here to prove.
SEED_AST_VARIANT = '''\
"""Retry a flaky subprocess call with exponential backoff."""
# A reformatted copy of the original: comments and blank lines added, code untouched.
import subprocess
import time


def call_with_retry(cmd, attempts=3, delay=0.5):
    """Run cmd, retrying on a non-zero exit up to `attempts` times.

    Returns the first successful CompletedProcess, or the last failure.
    """
    last = None

    # keep trying until the attempts run out
    for i in range(attempts):

        result = subprocess.run(cmd, capture_output=True)

        if result.returncode == 0:
            return result

        last = result
        time.sleep(delay * (2 ** i))   # exponential backoff
    return last
'''

# NEAR-duplicate: every local name renamed. Names ARE AST nodes, so the AST relation cannot see it
# either — only the #190 vectors can. Its cosine to the original is re-measured and printed by every
# --acceptance run rather than asserted here (~0.94 through the live proxy with nomic-embed).
SEED_NEAR_VARIANT = '''\
"""Retry a flaky subprocess call with exponential backoff."""
import subprocess
import time


def call_with_retry(command, tries=3, pause=0.5):
    """Run command, retrying on a non-zero exit up to `tries` times.

    Returns the first successful CompletedProcess, or the last failure.
    """
    previous = None
    for n in range(tries):
        outcome = subprocess.run(command, capture_output=True)
        if outcome.returncode == 0:
            return outcome
        previous = outcome
        time.sleep(pause * (2 ** n))
    return previous
'''

# The CONTROL: unrelated source. It is reachable by the similarity leg (its cosine to the original,
# 0.61, clears the 0.5 gather floor) and so it DOES enter the collection — which is the point. It must
# still not enter the cluster. A dedup engine that clusters everything it is handed proves nothing;
# this copy is what makes the acceptance's PASS mean something.
SEED_CONTROL = '''\
"""Load a JSON config file into a dict."""
import json


def load_config(path):
    """Read the JSON config at `path` and return it as a dict."""
    with open(path) as fh:
        return json.load(fh)
'''

OMNI_SCHEMA = """
CREATE TABLE occ  (sha TEXT, path TEXT, ext TEXT, size INT, ref TEXT, repo TEXT, ts TEXT);
CREATE TABLE blob (sha TEXT PRIMARY KEY, path TEXT, ext TEXT, size INT, is_text INT);
"""

# ticket_works exactly as migrations/0029_ticket_authorization.sql:86-93 declares it, so what the
# resolver reads here is shaped like what it reads from the real state db.
TICKETS_SCHEMA = """
CREATE TABLE ticket_works (
  uid       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        REAL NOT NULL,
  ticket_id INTEGER NOT NULL,
  kind      TEXT,
  ref       TEXT,
  note      TEXT
);
"""


def _git_hash_object(gitdir, data):
    """Write `data` into the bare object store and return its blob sha, using git's own plumbing so
    the sha is git's, not this tool's idea of git's."""
    r = subprocess.run(["git", "--git-dir", gitdir, "hash-object", "-w", "--stdin"],
                       input=data, capture_output=True)
    if r.returncode != 0:
        raise Fault("seeding: git hash-object failed: %s" % r.stderr.decode("utf-8", "replace")[:200])
    return r.stdout.decode().strip()


def _proxy_up(cs, opts):
    """Whether the litellm embedding proxy will answer. Asked ONCE, up front, so the seed's shape is
    decided before anything is built rather than half-way through."""
    try:
        cs.embed_all(opts["litellm"], opts["model"], cs.LITELLM_KEY, ["search_document: ping"], 1, 15)
        return True
    except Exception:  # noqa: BLE001 — cs.EmbedError and any transport fault alike
        return False


def seed_plan(n, with_near):
    """[(role, repo, path, source)] — N copies of one module across N repos, plus the control.

    Paths are chosen so that NO seeded path is a '/'-delimited suffix of another. That matters: the
    resolver attaches a ticket whose ref is a path when `ref == path or one is a '/'-suffix of the
    other` (resolver.py:876-880), so a lazier layout (`pkg/util/retry.py` and
    `vendor/pkg/util/retry.py`) would attach the first copy's ticket to the second as well and the
    acceptance's "each dup carries ITS OWN ticket" check would pass for the wrong reason.
    """
    plan = [("original", "seed-alpha", "pkg/util/retry.py", SEED_ORIGINAL)]
    n_exact = n - (3 if with_near else 2)                   # the rest, after the original + ast (+ near)
    for i in range(1, n_exact + 1):
        plan.append(("exact", "seed-exact-%d" % i, "vendor%d/lib/retry.py" % i, SEED_ORIGINAL))
    plan.append(("ast", "seed-ast", "snapshots/2026/retry.py", SEED_AST_VARIANT))
    if with_near:
        plan.append(("near", "seed-near", "forks/upstream/retry.py", SEED_NEAR_VARIANT))
    plan.append(("control", "seed-control", "pkg/util/config.py", SEED_CONTROL))
    return plan


def seed_corpus(root, plan, cs, cw, opts, with_vectors):
    """Build the ephemeral corpus under `root` and return the paths + the seeded facts.

    Four objects, all inside `root`, all removed with it: a bare omni.git holding the blob bytes, an
    omni_index.db shaped exactly like the live one (its schema as read from the live index today), a
    #189 store built by #189's OWN chunker/embedder/writer, and a ticket_works db.
    """
    gitdir = os.path.join(root, "omni.git")
    r = subprocess.run(["git", "init", "--bare", "-q", gitdir], capture_output=True)
    if r.returncode != 0:
        raise Fault("seeding: git init --bare failed: %s" % r.stderr.decode("utf-8", "replace")[:200])

    omni_db = os.path.join(root, "omni_index.db")
    ocon = sqlite3.connect(omni_db)
    ocon.executescript(OMNI_SCHEMA)

    seeds = []
    for role, repo, path, source in plan:
        data = source.encode("utf-8")
        sha = _git_hash_object(gitdir, data)
        ocon.execute("INSERT OR REPLACE INTO blob (sha, path, ext, size, is_text) VALUES (?,?,?,?,1)",
                     (sha, path, ".py", len(data)))
        ocon.execute("INSERT INTO occ (sha, path, ext, size, ref, repo, ts) VALUES (?,?,?,?,?,?,?)",
                     (sha, path, ".py", len(data), "refs/seed/%s" % repo, repo, "2026-07-15T00:00:00Z"))
        seeds.append({"role": role, "repo": repo, "path": path, "sha": sha,
                      "content_sha256": hashlib.sha256(data).hexdigest()})
    ocon.commit()
    ocon.close()

    # The #189 store, built the way #189 builds it: its schema, its chunker, its prefix, its writer.
    store = os.path.join(root, "code_sim.db")
    scon = cs.open_store(store)
    for s, (_role, _repo, _path, source) in zip(seeds, plan):
        chunks, status = cs.chunk_text(cw, source)
        dim = 0
        if chunks and with_vectors:
            payload = [cs.DOC_PREFIX + c["text"][:cs.MAX_CHARS] for c in chunks]
            vecs = cs.embed_all(opts["litellm"], opts["model"], cs.LITELLM_KEY, payload,
                                cs.BATCH, opts["timeout"])
            for c, v in zip(chunks, vecs):
                c["vector"], c["embed_chars"], c["truncated"] = v, len(c["text"]), 0
            dim = len(vecs[0])
        elif chunks:
            # No proxy: the store still records the chunks (so line-ranges, symbols and the AST text
            # are all real), but carries no vector — and so the NEAR relation is simply unavailable,
            # which is why the near copy is not seeded in that mode.
            for c in chunks:
                c["vector"], c["embed_chars"], c["truncated"] = None, len(c["text"]), 0
        cs.store_blob(scon, s["sha"], opts["model"], ".py", len(source.encode()), chunks, status,
                      cs.DOC_PREFIX, dim)
        s["chunks"] = [{"symbol": c["symbol"], "line_start": c["line_start"], "line_end": c["line_end"]}
                       for c in chunks]
    cs.store_occurrences(scon, [(s["sha"], s["repo"], s["path"]) for s in seeds])
    scon.commit()
    scon.close()

    # ticket_works: one ticket per seeded copy, by the PATH convention; plus one by the
    # `omni-blob:<sha>` convention (the ref index_watch.py:214 records for an indexed blob), so BOTH
    # of the conventions the resolver actually reads are exercised (resolver.py:851-857).
    tdb = os.path.join(root, "congruency.sqlite")
    ccon = sqlite3.connect(tdb)
    ccon.executescript(TICKETS_SCHEMA)
    for k, s in enumerate(seeds):
        tid = SEED_TICKET_BASE + 1 + k
        ccon.execute("INSERT INTO ticket_works (ts, ticket_id, kind, ref, note) VALUES (?,?,?,?,?)",
                     (0.0, tid, "code", s["path"], "seeded by --acceptance for the %s copy" % s["role"]))
        s["ticket"] = tid
    blob_ref_sha = seeds[0]["sha"]
    ccon.execute("INSERT INTO ticket_works (ts, ticket_id, kind, ref, note) VALUES (?,?,?,?,?)",
                 (0.0, SEED_TICKET_BASE, "code", "omni-blob:" + blob_ref_sha,
                  "seeded by --acceptance: the omni-blob ref convention"))
    ccon.commit()
    ccon.close()
    return {"omni_db": omni_db, "omni_git": gitdir, "store": store, "tickets_db": tdb,
            "seeds": seeds, "blob_ref_ticket": SEED_TICKET_BASE, "blob_ref_sha": blob_ref_sha}


def _snapshot(root):
    """{relative path: sha256} for every file under `root` — the before/after evidence that the engine
    wrote nothing and deleted nothing. Hashes, not mtimes: a rewrite with identical bytes is not a
    change, and a change with an identical mtime is."""
    out = {}
    for base, _dirs, files in os.walk(root):
        for fn in files:
            p = os.path.join(base, fn)
            try:
                with open(p, "rb") as fh:
                    out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
            except OSError:
                out[os.path.relpath(p, root)] = "(unreadable)"
    return out


def acceptance(rv, cs, cw, opts, a):
    """PROVE the ticket's acceptance on a SEEDED corpus, then destroy it.

    THE CLAIM, stated exactly as it is checked: "seed N known copies of a module across repos; the
    engine clusters all N, names one canonical, and lists the rest as dups with their tickets."
    Every check prints PASS or FAIL; exit 1 if any FAILED.
    """
    n = a.seed_n
    if n < SEED_MIN:
        raise Fault("--seed-n %d is below the minimum of %d: proving a duplicate cluster needs at "
                    "least an original and one copy of it" % (n, SEED_MIN))

    with_near = _proxy_up(cs, opts)
    if with_near and n < 3:
        with_near = False                                   # no room for a near copy beside the ast one
    if not with_near:
        print("NOTE: the NEAR-duplicate copy is NOT part of this run's seed.")
        print("      Reason: %s" % (
            "the litellm embedding proxy at %s is unreachable, so no vector can be produced for it "
            "and the #190 similarity relation is unavailable" % opts["litellm"]
            if n >= 3 else "--seed-n %d leaves no room for it beside the original and the AST copy" % n))
        print("      The exact and AST legs below still prove the ticket's acceptance over the %d "
              "copies that WERE seeded. Re-run with the proxy up%s to prove the similarity leg.\n"
              % (n, "" if n >= 3 else " and --seed-n 3 or more"))

    plan = seed_plan(n, with_near)
    copies = [p for p in plan if p[0] != "control"]
    print("=== source_dedup --acceptance: seed %d copies of one module across %d repos, then cluster ==="
          % (len(copies), len(copies)))
    print("\nTHE SEED (built in a temporary directory, and removed when this returns —")
    print("          the live corpus is never opened on this path, let alone written)")

    with tempfile.TemporaryDirectory(prefix="source_dedup_seed_") as root:
        seeded = seed_corpus(root, plan, cs, cw, opts, with_vectors=with_near)
        by_role = {}
        for s in seeded["seeds"]:
            by_role.setdefault(s["role"], []).append(s)

        print("\n  %-9s %-16s %-26s %-10s %-8s %s"
              % ("ROLE", "REPO", "PATH", "BLOB", "TICKET", "WHY IT IS HERE"))
        print("  " + "-" * 116)
        why = {"original": "the source every other copy is a copy of",
               "exact":    "byte-identical -> same content sha256 -> the EXACT relation",
               "ast":      "reformatted+commented -> different sha, same AST -> the AST relation",
               "near":     "every local renamed -> different sha AND different AST -> the NEAR relation",
               "control":  "unrelated source: enters the collection, must NOT enter the cluster"}
        for s in seeded["seeds"]:
            print("  %-9s %-16s %-26s %-10s #%-7s %s"
                  % (s["role"], s["repo"], s["path"], s["sha"][:8], s["ticket"], why[s["role"]]))
        print("\n  plus ticket #%d with ref `omni-blob:%s` — the OTHER ticket_works ref convention"
              % (seeded["blob_ref_ticket"], seeded["blob_ref_sha"][:8]))

        # The evidence for "no auto-delete", taken BEFORE the engine runs.
        before = _snapshot(root)

        ns = _ns(omni_db=seeded["omni_db"], omni_git=seeded["omni_git"], store=seeded["store"],
                 mem_graph_db=os.path.join(root, "no_such_mem_graph.db"),
                 forge_db=os.path.join(root, "no_such_forge.db"),
                 congruency_db=seeded["tickets_db"])
        src = rv.open_sources(ns, cs)
        try:
            res = dedup("retry.py", src, rv, cs, cw, dict(opts, exact_only=not with_near))
        finally:
            for k in ("omni", "store", "graph", "forge", "cong"):
                if src.get(k) is not None:
                    src[k].close()
        after = _snapshot(root)

        print("\nTHE CLUSTERING (the engine, run over the seeded corpus)")
        render(res)

        # ── the checks ───────────────────────────────────────────────────────────────────────────
        checks = []
        want = {(s["repo"], s["path"]) for s in seeded["seeds"] if s["role"] != "control"}
        ctrl = by_role["control"][0]

        # 1. the N copies land in ONE cluster
        holding = [c for c in res["clusters"]
                   if want & {(m["repo"], m["path"])
                              for m in [c["canonical"]] + c["duplicates"]}]
        checks.append(("the seeded copies fall in exactly ONE cluster (found %d)" % len(holding),
                       len(holding) == 1))
        cl = holding[0] if len(holding) == 1 else None
        got = set()
        if cl:
            got = {(m["repo"], m["path"]) for m in [cl["canonical"]] + cl["duplicates"]}

        # 2. ALL N of them, and nothing else
        checks.append(("the cluster holds ALL %d seeded copies (missing: %s)"
                       % (len(want), sorted(p for _r, p in (want - got)) or "none"), got >= want))
        checks.append(("the cluster holds NOTHING but the seeded copies (extra: %s)"
                       % (sorted(p for _r, p in (got - want)) or "none"), got <= want))

        # 3. exactly one canonical, and the rest are dups
        checks.append(("the cluster names exactly ONE canonical", bool(cl)))
        checks.append(("the other %d copies are listed as duplicates (got %d)"
                       % (len(want) - 1, len(cl["duplicates"]) if cl else 0),
                       bool(cl) and len(cl["duplicates"]) == len(want) - 1))

        # 4. every duplicate carries ITS OWN seeded ticket
        if cl:
            tick_by_path = {s["path"]: s["ticket"] for s in seeded["seeds"]}
            missing = [d["path"] for d in cl["duplicates"]
                       if tick_by_path[d["path"]] not in [t["ticket"] for t in d["tickets"]]]
            checks.append(("every duplicate carries its own seeded ticket (missing: %s)"
                           % (missing or "none"), not missing))
            # 5. the omni-blob ref convention reaches every byte-identical copy
            exact_paths = {s["path"] for s in seeded["seeds"] if s["role"] in ("original", "exact")}
            reached = {m["path"] for m in [cl["canonical"]] + cl["duplicates"]
                       if seeded["blob_ref_ticket"] in [t["ticket"] for t in m["tickets"]]}
            checks.append(("the `omni-blob:<sha>` ticket ref reaches all %d byte-identical copies"
                           % len(exact_paths), reached == exact_paths))
            # 6. each duplicate's relation is the one it was seeded to demonstrate
            role_by_path = {s["path"]: s["role"] for s in seeded["seeds"]}
            canon_role = role_by_path[cl["canonical"]["path"]]
            wrong = []
            for d in cl["duplicates"]:
                role = role_by_path[d["path"]]
                # original/exact copies are byte-identical to each other; against an exact/original
                # canonical they must read `exact`, and the ast/near copies must read `ast`/`near`.
                expect = "exact" if role in ("original", "exact") else role
                if canon_role in ("original", "exact") and d["relation"] != expect:
                    wrong.append("%s: expected %s, got %s" % (d["path"], expect, d["relation"]))
            checks.append(("each duplicate's relation to the canonical is the seeded one (%s)"
                           % ("; ".join(wrong) if wrong else "all as seeded"), not wrong))
            # 7. the recommendation collapses the identical copies and only REVIEWS the near one
            near_dups = [d for d in cl["duplicates"] if d["relation"] == "near"]
            checks.append(("every exact/AST duplicate is recommended `collapse`",
                           all(d["action"] == "collapse" for d in cl["duplicates"]
                               if d["relation"] in ("exact", "ast"))))
            # "no near duplicate IN THE CLUSTER" — which is not the same as "none seeded": a near copy
            # can be seeded and still not cluster (raise --threshold above its cosine and it will not),
            # and saying "none seeded" there would be a false claim about this run's own seed.
            checks.append(("every near duplicate is recommended `review`, never `collapse`"
                           + (" (no near duplicate in the cluster)" if not near_dups else ""),
                           all(d["action"] == "review" for d in near_dups)))

        # 8. the control entered the collection but NOT the cluster — the proof the engine discriminates
        in_cluster = any((ctrl["repo"], ctrl["path"]) in
                         {(m["repo"], m["path"]) for m in [c["canonical"]] + c["duplicates"]}
                         for c in res["clusters"])
        checks.append(("the unrelated control module is NOT clustered with the copies", not in_cluster))

        # 9. no auto-delete, and no write: the ticket's read-only constraint, proved in isolation
        checks.append(("no seeded file was deleted (%d before, %d after)" % (len(before), len(after)),
                       set(before) <= set(after)))
        checks.append(("no seeded file was modified — every byte identical before and after",
                       all(after.get(k) == v for k, v in before.items())))
        sidecars = sorted(p for p in after if p.endswith("-wal") or p.endswith("-shm"))
        checks.append(("no -wal/-shm sidecar was created by the read (%s)" % (sidecars or "none"),
                       not sidecars))
        new = sorted(set(after) - set(before))
        checks.append(("the engine created no file at all (%s)" % (new or "none"), not new))
        actions = {d["action"] for c in res["clusters"] for d in c["duplicates"]}
        checks.append(("the proposal contains no delete/rewrite action (actions: %s)"
                       % (sorted(actions) or "none"), actions <= {"collapse", "review"}))

        print("\nTHE CHECKS")
        good = True
        for what, ok in checks:
            print("  [%s] %s" % ("PASS" if ok else "FAIL", what))
            good = good and ok
        print("\n%s — %d/%d checks passed"
              % ("ACCEPTANCE PROVED" if good else "ACCEPTANCE FAILED",
                 sum(1 for _w, ok in checks if ok), len(checks)))
        if good and not with_near:
            print("(The similarity leg was not exercised — see the NOTE at the top of this run.)")
        return 0 if good else 1


class _ns(object):
    """A tiny attribute bag for resolver.open_sources, which takes an argparse namespace.

    Built explicitly rather than by re-parsing argv so the seeded acceptance cannot accidentally
    inherit a real corpus path from the command line.
    """

    def __init__(self, **kw):
        self.__dict__.update(kw)


# ── main ─────────────────────────────────────────────────────────────────────────────────────────
def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    rv = load_resolver()
    cs = rv.load_indexer()
    ap = argparse.ArgumentParser(
        description="the source dedup engine (#194): consume the resolver's match collection and "
                    "cluster it into canonical + duplicates — exact via content sha256, near via a "
                    "similarity threshold (#190), grouped by codebean's AST-normalized form (#183). "
                    "A read-only proposal: it has no delete, move or rewrite path.",
        epilog="kinds: auto (default), " + ", ".join(rv.KINDS))
    ap.add_argument("identifier", nargs="?", default="",
                    help="what to deduplicate: a file-name, a symbol name, a path, a git blob hash, "
                         "a content sha256, '#N', or free text — anything the resolver accepts")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help="near-duplicate cosine floor (default: %.2f)" % DEFAULT_THRESHOLD)
    ap.add_argument("--exact-only", action="store_true",
                    help="cluster by content sha256 and AST only; skip the similarity leg entirely")
    ap.add_argument("--include-singletons", action="store_true",
                    help="also show units that are nobody's duplicate (hidden by default)")
    ap.add_argument("--kind", default="auto", help="override the resolver's kind detection (default: auto)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help="max matches gathered per resolver leg (default: %d)" % DEFAULT_LIMIT)
    ap.add_argument("--repo", default="", help="restrict the collection to one repo in the corpus")
    ap.add_argument("--json", action="store_true", help="print the clustering as JSON")
    ap.add_argument("--acceptance", action="store_true",
                    help="SEED N copies of a module across repos and PROVE the clustering; "
                         "writes only inside a temporary directory, which it then removes")
    ap.add_argument("--seed-n", type=int, default=5,
                    help="--acceptance: how many copies to seed (default: 5, minimum: %d)" % SEED_MIN)
    ap.add_argument("--omni-db", default=cs.OMNI_DB, help="omni-git index (default: %s)" % cs.OMNI_DB)
    ap.add_argument("--omni-git", default=cs.OMNI_GIT, help="omni-git objects (default: %s)" % cs.OMNI_GIT)
    ap.add_argument("--store", default=cs.STORE, help="#189 vector store (default: %s)" % cs.STORE)
    ap.add_argument("--mem-graph-db", default=rv.MEM_GRAPH_DB, help="mem-graph (default: %s)" % rv.MEM_GRAPH_DB)
    ap.add_argument("--forge-db", default=rv.FORGE_DB, help="forge ledger (default: %s)" % rv.FORGE_DB)
    ap.add_argument("--congruency-db", default=rv.CONGRUENCY_DB,
                    help="congruency state db, for associated tickets (default: %s)" % rv.CONGRUENCY_DB)
    ap.add_argument("--codebean", default=cs.CODEBEAN, help="codebean_mcp dir (default: %s)" % cs.CODEBEAN)
    ap.add_argument("--litellm", default=cs.LITELLM, help="litellm proxy (default: %s)" % cs.LITELLM)
    ap.add_argument("--model", default=cs.MODEL, help="embedding model (default: %s)" % cs.MODEL)
    ap.add_argument("--timeout", type=int, default=120, help="embed timeout secs (default: 120)")
    a = ap.parse_args()

    if a.kind != "auto" and a.kind not in rv.KINDS:
        print("source_dedup: unknown --kind %r — kinds are: auto, %s" % (a.kind, ", ".join(rv.KINDS)))
        return 2
    if not (a.identifier or a.acceptance):
        ap.error("give an identifier to deduplicate, or --acceptance")
    if not 0.0 <= a.threshold <= 1.0:
        print("source_dedup: --threshold %r is outside [0.0, 1.0] — it is a cosine between "
              "unit-norm vectors" % a.threshold)
        return 2

    cw = load_codebean(cs, a.codebean)
    opts = {"kind": a.kind, "threshold": a.threshold, "exact_only": a.exact_only,
            "include_singletons": a.include_singletons, "limit": max(1, a.limit), "repo": a.repo,
            "model": a.model, "litellm": a.litellm, "timeout": a.timeout}

    if a.acceptance:
        # The seeded corpus is built and read entirely inside a temp dir: the live corpus is never
        # opened on this path, so none of the --omni-db/--store/... defaults above are touched.
        return acceptance(rv, cs, cw, opts, a)

    src = rv.open_sources(a, cs)
    try:
        if src["store"] is None and not a.exact_only:
            raise Fault("no #189 vector store at %s — there are no vectors, so the near-duplicate "
                        "relation cannot run; build it with tools/code_sim_indexer.py, or pass "
                        "--exact-only to cluster by content sha256 and AST alone" % a.store)
        res = dedup(a.identifier, src, rv, cs, cw, opts)
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
        print("source_dedup: %s" % e)
        sys.exit(2)
    except BrokenPipeError:
        sys.exit(0)                                   # `| head` closed the pipe — not an error
    except KeyboardInterrupt:
        print("source_dedup: interrupted")
        sys.exit(130)
    except Exception as e:  # noqa: BLE001 — note-for-claude: a report, never a traceback
        # The resolver's and #189's own faults surface here by class NAME rather than by identity:
        # they are loaded from source, so `except rv.Fault` would need the module this handler may
        # not have (a load failure raises before `rv` exists).
        name = type(e).__name__
        if name == "Fault":
            print("source_dedup: %s" % e)
            sys.exit(2)
        if name in ("EmbedError", "PairError"):
            print("source_dedup: %s" % e)
            sys.exit(3 if name == "EmbedError" else 1)
        bug_report("main", e, " ".join(sys.argv), e)
        print("source_dedup: unexpected error: %s (a bug report was filed to %s)"
              % (e, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl")))
        sys.exit(2)
