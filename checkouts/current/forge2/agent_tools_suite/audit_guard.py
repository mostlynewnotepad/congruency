#!/usr/bin/env python3
"""forge2 / agent_tools_suite / audit_guard — a behavior-preserving rewrite of the forge unit
`agent_tools_suite:audit_guard.py` (module key forge-rw:d654dce464c49da7, git blob
a8ac29e086c136b9b36904a1896caa3ae9c19cfc, 5121 bytes), filed under ticket #415 against the
FORGE-wide refactor standard #200.

WHAT THIS IS
------------
The original unit runs an UNTRUSTED "crank patch" — a Python file written by a model — under a
RUNTIME veto. It installs a `sys.addaudithook` (see TERMS) and refuses, at the moment the real
operation happens, anything that shells out, execs or spawns a process; imports native FFI
(`ctypes`), which could switch the hook off; opens a network connection or resolves a host; or
writes, deletes or renames outside the build repo or at a sensitive path. Reads of the stdlib are
allowed so imports work.

Its central idea is worth stating because this rewrite preserves it exactly: inspecting the
patch's SOURCE is theater, because the model can build the call dynamically and walk around it. The
hook fires on the ACTUAL runtime operation, however the source spelled it.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and it adds the three things #200 requires that the original
lacked: it is a proper installable package, it is driven by a configuration object, and it refuses
to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    _under(path, roots)      -> bool   is `path` inside one of `roots`?
    _sensitive(path)         -> bool   does `path` name something secret?
    _writing(mode, flags)    -> bool   does this `open` intend to write?
    _hook(event, args)       -> None   the audit hook itself; raises CrankEscape to veto
    main(argv=None)          -> int    the CLI: run a patch under the veto

`CrankEscape` (the veto exception) is also part of the contract, since `main` returns 3 when one
escapes the patch, and callers catch it.

`main` carries the surface's ONE deviation, and it is an ADDITION: the original's signature was
`main(argv)`, and `argv` here is still the same positional parameter, so every existing caller —
`main(sys.argv)` — is untouched. It gained a default because #200 requirement 3 asks for a console
entry point and the generated entry point calls `main()` with no arguments; `None` means
`sys.argv`. Without the default the console script this ticket requires would raise TypeError on
every invocation. `selftest` asserts both the signature and that `main([])` still answers 2.

TERMS USED HERE
---------------
audit hook
    A function registered with `sys.addaudithook`. CPython calls it on every "audit event" — a
    named runtime operation like `open`, `os.system` or `socket.connect` — with the event name and
    that event's arguments. A hook that RAISES aborts the operation. Registration is ONE-WAY: a hook
    cannot be removed for the life of the process. That single fact drives this module's design; see
    WHY THE POLICY IS PRE-RESOLVED.
crank patch
    The untrusted Python file this tool runs, as `__main__`, under the veto.
build repo
    The one directory tree the patch may write to. The original found it in the `CRANK_REPO`
    environment variable, falling back to the current directory; here the variable's NAME is config
    (`repo_env`), because a hardcoded environment-variable name is exactly the hardcoded param #200
    forbids.
registry / config object
    The JSON configuration registry described in this repository's `note-for-claude`: one `.json`
    file holding the configuration for every tool in a set of packaging. `note-for-claude` states
    the contract this module obeys — "if a tool cannot see the registry it will throw an exeption"
    [sic]. The "config object" is this unit's own `forge2.agent_tools_suite.audit_guard` section of
    it. THIS package ships a `registry.json` beside this file; see CONFIGURATION.
policy
    The config object, resolved and compiled into the concrete roots, path sets and event tables the
    hook consults. Built once, then cached. `show-policy` prints it.
veto
    A refusal. The hook raises `CrankEscape`; the operation never happens; `main` reports
    `CRANK-VETO: <reason>` and exits 3.

WHY THE POLICY IS PRE-RESOLVED (the one design constraint that shapes this file)
-------------------------------------------------------------------------------
`sys.addaudithook` is one-way, and the hook is called for `open`. So a config-gated hook that
resolved its config LAZILY — on first use, the obvious pattern and the one this package's sibling
units use — would, on its first event, open its registry to find out what to do, and that `open`
would re-enter the hook, which would open the registry again, forever. This is not theoretical:
`python3 -c` proof of the re-entry is in this ticket's build record; one `open()` re-entered a
lazily-resolving hook 6 times before the guard rail stopped it, and would otherwise have ended in
`RecursionError` inside an audit hook, i.e. inside an arbitrary victim operation.

Therefore `main()` fully resolves the config and compiles the policy BEFORE it calls
`sys.addaudithook`, and `_hook` only ever reads the already-compiled policy — it never touches the
disk. `install_hook()` enforces this ordering for any caller that installs the hook itself, and
then PINS the compiled policy: from that moment `_hook` consults only the pinned object, so no
later `reset_config()` or `configure()` can send the live veto back to a file (re-entering the hook
from inside itself) or quietly weaken a guard that is already running. A `ConfigError` is
consequently reported cleanly, by a process that has NOT installed an irremovable hook and has NOT
run the patch. `selftest` proves the pinning by resetting the config layer from inside a running
patch and requiring the veto to survive.

Pinning is also the closer match to the original, whose hook consulted module constants computed
once, at import, and never moved again.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
Every path, every environment-variable name and every event table the original hardcoded is now a
config key. The unit resolves its config object from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. This file holds the unit config
     object itself — exactly what `emit-config` prints.
  2. otherwise, the `forge2.agent_tools_suite.audit_guard` section of the nearest `registry.json`
     found by walking UP from THIS FILE's directory.

If NEITHER answers, the unit raises `ConfigError` and vetoes nothing — it never guesses a default.
That is `note-for-claude`'s rule and this ticket's acceptance item (d). A config object that is
found but is missing a key an operation needs is also a `ConfigError`, naming the key.

This package ships `registry.json` NEXT TO this file, so source 2 answers and the guard works from a
clean checkout with no setup. That shipped registry is the config object this unit runs on; it is
not a fallback baked into the code. Its values are exactly the original's hardcoded ones, which is
what makes this rewrite behavior-preserving in its shipped configuration. Delete it (with
`FORGE2_CONFIG` unset and no other `registry.json` above this directory) and the unit throws — the
gate is in the code, not in the file's presence. `selftest` proves the gate directly, without
deleting anything, by pointing `FORGE2_CONFIG` at a file that does not exist.

The config keys, and the original's value for each:

    repo_env             "CRANK_REPO"   env var naming the build repo; empty/unset -> cwd
    write_roots          ["${repo}", "${tempdir}", "/tmp", "/private/tmp"]
                         Roots the patch may write to. `${repo}` expands to the build repo and
                         `${tempdir}` to `tempfile.gettempdir()`; `~` expands; each is realpath'd.
    sensitive_paths      ["~/.ssh", "~/.secrets", "~/.claude", "~/.aws", "~/.gnupg",
                          "~/.config/jazz", "~/.jazz"]
                         Secret locations. `~` expands and each is realpath'd.
    sensitive_substrings ["id_ed25519", "id_rsa", "wallet-seed", "master-seed",
                          "authorized_keys", "/etc/", "/private/etc"]
                         Matched as raw substrings, NOT expanded and NOT realpath'd. The two lists
                         are distinct because the original treated them differently, and the
                         difference is load-bearing: realpath'ing "/etc/" would turn it into
                         "/private/etc" on macOS and stop it matching "/etc/passwd" literally.
    shell_events         ["os.system", "subprocess.Popen", "os.posix_spawn", "pty.spawn"]
    exec_event_prefixes  ["os.exec", "os.spawn"]
    ffi_import_roots     ["ctypes", "_ctypes"]      first dotted component of a vetoed import
    ffi_event_prefixes   ["ctypes."]
    network_events       ["socket.connect", "socket.getaddrinfo"]
    mutate_events        {"os.remove": [0], ... }   event -> the arg indexes that are paths
    write_mode_chars     "wax+"                     any of these in a string mode means "writing"
    write_flag_names     ["O_WRONLY", "O_RDWR", "O_CREAT", "O_APPEND", "O_TRUNC"]
                         Names looked up on `os` and OR'd into the mask tested against int flags.
                         Names, not numbers, so the mask stays correct across platforms.
    dont_write_bytecode  true                       see THE ONE DEVIATION below
    bug_reports          "logs/bug_reports.jsonl"   infrastructure; see SIDE EFFECTS

WHAT IS *NOT* CONFIG, AND WHY
-----------------------------
#200 requires no hardcoded paths or params. It does not require inventing knobs the unit never had,
and a "knob" that changes what the code means is not a setting:

  * The event names `"open"` and `"import"` stay in the code. They are not policy — they are the
    CPython events whose ARGUMENTS this module unpacks (`open` gives `(path, mode, flags)`), so the
    unpacking is written for those two events specifically and a different name would be
    meaningless. Which events are REFUSED is policy, and all of that is config.
  * The veto messages stay in the code. They are the behavior this ticket preserves — the
    exemplars assert them verbatim — not settings.
  * The structure of the checks (their ORDER, and which check wins) is the unit's definition.

THE ONE DEVIATION, STATED PLAINLY
---------------------------------
The original set `sys.dont_write_bytecode = True` at IMPORT time, as a module-level statement. This
rewrite sets it from the config key `dont_write_bytecode`, inside `install_hook()`, immediately
before the hook goes up. It cannot be done at import: reading config at import would either
hardcode the value (breaking requirement 4) or make the module unimportable without a registry.

For the documented entry path this is EXACTLY equivalent, and the equivalence is not an argument
but a fact about the code: nothing runs between importing this module and `main()` calling
`install_hook()`, so the flag is `True` before `runpy.run_path` executes the patch either way, which
is the only thing the flag exists to affect (it stops an import inside the patch writing a `.pyc`
that the hook would then veto). `selftest` proves it in a subprocess, by asserting the patch itself
observes `sys.dont_write_bytecode is True`.

The one case that differs: a caller that merely does `import audit_guard` as a library, and expects
the import alone to have flipped the interpreter flag, no longer gets that. Such a caller is
importing a module and using none of it; the flag is now tied to installing the veto, which is what
it is for. `set_dont_write_bytecode()` is exported for a caller that wants it without the hook.

RUNNING IT
----------
Every command below is executable as written from this file's own directory; from anywhere else,
give the full path to `audit_guard.py` instead of the bare name.

    python3 audit_guard.py run <patch.py> [args...]   # run patch.py as __main__ under the veto
    python3 audit_guard.py <patch.py> [args...]       # the ORIGINAL's spelling; identical
    python3 audit_guard.py selftest                   # prove the exemplars, the edges, the gate
    python3 audit_guard.py emit-config                # print a config-object template
    python3 audit_guard.py show-config                # print the resolved config + where it came from
    python3 audit_guard.py show-policy                # print the compiled policy

The original's CLI took the patch path as the first argument and had no subcommands, so
`audit_guard.py <patch.py>` MUST keep working: it is the invocation the original documents and the
one `crank_discipline.run_confined` spells. It does. The `run` subcommand is an explicit alias for
it, and the other subcommands are new. Any first argument that is not one of the reserved
subcommand names is treated as a patch path, exactly as before — so a patch named `selftest.py` is
still a patch (the reserved words have no `.py`), while a file literally named `selftest` would need
the `run` form. `main` returns the process exit code:

    0  the patch ran to completion            2  usage: no patch named
    3  the patch was VETOED                   4  no config object (nothing was installed or run)

Exit codes 0, 2 and 3 are the original's, unchanged. 4 is new and cannot collide with the
original's meanings, because the original had no config to be missing.

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, and the package is committed in full
beside it — `pyproject.toml`, `__init__.py`, `registry.json`, all DERIVED from the modules present
by `congruency/tools/forge_package.py` (#410), never hand-authored. From THIS file's directory:

    pip install -e .
    forge2-audit-guard run patch.py

`pyproject.toml` maps this directory onto the import package `agent_tools_suite`, so an installed
copy imports as `from agent_tools_suite.audit_guard import main`, and declares the
`forge2-audit-guard` console script pointing at `main()` below. `registry.json` is package-data, so
it lands NEXT TO this module on a non-editable install too and the walk-up in (2) still finds it.

SIDE EFFECTS
------------
Importing this module touches nothing — no config read, no interpreter flag, no file. `_under`,
`_sensitive`, `_writing`, `_hook`, `selftest`, `emit-config`, `show-config` and `show-policy` create
no files and write nothing.

`install_hook()` and therefore `main`'s run path DO change the interpreter, irreversibly and on
purpose: they set `sys.dont_write_bytecode` and install an audit hook that cannot be removed. That
is the tool's whole function. `main` also rebinds `sys.argv` for the patch, as the original did.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception is
thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path if it hits an
UNEXPECTED exception — a defect in this tool. A `ConfigError` is designed behavior, not a bug, and
neither is a `CrankEscape` (that is the tool WORKING); neither files a report. An exception raised
by the patch itself is the PATCH's, not this tool's: it propagates exactly as the original let it
propagate, and files no report.
"""

