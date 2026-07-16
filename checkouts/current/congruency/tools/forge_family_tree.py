#!/usr/bin/env python3
"""forge_family_tree — cluster the forge's bare repos into LINEAGES and classify each one.

config/forge/remotes/*.git holds 264 bare repos that are not 264 projects: they are a few dozen
projects, each ingested several times under different names (a gitlab mirror, a rebuild, a
worktree snapshot, an expedient rename). This tool recovers the family structure and says, for
each family, how its members relate.

  DISCOVER   walk config/forge/remotes/*.git
  CLUSTER    group by ROOT-COMMIT SET (`git rev-list --max-parents=0 --all`). Two repos sharing a
             root set are the same project — one LINEAGE.
  CLASSIFY   IDENTICAL / LINEAR / FORK-CAME-HOME / DIVERGED / SPLIT-STORE (defined below)
  EMIT       a JSON document (machine-readable) and an ASCII family tree (human-readable)

SCOPE — this is PART 1 of 2 (ticket #445). It DISCOVERS and CLASSIFIES only. The containment
retirement gate and the merge-home planning are PART 2 and are deliberately NOT built here: this
tool reports and proposes, it never retires, merges, or writes to any repo it inspects.

    python3 forge_family_tree.py                       # ASCII family tree of the live forge
    python3 forge_family_tree.py --json tree.json      # + machine-readable JSON
    python3 forge_family_tree.py --json -              # JSON to stdout instead of the tree
    python3 forge_family_tree.py --lineage jail        # one family, in full detail
    python3 forge_family_tree.py --selftest            # throwaway repos in a temp dir

THE MEASURED HEADLINE, so a reader can check this tool against the forge rather than trust it.
A bare run of the live forge prints, and `--json -` reports in `totals`:

    264 repos walked -> 109 LINEAGES: 68 IDENTICAL / 36 LINEAR / 3 DIVERGED / 2 SPLIT-STORE

  * 264 repos, but only 261 join a lineage — the 3 with no refs have no tip and cannot be
    clustered, so 261 repos form the 109 lineages and the 3 are reported on their own.
  * the 3 DIVERGED are jazz, notes_db, z3_mcp; the 2 SPLIT-STORE are big-jazz and code__code,
    and both RESOLVE (to DIVERGED) after their members are fetched into a scratch store.
  * 1 of the 36 LINEAR — the jail / agent_tools_suite family — is classified FORK-CAME-HOME.
    That is not a contradiction; see TOPOLOGY vs CLASSIFICATION below.
  * 183 of the 264 have an unresolvable HEAD; see the trap immediately below.

THE UNRESOLVABLE-HEAD TRAP — READ THIS BEFORE CHANGING TIP RESOLUTION.
Most of these bare repos have a HEAD symref pointing at a branch THAT DOES NOT EXIST (HEAD says
`ref: refs/heads/master`; the actual branch is `refs/heads/main`). For such a repo
`git rev-parse HEAD` prints the literal string "HEAD" and `git rev-parse --verify HEAD` FAILS.
Measured on the live forge: 183 of 264 repos are in this state. A first prototype resolved tips
with `--verify`, silently dropped the failures, and confidently reported "0 diverged" — a false
answer. So tips are resolved from `git for-each-ref refs/heads` ONLY: prefer main, then master,
else the ref with the most commits (ties broken by ref name, so a run is reproducible). HEAD is
never trusted. A repo with NO refs at all cannot have a tip: it is REPORTED explicitly (never
skipped silently) and takes no part in any lineage.

THE CLASSES.

  IDENTICAL   every member resolves to ONE tip. Pure ingestion duplicates; nothing to reconcile.
  LINEAR      the max-commit tip (the "superset") is an ancestor of every other tip. The other
              members are STALE ALIASES — older snapshots of the same line, holding nothing the
              superset lacks.
  FORK-CAME-HOME
              *** EXACTLY THE SAME GIT SHAPE AS LINEAR. *** A fork whose additions belong merged
              BACK into its parent (its "home"), after which the fork retires. Topology CANNOT
              tell this apart from LINEAR — they differ only in INTENT, and intent is not in the
              DAG. So this tool NEVER auto-decides direction: it reports the TOPOLOGY, PROPOSES a
              direction, and accepts an operator override (--override / --override-file). Because
              the shape is LINEAR, a FORK-CAME-HOME family is still counted as LINEAR in the
              topology totals; FORK-CAME-HOME is an INTENT overlay carried in a separate field.
              See "TOPOLOGY vs CLASSIFICATION" below — the two counts are not a contradiction.
  DIVERGED    some tip is NOT reachable from the candidate. Reported with the merge-base, each
              side's unique commits, and the file-level diff, and split into:
                ADDITIVE    — the two sides touch DISJOINT files. A mechanical union; no hunk of
                              one side contradicts the other.
                CONFLICTING — both sides changed the SAME file. That overlap IS the
                              reconciliation cost, so it is named file by file.
              A DIVERGED pair may share NO commit at all (`git merge-base` empty): this forge
              holds RE-ROOTED lines where a repo carries both root commits but its main reaches
              only one, and two ingestions publish DIFFERENT roots as main — the root SETS still
              match, so they are one lineage. Live: notes_db and z3_mcp are both this shape. With
              no base to diff against, the two TREES are compared directly and a file present on
              both sides with different content is the conflict; `unrelated_histories` marks it.
  SPLIT-STORE a member's tip OBJECT is absent from the candidate's object store, so the two
              cannot be compared where they sit and ancestry is UNKNOWN, not false. The tool does
              not guess: it fetches every member into a scratch object store under a temp dir and
              RE-CLASSIFIES there. The family keeps the SPLIT-STORE label (it records a real fact
              about how the forge stores it) and carries the resolved class in `resolved_as`.

TOPOLOGY vs CLASSIFICATION — why the totals say 36 LINEAR *and* a family is FORK-CAME-HOME.
Every lineage carries two fields. `topology` is what the DAG proves: IDENTICAL / LINEAR /
DIVERGED / SPLIT-STORE. `classification` is what the operator asserts, which for every family
except an overridden one is just the topology. FORK-CAME-HOME only ever appears in
`classification`, never in `topology`, because it has no distinct shape to detect. The headline
totals count TOPOLOGY — that is why the jail family appears inside the 36 LINEAR while its
classification reads FORK-CAME-HOME. Both statements are true of the same family.

THE JAIL CASE (operator-defined; this tool does NOT re-derive it).
jail.git (47 commits) is topologically a linear superset of agent_tools_suite.git (46): shared
root 379ac05319, ats tip 888d3447c6 is an ancestor of jail tip 38e95ad16d, and jail adds 6 files.
Read naively, topology nominates jail as canonical. THAT IS WRONG. jail was an expedient — a name
wrapped around some packages in a folder, with a mess of tests cleaned up in a hurry. It is a
GRAB-BAG whose packages belong to SEVERAL DIFFERENT home repos. agent_tools_suite IS a home repo;
jail is NOT canonical and NOT a destination. The direction is REVERSED from what the topology
suggests: jail merges HOME into agent_tools_suite and is then omitted. That decision is an
operator fact, not a measurement, so it lives in OPERATOR_OVERRIDES below as data, applied like
any `--override`.

HOW "NEVER NAMES JAIL CANONICAL" IS ACTUALLY GUARANTEED. Being the default is not enough — the
question is what happens when something goes WRONG, because raw topology nominates jail and every
failure that discards the operator's decision therefore lands on the forbidden answer. Two
independent mechanisms, either of which alone would hold:

  * LAYERS THAT FALL THROUGH, NOT AWAY. The operator layers are separate and ordered: this run's
    --override, then OPERATOR_OVERRIDES, then topology. A refused entry falls through to the NEXT
    layer, so refusing an --override lands on the built-in rule, never on topology. (This is the
    fix for a real defect: the command line was once MERGED into OPERATOR_OVERRIDES, so the typo
    `--override 379ac05319=agent_tools_suite` — missing `.git` — overwrote the rule's canonical,
    failed validation as a non-member, and dropped the family to topology, printing jail.git as
    CANONICAL while exiting 0.)
  * A HARD CONSTRAINT, CHECKED SEPARATELY. NEVER_CANONICAL lists jail.git as a ruled-out
    destination. `build` refuses to emit ANY lineage naming a listed repo canonical, whatever the
    topology says and whatever an override asks for — including `--override 379ac05319=jail.git`,
    which names a perfectly real member and which no typo-check could ever catch. This check does
    not depend on a rule lookup succeeding, so it holds even if the rule above is deleted.

Both refuse the run with exit 2 and a message, rather than emitting a jail-canonical tree — a
forbidden answer is never printed, and never printed with a 0 exit. To genuinely reverse the
decision, edit OPERATOR_OVERRIDES / NEVER_CANONICAL: a deliberate, reviewable edit to the
operator's own data, not a flag. --selftest proves every one of these paths.

DO NOT USE omni.git AS THE SOURCE OF TRUTH — it is incomplete. It is not one of the 264 repos
under remotes/ at all; it sits at config/forge/archives/omni.git, and it is missing
agent_tools_suite's tip 888d3447c6 (re-measured while writing this tool:
`git --git-dir config/forge/archives/omni.git cat-file -e 888d3447c6...^{commit}` fails).
config/forge/remotes/*.git is authoritative, and is the only thing this tool ever opens.

SIDE EFFECTS — none, by construction. Every git command run against a discovered repo is a read
(rev-list, for-each-ref, cat-file, merge-base, diff, ls-tree). The ONLY writes this tool ever
makes are into a scratch directory it creates under the system temp dir (to resolve SPLIT-STORE by
fetch) and removes before exit, plus the --json path when you name one. --override-file is READ,
never written. Proven on the live forge: a real run leaves all 264 bare repos (12,695 files) and
this tool's own directory byte-identical, and leaks no scratch store. --selftest builds throwaway
repos in a temp dir, uses no network and no live db, and asserts the same byte-identity.

exits 0 on success; 2 on a usage/environment error (a one-line message, never a traceback);
1 if --selftest has a failing check.
"""
import argparse
import collections
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True   # importing/being imported must not litter .pyc into the repo

# ── the operator's decisions ──────────────────────────────────────────────────────────────────
# Data, not logic. Keyed by LINEAGE ID (the sorted short root-commit shas of the family, joined by
# '+') — a name is not stable across ingestions, a root set is. This is the operator's own layer:
# a --override on the command line is tried FIRST, but if it is invalid this layer still applies.
# A bad command line can NEVER erase an operator decision back down to raw topology.
OPERATOR_OVERRIDES = {
    "379ac05319": {
        "classification": "FORK-CAME-HOME",
        "canonical": "agent_tools_suite.git",
        "fork": "jail.git",
        "why": "jail is an expedient grab-bag whose packages belong to several different home "
               "repos; agent_tools_suite is a home repo. Direction is REVERSED from topology: "
               "jail merges HOME into agent_tools_suite, then jail is omitted. jail is NOT "
               "canonical and NOT a destination.",
        "source": "ticket #445 §4 — operator-defined, not derived from the DAG",
    },
}

