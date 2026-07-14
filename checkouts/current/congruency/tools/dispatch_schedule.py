#!/usr/bin/env python3
"""dispatch_schedule.py — run dispatch-01 on a schedule. ONE python script, no shell scripts.

Installs a macOS LaunchAgent that runs `pair_loop.py --dispatch <cap>` every `interval_hours`,
so the dispatcher routes whatever the queue holds — and correctly declines stopped/control
tickets — without a human in the loop. The BOUNDS are the safety case: the per-run cap, the
stop-ticket brake pair_loop checks before acting, and the SQL governance that refuses erasure
no matter what a scheduled agent does.

Config lives in the repo registry.json (walk-up; refuses to run without it, per note-for-claude):

    "dispatch": {"interval_hours": 6, "cap": 3, "timeout": 480}

    python3 dispatch_schedule.py install     # write + load the LaunchAgent
    python3 dispatch_schedule.py uninstall   # unload + remove it
    python3 dispatch_schedule.py status      # loaded? last log lines
    python3 dispatch_schedule.py run-once    # kickstart one dispatch NOW (proof / manual turn)

Output lands in <repo>/logs/dispatch.log (+ .err). Unexpected outcomes inside the dispatch run
itself file Variant-A bug reports via pair_loop's own harness.
"""
import json
import os
import plistlib
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def find_root():
    d = HERE
    while d != "/":
        if os.path.isfile(os.path.join(d, "registry.json")):
            return d
        d = os.path.dirname(d)
    raise SystemExit("registry.json not found walking up from %s — refusing to run (note-for-claude)" % HERE)


ROOT = find_root()
LABEL = "com.congruency.dispatch"
PLIST = os.path.expanduser("~/Library/LaunchAgents/%s.plist" % LABEL)
PAIR_LOOP = os.path.join(ROOT, "checkouts", "current", "congruency", "tools", "pair_loop.py")


def config():
    with open(os.path.join(ROOT, "registry.json")) as fh:
        reg = json.load(fh)
    c = reg.get("dispatch") or {}
    return {"interval_hours": float(c.get("interval_hours", 6)),
            "cap": int(c.get("cap", 3)),
            "timeout": int(c.get("timeout", 480))}


def build_plist(c):
    python3 = sys.executable or shutil.which("python3")
    claude = shutil.which("claude")
    if not claude:
        raise SystemExit("`claude` CLI not on PATH — the pairs cannot spawn; aborting install")
    path = ":".join(dict.fromkeys([os.path.dirname(claude), "/usr/local/bin", "/usr/bin", "/bin"]))
    logs = os.path.join(ROOT, "logs")
    os.makedirs(logs, exist_ok=True)
    return {
        "Label": LABEL,
        "ProgramArguments": [python3, PAIR_LOOP, "--dispatch", str(c["cap"]), "--timeout", str(c["timeout"])],
        "WorkingDirectory": ROOT,
        "StartInterval": int(c["interval_hours"] * 3600),
        "RunAtLoad": False,
        "StandardOutPath": os.path.join(logs, "dispatch.log"),
        "StandardErrorPath": os.path.join(logs, "dispatch.err"),
        "EnvironmentVariables": {"PATH": path, "HOME": os.path.expanduser("~")},
    }


def domain():
    return "gui/%d" % os.getuid()


def install():
    c = config()
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    with open(PLIST, "wb") as fh:
        plistlib.dump(build_plist(c), fh)
    subprocess.run(["launchctl", "bootout", domain(), PLIST], capture_output=True)  # reload-safe
    r = subprocess.run(["launchctl", "bootstrap", domain(), PLIST], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("launchctl bootstrap failed: %s" % (r.stderr or r.stdout).strip())
    print("installed %s: dispatch-01 every %gh, cap %d ticket(s)/run, log %s"
          % (LABEL, c["interval_hours"], c["cap"], os.path.join(ROOT, "logs", "dispatch.log")))


def uninstall():
    subprocess.run(["launchctl", "bootout", domain(), PLIST], capture_output=True)
    if os.path.exists(PLIST):
        os.remove(PLIST)
    print("uninstalled %s" % LABEL)


def status():
    r = subprocess.run(["launchctl", "print", "%s/%s" % (domain(), LABEL)], capture_output=True, text=True)
    loaded = r.returncode == 0
    print("%s: %s" % (LABEL, "LOADED" if loaded else "not loaded"))
    if loaded:
        for ln in r.stdout.splitlines():
            if any(k in ln for k in ("state =", "runs =", "last exit", "interval")):
                print("  " + ln.strip())
    log = os.path.join(ROOT, "logs", "dispatch.log")
    if os.path.isfile(log):
        with open(log) as fh:
            tail = fh.readlines()[-8:]
        print("-- %s (tail) --" % log)
        for ln in tail:
            print("  " + ln.rstrip())
    return 0 if loaded else 1


def run_once():
    r = subprocess.run(["launchctl", "kickstart", "-k", "%s/%s" % (domain(), LABEL)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("kickstart failed (is it installed?): %s" % (r.stderr or r.stdout).strip())
    print("kickstarted %s — watch logs/dispatch.log" % LABEL)


def main():
    cmds = {"install": install, "uninstall": uninstall, "status": status, "run-once": run_once}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        print(__doc__)
        return 2
    return cmds[sys.argv[1]]() or 0


if __name__ == "__main__":
    sys.exit(main())
