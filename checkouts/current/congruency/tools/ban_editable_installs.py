#!/usr/bin/env python3
"""ban_editable_installs.py — POLICY 2: a package is installed PROPER, never EDITABLE. The editable
escape hatch exists, is explicit, is auditable, and NEVER ships (ticket #215).

THE POLICY, quoted from ticket #215, which is its only source in this repository (nothing else here
defines it — do not go looking): "Install tooling installs packages PROPER (pip install . / a built
wheel), NEVER editable, by default. Editable (pip install -e) is permitted ONLY when an explicit
dev-phase flag is set (e.g. --dev-debug / config phase='debug') for a package under sustained
debugging, and such a package is BLOCKED from being marked done/committed until re-installed proper.
Add a CHECK (lint/CI shadow) that fails if any 'done' package is installed editable or if a venv
contains .egg-link / editable entries outside a declared dev-phase."

  !! THE NUMBER IS AMBIGUOUS IN THIS REPO — READ THIS ONCE AND THE CONFUSION IS GONE. "POLICY 2"
  here is TICKET #215's numbering. It is NOT pair_loop.py's policy (2), which is branch LIFECYCLE
  ("(2) LIFECYCLE — the branch is created when the pair is dispatched", pair_loop.py:41-43). It is
  also not "POLICY 1", which is ticket #214's clean-re-checkout invariant (tools/clean_recheckout.py).
  The numbering schemes are unrelated; this file implements #215's and cites the others by full name.

TERMS, each defined at first use, because whoever reads this file did not watch it being written:

  * A PROPER install COPIES the package's files into the interpreter's `site-packages` directory
    (`pip install .`, or `pip install <built wheel>`). The installed module is a copy: it is
    DECOUPLED from the source tree it was built from, and moving or deleting that source cannot
    break it.
  * An EDITABLE install (`pip install -e .`) copies nothing. It installs a POINTER back to the
    source tree, so `import <pkg>` executes the files in your checkout. Delete or move the checkout
    and the installed package breaks. That coupling is what POLICY 2 bans by default.
  * SITE-PACKAGES is the directory on `sys.path` where installed packages live
    (`<venv>/lib/python3.X/site-packages`). A VENV is a self-contained interpreter + its own
    site-packages, made by `python3 -m venv <dir>`.
  * DEV-PHASE (phase='debug') is the ONLY state in which an editable install is permitted: a package
    under sustained debugging, declared explicitly (see THE DEV-PHASE DECLARATION). Every other
    package is DONE — the default, and the state POLICY 2 assumes. "DONE" here means shippable;
    it is not the ticket-lifecycle DONE of pair_loop.py.
  * SHIP means to mark a package done or commit it. POLICY 2 refuses to ship an editable-installed
    package, dev-phase or not — see WHY THE HATCH NEVER SHIPS.

HOW AN EDITABLE INSTALL IS ACTUALLY DETECTED — the part that must be right, and that a reader is
entitled to see evidence for rather than trust. Editable installs have changed shape, so a detector
written from memory looks for the wrong thing:

  * `.egg-link` is LEGACY (`setup.py develop`, and `pip install -e` before pip 21.3). The ticket
    names it, and this file detects it, but MODERN pip does not create one at all. A check that
    looks ONLY for .egg-link finds nothing on any current toolchain and reports a clean venv that
    is full of editables. That is the trap this file is built to avoid.
  * PEP 660 is what modern pip writes: a `__editable__.<name>-<ver>.pth` in site-packages that
    imports a generated `__editable___<mangled>_finder.py` whose MAPPING points at the source tree.
  * PEP 610 `direct_url.json` (inside the `.dist-info` directory) is the AUTHORITATIVE, installer-
    independent record. `{"dir_info": {"editable": true}}` means editable, full stop.

    THE FALSE-POSITIVE TRAP that makes the `editable` key load-bearing: a PROPER `pip install .`
    from a local directory ALSO writes a direct_url.json, with the same `file://` url — only its
    dir_info is `{}`. So "direct_url.json exists" and "the url is a local path" are BOTH true of a
    perfectly compliant install. Only `dir_info.editable` separates them, and this file keys on
    exactly that. (Observed on the toolchain this was written against — python 3.14.6 / pip 26.1.2:
    editable -> `{"dir_info": {"editable": true}, "url": "file:///.../pkg"}`; proper -> `{"dir_info":
    {}, "url": "file:///.../pkg"}`. --selftest asserts both, so the claim is checked, not asserted.)

  All four forms are detected, plus a bare path-injection `.pth` (a file whose lines are PATHS into
  a source tree rather than the ordinary `import ...` line real packages ship). Detection is a pure
  FILESYSTEM read of site-packages: it never runs the venv's python, so it works on a CI shadow of a
  venv, on a venv whose interpreter is broken, and on a venv for another platform.

THE DEV-PHASE DECLARATION — the escape hatch, and what makes it auditable. Two independent
mechanisms, exactly as #215 names them ("--dev-debug / config phase='debug'"), and they do different
jobs. Read this before using either:

  * `--dev-debug --reason "<why>"` permits ONE editable install, right now, at the command line.
    --reason is mandatory: an escape hatch with no recorded reason is not auditable, and #215 asks
    for one that is. Every use appends to the AUDIT LOG (below) BEFORE pip runs and again after, so
    an editable install that happened is always on the record — including one that failed halfway.
  * `registry.json` config is what makes the hatch survive into CI. The CHECK is a fresh process
    scanning a venv days later; it cannot know what flags someone typed. Only a declaration in the
    repo's own config can waive it:

        "editable_installs": {
          "audit_log": "logs/editable_installs.jsonl",
          "packages": {
            "demo-pkg": {"phase": "debug", "reason": "chasing a heisenbug in the parser",
                         "declared_by": "steve", "ticket": 215, "expires": "2026-08-01"}
          }
        }

    `phase` must be exactly "debug" to waive. Any other value, or no entry at all, means DONE — so
    the DEFAULT for every package in this repo is DONE, and the default answer to every editable
    install is REFUSED. `expires` is optional; once the date is past the waiver is DEAD and the
    package is DONE again, because "sustained debugging" is a phase and not a permanent condition.
    Package names are matched PEP 503-normalized (`demo-pkg`, `demo_pkg` and `Demo.Pkg` are one
    name) — the dist-info directory spells it `demo_pkg` while the project spells it `demo-pkg`, and
    a matcher that missed that would silently waive nothing.

  THIS REPO'S registry.json DECLARES NO DEV-PHASE PACKAGES (there is no `editable_installs` key in
  it as of this commit, and adding one is not this ticket's business — its deliverable line says to
  write this file and "touch nothing else"). So on this repo, today, EVERY editable install is a
  violation. That is the intended resting state, not an oversight.

  `--dev-debug` WITHOUT a config declaration installs editable and then FAILS the check — correctly,
  and this is not a gap: the flag says "let me install this now", the config says "CI knows why".
  `install --dev-debug` prints that warning itself rather than letting you discover it in CI.

WHY THE HATCH NEVER SHIPS. #215: a dev-phase package "is BLOCKED from being marked done/committed
until re-installed proper." So the two gates answer DIFFERENT questions, and a declaration moves
only one of them:

    check   "may this venv exist as it is?"        declared dev-phase -> WAIVED (exit 0, reported)
    ship    "may this package be marked done?"     declared dev-phase -> STILL REFUSED (exit 3)

A declaration buys you a debugging session, never a release. `ship` is refused until the package is
re-installed proper — at which point the editable evidence is gone from site-packages and `ship`
passes on its own. Nothing needs to be un-declared for shipping to work again.

WHAT THIS FILE DOES — four commands, one invariant.

  1. install <pkg_dir> --venv <dir>   THE DEFAULT INSTALL PATH. Proper, always, unless --dev-debug.
     `--method source` (default) runs `pip install <pkg_dir>`; `--method wheel` BUILDS a wheel and
     installs that — #215 names both ("pip install . / a built wheel"). After a proper install it
     PROVES the result: zero editable evidence in the venv, direct_url.json not editable, and every
     top-level module imports from a neutral cwd with its `__file__` resolving INSIDE site-packages
     rather than inside the source tree. That is decoupling, proven structurally on every install.
  2. check --venv <dir>               THE LINT / CI SHADOW. Scans a venv and fails if any DONE
     package is installed editable, or if any editable entry exists outside a declared dev-phase.
     READ-ONLY: it never runs pip, never runs the venv's python, and creates NO file. --selftest
     proves that by listing the venv before and after.
  3. ship --venv <dir> [-- <cmd>]     THE SHIP GATE. Refuses (exit 3) if the package is editable-
     installed — dev-phase or not. With `-- <cmd>` it is a WIRE: the commit/ship command runs ONLY
     if the gate passes, so "an attempt to ship/commit an editable-installed package is refused" is
     enforced rather than merely reported.
  4. audit                            Prints the append-only audit log: every editable install ever
     performed through this tool, with its reason, its operator and its outcome.

THE LIVE VIOLATION IN THIS REPO, reported honestly and NOT edited. `pair_loop.py`'s install_check()
— the repo's own install tooling, and the thing #409 uses to prove a forge package installs — runs
`pip install -e .`:

    r = subprocess.run([py, "-m", "pip", "install", "-e", ".", "-q"], cwd=pkg_dir,   # pair_loop.py:1001
                       capture_output=True, text=True, env=env, timeout=300)         # pair_loop.py:1002

That is POLICY 2's most important real target, and it is untouched by this commit: pair_loop.py is
not this ticket's deliverable and editing it is outside what #215 authorized. Do not read any claim
here as saying otherwise. The replacement is provided instead, ready to drop in, and deliberately
mirrors install_check()'s exact contract (pair_loop.py:979-1027) so the future edit is mechanical
rather than archaeology — same signature, same ("PASS"|"FAIL"|"SKIP", detail) return, same
network-vs-defect distinction:

    from ban_editable_installs import proper_install_check     # tools/ is already on that path

    def install_check(base_dir, pkg_dir):                      # pair_loop.py:979
        return proper_install_check(base_dir, pkg_dir)

  Why "SKIP" survives the port: install_check treats an unreachable package index as a fact about
  the host and never as a failure of the package ("An unreachable index is a fact about this host,
  never about the package, so it must not be reported as a failure of the package", pair_loop.py:987-
  988). That reasoning is correct and is preserved verbatim in behavior — proper_install_check()
  returns SKIP on exactly the same conditions, using the same substring probe (pair_loop.py:1009-1013).

  What CHANGES in the port, and why it is strictly stronger: the installed package is a copy in
  site-packages, so the import that proves it usable proves something `-e` never could. Under `-e`,
  `from add import add` can succeed merely because the source tree is still on disk — pair_loop's own
  comment worries about the cwd (pair_loop.py:1015-1017) but the editable finder makes the source
  importable from ANY cwd, so that check cannot distinguish "installed" from "the checkout exists".
  Proper-installed, the same import passes only if the install really happened.

EXIT CODES (the CLI's whole contract):
    0  POLICY 2 HOLDS — no editable install outside a declared dev-phase; the gate permits the ship.
    1  the wrapped ship/commit command FAILED — read precisely: the command's OWN exit code is
       propagated verbatim, so a command that exits 7 makes this tool exit 7. What is guaranteed is
       non-zero, not the digit. This code is seen only when the command itself exited 1.
    2  UNEXPECTED — a Variant-A bug report was filed to the registry's bug_reports sink
       (note-for-claude: filename, function, time-of-occurance, methods-to-reproduce, possible-cause).
       Also argparse's own exit for a USAGE refusal (e.g. --dev-debug with no --reason), which files
       NO bug report and prints no traceback, because a misuse is not a fault.
    3  REFUSED — a POLICY 2 violation: an editable install outside a declared dev-phase, or an
       attempt to ship an editable-installed package. The wrapped command, if any, is NOT run.

USAGE (python only, per note-for-claude; registry-gated — a tool that cannot see registry.json throws):
    python3 ban_editable_installs.py install ./pkg --venv .venv          # PROPER (the default)
    python3 ban_editable_installs.py install ./pkg --venv .venv --method wheel
    python3 ban_editable_installs.py install ./pkg --venv .venv --dev-debug --reason "heisenbug"
    python3 ban_editable_installs.py check --venv .venv                  # the CI shadow (read-only)
    python3 ban_editable_installs.py check --venv .venv --json
    python3 ban_editable_installs.py ship --venv .venv --package demo-pkg
    python3 ban_editable_installs.py ship --venv .venv -- git commit -m "release"   # THE WIRE
    python3 ban_editable_installs.py audit                               # the escape hatch's record
    python3 ban_editable_installs.py --selftest                          # prove all of it; exit 0/1

--selftest builds throwaway venvs in a temp dir and checks every claim this docstring makes. Its
detector checks are HERMETIC — they build site-packages fixtures by hand (including a legacy
.egg-link, which modern pip can no longer produce), so they need no network and no pip. Its
end-to-end checks run REAL pip installs and prove the acceptance criteria for real, including moving
the source tree away and importing the proper-installed module anyway; those SKIP (never fail) if
pip cannot reach an index, exactly as pair_loop.py:985-988 does. It touches neither this repo nor the
db, needs no API key and no server, and gives every temp tree a registry.json of its own so even the
Variant-A bug reports it deliberately provokes land in the throwaway and not in this repo's logs/.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.parse


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
# pair_loop.py:168) and as clean_recheckout.py's does (:201): a tool that cannot see its registry
# throws rather than guessing. --root only chooses WHICH repo's config and audit log are used; it
# never disables this gate.
ROOT, REGISTRY = find_registry(os.path.dirname(os.path.abspath(__file__)))

AUDIT_DEFAULT = "logs/editable_installs.jsonl"


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
                "note": "POLICY 2 (ban editable installs) enforcement — ticket #215",
            }) + "\n")
        return path
    except Exception:  # noqa: BLE001 — the reporter is never allowed to be the failure
        return None


# ── names ─────────────────────────────────────────────────────────────────────────────────────────
def canon(name):
    """PEP 503 normalization: the one spelling every comparison in this file uses.

    Load-bearing, not cosmetic. pip escapes a project name for the dist-info DIRECTORY (`demo-pkg`
    becomes `demo_pkg-0.1.0.dist-info`) while the project, the registry declaration and the operator
    all say `demo-pkg`. Comparing the two raw spellings matches nothing, so a declaration would
    silently waive nothing and `ship --package demo-pkg` would silently gate nothing. Both failures
    are silent PASSES, which is the worst kind.
    """
    return re.sub(r"[-_.]+", "-", (name or "").strip()).lower()


def _url_to_path(url):
    """A PEP 610 `file://` url back to a filesystem path (percent-decoded; `file:///a/b%20c` is a
    real path with a space in it). Anything that is not a file url is returned verbatim — a package
    installed from an index has a https url and no source tree to point at."""
    if not isinstance(url, str) or not url.startswith("file://"):
        return url
    p = urllib.parse.urlparse(url)
    return urllib.parse.unquote(p.path)


# ── the evidence ──────────────────────────────────────────────────────────────────────────────────
class Editable:
    """ONE editable-installed package found in a venv, and every piece of evidence that says so.

    `package` is the PEP 503-normalized name, or "" for evidence that names no package (an orphan
    path-injection .pth). An unnamed entry can never be covered by a declaration — a declaration is
    keyed by name — so it is always a violation, and says so rather than being quietly dropped.
    """

    def __init__(self, package, version=None, source=None, site=None):
        self.package, self.version, self.source, self.site = package, version, source, site
        self.source_authoritative = False
        self.evidence = []          # [(kind, path)] — every independent reason we say "editable"

    def add(self, kind, path):
        if (kind, path) not in self.evidence:
            self.evidence.append((kind, path))

    def set_source(self, path, authoritative=False):
        """Record the source tree this install points at. AUTHORITATIVE wins over a guess.

        Not a detail: two pieces of evidence disagree about what "the source" is, and only one of
        them answers the question an operator is actually asking. PEP 610's direct_url.json records
        the PROJECT ROOT — the directory `pip install -e` was pointed at. A PEP 660 finder's MAPPING
        records the MODULE directory INSIDE it (`<root>/demo_mod`, not `<root>`). Both are true; the
        project root is the one you can act on. Without this precedence the answer would depend on
        os.listdir's ordering — `__editable__....pth` sorts before `demo_pkg-...dist-info` because
        `_` < `d` — which is not a basis for anything.
        """
        if not path:
            return
        if self.source is None or (authoritative and not self.source_authoritative):
            self.source, self.source_authoritative = path, authoritative

    @property
    def label(self):
        return "%s%s" % (self.package or "(unnamed)", " %s" % self.version if self.version else "")

    def as_dict(self):
        return {"package": self.package, "version": self.version, "source": self.source,
                "site_packages": self.site,
                "evidence": [{"kind": k, "path": p} for k, p in self.evidence]}

    def report(self, indent="   "):
        out = ["%s%s" % (indent, self.label)]
        if self.source:
            out.append("%s  source tree it points at: %s%s"
                       % (indent, self.source,
                          "" if os.path.exists(self.source) else "   <- WHICH NO LONGER EXISTS"))
        for k, p in self.evidence:
            out.append("%s  evidence: %s   [%s]" % (indent, k, p))
        return "\n".join(out)


# ── the scan: a pure filesystem read of a venv ────────────────────────────────────────────────────
K_DIRECT_URL = "PEP 610 direct_url.json says dir_info.editable=true (authoritative)"
K_PEP660_PTH = "PEP 660 __editable__ .pth (modern `pip install -e`)"
K_PEP660_FIND = "PEP 660 editable finder module"
K_EGG_LINK = "legacy .egg-link (`setup.py develop` / `pip install -e` before pip 21.3)"
K_EASY_PTH = "legacy easy-install.pth entry pointing outside site-packages"
K_PATH_PTH = "path-injection .pth: a source tree spliced onto sys.path"


def site_packages_dirs(venv):
    """Every site-packages/dist-packages directory under a venv. Accepts a site-packages directory
    directly too, so a CI shadow that has only that directory (and not a whole venv) can be scanned.

    Cross-platform by construction rather than by assumption: posix venvs use
    `lib/python3.X/site-packages`, Windows uses `Lib\\site-packages`, and some distros ship
    `dist-packages`. The walk finds whichever exists and never descends INTO one (a package may
    perfectly well vendor a directory named site-packages, and that is not a venv's).

    THE CASE-INSENSITIVE TRAP, which is why identity is by INODE and not by string. macOS and
    Windows filesystems are case-insensitive: `<venv>/lib` and `<venv>/Lib` are THE SAME DIRECTORY,
    opened under two spellings. Probing both (as the cross-platform tuple below must) therefore
    finds the same site-packages twice, and `set()` cannot tell — the two strings genuinely differ.
    Every editable install then gets reported TWICE: two violations for one defect, a doubled JSON
    report, and a `len(...) == 1` assertion that fails for a reason nobody would guess. Deduping on
    (st_dev, st_ino) asks the filesystem which directories are the same object, which is the only
    thing that actually knows — and it collapses symlinked venvs for free.
    """
    venv = os.path.abspath(venv)
    if os.path.basename(venv) in ("site-packages", "dist-packages") and os.path.isdir(venv):
        return [venv]
    out, seen = [], set()

    def remember(path):
        try:
            st = os.stat(path)
            key = (st.st_dev, st.st_ino)
        except OSError:                      # unstattable: fall back to a normalized string
            key = os.path.normcase(os.path.realpath(path))
        if key in seen:
            return
        seen.add(key)
        out.append(path)

    for lib in ("lib", "lib64", "Lib"):
        base = os.path.join(venv, lib)
        if not os.path.isdir(base):
            continue
        for root, dirs, _ in os.walk(base):
            if os.path.basename(root) in ("site-packages", "dist-packages"):
                remember(root)
                dirs[:] = []        # never descend into it
    return out


def _dist_name_version(dist_info):
    """(name, version) for a .dist-info directory. METADATA's `Name:` is authoritative when it is
    readable; the directory name is the fallback. Both are normalized by the caller.

    The directory name is `<escaped name>-<version>.dist-info`, and rsplit-on-the-last-dash is the
    right split because a normalized version never contains a dash (PEP 440 uses `+` for local
    versions) while an escaped name never contains one either (it becomes `_`).
    """
    stem = os.path.basename(dist_info)[: -len(".dist-info")]
    name, version = (stem.rsplit("-", 1) + [None])[:2] if "-" in stem else (stem, None)
    meta = os.path.join(dist_info, "METADATA")
    if os.path.isfile(meta):
        try:
            for line in open(meta, encoding="utf-8", errors="replace"):
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                    break
                if not line.strip():        # the header block ended; Name: is not coming
                    break
        except OSError:
            pass
    return name, version


def _pth_entries(path):
    """The PATH lines of a .pth file — never its code lines.

    site.py executes a .pth line that begins with `import` and otherwise treats it as a directory to
    put on sys.path. Real, compliant packages ship the `import` form (setuptools'
    `distutils-precedence.pth`, and PEP 660's own `__editable__....pth`), so a detector that flagged
    every .pth would flag half of every venv on earth. Only the path form is returned here, which is
    exactly the form that splices a source tree onto sys.path.
    """
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("import ") or s.startswith("import\t"):
            continue
        out.append(s)
    return out


def scan_site(site):
    """Every editable install in ONE site-packages directory. Filesystem only: no pip, no import, no
    running of the venv's interpreter — so this works on a broken venv, a foreign-platform venv, or
    a bare site-packages directory copied into CI.
    """
    found = {}      # canon name -> Editable

    def get(name, version=None, source=None, authoritative=False):
        key = canon(name)
        e = found.get(key)
        if e is None:
            e = found[key] = Editable(key, version, None, site)
        if version and not e.version:
            e.version = version
        e.set_source(source, authoritative)
        return e

    try:
        entries = sorted(os.listdir(site))
    except OSError:
        return []

    finders_claimed = set()

    for name in entries:
        full = os.path.join(site, name)

        # 1. PEP 610 direct_url.json — the authoritative record, and the only one that survives a
        #    non-pip installer. Note the guard: a PROPER local install has this file too, with
        #    dir_info == {}. Only `editable` truthy is an editable install.
        if name.endswith(".dist-info") and os.path.isdir(full):
            du = os.path.join(full, "direct_url.json")
            if os.path.isfile(du):
                try:
                    d = json.load(open(du))
                except (ValueError, OSError):
                    d = {}
                di = d.get("dir_info") if isinstance(d, dict) else None
                if isinstance(di, dict) and di.get("editable"):
                    n, v = _dist_name_version(full)
                    # authoritative=True: this url is the PROJECT ROOT, the thing an operator acts on.
                    get(n, v, _url_to_path(d.get("url")), authoritative=True).add(
                        K_DIRECT_URL, os.path.join(os.path.basename(full), "direct_url.json"))
            continue

        # 2. PEP 660 .pth — `__editable__.demo_pkg-0.1.0.pth`. Its CONTENT names the generated
        #    finder module, which is how the finder is attributed to this package exactly rather
        #    than by guessing at a mangled filename.
        if name.startswith("__editable__") and name.endswith(".pth"):
            stem = name[: -len(".pth")]
            stem = stem[len("__editable__"):].lstrip(".")
            n, v = (stem.rsplit("-", 1) + [None])[:2] if "-" in stem else (stem, None)
            e = get(n, v)
            e.add(K_PEP660_PTH, name)
            body = ""
            try:
                body = open(full, encoding="utf-8", errors="replace").read()
            except OSError:
                pass
            for m in re.finditer(r"__editable___[A-Za-z0-9_]+_finder", body):
                fmod = m.group(0)
                fpath = os.path.join(site, fmod + ".py")
                if os.path.isfile(fpath):
                    finders_claimed.add(fmod + ".py")
                    e.add(K_PEP660_FIND, fmod + ".py")
                    # NOT authoritative: a MAPPING points at the MODULE dir inside the project root.
                    e.set_source(_finder_source(fpath))
            # A PEP 660 .pth may also be the plain path form (setuptools' "compat" mode writes the
            # source directory straight into it) — that path IS the source tree.
            for entry in _pth_entries(full):
                if os.path.isdir(entry):
                    e.set_source(entry)
            continue

        # 3. legacy .egg-link — `setup.py develop`, and `pip install -e` before pip 21.3. Modern pip
        #    never writes one, and #215 names it explicitly, so it is detected on its own account.
        #    Its first line is the source tree.
        if name.endswith(".egg-link") and os.path.isfile(full):
            lines = _pth_entries(full)
            src = lines[0] if lines else None
            # authoritative=True: an .egg-link's first line IS the project root `develop` was run in.
            e = get(name[: -len(".egg-link")], None, src, authoritative=True)
            e.add(K_EGG_LINK, name)
            continue

        # 4. any other .pth whose lines are PATHS into a tree outside site-packages. This is what
        #    `setup.py develop` adds to easy-install.pth, and what a hand-rolled "just put my
        #    checkout on sys.path" hack looks like. A path INSIDE site-packages is ordinary
        #    (namespace packages and vendored dirs do it) and is not flagged.
        if name.endswith(".pth") and os.path.isfile(full):
            for entry in _pth_entries(full):
                cand = entry if os.path.isabs(entry) else os.path.join(site, entry)
                cand = os.path.realpath(cand)
                if not os.path.isdir(cand):
                    continue
                if cand == os.path.realpath(site) or cand.startswith(os.path.realpath(site) + os.sep):
                    continue
                kind = K_EASY_PTH if name == "easy-install.pth" else K_PATH_PTH
                e = get(_guess_pkg_for_path(cand), None, cand)
                e.add(kind, "%s -> %s" % (name, entry))

    # An editable finder module with no .pth claiming it: the .pth was deleted, or something wrote a
    # finder by hand. Either way the mapping is still there, so it is still evidence and must not be
    # dropped just because nothing pointed at it.
    for name in entries:
        if name.startswith("__editable___") and name.endswith("_finder.py") and name not in finders_claimed:
            full = os.path.join(site, name)
            get(_guess_pkg_for_path(_finder_source(full)) or name[: -len(".py")], None,
                _finder_source(full)).add(K_PEP660_FIND, name)

    return [found[k] for k in sorted(found)]


def _finder_source(path):
    """The source tree a PEP 660 finder module maps to: the first path in its MAPPING dict. Read as
    text and not imported — importing a venv's generated module into THIS interpreter would be a
    side effect, and a scan that executes what it audits is not a scan."""
    try:
        body = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    m = re.search(r"MAPPING\s*(?::[^=]*)?=\s*\{(.*?)\}", body, re.S)
    if not m:
        return None
    vals = re.findall(r"['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]+)['\"]", m.group(1))
    return vals[0][1] if vals else None


def _guess_pkg_for_path(path):
    """A best-effort package name for evidence that carries only a directory (a bare .pth entry).

    Deliberately WEAK, and its weakness is the safe direction: if this guesses wrong, the entry is
    simply not matched by a declaration and stays a VIOLATION. A wrong guess can only refuse too
    much, never waive too much, and a check that errs toward refusing is the one you want.
    """
    return canon(os.path.basename(path.rstrip("/\\"))) if path else ""


def scan_venv(venv):
    """Every editable install across every site-packages of a venv. READ-ONLY: this creates no file,
    runs no subprocess, and imports nothing from the venv."""
    if not os.path.isdir(venv):
        raise Unexpected("no such venv directory: %s. `check` audits a venv (or a site-packages "
                         "directory) that already exists; it never creates one." % venv)
    sites = site_packages_dirs(venv)
    if not sites:
        raise Unexpected("%s has no site-packages directory — it is not a venv (and not a "
                         "site-packages directory either). Point --venv at a venv made by `python3 "
                         "-m venv <dir>`, or at a site-packages directory itself." % venv)
    out = []
    for s in sites:
        out.extend(scan_site(s))
    return sites, out


# ── the dev-phase declaration ─────────────────────────────────────────────────────────────────────
class Phases:
    """The registry's `editable_installs.packages` map: who is in dev-phase, and until when.

    Fully defensive about types for the reason bug_report() is: every value here comes from
    registry.json, so it is whatever someone typed. A malformed declaration must never crash the
    check and must never silently WAIVE — it is reported as not-a-waiver, which keeps the failure on
    the refusing side.
    """

    def __init__(self, reg, today=None):
        self.today = today or datetime.date.today()
        sec = (reg or {}).get("editable_installs")
        sec = sec if isinstance(sec, dict) else {}
        pkgs = sec.get("packages")
        self.packages = {}
        if isinstance(pkgs, dict):
            for k, v in pkgs.items():
                if isinstance(v, dict):
                    self.packages[canon(k)] = v
        log = sec.get("audit_log")
        self.audit_log = log if isinstance(log, str) and log.strip() else AUDIT_DEFAULT

    def status(self, package):
        """(phase, declaration, why) for one package name.

        phase is "debug" only for a live, well-formed declaration; otherwise "done" — the default
        for every package that is not explicitly declared, which is what makes POLICY 2's default
        answer "no". `why` explains a rejected declaration so an operator whose waiver stopped
        working is told the reason instead of having to guess at it.
        """
        d = self.packages.get(canon(package))
        if not package:
            return "done", None, ("this evidence names no package, so no declaration can cover it "
                                  "(a declaration is keyed by package name)")
        if d is None:
            return "done", None, "no dev-phase declaration in registry.json"
        phase = d.get("phase")
        if phase != "debug":
            return "done", d, ("declared with phase=%r, and only phase='debug' waives POLICY 2"
                               % (phase,))
        exp = d.get("expires")
        if exp is not None:
            if not isinstance(exp, str):
                return "done", d, "declaration's `expires` is not a date string: %r" % (exp,)
            try:
                when = datetime.date.fromisoformat(exp.strip())
            except ValueError:
                return "done", d, ("declaration's `expires` is not an ISO date (YYYY-MM-DD): %r"
                                   % (exp,))
            if when < self.today:
                return "done", d, ("the dev-phase declaration EXPIRED on %s (today is %s) — "
                                   "sustained debugging is a phase, not a permanent condition"
                                   % (exp, self.today.isoformat()))
        if not str(d.get("reason") or "").strip():
            return "done", d, ("the declaration records no `reason`, so it is not auditable and "
                               "does not waive POLICY 2")
        return "debug", d, ""


def describe(decl):
    """A declaration in one line, for the operator who has to decide whether it is still true."""
    if not decl:
        return "(none)"
    bits = [str(decl.get("reason") or "(no reason)")]
    for k in ("declared_by", "ticket", "expires"):
        if decl.get(k) not in (None, ""):
            bits.append("%s=%s" % (k, decl[k]))
    return "; ".join(bits)


# ── the verdict ───────────────────────────────────────────────────────────────────────────────────
class Verdict:
    """What POLICY 2 says about one venv. `holds` is the whole invariant."""

    def __init__(self, venv, sites, editables, phases):
        self.venv, self.sites, self.phases = venv, sites, phases
        self.violations, self.waived = [], []
        for e in editables:
            phase, decl, why = phases.status(e.package)
            (self.waived if phase == "debug" else self.violations).append((e, decl, why))

    @property
    def holds(self):
        return not self.violations

    def as_dict(self):
        return {"policy2": "holds" if self.holds else "refused", "venv": self.venv,
                "site_packages": self.sites,
                "violations": [dict(e.as_dict(), why=w) for e, _, w in self.violations],
                "waived": [dict(e.as_dict(), declaration=d) for e, d, _ in self.waived]}

    def report(self, indent="   "):
        out = []
        if not self.violations and not self.waived:
            out.append("%sno editable installs — every package in this venv is installed PROPER."
                       % indent)
        for e, _, why in self.violations:
            out.append("%sVIOLATION — editable install of a DONE package:" % indent)
            out.append(e.report(indent + "  "))
            out.append("%s  why this is a violation: %s" % (indent, why))
        for e, d, _ in self.waived:
            out.append("%sWAIVED — %s is in a declared dev-phase (phase='debug'):" % (indent, e.label))
            out.append(e.report(indent + "  "))
            out.append("%s  declaration: %s" % (indent, describe(d)))
            out.append("%s  NOTE: this waiver permits the INSTALL. It does NOT permit shipping — "
                       "`ship` refuses this package until it is re-installed proper." % indent)
        return "\n".join(out)


# ── the audit log: what makes the escape hatch auditable ──────────────────────────────────────────
def audit_path(root, phases):
    return os.path.join(root, phases.audit_log)


def audit_write(root, phases, record):
    """Append ONE record to the append-only audit log.

    This one is NOT best-effort, and that is deliberate — it is the opposite of bug_report(). #215
    requires the escape hatch to be auditable, so a hatch whose record cannot be written is a hatch
    that must not open: this raises, and the caller refuses the editable install BEFORE pip runs.
    An unrecorded editable install is exactly what this file exists to prevent.
    """
    p = audit_path(root, phases)
    try:
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(p, "a") as fh:
            fh.write(json.dumps(record) + "\n")
        return p
    except OSError as e:
        raise Unexpected("the editable install is REFUSED because its audit record could not be "
                         "written to %s (%s). POLICY 2's escape hatch is only permitted while it is "
                         "auditable, so an unwritable log closes the hatch rather than opening it "
                         "silently." % (p, e))


def audit_read(root, phases):
    p = audit_path(root, phases)
    if not os.path.isfile(p):
        return p, []
    out = []
    for line in open(p, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            out.append({"unparseable": line[:200]})
    return p, out


# ── the installer ─────────────────────────────────────────────────────────────────────────────────
# The substring probe that separates "this host has no network" from "this package is broken",
# lifted from pair_loop.py:1009-1013 so the two tools agree on what a SKIP is.
NETWORK_MARKERS = ("no matching distribution found", "could not find a version", "backendunavailable",
                   "cannot import", "network is unreachable", "temporary failure in name resolution",
                   "connection", "retries exceeded", "proxy", "ssl")


class Installer:
    """Every install act POLICY 2 performs, against one venv.

    Scoped to a venv rather than reaching for a global so --selftest can drive a THROWAWAY venv
    through the identical code path a real one takes — the established pattern in this repo
    (pair_loop.py's Forge takes a root for the same reason; clean_recheckout.py's Recheckout takes a
    root for the same reason).
    """

    def __init__(self, venv):
        self.venv = os.path.abspath(venv)

    def python(self, create=True):
        """The venv's interpreter, creating the venv if it does not exist yet.

        A venv is the unit POLICY 2 talks about ("a venv contains .egg-link / editable entries"), and
        installing into the interpreter that is RUNNING this tool would be a side effect on the host
        no ticket asked for — on a homebrew/system python it is also refused outright as an
        externally-managed environment. So the venv is explicit and required.
        """
        for rel in (("bin", "python"), ("Scripts", "python.exe")):
            p = os.path.join(self.venv, *rel)
            if os.path.isfile(p):
                return p
        if not create:
            raise Unexpected("no python interpreter in %s — it is not a venv. Make one with "
                             "`python3 -m venv %s`." % (self.venv, self.venv))
        r = subprocess.run([sys.executable, "-m", "venv", self.venv], capture_output=True, text=True)
        if r.returncode != 0:
            raise Unexpected("could not create a venv at %s: %s"
                             % (self.venv, (r.stderr or r.stdout).strip()[-200:]))
        return self.python(create=False)

    def _pip(self, py, args, cwd=None, timeout=300):
        env = dict(os.environ, PIP_DISABLE_PIP_VERSION_CHECK="1")
        try:
            r = subprocess.run([py, "-m", "pip", *args], cwd=cwd, capture_output=True, text=True,
                               env=env, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, "pip did not finish in %ss (a slow or absent network)" % timeout
        return r, ((r.stderr or "") + (r.stdout or "")).strip()

    def install(self, pkg_dir, method="source", editable=False):
        """Install a package into the venv. PROPER unless `editable` is explicitly True.

        Returns ("PASS"|"FAIL"|"SKIP", detail), the same three-state contract pair_loop.py's
        install_check() uses (pair_loop.py:980-988), because an unreachable package index is a fact
        about the host and never a verdict on the package.

        method="source"  -> `pip install <pkg_dir>`      (#215's "pip install .")
        method="wheel"   -> `pip wheel` then install the built .whl   (#215's "a built wheel")

        The absolute pkg_dir is passed rather than "." with cwd=pkg_dir: the two are the same
        operation to pip, and the absolute form cannot be perturbed by the cwd the caller happens to
        be in — which matters here, because a cwd holding the source is exactly what makes a broken
        install look like a working one.
        """
        pkg_dir = os.path.abspath(pkg_dir)
        if not os.path.isdir(pkg_dir):
            raise Unexpected("no such package directory: %s" % pkg_dir)
        if not any(os.path.isfile(os.path.join(pkg_dir, f)) for f in ("pyproject.toml", "setup.py")):
            raise Unexpected("%s has neither pyproject.toml nor setup.py — there is no package here "
                             "to install." % pkg_dir)
        py = self.python()

        if editable:
            r, out = self._pip(py, ["install", "-e", pkg_dir, "-q"])
        elif method == "wheel":
            wd = tempfile.mkdtemp(prefix="policy2-wheel-")
            try:
                r, out = self._pip(py, ["wheel", pkg_dir, "--no-deps", "-w", wd, "-q"])
                if r is None:
                    return "SKIP", out
                if r.returncode != 0:
                    return self._verdict(r, out, "pip wheel")
                whls = [os.path.join(wd, f) for f in os.listdir(wd) if f.endswith(".whl")]
                if not whls:
                    return "FAIL", "pip wheel exited 0 but built no .whl in %s" % wd
                r, out = self._pip(py, ["install", *whls, "-q"])
            finally:
                shutil.rmtree(wd, ignore_errors=True)
        else:
            r, out = self._pip(py, ["install", pkg_dir, "-q"])

        if r is None:
            return "SKIP", out
        return self._verdict(r, out, "pip install -e" if editable else "pip install")

    def _verdict(self, r, out, what):
        if r.returncode != 0:
            # Distinguish "the package is broken" from "this host could not fetch a build backend".
            if any(s in out.lower() for s in NETWORK_MARKERS):
                return "SKIP", "pip could not obtain the build backend (no network?): %s" % out[-200:]
            return "FAIL", "%s exited %s: %s" % (what, r.returncode, out[-300:])
        return "PASS", "%s clean" % what

    # ── proving the install is what POLICY 2 asked for ────────────────────────
    def top_levels(self, package):
        """The importable top-level names a distribution installed, from its own dist-info.

        top_level.txt when setuptools wrote one; otherwise derived from RECORD, which every wheel
        install has. Entries starting with `..` (scripts installed into bin/) and the dist-info
        itself are not importable names and are skipped.
        """
        names = []
        for site in site_packages_dirs(self.venv):
            for e in sorted(os.listdir(site)):
                if not e.endswith(".dist-info"):
                    continue
                n, _ = _dist_name_version(os.path.join(site, e))
                if canon(n) != canon(package):
                    continue
                tl = os.path.join(site, e, "top_level.txt")
                if os.path.isfile(tl):
                    names += [l.strip() for l in open(tl) if l.strip()]
                    continue
                rec = os.path.join(site, e, "RECORD")
                if os.path.isfile(rec):
                    for line in open(rec, encoding="utf-8", errors="replace"):
                        rel = line.split(",")[0].strip()
                        if not rel or rel.startswith("..") or rel.startswith(e):
                            continue
                        head = rel.replace("\\", "/").split("/")[0]
                        if head.endswith(".py"):
                            head = head[:-3]
                        if head and not head.startswith("__") and head not in names:
                            names.append(head)
        return names

    def prove_proper(self, package, pkg_dir):
        """Prove a PROPER install really is decoupled from its source tree. Raises Unexpected if not.

        Three independent proofs, because "pip exited 0" proves only that pip exited 0:

          1. NO editable evidence for this package anywhere in the venv (the same scan `check` runs).
          2. Every top-level module IMPORTS from a NEUTRAL cwd — a temp directory that holds none of
             the source — so nothing can be satisfied by the current directory happening to contain
             the package. This is the trap pair_loop.py:1015-1017 names.
          3. Each imported module's __file__ resolves INSIDE site-packages and NOT inside pkg_dir.
             This is the decoupling itself, stated as a fact about where the bytes came from: an
             installed copy in site-packages cannot be affected by moving or deleting the source.

        Proof 3 is a STRUCTURAL proof and is honest about being one. It does not move your source
        tree to find out what happens — a tool that mutated the operator's checkout to make a point
        would be a side effect no ticket asked for. --selftest performs the DESTRUCTIVE version on a
        throwaway package (source moved away entirely, then imported), which is where #215's
        acceptance criterion is demonstrated for real.
        """
        _, eds = scan_venv(self.venv)
        bad = [e for e in eds if canon(e.package) == canon(package)]
        if bad:
            raise Unexpected("the install of %s left EDITABLE evidence in %s — it is not a proper "
                             "install:\n%s" % (package, self.venv,
                                               "\n".join(e.report() for e in bad)))
        tops = self.top_levels(package)
        if not tops:
            raise Unexpected("cannot prove the install of %s: no dist-info for it in %s, so it did "
                             "not install." % (package, self.venv))
        py = self.python(create=False)
        sites = [os.path.realpath(s) for s in site_packages_dirs(self.venv)]
        neutral = tempfile.mkdtemp(prefix="policy2-neutral-")
        try:
            proofs = []
            for t in tops:
                r = subprocess.run(
                    [py, "-c", "import importlib,sys; m=importlib.import_module(%r); "
                               "print(getattr(m,'__file__','') or '')" % t],
                    capture_output=True, text=True, cwd=neutral)
                if r.returncode != 0:
                    raise Unexpected("%s installed but `import %s` FAILS from a neutral directory: "
                                     "%s" % (package, t, (r.stderr or r.stdout).strip()[-250:]))
                f = os.path.realpath(r.stdout.strip())
                if not f:
                    continue        # a namespace package has no __file__; nothing to locate
                src = os.path.realpath(os.path.abspath(pkg_dir))
                if f == src or f.startswith(src + os.sep):
                    raise Unexpected("%s is NOT decoupled: `import %s` resolves to %s, which is "
                                     "INSIDE the source tree %s. That is what an editable install "
                                     "does, and POLICY 2 bans it." % (package, t, f, src))
                if not any(f == s or f.startswith(s + os.sep) for s in sites):
                    raise Unexpected("%s is NOT a site-packages install: `import %s` resolves to "
                                     "%s, which is outside %s." % (package, t, f, sites))
                proofs.append("%s -> %s" % (t, f))
            return proofs
        finally:
            shutil.rmtree(neutral, ignore_errors=True)


# ── the importable API (for the in-process wire; see THE LIVE VIOLATION in the docstring) ─────────
def guard_policy2(venv, reg=None, today=None):
    """CHECK-ONLY. Returns the Verdict. Raises Unexpected if any editable install sits outside a
    declared dev-phase. Read-only: it changes nothing, ever."""
    sites, eds = scan_venv(venv)
    v = Verdict(os.path.abspath(venv), sites, eds, Phases(REGISTRY if reg is None else reg, today))
    if not v.holds:
        raise Unexpected("POLICY 2 violated — %s contains an editable install outside a declared "
                         "dev-phase: %s" % (venv, ", ".join(e.label for e, _, _ in v.violations)))
    return v


def guard_ship(venv, package=None, reg=None, today=None):
    """THE SHIP GATE, as a function. Raises Unexpected if `package` (or ANY package, when none is
    named) is editable-installed in `venv` — a declared dev-phase does NOT waive this, per #215's
    "BLOCKED from being marked done/committed until re-installed proper". Read-only."""
    sites, eds = scan_venv(venv)
    hits = [e for e in eds if package is None or canon(e.package) == canon(package)]
    if hits:
        raise Unexpected("POLICY 2 violated — refusing to ship: %s is installed EDITABLE in %s. "
                         "Re-install it proper first (`ban_editable_installs.py install <pkg_dir> "
                         "--venv %s`); a dev-phase declaration permits the install but never the "
                         "ship." % (", ".join(e.label for e in hits), venv, venv))
    return Verdict(os.path.abspath(venv), sites, eds, Phases(REGISTRY if reg is None else reg, today))


def proper_install_check(base_dir, pkg_dir):
    """A drop-in replacement for pair_loop.py's install_check() (pair_loop.py:979-1027) that installs
    PROPER instead of `pip install -e .` (pair_loop.py:1001) — POLICY 2 applied to the repo's own
    install tooling, in one line at the call site. NOT yet wired in: see THE LIVE VIOLATION IN THIS
    REPO in the module docstring for why, and for the exact edit.

    Same contract as the function it replaces, deliberately:
      "PASS"  pip installed it AND the installed package imports and runs from the venv.
      "FAIL"  pip rejected the package, or it installed but could not be imported. A real defect.
      "SKIP"  the fixture could not be built: no venv, or pip could not obtain the PEP 517 build
              backend (which needs the network). A fact about this host, never about the package.

    Strictly stronger than the original for the reason the docstring gives: under `-e` the import
    proves only that the checkout still exists; installed proper, it proves the install.
    """
    venv = os.path.join(base_dir, "install-check-venv")
    inst = Installer(venv)
    try:
        inst.python()
    except Unexpected as e:
        return "SKIP", str(e)
    status, detail = inst.install(pkg_dir, method="source")
    if status != "PASS":
        return status, detail
    name = project_name(pkg_dir)
    if not name:
        return "FAIL", "installed, but %s declares no project name to verify" % pkg_dir
    try:
        proofs = inst.prove_proper(name, pkg_dir)
    except Unexpected as e:
        return "FAIL", str(e)
    return "PASS", ("pip install (PROPER, not -e) clean; imports from a neutral cwd out of "
                    "site-packages: %s" % "; ".join(proofs))


def project_name(pkg_dir):
    """The project's declared name, read from pyproject.toml (or setup.py's name=) WITHOUT importing
    or executing anything in it.

    A regex and not a TOML parse on purpose: tomllib exists only on python 3.11+, this repo's tools
    are plain-stdlib, and the one field needed is `name = "..."` under [project]. If the regex misses,
    the caller says so out loud rather than guessing a name — see the FAIL arm in
    proper_install_check() and the explicit --package flag on `install`.
    """
    py = os.path.join(pkg_dir, "pyproject.toml")
    if os.path.isfile(py):
        body = open(py, encoding="utf-8", errors="replace").read()
        m = re.search(r"^\s*\[project\]\s*$(.*?)(^\s*\[|\Z)", body, re.S | re.M)
        block = m.group(1) if m else body
        m = re.search(r"""^\s*name\s*=\s*['"]([^'"]+)['"]""", block, re.M)
        if m:
            return m.group(1)
    sp = os.path.join(pkg_dir, "setup.py")
    if os.path.isfile(sp):
        m = re.search(r"""name\s*=\s*['"]([^'"]+)['"]""",
                      open(sp, encoding="utf-8", errors="replace").read())
        if m:
            return m.group(1)
    return None


# ── the CLI ───────────────────────────────────────────────────────────────────────────────────────
def do_install(a, root, reg):
    phases = Phases(reg)
    inst = Installer(a.venv)
    name = a.package or project_name(a.pkg_dir)
    if not name:
        raise Unexpected("cannot determine the project name of %s (no `name = \"...\"` under "
                         "[project] in pyproject.toml, and no name= in setup.py). Pass --package "
                         "<name> to say what it is." % a.pkg_dir)

    if not a.dev_debug:
        status, detail = inst.install(a.pkg_dir, method=a.method)
        if status == "SKIP":
            print("== policy 2 == install SKIPPED — %s" % detail)
            print("   (an unreachable package index is a fact about this host, not about the "
                  "package; nothing was installed and nothing is claimed.)")
            if a.json:
                print(json.dumps({"policy2": "not-evaluated", "action": "install",
                                  "status": "SKIP", "package": canon(name), "detail": detail},
                                 indent=2))
            return 0
        if status == "FAIL":
            raise Unexpected("the PROPER install of %s failed: %s" % (name, detail))
        proofs = inst.prove_proper(name, a.pkg_dir)
        print("== policy 2 == %s installed PROPER into %s (%s)" % (name, a.venv, a.method))
        print("   proven decoupled from the source tree %s:" % os.path.abspath(a.pkg_dir))
        print("   - no editable evidence anywhere in the venv (the same scan `check` runs)")
        for p in proofs:
            print("   - imports from a NEUTRAL cwd, out of site-packages: %s" % p)
        print("   moving or deleting %s cannot break this install: the bytes are a copy in "
              "site-packages." % os.path.abspath(a.pkg_dir))
        if a.json:
            print(json.dumps({"policy2": "holds", "action": "install", "status": "PASS",
                              "package": canon(name), "editable": False, "method": a.method,
                              "venv": os.path.abspath(a.venv),
                              "source": os.path.abspath(a.pkg_dir), "decoupled": True,
                              "proofs": proofs}, indent=2))
        return 0

    # ── the escape hatch ──
    phase, decl, why = phases.status(name)
    record = {"time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": "requested",
              "package": canon(name), "source": os.path.abspath(a.pkg_dir),
              "venv": os.path.abspath(a.venv), "reason": a.reason,
              "operator": os.environ.get("USER") or os.environ.get("USERNAME") or "(unknown)",
              "declared_in_registry": bool(decl), "registry_phase": (decl or {}).get("phase"),
              "argv": " ".join(sys.argv[1:]), "note": "POLICY 2 dev-phase editable install (#215)"}
    log = audit_write(root, phases, record)      # BEFORE pip: an unrecordable hatch does not open

    status, detail = inst.install(a.pkg_dir, method=a.method, editable=True)
    audit_write(root, phases, dict(record, event="installed" if status == "PASS" else status.lower(),
                                   detail=detail,
                                   **{"time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S")}))
    if status == "SKIP":
        print("== policy 2 == editable install SKIPPED — %s" % detail)
        if a.json:
            print(json.dumps({"policy2": "not-evaluated", "action": "install", "status": "SKIP",
                              "package": canon(name), "editable": True, "detail": detail}, indent=2))
        return 0
    if status == "FAIL":
        raise Unexpected("the dev-phase editable install of %s failed: %s" % (name, detail))

    print("== policy 2 == %s installed EDITABLE under the dev-phase escape hatch." % name)
    print("   reason: %s" % a.reason)
    print("   audited -> %s (append-only; read it with `%s audit`)"
          % (log, os.path.basename(__file__)))
    print("   THIS PACKAGE CANNOT BE SHIPPED. `ship --venv %s --package %s` will REFUSE until it is "
          "re-installed proper:" % (a.venv, canon(name)))
    print("     python3 %s install %s --venv %s" % (os.path.basename(__file__), a.pkg_dir, a.venv))
    if phase != "debug":
        print("   !! WARNING — registry.json does NOT declare %s as phase='debug' (%s)."
              % (canon(name), why))
        print("      --dev-debug permitted THIS install, but `check` is a separate process that "
              "cannot know what flags you typed; it will REFUSE this venv until the declaration "
              "exists. Add it under \"editable_installs\": {\"packages\": {\"%s\": {\"phase\": "
              "\"debug\", \"reason\": \"...\"}}} — see THE DEV-PHASE DECLARATION." % canon(name))
    if a.json:
        print(json.dumps({"policy2": "waived" if phase == "debug" else "undeclared",
                          "action": "install", "status": "PASS", "package": canon(name),
                          "editable": True, "dev_phase": phase, "reason": a.reason,
                          "declared_in_registry": bool(decl), "audit_log": log,
                          "shippable": False,
                          "check_will_refuse": phase != "debug"}, indent=2))
    return 0


def do_check(a, root, reg):
    sites, eds = scan_venv(a.venv)
    v = Verdict(os.path.abspath(a.venv), sites, eds, Phases(reg))
    print("== policy 2 == %s — %s" % ("HOLDS" if v.holds else "REFUSED", a.venv))
    print(v.report())
    if a.json:
        print(json.dumps(v.as_dict(), indent=2))
    if not v.holds:
        print("   Fix either way: re-install the package PROPER —\n"
              "     python3 %s install <pkg_dir> --venv %s\n"
              "   or, if it is genuinely under sustained debugging, declare the dev-phase in "
              "registry.json (see THE DEV-PHASE DECLARATION in this tool's docstring). A declared "
              "package still cannot be shipped." % (os.path.basename(__file__), a.venv))
        return 3
    return 0


def do_ship(a, root, reg, cmd):
    sites, eds = scan_venv(a.venv)
    v = Verdict(os.path.abspath(a.venv), sites, eds, Phases(reg))
    hits = [e for e in eds if a.package is None or canon(e.package) == canon(a.package)]
    if hits:
        print("== policy 2 == SHIP REFUSED — an editable-installed package may not be marked "
              "done/committed.")
        for e in hits:
            print(e.report())
            phase, decl, _ = v.phases.status(e.package)
            if phase == "debug":
                print("   it IS in a declared dev-phase (%s) — and that permits the install, never "
                      "the ship (#215: 'BLOCKED from being marked done/committed until re-installed "
                      "proper')." % describe(decl))
        print("   re-install it proper, then ship:")
        print("     python3 %s install <pkg_dir> --venv %s" % (os.path.basename(__file__), a.venv))
        if cmd:
            print("   the ship command was NOT run: %s" % " ".join(cmd))
        if a.json:
            print(json.dumps({"policy2": "refused", "action": "ship", "shipped": False,
                              "venv": os.path.abspath(a.venv), "package": a.package,
                              "command_run": False, "command": cmd,
                              "editable": [e.as_dict() for e in hits]}, indent=2))
        return 3
    print("== policy 2 == ship PERMITTED — %s is installed PROPER in %s."
          % (a.package or "every package", a.venv))
    if not cmd:
        if a.json:
            print(json.dumps({"policy2": "holds", "action": "ship", "shipped": True,
                              "venv": os.path.abspath(a.venv), "package": a.package,
                              "command_run": False, "command": []}, indent=2))
        return 0
    print("== ship == %s" % " ".join(cmd))
    try:
        r = subprocess.run(cmd)
    except FileNotFoundError as e:
        raise Unexpected("cannot run the wrapped ship command %r: %s" % (cmd[0], e))
    print("== ship == exit %s" % r.returncode)
    if a.json:
        print(json.dumps({"policy2": "holds", "action": "ship", "shipped": r.returncode == 0,
                          "venv": os.path.abspath(a.venv), "package": a.package,
                          "command_run": True, "command": cmd,
                          "command_exit": r.returncode}, indent=2))
    return r.returncode


def do_audit(a, root, reg):
    phases = Phases(reg)
    p, recs = audit_read(root, phases)
    if not recs:
        print("== policy 2 == the editable-install audit log is empty: %s" % p)
        print("   (none) — no editable install has ever been performed through this tool here.")
        return 0
    print("== policy 2 == %d audit record(s) — %s" % (len(recs), p))
    for r in recs:
        if "unparseable" in r:
            print("   ?? unparseable line: %s" % r["unparseable"])
            continue
        print("   %s  %-9s %-24s %s" % (r.get("time-of-occurance", "?"), r.get("event", "?"),
                                        r.get("package", "?"), r.get("reason", "")))
        print("      by %s   source %s   venv %s%s"
              % (r.get("operator", "?"), r.get("source", "?"), r.get("venv", "?"),
                 "" if r.get("declared_in_registry") else "   [NOT declared in registry.json]"))
    if a.json:
        print(json.dumps(recs, indent=2))
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    # The ship command is everything after the FIRST `--`, split off BEFORE argparse sees it, so the
    # command may carry any flags it likes (including ones this tool also defines) without argparse
    # claiming them. `ship --venv v -- git commit -m "--venv"` must pass those to git, not eat them.
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = []
    if "--" in argv:
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]

    ap = argparse.ArgumentParser(
        prog="ban_editable_installs.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="POLICY 2 (ticket #215): install PROPER, never EDITABLE. Editable is permitted "
                    "only under an explicit, audited dev-phase, and never ships.",
        epilog="Exit: 0 policy holds; 2 unexpected (bug report filed) or a usage refusal; 3 REFUSED "
               "(an editable install outside a declared dev-phase, or an attempt to ship one). A "
               "wrapped ship command that fails propagates ITS OWN exit code verbatim.\n"
               "  python3 ban_editable_installs.py install ./pkg --venv .venv\n"
               "  python3 ban_editable_installs.py check --venv .venv\n"
               "  python3 ban_editable_installs.py ship --venv .venv -- git commit -m 'release'\n"
               "  python3 ban_editable_installs.py --selftest")
    ap.add_argument("--selftest", action="store_true",
                    help="prove this tool end-to-end in THROWAWAY venvs, then exit. Touches no db "
                         "and not this repo; the detector half needs no network, the end-to-end half "
                         "SKIPs without one")
    ap.add_argument("--root", default=None, metavar="DIR",
                    help="the repo whose registry.json declares the dev-phases and holds the audit "
                         "log (default: this tool's own registry root)")
    ap.add_argument("--json", action="store_true", help="print the result as JSON on stdout")

    # --root/--json are accepted on BOTH sides of the subcommand, because both readings are natural
    # and one of them silently failing is a finding, not a nitpick: `check --venv v --json` is what
    # this file's own USAGE block prints, while `--root X check` is what a wrapper writes. A parent
    # flag alone rejects the first form ("unrecognized arguments: --json"); redeclaring it on the
    # subparser with the ordinary default would reset the parent's value back to False whenever the
    # flag appeared BEFORE the subcommand. SUPPRESS is what makes them compose: the subparser sets
    # the attribute only when the flag is actually present after the subcommand, so whichever side
    # carries it wins and neither side clobbers the other.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS, metavar="DIR",
                        help=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="print the result as JSON on stdout")
    sub = ap.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser("install", parents=[common],
                       help="install a package into a venv — PROPER by default")
    p.add_argument("pkg_dir", metavar="PKG_DIR", help="the package's source directory")
    p.add_argument("--venv", required=True, metavar="DIR", help="the venv to install into (created "
                                                                "if it does not exist)")
    p.add_argument("--method", choices=("source", "wheel"), default="source",
                   help="source: `pip install <pkg_dir>` (default). wheel: BUILD a wheel and install "
                        "that. #215 names both as proper")
    p.add_argument("--package", default=None, metavar="NAME",
                   help="the project name, if pyproject.toml/setup.py does not state it plainly")
    p.add_argument("--dev-debug", action="store_true",
                   help="THE ESCAPE HATCH: install EDITABLE for sustained debugging. Requires "
                        "--reason, is written to the append-only audit log, and BLOCKS the package "
                        "from being shipped until it is re-installed proper")
    p.add_argument("--reason", default=None, metavar="TEXT",
                   help="why this package needs an editable install (mandatory with --dev-debug: an "
                        "escape hatch with no recorded reason is not auditable)")

    p = sub.add_parser("check", parents=[common],
                       help="THE CI SHADOW: fail if a venv holds an editable install "
                            "outside a declared dev-phase (read-only)")
    p.add_argument("--venv", required=True, metavar="DIR",
                   help="the venv (or a site-packages directory) to audit")

    p = sub.add_parser("ship", parents=[common],
                       help="THE SHIP GATE: refuse to mark done/commit an editable-installed "
                            "package; optionally wrap the ship command")
    p.add_argument("--venv", required=True, metavar="DIR", help="the venv the package is installed in")
    p.add_argument("--package", default=None, metavar="NAME",
                   help="the package being shipped (default: refuse if ANY package is editable)")

    sub.add_parser("audit", parents=[common],
                   help="print the append-only record of every dev-phase editable install")

    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()
    if not a.command:
        ap.error("a command is required: install, check, ship or audit (or --selftest). "
                 "See --help.")
    # A usage refusal, not a fault: no bug report, no traceback (argparse's own convention, exit 2).
    if a.command == "install" and a.dev_debug and not (a.reason or "").strip():
        ap.error("--dev-debug requires --reason \"<why this package needs an editable install>\". "
                 "#215 asks for an escape hatch that is AUDITABLE, and a reason nobody wrote down "
                 "is not an audit trail.")
    if a.command == "install" and a.reason and not a.dev_debug:
        ap.error("--reason is meaningful only with --dev-debug. The default install path is PROPER "
                 "and needs no excuse.")
    if cmd and a.command != "ship":
        ap.error("`-- <command>` is only meaningful for `ship`, which runs it if and only if the "
                 "gate passes.")

    # ROOT/REGISTRY came from the import-time gate. --root re-points the CONFIG and the audit log at
    # another repo; the Variant-A bug sink follows it, so a tool aimed elsewhere files its reports
    # there rather than into this repo, and falls back to this repo's registry when that one has none.
    root = os.path.abspath(a.root) if a.root else ROOT
    try:
        root, reg = find_registry(root)
    except RuntimeError:
        root, reg = ROOT, REGISTRY
    repro = "python3 %s %s" % (os.path.basename(__file__), " ".join(sys.argv[1:]))
    try:
        if a.command == "install":
            return do_install(a, root, reg)
        if a.command == "check":
            return do_check(a, root, reg)
        if a.command == "ship":
            return do_ship(a, root, reg, cmd)
        if a.command == "audit":
            return do_audit(a, root, reg)
        raise Unexpected("unreachable: unknown command %r" % a.command)
    except Exception as e:  # noqa: BLE001 — every unexpected outcome files a Variant-A bug report
        p = bug_report(root, reg, "main", e, repro)
        name = "" if isinstance(e, Unexpected) else "%s: " % type(e).__name__
        print("UNEXPECTED: %s%s%s" % (name, e, ("\n   bug report -> %s" % p) if p else ""),
              file=sys.stderr)
        return 2


# ── --selftest: prove every claim, in throwaway venvs (no db, no repo writes) ─────────────────────
DEMO_PYPROJECT = """[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "%(name)s"
version = "0.1.0"

[tool.setuptools]
packages = ["%(mod)s"]
"""


def _demo_pkg(base, name="demo-pkg", mod="demo_mod"):
    """A minimal but REAL installable package: a pyproject with a build backend and one module."""
    d = os.path.join(base, "src-" + mod)
    os.makedirs(os.path.join(d, mod), exist_ok=True)
    open(os.path.join(d, "pyproject.toml"), "w").write(DEMO_PYPROJECT % {"name": name, "mod": mod})
    open(os.path.join(d, mod, "__init__.py"), "w").write(
        "VALUE = 215\n\n\ndef hi():\n    return 'hi-from-%s'\n" % mod)
    return d


def _fixture_site(base, kind, name="fixture-pkg", version="0.1.0"):
    """A site-packages directory carrying ONE hand-built form of editable evidence.

    Hand-built on purpose, and this is the point of the hermetic half: modern pip CANNOT produce a
    .egg-link at all, so the only way to prove the legacy detector works is to write the legacy
    artifact. The same trick makes every detector check network-free and instant.
    """
    root = os.path.join(base, "fixture-" + kind)
    site = os.path.join(root, "lib", "python3.14", "site-packages")
    os.makedirs(site, exist_ok=True)
    os.makedirs(os.path.join(root, "bin"), exist_ok=True)
    src = os.path.join(base, "checkout-" + kind)
    os.makedirs(src, exist_ok=True)
    esc = name.replace("-", "_")
    di = os.path.join(site, "%s-%s.dist-info" % (esc, version))

    def dist_info(direct_url):
        os.makedirs(di, exist_ok=True)
        open(os.path.join(di, "METADATA"), "w").write(
            "Metadata-Version: 2.1\nName: %s\nVersion: %s\n\nbody\n" % (name, version))
        open(os.path.join(di, "top_level.txt"), "w").write("%s\n" % esc)
        if direct_url is not None:
            open(os.path.join(di, "direct_url.json"), "w").write(json.dumps(direct_url))

    if kind == "direct-url-editable":
        dist_info({"dir_info": {"editable": True}, "url": "file://" + src})
    elif kind == "proper":
        # The FALSE-POSITIVE trap: a proper local install also has direct_url.json with a file:// url.
        dist_info({"dir_info": {}, "url": "file://" + src})
        os.makedirs(os.path.join(site, esc), exist_ok=True)
        open(os.path.join(site, esc, "__init__.py"), "w").write("x = 1\n")
    elif kind == "pep660":
        dist_info(None)
        fmod = "__editable___%s_%s_finder" % (esc, version.replace(".", "_"))
        open(os.path.join(site, "__editable__.%s-%s.pth" % (esc, version)), "w").write(
            "import %s; %s.install()" % (fmod, fmod))
        open(os.path.join(site, fmod + ".py"), "w").write(
            "MAPPING: dict[str, str] = {'%s': '%s/%s'}\n" % (esc, src, esc))
    elif kind == "egg-link":
        open(os.path.join(site, "%s.egg-link" % name), "w").write("%s\n." % src)
    elif kind == "easy-install":
        open(os.path.join(site, "easy-install.pth"), "w").write("%s\n" % src)
    elif kind == "innocent-pth":
        # Everything a REAL venv has that a naive detector would flag. None of it is editable.
        open(os.path.join(site, "distutils-precedence.pth"), "w").write(
            "import os; var = 'SETUPTOOLS_USE_DISTUTILS'\n")
        os.makedirs(os.path.join(site, "vendored"), exist_ok=True)
        open(os.path.join(site, "inside.pth"), "w").write("vendored\n")   # relative, INSIDE the site
        open(os.path.join(site, "comment.pth"), "w").write("# just a comment\n\n")
        dist_info({"dir_info": {}, "url": "https://pypi.org/simple/x"})
    return root, site, src


def selftest():
    base = tempfile.mkdtemp(prefix="policy2-selftest-")
    me = os.path.abspath(__file__)
    checks = []

    def ck(what, ok, detail=""):
        checks.append((what, bool(ok)))
        print("   %s %s%s" % ("ok  " if ok else "FAIL", what,
                              "" if ok else ("\n        -> %s" % detail)))

    def cli(*args, **kw):
        """Run the REAL CLI as a subprocess, aimed at a throwaway --root, so its exit codes and its
        printed text are what is checked — not an internal call that could disagree with them."""
        r = subprocess.run([sys.executable, me, "--root", kw.get("root", base), *args],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    try:
        print("== selftest == POLICY 2 (ban editable installs) — ticket #215")
        # Its own registry.json, so every audit record and every Variant-A bug report this selftest
        # provokes lands in the THROWAWAY tree and never in this repo's logs/.
        open(os.path.join(base, "registry.json"), "w").write(json.dumps({
            "schema": 1, "bug_reports": "logs/bug_reports.jsonl",
            "editable_installs": {"audit_log": "logs/editable_installs.jsonl", "packages": {}},
        }))

        # ── names ──
        print("-- PEP 503 name normalization (the silent-pass trap)")
        ck("demo_pkg, demo-pkg and Demo.Pkg are ONE name",
           canon("demo_pkg") == canon("demo-pkg") == canon("Demo.Pkg") == "demo-pkg")

        # ── the detector, hermetically: every form of evidence #215 names ──
        print("-- the detector: every editable form, and every innocent look-alike")
        _, site, src = _fixture_site(base, "direct-url-editable")
        eds = scan_site(site)
        ck("PEP 610 direct_url.json dir_info.editable=true is DETECTED", len(eds) == 1, str(eds))
        ck("...as the right package, from METADATA's Name (not the escaped dir name)",
           eds and eds[0].package == "fixture-pkg", eds and eds[0].package)
        ck("...naming the source tree it points at", eds and eds[0].source == src,
           eds and eds[0].source)
        ck("...and saying WHY (the evidence is quoted, not asserted)",
           eds and any(K_DIRECT_URL == k for k, _ in eds[0].evidence), eds and str(eds[0].evidence))

        _, site_p, _ = _fixture_site(base, "proper")
        ck("a PROPER local install is NOT flagged, though it HAS a direct_url.json with a file:// "
           "url (the false-positive trap that makes dir_info.editable load-bearing)",
           scan_site(site_p) == [], str(scan_site(site_p)))

        _, site660, src660 = _fixture_site(base, "pep660")
        eds = scan_site(site660)
        ck("a PEP 660 __editable__ .pth is DETECTED (what modern pip actually writes)",
           len(eds) == 1 and eds[0].package == "fixture-pkg", str(eds))
        ck("...and its generated finder module is attributed to it via the .pth's own import line",
           eds and any(k == K_PEP660_FIND for k, _ in eds[0].evidence), eds and str(eds[0].evidence))
        ck("...and the source tree is read out of the finder's MAPPING without importing it",
           eds and eds[0].source == os.path.join(src660, "fixture_pkg"), eds and eds[0].source)

        _, site_egg, src_egg = _fixture_site(base, "egg-link")
        eds = scan_site(site_egg)
        ck("a legacy .egg-link is DETECTED (#215 names it; modern pip cannot even produce one)",
           len(eds) == 1 and eds[0].package == "fixture-pkg", str(eds))
        ck("...naming its source tree (the .egg-link's first line)", eds and eds[0].source == src_egg,
           eds and eds[0].source)

        _, site_easy, src_easy = _fixture_site(base, "easy-install")
        eds = scan_site(site_easy)
        ck("a legacy easy-install.pth pointing at a checkout is DETECTED", len(eds) == 1, str(eds))
        ck("...and is labelled as the legacy form it is",
           eds and any(k == K_EASY_PTH for k, _ in eds[0].evidence), eds and str(eds[0].evidence))

        _, site_ok, _ = _fixture_site(base, "innocent-pth")
        eds = scan_site(site_ok)
        ck("an ordinary venv is CLEAN: an `import`-form .pth (distutils-precedence.pth), a .pth "
           "pointing INSIDE site-packages, a comment-only .pth and an index-installed package are "
           "NONE of them editable", eds == [], str([e.as_dict() for e in eds]))

        # ── site-packages discovery: the case-insensitive trap ──
        # This is a REGRESSION check for a real defect this selftest caught: probing both `lib` and
        # `Lib` on a case-insensitive filesystem (macOS, Windows) finds ONE directory under TWO
        # spellings, and every editable install gets reported twice. Identity must come from the
        # filesystem (st_dev, st_ino), never from the string.
        print("-- site-packages discovery: one directory is found ONCE, however it is spelled")
        vv = os.path.join(base, "casefold-venv")
        os.makedirs(os.path.join(vv, "lib", "python3.14", "site-packages"), exist_ok=True)
        ck("a venv's site-packages is discovered exactly once (on a case-insensitive FS this fails "
           "if `lib` and `Lib` are deduped by string)", len(site_packages_dirs(vv)) == 1,
           str(site_packages_dirs(vv)))
        try:                    # on a case-INsensitive FS `Lib` already exists; that IS the trap
            os.symlink(os.path.join(vv, "lib"), os.path.join(vv, "Lib"))
            aliased = True
        except OSError:
            aliased = False
        if aliased:             # a case-sensitive FS: the symlink recreates the same trap portably
            ck("...and still exactly once when `Lib` is an ALIAS of `lib` (identity is by inode)",
               len(site_packages_dirs(vv)) == 1, str(site_packages_dirs(vv)))
        ck("a bare site-packages directory is accepted as itself",
           site_packages_dirs(site) == [site], str(site_packages_dirs(site)))

        # ── the declaration ──
        print("-- the dev-phase declaration: the default is DONE, and the hatch expires")
        ed = Editable("demo-pkg", "0.1.0", "/tmp/src", "/tmp/site")
        ed.add(K_DIRECT_URL, "x")
        undeclared = Verdict("v", [], [ed], Phases({}))
        ck("an UNDECLARED package is DONE, so its editable install is a VIOLATION",
           not undeclared.holds and len(undeclared.violations) == 1)
        reg_dbg = {"editable_installs": {"packages": {"demo_pkg": {"phase": "debug",
                                                                   "reason": "heisenbug"}}}}
        v = Verdict("v", [], [ed], Phases(reg_dbg))
        ck("a phase='debug' declaration WAIVES it — and matches across the _/- spelling gap",
           v.holds and len(v.waived) == 1)
        v = Verdict("v", [], [ed], Phases({"editable_installs": {"packages": {
            "demo-pkg": {"phase": "done", "reason": "r"}}}}))
        ck("phase='done' does NOT waive (only 'debug' does)", not v.holds)
        v = Verdict("v", [], [ed], Phases({"editable_installs": {"packages": {
            "demo-pkg": {"phase": "debug"}}}}))
        ck("a declaration with NO reason does not waive (an unauditable hatch is no hatch)",
           not v.holds)
        exp = {"editable_installs": {"packages": {"demo-pkg": {
            "phase": "debug", "reason": "r", "expires": "2020-01-01"}}}}
        v = Verdict("v", [], [ed], Phases(exp))
        ck("an EXPIRED declaration does not waive", not v.holds)
        ck("...and says so in words the operator can act on",
           "EXPIRED" in v.violations[0][2], v.violations[0][2])
        live = {"editable_installs": {"packages": {"demo-pkg": {
            "phase": "debug", "reason": "r", "expires": "2999-01-01"}}}}
        ck("...while an unexpired one still waives", Verdict("v", [], [ed], Phases(live)).holds)
        v = Verdict("v", [], [ed], Phases({"editable_installs": "not-a-dict"}))
        ck("a MALFORMED registry section does not crash, and does not waive", not v.holds)
        v = Verdict("v", [], [ed], Phases({"editable_installs": {"packages": {"demo-pkg": "nope"}}}))
        ck("a malformed DECLARATION does not crash, and does not waive", not v.holds)
        ck("this repo's real registry.json declares NO dev-phase packages (the resting state the "
           "docstring claims)", Phases(REGISTRY).packages == {})

        # ── check: exit codes, and READ-ONLY ──
        print("-- check: the CI shadow's exit codes, and that it writes NOTHING")
        code, out = cli("check", "--venv", site_p)
        ck("check on a proper venv exits 0 and says HOLDS", code == 0 and "HOLDS" in out, out[-200:])
        code, out = cli("check", "--venv", os.path.dirname(os.path.dirname(os.path.dirname(site660))))
        ck("check on an editable venv exits 3 and says REFUSED", code == 3 and "REFUSED" in out,
           "exit %s: %s" % (code, out[-300:]))
        ck("...and NAMES the package and the evidence rather than just 'dirty'",
           "fixture-pkg" in out and "PEP 660" in out, out[-400:])
        ck("...and tells the operator how to fix it", "install <pkg_dir>" in out, out[-300:])

        def snap(d):
            acc = {}
            for r, dirs, files in os.walk(d):
                for f in files:
                    p = os.path.join(r, f)
                    try:
                        acc[os.path.relpath(p, d)] = os.path.getmtime(p)
                    except OSError:
                        pass
            return acc

        venv660 = os.path.dirname(os.path.dirname(os.path.dirname(site660)))
        before = snap(venv660)
        cli("check", "--venv", venv660)
        cli("check", "--venv", venv660, "--json")
        ck("check created and touched NOTHING in the venv it audited (proven before/after)",
           snap(venv660) == before, str(set(snap(venv660)) ^ set(before)))
        ck("...and created no audit log (it is not an install)",
           not os.path.isfile(os.path.join(base, "logs", "editable_installs.jsonl")))
        code, out = cli("check", "--venv", site660, "--json")
        ck("check accepts a bare site-packages directory (a CI shadow may have only that)",
           code == 3 and '"policy2": "refused"' in out, out[-200:])

        # ── ship ──
        print("-- ship: the gate that a dev-phase declaration does NOT open")
        marker = os.path.join(base, "SHIPPED")
        ship_cmd = [sys.executable, "-c", "open(%r,'w').write('x')" % marker]
        code, out = cli("ship", "--venv", venv660, "--package", "fixture-pkg", "--", *ship_cmd)
        ck("ship REFUSES an editable-installed package (exit 3)", code == 3 and "SHIP REFUSED" in out,
           "exit %s: %s" % (code, out[-300:]))
        ck("...and does NOT run the ship command", not os.path.exists(marker), out[-200:])
        ck("...and says the command was not run", "was NOT run" in out, out[-300:])
        code, out = cli("ship", "--venv", venv660, "--package", "fixture-pkg", "--json")
        ck("ship --json emits a machine-readable refusal (the flag is HONOURED, not silently "
           "ignored)", code == 3 and '"policy2": "refused"' in out and '"command_run": false' in out,
           out[-300:])

        dbg_root = os.path.join(base, "declared")
        os.makedirs(dbg_root, exist_ok=True)
        open(os.path.join(dbg_root, "registry.json"), "w").write(json.dumps({
            "schema": 1, "editable_installs": {"packages": {
                "fixture-pkg": {"phase": "debug", "reason": "sustained debugging", "ticket": 215}}}}))
        code, out = cli("check", "--venv", venv660, root=dbg_root)
        ck("with the dev-phase DECLARED, check exits 0 and reports the waiver",
           code == 0 and "WAIVED" in out and "HOLDS" in out, "exit %s: %s" % (code, out[-300:]))
        # cli() always passes `--root base` BEFORE the subcommand, so this passes --root TWICE and
        # proves the argparse composition: the flag is accepted on either side, and the one after
        # the subcommand wins. Both readings are documented, so both must work.
        code, out = cli("check", "--venv", venv660, "--root", dbg_root)
        ck("--root is accepted AFTER the subcommand too, and wins over one given before it",
           code == 0 and "WAIVED" in out, "exit %s: %s" % (code, out[-300:]))
        ck("...and says out loud that the waiver does not permit shipping",
           "does NOT permit shipping" in out, out[-300:])
        code, out = cli("ship", "--venv", venv660, "--package", "fixture-pkg", root=dbg_root)
        ck("...but ship STILL refuses it (#215: blocked from done/committed until re-installed "
           "proper)", code == 3, "exit %s: %s" % (code, out[-300:]))
        ck("...and explains that the dev-phase permits the install, never the ship",
           "never" in out and "ship" in out.lower(), out[-300:])

        code, out = cli("ship", "--venv", site_p, "--", *ship_cmd)
        ck("ship PERMITS a proper-installed venv and RUNS the ship command", code == 0
           and os.path.isfile(marker), "exit %s: %s" % (code, out[-300:]))
        os.remove(marker)
        fail_cmd = [sys.executable, "-c", "import sys; sys.exit(7)"]
        code, out = cli("ship", "--venv", site_p, "--", *fail_cmd)
        ck("a failed ship command's OWN exit code is propagated verbatim (7, not 1 or 3)", code == 7,
           "exit %s: %s" % (code, out[-200:]))

        # ── usage refusals: exit 2, one line, no traceback, no bug report ──
        print("-- usage refusals and errors explain themselves (no traceback at the operator)")
        pkg = _demo_pkg(base)
        code, out = cli("install", pkg, "--venv", os.path.join(base, "nope-venv"), "--dev-debug")
        ck("--dev-debug with no --reason is refused (exit 2) with a one-line reason",
           code == 2 and "--reason" in out and "Traceback" not in out, "exit %s: %s" % (code, out[-300:]))
        ck("...and files NO bug report (a misuse is not a fault)",
           not os.path.isfile(os.path.join(base, "logs", "bug_reports.jsonl")), "")
        ck("...and installed nothing", not os.path.isdir(os.path.join(base, "nope-venv")))
        code, out = cli("install", pkg, "--venv", os.path.join(base, "nope-venv"), "--reason", "x")
        ck("--reason without --dev-debug is refused (it would imply an editable install)",
           code == 2 and "only with --dev-debug" in out, "exit %s: %s" % (code, out[-200:]))
        code, out = cli("check", "--venv", os.path.join(base, "not-a-venv"))
        ck("check on a missing venv exits 2 with a one-line explanation, not a traceback",
           code == 2 and "no such venv" in out and "Traceback" not in out, "exit %s: %s" % (code, out[-300:]))
        ck("...and its Variant-A bug report went to the THROWAWAY tree, not this repo",
           os.path.isfile(os.path.join(base, "logs", "bug_reports.jsonl")))
        empty = os.path.join(base, "empty-dir")
        os.makedirs(empty, exist_ok=True)
        code, out = cli("check", "--venv", empty)
        ck("check on a directory that is not a venv says exactly that",
           code == 2 and "no site-packages" in out, "exit %s: %s" % (code, out[-200:]))
        code, out = cli()
        ck("no command at all is a usage refusal that lists the commands",
           code == 2 and "install, check, ship or audit" in out, "exit %s: %s" % (code, out[-200:]))

        # ── audit ──
        print("-- the audit log: empty reads as (none), never as a crash")
        code, out = cli("audit", root=os.path.join(base, "declared"))
        ck("an empty audit log prints (none) and exits 0", code == 0 and "(none)" in out,
           "exit %s: %s" % (code, out[-200:]))

        # ── END-TO-END with REAL pip: #215's acceptance criteria ──
        print("-- END-TO-END with real pip: #215's acceptance, proven or honestly SKIPPED")
        venv = os.path.join(base, "e2e-venv")
        code, out = cli("install", pkg, "--venv", venv)
        skipped = "install SKIPPED" in out
        if skipped:
            print("   .. SKIP — pip could not reach an index on this host, so every end-to-end check")
            print("      below is skipped. This is a fact about the host, never about the package")
            print("      (the distinction pair_loop.py:985-988 makes). The detector checks above are")
            print("      hermetic and already ran.")
            print("      %s" % out.strip().splitlines()[-1][:160])
        else:
            ck("the DEFAULT install path exits 0 (no flags: proper is the default)", code == 0,
               "exit %s: %s" % (code, out[-400:]))
            ck("...and says it installed PROPER", "installed PROPER" in out, out[-300:])
            sites, eds = scan_venv(venv)
            ck("...leaving ZERO editable evidence in the venv", eds == [],
               str([e.as_dict() for e in eds]))
            site = sites[0]
            ck("...with the module as a real DIRECTORY in site-packages (a copy, not a pointer)",
               os.path.isfile(os.path.join(site, "demo_mod", "__init__.py")), site)
            du = os.path.join(site, "demo_pkg-0.1.0.dist-info", "direct_url.json")
            d = json.load(open(du)) if os.path.isfile(du) else {}
            ck("...and a direct_url.json whose dir_info has NO editable key — the exact shape the "
               "docstring claims for a proper local install", os.path.isfile(du)
               and d.get("dir_info") == {}, "%s: %s" % (du, d))
            code, out = cli("check", "--venv", venv)
            ck("check on the default-installed venv exits 0", code == 0 and "HOLDS" in out, out[-200:])
            code, out = cli("install", pkg, "--venv", os.path.join(base, "json-venv"), "--json")
            ck("install --json reports the decoupling proof machine-readably",
               code == 0 and '"decoupled": true' in out and '"editable": false' in out, out[-300:])

            # ACCEPTANCE 1: "moving/deleting the source does not break the installed module"
            py = Installer(venv).python(create=False)
            r = subprocess.run([py, "-c", "import demo_mod; print(demo_mod.hi())"],
                               capture_output=True, text=True, cwd=base)
            ck("the installed module imports before the source moves", r.stdout.strip() == "hi-from-demo_mod",
               r.stdout + r.stderr)
            moved = pkg + "-MOVED-AWAY"
            shutil.move(pkg, moved)
            r = subprocess.run([py, "-c", "import demo_mod; print(demo_mod.hi())"],
                               capture_output=True, text=True, cwd=base)
            ck("ACCEPTANCE 1 — with the SOURCE TREE MOVED AWAY the proper install still works "
               "(decoupled, for real, not structurally)", r.stdout.strip() == "hi-from-demo_mod",
               (r.stdout + r.stderr)[-250:])
            shutil.rmtree(moved + "-gone", ignore_errors=True)
            shutil.move(moved, pkg)

            # ACCEPTANCE 3: the hatch works and is auditable
            evenv = os.path.join(base, "e2e-editable-venv")
            code, out = cli("install", pkg, "--venv", evenv, "--dev-debug", "--reason", "chasing #215")
            ck("ACCEPTANCE 3 — --dev-debug --reason performs the EDITABLE install (the hatch works)",
               code == 0 and "installed EDITABLE" in out, "exit %s: %s" % (code, out[-400:]))
            ck("...and warns that check will still refuse it while undeclared",
               "does NOT declare" in out, out[-500:])
            ck("...and says the package cannot be shipped", "CANNOT BE SHIPPED" in out, out[-400:])
            _, recs = audit_read(base, Phases(json.load(open(os.path.join(base, "registry.json")))))
            ck("...and it is AUDITABLE: the log holds the request AND the outcome",
               len(recs) >= 2 and recs[-2].get("event") == "requested"
               and recs[-1].get("event") == "installed", str(recs[-2:])[:300])
            ck("...recording the reason, the operator, the source and the venv",
               recs[-1].get("reason") == "chasing #215" and recs[-1].get("package") == "demo-pkg"
               and recs[-1].get("operator") and recs[-1].get("venv") == os.path.abspath(evenv),
               str(recs[-1])[:300])
            code, out = cli("audit")
            ck("...and `audit` prints it back", code == 0 and "chasing #215" in out
               and "NOT declared in registry.json" in out, out[-300:])

            # the editable install is real, and the detector sees the REAL thing (not just fixtures)
            _, eds = scan_venv(evenv)
            ck("the detector finds the REAL pip-made editable install (not only hand-built fixtures)",
               len(eds) == 1 and eds[0].package == "demo-pkg", str([e.as_dict() for e in eds]))
            ck("...and cites PEP 610 direct_url.json as the authoritative evidence",
               any(k == K_DIRECT_URL for k, _ in eds[0].evidence), str(eds[0].evidence))
            ck("...and PEP 660's .pth, which is what pip actually wrote",
               any(k == K_PEP660_PTH for k, _ in eds[0].evidence), str(eds[0].evidence))
            # realpath on both sides: macOS resolves /var to /private/var, so pip records a path
            # that is the same directory as ours under a different spelling. Comparing the raw
            # strings would fail for a reason that has nothing to do with the policy.
            ck("...and points at the real source tree — the PROJECT ROOT from direct_url.json, not "
               "the module subdir the PEP 660 finder maps",
               os.path.realpath(eds[0].source) == os.path.realpath(pkg), eds[0].source)
            ck("...and marks that source as authoritative (PEP 610 beat the finder's MAPPING)",
               eds[0].source_authoritative, str(eds[0].as_dict()))

            # ACCEPTANCE 2: an editable-installed package is refused at ship
            code, out = cli("check", "--venv", evenv)
            ck("check REFUSES the real editable venv (undeclared)", code == 3, "exit %s: %s" % (code, out[-300:]))
            code, out = cli("ship", "--venv", evenv, "--package", "demo-pkg", "--", *ship_cmd)
            ck("ACCEPTANCE 2 — shipping an editable-installed package is REFUSED", code == 3,
               "exit %s: %s" % (code, out[-300:]))
            ck("...and the ship command did not run", not os.path.exists(marker))

            # "...until re-installed proper" — the block LIFTS on its own once that is done
            code, out = cli("install", pkg, "--venv", evenv)
            ck("re-installing PROPER over the editable install exits 0", code == 0, out[-300:])
            _, eds = scan_venv(evenv)
            ck("...and the editable evidence is GONE from the venv", eds == [],
               str([e.as_dict() for e in eds]))
            code, out = cli("ship", "--venv", evenv, "--package", "demo-pkg", "--", *ship_cmd)
            ck("...and the ship gate now PERMITS it and runs the command (the block lifts on "
               "re-install, with nothing to un-declare)", code == 0 and os.path.isfile(marker),
               "exit %s: %s" % (code, out[-300:]))
            os.remove(marker)

            # --method wheel: #215's other proper form
            wvenv = os.path.join(base, "e2e-wheel-venv")
            code, out = cli("install", pkg, "--venv", wvenv, "--method", "wheel")
            if "SKIPPED" in out:
                print("   .. SKIP — the wheel build needs the network too; not a verdict on the tool.")
            else:
                ck("--method wheel BUILDS a wheel and installs it, proper (#215's other form)",
                   code == 0 and "installed PROPER" in out, "exit %s: %s" % (code, out[-400:]))
                _, weds = scan_venv(wvenv)
                ck("...leaving no editable evidence either", weds == [], str(weds))

            # the drop-in for pair_loop.py:1001
            st, detail = proper_install_check(os.path.join(base, "pic"), pkg)
            ck("proper_install_check() — the drop-in for pair_loop.py's install_check — PASSes on a "
               "real package, installing PROPER rather than -e", st == "PASS", "%s: %s" % (st, detail))
            ck("...and its detail states the import came out of site-packages from a neutral cwd",
               "site-packages" in detail and "PROPER" in detail, detail)

        bad = [n for n, ok in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s"
              % (len(checks) - len(bad), len(checks), "" if not bad else "; FAILED: " + "; ".join(bad)))
        return 1 if bad else 0
    finally:
        shutil.rmtree(base, ignore_errors=True)
        print("== selftest == throwaway venvs removed (this repo, its logs and the db were never "
              "touched)")


if __name__ == "__main__":
    sys.exit(main())
