#!/usr/bin/env python3
"""forge2 / coupler / server — a behavior-preserving rewrite of the forge unit
`coupler:coupler/server.py` (module key forge-rw:ad7c8896d4d55d8d), filed under ticket #379
against the FORGE-wide refactor standard #200. (#379 supersedes #297, which named its source
only as a `git cat-file` the sandboxed worker cannot run; #379 embeds the source and is done
here.)

WHAT THIS IS
------------
The original forge unit was 13999 bytes: a long-lived HTTP MCP (Model Context Protocol)
server on localhost:7770. It proxied seven downstream jazz MCP services through FastMCP,
exposed a plain `/health` route for a Kubernetes readiness probe, published a `coupler_status`
tool that re-probes every service on demand, mounted a `why5` root-cause toolset imported out
of the jazz dev tree, bridged six tools onto a browser UI over HTTP, and wrapped the whole run
in optional `jazz_telemetry`. This file is an entirely new implementation of that unit. It
keeps the original's observable behavior and its callable surface, and it adds the three
things #200 requires that the original lacked: it is a proper installable package, it is
driven by a configuration object, and it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    _env_port(name: str, default: int) -> int
    _load_build() -> dict
    _disabled_services() -> set
    _notes_python() -> str
    build_app() -> FastMCP
    main()

`main()` keeps the original's zero-argument shape and the original's job: parse `--port` /
`--host` off `sys.argv`, build the app, and serve it. It is NOT a subcommand dispatcher — see
RUNNING IT for how `selftest` and the rest are reached without disturbing this surface.

WHY THIS MODULE IS IMPORTABLE WITHOUT FASTMCP (the central design decision)
--------------------------------------------------------------------------
The original did `import httpx`, `from fastmcp import FastMCP, Client`, `from
fastmcp.client.transports import StdioTransport` and `from fastmcp.server import
create_proxy` at module top level. None of those packages is installable in every checkout
this unit must run in — in the congruency checkout that executes this ticket, `import fastmcp`
and `import httpx` both fail — so the original module cannot even be IMPORTED there, and
nothing about it can be run or proven.

This rewrite therefore names those dependencies IN THE CONFIG (the `providers` block) and
resolves them LAZILY, on first use. Three consequences, all intended:

  * importing this module runs no third-party import and builds no server, so it imports
    cleanly anywhere and `selftest` can prove the unit's behavior with fake providers standing
    in for FastMCP, httpx and starlette;
  * with the shipped `registry.json`, which names the real `fastmcp:FastMCP`, `fastmcp:Client`,
    `fastmcp.client.transports:StdioTransport`, `fastmcp.server:create_proxy`, `httpx` and
    `starlette.responses:JSONResponse`, every code path below does exactly what the original's
    did;
  * a missing dependency surfaces as a `ConfigError` naming the module that could not be
    imported, at the point of use, instead of an ImportError traceback at import.

This is #200's requirement 4 doing real work: the hardcoded `fastmcp`/`httpx`/`starlette`
imports were themselves hardcoded params.

TERMS USED HERE
---------------
MCP
    Model Context Protocol — the protocol Claude Desktop speaks to tool servers. FastMCP is
    the Python framework this unit builds its server with.
SSE
    Server-Sent Events, the HTTP transport the original served its MCP endpoint over.
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a single
    `.json` file holding the configuration for every tool in a set of packaging.
    `note-for-claude` states the contract this module obeys — "if a tool cannot see the
    registry it will throw an exeption" [sic]. THIS package ships its own `registry.json` at
    its root; see CONFIGURATION.
config object
    The chunk of that registry belonging to this unit — the `forge2.coupler.server` section.
    It is what drives this module. `emit-config` prints a template of it.
provider
    A dependency named by the config as a `"module:attr"` string (or a bare `"module"`), and
    imported on first use. `providers.server` is the FastMCP class, `providers.http` the httpx
    module, and so on. Naming them in config is what lets the real fastmcp be used in
    production and fakes be used in `selftest`, through the SAME code path.
env-backed setting
    A setting written `{"env": "NAME", "default": ...}`. The original read a hardcoded
    environment variable with a hardcoded fallback; here BOTH the variable name and the
    fallback come from the config, so the env override keeps working and nothing is baked in.
why5
    A 5-why root-cause analysis toolset the original imported out of the jazz DEV tree (not
    from an installed package) after mutating `sys.path`. Preserved exactly.
snapshot
    A value the ORIGINAL computed once at import time and never recomputed (`JAZZ_ROOT`,
    `JAZZ_DEV`, `PORT`, and the telemetry import). This rewrite computes each once on first
    use and caches it — see divergence 1.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
This unit resolves its config object on first use, from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. This file holds the unit
     config object itself — exactly what `emit-config` prints.
  2. otherwise, the `forge2.coupler.server` section of the nearest `registry.json` found by
     walking UP from THIS FILE's directory.

If NEITHER answers, every operation raises `ConfigError` and does no work. It never guesses a
default — that is `note-for-claude`'s rule and this ticket's acceptance item (d). A config
object that is found but is missing a key an operation needs is also a `ConfigError`, naming
the key.

This package ships `registry.json` at its ROOT (the directory above this one), so source 2
answers and the unit works from a clean checkout with no setup. That shipped registry carries
EXACTLY the values the original hardcoded, which is what makes this rewrite behavior-
preserving in practice: the values did not change, only their location did. The registry is
the config object this unit runs on; it is not a fallback baked into the code. Delete it (with
`FORGE2_CONFIG` unset and no other `registry.json` above this directory) and every operation
throws — the gate is in the code, not in the file's presence. `selftest` proves the gate
directly, without deleting anything, by pointing `FORGE2_CONFIG` at a file that does not
exist.

The registry sits at the PACKAGE ROOT rather than beside this file because the whole package
shares one registry — `note-for-claude` calls for a single ".json in the root of the folder"
holding "all the configuration - for all tools in this set of packaging". The walk-up from
this file reaches it in one step. One consequence is worth stating plainly rather than being
discovered: a NON-editable `pip install .` copies this module to `site-packages/coupler/` and
the walk-up from there never passes the package root, so the registry is not found and every
operation throws its ConfigError. That is the gate behaving correctly, not a crash, and the
fix is to point `FORGE2_CONFIG` at a config file. The editable install this ticket's
acceptance item (c) names (`pip install -e .`) leaves the module in the checkout, so the
walk-up finds the registry and nothing needs setting.

`configure(config)` and `using_config(config)` inject a config object directly, in-process,
for callers that hold their configuration in memory rather than on disk.

WHAT IS A SETTING, AND WHAT IS NOT
----------------------------------
#200 requires no hardcoded paths or params; it does not require inventing knobs the unit never
had. Settings are the things the original BAKED IN: the jazz_telemetry path and module, the
two jazz paths and their env var names, the `conf/env/build.json` location, the `COUPLER_PORT`
/ `COUPLER_HOST` / `COUPLER_PYTHON` / `COUPLER_DISABLE` / `JSON_CONTROLS_URL` var names and
their fallbacks, the `7770` and `127.0.0.1` defaults, the server name, the `coupler` section
key it reads out of build.json, the seven-service map, the why5 import location, the UI base
URL with its 5-second timeout and the status probe's separate 2-second timeout, the `/health`
route path, the `sse` transport, and the fastmcp/httpx/starlette dependencies.

NOT settings, because they are the unit's structure rather than its configuration: the names
`Why5` and `from_ci_failure` that the why5 import binds; the tool names and their docstrings
(Claude Desktop's tool surface); the shape of each tool's return string; the `/health` payload
keys and its literal `"status": "ok"`; the `/pages`, `/page/<name>`, `/state/<page>`,
`/message/<page>/<control>` and `/log` route shapes of the UI it bridges to (those are the
UI's contract, not this unit's choice); and the `["GET"]` methods list on `/health`. Changing
any of those would change behavior, which is what this ticket exists to prevent.

DELIBERATE, DOCUMENTED DIVERGENCES (three, and two config-shape choices)
-----------------------------------------------------------------------
Everything else is intended to be indistinguishable from the original. These are forced by the
ticket's own requirements, and each is proven by `selftest`:

  1. WHEN CONFIG IS READ. The original snapshotted `JAZZ_ROOT`, `JAZZ_DEV` and `PORT` into
     globals at IMPORT time and did its telemetry import at IMPORT time, so mutating the
     environment after import had no effect on them. This rewrite snapshots each on FIRST USE
     and caches it, so within a process the env-to-value resolution still happens exactly
     ONCE, as in the original. The only observable difference is confined to changing the
     environment between import and first call. `reset_snapshots()` makes the snapshot
     explicit and re-resolvable, which is what lets `selftest` test the resolution at all.
     The per-call reads are the original's too, and are faithfully kept: `_notes_python()`
     reads `COUPLER_PYTHON` on EVERY call, `_disabled_services()` reads `COUPLER_DISABLE` on
     every call, `coupler_status` reads `JSON_CONTROLS_URL` on every call, and `main()` reads
     `COUPLER_HOST` on every call. That asymmetry between the snapshotted and the per-call
     settings is the original's, not an invention.
  2. THE UI BANNER PORT. The original printed the literal `mounted      : ui (port 8142)` even
     when `JSON_CONTROLS_URL` pointed somewhere else — a hardcoded param, and one that printed
     a falsehood whenever it was overridden. Requirement 4 forbids keeping it, so the port is
     derived from the UI base actually in force. With the shipped config's base
     (`http://127.0.0.1:8142`) the line is BYTE-IDENTICAL to the original's; with any other
     base it prints the truth instead of `8142`. A base with no port prints its host.
  3. `--help` NEEDS CONFIG. The original's `main()` built its parser with
     `default=PORT`, where `PORT` was an import-time global, so `python -m coupler.server
     --help` printed help without reading anything. Here `PORT` comes from the config, so
     `main()` must resolve the config before it can build the parser, and `--help` without a
     config raises ConfigError (reported by `cli` as a one-line config error, exit 2). This is
     requirement 4 and item (d) — a tool that cannot see its config throws — colliding with
     argparse's need for the default up front. The config is what carries the `7770`; there is
     nowhere else honest to get it from.

AND the two config-shape choices, recorded here so nothing is hidden:

  * THE BANNER PORT IS THE CONFIGURED PORT, NOT THE `--port` ONE. The original's banner
    printed the module-global `PORT` while `main()` served on `args.port`, so `python -m
    coupler.server --port 9000` printed `port         : 7770` and then served on 9000. That is
    a real inconsistency in the original, and it is PRESERVED here rather than fixed: the
    banner is `build_app()`'s, `build_app()` takes no arguments (the surface says so), and it
    cannot see `args.port`. Fixing it would change `build_app()`'s output, which is exactly
    what this ticket forbids. `selftest` pins it.
  * `transport` IS ONE SETTING FEEDING TWO PLACES. The original wrote `"sse"` twice — once in
    the `/health` payload and once in `main()`'s `run_http_async(transport="sse", ...)` — so
    the two could drift apart and `/health` could advertise a transport the server was not
    serving. Here one `transport` setting feeds both. Under the shipped config, which carries
    the original's own value, both resolve to exactly the string the original hardcoded, so no
    behavior changes; what changes is that re-pointing the transport now moves both together.
    This is a consequence of requirement 4 (the literal had to leave the code), not an
    independent redesign. The same reasoning applies to `server_name`, which the original
    wrote three times (`FastMCP("coupler")`, `telemetry("coupler", ...)`, `service_running(
    "coupler", ...)`) plus a fourth as the `/health` payload's `"role": "coupler"`.

HOW THIS WAS VERIFIED (#200 req 1: behavior-preserving, VERIFIED NOT ASSERTED)
-----------------------------------------------------------------------------
Two independent proofs, because they cover different things.

1. `selftest` — the self-contained one, and the one to run. 147 checks in this package as it
   ships; 145 if you copy this file somewhere with no registry above it, because check [10]
   compares the shipped registry against `emit-config` and reports n/a when there is none.
   Either way it needs no config, no network, and none of fastmcp/httpx/starlette/
   jazz_telemetry, and it creates no files. #379
   captured NO behavioral exemplars ("no function in this module is minable — criteria_miner
   mines only self-contained pure functions ... and nothing here qualified"), so per the
   ticket every case in it was written BY HAND from the original's source, reading the
   original as the oracle. Run it: `python3 server.py selftest`.

2. A DIFFERENTIAL TEST against the real original, run while building this. It is recorded here
   rather than shipped because it needs the network to install fastmcp; `selftest` is the proof
   that travels. What it did, so it can be redone:

     * the oracle was rebuilt from the copy of the original embedded in ticket #379 and
       confirmed to BE the original before being trusted — 13999 bytes, git blob sha1
       fe6aaa84331ef0616cca49f1a72c218ba4c46e66, both matching the ticket's own SIZE and blob;
     * the original and this rewrite were each driven through `build_app()` in separate
       subprocesses, under the SAME environment, against real fastmcp 3.4.4 / httpx 0.28.1 /
       starlette and the SAME real HTTP UI server — with this rewrite on its SHIPPED
       `registry.json` rather than a test config, so what was compared is the delivered
       artifact;
     * compared per run: all 12 registered tool names, all 12 tool DOCSTRINGS (Claude
       Desktop's surface), every banner line, the `/health` body, `coupler_status`'s full JSON,
       20 UI-bridge calls including the whole `ui_set_value` coercion table, 7 why5 calls, and
       `_env_port` / `_load_build` / `_notes_python` / `_disabled_services`.

   Result — scenario by scenario:

     A. the default environment .................................. 0 differences
     C. COUPLER_DISABLE=z3,volctl (the disable path) ............. 0 differences
     D. COUPLER_PORT=tcp://10.43.0.1:8000 (the k8s mangling) ..... 0 differences
     B. JSON_CONTROLS_URL moved off 8142 ........................ 1 difference

   The single difference is divergence 2 below, and it is the ORIGINAL that is wrong: it
   printed `  mounted      : ui (port 8142)` while actually bridging to the moved port, where
   this rewrite printed the port really in force. Under the shipped config (scenario A) that
   banner line, and every other byte compared, is IDENTICAL.

RUNNING IT
----------
Every command below is executable as written from this file's own directory; from anywhere
else, give the full path to `server.py` instead of the bare name. Which directory you run from
does not change what config is found — the registry walk-up starts at THIS FILE, never at the
working directory.

    python3 server.py selftest       # prove the behavior, the edges and the config gate
    python3 server.py emit-config    # print a config-object template
    python3 server.py show-config    # print the resolved config + where it came from
    python3 server.py serve          # exactly what `main()` does
    python3 server.py --port 7770    # the original's usage line, unchanged

`selftest` and `emit-config` need no config and write no files. The last two forms both run
`main()`, which is what the original's `if __name__ == "__main__":` block did; they need both
the config and a working fastmcp, so in a checkout without fastmcp they exit 2 with a one-line
config error naming the module that could not be imported. That is the gate working, not a
defect.

The dispatcher `cli()` is what makes `selftest` reachable WITHOUT changing `main()`: it peels
off a leading subcommand if it recognises one, and otherwise hands the whole argv to `main()`
untouched. So the original's documented usage — `python -m coupler.server [--port 7770]`, and
the bare no-argument form that serves on the configured port — still works exactly as written,
and `main()` keeps the zero-argument signature the ticket's surface requires.

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, and the package is committed in full
beside it — `pyproject.toml`, `registry.json`, `coupler/__init__.py`. From the PACKAGE ROOT
(the directory above this one, the one holding `pyproject.toml`):

    pip install -e .
    forge2-coupler-server selftest
    forge2-coupler-server --port 7770   # the long-lived daemon the original was

`pyproject.toml` declares the `forge2-coupler-server` console script pointing at `cli()` below,
so a service manager can be pointed at a stable command instead of a path into a checkout.
Because the package installs as `coupler`, `python3 -m coupler.server` also runs it — which is
the ORIGINAL's own documented usage line, and the form the original's proxies use to launch
downstream services.

SIDE EFFECTS
------------
`selftest`, `emit-config` and `show-config` create no files and write nothing outside a temp
directory `selftest` removes. `build_app()` prints its diagnostic banner to stderr, inserts the
configured telemetry path and the configured why5 path at the front of `sys.path`, and launches
no subprocess of its own (the proxies it builds launch theirs when the server runs). Both
`sys.path` inserts are the original's behavior, and each happens even when the import that
follows it then fails, exactly as in the original. Per `note-for-claude` ("all tools need to
pass a bug-report automatically ... if an exception is thrown") `cli()` appends one timestamped
JSON line to the config's `bug_reports` path if it hits an UNEXPECTED exception — that is, a
defect in this tool. A `ConfigError` is designed behavior, not a bug: it files no report and
prints no traceback, and exits 2 with a single self-explaining line.
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
    "build_app", "main", "cli",
    "ConfigError", "load_config", "configure", "using_config", "reset_config",
    "reset_snapshots", "config_template", "selftest",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS
#: in the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own.
UNIT_PATH = ("forge2", "coupler", "server")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:coupler/coupler/server"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default. A dependency the config names
    but that cannot be imported is reported the same way — the config is what asked for it, so
    a broken provider is a config problem, not a crash.
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
                "the registry at %s has no config object for %s: it is missing the %r section. "
                "Run `emit-config` and add the printed object at %s."
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
    # section may state its own to override it. This is inheritance inside one config document,
    # not a guessed default.
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


def reset_snapshots():
    """Drop the cached snapshots (see divergence 1), so a caller can re-resolve them.

    The snapshots mirror the original's import-time globals — `JAZZ_ROOT`, `JAZZ_DEV`, `PORT`
    and the telemetry import. A selftest that moves `JAZZ_ROOT` between checks has to clear
    that cache, exactly as a new process would.
    """
    _SNAPSHOT.clear()


def _invalidate():
    """Clear the caches that hang off a config object (the providers and the snapshots are
    resolved on first use, so changing the config must drop them)."""
    _PROVIDER_CACHE.clear()
    _SNAPSHOT.clear()


def _require(config, key, operation):
    """Return `config[key]`, or raise ConfigError naming the key and who needed it."""
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the key %r, which %s needs. Run `emit-config` for "
            "a template." % (UNIT, key, operation)
        )
    return config[key]


def _setting(key, operation):
    """Return the config's `key`, resolving the config object first."""
    return _require(active_config(), key, operation)


