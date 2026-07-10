#!/usr/bin/env python3
"""audit_guard — run an UNTRUSTED crank patch under a RUNTIME veto.

A crank patch runs as a real subprocess with full host rights. The escape used once (write ~/.claude,
read the wallet seed, exfiltrate, shell out) proves a patch can leave the build repo. Inspecting the
patch's SOURCE (AST) for `subprocess`/`os.system`/etc. is theater — the model constructs the call or
path dynamically and walks around the check. This instead installs a `sys.addaudithook` that fires on
the ACTUAL runtime operation, however the source spelled it, and REFUSES anything that:

  - shells out / execs / spawns a process         → the "python, not bash" rule
  - loads native FFI (ctypes) — which could disable this very hook
  - opens a network connection or resolves a host
  - writes / deletes / renames outside the build repo, or touches a sensitive path
    (~/.ssh, ~/.secrets, ~/.claude, wallet/seed material, /etc)

Reads of the stdlib / site-packages are allowed so imports work; bytecode writing is disabled so an
import can't write a .pyc outside the repo. The hook is one-way (addaudithook can't be removed) and is
installed BEFORE the patch runs, so the patch executes fully hooked.

NOT airtight: native code loaded another way, or an interpreter bug, can still escape — the guaranteed
boundary remains the VM. This is the strong in-process approximation that replaces the AST theater.

    python audit_guard.py <patch.py> [args...]      # runs patch.py as __main__ under the veto
env: CRANK_REPO=<repo root>  (defaults to cwd)
"""
import os
import runpy
import sys
import tempfile

sys.dont_write_bytecode = True   # no .pyc writes to site-packages while the hook confines writes

REPO = os.path.realpath(os.environ.get("CRANK_REPO") or os.getcwd())
_TMP = tuple(os.path.realpath(p) for p in {tempfile.gettempdir(), "/tmp", "/private/tmp"})
_WRITE_OK = (REPO,) + _TMP
_SENSITIVE = tuple(os.path.realpath(os.path.expanduser("~/" + n)) for n in
                   (".ssh", ".secrets", ".claude", ".aws", ".gnupg", ".config/jazz", ".jazz")) + \
             ("id_ed25519", "id_rsa", "wallet-seed", "master-seed", "authorized_keys",
              "/etc/", "/private/etc")
# events that mutate the filesystem, and which positional args are paths
_MUTATE = {"os.remove": (0,), "os.unlink": (0,), "os.rmdir": (0,), "os.mkdir": (0,),
           "os.makedirs": (0,), "os.rename": (0, 1), "os.replace": (0, 1), "os.link": (0, 1),
           "os.symlink": (0, 1), "os.chmod": (0,), "os.chown": (0,), "os.truncate": (0,),
           "shutil.rmtree": (0,), "shutil.move": (0, 1), "shutil.copyfile": (0, 1),
           "shutil.copytree": (0, 1), "shutil.copymode": (0, 1), "shutil.copystat": (0, 1)}


class CrankEscape(RuntimeError):
    """A crank patch tried to leave the build repo — refused at runtime."""


def _under(path, roots):
    try:
        rp = os.path.realpath(path)
    except Exception:      # noqa: BLE001
        return False
    return any(rp == r or rp.startswith(r + os.sep) for r in roots)


def _sensitive(path):
    p = str(path)
    rp = os.path.realpath(p)
    return any(s in rp or s in p for s in _SENSITIVE)


def _writing(mode, flags):
    if isinstance(mode, str):
        return any(c in mode for c in "wax+")
    if isinstance(flags, int):
        return bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC))
    return False


def _hook(event, args):
    # 1. shelling out / exec / spawn — the headline "python not bash" rule
    if event in ("os.system", "subprocess.Popen", "os.posix_spawn", "pty.spawn"):
        raise CrankEscape("shelling out is forbidden (%s) — do it in pure python" % event)
    if event.startswith("os.exec") or event.startswith("os.spawn"):
        raise CrankEscape("process exec/spawn is forbidden (%s)" % event)
    # 2. native FFI — could be used to tear the hook out
    if event == "import" and args and str(args[0]).split(".")[0] in ("ctypes", "_ctypes"):
        raise CrankEscape("native FFI import '%s' is forbidden" % args[0])
    if event.startswith("ctypes."):
        raise CrankEscape("ctypes/native is forbidden (%s)" % event)
    # 3. network egress (covers urllib/requests/http — they all connect via socket)
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise CrankEscape("network access is forbidden (%s)" % event)
    # 4. filesystem: reads roam (imports), but sensitive paths and out-of-repo writes are refused
    if event == "open":
        path, mode, flags = (list(args) + [None, None, None])[:3]
        if not isinstance(path, (str, bytes)):
            return
        if _sensitive(path):
            raise CrankEscape("touching a sensitive path is forbidden (%s)" % path)
        if _writing(mode, flags) and not _under(path, _WRITE_OK):
            raise CrankEscape("writing outside the build repo is forbidden (%s)" % path)
    elif event in _MUTATE:
        for i in _MUTATE[event]:
            if i < len(args) and isinstance(args[i], (str, bytes)):
                if _sensitive(args[i]):
                    raise CrankEscape("mutating a sensitive path is forbidden (%s: %s)" % (event, args[i]))
                if not _under(args[i], _WRITE_OK):
                    raise CrankEscape("mutating outside the build repo is forbidden (%s: %s)" % (event, args[i]))


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: audit_guard.py <patch.py> [args...]\n")
        return 2
    patch = argv[1]
    sys.argv = [patch] + list(argv[2:])
    sys.addaudithook(_hook)      # one-way; installed before the patch runs
    try:
        runpy.run_path(patch, run_name="__main__")
    except CrankEscape as e:
        sys.stderr.write("CRANK-VETO: %s\n" % e)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
