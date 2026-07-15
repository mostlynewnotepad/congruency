#!/usr/bin/env python3
"""clean_recheckout.py — POLICY 1: after a build commits, the working tree IS a CLEAN CHECKOUT of
that commit. Tree == HEAD, 100% of the time (ticket #214).

THE POLICY, quoted from ticket #214, which is its only source in this repository (nothing else here
defines it — do not go looking): "After any build/mint commits code, automatically materialize a
CLEAN checkout of that commit (git checkout <ref> into a clean tree; no untracked/modified drift) so
the working tree == HEAD, 100% of the time ... Add a guard that FAILS a build if it leaves the tree
dirty relative to the commit (the anti-stale invariant) ... a build that leaves drift is refused."

  !! THE NUMBER IS AMBIGUOUS IN THIS REPO — READ THIS ONCE AND THE CONFUSION IS GONE. "POLICY 1"
  here is TICKET #214's numbering. It is NOT pair_loop.py's policy (1), which is branch NAMING
  ("(1) NAMING — `ticket/<id>`, deterministic from the ticket id alone", pair_loop.py:39). The two
  numbering schemes are unrelated. This file implements #214's, and cites pair_loop's own policies
  by their full name ("pair_loop's policy 3") whenever it refers to them.

TERMS, each defined at first use, because whoever reads this file did not watch it being written:

  * A REF is any git revision spelling: a sha, a branch, a tag, "HEAD". THE REF this policy is about
    is the commit a build just made — HEAD.
  * TRACKED means git has the file in its index/commit. UNTRACKED means the file is on disk and git
    does not have it. IGNORED means .gitignore names it — see THE IGNORED-FILE RULE, which is the
    most safety-critical paragraph in this file.
  * DRIFT is any difference between the working tree and the ref: a tracked file MODIFIED or DELETED
    since the commit, a file STAGED in the index but never committed, or an UNTRACKED file the commit
    does not contain. An untracked file left by a build is the STALE FILE the anti-stale invariant
    is named for: the build produced something and did not commit it, so the tree no longer says what
    the commit says.
  * A CLEAN CHECKOUT of a ref is a tree with ZERO drift: every tracked file byte-identical to the
    ref, nothing missing, nothing staged, no untracked leftovers. "git status is clean" is a WEAKER
    claim than this one and is not what this file checks — see THE IGNORED-FILE RULE.

WHY THE INVARIANT EXISTS (the failure it prevents). A build that commits and then leaves artifacts
behind makes the tree and the commit disagree. Every later reader — the next build, the installer,
a `git checkout`, a human — sees the tree, and the tree is now a lie about what was captured. The
next mint then either sweeps those leftovers into a commit that claims to be a different change, or
trips its own precondition and refuses. mint_crank.py already hits the SECOND half of this: it
refuses to mint unless the tree is tracked-clean ("tree has uncommitted tracked changes; refusing to
mint", mint_crank.py:135, guarding on the dirty list built at mint_crank.py:132). pair_loop.py hits
it too and names the same ticket: its merge refuses a base tree with uncommitted tracked changes
("#213: never merge into a drifted tree", pair_loop.py:548-552, on the list from tracked_dirty(),
pair_loop.py:386-389). Both of those are DOWNSTREAM defenses — they refuse to act on a tree someone
else already dirtied. This file is the UPSTREAM one: it makes the build that dirtied it the thing
that fails, at the moment it did it, while the culprit is still known.

WHAT THIS FILE DOES — three modes, one invariant.

  1. THE GUARD (--check, the default). Audits the tree against the ref and answers one question:
     is this a clean checkout? Exit 0 yes, exit 3 no, and on no it NAMES every drifting path.
     READ-ONLY: it runs only `git rev-parse`, `git diff` and `git status`, creates no file, moves
     no ref, and writes nothing. --selftest proves that by listing the tree and .git before and
     after (see the read-only check).
  2. THE ENFORCEMENT (--enforce). Materializes the clean checkout: PRESERVE the drift, then bring
     the index and the tree back to the ref, then RE-AUDIT and prove tree == ref. See PRESERVE
     FIRST below — this mode discards drift from the tree, and it is the reason the default is the
     guard and not this.
  3. THE WIRE (`-- <build command...>`). Runs ANY build command and then applies the policy to what
     it left. This is how #214's "wired into mint_crank.py and the pair-loop settle path and any
     build tool" is satisfied by a file that is only allowed to be itself — see THE WIRE below.

PRESERVE FIRST — how enforcement obeys "produce, don't erase". Materializing a clean checkout means
the drift leaves the tree, and drift is uncommitted content: discarding it is destroying work. This
repo's governance is append-only ("History is append-only: never delete or rewrite anything that
exists; produce, don't erase", pair_loop.py:604-605). So --enforce never discards anything it has
not first PRESERVED as a real git object:

    GIT_INDEX_FILE=<temp>  git add -A .      # a snapshot of the whole drifted tree, in a temp index
                           git write-tree     # -> that tree object
                           git commit-tree    # -> a commit holding it, parented on the ref
                           git update-ref refs/policy1/drift/<stamp>   # -> a PERMANENT ref

The drift becomes a commit under `refs/policy1/drift/<stamp>`, parented on the build's own commit.
It is a ref, not a dangling object, so `git gc` will never reclaim it and nothing is on a clock.
Recover it with `git diff <ref> refs/policy1/drift/<stamp>` to read it, or `git checkout
refs/policy1/drift/<stamp> -- .` to put it all back. The ref name is printed on every enforcement
and is the receipt. Nothing is erased; the tree is restored and the drift is filed.

THE IGNORED-FILE RULE — the paragraph to read before changing anything in this file. IGNORED FILES
ARE NOT DRIFT AND ARE NEVER TOUCHED. .gitignore is the repo's own written declaration that a path is
not part of any commit and is regenerated by running things; pair_loop.py says exactly that about
the same class of file ("every one of these is REGENERATED by the act of building or validating a
package", pair_loop.py:228-233). Sweeping them is not enforcement, it is demolition. In THIS repo
the ignored set (.gitignore, repo root) includes:

    *.sqlite  /checkouts/current/state/congruency.sqlite   <- THE STATE DATABASE
    /tooling/congruencey-harness/php/                      <- the provisioned PHP the verify suite runs
    logs/                                                  <- the bug-report sink every tool writes to
    congruency-pair-worktrees/                             <- LIVE PAIR WORKTREES, mid-ticket
    __pycache__/  *.pyc  .claude/  /checkouts/current/install.json  ...

`git clean -fdx` would delete every one of those: the database, the PHP runtime, the logs, and the
working directories of every pair currently running. This file therefore NEVER runs `git clean` at
all. It removes exactly the untracked paths its own audit NAMED — one by one, each re-checked to be
repo-relative, inside the root, and outside `.git` — so the set removed is always identical to the
set reported, and can never be a surprise. --selftest proves the ignored set survives enforcement.

HOW THE TREE IS MATERIALIZED, and one thing this file will not do. Restoring the tree to the ref is
`git read-tree --reset -u <ref>`: it resets the INDEX to the ref and updates the WORKING TREE to
match, which restores modified files, restores deleted ones, and removes a file that was staged but
never committed. It does NOT move HEAD. `git reset --hard` would do the same to the tree AND move
the branch pointer — rewriting the ref the build just made. That is exactly the erasure the
governance forbids, so this file never calls it, and --selftest asserts HEAD is unmoved after every
enforcement.

THE WIRE — how one file wires into flows it is forbidden to edit. #214 asks for the policy to be
wired into mint_crank.py, the pair-loop settle path, and any build tool; #214's deliverable line
also says to write this file and "touch nothing else". Both are honored, and the honest statement of
where things stand is this:

  * NOT YET IMPORTED. As of this commit, mint_crank.py and pair_loop.py do NOT import this module.
    They are not this ticket's deliverable and editing them is outside what it authorized. Do not
    read any claim here as saying otherwise.
  * WIRED TODAY, WITHOUT EDITS, via the command wire. `-- <cmd>` wraps any build tool — that is a
    working wire for every build flow right now, requiring no change to any of them:

        python3 tools/clean_recheckout.py -- python3 tools/mint_crank.py --no-patch --no-state -m "..."
        python3 tools/clean_recheckout.py --enforce -- python3 tools/pair_loop.py --ticket 251 --deliverable docs/X.md
        python3 tools/clean_recheckout.py -- <any build tool at all>

    The wrapper is build-tool agnostic on purpose: it knows nothing about mint_crank or pair_loop,
    only about git, so "any build tool" is not a promise about a list this file has to keep current.
  * WIRED IN-PROCESS, when a ticket may edit those files, via the importable API. One line each,
    and the two call sites are named here so the future edit is mechanical rather than archaeology:

        from clean_recheckout import enforce_policy1     # or guard_policy1 for check-only

        # mint_crank.py — after the capture step commits + tags (the `do("capture (commit + tag)",
        # lambda: step_capture(message, version))` at mint_crank.py:422), before verify at :423:
        do("policy 1 (clean re-checkout)", lambda: enforce_policy1(ROOT))

        # pair_loop.py — in the settle path, after the merge is proven real (the `mg = step("merge:
        # ...", forge.merge_to_base, ...)` at pair_loop.py:1588 and its `if not mg.get("ok")` guard):
        step("policy 1 (clean re-checkout)", enforce_policy1, forge.root)

    enforce_policy1() raises Unexpected on drift, which is precisely what both flows already do with
    a failed step: mint_crank's do() files a Variant-A bug report and re-raises (mint_crank.py:392-404),
    and pair_loop's step() does the same (pair_loop.py:902-911).

EXIT CODES (the CLI's whole contract):
    0  POLICY 1 HOLDS — the tree is a clean checkout of the ref. Under the wire, the build also
       succeeded (and, with --require-commit, actually committed).
    1  the wrapped build command FAILED — but read this precisely: the build's OWN exit code is
       propagated verbatim, so a build that exits 7 makes this tool exit 7, and this code is seen
       only when the build itself exited 1. What is guaranteed is non-zero, not the digit. Either
       way the tree is audited and REPORTED but never enforced: a failed build's tree is evidence,
       and destroying evidence to satisfy a policy about successful builds helps nobody.
    2  UNEXPECTED — a Variant-A bug report was filed to the registry's bug_reports sink
       (note-for-claude: filename, function, time-of-occurance, methods-to-reproduce, possible-cause).
       Also argparse's own exit for a USAGE refusal — `--enforce --ref <not-HEAD>` is refused here,
       with a one-line reason and NO bug report, because it is a misuse and not a fault.
    3  REFUSED — drift. The anti-stale invariant is violated: the build left the tree dirty relative
       to its own commit. With --enforce the drift was preserved and the tree materialized clean
       FIRST, and the exit is STILL 3 — repairing the tree does not make the build compliant, and
       "a build that leaves drift is refused" is the acceptance criterion, not "is quietly fixed".

USAGE (python only, per note-for-claude; registry-gated — a tool that cannot see registry.json throws):
    python3 clean_recheckout.py                       # guard THIS repo's tree against HEAD (read-only)
    python3 clean_recheckout.py --ref <sha>           # ...against another commit (read-only)
    python3 clean_recheckout.py --enforce             # materialize the clean checkout of HEAD
    python3 clean_recheckout.py -- <build cmd...>     # THE WIRE: run a build, then guard what it left
    python3 clean_recheckout.py --enforce --require-commit -- <build cmd...>   # the full #214 form
    python3 clean_recheckout.py --json                # machine-readable audit for any of the above
    python3 clean_recheckout.py --selftest            # prove all of it in a THROWAWAY repo; exit 0/1

--selftest builds a throwaway git repo in a temp dir, runs real builds through it (a clean one and a
drifting one), and checks every claim this docstring makes — including that the guard writes nothing,
that ignored files survive enforcement, and that HEAD never moves. It touches neither this repo nor
the db nor the network, and needs no API key and no server. It does need to SEE registry.json, like
every tool here: the gate below fires at import, and from this file's home in tools/ it is satisfied
by the repo root's own registry.json. Every temp tree the selftest points at is given a registry.json
of its own, so even the Variant-A bug reports it deliberately provokes land in the throwaway and not
in this repo's logs/.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback


# ── registry gate (note-for-claude: "if a tool cannot see the registry it will throw an exception") ──
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


# The gate fires at IMPORT, exactly as pair_loop.py's does (ROOT, REGISTRY = find_registry(...),
# pair_loop.py:168): a tool that cannot see its registry throws rather than guessing. --root only
# chooses which repo is POLICED; it never disables this gate.
ROOT, REGISTRY = find_registry(os.path.dirname(os.path.abspath(__file__)))


class Unexpected(RuntimeError):
    """A step's actual outcome != the expected one. Raised by the API so a caller's own step handler
    (mint_crank.py's do(), pair_loop.py's step()) treats it exactly like any other failed step."""


def bug_report(root, reg, fn, exc, repro):
    """Variant-A bug report to the registry's bug_reports sink — the five fields note-for-claude
    names. Best-effort and fully defensive: a tool must never fail because its bug reporter did.

    Defensive on purpose, and not theoretically: `bug_reports` is a registry key, so its value is
    whatever the registry says. A non-string there (a dict, a list, None) makes os.path.join raise
    INSIDE this handler and replaces the original exception with a confusing one. Everything below
    the sink resolution is wrapped, and the sink resolution itself is type-checked.
    """
    try:
        sink = (reg or {}).get("bug_reports", "logs/bug_reports.jsonl")
        if not isinstance(sink, str):
            sink = "logs/bug_reports.jsonl"
        path = os.path.join(root, sink)
        frames = traceback.extract_tb(exc.__traceback__)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps({
                "filename": os.path.basename(__file__),
                "function": (frames[-1].name if frames else fn) or fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "methods-to-reproduce": repro,
                "possible-cause": "%s: %s" % (type(exc).__name__, exc),
                "traceback": traceback.format_exc().splitlines()[-6:],
                "note": "POLICY 1 (clean re-checkout) enforcement — ticket #214",
            }) + "\n")
        return path
    except Exception:  # noqa: BLE001 — the reporter is never allowed to be the failure
        return None


# ── the audit's result ────────────────────────────────────────────────────────────────────────────
class Drift:
    """What separates the working tree from the ref. `clean` is the whole invariant.

    tracked    [(status, path)] from `git diff --name-status <ref>`: M modified, D deleted (the
               commit has it, the tree does not), A staged-but-never-committed, T type-changed.
    untracked  [path] — files on disk that git neither tracks nor ignores: the STALE FILES.
    ignored    NOT COLLECTED AND NOT DRIFT, by the rule in the module docstring. It is named here so
               that a reader asking "where did ignored files go?" finds the answer at the data
               structure rather than having to infer it from an absence.
    """

    STATUS_WORDS = {"M": "modified", "D": "deleted (the commit has it; the tree does not)",
                    "A": "staged but never committed", "T": "type changed",
                    "C": "copied", "R": "renamed", "U": "unmerged"}

    def __init__(self, ref, sha, tracked, untracked):
        self.ref, self.sha, self.tracked, self.untracked = ref, sha, tracked, untracked

    @property
    def clean(self):
        return not self.tracked and not self.untracked

    @property
    def paths(self):
        return [p for _, p in self.tracked] + list(self.untracked)

    def as_dict(self):
        return {"ref": self.ref, "sha": self.sha, "clean": self.clean,
                "tracked": [{"status": s, "path": p, "what": self.STATUS_WORDS.get(s[:1], s)}
                            for s, p in self.tracked],
                "untracked": list(self.untracked)}

    def report(self, indent="   "):
        """The human-readable refusal. It names every path, because a guard that says only "dirty"
        makes its reader go and find out what this file already knows."""
        if self.clean:
            return "%sthe working tree is a CLEAN CHECKOUT of %s (%s): no drift." % (
                indent, self.ref, (self.sha or "")[:10])
        out = ["%sDRIFT vs %s (%s) — the working tree is NOT a clean checkout of it:"
               % (indent, self.ref, (self.sha or "")[:10])]
        for s, p in self.tracked:
            out.append("%s  %-24s %s" % (indent, self.STATUS_WORDS.get(s[:1], s), p))
        for p in self.untracked:
            out.append("%s  %-24s %s" % (indent, "STALE (untracked)", p))
        out.append("%s  (ignored files are not drift and were not examined — see THE IGNORED-FILE "
                   "RULE in this tool's docstring)" % indent)
        return "\n".join(out)


# ── the tree under policy ─────────────────────────────────────────────────────────────────────────
class Recheckout:
    """Every git act POLICY 1 performs, against one repo root.

    Scoped to a root rather than reaching for a global so --selftest can drive a THROWAWAY repo
    through the identical code path the real one takes — the established pattern in this repo
    (pair_loop.py's Forge takes a root for exactly this reason; its selftest builds a temp repo).
    """

    def __init__(self, root):
        self.root = os.path.abspath(root)

    # ── plumbing ──────────────────────────────────────────────────────────────
    def _run(self, args, env=None, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True, text=True,
                              env=env)

    def git(self, *args, **kw):
        r = self._run(list(args), env=kw.get("env"), cwd=kw.get("cwd"))
        if r.returncode != 0:
            raise Unexpected("git %s failed (exit %s): %s"
                             % (" ".join(args[:3]), r.returncode, (r.stderr or r.stdout).strip()[-300:]))
        return r.stdout

    def rev_parse(self, ref):
        r = self._run(["rev-parse", "--verify", "%s^{commit}" % ref])
        if r.returncode != 0:
            raise Unexpected("cannot resolve ref %r in %s — %s. (A repository with no commits has no "
                             "HEAD to be a clean checkout OF; make a commit first.)"
                             % (ref, self.root, (r.stderr or "").strip().splitlines()[:1]))
        return r.stdout.strip()

    def is_repo(self):
        return self._run(["rev-parse", "--git-dir"]).returncode == 0

    # ── the audit: what separates the tree from the ref ───────────────────────
    def tracked_drift(self, ref):
        """`git diff --name-status -z --no-renames <ref> --`: the ref vs the WORKING TREE, for every
        path git tracks (which includes a staged-but-uncommitted file — it is in the index, so it is
        tracked, and it surfaces here as 'A').

        -z, never the plain form, for the reason pair_loop.py spells out at :358-372: plain output
        C-QUOTES any path holding a space, a quote, or a non-ascii byte (`docs/naïve.md` prints as
        `"docs/na\\303\\257ve.md"`), so a raw compare of that text against a real path silently
        misses it — and here it would be worse than a miss: the path would be REMOVED under its
        quoted spelling or not at all. -z emits every path verbatim, NUL-separated.

        --no-renames on purpose: with rename detection on, one rename becomes a single R entry
        carrying TWO NUL path fields, which is the exact off-by-one that makes a NUL parser read the
        second path as an entry of its own (pair_loop.py:378-382 handles that trap for `git status`).
        Turning detection off makes a rename a D plus an A — two independent entries, both true, both
        drift, no second field to mis-consume. The parser below therefore has no special cases.
        """
        raw = [f for f in self.git("diff", "--name-status", "-z", "--no-renames", ref, "--").split("\0")]
        out, i = [], 0
        while i + 1 < len(raw):
            status, path = raw[i], raw[i + 1]
            i += 2
            if status and path:
                out.append((status, path))
        return sorted(out, key=lambda sp: sp[1])

    def untracked(self):
        """The STALE FILES: `git status --porcelain -z -uall` filtered to '??'.

        -uall, not the default: an entirely-untracked DIRECTORY collapses to a single `build/` entry
        in the default listing, and this needs the FILES — both to name them honestly in the refusal
        and because enforcement removes exactly what it named. Ignored files never appear here (no
        --ignored is passed), which is THE IGNORED-FILE RULE, enforced by omission at its source.
        """
        raw, out, i = self.git("status", "--porcelain", "-z", "-uall").split("\0"), [], 0
        while i < len(raw):
            entry = raw[i]
            i += 1
            if not entry:
                continue
            xy, path = entry[:2], entry[3:]
            if "R" in xy or "C" in xy:
                i += 1          # a rename/copy entry carries a SECOND NUL field (its source path)
            if xy == "??":
                out.append(path)
        return sorted(out)

    def audit(self, ref="HEAD"):
        """THE GUARD, as a function. Read-only: rev-parse + diff + status, nothing else."""
        sha = self.rev_parse(ref)
        return Drift(ref, sha, self.tracked_drift(ref), self.untracked())

    # ── preservation: nothing is discarded that was not first filed ───────────
    def preserve(self, ref, why):
        """Snapshot the ENTIRE drifted tree into a commit under a permanent ref; return its name+sha.

        A temp index (GIT_INDEX_FILE) is the whole trick: `git add -A .` against an index that starts
        EMPTY stages every path in the worktree, so write-tree emits a tree of the tree AS IT IS —
        without touching the real index, the real HEAD, or the real staging area. commit-tree parents
        it on the build's own commit, so `git diff <ref> <preserved>` is exactly the drift and
        nothing else. update-ref makes it a REF: `git gc` reclaims unreferenced objects, so a
        dangling commit would be a receipt with an expiry date, and this one has none.

        Ignored files are absent from the snapshot because `add -A` honors .gitignore — correct, and
        the same reason they are not drift: they are regenerated, they are not the build's output,
        and some of them (this repo's state database, its provisioned PHP) are far too big and far
        too live to be committing on the sly.
        """
        idx = os.path.join(tempfile.mkdtemp(prefix="policy1-index-"), "index")
        try:
            env = dict(os.environ, GIT_INDEX_FILE=idx)
            self.git("add", "-A", ".", env=env)
            tree = self.git("write-tree", env=env).strip()
            msg = ("POLICY 1 (#214): drift preserved before clean re-checkout\n\n%s\n\n"
                   "This commit holds the WORKING TREE EXACTLY as the build left it, parented on the\n"
                   "commit the build made. Nothing was erased to satisfy the policy.\n"
                   "  read it:    git diff %s <this ref>\n"
                   "  restore it: git checkout <this ref> -- .\n" % (why, ref))
            commit = self.git("commit-tree", tree, "-p", self.rev_parse(ref), "-m", msg).strip()
            stamp, name = time.strftime("%Y%m%dT%H%M%S"), None
            for n in range(0, 100):     # a second run in the same second must not collide
                cand = "refs/policy1/drift/%s%s" % (stamp, "" if n == 0 else "-%d" % n)
                if self._run(["rev-parse", "--verify", "--quiet", cand]).returncode != 0:
                    name = cand
                    break
            if name is None:
                raise Unexpected("could not find a free refs/policy1/drift/ name for %s" % stamp)
            self.git("update-ref", name, commit)
            return {"ref": name, "sha": commit}
        finally:
            shutil.rmtree(os.path.dirname(idx), ignore_errors=True)

    # ── enforcement: materialize the clean checkout ───────────────────────────
    def non_head_refusal(self, ref):
        """The one refusal --enforce makes on its own account, worded once so the API's exception and
        the CLI's usage error can never drift apart."""
        return ("refusing to --enforce against %s (%s), which is not HEAD (%s). Materializing a "
                "NON-HEAD commit into the tree without moving HEAD would leave the tree permanently "
                "drifted against HEAD — the exact opposite of POLICY 1. Use --check --ref %s to "
                "compare read-only, or check %s out first."
                % (ref, self.rev_parse(ref)[:10], self.rev_parse("HEAD")[:10], ref, ref))

    def _safe_to_remove(self, rel):
        """Defense in depth for the one destructive act this file performs.

        Every path here was produced by our own `git status` (so it is repo-relative, untracked and
        NOT ignored, which is already the whole safety argument). This re-derives that independently
        rather than trusting it: git could be handed a hostile path, and the cost of being wrong is
        a deleted file. Refuses anything absolute, anything that escapes the root, and anything
        inside `.git` — where pair_loop.py keeps live worktrees (`<repo>/.git/pair-worktrees`,
        pair_loop.py:57-60,304).
        """
        if os.path.isabs(rel) or ".." in rel.replace(os.sep, "/").split("/"):
            return False, "not a repo-relative path"
        full = os.path.realpath(os.path.join(self.root, rel))
        root = os.path.realpath(self.root)
        if full != root and not full.startswith(root + os.sep):
            return False, "resolves outside the repo root"
        if ".git" in os.path.relpath(full, root).replace(os.sep, "/").split("/"):
            return False, "inside .git"
        return True, ""

    def materialize(self, ref, untracked):
        """Bring the index and the working tree to `ref`, and remove exactly the named stale files.

        `read-tree --reset -u` restores modified files, restores deleted ones, and drops a
        staged-but-uncommitted one — index and tree both, HEAD untouched. `git reset --hard` would
        also move the branch pointer, i.e. rewrite the ref the build just made, and is never used
        here. `git clean` is never used either — see THE IGNORED-FILE RULE; removal below is
        surgical, one named path at a time.
        """
        self.git("read-tree", "--reset", "-u", ref)
        removed, refused, dirs = [], [], set()
        for rel in untracked:
            ok, why = self._safe_to_remove(rel)
            if not ok:
                refused.append((rel, why))
                continue
            full = os.path.join(self.root, rel)
            try:
                if os.path.isdir(full) and not os.path.islink(full):
                    shutil.rmtree(full)
                elif os.path.exists(full) or os.path.islink(full):
                    os.remove(full)
                removed.append(rel)
                dirs.add(os.path.dirname(full))
            except OSError as e:
                refused.append((rel, str(e)))
        # A directory git never tracked (git tracks files, not directories) is invisible to the
        # re-audit, but "a clean checkout" means the ref's shape and not the ref's shape plus empty
        # husks. Only directories we just emptied are considered, innermost first, and only while
        # they are genuinely empty and still inside the root.
        for d in sorted(dirs, key=lambda p: p.count(os.sep), reverse=True):
            while os.path.realpath(d) != os.path.realpath(self.root):
                ok, _ = self._safe_to_remove(os.path.relpath(d, self.root))
                if not ok or not os.path.isdir(d) or os.listdir(d):
                    break
                os.rmdir(d)
                d = os.path.dirname(d)
        return {"removed": removed, "refused": refused}

    def enforce(self, ref="HEAD"):
        """PRESERVE -> MATERIALIZE -> RE-AUDIT. Returns the whole story; raises if the re-audit still
        finds drift (an enforcement that did not enforce must never report success)."""
        before = self.audit(ref)
        if before.clean:
            return {"drifted": False, "before": before, "after": before, "preserved": None,
                    "removed": [], "refused": []}
        if self.rev_parse(ref) != self.rev_parse("HEAD"):
            raise Unexpected(self.non_head_refusal(ref))
        preserved = self.preserve(ref, why=before.report(indent=""))
        moved = self.materialize(ref, before.untracked)
        after = self.audit(ref)
        if not after.clean:
            raise Unexpected("enforcement did NOT produce a clean checkout of %s — drift remains: %s. "
                             "The drift was preserved at %s and nothing was lost."
                             % (ref, ", ".join(after.paths[:5]), preserved["ref"]))
        return {"drifted": True, "before": before, "after": after, "preserved": preserved,
                "removed": moved["removed"], "refused": moved["refused"]}


# ── the importable API (the in-process wire; see THE WIRE in the docstring) ───────────────────────
def guard_policy1(root, ref="HEAD"):
    """CHECK-ONLY. Returns the Drift. Raises Unexpected if the tree is not a clean checkout of `ref`.
    Read-only: it changes nothing, ever."""
    d = Recheckout(root).audit(ref)
    if not d.clean:
        raise Unexpected("POLICY 1 violated — the working tree is not a clean checkout of %s (%s). "
                         "Drift: %s" % (ref, (d.sha or "")[:10], ", ".join(d.paths)))
    return d


def enforce_policy1(root, ref="HEAD"):
    """ENFORCE. Materializes the clean checkout of `ref` (preserving any drift under
    refs/policy1/drift/<stamp> first), then raises Unexpected if there WAS drift.

    It raises on drift by design, even though it just repaired the tree: the caller is a build, and
    "a build that leaves drift is refused" (#214). The repair guarantees the NEXT build starts from
    tree == HEAD; the raise is what refuses THIS one. Both halves of the ticket, in one call."""
    res = Recheckout(root).enforce(ref)
    if res["drifted"]:
        raise Unexpected("POLICY 1 violated — the build left drift relative to its own commit %s "
                         "(%s). The tree has been restored to a clean checkout and the drift is "
                         "preserved at %s (git diff %s %s). Drifting paths: %s"
                         % (ref, (res["before"].sha or "")[:10], res["preserved"]["ref"], ref,
                            res["preserved"]["ref"], ", ".join(res["before"].paths)))
    return res


# ── the CLI ───────────────────────────────────────────────────────────────────────────────────────
def run_build(rc, cmd):
    """Run the wrapped build with the repo root as its cwd, streaming its output to ours (a build's
    progress is the operator's, not this wrapper's to swallow).

    Returns (the build's exit code, HEAD before it, HEAD after it). The two HEADs are what tell the
    caller whether the build COMMITTED, which #214's acceptance sentence asks about separately from
    whether the tree is clean.
    """
    before = rc.rev_parse("HEAD")
    print("== build == %s" % " ".join(cmd))
    try:
        r = subprocess.run(cmd, cwd=rc.root)
    except FileNotFoundError as e:
        raise Unexpected("cannot run the wrapped build command %r: %s" % (cmd[0], e))
    after = rc.rev_parse("HEAD")
    print("== build == exit %s; HEAD %s" % (r.returncode,
                                            "%s -> %s (the build COMMITTED)" % (before[:10], after[:10])
                                            if after != before else "%s (unmoved — no commit)" % before[:10]))
    return r.returncode, before, after


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    # The build command is everything after the FIRST `--`, split off BEFORE argparse sees it, so the
    # build may carry any flags it likes (including ones this tool also defines, and further `--`s)
    # without argparse claiming them. `python3 clean_recheckout.py -- python3 mint_crank.py --no-verify`
    # must pass --no-verify to mint_crank, not eat it here.
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = []
    if "--" in argv:
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]

    ap = argparse.ArgumentParser(
        prog="clean_recheckout.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="POLICY 1 (ticket #214): after a build commits, the working tree IS a clean "
                    "checkout of that commit. Guard it, enforce it, or wrap a build in it.",
        epilog="THE WIRE: put `-- <build command>` at the end to run any build tool and apply the "
               "policy to what it leaves.\n"
               "  python3 clean_recheckout.py -- python3 tools/mint_crank.py --no-patch -m 'msg'\n"
               "  python3 clean_recheckout.py --enforce --require-commit -- <any build tool>\n"
               "Exit: 0 policy holds; 2 unexpected (bug report filed) or a usage refusal; 3 REFUSED "
               "(drift). A wrapped build that fails propagates ITS OWN exit code verbatim.\n"
               "Ignored files (.gitignore) are never drift and are never touched — this tool does "
               "not run `git clean`.")
    ap.add_argument("--check", action="store_true",
                    help="audit only and report (the DEFAULT; read-only — writes nothing, moves nothing)")
    ap.add_argument("--enforce", action="store_true",
                    help="materialize the clean checkout: preserve the drift under refs/policy1/drift/"
                         "<stamp>, restore the tree to the ref, re-audit. Still exits 3 if there WAS "
                         "drift — repairing the tree does not make the build compliant")
    ap.add_argument("--ref", default="HEAD", metavar="REF",
                    help="the commit the tree must be a clean checkout of (default: HEAD). --enforce "
                         "requires it to resolve to HEAD; --check accepts any revision")
    ap.add_argument("--require-commit", action="store_true",
                    help="with a wrapped build: REFUSE (exit 3) if the build did not advance HEAD. "
                         "This is #214's 'code is committed AND the tree is a clean checkout' in full")
    ap.add_argument("--root", default=None, metavar="DIR",
                    help="the repo to police (default: this tool's own registry root). Only chooses "
                         "WHICH repo is policed; the registry gate still applies to this tool")
    ap.add_argument("--json", action="store_true", help="print the audit as JSON on stdout")
    ap.add_argument("--selftest", action="store_true",
                    help="prove this tool end-to-end in a THROWAWAY temp repo, then exit. Touches no "
                         "db, no network and not this repo; like every mode it does need to see "
                         "registry.json (the import-time gate)")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()

    # ROOT/REGISTRY came from the import-time gate. --root re-points the POLICY at another repo; the
    # Variant-A bug sink follows it, so a tool aimed elsewhere files its reports there rather than
    # into this repo, and falls back to this repo's registry when that one declares none.
    root = os.path.abspath(a.root) if a.root else ROOT
    try:
        sink_root, reg = find_registry(root)
    except RuntimeError:
        sink_root, reg = ROOT, REGISTRY
    repro = "python3 %s %s" % (os.path.basename(__file__), " ".join(sys.argv[1:]))
    try:
        rc = Recheckout(root)
        if not rc.is_repo():
            raise Unexpected("%s is not a git repository — POLICY 1 is a statement about a commit and "
                             "a working tree, and there is neither here" % rc.root)
        # A usage refusal, not a fault: it files no bug report and prints no traceback (argparse's
        # own convention — error() exits 2). The API arm raises the identical text from enforce().
        if a.enforce and rc.rev_parse(a.ref) != rc.rev_parse("HEAD"):
            ap.error(rc.non_head_refusal(a.ref))

        # ── THE WIRE: run the build first; the policy is about what it LEFT ──
        build_rc, moved = None, None
        if cmd:
            build_rc, before, after = run_build(rc, cmd)
            moved = before != after
            if build_rc != 0:
                # A failed build's tree is evidence. Report the state, enforce nothing, propagate.
                d = rc.audit(a.ref)
                print("== policy 1 == NOT EVALUATED — the wrapped build FAILED (exit %s). The tree is "
                      "reported, not enforced: a failed build's tree is evidence.\n%s"
                      % (build_rc, d.report()))
                if a.json:
                    print(json.dumps({"policy1": "not-evaluated", "build_exit": build_rc,
                                      "audit": d.as_dict()}, indent=2))
                return build_rc

        # ── the policy itself ──
        if a.enforce:
            res = rc.enforce(a.ref)
            d = res["before"]
            if res["drifted"]:
                print("== policy 1 == REFUSED — the build left drift relative to its own commit.\n%s"
                      % d.report())
                print("   drift PRESERVED at %s (%s) — nothing was erased:\n"
                      "     read it:    git diff %s %s\n     restore it: git checkout %s -- ."
                      % (res["preserved"]["ref"], res["preserved"]["sha"][:10], a.ref,
                         res["preserved"]["ref"], res["preserved"]["ref"]))
                if res["removed"]:
                    print("   stale files removed (exactly the ones named above): %s"
                          % ", ".join(res["removed"]))
                if res["refused"]:
                    print("   NOT removed (refused by the safety check): %s"
                          % ", ".join("%s (%s)" % (p, w) for p, w in res["refused"]))
                print("   the tree is NOW a clean checkout of %s (%s) — re-audited and proven."
                      % (a.ref, (res["after"].sha or "")[:10]))
            else:
                print("== policy 1 == HOLDS\n%s" % d.report())
        else:
            d = rc.audit(a.ref)
            print("== policy 1 == %s\n%s" % ("HOLDS" if d.clean else "REFUSED", d.report()))
            res = {"drifted": not d.clean, "preserved": None, "removed": []}

        if a.json:
            print(json.dumps({"policy1": "holds" if not res["drifted"] else "refused",
                              "enforced": bool(a.enforce), "build_exit": build_rc,
                              "committed": moved, "preserved": res["preserved"],
                              "removed": res.get("removed", []), "audit": d.as_dict()}, indent=2))

        # ── #214: "code is committed AND the working tree is a clean checkout of that commit" ──
        if cmd and a.require_commit and not moved:
            print("== policy 1 == REFUSED — the build exited 0 but committed NOTHING (HEAD did not "
                  "move). --require-commit says a build that produces artifacts must commit them; a "
                  "build that commits nothing has nothing for the tree to be a clean checkout OF.")
            return 3
        if res["drifted"]:
            return 3
        if cmd and moved:
            print("== policy 1 == the build committed %s AND the working tree is a clean checkout of "
                  "it — no stale files, no drift." % (d.sha or "")[:10])
        elif cmd:
            print("== policy 1 == the tree is a clean checkout of %s (the build made no commit)."
                  % (d.sha or "")[:10])
        return 0
    except Exception as e:  # noqa: BLE001 — every unexpected outcome files a Variant-A bug report
        p = bug_report(sink_root, reg, "main", e, repro)
        name = "" if isinstance(e, Unexpected) else "%s: " % type(e).__name__
        print("UNEXPECTED: %s%s%s" % (name, e, ("\n   bug report -> %s" % p) if p else ""),
              file=sys.stderr)
        return 2


# ── --selftest: prove every claim in a THROWAWAY repo (no db, no network, no registry) ────────────
def _st_git(repo, *a, **kw):
    return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, env=kw.get("env"))


def _st_repo(base):
    """A throwaway repo shaped like this one where it matters: a .gitignore that ignores a database,
    a logs dir and a provisioned-runtime dir, exactly as the real repo's does."""
    repo = os.path.join(base, "repo")
    os.makedirs(repo)
    _st_git(repo, "init", "--quiet", "-b", "main", ".")
    _st_git(repo, "config", "user.email", "policy1@selftest")
    _st_git(repo, "config", "user.name", "policy1 selftest")
    open(os.path.join(repo, ".gitignore"), "w").write(
        "*.sqlite\nlogs/\n/runtime/php/\n__pycache__/\n")
    open(os.path.join(repo, "registry.json"), "w").write('{"schema": 1, "package": "selftest"}\n')
    os.makedirs(os.path.join(repo, "src"))
    open(os.path.join(repo, "src", "app.py"), "w").write("VERSION = 1\n")
    open(os.path.join(repo, "src", "keep.py"), "w").write("keep\n")
    _st_git(repo, "add", "-A")
    _st_git(repo, "commit", "--quiet", "-m", "init")
    # the ignored set the real repo would die without: a state db, logs, a provisioned runtime
    open(os.path.join(repo, "state.sqlite"), "w").write("THE DATABASE\n")
    os.makedirs(os.path.join(repo, "logs"))
    open(os.path.join(repo, "logs", "bug_reports.jsonl"), "w").write("{}\n")
    os.makedirs(os.path.join(repo, "runtime", "php"))
    open(os.path.join(repo, "runtime", "php", "php"), "w").write("#!binary\n")
    return repo


# Two builds, shaped like mint_crank.py's capture step (write artifacts -> `git add -A` -> commit,
# mint_crank.py:269-274). The CLEAN one commits everything it made. The DRIFTING one commits, and
# then leaves artifacts behind — which is the whole failure #214 exists to catch.
CLEAN_BUILD = """import subprocess, sys, os
open("src/app.py", "w").write("VERSION = 2\\n")
open("src/generated.py", "w").write("# generated by the build\\n")
open("state.sqlite", "w").write("THE DATABASE, rewritten by the build\\n")   # ignored: not an artifact
subprocess.run(["git", "add", "-A"], check=True)
subprocess.run(["git", "commit", "--quiet", "-m", "build: version 2"], check=True)
print("clean build done")
"""

DRIFTING_BUILD = """import subprocess, os
open("src/app.py", "w").write("VERSION = 3\\n")
subprocess.run(["git", "add", "-A"], check=True)
subprocess.run(["git", "commit", "--quiet", "-m", "build: version 3"], check=True)
# ...and now it leaves drift, AFTER its own commit — every class of it:
open("src/app.py", "w").write("VERSION = 3 + uncommitted edit\\n")   # modified tracked
os.remove("src/keep.py")                                             # deleted tracked
open("src/stale.py", "w").write("# STALE: built, never committed\\n") # untracked stale file
os.makedirs("out/nested", exist_ok=True)
open("out/nested/artifact.bin", "w").write("stale artifact\\n")       # untracked stale tree
open("src/staged.py", "w").write("# staged, never committed\\n")
subprocess.run(["git", "add", "src/staged.py"], check=True)          # staged but uncommitted
open("state.sqlite", "w").write("db churn\\n")                        # IGNORED: must not be drift
os.makedirs("__pycache__", exist_ok=True)
open("__pycache__/app.pyc", "w").write("x\\n")                        # IGNORED: must not be drift
print("drifting build done")
"""

FAILING_BUILD = """import sys
open("src/half_done.py", "w").write("# a failed build's evidence\\n")
sys.stderr.write("the build broke\\n")
sys.exit(7)
"""


def _snapshot(root):
    """Every path under `root` (excluding .git's internals, which git churns on any read), plus the
    refs. The before/after evidence that --check writes NOTHING (playbook theme 3: prove it in
    isolation, don't assume the happy path does)."""
    files = []
    for d, dirs, fs in os.walk(root):
        if ".git" in dirs:
            dirs.remove(".git")
        for f in fs:
            p = os.path.join(d, f)
            files.append((os.path.relpath(p, root), os.path.getsize(p)))
    refs = subprocess.run(["git", "show-ref"], cwd=root, capture_output=True, text=True).stdout
    return sorted(files), refs


def selftest():
    """Drive every claim this file makes through a throwaway repo. One PASS/FAIL line per check;
    returns 0 only if every check passed."""
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond)))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name,
                                ("  — %s" % detail) if detail and not cond else ""))

    base = tempfile.mkdtemp(prefix="policy1-selftest-")
    try:
        repo = _st_repo(base)
        rc = Recheckout(repo)
        me = os.path.abspath(__file__)
        print("== selftest == throwaway repo %s" % repo)

        def build(src, name):
            p = os.path.join(base, name)
            open(p, "w").write(src)
            return p

        def cli(*args, cwd=None):
            r = subprocess.run([sys.executable, me, "--root", repo, *args], cwd=cwd or repo,
                               capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr

        # ── the guard on a clean tree ──
        print("-- the guard: a clean tree passes, and the guard writes nothing")
        ck("a freshly committed tree is a clean checkout of HEAD", rc.audit("HEAD").clean,
           rc.audit("HEAD").report())
        before_snap = _snapshot(repo)
        code, out = cli()
        after_snap = _snapshot(repo)
        ck("--check exits 0 on a clean tree", code == 0, "exit %s: %s" % (code, out[-200:]))
        ck("--check says the tree is a CLEAN CHECKOUT", "CLEAN CHECKOUT" in out, out[-200:])
        ck("--check is READ-ONLY: created/removed/changed no file (theme 3, before vs after)",
           before_snap[0] == after_snap[0], "before %s != after %s" % (before_snap[0], after_snap[0]))
        ck("--check is READ-ONLY: created no ref", before_snap[1] == after_snap[1])

        # ── the ignored set is not drift (the safety-critical rule) ──
        print("-- THE IGNORED-FILE RULE: the db, the logs and the runtime are not drift")
        d = rc.audit("HEAD")
        ck("an ignored database is NOT drift", "state.sqlite" not in d.paths, str(d.paths))
        ck("an ignored logs/ dir is NOT drift", not any(p.startswith("logs/") for p in d.paths), str(d.paths))
        ck("an ignored provisioned runtime is NOT drift",
           not any(p.startswith("runtime/") for p in d.paths), str(d.paths))

        # ── THE ACCEPTANCE, positive: a build that commits its artifacts passes ──
        print("-- ACCEPTANCE: a build that produces artifacts and commits them -> clean checkout")
        head_before = rc.rev_parse("HEAD")
        code, out = cli("--require-commit", "--", sys.executable, build(CLEAN_BUILD, "clean_build.py"))
        ck("the clean build's wrapper exits 0", code == 0, "exit %s: %s" % (code, out[-300:]))
        ck("the build COMMITTED (HEAD advanced)", rc.rev_parse("HEAD") != head_before)
        ck("...and the tree IS a clean checkout of that commit", rc.audit("HEAD").clean,
           rc.audit("HEAD").report())
        ck("...which the wrapper states in those terms", "clean checkout of" in out, out[-300:])
        ck("the build's artifact is IN the commit, not stale",
           "src/generated.py" in rc.git("show", "--name-only", "--format=", "HEAD"))
        ck("git status is clean after the clean build", not rc.git("status", "--porcelain").strip())
        ck("the ignored database SURVIVED the clean build wrapper",
           open(os.path.join(repo, "state.sqlite")).read().startswith("THE DATABASE, rewritten"))

        # ── THE ACCEPTANCE, negative: a build that leaves drift is REFUSED ──
        print("-- ACCEPTANCE: a build that leaves drift is REFUSED")
        drift_build = build(DRIFTING_BUILD, "drift_build.py")
        code, out = cli("--", sys.executable, drift_build)
        ck("a drifting build is REFUSED with exit 3", code == 3, "exit %s: %s" % (code, out[-400:]))
        ck("the refusal names the modified file", "src/app.py" in out, out[-400:])
        ck("the refusal names the deleted file", "src/keep.py" in out, out[-400:])
        ck("the refusal names the stale untracked file", "src/stale.py" in out, out[-400:])
        ck("the refusal names the stale untracked TREE (-uall, not a collapsed dir)",
           "out/nested/artifact.bin" in out, out[-400:])
        ck("the refusal names the staged-but-uncommitted file", "src/staged.py" in out, out[-400:])
        ck("the refusal does NOT name the ignored database", "state.sqlite" not in out, out[-400:])
        ck("the refusal does NOT name ignored __pycache__", "__pycache__" not in out, out[-400:])
        d = rc.audit("HEAD")
        ck("the audit classes every drift kind", sorted(d.paths) ==
           ["out/nested/artifact.bin", "src/app.py", "src/keep.py", "src/staged.py", "src/stale.py"],
           str(sorted(d.paths)))
        ck("the REFUSAL CHANGED NOTHING (a guard is not a repair)",
           os.path.isfile(os.path.join(repo, "src", "stale.py"))
           and not os.path.isfile(os.path.join(repo, "src", "keep.py")))

        # ── enforcement: preserve -> materialize -> re-audit ──
        print("-- ENFORCE: the clean checkout is materialized, and the drift is preserved not erased")
        head_pre = rc.rev_parse("HEAD")
        refs_pre = subprocess.run(["git", "show-ref"], cwd=repo, capture_output=True, text=True).stdout
        code, out = cli("--enforce")
        ck("--enforce on drift still exits 3 (the build is refused, not absolved)", code == 3,
           "exit %s: %s" % (code, out[-300:]))
        ck("the tree is NOW a clean checkout of HEAD", rc.audit("HEAD").clean, rc.audit("HEAD").report())
        ck("git status is clean after enforcement", not rc.git("status", "--porcelain").strip())
        ck("the modified file was restored to the commit's bytes",
           open(os.path.join(repo, "src", "app.py")).read() == "VERSION = 3\n",
           open(os.path.join(repo, "src", "app.py")).read())
        ck("the deleted file was restored", os.path.isfile(os.path.join(repo, "src", "keep.py")))
        ck("the stale untracked file is gone", not os.path.exists(os.path.join(repo, "src", "stale.py")))
        ck("the staged-but-uncommitted file is gone",
           not os.path.exists(os.path.join(repo, "src", "staged.py")))
        ck("the stale tree is gone, and its empty dirs with it",
           not os.path.exists(os.path.join(repo, "out")))
        ck("HEAD did NOT move (no `git reset --hard`; the build's commit is untouched)",
           rc.rev_parse("HEAD") == head_pre)

        # ...and the ignored set is still there. This is the check that matters most.
        ck("THE DATABASE SURVIVED enforcement", os.path.isfile(os.path.join(repo, "state.sqlite")))
        ck("the logs SURVIVED enforcement", os.path.isfile(os.path.join(repo, "logs", "bug_reports.jsonl")))
        ck("the provisioned runtime SURVIVED enforcement",
           os.path.isfile(os.path.join(repo, "runtime", "php", "php")))
        ck("ignored __pycache__ SURVIVED enforcement", os.path.isfile(os.path.join(repo, "__pycache__", "app.pyc")))

        # the receipt: the drift is a real, permanent, recoverable ref
        refs_post = subprocess.run(["git", "show-ref"], cwd=repo, capture_output=True, text=True).stdout
        pres = [l.split()[1] for l in refs_post.splitlines() if "refs/policy1/drift/" in l]
        ck("the drift was PRESERVED under a refs/policy1/drift/ ref", len(pres) == 1, refs_post)
        ck("...which did not exist before the enforcement", "refs/policy1/drift/" not in refs_pre)
        ck("...and the enforcement printed the recovery command", "git checkout" in out and "-- ." in out,
           out[-300:])
        if pres:
            held = rc.git("ls-tree", "-r", "--name-only", pres[0]).split()
            ck("the preserved commit holds the modified file's uncommitted content",
               rc.git("show", "%s:src/app.py" % pres[0]) == "VERSION = 3 + uncommitted edit\n",
               rc.git("show", "%s:src/app.py" % pres[0]))
            ck("...and the stale untracked file", "src/stale.py" in held, str(held))
            ck("...and the stale tree", "out/nested/artifact.bin" in held, str(held))
            ck("...and the staged-but-uncommitted file", "src/staged.py" in held, str(held))
            ck("...and records the deletion (the deleted file is absent from the snapshot)",
               "src/keep.py" not in held, str(held))
            ck("...and does NOT hold the ignored database (regenerated, never committed on the sly)",
               "state.sqlite" not in held, str(held))
            ck("the preserved commit is parented on the build's own commit (git diff <ref> <pres>)",
               rc.git("rev-parse", "%s^" % pres[0]).strip() == head_pre)
            # the recovery actually recovers
            r = _st_git(repo, "checkout", pres[0], "--", ".")
            ck("`git checkout <preserved> -- .` restores the drift for real", r.returncode == 0
               and open(os.path.join(repo, "src", "stale.py")).read() == "# STALE: built, never committed\n")
            _st_git(repo, "read-tree", "--reset", "-u", "HEAD")
            for junk in ("src/stale.py", "out"):
                p = os.path.join(repo, junk)
                shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.path.exists(p) and os.remove(p)

        # ── enforcement is idempotent, and a clean tree enforces to a no-op ──
        print("-- ENFORCE on a clean tree: a no-op that exits 0 and preserves nothing")
        refs_pre = subprocess.run(["git", "show-ref"], cwd=repo, capture_output=True, text=True).stdout
        code, out = cli("--enforce")
        refs_post2 = subprocess.run(["git", "show-ref"], cwd=repo, capture_output=True, text=True).stdout
        ck("--enforce on an already-clean tree exits 0", code == 0, "exit %s: %s" % (code, out[-300:]))
        ck("...and preserves NOTHING (no ref litter on the happy path)", refs_pre == refs_post2)
        ck("...and is idempotent (the tree is still a clean checkout)", rc.audit("HEAD").clean)

        # ── a failed build: evidence is not destroyed, its exit code is propagated ──
        print("-- a FAILED build: its exit code propagates and its tree is evidence, not swept")
        code, out = cli("--enforce", "--", sys.executable, build(FAILING_BUILD, "failing_build.py"))
        ck("the failed build's own exit code is propagated (7, not 3)", code == 7,
           "exit %s: %s" % (code, out[-300:]))
        ck("the policy reports NOT EVALUATED for a failed build", "NOT EVALUATED" in out, out[-300:])
        ck("the failed build's evidence was NOT destroyed",
           os.path.isfile(os.path.join(repo, "src", "half_done.py")), out[-200:])
        os.remove(os.path.join(repo, "src", "half_done.py"))

        # ── --require-commit: a build that commits nothing is refused ──
        print("-- --require-commit: 'code is committed AND the tree is clean' — both halves")
        noop = build("print('a build that commits nothing')\n", "noop_build.py")
        code, out = cli("--", sys.executable, noop)
        ck("a no-commit build passes WITHOUT --require-commit (not every build commits)", code == 0,
           "exit %s: %s" % (code, out[-200:]))
        code, out = cli("--require-commit", "--", sys.executable, noop)
        ck("a no-commit build is REFUSED with --require-commit", code == 3, "exit %s: %s" % (code, out[-200:]))
        ck("...and the refusal explains itself (committed NOTHING)", "committed NOTHING" in out, out[-300:])

        # ── --ref: read-only against any revision; --enforce refuses a non-HEAD ref ──
        print("-- --ref: the guard compares against any revision; --enforce refuses a non-HEAD one")
        first = rc.git("rev-list", "--max-parents=0", "HEAD").split()[0]
        code, out = cli("--ref", first)
        ck("--check against an OLD commit reports drift (the tree is not that commit)", code == 3,
           "exit %s: %s" % (code, out[-200:]))
        ck("...and names a file that changed since it", "src/app.py" in out, out[-300:])
        code, out = cli("--enforce", "--ref", first)
        ck("--enforce against a non-HEAD ref is REFUSED, not performed", code == 2,
           "exit %s: %s" % (code, out[-300:]))
        ck("...and explains why (it would leave the tree drifted against HEAD)",
           "not HEAD" in out and "opposite of POLICY 1" in out, out[-300:])
        ck("...and the tree was NOT touched by that refusal", rc.audit("HEAD").clean)

        # ── exotic paths: the -z trap that a plain porcelain parser walks into ──
        print("-- exotic paths: a stale file git would C-quote is still named and still removed")
        for name in ("src/naïve.py", "src/my file.py", "src/quote\"d.py"):
            open(os.path.join(repo, name), "w").write("stale\n")
        d = rc.audit("HEAD")
        ck("a non-ascii stale path is detected verbatim", "src/naïve.py" in d.untracked, str(d.untracked))
        ck("a spaced stale path is detected verbatim", "src/my file.py" in d.untracked, str(d.untracked))
        ck("a quoted stale path is detected verbatim", 'src/quote"d.py' in d.untracked, str(d.untracked))
        code, out = cli("--enforce")
        ck("...and enforcement removes them all", code == 3 and rc.audit("HEAD").clean
           and not os.path.exists(os.path.join(repo, "src", "naïve.py")), rc.audit("HEAD").report())

        # ── a RENAME: the trap that makes --no-renames load-bearing rather than decorative ──
        # With rename detection ON, `git diff --name-status -z` emits ONE entry carrying TWO NUL path
        # fields (R100\0old\0new\0). A parser reading fixed (status, path) pairs then reads `new` as
        # the NEXT entry's status and silently misaligns everything after it. --no-renames makes the
        # rename a D plus an A — two ordinary entries — which is why tracked_drift() needs no special
        # case. Without this check nothing proves that; the flag could be dropped and the suite would
        # stay green while the parser quietly went wrong.
        print("-- a rename parses as D + A (proving --no-renames is load-bearing)")
        _st_git(repo, "mv", "src/keep.py", "src/renamed.py")
        d = rc.audit("HEAD")
        ck("a renamed file's OLD path is reported deleted", ("D", "src/keep.py") in d.tracked, str(d.tracked))
        ck("a renamed file's NEW path is reported added", ("A", "src/renamed.py") in d.tracked, str(d.tracked))
        ck("...and no phantom entry is invented from the rename's second NUL field",
           sorted(d.paths) == ["src/keep.py", "src/renamed.py"], str(d.paths))
        ck("...and every status parsed is a real git status letter (no misalignment)",
           all(s[:1] in Drift.STATUS_WORDS for s, _ in d.tracked), str(d.tracked))
        code, out = cli("--enforce")
        ck("...and enforcement restores the rename to the commit's shape",
           code == 3 and rc.audit("HEAD").clean
           and os.path.isfile(os.path.join(repo, "src", "keep.py"))
           and not os.path.exists(os.path.join(repo, "src", "renamed.py")), rc.audit("HEAD").report())

        # ── the safety check on the one destructive act ──
        print("-- the removal safety check refuses anything it should never be handed")
        ok1, _ = rc._safe_to_remove("../outside.py")
        ok2, _ = rc._safe_to_remove("/etc/passwd")
        ok3, _ = rc._safe_to_remove(".git/config")
        ok4, _ = rc._safe_to_remove("src/legit.py")
        ck("a path escaping the root is refused", not ok1)
        ck("an absolute path is refused", not ok2)
        ck("a path inside .git is refused (live pair worktrees live there)", not ok3)
        ck("...but an ordinary in-repo path is allowed", ok4)

        # ── the API the in-process wire uses ──
        print("-- the importable API (the one-line wire for mint_crank / pair_loop)")
        ck("guard_policy1 returns a Drift on a clean tree", guard_policy1(repo).clean)
        open(os.path.join(repo, "src", "wire_stale.py"), "w").write("x\n")
        raised = ""
        try:
            guard_policy1(repo)
        except Unexpected as e:
            raised = str(e)
        ck("guard_policy1 RAISES Unexpected on drift (what do()/step() already handle)",
           "POLICY 1 violated" in raised and "src/wire_stale.py" in raised, raised[:200])
        ck("...and guard_policy1 changed nothing (it is the read-only arm)",
           os.path.isfile(os.path.join(repo, "src", "wire_stale.py")))
        raised = ""
        try:
            enforce_policy1(repo)
        except Unexpected as e:
            raised = str(e)
        ck("enforce_policy1 RAISES on drift too (the build is refused)", "POLICY 1 violated" in raised,
           raised[:200])
        ck("...and names the preservation ref in the exception (the receipt)",
           "refs/policy1/drift/" in raised, raised[:300])
        ck("...having FIRST materialized the clean checkout", rc.audit("HEAD").clean
           and not os.path.exists(os.path.join(repo, "src", "wire_stale.py")))
        ck("enforce_policy1 returns quietly on a clean tree (no raise)",
           enforce_policy1(repo)["drifted"] is False)

        # ── a non-repo, and a repo with no commits: errors that explain themselves ──
        # Each of these dirs gets its OWN registry.json so the Variant-A bug report these paths file
        # lands in the THROWAWAY tree and not in the real repo's logs/ — which is what lets the
        # closing line below say "this repo was never touched" and have it be true.
        print("-- errors explain themselves rather than throwing a traceback at the operator")
        notrepo = os.path.join(base, "notrepo")
        os.makedirs(notrepo)
        open(os.path.join(notrepo, "registry.json"), "w").write('{"schema": 1}\n')
        r = subprocess.run([sys.executable, me, "--root", notrepo], capture_output=True, text=True)
        ck("a non-repo exits 2 with a one-line explanation, not a traceback", r.returncode == 2
           and "not a git repository" in (r.stdout + r.stderr) and "Traceback" not in (r.stdout + r.stderr),
           (r.stdout + r.stderr)[-200:])
        ck("...and its Variant-A bug report went to the THROWAWAY tree, not this repo",
           os.path.isfile(os.path.join(notrepo, "logs", "bug_reports.jsonl")))
        empty = os.path.join(base, "empty")
        os.makedirs(empty)
        open(os.path.join(empty, "registry.json"), "w").write('{"schema": 1}\n')
        _st_git(empty, "init", "--quiet", "-b", "main", ".")
        r = subprocess.run([sys.executable, me, "--root", empty], capture_output=True, text=True)
        ck("a repo with NO commits exits 2 and says why", r.returncode == 2
           and "no commits" in (r.stdout + r.stderr) and "Traceback" not in (r.stdout + r.stderr),
           (r.stdout + r.stderr)[-200:])

        bad = [n for n, ok in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s"
              % (len(checks) - len(bad), len(checks), "" if not bad else "; FAILED: " + "; ".join(bad)))
        return 1 if bad else 0
    finally:
        shutil.rmtree(base, ignore_errors=True)
        print("== selftest == throwaway repo removed (this repo, the db and the network were never touched)")


if __name__ == "__main__":
    sys.exit(main())
