#!/usr/bin/env python3
"""pair_loop.py — the agent-pair loop, BRANCH-PER-TICKET: a ticket authorizes a worker; its
counterpart validates; the work lives on the ticket's own branch until it is merged.

One iteration of the adversarial network, harnessed:

    1. BRAKE     ticket.stops — an active (unreleased) stop ticket aimed at the target or any
                 ancestor halts the loop before anything acts.
    2. OPEN      create branch `ticket/<id>` off the base branch and check it out in a dedicated
                 git WORKTREE (a second working directory driven by the same .git, so the base
                 tree is never touched). The pair runs with its cwd IN that worktree.
    3. PAIR      register each agent and authorize it on the ticket (agent.register + ticket.assign)
                 LAZILY — immediately before that agent runs, never before (see Gov). A re-asked
                 worker exists only because its predecessor was rejected, so neither its id nor its
                 birth prompt is knowable any earlier. Then, and only then, the ticket goes ACTIVE:
                 the db REFUSES ACTIVE on a ticket with no agent assigned, so the assign must come
                 first (policy 9). Fresh spawns ARE the memory clear: a new agent has no context; the
                 OLD agents' trails stay on the record forever (the journal is append-only).
    4. WORK      spawn the worker (`claude -p`, tools limited to reading + writing the deliverable)
                 in the worktree; it reports {"done":true,"ref":...} on its last line. The HARNESS
                 then COMMITS the work onto `ticket/<id>` (the worker holds no git pen) — the single
                 --deliverable file by default, or its WHOLE PACKAGE when the deliverable is a forge
                 module (see policy 8, COMMIT SCOPE).
                 Every file that commit lands is then STAMPED into the artifact registry through the
                 governed artifact.record route, at the moment of the mint (policy 10).
                 A worker that reports NOTHING READABLE — no JSON on its last line, done=false, a
                 timeout, a non-zero exit — has FAILED ITS ROUND, and that is all: nothing is
                 committed (it reported no deliverable) and no adversary is spawned (there is no
                 claim to judge). The worktree PERSISTS with whatever it did write, and the next
                 round's fresh worker inherits both that and a finding saying what went wrong. The
                 pair does not crash over a silent agent (policy 9).
    5. VALIDATE  spawn the adversary in the same worktree, BLIND to the worker's reasoning (it sees
                 the ticket + the artifact, never the worker's transcript); it reports
                 {"verdict":"pass"|"fail","findings":[...]} on its last line.
    6. SETTLE    pass -> MERGE `ticket/<id>` into the base branch; only if the merge REALLY happened
                 (a new merge commit exists — see merge_to_base): work.record the artifact (permanent
                 UID), status DONE (the db itself refuses DONE without two distinct agents in two
                 distinct roles), then REAP the worktree.
                 fail -> journal the findings and re-run with a FRESH worker (--rounds), findings
                 appended to the new worker's birth prompt; the branch keeps every round's commits.
                 merge conflict -> the merge is ABORTED, the branch and worktree PERSIST, and the
                 ticket stays open (never DONE) — nothing is silently clobbered.
                 EMPTY branch (no commits the base lacks — e.g. the worker rewrote the file already
                 on base byte-for-byte, so there was nothing to commit) -> also a REFUSAL: nothing is
                 merged, nothing is recorded, the branch and worktree persist, the ticket stays open.
                 A ticket only ever reaches DONE by landing a real commit through a real merge.

THE SETTLED BRANCH-PER-TICKET DEFAULTS (RFC #220's open spec questions, answered here in code):

  (1) NAMING — `ticket/<id>`, deterministic from the ticket id alone (branch_of()). No title slug:
      a title can be long, non-ascii, or duplicated, and the id is already the ticket's identity.
  (2) LIFECYCLE — the branch is created when the pair is dispatched (this loop starts), off the
      base branch; EVERY round's deliverable is committed on it; the base branch is never written
      to by the pair.
  (3) MERGE POLICY — `git merge --no-ff` (an explicit merge commit) into the base. --no-ff, not
      fast-forward: the merge commit is the permanent record that `ticket/<id>` landed, and it
      survives even after the branch ref moves on. Not squash: squashing discards the per-round
      commits that ARE the ticket's history. A conflict aborts the merge and keeps the ticket open.
      The merge refuses unless the base tree is on the base branch and has NO uncommitted TRACKED
      changes (#213: never merge into a drifted tree) — the same guard mint_crank.py uses.
      It ALSO refuses unless `git rev-list <base>..ticket/<id>` is non-empty, because git's exit
      code alone does not mean a merge happened: merging a branch with no commits of its own prints
      "Already up to date" and exits 0, moving nothing. That success is a LIE the settle path must
      not believe — an empty branch means the deliverable was never committed, so there is nothing
      to land and nothing to record. merge_to_base therefore checks the branch is non-empty BEFORE
      merging and re-checks AFTER that a real merge commit (HEAD moved, two parents) now exists;
      only that post-state proves ok=True. See the "empty branch" checks in --selftest.
  (4) ISOLATION — one git worktree per ticket, under `<repo>/.git/pair-worktrees/ticket-<id>`.
      Inside `.git` on purpose: `.git` is not part of any working tree, so a worktree there can
      never appear in `git status` (#213: the base tree stays clean) and is skipped by the repo's
      tree-walkers, which prune `.git` (the established pattern — see gpl_stamp.py php_files()).
      Override with registry.json {"branch_per_ticket": {"worktrees": "<path>"}} (relative paths
      resolve against the repo root).
  (5) mint_crank — unaffected and NOT reconciled away: a crank is still "commit + tag IN PLACE on
      main" (mint_crank.py refuses any other branch). Pair work happens on ticket branches in
      OTHER worktrees; the base tree stays on the base branch the whole time, so the crank still
      sees exactly what it expects. The crank captures ticket work only after it has merged.
  (6) HYGIENE — the WORKTREE is ephemeral: reaped on a successful merge (#216), leaving the base
      tree clean (#213). The BRANCH is kept: it is the ticket's durable, checkable trace ("branch
      ticket/<ID> with the deliverable committed there" is an acceptance criterion that must stay
      true after DONE), and deleting it would erase history this system is built not to erase.
  (7) GOVERNANCE — branch-open, commit, merge and reap are each APPENDED to the ticket's journal
      (ticket.progress) attributed to `forge-t<id>`, a REGISTERED agent that holds the git pen for
      the ticket and never authors work product. It journals without being ticket.assign'd, exactly
      as dispatch-01 already does; see forge_agent() for why assigning it would hollow out the db's
      own pair-completion backstop.
  (8) COMMIT SCOPE (#409) — what the harness stages is the DELIVERABLE FILE, except for one case:
      a FORGE deliverable, whose scope is its whole PACKAGE DIRECTORY. A forge-rewrite unit must
      land a package `pip install -e .` can install (the FORGE refactor standard's requirement 3),
      and a package is never one file: it is the module PLUS its pyproject.toml, its config, its
      entry points and its submodules. Committing only the --deliverable landed the module alone
      and left the rest to be reported as strays and reaped — which is exactly what happened to the
      forge pilot #401: `checkouts/current/forge2/artifact_tree_gen/add.py` merged, its
      pyproject.toml never did, and the landed package is NOT installable.
      So: when the deliverable's path holds a `forge2` component with a package directory under it
      (package_root_of(): `<...>/forge2/<repo>/<anything>` => package root `<...>/forge2/<repo>`),
      the harness stages that WHOLE directory's new/modified/deleted fileset. Everything else — the
      tags, the tools, the docs — keeps the single-file behavior UNCHANGED, because the gate is the
      path and nothing else. `--package-commit on|off` overrides the gate; `auto` (the default) is
      the path gate above.
      Build artifacts under the package root are the one exclusion (is_build_artifact(): `.egg-info`,
      `build/`, `dist/`, `__pycache__`, ...). They are not source — validating installability with
      `pip install -e .` is what CREATES them — and committing them would be actively harmful: once
      `<repo>.egg-info` is TRACKED on the base, any later `pip install -e .` in the base tree rewrites
      it, the base tree is drifted, and policy 3's #213 guard REFUSES every subsequent merge. They are
      skipped and NAMED on the journal, never dropped silently.
  (9) THE PAIR'S GOVERNANCE ORDER (#439, redoing #279 without the regression it shipped) — two rules
      that only look like housekeeping until they are broken:
      LAZY REGISTRATION. An agent is registered and authorized at ITS OWN spawn (Gov.enlist), with
      the exact prompt it is spawned on. Registering the pair up front cannot work for a RE-ASKED
      worker: its id and birth prompt do not exist until its predecessor is rejected, so an eager
      harness could only ever record agents that do not exist with prompts they will not be born on.
      ASSIGN BEFORE ACTIVE. `tg_tickets_active_needs_agent` (migrations/0029_ticket_authorization.sql)
      ABORTS any UPDATE putting a ticket ACTIVE while no agent is assigned to it — SQLite raises,
      PDO reports SQLSTATE 23000, rest.php returns a 500. So ACTIVE must follow at least one
      ticket.assign. Ticket #279 made registration lazy but left the ACTIVE flip ahead of every
      assign, and every new dispatch died at "pair (round 1)" while already-ACTIVE tickets went on
      working — the pipeline's core function was dead and looked survivable. Gov.activate() now
      REFUSES to run before an enlist(), so the order cannot be re-broken silently, and --selftest
      drives it against the REAL trigger read out of the migration (see _StGov). ACTIVE is set once,
      on round 1; later rounds are already ACTIVE and send nothing.
      NO-VERDICT IS A ROUND OUTCOME, NOT A CRASH. See step 4 above and NoVerdict: a spawn that never
      answers fails its round; only the rounds running out ends the loop (exit 1).
 (10) THE MINT HOOK (#457) — every file a commit LANDS is stamped into the artifact registry at the
      moment it is minted, through the EXISTING governed route `artifact.record`
      (migrations/0014_ticket_artifacts.sql). A registry populated by SCANNING is stale the moment the
      scan finishes; a registry populated at the mint is not. Five deliverables merged before this
      landed (#438, #440, #445, #448, #439) and ticket_artifacts held 0 rows: nothing was forgotten by
      a person, nothing was ever written down. At commit time the harness ALREADY knows the ticket id,
      the path and the commit, and git already content-addresses the bytes, so the stamp costs one
      `rev-parse` per file and needs no new store, table or route:
          forge_sha = `git rev-parse <commit>:<path>` — the git BLOB sha of that exact file.
                      FOR CODE, GIT IS THE STORE. (large-blobs/artifacts exist only because VM images
                      do not fit in git.)
          name      = the file's repo-relative PATH — stable, resolvable, what a human greps.
          version   = the short commit sha the file landed in (sha[:10], the spelling the journal and
                      commit_note already use, so one ticket reads one way everywhere).
          kind      = ARTIFACT_KIND ('forge-source') — a STABLE ARTIFACT class, documented there.
                      NEVER the ticket's kind: build/test/documentation is the WORK's kind, not the
                      ARTIFACT's. VM images register as 'forge-vm' in this same column.
      EVERY file in the commit's SCOPE is stamped, never just the --deliverable: a forge package
      commits several (policy 8), and a registry naming one of them lies about the rest. That holds
      even when two of them are byte-identical (a package's empty `__init__.py` files share one blob
      sha) — they are two artifacts with two paths, so they get two rows; see IDEMPOTENT below.
      Three rules the stamp obeys, each driven in --selftest against the REAL 0014 route:
        NEVER FATAL. A failed artifact.record must not fail the commit or the round. The stamp is
          instrumentation, and instrumentation that can break the pipeline is worse than none (the
          discipline TreeView's telemetry already follows). Forge.stamp_artifacts() raises NOTHING,
          ever: every failure is caught, NAMED on the returned record, and journaled by commit_note.
        IDEMPOTENT. The key is (ticket_id, forge_sha, NAME) — re-committing the same bytes to the same
          PATH mints no second row, so a round-2 commit of an unchanged file is not a new artifact.
          The name belongs in the key: the dedupe rule exists to stop a ROUND from minting a file
          twice, and WITHOUT the name it also silences a file that merely shares another's bytes. Two
          DISTINCT paths that happen to be byte-identical — a package's empty `__init__.py` files, the
          everyday case for the packages policy 8 commits — are two artifacts, and each gets its row.
          A registry that names one of them lies about the other, and the unnamed one is exactly what
          a human greps for and cannot find. 0014's artifact.record is a bare INSERT with no unique
          index behind it, so the dedupe is a READ of the ticket's rows through the governed
          `artifact.list` route before any write — not a db constraint, and not a hand-written db
          touch.
        NO SQL PEN. artifact.record + artifact.list, and nothing else. The harness never writes SQL.

THE DIRECTORY-SERVICE GATE (#457) — MEASURED, AND NOT MET BY THIS FILE ALONE. READ THIS BEFORE
BELIEVING A STAMPED ROW IS FINDABLE:

  #457 asks that `resolver.py <forge_sha>` resolve a stamped row "via the forge-artifacts probe",
  on the premise that "the lookup path EXISTS". IT DOES NOT REACH THIS REGISTRY, for two INDEPENDENT
  reasons, both measured against tools/resolver.py as it is now and both pinned by --selftest so they
  cannot rot into a comfortable fiction:

    (a) WRONG STORE. resolver.py's `forge-artifacts` probe reads the FORGE ledger — forge.db's
        `artifacts` table, content-addressed by sha256 (resolver.py: "SELECT filename FROM artifacts
        WHERE lower(sha256) = ?"). `artifact.record` writes CONGRUENCY's `ticket_artifacts` table.
        They are two unrelated stores that share the word "artifact": resolver.py does not contain
        the string `ticket_artifacts` anywhere. No hash this harness could record makes a
        ticket_artifacts row visible to that probe, so this is not fixable by choosing a different
        sha — the STORE is the blocker.
    (b) WRONG KIND, so the probe never even runs. forge_sha is a git blob sha1 = 40 hex, and
        resolver.detect_kind() routes 40 hex to `git-blob`, whose fan-out is
        [omni-blob, store-occ, memgraph-node, git-object-db] — `forge-artifacts` is not in it. That
        probe only fires for a 64-hex `sha256`. The ticket's own transcript shows this: it read
        "probes: content-sha256, forge-artifacts, git-object-db" from a SHA256 query, then specified
        forge_sha as a git blob sha, which never reaches that fan-out.

  So the gate needs a change to tools/resolver.py, which is NOT this ticket's deliverable ("touch
  nothing else"). What this file CAN and does guarantee is the half that is its own: the row exists,
  at mint time, with a forge_sha that is a true content address of the landed bytes in the store the
  ticket names — `git cat-file -t <forge_sha>` is `blob` and `git rev-parse <commit>:<path>` returns
  it (both proven in --selftest). The tether is fixed; the resolver still cannot see it.

  THE MINIMAL RESOLVER CHANGE THAT CLOSES THE GATE (for the follow-up ticket, NOT done here):
    1. probes_for("git-blob") gains "ticket-artifacts"  (forge_sha is a git-blob identifier).
    2. resolve_to_shas() gains that probe against the congruency db `ccon`, which it already opens:
         SELECT name FROM ticket_artifacts WHERE lower(forge_sha) = ?
       -> the row's `name` IS the repo-relative path, so the match names the path with no join.
    Nothing else moves: `ccon` and its `table_exists()` guard are already there for ticket_works.

PARALLEL PAIRS: N tickets => N branches => N worktrees, with zero tree contention (that is the
whole point of worktrees). `--dispatch N --parallel K` runs up to K pairs at once, each a child
process on its own ticket. The only shared resource is the repo's .git (branch refs, the worktree
registry, and the base tree used for merging), so every operation that mutates it — worktree
add/remove/prune and the merge — is serialized across processes by an flock on
`<repo>/.git/pair-loop.lock`. Commits do not take that lock: each worktree has its OWN index, and
git's object store is already concurrency-safe.

Every db write goes through the governed REST surface (token routes) — the harness holds no SQL
pen. Registry-gated per note-for-claude: walks up to registry.json and throws if it cannot see it;
any unexpected outcome files a Variant-A bug report to the registry's bug_reports sink.

Usage (every form needs CONGRUENCY_API_KEY, from the env or .secrets/ats.env, EXCEPT --selftest):
    python3 pair_loop.py --ticket 251 --deliverable docs/X.md      # run the pair on an existing ticket
    python3 pair_loop.py --file documentation --title "..." --body "..." --deliverable docs/X.md
    python3 pair_loop.py --dispatch 3 --parallel 2                 # route the queue, 2 pairs at once
    python3 pair_loop.py --selftest                                # prove git + governance + the stamp
    python3 pair_loop.py --selftest --install-check                 # ...and pip-install the merged package
    ... [--rounds 2] [--timeout 480] [--base main] [--keep-worktree] [--package-commit auto|on|off]

--selftest builds a THROWAWAY git repo in a temp dir, runs the whole branch/worktree/commit/merge/
reap flow through it (including two pairs in parallel, a deliberate merge conflict, and a forge
PACKAGE deliverable per policy 8), then deletes it. It also proves policy 9's governance ORDER
against the REAL constraint: a second throwaway db is built by EXECUTING this repo's own
migrations/0029_ticket_authorization.sql, so the rule the checks meet is the actual shipping trigger
rather than a Python imitation of it (an imitation is what let #279 pass 129/129 while breaking every
dispatch). The MINT HOOK (policy 10) is driven the same way: the throwaway db also executes
migrations/0014_ticket_artifacts.sql, so the artifact.record/.list the stamp calls are the real routes
and the rows are read back out of the real table — never from what the hook says it did. Every
forge_sha a check asserts is compared against git's OWN answer in the throwaway repo (`git rev-parse
<commit>:<path>`, cross-checked by `git hash-object`), so no check can agree with a bug just because
the same code produced both sides. It spawns no agents, needs no api key and no server, and WRITES
nothing: this repo and the live db are only ever READ — the migrations for their DDL, tools/resolver.py
as TEXT for #457's gate pins (reading, never importing: an import would write a .pyc into this repo),
and the db (when this host has one) read-only via immutable=1, which creates no -wal/-shm sidecars
(#153). No live registry is ever written: every artifact.record here lands in a temp-dir db that is
deleted with the run. Unless you add --install-check below, it never touches the network either.

--install-check (only with --selftest) adds ONE further check, the last one to run: it builds a
throwaway venv and runs a real `pip install -e .` against the forge package the selftest merged onto
its throwaway base, proving the landed tree is installable — #409's acceptance criterion. It is
opt-in and not part of --selftest precisely because it is the one check that USES THE NETWORK (pip
fetches the PEP 517 build backend named by the package's pyproject.toml). Without a network it
reports SKIP, never FAIL: an unreachable index says nothing about the package.

Exit codes:
    0  settled — the branch merged into the base and the ticket is DONE (--selftest: all checks passed)
    1  rounds exhausted — no round ever passed: the adversary rejected the work, or the worker never
       answered (policy 9); branch + worktree kept, ticket stays open
       (--selftest: at least one check FAILED)
    2  unexpected — a Variant-A bug report was filed to the registry's bug_reports sink
    3  halted — an active stop ticket aims at this ticket or an ancestor; nothing was done
    4  passed review but the MERGE was refused — a conflict, a drifted base tree (#213), or an EMPTY
       branch with no commits the base lacks (the deliverable was never committed, or a prior run
       already merged it). The branch and its worktree persist and the ticket stays open; nothing was
       clobbered and no merge was claimed that did not happen.
"""
import argparse
import contextlib
import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
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
CONG = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")


def _secret(name):
    path = os.path.join(os.path.dirname(ROOT), ".secrets", "ats.env")
    if os.path.isfile(path):
        for line in open(path):
            if line.strip().startswith(name + "="):
                return line.strip().split("=", 1)[1]
    return os.environ.get(name)


API_KEY = _secret("CONGRUENCY_API_KEY")


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks)."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "pair_loop.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:], "note": "pair_loop harness",
            }) + "\n")
    except Exception:  # noqa: BLE001
        pass


class Unexpected(RuntimeError):
    pass


class NoVerdict(Unexpected):
    """A spawn that produced no usable answer: it timed out, exited non-zero, or printed no readable
    JSON object on its last line (and, for a worker, `done` that is not true).

    A SUBCLASS of Unexpected on purpose. Every call site that does NOT handle it keeps the old
    behavior exactly — bug report + exit 2 through main()'s handler — so nothing but the one path
    that opts in changes. The WORKER's spawn is that path: a worker who says nothing readable has
    FAILED ITS ROUND, which the loop absorbs (a fresh worker runs the next round); it has not
    crashed the pair. See main()'s round loop and --selftest's "-- no-verdict" checks.
    """


# ── REST (all writes go through the governed surface) ─────────────────────────────────────────────
def rest(route, obj=None, method=None):
    url = CONG + "/rest.php?route=" + route
    if obj is not None and (method or "POST") == "GET":
        url += "&" + "&".join("%s=%s" % (k, urllib.request.quote(str(v))) for k, v in obj.items())
        obj = None
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json", "X-Api-Key": API_KEY or ""})
    with urllib.request.urlopen(req, timeout=15) as r:
        out = json.loads(r.read().decode())
    if "error" in out:
        raise Unexpected("route %s failed: %s" % (route, out["error"]))
    return out


def rows(route, params):
    return rest(route, params, method="GET").get("rows", [])


# ── commit scope: which fileset a deliverable stands for (#409, policy 8) ─────────────────────────
PACKAGE_MARKER = "forge2"          # a path component; the directory UNDER it is a package root