# Repos the operator has ruled OUT as a destination, mapped to why. This is a HARD CONSTRAINT, not
# a default: no topology and no --override can name one of these canonical. Where OPERATOR_OVERRIDES
# says what the answer IS for a lineage, this says what the answer may never BE, for every lineage,
# whether or not a rule covers it. The two are checked independently on purpose — the guarantee
# "this tool never names jail canonical" must not depend on a rule lookup succeeding.
#
# WHY A HARD CONSTRAINT AND NOT JUST A DEFAULT. Ticket #445 §4 is unconditional: jail is NOT
# canonical and NOT a destination. An override is how an operator supplies INTENT the DAG cannot
# hold (§3 FORK-CAME-HOME) — it is not a way to contradict a decision the operator already made.
# So a run that would name a repo below canonical is REFUSED (exit 2) rather than emitted. To
# genuinely reverse this decision, edit this dict: it is the operator's data, and changing it is a
# deliberate, reviewable edit — not a typo on a command line.
NEVER_CANONICAL = {
    "jail.git": "jail is an expedient grab-bag whose packages belong to several different home "
                "repos, cleaned up in a hurry — it merges HOME and is then omitted, so it can "
                "never be a merge destination (ticket #445 §4)",
}

# where an operator entry came from, used in notes and in the JSON's `override_source`
USER_LAYER = "the --override / --override-file supplied on this run"
BUILTIN_LAYER = "the built-in operator rule (OPERATOR_OVERRIDES)"

IDENTICAL, LINEAR, DIVERGED, SPLIT_STORE = "IDENTICAL", "LINEAR", "DIVERGED", "SPLIT-STORE"
FORK_CAME_HOME = "FORK-CAME-HOME"
ADDITIVE, CONFLICTING = "ADDITIVE", "CONFLICTING"
TOPOLOGIES = (IDENTICAL, LINEAR, DIVERGED, SPLIT_STORE)

# a repo whose refs/heads is empty: no tip exists, so it joins no lineage. Reported, never dropped.
NO_REFS = "NO-REFS"


class ForgeError(RuntimeError):
    """A usage or environment problem worth one clear line, not a traceback."""


# ── git ───────────────────────────────────────────────────────────────────────────────────────

def git(gitdir, *args, **kw):
    """Run a git command against a bare repo. Returns (rc, stdout, stderr), never raises.

    Nothing here mutates `gitdir`; the one writing caller (`_union_store`) passes a scratch dir it
    owns. The environment is pinned so a user's global config, prompts, or a stray hook cannot
    change the answer or block the run.
    """
    env = dict(os.environ)
    env.update({
        "GIT_TERMINAL_PROMPT": "0",       # never block on credentials
        "GIT_ASKPASS": "true",
        "GIT_CONFIG_NOSYSTEM": "1",       # a system/global config must not steer the result
        "HOME": env.get("FFT_HOME", env.get("HOME", "")),
        "GIT_AUTHOR_NAME": "forge_family_tree",
        "GIT_AUTHOR_EMAIL": "forge_family_tree@localhost",
        "GIT_COMMITTER_NAME": "forge_family_tree",
        "GIT_COMMITTER_EMAIL": "forge_family_tree@localhost",
    })
    p = subprocess.run(["git", "--git-dir", gitdir] + [str(a) for a in args],
                       capture_output=True, text=True, env=env, timeout=kw.get("timeout", 120))
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def git_ok(gitdir, *args):
    """stdout of a git command, or "" if it failed."""
    rc, out, _ = git(gitdir, *args)
    return out if rc == 0 else ""


def have_git():
    try:
        return subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


# ── discover ──────────────────────────────────────────────────────────────────────────────────

def default_remotes():
    """Find config/forge/remotes by walking up from this file.

    This tool lives at <root>/congruency/checkouts/current/congruency/tools/, and the forge sits at
    <root>/config/forge/remotes — so the same walk-up works from the main checkout and from a pair
    worktree, where an untracked config/ is absent from the worktree itself.
    """
    here = os.path.dirname(os.path.realpath(__file__))
    d = here
    while True:
        cand = os.path.join(d, "config", "forge", "remotes")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def discover(remotes):
    """Every *.git bare repo directly under `remotes`, sorted by name."""
    if not os.path.isdir(remotes):
        raise ForgeError("no such remotes directory: %s" % remotes)
    names = sorted(n for n in os.listdir(remotes)
                   if n.endswith(".git") and os.path.isdir(os.path.join(remotes, n)))
    if not names:
        raise ForgeError("no *.git repos found under %s" % remotes)
    return names


def roots_of(gitdir):
    """The repo's ROOT-COMMIT SET — every parentless commit reachable from any ref.

    This is the cluster key: an ingestion copy keeps the original's root commits, so two repos
    sharing a root set are the same project however they were renamed. A repo with no refs has an
    empty set and is excluded from clustering by the caller.
    """
    out = git_ok(gitdir, "rev-list", "--max-parents=0", "--all")
    return frozenset(out.split())


def resolve_tip(gitdir):
    """The repo's tip, resolved from refs/heads ONLY — never from HEAD. See the module docstring.

    Returns a dict with the chosen ref, its sha, its commit count, every branch considered, and
    `head_resolvable` recording whether `rev-parse --verify HEAD` would have worked — which is the
    trap this function exists to route around. Returns None when the repo has no branches at all.
    """
    out = git_ok(gitdir, "for-each-ref", "--format=%(objectname) %(refname)", "refs/heads")
    refs = []
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            refs.append((parts[1], parts[0]))          # (refname, sha)
    rc_head, head_out, _ = git(gitdir, "rev-parse", "--verify", "HEAD")
    head_resolvable = (rc_head == 0)
    if not refs:
        return None
    by_name = dict(refs)
    chosen = None
    for pref in ("refs/heads/main", "refs/heads/master"):
        if pref in by_name:
            chosen = (pref, by_name[pref])
            break
    counts = {}
    for name, sha in refs:
        out = git_ok(gitdir, "rev-list", "--count", sha)
        counts[name] = int(out) if out.isdigit() else 0
    if chosen is None:
        # most commits; ties broken by ref name so the choice is reproducible run to run
        name = sorted(refs, key=lambda r: (-counts[r[0]], r[0]))[0][0]
        chosen = (name, by_name[name])
    return {
        "ref": chosen[0],
        "tip": chosen[1],
        "commits": counts[chosen[0]],
        "branches": sorted(name for name, _ in refs),
        "head_resolvable": head_resolvable,
        "head_symref": git_ok(gitdir, "symbolic-ref", "HEAD") or None,
    }


def survey(remotes, names=None):
    """Read every repo once: roots, tip, branches. Returns (members, no_refs)."""
    members, no_refs = [], []
    for name in (names if names is not None else discover(remotes)):
        gitdir = os.path.join(remotes, name)
        tip = resolve_tip(gitdir)
        rec = {"repo": name, "gitdir": gitdir, "roots": roots_of(gitdir)}
        if tip is None:
            rec.update({"tip": None, "ref": None, "commits": 0, "branches": [],
                        "head_resolvable": False, "reason": "refs/heads is empty"})
            no_refs.append(rec)
        else:
            rec.update(tip)
            members.append(rec)
    return members, no_refs


# ── cluster ───────────────────────────────────────────────────────────────────────────────────

def lineage_id(roots):
    """Stable id for a family: its sorted short root shas, joined by '+'."""
    return "+".join(sorted(r[:10] for r in roots))


def cluster(members):
    """Group members by root-commit SET. Returns a list of (roots, [member, ...])."""
    fams = collections.defaultdict(list)
    for m in members:
        fams[m["roots"]].append(m)
    out = [(roots, sorted(ms, key=lambda m: m["repo"])) for roots, ms in fams.items()]
    out.sort(key=lambda rm: lineage_id(rm[0]))
    return out


def pick_candidate(members, counts=None):
    """The family's topological candidate: the most commits; ties broken by repo name.

    The tie-break is not cosmetic — two members can hold the same count and the family's reported
    name follows the candidate, so a run must be reproducible.
    """
    def key(m):
        n = counts[m["repo"]] if counts else m["commits"]
        return (-n, m["repo"])
    return sorted(members, key=key)[0]


# ── classify ──────────────────────────────────────────────────────────────────────────────────

def has_commit(gitdir, sha):
    """Is this commit OBJECT present in this store? The SPLIT-STORE test."""
    return git(gitdir, "cat-file", "-e", sha + "^{commit}")[0] == 0


def is_ancestor(gitdir, older, newer):
    """Is `older` an ancestor of `newer`, asked of a store holding BOTH objects."""
    return git(gitdir, "merge-base", "--is-ancestor", older, newer)[0] == 0


