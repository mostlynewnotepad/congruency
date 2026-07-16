#!/usr/bin/env python3
"""forge_evolution — PART 2 of 2 (ticket #452): the forge's EVOLUTION TIMELINE, the CONTAINMENT
RETIREMENT GATE, and the ORPHAN-BLOB worklist.

PART 1 (ticket #445, tools/forge_family_tree.py) clusters config/forge/remotes/*.git — 264 bare
repos — into 109 LINEAGES and classifies each. It deliberately never retires or merges anything.
This tool adds the two things Part 1 does not do, and nothing else:

  1. THE EVOLUTION TIMELINE   Part 1 carries NO time data (its JSON holds zero date keys). Git has
                              every date for free. Per lineage: the root commit's date, each
                              member's FORK-POINT date, each member's tip date, and the fork WIDTH
                              (tip date minus fork-point date — how long that fork ran alone).
                              Members are ordered by fork-point date, so the tree reads as STAGES.
  2. THE RETIREMENT GATE      A mechanical CONTAINMENT PROOF, not a judgement. A fork is SAFE TO
                              OMIT if and only if EVERY file at its tip resolves, by CONTENT
                              IDENTITY, to a blob already present in its home repo(s). Any file
                              that does not resolve is emitted by name: that list IS the
                              merge-home worklist, and it shrinks to empty exactly when the fork
                              is safe to drop.
  3. THE ORPHAN SET           Code blobs that exist ONLY in non-canonical tips — content that a
                              naive "unify on the canonical tips" would SILENTLY LOSE. Emitted as
                              a first-class report: blob sha, path, holder, lineage.

    python3 forge_evolution.py                          # timeline + gate + orphans, live forge
    python3 forge_evolution.py --lineage agent_tools_suite --timeline
    python3 forge_evolution.py --orphans                # the orphan worklist alone
    python3 forge_evolution.py --gate                   # the containment gate alone
    python3 forge_evolution.py --json -                 # machine-readable, to stdout
    python3 forge_evolution.py --family-json tree.json  # consume a Part-1 JSON instead of running it
    python3 forge_evolution.py --selftest               # throwaway git repos in a temp dir

THIS TOOL CONSUMES PART 1 — IT NEVER RE-DERIVES IT. With no --family-json it runs
`forge_family_tree.py --json -` (the sibling file) and builds on the lineages, members, tips and
classification that come back. Two consequences worth stating plainly, because both are traps:

  * TIPS ARE PART 1'S, NEVER RE-RESOLVED HERE, AND **HEAD IS NEVER TRUSTED**. 183 of the 264 repos
    (69%) have an UNRESOLVABLE HEAD — a symref to a refs/heads/master that does not exist. For
    every one of them `git rev-parse HEAD` PRINTS THE LITERAL STRING "HEAD" ON STDOUT. What makes
    that dangerous is the combination: the string looks like a revision, so any caller that reads
    stdout without checking the status — a shell `$(git rev-parse HEAD)`, or a capture helper that
    ignores the exit code — feeds the word "HEAD" onward as if it were a sha. Part 1 already solved
    this (it resolves tips from `for-each-ref refs/heads` only); this tool takes its answer and
    never second-guesses it.

    A CORRECTION, because this tool re-measured it rather than inheriting it: ticket #452 says that
    command "EXITS 0". IT DOES NOT — measured across all 183, `git rev-parse HEAD` exits 128 every
    time, and so does `git rev-parse --abbrev-ref HEAD`; both still print "HEAD" on stdout. (Part 1
    never claimed exit 0 — it says `rev-parse --verify HEAD` FAILS, which is correct.) The trap is
    real and the mitigation is unchanged; only the exit code in the ticket's prose is wrong. Do not
    "fix" a caller by trusting that a zero exit means a resolved HEAD here.

    (Also verified while writing this tool: Part 1's tips and the HEAD-first tips
    forge_refactor_ticketer.py resolves agree on all 261 repos that have a tip — so consuming Part
    1 costs nothing in coverage.)
  * DIRECTION IS NOT THIS TOOL'S TO DECIDE. Part 1 owns the operator's home mapping via
    --override / --override-file; those flags are FORWARDED to it unchanged, and whatever it names
    `canonical` is the home this tool proves containment against. This tool PROPOSES; it never
    infers direction from topology. LINEAR and FORK-CAME-HOME are the same git shape and differ
    only in intent, which is not in the DAG. --home adds EXTRA home repos for the gate (a grab-bag
    fork's packages can belong to several different homes); it never renames a canonical. A home
    may live in ANOTHER lineage — that is the case the flag exists for — so the tip scans are keyed
    by REPO NAME and a cross-lineage home resolves content exactly like the canonical does. Two
    rules keep the flag from destroying the worklist it is meant to shrink: a repo named as a HOME
    is a DESTINATION and is never itself an omit candidate (it would be gated against itself and
    trivially "prove" it may be dropped — the same exclusion the canonical already gets, reported
    under `not_omit_candidates`), and a --home naming a lineage or repo Part 1 does not know is a
    usage error that STOPS the run, never a silent NOT-SAFE that blames git for a typo.

OMNI IS BLACK-BOXED — THIS TOOL NEVER OPENS IT, AND THAT IS ENFORCED IN CODE.
The black box stands on TWO facts, and only these two. Both are true; neither is about how much of
the forge omni holds.

  LEG 1 — OMNI IS NOT A GIT. config/forge/archives/omni.git is a TOOL MADE OF GITS (an archive of
  many repos' refs under refs/gitlab/*, refs/archives/*, refs/tarball/*) — a DEDUPLICATION DEVICE,
  and it was a TEST, not an archive of record. Every ordinary git command against it fails:
  `rev-parse HEAD` and `rev-parse --abbrev-ref HEAD` each exit 128 while PRINTING the literal
  string "HEAD" on stdout, `ls-tree HEAD` says "fatal: Not a valid object name HEAD", and `log -1`
  says "fatal: your current branch 'master' does not have any commits yet". There is nothing here
  that could read it correctly even if it were allowed to.
  LEG 2 — OMNI IS STALE AND INCOMPLETE. It does not hold the forge's current work: it is MISSING
  agent_tools_suite.git's tip 888d3447c6 — the very family this tool works through below — and 67
  other tips besides. What it does hold therefore cannot be trusted as current.

HOW MUCH OF THE FORGE OMNI HOLDS — MEASURED BY OBJECT, AND ONLY BY OBJECT (ticket #462). Of the
264 bare repos in config/forge/remotes, 261 have a resolvable tip (3 have no refs at all); omni
CONTAINS 193 of those 261 tips and is missing 68. Omni covers 74% of the forge's tips.

  THE METHOD IS THE POINT: A BY-NAME JOIN DOES NOT WORK HERE AND MUST NOT BE USED. Omni's refs are
  shaped `refs/gitlab/<slug>/heads/<branch>` while the forge's bare repos are named
  `gitlab__<slug>.git`. The two naming conventions do not align, so matching omni's repos to the
  forge's BY NAME matches almost nothing, and the coverage that falls out of it is an artifact of
  the mismatch rather than a measurement of anything. An earlier by-name attempt was reported as
  fact and propagated into this file in three places; ticket #462 exists to remove it. The
  name-independent method is the only one that holds, and it is re-runnable: take each forge repo's
  tip as Part 1 resolves it (from refs/heads, NEVER from HEAD) and ask
  `git -C config/forge/archives/omni.git cat-file -e <tip>` — a tip omni can name, omni has. A
  naming convention can disagree with another naming convention; an object id cannot.
  A THIRD NUMBER IS QUOTED ELSEWHERE AND ANSWERS A THIRD QUESTION: the "~86%" is BLOB coverage in
  the `occ` index — not repo coverage, and not the tip coverage above. Three different numbers
  measuring three different things; do not conflate them.

THE COVERAGE FIGURE IS NOT WHY THE BLACK BOX EXISTS, AND 74% DOES NOT SOFTEN IT. Legs 1 and 2 are
exactly as true at 74% as at any other number, and they are the whole justification. Therefore
config/forge/remotes/*.git is the ONLY authority here: this tool does not walk refs/archives/*,
does not read omni.git, and never treats it as a source of dates or provenance.
EVERY OMNI FACT ABOVE IS QUOTED, NOT RE-MEASURED BY THIS TOOL — and none of them can be re-measured
here. The not-a-git legs come from #452 and the 193-of-261 coverage from #462, each established by
a one-off probe run OUTSIDE this file, because measuring any of them means running git against
omni, which is the very thing this tool is forbidden to do. Re-deriving 193/261 in this file would
break the guarantee the guard exists to make; if you want the number again, run the cat-file probe
yourself. The prohibition is mechanical, not a promise: `_guard_store()` refuses any store named
omni.git or sitting under an archives/ directory, it is called by the single git entry point every
read in this file goes through, and --selftest asserts that it fires. A future omni interface is a
separate tool with its own contract.

CONTENT IDENTITY — THE MODULE-SHA. Identity is not the git blob sha1: two copies of a module that
differ only in whitespace or comments are the SAME module and must count as contained, while a
semantically changed file must NOT. So this tool uses the SAME module-sha that
tools/forge_refactor_ticketer.py computes (`module_identity`, forge_refactor_ticketer.py:816-832),
rather than inventing a second definition of sameness:

    sha256("raw:" + bytes)[:16]                    — non-Python, or Python that does not parse
    sha256("ast:" + _ast_norm(source))[:16]        — Python that parses

`_ast_norm` is codebean's own normalizer (codebean_mcp/prototype/code_wrapper.py) —
`ast.dump(ast.parse(ast.unparse(ast.parse(src))))`. This tool is standalone (stdlib + git only), so
it MIRRORS that one-liner rather than importing codebean; `--selftest` then EXTRACTS the real
`_ast_norm` from codebean's source and asserts the mirror agrees with it on real inputs, so the two
cannot drift apart silently. Note `raw:` is concatenated as BYTES (`b"raw:" + raw`) — a blob that is
not UTF-8 still gets an identity. A docstring is real content and does NOT normalize away.

THE MEASURED HEADLINE, so a reader can check this tool against the forge rather than trust it.
A bare run over the live forge reports, and `--json -` carries in `totals` (measured; ~55 seconds):

    109 lineages / 261 repos scanned at their tips
    121 ORPHAN code blobs (2.08% of 5,825 unique code blobs at the member tips); 101 orphan
        MODULE identities of 5,771 unique — the number the gate acts on, see THE ORPHAN SET below
    152 forks examined -> 81 SAFE TO OMIT (proven) / 71 NOT safe, 418 files of merge-home work
    6 of the 109 lineages put content AT RISK (the rest are naming decisions — see WHAT PUTS
        CONTENT AT RISK below)

and, for the family ticket #452 works through — `--lineage agent_tools_suite --timeline --gate`:

    2026-07-08 20:38  root 379ac05319  "agent_tools_suite: crankimg — a single-purpose pi-image…"
    2026-07-11 02:23  FORK POINT = agent_tools_suite.git tip 888d3447c6 ("add deploy_test loop…")
    2026-07-11 02:23  fork point 888d3447c6  -> jail.git tip 38e95ad16d at 2026-07-12 14:07
                      ran 1.49 days alone, 6 files changed (5 added, 1 modified)
    jail.git  NOT SAFE TO OMIT — 33 of 39 files resolve; the 6-file MERGE-HOME WORKLIST is
    claude-gui.py, crank_job_backlog.json, crank_job_congruency.json, crankws-mcp/server.py,
    registry.crankws.json, start-crank.py — they have not come home, so jail cannot be dropped.

TWO PLACES WHERE THIS TOOL'S MEASUREMENT DISAGREES WITH TICKET #452's PROSE. Both were re-measured
from the live forge while writing this tool, and in both cases the ticket's own DEFINITION is
implemented and its derived FIGURE is corrected. Neither number is hardcoded anywhere: both are
computed, so a reader can re-run and check.

  * THE ORPHAN COUNT: the ticket says "118 blobs (2.1% of 5,741 unique code blobs)". Measured here:
    121 of 5,825 (2.08%) — the percentage agrees, the absolute counts are 3 and 84 higher. The
    definition implemented is the one the ticket states: a code blob (an extension in SOURCE_EXT,
    the ticketer's own set) present at some NON-canonical member tip and present at NO canonical
    tip anywhere in the forge, over Part 1's tips. Several other readings were measured and none
    reproduces 118/5,741 either: deduping by module-sha instead of blob sha1 gives 101 of 5,771;
    restricting the universe to multi-member lineages gives 130 of 5,763; restricting it to
    lineages with more than one distinct tip gives 154 of 5,310. The HEAD-first tip resolution that
    forge_refactor_ticketer.py uses was also ruled out as the cause — it agrees with Part 1 on
    every repo. The ticket's exact universe could not be reconstructed, so this tool reports what
    the forge actually holds and states the definition it used rather than fitting a number.
  * THE FORK WIDTH IN THE WORKED EXAMPLE: the ticket's three agent_tools_suite timestamps are all
    CORRECT and this tool reproduces them exactly (root 2026-07-08 20:38, fork point 2026-07-11
    02:23, jail tip 2026-07-12 14:07). Its "-> jail ran 4 days alone" is not, because the ticket
    defines the width as "tip date minus fork-point date" and 07-11 02:23 -> 07-12 14:07 is
    1.49 days. 4 days is the ROOT-to-tip span (3.73 days, rounds to 4) — a different measurement.
    So this tool implements the stated definition and prints BOTH numbers, each labelled for what
    it is: `fork_width_days` (1.49 — how long the fork ran alone) and `span_from_root_days` (3.73 —
    the lineage's whole life). They are not interchangeable: the width is what a retirement
    decision cares about.

WHAT PUTS CONTENT AT RISK — computed, not assumed. Ticket #452 §5 notes that for a LINEAR family
the direction cannot lose code (the canonical supersets the rest) and that only DIVERGED/SPLIT-STORE
put content at risk. That is true ONLY while the canonical IS the topological superset. It is not
true of a family whose direction the operator REVERSED: the jail family is topologically LINEAR, yet
its canonical (agent_tools_suite.git) is the side that TRAILS, so jail's 6 files are genuinely at
risk. This tool therefore does not read the risk off the topology label. It PROVES it: `risk` is
NONE only when the canonical tip is a descendant of (or equal to) every member's tip, so nothing any
member holds can be lost — and AT-RISK otherwise, whatever the label says. A NONE family is a naming
decision; an AT-RISK family is a merge.

    Measured: 103 of the 109 lineages are risk NONE and 6 are AT-RISK — jazz, notes_db, z3_mcp (the
    3 DIVERGED), big-jazz, code__code (the 2 SPLIT-STORE), AND agent_tools_suite. That last one is
    the whole point: it is the jail family, its topology is LINEAR, and reading the risk off the
    label would have called the one family this ticket exists for a safe naming decision.

"EVERY FILE AT ITS TIP" INCLUDES THE ONES THIS TOOL CANNOT READ. The gate's rule is an IF AND ONLY
IF, so the only way to earn SAFE TO OMIT is to resolve every file — and a file whose blob the object
store will not produce has NOT been resolved. It is possible for `git ls-tree` to LIST a file whose
blob is missing or corrupt (`cat-file` then fails on that sha while the tip still enumerates), and
such a file is recorded as UNREADABLE: it keeps its place in the tip's file count, its content
identity is None, and it goes on the merge-home worklist marked `unreadable` with the reason. It can
never be counted as contained, because nobody can show it came home. This matters because the
failure is silent by nature — the file is still listed, so a scan that dropped what it could not
read would hand the gate a SHORTER tip in which every remaining file happens to resolve, and the
fork's real work would vanish from the worklist, the orphan set and the totals at once. UNKNOWN IS
NEVER PROOF, at any scale: an unreadable BLOB is one worklist entry; an unreadable TIP (ls-tree
itself fails, or the blob batch never answers) is reported NOT SAFE with the reason and an empty
worklist, since a git that never ran is an environment failure, not a list of un-merged work.
`totals.unreadable_blobs` and the `unreadable_blobs` list report every such gap; on the live forge
both are 0 — no forge repo is missing an object today, so this rule changes none of the figures
above. --selftest proves it the only way that means anything: it builds a fork holding a file that
never came home, deletes exactly that blob's loose object, and asserts the verdict, the file count
and the worklist are IDENTICAL to the intact run.

AT-RISK IS NOT "CANNOT RETIRE", AND THE TWO MUST NOT BE CONFUSED. `risk` is what the DAG can prove
about a whole family; the gate is what CONTENT proves about one fork. They disagree on purpose: a
family can be AT-RISK (its canonical does not contain some member's tip) while that member is still
PROVEN SAFE TO OMIT, because the files it holds came home by content even though its commits never
merged. That gap between ancestry and content is exactly why the gate exists — ancestry is what git
can see, content identity is what actually decides whether dropping a repo loses anything.
--selftest asserts a family in precisely that state.

SIDE EFFECTS — NONE. Every git command this tool runs is a read (log, merge-base, ls-tree, cat-file,
rev-list). It never writes to config/forge/remotes/*.git — the bare repos are the archive — and it
never touches the governance db (it does not open, or even import, sqlite). It PLANS retirement; it
never performs it. Unlike Part 1 it creates no scratch object store: where a merge-base needs both
tips in one store, it looks for a member that ALREADY holds both and reports the fork point as
UNKNOWN, with the reason, when none does — a SPLIT-STORE family is described, never fetched. The
only file this tool ever writes is the --json path when you name one. Proven on the live forge: a
real `--json -` run leaves all 264 bare repos byte-identical (12,695 files, sha1 of the whole tree
unchanged) and leaves this tools/ directory byte-identical too — RUN as a script it writes no .pyc,
both because __main__ never gets one and because `sys.dont_write_bytecode` (set at import, before
any sibling is read) stops the tools it reads from leaving one either. --selftest asserts the same
byte-identity over throwaway repos and uses no network and no live db.

One honest exception, because it is the tools/ directory and a reader checking these claims will
trip it: if you IMPORT this module instead of running it (`import forge_evolution`, e.g. to drive
gate() directly), CPython writes tools/__pycache__/forge_evolution.*.pyc when it compiles the file
— before the first line of this module can set anything. That is CPython's import machinery, not a
write this tool makes; no code in any Python file can prevent its OWN .pyc (only the importer can,
via `python3 -B` / PYTHONDONTWRITEBYTECODE=1). It is gitignored bytecode (`.gitignore` lines 4-5:
`__pycache__/`, `*.pyc`), regenerated on demand and never part of a commit. Nothing above is
weakened: the guarantees are about the ARCHIVE and the governance db, which no import touches.

exits 0 on success; 2 on a usage/environment error (a one-line message, never a traceback);
1 if --selftest has a failing check.
"""
import argparse
import ast
import collections
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True   # importing/being imported must not litter .pyc into the repo