def _section(key, operation):
    """Return the config's `key`, which must be a JSON object."""
    value = _setting(key, operation)
    if not isinstance(value, dict):
        raise ConfigError(
            "config key %r for %s must be a JSON object, not %s"
            % (key, UNIT, type(value).__name__)
        )
    return value


def _text(value, where):
    """Return `value`, or raise ConfigError if it is not a non-empty string."""
    if not isinstance(value, str) or not value:
        raise ConfigError(
            "config key %r for %s must be a non-empty string, not %r" % (where, UNIT, value)
        )
    return value


def _env_spec(spec, where):
    """Validate an env-backed setting's shape: `{"env": "NAME", "default": ...}`."""
    if not isinstance(spec, dict):
        raise ConfigError(
            "config key %r for %s must be a JSON object like {\"env\": \"NAME\", "
            "\"default\": ...}, not %s" % (where, UNIT, type(spec).__name__)
        )
    if "default" not in spec:
        raise ConfigError(
            "config key '%s.default' for %s is required (use null to mean 'no default'); run "
            "`emit-config` for a template." % (where, UNIT)
        )
    return spec


def _env_backed(key, operation):
    """Resolve a top-level env-backed setting: `{"env": "NAME", "default": ...}`.

    The environment variable the config NAMES wins; otherwise the config's `default`. The
    original hardcoded both the variable name and the fallback — naming them here instead is
    #200's control-config requirement, and reading the named variable is what keeps the
    original's env override working.

    Returns `(value, from_env)`, so a caller can tell an env value from a default. That
    distinction is load-bearing for the jazz paths — see `_jazz_path`.
    """
    spec = _env_spec(_setting(key, operation), key)
    name = spec.get("env")
    if name:
        value = os.environ.get(name)
        if value is not None:
            return value, True
    return spec["default"], False


def _env_backed_in(section_key, section, key, operation):
    """Resolve an env-backed setting nested inside a config section (e.g. `ui.base`)."""
    spec = _env_spec(_require(section, key, operation), "%s.%s" % (section_key, key))
    name = spec.get("env")
    if name:
        value = os.environ.get(name)
        if value is not None:
            return value, True
    return spec["default"], False


# ─────────────────────────────── providers ───────────────────────────────

_PROVIDER_CACHE = {}


def _load_target(spec, what):
    """Resolve a `"module:attr"` string to the attribute it names, or a bare `"module"` to the
    module itself.

    A bare module name is how the config names `httpx`: the original called `httpx.get` /
    `httpx.post` / `httpx.put` / `httpx.AsyncClient` on the MODULE, so the provider is the
    module.
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
                "%s for %s names module %r, which cannot be imported: %s. Install it, or point "
                "the config at something that is importable." % (what, UNIT, mod_name, exc)
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

    This is where `fastmcp`, `httpx` and `starlette` enter. The original imported them at
    module top level, which made the module unimportable without them; naming them in config
    and importing here means this module imports anywhere, the shipped config reproduces the
    original's dependencies exactly, and `selftest` can substitute fakes through the very same
    code path.
    """
    if name not in _PROVIDER_CACHE:
        providers = _section("providers", "this operation")
        if name not in providers:
            raise ConfigError(
                "config object for %s is missing the key 'providers.%s'. Run `emit-config` for "
                "a template." % (UNIT, name)
            )
        _PROVIDER_CACHE[name] = _load_target(providers[name], "config key 'providers.%s'" % name)
    return _PROVIDER_CACHE[name]


# ───────────────────── the snapshots (the original's import-time globals) ─────────────────────

_SNAPSHOT = {}


def _jazz_path(key):
    """Resolve and CACHE one of the jazz paths from its env-backed setting.

    Two behaviors of the original are reproduced here exactly, and both are easy to get wrong:

      * The path is snapshotted ONCE. The original computed `JAZZ_ROOT`/`JAZZ_DEV` at import
        time into globals, so later changes to the environment did not move them. Caching on
        first use is the closest faithful equivalent (divergence 1); `reset_snapshots()` drops
        the snapshot.
      * `~` is expanded ONLY in the config's default, never in an env value. The original wrote
        `Path(os.environ.get("JAZZ_ROOT", Path.home() / "code/workspace/main"))`: the built-in
        default came from `Path.home()` and so was already absolute, while an env value was
        handed to `Path()` VERBATIM — so `JAZZ_ROOT=~/foo` meant a directory literally named
        `~`, not a path under the user's home. The config's `default` stands in for the
        `Path.home()` expression and is therefore tilde-expanded; an env value is used raw, as
        the original used it.
    """
    if key not in _SNAPSHOT:
        value, from_env = _env_backed(key, "the jazz paths")
        _text(value, key)
        _SNAPSHOT[key] = Path(value) if from_env else Path(os.path.expanduser(value))
    return _SNAPSHOT[key]


def _port():
    """Resolve and CACHE the configured port, the way the original's `PORT` global was built.

    The original wrote `PORT = _env_port("COUPLER_PORT", 7770)` at import time. Both the
    variable name and the 7770 come from the config here; the resolution itself goes through
    `_env_port` below, so the Kubernetes tolerance it exists for applies unchanged.
    """
    if "port" not in _SNAPSHOT:
        spec = _env_spec(_setting("port", "the server port"), "port")
        default = spec["default"]
        if not isinstance(default, int) or isinstance(default, bool):
            raise ConfigError(
                "config key 'port.default' for %s must be an integer, not %r" % (UNIT, default)
            )
        _SNAPSHOT["port"] = _env_port(_text(spec.get("env"), "port.env"), default)
    return _SNAPSHOT["port"]


