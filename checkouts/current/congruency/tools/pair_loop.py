#!/usr/bin/env python3
"""pair_loop.py — the agent-pair loop: a ticket authorizes a worker; its counterpart validates.

One iteration of the adversarial network, harnessed:

    1. BRAKE     ticket.stops — an active (unreleased) stop ticket aimed at the target or any
                 ancestor halts the loop before anything acts.
    2. PAIR      register a FRESH worker + adversary for this ticket/round (agent.register, full
                 birth prompts) and authorize both on the ticket (ticket.assign). Fresh spawns ARE
                 the memory clear: a new agent has no context; the OLD agents' trails stay on the
                 record forever (the journal is append-only — nothing is erased).
    3. WORK      spawn the worker (`claude -p`, tools limited to reading + writing the deliverable);
                 it produces the artifact and reports {"done":true,"ref":...} on its last line.
    4. VALIDATE  spawn the adversary BLIND to the worker's reasoning (it sees the ticket + the
                 artifact, never the worker's transcript); it reports {"verdict":"pass"|"fail",
                 "findings":[...]} on its last line.
    5. SETTLE    pass -> work.record the artifact (permanent UID), journal, status DONE (the db
                 itself refuses DONE without two distinct agents in two distinct roles);
                 fail -> journal the findings and re-run with a FRESH worker (--rounds), findings
                 appended to the new worker's birth prompt.

Every write goes through the governed REST surface (token routes) — the harness holds no SQL pen.
Registry-gated per note-for-claude: walks up to registry.json and throws if it cannot see it; any
unexpected outcome files a Variant-A bug report to the registry's bug_reports sink.

Usage:
    python3 pair_loop.py --ticket 251                 # run the pair on an existing ticket
    python3 pair_loop.py --file documentation --title "..." --body "..." --deliverable docs/X.md
    ... [--rounds 2] [--timeout 480]
"""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request


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
CONG = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")


def _secret(name):
    path = os.path.join(os.path.dirname(ROOT), ".secrets", "ats.env")
    if os.path.isfile(path):
        for line in open(path):
            if line.strip().startswith(name + "="):
                return line.strip().split("=", 1)[1]
    return os.environ.get(name)


API_KEY = _secret("CONGRUENCY_API_KEY")


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks)."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "pair_loop.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S") + ".%06d" % int((time.time() % 1) * 1e6),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:], "note": "pair_loop harness",
            }) + "\n")
    except Exception:  # noqa: BLE001
        pass


class Unexpected(RuntimeError):
    pass


# ── REST (all writes go through the governed surface) ─────────────────────────────────────────────
def rest(route, obj=None, method=None):
    url = CONG + "/rest.php?route=" + route
    if obj is not None and (method or "POST") == "GET":
        url += "&" + "&".join("%s=%s" % (k, urllib.request.quote(str(v))) for k, v in obj.items())
        obj = None
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json", "X-Api-Key": API_KEY or ""})
    with urllib.request.urlopen(req, timeout=15) as r:
        out = json.loads(r.read().decode())
    if "error" in out:
        raise Unexpected("route %s failed: %s" % (route, out["error"]))
    return out


def rows(route, params):
    return rest(route, params, method="GET").get("rows", [])


# ── the pair's birth prompts ───────────────────────────────────────────────────────────────────────
GOVERNANCE = """
GOVERNANCE: ticket #%(tid)s authorizes you — work on nothing else. History is append-only: never
delete or rewrite anything that exists; produce, don't erase. You are registered as %(agent)s and
every action is on the record. Print your final answer as the LAST line of output: one JSON object,
nothing after it."""

WORKER_PROMPT = """You are %(agent)s, the %(role)s — the worker of a %(kind)s pair on ticket #%(tid)s.

TICKET: %(title)s
%(body)s

Deliverable: write it to %(deliverable)s (create or overwrite that file; touch nothing else).
Ground every claim in the actual repository — read the real migrations, routes, and tools you
describe; never document intentions as behavior. Your counterpart will adversarially audit this
with no access to your reasoning, so the artifact must stand alone.
%(findings)s
When the deliverable is written, print as your LAST line:
{"done": true, "ref": "%(deliverable)s", "note": "<one line on what you produced>"}
""" + GOVERNANCE

