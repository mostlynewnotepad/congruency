#!/usr/bin/env python3
"""tag_test_harness.py — predicted-vs-rendered tag testing, logged as bet/test tickets.

Modeled on the tournament predictions harness (tools/predict.py -> logs/predictions.jsonl):
state what you EXPECT before you look, render, then resolve with the ACTUAL. Here the subject
is every invocator tag under invocators/tags. For each tag the harness

  1. records a PREDICTED rendering as a `bet` ticket   (BEFORE rendering — the prediction),
  2. renders the tag standalone, exactly as ?page=tags&tag=NAME does in the gallery,
  3. compares the rendered result against the prediction, and
  4. logs the outcome as a `test` ticket (verdict PASS / FAIL).

`bet` and `test` are the two ticket types this harness writes, appended to a git-ignored JSONL
ledger (logs/tag_tests.jsonl by default) — the same append-only ledger shape predict.py uses.
Nothing is ever rewritten; a re-run appends new bet/test pairs.

Two prediction modes:
  * clean contract (default) — the bet predicts that the tag renders standalone with HTTP 200
    and no PHP error in its output (the same error markers tagcheck.py asserts on). A tag that
    errors REFUTES its bet and logs a FAIL test.
  * golden baseline (--record-golden captures it, later runs consume it) — the bet predicts the
    tag renders byte-for-byte identically to a stored baseline signature (status + clean flag +
    sha256 of the response body). Any drift REFUTES the bet.

Discovery mirrors TagList::scan() (invocators/tags/dev/TagList.php): every *.php file under
invocators/tags whose source contains 'Tag_Interface', keyed by basename-minus-.php, deduped and
sorted. That is the identical universe the gallery lists, so ?tag=NAME resolves for each one.

Rendering needs the reference server. By default the harness boots an ephemeral PHP built-in
server itself (the boot/router.php bootstrap serve.py uses) and tears it down when done; pass
--base URL to reuse a server that is already running instead.

    python3 tools/tag_test_harness.py                 # boot a server, bet+render+test every tag
    python3 tools/tag_test_harness.py --base http://127.0.0.1:8899   # reuse a running server
    python3 tools/tag_test_harness.py --record-golden # capture this run's renders as the baseline
    python3 tools/tag_test_harness.py --view          # print the bet/test ledger; no server, no render
    python3 tools/tag_test_harness.py --report out.json
"""
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))          # checkouts/current/congruency/tools
SOURCE = os.path.dirname(HERE)                             # checkouts/current/congruency (the CMS app root)
TAGS_DIR = os.path.join(SOURCE, "invocators", "tags")
ROUTER = os.path.join("boot", "router.php")               # relative to SOURCE (cwd at serve time)
STATE = os.path.join(os.path.dirname(SOURCE), "state")     # checkouts/current/state (sibling of congruency)
SQLITE = os.path.join(STATE, "congruency.sqlite")

# The PHP-error markers, identical to tagcheck.py's ERR list: fatals AND non-fatal diagnostics
# (bug #108 showed a Warning-level null-deref slipping past a fatals-only check). "clean" == none present.
ERR = ("Fatal error", "Parse error", "Uncaught", "PHP Fatal", "Stack trace",
       "error:", "cy-form-error",
       "Warning:", "Deprecated:", "Notice:", "Trying to access", "array offset on null")


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
    return reg


def bug_report(reg, exc, tb):
    """Best-effort timestamped bug report, mirroring predict.py/serve.py on any exception."""
    root = (reg or {}).get("__root__") or os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    path = os.path.join(root, (reg or {}).get("bug_reports", "logs/bug_reports.jsonl"))
    frames = traceback.extract_tb(exc.__traceback__)
    last = frames[-1] if frames else None
    entry = {"filename": os.path.basename(__file__), "function": last.name if last else "?",
             "time-of-occurance": datetime.now().isoformat(),
             "methods-to-reproduce": "python3 tools/tag_test_harness.py",
             "possible-cause": "%s: %s" % (type(exc).__name__, exc),
             "traceback": tb.strip().splitlines()[-6:], "note": "tag_test_harness.py"}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    return path


# --------------------------------------------------------------------------- #
# ledger (append-only JSONL, the predict.py shape)                            #
# --------------------------------------------------------------------------- #
def ledger_path(reg, override=""):
    if override:
        return override if os.path.isabs(override) else os.path.join(reg["__root__"], override)
    rel = reg.get("tag_tests", "logs/tag_tests.jsonl")
    return os.path.join(reg["__root__"], rel)


def golden_path(reg):
    rel = reg.get("tag_golden", "logs/tag_golden.json")
    return os.path.join(reg["__root__"], rel)


