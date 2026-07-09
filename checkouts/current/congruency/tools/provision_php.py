#!/usr/bin/env python3
"""provision_php.py — new-tree reference-server recipe: provision the php runtime.

The mono ships NO binaries (they don't belong in git); instead this python recipe places a
php binary into <mono>/<paths.php> (default tooling/congruencey-harness/php/php) from an
available source, in order:

  1. a local source path listed in registry php_provision.sources (or the legacy defaults);
  2. otherwise a NETWORK FETCH of a static php-cli build, extracted in-python — no shell script.
     The build is chosen for THIS host's os+arch (see platform_download): macOS arm64 gets a
     native arm64 php, so congruency runs on Apple Silicon with NO x86 emulation. A registry
     `php_provision.download.url` is honored only if it matches the host platform; otherwise it
     is a version hint and the native build wins. `download.version` picks a build without a URL.

The recipe is committed; the binary is git-ignored. It verifies the result with `php -v`.

python-only, registry-driven (throws if it can't see registry.json), auto-bug-report on
exception.
"""
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import traceback
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DEST_REL = os.path.join("tooling", "congruencey-harness", "php", "php")
DEFAULT_SOURCES = [
    "/home/notificationsforsteven/congruencey-harness/php/php",
    "/home/notificationsforsteven/b01/tooling/congruencey-harness/php/php",
]
PHP_VERSION = "8.4.23"     # static-php-cli build to fetch when none is provisioned/pinned
STATIC_PHP = "https://dl.static-php.dev/static-php-cli/common/php-%s-cli-%s-%s.tar.gz"
UA = "Mozilla/5.0 provision_php"


def _platform_slug():
    """(os, arch) slugs for the static-php-cli asset naming — the NATIVE build for THIS host, so
    macOS arm64 gets a real arm64 php (no x86 emulation), linux gets linux, an Intel Mac gets
    macos-x86_64, etc."""
    sysname = {"darwin": "macos", "linux": "linux"}.get(platform.system().lower(), "linux")
    m = platform.machine().lower()
    arch = "aarch64" if m in ("arm64", "aarch64") else "x86_64"
    return sysname, arch


def _version_from_url(url):
    m = re.search(r"php-([0-9]+\.[0-9]+\.[0-9]+)-cli", url or "")
    return m.group(1) if m else None


def platform_download(cfg):
    """Resolve the static-php download for THIS os+arch. A registry `download.url` is honored only
    when it already matches the host platform; otherwise (e.g. a linux url on macOS) it is treated
    as a version hint and the native build is chosen instead — so a linux-pinned registry never
    forces x86 emulation on an arm Mac. Set `download.version` to pick a build without a URL."""
    dl = dict(cfg.get("download") or {})
    member = dl.get("member", "php")
    sysname, arch = _platform_slug()
    slug = "%s-%s" % (sysname, arch)
    pinned = dl.get("url")
    if pinned and ("-%s." % slug) in pinned:
        return {"url": pinned, "member": member, "platform": slug}
    ver = dl.get("version") or _version_from_url(pinned) or PHP_VERSION
    return {"url": STATIC_PHP % (ver, sysname, arch), "member": member, "platform": slug}


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
    reg["__file__"] = path
    return reg


def bug_report(reg, exc, tb):
    # Root is the registry root when known; else the mono root (HERE's parent, since HERE is
    # file-system-repair/). Never HERE itself — that would double the default rel path.
    root = (reg or {}).get("__root__") or os.path.dirname(HERE)
    path = os.path.join(root, (reg or {}).get("bug_reports", "logs/bug_reports.jsonl"))
    frames = traceback.extract_tb(exc.__traceback__)
    last = frames[-1] if frames else None
    entry = {
        "filename": os.path.basename(last.filename) if last else os.path.basename(__file__),
        "function": last.name if last else "?",
        "time-of-occurance": datetime.now().isoformat(),
        "methods-to-reproduce": "python3 %s" % os.path.basename(__file__),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": tb.strip().splitlines()[-6:],
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(entry) + "\n")
    return path


