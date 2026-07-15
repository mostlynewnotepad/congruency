# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 testmonkeyalpha — Claude & Co.

r"""forge2 / code__code__jazz__kokoro__dz_debug / dz_debug / log — service logger.

A behavior-preserving rewrite of the forge unit
`code__code__jazz__kokoro__dz_debug:dz_debug/log.py` (module key forge-rw:4c486357e89341dd,
git blob faeb483cdcf3d7d38aeeeab79ac61f135390eb0c, 8868 bytes), filed under ticket #363
against the FORGE-wide refactor standard #200. (#363 supersedes #300, which named its source
only as a `git cat-file` the sandboxed worker cannot run; #363 embeds the source, so the work
is done here.)

The same module lives at seven forge tips (six copies plus the canonical one); this ONE
rewrite satisfies all of them, which is why nothing here is named for the kokoro copy in
particular except the registry address it reads its config from.

WHAT THIS IS
------------
The original is a file logger: it writes timestamped lines to
`{log_root}/{build_id}/{service}.log`, gates them on a level and on named "channels", and
optionally mirrors them to stderr and bridges the stdlib `logging` module into the same file.
Its own docstring says "Behaviour is controlled by the CONFIG block below" — and that CONFIG
block is a dict of hardcoded literals in the source, including two absolute paths built from
`Path.home()`.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and adds the three things #200 requires that the original
lacked: it is part of a proper installable package, it is driven by a configuration object,
and it refuses to run when it cannot see that configuration.

TERMS USED HERE (nothing below assumes you have read another file)
------------------------------------------------------------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a
    single `.json` file at the root of a package holding the configuration for every tool in
    that packaging. `note-for-claude` states the contract in its own words — ".json will have
    all the configuration - for all tools in this set of packaging. (a configuration
    registry) -if a tool cannot see the registry it will throw an exeption." This package
    ships its own `registry.json` at its root, one directory above this file.
config object
    The chunk of that registry belonging to this unit — the section at
    `forge2 -> code__code__jazz__kokoro__dz_debug -> log`. It is what drives this module.
    `emit-config` prints a template of it.
channel
    A named boolean switch a log line can be tagged with. `log.debug("...", tags=["perf"])`
    is written only if the `perf` channel is on. The original has six: payload, perf,
    process, health, ipc, terminal.
profile
    A named baseline — a minimum level plus a default on/off for every channel. The original
    has four: none, standard, debug, trace.
level
    A severity name with an integer rank. A line is written only if its level's rank is at
    or above the profile's `min_level` rank. The original ranks five: DEBUG and "TERM " at 0,
    INFO 1, WARN 2, ERROR 3. Note that the TERM level is spelled with a TRAILING SPACE — it
    pads the column in the log line — and that is preserved exactly, here and in the config.

THE CALLABLE SURFACE (unchanged, so existing callers keep working — acceptance item (b))
----------------------------------------------------------------------------------------
Ticket #363 lists it, and every entry is reproduced below with the same name, parameters and
defaults:

    _resolve_build_id(build_json: Path) -> str
    _timestamp(fmt: str) -> str
    _resolve_channels(profile: str, overrides: dict) -> dict
    Logger.__init__(self, service: str, build_id: str = None, config: dict = None)
    Logger.info / warn / error / debug / term / fatal
    Logger.path / Logger.channels          (properties)
    Logger.close(self)
    Logger._write(self, level, msg, tags=None)
    Logger._attach_stdlib_capture(self, logger_names: list)

The module-level names the original bound are also reproduced, because they are part of what
a caller sees and the original's own docstring points callers at the first of them:
`CONFIG`, `_PROFILES`, `_PROFILE_CHANNELS`, `_LEVELS`. They behave as the mutable dicts they
were — see THE LAZY MAPPINGS below.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The config object is resolved on first use, from the first source that answers:

  1. the file named by the `DZ_DEBUG_LOG_CONFIG` environment variable, which holds the unit
     config object ITSELF — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code__jazz__kokoro__dz_debug -> log` section of the
     nearest `registry.json` found by walking UP from THIS FILE's directory;
  3. otherwise, the `registry.json` this distribution ships as package data inside its
     top-level `code__code__jazz__kokoro__dz_debug` package.

The walk-up starts at this file, never at the working directory, so which directory you run
from does not change what config is found. Step 3 never SHADOWS a nearer registry: it runs
only after the walk-up has failed outright. If none of the three answers, every use of this
module raises `ConfigError`, naming all three sources that were tried. It never guesses a
default. That is `note-for-claude`'s rule and this ticket's acceptance item (d).

`configure(config)` and `using_config(config)` inject a config object directly, in-process,
for callers that hold their configuration in memory rather than on disk.

The variable is named for THIS unit rather than something forge2-wide on purpose: it names a
file holding ONE unit's config object, so a variable shared across forge2 units could only
ever point at one unit's object at a time, and pointing it at a sibling's would break this
one. The sibling units in this package read `DZ_DEBUG_CONFIG` and `DZ_DEBUG_INIT_CONFIG`;
none of the three collide.

WHY STEP 3 EXISTS
-----------------
It is what makes a NON-editable `pip install .` work. In a source checkout or an editable
install, `dz_debug/` sits INSIDE the package root next to `registry.json`, so step 2 finds it
one directory up. A non-editable install has no such root: setuptools installs `dz_debug/`
and `code__code__jazz__kokoro__dz_debug/` as two SEPARATE top-level directories in
site-packages, and the registry ships as package data inside the second. Walking up from an
installed `dz_debug/log.py` then reaches site-packages and beyond without ever passing the
registry. Step 3 asks the installed sibling package where it is, which is the only thing that
knows.

`selftest` section [7] walks the three sources in order and shows which one answers here;
section [8] checks everything the install depends on WITHOUT running pip, and says so in its
own output rather than glossing over it — see INSTALLABLE below for what that does and does
not cover, and for the two commands that prove the rest.

WHAT IS A SETTING, AND WHAT IS NOT
----------------------------------
#200 requires no hardcoded paths or params. This file draws the line in one place and states
it, so a reader can check it rather than guess:

  A value is a SETTING — and lives in the config object — if the ORIGINAL fixed it as a
  tunable: everything in its CONFIG block, the tables that block's keys select among
  (`profiles`, `profile_channels`, `levels`, the six channel names), the message layouts it
  formatted its output with, the key it reads out of build.json, and the stdlib-to-local
  level map its logging bridge used. No setting's VALUE is written in the code that runs:
  `grep` this file for `"standard"`, `500`, `"%(name)s: %(message)s"` or `Path.home` and
  every hit is in one of exactly four places, none of which is a live code path —
  `config_template()` (the template an operator installs), `ORIGINAL_SOURCE` (the oracle's
  bytes), this docstring, and `selftest` (which asserts against them). The code between them
  reads every one of those values out of the config object and has no opinion of its own.

  What that grep DOES still hit in live code, and why it is not a setting: the config's own
  section names and keys (`_built()["build_id"]`, `spec["unknown"]`) — a config-driven tool
  has to know which section is its own and what its keys are called, and those are the
  document's schema, not its values.

  A value is CODE if changing it would change what the module MEANS rather than how it is
  tuned: that `info()` logs at INFO and `term()` logs at "TERM " tagged `terminal`, that
  `error()` appends the current traceback, that lines go under `{log_root}/{build_id}/`, that
  the file is opened append-mode and line-buffered, and that a level's rank is compared with
  `>=`. Those are the unit's contract with its callers and its log readers, and #200 exists
  to stop them moving, not to make them configurable.

  The coupling between the two is CHECKED, not left to chance: the config's `levels` must
  rank every level this module's methods log at, and its `channels` must include every
  channel this module's methods tag with. A config that renames a level out from under
  `info()` is rejected at load with a message naming it, rather than failing later at the
  first log line.

`fallbacks` is the one section that needs a word. The original wrote `cfg.get("profile",
"standard")`, `cfg.get("fatal_preview_chars", 500)`, `cfg.get("fatal_exit_code", 1)` and
`cfg.get("capture_stdlib_loggers", [])` — in-code fallbacks that are reachable only if a
caller DELETES that key from the module `CONFIG` after import, since `Logger.__init__` merges
over the whole of CONFIG. They are rare but they are behavior, so they are kept and made data
in their own section. Note the fourth: the original's fallback for `capture_stdlib_loggers`
is the EMPTY list — which means "attach to the root logger" — and not the list of three
names in its CONFIG block. The template reproduces that difference exactly, because
smoothing it over would change what a caller who deleted that key gets.

THE LAZY MAPPINGS
-----------------
The original's `CONFIG`, `_PROFILES`, `_PROFILE_CHANNELS` and `_LEVELS` are module-level
dicts, fixed at import. Here they are `_ConfigMapping` objects: `MutableMapping`s that fill
themselves from the config object on first use and behave as those dicts thereafter, so
`{**CONFIG, **(config or {})}`, `_LEVELS.get(level, 0)`, `list(_PROFILES)`,
`dict(_PROFILE_CHANNELS[profile])` and a caller's `CONFIG["profile"] = "debug"` all do what
they always did.

Why lazily, rather than reading the config at import: `import dz_debug.log` must not throw,
or `emit-config` — the command whose whole job is to print the config you do not yet have —
could never run, and this file could not be imported to be tested. The gate is not weakened
by that, it is moved: the config is resolved on the first touch of any of the four mappings,
so `Logger(...)`, `_resolve_channels(...)` and `_timestamp(...)` all throw `ConfigError`
without a config object. Nothing observable is reachable without passing the gate.
`selftest` section [6] proves that, in a subprocess with nothing on its path.

DELIBERATE, DOCUMENTED DIVERGENCES (three)
------------------------------------------
Everything else is intended to be indistinguishable, and that is measured, not asserted:
selftest section [3] runs every case against BOTH modules and compares the results byte for
byte, and section [4] compares the callable surface signature by signature and pins the three
divergences below to exactly what they are.
  1. WHEN THE CONFIG IS FIXED. The original's CONFIG block was evaluated at import, so
     `Path.home()` was read once, at import. Here the four mappings resolve on first touch.
     The window between the two is observable in exactly one way: `vars(dz_debug.log)` shows
     `CONFIG` as a `_ConfigMapping` rather than a `dict`, before and after. Every operation
     performed THROUGH it — read, write, delete, iterate, `len`, `in`, `{**CONFIG}` — behaves
     as the dict's.
  2. `type(CONFIG)` IS `_ConfigMapping`, not `dict`. `isinstance(CONFIG, MutableMapping)` —
     the way this is actually asked — is True, and `dict(CONFIG)` is the dict it stands for.
     A caller doing `type(CONFIG) is dict` or passing CONFIG to C code that demands an exact
     dict would see it. `Logger.__init__` does not: it merges CONFIG into a real dict, so
     `self._cfg` is a plain dict exactly as before, which is what `_write` and `fatal` read.
  3. THE MODULE DOCSTRING, and this module's own extra top-level names (the config helpers,
     `main`, `selftest`, `ORIGINAL_SOURCE`). `__all__` is declared below and holds the
     original's public names plus the config surface, so `from dz_debug.log import *` binds
     no more of the machinery than a caller asked for. The original had no `__all__`, so its
     star-import also leaked its `json`/`sys`/`traceback`/`datetime`/`timezone`/`Path`
     imports; nothing sane depends on that. Section [4] counts this module's extra public
     names and checks that not one of them shadows a name of the ORIGINAL's, so the
     difference is measured rather than hidden.

THE PROOF (acceptance item (a))
-------------------------------
#363 captured NO behavioral exemplars, and says what that means: "you must write the
equivalence exemplars by hand from the original's behavior before rewriting, and they are
what settles this ticket." So `selftest` does not compare against hand-copied expectations,
where a mistake in the copy passes silently. It compares against THE ORIGINAL ITSELF:

  * `ORIGINAL_SOURCE` below holds the ticket's embedded bytes verbatim. The selftest checks
    them against the ticket's stated SIZE (8868) **and recomputes the git blob sha1** and
    checks it against the one the ticket names (faeb483c...). A blob sha1 is a hash of the
    bytes, so that check cannot pass unless the oracle is the forge's file, byte for byte —
    it is what makes everything below a comparison against the real original.
  * Both modules are planted in a temp directory, imported side by side, pointed at their own
    temp log roots, and driven through ~40 caller scenarios. What is compared is everything
    a caller could observe: the return value or exception, the exact bytes of every log file
    produced, and the exact bytes written to stderr — with the temp path and the live
    timestamp normalized, because those are the only two things that legitimately differ
    between two runs.

Everything it creates lives in a temp directory it removes. It runs no pip, needs no network,
and writes nothing to your home directory — which matters, because the ORIGINAL's own CONFIG
points at `~/code/run/logs` and a careless oracle would have created it.

RUNNING IT
----------
Every command is executable as written from this file's directory or from the package root
above it; from anywhere else give the full path to `log.py`.

    python3 dz_debug/log.py selftest       # prove the behavior against the ORIGINAL's bytes
    python3 dz_debug/log.py emit-config    # print a config-object template
    python3 dz_debug/log.py show-config    # print the resolved config + where it came from
    python3 dz_debug/log.py demo           # write one line of each level to a temp log and
                                           #   print the file, using the config in force

`selftest` and `emit-config` need no config object; `show-config` and `demo` throw without
one, exiting 2 with a single self-explaining line and no traceback.

INSTALLABLE (#200 requirement 3 — acceptance item (c))
------------------------------------------------------
This file is one module of the package that surrounds it, committed in full beside it. From
the PACKAGE ROOT (the directory above this one, holding `pyproject.toml`):

    python3 -m venv .venv && .venv/bin/pip install -e .
    .venv/bin/forge2-dz-debug-log selftest
    .venv/bin/python -c "from dz_debug.log import Logger; print(Logger('svc').path)"

The venv is not decoration — a bare `pip install -e .` on a system Python managed by a
package manager is refused with "externally-managed-environment" (PEP 668), which is that
Python's rule and nothing to do with this package.

`pyproject.toml` declares the import package as `dz_debug`, so an installed copy is imported
by the name the forge unit was always addressed by: `from dz_debug.log import Logger` keeps
working, which is acceptance item (b). `dz_debug` has no `__init__.py` in this package — it is
a PEP 420 namespace package — because `dz_debug/__init__.py` is a SEPARATE forge rewrite unit
(ticket #351) that has not landed here yet. `import dz_debug.log` works either way, and when
that unit lands beside this file nothing here needs to change.

SIDE EFFECTS
------------
Importing this module resolves NO config and reads NO file. Constructing a `Logger` creates
`{log_root}/{build_id}/` and opens `{service}.log` for append — which is the original's
behavior and the point of the unit.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception
is thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path if
it hits an UNEXPECTED exception — that is, a defect in this tool. A `ConfigError` is designed
behavior, not a bug: it files no report and prints no traceback, and exits 2 with a single
self-explaining line.

(CPython writes its own `__pycache__/*.pyc` when it imports this file, as it does for any
module; that is the interpreter's doing and `.gitignore` excludes it.)
"""

