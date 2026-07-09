#!/usr/bin/env python3
"""mint_crank.py — mint a crank: inject one python patch, capture it as the next version.

A crank stroke = INJECT one author-supplied Python patch on the single `main` branch, RUN it
(its one change), and CAPTURE it (commit + version tag) — the captured patch IS the diff that
defines the next version. No branch-per-crank: a crank is a commit + tag IN PLACE. This formalises
the fixes/*.py "ratchet link" discipline into one operation.

    # patch mode (precondition: on `main`, tracked-clean, php provisioned):
    python3 checkouts/current/congruency/tools/mint_crank.py --patch /path/to/turn_xyz.py [--name xyz] [-m MSG]
    # capture mode — mint a docs/config crank from the CURRENT working tree (no patch to run):
    python3 checkouts/current/congruency/tools/mint_crank.py --no-patch --keep-state [--no-verify] -m MSG
    # db-less crank — no database touched at all (make_state skipped; no database.tar.xz):
    python3 checkouts/current/congruency/tools/mint_crank.py --no-patch --no-state [--no-verify] -m MSG

Steps (each records a BUG EVENT on ANY unexpected outcome — exception OR expected!=actual —
then fail-fast):
    precondition  on `main`; tracked-clean (patch mode) OR a non-empty working tree (--no-patch)
    inject/run    patch mode only: copy the python patch -> fixes/<name>.py (must compile), run it (exit 0)
    state         make_state.py -> in-tree database.tar.xz  (skipped by --keep-state; --no-state omits state entirely)
    shadow gate   run install.json `shadows` (pure-python; the Mac-native regression gate)  (0 failed)
    capture       add -A + commit + version-4.0xx tag on `main` (installer + source + db + install.json in the commit);
                  install.json is re-emitted with the durable fields (preserve_db/migrate/shadows) CARRIED FORWARD
    verify        tooling/congruencey-tests/verify  (0 failed) — auto-skips when php isn't provisioned / --no-verify

Push is a SEPARATE release step — the mint stays local. python only, registry-gated.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))          # checkouts/current/congruency/tools
SOURCE = os.path.dirname(HERE)                             # checkouts/current
FIXES = os.path.join(SOURCE, "fixes")
VERSIONING = os.path.join(SOURCE, "versioning")


# --------------------------------------------------------------------------- #
# registry + Variant-A bug report + telemetry (reused pattern)                #
# --------------------------------------------------------------------------- #
def find_registry(start=HERE):
    d = os.path.abspath(start)
    while True:
        cand = os.path.join(d, "registry.json")
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            raise FileNotFoundError("registry.json not found at/above %s" % start)
        d = parent


def load_registry():
    import json
    path = find_registry()
    reg = json.load(open(path))
    reg["__root__"] = os.path.dirname(path)
    return reg


def bug_report(reg, exc, tb, step):
    import json
    root = (reg or {}).get("__root__") or os.path.dirname(os.path.dirname(SOURCE))
    path = os.path.join(root, (reg or {}).get("bug_reports", "logs/bug_reports.jsonl"))
    frames = traceback.extract_tb(exc.__traceback__)
    last = frames[-1] if frames else None
    entry = {
        "filename": os.path.basename(__file__),
        "function": last.name if last else "?",
        "time-of-occurance": datetime.now().isoformat(),
        "methods-to-reproduce": "python3 %s %s" % (os.path.relpath(__file__, root), " ".join(sys.argv[1:])),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": tb.strip().splitlines()[-6:],
        "note": "ratchet mint step: %s" % step,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    return path


def telemetry_handles(reg):
    try:
        pkgs = os.path.dirname(os.path.dirname(reg["__root__"]))   # .../packages
        cand = os.path.join(pkgs, "jazz_telemetry")
        if cand not in sys.path:
            sys.path.insert(0, cand)
        from jazz_telemetry import telemetry, open_ticket
        return telemetry("ratchet"), open_ticket
    except Exception:  # noqa: BLE001
        return None, None


class Unexpected(RuntimeError):
    """Raised when a step's actual outcome != expected (bug event, even without an exception)."""


# --------------------------------------------------------------------------- #
# git + subprocess helpers                                                    #
# --------------------------------------------------------------------------- #
def _root():
    return load_registry()["__root__"]


