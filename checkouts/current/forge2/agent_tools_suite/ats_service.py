#!/usr/bin/env python3
"""forge2 / agent_tools_suite / ats_service — a behavior-preserving rewrite of the forge unit
`agent_tools_suite:ats_service.py` (module key forge-rw:1fa0fdbc322b6466), filed under ticket
#413 against the FORGE-wide refactor standard #200.

WHAT THIS IS
------------
The original forge unit was a 3464-byte launcher: it started, stopped and reported on the
"ats gate" — a long-running MCP server — as a plain detached user process, with a single
pidfile for state. This file is an entirely new implementation of that unit. It keeps the
original's observable behavior and its callable surface, and adds the three things #200
requires that the original lacked: it is a proper installable package, it is driven by a
configuration object, and it refuses to run when it cannot see that configuration.

TERMS USED HERE (defined at first use, for a reader who has never seen this system)
-----------------------------------------------------------------------------------
the gate
    The server process this module launches and supervises — the original called it "the ats
    gate". This module never speaks the gate's protocol beyond one probe; it only starts it,
    signals it, and asks the endpoint for a status code.
pidfile
    The single file holding the gate's process id. It IS this module's entire state: there is
    no database and no daemon supervisor. "Running" means "the pid in this file answers a
    liveness probe".
registry
    The JSON configuration registry described in this repository's `note-for-claude`: one
    `.json` file holding the configuration for every tool in a package, which registry-gated
    tools "walk UP the tree to find" and "throw if it cannot see". This package ships its own
    at `registry.json`, beside this file.
config object
    The chunk of that registry belonging to this unit — the `forge2.agent_tools_suite.ats_service`
    section. It is what drives this module. `config_template()` prints a template of it.
exemplar
    A real (input, output) pair taken from the ORIGINAL acting as the oracle — #200's
    "verified, not asserted". `selftest()` replays them.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    read_pid()          endpoint_status()          on()          off()          status()
    main()

`COMMANDS` — the `{"on": on, "off": off, "status": status}` dispatch table — is also
preserved as a module attribute, because `main()` dispatches through it and a caller may too.

BEHAVIOR THAT IS EASY TO GET WRONG (each one OBSERVED from the original, not inferred)
--------------------------------------------------------------------------------------
Every item below was measured by running the original — reconstructed from this ticket's
embedded source and confirmed byte-identical to forge blob c7947a7e56c83c810b72ca13279c35431b762745
— inside a sandbox, and each is replayed by `selftest()`:

  * A STALE pidfile is DELETED, a GARBAGE one is NOT. `read_pid()` wraps the read-and-parse in
    one `try`, so an unparseable pidfile ("", "abc") leaves via the `ValueError` path and the
    file SURVIVES; a well-formed pid whose process is gone leaves via the `OSError` path,
    which removes the file first. The two paths look the same to the caller (both return
    `None`) but differ on disk.
  * `read_pid()` CAN RETURN 0, and 0 is FALSY. A pidfile containing "0" parses fine, and
    `os.kill(0, 0)` probes the caller's whole PROCESS GROUP rather than "process 0", so it
    succeeds and `read_pid()` returns `0`. Every CALLER then treats that 0 as "not running":
    `status()` prints "stopped", `off()` prints "not running", and `on()` starts a SECOND
    gate — because all three test the pid for truthiness, not for `is None`. This is
    preserved exactly; a rewrite using `if pid is not None` would diverge here.
  * ONLY 401 means enforced. `status()` maps 401 to "enforced (tokenless rejected)" and every
    other reachable code — 200, 500, anything — to "NOT enforcing".
  * `status()` CREATES NOTHING. Only `on()` creates the pid directory.
  * The exit code for an unknown verb is 1, and the usage line goes to STDERR, because the
    original reports it with `sys.exit("usage: ...")`.
  * `on()` makes the directory of the PIDFILE — not of the logfile. In the original both
    constants named the same directory, so the distinction was invisible; under a config that
    separates them it is not. See `on()`.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The original hardcoded every path and parameter it used: the interpreter, the server script,
the pidfile, the logfile, the URL, the 3-second timeout, the `ATS_TRANSPORT=streamable-http`
overlay, the probe body and headers, and the 401 that means "enforced". All of them are now
config keys, and NONE has a default. The config object is resolved on first use from the
first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. That file holds the unit
     config object itself — exactly what `config_template()` returns.
  2. otherwise, the `forge2.agent_tools_suite.ats_service` section of the nearest
     `registry.json` found by walking UP from THIS FILE's directory. This package ships one
     there, so an unmodified checkout resolves to it and the module runs.

If NEITHER answers, every operation raises `ConfigError` and NOTHING is started, signalled or
printed. It never guesses a default — that is `note-for-claude`'s rule and this ticket's
acceptance item (d). A config object that is found but lacks a key the ATTEMPTED operation
needs is also a `ConfigError`, naming the key. Keys are required per-operation, so `read_pid()`
needs only `pidfile` and does not throw because `url` is absent.

The keys, and the original constant each replaces:

    pidfile              str   ~/bin/config/ats/gate.pid          PIDFILE
    logfile              str   ~/bin/config/ats/gate.out.log      LOGFILE
    python               str   <this dir>/.venv/bin/python        PYTHON
    server               str   <this dir>/ats_http.py             SERVER
    url                  str   http://127.0.0.1:8811/mcp          URL
    timeout              num   3                                  urlopen(..., timeout=3)
    server_env           obj   {"ATS_TRANSPORT": "streamable-http"}   the Popen env overlay
    probe                obj   method/body/headers of the probe   the Request(...) literals
    auth_enforced_status int   401                                the `code == 401` test

A path key may be absolute, may start with `~` (expanded), or may be relative — in which case
it resolves against the directory the config came FROM (the registry's directory), never
against the current working directory. So `"server": "ats_http.py"` means "beside this
module", which is exactly what the original's `os.path.join(HERE, "ats_http.py")` meant.

`configure(config)` and `using_config(config)` inject a config object in-process, for callers
that hold their configuration in memory rather than on disk.

RUNNING IT
----------
The CLI is the original's, EXACTLY — three verbs, `status` by default:

    python3 ats_service.py on        # start the gate in the background
    python3 ats_service.py off       # stop it
    python3 ats_service.py status    # running? serving? auth enforced?  (also the default)

Any other argument prints `usage: ats_service.py [on|off|status]` on stderr and exits 1.

WHAT `on` NEEDS THAT THIS PACKAGE DOES NOT SHIP. `on` launches `[python, server]`, so the
interpreter and server script the config names must EXIST. Ticket #413 covers exactly one
module — this one — so `ats_http.py` and a `.venv` are NOT here, and `python3 ats_service.py
on` in an unmodified checkout therefore fails with `FileNotFoundError` on the configured
interpreter. That is not a defect and not a divergence: the ORIGINAL fails identically when
run away from its own `.venv`, with the same exception and the same exit 1 — it was measured
doing so. Point `python` and `server` at a real interpreter and a real gate, and `on` works.
`status` and `off` need neither and run as written right now.

WHY THERE IS NO `selftest` VERB — and how to run the selftest anyway. The original's `main()`
rejects every verb outside that set, `selftest` included; it was MEASURED doing so. Adding a
verb would therefore CHANGE the behavior of an input the original already defines, which
#200's first requirement forbids. So the diagnostics are module functions, not verbs. Run
them from this file's directory with:

    python3 -B -c "import ats_service; raise SystemExit(ats_service.selftest())"
    python3 -B -c "import ats_service; raise SystemExit(ats_service.check_package())"
    python3 -B -c "import ats_service, json; print(json.dumps(ats_service.config_template(), indent=2))"
    python3 -B -c "import ats_service, json; print(json.dumps(ats_service.show_config(), indent=2))"

(`python3 -c` puts the current directory on the import path, which is why these run as
written from the package directory. `selftest()` and `check_package()` return 0 on success
and 1 on failure, so `raise SystemExit(...)` makes that the process exit code. The `-B` is
not required — it just stops PYTHON from caching the bytecode of the module you are importing,
so the command leaves no `__pycache__` beside the source. Drop it and everything still works.)

To prove acceptance item (d) — that this throws rather than guessing — point the config
environment variable at a file that does not exist:

    FORGE2_CONFIG=/nonexistent.json python3 ats_service.py status    # -> exit 2, config error

INSTALLABLE (#200 requirement 3)
--------------------------------
This directory IS the import package `agent_tools_suite`, and ticket #413 lands the whole of
it, so it installs from its own source:

    pip install -e .                      # from this directory
    forge2-ats-service status             # the console script
    python3 -c "from agent_tools_suite.ats_service import read_pid"

`pyproject.toml` and `__init__.py` are NOT hand-authored here: per #200 requirement 3 they are
DERIVED from the modules present by `congruency/tools/forge_package.py` (#410), so a sibling
module of this package can land later without either unit clobbering the other. They were
generated by running that tool against this directory. `registry.json` holds only this unit's
own `forge2.agent_tools_suite.ats_service` section, added additively via that tool's
`merge_registry_section()`; no sibling's section is read, edited or dropped.

HOW FAR THIS WAS VERIFIED — and where it stops
----------------------------------------------
Everything claimed above was RUN, on Python 3.14 on macOS, and you can re-run all of it:

  * BOTH installs were executed, not asserted. `pip install -e .` and `pip install .` each
    built and installed this package into a fresh venv, exit 0. From the non-editable install
    — where this module sits in site-packages with no source tree in reach — the module still
    resolves its config, because `pyproject.toml` ships `registry.json` as package data and
    the walk-up finds it there. The `forge2-ats-service` console script works from both, and
    rejects an unknown verb with the original's usage line and exit 1.
  * BEHAVIOR was verified DIFFERENTIALLY against the original, not just against expectations.
    The original was reconstructed from ticket #413's embedded source, confirmed byte-identical
    to forge blob c7947a7e56c83c810b72ca13279c35431b762745, and run side by side with this
    rewrite through 19 scenarios in identical worlds (same HOME rule, same layout, same
    listener on 127.0.0.1:8811). All 19 were identical in exit code, stdout, stderr, pidfile
    and logfile. That harness was itself mutation-tested: four seeded defects in this module
    (the falsy-0 edge, the HTTPError/OSError ordering, the env overlay, the pidfile-survival
    path) were all caught, so its agreement is evidence rather than an artifact.
  * `selftest()` (52 checks) and `check_package()` (11 checks) pass.

Where it stops: the differential drives a STAND-IN gate — a script that reports its
environment and sleeps — not the real `ats_http.py` MCP server, which is not present in this
checkout. So what is proven is that this module launches, detaches, signals, logs and probes
IDENTICALLY to the original; what the gate itself does once launched is out of this unit's
scope and was never in it.

SIDE EFFECTS — what this module writes, and when
------------------------------------------------
`read_pid()` REMOVES the pidfile when it holds a stale pid; that is the original's behavior
and the whole point of the "clearing a stale pidfile" note in its docstring. `on()` creates
the pidfile's directory, appends to the logfile, spawns the gate and writes the pidfile.
`off()` signals the gate and removes the pidfile. `status()`, `endpoint_status()`,
`config_template()` and `show_config()` create nothing and write nothing.

`selftest()` works entirely inside a temporary directory it removes, against an ephemeral
port; it spawns real child processes and reaps them, and it restores every global and
environment variable it touches. `check_package()` only READS this directory's
`pyproject.toml` and `registry.json`; the one thing it does that could leave a trace is
importing the package to resolve the console-script target, and it switches bytecode writing
off around that import so no `__pycache__` appears.

Note what that claim does NOT cover: `python3 -c "import ats_service"` writes
`__pycache__/ats_service.*.pyc` before either function runs. That is PYTHON caching the module
you imported — it happens for any module and is not this module's doing. `python3 -B -c`
suppresses it, which is why the diagnostics above are written with `-B`.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception
is thrown") `main()` appends one timestamped JSON line to the config's `bug_reports` path if
an UNEXPECTED exception escapes a verb — and then RE-RAISES it, so the exception, its
traceback and the exit code the original produced are all unchanged.

THE ONE DELIBERATE DIVERGENCE, stated plainly rather than buried: on that crash path this
rewrite does two things the original did not — it writes the bug-report line, and it prints
one extra `EXCEPTION — ...` line to stderr saying where the report went. This repository's own
rule requires it, and it is confined to the path where the original was already crashing.
Everything an operator or a caller observes on that path — the exception type, the message,
the traceback, the exit code, and every file and directory the verb had already created — is
identical; that was verified side by side against the original. Filing the report is
best-effort and never masks the real exception.

A `ConfigError` is designed behavior, not a bug: it files no report and prints no traceback,
exiting 2 with a single self-explaining line.
"""

import contextlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime

__all__ = [
    "read_pid", "endpoint_status", "on", "off", "status", "main", "COMMANDS",
    "ConfigError", "load_config", "configure", "using_config", "reset_config",
    "config_template", "show_config", "selftest", "check_package",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: This unit's ADDRESS inside the registry document. Not a configurable setting — a
#: config-driven tool has to know which section is its own.
UNIT_PATH = ("forge2", "agent_tools_suite", "ats_service")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:agent_tools_suite/ats_service"

#: The import package this module belongs to, as the derived `pyproject.toml` declares it.
#: Used only by `check_package()`, to check the packaging against itself.
IMPORT_PACKAGE = "agent_tools_suite"

#: The original's usage line, preserved verbatim — including the `ats_service.py` program
#: name, which the original hardcoded rather than deriving from argv[0].
USAGE = "usage: ats_service.py [on|off|status]"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.
    """


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None      # config injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution, so a verb re-reads no files


def find_registry(start=None):
    """Walk UP from `start` (default: this file's directory) and return the nearest registry
    path, or None if the walk reaches the filesystem root without finding one.

    The walk starts at THIS FILE, never at the working directory, so which directory you run
    from cannot change which config is found. If the walk fails — a layout where the module
    was installed without its package data beside it — it falls back to asking the import
    system where `agent_tools_suite` lives and looks there.
    """
    directory = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))
    while True:
        candidate = os.path.join(directory, REGISTRY_NAME)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    if start is None:
        return _installed_registry()
    return None


def _installed_registry():
    """The registry shipped as package data beside the installed package, or None."""
    try:
        import importlib.util
        spec = importlib.util.find_spec(IMPORT_PACKAGE)
    except (ImportError, ValueError, AttributeError):
        return None
    locations = list(getattr(spec, "submodule_search_locations", None) or []) if spec else []
    for location in locations:
        candidate = os.path.join(location, REGISTRY_NAME)
        if os.path.isfile(candidate):
            return candidate
    return None


def _read_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise ConfigError("%s at %s could not be read as JSON: %s" % (what, path, exc)) from exc


def load_config(start=None):
    """Resolve this unit's config object from disk, ignoring any injected config.

    Returns a `(config, base, source)` triple: the config object, the directory that relative
    paths inside it resolve against, and a human-readable description of where it came from.
    `start` overrides the directory the registry walk-up begins at.

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
            "no config object for %s: %s is unset and no %s was found by walking up from %s. "
            "This tool does not guess defaults — install the config object printed by "
            "config_template()."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))))

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. "
                "Add the object returned by config_template() at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH)))
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError("the registry section %s at %s must be a JSON object, not %s"
                          % (".".join(UNIT_PATH), registry_path, type(node).__name__))

    config = dict(node)
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit
    # section may state its own to override it. This is inheritance inside ONE config
    # document, not a guessed default.
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