# The source extensions a "code blob" has, mirroring forge_refactor_ticketer.SOURCE_EXT so the
# orphan universe here means the same thing it means there. Deliberately NOT source: .pyc
# (bytecode), .json/.yml/.toml (data), .md/.txt (prose), .bin/.mp3/.pdf (assets).
SOURCE_EXT = (".py", ".php", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh", ".bash",
              ".rb", ".pl", ".go", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".lua", ".r",
              ".sql", ".sol")
PY_EXT = (".py",)

# Stores this tool refuses to open, mapped to why. omni.git is not a git — it is a TOOL MADE OF
# GITS — and ticket #452 §2 black-boxes it on two legs: it is not a git, and it is stale. Coverage
# is NOT one of the legs (#462): omni holds 74% of the forge's tips, which changes nothing here.
# See the module docstring; _guard_store enforces this.
BLACK_BOXED = {
    "omni.git": "omni.git is NOT a git repository — it is a tool made of gits (an archive of many "
                "repos' refs), so every ordinary git command against it fails; and it is STALE — "
                "measured BY OBJECT (a by-name join does not work: omni's refs are refs/gitlab/"
                "<slug> while the forge's repos are gitlab__<slug>.git) it holds 193 of the "
                "forge's 261 resolvable tips (74%) and is MISSING 68 of them, including "
                "agent_tools_suite.git's tip 888d3447c6. Ticket #452 §2 black-boxes it on those "
                "two facts and #462 leaves the box exactly as it is: config/forge/remotes/*.git is "
                "the only authority. Reading omni is a separate tool with its own contract.",
}
ARCHIVES_DIR = "archives"       # config/forge/archives/ — where omni.git lives; never opened here

SAFE, NOT_SAFE = "SAFE TO OMIT (proven)", "NOT SAFE TO OMIT"
RISK_NONE, RISK_AT = "NONE", "AT-RISK"
GIT_TIMEOUT = 120

# The `kind` of a scanned file's identity: how its module-sha was derived, or that it has none.
# UNREADABLE means ls-tree LISTS the file but its blob will not come out of the object store (a
# missing/corrupt object). Such a file has NO content identity, so it can never be PROVEN to have
# come home: §3's gate counts it as unresolved work, never as contained. It is a distinct value —
# not None, not a silent drop — precisely so no code path can mistake "we could not read it" for
# "it is not there".
UNREADABLE = "unreadable"


class ForgeError(RuntimeError):
    """A usage or environment problem worth one clear line, not a traceback."""


# ── git: reads only, and never against a black-boxed store ────────────────────────────────────

def _guard_store(gitdir):
    """Refuse a store ticket #452 §2 black-boxes. Called by the ONE git entry point below.

    This is what makes "this tool never opens omni" a mechanical fact instead of a promise: there
    is no path to a git command in this file that does not pass through here first.
    """
    norm = os.path.normpath(gitdir)
    base = os.path.basename(norm)
    parent = os.path.basename(os.path.dirname(norm))
    if base in BLACK_BOXED:
        raise ForgeError("REFUSING to open %s: %s" % (base, BLACK_BOXED[base]))
    if parent == ARCHIVES_DIR:
        raise ForgeError(
            "REFUSING to open %s: it sits under an %s/ directory, which is where the forge keeps "
            "omni.git. This tool reads config/forge/remotes/*.git only (ticket #452 §2)."
            % (norm, ARCHIVES_DIR))


def git(gitdir, *args, **kw):
    """Run a READ-ONLY git command against a bare repo. Returns (rc, stdout), never raises for a
    non-zero git.

    `text=False` returns bytes — blob content must never be decoded here, because a blob that is not
    UTF-8 still has an identity (see module_sha). The environment is pinned so a user's global
    config, a credential prompt, or a stray hook cannot change the answer or block the run.
    """
    _guard_store(gitdir)
    text = kw.get("text", True)
    env = dict(os.environ)
    env.update({
        "GIT_TERMINAL_PROMPT": "0",      # never block on credentials
        "GIT_ASKPASS": "true",
        "GIT_CONFIG_NOSYSTEM": "1",      # a system/global config must not steer the result
        "GIT_PAGER": "cat",
    })
    try:
        p = subprocess.run(["git", "--git-dir", gitdir] + [str(a) for a in args],
                           capture_output=True, text=text, env=env,
                           timeout=kw.get("timeout", GIT_TIMEOUT))
    except FileNotFoundError:
        raise ForgeError("git is not on PATH — this tool reads the forge's bare repos with git")
    except subprocess.TimeoutExpired:
        return 1, ("" if text else b"")
    return p.returncode, (p.stdout.strip() if text else p.stdout)


def git_ok(gitdir, *args, **kw):
    """stdout of a git command, or "" if it failed."""
    rc, out = git(gitdir, *args, **kw)
    return out if rc == 0 else ""


def have_git():
    try:
        return subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


# ── content identity: the module-sha (see CONTENT IDENTITY in the module docstring) ───────────

def _ast_norm(src):
    """codebean's normalizer, MIRRORED — codebean_mcp/prototype/code_wrapper.py.

    Normalise source through parse -> unparse -> dump so formatting does not matter. This tool is
    standalone (stdlib + git only), so codebean is not imported; `codebean_ast_norm()` below
    extracts the real function from codebean's source and --selftest asserts this mirror agrees
    with it, so the two cannot drift apart unnoticed.
    """
    return ast.dump(ast.parse(ast.unparse(ast.parse(src))))


def module_sha(raw, path):
    """(module_sha, kind) — the CONTENT IDENTITY of one blob, keyed to how it was derived.

    Mirrors forge_refactor_ticketer.module_identity (forge_refactor_ticketer.py:816-832) exactly:
    AST-normalized for a Python blob that PARSES, content sha256 for everything else. The
    'ast:'/'raw:' prefixes keep the two namespaces disjoint, so a file can never collide across
    them. A Python 2 / truncated / not-really-python blob falls through to 'raw' rather than being
    dropped: an unparseable file is still content that must come home.
    """
    if os.path.splitext(path)[1].lower() in PY_EXT:
        try:
            norm = _ast_norm(raw.decode("utf-8"))
            return hashlib.sha256(("ast:" + norm).encode("utf-8")).hexdigest()[:16], "ast"
        except (UnicodeDecodeError, SyntaxError, ValueError, RecursionError):
            pass
    return hashlib.sha256(b"raw:" + raw).hexdigest()[:16], "raw"


def codebean_ast_norm(start=None):
    """codebean's REAL `_ast_norm`, or None if codebean is not on this host.

    The function is EXTRACTED from codebean's source and compiled on its own — codebean is never
    imported. That keeps this tool standalone and side-effect free (importing the module would run
    its top level and could write bytecode), while still letting --selftest prove that the mirror
    above is faithful to the real definition rather than merely plausible.
    """
    d = start or os.path.dirname(os.path.realpath(__file__))
    src_path = None
    while True:
        cand = os.path.join(d, "codebean_mcp", "prototype", "code_wrapper.py")
        if os.path.isfile(cand):
            src_path = cand
            break
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    if not src_path:
        return None
    try:
        with open(src_path, "r") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_ast_norm":
            ns = {"ast": ast}
            try:
                exec(compile(ast.Module(body=[node], type_ignores=[]), src_path, "exec"), ns)
            except Exception:                                  # noqa: BLE001 — absence is not a bug
                return None
            return ns.get("_ast_norm")
    return None


# ── reading a tip ─────────────────────────────────────────────────────────────────────────────

def tip_files(gitdir, tip):
    """[(blob_sha, path)] — EVERY blob at this tip, in ls-tree order, regardless of extension.

    The containment gate asks about "every file at its tip" (#452 §3), so it must not be filtered
    to code: a config or fixture that has not come home is still work. The ORPHAN report filters to
    SOURCE_EXT separately, because its universe is "unique CODE blobs" (#452 §4). Two scopes, on
    purpose — see `evolve`.
    """
    rc, out = git(gitdir, "ls-tree", "-r", tip)
    if rc != 0:
        return None
    files = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) >= 3 and parts[1] == "blob":
            files.append((parts[2], path))
    return files