ROOT = _root()


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def run_py(path, *args, timeout=300):
    return subprocess.run([sys.executable, path, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)


# --------------------------------------------------------------------------- #
# steps                                                                       #
# --------------------------------------------------------------------------- #
def step_precondition(current, require_clean=True):
    # A crank is a commit + tag IN PLACE on the single `main` branch (no fork, no side branch).
    if current != "main":
        raise Unexpected("mint must run on the `main` branch, not %r" % current)
    dirty = [l for l in git("status", "--porcelain").stdout.splitlines() if not l.startswith("??")]
    if require_clean and dirty:
        # patch mode: the injected patch IS the change, so the tree must start clean.
        raise Unexpected("tree has uncommitted tracked changes; refusing to mint")
    if not require_clean and not git("status", "--porcelain").stdout.strip():
        # --no-patch capture mode: the change is already in the working tree (docs/config crank).
        raise Unexpected("--no-patch capture: nothing changed in the working tree to capture")
    return current


def step_inject(patch, name):
    if not os.path.isfile(patch):
        raise Unexpected("patch not found: %s" % patch)
    base = name if name.endswith(".py") else name + ".py"
    dest = os.path.join(FIXES, base)
    if os.path.exists(dest):
        raise Unexpected("patch destination already exists: %s" % dest)
    shutil.copy2(patch, dest)
    os.chmod(dest, os.stat(dest).st_mode | 0o111)
    c = subprocess.run([sys.executable, "-m", "py_compile", dest], capture_output=True, text=True)
    if c.returncode != 0:
        raise Unexpected("injected patch does not compile: %s" % c.stderr.strip())
    return dest


def step_run(dest):
    r = run_py(dest)
    if r.returncode != 0:
        raise Unexpected("patch exited %s: %s" % (r.returncode, (r.stderr or r.stdout).strip()[-400:]))
    return {"stdout_tail": (r.stdout or "").strip().splitlines()[-3:]}


DEFAULT_SHADOWS = ["tooling/congruencey-tests/db-preserve-shadow.py",
                   "tooling/congruencey-tests/agents-migration-shadow.py"]


def write_install_config(root, version, no_verify=False, return_to_main=False, host="0.0.0.0", port=8899, hash_track=True):
    """Emit the version's configuration object (install.json) at the repo root so it is committed
    INTO the version tag.

    Instrumentation counterpart to setup.py: extracts the version stamp + lifecycle params ahead
    of time so `python3 setup.py` needs no hand-typed args. Kept in lockstep with setup.py's
    canonical_config() — same schema.

    The durable install fields (preserve_db, migrate, shadows) are CARRIED FORWARD from the
    existing root install.json, so a mint never silently drops what the last crank declared — the
    config object is the source of truth, mint only re-stamps the version. (Bug: this used to emit
    a fixed subset and would regress preserve_db/migrate/shadows on the next mint.)"""
    import json
    prev = {}
    prevp = os.path.join(root, "install.json")
    if os.path.isfile(prevp):
        try:
            prev = json.load(open(prevp))
        except Exception:  # noqa: BLE001
            prev = {}
    cfg = {
        "component": "ratchet",
        "version": version,
        "no_verify": bool(no_verify),
        "return_to_main": bool(return_to_main),
        "host": host,
        "port": int(port),
        "hash_track": bool(hash_track),
        "preserve_db": bool(prev.get("preserve_db", True)),      # the installer remembers our db
        "migrate": bool(prev.get("migrate", True)),              # apply forward-only additive migrations
        "shadows": list(prev.get("shadows", DEFAULT_SHADOWS)),   # install-gating regression suites
        "components": {name: version for name, _ in COMPONENTS},
        "generated_by": "mint_crank.py (instrumentation)",
    }
    with open(os.path.join(root, "install.json"), "w") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    return cfg


# per-component config objects: each component carries its own version-stamped config object
# (config separated from code). Kept in lockstep with setup.py COMPONENTS / component_config().
COMPONENTS = [
    ("congruency", "checkouts/current/congruency"),
    ("state", "checkouts/current/state"),
]


def write_component_configs(root, version):
    """Write component.json (version stamp + identity) into each component dir so it rides in the
    crank. Non-colliding with the CMS's congruency/install.json (its constants map)."""
    import json
    for name, rel in COMPONENTS:
        d = os.path.join(root, rel)
        if not os.path.isdir(d):
            continue
        with open(os.path.join(d, "component.json"), "w") as fh:
            json.dump({"component": name, "version": version,
                       "generated_by": "mint_crank.py (instrumentation)"}, fh, indent=2)
            fh.write("\n")


def step_capture(message):
    """Capture the patch as the next version — LEAN single-repo path.

    commit_release's collect_modules() scans the parent for child repos (root=repo -> "no
    modules"; root=packages -> stray manifest + a landmine if a sibling ever gets git-init'd),
    so we stage/commit/tag THIS repo directly and reuse version_source.compute_next_version()
    for the python-computed version (never inferred). Single folded repo, no sibling reach."""
    if VERSIONING not in sys.path:
        sys.path.insert(0, VERSIONING)
    from gitutil import Git
    from version_source import compute_next_version

    g = Git(identity={"name": "ratchet", "email": "ratchet@congruency.local"}, echo=False)

    # Compute the version FIRST (reads live tags only — no staging needed), then emit this
    # version's install.json so it is CAPTURED IN the version commit — instrumentation, prior
    # to pushing. The ratchet's install.py reads `version-<v>:install.json` for the version +
    # args, so nobody hand-types them and it runs on any machine.
    tags_before = set(git("tag", "-l", "version-*").stdout.split())
    version = compute_next_version(g, ROOT)                     # python-computed from live tags
    tag = "version-%s" % version
    write_install_config(ROOT, version)
    write_component_configs(ROOT, version)                     # per-component config objects

    g.run(["add", "-A"], ROOT, write=True)                     # stages the patch + config objects
    if not (g.query(["diff", "--cached", "--name-only"], ROOT) or "").strip():
        raise Unexpected("nothing staged — the patch produced no change to capture")

    before = g.query(["rev-parse", "HEAD"], ROOT)
    g.run(["commit", "-m", message], ROOT, write=True)
    after = g.query(["rev-parse", "HEAD"], ROOT)
    if after == before:
        raise Unexpected("commit did not advance HEAD")
    g.run(["tag", "-a", tag, "-m", "Release %s" % version], ROOT, write=True)
    if tag not in (set(git("tag", "-l", "version-*").stdout.split()) - tags_before):
        raise Unexpected("expected new tag %s to be created" % tag)
    return {"version": version, "tag": tag, "committed_in": ["congruencey"], "commit": after[:10],
            "install_config": "install.json"}


def step_state():
    """Produce the crank's state as an in-tree database.tar.xz (no side branch). Runs BEFORE
    capture so `add -A` folds the db into the version commit — the crank carries its own state."""
    r = run_py(os.path.join(HERE, "make_state.py"))
    if r.returncode != 0:
        raise Unexpected("make_state failed: %s" % (r.stderr or r.stdout).strip()[-400:])
    artifact = os.path.join(ROOT, "checkouts", "current", "state", "database.tar.xz")
    if not os.path.isfile(artifact):
        raise Unexpected("make_state produced no in-tree database.tar.xz at %s" % artifact)
    return {"artifact": "checkouts/current/state/database.tar.xz", "bytes": os.path.getsize(artifact)}


def step_shadows():
    """Mac-native gate: run the pure-python shadow suites named by install.json. They exercise
    setup.py's DB-preserving install + the agent migration WITHOUT needing PHP, so the mint is
    gated even on a host where the full PHP verify suite can't run. A non-zero exit aborts the
    mint (a broken crank never lands)."""
    import json
    cfgp = os.path.join(ROOT, "install.json")
    shadows = []
    if os.path.isfile(cfgp):
        try:
            shadows = json.load(open(cfgp)).get("shadows", [])
        except Exception:  # noqa: BLE001
            shadows = []
    ran = []
    for rel in shadows:
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            raise Unexpected("shadow suite not found: %s" % rel)
        r = subprocess.run([sys.executable, path], cwd=ROOT, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            raise Unexpected("shadow FAILED (%s): %s" % (rel, (r.stdout + r.stderr).strip()[-400:]))
        ran.append(rel)
    return {"shadows": ran or ["(none declared)"]}


def _php_provisioned():
    return os.path.isfile(os.path.join(ROOT, "tooling", "congruencey-harness", "php", "php"))


def step_verify(skip=False):
    """The full PHP verify suite (stand-up + bug-catalog + branch-coverage). Auto-skips when PHP
    isn't provisioned (e.g. natively on macOS arm64, where the linux php can't exec) — the shadow
    gate is the native verification there. --no-verify forces the skip."""
    if skip or not _php_provisioned():
        reason = "forced (--no-verify)" if skip else "php not provisioned — shadow gate is the native gate"
        return {"skipped": True, "reason": reason}
    r = subprocess.run([os.path.join(ROOT, "tooling", "congruencey-tests", "verify")],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    m = re.search(r"(\d+)\s+suites passed,\s+(\d+)\s+failed", r.stdout)
    if not m or int(m.group(2)) != 0:
        raise Unexpected("verify not clean: %s" % (r.stdout or r.stderr).strip()[-400:])
    return {"passed": int(m.group(1)), "failed": int(m.group(2))}


# --------------------------------------------------------------------------- #
# driver                                                                      #
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="mint a crank: inject+run one python patch, OR (--no-patch) "
                                             "capture the current working-tree change. Commit + version tag in place.")
    ap.add_argument("--patch", default=None, help="path to the python patch script (the turn)")
    ap.add_argument("--no-patch", action="store_true",
                    help="capture the current working-tree change directly (docs/config crank — no patch to inject/run)")
    ap.add_argument("--name", default=None, help="injected filename under fixes/ (default: patch basename)")
    ap.add_argument("--keep-state", action="store_true",
                    help="keep the existing in-tree database.tar.xz (skip make_state — for changes that don't touch state, "
                         "and on hosts without the state source_db / php). Tolerant: proceeds even if none is present.")
    ap.add_argument("--no-state", action="store_true",
                    help="crank WITHOUT a database: skip state entirely — no make_state, no database.tar.xz produced OR "
                         "required. A crank is code + config; state is not a git blob.")
    ap.add_argument("--no-verify", action="store_true", help="skip the PHP verify suite (the shadow gate still runs)")
    ap.add_argument("-m", "--message", default=None, help="commit/release message")
    a = ap.parse_args()

    patch_mode = bool(a.patch) and not a.no_patch
    if not patch_mode and not a.no_patch:
        ap.error("give --patch <file> (patch mode) or --no-patch (capture the working tree)")

    reg = load_registry()
    T, open_ticket = telemetry_handles(reg)
    name = a.name or (os.path.splitext(os.path.basename(a.patch))[0] if a.patch else "capture")
    message = a.message or ("crank: %s" % name)
    current = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def do(step_name, fn):
        print("\n== %s ==" % step_name)
        t0 = time.time()
        try:
            out = fn()
            ms = (time.time() - t0) * 1000.0
            if T:
                T.emit("mint", status="ok", ms=ms, step=step_name)
            print("   ok (%.0f ms) %s" % (ms, out if out else ""))
            return out
        except Exception as exc:  # noqa: BLE001 — Unexpected or any error is a bug event
            tb = traceback.format_exc()
            p = bug_report(reg, exc, tb, step_name)
            if T:
                T.emit("mint", status="fail", step=step_name, error=str(exc)[:200])
            if open_ticket:
                try:
                    open_ticket("ratchet mint failed at %s" % step_name, component="ratchet",
                                severity="high", body=tb[-1500:], step=step_name)
                except Exception:  # noqa: BLE001
                    pass
            print("   FAIL: %s\n   bug report -> %s" % (exc, p), file=sys.stderr)
            raise

    print("mint crank: on %s, %s" % (current, ("patch=%s" % a.patch) if patch_mode else "capture working tree (--no-patch)"))
    do("precondition", lambda: step_precondition(current, require_clean=patch_mode))
    if patch_mode:
        dest = do("inject", lambda: step_inject(a.patch, name))
        do("run patch", lambda: step_run(dest))
    if a.no_state:
        print("\n== state ==\n   no-state: cranking WITHOUT a database (make_state skipped; no database.tar.xz)")
    elif a.keep_state:
        art = os.path.join(ROOT, "checkouts", "current", "state", "database.tar.xz")
        print("\n== state (in-tree db) ==\n   keep-state: %s"
              % ("reusing existing database.tar.xz" if os.path.isfile(art)
                 else "no database.tar.xz present — proceeding without one"))
    else:
        do("state (in-tree db)", step_state)                # produce db BEFORE capture...
    do("shadow gate", step_shadows)                         # Mac-native regression gate before landing
    cap = do("capture (commit + tag)", lambda: step_capture(message))   # ...so it rides in the version commit
    do("verify", lambda: step_verify(skip=a.no_verify))

    if T:
        T.emit("mint", status="ok", branch=current, version=cap.get("version"))
    print("\n== crank minted on %s: %s (commit + tag in place; shadow gate green) ==" % (current, cap.get("tag")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — per-step handler already recorded the bug event
        sys.exit(1)