# Not source, and not ours to land: every one of these is REGENERATED by the act of building or
# validating a package (`pip install -e .` writes <name>.egg-info; importing writes __pycache__), so
# committing them would track files that rewrite themselves and drift the base tree (#213).
PACKAGE_EXCLUDE_DIRS = ("__pycache__", "build", "dist", ".eggs", ".tox", ".nox",
                        ".venv", "venv", ".pytest_cache", ".mypy_cache", ".ruff_cache")
PACKAGE_EXCLUDE_ENDS = (".egg-info", ".dist-info", ".egg")     # directory OR file names
PACKAGE_EXCLUDE_FILES = (".pyc", ".pyo", ".pyd")


# ── the mint hook: what a stamped row says it IS (#457, policy 10) ────────────────────────────────
# The ARTIFACT's class, and a stable one: every file a pair lands is source held in git, whatever the
# WORK that produced it was. It is deliberately NOT the ticket's kind — 'build', 'bug' and
# 'documentation' describe the job, not the thing, and a registry keyed on the job cannot answer
# "what IS this?". The column is shared with the forge's other classes ('forge-vm' for a VM image,
# 'run-output' for crank evidence — 0014's own example), so the value must name the class and not
# the producer. Change it and every row minted before the change reads as a different class: this
# constant is a contract with the registry's readers, not a label.
ARTIFACT_KIND = "forge-source"

# The routes the mint hook uses — BOTH already exist (migrations/0014_ticket_artifacts.sql). #457 adds
# no store, no table and no route: it fills the one that was already there and always empty.
ARTIFACT_RECORD_ROUTE = "artifact.record"     # POST, token: INSERT one row
ARTIFACT_LIST_ROUTE = "artifact.list"         # GET, public: this ticket's rows — the idempotency read


def _parts(path):
    """A repo-relative path as its components, normalized ('./a//b' -> ['a', 'b']). git always
    speaks '/', os.path.normpath speaks os.sep; this reconciles them once, here."""
    return [p for p in os.path.normpath(path).replace(os.sep, "/").split("/") if p not in ("", ".")]


def package_root_of(deliverable, marker=PACKAGE_MARKER):
    """The PACKAGE directory a forge deliverable belongs to — `<...>/forge2/<repo>` — else None.

    None means "this deliverable is a lone file" and the caller keeps the single-file commit; that is
    the answer for every tag, tool and doc, whose paths hold no `forge2` component at all.

    The marker is matched as a path COMPONENT, anywhere in the path — not as a prefix. It has to be:
    the forge units' deliverables live at `checkouts/current/forge2/<repo>/<module>.py`, so `forge2`
    is the THIRD component, and a startswith("forge2/") test would miss every one of them. The last
    matching component wins, so a package that itself contains a `forge2` directory resolves to the
    innermost package rather than the outermost.

    A package root needs a directory of its own: there must be at least one component between the
    marker and the deliverable's filename (`forge2/<repo>/add.py` -> `forge2/<repo>`, but bare
    `forge2/add.py` -> None, because a file sitting directly in forge2/ is in no package and
    `git add forge2/` would sweep every OTHER repo in the forge into this ticket's commit).
    """
    parts = _parts(deliverable)
    for i in range(len(parts) - 1, -1, -1):        # last marker component wins (innermost package)
        if parts[i] == marker and len(parts) - i >= 3:
            return "/".join(parts[: i + 2])
    return None


def is_build_artifact(path):
    """True if `path` is a build/cache artifact rather than package source (policy 8's exclusion).

    Matched per COMPONENT, so it catches both the directory itself and everything under it:
    `forge2/x/x.egg-info` and `forge2/x/x.egg-info/PKG-INFO` are both artifacts.
    """
    for part in _parts(path):
        if part in PACKAGE_EXCLUDE_DIRS or part.endswith(PACKAGE_EXCLUDE_ENDS):
            return True
    return path.endswith(PACKAGE_EXCLUDE_FILES)


def under(path, scope):
    """Is `path` inside `scope` (or scope itself)? A PATH comparison, never a string prefix compare:
    `docs/xx.md`.startswith("docs/x") is True and would be a lie. Both sides must already be
    normpath'd by the caller — see commit_deliverable() on why a false answer here is unrecoverable.

    When `scope` is a FILE (the single-file default) only the equality arm can ever fire, since no
    path can live under a file — which is why that default's behavior is unchanged by #409.
    """
    return path == scope or path.startswith(scope + os.sep)


# ── the forge: branch-per-ticket git, scoped to one repo (so --selftest can drive a throwaway) ────
class Forge:
    """Every git act the branch-per-ticket flow performs, against one repo root.

    A WORKTREE is a second working directory driven by the same .git: `git worktree add` checks a
    branch out somewhere else on disk, so two pairs can hold two branches checked out at once with
    no contention — which a single working tree cannot do.

    Shared-.git mutations (worktree add/remove/prune, merge) are serialized across PROCESSES by an
    flock, so parallel pairs never race. Never nest lock() inside lock(): flock on a second open
    file description of the same file blocks the same process (self-deadlock).

    `api` is the mint hook's seam (#457, policy 10): the governed-route caller commit_deliverable
    stamps through. It is the SAME shape as Gov.api and for the same reason — --selftest binds a
    throwaway db carrying the REAL 0014 routes, so what the checks drive is the shipping code against
    the shipping SQL. None means "do not stamp", which is what a bare Forge(repo) is: the git layer
    on its own, with no governance surface to reach, exactly as every git check here has always
    constructed it. forge_for() binds the real `rest` for production.
    """

    def __init__(self, root, worktrees=None, package_marker=PACKAGE_MARKER, api=None):
        self.root = os.path.abspath(root)
        wt = worktrees or os.path.join(".git", "pair-worktrees")
        self.worktrees = wt if os.path.isabs(wt) else os.path.join(self.root, wt)
        self.lockfile = os.path.join(self.root, ".git", "pair-loop.lock")
        self.package_marker = package_marker    # policy 8's gate; see package_root_of()
        self.api = api                          # policy 10's seam; None = no stamping (git only)

    # ── plumbing ─────────────────────────────────────────────────────────────
    def _run(self, args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True, text=True)

    def git(self, *args, cwd=None):
        """Run git; raise Unexpected on non-zero. Returns stdout."""
        r = self._run(list(args), cwd)
        if r.returncode != 0:
            raise Unexpected("git %s failed (exit %s): %s"
                             % (" ".join(args[:3]), r.returncode, (r.stderr or r.stdout).strip()[-300:]))
        return r.stdout

    def git_ok(self, *args, cwd=None):
        """Run git; return (ok, combined-output) instead of raising — for the paths where failure
        is an OUTCOME (a merge conflict) rather than a harness fault."""
        r = self._run(list(args), cwd)
        return r.returncode == 0, (r.stdout + r.stderr).strip()

    @contextlib.contextmanager
    def lock(self):
        os.makedirs(os.path.dirname(self.lockfile), exist_ok=True)
        fh = open(self.lockfile, "a+")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()

    # ── naming (deterministic from the ticket id — RFC #220 q1) ──────────────
    def branch_of(self, tid):
        return "ticket/%d" % int(tid)

    def worktree_of(self, tid):
        return os.path.join(self.worktrees, "ticket-%d" % int(tid))

    # ── reads ────────────────────────────────────────────────────────────────
    def head(self, cwd=None):
        return self.git("rev-parse", "HEAD", cwd=cwd).strip()

    def current_branch(self, cwd=None):
        b = self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd).strip()
        if b == "HEAD":
            raise Unexpected("%s is in DETACHED HEAD state — check out a branch first" % (cwd or self.root))
        return b

    def branch_exists(self, br):
        return self._run(["show-ref", "--verify", "--quiet", "refs/heads/" + br]).returncode == 0

    def porcelain(self, cwd=None, extra=()):
        """`git status --porcelain -z` parsed into [(xy, path)]; paths are repo-relative and RAW.

        `extra` appends further arguments (a `-uall`, a `--` pathspec) for callers that need a
        narrower or deeper listing; the default () is the whole-worktree listing every caller before
        #409 got, unchanged.

        -z, never the plain form. In plain `--porcelain`, git C-QUOTES any path holding a space,
        a quote, or a non-ascii byte — `docs/naïve.md` is printed as `"docs/na\\303\\257ve.md"`
        (escapes and surrounding quotes included) — so a raw compare of that text against a real
        path silently MISSES it. `-z` is defined to emit each path verbatim, NUL-separated, and
        never quotes; that is the whole reason it exists. Rename/copy entries ('R'/'C') carry a
        SECOND NUL field (the source path); it is consumed here so it can never be mistaken for
        an entry of its own.
        """
        raw = self.git("status", "--porcelain", "-z", *extra, cwd=cwd).split("\0")
        fields, i = [], 0
        while i < len(raw):
            entry = raw[i]
            i += 1
            if not entry:
                continue          # the trailing NUL leaves an empty last field
            xy, path = entry[:2], entry[3:]
            if "R" in xy or "C" in xy:
                i += 1            # drop the rename/copy source field that follows
            fields.append((xy, path))
        return fields

    def tracked_dirty(self, cwd=None):
        """Paths with uncommitted TRACKED changes (untracked '??' entries ignored) — the #213 drift
        check, mirroring mint_crank.py's guard."""
        return [p for xy, p in self.porcelain(cwd) if xy != "??"]

    def staged(self, cwd=None):
        """The fileset the next commit will carry: the INDEX against HEAD, `git diff --cached
        --name-only -z`. ASKED of git rather than assembled from what we staged, so what gets
        journaled is what actually landed and not what we intended to land.

        -z for porcelain()'s reason: plain `--name-only` C-quotes exotic paths, and this list is
        written to the append-only record.
        """
        return [p for p in self.git("diff", "--cached", "--name-only", "-z", cwd=cwd).split("\0") if p]

    # ── the mint hook's content address (#457, policy 10) ────────────────────
    def blob_sha(self, commit, path, cwd=None):
        """The git BLOB sha of `path` AS IT EXISTS IN `commit` — `git rev-parse <commit>:<path>`.

        This is `forge_sha`, and it is free: git content-addressed the bytes when it wrote them, so
        the value is already in the object db and no hashing happens here. It is the sha of the bytes
        THAT COMMIT holds, not of the file on disk — a later round can move the worktree's copy
        without moving what this row says landed.

        None (never a raise) when the path is not a blob in that commit. That is a real case, not a
        fault: staged() reports DELETED files too (a package rewrite may retire a module, policy 8),
        and a deleted path has no blob in the commit that deletes it. A deletion is not an artifact,
        so the caller skips it and NAMES it rather than stamping a row for bytes that do not exist.

        git_ok, not git: a missing path is an OUTCOME here, and this runs under the never-fatal stamp
        (policy 10), which may not raise. --verify --quiet so a miss is a clean exit 1 with no stderr.
        The sha is shape-checked before it is returned: `<commit>:<dir>` resolves to a TREE and a
        gitlink to a COMMIT, and a row claiming either is a blob would be a lie the registry keeps.
        """
        ok, out = self.git_ok("rev-parse", "--verify", "--quiet", "%s:%s" % (commit, path), cwd=cwd)
        sha = (out or "").strip()
        if not ok or not sha:
            return None
        ok, kind = self.git_ok("cat-file", "-t", sha, cwd=cwd)
        return sha if ok and kind.strip() == "blob" else None

    # ── commit scope (#409, policy 8) ────────────────────────────────────────
    def package_root(self, deliverable, package="auto"):
        """This commit's scope: the deliverable's package root, or None for the single-file default.

        `package` is the --package-commit gate, in three explicit states:
          "auto" (default) — the PATH decides: a forge deliverable gets its package, everything else
                             (tags, tools, docs) gets the unchanged single-file commit.
          "on"             — force a package commit. If the path names no forge package, the scope
                             falls back to the deliverable's own DIRECTORY: an explicit request to
                             commit a directory, honored literally.
          "off"            — force the single-file commit, even for a forge deliverable.
        """
        if package == "off":
            return None
        root = package_root_of(deliverable, self.package_marker)
        if root is None and package == "on":
            root = "/".join(_parts(deliverable)[:-1]) or None
        return root

    def registered_worktrees(self):
        """Parse `git worktree list --porcelain` into [{path, branch}] (branch '' if detached)."""
        out, cur, res = self.git("worktree", "list", "--porcelain"), {}, []
        for line in out.splitlines():
            if line.startswith("worktree "):
                cur = {"path": line[9:], "branch": ""}
                res.append(cur)
            elif line.startswith("branch ") and cur:
                cur["branch"] = line[7:].replace("refs/heads/", "", 1)
        return res

    # ── i1: open the ticket's branch in its own worktree (idempotent/resumable) ──
    def open_worktree(self, tid, base):
        """Create branch ticket/<id> off `base` and check it out in its own worktree.

        Resumable, like ticket.assign (migration 0033): re-opening an already-open ticket reuses
        the existing branch and worktree instead of failing, so a crashed run can be re-run.
        """
        br, path = self.branch_of(tid), self.worktree_of(tid)
        with self.lock():
            self.git("worktree", "prune")   # drop admin records for worktrees whose dir is gone
            for wt in self.registered_worktrees():
                if wt["branch"] == br:
                    return {"branch": br, "path": wt["path"], "created": False, "base": base}
            if os.path.exists(path):
                raise Unexpected("%s exists but is not a registered worktree for %s — refusing to "
                                 "touch it; move it aside and re-run" % (path, br))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if self.branch_exists(br):
                self.git("worktree", "add", "--quiet", path, br)      # branch survived a prior run
            else:
                if not self.branch_exists(base):
                    raise Unexpected("base branch %r does not exist in %s" % (base, self.root))
                self.git("worktree", "add", "--quiet", "-b", br, path, base)
            return {"branch": br, "path": path, "created": True, "base": base}

    # ── i1: the deliverable is committed ON the branch (the harness holds the git pen) ──
    def commit_deliverable(self, tid, deliverable, message, package="auto"):
        """Stage the deliverable's SCOPE and commit it on the ticket's branch. Returns what landed.

        The scope is the single deliverable FILE — except for a forge deliverable, whose scope is its
        whole PACKAGE DIRECTORY (policy 8; package_root() decides, `package` is the --package-commit
        override). Never `add -A`: the scope is bounded either way, because the worker's mandate is
        bounded either way. Anything dirty OUTSIDE the scope is returned as `strays` so the caller
        can put it on the record rather than let it vanish unmentioned at reap time.

        Why a package cannot be committed one file at a time: a forge unit must land something
        `pip install -e .` installs, so the module without its pyproject.toml is not a smaller
        deliverable — it is a broken one. #401 proved it by landing exactly that.

        Deciding "is / is not in scope" is a PATH comparison, not a string comparison — get it wrong
        in the false-positive direction and the caller journals, permanently and append-only, that
        the delivered file was abandoned uncommitted. Two ways the naive compare lies, both proven in
        --selftest: git C-quotes exotic paths in plain `--porcelain` (hence porcelain()'s -z), and
        one path has many spellings (`./docs/x.md` and `docs/x.md` are the same file; git prints the
        second). So: raw paths from -z, os.path.normpath applied to BOTH sides, via under().

        Returns {committed, sha, branch, package, files, skipped, strays, artifacts}:
          package  the package root this commit's scope was, or None for a single-file commit
          files    the fileset ACTUALLY committed (git's own answer — Forge.staged())
          skipped  build artifacts under the package root, deliberately not committed
          strays   dirty paths outside the scope entirely
          artifacts what the MINT HOOK stamped for this commit (#457, policy 10) —
                   {recorded, skipped, errors, stamped}, from stamp_artifacts(). Present on EVERY
                   return, including the one that commits nothing. Never a raise: a registry that is
                   down costs the round its stamp, never its work.
        """
        wt = self.worktree_of(tid)
        if not os.path.isfile(os.path.join(wt, deliverable)):
            raise Unexpected("no deliverable at %s in the worktree %s — the worker reported done "
                             "but produced no file" % (deliverable, wt))
        # The deliverable itself, always and first — unchanged, and unconditional. A package add is
        # a directory add, which git silently narrows by .gitignore; the deliverable is never allowed
        # to go missing that quietly, so it is staged by name and any refusal raises here.
        self.git("add", "--", deliverable, cwd=wt)

        pkg, skipped = self.package_root(deliverable, package), []
        if pkg:
            # -uall: a wholly-untracked directory collapses to one 'forge2/x/' entry in the default
            # listing, and this needs the FILES. The '--' pathspec scopes the listing to the package,
            # so nothing outside it can be swept in by a glob or a rename.
            add = []
            for _, p in self.porcelain(cwd=wt, extra=("-uall", "--", pkg)):
                (skipped if is_build_artifact(p) else add).append(p)
            if add:
                # Staged by explicit path rather than `add <dir>` so the artifacts above stay out.
                # A DELETED file in `add` stages its deletion, which is correct: the package's real
                # fileset is what the worker left, and a rewrite may retire a module it replaced.
                self.git("add", "--", *add, cwd=wt)

        scope = os.path.normpath(pkg or deliverable)
        strays = [p for _, p in self.porcelain(cwd=wt) if not under(os.path.normpath(p), scope)]
        files = self.staged(cwd=wt)
        if not files:
            # Nothing landed, so there is nothing to stamp — but the key is still here, with the same
            # shape, because every caller reads cm["artifacts"] and a dict that sometimes lacks a key
            # is a KeyError waiting for the one path that made no commit (the empty-branch case).
            nothing = {"committed": False, "sha": self.head(wt), "branch": self.branch_of(tid),
                       "package": pkg, "files": [], "skipped": skipped, "strays": strays}
            nothing["artifacts"] = self.stamp_artifacts(tid, nothing)
            return nothing
        if pkg:
            # The commit log names the fileset, so `git show` alone answers "did the package land
            # whole?" — the question #401 could only be answered by discovering the absence.
            message += ("\n\nPackage commit (#409): %s/ — %d file(s)\n%s"
                        % (pkg, len(files), "\n".join("  " + f for f in files)))
            if skipped:
                message += ("\nBuild artifacts skipped (regenerated by any install): %s"
                            % ", ".join(skipped))
        self.git("commit", "--quiet", "-m", message, cwd=wt)
        cm = {"committed": True, "sha": self.head(wt), "branch": self.branch_of(tid),
              "package": pkg, "files": files, "skipped": skipped, "strays": strays}
        # THE MINT HOOK (#457, policy 10): the commit succeeded, so every file it landed is stamped
        # into the artifact registry NOW, while the ticket id, the paths and the commit are all in
        # hand. Last, and after the commit: a stamp is a record OF a commit that happened, and
        # stamp_artifacts() raises nothing, so nothing below this line can cost the round its work.
        cm["artifacts"] = self.stamp_artifacts(tid, cm)
        return cm

    # ── the mint hook: stamp what landed, at the moment it lands (#457, policy 10) ──
    def stamp_artifacts(self, tid, cm):
        """Record EVERY file this commit landed into the artifact registry, via `artifact.record`.

        Returns {recorded, skipped, errors, stamped} — never raises, whatever happens:

          recorded  [{name, version, forge_sha, kind}] — the rows this call actually minted.
          skipped   ["<path>: <why>"] — a file deliberately NOT stamped: already minted for this
                    ticket (the idempotency key), or not a blob in the commit (a deletion).
          errors    ["<what>: <why>"] — a stamp that was attempted and FAILED. Named, never raised.
          stamped   False when the whole hook was skipped or could not run (no api seam, no commit,
                    or the idempotency read failed); True when the ticket's rows are up to date.

        WHY IT CANNOT RAISE (policy 10's NEVER FATAL). This runs inside commit_deliverable, whose
        raise ends the round — so an exception here would let a registry outage destroy real, merged
        work. The stamp is instrumentation; instrumentation that can break the pipeline is worse than
        none. Every failure mode is therefore caught and returned as DATA for commit_note() to put on
        the append-only journal, where a human can see the gap. Two layers, on purpose: per file (one
        unreachable route must not cost the other files their rows) and around the whole hook (a
        surprise from any other line is still not the round's problem).

        WHY THE IDEMPOTENCY READ COMES FIRST (policy 10's IDEMPOTENT). The key is
        (ticket_id, forge_sha, name) and NOTHING IN THE DB ENFORCES IT: 0014's artifact.record is a
        bare INSERT and ticket_artifacts carries no unique index. So "record once" can only be honored
        by reading the ticket's existing rows through `artifact.list` and not re-inserting what is
        there. If that READ fails, this refuses to stamp AT ALL (stamped=False, the reason in
        `errors`) rather than insert blind: a duplicate row is permanent — it lands in an append-only
        registry and misreports one artifact as two — while a missing stamp is a gap the next commit
        closes. In practice the read and the write are the same surface, so a failed read means the
        write was never going to land either.

        WHY `name` IS IN THE KEY, AND WHY LEAVING IT OUT WAS A BUG. Two files with IDENTICAL BYTES
        share one blob sha — a package's empty `__init__.py` files are the everyday case for the
        packages policy 8 commits, and git stores both as e69de29bb2d1d6434b8b29ae775ad8c2e48c5391. A
        key of (ticket_id, forge_sha) alone cannot tell those two apart from ONE file stamped twice,
        so it drops the second as "already stamped" and its PATH never reaches the registry at all.
        That is the disease #457 exists to cure, reintroduced one layer down: `name` is the
        repo-relative path a human greps, so a file with no row is a file no one can find, however
        faithfully some OTHER file's row records its bytes. The dedupe rule is about ROUNDS —
        "re-committing the same bytes" — and (ticket_id, forge_sha, name) satisfies that exactly: a
        re-commit of the same path mints nothing, while every distinct path that landed gets its row.
        Per policy 10: EVERY file in the commit's SCOPE is stamped.
        """
        out = {"recorded": [], "skipped": [], "errors": [], "stamped": False}
        if self.api is None or not cm.get("committed"):
            return out                       # the git layer alone, or nothing landed: nothing to stamp
        try:
            try:
                rws = self.api(ARTIFACT_LIST_ROUTE, {"ticket_id": int(tid)}, "GET").get("rows", [])
                seen = {((r.get("forge_sha") or "").lower(), r.get("name")) for r in rws}
            except Exception as e:  # noqa: BLE001 — cannot prove idempotency, so do not write
                out["errors"].append("%s (the idempotency read) failed, so NOTHING was stamped rather "
                                     "than risk a duplicate row: %s" % (ARTIFACT_LIST_ROUTE, e))
                return out
            version = (cm.get("sha") or "")[:10]        # the short commit sha the file landed in
            for path in cm.get("files", []):
                sha = self.blob_sha(cm["sha"], path, cwd=self.worktree_of(tid))
                if not sha:
                    out["skipped"].append("%s: no blob in %s (a deletion is not an artifact)"
                                          % (path, version))
                    continue
                if (sha.lower(), path) in seen:
                    out["skipped"].append("%s: already stamped for #%s at forge_sha %s (this PATH "
                                          "already landed these exact bytes — not a new artifact)"
                                          % (path, tid, sha[:10]))
                    continue
                row = {"ticket_id": int(tid), "name": path, "version": version,
                       "forge_sha": sha, "kind": ARTIFACT_KIND}
                try:
                    self.api(ARTIFACT_RECORD_ROUTE, row)
                except Exception as e:  # noqa: BLE001 — one file's failure is not the others' problem
                    out["errors"].append("%s for %s (forge_sha %s) failed: %s"
                                         % (ARTIFACT_RECORD_ROUTE, path, sha[:10], e))
                    continue
                seen.add((sha.lower(), path))     # this PATH's bytes are now on the record
                out["recorded"].append(row)
            out["stamped"] = True
        except Exception as e:  # noqa: BLE001 — the outer net: the stamp NEVER costs the round
            out["errors"].append("the artifact stamp failed entirely (the commit stands): %s" % e)
        return out

    # ── i2: merge the branch into the base (--no-ff); a conflict is an OUTCOME, not a crash ──
    def ahead_of(self, tid, base):
        """How many commits `ticket/<id>` has that `base` does not (`git rev-list <base>..<br>`).

        ZERO means there is nothing to merge: either the deliverable was never committed on the
        branch (the worker reproduced what base already had, so commit_deliverable made no commit),
        or a prior run already merged it. Either way the branch has no work to land.
        """
        return int(self.git("rev-list", "--count", "%s..%s" % (base, self.branch_of(tid))).strip() or 0)

    def is_merge_commit(self, rev="HEAD", cwd=None):
        """True if `rev` has 2+ parents — i.e. it IS a merge commit (`--no-ff`'s whole point)."""
        return len(self.git("rev-list", "--parents", "-n", "1", rev, cwd=cwd).split()) >= 3

    def merge_to_base(self, tid, base, message):
        """Merge ticket/<id> into `base` with an explicit merge commit. ok=True ONLY if a real merge
        commit was created — never on git's exit code alone (see the module docstring, policy 3:
        merging an empty branch prints "Already up to date" and exits 0 while moving nothing)."""
        br = self.branch_of(tid)
        with self.lock():
            cur = self.current_branch()
            if cur != base:
                return {"ok": False, "reason": "the base tree %s is on %r, not the base branch %r"
                                               % (self.root, cur, base)}
            dirty = self.tracked_dirty()
            if dirty:
                return {"ok": False, "reason": "the base tree has uncommitted tracked changes (#213: "
                                               "never merge into a drifted tree): %s"
                                               % ", ".join(dirty[:5])}
            if not self.branch_exists(br):
                return {"ok": False, "reason": "branch %s does not exist" % br}
            # BEFORE merging: an empty branch is a refusal, not a merge. Checked inside the lock, so
            # a parallel pair cannot move `base` between this count and the merge.
            ahead = self.ahead_of(tid, base)
            if ahead == 0:
                return {"ok": False, "empty": True, "ahead": 0,
                        "reason": "branch %s has NO commits that %s lacks (git rev-list %s..%s is empty) — "
                                  "nothing to merge. The deliverable was never committed on the branch "
                                  "(the worker may have reproduced what %s already had), or a prior run "
                                  "already merged it. Branch %s kept, ticket stays open."
                                  % (br, base, base, br, base, br)}
            before = self.head()
            ok, out = self.git_ok("merge", "--no-ff", "-m", message, br)
            if not ok:
                self.git_ok("merge", "--abort")   # leave the base exactly as it was
                return {"ok": False, "conflict": True, "reason": "merge conflict — branch %s kept, "
                                                                 "ticket stays open" % br, "detail": out[-400:]}
            # AFTER merging: trust the post-state, not the exit code. Only a NEW merge commit on the
            # base proves ticket/<id> landed; anything else is refused and nothing is claimed.
            # (HEAD-moved is the load-bearing check; the message match is belt-and-braces, and covers
            # both spellings — git says "Already up to date." since 2.30, "Already up-to-date." before.)
            after, low = self.head(), out.lower()
            already = "already up to date" in low or "already up-to-date" in low
            if after == before or already or not self.is_merge_commit():
                return {"ok": False, "no_merge_commit": True, "ahead": ahead,
                        "reason": "git merge exited 0 but produced NO merge commit on %s (%s) — refusing "
                                  "to record a merge that did not happen. Branch %s kept, ticket stays open."
                                  % (base, (out.splitlines() or ["no output"])[0], br), "detail": out[-400:]}
            return {"ok": True, "sha": after, "was": before, "branch": br, "ahead": ahead}

    # ── i2: reap the ephemeral worktree; the BRANCH is kept as the ticket's trace ──
    def reap_worktree(self, tid):
        path = self.worktree_of(tid)
        with self.lock():
            if os.path.exists(path):
                # --force: the mandate forbids strays, and any that exist were journaled at commit
                # time; without it a worktree holding an untracked file refuses to go.
                self.git_ok("worktree", "remove", "--force", path)
            self.git_ok("worktree", "prune")
            return not os.path.exists(path)