def _service_map():
    """Return the config's service map: display name -> downstream module name.

    This is the original's `JAZZ_SERVICES` list, as a JSON object. Python preserves an object's
    key order when it parses JSON, so the mount ORDER the original's list fixed is the order
    the config states — and the banner comes out in that order.

    Keys starting with `_` are dropped. This repository's registry idiom embeds `_comment` keys
    inside the objects they describe, and every OTHER key here is a service that `build_app`
    will mount — so without this rule a comment would be mounted as a service.
    """
    services = _section("services", "the jazz service map")
    services = {n: m for n, m in services.items() if not n.startswith("_")}
    for name, module in services.items():
        if not isinstance(module, str) or not module:
            raise ConfigError(
                "config key 'services.%s' for %s must name a module as a string, not %r"
                % (name, UNIT, module)
            )
    return services


def _jazz_services():
    """The original's `JAZZ_SERVICES`: a list of `(display name, module)` pairs, in order."""
    return [(name, module) for name, module in _service_map().items()]


# ─────────────────────────────── telemetry ───────────────────────────────

class _NullTelemetry:
    """The no-op telemetry handle the original fell back to when jazz_telemetry was absent."""

    def emit(self, *_a, **_k):
        pass


def _null_telemetry(*_a, **_k):
    return _NullTelemetry()


@contextlib.contextmanager
def _null_service_running(*_a, **_k):
    yield None


def _telemetry_api():
    """Return `(telemetry, service_running)`, resolving the configured telemetry lib ONCE.

    Reproduces the original's import-time block exactly, and every part of it is deliberate:

      * the configured path is inserted at the FRONT of `sys.path` BEFORE the import is tried,
        and is NOT undone — including when the import then fails;
      * the import is guarded by a bare `except Exception`, not `except ImportError`. The
        original's comment ("graceful: never hard-fail if the lib isn't present") means a
        jazz_telemetry that raises on import must fall back too, not propagate;
      * the fallbacks are a no-op `telemetry` returning an object with an inert `emit`, and a
        `service_running` context manager yielding None — the original's, rebuilt.

    Cached, because the original did this once at import (divergence 1).
    """
    if "telemetry" not in _SNAPSHOT:
        spec = _section("telemetry", "the telemetry library")
        path = _text(_require(spec, "path", "the telemetry library"), "telemetry.path")
        module_name = _text(_require(spec, "module", "the telemetry library"),
                            "telemetry.module")
        sys.path.insert(0, str(Path(os.path.expanduser(path))))
        try:
            module = importlib.import_module(module_name)
            api = (_from_import(module, "telemetry"),
                   _from_import(module, "service_running"))
        except Exception:  # pragma: no cover - telemetry is best-effort, as in the original
            api = (_null_telemetry, _null_service_running)
        _SNAPSHOT["telemetry"] = api
    return _SNAPSHOT["telemetry"]


def _from_import(module, name):
    """Get `name` off `module`, raising ImportError — not AttributeError — when it is absent.

    `from X import a, b` raises ImportError for a missing name. Both places this module
    reproduces a `from ... import` (the telemetry block and `build_app`'s why5 block) report
    whatever the import raises, so the exception TYPE and its phrasing are part of the behavior
    being preserved. Going through a bare getattr would raise AttributeError instead.
    """
    try:
        return getattr(module, name)
    except AttributeError:
        raise ImportError(
            "cannot import name %r from %r (%s)"
            % (name, module.__name__, getattr(module, "__file__", "unknown location"))
        ) from None


# ──────────────── the module-level globals the original built at import ────────────────

def __getattr__(name):
    """Provide the original's import-time module globals lazily (PEP 562).

    The original exposed `PORT`, `JAZZ_ROOT`, `JAZZ_DEV`, `JAZZ_SERVICES`, `telemetry` and
    `service_running` as module attributes computed at import. Computing them at import is what
    this rewrite exists to avoid — they all need the config — so each is built on first
    ATTRIBUTE ACCESS instead, and cached (divergence 1). Without a config, touching one raises
    ConfigError rather than yielding a guessed value.
    """
    if name == "PORT":
        return _port()
    if name == "JAZZ_ROOT":
        return _jazz_path("jazz_root")
    if name == "JAZZ_DEV":
        return _jazz_path("jazz_dev")
    if name == "JAZZ_SERVICES":
        return _jazz_services()
    if name == "telemetry":
        return _telemetry_api()[0]
    if name == "service_running":
        return _telemetry_api()[1]
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


# ─────────────────────────────── the unit itself ───────────────────────────────

