#!/usr/bin/env python3
"""forge2 / coupler / __main__ — a behavior-preserving rewrite of the forge unit
`coupler:coupler/__main__.py` (module key forge-rw:eb9c79df006733b5), filed under ticket
#403 against the FORGE-wide refactor standard #200. (#403 supersedes #296, which named its
source only as a `git cat-file` the sandboxed worker cannot run; #403 embeds the source and
is done here.)

WHAT THIS IS
------------
The original forge unit was 9329 bytes: a stable MCP (Model Context Protocol) entry point
for Claude Desktop. It read jazz's `build.json` to report the active versioned env, proxied
two jazz MCP services through FastMCP, mounted a `why5` root-cause toolset imported from the
jazz dev tree, and bridged six tools onto a browser UI over HTTP. This file is an entirely
new implementation of that unit. It keeps the original's observable behavior and its callable
surface, and it adds the three things #200 requires that the original lacked: it is a proper
installable package, it is driven by a configuration object, and it refuses to run when it
cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    _load_build() -> dict
    _notes_python() -> str
    _jazz_client(module: str) -> Client
    async notes_db_proxy(tool: str, args: dict = {}) -> str
    async z3_proxy(tool: str, args: dict = {}) -> str
    _build_app()

`notes_db_proxy` and `z3_proxy` keep the original's MUTABLE `{}` default. A shared mutable
default is normally a defect, and it is preserved deliberately: it is the surface this ticket
requires, and it is inert here because neither function mutates `args` — each only forwards
it. `selftest` proves the non-mutation rather than asserting it, so the surface can be kept
without carrying the bug that shape usually implies.

WHY THIS MODULE IS IMPORTABLE WITHOUT FASTMCP (the central design decision)
--------------------------------------------------------------------------
The original did `import httpx` and `from fastmcp import FastMCP, Client` at module top
level, and built `mcp = FastMCP("coupler")` at IMPORT time. Neither package is installable
in every checkout this unit must run in — in the congruency checkout that executes this
ticket, `import fastmcp` and `import httpx` both fail — so the original module cannot even be
IMPORTED there, and nothing about it can be run or proven.

This rewrite therefore names those dependencies IN THE CONFIG (the `providers` block) and
resolves them LAZILY, on first use. Three consequences, all intended:

  * importing this module runs no third-party import and builds no server, so it imports
    cleanly anywhere and `selftest` can prove the unit's behavior with fake providers
    standing in for FastMCP and httpx;
  * with the shipped `registry.json`, which names the real `fastmcp:FastMCP`, `fastmcp:Client`
    and `httpx`, every code path below does exactly what the original's did;
  * a missing dependency surfaces as a `ConfigError` naming the module that could not be
    imported, at the point of use, instead of an ImportError traceback at import.

This is #200's requirement 4 doing real work: the hardcoded `fastmcp`/`httpx` imports were
themselves hardcoded params.

TERMS USED HERE
---------------
MCP
    Model Context Protocol — the protocol Claude Desktop speaks to tool servers. FastMCP is
    the Python framework this unit builds its server with.
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a
    single `.json` file holding the configuration for every tool in a set of packaging.
    `note-for-claude` states the contract this module obeys — "if a tool cannot see the
    registry it will throw an exeption" [sic]. THIS package ships its own `registry.json`
    beside this file; see CONFIGURATION.
config object
    The chunk of that registry belonging to this unit — the `forge2.coupler.__main__`
    section. It is what drives this module. `emit-config` prints a template of it.
provider
    A dependency named by the config as a `"module:attr"` string (or a bare `"module"`), and
    imported on first use. `providers.server` is the FastMCP class, `providers.client` the
    Client class, and so on. Naming them in config is what lets the real fastmcp be used in
    production and fakes be used in `selftest`, with the SAME code path.
env-backed setting
    A setting written `{"env": "NAME", "default": ...}`. The original read a hardcoded
    environment variable with a hardcoded fallback; here BOTH the variable name and the
    fallback come from the config, so the env override keeps working and nothing is baked in.
why5
    A 5-why root-cause analysis toolset the original imported out of the jazz DEV tree (not
    from an installed package) after mutating `sys.path`. Preserved exactly; see below.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
This unit resolves its config object on first use, from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. This file holds the unit
     config object itself — exactly what `emit-config` prints.
  2. otherwise, the `forge2.coupler.__main__` section of the nearest `registry.json` found by
     walking UP from THIS FILE's directory.

If NEITHER answers, every operation raises `ConfigError` and does no work. It never guesses a
default — that is `note-for-claude`'s rule and this ticket's acceptance item (d). A config
object that is found but is missing a key an operation needs is also a `ConfigError`, naming
the key.

This package ships `registry.json` NEXT TO this file, so source 2 answers and the unit works
from a clean checkout with no setup. That shipped registry carries EXACTLY the values the
original hardcoded, which is what makes this rewrite behavior-preserving in practice: the
values did not change, only their location did. The registry is the config object this unit
runs on; it is not a fallback baked into the code. Delete it (with `FORGE2_CONFIG` unset and
no other `registry.json` above this directory) and every operation throws — the gate is in
the code, not in the file's presence. `selftest` proves the gate directly, without deleting
anything, by pointing `FORGE2_CONFIG` at a file that does not exist.

`configure(config)` and `using_config(config)` inject a config object directly, in-process,
for callers that hold their configuration in memory rather than on disk.

WHAT IS A SETTING, AND WHAT IS NOT
----------------------------------
#200 requires no hardcoded paths or params; it does not require inventing knobs the unit
never had. Settings are the things the original BAKED IN: the two jazz paths and their env
var names, the `conf/env/build.json` location, the `COUPLER_PYTHON` var, the server name, the
service map, the why5 import location, the UI base URL and its 5-second timeout, and the
fastmcp/httpx dependencies. NOT settings, because they are the unit's structure rather than
its configuration: the names `Why5`, `from_ci_failure` and `from_commit_failure` that the
why5 import binds, the tool names and their docstrings (Claude Desktop's tool surface), and
the shape of each tool's return string. Changing those would change behavior, which is what
this ticket exists to prevent.

`NOTES_DB_URL` is deliberately ABSENT from the config. The original's docstring advertised it
("NOTES_DB_URL notes_db service URL (default: http://127.0.0.1:8765)") but the original's
code never read it — it is documented-but-dead. Preserving behavior means not reading it
either, and #200 does not license inventing a setting the unit never had. It is recorded here
so a reader comparing the two docstrings does not think it was dropped by accident.

DELIBERATE, DOCUMENTED DIVERGENCES (three, and one config-shape choice)
----------------------------------------------------------------------
Everything else is intended to be indistinguishable from the original. These three are forced
by the ticket's own requirements, and each is proven by `selftest`:

  1. WHEN CONFIG IS READ. The original snapshotted `JAZZ_ROOT`/`JAZZ_DEV` into globals at
     IMPORT time, so mutating the environment after import had no effect on them. This
     rewrite snapshots its config and those paths on FIRST USE and caches them, so within a
     process the env-to-path resolution still happens exactly ONCE, as in the original. The
     only observable difference is confined to changing the environment between import and
     first call. `reset_config()` makes the snapshot explicit and re-resolvable, which is
     what lets `selftest` test the resolution at all.
     `_notes_python()` is the exception, and matches the original exactly: the original read
     `COUPLER_PYTHON` at CALL time, so this rewrite reads the env on every call too. That
     asymmetry between the two is the original's, faithfully kept.
  2. THE UI BANNER PORT. The original printed the literal `mounted      : ui (port 8142)`
     even when `JSON_CONTROLS_URL` pointed somewhere else — a hardcoded param, and one that
     printed a falsehood whenever it was overridden. Requirement 4 forbids keeping it, so the
     port is derived from the UI base actually in force. With the shipped config's base
     (`http://127.0.0.1:8142`) the line is BYTE-IDENTICAL to the original's; with any other
     base it prints the truth instead of `8142`. A base with no port prints its host.
  3. IMPORT-TIME CONSTRUCTION. The original built `mcp = FastMCP("coupler")` at import and
     registered the two proxy tools onto it with `@mcp.tool()`. Building a server as a side
     effect of an import is exactly what makes the original unimportable without fastmcp, so
     here `mcp` is a lazily-built module attribute (PEP 562 `__getattr__`): the FIRST access
     to `coupler.__main__.mcp` builds the server, names it from the config, and registers
     `notes_db_proxy` and `z3_proxy` onto it — the same server, with the same two tools,
     built at first touch instead of at import. Accessing it without config raises
     `ConfigError` rather than building a half-configured server.
     A knock-on benefit: `notes_db_proxy` and `z3_proxy` are plain async functions here, so
     they are directly callable and directly testable, whereas `@mcp.tool()` may replace the
     name it decorates with a framework object depending on the fastmcp version.

AND the one config-shape choice, recorded here so nothing is hidden: the original wrote each
downstream module name TWICE — `"notes_db_mcp"` inside `notes_db_proxy` and again in
`_build_app`'s `services` map — so the two could drift apart. Here the `services` map is the
single source for both. Under the shipped config, which carries the original's own values,
every call site resolves to exactly the string the original hardcoded, so no behavior
changes; what changes is that re-pointing a service now moves its proxy with it instead of
leaving the two disagreeing. This is a consequence of requirement 4 (the names had to leave
the code), not an independent redesign.

RUNNING IT
----------
Every command below is executable as written from this file's own directory; from anywhere
else, give the full path to `__main__.py` instead of the bare name. Which directory you run
from does not change what config is found — the registry walk-up starts at THIS FILE, never
at the working directory.

    python3 __main__.py selftest       # prove the behavior, the edges and the config gate
    python3 __main__.py emit-config    # print a config-object template
    python3 __main__.py show-config    # print the resolved config + where it came from
    python3 __main__.py serve          # build the app and run it (the original's entry point)

`selftest` and `emit-config` need no config and write no files. `serve` is what the original's
`if __name__ == "__main__":` block did — `_build_app()` then `app.run()` — and it needs both
the config and a working fastmcp, so in a checkout without fastmcp it exits 2 with a one-line
config error naming the module that could not be imported. That is the gate working, not a
defect.

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, and the package is committed in
full beside it — `pyproject.toml`, `__init__.py`, `registry.json`. From the PACKAGE ROOT (the
directory above this one, the one holding `pyproject.toml`):

    pip install -e .
    coupler selftest
    coupler serve                      # the stable MCP entry point Claude Desktop calls

`pyproject.toml` declares the `coupler` console script pointing at `main()` below, so Claude
Desktop can be pointed at a stable command instead of a path into a checkout. Because this
module is a package `__main__`, `python3 -m coupler` also runs it, which is the form the
original's own proxies use to launch downstream services. `registry.json` ships INSIDE the
import package as package-data, so a non-editable install still finds its config by walking
up from the installed module.

SIDE EFFECTS
------------
`selftest`, `emit-config` and `show-config` create no files and write nothing. `_build_app()`
prints its diagnostic banner to stderr and inserts the configured why5 path at the front of
`sys.path` — both are the original's behavior, and the `sys.path` insert happens even when
the why5 import then fails, exactly as in the original. Per `note-for-claude` ("all tools need
to pass a bug-report automatically ... if an exception is thrown") the CLI appends one
timestamped JSON line to the config's `bug_reports` path if it hits an UNEXPECTED exception —
that is, a defect in this tool. A `ConfigError` is designed behavior, not a bug: it files no
report and prints no traceback, and exits 2 with a single self-explaining line.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import contextlib
import importlib
import inspect
import io
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

__all__ = [
    "notes_db_proxy", "z3_proxy",
    "ConfigError", "load_config", "configure", "using_config", "reset_config",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS
#: in the config document, not a configurable setting — a config-driven tool has to know
#: which section is its own.
UNIT_PATH = ("forge2", "coupler", "__main__")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:coupler/coupler/__main__"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default. A dependency the config
    names but that cannot be imported is reported the same way — the config is what asked
    for it, so a broken provider is a config problem, not a crash.
    """


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None      # config object injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution, so callers re-read no files