def batch_blobs(gitdir, shas):
    """{blob_sha: bytes} read in ONE `git cat-file --batch` process, or None if the BATCH failed.

    A tip holds hundreds of blobs and the forge holds 261 tips; one subprocess per blob would make
    a live run take minutes instead of seconds. A sha git reports as `missing` is simply absent
    from the returned map, so `scan_tip` sees that ONE blob as unreadable rather than as empty
    content.

    THE RETURN IS THREE-VALUED ON PURPOSE. `{}`/a partial map means "git ANSWERED; these are the
    blobs it had" — anything absent is a real per-blob gap in the object store. None means "git did
    not answer at all" (it timed out, or exited non-zero): nothing was learned about ANY blob, and
    the two must not be confused.

    What this protects is the WORKLIST'S MEANING, not the safety of the verdict. Either way the
    verdict is safe — `scan_tip` records an unread blob as UNREADABLE and the gate counts it as
    unresolved, so a failed batch can only ever produce NOT SAFE, never a false "contained". But
    #452 §3 makes the unresolved list THE MERGE-HOME WORKLIST — the thing an operator works through
    — and a batch that timed out is an environment failure, not 39 files of un-merged work. So None
    becomes a whole-tip UNKNOWN ("this member's tip would not enumerate"), which the gate reports as
    NOT SAFE with an EMPTY worklist and the reason stated, rather than inventing a worklist out of
    a git that never ran.
    """
    shas = [s for s in dict.fromkeys(shas)]
    if not shas:
        return {}
    _guard_store(gitdir)
    env = dict(os.environ)
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"})
    try:
        p = subprocess.Popen(["git", "--git-dir", gitdir, "cat-file", "--batch"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env)
        out, _ = p.communicate(("\n".join(shas) + "\n").encode(), timeout=GIT_TIMEOUT)
    except FileNotFoundError:
        raise ForgeError("git is not on PATH — this tool reads the forge's bare repos with git")
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        return None                         # the batch never answered — learn nothing, claim nothing
    if p.returncode != 0:
        return None                         # a fatal git error mid-stream: the map would be a lie
    res, i = {}, 0
    while i < len(out):
        nl = out.find(b"\n", i)
        if nl < 0:
            break
        header = out[i:nl].decode("utf-8", "replace").split()
        if len(header) >= 3 and header[1] == "blob":
            size = int(header[2])
            start = nl + 1
            res[header[0]] = out[start:start + size]
            i = start + size + 1            # +1 for the newline git writes after the payload
        else:
            i = nl + 1                      # "<sha> missing" — and any line we do not understand
    return res


def scan_tip(gitdir, tip, cache):
    """{path: {"blob": sha, "id": module_sha|None, "kind": "ast"|"raw"|UNREADABLE}}, or None.

    EVERY path `ls-tree` lists at `tip` appears in the result — that is the invariant the gate rests
    on, since §3 asks whether "every file at its tip" resolves and a file that is not in the result
    is a file nobody can ask about. A blob the object store will not produce is therefore recorded
    with id=None and kind=UNREADABLE rather than dropped: it is a file at the tip whose content is
    UNKNOWN, and unknown must surface as work, never as proof. (Dropping it silently made a fork
    holding un-merged files report "SAFE TO OMIT (proven)" — the gate saw a shorter tip and every
    file it could still see happened to resolve.)

    None means the TIP ITSELF would not enumerate (ls-tree failed, or the blob batch never answered)
    — nothing is known about any file, which `evolve` records as unreadable and the gate reports as
    NOT SAFE.

    `cache` maps (blob_sha, is_python) -> (module_sha, kind) across the whole run: the forge is
    mostly ingestion duplicates, so the same blob is met over and over and normalizing it once
    matters. The key carries is_python because identity depends on the PATH's extension, not only
    on the bytes — the same blob at a.py and at a.txt is a different module-sha by definition. Only
    successfully READ blobs are cached, so one repo's missing object can never poison another's.
    """
    files = tip_files(gitdir, tip)
    if files is None:
        return None
    want = [sha for sha, path in files
            if (sha, os.path.splitext(path)[1].lower() in PY_EXT) not in cache]
    blobs = batch_blobs(gitdir, want) if want else {}
    if blobs is None:
        return None                         # the batch never answered: the whole tip is UNKNOWN
    out = {}
    for sha, path in files:
        is_py = os.path.splitext(path)[1].lower() in PY_EXT
        key = (sha, is_py)
        if key not in cache:
            raw = blobs.get(sha)
            if raw is None:
                # ls-tree lists it but cat-file will not produce it: keep the FILE, drop only the
                # claim to know its content. id=None matches no home blob, so the gate lists it as
                # unresolved work and the fork cannot be proven safe to omit.
                out[path] = {"blob": sha, "id": None, "kind": UNREADABLE}
                continue
            cache[key] = module_sha(raw, path)
        mid, kind = cache[key]
        out[path] = {"blob": sha, "id": mid, "kind": kind}
    return out


# ── dates ─────────────────────────────────────────────────────────────────────────────────────

def _parse_date(s):
    try:
        return datetime.datetime.strptime((s or "").strip(), "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return None


def commit_meta(gitdir, sha):
    """{sha, date, subject} for one commit, or None if this store does not hold it.

    `%ai` is the AUTHOR date — when the work was done, which is what a timeline is about. (On this
    forge the author and committer dates are identical for the commits in the worked example; the
    author date is the one the ticket's figures quote.)
    """
    out = git_ok(gitdir, "log", "-1", "--format=%ai%x1f%s", sha)
    if not out:
        return None
    date, _, subject = out.partition("\x1f")
    return {"sha": sha, "date": date.strip(), "subject": subject.strip()}


def _days(a, b):
    """(b - a) in days, or None if either date is unparseable."""
    da, db = _parse_date(a), _parse_date(b)
    if da is None or db is None:
        return None
    return round((db - da).total_seconds() / 86400.0, 2)


def _hm(date):
    """'2026-07-08 20:38' — the timeline's display form, matching the ticket's worked example."""
    return (date or "")[:16]


# ── the timeline ──────────────────────────────────────────────────────────────────────────────

def store_holding(gitdirs, *objs):
    """The first store that holds EVERY named object, or None.

    A merge-base needs both tips in ONE object store. Part 1 resolves a SPLIT-STORE family by
    fetching every member into a scratch store; this tool does not write, so it looks for a member
    that ALREADY holds both (the fork usually does — jail.git holds agent_tools_suite's tip) and
    reports the fork point as UNKNOWN, with the reason, when none does. A described SPLIT-STORE is
    honest; a fetched one would be a side effect this tool's docstring forbids.
    """
    for gd in gitdirs:
        if all(git(gd, "cat-file", "-e", str(o) + "^{commit}")[0] == 0 for o in objs):
            return gd
    return None


def timeline(lin, remotes):
    """The lineage's TIMELINE: root date, and per member the fork point, the tip, and the width.

    THE FORK POINT of a member is the date of `merge-base(canonical-tip, member-tip)` — the last
    commit the member and its home share, i.e. the moment that member started running alone. THE
    FORK WIDTH is its tip date minus that: how long it ran alone. For the canonical member itself
    the fork point IS its tip and the width is 0 — it is the reference every other member is
    measured against, not a fork.

    Members come back ordered by fork-point date, oldest first, so the result reads as STAGES.
    A member whose fork point is unknown (no merge-base, or no store holds both tips) sorts last
    and says why, rather than being dropped or given a fabricated date.
    """
    gitdirs = {m["repo"]: os.path.join(remotes, m["repo"]) for m in lin["members"]}
    canon = lin.get("canonical") or lin.get("candidate")
    canon_tip = None
    for m in lin["members"]:
        if m["repo"] == canon:
            canon_tip = m["tip"]
    # the whole family's stores, canonical first: any of them may be the one holding both tips
    stores = [gitdirs[canon]] if canon in gitdirs else []
    stores += [gd for r, gd in sorted(gitdirs.items()) if r != canon]

    roots = []
    for r in lin["roots"]:
        gd = store_holding(stores, r)
        meta = commit_meta(gd, r) if gd else None
        roots.append(meta or {"sha": r, "date": None, "subject": None,
                              "note": "no member's store holds this root commit"})
    roots.sort(key=lambda r: (r["date"] is None, r["date"] or ""))

    out = []
    for m in lin["members"]:
        gd = gitdirs[m["repo"]]
        tip = commit_meta(gd, m["tip"]) or {"sha": m["tip"], "date": None, "subject": None}
        rec = {"repo": m["repo"], "tip": m["tip"], "tip_date": tip["date"],
               "tip_subject": tip["subject"], "commits": m.get("commits"),
               "is_canonical": m["repo"] == canon}
        if canon_tip is None:
            rec.update({"fork_point": None, "fork_point_date": None, "fork_width_days": None,
                        "fork_point_unknown": "this lineage names no canonical member"})
        elif m["repo"] == canon:
            rec.update({"fork_point": m["tip"], "fork_point_date": tip["date"],
                        "fork_width_days": 0.0,
                        "note": "the HOME — the reference the other members' fork points are "
                                "measured against, not a fork"})
        else:
            shared = store_holding(stores, canon_tip, m["tip"])
            if shared is None:
                rec.update({"fork_point": None, "fork_point_date": None, "fork_width_days": None,
                            "fork_point_unknown":
                                "no member's object store holds BOTH %s's tip and %s's tip, so no "
                                "merge-base is computable without fetching — which this tool does "
                                "not do (Part 1 classified this family SPLIT-STORE)"
                                % (canon, m["repo"])})
            else:
                mb = git_ok(shared, "merge-base", canon_tip, m["tip"]) or None
                if mb is None:
                    rec.update({"fork_point": None, "fork_point_date": None,
                                "fork_width_days": None,
                                "fork_point_unknown":
                                    "this tip shares NO commit with %s's tip: the line was "
                                    "re-rooted, so there is no fork point to date" % canon})
                else:
                    fp = commit_meta(shared, mb) or {"sha": mb, "date": None, "subject": None}
                    rec.update({"fork_point": mb, "fork_point_date": fp["date"],
                                "fork_point_subject": fp["subject"],
                                "fork_width_days": _days(fp["date"], tip["date"])})
                    if mb == canon_tip:
                        rec["note"] = ("the fork point IS %s's tip — this member ran on from the "
                                       "home's own tip" % canon)
                    if mb == m["tip"]:
                        rec["note"] = ("the fork point IS this member's tip — it never ran alone; "
                                       "it is an earlier snapshot of the same line")
        root_date = roots[0]["date"] if roots else None
        rec["span_from_root_days"] = _days(root_date, tip["date"])
        # the files this member holds that its home's tip does not — the shape of what it ran off
        # and did. Counted against the FORK POINT, which is what "ran alone" means.
        if rec.get("fork_point") and rec["fork_point"] != m["tip"]:
            st = store_holding(stores, rec["fork_point"], m["tip"])
            names = git_ok(st, "diff", "--name-status", rec["fork_point"], m["tip"]) if st else ""
            rows = [l.split("\t") for l in names.splitlines() if "\t" in l]
            rec["files_changed"] = len(rows)
            rec["files_added"] = sum(1 for r in rows if r[0].startswith("A"))
            rec["files_modified"] = sum(1 for r in rows if r[0].startswith("M"))
        else:
            rec["files_changed"] = rec["files_added"] = rec["files_modified"] = 0
        out.append(rec)

    # oldest fork point first, so the family reads as stages; unknowns last, never dropped
    out.sort(key=lambda r: (r["fork_point_date"] is None, r["fork_point_date"] or "", r["repo"]))
    return {"roots": roots, "root_date": roots[0]["date"] if roots else None, "stages": out}


# ── the containment gate ──────────────────────────────────────────────────────────────────────

def homes_for(lin, extra):
    """The repos a fork's content must resolve INTO: the canonical, plus any operator --home.

    Direction is Part 1's to decide (#452 §5), so the canonical comes from it untouched. --home
    only ADDS destinations, because a grab-bag fork's packages can belong to SEVERAL different home
    repos and containment against one of them alone would report work that is not real.
    """
    canon = lin.get("canonical") or lin.get("candidate")
    homes = [canon] if canon else []
    for r in (extra or {}).get(lin["id"], []):
        if r not in homes:
            homes.append(r)
    return homes


def named_home_repos(extra):
    """Every repo named by ANY --home, across all lineages: the operator's destinations.

    Global on purpose. A home named for lineage A is a DESTINATION other forks' content must
    resolve into, so it is not an omit candidate anywhere — including inside its OWN lineage's
    gate, where it would otherwise be gated against itself and trivially resolve. See gate().
    """
    return {r for repos in (extra or {}).values() for r in repos}


def gate(lin, remotes, scans, extra_homes=None, home_repos=None):
    """The CONTAINMENT PROOF for every non-canonical member of this lineage.

    THE RULE (#452 §3), mechanical and not a judgement: a fork is SAFE TO OMIT if and only if EVERY
    file at its tip resolves, by CONTENT IDENTITY (the module-sha), to a blob present at the tip of
    its home repo(s). AST-normalized identity means a file that came home with only whitespace or
    comment drift still counts as CONTAINED — it is the same module — while a semantically changed
    file correctly FAILS and surfaces as work.

    Every blob resolves -> "SAFE TO OMIT (proven)": proven, never assumed. Any blob unresolved ->
    the exact file list, which IS THE MERGE-HOME WORKLIST. The fork MUST NOT be dropped while that
    list is non-empty; it shrinks to empty exactly when the fork is safe to drop.

    "EVERY FILE" INCLUDES THE UNREADABLE ONES. Because the rule is an IF AND ONLY IF, the SAFE
    verdict is earned only by resolving every file — so a file whose blob the store will not produce
    (id=None, kind=UNREADABLE; `ls-tree` still lists it) is unresolved BY DEFINITION and joins the
    worklist with its reason. Unknown content is never proof, at either scale: an unreadable BLOB is
    one worklist entry, while an unreadable TIP (sc is None) is NOT SAFE with the reason and an
    empty worklist — a git that never answered is an environment failure, not a list of work.

    A HOME IS NEVER AN OMIT CANDIDATE. The canonical is skipped because it IS the home; every repo
    named by --home is skipped for the same reason, and recorded in `not_omit_candidates` rather
    than dropped silently. Gating a home against itself would trivially resolve every file and
    print "SAFE TO OMIT (proven)" for the very repo the operator designated a DESTINATION — a
    verdict that contradicts itself and, acted on, would lose exactly the content the gate exists
    to protect. `scans` is keyed by REPO NAME (not by lineage), so a home in a DIFFERENT lineage —
    which is the only case --home exists for — is found and actually proves containment.
    """
    canon = lin.get("canonical") or lin.get("candidate")
    homes = homes_for(lin, extra_homes)
    home_repos = set(home_repos or []) | set(homes)
    home_ids, home_missing = {}, []
    for h in homes:
        sc = scans.get(h)
        if sc is None:
            home_missing.append(h)
            continue
        for path, rec in sc.items():
            # An UNREADABLE file at the HOME has id=None and indexes NOTHING: a blob nobody could
            # read is not evidence that anything came home. This is the SECOND of two independent
            # guards and is redundant TODAY — the fork loop below tests `id is None` before it ever
            # consults home_ids, so a None key here could not be matched even if it existed. It is
            # kept because the two guards fail differently: this one keeps home_ids meaning exactly
            # "content identities PROVEN present at a home", so any future reader of it (a second
            # lookup, a reordered branch) inherits the invariant instead of a None that silently
            # matches. Neither guard is load-bearing alone; do not remove both.
            if rec["id"] is None:
                continue
            home_ids.setdefault(rec["id"], []).append("%s:%s" % (h, path))

    forks, not_candidates = [], []
    for m in lin["members"]:
        if m["repo"] == canon:
            continue
        if m["repo"] in home_repos:
            # A DESTINATION, not a candidate. Reported, never silently dropped, so a reader can
            # see why this member has no verdict instead of finding it missing from the list.
            not_candidates.append({
                "repo": m["repo"], "tip": m["tip"],
                "why": "named as a HOME by --home, so it is a DESTINATION other forks' content "
                       "must resolve INTO — not a repo this gate may propose dropping. Gating it "
                       "against itself would resolve every file trivially and print a proof that "
                       "contradicts its own role."})
            continue
        sc = scans.get(m["repo"])
        rec = {"repo": m["repo"], "tip": m["tip"], "homes": list(homes)}
        if sc is None:
            rec.update({"verdict": NOT_SAFE, "files_at_tip": 0, "unresolved": [],
                        "reason": "this member's tip would not enumerate, so containment is "
                                  "UNKNOWN — and unknown is never safe"})
            forks.append(rec)
            continue
        if home_missing:
            # Reached ONLY when a home repo Part 1 knows could not be scanned at all (its tip did
            # not enumerate, or its directory is gone from the forge — both are recorded in the
            # report's `unreadable`). A home that merely lives in a DIFFERENT lineage does NOT come
            # here: scans is keyed by repo name, so it is found and proves containment normally. A
            # home naming a repo Part 1 never heard of cannot come here either — evolve() rejects
            # that as a usage error before any gate runs, rather than blaming a git that never ran.
            rec.update({"verdict": NOT_SAFE, "files_at_tip": len(sc), "unresolved": [],
                        "reason": "the home repo(s) %s could not be scanned at all (see the "
                                  "report's 'unreadable'), so nothing can be proven contained — "
                                  "and unproven is never safe" % ", ".join(home_missing)})
            forks.append(rec)
            continue
        unresolved, unreadable_here = [], 0
        for path in sorted(sc):
            f = sc[path]
            if f["id"] is None:
                # UNKNOWN CONTENT IS NEVER PROOF. This file is at the tip; whether it came home
                # cannot be decided, so it counts as work and blocks the SAFE verdict.
                unreadable_here += 1
                unresolved.append({"path": path, "blob": f["blob"], "module_sha": None,
                                   "identity": UNREADABLE,
                                   "why": "blob %s is listed at this tip but the object store will "
                                          "not produce it, so its content identity is UNKNOWN and "
                                          "it cannot be proven to have come home" % f["blob"][:10]})
            elif f["id"] not in home_ids:
                unresolved.append({"path": path, "blob": f["blob"], "module_sha": f["id"],
                                   "identity": f["kind"]})
        rec.update({
            "files_at_tip": len(sc),
            "resolved": len(sc) - len(unresolved),
            "unresolved": unresolved,
            "unreadable_at_tip": unreadable_here,
            "verdict": SAFE if not unresolved else NOT_SAFE,
        })
        if unresolved:
            rec["worklist_note"] = (
                "THIS LIST IS THE MERGE-HOME WORKLIST: %d file(s) at %s's tip resolve to no blob "
                "in %s%s. %s MUST NOT be dropped while this list is non-empty; it shrinks to empty "
                "exactly when %s is safe to omit."
                % (len(unresolved), m["repo"], " or ".join(homes),
                   "" if not unreadable_here else
                   " (%d of them because the blob itself is UNREADABLE — unknown content is listed "
                   "as work, never assumed contained)" % unreadable_here,
                   m["repo"], m["repo"]))
        elif not sc:
            # An empty result now means ONE thing only — a tip whose tree genuinely holds no files.
            # It cannot mean "the read failed": a failed batch returns None (whole-tip UNKNOWN,
            # handled above as NOT SAFE) and an unreadable blob keeps its entry. Saying "every one
            # of the 0 files resolves — PROVEN contained" would still be vacuous phrasing that reads
            # like a proof over real files, so the empty tree says what it actually is.
            rec["worklist_note"] = (
                "%s's tip holds NO files at all — an EMPTY tree, not an unread one — so there is "
                "nothing to bring home and nothing to lose by omitting it." % m["repo"])
        else:
            rec["worklist_note"] = (
                "every one of the %d file(s) at %s's tip resolves by content identity to a blob in "
                "%s — PROVEN contained, so omitting %s loses nothing."
                % (len(sc), m["repo"], " or ".join(homes), m["repo"]))
        forks.append(rec)
    forks.sort(key=lambda f: (f["verdict"] == SAFE, f["repo"]))
    not_candidates.sort(key=lambda r: r["repo"])
    return {"homes": homes, "forks": forks, "not_omit_candidates": not_candidates}


def risk_of(lin, remotes):
    """(risk, why) — whether this family's direction can LOSE content. Computed, never assumed.

    #452 §5 says a LINEAR family's direction cannot lose code because the canonical supersets the
    rest, and only DIVERGED/SPLIT-STORE put content at risk. That holds only while the canonical IS
    the topological superset. It is false for a family whose direction the operator REVERSED — jail
    is topologically LINEAR, yet its canonical is the side that TRAILS, so jail's files are at risk.
    So the label is not consulted: the canonical tip is checked to be a descendant of (or equal to)
    every member's tip, which is exactly the condition under which nothing can be lost.
    """
    canon = lin.get("canonical") or lin.get("candidate")
    gitdirs = {m["repo"]: os.path.join(remotes, m["repo"]) for m in lin["members"]}
    canon_tip = next((m["tip"] for m in lin["members"] if m["repo"] == canon), None)
    if canon_tip is None:
        return RISK_AT, "this lineage names no canonical member, so nothing is proven contained"
    stores = [gitdirs[canon]] + [gd for r, gd in sorted(gitdirs.items()) if r != canon]
    for m in lin["members"]:
        if m["repo"] == canon or m["tip"] == canon_tip:
            continue
        st = store_holding(stores, canon_tip, m["tip"])
        if st is None:
            return (RISK_AT,
                    "%s's tip and the canonical's live in different object stores, so ancestry is "
                    "UNKNOWN — and unknown is not proof that nothing is lost" % m["repo"])
        if git(st, "merge-base", "--is-ancestor", m["tip"], canon_tip)[0] != 0:
            return (RISK_AT,
                    "%s's tip is NOT an ancestor of %s's, so it can hold content the canonical "
                    "does not — this is a MERGE, not a naming decision" % (m["repo"], canon))
    return (RISK_NONE,
            "%s's tip contains every member's tip, so no member holds anything it lacks — the "
            "direction here is a NAMING decision and cannot lose code" % canon)


# ── the orphan set ────────────────────────────────────────────────────────────────────────────

def orphans(doc_lineages, scans):
    """Code blobs that exist ONLY at non-canonical tips — what unifying on canonical tips LOSES.

    THE DEFINITION, stated because the count depends on it (#452 §4): a CODE blob (its extension in
    SOURCE_EXT) that is present at some NON-canonical member's tip and present at NO canonical tip
    ANYWHERE in the forge. Coverage is global, not per lineage: a blob that also sits at some other
    family's canonical tip is not lost by this plan, so it is not an orphan.

    Keyed by git blob sha1, which is what the report must name (#452 §4 asks for "blob sha, path,
    which member holds it, which lineage"). This is the ONE place identity is the blob sha rather
    than the module-sha: the two answer different questions, and both are reported in `totals`
    (`orphan_blobs` and `orphan_module_ids`). A blob whose CONTENT came home with whitespace drift
    is a blob-sha orphan but NOT a module-sha orphan — the gate above is what decides whether a
    fork may retire, and it uses the module-sha.
    """
    canon_blobs, canon_ids = set(), set()
    holders = collections.defaultdict(list)
    universe, universe_ids = set(), set()
    non_ids = collections.defaultdict(set)
    for lin in doc_lineages:
        canon = lin.get("canonical") or lin.get("candidate")
        for m in lin["members"]:
            sc = scans.get(m["repo"])          # keyed by repo name; see evolve()
            if sc is None:
                continue
            for path, rec in sc.items():
                if os.path.splitext(path)[1].lower() not in SOURCE_EXT:
                    continue
                universe.add(rec["blob"])
                if rec["id"] is not None:
                    universe_ids.add(rec["id"])
                if m["repo"] == canon:
                    canon_blobs.add(rec["blob"])
                    # an UNREADABLE canonical file (id=None) covers no CONTENT: its blob sha is
                    # still real and still present at a canonical tip, but None must never enter
                    # canon_ids or every unreadable fork file would read as "content came home".
                    if rec["id"] is not None:
                        canon_ids.add(rec["id"])
                else:
                    holders[rec["blob"]].append({"lineage": lin["name"], "lineage_id": lin["id"],
                                                 "repo": m["repo"], "path": path,
                                                 "module_sha": rec["id"], "identity": rec["kind"]})
                    # an UNREADABLE blob HAS no module id, so it cannot be counted as one; it still
                    # appears as a blob-sha orphan above, which is the report §4 asks for.
                    if rec["id"] is not None:
                        non_ids[rec["id"]].add(rec["blob"])
    rows = []
    for blob in sorted(holders):
        if blob in canon_blobs:
            continue
        held = sorted(holders[blob], key=lambda h: (h["lineage"], h["repo"], h["path"]))
        rows.append({
            "blob": blob,
            "module_sha": held[0]["module_sha"],
            "identity": held[0]["identity"],
            "path": held[0]["path"],
            "lineage": held[0]["lineage"],
            "lineage_id": held[0]["lineage_id"],
            "held_by": [{"repo": h["repo"], "path": h["path"]} for h in held],
            # a blob-sha orphan whose CONTENT is at a canonical tip came home with only
            # whitespace/comment drift: it is not lost, and the gate treats it as contained.
            # An UNREADABLE blob (module_sha None) is never one of those: unknown content has not
            # been shown to have come home, so it stays a live orphan.
            "content_came_home": (held[0]["module_sha"] is not None
                                  and held[0]["module_sha"] in canon_ids),
        })
    rows.sort(key=lambda r: (r["lineage"], r["path"], r["blob"]))
    return {
        "definition": "a code blob (extension in SOURCE_EXT) present at some NON-canonical member "
                      "tip and at NO canonical tip anywhere in the forge, over Part 1's tips",
        "universe_code_blobs": len(universe),
        "universe_module_ids": len(universe_ids),
        "orphan_blobs": len(rows),
        "orphan_module_ids": len([i for i in non_ids if i not in canon_ids]),
        "orphans": rows,
    }


# ── consume part 1 ────────────────────────────────────────────────────────────────────────────

def default_family_tree():
    """Part 1, next to this file. Both tools live in the same tools/ directory."""
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), "forge_family_tree.py")