def divergence(gitdir, cand_tip, other_tip):
    """Describe how two tips diverged: merge-base, each side's unique commits, file-level diff.

    ADDITIVE vs CONFLICTING is decided on the FILE SET each side changed since the merge-base.
    Disjoint sets mean no hunk of one side can contradict the other, so reconciling is a mechanical
    union. An overlap is the reconciliation cost, so the overlapping files are named.

    UNRELATED HISTORIES. Two tips in one lineage can share NO commit at all: this forge holds
    re-rooted projects (measured: notes_db, z3_mcp) where a repo carries BOTH root commits but its
    `main` reaches only one of them, and two ingestions publish DIFFERENT roots as main. The root
    SETS match, so they are one lineage, yet `git merge-base` is empty. There is no base to diff
    against, so the two TREES are compared directly instead: a file present on both sides with
    DIFFERENT content is the conflict. Every field below is filled in either way — a caller must
    never see None where a count belongs.
    """
    def count(rev):
        out = git_ok(gitdir, "rev-list", "--count", rev)
        return int(out) if out.isdigit() else 0

    def tree_files(rev):
        return sorted(f for f in git_ok(gitdir, "ls-tree", "-r", "--name-only", rev).splitlines()
                      if f)

    def differing(a, b):
        return sorted(f for f in git_ok(gitdir, "diff", "--name-only", a, b).splitlines() if f)

    mb = git_ok(gitdir, "merge-base", cand_tip, other_tip) or None
    if mb is None:
        cand_files, other_files = tree_files(cand_tip), tree_files(other_tip)
        clash = sorted(set(cand_files) & set(other_files) & set(differing(cand_tip, other_tip)))
        return {
            "merge_base": None,
            "unrelated_histories": True,
            "note": "the two tips share NO commit: this lineage was re-rooted and the two "
                    "ingestions publish different roots as main. Compared tree-to-tree.",
            # with no common ancestor every commit on each side is unique to it
            "candidate_unique_commits": count(cand_tip),
            "other_unique_commits": count(other_tip),
            "candidate_files_changed": cand_files,
            "other_files_changed": other_files,
            "conflicting_files": clash,
            "mode": CONFLICTING if clash else ADDITIVE,
            "diffstat": git_ok(gitdir, "diff", "--stat", cand_tip, other_tip),
        }

    def uniq(a, b):
        out = git_ok(gitdir, "rev-list", "--count", "%s..%s" % (a, b))
        return int(out) if out.isdigit() else 0
    cand_files, other_files = differing(mb, cand_tip), differing(mb, other_tip)
    overlap = sorted(set(cand_files) & set(other_files))
    return {
        "merge_base": mb,
        "unrelated_histories": False,
        "candidate_unique_commits": uniq(other_tip, cand_tip),
        "other_unique_commits": uniq(cand_tip, other_tip),
        "candidate_files_changed": cand_files,
        "other_files_changed": other_files,
        "conflicting_files": overlap,
        "mode": CONFLICTING if overlap else ADDITIVE,
        "diffstat": git_ok(gitdir, "diff", "--stat", cand_tip, other_tip),
    }


def _union_store(members, scratch):
    """Fetch every member into ONE scratch bare repo so a SPLIT-STORE family can be compared.

    This is the only code path in the tool that writes anything, and it writes only inside
    `scratch`, which the caller created under the system temp dir and removes. The source repos are
    read; `git fetch <path>` never writes to the thing it fetches from.
    """
    union = os.path.join(scratch, "union.git")
    p = subprocess.run(["git", "init", "--bare", "--quiet", union], capture_output=True, text=True)
    if p.returncode != 0:
        raise ForgeError("could not create a scratch object store: %s" % p.stderr.strip())
    for m in members:
        slug = m["repo"][:-4] if m["repo"].endswith(".git") else m["repo"]
        git(union, "fetch", "--quiet", "--no-tags", m["gitdir"],
            "+refs/heads/*:refs/remotes/%s/*" % slug)
    return union


def classify(roots, members, overrides=None, builtins=None, never=None):
    """Classify one lineage. Returns the lineage record described in the module docstring.

    `overrides` is THIS RUN's operator layer (--override / --override-file) and `builtins` the
    standing one (OPERATOR_OVERRIDES); they are kept apart all the way down to `_apply_overrides`,
    which explains why. `never` is the ruled-out-destination map (NEVER_CANONICAL).
    """
    lid = lineage_id(roots)
    tips = {m["repo"]: m["tip"] for m in members}
    lin = {
        "id": lid,
        "roots": sorted(roots),
        "members": [{"repo": m["repo"], "tip": m["tip"], "ref": m["ref"],
                     "commits": m["commits"], "branches": m["branches"],
                     "head_resolvable": m["head_resolvable"]} for m in members],
        "member_count": len(members),
        "notes": [],
    }

    # 1. IDENTICAL — one tip across every member. Nothing to reconcile.
    if len(set(tips.values())) == 1:
        cand = pick_candidate(members)
        lin.update({"topology": IDENTICAL, "candidate": cand["repo"], "tip": cand["tip"],
                    "stale_aliases": [], "duplicates": [m["repo"] for m in members
                                                        if m["repo"] != cand["repo"]]})
        return _apply_overrides(lin, members, overrides, builtins, never)

    cand = pick_candidate(members)
    store = cand["gitdir"]

    # 2. SPLIT-STORE — a member's tip object is absent from the candidate's store, so ancestry is
    #    UNKNOWN rather than false. Resolve by fetching everything into a scratch store.
    missing = [m["repo"] for m in members if not has_commit(store, tips[m["repo"]])]
    if missing:
        lin.update({"topology": SPLIT_STORE, "candidate": cand["repo"], "tip": cand["tip"],
                    "absent_tips": {r: tips[r] for r in missing},
                    "absent_from": cand["repo"]})
        scratch = tempfile.mkdtemp(prefix="fft-split-store-")
        try:
            union = _union_store(members, scratch)
            still = [m["repo"] for m in members if not has_commit(union, tips[m["repo"]])]
            if still:
                lin["resolved_as"] = "UNRESOLVED"
                lin["notes"].append(
                    "fetched every member into a scratch store and these tips are STILL absent, "
                    "so the object is nowhere in the forge: %s" % ", ".join(still))
                return _apply_overrides(lin, members, overrides, builtins, never)
            sub = _classify_in_store(union, roots, members, tips)
            lin["resolved_as"] = sub["topology"]
            lin["resolved"] = sub
            lin["candidate"] = sub["candidate"]
            lin["tip"] = sub["tip"]
            lin["notes"].append(
                "tip objects absent from %s's store were fetched into a scratch store; the family "
                "re-classifies there as %s (it is NOT unknown)" % (cand["repo"], sub["topology"]))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        return _apply_overrides(lin, members, overrides, builtins, never)

    # 3/4. LINEAR or DIVERGED, decided in the candidate's own store (which holds every tip).
    sub = _classify_in_store(store, roots, members, tips)
    lin.update(sub)
    return _apply_overrides(lin, members, overrides, builtins, never)


def _classify_in_store(store, roots, members, tips):
    """LINEAR vs DIVERGED vs IDENTICAL, decided in a store that holds EVERY member's tip.

    Used twice: for an ordinary family (the candidate's own store) and for a SPLIT-STORE family
    after its members are fetched into a scratch union store.
    """
    counts = {}
    for m in members:
        out = git_ok(store, "rev-list", "--count", tips[m["repo"]])
        counts[m["repo"]] = int(out) if out.isdigit() else m["commits"]
    if len(set(tips.values())) == 1:
        cand = pick_candidate(members, counts)
        return {"topology": IDENTICAL, "candidate": cand["repo"], "tip": cand["tip"],
                "stale_aliases": [], "duplicates": [m["repo"] for m in members
                                                    if m["repo"] != cand["repo"]]}
    cand = pick_candidate(members, counts)
    ctip = tips[cand["repo"]]
    stale, apart = [], []
    for m in members:
        if m["repo"] == cand["repo"] or tips[m["repo"]] == ctip:
            continue
        if is_ancestor(store, tips[m["repo"]], ctip):
            stale.append({"repo": m["repo"], "tip": tips[m["repo"]],
                          "commits": counts[m["repo"]],
                          "behind": counts[cand["repo"]] - counts[m["repo"]]})
        else:
            apart.append(m)
    if not apart:
        return {"topology": LINEAR, "candidate": cand["repo"], "tip": ctip,
                "superset": {"repo": cand["repo"], "tip": ctip, "commits": counts[cand["repo"]]},
                "stale_aliases": stale}
    return {"topology": DIVERGED, "candidate": cand["repo"], "tip": ctip,
            "superset": {"repo": cand["repo"], "tip": ctip, "commits": counts[cand["repo"]]},
            "stale_aliases": stale,
            "diverged": [dict(repo=m["repo"], tip=tips[m["repo"]], commits=counts[m["repo"]],
                              **divergence(store, ctip, tips[m["repo"]])) for m in apart]}


def _reject_reason(ov, names, never, candidate=None):
    """Why this operator entry CANNOT be applied to this lineage, or None if it can.

    An entry is refused when it names a repo that is not a member (a typo — the common case), when
    applying it would name a ruled-out repo canonical, or when it makes a repo its own fork. The
    caller must never apply a refused entry, and must never treat a refusal as "no decision".
    """
    for key in ("canonical", "fork"):
        v = ov.get(key)
        if v and v not in names:
            hint = ""
            if v + ".git" in names:
                hint = " — did you mean %s.git?" % v
            else:
                near = [n for n in sorted(names) if n.lower() in (v.lower(), v.lower() + ".git")]
                if near:
                    hint = " — did you mean %s?" % near[0]
            return ("names %s=%s, which is not a member of this lineage%s (members: %s)"
                    % (key, v, hint, ", ".join(sorted(names))))
    # What this entry would ACTUALLY make canonical, which is what must be judged — not merely what
    # it says. An entry with no `canonical` key still decides one: the topological candidate. That
    # is how `{"classification": "LINEAR"}` alone, naming nothing at all, once landed on jail.git.
    effective = ov.get("canonical") or candidate
    if effective in never:
        return ("would name %s canonical, which the operator has ruled OUT as a destination: %s"
                % (effective, never[effective]))
    # same reasoning for the fork: absent a `fork` key it defaults to the candidate, and a family
    # whose fork and home are one repo describes a merge into itself
    if ov.get("classification") == FORK_CAME_HOME and (ov.get("fork") or candidate) == effective:
        return ("names %s as BOTH the fork and the home — a fork cannot merge into itself"
                % effective)
    return None


def _use_override(lin, ov, source):
    """Apply one VALIDATED operator entry to a lineage record. Never call this on a refused entry."""
    if ov.get("classification"):
        lin["classification"] = ov["classification"]
    if ov.get("canonical"):
        lin["canonical"] = ov["canonical"]
    lin["override_applied"] = True
    lin["override_source"] = source
    lin["override"] = {k: v for k, v in ov.items() if k in ("classification", "canonical", "fork",
                                                            "why", "source")}
    if lin["classification"] == FORK_CAME_HOME:
        fork = ov.get("fork") or lin.get("candidate")
        lin["fork_edges"] = [{"fork": fork, "home": lin["canonical"],
                              "direction": "%s -> %s" % (fork, lin["canonical"]),
                              "topology_would_say": "%s (it holds the superset tip)" % fork,
                              "operator_says": ov.get("why", "")}]
        lin["proposed_direction"] = (
            "MERGE %s's additions HOME into %s, then OMIT %s. Topology alone would nominate %s as "
            "canonical because it holds the superset tip — the operator REVERSES that: %s"
            % (fork, lin["canonical"], fork, fork, ov.get("why", "")))
    else:
        lin["proposed_direction"] = _propose(lin)