def find_registry(start=None):
    """Walk UP from `start` (default: this file's directory) and return the nearest registry
    path, or None if the walk reaches the filesystem root without finding one."""
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

    Returns a `(config, base, source)` triple: the config object, the directory that relative
    paths inside it resolve against, and a human-readable description of where it came from.
    `start` overrides the directory the registry walk-up begins at.

    Raises:
        ConfigError: if no config object can be found, naming both sources that were tried.
    """
    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        if not os.path.isfile(env_path):
            raise ConfigError(
                "%s is set to %r, but no such file exists" % (CONFIG_ENV, env_path)
            )
        config = _read_json(env_path, "the config object named by " + CONFIG_ENV)
        if not isinstance(config, dict):
            raise ConfigError(
                "the config object at %s must be a JSON object, not %s"
                % (env_path, type(config).__name__)
            )
        return config, os.path.dirname(os.path.abspath(env_path)), "%s=%s" % (CONFIG_ENV, env_path)

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s: %s is unset and no %s was found by walking up from %s. "
            "Run `emit-config` for a template of the config object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))))
        )

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r "
                "section. Run `emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]),
                   " -> ".join(UNIT_PATH))
            )
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError(
            "the registry section %s at %s must be a JSON object, not %s"
            % (".".join(UNIT_PATH), registry_path, type(node).__name__)
        )

    config = dict(node)
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit
    # section may state its own to override it. This is inheritance inside one config
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
    """Drop the injected config, the cached disk resolution, and every cached snapshot; the
    next call re-resolves from scratch."""
    global _ACTIVE, _RESOLVED
    _ACTIVE = None
    _RESOLVED = None
    _invalidate()


def _invalidate():
    """Clear the caches that hang off a config object (see divergence 1: the paths and the
    providers are snapshotted on first use, so changing the config must drop them)."""
    _PROVIDER_CACHE.clear()
    _PATH_CACHE.clear()
    global _SERVER
    _SERVER = None


def _require(config, key, operation):
    """Return `config[key]`, or raise ConfigError naming the key and who needed it."""
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the key %r, which %s needs. Run `emit-config` "
            "for a template." % (UNIT, key, operation)
        )
    return config[key]


def _setting(key, operation):
    """Return the config's `key`, resolving the config object first."""
    return _require(active_config(), key, operation)


def _env_backed(key, operation):
    """Resolve an env-backed setting: `{"env": "NAME", "default": ...}`.

    The environment variable the config NAMES wins; otherwise the config's `default`. The
    original hardcoded both the variable name and the fallback — naming them here instead is
    #200's control-config requirement, and reading the named variable is what keeps the
    original's env override working.

    Returns `(value, from_env)`, so a caller can tell an env value from a default. That
    distinction is load-bearing for the jazz paths — see `_jazz_path`.
    """
    spec = _setting(key, operation)
    if not isinstance(spec, dict):
        raise ConfigError(
            "config key %r for %s must be a JSON object like {\"env\": \"NAME\", "
            "\"default\": ...}, not %s" % (key, UNIT, type(spec).__name__)
        )
    if "default" not in spec:
        raise ConfigError(
            "config key '%s.default' for %s is required (use null to mean 'no default'); "
            "run `emit-config` for a template." % (key, UNIT)
        )
    name = spec.get("env")
    if name:
        value = os.environ.get(name)
        if value is not None:
            return value, True
    return spec["default"], False


# ─────────────────────────────── providers ───────────────────────────────

_PROVIDER_CACHE = {}


def _load_target(spec, what):
    """Resolve a `"module:attr"` string to the attribute it names, or a bare `"module"` to
    the module itself.

    A bare module name is how the config names `httpx`: the original called `httpx.get` /
    `httpx.post` / `httpx.put` on the MODULE, so the provider is the module.
    """
    if not isinstance(spec, str) or not spec:
        raise ConfigError(
            "%s for %s must be a \"module:attr\" string (or a bare \"module\"), not %r"
            % (what, UNIT, spec)
        )
    mod_name, _, attr = spec.partition(":")
    module = sys.modules.get(mod_name)
    if module is None:
        try:
            module = importlib.import_module(mod_name)
        except ImportError as exc:
            raise ConfigError(
                "%s for %s names module %r, which cannot be imported: %s. Install it, or "
                "point the config at something that is importable."
                % (what, UNIT, mod_name, exc)
            ) from exc
    if not attr:
        return module
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ConfigError(
            "%s for %s names %r, but module %r has no attribute %r"
            % (what, UNIT, spec, mod_name, attr)
        ) from exc


def _provider(name):
    """Return the provider the config names under `providers.<name>`, imported on first use.

    This is where `fastmcp` and `httpx` enter. The original imported them at module top
    level, which made the module unimportable without them; naming them in config and
    importing here means this module imports anywhere, the shipped config reproduces the
    original's dependencies exactly, and `selftest` can substitute fakes through the very
    same code path.
    """
    if name not in _PROVIDER_CACHE:
        providers = _setting("providers", "this operation")
        if not isinstance(providers, dict):
            raise ConfigError(
                "config key 'providers' for %s must be a JSON object, not %s"
                % (UNIT, type(providers).__name__)
            )
        if name not in providers:
            raise ConfigError(
                "config object for %s is missing the key 'providers.%s'. Run `emit-config` "
                "for a template." % (UNIT, name)
            )
        _PROVIDER_CACHE[name] = _load_target(providers[name], "config key 'providers.%s'" % name)
    return _PROVIDER_CACHE[name]


# ─────────────────────────── the jazz paths ───────────────────────────

_PATH_CACHE = {}


def _jazz_path(key):
    """Resolve and CACHE one of the jazz paths from its env-backed setting.

    Two behaviors of the original are reproduced here exactly, and both are easy to get wrong:

      * The path is snapshotted ONCE. The original computed `JAZZ_ROOT`/`JAZZ_DEV` at import
        time into globals, so later changes to the environment did not move them. Caching on
        first use is the closest faithful equivalent (divergence 1); `reset_config()` drops
        the snapshot.
      * `~` is expanded ONLY in the config's default, never in an env value. The original
        wrote `Path(os.environ.get("JAZZ_ROOT", Path.home() / "code/workspace/main"))`: the
        built-in default came from `Path.home()` and so was already absolute, while an env
        value was handed to `Path()` VERBATIM — so `JAZZ_ROOT=~/foo` meant a directory
        literally named `~`, not a path under the user's home. The config's `default` stands
        in for the `Path.home()` expression and is therefore tilde-expanded; an env value is
        used raw, as the original used it.
    """
    if key not in _PATH_CACHE:
        value, from_env = _env_backed(key, "the jazz paths")
        if not isinstance(value, str) or not value:
            raise ConfigError(
                "config key '%s' for %s resolved to %r; it must name a path as a string"
                % (key, UNIT, value)
            )
        _PATH_CACHE[key] = Path(value) if from_env else Path(os.path.expanduser(value))
    return _PATH_CACHE[key]


