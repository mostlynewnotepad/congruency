#!/usr/bin/env python3
"""pair_loop.py — the agent-pair loop, BRANCH-PER-TICKET: a ticket authorizes a worker; its
counterpart validates; the work lives on the ticket's own branch until it is merged.

One iteration of the adversarial network, harnessed:

    1. BRAKE     ticket.stops — an active (unreleased) stop ticket aimed at the target or any
                 ancestor halts the loop before anything acts.
    2. OPEN      create branch `ticket/<id>` off the base branch and check it out in a dedicated
                 git WORKTREE (a second working directory driven by the same .git, so the base
                 tree is never touched). The pair runs with its cwd IN that worktree.
    3. PAIR      register a FRESH worker + adversary for this ticket/round (agent.register, full
                 birth prompts) and authorize both on the ticket (ticket.assign). Fresh spawns ARE
                 the memory clear: a new agent has no context; the OLD agents' trails stay on the
                 record forever (the journal is append-only — nothing is erased).
    4. WORK      spawn the worker (`claude -p`, tools limited to reading + writing the deliverable)
                 in the worktree; it reports {"done":true,"ref":...} on its last line. The HARNESS
                 then COMMITS the deliverable onto `ticket/<id>` (the worker holds no git pen).
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
    python3 pair_loop.py --selftest                                # prove the git layer; no db, no agents
    ... [--rounds 2] [--timeout 480] [--base main] [--keep-worktree]

--selftest builds a THROWAWAY git repo in a temp dir, runs the whole branch/worktree/commit/merge/
reap flow through it (including two pairs in parallel and a deliberate merge conflict), then deletes
it. It never touches this repo, the db, or the network, and spawns no agents.

Exit codes:
    0  settled — the branch merged into the base and the ticket is DONE (--selftest: all checks passed)
    1  rounds exhausted — the adversary never passed; branch + worktree kept, ticket stays open
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


# ── the forge: branch-per-ticket git, scoped to one repo (so --selftest can drive a throwaway) ────
class Forge:
    """Every git act the branch-per-ticket flow performs, against one repo root.

    A WORKTREE is a second working directory driven by the same .git: `git worktree add` checks a
    branch out somewhere else on disk, so two pairs can hold two branches checked out at once with
    no contention — which a single working tree cannot do.

    Shared-.git mutations (worktree add/remove/prune, merge) are serialized across PROCESSES by an
    flock, so parallel pairs never race. Never nest lock() inside lock(): flock on a second open
    file description of the same file blocks the same process (self-deadlock).
    """

    def __init__(self, root, worktrees=None):
        self.root = os.path.abspath(root)
        wt = worktrees or os.path.join(".git", "pair-worktrees")
        self.worktrees = wt if os.path.isabs(wt) else os.path.join(self.root, wt)
        self.lockfile = os.path.join(self.root, ".git", "pair-loop.lock")

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

    def porcelain(self, cwd=None):
        """`git status --porcelain -z` parsed into [(xy, path)]; paths are repo-relative and RAW.

        -z, never the plain form. In plain `--porcelain`, git C-QUOTES any path holding a space,
        a quote, or a non-ascii byte — `docs/naïve.md` is printed as `"docs/na\\303\\257ve.md"`
        (escapes and surrounding quotes included) — so a raw compare of that text against a real
        path silently MISSES it. `-z` is defined to emit each path verbatim, NUL-separated, and
        never quotes; that is the whole reason it exists. Rename/copy entries ('R'/'C') carry a
        SECOND NUL field (the source path); it is consumed here so it can never be mistaken for
        an entry of its own.
        """
        raw = self.git("status", "--porcelain", "-z", cwd=cwd).split("\0")
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
    def commit_deliverable(self, tid, deliverable, message):
        """Stage ONLY the deliverable and commit it on the ticket's branch.

        Only the deliverable: the worker's mandate is "create or overwrite that file; touch nothing
        else", so `add -A` would sweep in anything else the worktree happens to hold. Anything else
        that IS dirty is returned as `strays` so the caller can put it on the record rather than let
        it vanish unmentioned at reap time.

        A stray is every dirty path that is NOT the deliverable, and deciding "is not the
        deliverable" is a PATH comparison, not a string comparison — get it wrong in the false-
        positive direction and the caller journals, permanently and append-only, that the delivered
        file was abandoned uncommitted. Two ways the naive compare lies, both proven in --selftest:
        git C-quotes exotic paths in plain `--porcelain` (hence porcelain()'s -z), and one path has
        many spellings (`./docs/x.md` and `docs/x.md` are the same file; git prints the second).
        So: raw paths from -z, os.path.normpath applied to BOTH sides.
        """
        wt = self.worktree_of(tid)
        if not os.path.isfile(os.path.join(wt, deliverable)):
            raise Unexpected("no deliverable at %s in the worktree %s — the worker reported done "
                             "but produced no file" % (deliverable, wt))
        self.git("add", "--", deliverable, cwd=wt)
        want = os.path.normpath(deliverable)
        strays = [p for _, p in self.porcelain(cwd=wt) if os.path.normpath(p) != want]
        if not self.git("diff", "--cached", "--name-only", cwd=wt).strip():
            return {"committed": False, "sha": self.head(wt), "branch": self.branch_of(tid), "strays": strays}
        self.git("commit", "--quiet", "-m", message, cwd=wt)
        return {"committed": True, "sha": self.head(wt), "branch": self.branch_of(tid), "strays": strays}

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
    cfg = (REGISTRY.get("branch_per_ticket") or {}).get("worktrees")
    return Forge(root or ROOT, worktrees=cfg)


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

Deliverable: write it to %(deliverable)s (create or overwrite that file; touch nothing else).
%(worker_focus)s Your counterpart will adversarially audit this with no access to your
reasoning, so the artifact must stand alone.
%(workspace)s%(playbook)s%(findings)s
When the deliverable is written, print as your LAST line:
{"done": true, "ref": "%(deliverable)s", "note": "<one line on what you produced>"}
""" + GOVERNANCE

AUDITOR_PROMPT = """You are %(agent)s, the %(role)s — the adversary of a %(kind)s pair on ticket #%(tid)s.

TICKET: %(title)s
%(body)s

The worker produced %(deliverable)s. You did NOT see the worker's reasoning — judge the artifact
alone: no context, no charity. %(audit_focus)s Nitpicks are not findings.
%(workspace)s
Print as your LAST line:
{"verdict": "pass", "findings": []}   or   {"verdict": "fail", "findings": ["<finding>", ...]}
""" + GOVERNANCE


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


def spawn_claude(prompt, allowed_tools, timeout, cwd=None):
    """One fresh-context agent run, IN the ticket's worktree. Fresh spawn = clean memory; the db
    keeps the durable trail."""
    try:
        r = subprocess.run(["claude", "-p", prompt, "--allowedTools", allowed_tools],
                           cwd=cwd or ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # a spawn overrunning its budget is a ROUND OUTCOME, not a harness crash — journal + bug-report
        raise Unexpected("agent spawn exceeded its %ss budget (raise --timeout for heavier tickets)" % timeout)
    if r.returncode != 0:
        raise Unexpected("claude exited %s: %s" % (r.returncode, (r.stderr or r.stdout).strip()[-300:]))
    for line in reversed((r.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    raise Unexpected("no JSON verdict on the agent's last line; tail: %r" % (r.stdout or "")[-200:])


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
           "--deliverable", deliverable, "--rounds", str(a.rounds), "--timeout", str(a.timeout)]
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


def step(name, fn, *a, **kw):
    t0 = time.time()
    try:
        out = fn(*a, **kw)
        print("== %s ==\n   ok (%d ms) %s" % (name, (time.time() - t0) * 1000, out if out is not None else ""))
        return out
    except Exception as e:  # noqa: BLE001
        bug_report(name, e, "python3 pair_loop.py (step: %s)" % name, e)
        print("== %s ==\n   FAILED: %s" % (name, e))
        raise


# ── --selftest: prove the git layer end-to-end in a THROWAWAY repo (no db, no agents, no network) ──
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


def selftest():
    """Drive the whole branch-per-ticket flow against a temp repo and CHECK each acceptance claim.
    Prints one PASS/FAIL line per check; returns 0 only if every check passed."""
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name, ("  — %s" % detail) if detail and not cond else ""))

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

        bad = [n for n, ok, _ in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s"
              % (len(checks) - len(bad), len(checks), "" if not bad else "; FAILED: " + "; ".join(bad)))
        return 1 if bad else 0
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)
        print("== selftest == throwaway repo removed (this repo, the db and the network were never touched)")


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
    ap.add_argument("--selftest", action="store_true",
                    help="prove the branch/worktree/commit/merge/reap flow in a THROWAWAY temp repo, then exit "
                         "(no db, no agents, no network; this repo is not touched)")
    ap.add_argument("--compile-playbook", action="store_true",
                    help="file a documentation ticket from ALL harvested lessons and run the pair on it")
    ap.add_argument("--playbook", default="docs/PLAYBOOK.md",
                    help="the audited playbook artifact: injected into worker prompts when present; the --compile-playbook deliverable")
    a = ap.parse_args()

    # ── selftest: needs no key, no server, no db ──────────────────────────────
    if a.selftest:
        return selftest()

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

    findings, history = [], []
    for rnd in range(1, a.rounds + 1):
        worker = "%s-t%dr%d" % (w_role, tid, rnd)
        auditor = "%s-t%dr%d" % (a_role, tid, rnd)
        focus = FOCUS.get(kind, FOCUS["documentation"])
        ctx = dict(tid=tid, kind=kind, title=title, body=body, deliverable=a.deliverable, playbook=pb_line,
                   workspace=workspace, branch=wt["branch"],
                   worker_focus=focus["worker_focus"], audit_focus=focus["audit_focus"])

        # fresh pair, registered + authorized (fresh spawn = cleared memory; trails persist)
        def pair():
            for agent, role, tmpl in ((worker, w_role, WORKER_PROMPT), (auditor, a_role, AUDITOR_PROMPT)):
                fx = "\nPrior adversary findings to address:\n- " + "\n- ".join(findings) + "\n" if (findings and role == w_role) else ""
                rest("agent.register", {"agent_id": agent, "parent": "pair_loop",
                                        "prompt": tmpl % {**ctx, "agent": agent, "role": role, "findings": fx},
                                        "tools": json.dumps(["claude -p"])})
                rest("ticket.assign", {"ticket_id": tid, "agent_id": agent, "role": role})
            rest("process_status", {"id": tid, "status": "ACTIVE"})
            return {"worker": worker, "auditor": auditor, "branch": wt["branch"]}
        step("pair (round %d)" % rnd, pair)

        fx = "\nPrior adversary findings to address:\n- " + "\n- ".join(findings) + "\n" if findings else ""
        wp = WORKER_PROMPT % {**ctx, "agent": worker, "role": w_role, "findings": fx}
        wres = step("work: %s" % worker, spawn_claude, wp, focus["worker_tools"], a.timeout, wt["path"])
        if not wres.get("done"):
            raise Unexpected("worker did not report done: %s" % wres)
        rest("ticket.progress", {"ticket_id": tid, "agent_id": worker,
                                 "note": "round %d: produced %s — %s" % (rnd, wres.get("ref"), wres.get("note", "")),
                                 "steps_remaining": 2})

        # i1: the deliverable is COMMITTED on the ticket's branch — always, every round (#213)
        cm = step("commit: %s" % wt["branch"], forge.commit_deliverable, tid, a.deliverable,
                  "ticket #%d: %s\n\n%s\n\nRound %d on %s; worker %s; deliverable %s"
                  % (tid, (title or "")[:64], wres.get("note", ""), rnd, wt["branch"], worker, a.deliverable))
        rest("ticket.progress", {"ticket_id": tid, "agent_id": fid,
                                 "note": "round %d: %s on %s @ %s%s"
                                         % (rnd, "committed %s" % a.deliverable if cm["committed"]
                                            else "no change to commit for %s" % a.deliverable,
                                            wt["branch"], cm["sha"][:10],
                                            ("; UNCOMMITTED strays left in the worktree (the mandate forbids "
                                             "them; they will not survive the reap): " + ", ".join(cm["strays"][:5]))
                                            if cm["strays"] else "")})

        aprompt = AUDITOR_PROMPT % {**ctx, "agent": auditor, "role": a_role}
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
            rest("work.record", {"ticket_id": tid, "kind": "doc" if kind == "documentation" else "code",
                                 "ref": wres.get("ref", a.deliverable),
                                 "note": "%s [%s @ %s merged to %s @ %s]"
                                         % (wres.get("note", ""), wt["branch"], cm["sha"][:10], base, mg["sha"][:10])})
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
