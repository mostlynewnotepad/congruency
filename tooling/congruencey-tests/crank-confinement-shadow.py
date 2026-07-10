#!/usr/bin/env python3
"""crank-confinement-shadow — a crank patch is confined at RUNTIME by audit_guard.

A patch runs as a real subprocess, so without a guard a rogue/agent-authored patch could shell out,
write ~/.claude, read the wallet seed, or exfiltrate — the escape used once. Static source inspection
is theater (the model builds the call/path dynamically). This pins that audit_guard.py REFUSES, at the
moment of the actual operation, every escape class — shell-out, network, native FFI, sensitive-path
and out-of-repo writes — however the source spelled them, and PASSES a legitimate repo-editing patch
(imports still work; the edit lands under the repo).
"""
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUARD = os.path.join(REPO, "checkouts", "current", "congruency", "tools", "audit_guard.py")

checks = []
def check(name, ok):
    checks.append(bool(ok))
    print("  %s %s" % ("\033[32m✓\033[0m" if ok else "\033[31m✗ FAIL\033[0m", name))


def run_patch(src, sandbox):
    """Run a patch through the guard against a throwaway repo; return (rc, stderr)."""
    p = os.path.join(sandbox, "patch.py")
    with open(p, "w") as fh:
        fh.write(src)
    env = {**os.environ, "CRANK_REPO": sandbox, "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, GUARD, p], cwd=sandbox, capture_output=True, text=True,
                       timeout=60, env=env)
    return r.returncode, (r.stderr or "")


ESCAPES = {
    "shell-out (subprocess)":  "import subprocess\nsubprocess.run(['echo','x'])\n",
    "shell-out (os.system)":   "import os\nos.system('echo x')\n",
    "network egress":          "import socket\nsocket.create_connection(('example.com', 80))\n",
    "home write (the exploit)":"import os\nopen(os.path.expanduser('~/.claude/EVIL'),'w').write('x')\n",
    "wallet/ssh key read":     "import os\nprint(open(os.path.expanduser('~/.ssh/id_ed25519')).read())\n",
    "native FFI (ctypes)":     "import ctypes\nprint(ctypes)\n",
    "out-of-repo write":       "import os\nopen(os.path.expanduser('~/EVIL_crank_probe'),'w').write('x')\n",
}
LEGIT = ("src = open('target.txt').read()\n"
         "open('target.txt', 'w').write(src.replace('a', 'b'))\n"
         "print('patched')\n")


def main():
    with tempfile.TemporaryDirectory() as sandbox:
        for name, src in ESCAPES.items():
            rc, err = run_patch(src, sandbox)
            check("REFUSED at runtime: %s" % name, rc != 0 and "CRANK-VETO" in err)

        # a legitimate repo-editing patch runs, imports work, and the edit lands under the repo
        with open(os.path.join(sandbox, "target.txt"), "w") as fh:
            fh.write("aaa")
        rc, err = run_patch(LEGIT, sandbox)
        edited = open(os.path.join(sandbox, "target.txt")).read()
        check("PASSED: a legitimate repo-editing patch is allowed (rc=0)", rc == 0)
        check("PASSED: the legit patch actually edited the in-repo file", edited == "bbb")

    ok = all(checks)
    print("\n%s  (%d/%d)" % ("PASS" if ok else "FAIL", sum(checks), len(checks)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