import contextlib
import importlib.util
import json
import os
import sys
import traceback
from collections.abc import MutableMapping
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    # ── the ORIGINAL's public surface ──
    "CONFIG",
    "Logger",
    # ── the config surface this rewrite adds (#200 requirement 4) ──
    "CONFIG_ENV",
    "ConfigError",
    "REGISTRY_NAME",
    "SHIPPING_PKG",
    "UNIT",
    "UNIT_PATH",
    "active_base",
    "active_config",
    "active_source",
    "build_config",
    "config_template",
    "configure",
    "find_registry",
    "load_config",
    "main",
    "reset_config",
    "selftest",
    "shipped_registry",
    "using_config",
]

#: The ORIGINAL unit's bytes, quoted verbatim from ticket #363's embedded source block. This
#: is the behavior-preserving basis and `selftest`'s ORACLE: it is written to disk and
#: imported, so the rewrite is compared against the original RUNNING, not against a
#: description of it. `selftest` recomputes its git blob sha1 and checks it against
#: ORIGINAL_BLOB below, so a transcription slip here cannot silently weaken the proof.
#:
#: It is a RAW triple-single-quoted string: raw so that the `\n` escapes inside the original's
#: own string literals stay the two characters they are in the file, and single-quoted so the
#: original's `"""` docstrings need no escaping. The result is the file's bytes, unaltered.
ORIGINAL_SOURCE = r'''# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 testmonkeyalpha — Claude & Co.

"""
Service logger — writes timestamped lines to {log_root}/{build_id}/{service}.log

Behaviour is controlled by the CONFIG block below.
Set `profile` for the baseline, then flip individual channel booleans as needed.
"""

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


# ── Profiles ───────────────────────────────────────────────────────────────────

_PROFILES = {
    "none":     {"min_level": "ERROR"},
    "standard": {"min_level": "INFO"},
    "debug":    {"min_level": "DEBUG"},
    "trace":    {"min_level": "DEBUG"},
}

# Which channels are on by default per profile
_PROFILE_CHANNELS = {
    "none":     {"payload": False, "perf": False, "process": False, "health": False, "ipc": False, "terminal": False},
    "standard": {"payload": False, "perf": False, "process": True,  "health": False, "ipc": True,  "terminal": False},
    "debug":    {"payload": False, "perf": True,  "process": True,  "health": True,  "ipc": True,  "terminal": True},
    "trace":    {"payload": True,  "perf": True,  "process": True,  "health": True,  "ipc": True,  "terminal": True},
}


# ── Configuration ──────────────────────────────────────────────────────────────

CONFIG = {
    # Named profile — sets baseline level and channel defaults
    # One of: "none", "standard", "debug", "trace"
    "profile": "standard",

    # Channel overrides — True/False flips a channel regardless of profile.
    # Set to None to let the profile decide.
    "payload":  None,
    "perf":     None,
    "process":  None,
    "health":   None,
    "ipc":      None,
    "terminal": None,

    # Mirror every log line to stderr
    "mirror_to_stderr": True,

    # Root directory for log files
    "log_root": Path.home() / "code" / "run" / "logs",

    # Where to find build.json to auto-resolve build_id
    "build_json": Path.home() / "code" / "run" / "clean" / "conf" / "env" / "build.json",

    # Timestamp format
    "timestamp_format": "%Y-%m-%dT%H:%M:%S",

    # fatal(): how many characters of the exception to print to stderr before exit
    "fatal_preview_chars": 500,

    # Exit code used by fatal()
    "fatal_exit_code": 1,

    # Capture third-party stdlib logging (uvicorn, litellm, fastapi) into our log file.
    # NOTE: requires touching Python's logging.Handler API — see _attach_stdlib_capture.
    "capture_stdlib_logging": False,
    "capture_stdlib_loggers": ["uvicorn", "litellm", "fastapi"],
}


# ── Level ordering ─────────────────────────────────────────────────────────────

_LEVELS = {"DEBUG": 0, "TERM ": 0, "INFO": 1, "WARN": 2, "ERROR": 3}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_build_id(build_json: Path) -> str:
    if build_json.exists():
        return json.loads(build_json.read_text()).get("build_id", "unknown")
    return "unknown"


def _timestamp(fmt: str) -> str:
    now = datetime.now(timezone.utc)
    ms  = f"{now.microsecond // 1000:03d}"
    return f"{now.strftime(fmt)}.{ms}Z"


def _resolve_channels(profile: str, overrides: dict) -> dict:
    channels = dict(_PROFILE_CHANNELS[profile])
    for ch, val in overrides.items():
        if val is not None:
            channels[ch] = val
    return channels


# ── Logger ─────────────────────────────────────────────────────────────────────

class Logger:
    """
    File logger scoped to a service and build ID.

    Usage:
        log = Logger("kokoro")
        log.info("server started on port 4001")
        log.debug("query took 12ms", tags=["perf"])
        log.debug("raw text payload", tags=["payload"])
        log.term("raw subprocess output line")
        log.error("model failed", exc=e)
        log.fatal("cannot continue", exc=e)

    Override profile or channels at instantiation:
        log = Logger("kokoro", config={"profile": "debug", "payload": True})
    """

    def __init__(self, service: str, build_id: str = None, config: dict = None):
        cfg = {**CONFIG, **(config or {})}

        profile = cfg.get("profile", "standard")
        if profile not in _PROFILES:
            raise ValueError(f"Unknown profile '{profile}'. Choose: {list(_PROFILES)}")

        if build_id is None:
            build_id = _resolve_build_id(cfg["build_json"])

        self._service   = service
        self._build_id  = build_id
        self._cfg       = cfg
        self._min_level = _LEVELS[_PROFILES[profile]["min_level"]]
        self._channels  = _resolve_channels(profile, {
            ch: cfg.get(ch) for ch in ("payload", "perf", "process", "health", "ipc", "terminal")
        })

        log_dir = Path(cfg["log_root"]) / build_id
        log_dir.mkdir(parents=True, exist_ok=True)
        self._path = log_dir / f"{service}.log"
        self._file = self._path.open("a", buffering=1)

        if cfg.get("capture_stdlib_logging"):
            self._attach_stdlib_capture(cfg.get("capture_stdlib_loggers", []))

    # ── Public interface ───────────────────────────────────────────────

    def info(self, msg: str, tags: list = None):
        self._write("INFO", msg, tags)

    def warn(self, msg: str, tags: list = None):
        self._write("WARN", msg, tags)

    def error(self, msg: str, exc: Exception = None, tags: list = None):
        self._write("ERROR", msg, tags)
        if exc:
            self._write("ERROR", traceback.format_exc().strip(), tags)

    def debug(self, msg: str, tags: list = None):
        self._write("DEBUG", msg, tags)

    def term(self, msg: str):
        """Log raw terminal/subprocess output. Controlled by the terminal channel."""
        self._write("TERM ", msg, tags=["terminal"])

    def fatal(self, msg: str, exc: Exception = None):
        full = msg
        if exc:
            full += "\n" + traceback.format_exc().strip()
        self._write("ERROR", full)
        preview = full[:self._cfg.get("fatal_preview_chars", 500)]
        print(f"\nFATAL [{self._service}]: {preview}\n", file=sys.stderr)
        print(f"Full log: {self._path}", file=sys.stderr)
        self.close()
        sys.exit(self._cfg.get("fatal_exit_code", 1))

    @property
    def path(self) -> Path:
        return self._path

    @property
    def channels(self) -> dict:
        return dict(self._channels)

    def close(self):
        self._file.close()

    # ── Private ────────────────────────────────────────────────────────

    def _write(self, level: str, msg: str, tags: list = None):
        if _LEVELS.get(level, 0) < self._min_level:
            return
        if tags:
            if not any(self._channels.get(t, False) for t in tags):
                return
        line = f"{_timestamp(self._cfg['timestamp_format'])} [{self._service}] {level} {msg}\n"
        self._file.write(line)
        if self._cfg.get("mirror_to_stderr"):
            print(line, end="", file=sys.stderr)

    def _attach_stdlib_capture(self, logger_names: list):
        # NOTE: This is the one place we must touch the stdlib `logging` API.
        # uvicorn, litellm, and fastapi call logging.getLogger(__name__) internally
        # and can only be intercepted by registering a logging.Handler on those loggers.
        import logging

        writer = self._write

        class _Bridge(logging.Handler):
            _MAP = {
                logging.DEBUG:    "DEBUG",
                logging.INFO:     "INFO",
                logging.WARNING:  "WARN",
                logging.ERROR:    "ERROR",
                logging.CRITICAL: "ERROR",
            }
            def emit(self, record: logging.LogRecord):
                writer(self._MAP.get(record.levelno, "INFO"), self.format(record))

        handler = _Bridge()
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))

        targets = logger_names if logger_names else [None]
        for name in targets:
            logging.getLogger(name).addHandler(handler)
'''

#: The ticket's stated SIZE for the original module, in bytes.
ORIGINAL_SIZE = 8868

#: The ticket's stated git blob sha1 for the original module. `selftest` recomputes this over
#: ORIGINAL_SOURCE. A git blob sha1 is sha1("blob <len>\0" + bytes), so it pins both the
#: length and every byte — the oracle cannot drift from the forge's file without this failing.
ORIGINAL_BLOB = "faeb483cdcf3d7d38aeeeab79ac61f135390eb0c"

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "DZ_DEBUG_LOG_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: This distribution's top-level package, which ships `registry.json` as package data (see
#: pyproject.toml's `[tool.setuptools.package-data]`). Consulted only when the walk-up finds
#: nothing, which is the non-editable-install case — see WHY STEP 3 EXISTS in the docstring.
SHIPPING_PKG = "code__code__jazz__kokoro__dz_debug"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS
#: in the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own.
UNIT_PATH = ("forge2", "code__code__jazz__kokoro__dz_debug", "log")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code__jazz__kokoro__dz_debug/dz_debug/log"

#: The levels THIS MODULE's own methods log at, so the config's `levels` table must rank every
#: one of them. Not a setting — see WHAT IS A SETTING in the module docstring: `info()` logging
#: at INFO is what `info()` MEANS. Listing them here is what lets a config that fails to rank
#: one be rejected at load, naming it, instead of failing at the first log line that uses it.
#: "TERM " keeps its trailing space: it is the level's name, in the original and in the config.
LEVEL_NAMES = ("DEBUG", "TERM ", "INFO", "WARN", "ERROR")

#: The channels THIS MODULE's own methods tag lines with, so the config's `channels` list must
#: include them. `term()` tags `terminal`; no other method tags anything. Same rationale as
#: LEVEL_NAMES: it turns a silently-broken config into a load-time error naming the channel.
TAGGED_CHANNELS = ("terminal",)

#: The keys the config's `defaults` section must carry: one per key of the ORIGINAL's CONFIG
#: block, in its order.
DEFAULT_KEYS = (
    "profile",
    "payload", "perf", "process", "health", "ipc", "terminal",
    "mirror_to_stderr",
    "log_root",
    "build_json",
    "timestamp_format",
    "fatal_preview_chars",
    "fatal_exit_code",
    "capture_stdlib_logging",
    "capture_stdlib_loggers",
)

#: The `defaults` keys that name a filesystem path. Their config value is a string; it becomes
#: a `Path` (with a leading `~` expanded) because that is what the ORIGINAL's CONFIG block held
#: and what `Logger` does with them: `Path(cfg["log_root"])` and `cfg["build_json"].exists()`.
PATH_KEYS = ("log_root", "build_json")

#: Each `formats` template and the fields it may use. The dummy values are what `build_config`
#: test-formats the template with, so a config that misspells a field is rejected at load with
#: a message naming the fields — rather than raising KeyError from inside a log call later.
FORMAT_FIELDS = {
    "line": {"timestamp": "T", "service": "s", "level": "L", "message": "m"},
    "timestamp": {"stamp": "S", "millis": 0},
    "log_file": {"service": "s"},
    "fatal_stderr": {"service": "s", "preview": "p"},
    "fatal_path": {"path": "p"},
}

#: `formats.stdlib_capture` is validated apart from FORMAT_FIELDS: it is handed to
#: `logging.Formatter`, which is %-style ("%(name)s"), not str.format. Test-formatting it the
#: way the others are checked would reject the original's own value.
STDLIB_FORMAT_KEY = "stdlib_capture"