AUDITOR_PROMPT = """You are %(agent)s, the %(role)s — the adversary of a %(kind)s pair on ticket #%(tid)s.

TICKET: %(title)s
%(body)s

The worker produced %(deliverable)s. You did NOT see the worker's reasoning — judge the artifact
alone, as a hostile newcomer: no context, no charity. Verify its claims against the actual
repository (read the migrations/routes/tools it cites). Findings are: claims that don't match the
code, steps that can't be executed as written, terms undefined at first use, anything a newcomer
must read twice. Nitpicks are not findings. Print as your LAST line:
{"verdict": "pass", "findings": []}   or   {"verdict": "fail", "findings": ["<finding>", ...]}
""" + GOVERNANCE


def spawn_claude(prompt, allowed_tools, timeout):
    """One fresh-context agent run. Fresh spawn = clean memory; the db keeps the durable trail."""
    r = subprocess.run(["claude", "-p", prompt, "--allowedTools", allowed_tools],
                       cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise Unexpected("claude exited %s: %s" % (r.returncode, (r.stderr or r.stdout).strip()[-300:]))
    for line in reversed((r.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    raise Unexpected("no JSON verdict on the agent's last line; tail: %r" % (r.stdout or "")[-200:])


def step(name, fn, *a, **kw):
    t0 = time.time()
    try:
        out = fn(*a, **kw)
        print("== %s ==\n   ok (%d ms) %s" % (name, (time.time() - t0) * 1000, out if out is not None else ""))
        return out
    except Exception as e:  # noqa: BLE001
        bug_report(name, e, "python3 pair_loop.py (step: %s)" % name, e)
        print("== %s ==\n   FAILED: %s" % (name, e))
        raise


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)   # progress visible when redirected (background runs)
    ap = argparse.ArgumentParser(description="agent-pair loop: worker acts on a ticket, adversary validates")
    ap.add_argument("--ticket", type=int, help="existing ticket id to run the pair on")
    ap.add_argument("--file", metavar="KIND", help="file a NEW ticket of this kind instead")
    ap.add_argument("--title"), ap.add_argument("--body", default=""), ap.add_argument("--component", default="congruency")
    ap.add_argument("--deliverable", required=True, help="repo-relative path the worker must produce")
    ap.add_argument("--rounds", type=int, default=2, help="max worker rounds before giving up")
    ap.add_argument("--timeout", type=int, default=480, help="seconds per agent spawn")
    a = ap.parse_args()
    if not API_KEY:
        raise Unexpected("no CONGRUENCY_API_KEY (secrets or env) — token routes need it")

    # ── ticket: take it or file it ────────────────────────────────────────────
    if a.file:
        out = rest("ticket.create", {"component": a.component, "title": a.title or a.file,
                                     "severity": "normal", "body": a.body, "patch": ""})
        tid = int(out["rowid"])
        rest("ticket.kind", {"id": tid, "kind": a.file})
        print("== filed == ticket #%d (%s)" % (tid, a.file))
    elif a.ticket:
        tid = a.ticket
    else:
        ap.error("--ticket N or --file KIND required")

    with urllib.request.urlopen(CONG + "/rest.php?api=tickets&id=%d" % tid, timeout=15) as r:
        tk = json.loads(r.read().decode()).get("row") or {}
    title, body, kind = tk.get("title", ""), tk.get("body", ""), tk.get("kind")
    if not kind:
        raise Unexpected("ticket #%s has no kind — set it via ticket.kind first" % tid)

    kinds = {k["kind"]: k for k in rows("kind.roster", {})}
    if kinds.get(kind, {}).get("pattern") != "pair":
        raise Unexpected("ticket #%s kind %r is not a pair kind — the loop harnesses pairs" % (tid, kind))
    w_role, a_role = kinds[kind]["worker_role"], kinds[kind]["adversary_role"]

    # ── brake ─────────────────────────────────────────────────────────────────
    stops = rows("ticket.stops", {"ticket_id": tid})[0]["active_stops"]
    if int(stops) > 0:
        print("== HALT == %s active stop ticket(s) aim at #%s — the ticket authorizes nothing" % (stops, tid))
        return 3
    print("== brake == no active stops on #%s" % tid)

    findings = []
    for rnd in range(1, a.rounds + 1):
        worker = "%s-t%dr%d" % (w_role, tid, rnd)
        auditor = "%s-t%dr%d" % (a_role, tid, rnd)
        ctx = dict(tid=tid, kind=kind, title=title, body=body, deliverable=a.deliverable)

        # fresh pair, registered + authorized (fresh spawn = cleared memory; trails persist)
        def pair():
            for agent, role, tmpl in ((worker, w_role, WORKER_PROMPT), (auditor, a_role, AUDITOR_PROMPT)):
                fx = "\nPrior adversary findings to address:\n- " + "\n- ".join(findings) + "\n" if (findings and role == w_role) else ""
                rest("agent.register", {"agent_id": agent, "parent": "pair_loop",
                                        "prompt": tmpl % {**ctx, "agent": agent, "role": role, "findings": fx},
                                        "tools": json.dumps(["claude -p"])})
                rest("ticket.assign", {"ticket_id": tid, "agent_id": agent, "role": role})
            rest("process_status", {"id": tid, "status": "ACTIVE"})
            return {"worker": worker, "auditor": auditor}
        step("pair (round %d)" % rnd, pair)

        fx = "\nPrior adversary findings to address:\n- " + "\n- ".join(findings) + "\n" if findings else ""
        wp = WORKER_PROMPT % {**ctx, "agent": worker, "role": w_role, "findings": fx}
        wres = step("work: %s" % worker, spawn_claude, wp, "Read,Grep,Glob,Write,Edit", a.timeout)
        if not wres.get("done"):
            raise Unexpected("worker did not report done: %s" % wres)
        rest("ticket.progress", {"ticket_id": tid, "agent_id": worker,
                                 "note": "round %d: produced %s — %s" % (rnd, wres.get("ref"), wres.get("note", "")),
                                 "steps_remaining": 2})

        aprompt = AUDITOR_PROMPT % {**ctx, "agent": auditor, "role": a_role}
        vres = step("validate: %s" % auditor, spawn_claude, aprompt, "Read,Grep,Glob", a.timeout)
        rest("ticket.progress", {"ticket_id": tid, "agent_id": auditor,
                                 "note": "round %d verdict: %s%s" % (rnd, vres.get("verdict"),
                                        ("; findings: " + "; ".join(vres.get("findings", []))) if vres.get("findings") else ""),
                                 "steps_remaining": 1 if vres.get("verdict") == "pass" else 3})

        if vres.get("verdict") == "pass":
            rest("work.record", {"ticket_id": tid, "kind": "doc" if kind == "documentation" else "code",
                                 "ref": wres.get("ref", a.deliverable), "note": wres.get("note", "")})
            rest("process_status", {"id": tid, "status": "DONE"})  # db refuses without the pair
            rest("ticket.progress", {"ticket_id": tid, "agent_id": auditor,
                                     "note": "PASS — manifest updated, ticket DONE; pair retired (fresh agents next iteration)",
                                     "steps_remaining": 0})
            print("== settled == ticket #%s DONE (round %d) — deliverable %s carries a permanent UID" % (tid, rnd, wres.get("ref")))
            return 0
        findings = vres.get("findings", ["(none given)"])
        print("== round %d failed == %d finding(s); respawning a FRESH worker" % (rnd, len(findings)))

    print("== gave up == %d rounds exhausted on #%s; findings journaled, status stays ACTIVE" % (a.rounds, tid))
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Unexpected as e:
        bug_report("main", e, "python3 pair_loop.py " + " ".join(sys.argv[1:]), e)
        print("UNEXPECTED: %s" % e)
        sys.exit(2)
