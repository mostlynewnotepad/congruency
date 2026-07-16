#!/usr/bin/env python3
"""regression_capture.py — a CONFIRMED auditor finding becomes a red, worker-immutable regression
test that the fix must turn green (#440).

Today a failed round journals FINDINGS as free-text and re-runs a fresh worker; nothing about the
failure is captured as a test, so the same defect can recur unguarded. The adversary already PROVES
the failure by executing the required behavior (FOCUS["build"]["audit_focus"], pair_loop.py), so at
judgment time it HOLDS the concrete {entrypoint, input, observed} — it just summarizes it to prose
and drops the repro. This module captures that repro and mints a regression test from it.

THE ORACLE IS THE ORIGINAL — NOT THE WORKER, NOT THE FINDING. A forge rewrite is behavior-preserving
against the original module, whose bytes are embedded VERBATIM in the ticket body between the marker
lines `===ORIGINAL SOURCE (...)===` and `===END SOURCE===` (forge_refactor_ticketer.py:604-612,
embed_source():854-891). `expected` is therefore DERIVED here, by executing `entrypoint(input)`
against those embedded bytes in a throwaway directory. The worker's output is never consulted for
correctness, and the finding's `observed` field is recorded but never trusted. The worker cannot
define correctness, and neither can the adversary.

WHAT IT DOES, in the order it does it:

    1. SCHEMA    repros() reads a fail verdict's structured repro — {entrypoint, input, observed} —
                 from any of three backward-compatible spellings (see repros()). `expected` is NOT
                 part of the schema: it is derived (2). A verdict with no repro mints nothing and is
                 not an error: prose findings are still first-class.
    2. ORACLE    parse_original() lifts the original's bytes out of the ticket body (handling the
                 nonce fence, the base64 case, and REFUSING a truncated excerpt); the entrypoint is
                 executed against them in a temp dir.
    3. MINT      a test asserting `entrypoint(input) == expected` is generated into the HARNESS-OWNED
                 path `tests/regression/` under the unit's package.
    4. VALIDATE  the minted test is proven RED against the exact worker blob that produced the
                 finding, GREEN against the original, and RED again under mutation — before it is
                 written. A test that fails any of the three is REJECTED and nothing is written.
                 The harness self-checks every test it mints; see validate_note().
    5. GUARD     guard() restores any minted test the worker modified or deleted, from a ledger kept
                 OUTSIDE the worktree (see Ledger, and WORKER-IMMUTABILITY below).

WORKER-IMMUTABILITY — WHAT pair_loop ENFORCES, AND WHAT IT DOES NOT (#440 asked; this is the answer,
and `--verify-scope` re-proves it on demand against the live pair_loop):

  * A SINGLE-FILE deliverable (every tool, tag and doc) commits exactly one path, so a worker edit
    under `tests/regression/` is a STRAY: journaled, never committed, reaped with the worktree
    (pair_loop.py commit_deliverable(), and its `strays` line in commit_note()). Excluded. ENFORCED.
  * A PACKAGE deliverable — a forge unit, which is the ONLY kind this ticket's capture ever runs on
    — commits the WHOLE package directory (#409, policy 8). `<pkg>/tests/regression/` is INSIDE that
    directory, so commit_deliverable()'s `porcelain(-uall, -- pkg)` sweep stages whatever the worker
    left there. A worker that weakens or deletes the guard has its edit COMMITTED and MERGED.
    NOT ENFORCED. The path scoping alone does not make the guard immutable on the path that matters.

  So this module supplies the enforcement rather than assuming it. guard() is called before each
  round's commit; it compares every minted test against the Ledger and RESTORES any that was touched.
  The ledger is the authority and it lives in the repo's git common directory (ledger_dir()), beside
  the harness's own cross-process lock (Forge.lockfile, pair_loop.py) — not in the worktree, because
  the worker's Write tool reaches every path under the worktree and an in-tree manifest would be
  exactly as forgeable as the test it vouches for. Restoring is not erasing: the worker's module is
  never touched, only the harness's own artifact is put back.

ANTI-GAMING:

  * ADDITIVE FLOOR, NOT THE GATE. Nothing here returns a verdict or can pass a round. The adversarial
    auditor still executes the required behavior every round; overfitting the one captured input does
    not pass anything. capture() returns no "verdict" key, by construction (--selftest checks this).
  * INVISIBLE IN THE TWO CHANNELS THAT REACH THE WORKER. worker_findings() is the only text that
    reaches a worker's birth prompt, and it yields PROSE ONLY — the repro cannot ride along, because
    in every accepted spelling the repro is a sibling of the prose, never inside it. It also scrubs
    an adversary that tries to smuggle capture details into its prose (leaks_capture()). Since the
    lesson harvester composes its notes from those same findings (harvest(), pair_loop.py), and the
    playbook is compiled from those lessons (--compile-playbook), the capture details cannot reach
    docs/PLAYBOOK.md either. --selftest proves the whole chain — verdict -> worker prompt -> lesson
    -> playbook body — clean, using pair_loop's REAL prompt template and REAL body expression.
  * NOT A SECRET FILE. The minted test lives in the worktree and the worker can read it; that is
    unavoidable, because a guard that does not land is not a guard. It is stated here rather than
    over-claimed: "invisible" means the two channels above, not the filesystem. Reading it wins
    nothing — it is a floor, not the gate.

TOGGLE — DEFAULT OFF, and OFF is a byte-for-byte no-op:

    --regression-capture off   (THE DEFAULT) capture is off. Nothing is read, executed or written;
                               capture() returns immediately with {"enabled": False}. --selftest
                               proves this with a before/after tree snapshot.
    --regression-capture on    forced on, whatever registry.json says.
    --regression-capture auto  registry.json's {"regression_capture": {"enabled": true|false}}
                               decides; absent or false means off. This is the key's live setting:
                               `auto` is what lets an A/B flip capture with no code edit and no flag
                               change. An explicit `on`/`off` outranks the registry.

USAGE — this module is a LIBRARY with a self-proving CLI. It is called by pair_loop through a thin
hook (`--print-hook` prints the exact patch; the hook is two one-line calls, deliberately NOT a
pair_loop rewrite — the #279 regression came from exactly that):

    python3 regression_capture.py --selftest        # prove the method; no network, no db, no repo writes
    python3 regression_capture.py --verify-scope    # re-prove the scoping claims above against pair_loop
    python3 regression_capture.py --print-hook      # the exact pair_loop.py patch, and why each line

--selftest builds a THROWAWAY synthetic unit (a tiny original with a known bug and a repro) plus a
THROWAWAY git repo, and proves: red-on-buggy, green-on-original, mutation-resistance, bogus-capture
rejection, oracle-independence from both the worker and the finding, worker-scope exclusion of
tests/regression/, guard-restores-tampering, no leak into prompt/lesson/playbook, and that OFF
changes nothing. It never touches this repo, the db, or the network.

Exit codes:
    0  every check passed (--selftest) / the scope report printed (--verify-scope, --print-hook)
    1  at least one check FAILED
    2  unexpected — a Variant-A bug report was filed to the registry's bug_reports sink
"""
import argparse
import base64
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback


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


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks)."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "regression_capture.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:],
                "note": "regression_capture (#440) — auditor repro -> red regression test",
            }) + "\n")
    except Exception:  # noqa: BLE001
        pass


class Unexpected(RuntimeError):
    pass


# ── the embedded-original fence (forge_refactor_ticketer.py:604-612 — its OWNER) ─────────────────
# Mirrored, not imported: this module must stand alone (it is called from a hook and must not drag a
# ticket factory in with it). Mirroring risks DRIFT, so --selftest imports the owner and asserts
# these five constants still match it — if the fence ever moves, that check goes red here first.
EMBED_BEGIN_SENTINEL = "===ORIGINAL SOURCE"
EMBED_END_SENTINEL = "===END SOURCE"
EMBED_BEGIN_FMT = "===ORIGINAL SOURCE (%s)==="
EMBED_END = "===END SOURCE==="
EMBED_BEGIN_NONCE_FMT = "===ORIGINAL SOURCE:%s (%s)==="
EMBED_END_NONCE_FMT = "===END SOURCE:%s==="

# The four block descriptions the owner can emit (EMBED_DESC_* there). Only the two substrings below
# are load-bearing here: "base64" says decode it, "TRUNCATED" says REFUSE it — an excerpt is not an
# oracle, and a rewrite judged against a prefix of the original is judged against a different program
# (the owner's own words: "a rewrite of a truncated original is not behavior-preserving").
DESC_B64_MARK = "base64"
DESC_CUT_MARK = "TRUNCATED"

# ── the harness-owned path, and the toggle ───────────────────────────────────────────────────────
TESTS_DIR = "tests/regression"          # relative to the unit's package root; HARNESS-OWNED
MODES = ("on", "off", "auto")
DEFAULT_MODE = "off"                    # #440: default OFF; OFF is a byte-for-byte no-op
REGISTRY_KEY = "regression_capture"     # registry.json {"regression_capture": {"enabled": bool}}

RUN_TIMEOUT = 20                        # seconds for one entrypoint execution or one test run
SENTINEL = "<<<RC>>>"                   # the runner's outcome line marker (module prints are ignored)
LEDGER_DIRNAME = "regression-capture"   # under the repo's git COMMON dir; never under the worktree

# Re-introducing the defect must turn the test red (#440's mutation-resistance invariant). The probe
# shadows the entrypoint with a stub returning this sentinel: a value no real entrypoint returns, so
# a test that stays green under it is asserting nothing about the entrypoint's actual output.
MUTANT_SENTINEL = {"__regression_capture_mutant__": True}

# Text that must never reach a worker's birth prompt or docs/PLAYBOOK.md (see leaks_capture()).
# Each is a phrase that would tell a worker there is an assertion to satisfy. The bare word
# "regression" is NOT one of them: pair_loop's own docstring says "the #279 regression", and a
# detector that fires on that would redact honest prose and prove nothing.
CAPTURE_MARKERS = ("tests/regression", "regression_capture", "regression-capture",
                   "regression guard", "make this assertion pass", "make the assertion pass",
                   "captured repro", "structured repro")


# ── paths (mirrors pair_loop.py's _parts(): git speaks '/', os.path speaks os.sep) ───────────────
def _parts(path):
    return [p for p in os.path.normpath(path).replace(os.sep, "/").split("/") if p not in ("", ".")]


def is_harness_owned(path):
    """True if `path` is the harness-owned regression directory, or anything under it.

    Matched as consecutive path COMPONENTS, so it catches the directory and its contents at any
    depth, under any package root: `tests/regression`, `<pkg>/tests/regression/test_x.py`, and
    `checkouts/current/forge2/x/tests/regression/` are all owned. A string prefix compare would be a
    lie here for the same reason it is in pair_loop's under(): `tests/regression_notes.md` is not
    this directory.
    """
    parts = _parts(path)
    for i in range(len(parts) - 1):
        if parts[i] == "tests" and parts[i + 1] == "regression":
            return True
    return False


def tests_dir_for(deliverable, package=None):
    """The harness-owned `tests/regression/` under the unit's package (repo-relative, '/'-joined).

    `package` is pair_loop's already-resolved package root (Forge.package_root(), #409) — the same
    value that decides the commit's scope, passed in rather than re-derived, so the guard cannot land
    outside the fileset that gets committed. With no package (a lone-file deliverable) it falls back
    to the deliverable's own directory, and the minted test is then outside the single-file commit
    scope — which capture() handles by staging it explicitly. See stage in capture()'s docstring.
    """
    root = package or "/".join(_parts(deliverable)[:-1])
    return "/".join([p for p in (root, TESTS_DIR) if p])