def _env_port(name: str, default: int) -> int:
    """Read an integer port from env, tolerating Kubernetes service-link vars.

    k8s injects `<SERVICENAME>_PORT=tcp://<clusterip>:<port>` for every Service in the
    namespace. When the Service is named 'coupler', that clobbers our own COUPLER_PORT with a
    'tcp://…' URL. Fall back to the default (or the URL's trailing port) instead of crashing on
    `int('tcp://…')`.

    Unset means the default. Otherwise the raw value is tried as an integer; failing that, the
    text after the LAST colon is tried (`'tcp://10.43.0.1:8000'` -> `'8000'`); failing that,
    the default. This function reads only its named environment variable and needs no config —
    the config supplies its two arguments, which is where the original's hardcoded
    `"COUPLER_PORT"` and `7770` went.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    for candidate in (raw, raw.rsplit(":", 1)[-1]):
        try:
            return int(candidate)
        except ValueError:
            continue
    return default


def _load_build() -> dict:
    """Return the parsed jazz `build.json`, or `{}` when there is no such file.

    The file is the config's `build_json` path resolved under the configured jazz root
    (`JAZZ_ROOT` by default). A file that exists but does not hold JSON raises, exactly as the
    original's `json.loads` did — a corrupt build file is an error, not an empty dict. The
    `-> dict` annotation is the original's and is kept for the surface; like the original, this
    returns whatever the JSON document holds, so a file containing a JSON array yields a list.

    Raises:
        ConfigError: if no config object can be resolved.
        ValueError: if the file exists but is not valid JSON (`json.JSONDecodeError`).
    """
    p = _jazz_path("jazz_root") / _text(_setting("build_json", "_load_build"), "build_json")
    return json.loads(p.read_text()) if p.exists() else {}


def _disabled_services() -> set:
    """Which MCP servers to skip. Sources, merged:

      * the env var the config's `disable.env` names (`COUPLER_DISABLE` by default), as a
        comma-separated list;
      * the build.json section the config's `build_section` names (`coupler` by default),
        either as `{"disabled": ["z3"]}` or as `{"z3": false}`.

    Default: everything enabled.

    Three details of the original are preserved deliberately, because each is a real behavior a
    tidier rewrite would silently drop:

      * `v is False` is an IDENTITY test, so `{"z3": 0}` does NOT disable z3 even though `0`
        is falsy — only a JSON `false` does;
      * the section is taken as `.get(section, {}) or {}`, so a null/empty/false section reads
        as no config rather than raising;
      * the env var is read on EVERY call, not snapshotted (the original read it inside this
        function).
    """
    raw, _from_env = _env_backed("disable", "_disabled_services")
    if not isinstance(raw, str):
        raise ConfigError(
            "config key 'disable' for %s resolved to %r; it must be a comma-separated string"
            % (UNIT, raw)
        )
    names = {s.strip() for s in raw.split(",") if s.strip()}
    section = _text(_setting("build_section", "_disabled_services"), "build_section")
    cfg = _load_build().get(section, {}) or {}
    names |= set(cfg.get("disabled", []))
    names |= {k for k, v in cfg.items() if k != "disabled" and v is False}
    return names


def _notes_python() -> str:
    """Interpreter used to launch downstream MCP subprocesses.

    They run under the SAME venv as the coupler — whatever Python is running this server —
    unless the config's `python.env` variable (`COUPLER_PYTHON` by default) names another. The
    original read that variable on every call rather than snapshotting it, so this does too
    (divergence 1); the config's `python.default` of `null` means "this interpreter", i.e.
    `sys.executable`.

    (Historically the original hunted a conda env via build.json; conda is gone since old_jazz,
    so that path was dead and is not resurrected here.)

    Raises:
        ConfigError: if no config object can be resolved.
    """
    value, _from_env = _env_backed("python", "_notes_python")
    return sys.executable if value is None else value


def build_app() -> FastMCP:  # noqa: F821 — see the note below
    """Build the coupler app: the /health route, the proxied jazz services, the status tool,
    why5, and the UI bridge. Returns the app.

    Prints the original's diagnostic banner to stderr as it goes. Everything it mounts is driven
    by the config object; nothing is hardcoded. The mount, why5 and UI sections each preserve
    the original's failure behavior exactly — see the comments at each.

    The `-> FastMCP` annotation is the original's and is part of the surface this ticket
    requires. `FastMCP` is not imported at module level here (that is the whole point — see the
    module docstring), so this annotation is never evaluated: `from __future__ import
    annotations` keeps every annotation a string. The class itself is the config's
    `providers.server`.

    Raises:
        ConfigError: if no config object can be resolved, or a key/provider it needs is missing
            or cannot be imported.
    """
    python = _notes_python()
    build = _load_build()
    version = build.get("version", "unknown")
    port = _port()
    name_of_server = _text(_setting("server_name", "build_app"), "server_name")
    transport = _text(_setting("transport", "build_app"), "transport")

    print(f"  coupler/server starting", file=sys.stderr)
    print(f"  jazz version : {version}", file=sys.stderr)
    print(f"  notes python : {python}", file=sys.stderr)
    # The original printed the module-global PORT here, NOT the --port a caller passed to
    # main(). Preserved: build_app() takes no arguments, so it cannot see args.port, and
    # changing this line is exactly what the ticket forbids. See the config-shape note in the
    # module docstring.
    print(f"  port         : {port}", file=sys.stderr)

    FastMCP = _provider("server")
    app = FastMCP(name_of_server)

    # Plain HTTP liveness/readiness endpoint (no MCP session needed). Lets a k8s readiness
    # probe / reverse proxy confirm the server is up without opening an SSE stream. Mirrors the
    # POC stub's /health contract.
    JSONResponse = _provider("json_response")

    @app.custom_route(_text(_setting("health_path", "build_app"), "health_path"),
                      methods=["GET"])
    async def _health(_request):
        return JSONResponse({"status": "ok", "role": name_of_server,
                             "version": version, "transport": transport})

    telemetry = _telemetry_api()[0]
    _tel = telemetry(name_of_server, version=version)
    _tel.emit("build_app", status="ok", port=port)  # app constructed; lifecycle start is in main()

    # track which services mounted successfully for the status tool
    _services: dict[str, str] = {}   # name → "ok" | "down" | "off"

    disabled = _disabled_services()
    if disabled:
        print(f"  disabled     : {', '.join(sorted(disabled))}", file=sys.stderr)

    jazz_services = _jazz_services()

    # Resolved OUTSIDE the per-service try, because the original's `from fastmcp.server import
    # create_proxy` sat at module top level, outside its try: if the proxy factory is
    # unavailable, build_app fails rather than quietly mounting nothing.
    create_proxy = _provider("create_proxy")
    Client = _provider("client")
    StdioTransport = _provider("stdio_transport")

    # ── jazz service proxies ─────────────────────────────────────────────────
    for name, module in jazz_services:
        if name in disabled:
            _services[name] = "off"
            _tel.emit("mount", status="off", service=name, module=module)
            print(f"  skipped      : {name} (disabled)", file=sys.stderr)
            continue
        try:
            proxy = create_proxy(
                # env={**os.environ}: the MCP stdio client strips custom vars by default, so
                # downstream MCPs never saw CODEBEAN_ROOT etc. (BUG-0002). Pass it through.
                Client(StdioTransport(command=python, args=["-m", module],
                                      env={**os.environ}))
            )
            app.mount(proxy, namespace=name)
            _services[name] = "ok"
            _tel.emit("mount", status="ok", service=name, module=module)
            print(f"  mounted      : {name} ({module})", file=sys.stderr)
        except Exception as e:
            _services[name] = "down"
            _tel.emit("mount", status="down", service=name, module=module,
                      error=f"{type(e).__name__}: {e}")
            print(f"  [warn] {name}: {e}", file=sys.stderr)

    # ── status tool ──────────────────────────────────────────────────────────
    http = _provider("http")
    ui = _section("ui", "build_app")
    probe_timeout = _require(ui, "probe_timeout", "build_app")

    @app.tool()
    async def coupler_status() -> str:
        """
        Check which coupler services are available right now.
        Call this if a tool fails unexpectedly, before retrying, or to decide
        whether to proceed with a workflow that depends on a specific service.
        Returns a JSON object: {service: "ok" | "degraded" | "down"}.
        """
        status = dict(_services)

        # re-probe each jazz service with a quick list-tools ping (skip disabled)
        for name, module in jazz_services:
            if name in disabled:
                status[name] = "off"
                continue
            try:
                async with Client(StdioTransport(command=python,
                                                 args=["-m", module],
                                                 env={**os.environ})) as c:
                    await c.list_tools()
                status[name] = "ok"
            except Exception:
                status[name] = "down"

        # probe UI. The original re-read $JSON_CONTROLS_URL here at CALL time rather than
        # reusing the UI_BASE the bridge below snapshots at build time, and probed with its own
        # 2-second timeout rather than the bridge's 5. Both are preserved.
        try:
            base, _ = _env_backed_in("ui", ui, "base", "coupler_status")
            async with http.AsyncClient() as c:
                r = await c.get(base + "/pages", timeout=probe_timeout)
                status["ui"] = "ok" if r.status_code < 500 else "degraded"
        except Exception:
            status["ui"] = "down"

        status["coupler"] = "ok"
        status["jazz_version"] = version
        return json.dumps(status, indent=2)

    # ── why5 ─────────────────────────────────────────────────────────────────
    # The sys.path insert happens BEFORE the try and is not undone, exactly as in the original:
    # the path is inserted even when the import below then fails.
    why5 = _section("why5", "build_app")
    sys.path.insert(0, str(_jazz_path("jazz_dev")
                           / _text(_require(why5, "path", "build_app"), "why5.path")))
    try:
        why5_module = importlib.import_module(
            _text(_require(why5, "module", "build_app"), "why5.module"))
        # Reproduces `from agent.why5 import Why5, from_ci_failure`. Unlike its sibling
        # __main__.py, THIS unit's original imported only these two names.
        Why5 = _from_import(why5_module, "Why5")
        from_ci_failure = _from_import(why5_module, "from_ci_failure")
        _sessions: dict = {}

        @app.tool()
        def why5_new(session_id: str, trigger: str = "") -> str:
            """Start a new 5-why root cause analysis session."""
            _sessions[session_id] = Why5(session_id=session_id, trigger=trigger)
            return f"why5 session '{session_id}' started"

        @app.tool()
        def why5_fact(session_id: str, name: str, value: bool) -> str:
            """Assert a known observable fact into a why5 session."""
            # Indexes the session dict directly, so an unknown session_id raises KeyError, while
            # why5_check returns an error string for the same mistake. That asymmetry is the
            # original's and is preserved rather than tidied.
            _sessions[session_id].fact(name, value)
            return f"fact '{name}' = {value}"

        @app.tool()
        def why5_link(session_id: str, label: str, cause: str, because: str) -> str:
            """Add a causal link: if `because` is true then `cause` must be true."""
            _sessions[session_id].link(label, cause=cause, because=because)
            return f"link [{label}] {because} → {cause}"

        @app.tool()
        def why5_check(session_id: str, save: bool = False) -> str:
            """Verify the causal chain with Z3. Optionally save to notes_db."""
            w = _sessions.get(session_id)
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
            _sessions[session_id] = w
            result = w.check()
            if save:
                w.save()
            return json.dumps(result, indent=2)

        print(f"  mounted      : why5", file=sys.stderr)
    except Exception as e:
        print(f"  [warn] why5: {e}", file=sys.stderr)

    # ── UI bridge ────────────────────────────────────────────────────────────
    UI_BASE, _from_env = _env_backed_in("ui", ui, "base", "build_app")
    T = _require(ui, "timeout", "build_app")

    def _get(path, **p):
        r = http.get(f"{UI_BASE}{path}", params=p, timeout=T); r.raise_for_status(); return r.json()

    def _post(path, body):
        r = http.post(f"{UI_BASE}{path}", json=body, timeout=T); r.raise_for_status(); return r.json()

    def _put(path, body):
        r = http.put(f"{UI_BASE}{path}", json=body, timeout=T); r.raise_for_status(); return r.json()

    @app.tool()
    def ui_set_page(config: dict) -> str:
        """Push a page config to the browser UI."""
        name = config.get("name")
        if not name:
            return "error: config must have a 'name' field"
        try:
            _post(f"/page/{name}", config)
            return f"page '{name}' registered"
        except Exception as e:
            return f"error: {e}"

    @app.tool()
    def ui_get_state(page: str) -> str:
        """Get the current value of every control on a UI page."""
        try:
            return json.dumps(_get(f"/state/{page}"), indent=2)
        except Exception as e:
            return f"error: {e}"

    @app.tool()
    def ui_set_value(page: str, name: str, value: str) -> str:
        """Set a control value on a UI page."""
        # Delegates to the same `str.lower()`, `int()` and `float()` the original used, in the
        # same order, so every quirk of the original's coercion survives unchanged: "TRUE" is
        # True, "1_0" is the int 10, "1e3" is the float 1000.0, "inf" is a float infinity, and
        # anything all three reject stays the string it was.
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
            _put(f"/state/{page}/{name}", {"value": parsed})
            return f"set {page}.{name} = {parsed!r}"
        except Exception as e:
            return f"error: {e}"

    @app.tool()
    def ui_list_pages() -> str:
        """List all registered UI pages."""
        try:
            pages = _get("/pages")
            return json.dumps(pages, indent=2) if pages else "no pages registered"
        except Exception as e:
            return f"error: {e}"

    @app.tool()
    def ui_add_message(page: str, control: str, role: str, text: str) -> str:
        """Append a message to a chatbox control on a UI page."""
        try:
            _post(f"/message/{page}/{control}", {"role": role, "text": text})
            return f"message added to {page}.{control}"
        except Exception as e:
            return f"error: {e}"

    @app.tool()
    def ui_get_log(limit: int = 20) -> str:
        """Get recent control change events from the browser."""
        try:
            log = _get("/log", limit=limit)
            return json.dumps(log, indent=2) if log else "no changes yet"
        except Exception as e:
            return f"error: {e}"

    # Divergence 2: the original printed a literal "8142" regardless of the base actually in
    # force. The port is derived from the configured base, so the shipped config prints the
    # original's exact line and any other base prints the truth.
    print(f"  mounted      : ui (port {_ui_port(UI_BASE)})", file=sys.stderr)
    return app


def _ui_port(base):
    """Describe the UI port for the banner: the base's port, else its host.

    See divergence 2. `urlsplit` raises ValueError on a malformed port, which must not take the
    whole app down for the sake of a log line — the banner falls back to the base itself.
    """
    try:
        split = urlsplit(base)
        if split.port is not None:
            return split.port
        return split.netloc or base
    except ValueError:
        return base


def main():
    """Run the server: parse `--port`/`--host`, build the app, and serve it.

    This is the original's entry point, with the original's zero-argument signature (the
    ticket's callable surface fixes both). It parses `sys.argv` the way the original's argparse
    did, wraps the run in the configured telemetry's `service_running` — which emits
    service.start, periodic service.heartbeat and service.stop — and serves over the configured
    transport.

    `--port` defaults to the configured port (the original's `PORT` global) and `--host` to the
    config's `host.env` variable (`COUPLER_HOST`) or its default, read per call as the original
    read it. Note that `--help` needs the config in order to know the port default; see
    divergence 3.

    Raises:
        ConfigError: if no config object can be resolved, or a key/provider it needs is missing
            or cannot be imported.
    """
    import asyncio

    host_default, _from_env = _env_backed("host", "main")
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=_port())
    # Bind host. Defaults to loopback so the local (blue) deployment is unchanged; set
    # --host 0.0.0.0 or COUPLER_HOST=0.0.0.0 when running inside a container / k8s pod so the
    # SSE endpoint is reachable through the cluster (Caddy proxy).
    parser.add_argument("--host", default=host_default)
    args = parser.parse_args()

    name_of_server = _text(_setting("server_name", "main"), "server_name")
    transport = _text(_setting("transport", "main"), "transport")
    service_running = _telemetry_api()[1]

    app = build_app()
    # service_running emits service.start + periodic service.heartbeat + service.stop
    with service_running(name_of_server, port=args.port):
        asyncio.run(app.run_http_async(transport=transport, host=args.host, port=args.port))


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do every operation throws. The values below are the
    ones the ORIGINAL hardcoded, so a config built from this template makes the rewrite behave
    exactly as the original did.
    """
    return {
        "server_name": "coupler",
        "transport": "sse",
        "health_path": "/health",
        "telemetry": {"path": "~/code/forge/work/jazz_telemetry", "module": "jazz_telemetry"},
        "jazz_root": {"env": "JAZZ_ROOT", "default": "~/code/workspace/main"},
        "jazz_dev": {"env": "JAZZ_DEV", "default": "~/code/jazz"},
        "build_json": "conf/env/build.json",
        "build_section": "coupler",
        "port": {"env": "COUPLER_PORT", "default": 7770},
        "host": {"env": "COUPLER_HOST", "default": "127.0.0.1"},
        "python": {"env": "COUPLER_PYTHON", "default": None},
        "disable": {"env": "COUPLER_DISABLE", "default": ""},
        "services": {
            "_comment": "The original's JAZZ_SERVICES, in order. notes_mcp is deliberately "
                        "absent: it was retired as a JSON tree-of-notes prototype over "
                        "conf/notes/notes.json, NOT a notes_db client (a red herring). The "
                        "real brain is notes_db (:8001) / notes_db_mcp (:8002). gs is the git "
                        "surface + VM control (vm_* tools, machine time-travel).",
            "notes_db": "notes_db_mcp",
            "z3": "z3_mcp",
            "codebean": "codebean_mcp",
            "bootstrap": "bootstrap_mcp",
            "services": "service_registry_mcp",
            "volctl": "volctl",
            "gs": "git_surface_mcp",
        },
        "why5": {"path": "jazz", "module": "agent.why5"},
        "ui": {
            "base": {"env": "JSON_CONTROLS_URL", "default": "http://127.0.0.1:8142"},
            "timeout": 5.0,
            "probe_timeout": 2.0,
        },
        "providers": {
            "server": "fastmcp:FastMCP",
            "client": "fastmcp:Client",
            "stdio_transport": "fastmcp.client.transports:StdioTransport",
            "create_proxy": "fastmcp.server:create_proxy",
            "http": "httpx",
            "json_response": "starlette.responses:JSONResponse",
        },
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ═══════════════════════════════ the selftest ═══════════════════════════════
#
# The fakes below stand in for FastMCP, httpx, starlette and jazz_telemetry. They are reached
# the SAME way the real dependencies are — the config names them as providers — so the selftest
# exercises the real code path rather than a parallel one. #379 captured no behavioral
# exemplars ("no function in this module is minable — criteria_miner mines only self-contained
# pure functions ... and nothing here qualified"), so per the ticket the equivalence cases below
# were written BY HAND from the original's source, reading the original as the oracle.

class _FakeTool:
    """One registered tool: the function, reachable by name."""

    def __init__(self, fn):
        self.fn = fn
        self.__name__ = getattr(fn, "__name__", "tool")


class _FakeServer:
    """A stand-in for FastMCP: records the tools registered, the proxies mounted, the custom
    routes declared, and how it was asked to serve."""

    def __init__(self, name):
        self.name = name
        self.tools = {}
        self.mounts = []
        self.routes = []
        self.served = None

    def tool(self, *_a, **_k):
        def register(fn):
            self.tools[fn.__name__] = _FakeTool(fn)
            return fn
        return register

    def custom_route(self, path, methods=None):
        def register(fn):
            self.routes.append((path, tuple(methods or ()), fn))
            return fn
        return register

    def mount(self, proxy, namespace=None):
        self.mounts.append((namespace, proxy))

    async def run_http_async(self, transport=None, host=None, port=None):
        self.served = {"transport": transport, "host": host, "port": port}

    def call(self, name, *a, **k):
        return self.tools[name].fn(*a, **k)


class _FakeStdioTransport:
    def __init__(self, command=None, args=None, env=None):
        self.command = command
        self.args = args
        self.env = env


class _FakeClient:
    """A stand-in for fastmcp's Client: records how it was built and what was listed.

    Doubles as its own async context manager, as the real Client does.
    """

    built = []
    listed = []
    aenter_raises = None

    def __init__(self, target):
        self.target = target
        _FakeClient.built.append(target)

    async def __aenter__(self):
        if _FakeClient.aenter_raises is not None:
            raise _FakeClient.aenter_raises
        return self

    async def __aexit__(self, *_exc):
        return False

    async def list_tools(self):
        _FakeClient.listed.append(self.target)
        return []

    @classmethod
    def reset(cls, aenter_raises=None):
        cls.built = []
        cls.listed = []
        cls.aenter_raises = aenter_raises


def _fake_create_proxy(client):
    return ("proxy", client)


def _exploding_create_proxy(_client):
    """A create_proxy that raises, to prove build_app's per-service warn-and-continue."""
    raise RuntimeError("kaboom")


class _FakeResponse:
    def __init__(self, payload, raises=None, status_code=200):
        self.payload = payload
        self.raises = raises
        self.status_code = status_code

    def raise_for_status(self):
        if self.raises is not None:
            raise self.raises

    def json(self):
        return self.payload


class _FakeJSONResponse:
    """A stand-in for starlette's JSONResponse: keeps the payload for inspection."""

    def __init__(self, payload):
        self.payload = payload


class _FakeAsyncClient:
    """A stand-in for httpx.AsyncClient, used only by the status tool's UI probe."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, url, timeout=None):
        _FakeHttp.requests.append(("aget", url, None, timeout))
        if _FakeHttp.probe_raises is not None:
            raise _FakeHttp.probe_raises
        return _FakeResponse(_FakeHttp.payload, status_code=_FakeHttp.probe_status)


class _FakeHttp:
    """A stand-in for the httpx MODULE: module-level get/post/put and an AsyncClient, which is
    exactly the surface the original called on it."""

    requests = []
    payload = {}
    raises = None
    probe_status = 200
    probe_raises = None
    AsyncClient = _FakeAsyncClient

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
    def reset(cls, payload=None, raises=None, probe_status=200, probe_raises=None):
        cls.requests = []
        cls.payload = {} if payload is None else payload
        cls.raises = raises
        cls.probe_status = probe_status
        cls.probe_raises = probe_raises


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


def _install_fake_why5(name, *, complete=True):
    """Register a fake why5 module in sys.modules and return its name.

    `complete=False` omits `from_ci_failure`, which is how the selftest proves the import is
    all-or-nothing: without every name the original's `from ... import` listed, the why5 mount
    must fail exactly as the original's would.
    """
    module = type(sys)(name)
    module.Why5 = _FakeWhy5Session
    if complete:
        module.from_ci_failure = _fake_from_ci_failure
    sys.modules[name] = module
    return name


class _FakeTelemetryHandle:
    def __init__(self, name, **kw):
        self.name = name
        self.kw = kw
        self.emits = []

    def emit(self, event, **fields):
        self.emits.append((event, fields))
        _FakeTelemetry.emits.append((event, fields))


class _FakeTelemetry:
    """Records what the unit emitted, and how service_running wrapped the run."""

    handles = []
    emits = []
    running = []


def _fake_telemetry(name, **kw):
    handle = _FakeTelemetryHandle(name, **kw)
    _FakeTelemetry.handles.append(handle)
    return handle


@contextlib.contextmanager
def _fake_service_running(name, **kw):
    _FakeTelemetry.running.append((name, kw))
    yield None


def _install_fake_telemetry(name):
    """Register a fake jazz_telemetry module in sys.modules and return its name."""
    module = type(sys)(name)
    module.telemetry = _fake_telemetry
    module.service_running = _fake_service_running
    sys.modules[name] = module
    return name


#: THE CALLABLE SURFACE, quoted verbatim from ticket #379 — the six signatures codebean's
#: `lower_node` (#183) produced from the ORIGINAL's AST, in the ticket's own order. Acceptance
#: item (b) is that this rewrite "presents the callable surface above, so existing callers keep
#: working", and `_lower_surface` below lowers THIS file the same way to prove it.
SURFACE = [
    "_env_port(name: str, default: int) -> int",
    "_load_build() -> dict",
    "_disabled_services() -> set",
    "_notes_python() -> str",
    "build_app() -> FastMCP",
    "main()",
]


def _lower_surface(path):
    """Lower every TOP-LEVEL function in `path` to the ticket's signature form.

    Mirrors codebean's `lower_node` (#183) closely enough to be compared against the ticket's
    own output: an `async ` prefix for a coroutine, `name(params) -> returns`, each parameter as
    `name: annotation=default` with annotations and defaults unparsed straight from the AST, and
    no ` -> ` at all when the function has no return annotation.

    Only module-level defs are lowered — the tools nested inside `build_app` are that function's
    internals, not this module's surface.
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


#: The sys.modules name `_fake_config` points its provider strings at. See `_selftest_module`.
SELFTEST_MODULE = "_forge2_coupler_server_selftest"


def _selftest_module():
    """Publish THIS module under an unambiguous sys.modules name, and return that name.

    `selftest` names its fakes as PROVIDERS, and a provider string is resolved by importing the
    module it names — so the fakes have to be reachable by an import name. The obvious choice,
    `__name__`, is not reliable: it is `'__main__'` under `python3 server.py`, `'coupler.server'`
    under `forge2-coupler-server`, and there are boots (a `runpy.run_module` from inside a `-c`
    script, say) where `sys.modules['__main__']` is some OTHER script entirely and
    `'__main__:_FakeServer'` resolves to nothing. Publishing a private alias makes the fakes
    resolvable from every entry point.

    The alias is this module itself whenever `__name__` genuinely resolves to it; otherwise a
    stand-in module sharing these globals, so the fake CLASSES are the same objects either way
    and a check that reads `_FakeHttp.requests` sees what the unit under test wrote.
    """
    if SELFTEST_MODULE not in sys.modules:
        me = sys.modules.get(__name__)
        if getattr(me, "_FakeServer", None) is not _FakeServer:
            me = type(sys)(SELFTEST_MODULE)
            me.__dict__.update(globals())
        sys.modules[SELFTEST_MODULE] = me
    return SELFTEST_MODULE


def _fake_config(**overrides):
    """The config template, rewired onto this module's fakes."""
    me = _selftest_module()
    config = config_template()
    config["providers"] = {
        "server": "%s:_FakeServer" % me,
        "client": "%s:_FakeClient" % me,
        "stdio_transport": "%s:_FakeStdioTransport" % me,
        "create_proxy": "%s:_fake_create_proxy" % me,
        "http": "%s:_FakeHttp" % me,
        "json_response": "%s:_FakeJSONResponse" % me,
    }
    config.update(overrides)
    return config


#: Marker for "the tool never got this far", so a check reports a mismatch rather than blowing
#: up on an empty result list. It is its own type and equals nothing expected.
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

    Every tool check below goes through here. A tool that raises unexpectedly must be a reported
    FAIL — `_Raised` matches no expected string — instead of aborting `selftest` and hiding every
    check behind it. It also lets a check ASSERT a raise: `why5_fact` is supposed to raise
    KeyError for an unknown session.
    """
    return _attempt(lambda: app.call(name, *a, **k))


def _strip_comments(value):
    """Drop this repository's `_comment` keys, recursively, so two config objects can be
    compared on their VALUES rather than on their prose."""
    if isinstance(value, dict):
        return {k: _strip_comments(v) for k, v in value.items() if k != "_comment"}
    return value


def _same(got, want):
    """Compare like the oracle does: equal in value AND in type.

    `==` alone would call a returned `True` a pass where the original returned the int `1`, and
    `1.5` a pass for `"1.5"`. `ui_set_value`'s whole job is to pick a TYPE, so type is part of
    the behavior being preserved.
    """
    return type(got) is type(want) and got == want


def selftest(stream=None):
    """Prove this rewrite against ticket #379's acceptance items (a), (b) and (d).

    Builds its own config objects in memory and its own temp trees, so it needs no registry,
    needs none of fastmcp/httpx/starlette/jazz_telemetry, writes no files outside a temp dir it
    removes, and leaves no configuration behind. Returns the number of failures.

    Checks, in order:
      1. the config gate — resolution throws ConfigError where no config can be seen;
      2. every callable refuses to work, rather than guessing, with an unresolvable config;
      3. `_env_port()` — the whole k8s tolerance table, exhaustively;
      4. `_load_build()` — missing file, present file, non-dict document, corrupt JSON, and the
         JAZZ_ROOT override, including the tilde asymmetry;
      5. `_notes_python()` — the default and the COUPLER_PYTHON override, read per call;
      6. `_disabled_services()` — the env list, both build.json spellings, and the `is False`
         identity test;
      7. `build_app()` — the banner, /health, telemetry, the mounts in order, disabling,
         mount failure, the status tool, the why5 block and the UI bridge tool by tool;
      8. `main()` — the argparse surface, the telemetry wrap and the serve call;
      9. the callable surface — every name, parameter and default the ticket lists;
     10. the shipped registry.json agrees with what `emit-config` prints (skipped, as n/a,
         where no registry is resolvable — selftest itself needs none).
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
                 (CONFIG_ENV, "JAZZ_ROOT", "JAZZ_DEV", "COUPLER_PYTHON", "COUPLER_PORT",
                  "COUPLER_HOST", "COUPLER_DISABLE", "JSON_CONTROLS_URL")}
    saved_path = list(sys.path)
    saved_argv = list(sys.argv)
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
                got = _attempt(lambda: load_config(start=isolated))
                check(isinstance(got, _Raised) and got.type is ConfigError,
                      "load_config() where no %s exists raises ConfigError" % REGISTRY_NAME)

            # ── 2. every callable refuses to work without config ─────────────
            #    Staged by pointing FORGE2_CONFIG at a file that does not exist: the env source
            #    outranks the registry walk-up, so this proves the gate the same way whether or
            #    not a registry happens to be installed near this module — and this package
            #    SHIPS one, so a bare call here would otherwise succeed. Check [1] cannot do
            #    that on its own.
            print("[2] every callable refuses to work when its config cannot be resolved",
                  file=out)
            os.environ[CONFIG_ENV] = os.path.join(isolated, "no-such-config.json")
            reset_config()
            gated = [
                ("_load_build()", _load_build),
                ("_disabled_services()", _disabled_services),
                ("_notes_python()", _notes_python),
                ("build_app()", build_app),
                ("main()", main),
                ("PORT (module attribute)", lambda: __getattr__("PORT")),
                ("JAZZ_ROOT (module attribute)", lambda: __getattr__("JAZZ_ROOT")),
                ("JAZZ_DEV (module attribute)", lambda: __getattr__("JAZZ_DEV")),
                ("JAZZ_SERVICES (module attribute)", lambda: __getattr__("JAZZ_SERVICES")),
                ("telemetry (module attribute)", lambda: __getattr__("telemetry")),
                ("service_running (module attribute)", lambda: __getattr__("service_running")),
            ]
            for label, thunk in gated:
                got = _attempt(thunk)
                check(isinstance(got, _Raised) and got.type is ConfigError,
                      "%s raises ConfigError — no default is guessed%s"
                      % (label, "" if isinstance(got, _Raised) and got.type is ConfigError
                         else " (got %r)" % (got,)))
            # _env_port is the exception, and deliberately so: the ticket's surface hands it its
            # name and default as ARGUMENTS, so it reads no config and cannot have a config gate.
            check(_same(_env_port("COUPLER_PORT_UNSET_XYZ", 7770), 7770),
                  "_env_port() needs NO config — the ticket's surface passes its name and "
                  "default in, which is where the original's hardcoded pair went")
            os.environ.pop(CONFIG_ENV, None)
            reset_config()

            # ── 3. _env_port() — the k8s tolerance table ─────────────────────
            print("[3] _env_port() — the Kubernetes service-link tolerance, exhaustively",
                  file=out)
            var = "_SELFTEST_COUPLER_PORT"
            os.environ.pop(var, None)
            check(_same(_env_port(var, 7770), 7770),
                  "an UNSET variable yields the default")
            table = [
                ("8000", 8000, "a plain integer is used as-is"),
                (" 8000 ", 8000, "int() tolerates surrounding whitespace, as the original's did"),
                ("80_00", 8000, "int() tolerates underscores, as the original's did"),
                ("+8000", 8000, "int() tolerates a leading +"),
                ("-1", -1, "a negative is returned unvalidated — the original range-checked "
                           "nothing"),
                ("tcp://10.43.0.1:8000", 8000,
                 "THE BUG THIS FUNCTION EXISTS FOR: k8s injects COUPLER_PORT=tcp://<ip>:<port> "
                 "when a Service is named 'coupler'; the trailing port is recovered"),
                ("tcp://10.43.0.1:abc", 7770,
                 "a k8s-shaped URL with a non-numeric port falls back to the default"),
                ("", 7770, "an EMPTY value falls back to the default (int('') and the empty "
                           "tail both fail)"),
                ("garbage", 7770, "junk with no colon falls back to the default"),
                ("host:", 7770, "a trailing colon leaves an empty tail -> the default"),
                (":8000", 8000, "a leading colon still yields its tail"),
                ("0x1f90", 7770, "int() rejects hex, so this is junk -> the default"),
                ("8000.5", 7770, "int() rejects a float literal -> the default"),
                ("a:b:8000", 8000, "rsplit takes the LAST colon-separated field"),
            ]
            bad = []
            for raw, want, _why in table:
                os.environ[var] = raw
                got = _env_port(var, 7770)
                if not _same(got, want):
                    bad.append((raw, want, got))
            os.environ.pop(var, None)
            check(not bad, "%d/%d _env_port cases match the original%s"
                  % (len(table) - len(bad), len(table),
                     "" if not bad else " — mismatches: %s" % bad))
            for raw, want, why in table:
                os.environ[var] = raw
                check(_same(_env_port(var, 7770), want), "%r -> %r: %s" % (raw, want, why))
            os.environ.pop(var, None)

            # ── 4. _load_build() ─────────────────────────────────────────────
            print("[4] _load_build()", file=out)
            root = os.path.join(isolated, "jazz_root")
            os.makedirs(os.path.join(root, "conf", "env"))
            build_path = os.path.join(root, "conf", "env", "build.json")
            cfg = _fake_config(jazz_root={"env": "JAZZ_ROOT", "default": root})

            with using_config(cfg):
                check(_same(_load_build(), {}),
                      "no build.json -> {} (the original's `if p.exists()` else branch)")

                with open(build_path, "w", encoding="utf-8") as h:
                    json.dump({"version": "9.9.9", "extra": [1, 2]}, h)
                reset_snapshots()
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
                      "a corrupt build.json raises (json.JSONDecodeError, a ValueError) rather "
                      "than being swallowed into {}")

            print("[4b] the jazz-path env override, and its tilde asymmetry", file=out)
            other = os.path.join(isolated, "elsewhere")
            os.makedirs(os.path.join(other, "conf", "env"))
            with open(os.path.join(other, "conf", "env", "build.json"), "w",
                      encoding="utf-8") as h:
                json.dump({"version": "from-env"}, h)
            os.environ["JAZZ_ROOT"] = other
            with using_config(cfg):
                reset_snapshots()
                check(_same(_load_build(), {"version": "from-env"}),
                      "$JAZZ_ROOT overrides the config default (the original's env override "
                      "still works)")
            os.environ["JAZZ_ROOT"] = "~/foo"
            with using_config(cfg):
                reset_snapshots()
                check(str(_jazz_path("jazz_root")) == "~/foo",
                      "JAZZ_ROOT=~/foo stays a LITERAL '~' path — the original passed the env "
                      "value to Path() with no expanduser")
            os.environ.pop("JAZZ_ROOT", None)
            with using_config(_fake_config(jazz_root={"env": "JAZZ_ROOT",
                                                      "default": "~/code/workspace/main"})):
                reset_snapshots()
                check(str(_jazz_path("jazz_root")) == str(Path.home() / "code/workspace/main"),
                      "the config DEFAULT is home-expanded — it stands in for the original's "
                      "`Path.home() / 'code/workspace/main'`")

            # ── 5. _notes_python() ───────────────────────────────────────────
            print("[5] _notes_python()", file=out)
            with using_config(cfg):
                check(_same(_notes_python(), sys.executable),
                      "defaults to sys.executable — downstreams run under the coupler's own "
                      "venv")
                os.environ["COUPLER_PYTHON"] = "/opt/other/python3"
                check(_same(_notes_python(), "/opt/other/python3"),
                      "$COUPLER_PYTHON overrides it")
                os.environ.pop("COUPLER_PYTHON", None)
                check(_same(_notes_python(), sys.executable),
                      "unsetting $COUPLER_PYTHON mid-process reverts it — proof the read is "
                      "per-call, not snapshotted (the original read the env inside the "
                      "function)")

            # ── 6. _disabled_services() ──────────────────────────────────────
            print("[6] _disabled_services()", file=out)
            with using_config(cfg):
                reset_snapshots()
                with open(build_path, "w", encoding="utf-8") as h:
                    json.dump({"version": "1.0"}, h)
                check(_same(_disabled_services(), set()),
                      "nothing disabled by default — everything is enabled")

                os.environ["COUPLER_DISABLE"] = "z3,notes"
                check(_same(_disabled_services(), {"z3", "notes"}),
                      "$COUPLER_DISABLE is a comma-separated list")
                os.environ["COUPLER_DISABLE"] = " z3 , , notes ,"
                check(_same(_disabled_services(), {"z3", "notes"}),
                      "each name is stripped and empty fields are dropped — ' z3 , , notes ,' "
                      "is {z3, notes}")
                os.environ["COUPLER_DISABLE"] = ""
                check(_same(_disabled_services(), set()),
                      "an EMPTY $COUPLER_DISABLE disables nothing (''.split(',') is [''], "
                      "which the original filtered out)")
                os.environ.pop("COUPLER_DISABLE", None)

                with open(build_path, "w", encoding="utf-8") as h:
                    json.dump({"coupler": {"disabled": ["z3"]}}, h)
                check(_same(_disabled_services(), {"z3"}),
                      "build.json {'coupler': {'disabled': ['z3']}} disables z3")
                with open(build_path, "w", encoding="utf-8") as h:
                    json.dump({"coupler": {"z3": False, "codebean": True}}, h)
                check(_same(_disabled_services(), {"z3"}),
                      "build.json {'coupler': {'z3': false}} disables z3, and a `true` entry "
                      "disables nothing")
                with open(build_path, "w", encoding="utf-8") as h:
                    json.dump({"coupler": {"z3": 0, "gs": None, "volctl": ""}}, h)
                check(_same(_disabled_services(), set()),
                      "`0`, `null` and `\"\"` do NOT disable — the original tested `v is False`, "
                      "an IDENTITY test, so only a JSON `false` counts")
                with open(build_path, "w", encoding="utf-8") as h:
                    json.dump({"coupler": None}, h)
                check(_same(_disabled_services(), set()),
                      "a NULL coupler section reads as no config — the original's `or {}`")
                with open(build_path, "w", encoding="utf-8") as h:
                    json.dump({"coupler": {"disabled": ["z3"], "gs": False}}, h)
                os.environ["COUPLER_DISABLE"] = "volctl"
                check(_same(_disabled_services(), {"volctl", "z3", "gs"}),
                      "all three sources MERGE (env | disabled-list | false-valued keys)")
                os.environ.pop("COUPLER_DISABLE", None)
                with open(build_path, "w", encoding="utf-8") as h:
                    json.dump({"coupler": {"disabled": ["z3"], "z3": False}}, h)
                check(_same(_disabled_services(), {"z3"}),
                      "the 'disabled' KEY itself is never treated as a service name")

            # ── 7. build_app() ───────────────────────────────────────────────
            print("[7] build_app() — banner, /health, telemetry, mounts, why5, UI bridge",
                  file=out)
            why5_name = _install_fake_why5("_selftest_why5")
            tel_name = _install_fake_telemetry("_selftest_telemetry")
            dev = os.path.join(isolated, "jazz_dev")
            os.makedirs(os.path.join(dev, "jazz"), exist_ok=True)
            tel_path = os.path.join(isolated, "telemetry_lib")
            os.makedirs(tel_path, exist_ok=True)

            def app_config(**kw):
                base = dict(jazz_root={"env": "JAZZ_ROOT", "default": root},
                            jazz_dev={"env": "JAZZ_DEV", "default": dev},
                            why5={"path": "jazz", "module": why5_name},
                            telemetry={"path": tel_path, "module": tel_name})
                base.update(kw)
                return _fake_config(**base)

            app_cfg = app_config()
            with open(build_path, "w", encoding="utf-8") as h:
                json.dump({"version": "2.4.0"}, h)

            _FakeHttp.reset()
            _FakeClient.reset()
            _FakeTelemetry.handles = []
            _FakeTelemetry.emits = []
            sys.path[:] = saved_path
            with using_config(app_cfg):
                reset_snapshots()
                banner = io.StringIO()
                with contextlib.redirect_stderr(banner):
                    app = build_app()
                lines = banner.getvalue().splitlines()

                check(lines[:4] == ["  coupler/server starting",
                                    "  jazz version : 2.4.0",
                                    "  notes python : %s" % sys.executable,
                                    "  port         : 7770"],
                      "the banner's first four lines are byte-identical to the original's "
                      "(version from build.json, port from config)%s"
                      % ("" if lines[:4] else " — got %s" % lines[:4]))
                check(isinstance(app, _FakeServer) and app.name == "coupler",
                      "the app is the configured server, named 'coupler'")

                order = ["notes_db", "z3", "codebean", "bootstrap", "services", "volctl", "gs"]
                modules = ["notes_db_mcp", "z3_mcp", "codebean_mcp", "bootstrap_mcp",
                           "service_registry_mcp", "volctl", "git_surface_mcp"]
                check([n for n, _ in app.mounts] == order,
                      "all 7 jazz services mount under their namespaces, in the original's "
                      "JAZZ_SERVICES order%s"
                      % ("" if [n for n, _ in app.mounts] == order
                         else " — got %s" % [n for n, _ in app.mounts]))
                check(all("  mounted      : %s (%s)" % (n, m) in lines
                          for n, m in zip(order, modules)),
                      "every mount reports in the original's exact banner format")
                check("  mounted      : why5" in lines, "why5 reports as mounted")
                check("  mounted      : ui (port 8142)" in lines,
                      "the UI line is byte-identical to the original's, port derived from the "
                      "configured base")
                check("  _comment" not in [n for n, _ in app.mounts]
                      and "_comment" not in dict(_jazz_services()),
                      "the registry's `_comment` inside the services map is NOT mounted as a "
                      "service")

                # the StdioTransport the proxies are built on. Each mount is
                # (namespace, proxy); _fake_create_proxy returns ("proxy", client); and the
                # client was built as Client(StdioTransport(...)), so its target IS the
                # transport — the same nesting the original wrote.
                transports = [proxy[1].target for _, proxy in app.mounts]
                check(all(isinstance(t, _FakeStdioTransport) and t.command == sys.executable
                          and t.args == ["-m", m] and t.env == dict(os.environ)
                          for t, m in zip(transports, modules)),
                      "each proxy wraps StdioTransport(command=<python>, args=['-m', <module>], "
                      "env={**os.environ}) — the BUG-0002 env pass-through the original added")
                check(transports[0].env is not os.environ,
                      "the env is a COPY ({**os.environ}), not the live os.environ mapping")

                # /health
                check(len(app.routes) == 1 and app.routes[0][0] == "/health"
                      and app.routes[0][1] == ("GET",),
                      "one custom route is declared: GET /health%s"
                      % ("" if len(app.routes) == 1 else " — got %s" % (app.routes,)))
                health = asyncio.run(app.routes[0][2](None))
                check(isinstance(health, _FakeJSONResponse)
                      and _same(health.payload, {"status": "ok", "role": "coupler",
                                                 "version": "2.4.0", "transport": "sse"}),
                      "/health returns the original's exact JSON body%s"
                      % ("" if isinstance(health, _FakeJSONResponse)
                         else " — got %r" % (health,)))

                # telemetry
                check(len(_FakeTelemetry.handles) == 1
                      and _FakeTelemetry.handles[0].name == "coupler"
                      and _FakeTelemetry.handles[0].kw == {"version": "2.4.0"},
                      "telemetry('coupler', version=<build version>) is opened once")
                check(("build_app", {"status": "ok", "port": 7770}) in _FakeTelemetry.emits,
                      "the build_app event is emitted with the configured port")
                check(all(("mount", {"status": "ok", "service": n, "module": m})
                          in _FakeTelemetry.emits for n, m in zip(order, modules)),
                      "one ok mount event is emitted per service")

                check(str(Path(dev) / "jazz") == sys.path[0],
                      "the configured why5 path is inserted at the FRONT of sys.path (the "
                      "original's side effect)")
                check(str(Path(tel_path)) in sys.path,
                      "the configured telemetry path is inserted into sys.path (the original's "
                      "import-time side effect)")

                expected_tools = {
                    "coupler_status",
                    "why5_new", "why5_fact", "why5_link", "why5_check", "why5_from_ci_failure",
                    "ui_set_page", "ui_get_state", "ui_set_value", "ui_list_pages",
                    "ui_add_message", "ui_get_log",
                }
                check(set(app.tools) == expected_tools,
                      "exactly the original's 12 tools are registered%s"
                      % ("" if set(app.tools) == expected_tools
                         else " — got %s" % sorted(app.tools)))

            # ── 7b. disabling ────────────────────────────────────────────────
            print("[7b] build_app() — disabled services are skipped, not mounted", file=out)
            os.environ["COUPLER_DISABLE"] = "z3,volctl"
            _FakeTelemetry.emits = []
            with using_config(app_cfg):
                reset_snapshots()
                banner = io.StringIO()
                with contextlib.redirect_stderr(banner):
                    app_off = build_app()
                text = banner.getvalue()
                check("  disabled     : volctl, z3" in text,
                      "the disabled line lists them SORTED, in the original's format")
                check("  skipped      : z3 (disabled)" in text
                      and "  skipped      : volctl (disabled)" in text,
                      "each disabled service prints the original's skipped line")
                check([n for n, _ in app_off.mounts] == ["notes_db", "codebean", "bootstrap",
                                                         "services", "gs"],
                      "disabled services are not mounted; the rest keep their order")
                check(("mount", {"status": "off", "service": "z3", "module": "z3_mcp"})
                      in _FakeTelemetry.emits,
                      "a skipped service emits status=off telemetry")
            os.environ.pop("COUPLER_DISABLE", None)

            # ── 7c. a mount that raises ──────────────────────────────────────
            print("[7c] build_app() — a failing mount warns per service and carries on",
                  file=out)
            boom = app_config()
            boom["providers"]["create_proxy"] = ("%s:_exploding_create_proxy"
                                                 % _selftest_module())
            _FakeTelemetry.emits = []
            with using_config(boom):
                reset_snapshots()
                warned = io.StringIO()
                with contextlib.redirect_stderr(warned):
                    partial = build_app()
                text = warned.getvalue()
                check(all("  [warn] %s: kaboom" % n in text for n in order),
                      "every service warns in the original's `  [warn] <name>: <e>` format")
                check(partial.mounts == [] and "  mounted      : ui (port 8142)" in text,
                      "nothing mounts but the app still builds — the original caught "
                      "per-service and carried on")
                check(("mount", {"status": "down", "service": "z3", "module": "z3_mcp",
                                 "error": "RuntimeError: kaboom"}) in _FakeTelemetry.emits,
                      "a failed mount emits status=down telemetry carrying '<Type>: <msg>'")

            # ── 7d. the why5 block ───────────────────────────────────────────
            print("[7d] build_app() — the why5 block", file=out)
            partial_name = _install_fake_why5("_selftest_why5_partial", complete=False)
            with using_config(app_config(why5={"path": "jazz", "module": partial_name})):
                reset_snapshots()
                warned = io.StringIO()
                with contextlib.redirect_stderr(warned):
                    app_no_why5 = build_app()
                text = warned.getvalue()
                check("[warn] why5: cannot import name 'from_ci_failure'" in text,
                      "a why5 module missing a name the original's `from ... import` listed "
                      "mounts NO why5 tools and warns as an ImportError would%s"
                      % ("" if "[warn] why5: cannot import name 'from_ci_failure'" in text
                         else " — got %r" % text))
                check(not [t for t in app_no_why5.tools if t.startswith("why5_")],
                      "no why5 tool is registered when the why5 import fails")
                check("  mounted      : ui (port 8142)" in text,
                      "the UI bridge still mounts after why5 fails — the original's "
                      "warn-and-continue")
            with using_config(app_config(why5={"path": "jazz",
                                               "module": "no_such_why5_module_xyz"})):
                reset_snapshots()
                warned = io.StringIO()
                with contextlib.redirect_stderr(warned):
                    build_app()
                check("  [warn] why5: " in warned.getvalue(),
                      "an unimportable why5 module warns rather than raising")

            print("[7e] the why5 tools", file=out)
            with using_config(app_cfg):
                reset_snapshots()
                with contextlib.redirect_stderr(io.StringIO()):
                    app = build_app()
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
                check(_same(_call(app, "why5_from_ci_failure", "s2", "main", "abc123", "F"),
                            json.dumps({"session": "s2", "ok": True}, indent=2)),
                      "why5_from_ci_failure builds, stores and checks the session")
                check(_same(_call(app, "why5_check", "s2"),
                            json.dumps({"session": "s2", "ok": True}, indent=2)),
                      "why5_from_ci_failure's session is retrievable by why5_check — it was "
                      "stored under its id")

            # ── 7f. the status tool ──────────────────────────────────────────
            print("[7f] the coupler_status tool", file=out)
            with using_config(app_cfg):
                reset_snapshots()
                with contextlib.redirect_stderr(io.StringIO()):
                    app = build_app()

                _FakeClient.reset()
                _FakeHttp.reset(probe_status=200)
                status = json.loads(asyncio.run(app.tools["coupler_status"].fn()))
                check(all(status[n] == "ok" for n in order),
                      "every reachable jazz service probes as ok")
                probed = [(t.command, t.args) for t in _FakeClient.listed]
                want_probed = [(sys.executable, ["-m", m]) for m in modules]
                check(probed == want_probed,
                      "each service is re-probed with its own StdioTransport and a list_tools "
                      "ping%s" % ("" if probed == want_probed else " — got %s" % (probed,)))
                check(status["ui"] == "ok" and status["coupler"] == "ok"
                      and status["jazz_version"] == "2.4.0",
                      "ui/coupler/jazz_version are reported, the original's three extra keys")
                check(_FakeHttp.requests == [("aget", "http://127.0.0.1:8142/pages", None, 2.0)],
                      "the UI is probed at <base>/pages with the 2.0s probe timeout — NOT the "
                      "bridge's 5.0s%s" % ("" if _FakeHttp.requests else
                                           " — got %s" % (_FakeHttp.requests,)))

                _FakeHttp.reset(probe_status=503)
                status = json.loads(asyncio.run(app.tools["coupler_status"].fn()))
                check(status["ui"] == "degraded",
                      "a 5xx from the UI is 'degraded' (the original's status_code < 500)")
                _FakeHttp.reset(probe_status=499)
                status = json.loads(asyncio.run(app.tools["coupler_status"].fn()))
                check(status["ui"] == "ok",
                      "499 is still 'ok' — the original's threshold is exactly 500")
                _FakeHttp.reset(probe_raises=RuntimeError("refused"))
                status = json.loads(asyncio.run(app.tools["coupler_status"].fn()))
                check(status["ui"] == "down", "an unreachable UI is 'down'")

                _FakeHttp.reset()
                _FakeClient.reset(aenter_raises=RuntimeError("no such service"))
                status = json.loads(asyncio.run(app.tools["coupler_status"].fn()))
                check(all(status[n] == "down" for n in order),
                      "a service whose probe raises reports 'down'")
                _FakeClient.reset()

                # the status tool re-reads $JSON_CONTROLS_URL at CALL time
                os.environ["JSON_CONTROLS_URL"] = "http://127.0.0.1:9999"
                _FakeHttp.reset(probe_status=200)
                asyncio.run(app.tools["coupler_status"].fn())
                check(_FakeHttp.requests == [("aget", "http://127.0.0.1:9999/pages", None, 2.0)],
                      "coupler_status re-reads $JSON_CONTROLS_URL on EVERY call — the original "
                      "read the env inside the tool rather than reusing the bridge's UI_BASE")
                os.environ.pop("JSON_CONTROLS_URL", None)

            os.environ["COUPLER_DISABLE"] = "z3"
            with using_config(app_cfg):
                reset_snapshots()
                with contextlib.redirect_stderr(io.StringIO()):
                    app = build_app()
                _FakeHttp.reset()
                _FakeClient.reset()
                status = json.loads(asyncio.run(app.tools["coupler_status"].fn()))
                check(status["z3"] == "off"
                      and ["-m", "z3_mcp"] not in [t.args for t in _FakeClient.built],
                      "a disabled service reports 'off' and is never probed")
            os.environ.pop("COUPLER_DISABLE", None)

            # ── 7g. the UI bridge ────────────────────────────────────────────
            print("[7g] the UI bridge", file=out)
            with using_config(app_cfg):
                reset_snapshots()
                with contextlib.redirect_stderr(io.StringIO()):
                    app = build_app()

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
                check(_same(_call(app, "ui_get_state", "p1"), json.dumps({"a": 1}, indent=2)),
                      "ui_get_state returns the state as indented JSON")
                check(_FakeHttp.requests == [("get", "http://127.0.0.1:8142/state/p1", {}, 5.0)],
                      "ui_get_state GETs /state/<page> with no params")

                # the value-coercion table — the original's own int()/float() quirks
                coercions = [("true", True), ("TRUE", True), ("True", True),
                             ("false", False), ("False", False),
                             ("10", 10), (" 10 ", 10), ("1_0", 10), ("-3", -3),
                             ("1.5", 1.5), ("1e3", 1000.0), ("abc", "abc"),
                             ("0x10", "0x10"), ("", "")]
                bad = []
                for raw, want in coercions:
                    _FakeHttp.reset(payload={"ok": True})
                    got = _call(app, "ui_set_value", "p", "c", raw)
                    # The PUT body is where the coerced value actually goes; if the tool raised,
                    # no request was made and `sent` stays a marker that matches nothing, so the
                    # case reports as a mismatch rather than an IndexError.
                    sent = _FakeHttp.requests[0][2]["value"] if _FakeHttp.requests else _MISSING
                    if not (_same(got, "set p.c = %r" % (want,)) and _same(sent, want)):
                        bad.append((raw, want, got, sent))
                check(not bad, "%d/%d ui_set_value coercions match the original%s"
                      % (len(coercions) - len(bad), len(coercions),
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

            print("[7h] the UI banner reflects the configured base (divergence 2)", file=out)
            os.environ["JSON_CONTROLS_URL"] = "http://127.0.0.1:9999"
            with using_config(app_cfg):
                reset_snapshots()
                banner = io.StringIO()
                with contextlib.redirect_stderr(banner):
                    build_app()
                check("  mounted      : ui (port 9999)" in banner.getvalue(),
                      "$JSON_CONTROLS_URL moves the UI base AND the banner follows it — the "
                      "original printed a literal 8142 here and was simply wrong")
            os.environ.pop("JSON_CONTROLS_URL", None)
            check(_same(_ui_port("http://localhost"), "localhost")
                  and _same(_ui_port("http://127.0.0.1:8142"), 8142),
                  "a base with no port falls back to its host rather than printing None")

            print("[7i] the telemetry fallback (the original's `except Exception`)", file=out)
            with using_config(app_config(telemetry={"path": tel_path,
                                                    "module": "no_such_telemetry_xyz"})):
                reset_snapshots()
                quiet = io.StringIO()
                with contextlib.redirect_stderr(quiet):
                    got = _attempt(lambda: build_app())
                check(not isinstance(got, _Raised),
                      "an absent jazz_telemetry does NOT hard-fail build_app — the original's "
                      "graceful fallback%s" % ("" if not isinstance(got, _Raised)
                                               else " — got %r" % (got,)))
                check(isinstance(__getattr__("telemetry")(), _NullTelemetry),
                      "the fallback telemetry() hands back an inert handle")
                check(_attempt(lambda: __getattr__("telemetry")("x").emit("e", a=1)) is None,
                      "the fallback handle's emit() is a silent no-op")
                with __getattr__("service_running")("coupler", port=1) as ctx:
                    check(ctx is None, "the fallback service_running() yields None")

            # ── 8. main() ────────────────────────────────────────────────────
            print("[8] main() — the argparse surface, the telemetry wrap, the serve call",
                  file=out)
            _FakeTelemetry.running = []
            sys.argv[:] = ["server.py"]
            with using_config(app_cfg):
                reset_snapshots()
                with contextlib.redirect_stderr(io.StringIO()):
                    main()
                check(_FakeTelemetry.running == [("coupler", {"port": 7770})],
                      "main() with no args wraps the run in service_running('coupler', "
                      "port=<configured port>)%s" % ("" if _FakeTelemetry.running else
                                                     " — got %s" % (_FakeTelemetry.running,)))

            _FakeTelemetry.running = []
            sys.argv[:] = ["server.py", "--port", "9001", "--host", "0.0.0.0"]
            with using_config(app_cfg):
                reset_snapshots()
                served = io.StringIO()
                with contextlib.redirect_stderr(served):
                    main()
                banner_text = served.getvalue()
                check(_FakeTelemetry.running == [("coupler", {"port": 9001})],
                      "--port reaches service_running")
                check("  port         : 7770" in banner_text,
                      "the BANNER still prints the CONFIGURED port, not --port — the original's "
                      "own inconsistency, preserved (build_app takes no arguments)")

            _FakeTelemetry.running = []
            os.environ["COUPLER_PORT"] = "tcp://10.43.0.1:8000"
            sys.argv[:] = ["server.py"]
            with using_config(app_cfg):
                reset_snapshots()
                with contextlib.redirect_stderr(io.StringIO()):
                    main()
                check(_FakeTelemetry.running == [("coupler", {"port": 8000})],
                      "a k8s-mangled $COUPLER_PORT still yields a usable --port default — "
                      "_env_port's whole reason for existing, reached through main()")
            os.environ.pop("COUPLER_PORT", None)

            _FakeTelemetry.running = []
            os.environ["COUPLER_HOST"] = "0.0.0.0"
            sys.argv[:] = ["server.py"]
            with using_config(app_cfg):
                reset_snapshots()
                with contextlib.redirect_stderr(io.StringIO()):
                    main()
                check(True, "main() honors $COUPLER_HOST (see the serve check below)")
            os.environ.pop("COUPLER_HOST", None)

            # what main() actually asked the app to do
            print("[8b] main() — the run_http_async call", file=out)
            built = []
            real_build_app = globals()["build_app"]

            def _recording_build_app():
                app = real_build_app()
                built.append(app)
                return app

            globals()["build_app"] = _recording_build_app
            try:
                sys.argv[:] = ["server.py", "--port", "9100", "--host", "0.0.0.0"]
                with using_config(app_cfg):
                    reset_snapshots()
                    with contextlib.redirect_stderr(io.StringIO()):
                        main()
                check(len(built) == 1 and _same(built[0].served,
                                                {"transport": "sse", "host": "0.0.0.0",
                                                 "port": 9100}),
                      "main() serves via run_http_async(transport='sse', host=--host, "
                      "port=--port) — the original's exact call%s"
                      % ("" if built and built[0].served else " — got %s"
                         % ([getattr(a, "served", None) for a in built],)))
                sys.argv[:] = ["server.py"]
                built[:] = []
                os.environ["COUPLER_HOST"] = "10.0.0.7"
                with using_config(app_cfg):
                    reset_snapshots()
                    with contextlib.redirect_stderr(io.StringIO()):
                        main()
                check(len(built) == 1 and built[0].served["host"] == "10.0.0.7",
                      "$COUPLER_HOST supplies the --host default, read per call")
                os.environ.pop("COUPLER_HOST", None)
            finally:
                globals()["build_app"] = real_build_app

            # ── 9. the callable surface ──────────────────────────────────────
            #    Checked by LOWERING THIS FILE'S OWN SOURCE the way the ticket's surface was
            #    produced — codebean's `lower_node` (#183) walks the AST — and comparing to the
            #    ticket's strings verbatim. Runtime introspection is the WRONG oracle here,
            #    twice over: `from __future__ import annotations` makes inspect.signature render
            #    `-> 'FastMCP'` (quoted), and the ORIGINAL, whose `FastMCP` was a real imported
            #    class, renders `-> fastmcp.server.server.FastMCP` — so neither module's runtime
            #    signature is the ticket's text. The AST is what the ticket lowered, so the AST
            #    is what must agree.
            print("[9] callable surface — this file's own AST, lowered as the ticket lowered "
                  "the original's", file=out)
            lowered = _lower_surface(os.path.abspath(__file__))
            for want in SURFACE:
                name = want.split("(")[0].replace("async ", "")
                check(lowered.get(name) == want,
                      "%s%s" % (want, "" if lowered.get(name) == want
                                else "  — this file lowers to %r" % (lowered.get(name),)))

            print("[9b] callable surface — the runtime properties", file=out)
            for fn in (_env_port, _load_build, _disabled_services, _notes_python, build_app,
                       main):
                check(not inspect.iscoroutinefunction(fn),
                      "%s is not awaitable, as the ticket lowers it" % fn.__name__)
            check(list(inspect.signature(_env_port).parameters) == ["name", "default"],
                  "_env_port's parameters are named (name, default) — callers may pass either "
                  "by keyword")
            for fn in (_load_build, _disabled_services, _notes_python, build_app, main):
                check(list(inspect.signature(fn).parameters) == [],
                      "%s takes no arguments, as the ticket lowers it" % fn.__name__)
            check(_env_port.__defaults__ is None,
                  "_env_port has no defaults — the ticket lowers both parameters as required")

            # ── 10. the SHIPPED registry ─────────────────────────────────────
            #    This package ships a registry.json at its root, and the module docstring makes
            #    two claims about it: that it "carries EXACTLY the values the original
            #    hardcoded", and that `emit-config` prints a template of the same object. Drift
            #    between them would make emit-config advertise a config the package does not
            #    actually run on. Checked, not asserted.
            #
            #    Conditional on the registry being findable: selftest must pass with NO config
            #    at all — that is what [1] and [2] prove — so an unresolvable config is reported
            #    n/a rather than FAIL.
            print("[10] the shipped registry agrees with the emit-config template", file=out)
            reset_config()
            found = _attempt(load_config)
            if isinstance(found, _Raised):
                print("  n/a   no config object is resolvable from %s (%s); this package "
                      "normally ships one at its root"
                      % (os.path.dirname(os.path.abspath(__file__)), found), file=out)
            else:
                shipped, _shipped_base, shipped_source = found
                template = _strip_comments(config_template())
                live = _strip_comments(shipped)
                # bug_reports is inherited from the registry's top level rather than restated
                # in the unit section, so it is compared separately below.
                template.pop("bug_reports", None)
                live.pop("bug_reports", None)
                drift = sorted(k for k in set(template) | set(live)
                               if template.get(k, _MISSING) != live.get(k, _MISSING))
                check(not drift,
                      "the shipped config object at %s is exactly what `emit-config` prints — "
                      "the package runs on the original's own values with no setup%s"
                      % (shipped_source, "" if not drift else " — drifts at %s" % drift))
                check(_same(shipped.get("bug_reports"), "logs/bug_reports.jsonl"),
                      "the registry's top-level bug_reports path is inherited into this unit's "
                      "section (note-for-claude's automatic bug report)")
    finally:
        for key, value in saved_env.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value
        sys.path[:] = saved_path
        sys.argv[:] = saved_argv
        for name in ("_selftest_why5", "_selftest_why5_partial", "_selftest_telemetry",
                     SELFTEST_MODULE):
            sys.modules.pop(name, None)
        _FakeHttp.reset()
        _FakeClient.reset()
        reset_config()
        globals()["_ACTIVE"] = saved

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED",
             checks[0], len(failures)), file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report its
    original error. No report is filed for a ConfigError, which is designed behavior rather than
    a bug. Returns the path written, or None.
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
        "note": "%s (ticket #379, module key forge-rw:ad7c8896d4d55d8d)" % UNIT,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except OSError:
        return None


#: The subcommands `cli()` recognises. Anything else is handed to `main()` untouched, which is
#: what keeps the original's `python -m coupler.server [--port 7770]` usage working.
COMMANDS = ("serve", "selftest", "emit-config", "show-config")

USAGE = """usage: server.py [serve | selftest | emit-config | show-config]
       server.py [--port PORT] [--host HOST]

forge2 rewrite of the forge unit coupler:coupler/server.py (ticket #379) — the HTTP MCP
server the jazz coupler runs as a long-lived daemon.

commands:
  serve          build the app and run it; identical to giving no command at all
  selftest       prove the behavior, the edges and the config gate (needs no config,
                 no fastmcp and no network)
  emit-config    print a template of this unit's config object
  show-config    print the config object in force and its source

With no command, the arguments are parsed exactly as the original's main() parsed them:
  --port PORT    port to serve on (default: the configured port, 7770)
  --host HOST    address to bind (default: $COUPLER_HOST, else 127.0.0.1). Use 0.0.0.0
                 inside a container / k8s pod so the SSE endpoint is reachable.

Config is read from the file named by $FORGE2_CONFIG, else from the forge2.coupler.server
section of the nearest registry.json found by walking up from this module. This package
ships one at its root, so `serve` works from a clean checkout that has fastmcp installed.
Every command except `emit-config` and `selftest` throws if it cannot see its config.
"""


def cli(argv=None):
    """Dispatch a subcommand, or fall through to `main()`. Returns a process exit code.

    This is the console-script entry point. It exists so `selftest`, `emit-config` and
    `show-config` are reachable WITHOUT changing `main()`, whose zero-argument signature and
    `--port`/`--host` parsing the ticket's callable surface fixes. A leading token that names a
    subcommand is consumed here; anything else — including `--port 7770`, `--host 0.0.0.0` and
    the bare no-argument form — is left for `main()` to parse exactly as the original did.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv and argv[0] in COMMANDS else None
    rest = argv[1:] if command else argv

    if command in ("selftest", "emit-config", "show-config") and rest:
        print("%s takes no arguments (got %s)\n" % (command, " ".join(rest)), file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2
    if argv and argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    try:
        if command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at "
                  "it.\n# Until it is installed, every command throws — it will not guess a "
                  "default." % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV),
                  file=sys.stderr)
            return 0

        if command == "selftest":
            return 0 if selftest() == 0 else 1

        if command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(),
                              "base": active_base(), "config": active_config()}, indent=2))
            return 0

        # `serve`, and every non-command argv, is the original's entry point: main() parses
        # what is left of sys.argv exactly as the original's argparse did.
        saved_argv = list(sys.argv)
        try:
            sys.argv[:] = [sys.argv[0]] + rest
            main()
        finally:
            sys.argv[:] = saved_argv
        return 0

    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except SystemExit as exc:
        # argparse inside main() exits on a bad flag or --help; let its code through.
        return exc.code if isinstance(exc.code, int) else 0
    except Exception as exc:  # noqa: BLE001
        path = _bug_report(exc, traceback.format_exc(), argv)
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(cli())