def forge_for(root=None):
    # api=rest binds the mint hook to the real governed surface (#457, policy 10) — the ONE place
    # production gets a stamping Forge. A bare Forge(root) is the git layer with no registry to reach.
    cfg = REGISTRY.get("branch_per_ticket") or {}
    return Forge(root or ROOT, worktrees=cfg.get("worktrees"),
                 package_marker=cfg.get("package_marker") or PACKAGE_MARKER, api=rest)


# ── the pair's birth prompts ───────────────────────────────────────────────────────────────────────
GOVERNANCE = """
GOVERNANCE: ticket #%(tid)s authorizes you — work on nothing else. History is append-only: never
delete or rewrite anything that exists; produce, don't erase. You are registered as %(agent)s and
every action is on the record. Print your final answer as the LAST line of output: one JSON object,
nothing after it."""

WORKSPACE = """
WORKSPACE: your working directory is a private git WORKTREE of the repo, checked out on this
ticket's own branch %(branch)s. Paths are repo-relative and resolve here; the base branch is
untouched. Do NOT run git: the harness commits your deliverable to %(branch)s after you report done.
"""

WORKER_PROMPT = """You are %(agent)s, the %(role)s — the worker of a %(kind)s pair on ticket #%(tid)s.

TICKET: %(title)s
%(body)s

Deliverable: %(worker_scope)s
%(worker_focus)s Your counterpart will adversarially audit this with no access to your
reasoning, so the artifact must stand alone.
%(workspace)s%(playbook)s%(findings)s
When the deliverable is written, print as your LAST line:
{"done": true, "ref": "%(deliverable)s", "note": "<one line on what you produced>"}
""" + GOVERNANCE

AUDITOR_PROMPT = """You are %(agent)s, the %(role)s — the adversary of a %(kind)s pair on ticket #%(tid)s.

TICKET: %(title)s
%(body)s

The worker produced %(auditor_scope)s You did NOT see the worker's reasoning — judge the artifact
alone: no context, no charity. %(audit_focus)s Nitpicks are not findings.
%(workspace)s
Print as your LAST line:
{"verdict": "pass", "findings": []}   or   {"verdict": "fail", "findings": ["<finding>", ...]}
""" + GOVERNANCE


# The two prompt slots that must agree with what commit_deliverable() actually stages (#409, policy
# 8). A prompt is a promise: telling a forge worker to "touch nothing else" while the harness commits
# its whole package would be a promise the harness breaks, and telling it the opposite while the
# harness commits one file is how #401's pyproject.toml was written and then reaped. Both slots are
# derived from the same package root the commit uses, so the three can never drift apart.
def worker_scope(deliverable, pkg):
    """The worker's deliverable line: what to write, and what the harness will commit."""
    if not pkg:
        return "write it to %s (create or overwrite that file; touch nothing else)." % deliverable
    return ("write it to %s. That file is one module of the PACKAGE %s/, and the harness commits the "
            "WHOLE of %s/ — so build the package there in full (its pyproject.toml, its config, its "
            "console entry points, any submodules) and every part of it lands together. Create "
            "nothing OUTSIDE %s/: anything you leave elsewhere is a stray, is NOT committed, and "
            "does not survive. Build artifacts (%s.egg-info/, build/, dist/, __pycache__) are not "
            "committed either — they are regenerated by any install, so do not hand-write them."
            % (deliverable, pkg, pkg, pkg, pkg.rsplit("/", 1)[-1]))


def auditor_scope(deliverable, pkg):
    """The adversary's target line: the artifact it must judge is the package, not just the module."""
    if not pkg:
        return "%s." % deliverable
    return ("the PACKAGE %s/, whose module %s is the ticket's named deliverable. The whole package "
            "is the artifact and the whole package is what gets committed — judge it as one."
            % (pkg, deliverable))


def commit_note(rnd, deliverable, cm):
    """The journal line for one round's commit. It names the fileset that ACTUALLY landed (#409).

    Before #409 this line could only name the --deliverable, and every other file of a forge package
    was journaled as an UNCOMMITTED stray — which was, permanently and append-only, the true record
    of a package that never landed installable. #401 reads exactly that way. Now a package commit
    names its root and its every file, and `strays` is back to meaning what it says: work left
    outside the commit's scope that will not survive the reap.

    It also names what the MINT HOOK stamped (#457, policy 10), and — because the stamp may never
    raise — what it FAILED to stamp. An instrumentation failure that is invisible is indistinguishable
    from an instrumentation failure that never happened, so the errors go on the record where a human
    reads them; the journal is the only place a swallowed exception can still be seen.
    """
    if not cm["committed"]:
        what = "no change to commit for %s" % deliverable
    elif cm["package"]:
        what = ("committed the PACKAGE %s/ — %d file(s): %s"
                % (cm["package"], len(cm["files"]), ", ".join(cm["files"])))
    else:
        what = "committed %s" % deliverable
    note = "round %d: %s on %s @ %s" % (rnd, what, cm["branch"], cm["sha"][:10])
    art = cm.get("artifacts") or {}
    if art.get("recorded"):
        note += ("; STAMPED %d artifact(s) into the registry (%s, kind %s): %s"
                 % (len(art["recorded"]), ARTIFACT_RECORD_ROUTE, ARTIFACT_KIND,
                    ", ".join("%s @ %s" % (r["name"], r["forge_sha"][:10]) for r in art["recorded"][:5])))
    if art.get("skipped"):
        note += "; artifacts NOT re-stamped: " + ", ".join(art["skipped"][:3])
    if art.get("errors"):
        note += ("; the artifact stamp FAILED (the commit above still stands — the stamp is "
                 "instrumentation and never fails a round, #457): " + "; ".join(art["errors"][:3]))
    if cm["skipped"]:
        note += ("; build artifacts under the package NOT committed (any install regenerates them; "
                 "committing them would drift the base tree, #213): " + ", ".join(cm["skipped"][:5]))
    if cm["strays"]:
        note += ("; UNCOMMITTED strays left in the worktree (the mandate forbids them; they will not "
                 "survive the reap): " + ", ".join(cm["strays"][:5]))
    return note


# per-kind focus: what the worker optimizes for, how the adversary attacks, and each side's tools.
# build/bug pairs EXECUTE (a tester that cannot run code is a book reviewer, not an adversary).
FOCUS = {
    "documentation": {
        "worker_focus": "Ground every claim in the actual repository — read the real code you "
                        "describe; never document intentions as behavior.",
        "audit_focus": "Read as a hostile newcomer and verify every claim against the actual "
                       "repository (read the migrations/routes/tools it cites). Findings are: claims "
                       "that don't match the code, steps that can't be executed as written, terms "
                       "undefined at first use, anything a newcomer must read twice.",
        "worker_tools": "Read,Grep,Glob,Write,Edit",
        "auditor_tools": "Read,Grep,Glob",
    },
    "build": {
        "worker_focus": "Produce working code that meets the ticket's required behavior exactly; "
                        "mirror the repo's established patterns; RUN your own work before reporting "
                        "done (python3 and the repo php at tooling/congruencey-harness/php/php are allowed).",
        "audit_focus": "Assume the code is broken and try to PROVE it: execute its documented "
                       "invocations (python3 and the repo php at tooling/congruencey-harness/php/php "
                       "are allowed), feed edge cases, and compare ACTUAL behavior to the ticket's "
                       "required behavior, point by point. Findings are: requirements not met, "
                       "crashes, wrong output, side effects the ticket forbids.",
        "worker_tools": "Read,Grep,Glob,Write,Edit,Bash(python3:*),Bash(tooling/congruencey-harness/php/php:*)",
        "auditor_tools": "Read,Grep,Glob,Bash(python3:*),Bash(tooling/congruencey-harness/php/php:*)",
    },
}
FOCUS["bug"] = FOCUS["build"]