def run_part1(tool, remotes=None, overrides=None, override_file=None):
    """Run `forge_family_tree.py --json -` and return its document.

    Part 1 is CONSUMED, not re-implemented (#452): its lineages, members, tips and classification
    are taken as given. --override / --override-file are forwarded to it unchanged, because the
    operator's home mapping is its layer to apply, not this tool's to reinterpret.
    """
    if not os.path.isfile(tool):
        raise ForgeError("Part 1 not found at %s — pass --family-tree PATH, or --family-json PATH "
                         "to consume a JSON it already produced" % tool)
    cmd = [sys.executable, tool, "--json", "-"]
    if remotes:
        cmd += ["--remotes", remotes]
    for o in overrides or []:
        cmd += ["--override", o]
    if override_file:
        cmd += ["--override-file", override_file]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        raise ForgeError("%s timed out" % os.path.basename(tool))
    if p.returncode != 0:
        # Part 1 refuses a forbidden tree with exit 2 and one line; carry that reason out verbatim
        # rather than burying it — its refusals are decisions, not noise.
        raise ForgeError("%s exited %d: %s" % (os.path.basename(tool), p.returncode,
                                               (p.stderr or p.stdout).strip() or "no message"))
    try:
        return json.loads(p.stdout)
    except ValueError as e:
        raise ForgeError("%s did not print JSON: %s" % (os.path.basename(tool), e))


def load_family(path):
    """A Part-1 JSON from a file, or from stdin when path is '-'."""
    try:
        if path == "-":
            return json.load(sys.stdin)
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        raise ForgeError("could not read --family-json %s: %s" % (path, e))


def check_family(doc):
    """Fail with ONE line if this is not a usable Part-1 document — never a KeyError deep in the run.

    THE CONTRACT THIS ENFORCES is "every key the run goes on to REQUIRE is present and the right
    shape", not "some keys look familiar". A --family-json can be hand-edited, truncated, or written
    by a different version of forge_family_tree.py, and a document that gets past this guard only to
    die on `lineage['roots']` inside `timeline()` breaks the docstring's promise of exit 2 with one
    line and no traceback. So the list below is kept in step with what the code dereferences
    UNGUARDED: `roots` (timeline), `members[*].repo` and `members[*].tip` (timeline, gate, orphans).
    Keys the code reads through .get() — canonical/candidate/topology/classification/commits — are
    optional and deliberately NOT required here.
    """
    if not isinstance(doc, dict) or "lineages" not in doc or "remotes" not in doc:
        raise ForgeError("this is not a forge_family_tree.py document: it has no 'lineages' and "
                         "'remotes' keys. Produce one with `forge_family_tree.py --json -`")
    if not isinstance(doc["lineages"], list):
        raise ForgeError("this document's 'lineages' is %s, not a list — is it from a different "
                         "version of forge_family_tree.py?" % type(doc["lineages"]).__name__)
    if not isinstance(doc["remotes"], str):
        raise ForgeError("this document's 'remotes' is %s, not a path string — is it from a "
                         "different version of forge_family_tree.py?"
                         % type(doc["remotes"]).__name__)
    for lin in doc["lineages"]:
        if not isinstance(lin, dict):
            raise ForgeError("a lineage in this document is %s, not an object — is it from a "
                             "different version of forge_family_tree.py?" % type(lin).__name__)
        # 'roots' and 'members[*].tip' are required because timeline()/gate()/orphans() index them
        # directly; leaving them out of this check is what turns version skew into a KeyError.
        for key in ("id", "members", "name", "roots"):
            if key not in lin:
                raise ForgeError("lineage %r in this document has no %r key — is it from a "
                                 "different version of forge_family_tree.py?"
                                 % (lin.get("name", lin.get("id", "<unnamed>")), key))
        for key in ("members", "roots"):
            if not isinstance(lin[key], list):
                raise ForgeError("lineage %r has a %r that is %s, not a list — is it from a "
                                 "different version of forge_family_tree.py?"
                                 % (lin.get("name", lin.get("id")), key,
                                    type(lin[key]).__name__))
        for m in lin["members"]:
            if not isinstance(m, dict):
                raise ForgeError("a member of lineage %r is %s, not an object — is it from a "
                                 "different version of forge_family_tree.py?"
                                 % (lin.get("name", lin.get("id")), type(m).__name__))
            for key in ("repo", "tip"):
                if key not in m:
                    raise ForgeError("a member of lineage %r has no %r key — is it from a "
                                     "different version of forge_family_tree.py?"
                                     % (lin.get("name", lin.get("id")), key))
    return doc


def check_homes(family, extra):
    """Every --home must name a lineage and repos Part 1 actually knows. One clear line if not.

    This is refused UP FRONT, before any gate runs, because the alternative is worse than an error:
    a repo name Part 1 never heard of has no scan, so the gate would report every fork in the
    lineage NOT SAFE "because the home would not enumerate" — blaming a git failure that never
    happened and emptying the merge-home worklist that §3 makes the deliverable. A typo must not be
    able to silently delete the work list; it must stop the run.
    """
    known = {m["repo"] for lin in family["lineages"] for m in lin["members"]}
    ids = {lin["id"] for lin in family["lineages"]}
    for lid, repos in (extra or {}).items():
        if lid not in ids:
            raise ForgeError("--home names lineage %r, which is not a lineage in this forge — "
                             "the id is Part 1's lineage id (the root sha), as printed by "
                             "forge_family_tree.py" % lid)
        for r in repos:
            if r not in known:
                raise ForgeError("--home names %r as a home for lineage %s, but no such repo is in "
                                 "the forge — a home must be a real repo whose tip this tool can "
                                 "prove content against (did you mean a name ending in .git?)"
                                 % (r, lid))


# ── build ─────────────────────────────────────────────────────────────────────────────────────

def evolve(family, only=None, extra_homes=None):
    """Timeline + gate + orphans over a Part-1 document. Returns the JSON-able report.

    The member tips are scanned ONCE here and the scans are shared by the gate and the orphan
    report, because they are two different questions asked of the same trees: the gate reads EVERY
    file at a tip (#452 §3 — "every file"), the orphan report filters to code blobs (#452 §4 —
    "unique code blobs"). Scanning twice would double a live run for nothing.

    `only` filters the lineages AFTER the orphan set is computed over the whole forge, because a
    blob's canonical coverage is global: filtering first would invent orphans that are not orphans.

    THE SCANS ARE KEYED BY REPO NAME, NOT BY LINEAGE, and that is load-bearing for --home. A repo's
    tip is a property of the REPO (Part 1 gives each repo exactly one tip; a repo in two lineages
    with two different tips is a contradiction and is refused below), while a HOME may live in a
    DIFFERENT lineage than the fork resolving into it — which is the only case --home exists for
    (#452 §5: a grab-bag fork's packages belong to several homes). Keying by (lineage, repo) instead
    would file every scan under the scanning lineage, so a cross-lineage home would never be found:
    the gate would call it unscannable, blame a git failure that never happened, and empty the very
    merge-home worklist §3 makes the deliverable.
    """
    if not have_git():
        raise ForgeError("git is not on PATH — this tool needs git")
    remotes = family["remotes"]
    if not os.path.isdir(remotes):
        raise ForgeError("the forge is not at %s (named by the Part-1 document) — pass --remotes"
                         % remotes)
    lineages, cache, scans = family["lineages"], {}, {}
    check_homes(family, extra_homes)
    home_repos = named_home_repos(extra_homes)
    unreadable, unreadable_blobs = [], []
    tip_of = {}
    for lin in lineages:
        for m in lin["members"]:
            # One repo, one tip. Two lineages claiming the same repo at different tips would make a
            # repo-keyed scan ambiguous, so it is refused loudly rather than resolved by luck.
            if tip_of.setdefault(m["repo"], m["tip"]) != m["tip"]:
                raise ForgeError("this document gives %s two different tips (%s and %s) — is it "
                                 "from a different version of forge_family_tree.py?"
                                 % (m["repo"], tip_of[m["repo"]][:10], m["tip"][:10]))
    for lin in lineages:
        for m in lin["members"]:
            if m["repo"] in scans:
                continue                     # already scanned under another lineage: same tip
            gd = os.path.join(remotes, m["repo"])
            if not os.path.isdir(gd):
                unreadable.append({"repo": m["repo"], "reason": "no such repo under %s" % remotes})
                continue
            sc = scan_tip(gd, m["tip"], cache)
            if sc is None:
                unreadable.append({"repo": m["repo"],
                                   "reason": "tip %s would not enumerate" % m["tip"][:10]})
                continue
            scans[m["repo"]] = sc
            # PER-BLOB gaps are recorded too, not only whole-tip ones: a file ls-tree lists whose
            # blob will not come out of the store is unknown content at a tip, and unknown content
            # must be visible. It is already counted as work by the gate and kept in the orphan
            # report; this list is the third place it shows, so no run can hide it.
            for path in sorted(sc):
                if sc[path]["id"] is None:
                    unreadable_blobs.append({
                        "repo": m["repo"], "lineage_id": lin["id"], "path": path,
                        "blob": sc[path]["blob"],
                        "reason": "listed at tip %s but the object store will not produce this "
                                  "blob, so its content identity is UNKNOWN — it is counted as "
                                  "unresolved work, never as contained" % m["tip"][:10]})

    orph = orphans(lineages, scans)              # over the WHOLE forge, before any --lineage filter

    rows = []
    for lin in lineages:
        risk, why = risk_of(lin, remotes)
        rows.append({
            "id": lin["id"], "name": lin["name"],
            "topology": lin.get("topology"), "classification": lin.get("classification"),
            "canonical": lin.get("canonical"), "member_count": lin.get("member_count"),
            "risk": risk, "risk_why": why,
            "timeline": timeline(lin, remotes),
            "gate": gate(lin, remotes, scans, extra_homes, home_repos),
        })
    if only:
        keep = [r for r in rows if only in (r["id"], r["name"], r["name"] + ".git")
                or any(only in (m["repo"], m["repo"][:-4])
                       for m in next(l["members"] for l in lineages if l["id"] == r["id"]))]
        if not keep:
            raise ForgeError("no lineage matches %r (try a repo name, a lineage name, or an id)"
                             % only)
        rows = keep

    forks = [f for r in rows for f in r["gate"]["forks"]]
    safe = [f for f in forks if f["verdict"] == SAFE]
    unsafe = [f for f in forks if f["verdict"] != SAFE]
    return {
        "tool": "forge_evolution.py",
        "scope": "PART 2 of 2 (ticket #452) — evolution timeline, containment retirement gate, "
                 "orphan worklist. PLANS retirement; never performs it.",
        "remotes": remotes,
        "filtered_to": only,
        "part1": {"tool": family.get("tool"), "totals": family.get("totals")},
        "identity": {
            "python_that_parses": 'sha256("ast:" + _ast_norm(source))[:16]',
            "everything_else": 'sha256(b"raw:" + bytes)[:16]',
            "ast_norm": "ast.dump(ast.parse(ast.unparse(ast.parse(src)))) — codebean's own "
                        "normalizer, mirrored; see the module docstring",
            "same_as": "tools/forge_refactor_ticketer.py module_identity()",
        },
        "omni": {
            "opened": False,
            "why": BLACK_BOXED["omni.git"],
            "enforced_by": "_guard_store(), called by the single git entry point in this tool",
        },
        "totals": {
            "lineages": len(rows),
            "members_scanned": len(scans),
            "unreadable": len(unreadable),
            "unreadable_blobs": len(unreadable_blobs),
            "forks_examined": len(forks),
            "forks_safe_to_omit": len(safe),
            "forks_not_safe": len(unsafe),
            "worklist_files": sum(len(f["unresolved"]) for f in unsafe),
            "lineages_at_risk": sum(1 for r in rows if r["risk"] == RISK_AT),
            "orphan_blobs": orph["orphan_blobs"],
            "orphan_module_ids": orph["orphan_module_ids"],
            "universe_code_blobs": orph["universe_code_blobs"],
            "universe_module_ids": orph["universe_module_ids"],
        },
        "unreadable": unreadable,
        "unreadable_blobs": unreadable_blobs,
        "orphan_report": orph,
        "lineages": rows,
    }


# ── render ────────────────────────────────────────────────────────────────────────────────────

def _short(sha):
    return (sha or "")[:10]


def _plural(n, word):
    return "%d %s" % (n, word if n == 1 else word + "s")


def _cut(s, n):
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[:n - 1] + "…"


def _wrap(text, width, pad):
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return ("\n" + pad).join(lines) if lines else ""


def render_timeline(row, verbose=False):
    """The lineage's stages, oldest fork point first — the shape ticket #452 §1 asks for."""
    t = row["timeline"]
    L = ["  EVOLUTION IN STAGES (members ordered by fork-point date, oldest first)"]
    for r in t["roots"]:
        L.append("   %s  root %s  %s"
                 % (_hm(r["date"]) or "(no date)     ", _short(r["sha"]),
                    '"%s"' % _cut(r["subject"], 58) if r.get("subject")
                    else "(%s)" % r.get("note", "unknown")))
    for s in t["stages"]:
        if s.get("fork_point_unknown"):
            L.append("   (fork point unknown)  %s tip %s at %s"
                     % (s["repo"], _short(s["tip"]), _hm(s["tip_date"]) or "(no date)"))
            L.append("        %s" % _wrap(s["fork_point_unknown"], 74, "        "))
            continue
        who = "%s tip" % s["repo"]
        if s["is_canonical"]:
            L.append("   %s  FORK POINT = %s %s  (%s)   [HOME — CANONICAL]"
                     % (_hm(s["fork_point_date"]), who, _short(s["tip"]),
                        _cut(s["tip_subject"], 44)))
            continue
        L.append("   %s  fork point %s   -> %s %s at %s"
                 % (_hm(s["fork_point_date"]), _short(s["fork_point"]), who,
                    _short(s["tip"]), _hm(s["tip_date"])))
        width = s.get("fork_width_days")
        if s["fork_point"] == s["tip"]:
            # not a fork at all: an earlier snapshot of the home's own line. Saying "ran 0.00 days
            # alone" of it would be true but would read as a measurement, not as what it is.
            L.append("        never ran alone — its tip IS the fork point, so it is an earlier "
                     "snapshot of the same line (fork width 0)")
        elif width is not None:
            L.append("        ran %.2f days alone (fork width = tip date - fork-point date), "
                     "%s changed" % (width, _plural(s.get("files_changed") or 0, "file")))
            L.append("        (%d added, %d modified; whole-lineage span from root: %s — a "
                     "DIFFERENT number, not the width)"
                     % (s.get("files_added") or 0, s.get("files_modified") or 0,
                        ("%.2f days" % s["span_from_root_days"])
                        if s.get("span_from_root_days") is not None else "unknown"))
        if s.get("note") and verbose:
            L.append("        note: %s" % _wrap(s["note"], 72, "              "))
    return L


