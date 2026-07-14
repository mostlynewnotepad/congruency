#!/usr/bin/env python3
"""list_versions.py — discover the installable congruency versions from git tags.

A congruency release (a "crank") is a commit + a `version-<X>` git tag, not a branch
(README.md:7). `setup.py install` checks out `version-<X>`, and with no `--version` it
installs the NEWEST tag (setup.py's `newest_version_tag`, setup.py:180-186). Until now
those numbers lived ONLY as git tags: there was no command that printed the current
version, listed the installable ones, or emitted a machine-readable manifest. This tool is
that command.

It is READ-ONLY: it runs `git tag -l version-*` and nothing else — it never writes to git
or the repo and creates no files. The version set and its ordering are the SAME ones
`setup.py` uses, so every number this prints is a value `setup.py install --version <X>`
accepts. A tag is an installable version iff the suffix after `version-` parses as a
dotted-integer (e.g. `4.140` -> `(4, 140)`); non-numeric tags are ignored, exactly as
setup.py's `_vkey` filter does (setup.py:173-186). "Newest" is the max of those integer
tuples, so `4.100` correctly ranks above `4.099`.

Usage:
    python3 list_versions.py            # list every installable version, newest first
    python3 list_versions.py --latest   # print ONLY the newest version number (e.g. 4.140)
    python3 list_versions.py --json      # emit a versions.json manifest to stdout

The repo root is found by walking UP from this tool's own location to registry.json
(note-for-claude: a tool that cannot see the registry throws); git tags are read from
there. Exit 0 on success; exit 2 with a one-line message (never a traceback) if no
version-* tags exist or git cannot be read.
"""
import argparse
import json
import os
import subprocess
import sys

PREFIX = "version-"


# ── registry gate (note-for-claude: a tool that cannot see the registry throws) ──────────────────
def find_root(start):
    d = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(d, "registry.json")):
            return d
        nxt = os.path.dirname(d)
        if nxt == d:
            raise RuntimeError("registry.json not found walking up from %s — refusing to run" % start)
        d = nxt


ROOT = find_root(os.path.dirname(os.path.abspath(__file__)))


def _vkey(v):
    """Parse a version suffix into a sortable integer tuple, or None if non-numeric.

    Kept identical to setup.py's `_vkey` (setup.py:173-177) so this tool's version set and
    ordering agree exactly with what `setup.py install` resolves."""
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:  # noqa: BLE001
        return None


def discover(root):
    """Every installable version, as (suffix) strings sorted OLDEST first.

    Reads the live git tags (`git tag -l version-*`) from `root` and keeps the ones whose
    suffix parses via `_vkey`, mirroring setup.py's `newest_version_tag` (setup.py:180-186).
    Raises RuntimeError if git itself cannot be read."""
    r = subprocess.run(["git", "tag", "-l", "version-*"], cwd=root,
                        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("git tag failed: %s" % (r.stderr or r.stdout).strip())
    pairs = []
    for t in r.stdout.split():
        suffix = t[len(PREFIX):]
        key = _vkey(suffix)
        if key:
            pairs.append((key, suffix))
    pairs.sort()
    return [suffix for _, suffix in pairs]


def main():
    ap = argparse.ArgumentParser(
        description="discover the installable congruency versions from git tags (read-only)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--latest", action="store_true",
                   help="print ONLY the newest installable version number, e.g. 4.140")
    g.add_argument("--json", action="store_true",
                   help="emit a versions.json manifest {latest, count, versions} to stdout")
    a = ap.parse_args()

    try:
        versions = discover(ROOT)  # oldest first
    except RuntimeError as exc:
        print("list_versions: %s" % exc, file=sys.stderr)
        return 2

    if not versions:
        print("list_versions: no version-* tags found; nothing is installable", file=sys.stderr)
        return 2

    latest = versions[-1]
    newest_first = list(reversed(versions))  # latest is newest_first[0]

    if a.latest:
        print(latest)
        return 0

    if a.json:
        # versions: newest first, so versions[0] == latest.
        json.dump({"latest": latest, "count": len(versions), "versions": newest_first},
                  sys.stdout, indent=2)
        print()
        return 0

    # default: human-readable list, newest first, the latest marked.
    print("installable congruency versions (git tags %s*): %d" % (PREFIX, len(versions)))
    print("latest: %s   (installed by default: python3 setup.py install)" % latest)
    print()
    for v in newest_first:
        print("  %s%s" % (v, "   <- latest" if v == latest else ""))
    print()
    print("install a specific version:  python3 setup.py install --version %s" % latest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