def _read(sink):
    if not os.path.isfile(sink):
        return []
    out = []
    for ln in open(sink):
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
    return out


def _append(sink, rec):
    os.makedirs(os.path.dirname(sink), exist_ok=True)
    with open(sink, "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# --------------------------------------------------------------------------- #
# tag discovery (mirrors TagList::scan over invocators/tags)                   #
# --------------------------------------------------------------------------- #
def discover_tags():
    names = set()
    for root, _dirs, files in os.walk(TAGS_DIR):
        for fn in files:
            if not fn.lower().endswith(".php"):
                continue
            try:
                src = open(os.path.join(root, fn), "r", errors="replace").read()
            except OSError:
                continue
            if "Tag_Interface" in src:
                names.add(fn[:-4])                  # basename minus .php, exactly as scan() keys them
    return sorted(names)


# --------------------------------------------------------------------------- #
# php server (boot an ephemeral one, the serve.py way)                        #
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


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait_ready(base, deadline):
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/?page=tags", timeout=4) as r:
                if r.status:
                    return True
        except urllib.error.HTTPError:
            return True                             # server answered (any code) => it is up
        except Exception:                           # noqa: BLE001  (connection refused while it boots)
            time.sleep(0.25)
    return False


def boot_server(reg, port):
    """Start php -S on 127.0.0.1:port with the router, cwd=SOURCE. Returns (proc, base)."""
    if not os.path.isfile(SQLITE):
        raise FileNotFoundError(
            "no live state DB at %s. Restore it before rendering (python3 congruency_up.py restore), "
            "or point --base at a server that already has one." % SQLITE)
    php = find_php(reg)
    port = port or _free_port()
    base = "http://127.0.0.1:%d" % port
    proc = subprocess.Popen([php, "-S", "127.0.0.1:%d" % port, ROUTER], cwd=SOURCE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if not _wait_ready(base, time.time() + 15):
        proc.terminate()
        raise RuntimeError("php server did not become ready on %s" % base)
    return proc, base


def stop_server(proc):
    if not proc:
        return ""
    proc.terminate()
    try:
        _o, serr = proc.communicate(timeout=5)
    except Exception:                               # noqa: BLE001
        proc.kill()
        _o, serr = proc.communicate()
    return serr or ""


# --------------------------------------------------------------------------- #
# rendering + signatures                                                      #
# --------------------------------------------------------------------------- #
def get(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                          # noqa: BLE001
        return None, "%r" % e


def render_signature(base, tag):
    """Render one tag standalone (?page=tags&tag=NAME) and reduce it to a comparable signature."""
    st, body = get("%s/?page=tags&tag=%s" % (base, tag))
    markers = [m for m in ERR if m in body]
    return {"status": st, "clean": not markers, "markers": markers,
            "bytes": len(body), "body_sha": hashlib.sha256(body.encode("utf-8")).hexdigest()}


def predict_for(tag, golden):
    """The bet: what we expect BEFORE rendering. Golden baseline if present, else the clean contract."""
    g = (golden or {}).get(tag)
    if g:
        return {"mode": "golden", "status": g["status"], "clean": g["clean"], "body_sha": g["body_sha"]}
    return {"mode": "clean", "status": 200, "clean": True}


def statement_for(tag, predicted):
    if predicted["mode"] == "golden":
        return ("tag %s renders standalone identically to its golden baseline "
                "(HTTP %s, no PHP error, body sha %s)" % (tag, predicted["status"], predicted["body_sha"][:12]))
    return "tag %s renders standalone cleanly (HTTP 200, no PHP error)" % tag


def verdict_for(predicted, rendered):
    if predicted["mode"] == "golden":
        ok = (rendered["status"] == predicted["status"]
              and rendered["clean"] == predicted["clean"]
              and rendered["body_sha"] == predicted["body_sha"])
    else:                                           # clean contract
        ok = (rendered["status"] == 200 and rendered["clean"])
    return "PASS" if ok else "FAIL"


# --------------------------------------------------------------------------- #
# the view                                                                    #
# --------------------------------------------------------------------------- #
def view(reg, ledger):
    rows = _read(ledger)
    bets = {e["id"]: e for e in rows if e.get("kind") == "bet"}
    tests = [e for e in rows if e.get("kind") == "test"]
    print("=== tag_test_harness — ledger view ===")
    print("%s" % ledger)
    print("%d bet tickets, %d test tickets\n" % (len(bets), len(tests)))
    if not tests:
        print("  (no tests logged yet — run the harness without --view first)")
        return 0
    # latest test per tag
    latest = {}
    for t in tests:
        latest[t.get("tag")] = t                    # rows are in append order; last wins
    npass = sum(1 for t in latest.values() if t.get("verdict") == "PASS")
    print("latest verdict per tag — %d PASS, %d FAIL of %d tags:\n" % (npass, len(latest) - npass, len(latest)))
    for tag in sorted(latest):
        t = latest[tag]
        bet = bets.get(t.get("id"), {})
        print("  %-5s #%-4s %-22s %s" % (t.get("verdict", "?"), t.get("id", "?"), tag,
                                         bet.get("statement", "")))
    return 0 if npass == len(latest) else 1


# --------------------------------------------------------------------------- #
# the run                                                                      #
# --------------------------------------------------------------------------- #
def run(reg, ledger, base, record_golden, report):
    golden_file = golden_path(reg)
    golden = {}
    if os.path.isfile(golden_file):
        try:
            golden = json.load(open(golden_file)).get("tags", {})
        except (ValueError, OSError):
            golden = {}

    tags = discover_tags()
    next_id = max([e.get("id", 0) for e in _read(ledger) if e.get("kind") == "bet"], default=0) + 1

    results, fails, new_golden = [], [], {}
    for tag in tags:
        # 1. bet ticket (the prediction) — recorded BEFORE rendering.
        predicted = predict_for(tag, golden)
        bet_id = next_id
        next_id += 1
        _append(ledger, {"kind": "bet", "id": bet_id, "ts": _now(), "tag": tag,
                         "statement": statement_for(tag, predicted), "predicted": predicted,
                         "verdict": "PENDING"})
        # 2. render standalone, exactly as the gallery does.
        rendered = render_signature(base, tag)
        # 3. compare rendered vs predicted.
        verdict = verdict_for(predicted, rendered)
        # 4. test ticket (the outcome), referencing its bet by id.
        _append(ledger, {"kind": "test", "id": bet_id, "ts": _now(), "tag": tag,
                         "predicted": predicted, "rendered": rendered, "verdict": verdict})
        results.append({"id": bet_id, "tag": tag, "mode": predicted["mode"],
                        "status": rendered["status"], "verdict": verdict, "markers": rendered["markers"]})
        if verdict == "FAIL":
            fails.append(tag)
        new_golden[tag] = {"status": rendered["status"], "clean": rendered["clean"],
                           "body_sha": rendered["body_sha"], "bytes": rendered["bytes"]}

    if record_golden:
        os.makedirs(os.path.dirname(golden_file), exist_ok=True)
        json.dump({"ts": _now(), "base": base, "tags": new_golden}, open(golden_file, "w"), indent=2)

    print("=== tag_test_harness — %s ===" % base)
    print("%d tags, %d PASS, %d FAIL   (ledger: %s)\n"
          % (len(results), len(results) - len(fails), len(fails), ledger))
    for r in results:
        print("  %-5s #%-4s [%-6s] %-3s  %-22s %s"
              % (r["verdict"], r["id"], r["mode"], r["status"], r["tag"],
                 (", ".join(r["markers"]) if r["markers"] else "")))
    if record_golden:
        print("\ngolden baseline written: %s (%d tags)" % (golden_file, len(new_golden)))
    if report:
        json.dump({"base": base, "ledger": ledger, "results": results, "fails": fails},
                  open(report, "w"), indent=2)
        print("\nJSON: %s" % report)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description="predicted-vs-rendered tag test harness (bet/test tickets)")
    ap.add_argument("--base", default="",
                    help="reuse a running server (e.g. http://127.0.0.1:8899); default boots an ephemeral one")
    ap.add_argument("--port", type=int, default=0, help="port for the ephemeral server (default: a free port)")
    ap.add_argument("--record-golden", action="store_true",
                    help="write this run's renders as the golden baseline future bets predict against")
    ap.add_argument("--view", action="store_true", help="print the bet/test ledger and exit (no server, no render)")
    ap.add_argument("--ledger", default="", help="ledger path (default logs/tag_tests.jsonl under the registry root)")
    ap.add_argument("--report", default="", help="also dump a JSON report to this path")
    a = ap.parse_args()

    reg = load_registry()
    ledger = ledger_path(reg, a.ledger)

    if a.view:
        return view(reg, ledger)

    proc = None
    try:
        if a.base:
            base = a.base.rstrip("/")
        else:
            proc, base = boot_server(reg, a.port)
        return run(reg, ledger, base, a.record_golden, a.report)
    finally:
        stop_server(proc)


if __name__ == "__main__":
    _reg = None
    try:
        _reg = load_registry()
    except Exception:                               # noqa: BLE001
        pass
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:                        # noqa: BLE001
        p = bug_report(_reg, exc, traceback.format_exc())
        print("EXCEPTION — bug report -> %s" % p, file=sys.stderr)
        raise