# ─────────────────────────────── the unit itself ───────────────────────────────

def _load_build() -> dict:
    """Return the parsed jazz `build.json`, or `{}` when there is no such file.

    The file is the config's `build_json` path resolved under the configured jazz root
    (`JAZZ_ROOT` by default). A file that exists but does not hold JSON raises, exactly as
    the original's `json.loads` did — a corrupt build file is an error, not an empty dict.
    The `-> dict` annotation is the original's and is kept for the surface; like the
    original, this returns whatever the JSON document holds, so a file containing a JSON
    array yields a list.

    Raises:
        ConfigError: if no config object can be resolved.
        ValueError: if the file exists but is not valid JSON (`json.JSONDecodeError`).
    """
    p = _jazz_path("jazz_root") / _setting("build_json", "_load_build")
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _notes_python() -> str:
    """Interpreter used to launch downstream MCP subprocesses.

    They run under the SAME venv as the coupler — whatever Python is running this — unless
    the config's `python.env` variable (`COUPLER_PYTHON` by default) names another. The
    original read that variable on every call rather than snapshotting it, so this does too
    (divergence 1); the config's `python.default` of `null` means "this interpreter",
    i.e. `sys.executable`.

    (Historically the original hunted a conda env via build.json; conda is gone since
    old_jazz, so that path was dead and is not resurrected here.)

    Raises:
        ConfigError: if no config object can be resolved.
    """
    value, _from_env = _env_backed("python", "_notes_python")
    return sys.executable if value is None else value


def _jazz_client(module: str) -> Client:  # noqa: F821 — see the note below
    """Return a client that launches `python -m <module>` as a downstream MCP service.

    The command is the configured interpreter, then `-m`, then the module — the one-string
    form the original passed to `Client`.

    The `-> Client` annotation is the original's and is part of the surface this ticket
    requires. `Client` is not imported at module level here (that is the whole point — see
    the module docstring), so this annotation is never evaluated: `from __future__ import
    annotations` keeps every annotation a string. The class itself is the config's
    `providers.client`.

    Raises:
        ConfigError: if no config object can be resolved, or `providers.client` is missing
            or cannot be imported.
    """
    python = _notes_python()
    Client = _provider("client")
    return Client(f"{python} -m {module}")


async def notes_db_proxy(tool: str, args: dict = {}) -> str:
    """Forward a tool call to the notes_db_mcp service."""
    async with _jazz_client(_service_module("notes_db", "notes_db_proxy")) as c:
        result = await c.call_tool(tool, args)
        return str(result)


async def z3_proxy(tool: str, args: dict = {}) -> str:
    """Forward a tool call to the z3_mcp service."""
    async with _jazz_client(_service_module("z3", "z3_proxy")) as c:
        result = await c.call_tool(tool, args)
        return str(result)


def _service_module(name, operation):
    """Return the downstream module the config maps `name` onto.

    The original hardcoded `"notes_db_mcp"` and `"z3_mcp"` in two places each: once in a
    proxy tool and once in the `services` map that `_build_app` mounts. Here the `services`
    map is the single source for both, so the proxy and the mount can never disagree.
    """
    services = _services(operation)
    if name not in services:
        raise ConfigError(
            "config object for %s is missing the service %r under 'services', which %s "
            "forwards to. Run `emit-config` for a template." % (UNIT, name, operation)
        )
    return services[name]


def _services(operation):
    """Return the config's service map: display name -> downstream module name.

    Keys starting with `_` are dropped. This repository's registry idiom embeds `_comment`
    keys inside the objects they describe, and every OTHER key here is a service that
    `_build_app` will mount — so without this rule a comment would be mounted as a service.
    """
    services = _setting("services", operation)
    if not isinstance(services, dict):
        raise ConfigError(
            "config key 'services' for %s must be a JSON object mapping a display name to a "
            "module name, not %s" % (UNIT, type(services).__name__)
        )
    services = {n: m for n, m in services.items() if not n.startswith("_")}
    for name, module in services.items():
        if not isinstance(module, str) or not module:
            raise ConfigError(
                "config key 'services.%s' for %s must name a module as a string, not %r"
                % (name, UNIT, module)
            )
    return services


# ── the module-level server (divergence 3: lazily built, not built at import) ──

_SERVER = None


def _server():
    """Build (once) the module-level MCP server the original created at import time.

    The original's `mcp = FastMCP("coupler")` plus `@mcp.tool()` on the two proxies produced
    a server named by the config's `server_name` carrying exactly `notes_db_proxy` and
    `z3_proxy`. This produces the same thing on first access; see divergence 3.
    """
    global _SERVER
    if _SERVER is None:
        FastMCP = _provider("server")
        server = FastMCP(_setting("server_name", "the module-level server"))
        server.tool()(notes_db_proxy)
        server.tool()(z3_proxy)
        _SERVER = server
    return _SERVER


def __getattr__(name):
    """Provide the module-level `mcp` server lazily (PEP 562).

    The original exposed `mcp` as a module attribute built at import. Building it at import
    is what this rewrite exists to avoid, so it is built on first ATTRIBUTE ACCESS instead:
    `coupler.__main__.mcp` is the same server with the same two tools. Without a config (or
    without a working fastmcp) touching it raises ConfigError rather than yielding a
    half-configured server.
    """
    if name == "mcp":
        return _server()
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


# ─────────────────── mount jazz services as proper proxies ───────────────────