def render_gate(row, verbose=False, cap=12):
    """The containment proof per fork, and the worklist when there is one."""
    g = row["gate"]
    L = ["  RETIREMENT GATE — containment against %s" % " + ".join(g["homes"] or ["(no home)"])]
    for nc in g.get("not_omit_candidates") or []:
        L.append("   %-56s NOT AN OMIT CANDIDATE (a HOME)" % nc["repo"])
        L.append("        %s" % _wrap(nc["why"], 74, "        "))
    if not g["forks"]:
        L.append("   (this lineage has no non-canonical member left to retire: nothing to gate)"
                 if g.get("not_omit_candidates")
                 else "   (this lineage has no non-canonical member: nothing to retire)")
        return L
    for f in g["forks"]:
        L.append("   %-56s %s" % (f["repo"], f["verdict"]))
        if f.get("reason"):
            L.append("        %s" % _wrap(f["reason"], 74, "        "))
            continue
        L.append("        %d of %d file(s) at its tip resolve by content identity"
                 % (f.get("resolved", 0), f.get("files_at_tip", 0)))
        if f.get("unreadable_at_tip"):
            L.append("        %s at its tip UNREADABLE (listed by ls-tree, but the object store "
                     "will not produce the blob): content UNKNOWN, so counted as work below, "
                     "never as contained" % _plural(f["unreadable_at_tip"], "file"))
        if f["unresolved"]:
            L.append("        MERGE-HOME WORKLIST — %s NOT yet home:"
                     % _plural(len(f["unresolved"]), "file"))
            show = f["unresolved"] if (verbose or len(f["unresolved"]) <= cap) \
                else f["unresolved"][:cap]
            for u in show:
                L.append("          ! %-52s %s  (%s)"
                         % (u["path"], _short(u["blob"]), u["identity"]))
            if len(show) < len(f["unresolved"]):
                L.append("          ... and %d more (full list in --json / --verbose)"
                         % (len(f["unresolved"]) - len(show)))
            L.append("        %s" % _wrap(f["worklist_note"], 74, "        "))
    return L


def render_lineage(row, verbose=False):
    label = row["classification"] or "?"
    if row["classification"] != row["topology"]:
        label = "%s  [topology: %s]" % (row["classification"], row["topology"])
    L = ["-" * 94,
         "%s   root %s   (%s)" % (row["name"], row["id"],
                                  _plural(row["member_count"] or 0, "member")),
         "  class: %s   canonical/HOME: %s" % (label, row["canonical"]),
         "  content risk: %s — %s" % (row["risk"], _wrap(row["risk_why"], 70, "        "))]
    L += render_timeline(row, verbose)
    L += render_gate(row, verbose)
    return L


def render_orphans(doc, verbose=False, cap=40):
    o = doc["orphan_report"]
    L = ["=" * 94,
         "THE ORPHAN SET — code blobs that exist ONLY at NON-canonical tips",
         "=" * 94,
         _wrap("These would be SILENTLY LOST by naively unifying on the canonical tips.", 92, ""),
         _wrap("COUNTED AS: " + o["definition"] + ".", 92, "   "),
         "",
         "   %d orphan code blobs (%.2f%% of %d unique code blobs at the member tips)"
         % (o["orphan_blobs"], 100.0 * o["orphan_blobs"] / max(1, o["universe_code_blobs"]),
            o["universe_code_blobs"]),
         "   %d orphan MODULE identities of %d unique (content identity, not blob sha1 — the "
         "number the gate acts on)" % (o["orphan_module_ids"], o["universe_module_ids"]),
         ""]
    by_lin = collections.Counter(r["lineage"] for r in o["orphans"])
    L.append("   by lineage: %s" % (", ".join("%s %d" % (k, v)
                                              for k, v in by_lin.most_common()) or "(none)"))
    L.append("")
    rows = o["orphans"] if (verbose or len(o["orphans"]) <= cap) else o["orphans"][:cap]
    L.append("   %-10s %-16s %-38s %s" % ("BLOB", "MODULE-SHA", "PATH", "HELD BY (lineage / repo)"))
    for r in rows:
        holders = ", ".join(h["repo"] for h in r["held_by"])
        L.append("   %-10s %-16s %-38s %s / %s"
                 % (_short(r["blob"]), r["module_sha"], _cut(r["path"], 38), r["lineage"],
                    _cut(holders, 40)))
        if r["content_came_home"]:
            L.append("        (its CONTENT is at a canonical tip — whitespace/comment drift only, "
                     "so the gate counts it CONTAINED)")
    if len(rows) < len(o["orphans"]):
        L.append("   ... and %d more (full list in --json / --verbose)"
                 % (len(o["orphans"]) - len(rows)))
    return L


def render(doc, verbose=False, want=("timeline", "gate", "orphans")):
    t = doc["totals"]
    L = ["=" * 94,
         "FORGE EVOLUTION   %s" % doc["remotes"],
         "=" * 94,
         "PART 2 of 2 — consumes forge_family_tree.py (Part 1); adds the timeline, the containment",
         "retirement gate, and the orphan worklist. Read-only: it PLANS retirement, never performs",
         "it. omni.git is BLACK-BOXED and never opened (ticket #452 §2).",
         ""]
    if doc.get("filtered_to"):
        L.append("showing ONLY the %s matching --lineage %s (the orphan set is still computed over "
                 "the WHOLE forge: canonical coverage is global)"
                 % (_plural(t["lineages"], "lineage"), doc["filtered_to"]))
    else:
        L.append("%s / %s scanned at their tips"
                 % (_plural(t["lineages"], "lineage"), _plural(t["members_scanned"], "member")))
    L.append("   %d forks examined -> %d SAFE TO OMIT (proven) / %d NOT safe, %s of merge-home work"
             % (t["forks_examined"], t["forks_safe_to_omit"], t["forks_not_safe"],
                _plural(t["worklist_files"], "file")))
    L.append("   %d orphan code blobs of %d unique; %d lineages put content AT RISK"
             % (t["orphan_blobs"], t["universe_code_blobs"], t["lineages_at_risk"]))
    if doc["unreadable"]:
        L.append("   %d member(s) could NOT be read (never silently dropped):" % t["unreadable"])
        for u in doc["unreadable"]:
            L.append("       ! %-58s %s" % (u["repo"], u["reason"]))
    L.append("")
    if "orphans" in want:
        L += render_orphans(doc, verbose)
        L.append("")
    if "timeline" in want or "gate" in want:
        L.append("=" * 94)
        L.append("THE LINEAGES")
        L.append("=" * 94)
        for row in doc["lineages"]:
            label = row["classification"] or "?"
            if row["classification"] != row["topology"]:
                label = "%s  [topology: %s]" % (row["classification"], row["topology"])
            if "timeline" in want and "gate" in want:
                L += render_lineage(row, verbose)
            else:
                L.append("-" * 94)
                L.append("%s   root %s   class: %s   HOME: %s"
                         % (row["name"], row["id"], label, row["canonical"]))
                L += render_timeline(row, verbose) if "timeline" in want \
                    else render_gate(row, verbose)
            L.append("")
    return "\n".join(L)


# ── --home ────────────────────────────────────────────────────────────────────────────────────

def parse_homes(pairs):
    """--home <lineage-id>=<repo.git>[,<repo.git>...] -> {lineage_id: [repo, ...]}.

    This ADDS home repos for the containment gate; it never renames a canonical. Direction belongs
    to Part 1's --override / --override-file, which this tool forwards untouched (#452 §5).
    """
    homes = {}
    for p in pairs or []:
        if "=" not in p:
            raise ForgeError("--home wants <lineage-id>=<repo.git>[,<repo.git>...], got %r" % p)
        k, v = p.split("=", 1)
        k, v = k.strip(), v.strip()
        repos = [r.strip() for r in v.split(",") if r.strip()]
        if not k or not repos:
            raise ForgeError("--home wants <lineage-id>=<repo.git>[,<repo.git>...], got %r" % p)
        homes.setdefault(k, []).extend(repos)
    return homes


# ── selftest ──────────────────────────────────────────────────────────────────────────────────

def _sh(cwd, *args, **kw):
    env = dict(os.environ)
    env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@localhost",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"})
    when = kw.get("when")
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    p = subprocess.run(["git"] + [str(a) for a in args], cwd=cwd, capture_output=True,
                       text=True, env=env)
    if p.returncode != 0:
        raise ForgeError("selftest git failed: git %s\n%s" % (" ".join(map(str, args)), p.stderr))
    return p.stdout.strip()


def _fingerprint(path):
    """A content fingerprint of a directory tree — proves the tool did not write to it."""
    h = hashlib.sha1()
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for f in sorted(files):
            fp = os.path.join(root, f)
            h.update(os.path.relpath(fp, path).encode())
            try:
                with open(fp, "rb") as fh:
                    h.update(hashlib.sha1(fh.read()).digest())
            except OSError:
                h.update(b"?")
    return h.hexdigest()