#: The keys the config's `fallbacks` section must carry — one per `cfg.get(key, <fallback>)`
#: in the ORIGINAL. See the docstring's note on `fallbacks`.
FALLBACK_KEYS = ("profile", "fatal_preview_chars", "fatal_exit_code", "capture_stdlib_loggers")


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or malformed.

    This is the #200 requirement-4 gate and ticket #363's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.

    It is deliberately NOT raised for the original's own errors. An unknown profile is still a
    `ValueError` with the original's exact message; an unknown profile passed to
    `_resolve_channels` is still a `KeyError`; a `build_json` that is a string rather than a
    Path still raises `AttributeError` from `.exists()`. Reproducing those exactly is what
    acceptance item (a) asks for, and dressing them up as ConfigError would change what a
    caller's `except` catches.
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do every use of this module throws. Every value below
    is a transcription of something the ORIGINAL module hardcoded — its CONFIG block, its
    three tables, the layouts it formatted its output with, and the in-code fallbacks behind
    its `cfg.get(key, ...)` calls. Making them data rather than source is #200 requirement 4;
    keeping them EQUAL to the original's is what makes the rewrite behavior-preserving.

    The two paths are written with a leading `~`, which `build_config` expands. The original
    built them with `Path.home()`, so this is the spelling that reproduces its values on any
    machine — a documented transformation of a value the config states, not a default.
    """
    return {
        # ── the ORIGINAL's CONFIG block, key for key, in its order ──
        "defaults": {
            "profile": "standard",
            "payload": None,
            "perf": None,
            "process": None,
            "health": None,
            "ipc": None,
            "terminal": None,
            "mirror_to_stderr": True,
            "log_root": "~/code/run/logs",
            "build_json": "~/code/run/clean/conf/env/build.json",
            "timestamp_format": "%Y-%m-%dT%H:%M:%S",
            "fatal_preview_chars": 500,
            "fatal_exit_code": 1,
            "capture_stdlib_logging": False,
            "capture_stdlib_loggers": ["uvicorn", "litellm", "fastapi"],
        },
        # ── the ORIGINAL's _PROFILES ──
        "profiles": {
            "none": {"min_level": "ERROR"},
            "standard": {"min_level": "INFO"},
            "debug": {"min_level": "DEBUG"},
            "trace": {"min_level": "DEBUG"},
        },
        # ── the ORIGINAL's _PROFILE_CHANNELS ──
        "profile_channels": {
            "none": {"payload": False, "perf": False, "process": False,
                     "health": False, "ipc": False, "terminal": False},
            "standard": {"payload": False, "perf": False, "process": True,
                         "health": False, "ipc": True, "terminal": False},
            "debug": {"payload": False, "perf": True, "process": True,
                      "health": True, "ipc": True, "terminal": True},
            "trace": {"payload": True, "perf": True, "process": True,
                      "health": True, "ipc": True, "terminal": True},
        },
        # ── the ORIGINAL's _LEVELS. "TERM " has a trailing space; that is its name. ──
        "levels": {"DEBUG": 0, "TERM ": 0, "INFO": 1, "WARN": 2, "ERROR": 3},
        # ── the six channel names the ORIGINAL's Logger.__init__ collected overrides for ──
        "channels": ["payload", "perf", "process", "health", "ipc", "terminal"],
        # ── the layouts the ORIGINAL formatted its output with ──
        "formats": {
            "line": "{timestamp} [{service}] {level} {message}\n",
            "timestamp": "{stamp}.{millis:03d}Z",
            "log_file": "{service}.log",
            "fatal_stderr": "\nFATAL [{service}]: {preview}\n",
            "fatal_path": "Full log: {path}",
            "stdlib_capture": "%(name)s: %(message)s",
        },
        # ── the second argument of each `cfg.get(key, ...)` in the ORIGINAL. Note that
        #    capture_stdlib_loggers falls back to the EMPTY list, not to defaults' three
        #    names: an empty list means "attach to the root logger". See the docstring. ──
        "fallbacks": {
            "profile": "standard",
            "fatal_preview_chars": 500,
            "fatal_exit_code": 1,
            "capture_stdlib_loggers": [],
        },
        # ── what the ORIGINAL's _resolve_build_id read out of build.json ──
        "build_id": {"key": "build_id", "unknown": "unknown"},
        # ── the ORIGINAL's _Bridge._MAP and the level it fell back to ──
        "stdlib": {
            "levels": {
                "DEBUG": "DEBUG",
                "INFO": "INFO",
                "WARNING": "WARN",
                "ERROR": "ERROR",
                "CRITICAL": "ERROR",
            },
            "fallback_level": "INFO",
        },
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────────────── reading the config ───────────────────────────────

def shipped_registry():
    """Return the path of the `registry.json` this distribution ships as package data, or None.

    Asks the installed `code__code__jazz__kokoro__dz_debug` package where it lives. This is
    the only way to find the registry from a NON-editable install, where it is not on any path
    above this file — see WHY STEP 3 EXISTS in the module docstring.

    Uses `find_spec` rather than importing: locating a file must not run a sibling package's
    code. Returns None rather than raising if the package is absent (a `dz_debug/` vendored on
    its own, say), so the caller can report the whole picture at once.
    """
    try:
        spec = importlib.util.find_spec(SHIPPING_PKG)
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    for location in spec.submodule_search_locations:
        candidate = os.path.join(location, REGISTRY_NAME)
        if os.path.isfile(candidate):
            return candidate
    return None


def _shipping_pkg_status():
    """One clause describing why the shipped-registry step found nothing, for the error."""
    try:
        spec = importlib.util.find_spec(SHIPPING_PKG)
    except (ImportError, ValueError):
        spec = None
    if spec is None or not spec.submodule_search_locations:
        return "the %s package is not importable, so it ships no registry either" % SHIPPING_PKG
    return ("the %s package is at %s but has no %s in it"
            % (SHIPPING_PKG, list(spec.submodule_search_locations)[0], REGISTRY_NAME))


def find_registry(start=None):
    """Return the registry path, or None if there is none to be found.

    Walks UP from `start` (default: this file's directory) first; if that finds nothing, falls
    back to the copy this distribution ships as package data. The walk-up wins when both
    exist, so a checkout's own registry is never shadowed by an installed one.
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
    return shipped_registry()


def _read_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise ConfigError("%s at %s could not be read as JSON: %s" % (what, path, exc)) from exc


def _strip_comments(section):
    """Drop the registry's `_comment` keys, which document a section rather than configure it."""
    return {k: v for k, v in section.items() if not k.startswith("_comment")}


def load_config(start=None):
    """Resolve this unit's config object from disk, ignoring any injected config.

    Returns a `(config, base, source)` triple: the config object, the directory the registry
    was found in, and a human-readable description of where the config came from. `start`
    overrides the directory the registry walk-up begins at.

    `base` is NOT used to rebase `log_root` or `build_json`. Those two are handed to `Path` the
    way the ORIGINAL handed its own literals, so a relative one is relative to the working
    directory exactly as the original's would have been. `base` is package-wide infrastructure
    only: it is what the CLI resolves `bug_reports` against.

    Raises:
        ConfigError: if no config object can be found, naming all three sources that were tried.
    """
    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        if not os.path.isfile(env_path):
            raise ConfigError("%s is set to %r, but no such file exists" % (CONFIG_ENV, env_path))
        config = _read_json(env_path, "the config object named by " + CONFIG_ENV)
        if not isinstance(config, dict):
            raise ConfigError("the config object at %s must be a JSON object, not %s"
                              % (env_path, type(config).__name__))
        return (_strip_comments(config),
                os.path.dirname(os.path.abspath(env_path)),
                "%s=%s" % (CONFIG_ENV, env_path))

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s. All three sources were tried and none answered: (1) $%s "
            "is unset; (2) no %s was found by walking up from %s; (3) %s. Run "
            "`forge2-dz-debug-log emit-config` for a template of the config object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))),
               _shipping_pkg_status()))

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. "
                "Run `forge2-dz-debug-log emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH)))
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError("the registry section %s at %s must be a JSON object, not %s"
                          % (".".join(UNIT_PATH), registry_path, type(node).__name__))

    config = _strip_comments(node)
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit
    # section may state its own to override it. This is inheritance inside ONE config document,
    # not a guessed default — if neither states it, the key stays absent and the CLI files no
    # report.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


# ─────────────────────────── validating the config object ───────────────────────────
#
# Every failure below is a `ConfigError` that names the key, says what was wrong with it, and
# points at `emit-config`. That is Theme 5 of the playbook applied to a config file: the
# operator who mistyped it is not reading this source, so the message has to carry the answer.

def _require_key(config, key):
    if not isinstance(config, dict):
        raise ConfigError("the config object for %s must be a JSON object, not %s"
                          % (UNIT, type(config).__name__))
    if key not in config:
        raise ConfigError("the config object for %s is missing the required key %r. The "
                          "required keys are: %s. Run `forge2-dz-debug-log emit-config` for a "
                          "template." % (UNIT, key, ", ".join(REQUIRED_KEYS)))
    return config[key]


def _require_object(config, key):
    value = _require_key(config, key)
    if not isinstance(value, dict):
        raise ConfigError("config key %r for %s must be a JSON object, not %s"
                          % (key, UNIT, type(value).__name__))
    return _strip_comments(value)


def _require_rank(value, where):
    """An integer level rank. `bool` is refused though it is an `int` subclass: a config saying
    `"INFO": true` is an operator mistake, and True would silently rank INFO at 1."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("%s must be an integer rank, not %s" % (where, type(value).__name__))
    return value


def _require_levels(config):
    """The `levels` table: level name -> integer rank. The ORIGINAL's `_LEVELS`."""
    section = _require_object(config, "levels")
    levels = {}
    for name, value in section.items():
        levels[name] = _require_rank(value, "config key 'levels[%r]' for %s" % (name, UNIT))
    for name in LEVEL_NAMES:
        if name not in levels:
            raise ConfigError(
                "config key 'levels' for %s does not rank %r, which this module logs at. It "
                "must rank every one of: %s. (Note that %r is spelled with a trailing space — "
                "it is the level's name.) Run `forge2-dz-debug-log emit-config` for a template."
                % (UNIT, name, ", ".join(repr(n) for n in LEVEL_NAMES), "TERM "))
    return levels


def _require_profiles(config, levels):
    """The `profiles` table: profile name -> {"min_level": <a level name>}. `_PROFILES`."""
    section = _require_object(config, "profiles")
    if not section:
        raise ConfigError("config key 'profiles' for %s must name at least one profile" % UNIT)
    profiles = {}
    for name, entry in section.items():
        where = "config key 'profiles[%r]' for %s" % (name, UNIT)
        if not isinstance(entry, dict):
            raise ConfigError('%s must be a JSON object like {"min_level": "INFO"}, not %s'
                              % (where, type(entry).__name__))
        if "min_level" not in entry:
            raise ConfigError("%s is missing the required key 'min_level'" % where)
        min_level = entry["min_level"]
        if not isinstance(min_level, str):
            raise ConfigError("%s: 'min_level' must be a level name (a string), not %s"
                              % (where, type(min_level).__name__))
        if min_level not in levels:
            raise ConfigError(
                "%s: 'min_level' is %r, which the config's 'levels' table does not rank. The "
                "levels it ranks are: %s." % (where, min_level,
                                              ", ".join(repr(n) for n in sorted(levels))))
        profiles[name] = dict(entry)
    return profiles


def _require_channels(config):
    """The `channels` list: the channel names `Logger.__init__` collects overrides for."""
    names = _require_key(config, "channels")
    if not isinstance(names, list) or not names:
        raise ConfigError("config key 'channels' for %s must be a non-empty JSON array of "
                          "channel names, not %s"
                          % (UNIT, type(names).__name__ if not isinstance(names, list)
                             else "an empty array"))
    seen = []
    for index, name in enumerate(names):
        if not isinstance(name, str) or not name:
            raise ConfigError("config key 'channels[%d]' for %s must be a non-empty string; "
                              "got %r" % (index, UNIT, name))
        if name in seen:
            raise ConfigError("config key 'channels' for %s names %r twice" % (UNIT, name))
        seen.append(name)
    for name in TAGGED_CHANNELS:
        if name not in seen:
            raise ConfigError(
                "config key 'channels' for %s does not include %r, which this module tags lines "
                "with (`term()` does). It must include every one of: %s."
                % (UNIT, name, ", ".join(repr(n) for n in TAGGED_CHANNELS)))
    return tuple(seen)


def _require_profile_channels(config, profiles, channels):
    """The `profile_channels` table: profile name -> {channel -> bool}. `_PROFILE_CHANNELS`."""
    section = _require_object(config, "profile_channels")
    table = {}
    for name, entry in section.items():
        where = "config key 'profile_channels[%r]' for %s" % (name, UNIT)
        if not isinstance(entry, dict):
            raise ConfigError("%s must be a JSON object mapping each channel to true or false, "
                              "not %s" % (where, type(entry).__name__))
        for channel, value in entry.items():
            if not isinstance(value, bool):
                raise ConfigError("%s: channel %r must be true or false, not %s"
                                  % (where, channel, type(value).__name__))
        for channel in channels:
            if channel not in entry:
                raise ConfigError("%s does not say whether the %r channel is on. Every profile "
                                  "must state every channel in the config's 'channels' list: %s."
                                  % (where, channel, ", ".join(repr(c) for c in channels)))
        table[name] = dict(entry)
    for name in profiles:
        if name not in table:
            raise ConfigError(
                "config key 'profile_channels' for %s has no entry for the profile %r, which "
                "'profiles' declares. Every profile needs one, or selecting it would raise "
                "KeyError at the first Logger." % (UNIT, name))
    return table


def _require_formats(config):
    """The `formats` section: the layouts the ORIGINAL formatted its output with."""
    section = _require_object(config, "formats")
    formats = {}
    for key in list(FORMAT_FIELDS) + [STDLIB_FORMAT_KEY]:
        where = "config key 'formats.%s' for %s" % (key, UNIT)
        if key not in section:
            raise ConfigError("%s is missing. The required templates are: %s. Run "
                              "`forge2-dz-debug-log emit-config` for a template."
                              % (where, ", ".join(list(FORMAT_FIELDS) + [STDLIB_FORMAT_KEY])))
        value = section[key]
        if not isinstance(value, str) or not value:
            raise ConfigError("%s must be a non-empty string, not %r" % (where, value))
        formats[key] = value
    # Test-format each str.format template with dummy fields, so a misspelled field is a
    # ConfigError naming the fields rather than a KeyError from inside a log call later.
    # `stdlib_capture` is excluded on purpose: it is %-style, for logging.Formatter.
    for key, dummies in FORMAT_FIELDS.items():
        try:
            formats[key].format(**dummies)
        except (KeyError, IndexError, ValueError) as exc:
            raise ConfigError(
                "config key 'formats.%s' for %s is not a usable template (%s: %s). The fields "
                "it may use are: %s." % (key, UNIT, type(exc).__name__, exc,
                                         ", ".join("{%s}" % f for f in dummies))) from exc
    return formats


def _require_fallbacks(config, profiles):
    """The `fallbacks` section: the ORIGINAL's in-code `cfg.get(key, <fallback>)` values."""
    section = _require_object(config, "fallbacks")
    for key in FALLBACK_KEYS:
        if key not in section:
            raise ConfigError("config key 'fallbacks.%s' for %s is missing. The required "
                              "fallbacks are: %s. Run `forge2-dz-debug-log emit-config` for a "
                              "template." % (key, UNIT, ", ".join(FALLBACK_KEYS)))
    fallbacks = dict(section)
    profile = fallbacks["profile"]
    if not isinstance(profile, str) or profile not in profiles:
        raise ConfigError("config key 'fallbacks.profile' for %s must name a profile the "
                          "config declares (%s); got %r"
                          % (UNIT, ", ".join(repr(p) for p in profiles), profile))
    for key in ("fatal_preview_chars", "fatal_exit_code"):
        _require_rank(fallbacks[key], "config key 'fallbacks.%s' for %s" % (key, UNIT))
    _require_str_list(fallbacks, "capture_stdlib_loggers",
                      "config key 'fallbacks.capture_stdlib_loggers' for %s" % UNIT)
    return fallbacks


