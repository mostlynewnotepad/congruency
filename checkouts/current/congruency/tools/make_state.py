#!/usr/bin/env python3
"""make_state.py — produce this crank's state as an in-tree database.tar.xz.

State no longer lives on a `state` side-branch: it RIDES IN the version commit (the crank).
This PRODUCER snapshots the big unified database named by STATE.json `source_db`
(~/.jazz/congruency.sqlite) via sqlite's WAL-safe online backup, tars it into the tracked
`artifact` (checkouts/current/state/database.tar.xz), and leaves it in the working tree —
mint_crank's `add -A` captures it as part of the version. The legacy `seed` generator is a
fallback only. On checkout, install.py extracts the in-tree tarball into the state dir.

python only, registry-gated (throws if it can't see registry.json), auto bug-report on
exception (Variant-A), best-effort jazz telemetry.

    python3 checkouts/current/congruency/tools/make_state.py
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))          # checkouts/current/congruency/tools
SOURCE = os.path.dirname(HERE)                             # checkouts/current/congruency (the CMS app root)
STATE = os.path.join(os.path.dirname(SOURCE), "state")     # checkouts/current/state (sibling of congruency)
STATE_SPEC = os.path.join(STATE, "STATE.json")


# --------------------------------------------------------------------------- #
# registry (mandated: throw if not found) + Variant-A bug report              #
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
    path = find_registry()
    reg = json.load(open(path))
    reg["__root__"] = os.path.dirname(path)
    return reg


def bug_report(reg, exc, tb, note="ratchet crank: make_state"):
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
        "note": note,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    return path


def telemetry_handles(reg):
    """Best-effort jazz_telemetry (component 'ratchet'); returns (emit_handle, open_ticket)
    or (None, None). Never raises."""
    try:
        pkgs = os.path.dirname(os.path.dirname(reg["__root__"]))   # .../packages
        cand = os.path.join(pkgs, "jazz_telemetry")
        if cand not in sys.path:
            sys.path.insert(0, cand)
        from jazz_telemetry import telemetry, open_ticket           # noqa: E402
        return telemetry("ratchet"), open_ticket
    except Exception:  # noqa: BLE001
        return None, None


# --------------------------------------------------------------------------- #
# state production                                                            #
# --------------------------------------------------------------------------- #
def find_php(reg):
    env = os.environ.get("CONGRUENCEY_PHP")
    if env and os.path.isfile(env):
        return env
    rel = (reg.get("paths", {}) or {}).get("php", "tooling/congruencey-harness/php/php")
    p = os.path.join(reg["__root__"], rel)
    if not os.path.isfile(p):
        raise FileNotFoundError("php not provisioned at %s (run provision_php.py first)" % p)
    return p


def _snapshot_sqlite(src_path, dst_path):
    """Consistent single-file copy of a possibly-live/WAL sqlite via the online backup API —
    reads committed + WAL pages without mutating the source, and checkpoints into dst."""
    src = sqlite3.connect(src_path)
    try:
        dst = sqlite3.connect(dst_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def build_tarball(reg, tmp):
    """Capture THIS crank's state into `tmp` and return (tar_path, tables).

    The state IS the big unified database. `source_db` in STATE.json names it (default
    ~/.jazz/congruency.sqlite); it is snapshotted with sqlite's online backup so a live/WAL
    db yields a consistent single-file copy. It does NOT fabricate a fresh db — that produced
    a throwaway stub. The legacy seed generator is used ONLY as a fallback when no source_db
    is configured or present."""
    spec = json.load(open(STATE_SPEC)) if os.path.isfile(STATE_SPEC) else {}
    sqlite_tmp = os.path.join(tmp, "congruency.sqlite")

    # State is the REAL live DB and ONLY the real live DB. `source_db` must name it and exist; there
    # is NO fabricate/installed fallback. Capturing a seed as "state" is exactly how the clobber bug
    # propagated (a stale seed got re-committed and re-shipped, re-arming every extract site), so we
    # REFUSE rather than snapshot a guess.
    source_db = spec.get("source_db")
    src_path = os.path.expanduser(source_db) if source_db else None
    if not src_path:
        raise RuntimeError("STATE.json has no source_db — refusing to mint state. Point source_db at "
                           "the real live DB (~/bin/config/congruency/congruency.sqlite).")
    if os.path.islink(src_path) and not os.path.exists(src_path):
        raise RuntimeError("source_db symlink %s is DANGLING — refusing to snapshot a missing live DB." % src_path)
    if not os.path.isfile(src_path):
        raise RuntimeError("source_db %s does not exist — refusing to fabricate/snapshot a seed. The "
                           "live DB is the sole source of truth." % src_path)
    _snapshot_sqlite(src_path, sqlite_tmp)                      # WAL-safe read-only backup of the REAL live db
    members = [(sqlite_tmp, "congruency.sqlite")]

    con = sqlite3.connect(sqlite_tmp)
    try:
        tables = [x[0] for x in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    finally:
        con.close()
    missing = set(spec.get("expect_tables", [])) - set(tables)
    if missing:
        raise RuntimeError("state DB missing expected tables: %s" % sorted(missing))

    def _norm(ti):
        # reproducible (bug #3): strip mtime/owner so identical state -> identical blob
        ti.mtime = 0
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = ""
        ti.mode = 0o644
        return ti
    tar_path = os.path.join(tmp, "database.tar.xz")
    with tarfile.open(tar_path, "w:xz") as t:
        for src, arc in sorted(members, key=lambda x: x[1]):
            t.add(src, arcname=arc, filter=_norm)   # flat, normalized members
    return tar_path, tables


FORGE_DIR = "/Users/stevenpeterson/code/jazz-forge"
STATE_ARTIFACT = "congruency-state"    # forge artifact name for the state snapshot


def _forge():
    """The local content-addressed registry as a library (stdlib-only, cwd-independent)."""
    if FORGE_DIR not in sys.path:
        sys.path.insert(0, FORGE_DIR)
    from forge import artifacts
    return artifacts


def _git_head():
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=SOURCE, capture_output=True, text=True)
        return (r.stdout or "").strip() or None
    except Exception:      # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser(description="publish this crank's state to forge + write state.lock")
    # State does NOT ride in the git commit anymore: the reproducible snapshot is content-addressed in
    # forge, and only a small `state.lock` pointer is committed. Keeps cranks lean and, together with
    # halt-on-absent + explicit restore, makes a seed-over-live clobber structurally impossible.
    ap.add_argument("--version", default=None, help="crank version (from mint); labels the forge blob")
    a = ap.parse_args()

    reg = load_registry()
    lock_path = os.path.join(STATE, "state.lock")
    T, _ = telemetry_handles(reg)
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, tables = build_tarball(reg, tmp)                       # WAL-safe snapshot of the REAL live db
        sha = hashlib.sha256(open(tar_path, "rb").read()).hexdigest()
        ver = a.version or ("unversioned-%s" % sha[:12])
        artifacts = _forge()
        res = artifacts.put(tar_path, name=STATE_ARTIFACT, version=ver, kind="xz",
                            source_repo="congruency", source_commit=_git_head(), meta={"tables": tables})
        if res.get("sha256") != sha:
            raise RuntimeError("forge sha %s != computed %s — refusing to write an inconsistent lock"
                               % (res.get("sha256"), sha))
        os.makedirs(STATE, exist_ok=True)
        lock = {"schema": 1, "forge_name": res["name"], "forge_version": res["version"], "sha256": sha,
                "size": res.get("size"), "kind": "xz", "member": "congruency.sqlite", "tables": tables,
                "created": datetime.now().isoformat()}
        with open(lock_path, "w") as fh:
            json.dump(lock, fh, indent=2)
            fh.write("\n")
    result = {"forge_name": res["name"], "forge_version": res["version"], "sha256": sha,
              "size": res.get("size"), "lock": os.path.relpath(lock_path, reg["__root__"]), "tables": tables}
    if T:
        T.emit("make_state", status="ok", ms=(time.time() - t0) * 1000.0, version=res["version"])
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    _reg = None
    try:
        _reg = load_registry()
    except Exception:  # noqa: BLE001
        pass
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        p = bug_report(_reg, exc, tb)
        T, open_ticket = telemetry_handles(_reg) if _reg else (None, None)
        if T:
            T.emit("make_state", status="fail", note=str(exc)[:200])
        if open_ticket:
            try:
                open_ticket("ratchet make_state failed", component="ratchet", severity="high", body=tb[-1500:])
            except Exception:  # noqa: BLE001
                pass
        print("EXCEPTION — bug report -> %s" % p, file=sys.stderr)
        raise