def capture_enabled(mode=DEFAULT_MODE, registry=None):
    """Is capture on? The toggle, in three explicit states (see TOGGLE in the module docstring).

    "off" (the default) is off whatever registry.json says, and "on" is on whatever it says: an
    explicit flag outranks the file. "auto" is the state in which the registry key is live, so an A/B
    can flip capture by editing registry.json alone — no code edit, no flag change.
    """
    if mode not in MODES:
        raise Unexpected("regression-capture mode %r is not one of %s" % (mode, "|".join(MODES)))
    if mode == "on":
        return True
    if mode == "off":
        return False
    reg = REGISTRY if registry is None else registry
    return bool((reg.get(REGISTRY_KEY) or {}).get("enabled", False))


# ── 1. the structured repro schema (backward compatible: prose findings still mint nothing) ──────
def repros(verdict):
    """Every structured repro a FAIL verdict carries, in any of three spellings. [] if none.

    A repro is {"entrypoint": "<dotted attr path in the deliverable's module>",
                "input": {"args": [...], "kwargs": {...}},
                "observed": <recorded, NEVER trusted — see below>}
    `expected` is deliberately NOT in the schema. It is DERIVED from the ticket's embedded original
    (capture()), because a verdict that could state `expected` would let the adversary define
    correctness, exactly as letting the worker's output define it would.

    The three accepted spellings, all backward compatible with today's {"verdict","findings"}:
        {"verdict":"fail","findings":["..."],"repro":{...}}                    one repro
        {"verdict":"fail","findings":["..."],"repros":[{...},{...}]}           many
        {"verdict":"fail","findings":[{"finding":"...","repro":{...}}, "..."]} per-finding
    The first two keep `findings` a list of plain strings, which is what pair_loop already joins and
    journals — nothing downstream changes. The third is why worker_findings() exists: a dict in that
    list would otherwise reach pair_loop's `"; ".join(vres.get("findings", []))` and raise.

    `observed` is what the adversary says it saw. It is carried onto the journal for the record and
    is never an input to any decision: the red-on-buggy check re-executes the worker blob and reads
    the truth off it. An adversary that lies in `observed` changes nothing.
    """
    v = verdict or {}
    out = []
    if isinstance(v.get("repro"), dict):
        out.append(dict(v["repro"]))
    for r in (v.get("repros") or []):
        if isinstance(r, dict):
            out.append(dict(r))
    for f in (v.get("findings") or []):
        if isinstance(f, dict) and isinstance(f.get("repro"), dict):
            r = dict(f["repro"])
            r.setdefault("finding", _finding_text(f))
            out.append(r)
    return out


def _finding_text(f):
    if isinstance(f, dict):
        for k in ("finding", "text", "note", "summary"):
            if isinstance(f.get(k), str) and f[k].strip():
                return f[k]
        return ""
    return str(f)


def leaks_capture(text):
    """The capture markers present in `text` — [] means it leaks nothing. The anti-gaming detector.

    Applied to anything that could reach a worker or the playbook: a birth prompt, a finding, a
    lesson note, the --compile-playbook body. --selftest runs it over all four, built from
    pair_loop's real templates.
    """
    low = (text or "").lower()
    return sorted({m for m in CAPTURE_MARKERS if m in low})


def scrub(text):
    """`text` with every capture marker redacted — an adversary cannot smuggle the mechanism into its
    prose. Case-insensitive, and it preserves everything else the finding says."""
    out = text or ""
    low = out.lower()
    for m in CAPTURE_MARKERS:
        i = low.find(m)
        while i >= 0:
            out = out[:i] + "[redacted]" + out[i + len(m):]
            low = out.lower()
            i = low.find(m)
    return out


def worker_findings(verdict, scrub_markers=True):
    """The findings AS A WORKER MAY SEE THEM: prose only, every structured repro stripped.

    This is the one text that reaches a worker's birth prompt (pair_loop.py splices `findings` into
    WORKER_PROMPT's %(findings)s slot) and, through harvest(), the one text that reaches a lesson and
    from there docs/PLAYBOOK.md. So it is where the mechanism is kept invisible — and it is invisible
    structurally, not by filtering: in every spelling repros() accepts, the repro is a SIBLING of the
    prose, so there is nothing to strip out of the prose in the first place. The dict spelling is
    flattened to its prose here, which is also what stops a dict reaching pair_loop's `"; ".join`.

    `scrub_markers=False` disables the leaks_capture() redaction and makes this a pure flattener. The
    documented hook passes the capture mode through, so with capture OFF a list of plain strings is
    returned UNCHANGED, byte for byte — today's behavior exactly. --selftest checks that identity.
    """
    out = []
    for f in (verdict or {}).get("findings") or []:
        t = _finding_text(f)
        if not t:
            continue
        out.append(scrub(t) if scrub_markers else t)
    return out


# ── 2. the oracle: the ticket's embedded ORIGINAL SOURCE block ───────────────────────────────────
def parse_original(body):
    """The original module's bytes, lifted out of a ticket body. Returns (source, None) or (None, why).

    Mirrors forge_refactor_ticketer.py's embed_source()/_marks() (:840-891), which is what PUT the
    block there, and handles all four of the cases that tool can emit:

      VERBATIM   the bytes as text, between the marker lines. The normal case.
      BASE64     the block is base64 when the module is not UTF-8 text or holds a NUL; the begin
                 marker's description says so, and it is decoded here.
      NONCE'D    when the module's own text contains a marker line, BOTH markers take a `:<sha>`
                 suffix. The end marker is therefore matched to the BEGIN marker's nonce — never to
                 the first `===END SOURCE` seen. Getting this wrong would silently read a PREFIX of
                 the module as the whole of it, and a prefix oracle mints confidently wrong tests.
      TRUNCATED  REFUSED. An over-cap module is embedded as its first 256 KiB under a TRUNCATED
                 banner; that excerpt is a different program and cannot define `expected`. The
                 capture is rejected with a reason rather than minted against a prefix.
    """
    if not body:
        return None, "the ticket body is empty — no embedded original to derive `expected` from"
    lines = body.splitlines()
    begin_i, nonce, desc = None, None, ""
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith(EMBED_BEGIN_SENTINEL) and s.endswith("==="):
            head = s[len(EMBED_BEGIN_SENTINEL):]
            if head.startswith(":"):
                nonce = head[1:].split(" ", 1)[0].strip()
            desc = s.split("(", 1)[1].rsplit(")", 1)[0] if "(" in s and ")" in s else ""
            begin_i = i
            break
    if begin_i is None:
        return None, ("the ticket body carries no `%s ...` block — this unit's original was never "
                      "embedded, so there is no oracle and nothing may be minted" % EMBED_BEGIN_SENTINEL)
    end_marker = EMBED_END_NONCE_FMT % nonce if nonce else EMBED_END
    end_i = None
    for i in range(begin_i + 1, len(lines)):
        if lines[i].strip() == end_marker:
            end_i = i
            break
    if end_i is None:
        return None, "the embedded original block opens at %r but never closes with %r" % (
            lines[begin_i].strip()[:60], end_marker)
    if DESC_CUT_MARK in desc:
        return None, ("the embedded original is a TRUNCATED EXCERPT (%r), not the module — an excerpt "
                      "cannot define `expected`, so nothing is minted" % desc)
    payload = "\n".join(lines[begin_i + 1:end_i])
    if DESC_B64_MARK in desc:
        try:
            raw = base64.b64decode("".join(payload.split()), validate=True)
        except Exception as e:  # noqa: BLE001
            return None, "the embedded original claims base64 (%r) but does not decode: %s" % (desc, e)
        try:
            payload = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            return None, "the embedded original decodes from base64 to non-UTF-8 bytes: %s" % e
    if not payload.strip():
        return None, "the embedded original block is empty"
    return payload, None


# ── executing a candidate module, always in a THROWAWAY dir, never in the worktree ───────────────
# The runner prints ONE sentinel line. The module under test may print anything it likes (a rewrite
# often has a __main__ banner), so the outcome is read off the LAST sentinel line — the same "last
# JSON line" discipline pair_loop's spawn_claude() uses on an agent's stdout.
#
# import is separated from the call on purpose. A module that fails to IMPORT has no outcome, and
# folding that into the call's except would turn "the original does not import" into a legitimate
# expected value of ["raises","ImportError"] — an oracle failure minted as an oracle.
_RUNNER = r'''import json
import sys
import importlib

spec = json.loads(sys.argv[1])


def emit(outcome):
    print("<<<RC>>>" + json.dumps(outcome))
    raise SystemExit(0)


try:
    mod = importlib.import_module(spec["module"])
except BaseException as e:                       # noqa: BLE001
    emit(["import_error", type(e).__name__])
try:
    fn = mod
    for part in spec["entrypoint"].split("."):
        fn = getattr(fn, part)
except AttributeError:
    emit(["no_entrypoint", spec["entrypoint"]])
if not callable(fn):
    emit(["not_callable", spec["entrypoint"]])
try:
    got = fn(*spec["args"], **spec["kwargs"])
except BaseException as e:                       # noqa: BLE001
    emit(["raises", type(e).__name__])
try:
    emit(["return", json.loads(json.dumps(got))])
except (TypeError, ValueError):
    emit(["unserializable", type(got).__name__])
'''