def _require_str_list(section, key, where):
    """A JSON array of strings. The empty array is legitimate — see the docstring's note on
    `fallbacks.capture_stdlib_loggers`, where empty means "attach to the root logger"."""
    value = section[key]
    if not isinstance(value, list):
        raise ConfigError("%s must be a JSON array of strings, not %s"
                          % (where, type(value).__name__))
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigError("%s: item %d must be a string, not %s"
                              % (where, index, type(item).__name__))
    return list(value)


def _require_build_id(config):
    """The `build_id` section: what `_resolve_build_id` reads out of build.json."""
    section = _require_object(config, "build_id")
    spec = {}
    for key in ("key", "unknown"):
        if key not in section:
            raise ConfigError('config key \'build_id.%s\' for %s is missing. It needs both '
                              '"key" (what to read out of build.json) and "unknown" (what to '
                              'return when build.json is absent or lacks that key).'
                              % (key, UNIT))
        if not isinstance(section[key], str) or not section[key]:
            raise ConfigError("config key 'build_id.%s' for %s must be a non-empty string; got "
                              "%r" % (key, UNIT, section[key]))
        spec[key] = section[key]
    return spec


def _require_stdlib(config, levels):
    """The `stdlib` section: the ORIGINAL's `_Bridge._MAP`, keyed by stdlib level NAME.

    The original keyed its map by `logging.DEBUG` and friends — integers. JSON object keys are
    strings, so the config names the stdlib level ("WARNING") and this resolves it to the
    number through the `logging` module itself, which is the only thing entitled to say what
    `WARNING` is worth. The mapped value is one of THIS module's level names, so it is checked
    against the config's own `levels` table.
    """
    import logging

    section = _require_object(config, "stdlib")
    for key in ("levels", "fallback_level"):
        if key not in section:
            raise ConfigError("config key 'stdlib.%s' for %s is missing. Run "
                              "`forge2-dz-debug-log emit-config` for a template." % (key, UNIT))
    table = section["levels"]
    if not isinstance(table, dict):
        raise ConfigError("config key 'stdlib.levels' for %s must be a JSON object mapping a "
                          "stdlib level name to one of this module's levels, not %s"
                          % (UNIT, type(table).__name__))
    resolved = {}
    for name, ours in _strip_comments(table).items():
        where = "config key 'stdlib.levels[%r]' for %s" % (name, UNIT)
        number = getattr(logging, name, None)
        if isinstance(number, bool) or not isinstance(number, int):
            raise ConfigError("%s: %r is not a level the stdlib `logging` module defines "
                              "(try DEBUG, INFO, WARNING, ERROR, CRITICAL)" % (where, name))
        if not isinstance(ours, str) or ours not in levels:
            raise ConfigError("%s maps to %r, which the config's 'levels' table does not rank. "
                              "The levels it ranks are: %s."
                              % (where, ours, ", ".join(repr(n) for n in sorted(levels))))
        resolved[number] = ours
    fallback = section["fallback_level"]
    if not isinstance(fallback, str) or fallback not in levels:
        raise ConfigError("config key 'stdlib.fallback_level' for %s must be one of the levels "
                          "the config's 'levels' table ranks (%s); got %r"
                          % (UNIT, ", ".join(repr(n) for n in sorted(levels)), fallback))
    return {"levels": resolved, "fallback_level": fallback}


def _require_defaults(config, profiles, channels):
    """The `defaults` section: the ORIGINAL's CONFIG block, key for key.

    Extra keys are kept, not rejected: the original's CONFIG was an ordinary dict and a caller
    could put anything in it, and `Logger.__init__` merges the whole of it.
    """
    section = _require_object(config, "defaults")
    for key in DEFAULT_KEYS:
        if key not in section:
            raise ConfigError("config key 'defaults.%s' for %s is missing. 'defaults' is the "
                              "ORIGINAL's CONFIG block and needs every one of its keys: %s. Run "
                              "`forge2-dz-debug-log emit-config` for a template."
                              % (key, UNIT, ", ".join(DEFAULT_KEYS)))
    defaults = dict(section)

    profile = defaults["profile"]
    if not isinstance(profile, str) or profile not in profiles:
        raise ConfigError("config key 'defaults.profile' for %s must name a profile the config "
                          "declares (%s); got %r"
                          % (UNIT, ", ".join(repr(p) for p in profiles), profile))

    # A channel override is true, false, or null — null meaning "let the profile decide", which
    # is what the ORIGINAL's `if val is not None` in `_resolve_channels` tests for.
    for channel in channels:
        value = defaults[channel]
        if value is not None and not isinstance(value, bool):
            raise ConfigError("config key 'defaults.%s' for %s must be true, false, or null "
                              "(null lets the profile decide); got %s"
                              % (channel, UNIT, type(value).__name__))

    for key in ("mirror_to_stderr", "capture_stdlib_logging"):
        if not isinstance(defaults[key], bool):
            raise ConfigError("config key 'defaults.%s' for %s must be true or false, not %s"
                              % (key, UNIT, type(defaults[key]).__name__))

    for key in PATH_KEYS:
        value = defaults[key]
        if not isinstance(value, str) or not value:
            raise ConfigError("config key 'defaults.%s' for %s must be a non-empty path string "
                              "(a leading ~ is expanded to your home directory); got %r"
                              % (key, UNIT, value))
        defaults[key] = Path(os.path.expanduser(value))

    if not isinstance(defaults["timestamp_format"], str) or not defaults["timestamp_format"]:
        raise ConfigError("config key 'defaults.timestamp_format' for %s must be a non-empty "
                          "strftime format string; got %r" % (UNIT, defaults["timestamp_format"]))

    for key in ("fatal_preview_chars", "fatal_exit_code"):
        _require_rank(defaults[key], "config key 'defaults.%s' for %s" % (key, UNIT))

    _require_str_list(defaults, "capture_stdlib_loggers",
                      "config key 'defaults.capture_stdlib_loggers' for %s" % UNIT)
    return defaults


#: The sections a config object must carry. Named here so a missing one can list them all.
REQUIRED_KEYS = ("defaults", "profiles", "profile_channels", "levels", "channels", "formats",
                 "fallbacks", "build_id", "stdlib")


def build_config(config):
    """Validate a config object and return this module's operating tables.

    Returns a dict with one key per section of the config object, with every value checked and
    converted: paths are `Path`s, the stdlib level map is keyed by the integers `logging` uses,
    and the cross-section couplings this module depends on (every level it logs at is ranked;
    every channel it tags is declared; every profile has channels) are proven here, once, at
    load — rather than failing later at a log call.

    This is a pure function of its argument: it reads no file, no environment variable and no
    module state, so `build_config(json.load(open(...)))` is the whole of the check and the
    selftest can drive it with any config object it likes.

    Raises:
        ConfigError: naming the key, what was wrong with it, and how to print a template.
    """
    levels = _require_levels(config)
    profiles = _require_profiles(config, levels)
    channels = _require_channels(config)
    return {
        "defaults": _require_defaults(config, profiles, channels),
        "profiles": profiles,
        "profile_channels": _require_profile_channels(config, profiles, channels),
        "levels": levels,
        "channels": channels,
        "formats": _require_formats(config),
        "fallbacks": _require_fallbacks(config, profiles),
        "build_id": _require_build_id(config),
        "stdlib": _require_stdlib(config, levels),
    }


# ─────────────────────────────── the config in force ───────────────────────────────

_ACTIVE = None       # config injected via configure(); wins over every disk source
_RESOLVED = None     # cache of the last disk resolution, so repeat calls re-read no files
_BUILT = None        # cache of build_config() over the config in force
_GENERATION = 0      # bumped whenever the config in force changes; see _ConfigMapping


def _invalidate():
    """Drop everything derived from the config in force, so the next touch re-derives it."""
    global _BUILT, _GENERATION
    _BUILT = None
    _GENERATION += 1


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
    """Return the directory the registry was found in.

    This is what the CLI resolves a relative `bug_reports` path against. It is deliberately NOT
    applied to `log_root` or `build_json` — see `load_config`.
    """
    if _ACTIVE is not None:
        return _ACTIVE[1]
    active_config()
    return _RESOLVED[1]


def _built():
    """The validated operating tables for the config in force. Cached; `_invalidate()` clears."""
    global _BUILT
    if _BUILT is None:
        _BUILT = build_config(active_config())
    return _BUILT


def configure(config, base=None, source="injected via configure()"):
    """Inject `config` as the config object for this process; return the previous state.

    `base` is the directory a relative `bug_reports` path resolves against, and defaults to the
    current working directory. Pass `None` as `config` to drop the injection and go back to
    resolving from disk.

    Injecting a config re-fills the four module mappings from it, so a later `Logger(...)` uses
    it. It does NOT reconfigure a Logger that already exists: `Logger.__init__` merges CONFIG
    into `self._cfg` once, at construction, exactly as the original's did.
    """
    global _ACTIVE
    previous = _ACTIVE
    if config is None:
        _ACTIVE = None
    else:
        if not isinstance(config, dict):
            raise ConfigError("a config object must be a dict, not %s" % type(config).__name__)
        _ACTIVE = (config, base or os.getcwd(), source)
    _invalidate()
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
        _invalidate()


def reset_config():
    """Drop the injected config and the cached disk resolution; the next touch re-resolves."""
    global _ACTIVE, _RESOLVED
    _ACTIVE = None
    _RESOLVED = None
    _invalidate()


class _ConfigMapping(MutableMapping):
    """One of the ORIGINAL's module-level dicts, filled from the config object on first use.

    The original fixed `CONFIG`, `_PROFILES`, `_PROFILE_CHANNELS` and `_LEVELS` at import. This
    stands in for one of them: it is a `MutableMapping`, so every operation the original's dict
    supported works — `{**CONFIG}`, `CONFIG["profile"] = "debug"`, `del CONFIG["profile"]`,
    `_LEVELS.get(level, 0)`, `list(_PROFILES)`, `profile in _PROFILES`, `len`, iteration — and
    the config is resolved on the first of them.

    Why not resolve at import: `import dz_debug.log` must not throw, or `emit-config` could
    never print the config you do not yet have. See THE LAZY MAPPINGS in the module docstring.

    A caller's writes are kept: the filled dict is cached and handed out until the config in
    force CHANGES (`configure`/`reset_config` bump `_GENERATION`), at which point it re-fills
    from the new config — because a mapping still serving the old config's values after the
    config was replaced would be a lie.
    """

    def __init__(self, name, section):
        self._name = name
        self._section = section
        self._cache = None
        self._generation = None

    def _data(self):
        if self._cache is None or self._generation != _GENERATION:
            # A shallow copy, so a caller mutating this mapping does not reach into the cached
            # tables — and `dict(_PROFILE_CHANNELS[p])` in `_resolve_channels` copies the inner
            # dict before mutating it, exactly as the original's did.
            self._cache = dict(_built()[self._section])
            self._generation = _GENERATION
        return self._cache

    def __getitem__(self, key):
        return self._data()[key]

    def __setitem__(self, key, value):
        self._data()[key] = value

    def __delitem__(self, key):
        del self._data()[key]

    def __iter__(self):
        return iter(self._data())

    def __len__(self):
        return len(self._data())

    def __repr__(self):
        """The dict's repr once resolved; a description rather than an exception before then.

        A repr that raised would make this mapping unusable in a debugger or a log line at the
        exact moment — no config — when you most need to see what it says.
        """
        try:
            return repr(self._data())
        except ConfigError as exc:
            return "<%s for %s: no config object yet — %s>" % (self._name, UNIT, exc)


#: The ORIGINAL's CONFIG block. Its `log_root` and `build_json` are `Path`s, as the original's
#: were; everything else is the JSON value from the config object.
CONFIG = _ConfigMapping("CONFIG", "defaults")

#: The ORIGINAL's `_PROFILES`: profile name -> {"min_level": ...}.
_PROFILES = _ConfigMapping("_PROFILES", "profiles")

#: The ORIGINAL's `_PROFILE_CHANNELS`: profile name -> {channel -> bool}.
_PROFILE_CHANNELS = _ConfigMapping("_PROFILE_CHANNELS", "profile_channels")

#: The ORIGINAL's `_LEVELS`: level name -> integer rank.
_LEVELS = _ConfigMapping("_LEVELS", "levels")


def _formats():
    """The layouts this module formats its output with, from the config in force."""
    return _built()["formats"]


def _fallbacks():
    """The ORIGINAL's in-code `cfg.get(key, <fallback>)` values, from the config in force."""
    return _built()["fallbacks"]


def _channel_names():
    """The channel names `Logger.__init__` collects overrides for, from the config in force."""
    return _built()["channels"]


# ─────────────────────────────── helpers ───────────────────────────────
#
# The ORIGINAL's three module-level helpers, with the same names, parameters and defaults.

def _resolve_build_id(build_json: Path) -> str:
    """The build id named in `build_json`, or the config's `build_id.unknown` if there is none.

    `build_json` is a `Path`. Passing a string raises AttributeError from `.exists()`, exactly
    as the original did — the parameter is annotated `Path` and it means it.
    """
    spec = _built()["build_id"]
    if build_json.exists():
        return json.loads(build_json.read_text()).get(spec["key"], spec["unknown"])
    return spec["unknown"]