def selftest():
    """Throwaway git repos in a temp dir, one per case ticket #452 §7 names.

    No network, no live db, no writes outside the temp dir, and the live forge is never opened. The
    real Part 1 is RUN over the throwaway forge, so the consumption path these checks exercise is
    the shipped one, not a stand-in for it.
    """
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond)))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name,
                                ("  -- %s" % detail) if detail and not cond else ""))

    if not have_git():
        print("git is not on PATH — cannot selftest")
        return 1

    base = tempfile.mkdtemp(prefix="forge_evolution-selftest-")
    remotes = os.path.join(base, "remotes")
    os.makedirs(remotes)
    print("== selftest == throwaway forge %s" % remotes)
    print("               no network, no live db, no writes outside that temp dir\n")
    try:
        def work(name):
            w = os.path.join(base, "w-" + name)
            os.makedirs(w)
            _sh(w, "init", "--quiet", "--initial-branch=main", ".")
            return w

        def commit(w, fname, text, msg, when=None):
            p = os.path.join(w, fname)
            os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(fname) else None
            with open(p, "w") as fh:
                fh.write(text)
            _sh(w, "add", fname)
            _sh(w, "commit", "--quiet", "-m", msg, when=when)
            return _sh(w, "rev-parse", "HEAD")

        def publish(w, name):
            bare = os.path.join(remotes, name)
            _sh(base, "init", "--bare", "--quiet", "--initial-branch=main", bare)
            _sh(w, "push", "--quiet", bare, "main:main")
            return bare

        def root_of(w):
            return _sh(w, "rev-list", "--max-parents=0", "HEAD")[:10]

        HOME_PY = "import os\n\n\ndef go(n):\n    return n + 1\n"

        # ---- family A: the fork is FULLY CONTAINED in its home -> SAFE TO OMIT ----------------
        # home holds a.py and later c.py; the fork branched early and added c.py with the SAME
        # content. Every file at the fork's tip is in the home by identity, so it may retire.
        w = work("contA")
        commit(w, "a.py", HOME_PY, "A: root", when="2026-01-01T00:00:00 +0000")
        publish(w, "contained_home.git")
        wf = os.path.join(base, "w-contA-fork")
        _sh(base, "clone", "--quiet", os.path.join(remotes, "contained_home.git"), wf)
        commit(wf, "c.py", "def c():\n    return 3\n", "A/fork: adds c.py",
               when="2026-01-02T00:00:00 +0000")
        publish(wf, "contained_fork.git")
        # the same content comes HOME (a different commit, so a different tip)
        commit(w, "c.py", "def c():\n    return 3\n", "A/home: c.py comes home",
               when="2026-01-03T00:00:00 +0000")
        commit(w, "d.py", "def d():\n    return 4\n", "A/home: home runs on",
               when="2026-01-04T00:00:00 +0000")
        _sh(w, "push", "--quiet", os.path.join(remotes, "contained_home.git"), "main:main")
        # the home's store must hold the fork's tip, or Part 1 reads this as SPLIT-STORE
        _sh(base, "--git-dir", os.path.join(remotes, "contained_home.git"), "fetch", "--quiet",
            os.path.join(remotes, "contained_fork.git"), "+refs/heads/*:refs/remotes/fork/*")
        A_lid = root_of(w)

        # ---- family B: the fork holds ONE un-merged file -> worklist of exactly 1, NOT safe ----
        w = work("oneB")
        commit(w, "a.py", HOME_PY, "B: root", when="2026-02-01T00:00:00 +0000")
        publish(w, "one_home.git")
        wf = os.path.join(base, "w-oneB-fork")
        _sh(base, "clone", "--quiet", os.path.join(remotes, "one_home.git"), wf)
        commit(wf, "only_here.py", "def only():\n    return 'never came home'\n",
               "B/fork: one file that never came home", when="2026-02-02T00:00:00 +0000")
        publish(wf, "one_fork.git")
        commit(w, "b.py", "def b():\n    return 2\n", "B/home: home runs on",
               when="2026-02-03T00:00:00 +0000")
        _sh(w, "push", "--quiet", os.path.join(remotes, "one_home.git"), "main:main")
        _sh(base, "--git-dir", os.path.join(remotes, "one_home.git"), "fetch", "--quiet",
            os.path.join(remotes, "one_fork.git"), "+refs/heads/*:refs/remotes/fork/*")
        B_lid = root_of(w)

        # ---- family C: WHITESPACE/COMMENT-ONLY drift -> CONTAINED via ast identity -------------
        # The fork's a.py differs from the home's byte for byte (a different blob sha1), but it is
        # the SAME MODULE: only comments, blank lines and spacing changed. This is the case that
        # distinguishes content identity from a blob-sha comparison.
        DRIFTED = ("# a comment the home does not have\nimport os\n\n\n\ndef go(n):\n"
                   "    # explain the increment\n    return n + 1\n")
        w = work("driftC")
        commit(w, "a.py", HOME_PY, "C: root", when="2026-03-01T00:00:00 +0000")
        publish(w, "drift_home.git")
        wf = os.path.join(base, "w-driftC-fork")
        _sh(base, "clone", "--quiet", os.path.join(remotes, "drift_home.git"), wf)
        commit(wf, "a.py", DRIFTED, "C/fork: comments and spacing only",
               when="2026-03-02T00:00:00 +0000")
        publish(wf, "drift_fork.git")
        commit(w, "z.py", "def z():\n    return 26\n", "C/home: home runs on",
               when="2026-03-03T00:00:00 +0000")
        _sh(w, "push", "--quiet", os.path.join(remotes, "drift_home.git"), "main:main")
        _sh(base, "--git-dir", os.path.join(remotes, "drift_home.git"), "fetch", "--quiet",
            os.path.join(remotes, "drift_fork.git"), "+refs/heads/*:refs/remotes/fork/*")
        C_lid = root_of(w)
        drift_blob = _sh(base, "--git-dir", os.path.join(remotes, "drift_fork.git"),
                         "rev-parse", "refs/heads/main:a.py")
        home_blob = _sh(base, "--git-dir", os.path.join(remotes, "drift_home.git"),
                        "rev-parse", "refs/heads/main:a.py")

        # ---- family D: a SEMANTIC change -> correctly NOT contained ----------------------------
        SEMANTIC = "import os\n\n\ndef go(n):\n    return n + 2\n"      # + 1 became + 2
        w = work("semD")
        commit(w, "a.py", HOME_PY, "D: root", when="2026-04-01T00:00:00 +0000")
        publish(w, "sem_home.git")
        wf = os.path.join(base, "w-semD-fork")
        _sh(base, "clone", "--quiet", os.path.join(remotes, "sem_home.git"), wf)
        commit(wf, "a.py", SEMANTIC, "D/fork: n + 1 became n + 2",
               when="2026-04-02T00:00:00 +0000")
        publish(wf, "sem_fork.git")
        commit(w, "z.py", "def z():\n    return 26\n", "D/home: home runs on",
               when="2026-04-03T00:00:00 +0000")
        _sh(w, "push", "--quiet", os.path.join(remotes, "sem_home.git"), "main:main")
        _sh(base, "--git-dir", os.path.join(remotes, "sem_home.git"), "fetch", "--quiet",
            os.path.join(remotes, "sem_fork.git"), "+refs/heads/*:refs/remotes/fork/*")
        D_lid = root_of(w)

        # ---- family E: the FORK-WIDTH timeline, on pinned dates --------------------------------
        # root 01-01, fork point 01-02, fork tip 01-06. The width (tip - FORK POINT) is EXACTLY
        # 4.00 days and the span (tip - ROOT) is EXACTLY 5.00 days. They are different numbers on
        # purpose: conflating them is the error in ticket #452's own worked example (the module
        # docstring documents it), so the two are asserted apart here.
        w = work("widthE")
        commit(w, "a.py", "def a():\n    return 1\n", "E: root", when="2026-05-01T00:00:00 +0000")
        E_root_date = "2026-05-01"
        commit(w, "b.py", "def b():\n    return 2\n", "E: the fork point",
               when="2026-05-02T00:00:00 +0000")
        publish(w, "width_home.git")
        wf = os.path.join(base, "w-widthE-fork")
        _sh(base, "clone", "--quiet", os.path.join(remotes, "width_home.git"), wf)
        commit(wf, "wide.py", "def wide():\n    return 'ran alone'\n", "E/fork: ran alone",
               when="2026-05-06T00:00:00 +0000")
        publish(wf, "width_fork.git")
        _sh(base, "--git-dir", os.path.join(remotes, "width_home.git"), "fetch", "--quiet",
            os.path.join(remotes, "width_fork.git"), "+refs/heads/*:refs/remotes/fork/*")
        E_lid = root_of(w)

        # ---- family F: a LINEAR family whose canonical IS the superset -> risk NONE -------------
        # #452 §5: for LINEAR the direction cannot lose code, so it is a NAMING decision. That is
        # true here — and family E above is the counter-example that shows it is a property of the
        # canonical, not of the label: E is LINEAR too, but its direction is reversed and its
        # content IS at risk. Both are asserted, so `risk` cannot be a synonym for the topology.
        w = work("namingF")
        commit(w, "a.py", "def a():\n    return 1\n", "F: root", when="2026-07-01T00:00:00 +0000")
        commit(w, "b.py", "def b():\n    return 2\n", "F: the stale alias is published here",
               when="2026-07-02T00:00:00 +0000")
        publish(w, "naming_stale.git")
        commit(w, "c.py", "def c():\n    return 3\n", "F: the line runs on",
               when="2026-07-03T00:00:00 +0000")
        publish(w, "naming_super.git")

        # ---- family G: an UNRESOLVABLE HEAD on both members ------------------------------------
        # This is the live forge's DOMINANT shape — 183 of its 264 repos (69%) — so a selftest with
        # no such repo would not exercise the case this tool spends most of its time on. HEAD is a
        # symref to refs/heads/master, which does not exist; the only branch is main.
        w = work("unresG")
        commit(w, "a.py", HOME_PY, "G: root", when="2026-08-01T00:00:00 +0000")
        publish(w, "unres_home.git")
        wf = os.path.join(base, "w-unresG-fork")
        _sh(base, "clone", "--quiet", os.path.join(remotes, "unres_home.git"), wf)
        commit(wf, "stranded.py", "def stranded():\n    return 'not home'\n",
               "G/fork: a file that never came home", when="2026-08-02T00:00:00 +0000")
        publish(wf, "unres_fork.git")
        commit(w, "g.py", "def g():\n    return 7\n", "G/home: home runs on",
               when="2026-08-03T00:00:00 +0000")
        _sh(w, "push", "--quiet", os.path.join(remotes, "unres_home.git"), "main:main")
        for r in ("unres_home.git", "unres_fork.git"):
            _sh(base, "--git-dir", os.path.join(remotes, r), "symbolic-ref", "HEAD",
                "refs/heads/master")                      # master does not exist: HEAD now dangles
        _sh(base, "--git-dir", os.path.join(remotes, "unres_home.git"), "fetch", "--quiet",
            os.path.join(remotes, "unres_fork.git"), "+refs/heads/*:refs/remotes/fork/*")
        _sh(base, "--git-dir", os.path.join(remotes, "unres_fork.git"), "fetch", "--quiet",
            os.path.join(remotes, "unres_home.git"), "+refs/heads/*:refs/remotes/home/*")
        G_lid = root_of(w)

        # THE TRAP, asserted on the synthesized repo — and the CORRECTION the module docstring
        # makes to ticket #452's prose. The ticket says `rev-parse HEAD` "EXITS 0" on such a repo.
        # It does not: it prints the literal string "HEAD" on stdout and exits NON-ZERO. Both
        # halves matter — the string is what a caller ignoring the status would use as a sha.
        rc_p, out_p = git(os.path.join(remotes, "unres_home.git"), "rev-parse", "HEAD")
        rc_v, _ = git(os.path.join(remotes, "unres_home.git"), "rev-parse", "--verify", "HEAD")
        ck("HEAD TRAP: `rev-parse HEAD` prints the literal string 'HEAD' on a dangling symref",
           out_p == "HEAD", repr(out_p))
        ck("HEAD TRAP: and it exits NON-ZERO — #452's 'EXITS 0' is wrong (measured 128 on all 183 "
           "live repos); the docstring's correction is asserted here",
           rc_p != 0, "exit %s" % rc_p)
        ck("HEAD TRAP: `rev-parse --verify HEAD` fails too", rc_v != 0, "exit %s" % rc_v)

        # Each fork was cloned from its home BEFORE the home ran on, so a fork's store does not
        # hold the home's tip. Part 1 decides SPLIT-STORE from the CANDIDATE's store, and in
        # families B/C/D the candidate is the fork — so without this the families would classify
        # SPLIT-STORE and the checks below would be measuring the wrong shape. Fetch home -> fork
        # as well, so every store holds every tip and the topology means what it says.
        for home, fork in (("one_home.git", "one_fork.git"),
                           ("drift_home.git", "drift_fork.git"),
                           ("sem_home.git", "sem_fork.git"),
                           ("width_home.git", "width_fork.git")):
            _sh(base, "--git-dir", os.path.join(remotes, fork), "fetch", "--quiet",
                os.path.join(remotes, home), "+refs/heads/*:refs/remotes/home/*")

        # ---- the identity mirror, against codebean's REAL function ----------------------------
        real = codebean_ast_norm()
        if real is None:
            print("   NOTE codebean is not on this host, so the mirror could not be compared "
                  "against it (this is not a failure)")
        else:
            same = all(_ast_norm(s) == real(s) for s in
                       (HOME_PY, DRIFTED, SEMANTIC, "x = 1\n", "class C:\n    '''d'''\n    pass\n"))
            ck("IDENTITY: the mirrored _ast_norm agrees with codebean's real one", same)
            ck("IDENTITY: codebean's normalizer really does collapse comment/space drift",
               real(HOME_PY) == real(DRIFTED) and real(HOME_PY) != real(SEMANTIC))

        ck("IDENTITY: a python blob that parses gets an 'ast' identity",
           module_sha(HOME_PY.encode(), "a.py")[1] == "ast")
        ck("IDENTITY: a non-python blob gets a 'raw' identity",
           module_sha(b"{}", "x.json")[1] == "raw")
        ck("IDENTITY: python that does NOT parse falls back to 'raw', never dropped",
           module_sha(b"def broken(:\n", "b.py")[1] == "raw")
        ck("IDENTITY: a non-UTF8 blob still gets an identity (raw: is concatenated as BYTES)",
           module_sha(b"\xff\xfe\x00binary", "x.bin")[0] != "")
        ck("IDENTITY: the ast: and raw: namespaces are disjoint for identical bytes",
           module_sha(HOME_PY.encode(), "a.py")[0] != module_sha(HOME_PY.encode(), "a.txt")[0])
        ck("IDENTITY: whitespace/comment drift shares ONE module-sha",
           module_sha(HOME_PY.encode(), "a.py")[0] == module_sha(DRIFTED.encode(), "a.py")[0])
        ck("IDENTITY: a semantic change does NOT",
           module_sha(HOME_PY.encode(), "a.py")[0] != module_sha(SEMANTIC.encode(), "a.py")[0])

        # ---- omni is black-boxed, and the guard is what proves it -----------------------------
        for probe, why in ((os.path.join(base, "omni.git"), "named omni.git"),
                           (os.path.join(base, "archives", "anything.git"), "under archives/")):
            try:
                git(probe, "log", "-1")
                ck("OMNI: the guard refuses a store %s" % why, False, "it did not refuse")
            except ForgeError as e:
                ck("OMNI: the guard refuses a store %s" % why, "REFUSING to open" in str(e),
                   str(e))
        try:
            batch_blobs(os.path.join(base, "omni.git"), ["deadbeef"])
            ck("OMNI: the guard also covers the batch blob reader", False, "it did not refuse")
        except ForgeError:
            ck("OMNI: the guard also covers the batch blob reader", True)

        # ---- run the REAL Part 1 over the throwaway forge, then this tool over its output ------
        # --override names each home canonical where TOPOLOGY would not. In families B/C/D the two
        # sides tie on commit count and Part 1 breaks the tie by repo name — which nominates the
        # FORK ('one_fork.git' sorts before 'one_home.git'); in family E the fork genuinely holds
        # the superset tip. Direction is the operator's (#452 §5), and this is the shipped flag,
        # forwarded to Part 1 unchanged.
        #
        # Family A is deliberately NOT overridden: its home already has the most commits, so Part 1
        # nominates the home on topology alone and an override would name it BOTH the home and the
        # fork — which Part 1 correctly refuses (a fork cannot merge into itself). That keeps one
        # family in these checks whose canonical came from topology rather than from the operator.
        overrides = ["%s=%s" % (B_lid, "one_home.git"),
                     "%s=%s" % (C_lid, "drift_home.git"),
                     "%s=%s" % (D_lid, "sem_home.git"),
                     "%s=%s" % (E_lid, "width_home.git"),
                     "%s=%s" % (G_lid, "unres_home.git")]
        tool = default_family_tree()
        if not os.path.isfile(tool):
            print("   FAIL Part 1 (forge_family_tree.py) is not next to this file at %s" % tool)
            return 1
        before = _fingerprint(remotes)
        family = check_family(run_part1(tool, remotes=remotes, overrides=overrides))
        doc = evolve(family)
        after = _fingerprint(remotes)

        def lin(name):
            return next((r for r in doc["lineages"] if r["name"] == name), None)

        def fork_of(name, repo):
            r = lin(name)
            if not r:
                return None
            return next((f for f in r["gate"]["forks"] if f["repo"] == repo), None)

        ck("PART 1: the real forge_family_tree.py was run and its document consumed",
           bool(family.get("lineages")) and family.get("tool") == "forge_family_tree.py")
        ck("PART 1: the operator's --override was forwarded — the HOME is canonical, not the "
           "fork topology would have nominated",
           all((lin(n) or {}).get("canonical") == n + ".git"
               for n in ("one_home", "drift_home", "sem_home", "width_home")),
           str([(r["name"], r["canonical"]) for r in doc["lineages"]]))
        ck("PART 1: a family needing no override still gets its topological canonical",
           (lin("contained_home") or {}).get("canonical") == "contained_home.git",
           str((lin("contained_home") or {}).get("canonical")))

        # ---- §7 case 1: a fork fully contained in home -> SAFE TO OMIT --------------------------
        f = fork_of("contained_home", "contained_fork.git")
        ck("CONTAINED: the fully-contained fork is SAFE TO OMIT (proven)",
           f and f["verdict"] == SAFE, f and f["verdict"])
        ck("CONTAINED: its worklist is empty", f and f["unresolved"] == [],
           f and str(f["unresolved"]))
        ck("CONTAINED: every file at its tip was actually checked (not vacuously zero)",
           f and f["files_at_tip"] >= 2 and f["resolved"] == f["files_at_tip"],
           f and "%s/%s" % (f.get("resolved"), f.get("files_at_tip")))
        ck("CONTAINED: the proof names the home it resolved into",
           f and f["homes"] == ["contained_home.git"], f and str(f.get("homes")))

        # ---- §7 case 2: one un-merged file -> worklist of exactly 1, NOT safe -------------------
        f = fork_of("one_home", "one_fork.git")
        ck("ONE-FILE: the fork with an un-merged file is NOT SAFE TO OMIT",
           f and f["verdict"] == NOT_SAFE, f and f["verdict"])
        ck("ONE-FILE: the worklist is EXACTLY 1 file", f and len(f["unresolved"]) == 1,
           f and str(len(f["unresolved"])))
        ck("ONE-FILE: and it is the right file, named exactly",
           f and f["unresolved"][0]["path"] == "only_here.py",
           f and str([u["path"] for u in f["unresolved"]]))
        ck("ONE-FILE: the worklist entry carries the blob sha the reader needs",
           f and len(f["unresolved"][0]["blob"]) == 40)
        ck("ONE-FILE: the report says the fork must not be dropped while the list is non-empty",
           f and "MUST NOT be dropped" in f["worklist_note"])

        # ---- §7 case 3: whitespace/comment-only drift -> CONTAINED via ast identity -------------
        f = fork_of("drift_home", "drift_fork.git")
        ck("DRIFT: the byte-different blobs really are different blobs (or this proves nothing)",
           drift_blob != home_blob, "%s vs %s" % (drift_blob[:10], home_blob[:10]))
        ck("DRIFT: whitespace/comment-only drift is CONTAINED via ast identity",
           f and f["verdict"] == SAFE, f and "%s %s" % (f["verdict"],
                                                        [u["path"] for u in f["unresolved"]]))
        ck("DRIFT: it was contained by CONTENT, not by luck — the blob sha1 differs from the home's",
           f and f["verdict"] == SAFE and drift_blob != home_blob)
        ck("DRIFT: a blob-sha1 comparison would have called it work (the orphan report shows it)",
           any(r["path"] == "a.py" and r["lineage"] == "drift_home" and r["content_came_home"]
               for r in doc["orphan_report"]["orphans"]),
           str([(r["lineage"], r["path"], r["content_came_home"])
                for r in doc["orphan_report"]["orphans"]]))

        # ---- §7 case 4: a semantic change -> correctly NOT contained ----------------------------
        f = fork_of("sem_home", "sem_fork.git")
        ck("SEMANTIC: a semantically changed file is correctly NOT contained",
           f and f["verdict"] == NOT_SAFE, f and f["verdict"])
        ck("SEMANTIC: the changed file is the worklist, exactly 1 file",
           f and [u["path"] for u in f["unresolved"]] == ["a.py"],
           f and str([u["path"] for u in f["unresolved"]]))
        ck("SEMANTIC: it was judged by ast identity, not by bytes",
           f and f["unresolved"] and f["unresolved"][0]["identity"] == "ast",
           f and str(f["unresolved"]))

        # ---- §7 case 5: the fork-width timeline ------------------------------------------------
        r = lin("width_home")
        st = {s["repo"]: s for s in (r["timeline"]["stages"] if r else [])}
        fk = st.get("width_fork.git")
        ck("WIDTH: the root commit is dated from git", r and r["timeline"]["root_date"]
           and r["timeline"]["root_date"].startswith(E_root_date),
           r and str(r["timeline"]["root_date"]))
        ck("WIDTH: the fork point is dated, and it is the HOME's tip",
           fk and fk["fork_point_date"] and fk["fork_point_date"].startswith("2026-05-02"),
           fk and str(fk.get("fork_point_date")))
        ck("WIDTH: the fork's tip is dated", fk and fk["tip_date"].startswith("2026-05-06"),
           fk and str(fk.get("tip_date")))
        ck("WIDTH: fork width = tip - FORK POINT = exactly 4.00 days",
           fk and fk["fork_width_days"] == 4.0, fk and str(fk.get("fork_width_days")))
        ck("WIDTH: the span from the ROOT is 5.00 days — a DIFFERENT number, never the width",
           fk and fk["span_from_root_days"] == 5.0, fk and str(fk.get("span_from_root_days")))
        ck("WIDTH: the home is the reference: its own width is 0",
           st.get("width_home.git") and st["width_home.git"]["fork_width_days"] == 0.0)
        ck("WIDTH: the fork's one new file is counted",
           fk and fk["files_changed"] == 1 and fk["files_added"] == 1,
           fk and "%s/%s" % (fk.get("files_changed"), fk.get("files_added")))
        ck("WIDTH: stages are ordered by fork-point date, oldest first",
           r and [s["fork_point_date"] for s in r["timeline"]["stages"]]
           == sorted(s["fork_point_date"] for s in r["timeline"]["stages"]))

        # ---- the unresolvable-HEAD family still works end to end -------------------------------
        # 69% of the live forge looks like this. Part 1 supplies the tip from refs/heads; this tool
        # must time it and gate it exactly like any other family — never dropping it, and never
        # letting the literal string "HEAD" reach a git command as a revision.
        r = lin("unres_home")
        f = fork_of("unres_home", "unres_fork.git")
        ck("UNRESOLVABLE HEAD: the family is NOT dropped — Part 1's tip carried it through",
           r is not None and r["canonical"] == "unres_home.git",
           r and str(r.get("canonical")))
        ck("UNRESOLVABLE HEAD: its timeline is dated from git despite HEAD dangling",
           r and r["timeline"]["root_date"] and r["timeline"]["root_date"].startswith("2026-08-01"),
           r and str(r["timeline"]["root_date"]))
        ck("UNRESOLVABLE HEAD: the gate still proves containment and finds the stranded file",
           f and f["verdict"] == NOT_SAFE
           and [u["path"] for u in f["unresolved"]] == ["stranded.py"],
           f and str([u["path"] for u in (f["unresolved"] if f else [])]))
        ck("UNRESOLVABLE HEAD: every member's tip was scanned (none silently skipped)",
           r and all(s["tip_date"] for s in r["timeline"]["stages"]))

        # ---- risk is COMPUTED, not read off the topology label ---------------------------------
        # The pair that matters: two LINEAR families, opposite risk. This is the jail shape — #452
        # §5's "for LINEAR the direction cannot lose code" holds only while the canonical IS the
        # superset, and a reversed family breaks it. If `risk` were a synonym for the topology
        # label, one of these two checks would have to fail.
        ck("RISK: a REVERSED LINEAR family (home canonical, fork holds the superset) is AT-RISK",
           lin("width_home") and lin("width_home")["topology"] == "LINEAR"
           and lin("width_home")["risk"] == RISK_AT,
           lin("width_home") and "%s/%s" % (lin("width_home")["topology"],
                                            lin("width_home")["risk"]))
        ck("RISK: the reason says it is a merge, not a naming decision",
           lin("width_home") and "MERGE, not a naming decision" in lin("width_home")["risk_why"],
           lin("width_home") and lin("width_home")["risk_why"])
        ck("RISK: a LINEAR family whose canonical IS the superset is risk NONE — a naming decision",
           lin("naming_super") and lin("naming_super")["topology"] == "LINEAR"
           and lin("naming_super")["risk"] == RISK_NONE,
           lin("naming_super") and "%s/%s" % (lin("naming_super")["topology"],
                                              lin("naming_super")["risk"]))
        ck("RISK: and its stale alias is still proven SAFE TO OMIT by containment",
           (fork_of("naming_super", "naming_stale.git") or {}).get("verdict") == SAFE,
           str((fork_of("naming_super", "naming_stale.git") or {}).get("verdict")))
        # AT-RISK is not the same claim as "cannot retire": the DAG cannot prove nothing is lost,
        # and the containment gate then PROVES it by CONTENT. That is the whole reason the gate
        # exists, so the two must be able to disagree.
        ck("RISK: an AT-RISK family can still have a PROVEN-safe fork (the DAG cannot see content "
           "identity; the gate can)",
           lin("contained_home") and lin("contained_home")["risk"] == RISK_AT
           and (fork_of("contained_home", "contained_fork.git") or {}).get("verdict") == SAFE,
           lin("contained_home") and "%s/%s" % (lin("contained_home")["risk"],
                                                (fork_of("contained_home",
                                                         "contained_fork.git") or {}).get("verdict")))

        # ---- the orphan set --------------------------------------------------------------------
        o = doc["orphan_report"]
        ck("ORPHANS: only_here.py is an orphan — it exists ONLY at a non-canonical tip",
           any(r["path"] == "only_here.py" for r in o["orphans"]),
           str([r["path"] for r in o["orphans"]]))
        ck("ORPHANS: the report names the blob, the path, the holder and the lineage",
           all(all(k in r and r[k] for k in ("blob", "path", "lineage", "held_by"))
               for r in o["orphans"]))
        ck("ORPHANS: a file that came home is NOT an orphan (contained_fork's c.py)",
           not any(r["path"] == "c.py" for r in o["orphans"]),
           str([r["path"] for r in o["orphans"]]))
        ck("ORPHANS: the module-id count is <= the blob count (drift collapses, bytes do not)",
           o["orphan_module_ids"] <= o["orphan_blobs"],
           "%s vs %s" % (o["orphan_module_ids"], o["orphan_blobs"]))
        ck("ORPHANS: the universe is non-empty and the count is a real subset of it",
           0 < o["orphan_blobs"] < o["universe_code_blobs"],
           "%s of %s" % (o["orphan_blobs"], o["universe_code_blobs"]))
        ck("ORPHANS: a .json data file is NOT in the code-blob universe (SOURCE_EXT is the scope)",
           all(os.path.splitext(r["path"])[1] in SOURCE_EXT for r in o["orphans"]))

        # ---- the gate reads EVERY file, not only code ------------------------------------------
        # A fork holding an un-merged NON-code file must still be work: #452 §3 says "every file at
        # its tip", and the orphan set's SOURCE_EXT scope must not leak into the gate.
        wf = os.path.join(base, "w-oneB-fork")
        commit(wf, "fixture.json", '{"not": "code"}', "B/fork: a non-code file, also not home",
               when="2026-02-04T00:00:00 +0000")
        _sh(wf, "push", "--quiet", os.path.join(remotes, "one_fork.git"), "main:main")
        _sh(base, "--git-dir", os.path.join(remotes, "one_home.git"), "fetch", "--quiet",
            os.path.join(remotes, "one_fork.git"), "+refs/heads/*:refs/remotes/fork/*")
        doc2 = evolve(check_family(run_part1(tool, remotes=remotes, overrides=overrides)))
        f2 = next((f for r in doc2["lineages"] if r["name"] == "one_home"
                   for f in r["gate"]["forks"] if f["repo"] == "one_fork.git"), None)
        ck("EVERY FILE: an un-merged NON-code file is on the worklist too (the gate is not "
           "filtered to SOURCE_EXT)",
           f2 and sorted(u["path"] for u in f2["unresolved"]) == ["fixture.json", "only_here.py"],
           f2 and str([u["path"] for u in f2["unresolved"]]))
        ck("EVERY FILE: but it is NOT an orphan — the orphan universe IS code only",
           not any(r["path"] == "fixture.json" for r in doc2["orphan_report"]["orphans"]))

        # ---- --home adds a second destination for a grab-bag fork ------------------------------
        # one_fork's only_here.py lives in no home; point --home at a repo that holds it and the
        # gate must RESOLVE it there. This is #452 §5's "packages belonging to SEVERAL homes", and
        # it is the ONLY thing --home exists for: the extra home is in ANOTHER lineage than the
        # fork. Asserting merely that the home is NAMED in f3["homes"] proves nothing — that passes
        # while the gate silently fails to find the home, reports a git failure that never happened
        # and empties the worklist. So these checks assert the PROOF: the file resolves, the
        # worklist shrinks to empty, the verdict flips to SAFE, and no false reason is given.
        w2 = work("secondhome")
        commit(w2, "only_here.py", "def only():\n    return 'never came home'\n",
               "second home: holds the fork's file", when="2026-06-01T00:00:00 +0000")
        # the fork's fixture.json (added above) must come home too, or the fork stays NOT SAFE for
        # a REAL reason and this check could not tell a working --home from a broken one.
        commit(w2, "fixture.json", '{"not": "code"}', "second home: and the fork's data file",
               when="2026-06-01T00:01:00 +0000")
        publish(w2, "second_home.git")
        homes = {B_lid: ["second_home.git"]}
        base_fork = next((f for r in doc2["lineages"] if r["name"] == "one_home"
                          for f in r["gate"]["forks"] if f["repo"] == "one_fork.git"), None)
        doc3 = evolve(check_family(run_part1(tool, remotes=remotes, overrides=overrides)),
                      extra_homes=homes)
        f3 = next((f for r in doc3["lineages"] if r["name"] == "one_home"
                   for f in r["gate"]["forks"] if f["repo"] == "one_fork.git"), None)
        ck("--home: the extra home is named in the proof",
           f3 and "second_home.git" in f3["homes"], f3 and str(f3.get("homes")))
        ck("--home: a home in a DIFFERENT lineage is FOUND — no false 'would not enumerate'",
           f3 and not f3.get("reason"), f3 and str(f3.get("reason")))
        ck("--home: the fork's un-merged files RESOLVE at the cross-lineage home (the worklist "
           "shrinks to empty — it must not merely vanish)",
           f3 and f3["unresolved"] == [] and f3.get("resolved") == f3.get("files_at_tip")
           and f3.get("files_at_tip"),
           f3 and "unresolved=%s resolved=%s of %s"
           % ([u["path"] for u in f3["unresolved"]], f3.get("resolved"), f3.get("files_at_tip")))
        ck("--home: with its content proven home, the fork flips to SAFE TO OMIT",
           f3 and f3["verdict"] == SAFE, f3 and f3["verdict"])
        ck("--home: and the baseline it flipped FROM was a real 2-file worklist (so the flip is "
           "the home resolving content, not the worklist being emptied)",
           base_fork and base_fork["verdict"] == NOT_SAFE
           and sorted(u["path"] for u in base_fork["unresolved"])
           == ["fixture.json", "only_here.py"],
           base_fork and str([u["path"] for u in base_fork["unresolved"]]))
        ck("--home: totals.worklist_files drops by exactly the 2 files that came home",
           doc3["totals"]["worklist_files"] == doc2["totals"]["worklist_files"] - 2,
           "%s vs %s" % (doc3["totals"]["worklist_files"], doc2["totals"]["worklist_files"]))

        # ---- a HOME is never an OMIT CANDIDATE -------------------------------------------------
        # Naming a member as its own lineage's home must NOT gate it against itself: every file
        # would resolve trivially and the tool would print "SAFE TO OMIT (proven)" for a repo it
        # simultaneously designates a DESTINATION — and dropping it would lose exactly the content
        # the gate exists to protect. It is excluded like the canonical, and REPORTED, not dropped.
        # doc4_base is the SAME forge with no --home, so the only difference between the two runs
        # is the flag itself: any change in the SAFE count is caused by it and nothing else.
        doc4_base = evolve(check_family(run_part1(tool, remotes=remotes, overrides=overrides)))
        doc4 = evolve(check_family(run_part1(tool, remotes=remotes, overrides=overrides)),
                      extra_homes={B_lid: ["one_fork.git"]})
        g4 = next(r["gate"] for r in doc4["lineages"] if r["name"] == "one_home")
        b4 = next((f for r in doc4_base["lineages"] if r["name"] == "one_home"
                   for f in r["gate"]["forks"] if f["repo"] == "one_fork.git"), None)
        ck("HOME IS NOT A CANDIDATE: (baseline) un-named, one_fork.git IS gated and is NOT SAFE",
           b4 and b4["verdict"] == NOT_SAFE, b4 and b4["verdict"])
        ck("HOME IS NOT A CANDIDATE: a member named as its own home gets NO omit verdict "
           "(no vacuous self-proof)",
           not any(f["repo"] == "one_fork.git" for f in g4["forks"]),
           str([(f["repo"], f["verdict"]) for f in g4["forks"]]))
        ck("HOME IS NOT A CANDIDATE: it is REPORTED as a destination, not silently dropped",
           any(n["repo"] == "one_fork.git" and "DESTINATION" in n["why"]
               for n in g4["not_omit_candidates"]),
           str(g4.get("not_omit_candidates")))
        ck("HOME IS NOT A CANDIDATE: naming it a home invents NO new SAFE verdict anywhere "
           "(the totals do not grow)",
           doc4["totals"]["forks_safe_to_omit"] == doc4_base["totals"]["forks_safe_to_omit"],
           "%s vs baseline %s" % (doc4["totals"]["forks_safe_to_omit"],
                                  doc4_base["totals"]["forks_safe_to_omit"]))

        # ---- a --home that names something Part 1 never heard of STOPS the run ------------------
        # It must never degrade into "NOT SAFE because the home would not enumerate": that blames
        # git for a typo and deletes the worklist. One clear line, before any gate runs.
        for bad, what in ((["%s=no_such_repo.git" % B_lid], "an unknown repo"),
                          (["deadbeef00=one_home.git"], "an unknown lineage id")):
            try:
                evolve(check_family(run_part1(tool, remotes=remotes, overrides=overrides)),
                       extra_homes=parse_homes(bad))
                ck("--home: %s is refused up front, not blamed on git" % what, False,
                   "it ran anyway")
            except ForgeError as e:
                ck("--home: %s is refused up front, not blamed on git" % what,
                   "not a lineage" in str(e) or "no such repo is in the forge" in str(e), str(e))

        # ---- UNREADABLE BLOB: unknown content is WORK, never "proven contained" -----------------
        # A fork holding an un-merged file must not become SAFE TO OMIT merely because that file's
        # blob went unreadable. `ls-tree` still LISTS the file (only the blob is gone), so a scan
        # that drops what it cannot read hands the gate a shorter tip in which every remaining file
        # happens to resolve — and the fork's real work disappears from the worklist, the orphan
        # report and the totals at once. The proof here is the whole pipeline, twice, over its own
        # throwaway forge: the ONLY difference between the two runs is one deleted object file.
        remotes_c = os.path.join(base, "remotes-corrupt")
        os.makedirs(remotes_c)

        def publish_c(w, name):
            bare = os.path.join(remotes_c, name)
            _sh(base, "init", "--bare", "--quiet", "--initial-branch=main", bare)
            _sh(w, "push", "--quiet", bare, "main:main")
            return bare

        wch = work("corrupt")
        commit(wch, "a.py", HOME_PY, "X: root", when="2026-04-01T00:00:00 +0000")
        publish_c(wch, "corrupt_home.git")
        wcf = os.path.join(base, "w-corrupt-fork")
        _sh(base, "clone", "--quiet", os.path.join(remotes_c, "corrupt_home.git"), wcf)
        commit(wcf, "unique.py", "def unique():\n    return 'never came home'\n",
               "X/fork: a file that never came home", when="2026-04-02T00:00:00 +0000")
        publish_c(wcf, "corrupt_fork.git")
        # the home runs on so it wins on commit count and Part 1 nominates it canonical on topology
        commit(wch, "b.py", "def b():\n    return 2\n", "X/home: runs on",
               when="2026-04-03T00:00:00 +0000")
        commit(wch, "c.py", "def c():\n    return 3\n", "X/home: runs on again",
               when="2026-04-04T00:00:00 +0000")
        _sh(wch, "push", "--quiet", os.path.join(remotes_c, "corrupt_home.git"), "main:main")
        _sh(base, "--git-dir", os.path.join(remotes_c, "corrupt_home.git"), "fetch", "--quiet",
            os.path.join(remotes_c, "corrupt_fork.git"), "+refs/heads/*:refs/remotes/fork/*")

        def corrupt_run():
            d = evolve(check_family(run_part1(tool, remotes=remotes_c)))
            r = next((x for x in d["lineages"] if x["name"] == "corrupt_home"), None)
            fk = next((x for x in r["gate"]["forks"] if x["repo"] == "corrupt_fork.git"),
                      None) if r else None
            return d, fk

        docH, fH = corrupt_run()                       # run 1: the forge is intact
        ck("UNREADABLE: (baseline) the fork holding an un-merged file is NOT SAFE, worklist "
           "['unique.py'], 2 files at tip",
           fH and fH["verdict"] == NOT_SAFE and fH["files_at_tip"] == 2
           and [u["path"] for u in fH["unresolved"]] == ["unique.py"],
           fH and "%s files_at_tip=%s worklist=%s"
                  % (fH["verdict"], fH["files_at_tip"], [u["path"] for u in fH["unresolved"]]))
        ck("UNREADABLE: (baseline) unique.py is an orphan and no blob is unreadable yet",
           docH["orphan_report"]["orphan_blobs"] == 1
           and docH["totals"]["unreadable_blobs"] == 0,
           "orphans=%s unreadable_blobs=%s" % (docH["orphan_report"]["orphan_blobs"],
                                               docH["totals"]["unreadable_blobs"]))

        # now delete ONLY the loose object backing unique.py, exactly as the round-1 repro did
        ctip = _sh(base, "--git-dir", os.path.join(remotes_c, "corrupt_fork.git"),
                   "rev-parse", "refs/heads/main")
        cblob = _sh(base, "--git-dir", os.path.join(remotes_c, "corrupt_fork.git"),
                    "rev-parse", "%s:unique.py" % ctip)
        obj = os.path.join(remotes_c, "corrupt_fork.git", "objects", cblob[:2], cblob[2:])
        ck("UNREADABLE: the fork's blob is a loose object this check can remove",
           os.path.exists(obj), obj)
        if os.path.exists(obj):
            os.remove(obj)
        still = _sh(base, "--git-dir", os.path.join(remotes_c, "corrupt_fork.git"),
                    "ls-tree", "-r", ctip)
        rc_cat = subprocess.run(["git", "--git-dir", os.path.join(remotes_c, "corrupt_fork.git"),
                                 "cat-file", "-p", cblob],
                                capture_output=True, text=True).returncode
        ck("UNREADABLE: the trap is real — ls-tree STILL lists unique.py while cat-file fails",
           "unique.py" in still and rc_cat != 0, "ls-tree=%r cat-file rc=%s" % (still, rc_cat))

        docC, fC = corrupt_run()                       # run 2: same command, one object gone
        ck("UNREADABLE: the fork is STILL NOT SAFE TO OMIT — a missing object is not a proof",
           fC and fC["verdict"] == NOT_SAFE, fC and fC["verdict"])
        ck("UNREADABLE: the file is STILL counted at the tip (files_at_tip stays 2, not 1)",
           fC and fC["files_at_tip"] == 2, fC and str(fC.get("files_at_tip")))
        ck("UNREADABLE: unique.py is STILL the worklist — the work did not vanish with the blob",
           fC and [u["path"] for u in fC["unresolved"]] == ["unique.py"],
           fC and str([u["path"] for u in fC["unresolved"]]))
        ck("UNREADABLE: the worklist entry is marked unreadable and says why, rather than "
           "claiming an identity it does not have",
           fC and fC["unresolved"][0]["identity"] == UNREADABLE
           and fC["unresolved"][0]["module_sha"] is None
           and "UNKNOWN" in fC["unresolved"][0]["why"],
           fC and str(fC["unresolved"][0]))
        ck("UNREADABLE: the gate counts it (unreadable_at_tip=1) and nothing resolved falsely",
           fC and fC["unreadable_at_tip"] == 1 and fC["resolved"] == 1,
           fC and "unreadable_at_tip=%s resolved=%s" % (fC.get("unreadable_at_tip"),
                                                        fC.get("resolved")))
        ck("UNREADABLE: it is STILL an orphan — the orphan report does not lose it either",
           docC["orphan_report"]["orphan_blobs"] == 1
           and docC["orphan_report"]["orphans"][0]["blob"] == cblob
           and docC["orphan_report"]["orphans"][0]["content_came_home"] is False,
           str(docC["orphan_report"]["orphan_blobs"]))
        ck("UNREADABLE: totals report the gap (unreadable_blobs=1) — visible in the third output",
           docC["totals"]["unreadable_blobs"] == 1
           and docC["unreadable_blobs"][0]["path"] == "unique.py",
           str(docC["totals"]["unreadable_blobs"]))
        ck("UNREADABLE: the verdict is unchanged by the corruption — every field a reader acts on "
           "matches the intact run",
           fH and fC and (fH["verdict"], fH["files_at_tip"],
                          [u["path"] for u in fH["unresolved"]])
                      == (fC["verdict"], fC["files_at_tip"],
                          [u["path"] for u in fC["unresolved"]]))
        # the fork's own verdict LINE, not the whole page: the gate's summary line always spells
        # out "N SAFE TO OMIT (proven) / M NOT safe", so searching the page for that phrase would
        # match the tally and prove nothing about this fork.
        gtxt = render(docC, want=("gate",))
        fline = next((l for l in gtxt.splitlines()
                      if l.strip().startswith("corrupt_fork.git")), "")
        ck("UNREADABLE: the rendered gate calls the fork NOT SAFE and lists the file as work",
           NOT_SAFE in fline and SAFE not in fline and "unique.py" in gtxt
           and "MERGE-HOME WORKLIST" in gtxt, repr(fline))
        ck("UNREADABLE: the rendered gate says the blob is unreadable rather than staying silent",
           "UNREADABLE" in gtxt and "(unreadable)" in gtxt,
           "no unreadable marker in the rendered gate")
        # An unreadable blob at the HOME is the same trap wearing the other hat: two files nobody
        # can read are not "the same file". Corrupt the home's b.py as well and the fork's
        # unreadable unique.py must NOT resolve against it — were the unknown identity indexed as a
        # home blob, every unreadable fork file would match it and prove itself contained.
        hblob = _sh(base, "--git-dir", os.path.join(remotes_c, "corrupt_home.git"),
                    "rev-parse", "refs/heads/main:b.py")
        hobj = os.path.join(remotes_c, "corrupt_home.git", "objects", hblob[:2], hblob[2:])
        if os.path.exists(hobj):
            os.remove(hobj)
        docB, fB = corrupt_run()
        ck("UNREADABLE: an unreadable blob at the HOME resolves nothing — the fork is still NOT "
           "SAFE and unique.py is still its worklist",
           fB and fB["verdict"] == NOT_SAFE
           and [u["path"] for u in fB["unresolved"]] == ["unique.py"],
           fB and "%s worklist=%s" % (fB["verdict"], [u["path"] for u in fB["unresolved"]]))
        ck("UNREADABLE: both gaps are reported (the fork's and the home's)",
           docB["totals"]["unreadable_blobs"] == 2
           and sorted(u["path"] for u in docB["unreadable_blobs"]) == ["b.py", "unique.py"],
           str([(u["repo"], u["path"]) for u in docB["unreadable_blobs"]]))

        # a whole-tip read failure was already NOT SAFE; prove the two paths agree rather than
        # assuming the per-blob fix did not regress it.
        # `scans` is keyed by REPO NAME (see evolve): the home h.git is present here, the fork
        # f.git is absent, so this is a whole-tip read failure at the FORK.
        ck("UNREADABLE: a whole-tip failure is still NOT SAFE too ('unknown is never safe')",
           gate({"id": "x", "name": "x", "canonical": "h.git",
                 "members": [{"repo": "h.git", "tip": "0" * 40},
                             {"repo": "f.git", "tip": "1" * 40}]},
                remotes_c, {"h.git": {}})["forks"][0]["verdict"] == NOT_SAFE)
        # A 0-file tip may ONLY come from a genuinely empty tree now, so it must not borrow the
        # language of a proof over real files — that sentence was a symptom of the round-1 defect.
        empty = gate({"id": "e", "name": "e", "canonical": "h.git",
                      "members": [{"repo": "h.git", "tip": "0" * 40},
                                  {"repo": "f.git", "tip": "1" * 40}]},
                     remotes_c, {"h.git": {}, "f.git": {}})["forks"][0]
        ck("EMPTY TIP: a genuinely empty tree is SAFE but says it is EMPTY, never 'every one of "
           "the 0 file(s) resolves ... PROVEN contained'",
           empty["verdict"] == SAFE and "NO files at all" in empty["worklist_note"]
           and "0 file(s)" not in empty["worklist_note"],
           empty["worklist_note"])
        ck("UNREADABLE: batch_blobs is three-valued — 'nothing asked for' is {} but a FAILED batch "
           "is None, so a git that never ran cannot be read as a store with no blobs",
           batch_blobs(os.path.join(remotes_c, "corrupt_fork.git"), []) == {}
           and batch_blobs(os.path.join(base, "not-a-git-repo-at-all"), [cblob]) is None)
        ck("UNREADABLE: an unreadable TIP is a whole-tip UNKNOWN (None), never a short file list",
           scan_tip(os.path.join(remotes_c, "corrupt_fork.git"), "0" * 40, {}) is None)

        # ---- refusals and errors explain themselves --------------------------------------------
        try:
            check_family({"nope": 1})
            ck("ERRORS: a non-Part-1 document is refused with one clear line", False)
        except ForgeError as e:
            ck("ERRORS: a non-Part-1 document is refused with one clear line",
               "not a forge_family_tree.py document" in str(e), str(e))

        # ---- VERSION SKEW: every key the run REQUIRES is guarded, with one line and no traceback -
        # check_family is the tool's promise that a hand-edited, truncated or version-skewed
        # --family-json exits 2 with one line. A key it does not check but the run dereferences
        # anyway (roots in timeline(), tip in gate()/timeline()) breaks that promise with a raw
        # KeyError, so each required key is checked by REMOVING it from a document Part 1 really
        # produced and running the SAME entry point the CLI runs.
        good = json.loads(json.dumps(family))          # a real Part-1 document, deep-copied
        skews = [
            ("a lineage with no 'roots'", lambda d: d["lineages"][0].pop("roots"), "roots"),
            ("a lineage with no 'members'", lambda d: d["lineages"][0].pop("members"), "members"),
            ("a lineage with no 'id'", lambda d: d["lineages"][0].pop("id"), "id"),
            ("a lineage with no 'name'", lambda d: d["lineages"][0].pop("name"), "name"),
            ("a member with no 'tip'", lambda d: d["lineages"][0]["members"][0].pop("tip"), "tip"),
            ("a member with no 'repo'", lambda d: d["lineages"][0]["members"][0].pop("repo"),
             "repo"),
        ]
        for label, break_it, key in skews:
            d = json.loads(json.dumps(good))
            break_it(d)
            try:
                check_family(d)
                ck("SKEW: %s is refused" % label, False, "it was accepted")
            except ForgeError as e:
                ck("SKEW: %s is refused with ONE line naming %r" % (label, key),
                   key in str(e) and "\n" not in str(e), str(e))
            except KeyError as e:
                ck("SKEW: %s is refused" % label, False, "raw KeyError %s — the guard missed it" % e)
        for label, break_it in [("'lineages' that is not a list",
                                 lambda d: d.update({"lineages": {"a": 1}})),
                                ("'remotes' that is not a path",
                                 lambda d: d.update({"remotes": 7})),
                                ("a lineage that is not an object",
                                 lambda d: d.update({"lineages": ["nope"]})),
                                ("a member that is not an object",
                                 lambda d: d["lineages"][0].update({"members": ["nope"]}))]:
            d = json.loads(json.dumps(good))
            break_it(d)
            try:
                check_family(d)
                ck("SKEW: %s is refused" % label, False, "it was accepted")
            except ForgeError as e:
                ck("SKEW: %s is refused with one line" % label, "\n" not in str(e), str(e))
            except (KeyError, TypeError, AttributeError) as e:
                ck("SKEW: %s is refused" % label, False,
                   "raw %s: %s — the guard missed it" % (type(e).__name__, e))
        ck("SKEW: the UNBROKEN document still passes the guard (it refuses skew, not everything)",
           check_family(json.loads(json.dumps(good))) is not None)
        ck("SKEW: optional keys Part 1 may omit are NOT required (they are read via .get)",
           bool(check_family(dict(good, lineages=[
               dict(l, **{k: None for k in ()}) for l in good["lineages"]]))))
        d = json.loads(json.dumps(good))
        for l in d["lineages"]:
            for k in ("canonical", "candidate", "topology", "classification", "member_count"):
                l.pop(k, None)
            for m in l["members"]:
                m.pop("commits", None)
        try:
            ck("SKEW: a document missing only OPTIONAL keys runs end to end (no over-strict guard)",
               bool(evolve(check_family(d))))
        except (ForgeError, KeyError) as e:
            ck("SKEW: a document missing only OPTIONAL keys runs end to end (no over-strict guard)",
               False, "%s: %s" % (type(e).__name__, e))
        try:
            parse_homes(["garbage"])
            ck("ERRORS: a malformed --home is refused with one clear line", False)
        except ForgeError as e:
            ck("ERRORS: a malformed --home is refused with one clear line", "--home wants" in str(e))
        ck("--home: a well-formed value parses to the lineage's home list",
           parse_homes(["abc=x.git,y.git"]) == {"abc": ["x.git", "y.git"]})

        # ---- render + json ---------------------------------------------------------------------
        txt = render(doc)
        ck("RENDER: the report renders and shows the orphan set", "THE ORPHAN SET" in txt
           and "only_here.py" in txt)
        ck("RENDER: it shows the worklist for the fork that is not safe",
           "MERGE-HOME WORKLIST" in txt and "NOT SAFE TO OMIT" in txt)
        ck("RENDER: it shows a proven-safe fork too", "SAFE TO OMIT (proven)" in txt)
        ck("RENDER: the timeline prints dates and a fork width", "FORK POINT =" in txt
           and "fork width = tip date - fork-point date" in txt)
        ck("RENDER: no 'None' leaks into the report", "None" not in txt, )
        ck("RENDER: --timeline alone renders", "FORK POINT =" in render(doc, want=("timeline",)))
        ck("RENDER: --gate alone renders", "RETIREMENT GATE" in render(doc, want=("gate",)))
        ck("JSON: the document is serialisable", bool(json.dumps(doc)))
        ck("JSON: it records that omni was never opened",
           doc["omni"]["opened"] is False and "enforced_by" in doc["omni"])
        ck("JSON: it carries Part 1's totals rather than re-deriving them",
           doc["part1"]["totals"] == family["totals"])

        # ---- side effects ----------------------------------------------------------------------
        ck("NO SIDE EFFECTS: the inspected repos are byte-identical after the run",
           before == after)
        ck("NO SIDE EFFECTS: this tool created no scratch store (unlike Part 1, it never fetches)",
           not any(n.startswith("forge_evolution-scratch")
                   for n in os.listdir(tempfile.gettempdir())))

        bad = [n for n, ok in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s"
              % (len(checks) - len(bad), len(checks),
                 ("   FAILED: " + "; ".join(bad)) if bad else ""))
        return 1 if bad else 0
    except ForgeError as e:
        # A crash is not a pass: without this an unexpected refusal would abort with no FAIL line,
        # and the exit code alone could be mistaken for a clean run that reported nothing.
        print("\n== selftest == ABORTED after %d checks by an unexpected error: %s"
              % (len(checks), e))
        return 1
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ── cli ───────────────────────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="forge_evolution.py",
        description="PART 2 of 2 (ticket #452). Consumes forge_family_tree.py (Part 1) and adds "
                    "the EVOLUTION TIMELINE (root/fork-point/tip dates and the fork width), the "
                    "CONTAINMENT RETIREMENT GATE (a fork is safe to omit only when every file at "
                    "its tip resolves by content identity into its home), and the ORPHAN report "
                    "(code blobs that exist only at non-canonical tips). Read-only: it PLANS "
                    "retirement and never performs it.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Tips come from Part 1 and are NEVER re-resolved here: 183 of the 264 bare repos "
               "have an unresolvable HEAD (a symref to a branch that does not exist), for which "
               "`git rev-parse HEAD` prints the literal string 'HEAD' on stdout — so a caller that "
               "ignores the exit status passes the word 'HEAD' on as if it were a sha. omni.git is "
               "BLACK-BOXED (#452 §2) on two facts — it is NOT a git (every ordinary git command "
               "against it fails), and it is STALE (measured BY OBJECT, never by name, it holds "
               "193 of the forge's 261 resolvable tips — 74% — and is missing 68, including "
               "agent_tools_suite.git's tip 888d3447c6). This tool refuses to open it; "
               "config/forge/remotes/*.git is the only authority.")
    ap.add_argument("--remotes", help="the bare-repo directory (default: whatever Part 1 reports; "
                                      "it finds config/forge/remotes by walking up)")
    ap.add_argument("--family-json", metavar="PATH",
                    help="consume this Part-1 JSON ('-' reads stdin) instead of running Part 1")
    ap.add_argument("--family-tree", metavar="PATH", default=None,
                    help="path to forge_family_tree.py (default: next to this file)")
    ap.add_argument("--lineage", metavar="NAME",
                    help="show only the family matching this repo name, lineage name, or id (the "
                         "orphan set is still computed over the whole forge)")
    ap.add_argument("--override", action="append", metavar="ID=REPO.git",
                    help="forwarded to Part 1 unchanged: name REPO.git canonical for lineage ID. "
                         "Direction is Part 1's to decide, not this tool's (#452 §5)")
    ap.add_argument("--override-file", metavar="PATH", help="forwarded to Part 1 unchanged")
    ap.add_argument("--home", action="append", metavar="ID=REPO.git[,REPO.git]",
                    help="ADD home repos for the containment gate of lineage ID (a grab-bag fork's "
                         "packages can belong to several homes). REPO.git may live in ANOTHER "
                         "lineage — that is what this flag is for. It never renames a canonical, "
                         "a repo named here is a DESTINATION and so is never itself proposed for "
                         "omission, and a name Part 1 does not know stops the run")
    ap.add_argument("--timeline", action="store_true", help="the evolution timeline only")
    ap.add_argument("--gate", action="store_true", help="the containment retirement gate only")
    ap.add_argument("--orphans", action="store_true", help="the orphan blob report only")
    ap.add_argument("--json", metavar="PATH",
                    help="write the machine-readable JSON here ('-' for stdout, which suppresses "
                         "the report)")
    ap.add_argument("--verbose", action="store_true",
                    help="full file lists instead of a capped excerpt")
    ap.add_argument("--selftest", action="store_true",
                    help="throwaway git repos in a temp dir: containment, drift, semantic change, "
                         "and a fork-width timeline (no network, no live db)")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    try:
        if args.family_json:
            family = check_family(load_family(args.family_json))
            if args.remotes:
                family["remotes"] = args.remotes
            if args.override or args.override_file:
                raise ForgeError(
                    "--override / --override-file are forwarded to Part 1, so they cannot apply to "
                    "a --family-json that Part 1 has already produced. Either drop them, or drop "
                    "--family-json and let this tool run Part 1 with them.")
        else:
            family = check_family(run_part1(args.family_tree or default_family_tree(),
                                            remotes=args.remotes, overrides=args.override,
                                            override_file=args.override_file))
        doc = evolve(family, only=args.lineage, extra_homes=parse_homes(args.home))
    except ForgeError as e:
        sys.stderr.write("forge_evolution: %s\n" % e)
        return 2
    except subprocess.TimeoutExpired:
        sys.stderr.write("forge_evolution: a git command timed out — is a repo corrupt?\n")
        return 2

    if args.json == "-":
        print(json.dumps(doc, indent=2, sort_keys=True))
        return 0
    if args.json:
        try:
            with open(args.json, "w") as fh:
                json.dump(doc, fh, indent=2, sort_keys=True)
                fh.write("\n")
        except OSError as e:
            sys.stderr.write("forge_evolution: could not write --json %s: %s\n" % (args.json, e))
            return 2
        print("wrote %s" % args.json)
    want = tuple(w for w, on in (("timeline", args.timeline), ("gate", args.gate),
                                 ("orphans", args.orphans)) if on) \
        or ("timeline", "gate", "orphans")
    print(render(doc, verbose=args.verbose, want=want))
    return 0


if __name__ == "__main__":
    sys.exit(main())
