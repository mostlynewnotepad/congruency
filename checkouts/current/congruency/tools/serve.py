#!/usr/bin/env python3
"""serve.py — the congruency php-web reference server (ONE python script, no shell).

Reconstruction of the old ~/congruencey-harness as the source's own tool. It boots the
CMS under PHP's built-in web server using the relocatable new-tree bootstrap
(../boot/router.php), served from the congruency source root (checkouts/current/congruency). This
replaces the old bash `serve`/`verify` scripts, which note-for-claude forbids.

    python3 tools/serve.py                # serve on 0.0.0.0:8899   (Ctrl-C to stop)
    python3 tools/serve.py --port 9000
    python3 tools/serve.py --verify       # boot, probe pages, assert HTTP 200, exit

Design rules (note-for-claude):
  * python only, no shell;
  * registry-gated — throws if it cannot see registry.json;
  * every path derived from __file__ (relocatable — works at any clone location);
  * php located via $CONGRUENCEY_PHP, then registry paths.php, then convention;
  * auto bug-report (timestamped) on any exception.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import tarfile
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))          # checkouts/current/congruency/tools
SOURCE = os.path.dirname(HERE)                             # checkouts/current/congruency (the CMS app root)
ROUTER = os.path.join("boot", "router.php")               # relative to SOURCE (cwd at serve time)
STATE = os.path.join(os.path.dirname(SOURCE), "state")     # checkouts/current/state (sibling of congruency)
SQLITE = os.path.join(STATE, "congruency.sqlite")
DB_TAR = os.path.join(STATE, "database.tar.xz")
DEFAULT_PORT = 8899
PAGES = ["?page=catalog&fresh=1", "?page=about", "?page=catalog"]
FATAL = ("Fatal error", "Parse error", "Uncaught", "PHP Fatal", "Stack trace")


# --------------------------------------------------------------------------- #
# registry (mandated: a tool that cannot see the registry must throw)         #
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
    reg["__file__"] = path
    return reg


def bug_report(reg, exc, tb):
    root = (reg or {}).get("__root__", os.path.dirname(os.path.dirname(SOURCE)))
    rel = (reg or {}).get("bug_reports", "logs/bug_reports.jsonl")
    path = os.path.join(root, rel)
    frames = traceback.extract_tb(exc.__traceback__)
    last = frames[-1] if frames else None
    entry = {
        "filename": os.path.basename(__file__),
        "function": last.name if last else "?",
        "time-of-occurance": datetime.now().isoformat(),
        "methods-to-reproduce": "python3 tools/serve.py %s" % " ".join(sys.argv[1:]),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": tb.strip().splitlines()[-6:],
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    return path


# --------------------------------------------------------------------------- #
# prerequisites                                                               #
# --------------------------------------------------------------------------- #
def find_php(reg):
    env = os.environ.get("CONGRUENCEY_PHP")
    if env and os.path.isfile(env):
        return env
    rel = (reg.get("paths", {}) or {}).get("php", "tooling/congruencey-harness/php/php")
    cand = os.path.join(reg["__root__"], rel)
    if os.path.isfile(cand):
        return cand
    raise FileNotFoundError(
        "php not found (checked $CONGRUENCEY_PHP and %s). Provision it first: "
        "python3 checkouts/current/congruency/tools/provision_php.py" % cand)


def ensure_db():
    """Require a PRESENT live DB — never fabricate/extract one.

    `SQLITE` is a symlink to the live DB; extracting a seed here writes THROUGH the symlink and
    destroys real data — the historical clobber bug. serve.py must never write the state path. If
    the DB is absent (or the symlink dangles), HALT and tell the operator to restore explicitly."""
    if os.path.islink(SQLITE) and not os.path.exists(SQLITE):
        raise FileNotFoundError(
            "state DB symlink %s is DANGLING (live DB moved/absent). Refusing to serve or reseed — "
            "restore explicitly: `python3 congruency_up.py restore`." % SQLITE)
    if os.path.isfile(SQLITE):
        return "present"
    raise FileNotFoundError(
        "no live state DB at %s. Refusing to fabricate a seed (that was the data-loss bug) — "
        "restore explicitly: `python3 congruency_up.py restore`." % SQLITE)


# --------------------------------------------------------------------------- #
# verify mode — boot, probe, assert 200                                       #
# --------------------------------------------------------------------------- #
def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _probe(url):
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            return r.status, r.read(8000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(8000).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return None, "%r" % e


def verify(php):
    port = _free_port()
    proc = subprocess.Popen([php, "-S", "127.0.0.1:%d" % port, ROUTER], cwd=SOURCE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.5)
    rows, first = [], ""
    try:
        for pg in PAGES:
            st, body = _probe("http://127.0.0.1:%d/%s" % (port, pg))
            rows.append({"page": pg, "status": st, "bytes": len(body)})
            if not first:
                first = body
    finally:
        proc.terminate()
        try:
            _o, serr = proc.communicate(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()
            _o, serr = proc.communicate()
    ok = (all(r["status"] == 200 for r in rows)
          and not any(m in (first + (serr or "")) for m in FATAL))
    print(json.dumps({"ok": ok, "served_from": os.path.relpath(SOURCE, reg_root()),
                      "router": ROUTER, "pages": rows}, indent=2))
    if not ok:
        raise RuntimeError("verify failed (not all 200 / fatal detected): %s" % rows)
    return ok


def reg_root():
    try:
        return os.path.dirname(find_registry())
    except Exception:  # noqa: BLE001
        return SOURCE


# --------------------------------------------------------------------------- #
# serve mode — foreground php -S (php replaces this process)                   #
# --------------------------------------------------------------------------- #
def serve(php, host, port):
    print("serving congruency CMS  http://%s:%d/?page=catalog   (Ctrl-C to stop)" % (host, port))
    print("  served from %s  via %s" % (SOURCE, ROUTER))
    os.chdir(SOURCE)                          # router path is relative to the source root
    os.execv(php, [php, "-S", "%s:%d" % (host, port), ROUTER])   # never returns on success


def main():
    ap = argparse.ArgumentParser(description="congruency php-web reference server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--verify", action="store_true",
                    help="boot, probe catalog/about, assert HTTP 200, then exit")
    a = ap.parse_args()

    reg = load_registry()
    php = find_php(reg)
    ensure_db()
    if a.verify:
        return 0 if verify(php) else 1
    serve(php, a.host, a.port)
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
        p = bug_report(_reg, exc, traceback.format_exc())
        print("EXCEPTION — bug report -> %s" % p, file=sys.stderr)
        raise