def ensure_gitignore(mono, rel):
    gi = os.path.join(mono, ".gitignore")
    line = "/" + rel.replace(os.sep, "/")
    # Idempotent: if the path is ALREADY ignored (e.g. by a parent-dir pattern), don't touch
    # .gitignore — appending a redundant line dirties the tracked tree and would block a fresh
    # install/mint until uninstall. (bug_reports: provision_php ensure_gitignore.)
    if subprocess.run(["git", "check-ignore", "-q", rel], cwd=mono).returncode == 0:
        return gi
    existing = open(gi).read().splitlines() if os.path.isfile(gi) else []
    if line not in existing:
        with open(gi, "a") as fh:
            fh.write(("" if not existing or existing[-1] == "" else "\n") + line + "\n")
    return gi


def _download(url, dest_tmp):
    """Fetch url -> dest_tmp. Try urllib with a browser UA (static-php.dev/Cloudflare 403s
    the default python UA); fall back to curl if urllib is blocked. No shell script."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=240) as r, open(dest_tmp, "wb") as fh:
            shutil.copyfileobj(r, fh)
        if os.path.getsize(dest_tmp) > 0:
            return "urllib"
    except Exception:  # noqa: BLE001 — fall through to curl
        pass
    if shutil.which("curl"):
        rc = subprocess.run(["curl", "-sL", "--max-time", "240", "-o", dest_tmp, url]).returncode
        if rc == 0 and os.path.isfile(dest_tmp) and os.path.getsize(dest_tmp) > 0:
            return "curl"
    raise RuntimeError("could not download %s (urllib blocked and curl unavailable/failed)" % url)


def _provision_from_download(dl, dest):
    member = dl.get("member", "php")
    with tempfile.TemporaryDirectory() as td:
        arch = os.path.join(td, "php.tgz")
        how = _download(dl["url"], arch)
        with tarfile.open(arch) as t:
            name = next((n for n in t.getnames() if os.path.basename(n) == member), None)
            if not name:
                raise RuntimeError("no %r member in %s" % (member, dl["url"]))
            t.extract(name, td, filter="data")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(os.path.join(td, name), dest)
    return "downloaded (%s) from %s" % (how, dl["url"])


def _php_ok(path):
    """True iff `path` is a php that RUNS on this host. Catches OSError (Errno 8 Exec format error)
    so a wrong-arch leftover — e.g. a linux php left by the old amd64 container on an arm Mac — is
    treated as unusable and REPLACED with the native build, not raised as a crash."""
    try:
        return subprocess.run([path, "-v"], capture_output=True).returncode == 0
    except OSError:
        return False


def main():
    reg = load_registry()
    root = reg["__root__"]
    mono = os.path.join(root, reg.get("paths", {}).get("mono", "."))
    dest = os.path.join(mono, reg.get("paths", {}).get("php", DEST_REL))
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    # idempotent (bug #4): a WORKING php already at dest -> skip re-acquisition (the
    # network-fetch fallback below still runs on a genuinely fresh clone, or when the existing
    # binary is the wrong arch — a linux php on an arm Mac -> _php_ok False -> re-provision native).
    if os.path.isfile(dest) and _php_ok(dest):
        how = "already provisioned (%s)" % os.path.relpath(dest, mono)
    else:
        cfg = reg.get("php_provision", {}) or {}
        sources = cfg.get("sources", DEFAULT_SOURCES)
        src = next((c for c in sources if os.path.isfile(c)), None)
        if src and os.path.abspath(src) != os.path.abspath(dest):
            shutil.copy2(src, dest)
            how = "copied from %s" % src
        elif src:
            how = "already in place (%s)" % src
        else:
            how = _provision_from_download(platform_download(cfg), dest)
        os.chmod(dest, os.stat(dest).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    ver = subprocess.run([dest, "-v"], capture_output=True, text=True)
    if ver.returncode != 0:
        raise RuntimeError("provisioned php does not run: %s" % (ver.stderr or ver.stdout).strip())

    rel = os.path.relpath(dest, mono)
    ensure_gitignore(mono, rel)
    subprocess.run(["git", "add", ".gitignore", "checkouts/current/congruency/tools/provision_php.py"],
                   cwd=mono, capture_output=True, text=True)

    result = {
        "mono": mono, "php": rel, "how": how,
        "php_version": (ver.stdout or "").splitlines()[0] if ver.stdout else "?",
        "php_size_bytes": os.path.getsize(dest),
        "gitignored": "/" + rel.replace(os.sep, "/"),
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    _reg = None
    try:
        _reg = load_registry()
    except Exception:  # noqa: BLE001
        pass
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        p = bug_report(_reg, exc, traceback.format_exc())
        print("EXCEPTION — bug report -> %s" % p, file=sys.stderr)
        raise