def active_base():
    """Return the directory that relative paths in the config resolve against."""
    if _ACTIVE is not None:
        return _ACTIVE[1]
    active_config()
    return _RESOLVED[1]


def active_source():
    """Describe where the config object in force came from."""
    if _ACTIVE is not None:
        return _ACTIVE[2]
    active_config()
    return _RESOLVED[2]


def configure(config, base=None, source="injected via configure()"):
    """Inject `config` as the config object for this process; return the previous state.

    `base` is the directory relative paths in `config` resolve against, and defaults to the
    current working directory. Pass `None` as `config` to drop the injection and go back to
    resolving from disk.
    """
    global _ACTIVE
    previous = _ACTIVE
    if config is None:
        _ACTIVE = None
    else:
        if not isinstance(config, dict):
            raise ConfigError("a config object must be a dict, not %s" % type(config).__name__)
        _ACTIVE = (config, base or os.getcwd(), source)
    return previous


@contextlib.contextmanager
def using_config(config, base=None):
    """Use `config` as the config object for the duration of the `with` block."""
    previous = configure(config, base=base)
    try:
        yield config
    finally:
        global _ACTIVE
        _ACTIVE = previous


def reset_config():
    """Drop the injected config and the cached disk resolution; the next call re-resolves."""
    global _ACTIVE, _RESOLVED
    _ACTIVE = None
    _RESOLVED = None


def config_template():
    """Return a template of this unit's config object — every key set to the value that
    reproduces the ORIGINAL unit's hardcoded constant.

    This is scaffolding returned on request, not a default: nothing here is applied unless an
    operator installs it, and until they do every operation throws.
    """
    return {
        "pidfile": "~/bin/config/ats/gate.pid",
        "logfile": "~/bin/config/ats/gate.out.log",
        "python": ".venv/bin/python",
        "server": "ats_http.py",
        "url": "http://127.0.0.1:8811/mcp",
        "timeout": 3,
        "server_env": {"ATS_TRANSPORT": "streamable-http"},
        "probe": {
            "method": "POST",
            "body": '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}',
            "headers": {
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        },
        "auth_enforced_status": 401,
        "bug_reports": "logs/bug_reports.jsonl",
    }


def show_config():
    """Return the config object in force, its source and its base — for a human to inspect.

    Raises:
        ConfigError: if there is no config object to be had.
    """
    return {"unit": UNIT, "source": active_source(), "base": active_base(),
            "config": active_config()}


# ───────────────────────── typed access to the config ─────────────────────────

def _setting(key):
    """The config value for `key`, or ConfigError naming it. Required per-OPERATION: only the
    keys the attempted verb actually uses are demanded, so `read_pid()` does not throw over an
    absent `url`."""
    config = active_config()
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the required key %r. This tool does not guess "
            "defaults; see config_template() for the full object and the value that "
            "reproduces the original." % (UNIT, key))
    return config[key]