def _clean_env():
    """The child's environment, with PYTHONPATH removed: sys.path must be the throwaway dir and the
    stdlib, nothing else. A stray PYTHONPATH is how the REAL package under repair would shadow the
    candidate module and let the worker's code answer for the original's."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONSTARTUP")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


@contextlib.contextmanager
def _candidate_dir(module_src, module):
    """A throwaway directory holding ONE candidate module, laid out like the package root."""
    d = tempfile.mkdtemp(prefix="rc-run-")
    try:
        with open(os.path.join(d, module + ".py"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(module_src)
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run_entrypoint(module_src, module, entrypoint, args, kwargs, timeout=RUN_TIMEOUT):
    """Execute `entrypoint(*args, **kwargs)` against `module_src`, in a throwaway dir. -> outcome.

    An OUTCOME is a 2-list, and it is the ONLY currency this module compares — the minted test builds
    the identical shape, so red/green here and red/green in CI mean the same thing:
        ["return", <JSON-normalized value>]   the call returned
        ["raises", "<ExceptionTypeName>"]     the call raised
        ["unserializable", "<TypeName>"]      it returned something JSON cannot carry
        ["import_error", "<TypeName>"] / ["no_entrypoint", ...] / ["not_callable", ...]
        ["timeout", "<seconds>"] / ["runner_error", "<detail>"]
    Only the first two may ever become `expected`; the rest are oracle failures (capture() rejects).

    The value is JSON-normalized (round-tripped) because the minted test's literal has been through
    JSON too — without it a function returning (1, 2) would be compared against the literal [1, 2]
    and the test would be red against the ORIGINAL, rejecting a perfectly good capture.

    Nothing is executed inside the repo or the worktree: the candidate is COPIED into a temp dir and
    run there, so a module with import-time side effects cannot write into the tree under repair.
    """
    with _candidate_dir(module_src, module) as d:
        runner = os.path.join(d, "_rc_runner.py")
        with open(runner, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_RUNNER)
        spec = json.dumps({"module": module, "entrypoint": entrypoint, "args": args, "kwargs": kwargs})
        try:
            r = subprocess.run([sys.executable, "-B", runner, spec], cwd=d, capture_output=True,
                               text=True, timeout=timeout, env=_clean_env())
        except subprocess.TimeoutExpired:
            return ["timeout", str(timeout)]
        for line in reversed((r.stdout or "").splitlines()):
            if line.startswith(SENTINEL):
                try:
                    return json.loads(line[len(SENTINEL):])
                except ValueError:
                    continue
        return ["runner_error", ((r.stderr or "") + (r.stdout or "")).strip()[-160:] or "no outcome line"]


def _call_args(rep):
    """The repro's `input`, as (args, kwargs). Three spellings, so an adversary need not guess:
        {"args": [10, 0, 5], "kwargs": {"strict": true}}   the explicit form
        [10, 0, 5]                                          a bare list is positional args
        10                                                  a bare scalar is one positional arg
    A dict that names neither `args` nor `kwargs` is one positional dict argument, not kwargs: a
    function taking a dict is far commoner than an adversary meaning kwargs and spelling it wrong.
    """
    inp = rep.get("input")
    if isinstance(inp, dict) and ("args" in inp or "kwargs" in inp):
        return list(inp.get("args") or []), dict(inp.get("kwargs") or {})
    if isinstance(inp, list):
        return list(inp), {}
    if inp is None and "input" not in rep:
        return [], {}
    return [inp], {}


# ── 3. test emission ─────────────────────────────────────────────────────────────────────────────
# The guard's own bytes. Two properties are load-bearing and both are proven by --selftest:
#   * It runs under plain `python3 <file>` AND under pytest. pytest is not installable in a pair
#     worktree (`pip install` needs an approval that never comes), so a guard only pytest can run is
#     a guard the harness cannot validate — and an unvalidated guard is exactly what #440 forbids.
#   * It finds its module by walking up from its own location (<pkg>/tests/regression/ -> <pkg>),
#     which is how validation can run it against a candidate blob by laying a temp dir out the same
#     way. No env var, no conftest, nothing for a worker to lean on.
_TEST_TEMPLATE = '''# GENERATED — HARNESS-OWNED REGRESSION GUARD. DO NOT EDIT, WEAKEN OR DELETE (#440).
#
# Minted by tools/regression_capture.py from ticket #%(tid)d's CONFIRMED round-%(rnd)d finding.
#
# EXPECTED WAS NOT TAKEN FROM ANYONE'S OPINION. It was DERIVED by executing this entrypoint against
# the ticket's embedded ===ORIGINAL SOURCE=== block: the original module is the oracle, because a
# forge rewrite is behavior-preserving against it. It is not the worker's output and not the
# finding's text.
#
# Before this file was written it was PROVEN red against the exact worker blob that produced the
# finding, green against the original, and red again with the defect re-introduced. It is an
# ADDITIVE FLOOR: passing it is necessary, never sufficient — the adversarial auditor still executes
# the ticket's required behavior in full, every round.
#
# The harness records this file's sha256 outside the worktree and restores the file if it is
# modified or deleted. Fix the module; the guard is not yours to move.
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(os.path.dirname(_HERE))          # <pkg>/tests/regression/ -> <pkg>
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

import %(module)s as _mod

FINDING = %(prose)r
ENTRYPOINT = %(entrypoint)r
ARGS = %(args)r
KWARGS = %(kwargs)r
EXPECTED = %(expected)r          # what the ORIGINAL module does with this input


def %(func)s():
    """The behavior the original module has at this input, which the rewrite must preserve."""
    try:
        _got = _mod.%(entrypoint)s(*ARGS, **KWARGS)
    except BaseException as _e:                          # noqa: BLE001
        _outcome = ["raises", type(_e).__name__]
    else:
        try:
            _outcome = ["return", json.loads(json.dumps(_got))]
        except (TypeError, ValueError):
            _outcome = ["unserializable", type(_got).__name__]
    assert _outcome == EXPECTED, (
        "regression #%(tid)d: " + ENTRYPOINT + " with args=" + repr(ARGS) + " kwargs=" + repr(KWARGS)
        + " gives " + repr(_outcome) + "; the ORIGINAL module gives " + repr(EXPECTED)
        + ". The finding this guards: " + repr(FINDING))


if __name__ == "__main__":
    %(func)s()
    print("ok %(func)s")
'''


def _slug(text):
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in str(text))[:40].strip("_") or "x"


def _digest(*bits):
    return hashlib.sha256("\x00".join(json.dumps(b, sort_keys=True) for b in bits).encode()).hexdigest()


def mint_test_source(tid, rnd, module, entrypoint, args, kwargs, expected, prose):
    """The guard's source, and the function name inside it. Deterministic in every input.

    Deterministic on purpose: the filename carries a digest of (entrypoint, input, expected), so
    re-capturing the same repro rewrites the same path with the same bytes — minting is additive and
    idempotent, and two different expectations can never collide onto one file.

    Every value is emitted through repr() of a JSON-decoded object (dict/list/str/int/float/bool/
    None), whose repr is always a valid Python literal. That is also why the adversary's prose goes
    in as `FINDING = <repr>` rather than into a docstring: prose is arbitrary text and a docstring
    would let a stray triple-quote or backslash write code into the guard.
    """
    func = "test_t%d_%s" % (tid, _slug(entrypoint))
    return _TEST_TEMPLATE % {
        "tid": tid, "rnd": rnd, "module": module, "entrypoint": entrypoint, "func": func,
        "args": args, "kwargs": kwargs, "expected": expected, "prose": prose or "(no prose given)",
    }, func


def _mutate(original_src, entrypoint):
    """The original with the captured defect re-introduced: the entrypoint shadowed by a stub.

    Universal by construction. For a plain function the stub replaces it outright. For a dotted
    entrypoint (`Cls.method`) the stub shadows the top-level NAME, so `Cls.method` no longer resolves
    and the call raises — a different outcome either way. A guard that survives this cannot be shown
    to assert anything about what the entrypoint computes, and is rejected.

    Honest scope: mint_test_source() cannot emit a vacuous assertion, so the one input that actually
    survives this probe is an original whose entrypoint returns MUTANT_SENTINEL itself. The gate is
    therefore a fail-closed backstop rather than a common rejection path — but it is wired in, and
    --selftest proves it by feeding it exactly that collision (see 4d). Rejecting on a sentinel
    collision loses nothing: the safe direction is to mint no guard.
    """
    top = entrypoint.split(".")[0]
    return original_src + ("\n\n# --- regression_capture mutation probe (#440): the defect, re-introduced ---\n"
                           "def %s(*_a, **_k):\n    return %r\n" % (top, MUTANT_SENTINEL))


def run_test(test_src, module_src, module, timeout=RUN_TIMEOUT):
    """Run a minted guard against one candidate blob. -> (passed, detail).

    The temp dir is laid out EXACTLY like production — the module at the package root, the guard at
    <root>/tests/regression/ — so the file being validated is the file that will be committed, byte
    for byte, exercising the same import walk. Validating a rewritten or relocated copy would prove
    something about a file nobody ever runs.
    """
    d = tempfile.mkdtemp(prefix="rc-validate-")
    try:
        with open(os.path.join(d, module + ".py"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(module_src)
        td = os.path.join(d, "tests", "regression")
        os.makedirs(td)
        tp = os.path.join(td, "test_guard.py")
        with open(tp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(test_src)
        try:
            r = subprocess.run([sys.executable, "-B", tp], cwd=d, capture_output=True, text=True,
                               timeout=timeout, env=_clean_env())
        except subprocess.TimeoutExpired:
            return False, "the guard did not finish in %ss" % timeout
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()[-300:]
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 5. the ledger: the authority on what was minted, kept OUTSIDE the worktree ───────────────────
def ledger_dir(worktree):
    """The harness's own state directory for this repo — `<git common dir>/regression-capture`.

    Resolved by READING git's own layout, not by shelling out to git: a linked worktree's `.git` is a
    FILE holding `gitdir: <path>`, and that directory holds a `commondir` file pointing at the repo's
    real `.git`. (Confirmed against this checkout: `.git` -> `.../congruency/.git/worktrees/
    ticket-440`, whose commondir is `../..` -> `.../congruency/.git`.) A plain checkout's `.git` is a
    directory and is already the answer.

    It has to be outside the worktree. The worker's tools (Write, Edit) reach every path under the
    worktree, so a manifest kept beside the guard is exactly as forgeable as the guard. This is the
    same place pair_loop keeps its own cross-process lock (Forge.lockfile -> `<root>/.git/
    pair-loop.lock`), so it is the established home for harness state, and `git worktree remove
    --force` at reap time cannot take it.

    Returns None if the layout is not recognizable; capture() then REJECTS rather than falling back
    to somewhere the worker can reach.
    """
    dot = os.path.join(worktree, ".git")
    if os.path.isdir(dot):
        return os.path.join(dot, LEDGER_DIRNAME)
    if os.path.isfile(dot):
        try:
            head = open(dot).read().strip()
        except OSError:
            return None
        if not head.startswith("gitdir:"):
            return None
        gd = head.split(":", 1)[1].strip()
        gd = gd if os.path.isabs(gd) else os.path.abspath(os.path.join(worktree, gd))
        common = os.path.join(gd, "commondir")
        if os.path.isfile(common):
            rel = open(common).read().strip()
            gd = rel if os.path.isabs(rel) else os.path.abspath(os.path.join(gd, rel))
        return os.path.join(gd, LEDGER_DIRNAME)
    return None


class Ledger:
    """Every guard minted for one ticket: its path, its bytes and their sha256. Append-only.

    Append-only in the same sense the journal is: an entry is added and never rewritten. Re-minting
    an identical guard is a no-op; a DIFFERENT source for a path already recorded is refused, which
    cannot happen through mint_test_source() (the filename carries a digest of what determines the
    bytes) and would mean something is wrong if it did.
    """

    def __init__(self, dirpath, tid):
        self.dir, self.tid = dirpath, int(tid)
        self.path = os.path.join(dirpath, "t%d.json" % self.tid) if dirpath else None

    def entries(self):
        """What has been minted. Reads only — a ledger that was never written creates no file."""
        if not self.path or not os.path.isfile(self.path):
            return []
        try:
            return json.load(open(self.path)).get("tests") or []
        except (ValueError, OSError):
            return []

    def add(self, entry):
        os.makedirs(self.dir, exist_ok=True)
        tests = self.entries()
        for e in tests:
            if e["path"] == entry["path"]:
                if e["sha256"] != entry["sha256"]:
                    raise Unexpected("ledger refuses to rewrite %s: it is already recorded with a "
                                     "different sha256 (append-only)" % entry["path"])
                return False
        tests.append(entry)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"ticket": self.tid, "tests": tests}, fh, indent=1)
        os.replace(tmp, self.path)
        return True


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def _restore(worktree, tid, led):
    """Put back every minted guard the worker touched. -> {checked, intact, tampered, restored}."""
    out = {"checked": 0, "intact": [], "tampered": [], "restored": []}
    for e in led.entries():
        out["checked"] += 1
        p = os.path.join(worktree, e["path"])
        cur = _read_text(p)
        if cur is not None and _sha(cur) == e["sha256"]:
            out["intact"].append(e["path"])
            continue
        how = "DELETED" if cur is None else "MODIFIED"
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(e["source"])
        out["tampered"].append({"path": e["path"], "how": how})
        out["restored"].append(e["path"])
    return out


def guard(worktree, tid, mode=DEFAULT_MODE, registry=None, ledger=None):
    """Restore any minted guard the worker modified or deleted. Idempotent, cheap, and a NO-OP when
    capture is off or nothing has been minted.

    THIS IS WHY IT EXISTS, and it is the one thing pair_loop's scoping does not do for us. Call it
    immediately BEFORE each round's commit_deliverable(). The reason is the round ordering: a guard
    minted at the end of round N is visible to round N+1's worker, whose commit happens BEFORE
    round N+1's verdict. So a worker that deletes the guard and then PASSES would have the deletion
    committed and merged, and the fail-verdict hook would never run to notice. A pre-commit guard()
    closes that window; the fail-verdict hook alone cannot.

    Restoring is not erasing. Only the harness's own artifact is rewritten, from the harness's own
    ledger; the worker's module is never touched.
    """
    if not capture_enabled(mode, registry):
        return {"enabled": False, "checked": 0, "intact": [], "tampered": [], "restored": []}
    led = ledger or Ledger(ledger_dir(worktree), tid)
    out = _restore(worktree, tid, led)
    out["enabled"] = True
    return out


def guard_note(g):
    """The journal line for a guard() pass, or "" when there is nothing to say."""
    if not g.get("enabled") or not g.get("tampered"):
        return ""
    return ("regression guard: the worker %s — RESTORED from the harness ledger (the guard is "
            "harness-owned and worker-immutable; the module is the worker's to fix, the guard is "
            "not): %s" % ("; ".join("%s %s" % (t["how"].lower(), t["path"]) for t in g["tampered"]),
                          ", ".join(g["restored"])))


# ── 4 + the hook: capture one fail verdict ───────────────────────────────────────────────────────
def _reject(rep, why, check=None):
    r = {"reason": why, "entrypoint": rep.get("entrypoint"), "input": rep.get("input")}
    if check:
        r["check"] = check
    return r


def _mint_one(worktree, tid, rnd, deliverable, package, original_src, rep, led, timeout):
    """One repro -> (minted_entry, None) or (None, rejection). Writes NOTHING on a rejection."""
    ep = rep.get("entrypoint")
    if not isinstance(ep, str) or not ep or not all(p.isidentifier() for p in ep.split(".")):
        return None, _reject(rep, "the repro names no usable `entrypoint` (want a dotted attribute "
                                  "path inside the deliverable's module, e.g. \"clamp\" or "
                                  "\"Cls.method\"); got %r" % (ep,))
    module = os.path.basename(deliverable)
    if not module.endswith(".py"):
        return None, _reject(rep, "the deliverable %s is not a python module — nothing to import "
                                  "an entrypoint from" % deliverable)
    module = module[:-3]
    if not module.isidentifier():
        return None, _reject(rep, "the deliverable's module name %r is not importable" % module)
    args, kwargs = _call_args(rep)
    try:
        args, kwargs = json.loads(json.dumps(args)), json.loads(json.dumps(kwargs))
    except (TypeError, ValueError) as e:
        return None, _reject(rep, "the repro's `input` is not JSON data (%s) — it cannot be written "
                                  "into a durable test as a literal" % e)
    if not all(isinstance(k, str) and k.isidentifier() for k in kwargs):
        return None, _reject(rep, "the repro's `input.kwargs` has keys that are not python "
                                  "identifiers: %r" % (sorted(kwargs),))

    worker_src = _read_text(os.path.join(worktree, deliverable))
    if worker_src is None:
        return None, _reject(rep, "no worker blob readable at %s in the worktree — nothing to prove "
                                  "the guard red against" % deliverable)

    # 2. ORACLE = ORIGINAL. Never the worker's output; never the finding's `observed`.
    expected = run_entrypoint(original_src, module, ep, args, kwargs, timeout)
    if expected[0] not in ("return", "raises"):
        return None, _reject(rep, "the ORACLE could not be evaluated against the ticket's embedded "
                                  "original: %r. The repro's entrypoint/input is malformed, and only "
                                  "the original may define `expected` — nothing minted." % (expected,),
                             check="green-on-original")
    actual = run_entrypoint(worker_src, module, ep, args, kwargs, timeout)

    prose = rep.get("finding") or ""
    src, func = mint_test_source(tid, rnd, module, ep, args, kwargs, expected, prose)
    rel = "%s/test_t%d_%s_%s.py" % (tests_dir_for(deliverable, package), tid, _slug(ep),
                                    _digest(ep, args, kwargs, expected)[:8])

    # 4. THE VALIDATION INVARIANT — all three, or nothing is written.
    red, red_out = run_test(src, worker_src, module, timeout)
    if red:
        return None, _reject(rep, "BOGUS CAPTURE: the minted guard PASSES against the exact worker "
                                  "blob that produced the finding, so this repro does not reproduce "
                                  "the failure (the worker agrees with the original at this input: "
                                  "%r). Nothing minted." % (expected,), check="red-on-buggy")
    green, green_out = run_test(src, original_src, module, timeout)
    if not green:
        return None, _reject(rep, "the minted guard FAILS against the ticket's embedded original — "
                                  "the oracle or the input is malformed, so the guard would outlaw "
                                  "the original's own behavior. Nothing minted. Detail: %s" % green_out,
                             check="green-on-original")
    mut, _ = run_test(src, _mutate(original_src, ep), module, timeout)
    if mut:
        return None, _reject(rep, "the minted guard SURVIVES re-introducing the defect — it asserts "
                                  "nothing load-bearing about %s. Nothing minted." % ep,
                             check="mutation-resistant")

    p = os.path.join(worktree, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(src)
    entry = {"path": rel, "sha256": _sha(src), "source": src, "entrypoint": ep, "round": rnd,
             "expected": expected, "actual": actual, "observed_claimed": rep.get("observed"),
             "minted": time.strftime("%Y-%m-%dT%H:%M:%S"), "func": func}
    led.add(entry)
    return entry, None


def capture(worktree, tid, deliverable, package, ticket_body, verdict, rnd=1, mode=DEFAULT_MODE,
            registry=None, ledger=None, timeout=RUN_TIMEOUT):
    """THE HOOK. Call once, after a FAIL verdict. -> a report; never a verdict.

    Returns {"enabled", "mode", "minted", "rejected", "stage", "guard", "note"} and deliberately no
    "verdict"/"pass" key: this is an additive floor with no authority over the round (--selftest
    asserts the key's absence). The round outcome is the adversary's alone.

    `stage` is the repo-relative paths pair_loop should `git add` before its next commit. They are
    staged rather than left to commit_deliverable() because a lone-file deliverable's commit scope is
    one path and would leave the guard an uncommitted stray; a forge package's scope already contains
    them, and `git add` on an already-in-scope path is a no-op. The index survives to the next round's
    commit, which is where a guard minted at the end of round N lands.

    OFF is a byte-for-byte no-op: it returns before reading the body, the ledger or the worktree, and
    creates nothing. Not "creates nothing important" — nothing; --selftest proves it with a
    before/after tree snapshot of both the worktree and the ledger directory.
    """
    out = {"enabled": False, "mode": mode, "minted": [], "rejected": [], "stage": [],
           "guard": {"enabled": False, "checked": 0, "intact": [], "tampered": [], "restored": []},
           "note": ""}
    if not capture_enabled(mode, registry):
        return out
    out["enabled"] = True
    if (verdict or {}).get("verdict") != "fail":
        out["note"] = ""
        return out

    led = ledger or Ledger(ledger_dir(worktree), tid)
    if not led.path:
        out["note"] = ("regression capture ON but SKIPPED: %s has no recognizable git layout, so the "
                       "harness ledger cannot be kept outside the worktree. Refusing to keep it "
                       "somewhere the worker can rewrite." % worktree)
        return out
    out["guard"] = guard(worktree, tid, mode="on", ledger=led)

    reps = repros(verdict)
    if not reps:
        out["note"] = _note(out, "the finding carries no structured repro — nothing minted (a prose "
                                 "finding is still a valid finding)")
        return out
    original_src, why = parse_original(ticket_body)
    if original_src is None:
        out["rejected"] = [_reject(r, "no oracle: %s" % why, check="oracle") for r in reps]
        out["note"] = _note(out)
        return out
    for rep in reps:
        try:
            entry, rej = _mint_one(worktree, tid, rnd, deliverable, package, original_src, rep, led,
                                   timeout)
        except Unexpected as e:
            entry, rej = None, _reject(rep, str(e))
        if entry:
            out["minted"].append(entry)
            out["stage"].append(entry["path"])
        else:
            out["rejected"].append(rej)
    out["note"] = _note(out)
    return out


def _note(out, extra=""):
    """The journal line for one capture. Every rejection is journaled WITH its reason — a capture
    that mints nothing must say why, or the record cannot tell "no repro was filed" from "the repro
    was bogus and we refused it"."""
    bits = []
    g = guard_note(out.get("guard") or {})
    if g:
        bits.append(g)
    for m in out["minted"]:
        bits.append("regression guard MINTED %s (%s): validated red against the round's worker blob, "
                    "green against the ticket's embedded original, and red again under mutation. "
                    "`expected` was derived from the ORIGINAL, not from the worker or the finding. "
                    "It is an additive floor, not the round gate."
                    % (m["path"], m["entrypoint"]))
        if m.get("observed_claimed") is not None and m["observed_claimed"] != (m["actual"][1] if
                                                                               m["actual"][0] == "return" else None):
            bits.append("...the finding CLAIMED observed=%r; the worker blob actually gives %r. The "
                        "claim was recorded and not used — `expected` came from the original either "
                        "way." % (m["observed_claimed"], m["actual"]))
    for r in out["rejected"]:
        bits.append("regression capture REJECTED a repro for %s%s: %s"
                    % (r.get("entrypoint"), " [%s]" % r["check"] if r.get("check") else "", r["reason"]))
    if extra:
        bits.append("regression capture: " + extra)
    return " | ".join(bits)


# ── the pair_loop hook, stated exactly (this module does not edit pair_loop.py) ──────────────────
HOOK_PATCH = '''\
THE pair_loop.py HOOK — four inserted lines and one changed line, in three places. #440 asks for a
MINIMAL pair_loop change on purpose: the #279 regression came from a large pair_loop rewrite, so this
module carries all of the logic and pair_loop only calls it.

THIS PATCH IS NOT APPLIED BY THIS MODULE, and could not be: ticket #440's worker mandate is "write it
to checkouts/current/congruency/tools/regression_capture.py (create or overwrite that file; touch
nothing else)", and pair_loop's own commit scope for this deliverable is that single path — an edit
to pair_loop.py would be journaled a stray and reaped unmerged (commit_deliverable(), commit_note()).
So the patch is stated here, is proven by --selftest against pair_loop's real code, and lands under
its own ticket. `--verify-scope` reports whether it is installed in the live pair_loop yet.

1) beside the other imports (pair_loop and this module are both in tools/, so sys.path[0] finds it):

     import urllib.request
   + import regression_capture

2) in main()'s parser, beside --package-commit:

   + ap.add_argument("--regression-capture", choices=("on", "off", "auto"), default="off",
   +                 metavar="ON|OFF|AUTO",
   +                 help="capture a CONFIRMED auditor finding's structured repro as a red, "
   +                      "worker-immutable regression test under tests/regression/ (#440). off "
   +                      "(default): unchanged behavior. on: always. auto: registry.json's "
   +                      "{\\"regression_capture\\": {\\"enabled\\": bool}} decides.")

3) in the round loop, IMMEDIATELY BEFORE the `cm = step("commit: ...` call — this is the guard, and
   it is a separate call site for a reason stated in guard()'s docstring: a guard minted at the end
   of round N is exposed to round N+1's worker, whose COMMIT happens before round N+1's verdict, so
   a fail-verdict hook alone can never catch a worker that tampers and then passes:

   + regression_capture.guard(wt["path"], tid, a.regression_capture)

4) after the fail verdict — the single hook. It replaces the existing `findings = ...` line:

   - findings = vres.get("findings", ["(none given)"])
   + rc = regression_capture.capture(wt["path"], tid, a.deliverable, pkg, body, vres, rnd,
   +                                 a.regression_capture)
   + if rc["stage"]:
   +     forge.git("add", "--", *rc["stage"], cwd=wt["path"])
   + if rc["note"]:
   +     rest("ticket.progress", {"ticket_id": tid, "agent_id": fid, "note": rc["note"]})
   + findings = regression_capture.worker_findings(vres, rc["enabled"]) or ["(none given)"]

   worker_findings() replaces the raw `.get("findings")` for two reasons, and with capture OFF it
   returns a list of plain strings UNCHANGED, byte for byte (--selftest checks that identity):
     * the per-finding repro spelling puts a dict in `findings`, which pair_loop's
       `"; ".join(vres.get("findings", []))` would raise on;
     * it is the single place the worker-facing text is scrubbed, and because harvest() composes
       lessons from these same findings and --compile-playbook compiles the playbook from those
       lessons, scrubbing here keeps the mechanism out of docs/PLAYBOOK.md too.

NOTHING ELSE CHANGES. No verdict is touched, no ordering is touched — in particular ticket.assign
still runs before process_status ACTIVE in pair(), which is the #279 regression and must stay.
'''


# ── --verify-scope: re-prove the worker-immutability claims against the LIVE pair_loop ───────────
def _no_bytecode():
    """Stop CPython writing `tools/__pycache__/*.pyc` when this module's CLI imports its siblings.

    Importing pair_loop (and forge_refactor_ticketer) to test against the REAL code is the whole
    point of --selftest and --verify-scope — but an import writes a .pyc NEXT TO the module by
    default, so both commands created files in this repo while claiming they touched nothing. That
    is #153's lesson exactly: an operation that looks read-only is not, and the claim was checked
    against behavior and lost. --selftest now snapshots tools/ before and after and proves the
    directory is unchanged.

    Set ONLY on the CLI paths, never at import time: this module is a LIBRARY that pair_loop imports
    through the hook, and flipping a global interpreter flag as a side effect of being imported would
    change pair_loop's behavior with capture OFF — which must be byte-for-byte unchanged.
    """
    sys.dont_write_bytecode = True


def _import_pair_loop():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pair_loop
    return pair_loop


def scope_report(pl, tmp):
    """EXECUTE pair_loop's real commit scoping against a throwaway repo and report what it does with
    a worker's edit under tests/regression/. Returns a list of (claim, ok, detail).

    This is #440's "Verify pair_loop's deliverable/worker scoping enforces this", done by running the
    code rather than reading it — and the honest answer is two different answers (see the module
    docstring's WORKER-IMMUTABILITY): excluded for a single-file deliverable, NOT excluded for a
    package deliverable, which is the only kind that matters here. Hence guard().
    """
    res = []
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo)
    for a in (("init", "--quiet", "-b", "main", "."), ("config", "user.email", "rc@selftest"),
              ("config", "user.name", "rc selftest")):
        subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)
    open(os.path.join(repo, "registry.json"), "w").write('{"schema": 1}\n')
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "init"], cwd=repo, capture_output=True)
    f = pl.Forge(repo)
    base = f.current_branch()

    # (a) a lone-file deliverable: the guard is OUTSIDE the commit scope.
    w = f.open_worktree(4401, base)
    os.makedirs(os.path.join(w["path"], "tools", TESTS_DIR))
    open(os.path.join(w["path"], "tools", "unit.py"), "w").write("x = 1\n")
    open(os.path.join(w["path"], "tools", TESTS_DIR, "test_g.py"), "w").write("# guard\n")
    c = f.commit_deliverable(4401, "tools/unit.py", "m")
    guarded = "tools/%s/test_g.py" % TESTS_DIR
    # The stray is reported as `tools/tests/` — git's default porcelain listing COLLAPSES a wholly
    # untracked directory to one entry (which is why commit_deliverable passes -uall when it needs
    # the files). So the claim is checked as "not committed, and covered by a stray entry", not as
    # an equality against a spelling git only sometimes uses.
    covered = any(guarded == s or guarded.startswith(s.rstrip("/") + "/") for s in c["strays"])
    res.append(("single-file deliverable: a worker edit under %s/ is NOT committed (it is a stray, "
                "reported as its collapsed parent dir)" % TESTS_DIR,
                guarded not in c["files"] and covered,
                "files=%s strays=%s" % (c["files"], c["strays"])))
    f.reap_worktree(4401)

    # (b) a forge PACKAGE deliverable: the guard is INSIDE the commit scope (#409, policy 8).
    pkg = "checkouts/current/forge2/rc_unit"
    w = f.open_worktree(4402, base)
    os.makedirs(os.path.join(w["path"], pkg, TESTS_DIR))
    open(os.path.join(w["path"], pkg, "unit.py"), "w").write("x = 1\n")
    open(os.path.join(w["path"], pkg, TESTS_DIR, "test_g.py"), "w").write("# guard\n")
    c = f.commit_deliverable(4402, pkg + "/unit.py", "m")
    gp = "%s/%s/test_g.py" % (pkg, TESTS_DIR)
    swept = gp in c["files"]
    res.append(("package deliverable: %s/ IS inside the #409 package commit scope — pair_loop's "
                "scoping does NOT make it worker-immutable, so guard() must" % TESTS_DIR,
                swept, "files=%s" % (c["files"],)))

    # (c) ...and guard() closes it: the worker's weakened guard is restored before the commit.
    led = Ledger(os.path.join(tmp, "ledger"), 4402)
    led.add({"path": gp, "sha256": _sha("# guard\n"), "source": "# guard\n"})
    open(os.path.join(w["path"], gp), "w").write("# weakened by the worker\n")
    g = guard(w["path"], 4402, mode="on", ledger=led)
    back = _read_text(os.path.join(w["path"], gp))
    res.append(("guard() restores a guard the worker weakened, before the commit sees it",
                back == "# guard\n" and g["restored"] == [gp], "restored=%s content=%r" % (g["restored"], back)))
    f.reap_worktree(4402)

    # (d) is the hook actually installed in the live pair_loop?
    src = _read_text(os.path.abspath(pl.__file__)) or ""
    res.append(("the pair_loop hook is installed (`import regression_capture`) — INFORMATIONAL: "
                "until it lands under its own ticket, capture is inert and pair_loop is unchanged",
                "regression_capture" in src, "not found in %s" % pl.__file__))
    return res