def verdict_of(stdout):
    """An agent's answer: the LAST line of its output that parses as a JSON object.

    Raises NoVerdict when there is none — an agent that printed nothing readable has not answered,
    and there is no answer to invent for it. Split out of spawn_claude so --selftest can drive the
    real parser directly, with no subprocess and no agent.
    """
    for line in reversed((stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    raise NoVerdict("no JSON verdict on the agent's last line; tail: %r" % ((stdout or "")[-200:],))


def worker_done(res):
    """The worker's own report, validated: it must say done=true.

    A worker that reports done=false — or reports something that is not an object at all — has
    produced nothing the harness may commit or ask an adversary to judge. That is a FAILED ROUND
    (NoVerdict), which the loop absorbs; it is not a harness fault, so it never crashes the pair.
    """
    if not isinstance(res, dict) or not res.get("done"):
        raise NoVerdict("worker did not report done=true: %.200r" % (res,))
    return res


def spawn_claude(prompt, allowed_tools, timeout, cwd=None):
    """One fresh-context agent run, IN the ticket's worktree. Fresh spawn = clean memory; the db
    keeps the durable trail.

    Every way a spawn can fail to ANSWER — it overran its budget, it exited non-zero, it printed no
    readable JSON — raises NoVerdict. That is a subclass of Unexpected, so any caller that does not
    handle it is unaffected (bug report + exit 2, exactly as before); the worker's call site handles
    it and fails the round instead (#439).
    """
    try:
        r = subprocess.run(["claude", "-p", prompt, "--allowedTools", allowed_tools],
                           cwd=cwd or ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # a spawn overrunning its budget is a ROUND OUTCOME, not a harness crash — and now it is one
        raise NoVerdict("agent spawn exceeded its %ss budget (raise --timeout for heavier tickets)" % timeout)
    if r.returncode != 0:
        raise NoVerdict("claude exited %s: %s" % (r.returncode, (r.stderr or r.stdout).strip()[-300:]))
    return verdict_of(r.stdout)


DISPATCH_RULES = """
THE QUEUE above lists open/requested tickets with their active_stops count. For EACH ticket decide ONE action:
- "run": actionable NOW by a single pair producing ONE deliverable file. Supply "kind" (choose from
  the pair/solo kinds if the ticket is unkinded) and "deliverable" (repo-relative path — inspect the
  repository to choose the right home; mirror the existing layout).
- "skip": not actionable — control tickets (kind stop/start), tickets with active_stops > 0, work
  that needs a spec or a graft first, or anything too big for one deliverable. Supply "reason".
  Be conservative: prefer skip-with-reason over guessing.
- "stop": a job that should NOT proceed at all. Supply "reason" — a stop ticket will be aimed at it.
You route; you never author work product. Print as your LAST line ONLY this JSON, nothing after:
{"plan": [{"ticket": <id>, "action": "run|skip|stop", "kind": "<kind-or-empty>", "deliverable": "<path-or-empty>", "reason": "<why>"}]}
"""


def child_cmd(tid, deliverable, a):
    """The `--ticket` child a dispatched "run" becomes: its own process, its own branch+worktree."""
    cmd = [sys.executable, os.path.abspath(__file__), "--ticket", str(tid),
           "--deliverable", deliverable, "--rounds", str(a.rounds), "--timeout", str(a.timeout),
           "--package-commit", a.package_commit]     # the child decides nothing the parent didn't
    if a.base:
        cmd += ["--base", a.base]
    if a.keep_worktree:
        cmd += ["--keep-worktree"]
    return cmd


def do_dispatch(a):
    """--dispatch: dispatch-01 (its REGISTERED prompt, read back from the agents table) reads the
    queue and decides; the harness executes each decision through the governed routes.

    i3 — PARALLEL PAIRS: each "run" becomes a child `--ticket` process, and up to --parallel of them
    are in flight at once. Each child opens its OWN branch+worktree, so they never contend; the only
    shared state (.git refs, the base tree at merge) is flock-serialized inside Forge.
    """
    reg = rows("agent.prompt", {"agent_id": "dispatch-01"})
    if not reg:
        raise Unexpected("dispatch-01 is not registered — agent.register it first")
    queue = rows("ticket.queue", {})
    if not queue:
        print("== dispatch == queue is empty; nothing to route")
        return 0
    for t in queue:
        st = rows("ticket.stops", {"ticket_id": t["id"]})
        t["active_stops"] = st[0].get("active_stops", 0) if st else 0
    prompt = (reg[0]["prompt"] + "\n\nTHE QUEUE:\n" + json.dumps(queue, indent=1) + "\n" + DISPATCH_RULES)
    res = step("dispatch: plan", spawn_claude, prompt, "Read,Grep,Glob", a.timeout)
    plan = res.get("plan", [])
    if not plan:
        raise Unexpected("dispatch-01 returned no plan")

    results, runs = [], []
    for d in plan[: a.dispatch]:
        tid, act = d.get("ticket"), d.get("action")
        rest("ticket.progress", {"ticket_id": tid, "agent_id": "dispatch-01",
                                 "note": "dispatch: %s — %s" % (act, d.get("reason") or d.get("deliverable") or "")})
        if act == "run" and d.get("deliverable"):
            if d.get("kind"):
                try:
                    rest("ticket.kind", {"id": tid, "kind": d["kind"]})   # set-once; refused if kinded
                except Exception:  # noqa: BLE001
                    pass
            runs.append((tid, d["deliverable"]))
        elif act == "stop":
            out = rest("ticket.create", {"component": "congruency", "severity": "normal", "patch": "",
                                         "title": "STOP: #%s (dispatched)" % tid, "body": d.get("reason", "")})
            sid = int(out.get("rowid", 0))
            rest("ticket.kind", {"id": sid, "kind": "stop"})
            rest("edge.record", {"parent_id": sid, "child_id": tid, "kind": "stops"})
            results.append((tid, "stopped by #%s" % sid))
        else:
            results.append((tid, "skip — %s" % (d.get("reason") or "")))

    # run the pairs, up to --parallel at a time; each child owns its own branch + worktree
    lanes, pending = [], list(runs)
    if runs:
        print("== dispatch == running %d pair(s), up to %d at a time (branch+worktree each)"
              % (len(runs), max(1, a.parallel)))
    while pending or lanes:
        while pending and len(lanes) < max(1, a.parallel):
            tid, deliv = pending.pop(0)
            p = subprocess.Popen(child_cmd(tid, deliv, a), cwd=ROOT)
            lanes.append((tid, p))
            print("   -> #%s dispatched on branch ticket/%s (pid %s)" % (tid, tid, p.pid))
        for tid, p in list(lanes):
            if p.poll() is not None:
                lanes.remove((tid, p))
                results.append((tid, "run -> exit %s" % p.returncode))
        if lanes:
            time.sleep(1)
    for tid, what in results:
        print("== dispatched == #%s: %s" % (tid, what))
    return 0


# ── governance: the pair's db writes, and the ORDER the db enforces on them (#439) ────────────────
GOV_ACTIVE_RULE = "a ticket authorizes an agent: assign one (ticket.assign) before it can go ACTIVE"


class Gov:
    """The pair's two governance acts — enlisting an agent, and flipping the ticket ACTIVE — in one
    place, because their ORDER is a rule the database enforces and a harness cannot merely remember.

    THE RULE. `tg_tickets_active_needs_agent` (migrations/0029_ticket_authorization.sql) aborts any
    UPDATE that sets a ticket ACTIVE while no row in `ticket_agents` names it:

        "a ticket authorizes an agent: assign one (ticket.assign) before it can go ACTIVE"

    The abort is not advisory. SQLite raises SQLITE_CONSTRAINT_TRIGGER, PDO reports SQLSTATE 23000,
    and rest.php turns that into a 500 — so an out-of-order harness does not degrade, it dies, and it
    dies on EVERY new dispatch at "pair (round 1)". Only tickets already ACTIVE from an earlier run
    survive, which is what made the breakage look survivable while the pipeline's core was dead.

    THAT IS TICKET #279'S REGRESSION, and it is the reason this class exists. #279 was right that
    registration must be LAZY (see enlist) and wrong about one line: it moved every ticket.assign to
    spawn time but left `process_status -> ACTIVE` where it had always been, ahead of them all. Its
    selftest passed 129/129 because nothing in it ever met the live rule. So here the order is not a
    convention to be re-broken by the next edit — it is structure:

      * enlist()   registers an agent AND authorizes it on the ticket, together, always.
      * activate() REFUSES to run until enlist() has (see the guard below), and runs once.

    A caller therefore cannot express #279's order without tripping the guard, and --selftest drives
    THIS code against the REAL trigger, loaded from the real migration (see _st_gov()).
    """

    def __init__(self, tid, api=None):
        self.tid = int(tid)
        self.api = api or rest        # the seam: --selftest binds a throwaway db carrying the real rule
        self.assigned = []            # (agent_id, role) in authorization order — activate()'s precondition
        self.activated = False

    def enlist(self, agent, role, prompt):
        """Register ONE agent and authorize it on the ticket, LAZILY — immediately before it runs.

        Lazy is not an optimization, it is the only order that can work for a RE-ASKED agent: a
        round-2 worker exists *because* round 1's was rejected, so neither its id nor its birth
        prompt is knowable before that rejection. Registering the pair up front could only ever
        record agents that do not exist yet, with prompts they will not be born with.

        `prompt` is the exact string the agent is about to be spawned on — rendered once by the
        caller and passed to both, so the registered birth prompt and the real one cannot drift.

        register-then-assign, in that order: tg_ticket_agents_registered (0029) refuses to authorize
        an agent the registry has never heard of.
        """
        self.api("agent.register", {"agent_id": agent, "parent": "pair_loop", "prompt": prompt,
                                    "tools": json.dumps(["claude -p"])})
        self.api("ticket.assign", {"ticket_id": self.tid, "agent_id": agent, "role": role})
        self.assigned.append((agent, role))
        return agent

    def activate(self):
        """Flip the ticket ACTIVE — AFTER an enlist(), and only once. Returns True if this call set
        it, False if it was already set (rounds 2+ — ACTIVE is a round-1 act).

        The guard is a tripwire, not decoration. If a later edit re-introduces #279's order, this
        raises HERE, named and explained, instead of shipping a 500 that kills all dispatch.
        """
        if self.activated:
            return False
        if not self.assigned:
            raise Unexpected(
                "refusing process_status->ACTIVE on #%d before any ticket.assign — the db would "
                "abort it (SQLSTATE 23000: %s) and take down the dispatch. enlist() an agent first. "
                "This is ticket #279's regression, guarded at its source." % (self.tid, GOV_ACTIVE_RULE))
        self.api("process_status", {"id": self.tid, "status": "ACTIVE"})
        self.activated = True
        return True


def open_round(gov, worker, role, prompt, branch):
    """Open one round: bring the WORKER into existence, and only then take the ticket ACTIVE.

    Those two lines are the whole of #439, which is why they are a function instead of four lines
    inlined in main(): --selftest drives THIS code, so the order it proves is the order main() really
    runs. Inlined in a closure, the call site could be reordered back into #279 with every check
    still green — and a green selftest over a dead pipeline is precisely the failure being redone
    here. Order-dependent code that no test can reach is how the last attempt shipped.

    Returns the step's summary line. ACTIVE is a round-1 act: from round 2 on, activate() no-ops.
    """
    gov.enlist(worker, role, prompt)                 # lazy: this agent's id + prompt exist only now
    return {"worker": worker, "branch": branch,
            "ACTIVE": "set (after %s's assign)" % worker if gov.activate() else "already set"}


def forge_agent(tid):
    """Register `forge-t<id>`: the ticket's git steward, which holds the git pen and signs the
    branch/commit/merge/reap events on the journal.

    REGISTERED but deliberately NOT ticket.assign'd — exactly how dispatch-01 journals onto tickets
    it routes (do_dispatch below) without being authorized on them. The reason is governance, not
    convenience: tg_tickets_pair_completion (migration 0029) refuses DONE on a pair ticket unless
    ticket_agents holds two DISTINCT agents in two DISTINCT roles, which is the db's own backstop
    against a harness settling a ticket that never ran an adversary. Assigning a third, always-
    present agent would satisfy that check with forge+worker alone and quietly hollow the backstop
    out, so the forge stays off ticket_agents and the pair remains the only way to DONE.
    """
    fid = "forge-t%d" % tid
    rest("agent.register", {"agent_id": fid, "parent": "pair_loop",
                            "tools": json.dumps(["git branch", "git worktree", "git commit", "git merge"]),
                            "prompt": "You are %s, the git steward of ticket #%d. Your one duty: hold this "
                                      "ticket's branch (ticket/%d) and its worktree — open it, commit the "
                                      "pair's deliverable onto it, merge it to the base on settle, reap the "
                                      "worktree — and record each act on the append-only journal. You keep "
                                      "the branch; you never author or judge work product." % (fid, tid, tid)})
    return fid


def harvest(tid, history, passed, final_note):
    """Distill the settled ticket into a LESSON event — memory an agent may keep is memory it filed.
    Mechanical (no spawn): the lesson is composed from what the record already proves happened."""
    scribe = "scribe-t%d" % tid
    rest("agent.register", {"agent_id": scribe, "parent": "pair_loop", "tools": json.dumps(["ticket.lesson"]),
                            "prompt": "You are %s, the scribe of ticket #%d. Your one duty: distill the "
                                      "settled ticket's journal into a lesson future workers can apply — "
                                      "what the adversary caught, what resolved it. You record; you never "
                                      "author or judge work product." % (scribe, tid)})
    rest("ticket.assign", {"ticket_id": tid, "agent_id": scribe, "role": "scribe"})
    if passed and len(history) == 1:
        note = "clean pass in 1 round — the adversary found nothing. Produced: %s" % (final_note or "(see manifest)")
    elif passed:
        forced = "; ".join("round %d findings: %s" % (h["round"], " | ".join(h["findings"])) for h in history if h.get("findings"))
        note = ("passed in %d rounds. Rework forced by the adversary — %s. Resolution: %s"
                % (len(history), forced, final_note or "(see manifest)"))
    else:
        last = history[-1].get("findings", []) if history else []
        note = "UNRESOLVED after %d round(s). Standing findings: %s" % (len(history), " | ".join(last) or "(none recorded)")
    rest("ticket.lesson", {"ticket_id": tid, "agent_id": scribe, "note": note})
    print("== harvest == lesson filed on #%d by %s" % (tid, scribe))


def harvest_settled(tid):
    """--harvest N: retro-harvest an ALREADY-settled ticket from its journal (no spawns)."""
    history, final_note, passed = [], "", False
    for ev in rows("ticket.journal", {"ticket_id": tid}):
        note = ev.get("note") or ""
        if ev.get("event") == "progress" and "verdict: fail" in note:
            fx = note.split("findings:", 1)[1].strip() if "findings:" in note else note
            history.append({"round": len(history) + 1, "findings": [f.strip() for f in fx.split(";") if f.strip()]})
        elif ev.get("event") == "progress" and "verdict: pass" in note:
            passed = True
            history.append({"round": len(history) + 1, "findings": []})
        elif ev.get("event") == "progress" and ": produced" in note:
            final_note = note
    if not history:
        raise Unexpected("ticket #%s journal has no pair verdicts to harvest" % tid)
    harvest(tid, history, passed, final_note)


def step(name, fn, *a, tolerate=(), **kw):
    """Run one named stage of the loop, timed and printed.

    `tolerate` names exception types that are a defined OUTCOME this caller handles, not a harness
    fault. They are printed and re-raised (the caller decides what they mean) but NOT bug-reported:
    a Variant-A bug report asserts "this should never happen", and a caller that handles the case has
    already said that it can. Everything else keeps the old behavior exactly — report, print, re-raise.
    """
    t0 = time.time()
    try:
        out = fn(*a, **kw)
        print("== %s ==\n   ok (%d ms) %s" % (name, (time.time() - t0) * 1000, out if out is not None else ""))
        return out
    except tolerate as e:  # noqa: BLE001  — a round outcome the caller absorbs; not a bug
        print("== %s ==\n   no result: %s" % (name, e))
        raise
    except Exception as e:  # noqa: BLE001
        bug_report(name, e, "python3 pair_loop.py (step: %s)" % name, e)
        print("== %s ==\n   FAILED: %s" % (name, e))
        raise


# ── --selftest: prove the git layer end-to-end in a THROWAWAY repo (no agents, no server, no network) ─
def _st_git(repo, *a):
    return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)


def _st_repo(base):
    """A throwaway repo that looks enough like this one: a registry.json and a committed file."""
    repo = os.path.join(base, "repo")
    os.makedirs(repo)
    _st_git(repo, "init", "--quiet", "-b", "main", ".")
    _st_git(repo, "config", "user.email", "pair_loop@selftest")
    _st_git(repo, "config", "user.name", "pair_loop selftest")
    open(os.path.join(repo, "registry.json"), "w").write('{"schema": 1, "package": "selftest"}\n')
    os.makedirs(os.path.join(repo, "docs"))
    open(os.path.join(repo, "docs", "seed.md"), "w").write("seed\n")
    _st_git(repo, "add", "-A")
    _st_git(repo, "commit", "--quiet", "-m", "init")
    return repo


# The fixture package the #409 checks build, laid out the way a real forge unit is: the module sits
# DIRECTLY in the package root (#401's deliverable was forge2/artifact_tree_gen/add.py) with its
# pyproject.toml beside it, so that root is both the project root and the thing `pip install -e .`
# is run from. Hence py-modules for the flat module and packages for the submodule package.
FORGE_PYPROJECT = """[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "%(name)s"
version = "0.1.0"
description = "selftest forge package (#409 fixture)"

[project.scripts]
%(name)s = "add:main"

[tool.setuptools]
py-modules = ["add"]
packages = ["sub"]
"""


def _st_forge_package(wt, pkg, name):
    """Write what a forge unit's worker actually leaves in its worktree: the --deliverable MODULE,
    plus everything else the package needs to be installable (#409). Returns the fileset it wrote.

    Every part beyond add.py is one the ticket names — pyproject.toml, config, entry points,
    submodules — and every one of them is what #401 lost: a package whose pyproject.toml is not
    committed is not a package, and a check that only proved add.py lands would prove nothing new.

    TWO EMPTY `__init__.py` FILES, ON PURPOSE (#457). A real package carries one per package
    directory and they are EMPTY, so git stores both as the SAME blob
    (e69de29bb2d1d6434b8b29ae775ad8c2e48c5391) — two distinct paths, one content address. That is the
    everyday shape, and it is the one shape that can break the mint hook's dedupe: a key that ignores
    `name` reads the second file as the first one stamped twice and drops its row, so the file lands
    in git and is absent from the registry. This fixture wrote exactly ONE empty file before #457's
    round 2, which is precisely why the EVERY-FILE-IN-SCOPE check below could not see that defect. A
    fixture with no collision in it cannot prove a collision is handled.

    The root `__init__.py` is deliberately NOT declared in FORGE_PYPROJECT, and needs no declaration:
    naming py-modules AND packages explicitly turns setuptools' auto-discovery OFF, so the file is
    simply not installed and cannot disturb the build (--install-check proves the package still
    installs with it present). It is a file the worker LEFT — which is what this fixture reproduces —
    and therefore a file the package commit must stamp.
    """
    d = os.path.join(wt, pkg)
    os.makedirs(os.path.join(d, "sub"), exist_ok=True)
    files = {
        "add.py": "from sub.helper import bump\n\n\ndef add(a, b):\n    return bump(a + b, 0)\n\n\n"
                  "def main():\n    print(add(2, 3))\n",
        "pyproject.toml": FORGE_PYPROJECT % {"name": name},
        "config.json": '{"schema": 1, "offset": 0}\n',
        "__init__.py": "",
        "sub/__init__.py": "",
        "sub/helper.py": "def bump(v, by):\n    return v + by\n",
    }
    for rel, text in files.items():
        open(os.path.join(d, rel), "w").write(text)
    return sorted("%s/%s" % (pkg, r) for r in files)


def install_check(base_dir, pkg_dir):
    """`pip install -e .` on a package, in a THROWAWAY venv — #409's acceptance criterion, run
    against the tree the selftest actually merged. Returns (status, detail) with status one of:

      "PASS"  pip installed it AND the installed package imports and runs from the venv.
      "FAIL"  pip rejected the package, or it installed but could not be imported. A real defect.
      "SKIP"  the fixture could not be built: no venv, or pip could not obtain the PEP 517 build
              backend the pyproject.toml names (which needs the network — see --install-check).
              An unreachable index is a fact about this host, never about the package, so it must
              not be reported as a failure of the package.
    """
    venv = os.path.join(base_dir, "install-check-venv")
    r = subprocess.run([sys.executable, "-m", "venv", venv], capture_output=True, text=True)
    if r.returncode != 0:
        return "SKIP", "no venv available: %s" % (r.stderr or r.stdout).strip()[-160:]
    py = os.path.join(venv, "bin", "python")
    if not os.path.isfile(py):
        py = os.path.join(venv, "Scripts", "python.exe")
    if not os.path.isfile(py):
        return "SKIP", "venv built no interpreter at %s" % venv
    env = dict(os.environ, PIP_DISABLE_PIP_VERSION_CHECK="1")
    try:
        r = subprocess.run([py, "-m", "pip", "install", "-e", ".", "-q"], cwd=pkg_dir,
                           capture_output=True, text=True, env=env, timeout=300)
    except subprocess.TimeoutExpired:
        return "SKIP", "pip did not finish in 300s (a slow or absent network)"
    out = ((r.stderr or "") + (r.stdout or "")).strip()
    if r.returncode != 0:
        # Distinguish "the package is broken" from "this host could not fetch a build backend".
        low = out.lower()
        if any(s in low for s in ("no matching distribution found", "could not find a version",
                                 "backendunavailable", "cannot import", "network is unreachable",
                                 "temporary failure in name resolution", "connection", "retries exceeded",
                                 "proxy", "ssl")):
            return "SKIP", "pip could not obtain the build backend (no network?): %s" % out[-200:]
        return "FAIL", "pip install -e . exited %s: %s" % (r.returncode, out[-300:])
    # Installed is not the same as usable. Import the module and its submodule from the VENV — and
    # from a cwd outside the package, so it is the install being tested and not the current
    # directory happening to hold add.py.
    r = subprocess.run([py, "-c", "from add import add; print(add(2, 3))"],
                       capture_output=True, text=True, cwd=base_dir)
    if r.returncode != 0 or r.stdout.strip() != "5":
        return "FAIL", "installed but not importable/usable: %s" % ((r.stderr or r.stdout).strip()[-250:])
    # "console entry points where applicable" is part of what a forge package must land, so the
    # pyproject declares one and this proves the install actually created it.
    script = os.path.join(os.path.dirname(py), "selftest_forge")
    if not (os.path.isfile(script) or os.path.isfile(script + ".exe")):
        return "FAIL", "installed but its console entry point was not created at %s" % script
    return "PASS", "pip install -e . clean; `from add import add; add(2,3)` -> 5; entry point created"


# ── --selftest: the governance ORDER, against the REAL constraint (#439) ──────────────────────────
# The rule that killed #279 lives in SQL, so a selftest that re-implements it in Python proves
# nothing: a hand-written imitation passes exactly when its author believed it should, whether or not
# the real trigger agrees. #279's own selftest passed 129/129 for precisely that reason — it never met
# the rule it was breaking. So the throwaway db below is built by EXECUTING this repo's own
# migrations: the constraint the checks meet is the actual tg_tickets_active_needs_agent DDL, not a
# copy of it, and the checks drive the real Gov code against it. Still no server, no api key and no
# network — the selftest only READS migrations/*.sql (and the live db, read-only, if it is present).
GOV_MIGRATIONS = ("0002_ticket_approval.sql",       # tickets
                  "0001_agents.sql",                # agents — the registry ticket.assign requires
                  "0029_ticket_authorization.sql",  # ticket_agents + THE GOVERNANCE TRIGGERS + kinds
                  "0031_harvest_routes.sql",        # ticket.lesson — harvest() closes every run
                  "0033_assign_idempotent.sql",     # ticket.assign as it is really routed today
                  "0014_ticket_artifacts.sql")      # ticket_artifacts + artifact.record/.list (#457)

# Those four only INSERT into api_routes; on the live db some earlier migration already created it.
# This is that same CREATE, verbatim from migrations/0023_bug_catalog.sql:13 (0020/0024/0026/0027 all
# carry the identical line), so the throwaway db starts where they expect to land.
GOV_API_ROUTES_DDL = ("CREATE TABLE IF NOT EXISTS api_routes "
                      "(name TEXT PRIMARY KEY, method TEXT, sql TEXT, auth TEXT, params TEXT, meta TEXT);")

# `process_status` is the ONE route the pair calls that NO migration defines: it predates them and
# exists only as a row in the live db's api_routes. It is pinned here as read from that row — and the
# "pinned process_status SQL still matches the live db" check re-reads the live row and FAILS on
# drift, so this constant cannot quietly become a fiction the ordering checks then prove things about.
GOV_PROCESS_STATUS_SQL = "UPDATE tickets SET status=:status, updated=strftime('%s','now') WHERE id=:id"

LIVE_DB_REL = os.path.join("checkouts", "current", "state", "congruency.sqlite")


def _st_sql_eq(a, b):
    """SQL equality up to whitespace runs — the one thing sqlite reformats freely when it stores DDL."""
    return " ".join((a or "").split()) == " ".join((b or "").split())


def _st_live_db_path():
    """Where the live governance db actually is, from wherever this happens to be running.

    In the MAIN checkout it is simply ROOT/checkouts/current/state/congruency.sqlite. In a pair
    WORKTREE there is no such file at all: the db is untracked, so `git worktree add` never
    materialises it — and a selftest that only looked here would SKIP its live checks in exactly the
    place the pair loop runs. A worktree's `.git` is a FILE, not a directory, holding
    `gitdir: <main>/.git/worktrees/<name>`, so the main checkout is three directories up from that
    pointer and its db is the live one this branch was cut from.

    None when neither has it (a fresh clone, a CI box): a db that is not on this host says nothing
    about this code, so that is a SKIP and never a FAIL.
    """
    here = os.path.join(ROOT, LIVE_DB_REL)
    if os.path.isfile(here):
        return here
    dotgit = os.path.join(ROOT, ".git")
    if os.path.isfile(dotgit):                       # a worktree: a pointer file, not a directory
        try:
            line = open(dotgit).read().strip()
        except OSError:
            return None
        if line.startswith("gitdir:"):
            gitdir = os.path.abspath(line.split(":", 1)[1].strip())
            main = os.path.dirname(os.path.dirname(os.path.dirname(gitdir)))   # .../.git/worktrees/<n>
            cand = os.path.join(main, LIVE_DB_REL)
            if os.path.isfile(cand):
                return cand
    return None


def _st_live_gov():
    """The LIVE governance db, opened READ-ONLY: (connection, path), or (None, why-not).

    immutable=1, never mode=ro: the live db is in WAL journal mode, where even a read-only open
    creates `-shm`/`-wal` sidecars beside it (ticket #153's finding — the reason ticket_status.py
    opens it this way). immutable=1 promises sqlite the file will not change; it reads the same
    committed bytes and creates NOTHING. Nothing here writes, and nothing here is written to.
    """
    path = _st_live_db_path()
    if not path:
        return None, ("no live db on this host (%s is untracked, so a worktree has none of its own "
                      "and this one's main checkout has not got it either)" % LIVE_DB_REL)
    try:
        con = sqlite3.connect("file:%s?immutable=1" % path, uri=True)
        con.execute("SELECT 1 FROM api_routes LIMIT 1").fetchone()
        return con, path
    except sqlite3.Error as e:
        return None, "the live db at %s is unreadable: %s" % (path, e)


class _StGov:
    """A `rest`-shaped callable over a throwaway db carrying the REAL governance rules.

    What is stubbed here is the ROUTER and nothing else. boot/rest.php's congruency_rest_route()
    looks a name up in api_routes and executes that row's SQL with the caller's params bound; so does
    __call__, following the same three rules it does — bind only DECLARED params the SQL actually
    mentions, coerce each by its declared type, bind NULL for any the caller omitted
    (boot/rest.php:96-107) — and answering `rows` for a SELECT and `affected`/`rowid` otherwise
    (boot/rest.php:110-116). The SQL and the triggers both come from the repo's own migrations, so
    what the code under test meets is the real constraint rather than an opinion about it.

    A trigger's RAISE(ABORT) arrives here as sqlite3.IntegrityError. On the live stack that same
    abort becomes PDO's SQLSTATE 23000, which rest.php returns as an HTTP 500 with the trigger's
    message (boot/rest.php:272-275) and rest() raises out of. Either way the call RAISES at exactly
    the point the harness makes it — and the ORDER is what is under test here, not the exception's
    type, so this re-raises the Unexpected that rest() raises for a failed route.
    """

    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript(GOV_API_ROUTES_DDL)
        for m in GOV_MIGRATIONS:
            self.db.executescript(open(os.path.join(ROOT, "migrations", m)).read())
        self.db.execute("INSERT OR REPLACE INTO api_routes (name, method, sql, auth, params, meta) "
                        "VALUES ('process_status', 'POST', ?, 'token', ?, ?)",
                        (GOV_PROCESS_STATUS_SQL, '{"status":"str","id":"int"}',
                         "set a ticket's status (pinned from the live db; no migration defines it)"))
        self.calls = []          # [(route, params)] in call order — what the ORDERING checks read

    def __call__(self, route, obj=None, method=None):
        obj = obj or {}
        self.calls.append((route, dict(obj)))
        row = self.db.execute("SELECT sql, params FROM api_routes WHERE name = ?", (route,)).fetchone()
        if not row:
            raise Unexpected("route %s failed: unknown route" % route)
        sql, decl = row[0], json.loads(row[1] or "{}")
        binds = {}
        for pname, ptype in decl.items():
            if (":" + pname) not in sql:         # rest.php:98 — only bind what the SQL mentions
                continue
            val = obj.get(pname)
            if val is not None:                  # rest.php:100-105 — coerce by declared type
                t = str(ptype).lower()
                val = int(val) if t == "int" else float(val) if t in ("float", "real") else str(val)
            binds[pname] = val                   # rest.php:99 — an omitted param binds NULL
        try:
            cur = self.db.execute(sql, binds)
        except sqlite3.IntegrityError as e:      # a governance trigger fired — the live 500
            raise Unexpected("route %s failed: %s" % (route, e))
        if sql.lstrip().lower().startswith("select"):        # rest.php:110
            cols = [d[0] for d in cur.description]
            return {"route": route, "rows": [dict(zip(cols, r)) for r in cur.fetchall()]}
        return {"route": route, "affected": cur.rowcount, "rowid": cur.lastrowid}

    def routes(self):
        return [r for r, _ in self.calls]

    def ticket(self, tid, kind="build"):
        self.db.execute("INSERT INTO tickets (id, ts, updated, component, title, severity, status, body, kind) "
                        "VALUES (?, 0, 0, 'selftest', 'selftest ticket', 'normal', 'REQUESTED', 'body', ?)",
                        (int(tid), kind))
        return int(tid)

    def status(self, tid):
        r = self.db.execute("SELECT status FROM tickets WHERE id = ?", (int(tid),)).fetchone()
        return r[0] if r else None

    def registered(self):
        return [r[0] for r in self.db.execute("SELECT agent_id FROM agents ORDER BY agent_id")]

    def prompt_of(self, agent):
        r = self.db.execute("SELECT prompt FROM agents WHERE agent_id = ?", (agent,)).fetchone()
        return r[0] if r else None

    def crew(self, tid):
        return [(r[0], r[1]) for r in self.db.execute(
            "SELECT agent_id, role FROM ticket_agents WHERE ticket_id = ? ORDER BY agent_id", (int(tid),))]

    def trigger_sql(self, name):
        r = self.db.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name = ?", (name,)).fetchone()
        return r[0] if r else None

    def artifacts(self, tid=None):
        """ticket_artifacts as the DB really holds it — the mint hook's checks read THIS, not what
        stamp_artifacts() said it did (#457). A hook that returns a tidy `recorded` list while writing
        no row would pass every check that trusted its own report; only the table can refute it."""
        sql = "SELECT ticket_id, name, version, forge_sha, kind FROM ticket_artifacts"
        args = ()
        if tid is not None:
            sql, args = sql + " WHERE ticket_id = ?", (int(tid),)
        cols = ("ticket_id", "name", "version", "forge_sha", "kind")
        return [dict(zip(cols, r)) for r in self.db.execute(sql + " ORDER BY id", args)]


class _StLoopGov(_StGov):
    """_StGov plus the ONE route the round loop reads that no loaded migration defines.

    Everything else main() calls — kind.roster, ticket.progress, work.record, ticket.lesson,
    agent.register, ticket.assign, process_status — runs its REAL SQL against the real tables. Only
    `ticket.stops` is answered here: its route (0030) is a recursive walk over ticket_edges, the
    BRAKE rather than anything #439 touches, and pulling that whole subtree in would add scaffolding
    without adding proof. It answers "no active stops", which is the case the loop under test runs in.
    """

    def __call__(self, route, obj=None, method=None):
        if route == "ticket.stops":
            self.calls.append((route, dict(obj or {})))
            return {"rows": [{"active_stops": 0}]}
        return _StGov.__call__(self, route, obj, method)


def _st_loop_run(base_dir, tag, scripted, rounds=2):
    """Drive the REAL main() through one whole pair run, scripting only what each agent SAYS.

    This is what proves the round loop rather than its parts: `except NoVerdict: continue` is the
    heart of #439's no-verdict fix and lives inside main(), so nothing short of running main() ever
    executes it. Everything governed stays real — a real throwaway git repo, and an _StLoopGov whose
    routes and triggers come from the migrations. Exactly two things are replaced, both of them
    things --selftest must never really do: spawning `claude`, and reaching the network for the
    ticket row. Module globals are restored in a finally, so nothing leaks into a later check.

    `scripted` is what each successive spawn returns, in order; an Exception instance is RAISED
    instead (that is how a silent agent is expressed). Returns (exit_code, gov, prompts, repo).
    """
    repo = _st_repo(tempfile.mkdtemp(dir=base_dir))
    gov = _StLoopGov(os.path.join(base_dir, "loop-%s.sqlite" % tag))
    tid = 439
    gov.ticket(tid)
    spawns, prompts = list(scripted), []

    def fake_spawn(prompt, tools, timeout, cwd=None):
        prompts.append(prompt)
        nxt = spawns.pop(0)
        if isinstance(nxt, Exception):
            # A silent worker may still have WRITTEN something. Leaving it behind is what makes
            # "the worktree persists with whatever was written" a checkable claim, not an assertion.
            if cwd:
                open(os.path.join(cwd, "docs", "half-written.txt"), "a").write("partial work\n")
            raise nxt
        if isinstance(nxt, dict) and nxt.get("done") and cwd:      # a real worker writes its file
            open(os.path.join(cwd, "docs", "out.md"), "w").write("delivered\n")
        return nxt

    class _TicketRow:                      # what main()'s one direct urlopen() reads
        def read(self):
            return json.dumps({"row": {"title": "loop selftest", "body": "b", "kind": "build"}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    g = globals()
    saved = {k: g[k] for k in ("rest", "rows", "spawn_claude", "forge_for", "API_KEY")}
    real_urlopen, argv = urllib.request.urlopen, sys.argv
    try:
        g["rest"] = gov
        g["rows"] = lambda route, params: gov(route, params, "GET").get("rows", [])
        g["spawn_claude"] = fake_spawn
        # api=gov: exactly what forge_for() binds in production (api=rest), pointed at the throwaway
        # db instead of the live one. That is what makes the mint hook's end-to-end checks real —
        # main() stamps through the SAME seam, against the REAL 0014 routes, and writes nothing live.
        g["forge_for"] = lambda root=None: Forge(repo, api=gov)
        g["API_KEY"] = "selftest-key"
        urllib.request.urlopen = lambda url, timeout=None: _TicketRow()
        sys.argv = ["pair_loop.py", "--ticket", str(tid), "--deliverable", "docs/out.md",
                    "--rounds", str(rounds), "--base", Forge(repo).current_branch()]
        return main(), gov, prompts, repo
    finally:
        g.update(saved)
        urllib.request.urlopen = real_urlopen
        sys.argv = argv


def selftest(install_check_too=False):
    """Drive the whole branch-per-ticket flow against a temp repo and CHECK each acceptance claim.
    Prints one PASS/FAIL line per check; returns 0 only if every check passed.

    A SKIP is not a check: it is printed and counted separately and never fails the run
    (--install-check and the live-db cross-checks are the only sources — see install_check() and
    _st_live_gov()).
    """
    checks, skips = [], []

    # Theme 3 / #153: PROVE "this repo is not touched" rather than asserting it. The one thing this
    # run could plausibly write into the repo is a Variant-A bug report, so bug_report()'s sink is
    # snapshotted here — BEFORE the first line that could file one, since a baseline taken later
    # would silently count this run's own writes as pre-existing — and re-checked at the end.
    sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))

    def sink_state():
        return (os.path.isfile(sink), os.path.getsize(sink) if os.path.isfile(sink) else 0)

    sink_before = sink_state()

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name, ("  — %s" % detail) if detail and not cond else ""))

    def skip(name, detail):
        skips.append((name, detail))
        print("   SKIP %s  — %s" % (name, detail))

    # A check must REPORT, never explode. Calling a governance surface bare would abort the whole
    # run on a regression — exit 2, a traceback and a filed bug report — instead of printing the FAIL
    # that names it, and every check after it would go unrun. These two turn "did it raise?" into
    # data the ck()s above can judge.
    def attempt(fn, *aa):
        """A call expected to SUCCEED -> (error_text_or_empty, result)."""
        try:
            return "", fn(*aa)
        except Exception as e:  # noqa: BLE001
            return "%s: %s" % (type(e).__name__, e), None

    def refused(fn, *aa):
        """A call expected to be REFUSED -> the refusal text, or "" if it wrongly succeeded."""
        try:
            fn(*aa)
            return ""
        except Exception as e:  # noqa: BLE001
            return str(e)

    def before(routes, first, second):
        """Did BOTH routes get called, `first` before `second`? An ORDERING check that REPORTS.

        A missing route is a FAILED ordering, never an exception — and that distinction is the
        whole point. Under #279's order `ticket.assign` is never sent, so a bare
        routes.index("ticket.assign") raises ValueError and ABORTS the run at exactly the moment
        it should be printing the FAIL that names the regression: no tally, and every later check
        (the whole no-verdict block included) goes unrun. Same rule as attempt()/refused() above —
        a check turns "did it raise?" into data; it never explodes.
        """
        return first in routes and second in routes and routes.index(first) < routes.index(second)

    base_dir = tempfile.mkdtemp(prefix="pair_loop-selftest-")
    try:
        repo = _st_repo(base_dir)
        f = Forge(repo)
        base = f.current_branch()
        print("== selftest == throwaway repo %s (base branch %r)" % (repo, base))

        # ── i1: dispatching #221 produces branch ticket/221 with the deliverable committed there ──
        print("-- i1: branch + worktree + commit on the branch")
        ck("branch name is deterministic 'ticket/221'", f.branch_of(221) == "ticket/221", f.branch_of(221))
        o = f.open_worktree(221, base)
        ck("branch ticket/221 created", f.branch_exists("ticket/221"))
        ck("worktree exists and is a checkout", os.path.isfile(os.path.join(o["path"], "docs", "seed.md")))
        ck("worktree is checked out ON ticket/221", f.current_branch(cwd=o["path"]) == "ticket/221")
        ck("base tree still on the base branch", f.current_branch() == base)
        ck("worktree lives under .git (invisible to git status)",
           os.path.relpath(o["path"], repo).startswith(".git"), os.path.relpath(o["path"], repo))
        ck("base tree CLEAN after open (#213)", not f.git("status", "--porcelain").strip(),
           f.git("status", "--porcelain").strip())
        ck("re-open is idempotent/resumable", f.open_worktree(221, base)["created"] is False)

        # the worker writes its deliverable INTO the worktree; the harness commits it
        deliv = "tools/thing.py"
        os.makedirs(os.path.join(o["path"], "tools"), exist_ok=True)
        open(os.path.join(o["path"], deliv), "w").write("print('round 1')\n")
        c = f.commit_deliverable(221, deliv, "ticket #221: round 1")
        ck("deliverable committed on the branch", c["committed"] and c["sha"])
        ck("the commit is ON ticket/221",
           deliv in f.git("show", "--name-only", "--format=", "ticket/221"))
        ck("base branch does NOT have the deliverable",
           not os.path.exists(os.path.join(repo, deliv)) and deliv not in f.git("ls-tree", "-r", "--name-only", base))
        ck("nothing to commit twice is not a crash", f.commit_deliverable(221, deliv, "again")["committed"] is False)

        # a second round appends a second commit on the same branch (history is kept)
        open(os.path.join(o["path"], deliv), "w").write("print('round 2')\n")
        c2 = f.commit_deliverable(221, deliv, "ticket #221: round 2")
        ck("a later round adds another commit on the branch",
           c2["committed"] and len(f.git("log", "--oneline", "ticket/221").splitlines()) == 3)

        # ── i2: DONE merges to base and reaps the worktree ──
        print("-- i2: merge to base + reap the worktree")
        m = f.merge_to_base(221, base, "merge ticket/221")
        ck("merge to base succeeded", m.get("ok"), m.get("reason", ""))
        ck("base branch now HAS the deliverable", os.path.isfile(os.path.join(repo, deliv)))
        ck("merge made a merge COMMIT (--no-ff, not a fast-forward)",
           len(f.git("rev-list", "--parents", "-n", "1", "HEAD").split()) == 3)
        ck("worktree reaped", f.reap_worktree(221) and not os.path.exists(o["path"]))
        ck("branch ticket/221 KEPT after reap (the ticket's trace)", f.branch_exists("ticket/221"))
        ck("base tree CLEAN after the whole cycle (#213)", not f.git("status", "--porcelain").strip(),
           f.git("status", "--porcelain").strip())
        # realpath both sides: on macOS /var is a symlink to /private/var, so git reports the
        # resolved path while tempfile hands back the unresolved one.
        ck("no worktrees left registered but the base",
           [os.path.realpath(w["path"]) for w in f.registered_worktrees()] == [os.path.realpath(repo)],
           str([w["path"] for w in f.registered_worktrees()]))

        # a merge into a DRIFTED base is refused (#213), not forced
        open(os.path.join(repo, "docs", "seed.md"), "w").write("drift\n")
        f.open_worktree(777, base)
        open(os.path.join(f.worktree_of(777), "tools", "seven.py"), "w").write("7\n")
        f.commit_deliverable(777, "tools/seven.py", "ticket #777")
        d = f.merge_to_base(777, base, "merge ticket/777")
        ck("merge into a drifted base tree is REFUSED (#213)", not d.get("ok") and "drifted" in d.get("reason", ""),
           d.get("reason", ""))
        _st_git(repo, "checkout", "--", "docs/seed.md")   # undo the drift we made
        ck("...and the refusal left the ticket mergeable once clean", f.merge_to_base(777, base, "merge #777")["ok"])
        f.reap_worktree(777)

        # ── i3: two pairs on distinct tickets, concurrently, in separate worktrees ──
        print("-- i3: two pairs in parallel, no contention")
        errs, done = [], []

        def pair_run(tid, path):
            try:
                w = f.open_worktree(tid, base)
                os.makedirs(os.path.join(w["path"], os.path.dirname(path)), exist_ok=True)
                open(os.path.join(w["path"], path), "w").write("ticket %d\n" % tid)
                f.commit_deliverable(tid, path, "ticket #%d" % tid)
                r = f.merge_to_base(tid, base, "merge ticket/%d" % tid)
                if not r.get("ok"):
                    errs.append("#%d merge: %s" % (tid, r.get("reason")))
                    return
                f.reap_worktree(tid)
                done.append(tid)
            except Exception as e:  # noqa: BLE001
                errs.append("#%d: %s" % (tid, e))

        ts = [threading.Thread(target=pair_run, args=(901, "tools/nine01.py")),
              threading.Thread(target=pair_run, args=(902, "tools/nine02.py"))]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        ck("two concurrent pairs both completed", sorted(done) == [901, 902], "; ".join(errs) or str(done))
        ck("both branches exist", f.branch_exists("ticket/901") and f.branch_exists("ticket/902"))
        ck("both deliverables landed on base, no cross-ticket conflict",
           os.path.isfile(os.path.join(repo, "tools/nine01.py")) and os.path.isfile(os.path.join(repo, "tools/nine02.py")))
        ck("base tree CLEAN after parallel pairs (#213)", not f.git("status", "--porcelain").strip(),
           f.git("status", "--porcelain").strip())
        ck("both worktrees reaped",
           not os.path.exists(f.worktree_of(901)) and not os.path.exists(f.worktree_of(902)))

        # ── the adversary's own test (#222): two branches touching the SAME file must CONFLICT ──
        print("-- conflict: the second merge surfaces it, never clobbers")
        for tid, text in ((801, "from 801\n"), (802, "from 802\n")):
            w = f.open_worktree(tid, base)
            open(os.path.join(w["path"], "docs", "clash.md"), "w").write(text)
            f.commit_deliverable(tid, "docs/clash.md", "ticket #%d" % tid)
        r1 = f.merge_to_base(801, base, "merge ticket/801")
        r2 = f.merge_to_base(802, base, "merge ticket/802")
        ck("first merge of the clashing pair succeeds", r1.get("ok"), r1.get("reason", ""))
        ck("second merge CONFLICTS (not a silent clobber)", (not r2.get("ok")) and r2.get("conflict"),
           str(r2.get("reason")))
        ck("base keeps the FIRST ticket's content (nothing clobbered)",
           open(os.path.join(repo, "docs", "clash.md")).read() == "from 801\n")
        ck("base tree CLEAN after the aborted merge", not f.git("status", "--porcelain").strip(),
           f.git("status", "--porcelain").strip())
        ck("the conflicted branch ticket/802 PERSISTS", f.branch_exists("ticket/802"))
        ck("the conflicted worktree PERSISTS (work is not thrown away)", os.path.exists(f.worktree_of(802)))
        f.reap_worktree(801)
        f.reap_worktree(802)

        # ── an EMPTY branch never settles: no commit => no merge => no DONE ──
        # The trap: the worker rewrites the file base ALREADY has, byte-for-byte. commit_deliverable
        # makes no commit, and `git merge --no-ff` of that commit-less branch prints "Already up to
        # date" and exits 0 — a success that moved nothing. merge_to_base must refuse it, or the
        # harness would mint a UID and journal a merge for work that was never committed.
        print("-- empty branch: no commit -> no merge -> no settle")
        seed_before = f.head()
        w300 = f.open_worktree(300, base)
        open(os.path.join(w300["path"], "docs", "seed.md"), "w").write("seed\n")   # identical to base
        c300 = f.commit_deliverable(300, "docs/seed.md", "ticket #300: nothing new")
        ck("a byte-identical deliverable makes NO commit", c300["committed"] is False, str(c300))
        ck("branch ticket/300 is empty (0 commits base lacks)", f.ahead_of(300, base) == 0,
           str(f.ahead_of(300, base)))
        m300 = f.merge_to_base(300, base, "merge ticket/300")
        ck("merging an EMPTY branch is REFUSED, not reported merged",
           (not m300.get("ok")) and m300.get("empty"), str(m300))
        ck("the refusal explains itself (no commits / nothing to merge)",
           "nothing to merge" in m300.get("reason", ""), m300.get("reason", ""))
        ck("base HEAD did NOT move on the refusal", f.head() == seed_before,
           "%s -> %s" % (seed_before[:10], f.head()[:10]))
        ck("no merge commit was invented for the empty branch",
           f.git("rev-list", "--count", "%s..%s" % (seed_before, base)).strip() == "0")
        ck("the empty branch ticket/300 PERSISTS (ticket stays open)", f.branch_exists("ticket/300"))
        ck("the empty branch's worktree PERSISTS (nothing thrown away)", os.path.exists(f.worktree_of(300)))
        ck("base tree CLEAN after the empty-branch refusal (#213)", not f.git("status", "--porcelain").strip(),
           f.git("status", "--porcelain").strip())
        # ...and once the worker commits something REAL, the same branch merges normally.
        open(os.path.join(w300["path"], "docs", "seed.md"), "w").write("seed\nreal work\n")
        c300b = f.commit_deliverable(300, "docs/seed.md", "ticket #300: real work")
        ck("a real change on the same branch DOES commit", c300b["committed"] is True)
        m300b = f.merge_to_base(300, base, "merge ticket/300 (real)")
        ck("...and the once-empty branch then merges for real", m300b.get("ok") and m300b["sha"] != m300b["was"],
           str(m300b.get("reason", "")))
        ck("that merge landed a real merge COMMIT", f.is_merge_commit())
        ck("base now carries the ticket's content", open(os.path.join(repo, "docs", "seed.md")).read()
           == "seed\nreal work\n")
        f.reap_worktree(300)

        # ── strays: the DELIVERABLE is never a stray, whatever it is named ──
        # The trap: a stray is journaled as "UNCOMMITTED ... will not survive the reap", so a FALSE
        # stray writes into the append-only record that the delivered file was abandoned — while it
        # was in fact committed and merged. Plain `--porcelain` C-quotes exotic paths and normalizes
        # no spelling, so a raw compare against the deliverable string mis-reads all three of these.
        print("-- strays: an exotic deliverable name is not mistaken for a stray")
        for tid, deliv, label in ((401, "docs/naïve.md", "a non-ascii name (git C-quotes it)"),
                                  (402, "docs/my file.md", "a space in the name (git C-quotes it)"),
                                  (403, "./docs/dot.md", "a './' prefix (git prints it without)")):
            w = f.open_worktree(tid, base)
            open(os.path.join(w["path"], deliv), "w").write("content\n")
            c = f.commit_deliverable(tid, deliv, "ticket #%d" % tid)
            ck("deliverable with %s is committed" % label, c["committed"], str(c))
            ck("deliverable with %s is NOT called a stray" % label, c["strays"] == [], str(c["strays"]))
            f.reap_worktree(tid)

        # the other direction: a real stray must STILL be caught (the fix must not just go blind)
        w404 = f.open_worktree(404, base)
        open(os.path.join(w404["path"], "docs", "deliv.md"), "w").write("d\n")
        open(os.path.join(w404["path"], "docs", "stray.md"), "w").write("s\n")
        c404 = f.commit_deliverable(404, "docs/deliv.md", "ticket #404")
        ck("a REAL stray is still detected", c404["strays"] == ["docs/stray.md"], str(c404["strays"]))
        ck("...and the deliverable next to it still commits", c404["committed"] is True, str(c404))
        ck("...and the stray did NOT ride along into the commit",
           "docs/stray.md" not in f.git("show", "--name-only", "--format=", "ticket/404"))
        # a rename is TWO NUL fields (new + source); the source must not surface as a phantom stray
        f.git("mv", "docs/seed.md", "docs/moved.md", cwd=w404["path"])
        ents = f.porcelain(cwd=w404["path"])
        ck("a rename parses as ONE entry, not a phantom for its source path",
           sorted(p for _, p in ents) == ["docs/moved.md", "docs/stray.md"], str(ents))
        f.reap_worktree(404)

        # ── #409: a FORGE deliverable commits its WHOLE PACKAGE, so the package lands installable ──
        # The bug this proves gone: #401 merged forge2/artifact_tree_gen/add.py and nothing else, so
        # the pyproject.toml the worker wrote was journaled a stray and reaped, and what landed on
        # main cannot be `pip install -e .`'d. The scope gate is the deliverable's PATH.
        print("-- #409: a forge package deliverable commits the whole package")
        pkg, name = "checkouts/current/forge2/selftest_forge", "selftest_forge"
        deliv = pkg + "/add.py"
        ck("package_root_of() finds the package under a nested forge2/",
           package_root_of(deliv) == pkg, str(package_root_of(deliv)))
        ck("package_root_of() takes a SUBMODULE to the same package root",
           package_root_of(pkg + "/sub/helper.py") == pkg, str(package_root_of(pkg + "/sub/helper.py")))
        ck("package_root_of() ignores a tool path (single-file, unchanged)",
           package_root_of("tools/pair_loop.py") is None, str(package_root_of("tools/pair_loop.py")))
        ck("package_root_of() ignores a doc path (single-file, unchanged)",
           package_root_of("docs/PLAYBOOK.md") is None, str(package_root_of("docs/PLAYBOOK.md")))
        ck("package_root_of() refuses a file sitting DIRECTLY in forge2/ (no package dir)",
           package_root_of("checkouts/current/forge2/loose.py") is None,
           str(package_root_of("checkouts/current/forge2/loose.py")))
        ck("is_build_artifact() catches an egg-info dir and what's under it",
           is_build_artifact(pkg + "/selftest_forge.egg-info")
           and is_build_artifact(pkg + "/selftest_forge.egg-info/PKG-INFO")
           and is_build_artifact(pkg + "/__pycache__/add.cpython-311.pyc"))
        ck("is_build_artifact() leaves real package source alone",
           not any(is_build_artifact(p) for p in (deliv, pkg + "/pyproject.toml", pkg + "/config.json",
                                                  pkg + "/sub/helper.py")))

        w409 = f.open_worktree(409, base)
        wrote = _st_forge_package(w409["path"], pkg, name)
        # what the worker's own `pip install -e .` leaves behind, and what importing leaves behind
        os.makedirs(os.path.join(w409["path"], pkg, name + ".egg-info"))
        open(os.path.join(w409["path"], pkg, name + ".egg-info", "PKG-INFO"), "w").write("Name: x\n")
        os.makedirs(os.path.join(w409["path"], pkg, "build", "lib"))
        open(os.path.join(w409["path"], pkg, "build", "lib", "add.py"), "w").write("built\n")
        # ...and a genuine stray, OUTSIDE the package: the scope must still exclude it
        open(os.path.join(w409["path"], "docs", "notes.md"), "w").write("scratch\n")

        c409 = f.commit_deliverable(409, deliv, "ticket #409: forge unit")
        ck("a forge deliverable is a PACKAGE commit", c409["package"] == pkg, str(c409["package"]))
        ck("the package commit committed", c409["committed"], str(c409))
        in_commit = f.git("show", "--name-only", "--format=", "ticket/409").split()
        ck("the MODULE landed", deliv in in_commit, str(in_commit))
        ck("its pyproject.toml landed (THE #401 bug)", pkg + "/pyproject.toml" in in_commit, str(in_commit))
        ck("its config landed", pkg + "/config.json" in in_commit, str(in_commit))
        ck("its submodule landed", pkg + "/sub/helper.py" in in_commit, str(in_commit))
        ck("the WHOLE package source landed, exactly", sorted(in_commit) == wrote,
           "committed %s; wrote %s" % (sorted(in_commit), wrote))
        ck("the committed fileset is surfaced (files, not an empty strays:[])",
           sorted(c409["files"]) == wrote, str(c409["files"]))
        ck("build artifacts did NOT ride along into the commit",
           not any(is_build_artifact(p) for p in in_commit), str(in_commit))
        ck("...and they are NAMED as skipped, not dropped silently",
           sorted(c409["skipped"]) == sorted([pkg + "/build/lib/add.py", pkg + "/" + name + ".egg-info/PKG-INFO"]),
           str(c409["skipped"]))
        ck("a stray OUTSIDE the package is still a stray", c409["strays"] == ["docs/notes.md"],
           str(c409["strays"]))
        ck("the commit LOG names the fileset that landed",
           pkg + "/pyproject.toml" in f.git("log", "-1", "--format=%B", "ticket/409")
           and "Package commit (#409)" in f.git("log", "-1", "--format=%B", "ticket/409"),
           f.git("log", "-1", "--format=%B", "ticket/409"))
        ck("the journal line names the package and its files, not one module",
           "PACKAGE %s/" % pkg in commit_note(1, deliv, c409) and pkg + "/pyproject.toml" in commit_note(1, deliv, c409),
           commit_note(1, deliv, c409))
        ck("the worker's prompt line matches what the harness commits (no contradiction)",
           "commits the WHOLE of %s/" % pkg in worker_scope(deliv, pkg) and "touch nothing else" not in worker_scope(deliv, pkg),
           worker_scope(deliv, pkg))
        ck("a non-package deliverable's prompt line is UNCHANGED",
           worker_scope("docs/x.md", None) == "write it to docs/x.md (create or overwrite that file; "
                                              "touch nothing else).", worker_scope("docs/x.md", None))

        # a second round re-commits only what changed, and STILL names it
        open(os.path.join(w409["path"], pkg, "config.json"), "w").write('{"schema": 1, "offset": 1}\n')
        c409b = f.commit_deliverable(409, deliv, "ticket #409: round 2")
        ck("a later round commits the package file that changed", c409b["committed"]
           and c409b["files"] == [pkg + "/config.json"], str(c409b["files"]))

        # THE ACCEPTANCE: the package lands on the base, whole and installable
        m409 = f.merge_to_base(409, base, "merge ticket/409")
        ck("the package branch merged to base", m409.get("ok"), m409.get("reason", ""))
        merged_pkg = os.path.join(repo, pkg)
        ck("forge2/<repo>/ lands on base WITH its pyproject.toml (#409 acceptance)",
           os.path.isfile(os.path.join(merged_pkg, "pyproject.toml")), str(os.path.isdir(merged_pkg)))
        ck("...and with the module, config and submodule beside it",
           all(os.path.isfile(os.path.join(merged_pkg, r)) for r in ("add.py", "config.json", "sub/helper.py")))
        ck("...and with NO build artifacts on base",
           not os.path.exists(os.path.join(merged_pkg, name + ".egg-info"))
           and not os.path.exists(os.path.join(merged_pkg, "build")))
        f.reap_worktree(409)

        # THE PILOT, RE-RUN — #409's acceptance sentence, staged literally. The base starts holding
        # what #401 actually landed (the module, alone, no pyproject.toml), a fresh unit rewrites it
        # into a full package, and the fix has to carry the MISSING pyproject.toml onto the base this
        # time. Under the pre-#409 single-file commit this branch would have landed add.py again and
        # the pyproject.toml would have been journaled a stray and reaped a second time.
        print("-- #409: re-running the pilot over a module-only package heals it")
        pilot = "checkouts/current/forge2/pilot_pkg"
        os.makedirs(os.path.join(repo, pilot))
        open(os.path.join(repo, pilot, "add.py"), "w").write("def add(a, b):\n    return a + b\n")
        _st_git(repo, "add", "-A")
        _st_git(repo, "commit", "--quiet", "-m", "what #401 landed: the module, alone")
        ck("base starts module-only, exactly as the pilot left it (NOT installable)",
           os.path.isfile(os.path.join(repo, pilot, "add.py"))
           and not os.path.exists(os.path.join(repo, pilot, "pyproject.toml")))
        w412 = f.open_worktree(412, base)
        _st_forge_package(w412["path"], pilot, "pilot_pkg")
        c412 = f.commit_deliverable(412, pilot + "/add.py", "ticket #412: re-run the pilot")
        ck("the re-run commits the MISSING pyproject.toml together with the rewritten module",
           c412["package"] == pilot and pilot + "/pyproject.toml" in c412["files"]
           and pilot + "/add.py" in c412["files"], str(c412["files"]))
        m412 = f.merge_to_base(412, base, "merge ticket/412")
        ck("the re-run merged to base", m412.get("ok"), m412.get("reason", ""))
        ck("the module-only package is HEALED on base: pyproject.toml is now present",
           os.path.isfile(os.path.join(repo, pilot, "pyproject.toml")))
        f.reap_worktree(412)

        # the OTHER direction: --package-commit off keeps the single-file commit for a forge path,
        # and a tag/tool path is single-file whatever the gate says.
        print("-- #409: the gate, both ways")
        w410 = f.open_worktree(410, base)
        _st_forge_package(w410["path"], "checkouts/current/forge2/other_pkg", "other_pkg")
        c410 = f.commit_deliverable(410, "checkouts/current/forge2/other_pkg/add.py", "ticket #410", "off")
        ck("--package-commit off forces the single-file commit for a forge path",
           c410["package"] is None and c410["files"] == ["checkouts/current/forge2/other_pkg/add.py"],
           str(c410["files"]))
        ck("...and its package files are then reported as strays (the pre-#409 record)",
           "checkouts/current/forge2/other_pkg/pyproject.toml" in c410["strays"], str(c410["strays"]))
        f.reap_worktree(410)

        w411 = f.open_worktree(411, base)
        open(os.path.join(w411["path"], "tools", "tag_x.py"), "w").write("tag\n")
        open(os.path.join(w411["path"], "tools", "sibling.py"), "w").write("not mine\n")
        c411 = f.commit_deliverable(411, "tools/tag_x.py", "ticket #411")
        ck("a TOOL deliverable is untouched by #409: single file, sibling not swept in",
           c411["package"] is None and c411["files"] == ["tools/tag_x.py"]
           and c411["strays"] == ["tools/sibling.py"], str(c411))
        c411b = f.commit_deliverable(411, "tools/tag_x.py", "ticket #411 (forced)", "on")
        ck("--package-commit on honors an explicit directory commit for a non-forge path",
           c411b["package"] == "tools" and "tools/sibling.py" in c411b["files"], str(c411b))
        f.reap_worktree(411)

        # ── #439: the governance ORDER (assign -> ACTIVE), against the REAL 0029 constraint ──────
        # This is the block #279 did not have. Every check below runs the SHIPPING Gov code against
        # the actual tg_tickets_active_needs_agent trigger, executed into a throwaway db straight
        # from migrations/0029_ticket_authorization.sql. Re-introduce #279's order and these FAIL.
        print("-- #439: assign -> ACTIVE, driven against the REAL trigger from migrations/0029")
        missing = [m for m in GOV_MIGRATIONS if not os.path.isfile(os.path.join(ROOT, "migrations", m))]
        ck("this repo's governance migrations are readable (they ARE the rules under test)",
           not missing, "missing: %s" % missing)
        if not missing:
            g = _StGov(os.path.join(base_dir, "gov-teeth.sqlite"))
            ck("the throwaway db carries the REAL rule, loaded from migrations/0029",
               bool(g.trigger_sql("tg_tickets_active_needs_agent")))

            # FIRST: prove the ORACLE has teeth. If the db did not really refuse #279's order, every
            # green ordering check below would be meaningless — which is exactly how #279 went 129/129.
            g.ticket(439)
            bare = refused(g, "process_status", {"id": 439, "status": "ACTIVE"})
            ck("the real rule REFUSES ACTIVE before any assign — #279's exact order, and the db's 500",
               GOV_ACTIVE_RULE in bare,
               bare or "the db ACCEPTED it: this oracle has no teeth and proves nothing")
            ck("...and the ticket really did not move (still REQUESTED)",
               g.status(439) == "REQUESTED", str(g.status(439)))

            # NOW the shipping code, against that same armed rule: a real round 1 must reach ACTIVE.
            # open_round() is the very function main() calls, so this proves the ORDER MAIN RUNS —
            # not an arrangement of Gov calls written to agree with it.
            gv = _StGov(os.path.join(base_dir, "gov-round.sqlite"))
            gv.ticket(439)
            gov = Gov(439, api=gv)
            err, opened = attempt(open_round, gov, "coder-t439r1", "coder", "the worker's birth prompt",
                                  "ticket/439")
            ck("HARD REQ 1 — a real open_round() REACHES ACTIVE against the live rule (no 500)",
               not err and gv.status(439) == "ACTIVE" and "set (after" in (opened or {}).get("ACTIVE", ""),
               err or "status=%s opened=%s" % (gv.status(439), opened))
            ck("...in the order the db demands: ticket.assign BEFORE process_status",
               before(gv.routes(), "ticket.assign", "process_status"), str(gv.routes()))
            ck("...and agent.register before ticket.assign (tg_ticket_agents_registered refuses otherwise)",
               before(gv.routes(), "agent.register", "ticket.assign"), str(gv.routes()))
            # attempt(), not a bare gov.activate(): under #279's order this very call raises the
            # tripwire, and a bare call would abort the run instead of reporting the FAIL.
            aerr2, again = attempt(gov.activate)
            ck("ACTIVE is a round-1 act: a second activate() is a no-op, not a second write",
               not aerr2 and again is False and gv.routes().count("process_status") == 1,
               aerr2 or str(gv.routes()))

            # HARD REQ 2 — lazy: an agent exists only at ITS OWN spawn, with the prompt it is born on.
            ck("HARD REQ 2 — lazy: opening round 1 registers ONLY the worker; the adversary does not "
               "exist yet", gv.registered() == ["coder-t439r1"], str(gv.registered()))
            aerr, _ = attempt(gov.enlist, "tester-t439r1", "tester", "the adversary's birth prompt")
            ck("...the adversary registers at its own spawn",
               not aerr and "tester-t439r1" in gv.registered(), aerr or str(gv.registered()))
            r2err, r2 = attempt(open_round, gov, "coder-t439r2", "coder",
                                "ROUND 2 prompt: carries round 1's findings", "ticket/439")
            ck("...a RE-ASKED worker registers at ITS spawn, with the prompt it is actually born on "
               "(unknowable before its predecessor was rejected)",
               not r2err and gv.prompt_of("coder-t439r2") == "ROUND 2 prompt: carries round 1's findings",
               r2err or str(gv.prompt_of("coder-t439r2")))
            ck("...and round 2 sends no second process_status (the ticket is already ACTIVE)",
               (r2 or {}).get("ACTIVE") == "already set" and gv.routes().count("process_status") == 1,
               str(gv.routes()))

            # The tripwire: the code refuses to EXPRESS #279's order, before the db ever sees it.
            gt = _StGov(os.path.join(base_dir, "gov-trip.sqlite"))
            gt.ticket(439)
            tripped = refused(Gov(439, api=gt).activate)
            ck("Gov refuses #279's order AT THE SOURCE: activate() before any enlist() raises",
               "before any ticket.assign" in tripped, tripped or "activate() ran with nothing assigned!")
            ck("...and never reached the db (no process_status was ever sent)",
               "process_status" not in gt.routes(), str(gt.routes()))

            # The lazy pair must still satisfy the db's OTHER backstop, or settling would break.
            derr, _ = attempt(gv, "process_status", {"id": 439, "status": "DONE"})
            ck("the pair's own assigns still reach DONE (two distinct agents, two distinct roles)",
               not derr and gv.status(439) == "DONE", derr or "crew=%s" % gv.crew(439))
            gs = _StGov(os.path.join(base_dir, "gov-solo.sqlite"))
            gs.ticket(439)
            attempt(Gov(439, api=gs).enlist, "coder-t439r1", "coder", "p")
            solo = refused(gs, "process_status", {"id": 439, "status": "DONE"})
            ck("...and the pair-completion backstop is still armed: one agent alone cannot reach DONE",
               "two DISTINCT agents" in solo, solo or "a lone worker settled the ticket!")

            # The live surface, read-only: proof that the rule driven above IS the shipping rule, and
            # that the one pinned route has not drifted. SKIPped where the (untracked) db is absent.
            live, where = _st_live_gov()
            if live is None:
                skip("the pinned process_status SQL still matches the live db", where)
                skip("the trigger driven above is byte-identical to the live db's", where)
            else:
                print("        live governance db (read-only, immutable=1): %s" % where)
                lrow = live.execute("SELECT sql FROM api_routes WHERE name = 'process_status'").fetchone()
                ck("the pinned process_status SQL still matches the live db's api_routes row",
                   bool(lrow) and _st_sql_eq(lrow[0], GOV_PROCESS_STATUS_SQL),
                   "live=%r pinned=%r" % (lrow[0] if lrow else None, GOV_PROCESS_STATUS_SQL))
                ltrig = live.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name = ?",
                                     ("tg_tickets_active_needs_agent",)).fetchone()
                ck("the constraint these checks drive IS the live one (0029's trigger, byte for byte)",
                   bool(ltrig) and _st_sql_eq(ltrig[0], g.trigger_sql("tg_tickets_active_needs_agent")),
                   "live=%r" % (ltrig[0] if ltrig else None))

        # ── #439: a worker that says nothing readable FAILS THE ROUND; it never crashes the pair ──
        print("-- #439: no-verdict is a round outcome, not a harness crash")
        ck("verdict_of reads the agent's answer off the last JSON line",
           verdict_of('chatter\n{"done": true, "ref": "x"}') == {"done": True, "ref": "x"})
        ck("verdict_of skips an unparseable brace line and keeps looking upward",
           verdict_of('{"done": true, "ref": "x"}\n{oops') == {"done": True, "ref": "x"})
        # NoVerdict specifically, not merely "it raised": the loop catches NoVerdict and nothing else,
        # so a bare Unexpected here would sail past that handler and crash the pair all over again.
        def raised(fn, arg):
            try:
                fn(arg)
                return "RETURNED (no exception at all)"
            except NoVerdict:
                return "NoVerdict"
            except Exception as e:  # noqa: BLE001
                return "%s — NOT a NoVerdict, so the round loop would not catch it" % type(e).__name__

        for out, why in (("", "empty output"), ("I give up.\n", "prose, no JSON"),
                         ("{not json}\n", "an unparseable brace line"), ("[1, 2]\n", "a JSON array, not an object")):
            got = raised(verdict_of, out)
            ck("nothing readable (%s) -> NoVerdict" % why, got == "NoVerdict", got)
        for res, why in (({"done": False}, "done=false"), ({}, "no done key"),
                         ({"done": None}, "done=null"), ("nope", "not an object at all")):
            got = raised(worker_done, res)
            ck("worker_done refuses %s -> NoVerdict (the round fails)" % why, got == "NoVerdict", got)
        ck("worker_done passes a real report through untouched",
           worker_done({"done": True, "ref": "x"}) == {"done": True, "ref": "x"})
        ck("NoVerdict IS an Unexpected — every call site that does not handle it keeps exit 2",
           issubclass(NoVerdict, Unexpected))

        # ── #439: the ROUND LOOP itself, through the REAL main() ─────────────────────────────────
        # The checks above prove the parts; these prove the loop. `except NoVerdict: continue` is the
        # whole no-verdict fix and it lives inside main(), so only running main() executes it.
        if not missing:
            print("-- #439: main()'s round loop absorbs a silent worker (end to end)")
            # attempt(): a crash out of main() is the very regression under test, so it must be
            # REPORTED as a FAIL naming this check — not allowed to abort the run and skip the rest.
            lerr, lres = attempt(_st_loop_run, base_dir, "silent-then-ok", [
                NoVerdict("no JSON verdict on the agent's last line; tail: 'I am stuck'"),
                {"done": True, "ref": "docs/out.md", "note": "round 2 delivered"},
                {"verdict": "pass", "findings": []}])
            ck("a SILENT round-1 worker does not crash the pair — round 2 settles the ticket (exit 0)",
               not lerr and lres and lres[0] == 0, lerr or "exit=%s" % (lres[0] if lres else "?"))
            if lres:
                code, lg, prompts, lrepo = lres
                lroutes = [r for r, _ in lg.calls]
                lnotes = [o.get("note") or "" for r, o in lg.calls if r == "ticket.progress"]
                ck("...and it really settled: the ticket reached DONE",
                   lg.status(439) == "DONE", str(lg.status(439)))
                ck("...the silent round is named on the append-only journal",
                   any("produced no usable result" in n for n in lnotes), str(lnotes[:1]))
                ck("...recording that NOTHING was committed for it (no deliverable was reported)",
                   any("nothing committed" in n for n in lnotes), str(lnotes[:1]))
                ck("...and no commit was in fact made for it (only round 2's work is on the branch)",
                   len(Forge(lrepo).git("log", "--oneline", "ticket/439").strip().splitlines()) == 2,
                   Forge(lrepo).git("log", "--oneline", "ticket/439").strip())
                ck("...round 2's FRESH worker is told what its predecessor did wrong",
                   len(prompts) > 1 and "produced NO usable result" in prompts[1], "")
                ck("...round 1's ADVERSARY was never registered: there was nothing to judge (lazy)",
                   "tester-t439r1" not in lg.registered(), str(lg.registered()))
                ck("...ACTIVE was set once and only then DONE, never before an assign",
                   [o.get("status") for r, o in lg.calls if r == "process_status"] == ["ACTIVE", "DONE"]
                   and before(lroutes, "ticket.assign", "process_status"), str(lroutes[:6]))
                # #457 END TO END: the mint hook through the REAL main(). The checks further down
                # drive commit_deliverable directly; this one proves the SHIPPING round loop reaches
                # it — that forge_for()'s api seam is really bound, and that a settled ticket leaves
                # the registry populated rather than empty (the #438/#440/#445/#448/#439 failure).
                lart = lg.artifacts(439)
                ck("#457 END TO END — a ticket main() settled leaves a stamped row per landed file",
                   len(lart) == 1 and lart[0]["name"] == "docs/out.md"
                   and lart[0]["kind"] == ARTIFACT_KIND, str(lart))
                ck("...with forge_sha = `git rev-parse <commit>:<path>` in the repo it landed in",
                   bool(lart) and lart[0]["forge_sha"] == Forge(lrepo).git(
                       "rev-parse", "%s:docs/out.md" % Forge(lrepo).git(
                           "rev-parse", "ticket/439").strip()).strip(),
                   str(lart))
                ck("...minted through the governed route, not a hand-written db touch",
                   ARTIFACT_RECORD_ROUTE in lroutes, str(lroutes))

            e2, r2res = attempt(_st_loop_run, base_dir, "all-silent", [
                NoVerdict("no JSON verdict on the agent's last line; tail: ''"),
                NoVerdict("agent spawn exceeded its 480s budget (raise --timeout for heavier tickets)")])
            ck("EVERY round silent -> rounds exhausted (exit 1), still never a crash",
               not e2 and r2res and r2res[0] == 1, e2 or "exit=%s" % (r2res[0] if r2res else "?"))
            if r2res:
                _c2, lg2, _p2, lrepo2 = r2res
                ck("...the ticket never reached DONE", lg2.status(439) == "ACTIVE", str(lg2.status(439)))
                ck("...no work UID was minted for work that never landed",
                   "work.record" not in [r for r, _ in lg2.calls])
                wt2 = Forge(lrepo2).worktree_of(439)
                ck("...the worktree PERSISTS, with whatever the workers did write still in it",
                   os.path.isfile(os.path.join(wt2, "docs", "half-written.txt")), wt2)
                ck("...and a FRESH worker really ran each round (a new agent id, registered lazily)",
                   "coder-t439r2" in lg2.registered(), str(lg2.registered()))

            e3, r3res = attempt(_st_loop_run, base_dir, "done-false", [
                {"done": False, "note": "I could not finish"},
                {"done": True, "ref": "docs/out.md", "note": "second try"},
                {"verdict": "pass", "findings": []}])
            ck("a worker reporting done=false fails its round the same graceful way",
               not e3 and r3res and r3res[0] == 0 and r3res[1].status(439) == "DONE",
               e3 or str(r3res and (r3res[0], r3res[1].status(439))))

        # ── #457: THE MINT HOOK — every file a commit lands is stamped, AT COMMIT TIME ────────────
        # Driven against the REAL artifact.record/.list executed into a throwaway db straight from
        # migrations/0014, and against a REAL throwaway git repo — so the forge_sha these checks
        # compare against is git's own answer, never a value this code chose for itself. The rows are
        # read back out of the TABLE (_StGov.artifacts), not from what stamp_artifacts() reported:
        # a hook that returns a tidy list while writing nothing would pass a check that trusted it.
        # Nothing live is touched: the live registry is never opened, here or anywhere in --selftest.
        if not missing:
            print("-- #457: the mint hook — artifact.record for every file a commit lands")
            ga = _StGov(os.path.join(base_dir, "mint.sqlite"))
            ga.ticket(457)
            ck("the throwaway db carries the REAL artifact routes, loaded from migrations/0014",
               all(ga.db.execute("SELECT 1 FROM api_routes WHERE name = ?", (r,)).fetchone()
                   for r in (ARTIFACT_RECORD_ROUTE, ARTIFACT_LIST_ROUTE)))
            # Starts empty so that every row below is one THIS hook minted — the checks measure the
            # hook, not the fixture. (Not a claim about the live registry: #455 has since registered
            # its VM images there as kind 'forge-vm'. That is the same column, a different artifact
            # CLASS, and exactly why ARTIFACT_KIND is 'forge-source' and not the ticket's kind.)
            ck("...and its ticket_artifacts starts EMPTY, so every row below is one the hook minted",
               ga.artifacts() == [], str(ga.artifacts()))

            # THE PRODUCTION BINDING, checked directly — and the reason it must be. Every other check
            # here builds its own Forge(repo, api=...), and _st_loop_run OVERRIDES forge_for()
            # entirely, so NOTHING else in this file can notice if the one line that binds the hook in
            # production loses its api= argument: live commits would stamp nothing while --selftest
            # stayed green. That is #279's failure shape exactly (a green selftest over a dead path),
            # so the binding is asserted on its own. Constructing a Forge touches nothing.
            ck("PRODUCTION BINDING — forge_for() binds the mint hook to the REAL governed route "
               "(api=rest); without this every live commit stamps nothing",
               forge_for(repo).api is rest, str(forge_for(repo).api))

            fm = Forge(repo, api=ga)
            w457 = fm.open_worktree(457, base)
            open(os.path.join(w457["path"], "tools", "minted.py"), "w").write("print('minted')\n")
            e457, cm457 = attempt(fm.commit_deliverable, 457, "tools/minted.py", "ticket #457: mint")
            ck("a stamping commit still commits (the hook did not disturb the git layer)",
               not e457 and cm457 and cm457["committed"], e457 or str(cm457))

            r457 = ga.artifacts(457)
            ck("THE STAMP — ticket_artifacts gains one row for the file that landed",
               len(r457) == 1 and r457[0]["name"] == "tools/minted.py", str(r457))
            # THE acceptance equality, against git itself — and a SECOND, independent oracle:
            # hash-object hashes the BYTES, so agreement proves the row addresses this file's content
            # and not merely some object the commit happens to contain.
            oracle = fm.git("rev-parse", "%s:tools/minted.py" % cm457["sha"], cwd=w457["path"]).strip()
            bytes_oracle = fm.git("hash-object", os.path.join(w457["path"], "tools", "minted.py"),
                                  cwd=w457["path"]).strip()
            ck("THE STAMP — forge_sha IS `git rev-parse <commit>:<path>`, git's own answer",
               bool(r457) and r457[0]["forge_sha"] == oracle,
               "row=%s git=%s" % (r457[0]["forge_sha"] if r457 else None, oracle))
            ck("...and that sha is the content address of the landed BYTES (git hash-object agrees)",
               bool(r457) and r457[0]["forge_sha"] == bytes_oracle, bytes_oracle)
            ck("...name is the repo-relative PATH (stable, resolvable, what a human greps)",
               bool(r457) and r457[0]["name"] == "tools/minted.py", str(r457))
            ck("...version is the short commit sha the file landed in",
               bool(r457) and r457[0]["version"] == cm457["sha"][:10],
               "%s vs %s" % (r457[0]["version"] if r457 else None, cm457["sha"][:10]))
            ck("...kind is the stable ARTIFACT class 'forge-source', NOT the ticket's kind ('build')",
               bool(r457) and r457[0]["kind"] == ARTIFACT_KIND == "forge-source"
               and r457[0]["kind"] != ga.db.execute("SELECT kind FROM tickets WHERE id=457").fetchone()[0],
               str(r457))
            ck("...minted through the governed route — no SQL pen, no hand-written db",
               ARTIFACT_RECORD_ROUTE in ga.routes(), str(ga.routes()[-3:]))
            ck("THE GATE, the half this file owns: the stamped forge_sha is a REAL blob in the store "
               "the ticket names (`git cat-file -t` -> blob)",
               bool(r457) and fm.git("cat-file", "-t", r457[0]["forge_sha"], cwd=w457["path"]).strip() == "blob")

            # blob_sha() returns a BLOB or None — never a tree. `<commit>:<dir>` resolves happily to a
            # tree sha, and a row claiming that is a blob would be a lie the registry keeps forever.
            # staged() never names a directory today, so only a direct call can reach this guard —
            # which is exactly why it is checked here rather than trusted.
            ck("blob_sha() returns a blob, never a TREE (`<commit>:<dir>` resolves, but is not a file)",
               fm.blob_sha(cm457["sha"], "tools", cwd=w457["path"]) is None
               and fm.blob_sha(cm457["sha"], "tools/minted.py", cwd=w457["path"]) == oracle)
            ck("blob_sha() returns None (never raises) for a path absent from the commit",
               fm.blob_sha(cm457["sha"], "tools/never-existed.py", cwd=w457["path"]) is None)

            # The IDEMPOTENCY READ is the one failure that must stop the hook rather than let it write
            # blind: without the ticket's existing rows there is no way to honor (ticket_id,
            # forge_sha), and a duplicate row in an append-only registry cannot be taken back.
            class _ListDown(_StGov):
                def __call__(self, route, obj=None, method=None):
                    if route == ARTIFACT_LIST_ROUTE:
                        raise Unexpected("route %s failed: the read is down" % route)
                    return _StGov.__call__(self, route, obj, method)

            gl = _ListDown(os.path.join(base_dir, "mint-listdown.sqlite"))
            gl.ticket(464)
            fl = Forge(repo, api=gl)
            wl = fl.open_worktree(464, base)
            open(os.path.join(wl["path"], "tools", "blind.py"), "w").write("b\n")
            el, cl = attempt(fl.commit_deliverable, 464, "tools/blind.py", "ticket #464")
            ck("a failed idempotency READ stamps NOTHING rather than insert blind (a duplicate row "
               "is permanent; a missing stamp is not)",
               not el and cl and cl["committed"] and gl.artifacts(464) == []
               and not cl["artifacts"]["stamped"]
               and any(ARTIFACT_LIST_ROUTE in x for x in cl["artifacts"]["errors"]),
               el or str(cl["artifacts"]) if cl else "")
            ck("...and it never sent an artifact.record it could not prove was new",
               ARTIFACT_RECORD_ROUTE not in gl.routes(), str(gl.routes()))
            fl.reap_worktree(464)

            # IDEMPOTENT (key: ticket_id, forge_sha, name) — the same commit, stamped twice.
            again = fm.stamp_artifacts(457, cm457)
            ck("IDEMPOTENT — re-stamping the same commit mints NO second row",
               again["recorded"] == [] and len(ga.artifacts(457)) == 1 and bool(again["skipped"]),
               str(again))
            ck("...and says WHY it did not (the row is named, not silently dropped)",
               any("already stamped" in s for s in again["skipped"]), str(again["skipped"]))
            # ...and the real round-2 shape of it: bytes CHANGE, then come BACK. Round 3 is a genuine
            # commit whose blob sha equals round 1's, which is exactly "re-committing the same bytes".
            open(os.path.join(w457["path"], "tools", "minted.py"), "w").write("print('changed')\n")
            fm.commit_deliverable(457, "tools/minted.py", "ticket #457: round 2")
            ck("...a round that changes the bytes DOES mint a row (the key is not just 'seen once')",
               len(ga.artifacts(457)) == 2, str(ga.artifacts(457)))
            open(os.path.join(w457["path"], "tools", "minted.py"), "w").write("print('minted')\n")
            c457c = fm.commit_deliverable(457, "tools/minted.py", "ticket #457: round 3 (bytes revert)")
            ck("...but a round REVERTING to bytes already stamped mints none (a real round-2 commit, "
               "not a no-op)", c457c["committed"] and len(ga.artifacts(457)) == 2
               and c457c["artifacts"]["recorded"] == [], str(ga.artifacts(457)))
            fm.reap_worktree(457)

            # EVERY FILE IN SCOPE — a forge package commits several (policy 8); stamping one lies
            # about the rest. This is the #401/#409 shape, now at the registry.
            gp = _StGov(os.path.join(base_dir, "mint-pkg.sqlite"))
            gp.ticket(460)
            fp = Forge(repo, api=gp)
            w460 = fp.open_worktree(460, base)
            pkg460 = "checkouts/current/forge2/mint_pkg"
            wrote460 = _st_forge_package(w460["path"], pkg460, "mint_pkg")
            os.makedirs(os.path.join(w460["path"], pkg460, "mint_pkg.egg-info"))
            open(os.path.join(w460["path"], pkg460, "mint_pkg.egg-info", "PKG-INFO"), "w").write("x\n")
            c460 = fp.commit_deliverable(460, pkg460 + "/add.py", "ticket #460: package")
            r460 = gp.artifacts(460)
            ck("EVERY FILE IN SCOPE — a PACKAGE commit stamps one row per file, not just the module",
               sorted(r["name"] for r in r460) == wrote460, str([r["name"] for r in r460]))
            ck("...each with its OWN forge_sha, matching git for that exact path",
               all(r["forge_sha"] == fp.git("rev-parse", "%s:%s" % (c460["sha"], r["name"]),
                                            cwd=w460["path"]).strip() for r in r460), str(r460))
            ck("...and the build artifacts that were never committed are never stamped either",
               not any(is_build_artifact(r["name"]) for r in r460), str([r["name"] for r in r460]))
            # THE COLLISION (#457 round 2). The package's two `__init__.py` files are both EMPTY, so
            # git gives them ONE blob sha. A dedupe keyed on (ticket_id, forge_sha) alone reads the
            # second as the first stamped twice and drops it: the file lands in git and its PATH is
            # nowhere in the registry — the exact disease #457 exists to cure. The shared sha is
            # proven here from GIT's own answer (not asserted), so this check cannot pass by the
            # fixture quietly losing its collision.
            empties = [p for p in wrote460 if p.endswith("__init__.py")]
            eshas = {fp.git("rev-parse", "%s:%s" % (c460["sha"], p), cwd=w460["path"]).strip()
                     for p in empties}
            ck("...INCLUDING two DISTINCT paths that git stores as ONE blob (both `__init__.py` are "
               "empty): the key is (ticket_id, forge_sha, name), so a shared content address costs "
               "neither file its row",
               len(empties) == 2 and len(eshas) == 1
               and sorted(r["name"] for r in r460 if r["name"] in empties) == sorted(empties),
               "empties=%s shared_sha=%s rows=%s" % (empties, eshas, [r["name"] for r in r460]))
            ck("...and the name in the key NARROWS the dedupe without disabling it: re-stamping that "
               "same package commit mints NO second row for ANY of its files",
               fp.stamp_artifacts(460, c460)["recorded"] == []
               and sorted(r["name"] for r in gp.artifacts(460)) == wrote460,
               str([r["name"] for r in gp.artifacts(460)]))
            # a DELETION is in the commit's fileset but is not an artifact: there are no bytes.
            os.remove(os.path.join(w460["path"], pkg460, "config.json"))
            c460b = fp.commit_deliverable(460, pkg460 + "/add.py", "ticket #460: retire the config")
            ck("a DELETED file is in the commit but is NOT stamped (a deletion has no blob)",
               pkg460 + "/config.json" in c460b["files"]
               and not any(r["name"] == pkg460 + "/config.json" for r in gp.artifacts(460)[len(r460):])
               and any("no blob" in s for s in c460b["artifacts"]["skipped"]),
               "files=%s skipped=%s" % (c460b["files"], c460b["artifacts"]["skipped"]))
            fp.reap_worktree(460)

            # NEVER FATAL — the whole point of rule 2: instrumentation may not break the pipeline.
            def _down(route, obj=None, method=None):
                raise Unexpected("route %s failed: the registry is down" % route)

            fd = Forge(repo, api=_down)
            w461 = fd.open_worktree(461, base)
            open(os.path.join(w461["path"], "tools", "survives.py"), "w").write("survivor\n")
            ed, cd = attempt(fd.commit_deliverable, 461, "tools/survives.py", "ticket #461")
            ck("NEVER FATAL — a registry that refuses EVERY route does not fail the commit",
               not ed and cd and cd["committed"], ed or str(cd))
            ck("...the work is really on the branch (the round kept what it earned)",
               "tools/survives.py" in fd.git("show", "--name-only", "--format=", "ticket/461"))
            ck("...and the stamp failure is NAMED, never swallowed",
               bool(cd) and cd["artifacts"]["errors"] and not cd["artifacts"]["stamped"],
               str(cd["artifacts"]) if cd else "")
            ck("...and reaches the append-only JOURNAL, where a human can see the gap",
               "artifact stamp FAILED" in commit_note(1, "tools/survives.py", cd),
               commit_note(1, "tools/survives.py", cd))
            ck("...and stamp_artifacts() itself raises NOTHING, whatever the api does",
               attempt(fd.stamp_artifacts, 461, cd)[0] == "", attempt(fd.stamp_artifacts, 461, cd)[0])
            fd.reap_worktree(461)

            # ...and the narrower fault: the LIST works, one RECORD fails. The other files keep theirs.
            class _RecordDown(_StGov):
                def __call__(self, route, obj=None, method=None):
                    if route == ARTIFACT_RECORD_ROUTE and (obj or {}).get("name", "").endswith("helper.py"):
                        raise Unexpected("route %s failed: a 500 on this one row" % route)
                    return _StGov.__call__(self, route, obj, method)

            gr = _RecordDown(os.path.join(base_dir, "mint-partial.sqlite"))
            gr.ticket(462)
            fr = Forge(repo, api=gr)
            w462 = fr.open_worktree(462, base)
            pkg462 = "checkouts/current/forge2/partial_pkg"
            wrote462 = _st_forge_package(w462["path"], pkg462, "partial_pkg")
            e462, c462 = attempt(fr.commit_deliverable, 462, pkg462 + "/add.py", "ticket #462")
            got462 = sorted(r["name"] for r in gr.artifacts(462))
            ck("ONE row's failure costs only THAT row — the rest of the package is still stamped",
               not e462 and got462 == [p for p in wrote462 if not p.endswith("helper.py")], str(got462))
            ck("...and the one that failed is named on the record",
               bool(c462) and any("helper.py" in x for x in c462["artifacts"]["errors"]),
               str(c462["artifacts"]["errors"]) if c462 else "")
            fr.reap_worktree(462)

            # The bare git layer stamps nothing: no api seam, no registry to reach. This is what every
            # git check above constructs, which is why none of them needed a db.
            gn = _StGov(os.path.join(base_dir, "mint-none.sqlite"))
            gn.ticket(463)
            fn_ = Forge(repo)
            w463 = fn_.open_worktree(463, base)
            open(os.path.join(w463["path"], "tools", "unstamped.py"), "w").write("u\n")
            c463 = fn_.commit_deliverable(463, "tools/unstamped.py", "ticket #463")
            ck("a Forge with NO api seam commits and stamps nothing (the git layer, unchanged)",
               c463["committed"] and c463["artifacts"] == {"recorded": [], "skipped": [], "errors": [],
                                                           "stamped": False}, str(c463["artifacts"]))
            # ...and a commit that lands NOTHING still answers the caller with the same shape.
            c463b = fn_.commit_deliverable(463, "tools/unstamped.py", "ticket #463 again")
            ck("a commit that lands nothing still returns an artifacts record (no KeyError downstream)",
               c463b["committed"] is False and c463b["artifacts"]["recorded"] == []
               and commit_note(1, "tools/unstamped.py", c463b), str(c463b["artifacts"]))
            fn_.reap_worktree(463)

        # ── #457: THE DIRECTORY-SERVICE GATE — pinned against the REAL resolver.py ────────────────
        # #457's third gate asks that `resolver.py <forge_sha>` find a stamped row via the
        # forge-artifacts probe. It CANNOT today, for two reasons this file cannot fix from its own
        # deliverable — see THE DIRECTORY-SERVICE GATE in the module docstring. These pins make that
        # a CHECKED fact rather than a claim: read resolver.py's source (a pure read — importing it
        # would write a .pyc into this repo and break "--selftest writes nothing") and assert the two
        # facts. If either FAILS, resolver.py has changed and the gate may now be closable: that is
        # the signal to re-read the docstring and finish #457, not a defect in this file.
        print("-- #457: the directory-service gate, pinned against the real tools/resolver.py")
        rpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resolver.py")
        if not os.path.isfile(rpath):
            skip("#457 GATE: resolver.py's forge-artifacts probe still cannot see ticket_artifacts",
                 "no resolver.py beside this tool (%s)" % rpath)
            skip("#457 GATE: a git blob sha does not route to the forge-artifacts probe", rpath)
        else:
            rsrc = open(rpath).read()
            ck("#457 GATE (a): resolver.py DOES reference `ticket_artifacts` — the table "
               "artifact.record writes — so a stamped row is now a REAL match, not an invisible one. "
               "#461 (DONE, merged) CLOSED the directory-service gap this gate once pinned open: "
               "minting_tickets() reads `ticket_artifacts` in the congruency state db and joins it on "
               "the sha256 content address, so the tether from resolver.py to the mint table is "
               "CLOSED. FAIL here = resolver.py was silently UNWIRED from `ticket_artifacts`; re-read "
               "THE DIRECTORY-SERVICE GATE in this docstring — #461 must stay closed.",
               "ticket_artifacts" in rsrc
               and "SELECT id, ticket_id, kind FROM ticket_artifacts WHERE lower(forge_sha) = ?" in rsrc,
               "resolver.py no longer references ticket_artifacts=%s" % ("ticket_artifacts" not in rsrc))
            ck("#457 GATE (b): forge_sha is a 40-hex git blob sha, which resolver routes to kind "
               "`git-blob`, whose fan-out has no forge-artifacts probe (that probe fires only for a "
               "64-hex sha256). FAIL here = the fan-out changed; re-check the gate.",
               '"git-blob":  ["omni-blob", "store-occ", "memgraph-node", "git-object-db"]' in rsrc
               and '"sha256":    ["content-sha256", "forge-artifacts", "git-object-db"]' in rsrc,
               "probes_for() no longer reads as pinned — re-read resolver.probes_for()")
            print("        NOTE (#457): the stamp is minted and its forge_sha is a true git blob "
                  "address, but resolver.py cannot yet see ticket_artifacts. Closing the gate needs "
                  "a resolver.py change (probes_for('git-blob') += 'ticket-artifacts', plus a "
                  "SELECT name FROM ticket_artifacts WHERE lower(forge_sha)=? probe on the congruency "
                  "db it already opens) — NOT this ticket's deliverable. See the module docstring.")

        # step() must not file a Variant-A bug report for an outcome its caller handles. Checking that
        # must not file one EITHER, so bug_report is swapped for a recorder while these two run.
        filed, real_bug_report = [], bug_report
        globals()["bug_report"] = lambda fn, *aa, **kk: filed.append(fn)
        try:
            def silent():
                raise NoVerdict("nothing readable")

            def broken():
                raise RuntimeError("a real harness fault")
            # These two step names are deliberately self-explaining: step() prints "no result:"/
            # "FAILED:" for them, and an unlabelled "FAILED" in a passing selftest's output reads
            # like a real defect to anyone scanning it.
            try:
                step("selftest: a DELIBERATELY silent worker (expected)", silent, tolerate=NoVerdict)
                got = "RETURNED"
            except NoVerdict:
                got = "re-raised"
            ck("step(tolerate=NoVerdict) re-raises the outcome for its caller to absorb",
               got == "re-raised", got)
            ck("...and files NO bug report (a handled round outcome is not a Variant-A bug)",
               filed == [], str(filed))
            try:
                step("selftest: a DELIBERATE harness fault (expected)", broken, tolerate=NoVerdict)
            except RuntimeError:
                pass
            ck("...while an unhandled fault still files one (step's old behavior, kept)",
               filed == ["selftest: a DELIBERATE harness fault (expected)"], str(filed))
        finally:
            globals()["bug_report"] = real_bug_report
        ck("the real bug_report is restored after that swap", bug_report is real_bug_report)

        # ── the acceptance criterion itself: `pip install -e .` from the MERGED tree (opt-in) ──
        # LAST on purpose: it is the only step that touches the network, and pip writes an .egg-info
        # into the base tree it installs from — which the checks above must not see.
        if install_check_too:
            print("-- #409 acceptance: pip install -e . from the merged base tree (--install-check)")
            status, detail = install_check(base_dir, merged_pkg)
            if status == "SKIP":
                skip("`pip install -e .` succeeds from the merged tree", detail)
            else:
                ck("`pip install -e .` succeeds from the merged tree", status == "PASS", detail)
                if status == "PASS":
                    print("        %s" % detail)
            # And the reason the artifacts were excluded: the install just wrote an .egg-info into
            # the base tree. Because it was never committed, it is UNTRACKED — so the base tree has
            # no tracked drift and policy 3's #213 guard still lets the next ticket merge.
            ck("the install left the base tree free of TRACKED drift (#213 still mergeable)",
               f.tracked_dirty() == [], str(f.tracked_dirty()))

        ck("--selftest filed no bug report into this repo (the sink is unchanged, #153 in isolation)",
           sink_state() == sink_before, "%s: %s -> %s" % (sink, sink_before, sink_state()))

        bad = [n for n, ok, _ in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s%s"
              % (len(checks) - len(bad), len(checks),
                 "; %d skipped" % len(skips) if skips else "",
                 "" if not bad else "; FAILED: " + "; ".join(bad)))
        return 1 if bad else 0
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)
        # The claim has to track what actually ran: --install-check pip-installs, which reaches the
        # network, so the default's "the network was never touched" would be a lie on that path.
        print("== selftest == throwaway repo removed (nothing here was WRITTEN: the #439 checks only "
              "READ migrations/*.sql for the real rules and the live db via immutable=1, which "
              "creates no -wal/-shm sidecars, #153; %s)"
              % ("the network was used by --install-check's pip install, and nothing else"
                 if install_check_too else "the network was never touched"))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)   # progress visible when redirected (background runs)
    ap = argparse.ArgumentParser(description="agent-pair loop: worker acts on a ticket's own branch, adversary validates")
    ap.add_argument("--ticket", type=int, help="existing ticket id to run the pair on")
    ap.add_argument("--file", metavar="KIND", help="file a NEW ticket of this kind instead")
    ap.add_argument("--title"), ap.add_argument("--body", default=""), ap.add_argument("--component", default="congruency")
    ap.add_argument("--deliverable", help="repo-relative path the worker must produce")
    ap.add_argument("--rounds", type=int, default=2, help="max worker rounds before giving up")
    ap.add_argument("--timeout", type=int, default=480, help="seconds per agent spawn")
    ap.add_argument("--harvest", type=int, metavar="TICKET", help="retro-harvest a settled ticket's lesson, then exit")
    ap.add_argument("--dispatch", type=int, nargs="?", const=5, metavar="N",
                    help="dispatch-01 routes up to N queue tickets (default 5): decide run/skip/stop, then execute")
    ap.add_argument("--parallel", type=int, default=1, metavar="K",
                    help="with --dispatch: run up to K pairs CONCURRENTLY (default 1); each gets its own branch+worktree")
    ap.add_argument("--base", default=None, metavar="BRANCH",
                    help="branch to fork ticket/<id> from and merge back into (default: the repo's current branch)")
    ap.add_argument("--keep-worktree", action="store_true",
                    help="do not reap the worktree after a successful merge (debugging; the merge still happens)")
    ap.add_argument("--package-commit", choices=("auto", "on", "off"), default="auto", metavar="AUTO|ON|OFF",
                    help="what one round COMMITS (#409). auto (default): the deliverable's path decides — a "
                         "forge module (<...>/%s/<repo>/...) commits its WHOLE package directory so its "
                         "pyproject.toml/config/entry points land with it; every other deliverable (tags, "
                         "tools, docs) commits that one file alone. on: always commit the deliverable's "
                         "package (its own directory, if the path names no forge package). off: always "
                         "commit only the deliverable file." % PACKAGE_MARKER)
    ap.add_argument("--selftest", action="store_true",
                    help="prove the branch/worktree/commit/merge/reap flow in a THROWAWAY temp repo, plus "
                         "policy 9's assign->ACTIVE governance order against the REAL trigger executed "
                         "from migrations/0029 and policy 10's artifact stamp against the REAL routes "
                         "from migrations/0014, then exit (no api key, no server, no agents, no network; "
                         "this repo and the live db are READ, never written)")
    ap.add_argument("--install-check", action="store_true",
                    help="with --selftest only: also run a real `pip install -e .` on the forge package the "
                         "selftest merged, in a throwaway venv — #409's acceptance criterion. USES THE "
                         "NETWORK (pip fetches the build backend), which is why --selftest excludes it by "
                         "default; with no network it reports SKIP, not FAIL")
    ap.add_argument("--compile-playbook", action="store_true",
                    help="file a documentation ticket from ALL harvested lessons and run the pair on it")
    ap.add_argument("--playbook", default="docs/PLAYBOOK.md",
                    help="the audited playbook artifact: injected into worker prompts when present; the --compile-playbook deliverable")
    a = ap.parse_args()

    # ── selftest: needs no key and no server (it only READS the repo's migrations + the live db) ──
    if a.selftest:
        return selftest(install_check_too=a.install_check)
    if a.install_check:
        ap.error("--install-check only means anything with --selftest")

    if not API_KEY:
        raise Unexpected("no CONGRUENCY_API_KEY (secrets or env) — token routes need it")

    # ── harvest-only mode: file the lesson and exit ───────────────────────────
    if a.harvest:
        harvest_settled(a.harvest)
        return 0

    # ── dispatch mode: dispatch-01 routes the queue ───────────────────────────
    if a.dispatch:
        return do_dispatch(a)

    # ── compile mode: the playbook is itself a pair-audited deliverable ──────
    if a.compile_playbook:
        lessons = rows("lessons.recent", {})
        if not lessons:
            raise Unexpected("no harvested lessons yet — settle (or --harvest) some tickets first")
        a.file, a.deliverable = "documentation", a.playbook
        a.title = "Compile the playbook: audited lessons from settled tickets"
        a.body = ("Write %s: the playbook future workers read at birth. Distill the harvested lessons "
                  "below into actionable guidance — what adversaries catch, how workers avoid it. Group "
                  "by theme, keep each lesson checkable, cite the source ticket ids. Lessons:\n%s"
                  % (a.playbook, "\n".join("- [ticket #%s] %s" % (l["ticket_id"], l["note"]) for l in lessons)))

    # ── ticket: take it or file it ────────────────────────────────────────────
    if a.file:
        out = rest("ticket.create", {"component": a.component, "title": a.title or a.file,
                                     "severity": "normal", "body": a.body, "patch": ""})
        tid = int(out["rowid"])
        rest("ticket.kind", {"id": tid, "kind": a.file})
        print("== filed == ticket #%d (%s)" % (tid, a.file))
    elif a.ticket:
        tid = a.ticket
    else:
        ap.error("--ticket N or --file KIND required")
    if not a.deliverable:
        ap.error("--deliverable is required to run the pair")

    with urllib.request.urlopen(CONG + "/rest.php?api=tickets&id=%d" % tid, timeout=15) as r:
        tk = json.loads(r.read().decode()).get("row") or {}
    title, body, kind = tk.get("title", ""), tk.get("body", ""), tk.get("kind")
    if not kind:
        raise Unexpected("ticket #%s has no kind — set it via ticket.kind first" % tid)

    kinds = {k["kind"]: k for k in rows("kind.roster", {})}
    if kinds.get(kind, {}).get("pattern") != "pair":
        raise Unexpected("ticket #%s kind %r is not a pair kind — the loop harnesses pairs" % (tid, kind))
    w_role, a_role = kinds[kind]["worker_role"], kinds[kind]["adversary_role"]

    # ── brake ─────────────────────────────────────────────────────────────────
    stops = rows("ticket.stops", {"ticket_id": tid})[0]["active_stops"]
    if int(stops) > 0:
        print("== HALT == %s active stop ticket(s) aim at #%s — the ticket authorizes nothing" % (stops, tid))
        return 3
    print("== brake == no active stops on #%s" % tid)

    # ── i1: open the ticket's branch in its own worktree; the pair works THERE ──
    forge = forge_for()
    base = a.base or forge.current_branch()
    fid = forge_agent(tid)
    wt = step("branch: %s" % forge.branch_of(tid), forge.open_worktree, tid, base)
    rest("ticket.progress", {"ticket_id": tid, "agent_id": fid,
                             "note": "branch %s %s off %s; worktree %s"
                                     % (wt["branch"], "opened" if wt["created"] else "reopened (resumed)",
                                        base, os.path.relpath(wt["path"], ROOT))})
    workspace = WORKSPACE % {"branch": wt["branch"]}

    pb = os.path.join(wt["path"], a.playbook)
    pb_line = ("\nBefore starting, read %s — the AUDITED playbook of lessons harvested from prior "
               "tickets. Apply what applies.\n" % a.playbook) if os.path.isfile(pb) else ""

    # #409: ONE package root decides all three of — what the worker is told to build, what the
    # adversary is told to judge, and what the commit stages. Resolved once, here, from the same
    # forge + --package-commit gate commit_deliverable() will use, so the three cannot disagree.
    pkg = forge.package_root(a.deliverable, a.package_commit)
    print("== scope == %s" % ("PACKAGE %s/ — the whole package is committed each round (#409)" % pkg
                              if pkg else "single file %s (unchanged)" % a.deliverable))

    gov = Gov(tid)
    findings, history = [], []
    for rnd in range(1, a.rounds + 1):
        worker = "%s-t%dr%d" % (w_role, tid, rnd)
        auditor = "%s-t%dr%d" % (a_role, tid, rnd)
        focus = FOCUS.get(kind, FOCUS["documentation"])
        ctx = dict(tid=tid, kind=kind, title=title, body=body, deliverable=a.deliverable, playbook=pb_line,
                   workspace=workspace, branch=wt["branch"],
                   worker_scope=worker_scope(a.deliverable, pkg), auditor_scope=auditor_scope(a.deliverable, pkg),
                   worker_focus=focus["worker_focus"], audit_focus=focus["audit_focus"])

        # The worker's birth prompt, rendered ONCE: Gov.enlist registers this exact string and the
        # spawn below runs on it, so the recorded birth and the real one are the same object.
        fx = "\nPrior adversary findings to address:\n- " + "\n- ".join(findings) + "\n" if findings else ""
        wp = WORKER_PROMPT % {**ctx, "agent": worker, "role": w_role, "findings": fx}

        # Open the round: a FRESH worker enlisted at ITS spawn, and only THEN the ticket ACTIVE
        # (policy 9). open_round() owns that order and --selftest drives it; the adversary is
        # enlisted further down, at its own spawn, for the same reason.
        step("pair (round %d)" % rnd, open_round, gov, worker, w_role, wp, wt["branch"])

        try:
            wres = worker_done(step("work: %s" % worker, spawn_claude, wp, focus["worker_tools"],
                                    a.timeout, wt["path"], tolerate=NoVerdict))
        except NoVerdict as e:
            # The worker said nothing the harness can act on. That FAILS THE ROUND and nothing more:
            # there is no reported deliverable to commit and nothing an adversary could judge, so the
            # round ends here. The worktree PERSISTS with whatever the worker did write, and the next
            # round's FRESH worker inherits it plus a finding telling it what went wrong. Only when
            # the rounds run out does the loop give up (exit 1) — the pair never crashes over this.
            # What happens NEXT depends on whether a round is left, so say the true one: claiming a
            # respawn that the loop is about to skip would write a falsehood onto an append-only
            # journal that no one can ever correct.
            nxt = ("a fresh worker runs the next round" if rnd < a.rounds
                   else "no rounds remain, so the loop gives up and the ticket stays open")
            rest("ticket.progress", {"ticket_id": tid, "agent_id": fid, "steps_remaining": 3,
                                     "note": "round %d: worker %s produced no usable result (%s). Round "
                                             "FAILED; nothing committed (no deliverable was reported). "
                                             "Worktree %s persists with whatever was written; %s."
                                             % (rnd, worker, e, wt["branch"], nxt)})
            findings = ["Your predecessor produced NO usable result: %s. It was born with the same "
                        "prompt as you. Anything it wrote is still in the worktree — read the "
                        "deliverable, finish it, and make ABSOLUTELY SURE your final output ends "
                        "with the required one-line JSON object as the VERY LAST line, with nothing "
                        "printed after it." % e]
            history.append({"round": rnd, "findings": findings})
            print("== round %d failed == worker %s produced no usable result (%s); %s"
                  % (rnd, worker, e, nxt))
            continue
        rest("ticket.progress", {"ticket_id": tid, "agent_id": worker,
                                 "note": "round %d: produced %s — %s" % (rnd, wres.get("ref"), wres.get("note", "")),
                                 "steps_remaining": 2})

        # i1: the work is COMMITTED on the ticket's branch — always, every round (#213). Its scope is
        # the deliverable, or the deliverable's whole package for a forge unit (#409, policy 8).
        cm = step("commit: %s" % wt["branch"], forge.commit_deliverable, tid, a.deliverable,
                  "ticket #%d: %s\n\n%s\n\nRound %d on %s; worker %s; deliverable %s"
                  % (tid, (title or "")[:64], wres.get("note", ""), rnd, wt["branch"], worker, a.deliverable),
                  a.package_commit)
        rest("ticket.progress", {"ticket_id": tid, "agent_id": fid,
                                 "note": commit_note(rnd, a.deliverable, cm)})

        # The adversary, enlisted at ITS spawn (lazy, like the worker) and never before the work it
        # judges exists. Its assign is also what lets the ticket reach DONE below: the db demands two
        # distinct agents in two distinct roles (tg_tickets_pair_completion), which is satisfied here,
        # by the pair actually running — not by anything registered up front on speculation.
        aprompt = AUDITOR_PROMPT % {**ctx, "agent": auditor, "role": a_role}
        step("adversary (round %d)" % rnd, gov.enlist, auditor, a_role, aprompt)
        vres = step("validate: %s" % auditor, spawn_claude, aprompt, focus["auditor_tools"], a.timeout, wt["path"])
        rest("ticket.progress", {"ticket_id": tid, "agent_id": auditor,
                                 "note": "round %d verdict: %s%s" % (rnd, vres.get("verdict"),
                                        ("; findings: " + "; ".join(vres.get("findings", []))) if vres.get("findings") else ""),
                                 "steps_remaining": 1 if vres.get("verdict") == "pass" else 3})

        if vres.get("verdict") == "pass":
            # ── i2: settle — MERGE first; DONE only if the branch actually landed. "Landed" is
            # merge_to_base's post-state (a real merge commit), never git's exit code: a branch with
            # no commits merges "successfully" while moving nothing, and a pass on top of THAT must
            # not mint a UID or a DONE. Every non-ok reason (conflict, drift, empty branch) exits 4
            # with the branch and worktree intact.
            mg = step("merge: %s -> %s" % (wt["branch"], base), forge.merge_to_base, tid, base,
                      "merge %s: ticket #%d — %s\n\n%s"
                      % (wt["branch"], tid, (title or "")[:64], wres.get("note", "")))
            if not mg.get("ok"):
                rest("ticket.progress", {"ticket_id": tid, "agent_id": fid,
                                         "note": "MERGE REFUSED: %s. Branch %s and its worktree PERSIST; the "
                                                 "ticket stays open — resolve and re-run."
                                                 % (mg.get("reason"), wt["branch"]), "steps_remaining": 2})
                print("== not settled == #%s passed review but %s — branch %s kept, worktree kept, ticket stays open"
                      % (tid, mg.get("reason"), wt["branch"]))
                harvest(tid, history + [{"round": rnd, "findings": ["merge blocked: %s" % mg.get("reason")]}],
                        False, "")
                return 4
            history.append({"round": rnd, "findings": []})
            # The manifest's permanent UID covers what LANDED, so the note names it: for a forge unit
            # that is the package and its fileset, not the one module the ref points at (#409).
            landed = ("package %s/ (%s)" % (cm["package"], ", ".join(cm["files"]))) if cm["package"] else wres.get("ref", a.deliverable)
            rest("work.record", {"ticket_id": tid, "kind": "doc" if kind == "documentation" else "code",
                                 "ref": wres.get("ref", a.deliverable),
                                 "note": "%s [landed %s; %s @ %s merged to %s @ %s]"
                                         % (wres.get("note", ""), landed, wt["branch"], cm["sha"][:10],
                                            base, mg["sha"][:10])})
            rest("ticket.progress", {"ticket_id": tid, "agent_id": fid,
                                     "note": "MERGED %s -> %s (--no-ff): %d commit(s) landed in merge commit %s "
                                             "(base was %s); branch kept as the ticket's trace"
                                             % (wt["branch"], base, mg.get("ahead", 0), mg["sha"][:10],
                                                mg["was"][:10])})
            rest("process_status", {"id": tid, "status": "DONE"})  # db refuses without the pair
            reaped = False if a.keep_worktree else step("reap: worktree", forge.reap_worktree, tid)
            rest("ticket.progress", {"ticket_id": tid, "agent_id": fid,
                                     "note": "worktree %s (base tree clean, #213/#216)"
                                             % ("reaped" if reaped else "KEPT (--keep-worktree)")})
            rest("ticket.progress", {"ticket_id": tid, "agent_id": auditor,
                                     "note": "PASS — manifest updated, ticket DONE; pair retired (fresh agents next iteration)",
                                     "steps_remaining": 0})
            print("== settled == ticket #%s DONE (round %d) — %s committed on %s @ %s, merged to %s @ %s; "
                  "worktree %s; deliverable carries a permanent UID"
                  % (tid, rnd, wres.get("ref"), wt["branch"], cm["sha"][:10], base, mg["sha"][:10],
                     "reaped" if reaped else "kept"))
            harvest(tid, history, True, wres.get("note", ""))
            return 0
        findings = vres.get("findings", ["(none given)"])
        history.append({"round": rnd, "findings": findings})
        print("== round %d failed == %d finding(s); respawning a FRESH worker on %s"
              % (rnd, len(findings), wt["branch"]))

    print("== gave up == %d rounds exhausted on #%s; findings journaled, status stays ACTIVE. Branch %s "
          "and its worktree persist (nothing merged, nothing lost)." % (a.rounds, tid, wt["branch"]))
    rest("ticket.progress", {"ticket_id": tid, "agent_id": fid,
                             "note": "rounds exhausted — branch %s and worktree kept unmerged; ticket stays open"
                                     % wt["branch"]})
    harvest(tid, history, False, "")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Unexpected as e:
        bug_report("main", e, "python3 pair_loop.py " + " ".join(sys.argv[1:]), e)
        print("UNEXPECTED: %s" % e)
        sys.exit(2)