def _apply_overrides(lin, members, overrides=None, builtins=None, never=None):
    """Set `classification` and the PROPOSED direction, letting an operator override the direction.

    Direction is never auto-decided for a fork: the topology is reported, a direction is PROPOSED,
    and a valid operator entry replaces it. With no entry at all, classification == topology.

    PRECEDENCE — first VALID layer wins, and a refused layer falls through to the NEXT one:

        1. this run's --override / --override-file   (the operator speaking now)
        2. OPERATOR_OVERRIDES                        (the operator's standing decision)
        3. the topology                              (what the DAG alone proves)

    WHY THE FALLTHROUGH MATTERS — this is the bug this structure exists to prevent. A refused
    entry is NOT a decision, so it must not be able to CONSUME the layer below it. Earlier this
    tool merged the command line into OPERATOR_OVERRIDES and validated the merged result: a single
    typo (`--override 379ac05319=agent_tools_suite`, missing `.git`) overwrote the jail rule's
    canonical, failed validation as a non-member, and dropped the family all the way to raw
    topology — which nominates jail.git, the one thing ticket #445 §4 forbids. The layers are kept
    SEPARATE here so that refusing layer 1 lands on layer 2, never on layer 3.

    Refusals are recorded in `rejected_overrides` (and in the notes) rather than swallowed; `build`
    turns a refused USER entry into a non-zero exit, so a typo can never quietly change the answer.
    """
    never = NEVER_CANONICAL if never is None else never
    names = {m["repo"] for m in members}

    lin["classification"] = lin["topology"]
    lin["canonical"] = lin.get("candidate")
    lin["override_applied"] = False
    lin["override_source"] = None
    lin["rejected_overrides"] = []
    lin["proposed_direction"] = _propose(lin)

    layers = [(src, table.get(lin["id"]))
              for src, table in ((USER_LAYER, overrides or {}), (BUILTIN_LAYER, builtins or {}))]
    layers = [(src, ent) for src, ent in layers if ent]

    for i, (src, ent) in enumerate(layers):
        why = _reject_reason(ent, names, never, lin.get("candidate"))
        if why is None:
            _use_override(lin, ent, src)
            break
        nxt = ("falling back to %s" % layers[i + 1][0] if i + 1 < len(layers)
               else "no operator decision remains for this lineage, so the TOPOLOGY stands")
        lin["rejected_overrides"].append({"source": src, "reason": why, "entry": dict(ent)})
        lin["notes"].append("%s REJECTED: it %s. %s." % (src, why, nxt))
    lin["name"] = _name_of(lin)
    return lin


def _name_of(lin):
    n = lin.get("canonical") or lin.get("candidate") or lin["id"]
    return n[:-4] if n.endswith(".git") else n


def _propose(lin):
    """The direction this tool PROPOSES from topology alone. Always a proposal, never a decision."""
    t, cand = lin["topology"], lin.get("candidate")
    if t == IDENTICAL:
        if lin["member_count"] == 1:
            return "single member; nothing to reconcile."
        return ("every member holds the same tip — pure ingestion duplicates of %s; nothing to "
                "merge." % cand)
    if t == LINEAR:
        return ("%s holds the superset tip; the other members are stale aliases holding nothing "
                "it lacks." % cand)
    if t == DIVERGED:
        ds = lin.get("diverged", [])
        modes = {d["mode"] for d in ds}
        cost = ("a mechanical union (no file clashes)" if modes == {ADDITIVE}
                else "CONFLICTING — the same file(s) differ on both sides")
        rerooted = (" Some tips share no commit at all (the line was re-rooted), so there is no "
                    "merge-base to reconcile against." if any(d.get("unrelated_histories")
                                                              for d in ds) else "")
        return ("%s is the largest tip but does NOT contain every member; reconciliation cost is "
                "%s.%s" % (cand, cost, rerooted))
    if t == SPLIT_STORE:
        return ("tips live in different object stores; after fetching into a scratch store the "
                "family is %s." % lin.get("resolved_as", "UNRESOLVED"))
    return ""


# ── build the whole tree ──────────────────────────────────────────────────────────────────────

def build(remotes, overrides=None, only=None, builtins=None, never_canonical=None, strict=False):
    """Discover, cluster, and classify the whole forge. Returns the JSON-able document.

      overrides        THIS RUN's operator layer, from --override / --override-file. Default none.
      builtins         the standing operator layer. Defaults to OPERATOR_OVERRIDES; the selftest
                       passes its own so it can drive the real rule SHAPE over throwaway repos.
      never_canonical  repos that may never be named canonical. Defaults to NEVER_CANONICAL.
      strict           raise on a refused USER override instead of only noting it. The CLI passes
                       True: a typo must not quietly produce a different answer.

    Two guarantees are enforced here, AFTER classification and BEFORE anything is emitted, so no
    caller can print a tree that breaks them:

      1. no lineage names a NEVER_CANONICAL repo canonical — checked over EVERY lineage, not just
         overridden ones, and independently of whether any rule matched. This is what actually
         backs "this tool never names jail canonical": it holds even if the rule is deleted.
      2. under `strict`, a refused user override fails the run rather than changing the answer.
    """
    if not have_git():
        raise ForgeError("git is not on PATH — this tool needs git")
    overrides = dict(overrides or {})
    builtins = dict(OPERATOR_OVERRIDES if builtins is None else builtins)
    never = dict(NEVER_CANONICAL if never_canonical is None else never_canonical)
    members, no_refs = survey(remotes)
    fams = cluster(members)
    lineages = [classify(roots, ms, overrides, builtins, never) for roots, ms in fams]

    # (1) the hard constraint, checked before --lineage filtering so a filter cannot hide a breach
    breach = [l for l in lineages if l.get("canonical") in never]
    if breach:
        l = breach[0]
        raise ForgeError(
            "REFUSING to emit this tree: lineage %s (%s) names %s canonical, which is ruled out "
            "as a destination — %s. No valid operator rule covered this lineage, so the raw "
            "topology nominated it; restore its entry in OPERATOR_OVERRIDES."
            % (l["id"], l["name"], l["canonical"], never[l["canonical"]]))

    # (2) a refused user override is an input error: say so and emit nothing
    if strict:
        bad = []
        for l in lineages:
            for r in l["rejected_overrides"]:
                if r["source"] != USER_LAYER:
                    continue
                # say which answer the refusal left in place, and be exact about WHY it stands:
                # an operator rule and a bare topology are not the same fallback
                stands = ("the operator's standing decision for it (canonical=%s) is untouched"
                          % l["canonical"] if l["override_applied"] else
                          "no operator rule covers this lineage, so its topology stands "
                          "(canonical=%s)" % l["canonical"])
                bad.append("lineage %s: --override %s. Nothing was emitted and %s"
                           % (l["id"], r["reason"], stands))
        if bad:
            raise ForgeError("; ".join(bad))

    if only:
        keep = [l for l in lineages
                if only == l["id"] or only == l["name"] or only == l["name"] + ".git"
                or any(only in (m["repo"], m["repo"][:-4]) for m in l["members"])]
        if not keep:
            raise ForgeError("no lineage matches %r (try a repo name, a lineage name, or an id)"
                             % only)
        lineages = keep
    lineages.sort(key=lambda l: (TOPOLOGIES.index(l["topology"]), l["name"]))

    by_top = collections.Counter(l["topology"] for l in lineages)
    by_cls = collections.Counter(l["classification"] for l in lineages)
    return {
        "tool": "forge_family_tree.py",
        "filtered_to": only,
        "scope": "PART 1 of 2 — discover + classify only; no containment gate, no merge planning",
        "remotes": remotes,
        "totals": {
            "repos_walked": len(members) + len(no_refs),
            "repos_in_lineages": len(members),
            "lineages": len(lineages),
            "no_refs": len(no_refs),
            # counted over EVERY repo walked, the no-refs ones included: an empty repo's HEAD does
            # not resolve either, and the number exists to say how widespread the trap is.
            "unresolvable_head": sum(1 for m in members + no_refs
                                     if not m["head_resolvable"]),
            "by_topology": {k: by_top.get(k, 0) for k in TOPOLOGIES},
            "by_classification": dict(sorted(by_cls.items())),
        },
        "no_refs": [{"repo": r["repo"], "reason": r["reason"]} for r in no_refs],
        "lineages": lineages,
    }


# ── render ────────────────────────────────────────────────────────────────────────────────────

def _short(sha):
    return (sha or "")[:10]


def _plural(n, word):
    return "%d %s" % (n, word if n == 1 else word + "s")


def _files(paths, verbose, cap=6):
    """A file list the tree can actually show.

    A real divergence here touches 120+ files; printing them inline destroys the tree. The count is
    always exact, the full list always lives in --json, and --verbose prints it here too.
    """
    paths = list(paths)
    if not paths:
        return "(none)"
    if verbose or len(paths) <= cap:
        return "%d: %s" % (len(paths), ", ".join(paths))
    return "%d: %s, ... and %d more (full list in --json / --verbose)" % (
        len(paths), ", ".join(paths[:cap]), len(paths) - cap)


def render(doc, verbose=False):
    """The human-readable ASCII family tree."""
    t = doc["totals"]
    L = []
    L.append("=" * 94)
    L.append("FORGE FAMILY TREE   %s" % doc["remotes"])
    L.append("=" * 94)
    order = [k for k in TOPOLOGIES if t["by_topology"].get(k)]
    head = " / ".join("%d %s" % (t["by_topology"][k], k) for k in order)
    if doc.get("filtered_to"):
        L.append("%d repos walked; showing ONLY the %s matching --lineage %s: %s"
                 % (t["repos_walked"], _plural(t["lineages"], "lineage"),
                    doc["filtered_to"], head))
    else:
        L.append("%d repos walked -> %d LINEAGES: %s"
                 % (t["repos_walked"], t["lineages"], head))
    fch = t["by_classification"].get(FORK_CAME_HOME, 0)
    if fch:
        L.append("   (of the %d LINEAR, %d is marked %s by the operator — same git shape, "
                 "reversed intent)" % (t["by_topology"][LINEAR], fch, FORK_CAME_HOME))
    L.append("   %d repos have an UNRESOLVABLE HEAD (tips came from refs/heads, never HEAD)"
             % t["unresolvable_head"])
    L.append("   %d repos have NO REFS AT ALL and join no lineage:" % t["no_refs"])
    for r in doc["no_refs"]:
        L.append("       ! %-72s %s" % (r["repo"], r["reason"]))
    if not doc["no_refs"]:
        L.append("       (none)")
    L.append("")

    cur = None
    for lin in doc["lineages"]:
        if lin["topology"] != cur:
            cur = lin["topology"]
            L.append("-" * 94)
            L.append("%s   (%s)" % (cur, _plural(sum(1 for x in doc["lineages"]
                                                     if x["topology"] == cur), "lineage")))
            L.append("-" * 94)
        L.extend(_render_lineage(lin, verbose))
        L.append("")
    return "\n".join(L)