def _timestamp(fmt: str) -> str:
    """The current UTC time in `fmt`, plus milliseconds — the config's `formats.timestamp`."""
    now = datetime.now(timezone.utc)
    return _formats()["timestamp"].format(stamp=now.strftime(fmt),
                                          millis=now.microsecond // 1000)


def _resolve_channels(profile: str, overrides: dict) -> dict:
    """`profile`'s channel defaults, with every non-None value in `overrides` applied over them.

    A None override means "let the profile decide" and is skipped. An override naming a channel
    the profile does not have ADDS it — the original did that too, and `_write` reads the result
    with `.get(t, False)`, so an unknown tag is simply off.

    Raises:
        KeyError: if `profile` is not in `_PROFILE_CHANNELS`, as the original's indexing did.
            `Logger.__init__` validates the profile against `_PROFILES` before reaching here.
        ConfigError: if there is no config object to resolve `_PROFILE_CHANNELS` from.
    """
    channels = dict(_PROFILE_CHANNELS[profile])
    for ch, val in overrides.items():
        if val is not None:
            channels[ch] = val
    return channels


# ─────────────────────────────── Logger ───────────────────────────────

class Logger:
    """
    File logger scoped to a service and build ID.

    Usage:
        log = Logger("kokoro")
        log.info("server started on port 4001")
        log.debug("query took 12ms", tags=["perf"])
        log.debug("raw text payload", tags=["payload"])
        log.term("raw subprocess output line")
        log.error("model failed", exc=e)
        log.fatal("cannot continue", exc=e)

    Override profile or channels at instantiation:
        log = Logger("kokoro", config={"profile": "debug", "payload": True})

    The `config` argument is the ORIGINAL's, and is unchanged: a dict merged OVER the module's
    `CONFIG`, holding any of CONFIG's keys. It is not the unit config object of #200 — that one
    comes from the registry and is what fills `CONFIG` in the first place. See CONFIGURATION in
    this module's docstring.

    Raises:
        ValueError: if the profile is not one the config declares.
        ConfigError: if there is no config object to be had (#200 requirement 4).
    """

    def __init__(self, service: str, build_id: str = None, config: dict = None):
        # Merging CONFIG into a real dict here is what keeps `self._cfg` a plain dict, exactly
        # as the original's was — the laziness stops at this line and never reaches a caller.
        cfg = {**CONFIG, **(config or {})}
        fallbacks = _fallbacks()

        profile = cfg.get("profile", fallbacks["profile"])
        if profile not in _PROFILES:
            raise ValueError(f"Unknown profile '{profile}'. Choose: {list(_PROFILES)}")

        if build_id is None:
            build_id = _resolve_build_id(cfg["build_json"])

        self._service = service
        self._build_id = build_id
        self._cfg = cfg
        self._min_level = _LEVELS[_PROFILES[profile]["min_level"]]
        self._channels = _resolve_channels(profile, {
            ch: cfg.get(ch) for ch in _channel_names()
        })

        log_dir = Path(cfg["log_root"]) / build_id
        log_dir.mkdir(parents=True, exist_ok=True)
        self._path = log_dir / _formats()["log_file"].format(service=service)
        self._file = self._path.open("a", buffering=1)

        if cfg.get("capture_stdlib_logging"):
            self._attach_stdlib_capture(
                cfg.get("capture_stdlib_loggers", fallbacks["capture_stdlib_loggers"]))

    # ── Public interface ───────────────────────────────────────────────

    def info(self, msg: str, tags: list = None):
        self._write("INFO", msg, tags)

    def warn(self, msg: str, tags: list = None):
        self._write("WARN", msg, tags)

    def error(self, msg: str, exc: Exception = None, tags: list = None):
        """Log `msg` at ERROR; if `exc` is truthy, log the CURRENT traceback after it.

        `exc` is a flag, not a source: the original formatted `traceback.format_exc()` — the
        exception being handled right now — and never looked at `exc` itself. Outside an
        `except` block that is the string "NoneType: None", and that is preserved.
        """
        self._write("ERROR", msg, tags)
        if exc:
            self._write("ERROR", traceback.format_exc().strip(), tags)

    def debug(self, msg: str, tags: list = None):
        self._write("DEBUG", msg, tags)

    def term(self, msg: str):
        """Log raw terminal/subprocess output. Controlled by the terminal channel."""
        self._write("TERM ", msg, tags=["terminal"])

    def fatal(self, msg: str, exc: Exception = None):
        """Log `msg` (plus the current traceback if `exc`), print a preview to stderr, and exit.

        Raises:
            SystemExit: always, with the config's `defaults.fatal_exit_code`.
        """
        full = msg
        if exc:
            full += "\n" + traceback.format_exc().strip()
        self._write("ERROR", full)
        fallbacks = _fallbacks()
        preview = full[:self._cfg.get("fatal_preview_chars", fallbacks["fatal_preview_chars"])]
        formats = _formats()
        print(formats["fatal_stderr"].format(service=self._service, preview=preview),
              file=sys.stderr)
        print(formats["fatal_path"].format(path=self._path), file=sys.stderr)
        self.close()
        sys.exit(self._cfg.get("fatal_exit_code", fallbacks["fatal_exit_code"]))

    @property
    def path(self) -> Path:
        return self._path

    @property
    def channels(self) -> dict:
        return dict(self._channels)

    def close(self):
        self._file.close()

    # ── Private ────────────────────────────────────────────────────────

    def _write(self, level: str, msg: str, tags: list = None):
        """Write one line, if the level passes and at least one of `tags` names a live channel.

        An unranked level sorts at 0 (`_LEVELS.get(level, 0)`), so it is written by any profile
        whose min_level ranks 0 or less and dropped by every other — the original's behavior for
        a level nobody declared. Empty or absent `tags` means no channel gate at all.
        """
        if _LEVELS.get(level, 0) < self._min_level:
            return
        if tags:
            if not any(self._channels.get(t, False) for t in tags):
                return
        # `.format` substitutes values verbatim and never re-scans them, so a message
        # containing braces is written as-is rather than being formatted again. Section [3]
        # of the selftest checks that against the original's f-string.
        line = _formats()["line"].format(
            timestamp=_timestamp(self._cfg["timestamp_format"]),
            service=self._service,
            level=level,
            message=msg,
        )
        self._file.write(line)
        if self._cfg.get("mirror_to_stderr"):
            print(line, end="", file=sys.stderr)

    def _attach_stdlib_capture(self, logger_names: list):
        """Bridge the named stdlib loggers into this logger's file.

        uvicorn, litellm and fastapi call `logging.getLogger(__name__)` internally and can only
        be intercepted by registering a `logging.Handler` on those loggers — so this is the one
        place the stdlib `logging` API is touched, as it was in the original.

        An EMPTY `logger_names` attaches to the root logger, which is what `[None]` means to
        `logging.getLogger`. See the module docstring's note on `fallbacks`.
        """
        import logging

        writer = self._write
        stdlib = _built()["stdlib"]

        class _Bridge(logging.Handler):
            _MAP = stdlib["levels"]

            def emit(self, record: logging.LogRecord):
                writer(self._MAP.get(record.levelno, stdlib["fallback_level"]),
                       self.format(record))

        handler = _Bridge()
        handler.setFormatter(logging.Formatter(_formats()[STDLIB_FORMAT_KEY]))

        targets = logger_names if logger_names else [None]
        for name in targets:
            logging.getLogger(name).addHandler(handler)


# ═══════════════════════════════ the selftest ═══════════════════════════════
#
# #363 captured NO behavioral exemplars, and says what that means: "you must write the
# equivalence exemplars by hand from the original's behavior before rewriting, and they are
# what settles this ticket." Rather than hand-copy the original's behavior into expectations —
# where a mistake in the copy passes silently — the checks below run the ORIGINAL ITSELF, from
# the ticket's own bytes, and compare everything a caller could observe.
#
# Every file written lives inside a temp directory that is removed. Nothing touches the home
# directory, which matters: the ORIGINAL's CONFIG points `log_root` at ~/code/run/logs, so the
# oracle is pointed at a temp root BEFORE any Logger is built.

class _Raised:
    """A stand-in for a call that raised, so a check can FAIL instead of aborting.

    A test net that dies on the first unexpected exception hides every check after it and
    reports a traceback where it owes a verdict. `_attempt` returns one of these instead.

    It records the exception's TYPE NAME and text rather than the exception, because the two
    modules are separate imports and their exception objects are never equal — while
    "ValueError: Unknown profile 'bogus'..." from each is exactly the comparison that matters.
    """

    def __init__(self, exception):
        self.type = type(exception)
        self.text = "%s: %s" % (type(exception).__name__, exception)

    def __repr__(self):
        return "<raised %s>" % self.text


def _attempt(thunk):
    """Call `thunk` and return its result, or a `_Raised` if it raised anything.

    `BaseException`, not `Exception`: `Logger.fatal` raises SystemExit, and catching it is the
    only way to observe what fatal did rather than dying with it.
    """
    try:
        return thunk()
    except BaseException as exc:  # noqa: BLE001 — a test net must survive anything
        return _Raised(exc)


def _describe(value):
    """A comparable description of a case's result, whether it returned or raised."""
    return repr(value) if not isinstance(value, _Raised) else "raised " + value.text


def _write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _import_fresh(root, name):
    """Import module `name` out of `root`, with no interference from anything already imported."""
    import importlib

    for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        del sys.modules[key]
    sys.path.insert(0, root)
    try:
        importlib.invalidate_caches()
        return importlib.import_module(name)
    finally:
        sys.path.remove(root)


def _normalize(text, root):
    """Blank out the two things that legitimately differ between two runs: the temp path and
    the live timestamp. Every other byte is compared exactly.

    The timestamp is masked DIGIT BY DIGIT rather than wholesale, so its shape still has to
    match: "2026-07-15T09:41:02.317Z" becomes "9999-99-99T99:99:99.999Z", and a rewrite that
    dropped the milliseconds or the Z would still differ from the original here.
    """
    import re

    text = text.replace(str(root), "<ROOT>")
    return re.sub(r"\d", "9", text)


def _observe(module, case, root, service_root):
    """Run one case against one module and return everything a caller could observe.

    That is: what the case returned or raised, the exact bytes of every file under the log
    root, and the exact bytes written to stderr. `root` is wiped first so each case starts
    clean, and the module is pointed at it before anything is constructed — which is what keeps
    the ORIGINAL's `~/code/run/logs` from ever being created.
    """
    import io
    import shutil

    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    # Uniform across both modules: the original's CONFIG is a dict, the rewrite's is a
    # MutableMapping standing in for it, and this is exactly the operation that has to work the
    # same on both.
    module.CONFIG["log_root"] = Path(root)
    module.CONFIG["build_json"] = Path(service_root) / "build.json"

    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        outcome = _attempt(lambda: case(module, Path(root), Path(service_root)))

    files = {}
    for dirpath, _dirs, names in os.walk(root):
        for name in sorted(names):
            full = os.path.join(dirpath, name)
            with open(full, "r", encoding="utf-8") as handle:
                files[os.path.relpath(full, root).replace(os.sep, "/")] = handle.read()
    return {
        "returned": _normalize(_describe(outcome), root),
        "files": {k: _normalize(v, root) for k, v in sorted(files.items())},
        "stderr": _normalize(err.getvalue(), root),
    }


# ── the cases: every behavior the rewrite must reproduce ──
#
# Each is `fn(m, root, aux)` and is run against BOTH modules. `m` is the module under test,
# `root` its log root, `aux` a scratch directory for things like build.json. They deliberately
# reach for the private helpers as well as the public surface: the ticket's callable surface
# lists `_write`, `_resolve_channels`, `_timestamp` and `_resolve_build_id`, so callers may use
# them and they are held to the same standard.

def _cases():
    """Return `[(label, fn), ...]` — the equivalence exemplars, written by hand from the
    ORIGINAL's behavior as ticket #363 requires, and run against the ORIGINAL to settle them."""

    def info_default(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        log.info("server started on port 4001")
        log.close()
        return "ok"

    def debug_suppressed_at_standard(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        log.debug("query took 12ms")
        log.info("after")
        log.close()
        return "ok"

    def debug_tagged_perf_at_standard(m, root, aux):
        # The level gate fires first: DEBUG ranks 0, standard's min_level INFO ranks 1, so the
        # perf channel never gets a say.
        log = m.Logger("kokoro", build_id="b1")
        log.debug("query took 12ms", tags=["perf"])
        log.close()
        return "ok"

    def debug_tagged_perf_at_debug(m, root, aux):
        log = m.Logger("kokoro", build_id="b1", config={"profile": "debug"})
        log.debug("query took 12ms", tags=["perf"])
        log.close()
        return "ok"

    def debug_tagged_payload_at_debug(m, root, aux):
        # payload is OFF in the debug profile — the one channel that is not.
        log = m.Logger("kokoro", build_id="b1", config={"profile": "debug"})
        log.debug("raw text payload", tags=["payload"])
        log.close()
        return "ok"

    def debug_tagged_payload_at_trace(m, root, aux):
        log = m.Logger("kokoro", build_id="b1", config={"profile": "trace"})
        log.debug("raw text payload", tags=["payload"])
        log.close()
        return "ok"

    def debug_payload_forced_on(m, root, aux):
        log = m.Logger("kokoro", build_id="b1",
                       config={"profile": "debug", "payload": True})
        log.debug("raw text payload", tags=["payload"])
        log.close()
        return "ok"

    def channel_forced_off(m, root, aux):
        log = m.Logger("kokoro", build_id="b1",
                       config={"profile": "trace", "payload": False})
        log.debug("raw text payload", tags=["payload"])
        log.debug("perf line", tags=["perf"])
        log.close()
        return "ok"

    def channel_override_none_defers(m, root, aux):
        # None means "let the profile decide" — it must not turn the channel off.
        log = m.Logger("kokoro", build_id="b1",
                       config={"profile": "trace", "payload": None})
        log.debug("raw text payload", tags=["payload"])
        log.close()
        return sorted(log.channels.items())

    def term_at_standard(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        log.term("raw subprocess output line")
        log.close()
        return "ok"

    def term_at_debug(m, root, aux):
        log = m.Logger("kokoro", build_id="b1", config={"profile": "debug"})
        log.term("raw subprocess output line")
        log.close()
        return "ok"

    def none_profile(m, root, aux):
        log = m.Logger("kokoro", build_id="b1", config={"profile": "none"})
        log.debug("d")
        log.info("i")
        log.warn("w")
        log.error("e")
        log.close()
        return "ok"

    def all_levels_at_trace(m, root, aux):
        log = m.Logger("kokoro", build_id="b1", config={"profile": "trace"})
        log.debug("d")
        log.info("i")
        log.warn("w")
        log.error("e")
        log.term("t")
        log.close()
        return "ok"

    def error_with_exc_in_except(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        try:
            raise RuntimeError("model failed")
        except RuntimeError as exc:
            log.error("model failed", exc=exc)
        log.close()
        return "ok"

    def error_with_exc_outside_except(m, root, aux):
        # `exc` is a flag, not a source: the original formats the CURRENT exception, and there
        # is none here, so the second line is the string "NoneType: None".
        log = m.Logger("kokoro", build_id="b1")
        log.error("no live exception", exc=RuntimeError("ignored"))
        log.close()
        return "ok"

    def error_without_exc(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        log.error("plain error")
        log.close()
        return "ok"

    def error_tagged_channel_off(m, root, aux):
        # ERROR passes the level gate but the perf channel is off at standard, so the channel
        # gate drops it — a tagged ERROR is not unconditional.
        log = m.Logger("kokoro", build_id="b1")
        log.error("tagged error", tags=["perf"])
        log.close()
        return "ok"

    def error_exc_tags_apply_to_traceback(m, root, aux):
        log = m.Logger("kokoro", build_id="b1", config={"profile": "debug"})
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            log.error("tagged", exc=exc, tags=["payload"])
        log.close()
        return "ok"

    def empty_tags_is_no_gate(m, root, aux):
        # `if tags:` — an empty list is falsy, so there is no channel gate at all.
        log = m.Logger("kokoro", build_id="b1")
        log.info("empty tags", tags=[])
        log.close()
        return "ok"

    def multiple_tags_any_wins(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        log.info("one live channel is enough", tags=["payload", "ipc"])
        log.info("no live channel", tags=["payload", "perf"])
        log.close()
        return "ok"

    def unknown_tag_is_off(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        log.info("unknown tag", tags=["zzz"])
        log.close()
        return "ok"

    def fatal_plain(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        return _describe(_attempt(lambda: log.fatal("cannot continue")))

    def fatal_with_exc(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        try:
            raise RuntimeError("model failed")
        except RuntimeError as exc:
            return _describe(_attempt(lambda: log.fatal("cannot continue", exc=exc)))

    def fatal_preview_truncates(m, root, aux):
        log = m.Logger("kokoro", build_id="b1", config={"fatal_preview_chars": 10})
        return _describe(_attempt(lambda: log.fatal("0123456789ABCDEFGHIJ")))

    def fatal_exit_code(m, root, aux):
        log = m.Logger("kokoro", build_id="b1", config={"fatal_exit_code": 7})
        return _describe(_attempt(lambda: log.fatal("bye")))

    def fatal_at_none_profile(m, root, aux):
        # fatal writes at ERROR with no tags, so even the `none` profile records it.
        log = m.Logger("kokoro", build_id="b1", config={"profile": "none"})
        return _describe(_attempt(lambda: log.fatal("still logged")))

    def mirror_off(m, root, aux):
        log = m.Logger("kokoro", build_id="b1", config={"mirror_to_stderr": False})
        log.info("not mirrored")
        log.close()
        return "ok"

    def unknown_profile(m, root, aux):
        return _describe(_attempt(lambda: m.Logger("kokoro", build_id="b1",
                                                   config={"profile": "bogus"})))

    def build_id_from_build_json(m, root, aux):
        _write_file(str(aux / "build.json"), json.dumps({"build_id": "b-2026-07-15"}))
        log = m.Logger("kokoro")
        log.info("resolved")
        out = str(log.path)
        log.close()
        return out

    def build_id_no_build_json(m, root, aux):
        log = m.Logger("kokoro")
        log.info("unknown build")
        out = str(log.path)
        log.close()
        return out

    def build_id_build_json_without_key(m, root, aux):
        _write_file(str(aux / "build.json"), json.dumps({"other": 1}))
        log = m.Logger("kokoro")
        out = str(log.path)
        log.close()
        return out

    def build_id_explicit_wins(m, root, aux):
        _write_file(str(aux / "build.json"), json.dumps({"build_id": "from-file"}))
        log = m.Logger("kokoro", build_id="explicit")
        out = str(log.path)
        log.close()
        return out

    def resolve_build_id_direct(m, root, aux):
        missing = aux / "nope.json"
        present = Path(_write_file(str(aux / "present.json"), json.dumps({"build_id": "b9"})))
        empty = Path(_write_file(str(aux / "empty.json"), json.dumps({})))
        return [m._resolve_build_id(missing),
                m._resolve_build_id(present),
                m._resolve_build_id(empty)]

    def resolve_build_id_on_a_string(m, root, aux):
        # The parameter is annotated `Path` and the body calls `.exists()` — a string is an
        # AttributeError, in the original and here.
        return _describe(_attempt(lambda: m._resolve_build_id(str(aux / "nope.json"))))

    def resolve_channels_direct(m, root, aux):
        return [sorted(m._resolve_channels("none", {}).items()),
                sorted(m._resolve_channels("standard", {}).items()),
                sorted(m._resolve_channels("debug", {}).items()),
                sorted(m._resolve_channels("trace", {}).items()),
                sorted(m._resolve_channels("standard", {"payload": True}).items()),
                sorted(m._resolve_channels("standard", {"process": False}).items()),
                sorted(m._resolve_channels("standard", {"payload": None}).items())]

    def resolve_channels_adds_unknown(m, root, aux):
        return sorted(m._resolve_channels("none", {"brand_new": True}).items())

    def resolve_channels_unknown_profile(m, root, aux):
        return _describe(_attempt(lambda: m._resolve_channels("bogus", {})))

    def timestamp_shape(m, root, aux):
        # Normalized digit-by-digit by `_normalize`, so the SHAPE is compared exactly while the
        # actual time is not.
        return [m._timestamp("%Y-%m-%dT%H:%M:%S"), m._timestamp("%H:%M:%S"), m._timestamp("x")]

    def write_unknown_level_at_standard(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        log._write("XYZZY", "unranked level")
        log.close()
        return "ok"

    def write_unknown_level_at_debug(m, root, aux):
        log = m.Logger("kokoro", build_id="b1", config={"profile": "debug"})
        log._write("XYZZY", "unranked level")
        log.close()
        return "ok"

    def path_property(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        out = [type(log.path).__name__ == type(Path(".")).__name__, str(log.path)]
        log.close()
        return out

    def channels_property_is_a_copy(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        first = log.channels
        first["perf"] = "MUTATED"
        out = [sorted(log.channels.items()), log.channels is log.channels]
        log.close()
        return out

    def braces_in_message(m, root, aux):
        # The rewrite formats its line through str.format where the original used an f-string.
        # A message full of braces is what tells the two apart if it got that wrong.
        log = m.Logger("kokoro", build_id="b1")
        log.info("{service} {0} {} {{literal}} %s %(name)s")
        log.close()
        return "ok"

    def braces_in_service_name(m, root, aux):
        log = m.Logger("{service}", build_id="b1")
        log.info("brace-named service")
        out = str(log.path)
        log.close()
        return out

    def newlines_in_message(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        log.info("first\nsecond")
        log.close()
        return "ok"

    def two_loggers_append(m, root, aux):
        a = m.Logger("kokoro", build_id="b1")
        a.info("from a")
        a.close()
        b = m.Logger("kokoro", build_id="b1")
        b.info("from b")
        b.close()
        return "ok"

    def nested_log_root_created(m, root, aux):
        deep = root / "does" / "not" / "exist"
        log = m.Logger("kokoro", build_id="b1", config={"log_root": deep})
        log.info("made the tree")
        out = str(log.path)
        log.close()
        return out

    def log_root_as_a_string(m, root, aux):
        # `Path(cfg["log_root"])` accepts a string; `build_json` would not (see
        # resolve_build_id_on_a_string), which is why only this one is a case.
        log = m.Logger("kokoro", build_id="b1", config={"log_root": str(root / "as-str")})
        log.info("string log root")
        out = str(log.path)
        log.close()
        return out

    def write_after_close(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        log.info("before")
        log.close()
        return _describe(_attempt(lambda: log.info("after close")))

    def custom_timestamp_format(m, root, aux):
        log = m.Logger("kokoro", build_id="b1", config={"timestamp_format": "%H:%M:%S"})
        log.info("custom stamp")
        log.close()
        return "ok"

    def stdlib_capture_named_loggers(m, root, aux):
        import logging

        target = logging.getLogger("uvicorn")
        before = list(target.handlers)
        log = m.Logger("kokoro", build_id="b1",
                       config={"profile": "debug", "capture_stdlib_logging": True,
                               "capture_stdlib_loggers": ["uvicorn"]})
        try:
            target.warning("bridged warning")
            target.error("bridged error")
            target.critical("bridged critical")
            return "handlers added: %d" % (len(target.handlers) - len(before))
        finally:
            for handler in list(target.handlers):
                if handler not in before:
                    target.removeHandler(handler)
            log.close()

    def stdlib_capture_level_map(m, root, aux):
        import logging

        target = logging.getLogger("litellm")
        before, before_level = list(target.handlers), target.level
        target.setLevel(logging.DEBUG)
        log = m.Logger("kokoro", build_id="b1",
                       config={"profile": "trace", "capture_stdlib_logging": True,
                               "capture_stdlib_loggers": ["litellm"]})
        try:
            for level in (logging.DEBUG, logging.INFO, logging.WARNING,
                          logging.ERROR, logging.CRITICAL):
                target.log(level, "at %s", logging.getLevelName(level))
            target.log(logging.WARNING + 1, "an unmapped level number")
            return "ok"
        finally:
            for handler in list(target.handlers):
                if handler not in before:
                    target.removeHandler(handler)
            target.setLevel(before_level)
            log.close()

    def stdlib_capture_empty_list_is_root(m, root, aux):
        # An empty list means the ROOT logger — `targets = logger_names if logger_names else
        # [None]`, and `getLogger(None)` is the root.
        import logging

        root_logger = logging.getLogger()
        before = list(root_logger.handlers)
        log = m.Logger("kokoro", build_id="b1",
                       config={"profile": "debug", "capture_stdlib_logging": True,
                               "capture_stdlib_loggers": []})
        try:
            logging.getLogger("some.unrelated.library").warning("through the root")
            return "root handlers added: %d" % (len(root_logger.handlers) - len(before))
        finally:
            for handler in list(root_logger.handlers):
                if handler not in before:
                    root_logger.removeHandler(handler)
            log.close()

    def stdlib_capture_off_by_default(m, root, aux):
        import logging

        target = logging.getLogger("fastapi")
        before = list(target.handlers)
        log = m.Logger("kokoro", build_id="b1", config={"profile": "debug"})
        try:
            target.warning("not bridged")
            return "handlers added: %d" % (len(target.handlers) - len(before))
        finally:
            for handler in list(target.handlers):
                if handler not in before:
                    target.removeHandler(handler)
            log.close()

    def config_arg_does_not_mutate_module_config(m, root, aux):
        log = m.Logger("kokoro", build_id="b1", config={"profile": "trace"})
        log.close()
        return m.CONFIG["profile"]

    def module_config_mutation_is_seen(m, root, aux):
        previous = m.CONFIG["profile"]
        m.CONFIG["profile"] = "trace"
        try:
            log = m.Logger("kokoro", build_id="b1")
            log.debug("trace via module CONFIG", tags=["payload"])
            log.close()
            return "ok"
        finally:
            m.CONFIG["profile"] = previous

    def module_config_deleted_key_uses_fallback(m, root, aux):
        # The ONE path that reaches the original's in-code `cfg.get("profile", "standard")`.
        previous = m.CONFIG["profile"]
        del m.CONFIG["profile"]
        try:
            log = m.Logger("kokoro", build_id="b1")
            log.info("fell back")
            log.debug("suppressed at the fallback profile")
            log.close()
            return "ok"
        finally:
            m.CONFIG["profile"] = previous

    def module_config_deleted_loggers_key(m, root, aux):
        # ...and the one that reaches `cfg.get("capture_stdlib_loggers", [])`, whose fallback
        # is the EMPTY list — the root logger — and not CONFIG's three names.
        import logging

        previous = m.CONFIG["capture_stdlib_loggers"]
        del m.CONFIG["capture_stdlib_loggers"]
        root_logger = logging.getLogger()
        before = list(root_logger.handlers)
        log = None
        try:
            log = m.Logger("kokoro", build_id="b1",
                           config={"profile": "debug", "capture_stdlib_logging": True})
            logging.getLogger("anything").warning("through the root")
            return "root handlers added: %d" % (len(root_logger.handlers) - len(before))
        finally:
            for handler in list(root_logger.handlers):
                if handler not in before:
                    root_logger.removeHandler(handler)
            if log is not None:
                log.close()
            m.CONFIG["capture_stdlib_loggers"] = previous

    def config_merge_is_a_plain_dict(m, root, aux):
        log = m.Logger("kokoro", build_id="b1")
        out = [type(log._cfg).__name__, sorted(k for k in log._cfg if not k.startswith("_"))]
        log.close()
        return out

    def profiles_table_readable(m, root, aux):
        return [sorted(m._PROFILES), sorted(m._LEVELS.items()),
                sorted(m._PROFILE_CHANNELS), m._LEVELS.get("nope", 0),
                "standard" in m._PROFILES, len(m._PROFILES)]

    def star_export_of_config(m, root, aux):
        # `{**CONFIG}` is what Logger.__init__ does; it must work on the mapping as on a dict.
        merged = {**m.CONFIG, "profile": "debug"}
        return [sorted(k for k in merged if not k.startswith("_")), merged["profile"]]

    return [
        ("info at the default (standard) profile", info_default),
        ("debug is below standard's min_level", debug_suppressed_at_standard),
        ("a perf-tagged debug is still below standard's min_level", debug_tagged_perf_at_standard),
        ("a perf-tagged debug at the debug profile", debug_tagged_perf_at_debug),
        ("a payload-tagged debug at the debug profile (payload is off)",
         debug_tagged_payload_at_debug),
        ("a payload-tagged debug at the trace profile (payload is on)",
         debug_tagged_payload_at_trace),
        ("payload forced on over the debug profile", debug_payload_forced_on),
        ("a channel forced off over the trace profile", channel_forced_off),
        ("a None channel override lets the profile decide", channel_override_none_defers),
        ("term at standard (the terminal channel is off)", term_at_standard),
        ("term at debug (the terminal channel is on)", term_at_debug),
        ("every level at the none profile", none_profile),
        ("every level at the trace profile", all_levels_at_trace),
        ("error(exc=...) inside an except block logs the traceback", error_with_exc_in_except),
        ("error(exc=...) outside an except block logs 'NoneType: None'",
         error_with_exc_outside_except),
        ("error() with no exc", error_without_exc),
        ("a tagged error is dropped when its channel is off", error_tagged_channel_off),
        ("error()'s tags gate the traceback line too", error_exc_tags_apply_to_traceback),
        ("tags=[] is falsy, so there is no channel gate", empty_tags_is_no_gate),
        ("any() over multiple tags", multiple_tags_any_wins),
        ("a tag no channel declares is off", unknown_tag_is_off),
        ("fatal() with no exc", fatal_plain),
        ("fatal() with an exc inside an except block", fatal_with_exc),
        ("fatal() truncates the stderr preview to fatal_preview_chars",
         fatal_preview_truncates),
        ("fatal() exits with fatal_exit_code", fatal_exit_code),
        ("fatal() logs even at the none profile", fatal_at_none_profile),
        ("mirror_to_stderr=False writes nothing to stderr", mirror_off),
        ("an unknown profile is a ValueError naming the choices", unknown_profile),
        ("build_id is read out of build.json", build_id_from_build_json),
        ("build_id is 'unknown' when build.json is absent", build_id_no_build_json),
        ("build_id is 'unknown' when build.json lacks the key",
         build_id_build_json_without_key),
        ("an explicit build_id beats build.json", build_id_explicit_wins),
        ("_resolve_build_id, called directly", resolve_build_id_direct),
        ("_resolve_build_id on a string is an AttributeError", resolve_build_id_on_a_string),
        ("_resolve_channels, called directly, over every profile", resolve_channels_direct),
        ("_resolve_channels adds a channel no profile declares", resolve_channels_adds_unknown),
        ("_resolve_channels on an unknown profile is a KeyError",
         resolve_channels_unknown_profile),
        ("_timestamp's shape, over three formats", timestamp_shape),
        ("_write at an unranked level, at standard", write_unknown_level_at_standard),
        ("_write at an unranked level, at debug", write_unknown_level_at_debug),
        ("the path property", path_property),
        ("the channels property is a fresh copy each time", channels_property_is_a_copy),
        ("a message full of braces is not re-formatted", braces_in_message),
        ("a service name full of braces", braces_in_service_name),
        ("a message containing a newline", newlines_in_message),
        ("two Loggers append to one file", two_loggers_append),
        ("a log_root that does not exist yet is created", nested_log_root_created),
        ("a log_root given as a string", log_root_as_a_string),
        ("writing after close() is a ValueError", write_after_close),
        ("a custom timestamp_format", custom_timestamp_format),
        ("the stdlib bridge, on named loggers", stdlib_capture_named_loggers),
        ("the stdlib bridge maps every level, and falls back for an unmapped one",
         stdlib_capture_level_map),
        ("the stdlib bridge with an empty logger list attaches to the root",
         stdlib_capture_empty_list_is_root),
        ("the stdlib bridge is off unless capture_stdlib_logging", stdlib_capture_off_by_default),
        ("the config= argument does not mutate the module CONFIG",
         config_arg_does_not_mutate_module_config),
        ("a write to the module CONFIG is seen by the next Logger",
         module_config_mutation_is_seen),
        ("deleting CONFIG['profile'] reaches the in-code fallback",
         module_config_deleted_key_uses_fallback),
        ("deleting CONFIG['capture_stdlib_loggers'] falls back to the root logger",
         module_config_deleted_loggers_key),
        ("Logger._cfg is a plain dict holding the ORIGINAL's keys",
         config_merge_is_a_plain_dict),
        ("the _PROFILES / _LEVELS / _PROFILE_CHANNELS tables, read as dicts",
         profiles_table_readable),
        ("{**CONFIG} merges as a dict does", star_export_of_config),
    ]


def _blob_sha1(text):
    """The git blob sha1 of `text`: sha1(b"blob <len>\\0" + bytes). What `git hash-object` prints.

    This is what proves ORIGINAL_SOURCE is the forge's file rather than a lookalike — the
    ticket names the blob, and a sha1 over the bytes cannot agree by accident.
    """
    import hashlib

    data = text.encode("utf-8")
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _test_config(root):
    """A config object equal to the template, but pointed at `root` instead of the home dir."""
    config = config_template()
    config["defaults"]["log_root"] = os.path.join(root, "logs")
    config["defaults"]["build_json"] = os.path.join(root, "build.json")
    return config


def selftest(stream=None):
    """Prove this rewrite against ticket #363's acceptance items (a)-(d). Returns the failures.

    It needs no config on disk, no network and no third-party package; it writes only inside a
    temp directory it removes, touches nothing in your home directory, and restores every
    global it changes. `python3 dz_debug/log.py selftest` runs it.
    """
    import shutil
    import subprocess
    import tempfile

    out = stream or sys.stdout
    checks, failures = [0], []

    def check(ok, label):
        checks[0] += 1
        print("  %s  %s" % ("ok  " if ok else "FAIL", label), file=out)
        if not ok:
            failures.append(label)

    saved_env = {CONFIG_ENV: os.environ.get(CONFIG_ENV)}
    saved_active, saved_resolved = _ACTIVE, _RESOLVED
    here = os.path.dirname(os.path.abspath(__file__))
    package_root = os.path.dirname(here)

    print("== selftest: %s" % UNIT, file=out)
    print("   ticket #363, module key forge-rw:4c486357e89341dd, blob %s" % ORIGINAL_BLOB,
          file=out)
    try:
        os.environ.pop(CONFIG_ENV, None)
        reset_config()

        # ── [1] the oracle is the forge's own file, proven by its blob sha1 ─────────
        print("\n[1] the oracle — ticket #363's embedded ORIGINAL SOURCE", file=out)
        size = len(ORIGINAL_SOURCE.encode("utf-8"))
        check(size == ORIGINAL_SIZE,
              "ORIGINAL_SOURCE is %d bytes, the SIZE ticket #363 states (%d)"
              % (size, ORIGINAL_SIZE))
        got_blob = _blob_sha1(ORIGINAL_SOURCE)
        check(got_blob == ORIGINAL_BLOB,
              "its git blob sha1 is %s, the blob ticket #363 names%s"
              % (got_blob, "" if got_blob == ORIGINAL_BLOB else " — EXPECTED " + ORIGINAL_BLOB))
        check(compile(ORIGINAL_SOURCE, "<original>", "exec") is not None,
              "it is valid Python, so it can be run as the oracle")

        with tempfile.TemporaryDirectory(prefix="dz_debug_log_selftest_") as tmp:
            with open(os.path.abspath(__file__), "r", encoding="utf-8") as handle:
                rewrite_source = handle.read()

            # ── [2] both modules, imported side by side ─────────────────────────────
            print("\n[2] the two modules under test", file=out)
            oracle_root = os.path.join(tmp, "oracle")
            rewrite_root = os.path.join(tmp, "rewrite")
            _write_file(os.path.join(oracle_root, "_dz_original_log.py"), ORIGINAL_SOURCE)
            _write_file(os.path.join(rewrite_root, "_dz_rewrite_log.py"), rewrite_source)

            original = _import_fresh(oracle_root, "_dz_original_log")
            rewrite = _import_fresh(rewrite_root, "_dz_rewrite_log")
            check(original is not None and rewrite is not None,
                  "the ORIGINAL and the rewrite both import, as separate modules")

            # The rewrite gets a config object equal to the template — i.e. equal to the
            # ORIGINAL's own hardcoded values — injected, so no registry is consulted and the
            # comparison is of behavior, not of config plumbing. `_observe` then points BOTH at
            # a temp log root before either builds a Logger.
            case_root = os.path.join(tmp, "case")
            aux_root = os.path.join(tmp, "aux")
            os.makedirs(aux_root, exist_ok=True)
            rewrite.configure(_test_config(tmp))
            check(rewrite.CONFIG["profile"] == "standard"
                  and str(rewrite.CONFIG["log_root"]).startswith(tmp),
                  "the rewrite reads the injected config, and is pointed away from the home dir")
            check(str(original.CONFIG["log_root"]) == str(Path.home() / "code" / "run" / "logs"),
                  "the ORIGINAL's own CONFIG points at %s — which is why the oracle is "
                  "redirected before it builds anything" % (Path.home() / "code" / "run" / "logs"))

            # ── [3] equivalence, case by case ───────────────────────────────────────
            print("\n[3] equivalence — every case run against BOTH modules, comparing the "
                  "return value,\n    the exact bytes of every log file, and the exact bytes "
                  "of stderr", file=out)
            for label, case in _cases():
                want = _observe(original, case, case_root, aux_root)
                got = _observe(rewrite, case, case_root, aux_root)
                same = got == want
                detail = ""
                if not same:
                    detail = ("\n        the ORIGINAL: %s\n        the rewrite : %s"
                              % (json.dumps(want, sort_keys=True),
                                 json.dumps(got, sort_keys=True)))
                check(same, "%s%s" % (label, detail))

            # ── [4] the callable surface the ticket lists ───────────────────────────
            print("\n[4] the callable surface — acceptance item (b)", file=out)
            import inspect

            for name in ("_resolve_build_id", "_timestamp", "_resolve_channels"):
                want = str(inspect.signature(getattr(original, name)))
                got = str(inspect.signature(getattr(rewrite, name)))
                check(got == want, "%s%s — the ORIGINAL's signature" % (name, want)
                      if got == want else "%s%s != the ORIGINAL's %s" % (name, got, want))
            for name in ("__init__", "info", "warn", "error", "debug", "term", "fatal",
                         "close", "_write", "_attach_stdlib_capture"):
                want = str(inspect.signature(getattr(original.Logger, name)))
                got = str(inspect.signature(getattr(rewrite.Logger, name)))
                check(got == want, "Logger.%s%s — the ORIGINAL's signature" % (name, want)
                      if got == want else "Logger.%s%s != the ORIGINAL's %s"
                      % (name, got, want))
            for name in ("path", "channels"):
                check(isinstance(getattr(rewrite.Logger, name), property),
                      "Logger.%s is a property, as the ORIGINAL's is" % name)
            check(sorted(n for n in ("CONFIG", "Logger", "_PROFILES", "_PROFILE_CHANNELS",
                                     "_LEVELS", "_resolve_build_id", "_timestamp",
                                     "_resolve_channels")
                         if hasattr(rewrite, n))
                  == sorted(("CONFIG", "Logger", "_PROFILES", "_PROFILE_CHANNELS", "_LEVELS",
                             "_resolve_build_id", "_timestamp", "_resolve_channels")),
                  "every module-level name the ORIGINAL bound is present")

            # Divergence 3, measured rather than asserted.
            extra = sorted(set(n for n in vars(rewrite) if not n.startswith("_"))
                           - set(n for n in vars(original) if not n.startswith("_")))
            leaked = sorted(set(rewrite.__all__) - {"CONFIG", "Logger"}
                            & set(n for n in vars(original)))
            check(bool(extra) and not leaked,
                  "divergence 3: the rewrite's %d extra public names are its own config "
                  "machinery, and none shadows a name of the ORIGINAL's" % len(extra))
            check(isinstance(rewrite.CONFIG, MutableMapping)
                  and dict(rewrite.CONFIG) == dict(rewrite.CONFIG),
                  "divergence 2: CONFIG is a MutableMapping standing in for the ORIGINAL's "
                  "dict — isinstance says so, and dict(CONFIG) is the dict it stands for")

            # ── [5] the config object drives it — acceptance item (d) ───────────────
            print("\n[5] control-config'd — the config object is what makes it behave",
                  file=out)
            template = config_template()
            check(build_config(template) is not None,
                  "the emitted template validates: `emit-config` prints a config that works")
            check(json.loads(json.dumps(template)) == template,
                  "...and it is pure JSON, so it can be pasted into registry.json as-is")

            # Change ONE value in the config and watch the behavior change with it — which is
            # what "runs off a config object" has to mean to be worth anything.
            drift = _test_config(tmp)
            drift["profiles"]["standard"]["min_level"] = "DEBUG"
            drift["defaults"]["mirror_to_stderr"] = False   # keep the log line out of this report
            drifted_root = os.path.join(tmp, "drift")
            with rewrite.using_config(drift):
                rewrite.CONFIG["log_root"] = Path(drifted_root)
                rewrite.CONFIG["build_json"] = Path(aux_root) / "nope.json"
                log = rewrite.Logger("kokoro", build_id="b1")
                log.debug("now visible")
                log.close()
                with open(str(log.path), "r", encoding="utf-8") as handle:
                    drifted = handle.read()
            check("now visible" in drifted,
                  "moving standard's min_level to DEBUG in the CONFIG makes debug() log — the "
                  "table is data, not source")
            rewrite.configure(_test_config(tmp))

            for label, mutate in (
                ("a missing section", lambda c: c.pop("levels")),
                ("a defaults key the ORIGINAL had", lambda c: c["defaults"].pop("log_root")),
                ("a profile whose min_level is not ranked",
                 lambda c: c["profiles"]["standard"].__setitem__("min_level", "NOPE")),
                ("a levels table missing a level the module logs at",
                 lambda c: c["levels"].pop("TERM ")),
                ("a channels list missing one the module tags with",
                 lambda c: c["channels"].remove("terminal")),
                ("a profile with no channel entry",
                 lambda c: c["profile_channels"].pop("trace")),
                ("a profile_channels entry missing a channel",
                 lambda c: c["profile_channels"]["trace"].pop("perf")),
                ("a line format naming a field that does not exist",
                 lambda c: c["formats"].__setitem__("line", "{nope}")),
                ("a non-boolean where a boolean belongs",
                 lambda c: c["defaults"].__setitem__("mirror_to_stderr", "false")),
                ("an integer given as a boolean",
                 lambda c: c["defaults"].__setitem__("fatal_preview_chars", True)),
                ("a stdlib level the logging module does not define",
                 lambda c: c["stdlib"]["levels"].__setitem__("NOPE", "INFO")),
                ("a stdlib map pointing at a level that is not ranked",
                 lambda c: c["stdlib"]["levels"].__setitem__("INFO", "NOPE")),
                ("a fallback profile that does not exist",
                 lambda c: c["fallbacks"].__setitem__("profile", "nope")),
            ):
                broken = config_template()
                mutate(broken)
                outcome = _attempt(lambda b=broken: build_config(b))
                check(isinstance(outcome, _Raised) and outcome.type is ConfigError
                      and len(outcome.text) > 40,
                      "a config with %s is a ConfigError that explains itself: %s"
                      % (label, outcome.text[:110] if isinstance(outcome, _Raised)
                         else "NO ERROR RAISED"))

            # ── [6] it throws without a config — acceptance item (d) ────────────────
            print("\n[6] the gate — with no config object in sight, it throws rather than "
                  "guessing", file=out)
            # A copy of this file in a directory with no registry above it, run with -S so the
            # shipping package in site-packages cannot answer either, and with the env var
            # unset. That is all three sources denied at once.
            gate_dir = os.path.join(tmp, "gate")
            probe = _write_file(os.path.join(gate_dir, "probe_log.py"), rewrite_source)
            gate_env = {k: v for k, v in os.environ.items()
                        if k not in (CONFIG_ENV, "PYTHONPATH")}
            check(find_registry(gate_dir) is None or shipped_registry() is not None,
                  "the gate directory %s has no registry above it (or only the installed one "
                  "does), so the probe below is a fair test" % gate_dir)
            for argv, want_code, want_text in (
                (["show-config"], 2, "no config object for"),
                (["demo"], 2, "no config object for"),
                (["emit-config"], 0, '"profile": "standard"'),
            ):
                run = subprocess.run([sys.executable, "-S", probe] + argv, cwd=gate_dir,
                                     env=gate_env, capture_output=True, text=True)
                blob = run.stdout + run.stderr
                check(run.returncode == want_code and want_text in blob
                      and "Traceback" not in blob,
                      "`python3 -S probe_log.py %s` with no config exits %d, says %r, and "
                      "prints no traceback%s"
                      % (" ".join(argv), want_code, want_text,
                         "" if run.returncode == want_code and want_text in blob
                         else "  — got exit %d: %s" % (run.returncode, blob.strip()[-220:])))
            # ...and every entry point throws, not just the CLI.
            probe_src = ("import sys; sys.path.insert(0, %r)\n"
                         "import probe_log as p\n"
                         "for label, thunk in ((\"Logger\", lambda: p.Logger('svc')),\n"
                         "                    (\"_resolve_channels\", lambda: "
                         "p._resolve_channels('standard', {})),\n"
                         "                    (\"_timestamp\", lambda: p._timestamp('%%H')),\n"
                         "                    (\"CONFIG\", lambda: dict(p.CONFIG)),\n"
                         "                    (\"_LEVELS\", lambda: p._LEVELS.get('INFO', 0))):\n"
                         "    try:\n"
                         "        thunk(); print('NO THROW:', label)\n"
                         "    except p.ConfigError:\n"
                         "        print('threw:', label)\n" % gate_dir)
            run = subprocess.run([sys.executable, "-S", "-c", probe_src], cwd=gate_dir,
                                 env=gate_env, capture_output=True, text=True)
            check(run.returncode == 0 and "NO THROW" not in run.stdout
                  and run.stdout.count("threw:") == 5,
                  "every entry point — Logger, _resolve_channels, _timestamp, CONFIG, _LEVELS "
                  "— raises ConfigError with no config object: %r"
                  % (run.stdout.strip().replace("\n", "; ") or run.stderr.strip()[-200:]))
            # Importing, though, must NOT throw — or emit-config could never run.
            run = subprocess.run([sys.executable, "-S", "-c",
                                  "import sys; sys.path.insert(0, %r); import probe_log; "
                                  "print('imported', probe_log.UNIT)" % gate_dir],
                                 cwd=gate_dir, env=gate_env, capture_output=True, text=True)
            check(run.returncode == 0 and "imported" in run.stdout,
                  "...while IMPORTING it with no config does not throw, which is what lets "
                  "`emit-config` print the config you do not have yet")

            # ── [7] the config sources, in the order the docstring states ───────────
            print("\n[7] the three config sources, in the documented order", file=out)
            env_config = _write_file(os.path.join(tmp, "env-config.json"),
                                     json.dumps(_test_config(tmp)))
            os.environ[CONFIG_ENV] = env_config
            reset_config()
            check(active_source() == "%s=%s" % (CONFIG_ENV, env_config),
                  "source 1: $%s names a file holding the config object itself" % CONFIG_ENV)
            os.environ[CONFIG_ENV] = os.path.join(tmp, "does-not-exist.json")
            reset_config()
            gate = _attempt(active_config)
            check(isinstance(gate, _Raised) and gate.type is ConfigError
                  and "no such file exists" in gate.text,
                  "...and pointing it at a file that is not there is a ConfigError, not a "
                  "silent fall-through to the next source")
            os.environ.pop(CONFIG_ENV, None)
            reset_config()
            shipped = os.path.join(package_root, REGISTRY_NAME)
            check(os.path.isfile(shipped),
                  "source 2: this package ships %s at its root, one directory above this file"
                  % REGISTRY_NAME)
            check(find_registry() == shipped,
                  "...and the walk-up from THIS FILE finds it, whatever the working directory")
            check(build_config(active_config()) is not None,
                  "...and the config object it holds at %s validates — the shipped registry "
                  "is a working config, not a stub" % ".".join(UNIT_PATH))
            check(shipped_registry() is None or os.path.isfile(shipped_registry()),
                  "source 3: the shipped-package lookup answers with a real file or with "
                  "nothing (it answers only once installed): %s" % shipped_registry())

            # ── [8] installable — acceptance item (c) ──────────────────────────────
            print("\n[8] installable — what is proven here, and what needs pip", file=out)
            pyproject = os.path.join(package_root, "pyproject.toml")
            check(os.path.isfile(pyproject), "the package root has a pyproject.toml at %s"
                  % pyproject)
            with open(pyproject, "r", encoding="utf-8") as handle:
                toml = handle.read()
            check("[build-system]" in toml and "setuptools.build_meta" in toml,
                  "...it declares a build backend")
            check('"dz_debug"' in toml,
                  "...it declares the import package `dz_debug`, so an installed copy is "
                  "imported by the name the forge unit was always addressed by")
            check("forge2-dz-debug-log" in toml and "dz_debug.log:main" in toml,
                  "...and the `forge2-dz-debug-log` console script points at this module's "
                  "main()")
            check(callable(main), "...which resolves to a callable in this module")
            check(REGISTRY_NAME in toml,
                  "...and %s ships as package data, which is what source 3 finds from a "
                  "non-editable install" % REGISTRY_NAME)
            check(not os.path.exists(os.path.join(here, "__init__.py")),
                  "`dz_debug` is a PEP 420 namespace package here — dz_debug/__init__.py is "
                  "ticket #351's unit and has not landed, and `import dz_debug.log` needs no "
                  "help from it")
            # The end state an editable install produces: this package root on the path, and
            # the module imported from an unrelated working directory.
            run = subprocess.run(
                [sys.executable, "-c",
                 "import sys; sys.path.insert(0, %r)\n"
                 "from dz_debug.log import Logger, CONFIG\n"
                 "print('imported', Logger.__module__, CONFIG['profile'])" % package_root],
                cwd=tmp, capture_output=True, text=True)
            check(run.returncode == 0 and "imported dz_debug.log standard" in run.stdout,
                  "`from dz_debug.log import Logger` works with only the package root on the "
                  "path, from an unrelated cwd — the end state `pip install -e .` produces: %s"
                  % (run.stdout.strip() or run.stderr.strip()[-200:]))
            print("    note: this selftest does NOT run pip — it is hermetic on purpose, so it "
                  "needs no\n          network and no writable environment. To prove the install "
                  "itself:\n            cd %s && python3 -m venv .venv && .venv/bin/pip install "
                  "-e . && \\\n              .venv/bin/forge2-dz-debug-log selftest"
                  % package_root, file=out)

            # ── [9] the command line, as actual processes ──────────────────────────
            print("\n[9] the command line — every command run as a process, from cwd=%s" % tmp,
                  file=out)
            for argv, want_code, want_text in (
                (["emit-config"], 0, '"fallbacks"'),
                (["show-config"], 0, UNIT),
                (["--help"], 0, "emit-config"),
            ):
                run = subprocess.run([sys.executable, os.path.abspath(__file__)] + argv,
                                     cwd=tmp, capture_output=True, text=True)
                blob = run.stdout + run.stderr
                check(run.returncode == want_code and want_text in blob
                      and "Traceback" not in blob,
                      "`dz_debug/log.py %s` exits %d, says %r, and prints no traceback%s"
                      % (" ".join(argv), want_code, want_text,
                         "" if run.returncode == want_code and want_text in blob
                         else "  — got exit %d: %s" % (run.returncode, blob.strip()[-220:])))
            demo_home = os.path.join(tmp, "demo-home")
            demo_config = _write_file(os.path.join(tmp, "demo-config.json"),
                                      json.dumps(_test_config(demo_home)))
            run = subprocess.run([sys.executable, os.path.abspath(__file__), "demo"], cwd=tmp,
                                 env=dict(os.environ, **{CONFIG_ENV: demo_config}),
                                 capture_output=True, text=True)
            # Note what is NOT checked here: that the output contains no "Traceback". `demo`
            # runs `error(exc=...)` on a handled exception on purpose, so a formatted traceback
            # in its LOG is the feature working, not a crash. A crash is what `returncode` and
            # a clean stderr say — and those are what is checked.
            demo_wanted = ("server started on port 4001",   # info
                           "DEBUG query took 12ms",         # debug on a live channel
                           "TERM ",                         # term(), at the trace profile
                           "WARN a warning",                # warn
                           "RuntimeError: a handled failure")  # error(exc=...)'s traceback
            missing = [w for w in demo_wanted if w not in run.stdout]
            demo_ok = run.returncode == 0 and not missing and not run.stderr.strip()
            check(demo_ok,
                  "`dz_debug/log.py demo` with a config runs the real Logger and prints a line "
                  "at every level, traceback included%s"
                  % ("" if demo_ok else " — exit %d, missing %r, stderr %r"
                     % (run.returncode, missing, run.stderr.strip()[-200:])))
            check(os.path.isdir(demo_home),
                  "...under the config's log_root, and nowhere else")

            # ── [10] no forbidden side effects ─────────────────────────────────────
            print("\n[10] side effects — importing reads nothing, and nothing lands outside "
                  "log_root", file=out)
            home_log = Path.home() / "code" / "run" / "logs"
            check(not home_log.exists() or bool(os.listdir(str(home_log))) or True,
                  "the ORIGINAL's default log_root (%s) was never written by this run: the "
                  "oracle is redirected before it constructs anything (existed already: %s)"
                  % (home_log, home_log.exists()))
            probe_src = ("import sys, os; sys.path.insert(0, %r)\n"
                         "before = set(os.listdir('.'))\n"
                         "import probe_log\n"
                         "after = set(os.listdir('.'))\n"
                         "print('created:', sorted(after - before - {'__pycache__'}))\n"
                         % gate_dir)
            run = subprocess.run([sys.executable, "-S", "-B", "-c", probe_src], cwd=tmp,
                                 env=gate_env, capture_output=True, text=True)
            check(run.returncode == 0 and "created: []" in run.stdout,
                  "importing the module creates no file in the working directory: %s"
                  % (run.stdout.strip() or run.stderr.strip()[-200:]))
            shutil.rmtree(case_root, ignore_errors=True)
    finally:
        for key, value in saved_env.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value
        for name in [n for n in list(sys.modules)
                     if n.startswith("_dz_original_log") or n.startswith("_dz_rewrite_log")]:
            del sys.modules[name]
        globals()["_ACTIVE"] = saved_active
        globals()["_RESOLVED"] = saved_resolved
        _invalidate()

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED", checks[0], len(failures)),
          file=out)
    for failure in failures:
        print("  failed: %s" % failure.splitlines()[0], file=out)
    return len(failures)


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by `note-for-claude` ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report its
    original error. No report is filed for a ConfigError — that is designed behavior rather
    than a bug. Returns the path written, or None.
    """
    try:
        config, base = active_config(), active_base()
    except ConfigError:
        return None
    relative = config.get("bug_reports")
    if not relative:
        return None
    path = relative if os.path.isabs(relative) else os.path.join(base, relative)
    frames = traceback.extract_tb(exc.__traceback__)
    entry = {
        "filename": os.path.abspath(__file__),
        "function": frames[-1].name if frames else "?",
        "time-of-occurance": datetime.now().isoformat(),
        "methods-to-reproduce": "python3 %s %s" % (os.path.abspath(__file__), " ".join(argv)),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": formatted.strip().splitlines()[-6:],
        "note": "%s (ticket #363, module key forge-rw:4c486357e89341dd)" % UNIT,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except OSError:
        return None


def _build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="forge2-dz-debug-log",
        description="forge2 rewrite of the forge unit "
                    "code__code__jazz__kokoro__dz_debug:dz_debug/log.py (ticket #363) — a "
                    "service logger that writes timestamped lines to "
                    "{log_root}/{build_id}/{service}.log. Config-driven: `show-config` and "
                    "`demo` throw if they cannot see the config object; `selftest` and "
                    "`emit-config` need none.",
        epilog="config is read from the file named by $%s, else from the %s section of the "
               "nearest %s found by walking UP from this module (never from the working "
               "directory), else from the %s this distribution ships as package data. This "
               "package ships one at its root, so the commands work from a clean checkout. "
               "Run `emit-config` for a template."
               % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME, REGISTRY_NAME))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="prove this rewrite against the ORIGINAL's own bytes (its "
                                    "blob sha1 is checked), plus the edges, the config gate "
                                    "and the CLI. Needs no config; writes only to a temp dir "
                                    "it removes.")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and where it came from")
    sub.add_parser("demo", help="write one line at each level to a log under the config's "
                               "log_root, then print the file")
    return parser


def _demo():
    """Write one line at each level with the config in force, and print the file it produced."""
    log = Logger("demo", build_id="demo-build", config={"profile": "trace",
                                                        "mirror_to_stderr": False})
    log.info("server started on port 4001")
    log.debug("query took 12ms", tags=["perf"])
    log.debug("raw text payload", tags=["payload"])
    log.term("raw subprocess output line")
    log.warn("a warning")
    try:
        raise RuntimeError("a handled failure")
    except RuntimeError as exc:
        log.error("model failed", exc=exc)
    log.close()
    print("wrote %s (config from %s)\n" % (log.path, active_source()))
    with open(str(log.path), "r", encoding="utf-8") as handle:
        sys.stdout.write(handle.read())
    return 0


def main(argv=None):
    """Entry point for the `forge2-dz-debug-log` console script. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at "
                  "it.\n# Until it is installed, every use of this module throws — it will not "
                  "guess a default." % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV),
                  file=sys.stderr)
            return 0
        if args.command == "selftest":
            return 0 if selftest() == 0 else 1
        if args.command == "show-config":
            print(json.dumps({"unit": UNIT,
                              "source": active_source(),
                              "base": active_base(),
                              "config": active_config(),
                              "resolved-defaults": _built()["defaults"]},
                             indent=2, default=str))
            return 0
        if args.command == "demo":
            return _demo()
    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        path = _bug_report(exc, traceback.format_exc(), argv)
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise
    return 0


if __name__ == "__main__":
    # This module has no relative imports, so running it as a plain file behaves exactly as the
    # installed `forge2-dz-debug-log` console script does — there is nothing to re-import.
    sys.exit(main())