def _str_setting(key):
    value = _setting(key)
    if not isinstance(value, str):
        raise ConfigError("config key %r for %s must be a string, not %s"
                          % (key, UNIT, type(value).__name__))
    return value


def _path_setting(key):
    """A path-valued config key, resolved to an absolute path: `~` is expanded, and a relative
    path resolves against the directory the CONFIG came from — never the working directory."""
    value = os.path.expanduser(_str_setting(key))
    if not os.path.isabs(value):
        value = os.path.join(active_base(), value)
    return value


def _int_setting(key):
    value = _setting(key)
    # bool is a subclass of int; `True` is not a status code.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("config key %r for %s must be an integer, not %s"
                          % (key, UNIT, type(value).__name__))
    return value


def _timeout_setting():
    """The probe timeout: a number of seconds, or null for "no timeout" (Python's default)."""
    value = _setting("timeout")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("config key 'timeout' for %s must be a number of seconds or null, "
                          "not %s" % (UNIT, type(value).__name__))
    return value


def _str_map_setting(key):
    """A config key holding an object of string -> string."""
    value = _setting(key)
    if not isinstance(value, dict):
        raise ConfigError("config key %r for %s must be a JSON object, not %s"
                          % (key, UNIT, type(value).__name__))
    for name, item in value.items():
        if not isinstance(item, str):
            raise ConfigError("config key %r for %s maps %r to %s; every value must be a string"
                              % (key, UNIT, name, type(item).__name__))
    return value


def _probe_setting():
    """The probe request description: `{"method": str, "body": str, "headers": {str: str}}`."""
    probe = _setting("probe")
    if not isinstance(probe, dict):
        raise ConfigError("config key 'probe' for %s must be a JSON object with 'method', "
                          "'body' and 'headers', not %s" % (UNIT, type(probe).__name__))
    for key in ("method", "body", "headers"):
        if key not in probe:
            raise ConfigError("config key 'probe' for %s is missing %r" % (UNIT, key))
    for key in ("method", "body"):
        if not isinstance(probe[key], str):
            raise ConfigError("probe %r for %s must be a string, not %s"
                              % (key, UNIT, type(probe[key]).__name__))
    headers = probe["headers"]
    if not isinstance(headers, dict) or not all(isinstance(v, str) for v in headers.values()):
        raise ConfigError("probe 'headers' for %s must be an object of string -> string" % UNIT)
    return probe


# ─────────────────────────────── the unit itself ───────────────────────────────

def read_pid():
    """The pid in the configured pidfile if that process is alive, else None (clearing a stale
    pidfile).

    The two ways of being "not running" differ ON DISK, and the difference is preserved from
    the original:
      * the pidfile is missing, unreadable, empty or not an integer -> None, and the file is
        LEFT ALONE (the read and the parse share one `try`, so both leave by the same path);
      * the pidfile holds an integer whose process does not exist -> the file is REMOVED
        first, then None.

    It can also return 0: "0" parses, and `os.kill(0, 0)` probes this process's whole PROCESS
    GROUP rather than a process called 0, so the probe succeeds. 0 is falsy, so every caller
    reads that as "not running" — see the module docstring.

    Raises:
        ConfigError: if there is no config object, or it has no `pidfile` key.
    """
    pidfile = _path_setting("pidfile")
    try:
        with open(pidfile) as handle:
            pid = int(handle.read().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)          # signal 0 is a liveness probe; it does not touch the process
    except OSError:
        os.remove(pidfile)
        return None
    return pid