def verify_scope():
    _no_bytecode()
    pl = _import_pair_loop()
    tmp = tempfile.mkdtemp(prefix="rc-scope-")
    try:
        print("== verify-scope == pair_loop %s, throwaway repo under %s" % (pl.__file__, tmp))
        for claim, ok, detail in scope_report(pl, tmp):
            print("   %-4s %s" % ("YES" if ok else "NO", claim))
            if not ok:
                print("        %s" % detail)
        print("\nSee WORKER-IMMUTABILITY in this module's docstring: the package case is why guard() "
              "exists.\nRun --print-hook for the two call sites.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── --selftest: prove the method on a THROWAWAY synthetic unit (no network, no db, no repo writes) ─
# The synthetic unit: a tiny original with a KNOWN bug in a worker rewrite of it, and a repro that
# hits the bug. Small on purpose — the point is to prove the harness, not to be a realistic module.
_ST_ORIGINAL = '''"""clamp — the synthetic unit's ORIGINAL (the oracle)."""


def clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def kind(v):
    if not isinstance(v, int):
        raise TypeError("want an int")
    return "neg" if v < 0 else "pos"
'''

# The worker's rewrite, with an off-by-one at the upper bound: clamp(10, 0, 5) -> 4, not 5.
_ST_BUGGY = _ST_ORIGINAL.replace("    if v > hi:\n        return hi\n",
                                 "    if v > hi:\n        return hi - 1\n")

# A rewrite that is behavior-preserving at the captured input (restructured, but correct).
_ST_FIXED = '''"""clamp — a correct, restructured rewrite."""


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def kind(v):
    if not isinstance(v, int):
        raise TypeError("want an int")
    return "neg" if v < 0 else "pos"
'''


def _st_body(source=None, desc=None, begin=None, end=None):
    """A ticket body carrying an embedded original, assembled EXACTLY as the owner assembles it.

    The assembly is forge_refactor_ticketer.py's source_block():936 — `"%s\\n%s\\n%s" % (begin,
    payload, end)` — and the newline between the payload and the end marker is load-bearing: it is
    what puts the marker on its own line, and it is why "\\n".join() over the lines BETWEEN the
    markers reconstructs the payload byte for byte, trailing newline included. Hand-rolling this
    fixture with a plausible-looking assembly instead of the real one is how a parser gets "proven"
    against a format nothing writes.
    """
    payload = _ST_ORIGINAL if source is None else source
    b = begin or (EMBED_BEGIN_FMT % (desc or "verbatim, the behavior-preserving basis"))
    return "Rewrite the unit.\n\n%s\n%s\n%s\n\nEnds.\n" % (b, payload, end or EMBED_END)


def _tree(root):
    """Every file under `root`, path -> sha256. The before/after isolation snapshot (Theme 3)."""
    out = {}
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if x != ".git"]
        for fn in fs:
            p = os.path.join(d, fn)
            try:
                out[os.path.relpath(p, root)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
            except OSError:
                out[os.path.relpath(p, root)] = "?"
    return out


def selftest():  # noqa: C901 — one linear proof; splitting it would hide the order things are proven in
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print("   %-4s %s%s" % ("PASS" if cond else "FAIL", name,
                                ("  — %s" % detail) if detail and not cond else ""))

    _no_bytecode()          # BEFORE the sibling imports below, or they write tools/__pycache__/
    tmp = tempfile.mkdtemp(prefix="rc-selftest-")
    # The repo must be untouched by this run, including the bug_reports sink my own except-handler
    # would write to (that handler catching something is itself a defect worth seeing), and the
    # tools/ directory this file lives in — which importing pair_loop silently writes a .pyc into
    # unless _no_bytecode() ran first. Snapshot before, diff after: a side effect I cannot see is
    # one the adversary will (#153).
    sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
    sink_before = (os.path.getsize(sink) if os.path.isfile(sink) else None)
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    tools_before = _tree(tools_dir)
    try:
        print("== selftest == throwaway workspace %s" % tmp)

        # ── the fence: still the one forge_refactor_ticketer writes (anti-drift) ──
        print("-- the embedded-original fence tracks its owner")
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import forge_refactor_ticketer as frt
            ck("the fence constants still match forge_refactor_ticketer (mirrored, not imported)",
               (frt.EMBED_BEGIN_SENTINEL, frt.EMBED_END_SENTINEL, frt.EMBED_BEGIN_FMT, frt.EMBED_END,
                frt.EMBED_BEGIN_NONCE_FMT, frt.EMBED_END_NONCE_FMT)
               == (EMBED_BEGIN_SENTINEL, EMBED_END_SENTINEL, EMBED_BEGIN_FMT, EMBED_END,
                   EMBED_BEGIN_NONCE_FMT, EMBED_END_NONCE_FMT),
               "the owner's fence moved — parse_original() must follow it")
            ck("the owner's four block descriptions still classify as this module reads them",
               DESC_B64_MARK in frt.EMBED_DESC_B64 and DESC_B64_MARK in frt.EMBED_DESC_B64_CUT
               and DESC_CUT_MARK in frt.EMBED_DESC_TEXT_CUT and DESC_CUT_MARK in frt.EMBED_DESC_B64_CUT
               and DESC_B64_MARK not in frt.EMBED_DESC_TEXT and DESC_CUT_MARK not in frt.EMBED_DESC_TEXT)
        except ImportError as e:
            ck("forge_refactor_ticketer importable for the fence check", False, str(e))

        # ── 1. schema: backward compatible, prose-only to the worker ──
        print("-- 1. the structured repro schema")
        rep = {"entrypoint": "clamp", "input": {"args": [10, 0, 5]}, "observed": 4}
        ck("a plain prose verdict carries no repro (backward compatible)",
           repros({"verdict": "fail", "findings": ["it is wrong"]}) == [])
        ck("top-level `repro` is read", len(repros({"verdict": "fail", "findings": ["x"], "repro": rep})) == 1)
        ck("plural `repros` is read", len(repros({"verdict": "fail", "repros": [rep, rep]})) == 2)
        ck("per-finding `repro` is read",
           len(repros({"verdict": "fail", "findings": [{"finding": "p", "repro": rep}, "plain"]})) == 1)
        ck("a per-finding repro inherits its finding's prose",
           repros({"verdict": "fail", "findings": [{"finding": "the prose", "repro": rep}]})[0]["finding"] == "the prose")
        ck("`expected` is NOT part of the schema (the oracle derives it)", "expected" not in rep)
        v_dict = {"verdict": "fail", "findings": [{"finding": "clamp is wrong at the bound", "repro": rep}, "and slow"]}
        ck("worker_findings() flattens a dict finding to prose (pair_loop's `\"; \".join` cannot raise)",
           worker_findings(v_dict) == ["clamp is wrong at the bound", "and slow"], str(worker_findings(v_dict)))
        ck("...and \"; \".join over it really works", "; ".join(worker_findings(v_dict)))
        plain = ["a finding", "another"]
        ck("worker_findings(scrub=False) over plain strings is byte-for-byte today's list (OFF is unchanged)",
           worker_findings({"findings": plain}, False) == plain)

        # ── 6. the toggle ──
        print("-- 6. the toggle: default OFF, registry live under `auto`")
        ck("the default mode is off", DEFAULT_MODE == "off" and capture_enabled() is False)
        ck("off beats a registry that says enabled", capture_enabled("off", {REGISTRY_KEY: {"enabled": True}}) is False)
        ck("on beats a registry that says disabled", capture_enabled("on", {REGISTRY_KEY: {"enabled": False}}) is True)
        ck("auto honors registry enabled=true", capture_enabled("auto", {REGISTRY_KEY: {"enabled": True}}) is True)
        ck("auto honors registry enabled=false", capture_enabled("auto", {REGISTRY_KEY: {"enabled": False}}) is False)
        ck("auto with no registry key is off (absent means off)", capture_enabled("auto", {}) is False)
        ck("this repo's registry.json does not enable capture (so main is unchanged)",
           capture_enabled("auto") is False, str(REGISTRY.get(REGISTRY_KEY)))
        try:
            capture_enabled("maybe")
            ck("an unknown mode is refused, not guessed", False, "no raise")
        except Unexpected:
            ck("an unknown mode is refused, not guessed", True)

        # ── 2. the oracle: parse_original over every case the owner emits ──
        print("-- 2. the oracle = the ticket's embedded ORIGINAL SOURCE")
        src, why = parse_original(_st_body())
        ck("a verbatim block is lifted whole, trailing newline included", src == _ST_ORIGINAL, str(why))

        # THE DIFFERENTIAL. The bodies above are this module's idea of the format; these are the
        # OWNER's. Each blob goes through forge_refactor_ticketer's real embed_source() and its real
        # assembly (source_block():936), and parse_original must hand back the ORIGINAL BYTES —
        # exactly, for every case that tool can emit. Anything less is a parser proven against a
        # format nothing writes.
        try:
            for label, raw in (("a plain module", _ST_ORIGINAL.encode()),
                               ("a module with no trailing newline", b"x = 1"),
                               ("a module ending in blank lines", b"x = 1\n\n\n"),
                               ("a module whose OWN text contains `===END SOURCE===` (nonce fence)",
                                (_ST_ORIGINAL + '\nBANNER = "%s"\n' % EMBED_END).encode()),
                               ("a module with a NUL byte (base64 fence)", b'X = "\x00"\n')):
                sha = hashlib.sha1(raw).hexdigest()
                e = frt.embed_source(raw, sha)
                body = "preamble\n\n%s\n%s\n%s\n\nends\n" % (e["begin"], e["payload"], e["end"])
                src, why = parse_original(body)
                ck("DIFFERENTIAL vs the owner's embed_source(): %s round-trips byte for byte" % label,
                   src is not None and src.encode() == raw, "%r -> %r" % (raw[:40], (src or why)[:60]))
            ck("...and the nonce case really did take the nonce fence (else the check above is vacuous)",
               frt.embed_source((_ST_ORIGINAL + '\nBANNER = "%s"\n' % EMBED_END).encode(), "deadbeef")["end"]
               == EMBED_END_NONCE_FMT % "deadbeef")
            ck("...and the NUL case really did take the base64 fence (else that check is vacuous)",
               frt.embed_source(b'X = "\x00"\n', "deadbeef")["binary"] is True)
        except NameError:
            ck("forge_refactor_ticketer available for the round-trip differential", False, "not imported")
        src, why = parse_original(_st_body(desc="TRUNCATED EXCERPT — NOT the whole module"))
        ck("a TRUNCATED excerpt is REFUSED as an oracle (a prefix is a different program)",
           src is None and "TRUNCATED" in why, str(why))
        src, why = parse_original("a body with no source block at all")
        ck("a body with no block is refused with a reason", src is None and "never embedded" in why, str(why))
        src, why = parse_original(EMBED_BEGIN_FMT % "verbatim, the behavior-preserving basis")
        ck("an unclosed block is refused with a reason", src is None and "never closes" in why, str(why))

        print("-- 2b. run_entrypoint(): the outcome currency")
        ck("the original's outcome is derived by EXECUTION",
           run_entrypoint(_ST_ORIGINAL, "clamp", "clamp", [10, 0, 5], {}) == ["return", 5])
        ck("the buggy blob's outcome differs", run_entrypoint(_ST_BUGGY, "clamp", "clamp", [10, 0, 5], {}) == ["return", 4])
        ck("a raising entrypoint yields a `raises` outcome",
           run_entrypoint(_ST_ORIGINAL, "clamp", "kind", ["x"], {}) == ["raises", "TypeError"])
        ck("a missing entrypoint is an oracle failure, not an outcome",
           run_entrypoint(_ST_ORIGINAL, "clamp", "nope", [], {})[0] == "no_entrypoint")
        ck("an unimportable module is an import_error, never `raises` (it must not become `expected`)",
           run_entrypoint("import nonexistent_module_xyz\n", "clamp", "clamp", [1, 0, 5], {})[0] == "import_error")
        ck("a module that prints does not confuse the outcome reader (last sentinel line wins)",
           run_entrypoint("print('<<<RC>>>[\"return\", 999]')\n\n\ndef clamp(v, lo, hi):\n    return 5\n",
                          "clamp", "clamp", [10, 0, 5], {}) == ["return", 5])
        ck("nothing is executed inside the repo: the candidate is copied to a temp dir",
           not os.path.exists(os.path.join(ROOT, "_rc_runner.py")))

        # ── the happy path: capture on the synthetic unit ──
        print("-- 3/4. mint + the validation invariant (red-on-buggy, green-on-original, mutation)")
        pkg = "checkouts/current/forge2/rc_synth"
        deliv = pkg + "/clamp.py"
        wt = os.path.join(tmp, "wt")
        os.makedirs(os.path.join(wt, pkg))
        open(os.path.join(wt, deliv), "w").write(_ST_BUGGY)
        led = Ledger(os.path.join(tmp, "ledger"), 440)
        verdict = {"verdict": "fail", "findings": ["clamp is wrong at the upper bound"], "repro": rep}

        r = capture(wt, 440, deliv, pkg, _st_body(), verdict, 1, mode="on", ledger=led)
        ck("capture ON with a repro MINTS one guard", len(r["minted"]) == 1 and not r["rejected"],
           str(r["rejected"]))
        m = r["minted"][0] if r["minted"] else {}
        rel = m.get("path", "")
        ck("the guard lands under the unit's package at %s/" % TESTS_DIR,
           rel.startswith(pkg + "/" + TESTS_DIR + "/") and os.path.isfile(os.path.join(wt, rel)), rel)
        ck("is_harness_owned() calls that path harness-owned", is_harness_owned(rel))
        ck("`expected` is the ORIGINAL's answer (5), not the worker's (4) and not `observed` (4)",
           m.get("expected") == ["return", 5], str(m.get("expected")))
        ck("the guard is returned for staging", r["stage"] == [rel], str(r["stage"]))
        ck("capture() returns NO verdict key — it is a floor, not the gate",
           "verdict" not in r and "pass" not in r, str(sorted(r)))

        guard_src = _read_text(os.path.join(wt, rel))
        ck("THE INVARIANT — the minted guard is RED against the worker blob that produced the finding",
           not run_test(guard_src, _ST_BUGGY, "clamp")[0])
        ck("THE INVARIANT — the minted guard is GREEN against the original", run_test(guard_src, _ST_ORIGINAL, "clamp")[0],
           run_test(guard_src, _ST_ORIGINAL, "clamp")[1])
        ck("THE INVARIANT — mutation: re-introducing the defect turns it RED",
           not run_test(guard_src, _mutate(_ST_ORIGINAL, "clamp"), "clamp")[0])
        ck("the guard is GREEN against a correct, RESTRUCTURED rewrite (it guards behavior, not shape)",
           run_test(guard_src, _ST_FIXED, "clamp")[0], run_test(guard_src, _ST_FIXED, "clamp")[1])
        ck("the guard runs under a plain `python3 <file>` (pytest is not installable in a worktree)",
           "if __name__ == \"__main__\":" in guard_src)
        ck("...and is a pytest test too (its function is named test_*)", m.get("func", "").startswith("test_"))
        ck("the guard's failure message names the entrypoint, the input and the original's answer",
           not run_test(guard_src, _ST_BUGGY, "clamp")[0]
           and all(s in run_test(guard_src, _ST_BUGGY, "clamp")[1] for s in ("clamp", "[10, 0, 5]", "5")),
           run_test(guard_src, _ST_BUGGY, "clamp")[1])
        ck("minting is deterministic and idempotent (same repro -> same path, same bytes)",
           mint_test_source(440, 1, "clamp", "clamp", [10, 0, 5], {}, ["return", 5], "p")[0]
           == mint_test_source(440, 1, "clamp", "clamp", [10, 0, 5], {}, ["return", 5], "p")[0])
        ck("the ledger recorded the guard's sha256 OUTSIDE the worktree",
           led.entries() and led.entries()[0]["sha256"] == _sha(guard_src)
           and not os.path.abspath(led.path).startswith(os.path.abspath(wt)), str(led.path))

        # a `raises` expectation mints and validates the same way
        rep_raise = {"entrypoint": "kind", "input": {"args": ["x"]}}
        buggy2 = _ST_BUGGY.replace('        raise TypeError("want an int")\n', '        return "unknown"\n')
        wt2 = os.path.join(tmp, "wt2")
        os.makedirs(os.path.join(wt2, pkg))
        open(os.path.join(wt2, deliv), "w").write(buggy2)
        r2 = capture(wt2, 441, deliv, pkg, _st_body(), {"verdict": "fail", "findings": ["kind swallows the error"],
                                                        "repro": rep_raise}, 1, mode="on",
                     ledger=Ledger(os.path.join(tmp, "ledger2"), 441))
        ck("a repro whose original RAISES mints a guard on the exception type",
           len(r2["minted"]) == 1 and r2["minted"][0]["expected"] == ["raises", "TypeError"],
           str(r2["minted"] or r2["rejected"]))

        # ── the oracle is independent of BOTH the worker and the finding ──
        print("-- 2c. anti-gaming: neither the worker nor the adversary defines correctness")
        wt3 = os.path.join(tmp, "wt3")
        os.makedirs(os.path.join(wt3, pkg))
        open(os.path.join(wt3, deliv), "w").write(_ST_BUGGY)
        lying = {"entrypoint": "clamp", "input": {"args": [10, 0, 5]}, "observed": 99}
        r3 = capture(wt3, 442, deliv, pkg, _st_body(), {"verdict": "fail", "findings": ["wrong"], "repro": lying},
                     1, mode="on", ledger=Ledger(os.path.join(tmp, "l3"), 442))
        ck("a finding that LIES in `observed` still gets expected=5 from the original",
           r3["minted"] and r3["minted"][0]["expected"] == ["return", 5], str(r3["minted"] or r3["rejected"]))
        ck("...and the lie is journaled as recorded-not-used, not silently swallowed",
           "CLAIMED observed=99" in r3["note"] and "not used" in r3["note"], r3["note"][:200])
        # the worker cannot move the oracle: same repro, a worker blob that returns something absurd
        wt4 = os.path.join(tmp, "wt4")
        os.makedirs(os.path.join(wt4, pkg))
        open(os.path.join(wt4, deliv), "w").write(_ST_ORIGINAL.replace("    return v\n", "    return 12345\n", 1)
                                                  .replace("        return hi\n", "        return 777\n"))
        r4 = capture(wt4, 443, deliv, pkg, _st_body(), verdict, 1, mode="on", ledger=Ledger(os.path.join(tmp, "l4"), 443))
        ck("a worker blob returning 777 does not move `expected` off the original's 5",
           r4["minted"] and r4["minted"][0]["expected"] == ["return", 5], str(r4["minted"] or r4["rejected"]))

        # ── bogus-capture rejection: nothing is minted, and nothing is written ──
        print("-- 4b. bogus captures are REJECTED and nothing is written")
        wt5 = os.path.join(tmp, "wt5")
        os.makedirs(os.path.join(wt5, pkg))
        open(os.path.join(wt5, deliv), "w").write(_ST_ORIGINAL)      # the worker AGREES with the original
        before = _tree(wt5)
        l5 = Ledger(os.path.join(tmp, "l5"), 444)
        r5 = capture(wt5, 444, deliv, pkg, _st_body(), verdict, 1, mode="on", ledger=l5)
        ck("a repro the worker blob does NOT fail is rejected as BOGUS (not minted)",
           not r5["minted"] and r5["rejected"] and r5["rejected"][0]["check"] == "red-on-buggy",
           str(r5["rejected"]))
        ck("...the rejection says why, on the journal", "BOGUS CAPTURE" in r5["note"], r5["note"][:160])
        ck("...and NOTHING was written for it (before/after tree identical)", _tree(wt5) == before,
           str(set(_tree(wt5)) ^ set(before)))
        ck("...and no ledger entry was recorded", l5.entries() == [])

        bad_ep = {"entrypoint": "not_there", "input": {"args": [1]}}
        r6 = capture(wt3, 445, deliv, pkg, _st_body(), {"verdict": "fail", "findings": ["x"], "repro": bad_ep},
                     1, mode="on", ledger=Ledger(os.path.join(tmp, "l6"), 445))
        ck("a repro naming an entrypoint the ORIGINAL lacks is rejected (malformed oracle)",
           not r6["minted"] and r6["rejected"] and "ORACLE" in r6["rejected"][0]["reason"], str(r6["rejected"]))
        r7 = capture(wt3, 446, deliv, pkg, "no source block here", verdict, 1, mode="on",
                     ledger=Ledger(os.path.join(tmp, "l7"), 446))
        ck("with no embedded original there is NO oracle, so nothing is minted",
           not r7["minted"] and r7["rejected"] and "no oracle" in r7["rejected"][0]["reason"], str(r7["rejected"]))
        r8 = capture(wt3, 447, deliv, pkg, _st_body(), {"verdict": "fail", "findings": ["prose only"]}, 1,
                     mode="on", ledger=Ledger(os.path.join(tmp, "l8"), 447))
        ck("a prose-only finding mints nothing and is NOT an error (backward compatible)",
           not r8["minted"] and not r8["rejected"] and "no structured repro" in r8["note"], r8["note"])
        r9 = capture(wt3, 448, deliv, pkg, _st_body(), {"verdict": "pass", "findings": [], "repro": rep}, 1,
                     mode="on", ledger=Ledger(os.path.join(tmp, "l9"), 448))
        ck("a PASS verdict mints nothing (only a CONFIRMED failure is captured)", not r9["minted"])

        # a guard that would be red against the original is refused, even though it is red on the worker
        print("-- 4c. a guard that outlaws the original's own behavior is REJECTED")
        bad_body = _st_body(source=_ST_ORIGINAL.replace("        return hi\n", "        return 6\n"))
        wtA = os.path.join(tmp, "wtA")
        os.makedirs(os.path.join(wtA, pkg))
        open(os.path.join(wtA, deliv), "w").write(_ST_BUGGY)
        rA = capture(wtA, 449, deliv, pkg, bad_body, verdict, 1, mode="on", ledger=Ledger(os.path.join(tmp, "lA"), 449))
        ck("a DIFFERENT embedded original moves `expected` with it (the oracle really is the block)",
           rA["minted"] and rA["minted"][0]["expected"] == ["return", 6], str(rA["minted"] or rA["rejected"]))

        # ── 4d. the two gates that only ever fire on a guard that would OTHERWISE be minted ──
        # Every case above is red-on-buggy AND green-on-original AND mutation-resistant, so deleting
        # either of those two gates would leave every one of them green. Mutation-testing this
        # selftest found exactly that blindness; these are the two cases that make the gates
        # load-bearing, and without them the invariant is asserted rather than proven.
        print("-- 4d. green-on-original and mutation-resistance are load-bearing, not decoration")
        nondet = "import random\n\n\ndef roll():\n    return random.getrandbits(64)\n"
        wtN = os.path.join(tmp, "wtN")
        os.makedirs(os.path.join(wtN, pkg))
        open(os.path.join(wtN, pkg, "roll.py"), "w").write(nondet)
        rN = capture(wtN, 451, pkg + "/roll.py", pkg, _st_body(source=nondet),
                     {"verdict": "fail", "findings": ["roll is wrong"],
                      "repro": {"entrypoint": "roll", "input": {"args": []}}},
                     1, mode="on", ledger=Ledger(os.path.join(tmp, "lN"), 451))
        ck("a NON-DETERMINISTIC entrypoint is REJECTED by green-on-original — a guard that cannot "
           "reproduce the ORIGINAL's own answer is flaky, and no flaky guard is ever minted",
           not rN["minted"] and rN["rejected"] and rN["rejected"][0].get("check") == "green-on-original",
           str(rN["minted"] or rN["rejected"]))
        ck("...and that rejection wrote nothing under %s/" % TESTS_DIR,
           not os.path.exists(os.path.join(wtN, pkg, TESTS_DIR)))

        # The mutation probe shadows the entrypoint with a stub returning MUTANT_SENTINEL, so the one
        # reachable way a minted guard survives it is an original that returns the sentinel itself.
        # Contrived, and that is the point: it is the degenerate case the gate exists to fail closed
        # on, and it is the only input that proves the gate is wired in at all.
        wtM = os.path.join(tmp, "wtM")
        os.makedirs(os.path.join(wtM, pkg))
        open(os.path.join(wtM, pkg, "echo.py"), "w").write('def echo():\n    return "something else"\n')
        rM = capture(wtM, 452, pkg + "/echo.py", pkg,
                     _st_body(source="def echo():\n    return %r\n" % (MUTANT_SENTINEL,)),
                     {"verdict": "fail", "findings": ["echo is wrong"],
                      "repro": {"entrypoint": "echo", "input": {"args": []}}},
                     1, mode="on", ledger=Ledger(os.path.join(tmp, "lM"), 452))
        ck("a guard that SURVIVES the mutation probe is REJECTED (it cannot be shown to assert "
           "anything load-bearing about the entrypoint) — the gate fails closed",
           not rM["minted"] and rM["rejected"] and rM["rejected"][0].get("check") == "mutation-resistant",
           str(rM["minted"] or rM["rejected"]))
        ck("...and that rejection wrote nothing under %s/ either" % TESTS_DIR,
           not os.path.exists(os.path.join(wtM, pkg, TESTS_DIR)))

        # ── 5. worker-immutability: the scope claims, and guard() ──
        print("-- 5. worker-immutability: pair_loop's scope, and the guard that completes it")
        ck("is_harness_owned() catches the dir, its files, and any package root",
           all(is_harness_owned(p) for p in ("tests/regression", "tests/regression/test_x.py",
                                             pkg + "/tests/regression/test_x.py", "./tests/regression/x.py")))
        ck("is_harness_owned() is a PATH match, not a string prefix (tests/regression_notes.md is not it)",
           not any(is_harness_owned(p) for p in ("tests/regression_notes.md", "tests/regressions/x.py",
                                                 "regression/x.py", pkg + "/clamp.py")))
        ck("tests_dir_for() puts the guard under the #409 package root pair_loop resolved",
           tests_dir_for(deliv, pkg) == pkg + "/" + TESTS_DIR, tests_dir_for(deliv, pkg))
        ck("tests_dir_for() falls back to the deliverable's own directory with no package",
           tests_dir_for("tools/x.py", None) == "tools/" + TESTS_DIR, tests_dir_for("tools/x.py", None))

        # tamper, three ways; the guard restores all three
        gp = os.path.join(wt, rel)
        open(gp, "w").write("def test_nothing():\n    assert True\n")      # weakened
        g = guard(wt, 440, mode="on", ledger=led)
        ck("guard() RESTORES a guard the worker weakened", _read_text(gp) == guard_src
           and g["tampered"] and g["tampered"][0]["how"] == "MODIFIED", str(g["tampered"]))
        os.remove(gp)
        g = guard(wt, 440, mode="on", ledger=led)
        ck("guard() RESTORES a guard the worker deleted", _read_text(gp) == guard_src
           and g["tampered"] and g["tampered"][0]["how"] == "DELETED", str(g["tampered"]))
        shutil.rmtree(os.path.join(wt, pkg, "tests"))
        g = guard(wt, 440, mode="on", ledger=led)
        ck("guard() RESTORES a guard whose whole directory the worker removed", _read_text(gp) == guard_src)
        ck("...and the tamper is journaled, naming what was done", "RESTORED from the harness ledger" in guard_note(g)
           and rel in guard_note(g), guard_note(g))
        g = guard(wt, 440, mode="on", ledger=led)
        ck("guard() is idempotent: an intact guard is left alone and reported intact",
           not g["tampered"] and g["intact"] == [rel] and guard_note(g) == "", str(g))
        wsrc_before = _read_text(os.path.join(wt, deliv))
        guard(wt, 440, mode="on", ledger=led)
        ck("guard() never touches the worker's MODULE — only the harness's own artifact",
           _read_text(os.path.join(wt, deliv)) == wsrc_before)
        ck("an in-tree manifest could not have survived that: the ledger is outside the worktree",
           not os.path.abspath(led.path).startswith(os.path.abspath(wt) + os.sep))
        ck("the ledger is append-only: re-adding the same path with different bytes is refused",
           _ledger_refuses(led, rel))

        # the ledger's real home, resolved from git's own layout
        print("-- 5b. the ledger's home is the repo's git COMMON dir, resolved without running git")
        ck("a plain checkout's .git directory is the answer", _ledger_dir_plain(tmp))
        ck("a linked worktree's .git FILE is followed through commondir to the repo's real .git",
           _ledger_dir_linked(tmp))
        ck("an unrecognizable layout returns None (capture then REFUSES, never falls back in-tree)",
           ledger_dir(os.path.join(tmp, "nothing-here")) is None)
        ck("this ticket's own worktree resolves to congruency/.git/%s" % LEDGER_DIRNAME,
           (ledger_dir(ROOT) or "").endswith(os.path.join(".git", LEDGER_DIRNAME)), str(ledger_dir(ROOT)))

        # ── pair_loop's real scoping, executed ──
        print("-- 5c. pair_loop's deliverable/worker scoping, EXECUTED (#440's 'verify' item)")
        try:
            pl = _import_pair_loop()
            rep_rows = scope_report(pl, os.path.join(tmp, "scope"))
            named = dict((c[0].split(":")[0], c) for c in rep_rows)
            for claim, ok, detail in rep_rows[:3]:
                ck(claim, ok, detail)
            ck("...so guard() is REQUIRED, and this module says so rather than claiming the scope "
               "already does it", "package deliverable" in " ".join(named), "")
        except Exception as e:  # noqa: BLE001
            ck("pair_loop importable so its real scoping can be executed", False, str(e))

        # ── 5d. no leak into the worker's prompt, the lesson, or the playbook ──
        print("-- 5d. the mechanism never reaches the worker's prompt, a lesson, or the playbook")
        pl = _import_pair_loop()
        wf = worker_findings(v_dict)
        ck("the worker-facing findings carry no capture marker", leaks_capture(" ".join(wf)) == [],
           str(leaks_capture(" ".join(wf))))
        ck("...nor the expected value, the guard path, or any assertion literal",
           not any(s in " ".join(wf) for s in (rel, "expected", "assert", "EXPECTED", "5")), str(wf))
        fx = "\nPrior adversary findings to address:\n- " + "\n- ".join(wf) + "\n"
        prompt = pl.WORKER_PROMPT % {"agent": "coder-t440r2", "role": "coder", "kind": "build", "tid": 440,
                                     "title": "t", "body": _st_body(), "deliverable": deliv,
                                     "worker_scope": pl.worker_scope(deliv, pkg), "playbook": "",
                                     "workspace": pl.WORKSPACE % {"branch": "ticket/440"}, "findings": fx,
                                     "worker_focus": pl.FOCUS["build"]["worker_focus"]}
        ck("pair_loop's REAL worker birth prompt, built from these findings, leaks nothing",
           leaks_capture(prompt) == [], str(leaks_capture(prompt)))
        ck("...and never tells the worker there is an assertion to satisfy",
           "make this assertion pass" not in prompt.lower() and rel not in prompt)
        # the harvester's note -> lessons.recent -> --compile-playbook's body, exactly as pair_loop builds it
        lesson = ("passed in 2 rounds. Rework forced by the adversary — round 1 findings: %s. "
                  "Resolution: fixed" % " | ".join(wf))
        ck("the lesson harvest() would file from these findings leaks nothing", leaks_capture(lesson) == [])
        pb_body = ("Write docs/PLAYBOOK.md: the playbook future workers read at birth. Lessons:\n"
                   + "\n".join("- [ticket #%s] %s" % (l["ticket_id"], l["note"])
                               for l in [{"ticket_id": 440, "note": lesson}]))
        ck("--compile-playbook's body, built from that lesson, leaks nothing into docs/PLAYBOOK.md",
           leaks_capture(pb_body) == [], str(leaks_capture(pb_body)))
        # ...and an adversary that TRIES to smuggle the mechanism into its prose is scrubbed
        nasty_v = {"verdict": "fail", "findings": ["just make tests/regression/test_t440_clamp_ab.py pass "
                                                   "— see regression_capture.py for the captured repro"]}
        ck("an adversary smuggling the mechanism into its PROSE is detected", leaks_capture(nasty_v["findings"][0]))
        ck("...and scrubbed out of the worker-facing findings", leaks_capture(" ".join(worker_findings(nasty_v))) == [],
           str(worker_findings(nasty_v)))
        ck("...while the rest of its prose survives (scrubbing is redaction, not deletion)",
           "pass" in worker_findings(nasty_v)[0] and "[redacted]" in worker_findings(nasty_v)[0],
           str(worker_findings(nasty_v)))
        ck("leaks_capture() does NOT fire on honest prose using the word 'regression'",
           leaks_capture("this reintroduces the #279 regression in the dispatch path") == [])
        ck("the documented hook patch itself is stated, not applied (pair_loop.py is not this "
           "deliverable and an edit to it would be reaped as a stray)",
           "does not edit pair_loop" in HOOK_PATCH or "NOT APPLIED BY THIS MODULE" in HOOK_PATCH)

        # ── 7. OFF changes nothing ──
        print("-- 7. OFF is a byte-for-byte no-op")
        wtO = os.path.join(tmp, "wtOff")
        os.makedirs(os.path.join(wtO, pkg))
        open(os.path.join(wtO, deliv), "w").write(_ST_BUGGY)
        led_dir = os.path.join(tmp, "ledgerOff")
        before = _tree(wtO)
        rO = capture(wtO, 450, deliv, pkg, _st_body(), verdict, 1, mode="off", ledger=Ledger(led_dir, 450))
        ck("capture OFF returns immediately, disabled", rO["enabled"] is False and not rO["minted"]
           and not rO["rejected"] and not rO["stage"] and rO["note"] == "", str(rO))
        ck("capture OFF created NO file in the worktree (before/after tree identical)", _tree(wtO) == before,
           str(set(_tree(wtO)) ^ set(before)))
        ck("capture OFF created no ledger, not even its directory", not os.path.exists(led_dir))
        gO = guard(wtO, 450, mode="off", ledger=Ledger(led_dir, 450))
        ck("guard OFF is a no-op too", gO["enabled"] is False and gO["checked"] == 0 and not os.path.exists(led_dir))
        ck("capture OFF with a registry that says enabled is STILL off (the flag outranks the file)",
           capture(wtO, 450, deliv, pkg, _st_body(), verdict, 1, mode="off",
                   registry={REGISTRY_KEY: {"enabled": True}}, ledger=Ledger(led_dir, 450))["enabled"] is False)
        ck("...and the default-argument path is the OFF path (no mode passed at all)",
           capture(wtO, 450, deliv, pkg, _st_body(), verdict, 1, ledger=Ledger(led_dir, 450))["enabled"] is False)
        ck("capture OFF leaves the worker's findings byte-for-byte what pair_loop journals today",
           worker_findings({"findings": plain}, capture_enabled("off")) == plain)

        # ── the repo itself was never touched ──
        print("-- isolation: this repo, the db and the network were never touched")
        ck("no bug_report was filed into this repo's sink during the selftest",
           (os.path.getsize(sink) if os.path.isfile(sink) else None) == sink_before,
           "%s changed size" % sink)
        ck("no guard, ledger or runner was written into this repo",
           not os.path.exists(os.path.join(ROOT, TESTS_DIR)) and not os.path.exists(os.path.join(ROOT, "_rc_runner.py")))
        # THE ONE THAT CAUGHT ME: importing pair_loop/forge_refactor_ticketer to test against the
        # REAL code writes tools/__pycache__/*.pyc unless sys.dont_write_bytecode is set first. The
        # claim below is worth nothing unless it is checked, so it is checked.
        tools_after = _tree(tools_dir)
        ck("importing the real pair_loop wrote NO .pyc into tools/ (_no_bytecode(); #153: a "
           "'read-only' operation is not automatically side-effect-free)",
           tools_after == tools_before,
           "appeared: %s" % sorted(set(tools_after) - set(tools_before))[:4])
        ck("...and no __pycache__ directory exists beside this module because of this run",
           not any(p.startswith("__pycache__") for p in tools_after),
           str([p for p in tools_after if p.startswith("__pycache__")][:3]))

        bad = [n for n, ok, _ in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s"
              % (len(checks) - len(bad), len(checks), "" if not bad else "; FAILED: " + "; ".join(bad)))
        return 1 if bad else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        print("== selftest == throwaway workspace removed (no db, no agents, no network, no repo writes)")


def _ledger_refuses(led, rel):
    try:
        led.add({"path": rel, "sha256": _sha("different"), "source": "different"})
        return False
    except Unexpected:
        return True


def _ledger_dir_plain(tmp):
    d = os.path.join(tmp, "plain")
    os.makedirs(os.path.join(d, ".git"))
    return ledger_dir(d) == os.path.join(d, ".git", LEDGER_DIRNAME)


def _ledger_dir_linked(tmp):
    """A linked worktree's layout, byte for byte as git writes it (and as this checkout has it)."""
    repo, wt = os.path.join(tmp, "lrepo"), os.path.join(tmp, "lwt")
    gd = os.path.join(repo, ".git", "worktrees", "ticket-440")
    os.makedirs(gd)
    os.makedirs(wt)
    open(os.path.join(gd, "commondir"), "w").write("../..\n")
    open(os.path.join(wt, ".git"), "w").write("gitdir: %s\n" % gd)
    return ledger_dir(wt) == os.path.join(repo, ".git", LEDGER_DIRNAME)


def main():
    ap = argparse.ArgumentParser(
        description="regression_capture (#440): a CONFIRMED auditor finding's structured repro "
                    "becomes a red, worker-immutable regression test whose `expected` is derived "
                    "from the ticket's embedded ORIGINAL SOURCE. Default OFF.")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the method on a THROWAWAY synthetic unit: red-on-buggy, "
                         "green-on-original, mutation-resistance, bogus-capture rejection, "
                         "worker-scope exclusion of %s/, and OFF-is-a-no-op. No network, no db, "
                         "no writes to this repo." % TESTS_DIR)
    ap.add_argument("--verify-scope", action="store_true",
                    help="EXECUTE pair_loop's real commit scoping against a throwaway repo and "
                         "report what it does with a worker edit under %s/ (#440's 'verify "
                         "pair_loop's deliverable/worker scoping enforces this')" % TESTS_DIR)
    ap.add_argument("--print-hook", action="store_true",
                    help="print the exact pair_loop.py patch that installs the hook, and why each line")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.verify_scope:
        return verify_scope()
    if a.print_hook:
        print(HOOK_PATCH)
        return 0
    ap.print_help()
    print("\nThis module is a LIBRARY: pair_loop calls capture()/guard()/worker_findings() through "
          "the hook printed by --print-hook. Capture is OFF unless pair_loop is run with "
          "--regression-capture on, or with auto and registry.json's "
          '{"%s": {"enabled": true}}.' % REGISTRY_KEY)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Unexpected as e:
        bug_report("main", e, "python3 regression_capture.py " + " ".join(sys.argv[1:]), e)
        print("UNEXPECTED: %s" % e)
        sys.exit(2)