def _render_lineage(lin, verbose=False):
    label = lin["topology"]
    if lin["classification"] != lin["topology"]:
        label = "%s  [topology: %s]" % (lin["classification"], lin["topology"])
    L = ["%s   root %s   (%s)" % (lin["name"], "+".join(lin["id"].split("+")),
                                  _plural(lin["member_count"], "member"))]
    L.append("  class: %s" % label)

    canon = lin.get("canonical")
    fork = None
    if lin.get("fork_edges"):
        fork = lin["fork_edges"][0]["fork"]
    cand = lin.get("candidate")
    for m in sorted(lin["members"], key=lambda m: (-m["commits"], m["repo"])):
        marks = []
        is_home = (m["repo"] == canon and lin["classification"] == FORK_CAME_HOME)
        if m["repo"] == canon:
            marks.append("HOME — CANONICAL" if is_home else "CANONICAL")
        if fork and m["repo"] == fork:
            marks.append("FORK — merges home, then retires; NOT canonical")
        if any(m["repo"] == s["repo"] for s in lin.get("stale_aliases", [])):
            s = [x for x in lin["stale_aliases"] if x["repo"] == m["repo"]][0]
            if is_home:
                # The home trails the fork by construction — that gap IS what merges home. Calling
                # the destination a "stale alias" would contradict the direction named just below.
                marks.append("%d behind %s, which is the gap that merges here"
                             % (s["behind"], fork or cand))
            else:
                marks.append("stale alias, %d behind %s" % (s["behind"], cand))
        if any(m["repo"] == d["repo"] for d in lin.get("diverged", [])):
            d = [x for x in lin["diverged"] if x["repo"] == m["repo"]][0]
            marks.append("DIVERGED — %s" % d["mode"])
        if lin["topology"] == IDENTICAL and m["repo"] != canon:
            marks.append("duplicate")
        if lin["topology"] == SPLIT_STORE and m["repo"] in (lin.get("absent_tips") or {}):
            marks.append("tip ABSENT from %s's store" % lin.get("absent_from"))
        if not m["head_resolvable"]:
            marks.append("HEAD unresolvable")
        bullet = "*" if m["repo"] == canon else "|"
        L.append("   %s %-58s %4d  %s  %-18s %s"
                 % (bullet, m["repo"], m["commits"], _short(m["tip"]),
                    (m["ref"] or "").replace("refs/heads/", ""),
                    ("<- " + "; ".join(marks)) if marks else ""))

    if lin["topology"] == SPLIT_STORE:
        for repo, tip in (lin.get("absent_tips") or {}).items():
            L.append("   ! %s's tip %s is ABSENT from %s's object store"
                     % (repo, _short(tip), lin.get("absent_from")))
        L.append("   -> fetched into a scratch store; RESOLVED AS: %s" % lin.get("resolved_as"))
        r = lin.get("resolved")
        if r:
            for d in _group_diverged(r.get("diverged", [])):
                L.extend(_render_divergence(d, indent="      ", verbose=verbose))
            for s in r.get("stale_aliases", []):
                L.append("      %s is %d behind %s (stale)" % (s["repo"], s["behind"],
                                                               r.get("candidate")))
    for d in _group_diverged(lin.get("diverged", [])):
        L.extend(_render_divergence(d, indent="   ", verbose=verbose))

    if lin.get("fork_edges"):
        e = lin["fork_edges"][0]
        L.append("   fork edge: %s" % e["direction"])
        L.append("     topology would say: %s" % e["topology_would_say"])
        L.append("     operator override : %s" % _wrap(e["operator_says"], 78, "                         "))
    L.append("   proposed: %s" % _wrap(lin["proposed_direction"], 78, "             "))
    if lin["notes"]:
        for n in lin["notes"]:
            L.append("   note: %s" % _wrap(n, 78, "         "))
    return L


def _group_diverged(diverged):
    """Collapse members that resolve to the SAME tip into one block.

    Three ingestion copies of one stale line diverge from the candidate identically; printing the
    same merge-base and file list three times is noise, not evidence.
    """
    by_tip = collections.OrderedDict()
    for d in diverged:
        by_tip.setdefault(d["tip"], []).append(d)
    out = []
    for tip, group in by_tip.items():
        g = dict(group[0])
        g["repos"] = [x["repo"] for x in group]
        out.append(g)
    return out


def _render_divergence(d, indent="   ", verbose=False):
    repos = d.get("repos") or [d["repo"]]
    who = repos[0] if len(repos) == 1 else ("%s (and %s sharing this tip: %s)"
                                            % (repos[0], _plural(len(repos) - 1, "other"),
                                               ", ".join(repos[1:])))
    unrelated = d.get("unrelated_histories")
    L = ["%sDIVERGED from the candidate: %s  (%s)" % (indent, who, d["mode"])]
    if unrelated:
        L.append("%s  tip %s   NO merge-base — UNRELATED histories (the line was re-rooted)"
                 % (indent, _short(d.get("tip"))))
        L.append("%s  commits: candidate %s / this side %s (no commit is shared)"
                 % (indent, d.get("candidate_unique_commits"), d.get("other_unique_commits")))
    else:
        L.append("%s  tip %s   merge-base %s"
                 % (indent, _short(d.get("tip")), _short(d.get("merge_base"))))
        L.append("%s  unique commits: candidate +%s / this side +%s"
                 % (indent, d.get("candidate_unique_commits"), d.get("other_unique_commits")))
    if d["mode"] == CONFLICTING:
        n = len(d.get("conflicting_files", []))
        L.append("%s  CONFLICTING — the same %s %s — that is the reconciliation cost"
                 % (indent, _plural(n, "file"),
                    ("exist" if n != 1 else "exists") + " on both sides with different content"
                    if unrelated else "changed on both sides"))
        L.append("%s    both sides: %s" % (indent, _files(d.get("conflicting_files", []), verbose)))
    else:
        L.append("%s  ADDITIVE — no file clashes, so reconciling is a mechanical union" % indent)
    verb = "tree holds" if unrelated else "touched"
    L.append("%s    candidate %s: %s"
             % (indent, verb, _files(d.get("candidate_files_changed", []), verbose)))
    L.append("%s    this side %s: %s"
             % (indent, verb, _files(d.get("other_files_changed", []), verbose)))
    if unrelated:
        L.append("%s    note: %s" % (indent, _wrap(d.get("note", ""), 74, indent + "          ")))
    return L


def _wrap(text, width, pad):
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return ("\n" + pad).join(lines) if lines else ""


# ── overrides from the command line ───────────────────────────────────────────────────────────

def parse_overrides(pairs, path):
    """Parse THIS RUN's operator layer from --override / --override-file. Returns it ALONE.

    --override <lineage>=<repo.git> sets the canonical member and, because naming a canonical
    against the topology IS the fork-came-home assertion, marks the family FORK-CAME-HOME.
    --override-file takes the same shape as OPERATOR_OVERRIDES for full control; --override then
    updates the file's entry for the same lineage key by key, so a `why` from the file survives.

    IT DOES NOT MERGE INTO OPERATOR_OVERRIDES, and that is the point. These two layers are kept
    apart end to end (see `_apply_overrides`): merging here is exactly how a typo on the command
    line used to silently overwrite the built-in jail rule and let raw topology name jail.git
    canonical. An entry here REPLACES the built-in rule for that lineage only when it is valid; a
    partial entry is therefore the WHOLE decision for that lineage, not a patch onto the built-in.
    """
    ov = {}
    if path:
        try:
            with open(path) as fh:
                data = json.load(fh)
        except (OSError, ValueError) as e:
            raise ForgeError("could not read --override-file %s: %s" % (path, e))
        if not isinstance(data, dict):
            raise ForgeError("--override-file %s must hold a JSON object keyed by lineage id" % path)
        for k, v in data.items():
            if not isinstance(v, dict):
                raise ForgeError("--override-file entry %r must be an object" % k)
            ov.setdefault(k, {}).update(v)
            ov[k].setdefault("source", "--override-file %s" % path)
    for p in pairs or []:
        if "=" not in p:
            raise ForgeError("--override wants <lineage-id>=<canonical-repo.git>, got %r" % p)
        k, v = p.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k or not v:
            raise ForgeError("--override wants <lineage-id>=<canonical-repo.git>, got %r" % p)
        ov.setdefault(k, {}).update({"canonical": v, "classification": FORK_CAME_HOME,
                                     "source": "--override on the command line"})
        ov[k].setdefault("why", "operator-supplied on the command line")
    return ov


# ── selftest ──────────────────────────────────────────────────────────────────────────────────