import contextlib
import json
import os
import runpy
import sys
import tempfile
import traceback
from datetime import datetime

__all__ = [
    "CrankEscape", "ConfigError",
    "_under", "_sensitive", "_writing", "_hook", "main",
    "install_hook", "run_patch", "set_dont_write_bytecode",
    "load_config", "configure", "using_config", "reset_config", "config_template",
    "active_config", "active_source", "active_base", "active_policy", "build_policy",
    "find_registry", "selftest",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in the
#: config document, not a configurable setting — a config-driven tool has to know which section is
#: its own.
UNIT_PATH = ("forge2", "agent_tools_suite", "audit_guard")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:agent_tools_suite/audit_guard"

#: Exit codes. 0/2/3 are the original's; 4 is new — see the module docstring, RUNNING IT.
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_VETO = 3
EXIT_NO_CONFIG = 4

#: The audit events whose ARGUMENTS this module unpacks. Not policy — see the module docstring,
#: WHAT IS *NOT* CONFIG, AND WHY.
OPEN_EVENT = "open"
IMPORT_EVENT = "import"

#: Reserved first arguments. Any OTHER first argument is a patch path, which is how the original's
#: CLI spelled it and what `crank_discipline.run_confined` calls. The reserved words carry no `.py`,
#: so a patch file keeps working under its own name; a file literally named `selftest` needs the
#: `run` form.
_COMMANDS = ("run", "selftest", "emit-config", "show-config", "show-policy", "-h", "--help")


class CrankEscape(RuntimeError):
    """A crank patch tried to leave the build repo — refused at runtime.

    Raised from inside the audit hook, so it aborts the very operation that tripped it. `main`
    catches it around the patch and exits 3.
    """


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that cannot
    see its config throws rather than guessing a default. It is NOT a `CrankEscape`: nothing was
    vetoed, because nothing was ever guarded.
    """


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None      # config object injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution, so the hook re-reads no files
_POLICY = None      # the compiled policy, cached: see WHY THE POLICY IS PRE-RESOLVED
_INSTALLED = None   # the policy PINNED by install_hook(); once set, `_hook` reads only this


def find_registry(start=None):
    """Walk UP from `start` (default: this file's directory) and return the nearest registry path,
    or None if the walk reaches the filesystem root without finding one.

    Starting at THIS FILE, never at the working directory, is deliberate: the guard's policy must
    not change because a patch was launched from somewhere else. `registry.json` ships as
    package-data, so on a non-editable install it sits in this same directory and the first
    iteration finds it.
    """
    directory = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))
    while True:
        candidate = os.path.join(directory, REGISTRY_NAME)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def _read_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise ConfigError("%s at %s could not be read as JSON: %s" % (what, path, exc)) from exc


def load_config(start=None):
    """Resolve this unit's config object from disk, ignoring any injected config.

    Returns a `(config, base, source)` triple: the config object, the directory that relative paths
    inside it resolve against, and a human-readable description of where it came from. `start`
    overrides the directory the registry walk-up begins at.

    Raises:
        ConfigError: if no config object can be found, naming both sources that were tried.
    """
    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        if not os.path.isfile(env_path):
            raise ConfigError("%s is set to %r, but no such file exists" % (CONFIG_ENV, env_path))
        config = _read_json(env_path, "the config object named by " + CONFIG_ENV)
        if not isinstance(config, dict):
            raise ConfigError("the config object at %s must be a JSON object, not %s"
                              % (env_path, type(config).__name__))
        return config, os.path.dirname(os.path.abspath(env_path)), "%s=%s" % (CONFIG_ENV, env_path)

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s: %s is unset and no %s was found by walking up from %s. Run "
            "`emit-config` for a template of the config object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))))

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. Run "
                "`emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH)))
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError("the registry section %s at %s must be a JSON object, not %s"
                          % (".".join(UNIT_PATH), registry_path, type(node).__name__))

    config = dict(node)
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit section
    # may state its own to override it. This is inheritance inside one config document, not a
    # guessed default.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


def active_config():
    """Return the config object in force: the injected one, else the disk resolution.

    Raises:
        ConfigError: if there is no config object to be had.
    """
    global _RESOLVED
    if _ACTIVE is not None:
        return _ACTIVE[0]
    if _RESOLVED is None:
        _RESOLVED = load_config()
    return _RESOLVED[0]


def active_source():
    """Describe where the config object in force came from."""
    if _ACTIVE is not None:
        return _ACTIVE[2]
    active_config()
    return _RESOLVED[2]


def active_base():
    """Return the directory that relative paths in the config resolve against."""
    if _ACTIVE is not None:
        return _ACTIVE[1]
    active_config()
    return _RESOLVED[1]


def configure(config, base=None, source="injected via configure()"):
    """Inject `config` as the config object for this process; return the previous state.

    `base` is the directory relative paths in `config` resolve against, and defaults to the current
    working directory. Pass `None` as `config` to drop the injection and go back to resolving from
    disk. The compiled policy is dropped, so the next use recompiles.
    """
    global _ACTIVE, _POLICY
    previous = _ACTIVE
    if config is None:
        _ACTIVE = None
    else:
        if not isinstance(config, dict):
            raise ConfigError("a config object must be a dict, not %s" % type(config).__name__)
        _ACTIVE = (config, base or os.getcwd(), source)
    _POLICY = None
    return previous


@contextlib.contextmanager
def using_config(config, base=None):
    """Use `config` as the config object for the duration of the `with` block."""
    previous = configure(config, base=base)
    try:
        yield config
    finally:
        global _ACTIVE, _POLICY
        _ACTIVE = previous
        _POLICY = None


def reset_config():
    """Drop the injected config, the cached disk resolution and the compiled policy."""
    global _ACTIVE, _RESOLVED, _POLICY
    _ACTIVE = None
    _RESOLVED = None
    _POLICY = None


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do the unit throws. The values are the ORIGINAL unit's
    hardcoded ones, so a registry built from this template makes this rewrite behave exactly like
    the module it replaces.
    """
    return {
        "repo_env": "CRANK_REPO",
        "write_roots": ["${repo}", "${tempdir}", "/tmp", "/private/tmp"],
        "sensitive_paths": ["~/.ssh", "~/.secrets", "~/.claude", "~/.aws", "~/.gnupg",
                            "~/.config/jazz", "~/.jazz"],
        "sensitive_substrings": ["id_ed25519", "id_rsa", "wallet-seed", "master-seed",
                                 "authorized_keys", "/etc/", "/private/etc"],
        "shell_events": ["os.system", "subprocess.Popen", "os.posix_spawn", "pty.spawn"],
        "exec_event_prefixes": ["os.exec", "os.spawn"],
        "ffi_import_roots": ["ctypes", "_ctypes"],
        "ffi_event_prefixes": ["ctypes."],
        "network_events": ["socket.connect", "socket.getaddrinfo"],
        "mutate_events": {
            "os.remove": [0], "os.unlink": [0], "os.rmdir": [0], "os.mkdir": [0],
            "os.makedirs": [0], "os.rename": [0, 1], "os.replace": [0, 1], "os.link": [0, 1],
            "os.symlink": [0, 1], "os.chmod": [0], "os.chown": [0], "os.truncate": [0],
            "shutil.rmtree": [0], "shutil.move": [0, 1], "shutil.copyfile": [0, 1],
            "shutil.copytree": [0, 1], "shutil.copymode": [0, 1], "shutil.copystat": [0, 1],
        },
        "write_mode_chars": "wax+",
        "write_flag_names": ["O_WRONLY", "O_RDWR", "O_CREAT", "O_APPEND", "O_TRUNC"],
        "dont_write_bytecode": True,
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────────────── the compiled policy ───────────────────────────────

def _require(config, key, types, what):
    """Return `config[key]`, checking its type. A missing or mistyped key is a ConfigError naming
    the key — never a silent default."""
    if key not in config:
        raise ConfigError("config object for %s is missing the required key %r (%s). Run "
                          "`emit-config` for a template." % (UNIT, key, what))
    value = config[key]
    if not isinstance(value, types):
        names = types.__name__ if isinstance(types, type) else "/".join(t.__name__ for t in types)
        raise ConfigError("config key %r for %s must be %s, not %s"
                          % (key, UNIT, names, type(value).__name__))
    return value


def _require_str_list(config, key, what):
    """Return `config[key]` as a tuple of str, or raise ConfigError naming the offending element."""
    value = _require(config, key, list, what)
    for element in value:
        if not isinstance(element, str):
            raise ConfigError("config key %r for %s must be a list of strings; it contains %r (%s)"
                              % (key, UNIT, element, type(element).__name__))
    return tuple(value)


def _expand_root(token, repo):
    """Expand one `write_roots` entry: `${repo}` and `${tempdir}` first, then `~`, then realpath.

    `${tempdir}` is `tempfile.gettempdir()`, which the ORIGINAL called at import; keeping it a token
    rather than freezing today's value into the config preserves that — the temp dir follows
    `TMPDIR`, so a frozen literal would be wrong for any process that sets it.
    """
    text = token.replace("${repo}", repo).replace("${tempdir}", tempfile.gettempdir())
    return os.path.realpath(os.path.expanduser(text))


def _dedup(items):
    """Order-preserving dedup. The original built its temp roots through a `set`, so its
    `_WRITE_OK` element ORDER was hash-randomized per process and its realpath'd contents could
    repeat (on macOS `/tmp` and `/private/tmp` both realpath to `/private/tmp`). Neither was ever a
    contract — the roots are only ever consumed by `any()` in `_under` — so this dedups and keeps a
    deterministic order. `_under` is proven to agree with the original on every input regardless.
    """
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return tuple(out)


class _Policy(object):
    """The config object, compiled into what `_hook` actually consults.

    Compiled ONCE and cached, then read-only. `__slots__` because the hook touches this on every
    audit event in the interpreter, which is as hot as code gets.
    """

    __slots__ = ("repo", "tmp_roots", "write_roots", "sensitive", "mutate", "shell_events",
                 "exec_prefixes", "ffi_import_roots", "ffi_prefixes", "network_events",
                 "mode_chars", "flag_mask", "dont_write_bytecode")

    def as_dict(self):
        """A JSON-able view of the compiled policy, for `show-policy`."""
        return {
            "repo": self.repo,
            "tmp_roots": list(self.tmp_roots),
            "write_roots": list(self.write_roots),
            "sensitive": list(self.sensitive),
            "mutate": {event: list(indexes) for event, indexes in sorted(self.mutate.items())},
            "shell_events": sorted(self.shell_events),
            "exec_prefixes": list(self.exec_prefixes),
            "ffi_import_roots": sorted(self.ffi_import_roots),
            "ffi_prefixes": list(self.ffi_prefixes),
            "network_events": sorted(self.network_events),
            "mode_chars": self.mode_chars,
            "flag_mask": self.flag_mask,
            "dont_write_bytecode": self.dont_write_bytecode,
        }


def build_policy(config):
    """Compile a config object into a `_Policy`. Pure with respect to the filesystem except for the
    environment/cwd lookup that finds the build repo and the temp dir, exactly as the original's
    module-level code did.

    Raises:
        ConfigError: naming the first key that is missing or malformed.
    """
    policy = _Policy()

    repo_env = _require(config, "repo_env", str, "environment variable naming the build repo")
    # The original: REPO = realpath(environ.get("CRANK_REPO") or getcwd()). `or` means an EMPTY
    # value falls back to the cwd too, not just an unset one; preserved here.
    policy.repo = os.path.realpath(os.environ.get(repo_env) or os.getcwd())

    roots = _require_str_list(config, "write_roots", "roots the patch may write to")
    expanded = tuple(_expand_root(token, policy.repo) for token in roots)
    policy.write_roots = _dedup(expanded)
    policy.tmp_roots = _dedup(tuple(root for token, root in zip(roots, expanded)
                                    if "${repo}" not in token))

    sensitive_paths = _require_str_list(config, "sensitive_paths", "secret locations")
    sensitive_substrings = _require_str_list(config, "sensitive_substrings",
                                             "raw substrings that mark a path secret")
    # Two different treatments, exactly as the original had them: the paths are expanded and
    # realpath'd, the substrings are used verbatim. See the module docstring.
    policy.sensitive = (tuple(os.path.realpath(os.path.expanduser(p)) for p in sensitive_paths)
                        + tuple(sensitive_substrings))

    policy.shell_events = frozenset(_require_str_list(config, "shell_events",
                                                      "events that shell out"))
    policy.exec_prefixes = _require_str_list(config, "exec_event_prefixes",
                                             "event prefixes that exec/spawn a process")
    policy.ffi_import_roots = frozenset(_require_str_list(config, "ffi_import_roots",
                                                          "vetoed import roots"))
    policy.ffi_prefixes = _require_str_list(config, "ffi_event_prefixes", "vetoed event prefixes")
    policy.network_events = frozenset(_require_str_list(config, "network_events",
                                                        "events that touch the network"))

    mutate = _require(config, "mutate_events", dict, "event -> the arg indexes that are paths")
    compiled = {}
    for event, indexes in mutate.items():
        if not isinstance(event, str):
            raise ConfigError("config key 'mutate_events' for %s must be keyed by event name "
                              "strings; got %r" % (UNIT, event))
        if not isinstance(indexes, (list, tuple)) or not all(
                isinstance(i, int) and not isinstance(i, bool) for i in indexes):
            raise ConfigError("config key 'mutate_events' for %s maps %r to %r; it must map each "
                              "event to a list of integer argument indexes" % (UNIT, event, indexes))
        compiled[event] = tuple(indexes)
    policy.mutate = compiled

    policy.mode_chars = _require(config, "write_mode_chars", str,
                                 "characters in a string mode that mean 'writing'")

    mask = 0
    for name in _require_str_list(config, "write_flag_names",
                                  "names of the os.O_* flags that mean 'writing'"):
        flag = getattr(os, name, None)
        if not isinstance(flag, int) or isinstance(flag, bool):
            raise ConfigError("config key 'write_flag_names' for %s names %r, which is not an "
                              "integer flag on the os module of this platform" % (UNIT, name))
        mask |= flag
    policy.flag_mask = mask

    policy.dont_write_bytecode = _require(config, "dont_write_bytecode", bool,
                                          "whether installing the hook also disables .pyc writes")
    return policy


def active_policy():
    """Return the compiled policy in force, compiling and caching it on first use.

    Raises:
        ConfigError: if there is no config object, or it is malformed.
    """
    global _POLICY
    if _POLICY is None:
        _POLICY = build_policy(active_config())
    return _POLICY


def _policy_in_force():
    """The policy the LIVE veto consults — `_hook` and the two helpers it calls.

    Once `install_hook()` has pinned a policy, that pinned object is the only thing consulted, and
    the config layer is never touched again. This is what makes `_hook`'s "never reads the disk"
    promise structural instead of a convention every caller has to respect: after the veto is live,
    neither `reset_config()` nor a `configure()` can send it back to a file — which would re-enter
    the hook from inside itself — or quietly weaken a running guard.

    It is also the closer match to the original, whose hook consulted module constants that were
    computed once, at import, and never moved again.

    Uninstalled — direct calls, and every test in this module — it resolves through the config
    layer, so the #200 requirement-4 gate still applies and `ConfigError` is still raised.
    """
    return _INSTALLED if _INSTALLED is not None else active_policy()


# The original exposed its resolved policy as module-level constants. Callers that read them keep
# working: PEP 562 resolves these lazily, from the config, on attribute access — which is what lets
# the module import with no config at all while still throwing for anyone who asks for a value it
# would have had to guess.
_LAZY_ATTRS = {
    "REPO": lambda p: p.repo,
    "_TMP": lambda p: p.tmp_roots,
    "_WRITE_OK": lambda p: p.write_roots,
    "_SENSITIVE": lambda p: p.sensitive,
    "_MUTATE": lambda p: dict(p.mutate),
}


def __getattr__(name):
    """Resolve the original's module-level policy constants on demand (PEP 562)."""
    if name in _LAZY_ATTRS:
        return _LAZY_ATTRS[name](active_policy())
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(list(globals()) + list(_LAZY_ATTRS))


# ─────────────────────────────── the unit itself ───────────────────────────────

def _under(path, roots):
    """True if `path` is one of `roots` or lives inside one of them.

    Takes its roots as an argument and reads no config, exactly as the original did — it is the one
    function here that needs none.

    `path` is realpath'd first, so symlinks cannot smuggle a write out of the repo; a realpath that
    raises (a path with an embedded NUL, say) is answered False rather than propagating, which is
    the original's `except Exception: return False`. Note that ONLY the realpath is guarded: a
    `bytes` path realpaths fine and then raises TypeError from `startswith` against `str` roots.
    That is the original's behavior and it is preserved deliberately — see `_hook`.
    """
    try:
        real = os.path.realpath(path)
    except Exception:      # noqa: BLE001 — the original swallows everything realpath can raise
        return False
    return any(real == root or real.startswith(root + os.sep) for root in roots)


def _sensitive(path):
    """True if `path` names something secret, per the config's `sensitive_paths` and
    `sensitive_substrings`.

    A rule matches if it appears in the REALPATH of `path` or in `path` as written — so both
    `~/.ssh/id_rsa` (via the literal substring `id_rsa`) and a symlink pointing into `~/.ssh` (via
    the realpath) are caught.

    Two faithfulness notes:
      * The realpath is computed INSIDE the `any()`, once per rule, exactly as the original wrote
        it, rather than hoisted out and computed once. Hoisting is the obvious optimisation and it
        is TEMPTING: with the shipped config the two are indistinguishable, because the rule set is
        never empty and the realpath's value and exceptions are identical either way. It is kept
        faithful for the case config now makes reachable and the original could not: an EMPTY rule
        set short-circuits `any()` before the first realpath, so `_sensitive("\\0")` returns False
        where a hoisted realpath would raise ValueError. `selftest` covers exactly that, since a
        differential against the original cannot reach it.
      * `str(path)` is applied to whatever it is handed, so a `bytes` path becomes the STRING
        `"b'/etc/passwd'"` — quotes, `b` prefix and all — and is matched in that form. That is why
        `b'/etc/passwd'` is still caught (it contains `/etc/`) while the realpath of that mangled
        string is resolved against the cwd. Preserved as-is.

    Raises:
        ConfigError: if there is no config object.
        ValueError: from realpath, for a path containing an embedded NUL (as the original did).
    """
    sensitive = _policy_in_force().sensitive
    text = str(path)
    return any(s in os.path.realpath(text) or s in text for s in sensitive)


def _writing(mode, flags):
    """True if an `open` described by `mode`/`flags` intends to write.

    A string `mode` is checked for any of the config's `write_mode_chars`; otherwise an int `flags`
    is masked with the config's `write_flag_names`. The precedence is the original's and it is
    visible: a string mode WINS, so `_writing("r", os.O_WRONLY)` is False. Because `bool` is a
    subclass of `int`, `_writing(None, True)` is True — `True & os.O_WRONLY` is 1. Anything else is
    False.

    Raises:
        ConfigError: if there is no config object.
    """
    policy = _policy_in_force()
    if isinstance(mode, str):
        return any(c in mode for c in policy.mode_chars)
    if isinstance(flags, int):
        return bool(flags & policy.flag_mask)
    return False


def _hook(event, args):
    """The audit hook. Returns None to allow the operation; raises `CrankEscape` to veto it.

    CPython calls this for every audit event once `install_hook()` has run. The checks are applied
    in the original's order, which matters wherever an event could match two rules: the reported
    reason is the first that fires.

      1. `shell_events`                          -> shelling out
      2. any `exec_event_prefixes` prefix        -> process exec/spawn
      3. an `import` whose first dotted component is in `ffi_import_roots` -> native FFI
      4. any `ffi_event_prefixes` prefix         -> ctypes/native
      5. `network_events`                        -> network access
      6. `open`   -> vetoed if the path is sensitive, or if it is a write outside `write_roots`
      7. `mutate_events` -> vetoed if any of the event's path arguments is sensitive or outside

    Everything else is allowed, which is what lets the patch import from the stdlib and read.

    This function reads the ALREADY-COMPILED policy and never touches the disk. It must not: it is
    called for `open`, so a hook that read its own config here would re-enter itself forever. See
    the module docstring, WHY THE POLICY IS PRE-RESOLVED.

    Two preserved sharp edges, both verified against the original rather than reasoned about:
      * A `bytes` path in a WRITE position raises `TypeError` out of `_under`, not `CrankEscape` —
        the operation is still aborted (an audit hook that raises anything aborts its event), but
        the exception differs. `main` does not catch it, so it surfaces as the patch's traceback.
      * A `bytes` module name escapes check 3 entirely: `str(b"ctypes").split(".")[0]` is
        `"b'ctypes'"`, which is not in `ffi_import_roots`. The import proceeds.
    Both are the original's behavior. This is a rewrite, not a repair: changing either would be a
    silent policy change in a security tool, which is the last place to slip one in.

    Raises:
        CrankEscape: to veto the operation.
        ConfigError: if there is no config object AND the hook is not installed (see below).
    """
    policy = _policy_in_force()
    if event in policy.shell_events:
        raise CrankEscape(f"shelling out is forbidden ({event}) — do it in pure python")
    if any(event.startswith(prefix) for prefix in policy.exec_prefixes):
        raise CrankEscape(f"process exec/spawn is forbidden ({event})")
    if event == IMPORT_EVENT and args and str(args[0]).split(".")[0] in policy.ffi_import_roots:
        raise CrankEscape(f"native FFI import '{args[0]}' is forbidden")
    if any(event.startswith(prefix) for prefix in policy.ffi_prefixes):
        raise CrankEscape(f"ctypes/native is forbidden ({event})")
    if event in policy.network_events:
        raise CrankEscape(f"network access is forbidden ({event})")
    if event == OPEN_EVENT:
        path, mode, flags = (list(args) + [None, None, None])[:3]
        if not isinstance(path, (str, bytes)):
            return
        if _sensitive(path):
            raise CrankEscape(f"touching a sensitive path is forbidden ({path})")
        if _writing(mode, flags) and not _under(path, policy.write_roots):
            raise CrankEscape(f"writing outside the build repo is forbidden ({path})")
    elif event in policy.mutate:
        for index in policy.mutate[event]:
            if index < len(args) and isinstance(args[index], (str, bytes)):
                if _sensitive(args[index]):
                    raise CrankEscape(
                        f"mutating a sensitive path is forbidden ({event}: {args[index]})")
                if not _under(args[index], policy.write_roots):
                    raise CrankEscape(
                        f"mutating outside the build repo is forbidden ({event}: {args[index]})")


# ─────────────────────────────── installing the veto ───────────────────────────────

def set_dont_write_bytecode(value=True):
    """Set `sys.dont_write_bytecode`, so an import cannot write a `.pyc` the hook would then veto.

    The original did this at import time; this rewrite does it from config, in `install_hook()`.
    Exported for a caller that wants the flag without the hook. See the module docstring, THE ONE
    DEVIATION.
    """
    sys.dont_write_bytecode = bool(value)


def install_hook():
    """Compile the policy, apply `dont_write_bytecode`, and install `_hook`. Returns the policy.

    IRREVERSIBLE, and the ordering is the point: the policy is fully compiled BEFORE the hook goes
    up, so `_hook` never has to read a file — a read that would re-enter the hook it is running
    inside. A `ConfigError` therefore leaves the process exactly as it was found: no hook, no flag,
    nothing run.

    Raises:
        ConfigError: if there is no config object, or it is malformed.
    """
    global _INSTALLED
    policy = active_policy()          # resolve EVERYTHING first — see the docstring above
    set_dont_write_bytecode(policy.dont_write_bytecode)
    _INSTALLED = policy               # pin it BEFORE the hook can fire; see _policy_in_force
    sys.addaudithook(_hook)           # one-way; installed before the patch runs
    return policy


def run_patch(patch, patch_argv):
    """Run `patch` as `__main__` under the veto, with `sys.argv` set to `[patch] + patch_argv`.

    Returns the process exit code: 0 if the patch ran to completion, 3 if it was vetoed. Every
    OTHER exception the patch raises propagates untouched, exactly as the original let it — a
    patch that raises is the patch's business, and a `SystemExit` from the patch must stay a
    `SystemExit` so the caller sees the code the patch chose.
    """
    sys.argv = [patch] + list(patch_argv)
    install_hook()
    try:
        runpy.run_path(patch, run_name="__main__")
    except CrankEscape as escape:
        sys.stderr.write(f"CRANK-VETO: {escape}\n")
        return EXIT_VETO
    return EXIT_OK


def _plan(argv):
    """Decide what `main` should do, and resolve the config while it still can fail cleanly.

    Returns `("exit", code)` for anything handled here, or `("run", [patch, *args])` for a patch to
    be run — deliberately WITHOUT running it, so that `main` can run the patch outside its own
    error handling. Everything that can raise a `ConfigError` happens here.
    """
    if len(argv) < 2:
        sys.stderr.write("usage: audit_guard.py <patch.py> [args...]\n")
        return "exit", EXIT_USAGE

    command = argv[1]
    rest = argv[2:]
    if command not in _COMMANDS:
        command, rest = "run", argv[1:]          # the original's spelling: argv[1] IS the patch

    if command in ("-h", "--help"):
        _print_help()
        return "exit", EXIT_OK

    if command == "emit-config":
        print(json.dumps(config_template(), indent=2))
        print("\n# Install this at %s in your %s, or save it to a file and point $%s at it.\n"
              "# Until it is installed, the guard throws — it will not guess a default."
              % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV), file=sys.stderr)
        return "exit", EXIT_OK

    if command == "selftest":
        return "exit", EXIT_OK if selftest() == 0 else 1

    if command == "show-config":
        print(json.dumps({"unit": UNIT, "source": active_source(), "base": active_base(),
                          "config": active_config()}, indent=2))
        return "exit", EXIT_OK

    if command == "show-policy":
        print(json.dumps({"unit": UNIT, "source": active_source(),
                          "policy": active_policy().as_dict()}, indent=2))
        return "exit", EXIT_OK

    if not rest:
        sys.stderr.write("usage: audit_guard.py <patch.py> [args...]\n")
        return "exit", EXIT_USAGE
    active_policy()          # resolve NOW: before sys.argv is touched, before the hook goes up,
    return "run", rest       # and while a ConfigError can still be reported as exit 4


def main(argv=None):
    """Run a crank patch under the runtime veto. Returns the process exit code.

    `argv` is a full argv INCLUDING the program name at `argv[0]`, as the original's
    `main(sys.argv)` was called; `argv[1]` is the patch path (or a subcommand) and the rest is
    passed through to the patch.

        0  the patch ran      2  usage      3  vetoed      4  no config object

    The usage check comes first, so a bad argv is exit 2 whether or not a config exists — that is
    the original's answer to `main([])`, and it needs no policy to give it. Config is resolved next,
    before `sys.argv` is touched and before the irremovable hook goes up, so exit 4 leaves the
    process unchanged and the patch unrun.

    THE SURFACE ADDITION. The original's signature was `main(argv)`, with no default, and every
    existing caller — `main(sys.argv)`, `main([prog, patch])` — is unaffected by the one added
    here. The default is required, not cosmetic: #200 requirement 3 asks for a console entry point,
    and the entry point generated for this module is `main`, which setuptools calls as `main()`
    with no arguments. `argv=None` means `sys.argv`, so `forge2-audit-guard` and
    `python3 audit_guard.py` behave identically.
    """
    argv = list(sys.argv if argv is None else argv)
    try:
        outcome, payload = _plan(argv)
    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no bug report. The
        # patch has NOT run and no hook has been installed.
        sys.stderr.write("config error: %s\n" % exc)
        return EXIT_NO_CONFIG
    except Exception as exc:      # noqa: BLE001 — an unexpected exception here IS a defect in this
        # tool, which is exactly what note-for-claude wants reported.
        path = _bug_report(exc, traceback.format_exc(), argv[1:])
        sys.stderr.write("EXCEPTION — %s\n" % ("bug report filed at %s" % path if path
                                               else "no bug report could be filed"))
        raise

    if outcome == "exit":
        return payload

    # The patch runs OUTSIDE the handler above, and that placement is deliberate. An exception the
    # patch raises is the PATCH's defect, not this tool's: the original propagated it untouched, so
    # filing a bug report against THIS module for it would be a lie, and catching it here would
    # bury this module's own frames in the patch's traceback. Nothing between here and
    # `runpy.run_path` can swallow it.
    return run_patch(payload[0], payload[1:])


# ─────────────────────────────── the selftest ───────────────────────────────

def _attempt(thunk):
    """Call `thunk`; return `("ok", value)` or `("raised", type_name, message)`.

    A test net that dies on the first unexpected exception hides every check after it and reports a
    traceback where it owes a verdict. Every check below compares against one of these tuples, so an
    exception is a REPORTED result — including the TypeError and ValueError the original itself
    raises, which are expected results here, not accidents.
    """
    try:
        return ("ok", thunk())
    except BaseException as exc:      # noqa: BLE001 — a test net must survive anything
        return ("raised", type(exc).__name__, str(exc))


#: The config object the exemplars run against: the ORIGINAL's hardcoded values, which is the whole
#: point — in this configuration the rewrite must BE the original.
def _oracle_config(repo_env="CRANK_REPO"):
    config = config_template()
    config["repo_env"] = repo_env
    return config


def selftest(stream=None):
    """Prove this rewrite against ticket #415's acceptance items (a), (b) and (d).

    Builds its own config objects in memory, runs the CLI in SUBPROCESSES (because
    `sys.addaudithook` is one-way — a hook installed to test it could never be removed, and would
    veto the rest of this process), writes no files outside a temporary directory it creates and
    removes, and returns the number of failures.

    Every expected value below was read off the ORIGINAL unit acting as the oracle, at git blob
    a8ac29e086c136b9b36904a1896caa3ae9c19cfc — never off this rewrite.
    """
    out = stream or sys.stdout
    checks = [0]
    failures = []

    def check(ok, label):
        checks[0] += 1
        if ok:
            print("  ok   %s" % label, file=out)
        else:
            failures.append(label)
            print("  FAIL %s" % label, file=out)

    saved_active, saved_resolved = _ACTIVE, _RESOLVED
    saved_env = os.environ.get(CONFIG_ENV)
    saved_repo = os.environ.get("CRANK_REPO")
    saved_argv = list(sys.argv)
    repo = os.path.realpath(tempfile.mkdtemp(prefix="audit_guard_selftest_repo_"))
    try:
        os.environ.pop(CONFIG_ENV, None)
        os.environ["CRANK_REPO"] = repo
        reset_config()

        with using_config(_oracle_config()):
            outside = "/somewhere/else"          # not under the repo, not under any temp root
            secret = os.path.expanduser("~/.ssh/id_rsa")

            # 1. _under — pure, config-free, and the one place symlink escape is stopped.
            print("[1] _under(path, roots)", file=out)
            roots = active_policy().write_roots
            check(_attempt(lambda: _under(repo, roots)) == ("ok", True),
                  "_under(repo, roots) is True — a root is under itself")
            check(_attempt(lambda: _under(os.path.join(repo, "a/b"), roots)) == ("ok", True),
                  "_under(repo + '/a/b', roots) is True")
            # Roots are (repo,) ALONE here on purpose: the selftest's repo is a mkdtemp, so it
            # lives under the temp root, and `repo + "-sibling"` would be legitimately inside THAT.
            # Testing the separator rule needs the repo to be the only root, or the check proves
            # nothing about the rule it names.
            check(_attempt(lambda: _under(repo + "-sibling", (repo,))) == ("ok", False),
                  "_under(repo + '-sibling', (repo,)) is False — the prefix match is on a path "
                  "SEPARATOR, so a sibling whose name merely starts with the root is outside")
            check(_attempt(lambda: _under(os.path.join(repo, "a"), (repo,))) == ("ok", True),
                  "_under(repo + '/a', (repo,)) is True — the same rule, admitting a real child")
            check(_attempt(lambda: _under(outside, roots)) == ("ok", False),
                  "_under('/somewhere/else', roots) is False")
            check(_attempt(lambda: _under(None, roots)) == ("ok", False),
                  "_under(None, roots) is False — realpath raises, and the original swallows it")
            check(_attempt(lambda: _under("\0", roots)) == ("ok", False),
                  "_under('\\0', roots) is False — an embedded NUL is swallowed too")
            check(_attempt(lambda: _under("anything", ())) == ("ok", False),
                  "_under('anything', ()) is False — no roots, nothing is under them")
            got = _attempt(lambda: _under(b"/private/tmp/x", roots))
            check(got[0] == "raised" and got[1] == "TypeError",
                  "_under(bytes, str roots) raises TypeError — the original's try wraps ONLY "
                  "realpath, so bytes.startswith(str) escapes it (preserved, not repaired)")

            # 2. _sensitive.
            print("[2] _sensitive(path)", file=out)
            check(_attempt(lambda: _sensitive("/etc/passwd")) == ("ok", True),
                  "_sensitive('/etc/passwd') is True — the raw substring '/etc/'")
            check(_attempt(lambda: _sensitive("/etc")) == ("ok", True),
                  "_sensitive('/etc') is True — via its REALPATH '/private/etc' on this platform")
            check(_attempt(lambda: _sensitive(secret)) == ("ok", True),
                  "_sensitive('~/.ssh/id_rsa' expanded) is True")
            check(_attempt(lambda: _sensitive("id_rsa")) == ("ok", True),
                  "_sensitive('id_rsa') is True — a bare filename matches the substring rule")
            check(_attempt(lambda: _sensitive(os.path.join(repo, "ok.txt"))) == ("ok", False),
                  "_sensitive(repo + '/ok.txt') is False")
            check(_attempt(lambda: _sensitive("")) == ("ok", False),
                  "_sensitive('') is False")
            check(_attempt(lambda: _sensitive(None)) == ("ok", False),
                  "_sensitive(None) is False — str(None) is 'None', which matches no rule")
            check(_attempt(lambda: _sensitive(b"/etc/passwd")) == ("ok", True),
                  "_sensitive(b'/etc/passwd') is True — str(bytes) is \"b'/etc/passwd'\", which "
                  "still contains '/etc/'")
            got = _attempt(lambda: _sensitive("\0"))
            check(got[0] == "raised" and got[1] == "ValueError",
                  "_sensitive('\\0') raises ValueError from realpath — unguarded in the original")
            with using_config(dict(_oracle_config(), sensitive_paths=[], sensitive_substrings=[])):
                check(_attempt(lambda: _sensitive("\0")) == ("ok", False),
                      "_sensitive('\\0') with NO rules is False, NOT ValueError — realpath lives "
                      "inside the any(), so an empty rule set never calls it")

            # 3. _writing.
            print("[3] _writing(mode, flags)", file=out)
            for mode, want in [("r", False), ("rb", False), ("w", True), ("a", True), ("x", True),
                               ("rb+", True), ("w+b", True)]:
                check(_attempt(lambda m=mode: _writing(m, None)) == ("ok", want),
                      "_writing(%r, None) is %s" % (mode, want))
            check(_attempt(lambda: _writing(None, os.O_RDONLY)) == ("ok", False),
                  "_writing(None, os.O_RDONLY) is False")
            check(_attempt(lambda: _writing(None, os.O_WRONLY)) == ("ok", True),
                  "_writing(None, os.O_WRONLY) is True")
            check(_attempt(lambda: _writing(None, os.O_RDWR | os.O_CREAT)) == ("ok", True),
                  "_writing(None, os.O_RDWR|os.O_CREAT) is True")
            check(_attempt(lambda: _writing("r", os.O_WRONLY)) == ("ok", False),
                  "_writing('r', os.O_WRONLY) is False — a string mode WINS; flags are not even "
                  "looked at")
            check(_attempt(lambda: _writing(None, True)) == ("ok", True),
                  "_writing(None, True) is True — bool is a subclass of int, and True & O_WRONLY "
                  "is 1")
            check(_attempt(lambda: _writing(None, False)) == ("ok", False),
                  "_writing(None, False) is False")
            check(_attempt(lambda: _writing(None, None)) == ("ok", False),
                  "_writing(None, None) is False")
            check(_attempt(lambda: _writing(b"w", None)) == ("ok", False),
                  "_writing(b'w', None) is False — bytes is not str and not int")

            # 4. _hook — the vetoes.
            print("[4] _hook(event, args) — vetoes", file=out)
            vetoes = [
                (("os.system", ("ls",)),
                 "shelling out is forbidden (os.system) — do it in pure python"),
                (("subprocess.Popen", (["ls"],)),
                 "shelling out is forbidden (subprocess.Popen) — do it in pure python"),
                (("os.posix_spawn", ()),
                 "shelling out is forbidden (os.posix_spawn) — do it in pure python"),
                (("pty.spawn", ()), "shelling out is forbidden (pty.spawn) — do it in pure python"),
                (("os.execv", ("/bin/ls", [])), "process exec/spawn is forbidden (os.execv)"),
                (("os.spawnl", ()), "process exec/spawn is forbidden (os.spawnl)"),
                (("import", ("ctypes", None, None, None, 0)),
                 "native FFI import 'ctypes' is forbidden"),
                (("import", ("_ctypes",)), "native FFI import '_ctypes' is forbidden"),
                (("import", ("ctypes.util",)), "native FFI import 'ctypes.util' is forbidden"),
                (("ctypes.dlopen", ("libc",)), "ctypes/native is forbidden (ctypes.dlopen)"),
                (("socket.connect", (None, None)), "network access is forbidden (socket.connect)"),
                (("socket.getaddrinfo", ()), "network access is forbidden (socket.getaddrinfo)"),
                (("open", ("/etc/passwd", "r", None)),
                 "touching a sensitive path is forbidden (/etc/passwd)"),
                (("open", (secret, "r", None)),
                 "touching a sensitive path is forbidden (%s)" % secret),
                (("open", (outside, "w", None)),
                 "writing outside the build repo is forbidden (%s)" % outside),
                (("open", (outside, None, os.O_WRONLY)),
                 "writing outside the build repo is forbidden (%s)" % outside),
                (("os.remove", (outside,)),
                 "mutating outside the build repo is forbidden (os.remove: %s)" % outside),
                (("os.remove", ("/etc/passwd",)),
                 "mutating a sensitive path is forbidden (os.remove: /etc/passwd)"),
                (("shutil.rmtree", (outside,)),
                 "mutating outside the build repo is forbidden (shutil.rmtree: %s)" % outside),
                (("os.rename", (os.path.join(repo, "a"), outside)),
                 "mutating outside the build repo is forbidden (os.rename: %s)" % outside),
                (("os.chmod", (outside, 0o777)),
                 "mutating outside the build repo is forbidden (os.chmod: %s)" % outside),
            ]
            for (event, args), message in vetoes:
                got = _attempt(lambda e=event, a=args: _hook(e, a))
                check(got == ("raised", "CrankEscape", message),
                      "_hook(%r, ...) vetoes: %s" % (event, message))

            # 5. _hook — what it must ALLOW. A guard that refuses everything is not a guard; these
            #    are the operations the patch legitimately needs.
            print("[5] _hook(event, args) — allowed", file=out)
            allowed = [
                ("open", (os.path.join(repo, "x"), "w", None)),
                ("open", (os.path.join(repo, "x"), None, os.O_WRONLY | os.O_CREAT)),
                ("open", (outside, "r", None)),
                ("open", (outside, None, os.O_RDONLY)),
                ("open", ()),
                ("open", (None, "w", None)),
                ("open", (123, "w", None)),
                ("import", ("os",)),
                ("import", ()),
                ("import", (None,)),
                ("socket.bind", ()),
                ("ctypes", ()),
                ("exec", ()),
                ("compile", ()),
                ("os.remove", (os.path.join(repo, "x"),)),
                ("os.remove", ()),
                ("os.remove", (None,)),
                ("os.rename", (os.path.join(repo, "a"),)),
                ("object.__getattr__", ()),
            ]
            for event, args in allowed:
                check(_attempt(lambda e=event, a=args: _hook(e, a)) == ("ok", None),
                      "_hook(%r, %r) allows" % (event, args))
            check(_attempt(lambda: _hook("import", (b"ctypes",))) == ("ok", None),
                  "_hook('import', (b'ctypes',)) ALLOWS — str(b'ctypes') is \"b'ctypes'\", which "
                  "is not an ffi_import_root (the original's hole, preserved not repaired)")
            got = _attempt(lambda: _hook("open", (b"/somewhere/else", "w", None)))
            check(got[0] == "raised" and got[1] == "TypeError",
                  "_hook('open', (bytes, 'w', None)) raises TypeError, not CrankEscape — the "
                  "operation is still aborted, but by _under's bytes-vs-str comparison")

            # 6. the callable surface (acceptance item b).
            print("[6] callable surface", file=out)
            import inspect
            for name, want in [("_under", "(path, roots)"), ("_sensitive", "(path)"),
                               ("_writing", "(mode, flags)"), ("_hook", "(event, args)")]:
                got = str(inspect.signature(globals()[name]))
                check(got == want, "%s%s matches the ticket's surface %s%s"
                      % (name, got, name, want))
            # main is the ONE surface deviation, and it is an addition: the ticket's surface is
            # main(argv) and every existing caller passes argv, which still works. The default
            # exists because #200's console entry point calls main() with no arguments. See main.
            check(str(inspect.signature(main)) == "(argv=None)",
                  "main(argv=None) — argv is still positional and main(sys.argv) is unchanged; "
                  "the default is what lets the console entry point call main()")
            check(_attempt(lambda: main([])) == ("ok", EXIT_USAGE),
                  "main([]) still works positionally and returns 2, as the original's did")
            check(issubclass(CrankEscape, RuntimeError),
                  "CrankEscape is a RuntimeError, as the original's was")
            check(_attempt(lambda: _hook("nonexistent.event", ())) == ("ok", None),
                  "_hook returns None (not False) for an event it does not police — an audit hook's "
                  "return value is ignored, and only raising vetoes")

        # 7. the config gate (acceptance item d).
        print("[7] the config gate — no config, no guessing", file=out)
        reset_config()
        missing = os.path.join(repo, "definitely-not-here.json")
        os.environ[CONFIG_ENV] = missing
        try:
            for name, thunk in [("_sensitive('/etc/passwd')", lambda: _sensitive("/etc/passwd")),
                                ("_writing('w', None)", lambda: _writing("w", None)),
                                ("_hook('os.system', ('ls',))", lambda: _hook("os.system", ("ls",))),
                                ("active_policy()", active_policy)]:
                got = _attempt(thunk)
                check(got[0] == "raised" and got[1] == "ConfigError",
                      "%s throws ConfigError when the config cannot be seen" % name)
            check(_attempt(lambda: _under("/x", ("/x",))) == ("ok", True),
                  "_under STILL works with no config — it takes its roots as an argument and "
                  "needs none, exactly as the original did")
            # A missing key is named, not defaulted.
            for key in ("repo_env", "write_roots", "sensitive_paths", "mutate_events",
                        "write_mode_chars", "write_flag_names", "dont_write_bytecode"):
                broken = _oracle_config()
                del broken[key]
                with using_config(broken):
                    got = _attempt(active_policy)
                    check(got[0] == "raised" and got[1] == "ConfigError" and key in got[2],
                          "a config object missing %r throws ConfigError naming that key" % key)
        finally:
            os.environ.pop(CONFIG_ENV, None)
            reset_config()

        # 8. main() end to end, in subprocesses.
        print("[8] main(argv) end to end (subprocesses — addaudithook is one-way)", file=out)
        for label, ok in _cli_checks(repo):
            check(ok, label)

    finally:
        os.environ.pop(CONFIG_ENV, None)
        if saved_env is not None:
            os.environ[CONFIG_ENV] = saved_env
        os.environ.pop("CRANK_REPO", None)
        if saved_repo is not None:
            os.environ["CRANK_REPO"] = saved_repo
        sys.argv[:] = saved_argv
        reset_config()
        globals()["_ACTIVE"], globals()["_RESOLVED"] = saved_active, saved_resolved
        _rmtree(repo)

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED", checks[0], len(failures)),
          file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


def _rmtree(root):
    """Remove a directory tree with `os.walk`, so the selftest needs no `shutil` import."""
    for base, dirs, files in os.walk(root, topdown=False):
        for name in files:
            with contextlib.suppress(OSError):
                os.remove(os.path.join(base, name))
        for name in dirs:
            with contextlib.suppress(OSError):
                os.rmdir(os.path.join(base, name))
    with contextlib.suppress(OSError):
        os.rmdir(root)


def _run_cli(repo, argv, patch_source=None, patch_name="patch.py"):
    """Run this module's CLI in a SUBPROCESS with CRANK_REPO=repo; return (code, stdout, stderr).

    A subprocess is not a convenience here: `sys.addaudithook` cannot be undone, so a `main()` run
    in-process would leave the veto standing over the rest of the selftest.
    """
    import subprocess
    if patch_source is not None:
        with open(os.path.join(repo, patch_name), "w", encoding="utf-8") as handle:
            handle.write(patch_source)
    env = dict(os.environ, CRANK_REPO=repo)
    env.pop(CONFIG_ENV, None)
    proc = subprocess.run([sys.executable, os.path.abspath(__file__)] + argv,
                          cwd=repo, env=env, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _cli_checks(repo):
    """Yield `(label, ok)` for each end-to-end CLI check. See `selftest`."""
    code, _, err = _run_cli(repo, [])
    yield ("main([]) exits 2 and prints the original's usage line, with no config needed",
           code == EXIT_USAGE and err == "usage: audit_guard.py <patch.py> [args...]\n")

    code, out, _ = _run_cli(repo, ["patch.py", "alpha", "beta"],
                            patch_source="import sys\n"
                                         "print('ARGV', sys.argv)\n"
                                         "print('NAME', __name__)\n"
                                         "print('PYC', sys.dont_write_bytecode)\n")
    yield ("a clean patch exits 0, runs as __main__, sees sys.argv == [patch, *args], and "
           "observes dont_write_bytecode True",
           code == EXIT_OK and "ARGV ['patch.py', 'alpha', 'beta']" in out
           and "NAME __main__" in out and "PYC True" in out)

    code, _, err = _run_cli(repo, ["run", "patch.py", "alpha", "beta"],
                            patch_source="import sys\nprint('ARGV', sys.argv)\n")
    yield ("the `run` subcommand is an alias for the original's bare-path spelling", code == EXIT_OK)

    code, out, _ = _run_cli(repo, ["patch.py"],
                            patch_source="open('inside.txt', 'w').write('ok')\nprint('WROTE')\n")
    yield ("a patch WRITING inside the build repo is allowed (a guard that blocked this would be "
           "useless)", code == EXIT_OK and "WROTE" in out
           and os.path.isfile(os.path.join(repo, "inside.txt")))

    vetoed = [
        ("os.system", "import os\nos.system('echo pwned')\n", "shelling out is forbidden"),
        ("subprocess", "import subprocess\nsubprocess.run(['echo', 'pwned'])\n",
         "shelling out is forbidden"),
        ("ctypes import", "import ctypes\n", "native FFI import 'ctypes' is forbidden"),
        ("dynamic ctypes import", "m = __import__('cty' + 'pes')\n",
         "native FFI import 'ctypes' is forbidden"),
        ("network", "import socket\nsocket.create_connection(('example.com', 80))\n",
         "network access is forbidden"),
        ("write outside the repo", "open('/somewhere/else.txt', 'w')\n",
         "writing outside the build repo is forbidden"),
        ("read a sensitive path", "open('/etc/passwd')\n",
         "touching a sensitive path is forbidden"),
        ("delete outside the repo", "import os\nos.remove('/somewhere/else.txt')\n",
         "mutating outside the build repo is forbidden"),
        ("dynamic getattr shell-out", "import os\ngetattr(os, 'sys' + 'tem')('echo pwned')\n",
         "shelling out is forbidden"),
    ]
    for label, source, expect in vetoed:
        code, out, err = _run_cli(repo, ["patch.py"], patch_source=source)
        yield ("a patch that tries to %s is VETOED: exit 3, 'CRANK-VETO: %s...'" % (label, expect),
               code == EXIT_VETO and err.startswith("CRANK-VETO: ") and expect in err
               and "pwned" not in out)

    code, _, err = _run_cli(repo, ["patch.py"], patch_source="raise ValueError('the patch broke')\n")
    yield ("an exception raised by the PATCH propagates as the original let it (traceback, not a "
           "veto, not exit 3)", code not in (EXIT_OK, EXIT_VETO) and "ValueError" in err
           and "the patch broke" in err)

    code, _, err = _run_cli(repo, ["no-such-patch.py"])
    yield ("a missing patch file propagates its FileNotFoundError, as the original did",
           code not in (EXIT_OK, EXIT_VETO) and "FileNotFoundError" in err)

    code, out, _ = _run_cli(repo, ["patch.py"], patch_source="import sys\nsys.exit(7)\n")
    yield ("a patch calling sys.exit(7) exits 7 — SystemExit is not caught, as in the original",
           code == 7)

    # The config gate, end to end: FORGE2_CONFIG points at nothing, so nothing runs.
    import subprocess
    marker = os.path.join(repo, "gate-marker.txt")
    with open(os.path.join(repo, "gate.py"), "w", encoding="utf-8") as handle:
        handle.write("open(%r, 'w').write('the patch RAN')\n" % marker)
    env = dict(os.environ, CRANK_REPO=repo)
    env[CONFIG_ENV] = os.path.join(repo, "definitely-not-here.json")
    proc = subprocess.run([sys.executable, os.path.abspath(__file__), "gate.py"],
                          cwd=repo, env=env, capture_output=True, text=True)
    yield ("with no config the CLI exits 4, says so in one line, and the patch NEVER RAN — the "
           "gate refuses rather than guessing a default policy",
           proc.returncode == EXIT_NO_CONFIG and proc.stderr.startswith("config error: ")
           and "Traceback" not in proc.stderr and not os.path.isfile(marker))

    code, out, _ = _run_cli(repo, ["emit-config"])
    yield ("emit-config prints a config object that is valid JSON and rebuilds a working policy",
           code == EXIT_OK and _emitted_config_is_usable(out))

    # The reentrancy trap this whole module is shaped around. A live hook that could be sent back
    # to the config layer would re-enter itself on its own registry read and recurse forever.
    # Proven by doing the worst thing available: reset the config layer from INSIDE the running
    # patch, AFTER the veto is up and can no longer be removed, then keep touching files.
    code, out, err = _run_cli(repo, ["patch.py"], patch_source=(
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import audit_guard\n"
        "audit_guard.reset_config()   # the hook is ALREADY installed and cannot be removed\n"
        "open('inside_after_reset.txt', 'w').close()   # allowed: inside the build repo\n"
        "print('SURVIVED-RESET')\n"
        "open('/somewhere/outside.txt', 'w')           # must STILL be vetoed\n"
        % os.path.dirname(os.path.abspath(__file__))))
    yield ("resetting the config layer from inside a RUNNING patch cannot un-resolve or weaken the "
           "live veto, and cannot make the hook re-enter itself (no RecursionError)",
           code == EXIT_VETO and "SURVIVED-RESET" in out
           and "writing outside the build repo is forbidden" in err
           and "RecursionError" not in err)


def _emitted_config_is_usable(text):
    """True if `emit-config`'s stdout parses and compiles into a policy — so the template it tells
    an operator to install actually works, rather than being a plausible-looking wish list."""
    try:
        config = json.loads(text)
    except ValueError:
        return False
    try:
        return build_policy(config) is not None
    except ConfigError:
        return False


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ... Filename -
    function name - time of occurance - methods to reproduce - possible cause"). Best-effort and
    silent on failure: a tool that cannot file a report must still report its original error.
    Returns the path written, or None.
    """
    try:
        config = active_config()
        base = active_base()
    except ConfigError:
        return None
    relative = config.get("bug_reports")
    if not isinstance(relative, str) or not relative:
        return None
    path = relative if os.path.isabs(relative) else os.path.join(base, relative)
    frames = traceback.extract_tb(exc.__traceback__)
    entry = {
        "filename": os.path.basename(os.path.abspath(__file__)),
        "function": frames[-1].name if frames else "?",
        "time-of-occurance": datetime.now().isoformat(),
        "methods-to-reproduce": "python3 %s %s" % (os.path.basename(os.path.abspath(__file__)),
                                                   " ".join(str(a) for a in argv)),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": formatted.strip().splitlines()[-6:],
        "note": "%s (ticket #415, module key forge-rw:d654dce464c49da7)" % UNIT,
    }
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except OSError:
        return None


def _print_help():
    """Print the usage text.

    Hand-rolled rather than argparse: the original's CLI takes a bare patch path as `argv[1]` and
    passes every remaining argument THROUGH to the patch untouched — including flags like `-h` or
    `--version` that a parser would eat. Preserving that pass-through matters more than the
    conveniences a parser would add, because the patch's own argv is part of the contract.
    """
    print(
        "forge2-audit-guard — run an UNTRUSTED crank patch under a RUNTIME veto.\n"
        "A rewrite of the forge unit agent_tools_suite:audit_guard.py (ticket #415, standard #200).\n"
        "\n"
        "The veto fires on the ACTUAL runtime operation, however the patch's source spelled it,\n"
        "and refuses: shelling out / exec / spawn, native FFI (ctypes), network access, and\n"
        "writes, deletes or renames outside the build repo or at a sensitive path. Reads of the\n"
        "stdlib are allowed so imports work.\n"
        "\n"
        "usage:\n"
        "  forge2-audit-guard <patch.py> [args...]       run patch.py as __main__ under the veto\n"
        "  forge2-audit-guard run <patch.py> [args...]   the same, spelled explicitly\n"
        "  forge2-audit-guard selftest                   prove the exemplars, edges and gate\n"
        "  forge2-audit-guard emit-config                print a config-object template\n"
        "  forge2-audit-guard show-config                print the resolved config + its source\n"
        "  forge2-audit-guard show-policy                print the compiled policy\n"
        "\n"
        "Any first argument that is not one of the words above is taken as a patch path, which is\n"
        "the original's spelling and the one crank_discipline.run_confined uses. Arguments after\n"
        "the patch are passed through to it as its own sys.argv.\n"
        "\n"
        "exit codes: 0 patch ran | 2 usage | 3 VETOED | 4 no config object\n"
        "\n"
        "The build repo is the one tree the patch may write to. It is named by the config's\n"
        "`repo_env` (shipped: $CRANK_REPO) and defaults to the current directory when that is\n"
        "unset or empty.\n"
        "\n"
        "Config is read from the file named by $%s, else from the %s section of the\n"
        "nearest %s found by walking up from this module. This package ships one beside the\n"
        "module, so the guard works from a clean checkout. Run `emit-config` for a template;\n"
        "with no config the guard THROWS and runs nothing — it never guesses a policy."
        % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