def _build_app():
    """Build the coupler app: the proxied jazz services, why5, and the UI bridge.

    Prints the original's diagnostic banner to stderr as it goes, and returns the app.
    Everything it mounts is driven by the config object; nothing is hardcoded. The mount,
    why5 and UI sections each preserve the original's failure behavior exactly — see the
    comments at each.

    Raises:
        ConfigError: if no config object can be resolved, or a key/provider it needs is
            missing or cannot be imported.
    """
    python = _notes_python()
    build = _load_build()
    version = build.get("version", "unknown")

    print(f"  coupler starting", file=sys.stderr)
    print(f"  jazz version : {version}", file=sys.stderr)
    print(f"  notes python : {python}", file=sys.stderr)

    FastMCP = _provider("server")
    app = FastMCP(_setting("server_name", "_build_app"))

    # mount each jazz service — tools appear natively in Claude
    services = _services("_build_app")

    # Resolved OUTSIDE the per-service try, because the original's `from fastmcp.server
    # import create_proxy` sat outside its try too: if the proxy factory is unavailable,
    # _build_app fails rather than quietly mounting nothing.
    create_proxy = _provider("create_proxy")
    Client = _provider("client")
    StdioTransport = _provider("stdio_transport")

    for name, module in services.items():
        # The original gated each mount on the interpreter path existing, and skipped
        # SILENTLY when it did not — no "mounted" line and no warning. Preserved.
        if Path(python).exists():
            try:
                proxy = create_proxy(
                    Client(StdioTransport(command=python, args=["-m", module]))
                )
                app.mount(proxy, namespace=name)
                print(f"  mounted      : {name} ({module})", file=sys.stderr)
            except Exception as e:
                print(f"  [warn] could not mount {name}: {e}", file=sys.stderr)

    # ── why5 (from jazz dev tree) ─────────────────────────────────────────────
    # The sys.path insert happens BEFORE the try and is not undone, exactly as in the
    # original: the path is inserted even when the import below then fails.
    why5 = _setting("why5", "_build_app")
    if not isinstance(why5, dict):
        raise ConfigError(
            "config key 'why5' for %s must be a JSON object, not %s"
            % (UNIT, type(why5).__name__)
        )
    sys.path.insert(0, str(_jazz_path("jazz_dev") / _require(why5, "path", "_build_app")))
    try:
        why5_module = importlib.import_module(_require(why5, "module", "_build_app"))
        # Reproduces `from agent.why5 import Why5, from_ci_failure, from_commit_failure`.
        # `from_commit_failure` is imported and never used — in the original too — and that
        # is behavior, not dead weight: if the why5 module lacks it, the import fails and
        # NOTHING why5-related mounts. Dropping it would mount why5 where the original did
        # not.
        Why5 = _from_import(why5_module, "Why5")
        from_ci_failure = _from_import(why5_module, "from_ci_failure")
        _from_import(why5_module, "from_commit_failure")
        _why5_sessions: dict = {}

        @app.tool()
        def why5_new(session_id: str, trigger: str = "") -> str:
            """Start a new 5-why root cause analysis session."""
            _why5_sessions[session_id] = Why5(session_id=session_id, trigger=trigger)
            return f"why5 session '{session_id}' started"

        @app.tool()
        def why5_fact(session_id: str, name: str, value: bool) -> str:
            """Assert a known observable fact into a why5 session."""
            # Indexes the session dict directly, so an unknown session_id raises KeyError.
            # why5_check returns an error string for the same mistake. That asymmetry is the
            # original's and is preserved rather than tidied.
            _why5_sessions[session_id].fact(name, value)
            return f"fact '{name}' = {value}"

        @app.tool()
        def why5_link(session_id: str, label: str, cause: str, because: str) -> str:
            """Add a causal link: if `because` is true then `cause` must be true."""
            _why5_sessions[session_id].link(label, cause=cause, because=because)
            return f"link [{label}] {because} → {cause}"

        @app.tool()
        def why5_check(session_id: str, save: bool = False) -> str:
            """Verify the causal chain with Z3. Optionally save to notes_db."""
            w = _why5_sessions.get(session_id)
            if not w:
                return f"error: session '{session_id}' not found"
            result = w.check()
            if save:
                w.save()
            return json.dumps(result, indent=2)

        @app.tool()
        def why5_from_ci_failure(session_id: str, branch: str, sha: str,
                                 pytest_output: str, save: bool = False) -> str:
            """Build and verify a why5 chain from CI pytest output."""
            w = from_ci_failure(session_id, branch=branch, pre_sha=sha,
                                pytest_output=pytest_output)
            _why5_sessions[session_id] = w
            result = w.check()
            if save:
                w.save()
            return json.dumps(result, indent=2)

        print(f"  mounted      : why5", file=sys.stderr)
    except Exception as e:
        print(f"  [warn] why5 not available: {e}", file=sys.stderr)

    # ── UI bridge (http provider, always direct) ─────────────────────────────
    ui = _setting("ui", "_build_app")
    if not isinstance(ui, dict):
        raise ConfigError(
            "config key 'ui' for %s must be a JSON object, not %s" % (UNIT, type(ui).__name__)
        )
    UI_BASE, _ = _env_backed_in("ui", ui, "base", "_build_app")
    UI_TIMEOUT = _require(ui, "timeout", "_build_app")
    http = _provider("http")

    def _ui_get(path, **params):
        r = http.get(f"{UI_BASE}{path}", params=params, timeout=UI_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def _ui_post(path, body):
        r = http.post(f"{UI_BASE}{path}", json=body, timeout=UI_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def _ui_put(path, body):
        r = http.put(f"{UI_BASE}{path}", json=body, timeout=UI_TIMEOUT)
        r.raise_for_status()
        return r.json()

    @app.tool()
    def ui_set_page(config: dict) -> str:
        """Push a page config to the browser UI."""
        name = config.get("name")
        if not name:
            return "error: config must have a 'name' field"
        try:
            _ui_post(f"/page/{name}", config)
            return f"page '{name}' registered"
        except Exception as e:
            return f"error: {e}"

    @app.tool()
    def ui_get_state(page: str) -> str:
        """Get the current value of every control on a UI page."""
        try:
            return json.dumps(_ui_get(f"/state/{page}"), indent=2)
        except Exception as e:
            return f"error: {e}"

    @app.tool()
    def ui_set_value(page: str, name: str, value: str) -> str:
        """Set a control value on a UI page."""
        # Delegates to the same `str.lower()`, `int()` and `float()` the original used, in
        # the same order, so every quirk of the original's coercion survives unchanged:
        # "TRUE" is True, "1_0" is the int 10, "1e3" is the float 1000.0, "inf" is a float
        # infinity, and anything all three reject stays the string it was.
        parsed: object = value
        if value.lower() == "true":
            parsed = True
        elif value.lower() == "false":
            parsed = False
        else:
            try:
                parsed = int(value)
            except ValueError:
                try:
                    parsed = float(value)
                except ValueError:
                    pass
        try:
            _ui_put(f"/state/{page}/{name}", {"value": parsed})
            return f"set {page}.{name} = {parsed!r}"
        except Exception as e:
            return f"error: {e}"

    @app.tool()
    def ui_list_pages() -> str:
        """List all registered UI pages."""
        try:
            pages = _ui_get("/pages")
            return json.dumps(pages, indent=2) if pages else "no pages registered"
        except Exception as e:
            return f"error: {e}"

    @app.tool()
    def ui_add_message(page: str, control: str, role: str, text: str) -> str:
        """Append a message to a chatbox control on a UI page."""
        try:
            _ui_post(f"/message/{page}/{control}", {"role": role, "text": text})
            return f"message added to {page}.{control}"
        except Exception as e:
            return f"error: {e}"

    @app.tool()
    def ui_get_log(limit: int = 20) -> str:
        """Get recent control change events from the browser."""
        try:
            log = _ui_get("/log", limit=limit)
            return json.dumps(log, indent=2) if log else "no changes yet"
        except Exception as e:
            return f"error: {e}"

    # Divergence 2: the original printed a literal "8142" regardless of the base actually in
    # force. The port is derived from the configured base, so the shipped config prints the
    # original's exact line and any other base prints the truth.
    print(f"  mounted      : ui (port {_ui_port(UI_BASE)})", file=sys.stderr)
    return app


def _from_import(module, name):
    """Get `name` off `module`, raising ImportError — not AttributeError — when it is absent.

    `from X import a, b, c` raises ImportError for a missing name, and `_build_app`'s why5
    block reports whatever the import raises in its `[warn] why5 not available:` line. Going
    through getattr would raise AttributeError and change that line, so the ImportError is
    reconstructed here with the phrasing the `from ... import` form uses.
    """
    try:
        return getattr(module, name)
    except AttributeError:
        raise ImportError(
            "cannot import name %r from %r (%s)"
            % (name, module.__name__, getattr(module, "__file__", "unknown location"))
        ) from None


def _env_backed_in(section_key, section, key, operation):
    """Resolve an env-backed setting nested inside a config section (e.g. `ui.base`)."""
    spec = _require(section, key, operation)
    if not isinstance(spec, dict):
        raise ConfigError(
            "config key '%s.%s' for %s must be a JSON object like {\"env\": \"NAME\", "
            "\"default\": ...}, not %s" % (section_key, key, UNIT, type(spec).__name__)
        )
    if "default" not in spec:
        raise ConfigError(
            "config key '%s.%s.default' for %s is required; run `emit-config` for a template."
            % (section_key, key, UNIT)
        )
    name = spec.get("env")
    if name:
        value = os.environ.get(name)
        if value is not None:
            return value, True
    return spec["default"], False


def _ui_port(base):
    """Describe the UI port for the banner: the base's port, else its host.

    See divergence 2. `urlsplit` raises ValueError on a malformed port, which must not take
    the whole app down for the sake of a log line — the banner falls back to the base itself.
    """
    try:
        split = urlsplit(base)
        if split.port is not None:
            return split.port
        return split.netloc or base
    except ValueError:
        return base


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do every operation throws. The values below are the
    ones the ORIGINAL hardcoded, so a config built from this template makes the rewrite
    behave exactly as the original did.
    """
    return {
        "server_name": "coupler",
        "jazz_root": {"env": "JAZZ_ROOT", "default": "~/code/workspace/main"},
        "jazz_dev": {"env": "JAZZ_DEV", "default": "~/code/jazz"},
        "build_json": "conf/env/build.json",
        "python": {"env": "COUPLER_PYTHON", "default": None},
        "services": {"notes_db": "notes_db_mcp", "z3": "z3_mcp"},
        "why5": {"path": "jazz", "module": "agent.why5"},
        "ui": {
            "base": {"env": "JSON_CONTROLS_URL", "default": "http://127.0.0.1:8142"},
            "timeout": 5.0,
        },
        "providers": {
            "server": "fastmcp:FastMCP",
            "client": "fastmcp:Client",
            "stdio_transport": "fastmcp.client.transports:StdioTransport",
            "create_proxy": "fastmcp.server:create_proxy",
            "http": "httpx",
        },
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ═══════════════════════════════ the selftest ═══════════════════════════════
#
# The fakes below stand in for FastMCP and httpx. They are reached the SAME way the real
# dependencies are — the config names them as providers — so the selftest exercises the real
# code path rather than a parallel one. #403 captured no behavioral exemplars (criteria_miner
# mines only self-contained pure functions, and every callable here touches the world), so
# per the ticket the equivalence cases below were written BY HAND from the original's source,
# reading the original as the oracle.

class _FakeTool:
    """One registered tool: the function, reachable by name."""

    def __init__(self, fn):
        self.fn = fn
        self.__name__ = getattr(fn, "__name__", "tool")


class _FakeServer:
    """A stand-in for FastMCP: records the tools registered and the proxies mounted."""

    def __init__(self, name):
        self.name = name
        self.tools = {}
        self.mounts = []
        self.ran = False

    def tool(self, *_a, **_k):
        def register(fn):
            self.tools[fn.__name__] = _FakeTool(fn)
            return fn
        return register

    def mount(self, proxy, namespace=None):
        self.mounts.append((namespace, proxy))

    def run(self):
        self.ran = True

    def call(self, name, *a, **k):
        return self.tools[name].fn(*a, **k)


class _FakeStdioTransport:
    def __init__(self, command=None, args=None):
        self.command = command
        self.args = args


class _FakeClient:
    """A stand-in for fastmcp's Client: records how it was built and what was called.

    Doubles as its own async context manager, as the real Client does.
    """

    built = []
    calls = []

    def __init__(self, target):
        self.target = target
        self.entered = False
        self.exited = False
        _FakeClient.built.append(target)

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *_exc):
        self.exited = True
        return False

    async def call_tool(self, tool, args):
        _FakeClient.calls.append((self.target, tool, args))
        return {"tool": tool, "args": args}


def _fake_create_proxy(client):
    return ("proxy", client)


class _FakeResponse:
    def __init__(self, payload, raises=None):
        self.payload = payload
        self.raises = raises

    def raise_for_status(self):
        if self.raises is not None:
            raise self.raises

    def json(self):
        return self.payload


class _FakeHttp:
    """A stand-in for the httpx MODULE: module-level get/post/put, as the original called."""

    requests = []
    payload = {}
    raises = None

    @classmethod
    def get(cls, url, params=None, timeout=None):
        cls.requests.append(("get", url, params, timeout))
        return _FakeResponse(cls.payload, cls.raises)

    @classmethod
    def post(cls, url, json=None, timeout=None):
        cls.requests.append(("post", url, json, timeout))
        return _FakeResponse(cls.payload, cls.raises)

    @classmethod
    def put(cls, url, json=None, timeout=None):
        cls.requests.append(("put", url, json, timeout))
        return _FakeResponse(cls.payload, cls.raises)

    @classmethod
    def reset(cls, payload=None, raises=None):
        cls.requests = []
        cls.payload = {} if payload is None else payload
        cls.raises = raises


class _FakeWhy5Session:
    def __init__(self, session_id=None, trigger=None):
        self.session_id = session_id
        self.trigger = trigger
        self.facts = []
        self.links = []
        self.saved = False

    def fact(self, name, value):
        self.facts.append((name, value))

    def link(self, label, cause=None, because=None):
        self.links.append((label, cause, because))

    def check(self):
        return {"session": self.session_id, "ok": True}

    def save(self):
        self.saved = True


def _fake_from_ci_failure(session_id, branch=None, pre_sha=None, pytest_output=None):
    session = _FakeWhy5Session(session_id=session_id, trigger="ci")
    session.ci = (branch, pre_sha, pytest_output)
    return session


def _fake_from_commit_failure(*_a, **_k):  # imported by _build_app, never called — as in the original
    raise AssertionError("from_commit_failure is imported for its import side effect only")


def _install_fake_why5(name, *, complete=True):
    """Register a fake why5 module in sys.modules and return its name.

    `complete=False` omits `from_commit_failure`, which is how the selftest proves that the
    unused import is load-bearing: without it the why5 mount must fail exactly as the
    original's `from ... import` would.
    """
    module = type(sys)(name)
    module.Why5 = _FakeWhy5Session
    module.from_ci_failure = _fake_from_ci_failure
    if complete:
        module.from_commit_failure = _fake_from_commit_failure
    sys.modules[name] = module
    return name


#: THE CALLABLE SURFACE, quoted verbatim from ticket #403 — the six signatures codebean's
#: `lower_node` (#183) produced from the ORIGINAL's AST, in the ticket's own order. Acceptance
#: item (b) is that this rewrite "presents the callable surface above, so existing callers
#: keep working", and `_lower_surface` below lowers THIS file the same way to prove it.
SURFACE = [
    "_load_build() -> dict",
    "_notes_python() -> str",
    "_jazz_client(module: str) -> Client",
    "async notes_db_proxy(tool: str, args: dict={}) -> str",
    "async z3_proxy(tool: str, args: dict={}) -> str",
    "_build_app()",
]


def _lower_surface(path):
    """Lower every TOP-LEVEL function in `path` to the ticket's signature form.

    Mirrors codebean's `lower_node` (#183) closely enough to be compared against the
    ticket's own output: an `async ` prefix for a coroutine, `name(params) -> returns`, each
    parameter as `name: annotation=default` with annotations and defaults unparsed straight
    from the AST, and no ` -> ` at all when the function has no return annotation.

    Only module-level defs are lowered — the tools nested inside `_build_app` are that
    function's internals, not this module's surface.
    """
    with open(path, "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read())

    lowered = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = []
        args = node.args
        # Defaults bind to the TAIL of the positional parameters, so line them up from the
        # right; a shorter defaults list simply leaves the leading parameters undefaulted.
        positional = args.posonlyargs + args.args
        padding = [None] * (len(positional) - len(args.defaults))
        for arg, default in zip(positional, padding + list(args.defaults)):
            text = arg.arg
            if arg.annotation is not None:
                text += ": " + ast.unparse(arg.annotation)
            if default is not None:
                text += "=" + ast.unparse(default)
            params.append(text)
        signature = "%s(%s)" % (node.name, ", ".join(params))
        if node.returns is not None:
            signature += " -> " + ast.unparse(node.returns)
        if isinstance(node, ast.AsyncFunctionDef):
            signature = "async " + signature
        lowered[node.name] = signature
    return lowered


def _fake_config(**overrides):
    """The config template, rewired onto this module's fakes."""
    config = config_template()
    config["providers"] = {
        "server": "%s:_FakeServer" % __name__,
        "client": "%s:_FakeClient" % __name__,
        "stdio_transport": "%s:_FakeStdioTransport" % __name__,
        "create_proxy": "%s:_fake_create_proxy" % __name__,
        "http": "%s:_FakeHttp" % __name__,
    }
    config.update(overrides)
    return config


def selftest(stream=None):
    """Prove this rewrite against ticket #403's acceptance items (a), (b) and (d).

    Builds its own config objects in memory and its own temp trees, so it needs no registry,
    needs neither fastmcp nor httpx, writes no files outside a temp dir it removes, and
    leaves no configuration behind. Returns the number of failures.

    Checks, in order:
      1. the config gate — resolution throws ConfigError where no config can be seen;
      2. every callable refuses to work, rather than guessing, with an unresolvable config;
      3. `_load_build()` — missing file, present file, non-dict document, corrupt JSON, and
         the JAZZ_ROOT override, including the tilde asymmetry;
      4. `_notes_python()` — the default and the COUPLER_PYTHON override, read per call;
      5. `_jazz_client()` — the exact `"<python> -m <module>"` command string;
      6. `notes_db_proxy` / `z3_proxy` — the right service, `str(result)`, the context
         manager, and that the shared mutable default is never mutated;
      7. `_build_app()` — the banner, the mounts, the interpreter gate, the why5 block
         (including the load-bearing unused import), and the UI bridge tool by tool;
      8. the callable surface — every name, parameter and default the ticket lists.
    """
    out = stream or sys.stdout
    failures = []
    checks = [0]

    def check(ok, label):
        checks[0] += 1
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    saved = configure(None)
    saved_env = {k: os.environ.get(k) for k in
                 (CONFIG_ENV, "JAZZ_ROOT", "JAZZ_DEV", "COUPLER_PYTHON", "JSON_CONTROLS_URL")}
    saved_path = list(sys.path)
    for key in saved_env:
        os.environ.pop(key, None)
    try:
        reset_config()

        with tempfile.TemporaryDirectory() as isolated:
            # ── 1. the config gate ───────────────────────────────────────────
            print("[1] config gate — a tool that cannot see its config throws", file=out)
            if find_registry(isolated) is not None:
                print("  n/a   a %s exists above the temp dir %s, so 'no registry anywhere' "
                      "cannot be staged here; check [2] proves the gate instead"
                      % (REGISTRY_NAME, isolated), file=out)
            else:
                try:
                    load_config(start=isolated)
                    check(False, "load_config() where no %s exists raises ConfigError"
                          % REGISTRY_NAME)
                except ConfigError:
                    check(True, "load_config() where no %s exists raises ConfigError"
                          % REGISTRY_NAME)

            # ── 2. every callable refuses to work without config ─────────────
            #    Staged by pointing FORGE2_CONFIG at a file that does not exist: the env
            #    source outranks the registry walk-up, so this proves the gate the same way
            #    whether or not a registry happens to be installed near this module — and
            #    this package SHIPS one, so a bare call here would otherwise succeed. Check
            #    [1] cannot do that on its own.
            print("[2] every callable refuses to work when its config cannot be resolved",
                  file=out)
            os.environ[CONFIG_ENV] = os.path.join(isolated, "no-such-config.json")
            reset_config()
            gated = [
                ("_load_build()", lambda: _load_build()),
                ("_notes_python()", lambda: _notes_python()),
                ("_jazz_client('m')", lambda: _jazz_client("m")),
                ("notes_db_proxy('t')", lambda: asyncio.run(notes_db_proxy("t"))),
                ("z3_proxy('t')", lambda: asyncio.run(z3_proxy("t"))),
                ("_build_app()", lambda: _build_app()),
                ("mcp (module attribute)", lambda: __getattr__("mcp")),
            ]
            for label, thunk in gated:
                got = _attempt(thunk)
                check(isinstance(got, _Raised) and got.type is ConfigError,
                      "%s raises ConfigError — no default is guessed%s"
                      % (label, "" if isinstance(got, _Raised) and got.type is ConfigError
                         else " (got %r)" % (got,)))
            os.environ.pop(CONFIG_ENV, None)
            reset_config()

            # ── 3. _load_build() ─────────────────────────────────────────────
            print("[3] _load_build()", file=out)
            root = os.path.join(isolated, "jazz_root")
            os.makedirs(os.path.join(root, "conf", "env"))
            build_path = os.path.join(root, "conf", "env", "build.json")
            cfg = _fake_config(jazz_root={"env": "JAZZ_ROOT", "default": root})

            with using_config(cfg):
                check(_same(_load_build(), {}),
                      "no build.json -> {} (the original's `if p.exists()` else branch)")

                with open(build_path, "w", encoding="utf-8") as h:
                    json.dump({"version": "9.9.9", "extra": [1, 2]}, h)
                reset_paths()
                check(_same(_load_build(), {"version": "9.9.9", "extra": [1, 2]}),
                      "build.json is parsed and returned verbatim")

                with open(build_path, "w", encoding="utf-8") as h:
                    h.write("[1, 2]")
                check(_same(_load_build(), [1, 2]),
                      "a JSON array comes back as a list — the `-> dict` annotation is the "
                      "original's claim, not a coercion the original performed")

                with open(build_path, "w", encoding="utf-8") as h:
                    h.write("{not json")
                got = _attempt(_load_build)
                check(isinstance(got, _Raised) and issubclass(got.type, ValueError),
                      "a corrupt build.json raises (json.JSONDecodeError, a ValueError) "
                      "rather than being swallowed into {}")

            # the JAZZ_ROOT override, and the tilde asymmetry the original had
            print("[3b] the jazz-path env override, and its tilde asymmetry", file=out)
            other = os.path.join(isolated, "elsewhere")
            os.makedirs(os.path.join(other, "conf", "env"))
            with open(os.path.join(other, "conf", "env", "build.json"), "w",
                      encoding="utf-8") as h:
                json.dump({"version": "from-env"}, h)
            os.environ["JAZZ_ROOT"] = other
            with using_config(cfg):
                reset_paths()
                check(_same(_load_build(), {"version": "from-env"}),
                      "$JAZZ_ROOT overrides the config default (the original's env override "
                      "still works)")
            os.environ["JAZZ_ROOT"] = "~/foo"
            with using_config(cfg):
                reset_paths()
                check(str(_jazz_path("jazz_root")) == "~/foo",
                      "JAZZ_ROOT=~/foo stays a LITERAL '~' path — the original passed the env "
                      "value to Path() with no expanduser")
            os.environ.pop("JAZZ_ROOT", None)
            with using_config(_fake_config(jazz_root={"env": "JAZZ_ROOT",
                                                      "default": "~/code/workspace/main"})):
                reset_paths()
                check(str(_jazz_path("jazz_root"))
                      == str(Path.home() / "code/workspace/main"),
                      "the config DEFAULT is home-expanded — it stands in for the original's "
                      "`Path.home() / 'code/workspace/main'`")

            # ── 4. _notes_python() ───────────────────────────────────────────
            print("[4] _notes_python()", file=out)
            with using_config(cfg):
                check(_same(_notes_python(), sys.executable),
                      "defaults to sys.executable — downstreams run under the coupler's own "
                      "venv")
                os.environ["COUPLER_PYTHON"] = "/opt/other/python3"
                check(_same(_notes_python(), "/opt/other/python3"),
                      "$COUPLER_PYTHON overrides it")
                check(_same(_notes_python(), "/opt/other/python3"),
                      "the override is read on EVERY call, not snapshotted (the original read "
                      "the env inside the function)")
                os.environ.pop("COUPLER_PYTHON", None)
                check(_same(_notes_python(), sys.executable),
                      "unsetting $COUPLER_PYTHON mid-process reverts it — proof the read is "
                      "per-call")

            # ── 5. _jazz_client() ────────────────────────────────────────────
            print("[5] _jazz_client()", file=out)
            with using_config(cfg):
                _FakeClient.built = []
                os.environ["COUPLER_PYTHON"] = "/opt/py"
                client = _jazz_client("notes_db_mcp")
                check(isinstance(client, _FakeClient)
                      and client.target == "/opt/py -m notes_db_mcp",
                      "builds Client('<python> -m <module>') — the exact one-string command "
                      "the original passed (got %r)"
                      % (getattr(client, "target", client),))
                os.environ.pop("COUPLER_PYTHON", None)

            # ── 6. the two proxies ───────────────────────────────────────────
            print("[6] notes_db_proxy / z3_proxy", file=out)
            with using_config(cfg):
                for fn, service in ((notes_db_proxy, "notes_db_mcp"), (z3_proxy, "z3_mcp")):
                    _FakeClient.built = []
                    _FakeClient.calls = []
                    result = asyncio.run(fn("some_tool", {"a": 1}))
                    ok = (_FakeClient.built == ["%s -m %s" % (sys.executable, service)]
                          and _FakeClient.calls
                          == [("%s -m %s" % (sys.executable, service), "some_tool", {"a": 1})])
                    check(ok, "%s forwards to %s and calls the named tool with its args"
                          % (fn.__name__, service))
                    check(_same(result, str({"tool": "some_tool", "args": {"a": 1}})),
                          "%s returns str(result) — the original stringified whatever the "
                          "service returned" % fn.__name__)

                # `async with` is the original's shape: the client must be entered AND exited.
                _FakeClient.built = []
                holder = []
                original_aenter = _FakeClient.__aenter__

                async def _record_aenter(self):
                    holder.append(self)
                    return await original_aenter(self)

                _FakeClient.__aenter__ = _record_aenter
                try:
                    asyncio.run(notes_db_proxy("t"))
                finally:
                    _FakeClient.__aenter__ = original_aenter
                check(len(holder) == 1 and holder[0].entered and holder[0].exited,
                      "the client is opened and closed via `async with` (no leaked session)")

                # The mutable {} default is the ticket's surface. Prove it is inert.
                _FakeClient.calls = []
                asyncio.run(notes_db_proxy("t"))
                default_after_first = notes_db_proxy.__defaults__[0]
                asyncio.run(z3_proxy("t"))
                check(_same(default_after_first, {})
                      and _same(notes_db_proxy.__defaults__[0], {})
                      and _same(z3_proxy.__defaults__[0], {}),
                      "the shared mutable {} default is never mutated — the surface is kept "
                      "without the bug that shape usually implies")
                check(_FakeClient.calls[0][2] == {} and _FakeClient.calls[1][2] == {},
                      "an omitted `args` forwards {} to the service")

            # ── 7. _build_app() ──────────────────────────────────────────────
            print("[7] _build_app() — banner, mounts, why5, UI bridge", file=out)
            why5_name = _install_fake_why5("_selftest_why5")
            dev = os.path.join(isolated, "jazz_dev")
            os.makedirs(os.path.join(dev, "jazz"), exist_ok=True)
            app_cfg = _fake_config(
                jazz_root={"env": "JAZZ_ROOT", "default": root},
                jazz_dev={"env": "JAZZ_DEV", "default": dev},
                why5={"path": "jazz", "module": why5_name},
            )
            with open(build_path, "w", encoding="utf-8") as h:
                json.dump({"version": "2.4.0"}, h)

            _FakeHttp.reset()
            sys.path[:] = saved_path
            with using_config(app_cfg):
                reset_paths()
                banner = io.StringIO()
                with contextlib.redirect_stderr(banner):
                    app = _build_app()
                lines = banner.getvalue().splitlines()

                check(lines[:3] == ["  coupler starting",
                                    "  jazz version : 2.4.0",
                                    "  notes python : %s" % sys.executable],
                      "the banner's first three lines are byte-identical to the original's "
                      "(version read from build.json)")
                check(isinstance(app, _FakeServer) and app.name == "coupler",
                      "the app is the configured server, named 'coupler'")
                check("  mounted      : notes_db (notes_db_mcp)" in lines
                      and "  mounted      : z3 (z3_mcp)" in lines,
                      "both jazz services report as mounted, in the original's exact format")
                check([n for n, _ in app.mounts] == ["notes_db", "z3"],
                      "both proxies are mounted under their namespaces, in config order")
                check("  mounted      : why5" in lines, "why5 reports as mounted")
                check("  mounted      : ui (port 8142)" in lines,
                      "the UI line is byte-identical to the original's, port derived from the "
                      "configured base")
                check(str(Path(dev) / "jazz") == sys.path[0],
                      "the configured why5 path is inserted at the FRONT of sys.path (the "
                      "original's side effect)")

                expected_tools = {
                    "why5_new", "why5_fact", "why5_link", "why5_check", "why5_from_ci_failure",
                    "ui_set_page", "ui_get_state", "ui_set_value", "ui_list_pages",
                    "ui_add_message", "ui_get_log",
                }
                check(set(app.tools) == expected_tools,
                      "exactly the original's 11 tools are registered%s"
                      % ("" if set(app.tools) == expected_tools
                         else " — got %s" % sorted(app.tools)))

                # the mount is gated on the interpreter path EXISTING, and skips silently
                os.environ["COUPLER_PYTHON"] = os.path.join(isolated, "no-such-python")
                quiet = io.StringIO()
                with contextlib.redirect_stderr(quiet):
                    gated_app = _build_app()
                os.environ.pop("COUPLER_PYTHON", None)
                check(gated_app.mounts == []
                      and "mounted      : notes_db" not in quiet.getvalue()
                      and "[warn] could not mount" not in quiet.getvalue(),
                      "a non-existent interpreter skips every mount SILENTLY — no mount line "
                      "and no warning, exactly as the original's `if Path(python).exists()`")

                # a mount that raises is warned about, and does not stop the others
                boom = _fake_config(
                    jazz_root={"env": "JAZZ_ROOT", "default": root},
                    jazz_dev={"env": "JAZZ_DEV", "default": dev},
                    why5={"path": "jazz", "module": why5_name},
                )
                boom["providers"]["create_proxy"] = "%s:_exploding_create_proxy" % __name__
                with using_config(boom):
                    reset_paths()
                    warned = io.StringIO()
                    with contextlib.redirect_stderr(warned):
                        partial = _build_app()
                    text = warned.getvalue()
                    check("  [warn] could not mount notes_db: kaboom" in text
                          and "  [warn] could not mount z3: kaboom" in text
                          and partial.mounts == []
                          and "  mounted      : ui (port 8142)" in text,
                          "a failing mount warns per service and the app still builds — the "
                          "original caught per-service and carried on")

            # why5: the unused import is load-bearing
            print("[7b] why5 — the unused import is load-bearing", file=out)
            partial_name = _install_fake_why5("_selftest_why5_partial", complete=False)
            with using_config(_fake_config(
                    jazz_root={"env": "JAZZ_ROOT", "default": root},
                    jazz_dev={"env": "JAZZ_DEV", "default": dev},
                    why5={"path": "jazz", "module": partial_name})):
                reset_paths()
                warned = io.StringIO()
                with contextlib.redirect_stderr(warned):
                    app_no_why5 = _build_app()
                text = warned.getvalue()
                check("[warn] why5 not available: cannot import name 'from_commit_failure'"
                      in text,
                      "a why5 module missing the UNUSED `from_commit_failure` mounts NO why5 "
                      "tools and warns — dropping that import would mount why5 where the "
                      "original did not")
                check(not [t for t in app_no_why5.tools if t.startswith("why5_")],
                      "no why5 tool is registered when the why5 import fails")
                check("  mounted      : ui (port 8142)" in text,
                      "the UI bridge still mounts after why5 fails — the original's warn-and-"
                      "continue")

            with using_config(_fake_config(
                    jazz_root={"env": "JAZZ_ROOT", "default": root},
                    jazz_dev={"env": "JAZZ_DEV", "default": dev},
                    why5={"path": "jazz", "module": "no_such_why5_module_xyz"})):
                reset_paths()
                warned = io.StringIO()
                with contextlib.redirect_stderr(warned):
                    _build_app()
                check("[warn] why5 not available:" in warned.getvalue(),
                      "an unimportable why5 module warns rather than raising")

            # ── the why5 tools ───────────────────────────────────────────────
            print("[7c] the why5 tools", file=out)
            with using_config(app_cfg):
                reset_paths()
                with contextlib.redirect_stderr(io.StringIO()):
                    app = _build_app()
                check(_same(_call(app, "why5_new", "s1", "ci broke"),
                            "why5 session 's1' started"), "why5_new returns its exact string")
                check(_same(_call(app, "why5_fact", "s1", "tests_ran", True),
                            "fact 'tests_ran' = True"), "why5_fact returns its exact string")
                # why5_link(session_id, label, cause, because) -> "link [label] because → cause"
                check(_same(_call(app, "why5_link", "s1", "L1", "a", "b"), "link [L1] b → a"),
                      "why5_link returns its exact string, arrow and all")
                check(_same(_call(app, "why5_check", "s1"),
                            json.dumps({"session": "s1", "ok": True}, indent=2)),
                      "why5_check returns the check result as indented JSON")
                check(_same(_call(app, "why5_check", "nope"),
                            "error: session 'nope' not found"),
                      "why5_check returns an error STRING for an unknown session")
                got = _call(app, "why5_fact", "nope", "x", True)
                check(isinstance(got, _Raised) and got.type is KeyError,
                      "why5_fact RAISES KeyError for an unknown session — the original's "
                      "asymmetry with why5_check, preserved rather than tidied")
                out_json = _call(app, "why5_from_ci_failure", "s2", "main", "abc123", "F")
                check(_same(out_json, json.dumps({"session": "s2", "ok": True}, indent=2)),
                      "why5_from_ci_failure builds, stores and checks the session")
                check(_same(_call(app, "why5_check", "s2"),
                            json.dumps({"session": "s2", "ok": True}, indent=2)),
                      "why5_from_ci_failure's session is retrievable by why5_check — it was "
                      "stored under its id")
                # the session dict is shared across the tools, and keyed by session_id
                check(_same(_call(app, "why5_new", "s1", ""), "why5 session 's1' started"),
                      "why5_new on an existing id replaces the session rather than erroring")

            # ── the UI bridge ────────────────────────────────────────────────
            print("[7d] the UI bridge", file=out)
            with using_config(app_cfg):
                reset_paths()
                with contextlib.redirect_stderr(io.StringIO()):
                    app = _build_app()

                _FakeHttp.reset(payload={"ok": True})
                check(_same(_call(app, "ui_set_page", {"name": "p1", "x": 1}),
                            "page 'p1' registered"), "ui_set_page returns its exact string")
                check(_FakeHttp.requests == [("post", "http://127.0.0.1:8142/page/p1",
                                              {"name": "p1", "x": 1}, 5.0)],
                      "ui_set_page POSTs the whole config to /page/<name> at the configured "
                      "base and timeout")
                _FakeHttp.reset(payload={"ok": True})
                check(_same(_call(app, "ui_set_page", {"x": 1}),
                            "error: config must have a 'name' field"),
                      "ui_set_page rejects a config with no name")
                check(_FakeHttp.requests == [],
                      "a nameless config is rejected WITHOUT touching the UI — the original "
                      "checked the name before posting")
                check(_same(_call(app, "ui_set_page", {"name": "", "x": 1}),
                            "error: config must have a 'name' field"),
                      "an EMPTY name is rejected too — the original tested falsiness, not "
                      "presence")

                _FakeHttp.reset(payload={"a": 1})
                check(_same(_call(app, "ui_get_state", "p1"),
                            json.dumps({"a": 1}, indent=2)),
                      "ui_get_state returns the state as indented JSON")
                check(_FakeHttp.requests == [("get", "http://127.0.0.1:8142/state/p1",
                                              {}, 5.0)],
                      "ui_get_state GETs /state/<page> with no params")

                # the value-coercion table — the original's own int()/float() quirks
                table = [("true", True), ("TRUE", True), ("True", True),
                         ("false", False), ("False", False),
                         ("10", 10), (" 10 ", 10), ("1_0", 10), ("-3", -3),
                         ("1.5", 1.5), ("1e3", 1000.0), ("abc", "abc"),
                         ("0x10", "0x10"), ("", "")]
                bad = []
                for raw, want in table:
                    _FakeHttp.reset(payload={"ok": True})
                    got = _call(app, "ui_set_value", "p", "c", raw)
                    # The PUT body is where the coerced value actually goes; if the tool
                    # raised, no request was made and `sent` stays a marker that matches
                    # nothing, so the case reports as a mismatch rather than an IndexError.
                    sent = _FakeHttp.requests[0][2]["value"] if _FakeHttp.requests else _MISSING
                    if not (_same(got, "set p.c = %r" % (want,)) and _same(sent, want)):
                        bad.append((raw, want, got, sent))
                check(not bad, "%d/%d ui_set_value coercions match the original%s"
                      % (len(table) - len(bad), len(table),
                         "" if not bad else " — mismatches: %s" % bad))
                _FakeHttp.reset(payload={"ok": True})
                _call(app, "ui_set_value", "p", "c", "7")
                check(_FakeHttp.requests == [("put", "http://127.0.0.1:8142/state/p/c",
                                              {"value": 7}, 5.0)],
                      "ui_set_value PUTs {'value': parsed} to /state/<page>/<name>")

                _FakeHttp.reset(payload=["p1", "p2"])
                check(_same(_call(app, "ui_list_pages"), json.dumps(["p1", "p2"], indent=2)),
                      "ui_list_pages lists the pages as indented JSON")
                _FakeHttp.reset(payload=[])
                check(_same(_call(app, "ui_list_pages"), "no pages registered"),
                      "ui_list_pages says 'no pages registered' for an EMPTY list, not '[]'")

                _FakeHttp.reset(payload={"ok": True})
                check(_same(_call(app, "ui_add_message", "p", "chat", "user", "hi"),
                            "message added to p.chat"),
                      "ui_add_message returns its exact string")
                check(_FakeHttp.requests == [("post", "http://127.0.0.1:8142/message/p/chat",
                                              {"role": "user", "text": "hi"}, 5.0)],
                      "ui_add_message POSTs {'role','text'} to /message/<page>/<control>")

                _FakeHttp.reset(payload=[{"c": 1}])
                check(_same(_call(app, "ui_get_log"), json.dumps([{"c": 1}], indent=2)),
                      "ui_get_log returns the log as indented JSON")
                check(_FakeHttp.requests == [("get", "http://127.0.0.1:8142/log",
                                              {"limit": 20}, 5.0)],
                      "ui_get_log defaults to limit=20 and passes it as a query param")
                _FakeHttp.reset(payload=[{"c": 1}])
                _call(app, "ui_get_log", 5)
                check(_FakeHttp.requests == [("get", "http://127.0.0.1:8142/log",
                                              {"limit": 5}, 5.0)],
                      "an explicit limit is forwarded as the query param")
                _FakeHttp.reset(payload=[])
                check(_same(_call(app, "ui_get_log"), "no changes yet"),
                      "ui_get_log says 'no changes yet' for an EMPTY log")

                # every UI tool turns a transport failure into an "error: ..." string
                _FakeHttp.reset(raises=RuntimeError("connection refused"))
                errs = [_call(app, "ui_set_page", {"name": "p"}),
                        _call(app, "ui_get_state", "p"),
                        _call(app, "ui_set_value", "p", "c", "1"),
                        _call(app, "ui_list_pages"),
                        _call(app, "ui_add_message", "p", "c", "user", "t"),
                        _call(app, "ui_get_log")]
                check(all(_same(e, "error: connection refused") for e in errs),
                      "all 6 UI tools return 'error: <e>' when the UI is unreachable — they "
                      "never raise at the tool boundary%s"
                      % ("" if all(_same(e, "error: connection refused") for e in errs)
                         else " — got %s" % errs))
                _FakeHttp.reset()

            # the UI banner honors a reconfigured base (divergence 2)
            print("[7e] the UI banner reflects the configured base (divergence 2)", file=out)
            os.environ["JSON_CONTROLS_URL"] = "http://127.0.0.1:9999"
            with using_config(app_cfg):
                reset_paths()
                banner = io.StringIO()
                with contextlib.redirect_stderr(banner):
                    _build_app()
                check("  mounted      : ui (port 9999)" in banner.getvalue(),
                      "$JSON_CONTROLS_URL moves the UI base AND the banner follows it — the "
                      "original printed a literal 8142 here and was simply wrong")
            os.environ.pop("JSON_CONTROLS_URL", None)
            check(_same(_ui_port("http://localhost"), "localhost")
                  and _same(_ui_port("http://127.0.0.1:8142"), 8142),
                  "a base with no port falls back to its host rather than printing None")

            # the module-level `mcp` server (divergence 3)
            print("[7f] the module-level `mcp` server (divergence 3)", file=out)
            with using_config(cfg):
                server = __getattr__("mcp")
                check(isinstance(server, _FakeServer) and server.name == "coupler",
                      "`mcp` is the configured server named 'coupler', built on first access")
                check(set(server.tools) == {"notes_db_proxy", "z3_proxy"},
                      "`mcp` carries exactly the two proxy tools the original registered on "
                      "it%s" % ("" if set(server.tools) == {"notes_db_proxy", "z3_proxy"}
                                else " — got %s" % sorted(server.tools)))
                check(__getattr__("mcp") is server,
                      "`mcp` is a singleton — repeated access does not rebuild it")
            got = _attempt(lambda: __getattr__("no_such_attribute"))
            check(isinstance(got, _Raised) and got.type is AttributeError,
                  "an unknown module attribute still raises AttributeError, not ConfigError")

            # ── 8. the callable surface ──────────────────────────────────────
            #    Checked by LOWERING THIS FILE'S OWN SOURCE the way the ticket's surface was
            #    produced — codebean's `lower_node` (#183) walks the AST — and comparing to
            #    the ticket's strings verbatim. Runtime introspection is the WRONG oracle
            #    here, twice over: `from __future__ import annotations` makes
            #    inspect.signature render `-> 'Client'` (quoted), and the ORIGINAL, whose
            #    `Client` was a real imported class, renders `-> fastmcp.client.client.Client`
            #    — so neither module's runtime signature is the ticket's text. The AST is what
            #    the ticket lowered, so the AST is what must agree.
            print("[8] callable surface — this file's own AST, lowered as the ticket lowered "
                  "the original's", file=out)
            lowered = _lower_surface(os.path.abspath(__file__))
            for want in SURFACE:
                name = want.split("(")[0].replace("async ", "")
                check(lowered.get(name) == want,
                      "%s%s" % (want, "" if lowered.get(name) == want
                                else "  — this file lowers to %r" % (lowered.get(name),)))

            # What runtime CAN prove about the surface, and the AST cannot.
            print("[8b] callable surface — the runtime properties", file=out)
            for fn, want_async in ((_load_build, False), (_notes_python, False),
                                   (_jazz_client, False), (notes_db_proxy, True),
                                   (z3_proxy, True), (_build_app, False)):
                check(inspect.iscoroutinefunction(fn) is want_async,
                      "%s is %sawaitable, as the ticket lowers it"
                      % (fn.__name__, "" if want_async else "not "))
            for fn in (notes_db_proxy, z3_proxy):
                check(list(inspect.signature(fn).parameters) == ["tool", "args"],
                      "%s's parameters are named (tool, args) — callers may pass either by "
                      "keyword" % fn.__name__)
            check(list(inspect.signature(_jazz_client).parameters) == ["module"],
                  "_jazz_client's parameter is named `module`")
            check(_same(notes_db_proxy.__defaults__, ({},))
                  and _same(z3_proxy.__defaults__, ({},)),
                  "both proxies keep the original's mutable {} default for `args`")
    finally:
        for key, value in saved_env.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value
        sys.path[:] = saved_path
        for name in ("_selftest_why5", "_selftest_why5_partial"):
            sys.modules.pop(name, None)
        _FakeHttp.reset()
        reset_config()
        globals()["_ACTIVE"] = saved

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED",
             checks[0], len(failures)), file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


def _exploding_create_proxy(_client):
    """A create_proxy that raises, to prove _build_app's per-service warn-and-continue."""
    raise RuntimeError("kaboom")


def reset_paths():
    """Drop the cached jazz-path snapshots (see divergence 1), so a test can re-resolve them.

    `_jazz_path` caches to mirror the original's import-time snapshot; a selftest that moves
    JAZZ_ROOT between checks has to clear that cache, exactly as a new process would.
    """
    _PATH_CACHE.clear()


#: Marker for "the tool never got this far", so a check reports a mismatch rather than
#: blowing up on an empty result list. It is its own type and equals nothing expected.
_MISSING = object()


class _Raised:
    """A stand-in for a call that raised, so a check can FAIL instead of aborting.

    A test net that dies on the first unexpected exception hides every check after it, and
    reports a traceback where it owes a verdict. `_attempt` returns one of these instead.
    """

    def __init__(self, exception):
        self.type = type(exception)
        self.exception = "%s: %s" % (type(exception).__name__, exception)

    def __repr__(self):
        return "<raised %s>" % self.exception


def _attempt(thunk):
    """Call `thunk` and return its result, or a `_Raised` if it raised anything."""
    try:
        return thunk()
    except BaseException as exc:  # noqa: BLE001 — a test net must survive anything
        return _Raised(exc)


def _call(app, name, *a, **k):
    """Invoke a registered tool, returning a `_Raised` rather than propagating.

    Every tool check below goes through here. A tool that raises unexpectedly must be a
    reported FAIL — `_Raised` matches no expected string — instead of aborting `selftest`
    and hiding every check behind it. It also lets a check ASSERT a raise: `why5_fact` is
    supposed to raise KeyError for an unknown session.
    """
    return _attempt(lambda: app.call(name, *a, **k))


def _same(got, want):
    """Compare like the oracle does: equal in value AND in type.

    `==` alone would call a returned `True` a pass where the original returned the int `1`,
    and `1.5` a pass for `"1.5"`. `ui_set_value`'s whole job is to pick a TYPE, so type is
    part of the behavior being preserved.
    """
    return type(got) is type(want) and got == want


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report its
    original error. No report is filed for a ConfigError, which is designed behavior rather
    than a bug. Returns the path written, or None.
    """
    try:
        config = active_config()
        base = active_base()
    except ConfigError:
        return None
    relative = config.get("bug_reports")
    if not relative:
        return None
    path = relative if os.path.isabs(relative) else os.path.join(base, relative)
    frames = traceback.extract_tb(exc.__traceback__)
    entry = {
        "filename": os.path.basename(os.path.abspath(__file__)),
        "function": frames[-1].name if frames else "?",
        "time-of-occurance": datetime.now().isoformat(),
        "methods-to-reproduce": "python3 %s %s" % (os.path.basename(os.path.abspath(__file__)),
                                                   " ".join(argv)),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": formatted.strip().splitlines()[-6:],
        "note": "%s (ticket #403, module key forge-rw:eb9c79df006733b5)" % UNIT,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except OSError:
        return None


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="coupler",
        description="forge2 rewrite of the forge unit coupler:coupler/__main__.py "
                    "(ticket #403) — the stable MCP entry point for Claude Desktop. "
                    "Config-driven: every command below except `emit-config` and `selftest` "
                    "throws if it cannot see its config object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="config is read from the file named by $%s, else from the %s section of the "
               "nearest %s found by walking up from this module. This package ships one "
               "beside the module, so `serve` works from a clean checkout that has fastmcp "
               "installed. Run `emit-config` for a template."
               % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="build the coupler app and run it (the original's entry "
                                 "point; needs fastmcp)")
    sub.add_parser("selftest", help="prove the behavior, the edges and the config gate "
                                    "(needs no config, no fastmcp and no network)")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and its source")
    return parser


def main(argv=None):
    """Entry point for the `coupler` console script. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at "
                  "it.\n# Until it is installed, every command throws — it will not guess a "
                  "default." % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV),
                  file=sys.stderr)
            return 0

        if args.command == "selftest":
            return 0 if selftest() == 0 else 1

        if args.command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(),
                              "base": active_base(), "config": active_config()}, indent=2))
            return 0

        if args.command == "serve":
            # What the original's `if __name__ == "__main__":` block did, verbatim in shape:
            # build the app, then run it.
            app = _build_app()
            app.run()
            return 0

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
    sys.exit(main())