def endpoint_status():
    """POST a tokenless initialize; return the HTTP status code, or None if unreachable.

    The request — method, body and headers — and the timeout come from the config's `probe`
    and `timeout` keys. A non-2xx answer still reaches us as an `HTTPError`, which carries the
    code, so a 401 is REPORTED rather than raised; only a transport failure (nothing
    listening, DNS, timeout) is None. `HTTPError` is caught before `OSError` because it is a
    subclass of it, and swapping them would turn every 401 into None.

    Raises:
        ConfigError: if there is no config object, or it lacks `url`, `probe` or `timeout`.
    """
    url = _str_setting("url")
    probe = _probe_setting()
    timeout = _timeout_setting()
    request = urllib.request.Request(
        url,
        method=probe["method"],
        data=probe["body"].encode("utf-8"),
        headers=dict(probe["headers"]),
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except OSError:
        return None


def on():
    """Start the gate in the background, detached, and record its pid. Idempotent while the
    recorded process is alive: it prints "already running" and starts nothing.

    The gate is spawned in its OWN SESSION so it outlives this launcher, its stdout and stderr
    are MERGED into the appended logfile, and the config's `server_env` is overlaid on this
    process's environment (the original hardcoded `ATS_TRANSPORT=streamable-http`).

    Only the PIDFILE's directory is created — not the logfile's. The original called
    `os.makedirs(os.path.dirname(PIDFILE))` and nothing else, and both of its constants named
    the same directory, so this was invisible; it is preserved rather than "fixed" because
    creating a directory the original never created is a side effect this ticket does not
    authorize. Configure the logfile beside the pidfile, or create its directory yourself.

    Raises:
        ConfigError: if there is no config object, or it lacks a key this needs.
    """
    running = read_pid()
    if running:
        print(f"already running (pid {running})")
        return
    # Resolve EVERY setting before touching the filesystem, so an incomplete config cannot
    # leave a half-made directory behind.
    pidfile = _path_setting("pidfile")
    logfile_path = _path_setting("logfile")
    python = _path_setting("python")
    server = _path_setting("server")
    overlay = _str_map_setting("server_env")

    os.makedirs(os.path.dirname(pidfile), exist_ok=True)
    logfile = open(logfile_path, "a")
    try:
        process = subprocess.Popen(
            [python, server],
            stdout=logfile,
            stderr=subprocess.STDOUT,
            start_new_session=True,      # detach so the gate outlives this launcher
            env={**os.environ, **overlay},
        )
    finally:
        # The child holds its own duplicate of this descriptor, so closing ours changes
        # nothing about the gate's logging.
        logfile.close()
    with open(pidfile, "w") as handle:
        handle.write(str(process.pid))
    print(f"started (pid {process.pid})")


def off():
    """Stop the recorded gate with SIGTERM and drop the pidfile.

    `if not pid` — not `if pid is None` — so a pidfile holding 0 reports "not running",
    exactly as the original did. See `read_pid()`.

    Raises:
        ConfigError: if there is no config object, or it has no `pidfile` key.
    """
    pid = read_pid()
    if not pid:
        print("not running")
        return
    os.kill(pid, signal.SIGTERM)
    os.remove(_path_setting("pidfile"))
    print(f"stopped (pid {pid})")


def status():
    """Print three lines: is the process running, is the endpoint serving, is auth enforced.

    Only `auth_enforced_status` (401 in the original) reads as enforced; every other reachable
    code reads as "NOT enforcing", including a 500. An unreachable endpoint makes auth
    "unknown" rather than "NOT enforcing" — absence of evidence is not evidence.

    Creates nothing.

    Raises:
        ConfigError: if there is no config object, or it lacks a key this needs.
    """
    pid = read_pid()
    code = endpoint_status()
    enforced = _int_setting("auth_enforced_status")

    process_line = f"running (pid {pid})" if pid else "stopped"
    if code is None:
        endpoint_line = "not reachable"
        auth_line = "unknown"
    else:
        endpoint_line = f"HTTP {code}, serving"
        auth_line = "enforced (tokenless rejected)" if code == enforced else "NOT enforcing"

    print(f"process : {process_line}")
    print(f"endpoint: {endpoint_line}")
    print(f"auth    : {auth_line}")


#: The verb dispatch table — preserved as a module attribute because `main()` dispatches
#: through it and the original exposed it. Its key set IS the CLI's contract: anything else
#: is a usage error.
COMMANDS = {"on": on, "off": off, "status": status}


# ─────────────────────────────── the bug report ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception. Returns the path
    written, or None.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").

    TRULY best-effort: the whole body is guarded, because this runs INSIDE an `except` block
    and any exception raised here would REPLACE the real one the operator needs to see. That
    includes a `bug_reports` key holding a non-string, which would otherwise raise TypeError
    from `os.path.isabs` and bury the original error.
    """
    try:
        try:
            config = active_config()
            base = active_base()
        except ConfigError:
            return None                      # no config to tell us where reports go
        relative = config.get("bug_reports")
        if not isinstance(relative, str) or not relative:
            return None
        path = relative if os.path.isabs(relative) else os.path.join(base, relative)
        frames = traceback.extract_tb(exc.__traceback__)
        entry = {
            "filename": os.path.basename(os.path.abspath(__file__)),
            "function": frames[-1].name if frames else "?",
            "time-of-occurance": datetime.now().isoformat(),
            "methods-to-reproduce": "python3 %s %s" % (
                os.path.basename(os.path.abspath(__file__)), " ".join(argv)),
            "possible-cause": "%s: %s" % (type(exc).__name__, exc),
            "traceback": formatted.strip().splitlines()[-6:],
            "note": "%s (ticket #413, module key forge-rw:1fa0fdbc322b6466)" % UNIT,
        }
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except Exception:                        # noqa: BLE001 — never mask the real exception
        return None


# ─────────────────────────────── the command line ───────────────────────────────

def main():
    """The original's entry point, preserved exactly: dispatch `sys.argv[1]` through
    `COMMANDS`, defaulting to `status`, and `sys.exit(USAGE)` on anything else.

    Returns None, and exits 0, on success — so the `forge2-ats-service` console script, whose
    generated wrapper calls `sys.exit(main())`, exits 0 too. An unknown verb raises
    `SystemExit(USAGE)`, which prints the usage line on stderr and exits 1, for an in-process
    caller and the shell alike.

    NO verb was added. `selftest`, `--help` and `-h` are all unknown verbs here because they
    were unknown verbs in the original — see the module docstring on why, and for how to run
    the diagnostics.
    """
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    action = COMMANDS.get(command)
    if action is None:
        sys.exit(USAGE)
    try:
        action()
    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        raise SystemExit(2) from None
    except Exception as exc:                 # noqa: BLE001
        path = _bug_report(exc, traceback.format_exc(), sys.argv[1:])
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        # Re-raise: the original crashed with a traceback and a non-zero exit, and filing a
        # report must not change that.
        raise


# ───────────────────────── the exemplars and the selftest ─────────────────────────

#: The gate stand-in the selftest launches. It reports, on BOTH streams, the facts `on()` is
#: supposed to have arranged, so the logfile proves the env overlay, the merge and the detach.
_FAKE_SERVER = textwrap.dedent("""\
    import os, sys, time
    print("TRANSPORT=%r" % os.environ.get("ATS_TRANSPORT"))
    print("OWN_SESSION=%s" % (os.getsid(0) == os.getpid()))
    print("INHERITED_MARKER=%r" % os.environ.get("SELFTEST_MARKER"))
    sys.stdout.flush()
    sys.stderr.write("STDERR_MERGED=yes\\n")
    sys.stderr.flush()
    time.sleep(120)
    """)


class _Probe:
    """A real HTTP server on an ephemeral port that answers every request with `code` and
    records what it received — so the selftest checks the WIRE, not just the return value."""

    def __init__(self, code):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        self.seen = []
        seen = self.seen

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                seen.append({"method": self.command,
                             "body": self.rfile.read(length).decode("utf-8"),
                             "accept": self.headers.get("Accept"),
                             "content_type": self.headers.get("Content-Type")})
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_POST
            do_PUT = do_POST

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        return "http://127.0.0.1:%d/mcp" % self.server.server_address[1]

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        return False


def _dead_pid():
    """A pid that is certainly not running: spawn a process and wait for it to exit."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _await_death(pid, timeout=10.0):
    """Wait for the gate `pid` to die and return HOW it died: the terminating signal number,
    "exit-N", or None if it is still running when `timeout` expires.

    Why this REAPS rather than probing with `os.kill(pid, 0)`: inside this selftest the gate is
    a DIRECT CHILD of the running process, so once it dies it stays in the process table as a
    ZOMBIE until someone wait()s for it — and `os.kill(zombie, 0)` SUCCEEDS, which would report
    a dead gate as alive. (This is an artifact of testing in-process. The real launcher exits
    immediately after `on()`, so the gate is reparented to init and reaped there.) Reaping is
    also the stronger check: it proves the gate died OF SIGTERM, not merely that it stopped.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            reaped, wait_status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return "already-reaped"          # someone else got there first; it is gone
        if reaped == pid:
            if os.WIFSIGNALED(wait_status):
                return os.WTERMSIG(wait_status)
            return "exit-%d" % os.WEXITSTATUS(wait_status)
        time.sleep(0.05)
    return None


def _capture(fn, *args, **kwargs):
    """Run `fn` and return (stdout_text, returned_value)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        value = fn(*args, **kwargs)
    return buffer.getvalue(), value


def selftest(stream=None):
    """Replay the ORIGINAL's measured behavior against this rewrite. Returns 0 or 1.

    Every expected value below was OBSERVED by running the original — reconstructed from
    ticket #413's embedded source and confirmed byte-identical to the forge blob
    c7947a7e56c83c810b72ca13279c35431b762745 — inside a sandbox. These are #200's exemplars:
    the original is the oracle, and this replays what it actually did rather than what its
    source appears to say.

    Runs entirely inside a temporary directory it removes, against a real HTTP server on an
    ephemeral port and REAL detached child processes, which it reaps. It restores every global
    and environment variable it touches.
    """
    out = stream or sys.stdout
    checks = []

    def ck(name, ok, detail=""):
        checks.append((name, bool(ok)))
        print("  %-4s %s%s" % ("PASS" if ok else "FAIL", name,
                               "" if ok else "   <- %s" % detail), file=out)

    root = tempfile.mkdtemp(prefix="ats-selftest-")
    spawned = []
    saved_env = os.environ.get(CONFIG_ENV)
    saved_state = (_ACTIVE, _RESOLVED)
    try:
        os.environ.pop(CONFIG_ENV, None)
        reset_config()
        server_path = os.path.join(root, "gate.py")
        with open(server_path, "w") as handle:
            handle.write(_FAKE_SERVER)
        state = os.path.join(root, "state")
        pidfile = os.path.join(state, "gate.pid")
        logfile = os.path.join(state, "gate.out.log")

        def cfg(url="http://127.0.0.1:1/mcp", **over):
            base = dict(config_template())
            base.update({"pidfile": pidfile, "logfile": logfile, "python": sys.executable,
                         "server": server_path, "url": url, "timeout": 3})
            base.update(over)
            return base

        def write_pid(text):
            os.makedirs(state, exist_ok=True)
            with open(pidfile, "w") as handle:
                handle.write(text)

        print("== forge2:agent_tools_suite/ats_service — exemplars replayed from the original",
              file=out)
        print("-- read_pid(): the two ways of being 'not running' differ ON DISK", file=out)
        with using_config(cfg(), base=root):
            if os.path.exists(pidfile):
                os.remove(pidfile)
            ck("no pidfile -> None", read_pid() is None)

            write_pid("not-a-number")
            ck("garbage pidfile -> None", read_pid() is None)
            ck("garbage pidfile SURVIVES (ValueError path removes nothing)",
               os.path.exists(pidfile))

            write_pid("")
            ck("empty pidfile -> None", read_pid() is None)
            ck("empty pidfile SURVIVES", os.path.exists(pidfile))

            dead = _dead_pid()
            write_pid(str(dead))
            ck("stale pidfile -> None", read_pid() is None)
            ck("stale pidfile is REMOVED (OSError path clears it)", not os.path.exists(pidfile))

            live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            spawned.append(live.pid)
            write_pid("  %d\n" % live.pid)
            ck("live pid, whitespace-padded -> the pid (strip() honored)", read_pid() == live.pid)

            write_pid("0")
            got = read_pid()
            ck("pidfile '0' -> 0, NOT None (os.kill(0,0) probes the process group)", got == 0
               and got is not None, "got %r" % (got,))
            ck("pidfile '0' SURVIVES (the probe did not raise)", os.path.exists(pidfile))

            print("-- status(): three lines; only 401 is 'enforced'", file=out)
            write_pid("0")
            text, _ = _capture(status)
            ck("pidfile '0' -> 'stopped' (0 is falsy to every caller)",
               text == "process : stopped\nendpoint: not reachable\nauth    : unknown\n",
               repr(text))

            # Clear the whole state directory, so "creates nothing" is checked against an
            # absence this selftest did not itself create a moment ago.
            shutil.rmtree(state, ignore_errors=True)
            text, _ = _capture(status)
            ck("nothing running, nothing listening",
               text == "process : stopped\nendpoint: not reachable\nauth    : unknown\n",
               repr(text))
            ck("status() created NOTHING", not os.path.exists(state))

        for code, expect_auth in ((401, "enforced (tokenless rejected)"),
                                  (200, "NOT enforcing"),
                                  (500, "NOT enforcing")):
            with _Probe(code) as probe:
                with using_config(cfg(url=probe.url), base=root):
                    write_pid(str(live.pid))
                    text, _ = _capture(status)
                    ck("listener %d -> 'HTTP %d, serving' + %r" % (code, code, expect_auth),
                       text == ("process : running (pid %d)\nendpoint: HTTP %d, serving\n"
                                "auth    : %s\n" % (live.pid, code, expect_auth)), repr(text))
                    ck("endpoint_status() -> %d" % code, endpoint_status() == code)
                if probe.seen:
                    sent = probe.seen[0]
                    ck("probe %d: the wire carries the original's method/body/headers" % code,
                       sent["method"] == "POST"
                       and sent["body"] == ('{"jsonrpc": "2.0", "id": 1, "method": '
                                            '"initialize", "params": {}}')
                       and sent["accept"] == "application/json, text/event-stream"
                       and sent["content_type"] == "application/json", repr(sent))
                else:
                    ck("probe %d reached the listener" % code, False, "nothing recorded")

        print("-- on() / off(): the real lifecycle, with a real detached child", file=out)
        os.environ["SELFTEST_MARKER"] = "inherited"
        try:
            with using_config(cfg(), base=root):
                if os.path.exists(pidfile):
                    os.remove(pidfile)
                shutil.rmtree(state, ignore_errors=True)
                text, _ = _capture(on)
                gate = int(open(pidfile).read())
                spawned.append(gate)
                ck("on() prints 'started (pid N)' with the pid it wrote",
                   text == "started (pid %d)\n" % gate, repr(text))
                ck("on() created the pidfile directory", os.path.isdir(state))

                def wait_for_log(marker, seen_before=""):
                    """The logfile once the gate has appended `marker` past `seen_before`."""
                    deadline = time.time() + 10
                    text = ""
                    while time.time() < deadline:
                        if os.path.exists(logfile):
                            text = open(logfile).read()
                            if marker in text[len(seen_before):]:
                                return text
                        time.sleep(0.05)
                    return text

                log = wait_for_log("STDERR_MERGED")
                ck("the gate got server_env's ATS_TRANSPORT", "TRANSPORT='streamable-http'" in log,
                   repr(log))
                ck("the gate runs in its OWN SESSION (start_new_session)",
                   "OWN_SESSION=True" in log, repr(log))
                ck("the gate INHERITED this process's environment too",
                   "INHERITED_MARKER='inherited'" in log, repr(log))
                ck("stderr is MERGED into the same logfile", "STDERR_MERGED=yes" in log, repr(log))

                text, _ = _capture(on)
                ck("on() again -> 'already running (pid N)', no second gate",
                   text == "already running (pid %d)\n" % gate, repr(text))

                text, _ = _capture(status)
                ck("status() sees it running",
                   text.startswith("process : running (pid %d)\n" % gate), repr(text))

                before_text = open(logfile).read()
                text, _ = _capture(off)
                ck("off() prints 'stopped (pid N)'", text == "stopped (pid %d)\n" % gate, repr(text))
                ck("off() removed the pidfile", not os.path.exists(pidfile))

                how = _await_death(gate)
                ck("off() actually stopped the gate, and did it with SIGTERM",
                   how in (signal.SIGTERM, "already-reaped"), "died by %r" % (how,))

                text, _ = _capture(off)
                ck("off() when not running -> 'not running'", text == "not running\n", repr(text))

                text, _ = _capture(on)
                gate2 = int(open(pidfile).read())
                spawned.append(gate2)
                ck("on() starts a fresh gate after off()",
                   text == "started (pid %d)\n" % gate2 and gate2 != gate, repr(text))

                after_text = wait_for_log("STDERR_MERGED", before_text)
                ck("the logfile was APPENDED to, not truncated (mode 'a'): the first gate's "
                   "output is still there, with the second gate's after it",
                   after_text.startswith(before_text) and len(after_text) > len(before_text),
                   "before=%d after=%d" % (len(before_text), len(after_text)))
                _capture(off)
                _await_death(gate2)

                write_pid("0")
                text, _ = _capture(off)
                ck("off() with pidfile '0' -> 'not running' (0 is falsy)",
                   text == "not running\n", repr(text))
        finally:
            os.environ.pop("SELFTEST_MARKER", None)

        print("-- main(): the CLI contract, unchanged from the original", file=out)
        saved_argv = sys.argv
        try:
            with using_config(cfg(), base=root):
                if os.path.exists(pidfile):
                    os.remove(pidfile)
                sys.argv = ["ats_service.py"]
                text, _ = _capture(main)
                ck("no argv -> status is the default",
                   text.startswith("process : stopped\n"), repr(text))

                for verb in ("bogus", "selftest", "ON", "start", "--help", ""):
                    sys.argv = ["ats_service.py", verb]
                    try:
                        main()
                        ck("verb %r -> usage error" % verb, False, "did not exit")
                    except SystemExit as exc:
                        ck("verb %r -> SystemExit(%r)  [the original rejects it too]"
                           % (verb, USAGE), exc.code == USAGE, "got %r" % (exc.code,))
        finally:
            sys.argv = saved_argv

        print("-- the config gate (#200 req 4 / acceptance (d)): no config -> throw", file=out)
        reset_config()
        missing = os.path.join(root, "nope.json")
        os.environ[CONFIG_ENV] = missing
        try:
            for name, fn in (("read_pid", read_pid), ("endpoint_status", endpoint_status),
                             ("on", on), ("off", off), ("status", status)):
                try:
                    fn()
                    ck("%s() throws without a config" % name, False, "returned instead")
                except ConfigError:
                    ck("%s() throws ConfigError without a config" % name, True)
                except Exception as exc:      # noqa: BLE001
                    ck("%s() throws ConfigError without a config" % name, False,
                       "raised %r" % exc)
        finally:
            os.environ.pop(CONFIG_ENV, None)
            reset_config()

        partial = os.path.join(root, "partial.json")
        with open(partial, "w") as handle:
            json.dump({"pidfile": pidfile}, handle)     # has pidfile, lacks everything else
        os.environ[CONFIG_ENV] = partial
        try:
            reset_config()
            ck("a key a verb does NOT need is not demanded (read_pid with only 'pidfile')",
               read_pid() is None)
            try:
                endpoint_status()
                ck("endpoint_status() throws when 'url' is absent", False, "returned instead")
            except ConfigError as exc:
                ck("endpoint_status() throws ConfigError naming the missing key",
                   "'url'" in str(exc), str(exc))
        finally:
            os.environ.pop(CONFIG_ENV, None)
            reset_config()

        bad = os.path.join(root, "bad.json")
        with open(bad, "w") as handle:
            json.dump(dict(config_template(), auth_enforced_status="401"), handle)
        os.environ[CONFIG_ENV] = bad
        try:
            reset_config()
            try:
                status()
                ck("a wrongly-typed key throws", False, "returned instead")
            except ConfigError:
                ck("a wrongly-typed key ('auth_enforced_status': \"401\") throws ConfigError", True)
        finally:
            os.environ.pop(CONFIG_ENV, None)
            reset_config()

    finally:
        for pid in spawned:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        shutil.rmtree(root, ignore_errors=True)
        if saved_env is None:
            os.environ.pop(CONFIG_ENV, None)
        else:
            os.environ[CONFIG_ENV] = saved_env
        globals()["_ACTIVE"], globals()["_RESOLVED"] = saved_state

    failed = [name for name, ok in checks if not ok]
    print("\n%d/%d checks passed%s"
          % (len(checks) - len(failed), len(checks),
             "" if not failed else " — FAILED: %s" % ", ".join(failed)), file=out)
    return 0 if not failed else 1


# ──────────────────── the packaging, checked against itself ────────────────────

def check_package(stream=None):
    """Prove this package's DERIVED pyproject.toml is coherent with this module. Returns 0/1.

    Checks what an install depends on: that the pyproject parses, declares the import package
    this module names, maps it onto this directory, ships registry.json as package data, and
    declares a console script whose `module:function` target actually resolves to a callable.

    Imports the package to resolve that target, with bytecode writing switched OFF so it
    leaves no __pycache__ behind.
    """
    out = stream or sys.stdout
    checks = []

    def ck(name, ok, detail=""):
        checks.append((name, bool(ok)))
        print("  %-4s %s%s" % ("PASS" if ok else "FAIL", name,
                               "" if ok else "   <- %s" % detail), file=out)

    try:
        import tomllib
    except ImportError:
        print("check_package: needs Python 3.11+ for tomllib; skipped", file=out)
        return 0

    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "pyproject.toml")
    print("== packaging: %s" % path, file=out)
    if not os.path.isfile(path):
        ck("pyproject.toml exists", False, "not found — the package cannot install")
        return 1
    with open(path, "rb") as handle:
        data = tomllib.load(handle)

    ck("pyproject.toml parses as TOML", True)
    tool = data.get("tool", {}).get("setuptools", {})
    ck("declares the import package %r" % IMPORT_PACKAGE,
       IMPORT_PACKAGE in tool.get("packages", []), repr(tool.get("packages")))
    ck("maps %r onto this directory" % IMPORT_PACKAGE,
       tool.get("package-dir", {}).get(IMPORT_PACKAGE) == ".", repr(tool.get("package-dir")))
    ck("ships %s as package data (so a non-editable install can still see its config)"
       % REGISTRY_NAME,
       REGISTRY_NAME in tool.get("package-data", {}).get(IMPORT_PACKAGE, []),
       repr(tool.get("package-data")))
    ck("declares a build backend",
       bool(data.get("build-system", {}).get("build-backend")), repr(data.get("build-system")))
    ck("names a distribution", bool(data.get("project", {}).get("name")))

    stem = os.path.splitext(os.path.basename(os.path.abspath(__file__)))[0]
    scripts = data.get("project", {}).get("scripts", {})
    target = "%s.%s:main" % (IMPORT_PACKAGE, stem)
    named = [name for name, value in scripts.items() if value == target]
    ck("declares a console script pointing at %s" % target, bool(named), repr(scripts))

    if named:
        parent = os.path.dirname(here)
        saved_path, saved_bytecode = list(sys.path), sys.dont_write_bytecode
        sys.dont_write_bytecode = True       # leave no __pycache__ beside the source
        try:
            if parent not in sys.path:
                sys.path.insert(0, parent)
            import importlib
            module = importlib.import_module("%s.%s" % (IMPORT_PACKAGE, stem))
            ck("the console-script target resolves to a callable",
               callable(getattr(module, "main", None)))
            ck("the package imports under the name the pyproject declares, and exposes the "
               "original's surface",
               all(callable(getattr(module, n, None))
                   for n in ("read_pid", "endpoint_status", "on", "off", "status", "main")))
        except ImportError as exc:
            ck("the package imports under the name the pyproject declares", False, str(exc))
        finally:
            sys.path[:] = saved_path
            sys.dont_write_bytecode = saved_bytecode

    registry = os.path.join(here, REGISTRY_NAME)
    if os.path.isfile(registry):
        with open(registry) as handle:
            document = json.load(handle)
        node = document
        ok = True
        for key in UNIT_PATH:
            if not isinstance(node, dict) or key not in node:
                ok = False
                break
            node = node[key]
        ck("registry.json carries this unit's own %s section" % ".".join(UNIT_PATH), ok)
        if ok:
            ck("that section has every key this module requires",
               all(k in node for k in ("pidfile", "logfile", "python", "server", "url",
                                       "timeout", "server_env", "probe",
                                       "auth_enforced_status")),
               repr(sorted(node)))
    else:
        ck("registry.json exists", False, "not found")

    failed = [name for name, ok in checks if not ok]
    print("\n%d/%d checks passed%s"
          % (len(checks) - len(failed), len(checks),
             "" if not failed else " — FAILED: %s" % ", ".join(failed)), file=out)
    return 0 if not failed else 1


if __name__ == "__main__":
    main()