def _sh(cwd, *args):
    env = dict(os.environ)
    env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@localhost",
                "GIT_AUTHOR_DATE": "2020-01-01T00:00:00 +0000",
                "GIT_COMMITTER_DATE": "2020-01-01T00:00:00 +0000",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"})
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
    """Synthesize one throwaway family per class and prove each is classified correctly.

    Everything happens under one temp dir: no network, no live db, no writes outside it. The real
    forge is never opened. The synthetic repos are fingerprinted before and after classification to
    prove the tool only reads them.
    """
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond)))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name,
                                ("  -- %s" % detail) if detail and not cond else ""))

    if not have_git():
        print("git is not on PATH — cannot selftest")
        return 1

    base = tempfile.mkdtemp(prefix="forge_family_tree-selftest-")
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

        def commit(w, fname, text, msg):
            with open(os.path.join(w, fname), "w") as fh:
                fh.write(text)
            _sh(w, "add", fname)
            _sh(w, "commit", "--quiet", "-m", msg)

        def init_bare(name):
            """A bare repo whose HEAD is refs/heads/main — so a clone of it has a branch.

            --initial-branch is explicit because a host's init.defaultBranch would otherwise
            decide it, and family 7 needs HEAD to be wrong ONLY where it is made wrong on purpose.
            """
            bare = os.path.join(remotes, name)
            _sh(base, "init", "--bare", "--quiet", "--initial-branch=main", bare)
            return bare

        def publish(w, name):
            bare = init_bare(name)
            _sh(w, "push", "--quiet", bare, "main:main")
            return bare

        # Every family gets a DISTINCT root commit. The author/committer dates are pinned, so
        # two families whose root commit had the same tree and message would land on the same sha
        # and — correctly — cluster into ONE lineage. Distinct roots keep the families apart.
        # ---- family 1: IDENTICAL — one line, published twice under different names
        w = work("ident")
        commit(w, "a.txt", "ident root\n", "ident: root")
        commit(w, "b.txt", "two\n", "two")
        publish(w, "ident_home.git")
        publish(w, "ident_mirror.git")

        # ---- family 2: LINEAR — a stale alias published early, then the line grows
        w = work("lin")
        commit(w, "a.txt", "lin root\n", "lin: root")
        commit(w, "b.txt", "two\n", "two")
        publish(w, "lin_stale.git")
        stale_tip = _sh(w, "rev-parse", "HEAD")
        commit(w, "c.txt", "three\n", "three")
        publish(w, "lin_super.git")
        super_tip = _sh(w, "rev-parse", "HEAD")
        lin_lid = _sh(w, "rev-list", "--max-parents=0", "HEAD")[:10]   # a family with NO rule

        # ---- family 3: ADDITIVE-DIVERGED — two sides, DISJOINT files
        w = work("addbase")
        commit(w, "a.txt", "add root\n", "add: root")
        base_tip = _sh(w, "rev-parse", "HEAD")
        publish(w, "add_left.git")
        wl = os.path.join(base, "w-addleft")
        _sh(base, "clone", "--quiet", os.path.join(remotes, "add_left.git"), wl)
        commit(wl, "left_only.txt", "L\n", "left adds a file")
        _sh(wl, "push", "--quiet", os.path.join(remotes, "add_left.git"), "main:main")
        wr = os.path.join(base, "w-addright")
        _sh(base, "clone", "--quiet", os.path.join(remotes, "add_left.git"), wr)
        _sh(wr, "reset", "--quiet", "--hard", base_tip)
        commit(wr, "right_only.txt", "R\n", "right adds a different file")
        rb = init_bare("add_right.git")
        _sh(wr, "push", "--quiet", rb, "main:main")
        # add_left must also hold add_right's objects, or this would read as SPLIT-STORE
        _sh(base, "--git-dir", os.path.join(remotes, "add_left.git"),
            "fetch", "--quiet", rb, "+refs/heads/*:refs/remotes/right/*")

        # ---- family 4: CONFLICTING-DIVERGED — two sides changed the SAME file
        w = work("confbase")
        commit(w, "shared.txt", "conf root\n", "conf: root")
        cbase = _sh(w, "rev-parse", "HEAD")
        publish(w, "conf_left.git")
        wl = os.path.join(base, "w-confleft")
        _sh(base, "clone", "--quiet", os.path.join(remotes, "conf_left.git"), wl)
        commit(wl, "shared.txt", "left edit\n", "left edits shared.txt")
        _sh(wl, "push", "--quiet", os.path.join(remotes, "conf_left.git"), "main:main")
        wr = os.path.join(base, "w-confright")
        _sh(base, "clone", "--quiet", os.path.join(remotes, "conf_left.git"), wr)
        _sh(wr, "reset", "--quiet", "--hard", cbase)
        commit(wr, "shared.txt", "right edit\n", "right edits shared.txt")
        rb = init_bare("conf_right.git")
        _sh(wr, "push", "--quiet", rb, "main:main")
        _sh(base, "--git-dir", os.path.join(remotes, "conf_left.git"),
            "fetch", "--quiet", rb, "+refs/heads/*:refs/remotes/right/*")

        # ---- family 5: SPLIT-STORE — same root, neither store holds the other's tip
        w = work("splitroot")
        commit(w, "a.txt", "split root\n", "split: root")
        publish(w, "split_a.git")
        wb = os.path.join(base, "w-splitb")
        _sh(base, "clone", "--quiet", os.path.join(remotes, "split_a.git"), wb)
        commit(w, "a1.txt", "a1\n", "a1")
        _sh(w, "push", "--quiet", os.path.join(remotes, "split_a.git"), "main:main")
        for i in (1, 2, 3):
            commit(wb, "b%d.txt" % i, "b%d\n" % i, "b%d" % i)
        sb = init_bare("split_b.git")
        _sh(wb, "push", "--quiet", sb, "main:main")

        # ---- family 6: a repo with NO REFS AT ALL
        init_bare("norefs_empty.git")   # created and never pushed to: zero refs

        # ---- family 7: UNRESOLVABLE HEAD — HEAD points at a branch that does not exist.
        #      This is the live forge's dominant state and the trap that broke the prototype.
        w = work("unres")
        commit(w, "a.txt", "unres root\n", "unres: root")
        commit(w, "b.txt", "two\n", "two")
        b = publish(w, "unres_head.git")
        _sh(base, "--git-dir", b, "symbolic-ref", "HEAD", "refs/heads/master")  # master: absent
        unres_tip = _sh(w, "rev-parse", "HEAD")

        # ---- family 8: FORK-CAME-HOME — a linear family the operator reverses (the jail shape)
        w = work("home")
        commit(w, "a.txt", "home root\n", "home: root")
        publish(w, "home_repo.git")
        home_tip = _sh(w, "rev-parse", "HEAD")
        commit(w, "grabbag.txt", "expedient\n", "the fork adds a file")
        publish(w, "fork_repo.git")
        fork_tip = _sh(w, "rev-parse", "HEAD")
        home_root = _sh(w, "rev-list", "--max-parents=0", "HEAD")
        fork_lid = home_root[:10]

        # ---- family 9: RE-ROOTED — both repos hold BOTH roots, but each publishes a different
        #      one as main, so the root SETS match (one lineage) while the tips share NO commit.
        #      This is the live shape of notes_db and z3_mcp; it must not print a None count.
        w = work("reroot")
        commit(w, "old.txt", "the original line\n", "reroot: root A")
        _sh(w, "branch", "-m", "main", "lineA")
        _sh(w, "checkout", "--quiet", "--orphan", "lineB")
        _sh(w, "rm", "-rq", "--cached", ".")
        os.remove(os.path.join(w, "old.txt"))
        commit(w, "new.txt", "the re-rooted line\n", "reroot: root B")
        # X publishes line A as main; Y publishes line B as main. Both carry both roots.
        x = init_bare("reroot_a.git")
        _sh(w, "push", "--quiet", x, "lineA:main", "lineB:other")
        y = init_bare("reroot_b.git")
        _sh(w, "push", "--quiet", y, "lineB:main", "lineA:other")
        # reroot_a must hold reroot_b's tip too, or this reads as SPLIT-STORE rather than DIVERGED
        _sh(base, "--git-dir", x, "fetch", "--quiet", y, "+refs/heads/*:refs/remotes/b/*")
        rr_a_tip = _sh(base, "--git-dir", x, "rev-parse", "refs/heads/main")
        rr_b_tip = _sh(base, "--git-dir", y, "rev-parse", "refs/heads/main")

        # ---- family 10: THE JAIL SHAPE — the live jail.git / agent_tools_suite.git family,
        #      reproduced on throwaway repos: shared root, the home's tip an ancestor of the
        #      fork's, the fork adding a file, the fork holding the superset tip.
        #
        #      The members carry the REAL names on purpose, so the REAL NEVER_CANONICAL entry
        #      ("jail.git") governs this family unchanged — these checks exercise the shipped
        #      constant, not a stand-in for it. Only the lineage id must differ: a synthetic root
        #      commit cannot be handed the live sha 379ac05319, so the real rule is re-keyed to
        #      this family's id. Its SHAPE — canonical=agent_tools_suite.git, fork=jail.git — is
        #      what the checks below drive, and it is a copy of the shipped OPERATOR_OVERRIDES
        #      entry (asserted field by field under "JAIL RULE" further down).
        w = work("jail")
        commit(w, "ats.py", "the home repo's package\n", "ats: root")
        publish(w, "agent_tools_suite.git")
        ats_tip = _sh(w, "rev-parse", "HEAD")
        commit(w, "grabbag.py", "an expedient wrapped around some packages\n",
               "jail: the fork adds a file")
        publish(w, "jail.git")
        jail_tip = _sh(w, "rev-parse", "HEAD")
        jail_lid = _sh(w, "rev-list", "--max-parents=0", "HEAD")[:10]
        real_rule = OPERATOR_OVERRIDES["379ac05319"]
        JAIL_RULE = {"classification": real_rule["classification"],
                     "canonical": real_rule["canonical"], "fork": real_rule["fork"],
                     "why": real_rule["why"], "source": "selftest: the shipped rule, re-keyed"}

        # ---- the trap itself, asserted on the synthesized repo -----------------------------
        rc_v, _, _ = git(os.path.join(remotes, "unres_head.git"), "rev-parse", "--verify", "HEAD")
        rc_p, out_p, _ = git(os.path.join(remotes, "unres_head.git"), "rev-parse", "HEAD")
        ck("the trap is real: `rev-parse --verify HEAD` FAILS on unres_head.git", rc_v != 0)
        ck("the trap is real: `rev-parse HEAD` prints the literal string 'HEAD'", out_p == "HEAD")

        # ---- run the tool over the throwaway forge -----------------------------------------
        # The operator's standing layer for this throwaway forge: the re-keyed jail rule plus a
        # generic fork rule. Passed as `builtins`, NOT as `overrides`, so the checks below can put
        # a command-line layer on TOP of it and prove a refused --override falls back to it.
        builtins = {
            jail_lid: dict(JAIL_RULE),
            fork_lid: {"classification": FORK_CAME_HOME, "canonical": "home_repo.git",
                       "fork": "fork_repo.git", "why": "selftest: the fork is an expedient "
                       "grab-bag; home_repo is the home. It merges home and retires.",
                       "source": "selftest"},
        }
        before = _fingerprint(remotes)
        doc = build(remotes, builtins=builtins)
        after = _fingerprint(remotes)

        def fam_of(d, *repos):
            if not d:
                return None
            for l in d["lineages"]:
                if {m["repo"] for m in l["members"]} == set(repos):
                    return l
            return None

        def fam(*repos):
            return fam_of(doc, *repos)

        def rebuild(**kw):
            """build() over the throwaway forge, returning None if the run was REFUSED.

            A refusal is an OUTCOME these checks assert, so it must not escape as an exception and
            take every later check down with it: a crashed selftest prints no FAIL line and would
            look, to anyone reading its exit code alone, exactly like a passing one that reported
            nothing. Callers below treat None as "no tree was emitted" and fail their check.
            """
            kw.setdefault("builtins", builtins)
            try:
                return build(remotes, **kw)
            except ForgeError:
                return None

        def jail_fam(**kw):
            """The jail family as this override layer leaves it, or None if the run was refused."""
            return fam_of(rebuild(**kw), "jail.git", "agent_tools_suite.git")

        def canon(f):
            return (f or {}).get("canonical") or "(the run emitted no tree at all)"

        def refused(**kw):
            """The ForgeError message from a strict build, or "" if it did not refuse."""
            kw.setdefault("builtins", builtins)
            kw.setdefault("strict", True)
            try:
                build(remotes, **kw)
                return ""
            except ForgeError as e:
                return str(e)

        # 1. IDENTICAL
        f = fam("ident_home.git", "ident_mirror.git")
        ck("IDENTICAL: the two ingestion copies form ONE lineage", f is not None)
        ck("IDENTICAL: classified IDENTICAL", f and f["topology"] == IDENTICAL,
           f and f["topology"])
        ck("IDENTICAL: both duplicates reported", f and len(f["members"]) == 2)

        # 2. LINEAR
        f = fam("lin_super.git", "lin_stale.git")
        ck("LINEAR: classified LINEAR", f and f["topology"] == LINEAR, f and f["topology"])
        ck("LINEAR: the superset tip is lin_super.git's",
           f and f.get("superset", {}).get("tip") == super_tip)
        ck("LINEAR: lin_stale.git named a STALE ALIAS",
           f and [s["repo"] for s in f.get("stale_aliases", [])] == ["lin_stale.git"])
        ck("LINEAR: the stale alias's tip is the earlier commit",
           f and f["stale_aliases"][0]["tip"] == stale_tip)

        # 3. ADDITIVE-DIVERGED
        f = fam("add_left.git", "add_right.git")
        ck("ADDITIVE-DIVERGED: classified DIVERGED", f and f["topology"] == DIVERGED,
           f and f["topology"])
        d = (f.get("diverged") or [{}])[0] if f else {}
        ck("ADDITIVE-DIVERGED: mode is ADDITIVE (disjoint files)", d.get("mode") == ADDITIVE,
           d.get("mode"))
        ck("ADDITIVE-DIVERGED: merge-base is the shared root commit",
           d.get("merge_base") == base_tip)
        ck("ADDITIVE-DIVERGED: no conflicting files reported", d.get("conflicting_files") == [])
        ck("ADDITIVE-DIVERGED: each side's unique commit counted",
           d.get("candidate_unique_commits") == 1 and d.get("other_unique_commits") == 1,
           "%s/%s" % (d.get("candidate_unique_commits"), d.get("other_unique_commits")))

        # 4. CONFLICTING-DIVERGED
        f = fam("conf_left.git", "conf_right.git")
        ck("CONFLICTING-DIVERGED: classified DIVERGED", f and f["topology"] == DIVERGED,
           f and f["topology"])
        d = (f.get("diverged") or [{}])[0] if f else {}
        ck("CONFLICTING-DIVERGED: mode is CONFLICTING", d.get("mode") == CONFLICTING,
           d.get("mode"))
        ck("CONFLICTING-DIVERGED: the shared file is named as the reconciliation cost",
           d.get("conflicting_files") == ["shared.txt"], str(d.get("conflicting_files")))

        # 5. SPLIT-STORE
        f = fam("split_a.git", "split_b.git")
        ck("SPLIT-STORE: classified SPLIT-STORE", f and f["topology"] == SPLIT_STORE,
           f and f["topology"])
        ck("SPLIT-STORE: the absent tip is named, not guessed at",
           f and bool(f.get("absent_tips")))
        ck("SPLIT-STORE: RESOLVED after fetch, not left unknown",
           f and f.get("resolved_as") in (IDENTICAL, LINEAR, DIVERGED),
           f and f.get("resolved_as"))
        ck("SPLIT-STORE: resolves to DIVERGED (the two sides really did split)",
           f and f.get("resolved_as") == DIVERGED, f and f.get("resolved_as"))

        # 6. NO-REFS
        ck("NO-REFS: norefs_empty.git is REPORTED explicitly",
           any(r["repo"] == "norefs_empty.git" for r in doc["no_refs"]))
        ck("NO-REFS: it joins no lineage",
           not any("norefs_empty.git" in {m["repo"] for m in l["members"]}
                   for l in doc["lineages"]))
        ck("NO-REFS: it is not silently dropped — the count is in the totals",
           doc["totals"]["no_refs"] == 1, str(doc["totals"]["no_refs"]))

        # 7. UNRESOLVABLE HEAD — the family must survive with the right tip
        f = fam("unres_head.git")
        ck("UNRESOLVABLE-HEAD: the repo is NOT dropped (the prototype's bug)", f is not None)
        ck("UNRESOLVABLE-HEAD: its tip resolved from refs/heads, matching the real branch",
           f and f["members"][0]["tip"] == unres_tip)
        ck("UNRESOLVABLE-HEAD: recorded as head_resolvable=False",
           f and f["members"][0]["head_resolvable"] is False)
        ck("UNRESOLVABLE-HEAD: the totals count it", doc["totals"]["unresolvable_head"] >= 1)

        # 8. FORK-CAME-HOME
        f = fam("home_repo.git", "fork_repo.git")
        ck("FORK-CAME-HOME: the topology is LINEAR (the same shape as LINEAR)",
           f and f["topology"] == LINEAR, f and f["topology"])
        ck("FORK-CAME-HOME: the classification is FORK-CAME-HOME",
           f and f["classification"] == FORK_CAME_HOME, f and f["classification"])
        ck("FORK-CAME-HOME: canonical is the HOME, not the topological superset",
           f and f["canonical"] == "home_repo.git", f and f.get("canonical"))
        ck("FORK-CAME-HOME: the fork holds the superset tip yet is NOT canonical",
           f and f.get("superset", {}).get("tip") == fork_tip
           and f["canonical"] != "fork_repo.git")
        ck("FORK-CAME-HOME: a fork edge points fork -> home",
           f and f.get("fork_edges") and f["fork_edges"][0]["direction"]
           == "fork_repo.git -> home_repo.git")
        ck("FORK-CAME-HOME: the proposal says merge home then omit the fork",
           f and "OMIT fork_repo.git" in f["proposed_direction"])
        ck("FORK-CAME-HOME: counted as LINEAR in the topology totals",
           doc["totals"]["by_topology"][LINEAR] >= 1)
        ck("FORK-CAME-HOME: counted as FORK-CAME-HOME in the classification totals",
           # two such families in this throwaway forge: home/fork, and the jail shape below
           doc["totals"]["by_classification"].get(FORK_CAME_HOME) == 2,
           str(doc["totals"]["by_classification"]))

        # 9. RE-ROOTED — one lineage (same root set), tips with no merge-base
        f = fam("reroot_a.git", "reroot_b.git")
        ck("RE-ROOTED: the two repos share a root SET, so they are ONE lineage", f is not None)
        ck("RE-ROOTED: classified DIVERGED", f and f["topology"] == DIVERGED, f and f["topology"])
        d = (f.get("diverged") or [{}])[0] if f else {}
        ck("RE-ROOTED: flagged unrelated_histories with NO merge-base",
           d.get("unrelated_histories") is True and d.get("merge_base") is None,
           "%s / %s" % (d.get("unrelated_histories"), d.get("merge_base")))
        ck("RE-ROOTED: commit counts are real numbers, never None (the bug this case caught)",
           isinstance(d.get("candidate_unique_commits"), int)
           and isinstance(d.get("other_unique_commits"), int),
           "%s / %s" % (d.get("candidate_unique_commits"), d.get("other_unique_commits")))
        ck("RE-ROOTED: disjoint trees read as ADDITIVE, not a bogus conflict",
           d.get("mode") == ADDITIVE and d.get("conflicting_files") == [],
           "%s / %s" % (d.get("mode"), d.get("conflicting_files")))
        ck("RE-ROOTED: each side's tree contents are reported",
           sorted(d.get("candidate_files_changed", []) + d.get("other_files_changed", []))
           == ["new.txt", "old.txt"],
           str(d.get("candidate_files_changed")) + str(d.get("other_files_changed")))
        rr = render({"totals": doc["totals"], "no_refs": doc["no_refs"], "remotes": "x",
                     "lineages": [f]}) if f else ""
        ck("RE-ROOTED: the tree says UNRELATED and prints no 'None'",
           "UNRELATED histories" in rr and "None" not in rr)

        # ---- 10. THE JAIL SHAPE, end to end ------------------------------------------------
        # These drive the TOOL'S OUTPUT over the jail-shaped family above. (An earlier selftest
        # only asserted the OPERATOR_OVERRIDES dict literal — which is why it stayed green while
        # the tool itself could be made to print jail.git as CANONICAL.)
        f = fam("jail.git", "agent_tools_suite.git")
        ck("JAIL: the family is found and its topology is LINEAR (jail holds the superset tip)",
           f and f["topology"] == LINEAR and f.get("superset", {}).get("tip") == jail_tip,
           f and f["topology"])
        ck("JAIL: classified FORK-CAME-HOME", f and f["classification"] == FORK_CAME_HOME,
           f and f["classification"])
        ck("JAIL: agent_tools_suite.git is canonical, NOT the topological superset jail.git",
           f and f["canonical"] == "agent_tools_suite.git", f and f.get("canonical"))
        ck("JAIL: the direction is REVERSED — jail merges home, then is omitted",
           f and f["fork_edges"][0]["direction"] == "jail.git -> agent_tools_suite.git"
           and "OMIT jail.git" in f["proposed_direction"])
        ck("JAIL: the home trails the fork, exactly the live shape (ats is behind jail)",
           f and [(s["repo"], s["tip"]) for s in f.get("stale_aliases", [])]
           == [("agent_tools_suite.git", ats_tip)],
           f and str(f.get("stale_aliases")))

        # THE REPORTED DEFECT, in every reported form. Each of these is a plausible operator typo
        # aimed at the jail lineage. Every one of them once ended with canonical=jail.git,
        # classification=LINEAR and exit 0. The decision must survive all of them.
        typos = [
            ("--override with '.git' missing", {"canonical": "agent_tools_suite"}),
            ("--override naming a nickname", {"canonical": "ats.git"}),
            ("--override with the wrong case", {"canonical": "Agent_Tools_Suite.git"}),
            ("--override-file setting only a typo'd fork", {"fork": "jail"}),
            ("--override-file entry that omits canonical entirely",
             {"classification": "LINEAR"}),
        ]
        for label, entry in typos:
            e = dict(entry)
            e.setdefault("source", "selftest: a typo")
            f2 = jail_fam(overrides={jail_lid: e})
            ck("JAIL/typo (%s): canonical falls back to the operator rule, NOT to topology"
               % label, f2 and f2["canonical"] == "agent_tools_suite.git", canon(f2))
            ck("JAIL/typo (%s): jail.git is still never canonical" % label,
               f2 and f2["canonical"] != "jail.git", canon(f2))
            ck("JAIL/typo (%s): still FORK-CAME-HOME, not raw LINEAR" % label,
               f2 and f2["classification"] == FORK_CAME_HOME,
               (f2 or {}).get("classification") or "(no tree)")
            ck("JAIL/typo (%s): the refusal is recorded, not swallowed" % label,
               f2 and any(r["source"] == USER_LAYER for r in f2["rejected_overrides"])
               and any("REJECTED" in n for n in f2["notes"]))
            ck("JAIL/typo (%s): a strict run REFUSES rather than emitting a tree" % label,
               bool(refused(overrides={jail_lid: e})))
            ck("JAIL/typo (%s): the ASCII tree never marks jail.git canonical" % label,
               f2 and "* jail.git" not in "\n".join(_render_lineage(f2)))

        # A VALID member name is not a loophole: jail.git IS a member, so no typo-check could ever
        # catch this one. NEVER_CANONICAL is what refuses it.
        for label, entry in (("--override 379ac05319=jail.git", {"canonical": "jail.git"}),
                             ("an override-file naming jail home",
                              {"canonical": "jail.git", "classification": FORK_CAME_HOME,
                               "fork": "agent_tools_suite.git"})):
            f2 = jail_fam(overrides={jail_lid: dict(entry, source="selftest")})
            ck("JAIL/forbidden (%s): refused even though jail.git IS a real member" % label,
               f2 and f2["canonical"] == "agent_tools_suite.git", canon(f2))
            msg = refused(overrides={jail_lid: dict(entry, source="selftest")})
            ck("JAIL/forbidden (%s): a strict run refuses and says why" % label,
               "ruled OUT as a destination" in msg, msg or "(no refusal)")

        # A family cannot be its own fork. Both spellings: naming the fork explicitly, and letting
        # it default to the candidate. Either would print the nonsense edge "X -> X".
        for label, entry in (("fork named explicitly",
                              {"canonical": "lin_super.git", "fork": "lin_super.git",
                               "classification": FORK_CAME_HOME}),
                             ("fork defaulting to the candidate",
                              {"canonical": "lin_super.git", "classification": FORK_CAME_HOME})):
            msg = refused(overrides={lin_lid: dict(entry, source="selftest")})
            ck("SELF-FORK (%s): refused — a fork cannot merge into itself" % label,
               "cannot merge into itself" in msg, msg or "(no refusal)")

        # THE BACKSTOP: with the operator rule GONE, topology nominates jail.git — and the tool
        # must refuse to emit that tree rather than print it. This is what makes the guarantee
        # structural instead of a default that a missing rule can silently undo.
        no_rule = {k: v for k, v in builtins.items() if k != jail_lid}
        try:
            build(remotes, builtins=no_rule)
            ck("JAIL/backstop: with no operator rule, the tool REFUSES to emit a jail-canonical "
               "tree", False, "it emitted one")
        except ForgeError as e:
            ck("JAIL/backstop: with no operator rule, the tool REFUSES to emit a jail-canonical "
               "tree", "REFUSING to emit" in str(e) and "jail.git" in str(e), str(e))

        # CONTROL (the adversary's own): the SAME typo against a lineage with NO operator rule
        # must still fall back to TOPOLOGY — there is no decision to protect, so the fallthrough
        # must not invent one. This is what proves the fix is specific, not a blanket suppression.
        f2 = fam_of(rebuild(overrides={lin_lid: {"canonical": "nope.git", "source": "selftest"}}),
                    "lin_super.git", "lin_stale.git")
        ck("CONTROL: a refused override on a lineage with NO operator rule falls back to topology",
           f2 and f2["canonical"] == "lin_super.git" and f2["classification"] == LINEAR
           and f2["override_applied"] is False, canon(f2))
        ck("CONTROL: and it is refused by a strict run all the same",
           bool(refused(overrides={lin_lid: {"canonical": "nope.git", "source": "selftest"}})))

        # A VALID override must still be obeyed — the guard must not have broken overriding itself.
        f2 = fam_of(rebuild(overrides={lin_lid: {"canonical": "lin_stale.git",
                                                 "classification": FORK_CAME_HOME,
                                                 "why": "selftest: the operator reverses this one",
                                                 "fork": "lin_super.git", "source": "selftest"}}),
                    "lin_super.git", "lin_stale.git")
        ck("OVERRIDE: a VALID operator override is obeyed and marked applied",
           f2 and f2["canonical"] == "lin_stale.git"
           and f2["classification"] == FORK_CAME_HOME and f2["override_applied"] is True
           and f2["override_source"] == USER_LAYER, canon(f2))
        f3 = jail_fam(overrides={jail_lid: {"canonical": "agent_tools_suite.git",
                                            "classification": LINEAR, "source": "selftest"}})
        ck("OVERRIDE: a valid one beats the built-in rule for the same lineage",
           f3 and f3["classification"] == LINEAR and f3["override_source"] == USER_LAYER,
           (f3 or {}).get("classification") or "(no tree)")
        ck("OVERRIDE: a run with no overrides at all is clean (no spurious refusals)",
           not any(l["rejected_overrides"] for l in doc["lineages"]))

        # the jail rule must be data the operator can point at, keyed to the LIVE lineage
        ck("JAIL RULE: the built-in rule is keyed by the live root 379ac05319",
           "379ac05319" in OPERATOR_OVERRIDES)
        ck("JAIL RULE: it names agent_tools_suite.git canonical, never jail.git",
           OPERATOR_OVERRIDES["379ac05319"]["canonical"] == "agent_tools_suite.git")
        ck("JAIL RULE: jail.git is the FORK that merges home and retires",
           OPERATOR_OVERRIDES["379ac05319"]["fork"] == "jail.git")
        ck("JAIL RULE: jail.git is ruled out as a destination independently of that rule",
           "jail.git" in NEVER_CANONICAL)
        ck("JAIL RULE: the two agree — no rule may name a ruled-out repo canonical",
           not any(r.get("canonical") in NEVER_CANONICAL for r in OPERATOR_OVERRIDES.values()))

        # totals must add up and the render must not explode
        ck("TOTALS: every lineage is counted exactly once by topology",
           sum(doc["totals"]["by_topology"].values()) == doc["totals"]["lineages"])
        ck("TOTALS: repos in lineages + no-refs == repos walked",
           doc["totals"]["repos_in_lineages"] + doc["totals"]["no_refs"]
           == doc["totals"]["repos_walked"])
        txt = render(doc)
        ck("RENDER: the ASCII tree renders and names the no-refs repo",
           "norefs_empty.git" in txt and "FORGE FAMILY TREE" in txt)
        ck("RENDER: the tree never calls the fork canonical",
           "fork_repo.git" in txt and "* fork_repo.git" not in txt)
        ck("RENDER: the tree shows jail.git but never marks it canonical (the '*' bullet)",
           "jail.git" in txt and "* jail.git" not in txt)
        ck("RENDER: the tree marks agent_tools_suite.git as the canonical home",
           "* agent_tools_suite.git" in txt)
        ck("JSON: the document is serialisable", bool(json.dumps(doc)))

        # side effects: the tool must only READ the repos it inspects
        ck("NO SIDE EFFECTS: the inspected repos are byte-identical after the run",
           before == after)
        ck("NO SIDE EFFECTS: no scratch store was left behind",
           not any(n.startswith("fft-split-store-")
                   for n in os.listdir(tempfile.gettempdir())))

        bad_checks = [n for n, ok in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s"
              % (len(checks) - len(bad_checks), len(checks),
                 ("   FAILED: " + "; ".join(bad_checks)) if bad_checks else ""))
        return 1 if bad_checks else 0
    except ForgeError as e:
        # A crash is not a pass. Without this, an unexpected refusal would abort the run with no
        # FAIL line printed at all, and the only signal left would be an exit code that a reader
        # could easily mistake for "nothing to report".
        print("\n== selftest == ABORTED after %d checks by an unexpected error: %s" % (len(checks), e))
        return 1
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ── cli ───────────────────────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="forge_family_tree.py",
        description="Cluster config/forge/remotes/*.git into lineages and classify each "
                    "(IDENTICAL / LINEAR / FORK-CAME-HOME / DIVERGED / SPLIT-STORE). "
                    "PART 1 of 2: discovers and classifies; never retires or merges anything.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Tips are resolved from refs/heads, NEVER from HEAD: most of these bare repos have "
               "a HEAD symref pointing at a branch that does not exist, so `rev-parse --verify "
               "HEAD` fails on them. Repos with no refs at all are reported, never skipped.")
    ap.add_argument("--remotes", help="the bare-repo directory "
                                      "(default: config/forge/remotes, found by walking up)")
    ap.add_argument("--json", metavar="PATH",
                    help="write the machine-readable JSON here ('-' for stdout, "
                         "which suppresses the ASCII tree)")
    ap.add_argument("--lineage", metavar="NAME",
                    help="show only the family matching this repo name, lineage name, or id")
    ap.add_argument("--override", action="append", metavar="ID=REPO.git",
                    help="name REPO.git canonical for lineage ID and mark it FORK-CAME-HOME "
                         "(repeatable; takes precedence over the built-in operator decisions). "
                         "REPO.git must be a member of that lineage and must not be a repo ruled "
                         "out as a destination (NEVER_CANONICAL) — either way the run is refused "
                         "with exit 2 and the built-in operator decision stands untouched")
    ap.add_argument("--override-file", metavar="PATH",
                    help="a JSON object keyed by lineage id, same shape as OPERATOR_OVERRIDES. An "
                         "entry REPLACES the built-in rule for its lineage (it is not merged into "
                         "it), so a partial entry is the whole decision for that lineage")
    ap.add_argument("--verbose", action="store_true", help="more detail per lineage")
    ap.add_argument("--selftest", action="store_true",
                    help="synthesize one throwaway family per class in a temp dir and prove each "
                         "is classified correctly (no network, no live db)")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    try:
        remotes = args.remotes or default_remotes()
        if not remotes:
            raise ForgeError(
                "could not find config/forge/remotes by walking up from %s — pass --remotes PATH"
                % os.path.dirname(os.path.realpath(__file__)))
        remotes = os.path.realpath(remotes)
        overrides = parse_overrides(args.override, args.override_file)
        # strict: a refused override is an input error worth exit 2, not a silent change of answer
        doc = build(remotes, overrides=overrides, only=args.lineage, strict=True)
    except ForgeError as e:
        sys.stderr.write("forge_family_tree: %s\n" % e)
        return 2
    except subprocess.TimeoutExpired:
        sys.stderr.write("forge_family_tree: a git command timed out — is a repo corrupt?\n")
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
            sys.stderr.write("forge_family_tree: could not write --json %s: %s\n" % (args.json, e))
            return 2
        print("wrote %s" % args.json)
    print(render(doc, verbose=args.verbose))
    return 0


if __name__ == "__main__":
    sys.exit(main())
