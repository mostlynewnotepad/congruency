#!/usr/bin/env python3
"""forge2 / code__code-invalid__coupler / coupler.__main__ — a behavior-preserving rewrite of
the forge unit `code__code-invalid__coupler:coupler/__main__.py` (module key
forge-rw:74c24d09f565e96d), filed under ticket #369 against the FORGE-wide refactor standard
#200.

(#369 supersedes #285, which named its source only as a `git cat-file` against the forge's
bare repos that the sandboxed pair_loop worker cannot run. #369 embeds the source instead, so
the rewrite needs no forge access, and the work is done HERE. `ORIGINAL_SOURCE` below is that
embedded copy, and `selftest` check [0] proves it is the real forge blob by hashing it — see
THE EQUIVALENCE BASIS.)

WHAT THIS IS
------------
The original forge unit was 9204 bytes: the stable MCP entry point Claude Desktop is pointed
at. It read jazz's `build.json` to report the active versioned env, proxied two jazz MCP
services through FastMCP, mounted a `why5` root-cause toolset imported from the `coupler`
package, and bridged six tools onto a browser UI over HTTP.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and it adds the three things #200 requires that the
original lacked: it is part of a proper installable package, it is driven by a configuration
object, and it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
Quoted from ticket #369, which lowered the original with codebean's `lower_node` (#183):

    _load_build() -> dict
    _notes_python() -> str
    _jazz_client(module: str) -> Client
    async notes_db_proxy(tool: str, args: dict={}) -> str
    async z3_proxy(tool: str, args: dict={}) -> str
    _build_app()

`selftest` check [8] proves this rewrite presents that surface by re-lowering THIS FILE's own
AST the way #183 lowers a module and comparing to the six lines above, rather than asserting
it.

`notes_db_proxy` and `z3_proxy` keep the original's MUTABLE `{}` default. A shared mutable
default is normally a defect, and it is preserved deliberately: it is the surface this ticket
requires, and it is inert here because neither function mutates `args` — each only forwards
it. `selftest` proves the non-mutation rather than asserting it, so the surface can be kept
without carrying the bug that shape usually implies.

The original also bound three module-level names that a caller can read — `mcp`, `JAZZ_ROOT`
and `JAZZ_DEV`. All three are preserved; see divergence 3 for how, and why they are lazy.

THE EQUIVALENCE BASIS — THE ORIGINAL ITSELF IS THE ORACLE
----------------------------------------------------------
Ticket #369 captured NO behavioral exemplars ("no function in this module is minable"), and
says so explicitly: that "does NOT weaken the ticket's bar — it MOVES the work: you must write
the equivalence exemplars by hand from the original's behavior before rewriting, and they are
what settles this ticket."

This file goes further than a hand-written table, because a hand-written table is only ever as
good as its author's reading of the original. `ORIGINAL_SOURCE` below holds the original's own
9204 bytes verbatim, and `selftest`:

  0. HASHES them and checks the digest against the git blob sha1 ticket #369 names
     (`bbc6710713ca121196bdcabbc77a6fc638465666`). Git's blob sha1 is taken over
     `"blob <len>\\0" + bytes`, so reproducing it proves the embedded copy is the real forge
     blob, byte for byte — not a paraphrase, and not something drifted in transcription. If a
     byte were wrong the check fails loudly and every result below is void.
  1. EXECUTES them, and drives the ORIGINAL and this rewrite through the SAME scenarios with
     the SAME fakes standing in for fastmcp and httpx, then compares the outputs. The
     expectations are therefore not this author's belief about the original — they are taken
     from the original AS IT RUNS.

That the original can be run at all here is the point of the lazy-provider design below: the
fakes are injected under the names the original hardcodes (`fastmcp`, `httpx`), so the
original's own `import httpx` and `from fastmcp import FastMCP, Client` resolve to them. The
comparison is differential, over the banner, the registered tool names, every tool's exact
return value and type, the HTTP requests actually issued, and the client command strings.

WHY THIS MODULE IS IMPORTABLE WITHOUT FASTMCP (the central design decision)
--------------------------------------------------------------------------
The original did `import httpx` and `from fastmcp import FastMCP, Client` at module top level,
and built `mcp = FastMCP("coupler")` at IMPORT time. Neither package is installable in every
checkout this unit must run in — in the congruency checkout that executes this ticket,
`import fastmcp` and `import httpx` both fail — so the original module cannot even be IMPORTED
there, and nothing about it could be run or proven.

This rewrite therefore names those dependencies IN THE CONFIG (the `providers` block) and
resolves them LAZILY, on first use. Three consequences, all intended:

  * importing this module runs no third-party import and builds no server, so it imports
    cleanly anywhere and `selftest` can prove the unit's behavior with fakes standing in for
    FastMCP and httpx — including running the ORIGINAL against those same fakes;
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
    The JSON configuration registry described in this repository's `note-for-claude`: a single
    `.json` file at the root of a package holding the configuration for every tool in that
    package. `note-for-claude` states the contract this module obeys — ".json will have all the
    configuration - for all tools in this set of packaging. (a configuration registry) -if a
    tool cannot see the registry it will throw an exeption." [sic] This package ships its own
    `registry.json` at its root, one directory above this file.
config object
    The chunk of that registry belonging to this unit — the section at
    `forge2 -> code__code-invalid__coupler -> coupler.__main__`. It is what drives this module.
    `emit-config` prints a template of it. Sibling units in this package (`coupler`,
    `coupler.bridge`, ...) each read their OWN disjoint section, so adding this one disturbs
    none of them.
provider
    A dependency named by the config as a `"module:attr"` string (or a bare `"module"`), and
    imported on first use. `providers.server` is the FastMCP class, `providers.client` the
    Client class, and so on. Naming them in config is what lets the real fastmcp be used in
    production and fakes be used in `selftest`, through the SAME code path.
env-backed setting
    A setting written `{"env": "NAME", "default": ...}`. The original read a hardcoded
    environment variable with a hardcoded fallback; here BOTH the variable name and the
    fallback come from the config, so the env override keeps working and nothing is baked in.
why5
    A 5-why root-cause analysis toolset. The original imported it from the `coupler` PACKAGE
    (`from coupler.why5 import ...`) — see WHY5 below, where this unit differs from its
    near-twin in the sibling `forge2/coupler` package.
oracle
    The original, executed from `ORIGINAL_SOURCE`, used as the source of truth a check
    compares against. See THE EQUIVALENCE BASIS.

WHY5 — THIS UNIT IMPORTS IT FROM THE PACKAGE, AND INSERTS NOTHING ON sys.path
-----------------------------------------------------------------------------
This is the one place where a reader who knows the near-identical unit in the sibling
`forge2/coupler` package (ticket #403) must not pattern-match. That unit's original mutated
`sys.path` to reach why5 in the jazz DEV tree. THIS original does not:

    # ── why5 (ported into the coupler package; z3_mcp via forge editable) ─────
    try:
        from coupler.why5 import Why5, from_ci_failure, from_commit_failure

It is a plain package-relative import, with NO `sys.path` insert anywhere in the module. So
this rewrite performs no `sys.path` insert either — inventing one would be a side effect the
original does not have. The config's `why5` section names the MODULE only; there is no `path`
key, because there is no path to configure.

`coupler.why5` does not exist in this forge2 package: it is a DIFFERENT forge module with its
own rewrite ticket, and #369 "covers ONE module — the one identified below — and nothing
else." So this file does not ship one, and must not. The consequence is the original's own,
preserved exactly: the import fails, `_build_app` prints `  [warn] why5 not available: ...`
and mounts the six UI tools without the five why5 tools. `selftest` [7] proves the rewrite and
the original agree on that warning, and [7c] proves they agree tool-for-tool when a why5
module IS present, by staging a fake one for both.

`JAZZ_DEV` IS DEAD IN THE ORIGINAL, AND IS PRESERVED DEAD
---------------------------------------------------------
Because why5 comes from the package rather than from a path, the original's `JAZZ_DEV` global
is bound at import and then never read by any code in the module. It is still part of the
module's namespace, so it is still reachable here (`coupler.__main__.JAZZ_DEV`) and still
resolves `$JAZZ_DEV` against the same default. It drives nothing — in the original or here.
It is kept because removing a name a caller can read is a surface change, and it is documented
as dead so no reader concludes it was wired to something.

WHAT IS A SETTING, AND WHAT IS NOT
----------------------------------
#200 requires no hardcoded paths or params; it does not require inventing knobs the unit never
had. Settings are the things the original BAKED IN: the two jazz paths and their env var
names, the `conf/env/build.json` location, the `COUPLER_PYTHON` var, the server name, the
service map, the why5 module, the UI base URL and its 5-second timeout, and the fastmcp/httpx
dependencies. NOT settings, because they are the unit's structure rather than its
configuration: the names `Why5`, `from_ci_failure` and `from_commit_failure` that the why5
import binds, the tool names and their docstrings (Claude Desktop's tool surface), and the
shape of each tool's return string. Changing those would change behavior, which is what this
ticket exists to prevent.

`NOTES_DB_URL` is deliberately ABSENT from the config. The original's docstring advertised it
("NOTES_DB_URL   notes_db service URL   (default: http://127.0.0.1:8765)") but the original's
code never read it — it is documented-but-dead. Preserving behavior means not reading it
either, and #200 does not license inventing a setting the unit never had. It is recorded here
so a reader comparing the two docstrings does not think it was dropped by accident.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
This unit resolves its config object on first use, from the first source that answers:

  1. the file named by the `COUPLER_MAIN_CONFIG` environment variable. This file holds the unit
     config object itself — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code-invalid__coupler -> coupler.__main__` section of the
     nearest `registry.json` found by walking UP from THIS FILE's directory.

The walk-up starts at this file, never at the working directory, so which directory you run
from does not change what config is found.

If NEITHER answers, every operation raises `ConfigError` and does no work. It never guesses a
default — that is `note-for-claude`'s rule and this ticket's acceptance item (d). A config
object that is found but is missing a key an operation needs is also a `ConfigError`, naming
the key.

The variable is `COUPLER_MAIN_CONFIG` and not a name shared across this package because it
names a file holding ONE unit's config object: a shared variable could only ever point at one
unit's object at a time, so pointing it at a sibling's config would break this one. Each unit
in this package follows that rule with its own name (`coupler._config` uses `COUPLER_CONFIG`,
`coupler.bridge` uses `COUPLER_BRIDGE_CONFIG`).

This package ships `registry.json` at its root, so source 2 answers and the unit works from a
clean checkout with no setup. That shipped registry carries EXACTLY the values the original
hardcoded, which is what makes this rewrite behavior-preserving in practice: the values did
not change, only their location did. The registry is the config object this unit runs on; it
is not a fallback baked into the code. Delete it (with `COUPLER_MAIN_CONFIG` unset and no
other `registry.json` above this directory) and every operation throws — the gate is in the
code, not in the file's presence. `selftest` proves the gate directly, without deleting
anything, by pointing `COUPLER_MAIN_CONFIG` at a file that does not exist.

`configure(config)` and `using_config(config)` inject a config object directly, in-process, for
callers that hold their configuration in memory rather than on disk.

DELIBERATE, DOCUMENTED DIVERGENCES (three, and one config-shape choice)
----------------------------------------------------------------------
Everything else is intended to be indistinguishable from the original, and the differential in
`selftest` is what holds that claim up. These three are forced by the ticket's own
requirements, and each is proven by `selftest`:

  1. WHEN CONFIG IS READ. The original snapshotted `JAZZ_ROOT`/`JAZZ_DEV` into globals at
     IMPORT time, so mutating the environment after import had no effect on them. This rewrite
     snapshots its config and those paths on FIRST USE and caches them, so within a process the
     env-to-path resolution still happens exactly ONCE, as in the original. The only observable
     difference is confined to changing the environment between import and first call.
     `reset_config()` makes the snapshot explicit and re-resolvable, which is what lets
     `selftest` test the resolution at all.
     `_notes_python()` is the exception, and matches the original exactly: the original read
     `COUPLER_PYTHON` at CALL time, so this rewrite reads the env on every call too. That
     asymmetry between the two is the original's, faithfully kept, and [4] proves it.
  2. THE UI BANNER PORT. The original printed the literal `mounted      : ui (port 8142)` even
     when `JSON_CONTROLS_URL` pointed somewhere else — a hardcoded param, and one that printed
     a falsehood whenever it was overridden. Requirement 4 forbids keeping it, so the port is
     derived from the UI base actually in force. With the shipped config's base
     (`http://127.0.0.1:8142`) the line is BYTE-IDENTICAL to the original's, which [7] proves
     against the oracle; with any other base it prints the truth instead of `8142`, which [7e]
     proves is the ONE line where the two intentionally disagree. A base with no port prints
     its host.
  3. IMPORT-TIME CONSTRUCTION. The original built `mcp = FastMCP("coupler")` at import,
     registered the two proxy tools onto it with `@mcp.tool()`, and bound `JAZZ_ROOT` and
     `JAZZ_DEV` at import too. Doing any of that as a side effect of an import is exactly what
     makes the original unimportable without fastmcp and unconfigurable without an env, so all
     three are lazy module attributes here (PEP 562 `__getattr__`):

       - the FIRST access to `mcp` builds the server, names it from the config, and registers
         `notes_db_proxy` and `z3_proxy` onto it — the same server, with the same two tools,
         built at first touch instead of at import. [7f] proves it against the oracle's `mcp`.
       - `JAZZ_ROOT` and `JAZZ_DEV` resolve their env-backed settings on first access and cache
         them, so they are the same `Path` objects the original bound. [3c] proves both against
         the oracle's globals.

     Accessing any of them without config raises `ConfigError` rather than yielding a
     half-configured value.
     A knock-on benefit: `notes_db_proxy` and `z3_proxy` are plain async functions here, so
     they are directly callable and directly testable, whereas `@mcp.tool()` may replace the
     name it decorates with a framework object depending on the fastmcp version.

AND the one config-shape choice, recorded here so nothing is hidden: the original wrote each
downstream module name TWICE — `"notes_db_mcp"` inside `notes_db_proxy` and again in
`_build_app`'s `services` map — so the two could drift apart. Here the `services` map is the
single source for both. Under the shipped config, which carries the original's own values,
every call site resolves to exactly the string the original hardcoded, so no behavior changes;
what changes is that re-pointing a service now moves its proxy with it instead of leaving the
two disagreeing. This is a consequence of requirement 4 (the names had to leave the code), not
an independent redesign.

RUNNING IT
----------
Every command below is executable as written from THIS FILE's own directory; from anywhere
else, give the full path to `__main__.py` instead of the bare name. Which directory you run
from does not change what config is found — the registry walk-up starts at THIS FILE, never at
the working directory.

    python3 __main__.py selftest       # prove the behavior against the original, and the gate
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
This file is one module of the package that surrounds it, and the package is committed in full
around it — `pyproject.toml`, `registry.json`, `coupler/__init__.py` and its siblings. From the
PACKAGE ROOT (the directory above this one, the one holding `pyproject.toml`):

    pip install -e .
    forge2-coupler selftest
    forge2-coupler serve               # the stable MCP entry point Claude Desktop calls

`pyproject.toml` declares the `forge2-coupler` console script pointing at `main()` below, so
Claude Desktop can be pointed at a stable command instead of a path into a checkout. Because
this module is the `coupler` package's `__main__`, `python3 -m coupler` also runs it — which is
the very form this unit's own proxies use to launch downstream services.

`pyproject.toml` also had to LEARN about the `coupler` directory. Its scaffolding enumerates
only the `.py` files sitting directly in the package root, so before #369 it declared just the
root package and NOTHING under `coupler/` was installed at all — `import coupler` worked from a
checkout (the working directory is on `sys.path`) and failed from an install, which would have
made this console script unrunnable. #369 adds `coupler` (and `coupler.tests`) to `packages`.
That is additive: no sibling's behavior changes, and every sibling unit's own selftest reaches
the identical verdict before and after.

ONE HONEST LIMIT — a NON-EDITABLE INSTALL NEEDS ITS CONFIG NAMED
----------------------------------------------------------------
`registry.json` sits at the PACKAGE ROOT, beside `pyproject.toml`, one directory ABOVE the
`coupler` import package. An editable install (`pip install -e .` — what acceptance item (c)
requires, and what the commands above are verified under) leaves this file in the checkout, so
the walk-up finds it and everything works, console script included.

A non-editable `pip install .` succeeds and installs this module, but it copies `coupler/` into
site-packages WITHOUT that root, so nothing under `coupler/` can walk up to a registry. What
then happens, precisely:

  * `python3 <site-packages>/coupler/__main__.py selftest` still passes — `selftest` needs no
    config — and `emit-config` still prints its template. `show-config` and `serve` exit 2 with
    this module's one-line config error. That is the gate working.
  * the `forge2-coupler` console script, however, does NOT reach this module's error handling.
    It imports `coupler.__main__`, which imports the `coupler` PACKAGE, and the sibling
    `coupler/__init__.py` (ticket #397) runs its OWN config gate at import — so the failure is
    that sibling's `ConfigError` traceback, raised before `main()` is ever called. The message
    names `COUPLER_CONFIG`, which is #397's variable, not this unit's.
  * setting BOTH `COUPLER_MAIN_CONFIG` (this unit) and `COUPLER_CONFIG` (the sibling) makes the
    console script work from a non-editable install; `emit-config` prints what the first one
    wants.

This is recorded rather than fixed because both fixes are out of bounds for #369. Shipping a
copy of `registry.json` inside `coupler/` would put it EARLIER in the walk-up than the root one
for every sibling in this package — their resolution starts at `coupler/_config.py` — silently
changing which config document they read. And the import-time gate belongs to #397's module.
#369 "covers ONE module — the one identified below — and nothing else."

SIDE EFFECTS
------------
`selftest`, `emit-config` and `show-config` create no files and write nothing outside a temp
directory that is removed. `_build_app()` prints its diagnostic banner to stderr; unlike its
near-twin in the sibling `forge2/coupler` package it does NOT touch `sys.path`, because this
original does not (see WHY5). Per `note-for-claude` ("all tools need to pass a bug-report
automatically ... if an exception is thrown") the CLI appends one timestamped JSON line to the
config's `bug_reports` path if it hits an UNEXPECTED exception — that is, a defect in this
tool. A `ConfigError` is designed behavior, not a bug: it files no report and prints no
traceback, and exits 2 with a single self-explaining line.

Importing this module reads no file and imports nothing outside the standard library. The one
thing that appears on disk when you import it is CPython's own `coupler/__pycache__/*.pyc`
bytecode cache, which the interpreter writes for any module it imports and which `.gitignore`
excludes — named here rather than claimed away, because "creates no files" would otherwise be
false.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import contextlib
import hashlib
import importlib
import inspect
import io
import json
import os
import sys
import tempfile
import traceback
import types
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

__all__ = [
    "notes_db_proxy", "z3_proxy",
    "ConfigError", "load_config", "configure", "using_config", "reset_config",
]

#: Environment variable naming a file that holds this unit's config object. See CONFIGURATION
#: in the module docstring for why the name is specific to this unit rather than shared.
CONFIG_ENV = "COUPLER_MAIN_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in
#: the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own. It is disjoint from every sibling unit's section.
UNIT_PATH = ("forge2", "code__code-invalid__coupler", "coupler.__main__")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code-invalid__coupler/coupler/__main__"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and ticket #369's acceptance item (d): a tool that
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
    # section may state its own to override it. This is inheritance inside ONE config document,
    # not a guessed default — if neither states it, the key stays absent and the CLI files no
    # report.
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
    """Drop the injected config, the cached disk resolution, and every cached snapshot; the next
    call re-resolves from scratch."""
    global _ACTIVE, _RESOLVED
    _ACTIVE = None
    _RESOLVED = None
    _invalidate()


def _invalidate():
    """Clear the caches that hang off a config object (see divergence 1: the paths, the
    providers and the server are snapshotted on first use, so changing the config must drop
    them)."""
    _PROVIDER_CACHE.clear()
    _PATH_CACHE.clear()
    global _SERVER
    _SERVER = None


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
    return _env_backed_spec(spec, key, operation)


def _env_backed_spec(spec, key, operation):
    """The body of `_env_backed`, over a spec already in hand (so a nested section can reuse it)."""
    if not isinstance(spec, dict):
        raise ConfigError(
            "config key %r for %s must be a JSON object like {\"env\": \"NAME\", "
            "\"default\": ...}, not %s" % (key, UNIT, type(spec).__name__)
        )
    if "default" not in spec:
        raise ConfigError(
            "config key '%s.default' for %s is required (use null to mean 'no default'); run "
            "`emit-config` for a template." % (key, UNIT)
        )
    name = spec.get("env")
    if name:
        value = os.environ.get(name)
        if value is not None:
            return value, True
    return spec["default"], False


def _env_backed_in(section_key, section, key, operation):
    """Resolve an env-backed setting nested inside a config section (e.g. `ui.base`)."""
    spec = _require(section, key, operation)
    return _env_backed_spec(spec, "%s.%s" % (section_key, key), operation)


# ─────────────────────────────── providers ───────────────────────────────

_PROVIDER_CACHE = {}


def _load_target(spec, what):
    """Resolve a `"module:attr"` string to the attribute it names, or a bare `"module"` to the
    module itself.

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

    This is where `fastmcp` and `httpx` enter. The original imported them at module top level,
    which made the module unimportable without them; naming them in config and importing here
    means this module imports anywhere, the shipped config reproduces the original's
    dependencies exactly, and `selftest` can substitute fakes through the very same code path —
    the same fakes the ORACLE runs against.
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
                "config object for %s is missing the key 'providers.%s'. Run `emit-config` for "
                "a template." % (UNIT, name)
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
        first use is the closest faithful equivalent (divergence 1); `reset_paths()` drops the
        snapshot.
      * `~` is expanded ONLY in the config's default, never in an env value. The original wrote
        `Path(os.environ.get("JAZZ_ROOT", Path.home() / "code/workspace/main"))`: the built-in
        default came from `Path.home()` and so was already absolute, while an env value was
        handed to `Path()` VERBATIM — so `JAZZ_ROOT=~/foo` meant a directory literally named
        `~`, not a path under the user's home. The config's `default` stands in for the
        `Path.home()` expression and is therefore tilde-expanded; an env value is used raw, as
        the original used it. `selftest` [3b] proves both halves against the oracle.
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


def reset_paths():
    """Drop the cached jazz-path snapshots (see divergence 1), so a caller can re-resolve them.

    `_jazz_path` caches to mirror the original's import-time snapshot; a test that moves
    `$JAZZ_ROOT` between checks has to clear that cache, exactly as a new process would.
    """
    _PATH_CACHE.clear()


# ─────────────────────────────── the unit itself ───────────────────────────────

def _load_build() -> dict:
    """Return the parsed jazz `build.json`, or `{}` when there is no such file.

    The file is the config's `build_json` path resolved under the configured jazz root
    (`$JAZZ_ROOT` by default). A file that exists but does not hold JSON raises, exactly as the
    original's `json.loads` did — a corrupt build file is an error, not an empty dict. The
    `-> dict` annotation is the original's and is kept for the surface; like the original, this
    returns whatever the JSON document holds, so a file containing a JSON array yields a list.

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

    They run under the SAME venv as the coupler — whatever Python is running this — unless the
    config's `python.env` variable (`COUPLER_PYTHON` by default) names another. The original
    read that variable on every call rather than snapshotting it, so this does too (divergence
    1); the config's `python.default` of `null` means "this interpreter", i.e. `sys.executable`.

    (Historically the original hunted a conda env via build.json; conda is gone since old_jazz,
    so that path was dead and is not resurrected here.)

    Raises:
        ConfigError: if no config object can be resolved.
    """
    value, _from_env = _env_backed("python", "_notes_python")
    return sys.executable if value is None else value


def _jazz_client(module: str) -> Client:  # noqa: F821 — see the note below
    """Return a client that launches `python -m <module>` as a downstream MCP service.

    The command is the configured interpreter, then `-m`, then the module — the one-string form
    the original passed to `Client`.

    The `-> Client` annotation is the original's and is part of the surface this ticket
    requires. `Client` is not imported at module level here (that is the whole point — see the
    module docstring), so this annotation is never evaluated: `from __future__ import
    annotations` keeps every annotation a string. The class itself is the config's
    `providers.client`.

    Raises:
        ConfigError: if no config object can be resolved, or `providers.client` is missing or
            cannot be imported.
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

    The original hardcoded `"notes_db_mcp"` and `"z3_mcp"` in two places each: once in a proxy
    tool and once in the `services` map that `_build_app` mounts. Here the `services` map is the
    single source for both, so the proxy and the mount can never disagree.
    """
    services = _services(operation)
    if name not in services:
        raise ConfigError(
            "config object for %s is missing the service %r under 'services', which %s forwards "
            "to. Run `emit-config` for a template." % (UNIT, name, operation)
        )
    return services[name]


def _services(operation):
    """Return the config's service map: display name -> downstream module name.

    Keys starting with `_` are dropped. This repository's registry idiom embeds `_comment` keys
    inside the objects they describe, and every OTHER key here is a service that `_build_app`
    will mount — so without this rule a comment would be mounted as a service.
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


# ── the module-level names (divergence 3: lazily built, not built at import) ──

_SERVER = None


def _server():
    """Build (once) the module-level MCP server the original created at import time.

    The original's `mcp = FastMCP("coupler")` plus `@mcp.tool()` on the two proxies produced a
    server named by the config's `server_name` carrying exactly `notes_db_proxy` and `z3_proxy`.
    This produces the same thing on first access; see divergence 3.
    """
    global _SERVER
    if _SERVER is None:
        FastMCP = _provider("server")
        server = FastMCP(_setting("server_name", "the module-level server"))
        server.tool()(notes_db_proxy)
        server.tool()(z3_proxy)
        _SERVER = server
    return _SERVER


#: The module-level names the original bound at import, and how each is produced on first
#: access. See divergence 3. `JAZZ_DEV` is dead in the original and is preserved dead — it
#: resolves, and nothing reads it.
_LAZY_ATTRS = {
    "mcp": lambda: _server(),
    "JAZZ_ROOT": lambda: _jazz_path("jazz_root"),
    "JAZZ_DEV": lambda: _jazz_path("jazz_dev"),
}


def __getattr__(name):
    """Provide the original's import-time module attributes lazily (PEP 562).

    The original bound `mcp`, `JAZZ_ROOT` and `JAZZ_DEV` as a side effect of being imported.
    Doing that at import is what this rewrite exists to avoid, so each is produced on first
    ATTRIBUTE ACCESS instead and then cached — `coupler.__main__.mcp` is the same server with
    the same two tools, and the two paths are the same `Path` objects. Without a config (or,
    for `mcp`, without a working fastmcp) touching one raises ConfigError rather than yielding a
    half-configured value.
    """
    if name in _LAZY_ATTRS:
        return _LAZY_ATTRS[name]()
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    """List the lazy attributes alongside the real ones, so `dir()` and tab-completion show the
    module-level names the original bound. `__getattr__` alone leaves them invisible."""
    return sorted(list(globals()) + list(_LAZY_ATTRS))


# ─────────────────── mount jazz services as proper proxies ───────────────────

def _build_app():
    """Build the coupler app: the proxied jazz services, why5, and the UI bridge.

    Prints the original's diagnostic banner to stderr as it goes, and returns the app.
    Everything it mounts is driven by the config object; nothing is hardcoded. The mount, why5
    and UI sections each preserve the original's failure behavior exactly — see the comments at
    each, and `selftest` [7], which compares this function's whole observable output against the
    original's.

    Raises:
        ConfigError: if no config object can be resolved, or a key/provider it needs is missing
            or cannot be imported.
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

    # Resolved OUTSIDE the per-service try, because the original's `from fastmcp.server import
    # create_proxy` sat outside its try too: if the proxy factory is unavailable, _build_app
    # fails rather than quietly mounting nothing.
    create_proxy = _provider("create_proxy")
    Client = _provider("client")
    StdioTransport = _provider("stdio_transport")

    for name, module in services.items():
        # The original gated each mount on the interpreter path existing, and skipped SILENTLY
        # when it did not — no "mounted" line and no warning. Preserved.
        if Path(python).exists():
            try:
                proxy = create_proxy(
                    Client(StdioTransport(command=python, args=["-m", module]))
                )
                app.mount(proxy, namespace=name)
                print(f"  mounted      : {name} ({module})", file=sys.stderr)
            except Exception as e:
                print(f"  [warn] could not mount {name}: {e}", file=sys.stderr)

    # ── why5 (ported into the coupler package; z3_mcp via forge editable) ─────
    # The original's import is `from coupler.why5 import Why5, from_ci_failure,
    # from_commit_failure` — a plain package import with NO sys.path insert. This rewrite
    # inserts nothing either; see WHY5 in the module docstring.
    why5 = _setting("why5", "_build_app")
    if not isinstance(why5, dict):
        raise ConfigError(
            "config key 'why5' for %s must be a JSON object, not %s" % (UNIT, type(why5).__name__)
        )
    why5_module_name = _require(why5, "module", "_build_app")
    try:
        why5_module = _import_module_like_from(why5_module_name)
        # Reproduces `from coupler.why5 import Why5, from_ci_failure, from_commit_failure`.
        # `from_commit_failure` is imported and never used — in the original too — and that is
        # behavior, not dead weight: if the why5 module lacks it, the import fails and NOTHING
        # why5-related mounts. Dropping it would mount why5 where the original did not.
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
        # Delegates to the same `str.lower()`, `int()` and `float()` the original used, in the
        # same order, so every quirk of the original's coercion survives unchanged: "TRUE" is
        # True, "1_0" is the int 10, "1e3" is the float 1000.0, "inf" is a float infinity, and
        # anything all three reject stays the string it was. [7d] proves the table against the
        # oracle rather than against this comment.
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


def _import_module_like_from(name):
    """Import `name` the way `from <name> import ...` would.

    `importlib.import_module` is the honest equivalent of the original's `from coupler.why5
    import ...` for the module-loading half: both import the parent package first and both
    raise ImportError (ModuleNotFoundError) when it cannot be found, which `_build_app`'s
    `except Exception` then reports as `[warn] why5 not available: <e>`. Going through
    `__import__` instead would hand back the ROOT package rather than the submodule.

    A module already in `sys.modules` is returned as-is, exactly as the import statement would
    — that is what lets `selftest` stage a fake `coupler.why5` for the oracle and the rewrite
    alike.
    """
    module = sys.modules.get(name)
    if module is not None:
        return module
    return importlib.import_module(name)


def _from_import(module, name):
    """Get `name` off `module`, raising ImportError — not AttributeError — when it is absent.

    `from X import a, b, c` raises ImportError for a missing name, and `_build_app`'s why5 block
    reports whatever the import raises in its `[warn] why5 not available:` line. Going through
    getattr would raise AttributeError and change that line, so the ImportError is reconstructed
    here with the phrasing the `from ... import` form uses. `selftest` [7b] proves the resulting
    warning is byte-identical to the original's, which is the only reason to believe this
    reconstruction is right.
    """
    try:
        return getattr(module, name)
    except AttributeError:
        raise ImportError(
            "cannot import name %r from %r (%s)"
            % (name, module.__name__, getattr(module, "__file__", "unknown location"))
        ) from None


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


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do every operation throws. The values below are the
    ones the ORIGINAL hardcoded, so a config built from this template makes the rewrite behave
    exactly as the original did.

    Note what is NOT here: no `why5.path`. This unit's original imports why5 from the `coupler`
    package and touches no `sys.path`, so there is no path to configure (see WHY5).
    """
    return {
        "server_name": "coupler",
        "jazz_root": {"env": "JAZZ_ROOT", "default": "~/code/workspace/main"},
        "jazz_dev": {"env": "JAZZ_DEV", "default": "~/code/jazz"},
        "build_json": "conf/env/build.json",
        "python": {"env": "COUPLER_PYTHON", "default": None},
        "services": {"notes_db": "notes_db_mcp", "z3": "z3_mcp"},
        "why5": {"module": "coupler.why5"},
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


# ═════════════════════════ the original, embedded verbatim ═════════════════════════
#
# Ticket #369's own words: "THE ORIGINAL SOURCE, EMBEDDED — YOU NEED NO FORGE ACCESS TO DO THIS
# TICKET. The module's own bytes are reproduced below, inside this ticket. THEY are the
# authoritative copy and the behavior-preserving basis." They are reproduced here for the same
# reason: so this file's equivalence claim can be CHECKED by whoever reads it, with no forge
# access and no trust in the author. `selftest` [0] hashes these bytes and [1..8] run them.

ORIGINAL_SOURCE = '''#!/usr/bin/env python3
"""
coupler — stable MCP entry point for Claude Desktop.

Reads jazz build.json to find the active versioned env, then proxies
all jazz MCP services through FastMCP. Claude Desktop always points here.
Jazz installs come and go — this never changes.

Environment:
  JAZZ_ROOT      path to jazz checkout  (default: ~/code/workspace/main)
  JAZZ_DEV       path to jazz dev repo  (default: ~/code/jazz)
  NOTES_DB_URL   notes_db service URL   (default: http://127.0.0.1:8765)
  JSON_CONTROLS_URL  browser UI URL     (default: http://127.0.0.1:8142)
"""

import json
import os
import sys
from pathlib import Path

import httpx
from fastmcp import FastMCP, Client
from fastmcp.client.transports import StdioTransport

# ── Resolve jazz paths ────────────────────────────────────────────────────────

JAZZ_ROOT = Path(os.environ.get("JAZZ_ROOT", Path.home() / "code/workspace/main"))
JAZZ_DEV  = Path(os.environ.get("JAZZ_DEV",  Path.home() / "code/jazz"))

def _load_build() -> dict:
    p = JAZZ_ROOT / "conf/env/build.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}

def _notes_python() -> str:
    """Interpreter used to launch downstream MCP subprocesses.

    They run under the SAME venv as the coupler — whatever Python is running this.
    (Historically this hunted a conda env via build.json; conda is gone since old_jazz,
    so that path was dead.) Override with COUPLER_PYTHON if a downstream needs a
    different interpreter.
    """
    return os.environ.get("COUPLER_PYTHON", sys.executable)

# ── MCP server ────────────────────────────────────────────────────────────────

mcp = FastMCP("coupler")

# ── Proxy jazz MCP services ───────────────────────────────────────────────────

def _jazz_client(module: str) -> Client:
    python = _notes_python()
    return Client(f"{python} -m {module}")


@mcp.tool()
async def notes_db_proxy(tool: str, args: dict = {}) -> str:
    """Forward a tool call to the notes_db_mcp service."""
    async with _jazz_client("notes_db_mcp") as c:
        result = await c.call_tool(tool, args)
        return str(result)


@mcp.tool()
async def z3_proxy(tool: str, args: dict = {}) -> str:
    """Forward a tool call to the z3_mcp service."""
    async with _jazz_client("z3_mcp") as c:
        result = await c.call_tool(tool, args)
        return str(result)


# ── Mount jazz services as proper proxies (exposes their tools natively) ──────

def _build_app():
    python = _notes_python()
    build  = _load_build()
    version = build.get("version", "unknown")

    print(f"  coupler starting", file=sys.stderr)
    print(f"  jazz version : {version}", file=sys.stderr)
    print(f"  notes python : {python}", file=sys.stderr)

    app = FastMCP("coupler")

    # mount each jazz service — tools appear natively in Claude
    services = {
        "notes_db": "notes_db_mcp",
        "z3":       "z3_mcp",
    }

    from fastmcp.server import create_proxy

    for name, module in services.items():
        if Path(python).exists():
            try:
                proxy = create_proxy(
                    Client(StdioTransport(command=python, args=["-m", module]))
                )
                app.mount(proxy, namespace=name)
                print(f"  mounted      : {name} ({module})", file=sys.stderr)
            except Exception as e:
                print(f"  [warn] could not mount {name}: {e}", file=sys.stderr)

    # ── why5 (ported into the coupler package; z3_mcp via forge editable) ─────
    try:
        from coupler.why5 import Why5, from_ci_failure, from_commit_failure
        _why5_sessions: dict = {}

        @app.tool()
        def why5_new(session_id: str, trigger: str = "") -> str:
            """Start a new 5-why root cause analysis session."""
            _why5_sessions[session_id] = Why5(session_id=session_id, trigger=trigger)
            return f"why5 session '{session_id}' started"

        @app.tool()
        def why5_fact(session_id: str, name: str, value: bool) -> str:
            """Assert a known observable fact into a why5 session."""
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

    # ── UI bridge (httpx, always direct) ─────────────────────────────────────
    UI_BASE    = os.environ.get("JSON_CONTROLS_URL", "http://127.0.0.1:8142")
    UI_TIMEOUT = 5.0

    def _ui_get(path, **params):
        r = httpx.get(f"{UI_BASE}{path}", params=params, timeout=UI_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def _ui_post(path, body):
        r = httpx.post(f"{UI_BASE}{path}", json=body, timeout=UI_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def _ui_put(path, body):
        r = httpx.put(f"{UI_BASE}{path}", json=body, timeout=UI_TIMEOUT)
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
        parsed: object = value
        if value.lower() == "true":    parsed = True
        elif value.lower() == "false": parsed = False
        else:
            try: parsed = int(value)
            except ValueError:
                try: parsed = float(value)
                except ValueError: pass
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

    print(f"  mounted      : ui (port 8142)", file=sys.stderr)
    return app


if __name__ == "__main__":
    app = _build_app()
    app.run()
'''

#: The git blob sha1 ticket #369 records for the original, under CANONICAL SOURCE:
#: `blob : bbc6710713ca121196bdcabbc77a6fc638465666`. Git hashes a blob as
#: sha1("blob " + len + "\0" + bytes), so reproducing this digest from ORIGINAL_SOURCE proves
#: the embedded copy is that exact forge object.
ORIGINAL_BLOB_SHA1 = "bbc6710713ca121196bdcabbc77a6fc638465666"

#: The byte length ticket #369 records for the original, under SIZE.
ORIGINAL_SIZE = 9204


def original_bytes():
    """Return the embedded original as the bytes git hashed.

    `ORIGINAL_SOURCE` is a str literal, so it is encoded UTF-8 — the encoding the original's own
    non-ASCII box-drawing and arrow characters are written in, and the encoding `Path.read_text`
    would have handed the interpreter.
    """
    return ORIGINAL_SOURCE.encode("utf-8")


def original_blob_sha1():
    """Return the git blob sha1 of the embedded original, computed the way git computes it."""
    data = original_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def verify_original():
    """Prove the embedded original is the forge blob ticket #369 names.

    Returns a list of failure strings; empty means the embedded copy is byte-identical to the
    object at `bbc6710713ca121196bdcabbc77a6fc638465666`. Every equivalence claim this file
    makes rests on this, so it is check [0] and it is checked before anything else runs.
    """
    problems = []
    size = len(original_bytes())
    if size != ORIGINAL_SIZE:
        problems.append("embedded original is %d bytes; ticket #369 records %d"
                        % (size, ORIGINAL_SIZE))
    got = original_blob_sha1()
    if got != ORIGINAL_BLOB_SHA1:
        problems.append("embedded original hashes to git blob %s; ticket #369 records %s"
                        % (got, ORIGINAL_BLOB_SHA1))
    return problems


# ═══════════════════════════════ the selftest ═══════════════════════════════
#
# The fakes below stand in for FastMCP and httpx. They are reached the SAME way the real
# dependencies are — the config names them as providers for the rewrite, and they are injected
# into sys.modules under the names the ORIGINAL hardcodes — so the selftest exercises the real
# code path of BOTH programs rather than a parallel one.
#
# #369 captured no behavioral exemplars ("no function in this module is minable"), so per the
# ticket the equivalence cases below were written by hand from the original's behavior. They are
# not, however, hand-computed: every expected value is read off the ORIGINAL AS IT RUNS. See THE
# EQUIVALENCE BASIS in the module docstring.

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

    @classmethod
    def reset(cls):
        cls.built = []
        cls.calls = []


def _fake_create_proxy(client):
    return ("proxy", client)


def _exploding_create_proxy(_client):
    """A create_proxy that raises, to prove _build_app's per-service warn-and-continue."""
    raise RuntimeError("kaboom")


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


#: The module name the ORIGINAL hardcodes for why5, and its parent package. The oracle imports
#: exactly this, so the selftest stages a fake under this name for BOTH programs — that is what
#: makes the why5 comparison a fair one rather than two different experiments.
WHY5_MODULE = "coupler.why5"
WHY5_PARENT = "coupler"


def _make_fake_why5(name, complete=True):
    """Build (but do not install) a fake why5 module.

    `complete=False` omits `from_commit_failure`, which is how the selftest proves that the
    unused import is load-bearing: without it the why5 mount must fail in BOTH programs.
    """
    module = types.ModuleType(name)
    module.__file__ = "<selftest fake %s>" % name
    module.Why5 = _FakeWhy5Session
    module.from_ci_failure = _fake_from_ci_failure
    if complete:
        module.from_commit_failure = _fake_from_commit_failure
    return module


# ────────────────────────── the oracle: the original, running ──────────────────────────

#: Distinct from `_MISSING`: this one means "stage NO why5 module at all", which is a
#: meaningful scenario rather than a missing result.
_NO_WHY5 = object()


@contextlib.contextmanager
def _stubbed_world(why5=_NO_WHY5):
    """Install this file's fakes under the names the ORIGINAL hardcodes, then restore.

    The original does `import httpx`, `from fastmcp import FastMCP, Client`, `from
    fastmcp.client.transports import StdioTransport`, `from fastmcp.server import create_proxy`
    and `from coupler.why5 import ...`. Pre-seeding `sys.modules` with modules under exactly
    those names makes every one of those statements resolve to a fake, WITHOUT touching the real
    fastmcp/httpx (which are not installed here anyway) and without importing the real `coupler`
    package.

    `why5` is the fake why5 module to publish as `coupler.why5`, or the sentinel default to
    publish NONE — which is what makes the original's `from coupler.why5 import ...` fail, the
    situation that holds in this package today.

    Every `sys.modules` key touched is saved and restored, including deleting keys that did not
    exist before, so the selftest leaves the import system exactly as it found it.
    """
    names = ["fastmcp", "fastmcp.client", "fastmcp.client.transports", "fastmcp.server",
             "httpx", WHY5_PARENT, WHY5_MODULE]
    saved = {name: sys.modules.get(name) for name in names}

    fastmcp = types.ModuleType("fastmcp")
    fastmcp.FastMCP = _FakeServer
    fastmcp.Client = _FakeClient
    fastmcp.__path__ = []
    client_pkg = types.ModuleType("fastmcp.client")
    client_pkg.__path__ = []
    transports = types.ModuleType("fastmcp.client.transports")
    transports.StdioTransport = _FakeStdioTransport
    client_pkg.transports = transports
    fastmcp.client = client_pkg
    server_mod = types.ModuleType("fastmcp.server")
    server_mod.create_proxy = _fake_create_proxy
    fastmcp.server = server_mod

    try:
        sys.modules["fastmcp"] = fastmcp
        sys.modules["fastmcp.client"] = client_pkg
        sys.modules["fastmcp.client.transports"] = transports
        sys.modules["fastmcp.server"] = server_mod
        sys.modules["httpx"] = _FakeHttp
        if why5 is _NO_WHY5:
            # No why5 at all: drop both names so the oracle's import genuinely fails, as it does
            # in this package today. The real `coupler` package must not be reachable either —
            # importing it would run its own config gate and change what is being measured.
            parent = types.ModuleType(WHY5_PARENT)
            parent.__path__ = []
            sys.modules[WHY5_PARENT] = parent
            sys.modules.pop(WHY5_MODULE, None)
        else:
            parent = types.ModuleType(WHY5_PARENT)
            parent.__path__ = []
            parent.why5 = why5
            sys.modules[WHY5_PARENT] = parent
            sys.modules[WHY5_MODULE] = why5
        yield
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def _oracle():
    """Execute the embedded ORIGINAL in a fresh namespace and return it as a module.

    Must be called inside `_stubbed_world()`. A FRESH exec per scenario is what makes the
    comparison fair: the original resolves `JAZZ_ROOT`/`JAZZ_DEV` and builds `mcp` at IMPORT
    time, so re-importing it is how a test moves those — exactly as a new process would, and
    exactly what `reset_config()`/`reset_paths()` do for the rewrite (divergence 1).
    """
    module = types.ModuleType("_coupler_original_oracle")
    module.__file__ = "<ticket #369 ORIGINAL_SOURCE>"
    exec(compile(ORIGINAL_SOURCE, module.__file__, "exec"), module.__dict__)
    return module


def _oracle_build_app():
    """Run the ORACLE's `_build_app()`, returning `(app, banner_lines)`.

    Must be called inside `_stubbed_world()`. The app comes back as a `_Raised` if the build
    raised — see `_rewrite_build_app` for why both sides are guarded.
    """
    module = _oracle()
    banner = io.StringIO()
    with contextlib.redirect_stderr(banner):
        app = _attempt(module._build_app)
    return app, banner.getvalue().splitlines()


def _rewrite_build_app():
    """Run THIS rewrite's `_build_app()`, returning `(app, banner_lines)`.

    Guarded exactly as `_oracle_build_app` is: `_build_app` RAISING where the original did not
    is a difference the differential must REPORT as a failing check, not something that aborts
    `selftest` with a traceback and hides every check behind it. "The app raised" is then just
    another outcome the two programs are compared on — and since `_Raised` compares by type and
    message, two builds that raise identically still agree.

    The caller must have a config in force.
    """
    banner = io.StringIO()
    with contextlib.redirect_stderr(banner):
        app = _attempt(_build_app)
    return app, banner.getvalue().splitlines()


def _app_tools(app):
    """Sorted tool names of an app, or the `_Raised` it came back as instead.

    Lets a check compare tool surfaces without first having to prove the build succeeded — a
    build that raised simply compares unequal to one that did not.
    """
    if isinstance(app, _Raised):
        return app
    return sorted(app.tools)


def _app_mounts(app):
    """Mounted namespaces of an app, or the `_Raised` it came back as instead."""
    if isinstance(app, _Raised):
        return app
    return [namespace for namespace, _proxy in app.mounts]


# ────────────────────────── the surface ──────────────────────────

#: THE CALLABLE SURFACE, quoted verbatim from ticket #369 — the six signatures codebean's
#: `lower_node` (#183) produced from the ORIGINAL's AST, in the ticket's own order. Acceptance
#: item (b) is that this rewrite "presents the callable surface above, so existing callers keep
#: working", and `_lower_surface` below lowers THIS file the same way to prove it.
SURFACE = [
    "_load_build() -> dict",
    "_notes_python() -> str",
    "_jazz_client(module: str) -> Client",
    "async notes_db_proxy(tool: str, args: dict={}) -> str",
    "async z3_proxy(tool: str, args: dict={}) -> str",
    "_build_app()",
]


def _lower_surface(source, filename="<source>"):
    """Lower every TOP-LEVEL function in `source` to the ticket's signature form.

    Mirrors codebean's `lower_node` (#183) closely enough to be compared against the ticket's
    own output: an `async ` prefix for a coroutine, `name(params) -> returns`, each parameter as
    `name: annotation=default` with annotations and defaults unparsed straight from the AST, and
    no ` -> ` at all when the function has no return annotation.

    Only module-level defs are lowered — the tools nested inside `_build_app` are that
    function's internals, not the module's surface.
    """
    tree = ast.parse(source, filename=filename)

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


def _global_reads(source):
    """Count how many times each name is READ (loaded) in `source`, per its AST.

    Used to prove from the original itself which of its module-level globals are live and which
    are dead, instead of taking anyone's word for it. A name is read exactly when it appears as
    an `ast.Name` in a `Load` context; the binding `JAZZ_DEV = ...` is a `Store`, the `"JAZZ_DEV"`
    inside `os.environ.get(...)` is a string constant, and the one in the module docstring is
    prose — none of the three is a read, which is why grepping for the name cannot answer this
    and the AST can.
    """
    counts = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            counts[node.id] = counts.get(node.id, 0) + 1
    return counts


def _fake_config(**overrides):
    """The config template, rewired onto this module's fakes.

    The providers point at the very same fake classes `_stubbed_world` publishes as `fastmcp`
    and `httpx`, so the rewrite and the oracle are driven by ONE set of fakes and a difference
    in output can only come from a difference in the two programs.
    """
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
    """Prove this rewrite against ticket #369's acceptance items (a), (b) and (d).

    Builds its own config objects in memory and its own temp trees, so it needs no registry,
    needs neither fastmcp nor httpx, writes no files outside a temp dir it removes, and leaves
    no configuration, environment variable or `sys.modules` entry behind. Returns the number of
    failures.

    Almost every check below is DIFFERENTIAL: it runs the embedded ORIGINAL and this rewrite
    through the same scenario with the same fakes and compares. Where a check states a literal
    expectation instead, it is because the property is about this rewrite's own additions (the
    config gate) or about the ticket's text (the surface).

    Checks, in order:
      0. the embedded original is the forge blob #369 names — everything else rests on this;
      1. the config gate — resolution throws ConfigError where no config can be seen;
      2. every callable refuses to work, rather than guessing, with an unresolvable config;
      3. `_load_build()` vs the oracle — missing file, present file, non-dict document, corrupt
         JSON, the JAZZ_ROOT override and its tilde asymmetry, and the two path globals;
      4. `_notes_python()` vs the oracle — the default and the COUPLER_PYTHON override, per call;
      5. `_jazz_client()` vs the oracle — the exact `"<python> -m <module>"` command string;
      6. `notes_db_proxy` / `z3_proxy` vs the oracle — service, `str(result)`, the context
         manager, and that the shared mutable default is never mutated;
      7. `_build_app()` vs the oracle — the banner, the mounts, the interpreter gate, the why5
         block (including the load-bearing unused import) and the UI bridge tool by tool;
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

    def same_as_oracle(got, want, label):
        """Assert `got` equals what the ORACLE produced, in value and in type."""
        ok = _same(got, want)
        check(ok, "%s%s" % (label, "" if ok else
                            "  — oracle: %r (%s), rewrite: %r (%s)"
                            % (want, type(want).__name__, got, type(got).__name__)))
        return ok

    print("[0] the embedded original IS the forge blob ticket #369 names", file=out)
    problems = verify_original()
    check(not problems,
          "ORIGINAL_SOURCE is %d bytes and hashes to git blob %s%s"
          % (ORIGINAL_SIZE, ORIGINAL_BLOB_SHA1,
             "" if not problems else " — " + "; ".join(problems)))
    if problems:
        print("\nSELFTEST FAILED — the embedded original is not the forge blob, so every "
              "equivalence result below would be meaningless. Refusing to run them.", file=out)
        return len(problems)

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
                got = _attempt(lambda: load_config(start=isolated))
                check(isinstance(got, _Raised) and got.type is ConfigError,
                      "load_config() where no %s exists raises ConfigError" % REGISTRY_NAME)

            # ── 2. every callable refuses to work without config ─────────────
            #    Staged by pointing COUPLER_MAIN_CONFIG at a file that does not exist: the env
            #    source outranks the registry walk-up, so this proves the gate the same way
            #    whether or not a registry happens to be installed near this module — and this
            #    package SHIPS one, so a bare call here would otherwise succeed. Check [1]
            #    cannot do that on its own.
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
                ("JAZZ_ROOT (module attribute)", lambda: __getattr__("JAZZ_ROOT")),
                ("JAZZ_DEV (module attribute)", lambda: __getattr__("JAZZ_DEV")),
            ]
            for label, thunk in gated:
                got = _attempt(thunk)
                ok = isinstance(got, _Raised) and got.type is ConfigError
                check(ok, "%s raises ConfigError — no default is guessed%s"
                          % (label, "" if ok else " (got %r)" % (got,)))
            os.environ.pop(CONFIG_ENV, None)
            reset_config()

            # ── 3. _load_build() vs the oracle ───────────────────────────────
            print("[3] _load_build() — differential against the original", file=out)
            root = os.path.join(isolated, "jazz_root")
            os.makedirs(os.path.join(root, "conf", "env"))
            build_path = os.path.join(root, "conf", "env", "build.json")
            cfg = _fake_config(jazz_root={"env": "JAZZ_ROOT", "default": root})

            # The oracle reads its build path off the JAZZ_ROOT it snapshots AT IMPORT, so each
            # scenario points the env at `root` and re-execs it. The rewrite gets the same root
            # from its config default. Same file, both programs.
            os.environ["JAZZ_ROOT"] = root
            with _stubbed_world():
                scenarios = [
                    ("no build.json -> the original's `if p.exists()` else branch", None),
                    ("a build.json is parsed and returned verbatim",
                     json.dumps({"version": "9.9.9", "extra": [1, 2]})),
                    ("a JSON array comes back as a list — the `-> dict` annotation is the "
                     "original's claim, not a coercion it performed", "[1, 2]"),
                    ("a JSON string comes back as a str", '"just a string"'),
                ]
                for label, content in scenarios:
                    if content is None:
                        if os.path.exists(build_path):
                            os.remove(build_path)
                    else:
                        with open(build_path, "w", encoding="utf-8") as h:
                            h.write(content)
                    want = _attempt(lambda: _oracle()._load_build())
                    with using_config(cfg):
                        reset_paths()
                        got = _attempt(_load_build)
                    same_as_oracle(got, want, label)

                # a corrupt build.json must raise in BOTH, with the same exception type
                with open(build_path, "w", encoding="utf-8") as h:
                    h.write("{not json")
                want = _attempt(lambda: _oracle()._load_build())
                with using_config(cfg):
                    reset_paths()
                    got = _attempt(_load_build)
                ok = (isinstance(want, _Raised) and isinstance(got, _Raised)
                      and got.type is want.type and issubclass(got.type, ValueError))
                check(ok, "a corrupt build.json raises the SAME exception the original raises "
                          "(%s) rather than being swallowed into {}%s"
                          % (want.type.__name__ if isinstance(want, _Raised) else "?",
                             "" if ok else " — oracle: %r, rewrite: %r" % (want, got)))

            # the JAZZ_ROOT override, and the tilde asymmetry the original had
            print("[3b] the jazz-path env override, and its tilde asymmetry", file=out)
            other = os.path.join(isolated, "elsewhere")
            os.makedirs(os.path.join(other, "conf", "env"))
            with open(os.path.join(other, "conf", "env", "build.json"), "w",
                      encoding="utf-8") as h:
                json.dump({"version": "from-env"}, h)
            os.environ["JAZZ_ROOT"] = other
            with _stubbed_world():
                want = _oracle()._load_build()
                with using_config(cfg):
                    reset_paths()
                    got = _load_build()
                same_as_oracle(got, want,
                               "$JAZZ_ROOT overrides the config default — the original's env "
                               "override still works")

                os.environ["JAZZ_ROOT"] = "~/foo"
                want_root = _oracle().JAZZ_ROOT
                with using_config(cfg):
                    reset_paths()
                    got_root = _jazz_path("jazz_root")
                same_as_oracle(got_root, want_root,
                               "JAZZ_ROOT=~/foo stays a LITERAL '~' path in both — the original "
                               "passed the env value to Path() with no expanduser")

                os.environ.pop("JAZZ_ROOT", None)
                os.environ.pop("JAZZ_DEV", None)
                default_cfg = _fake_config()
                oracle_module = _oracle()
                with using_config(default_cfg):
                    reset_paths()
                    got_root = _jazz_path("jazz_root")
                    got_dev = _jazz_path("jazz_dev")
                same_as_oracle(got_root, oracle_module.JAZZ_ROOT,
                               "with no env set, the config DEFAULT is home-expanded to exactly "
                               "the original's `Path.home() / 'code/workspace/main'`")
                same_as_oracle(got_dev, oracle_module.JAZZ_DEV,
                               "and jazz_dev to exactly the original's "
                               "`Path.home() / 'code/jazz'`")

            # ── 3c. the module-level path globals (divergence 3) ─────────────
            print("[3c] JAZZ_ROOT / JAZZ_DEV as module attributes (divergence 3)", file=out)
            os.environ["JAZZ_ROOT"] = root
            os.environ["JAZZ_DEV"] = os.path.join(isolated, "devtree")
            with _stubbed_world():
                oracle_module = _oracle()
                with using_config(_fake_config()):
                    reset_paths()
                    same_as_oracle(__getattr__("JAZZ_ROOT"), oracle_module.JAZZ_ROOT,
                                   "coupler.__main__.JAZZ_ROOT is the same Path the original "
                                   "bound at import")
                    same_as_oracle(__getattr__("JAZZ_DEV"), oracle_module.JAZZ_DEV,
                                   "coupler.__main__.JAZZ_DEV is the same Path the original "
                                   "bound at import — preserved though the original never "
                                   "reads it")
                    check(all(n in __dir__() for n in ("mcp", "JAZZ_ROOT", "JAZZ_DEV")),
                          "all three lazy names are visible to dir(), not only to attribute "
                          "access — a PEP 562 __getattr__ alone would leave them invisible")
            os.environ.pop("JAZZ_ROOT", None)
            os.environ.pop("JAZZ_DEV", None)

            # JAZZ_DEV is dead in the original: PROVE it from the original's AST, rather than
            # asserting it or grepping for a name that also appears as an env-var string and in
            # a docstring. A global is "read" exactly when its name appears in a Load context.
            reads = _global_reads(ORIGINAL_SOURCE)
            check(reads.get("JAZZ_DEV", 0) == 0,
                  "the ORIGINAL never READS JAZZ_DEV — 0 Load references in its AST, so the "
                  "name is dead in the original and is preserved dead here (proven from the "
                  "embedded original's AST, not asserted)%s"
                  % ("" if reads.get("JAZZ_DEV", 0) == 0
                     else " — found %d" % reads.get("JAZZ_DEV")))
            check(reads.get("JAZZ_ROOT", 0) >= 1,
                  "and JAZZ_ROOT IS read (%d Load reference(s), in `_load_build`) — so the check "
                  "above discriminates rather than passing for every name"
                  % reads.get("JAZZ_ROOT", 0))
            check("sys.path" not in ORIGINAL_SOURCE,
                  "the ORIGINAL touches sys.path nowhere — so this rewrite inserts nothing "
                  "either (unlike its near-twin in the sibling forge2/coupler package)")

            # ── 4. _notes_python() vs the oracle ─────────────────────────────
            print("[4] _notes_python() — differential against the original", file=out)
            with _stubbed_world():
                oracle_module = _oracle()
                with using_config(cfg):
                    same_as_oracle(_notes_python(), oracle_module._notes_python(),
                                   "defaults to the same interpreter the original picks "
                                   "(sys.executable — downstreams run under the coupler's own "
                                   "venv)")
                    os.environ["COUPLER_PYTHON"] = "/opt/other/python3"
                    same_as_oracle(_notes_python(), oracle_module._notes_python(),
                                   "$COUPLER_PYTHON overrides it in both")
                    same_as_oracle(_notes_python(), oracle_module._notes_python(),
                                   "the override is read on EVERY call in both, not snapshotted")
                    os.environ.pop("COUPLER_PYTHON", None)
                    same_as_oracle(_notes_python(), oracle_module._notes_python(),
                                   "unsetting $COUPLER_PYTHON mid-process reverts both — proof "
                                   "the read is per-call, which is the original's asymmetry with "
                                   "the jazz paths")

            # ── 5. _jazz_client() vs the oracle ──────────────────────────────
            print("[5] _jazz_client() — differential against the original", file=out)
            with _stubbed_world():
                oracle_module = _oracle()
                os.environ["COUPLER_PYTHON"] = "/opt/py"
                _FakeClient.reset()
                want_client = oracle_module._jazz_client("notes_db_mcp")
                with using_config(cfg):
                    got_client = _jazz_client("notes_db_mcp")
                ok = (isinstance(got_client, _FakeClient) and isinstance(want_client, _FakeClient)
                      and _same(got_client.target, want_client.target))
                check(ok, "builds Client('<python> -m <module>') with the exact one-string "
                          "command the original passed%s"
                          % ("" if ok else " — oracle: %r, rewrite: %r"
                             % (getattr(want_client, "target", want_client),
                                getattr(got_client, "target", got_client))))
                check(_same(getattr(got_client, "target", None), "/opt/py -m notes_db_mcp"),
                      "and that string is exactly '/opt/py -m notes_db_mcp'")
                os.environ.pop("COUPLER_PYTHON", None)

            # ── 6. the two proxies vs the oracle ─────────────────────────────
            print("[6] notes_db_proxy / z3_proxy — differential against the original", file=out)
            with _stubbed_world():
                oracle_module = _oracle()
                for name, fn in (("notes_db_proxy", notes_db_proxy), ("z3_proxy", z3_proxy)):
                    _FakeClient.reset()
                    want = asyncio.run(getattr(oracle_module, name)("some_tool", {"a": 1}))
                    want_built, want_calls = list(_FakeClient.built), list(_FakeClient.calls)
                    _FakeClient.reset()
                    with using_config(cfg):
                        got = asyncio.run(fn("some_tool", {"a": 1}))
                    got_built, got_calls = list(_FakeClient.built), list(_FakeClient.calls)
                    same_as_oracle(got, want,
                                   "%s returns exactly what the original returns — str(result) "
                                   "of whatever the service handed back" % name)
                    ok = (got_built == want_built and got_calls == want_calls)
                    check(ok, "%s opens the same client and calls the same tool with the same "
                              "args as the original%s"
                              % (name, "" if ok else " — oracle: %r / %r, rewrite: %r / %r"
                                 % (want_built, want_calls, got_built, got_calls)))

                # `async with` is the original's shape: the client must be entered AND exited.
                _FakeClient.reset()
                holder = []
                original_aenter = _FakeClient.__aenter__

                async def _record_aenter(self):
                    holder.append(self)
                    return await original_aenter(self)

                _FakeClient.__aenter__ = _record_aenter
                try:
                    with using_config(cfg):
                        asyncio.run(notes_db_proxy("t"))
                finally:
                    _FakeClient.__aenter__ = original_aenter
                check(len(holder) == 1 and holder[0].entered and holder[0].exited,
                      "the client is opened and closed via `async with` (no leaked session)")

                # The mutable {} default is the ticket's surface. Prove it is inert — in BOTH.
                _FakeClient.reset()
                with using_config(cfg):
                    asyncio.run(notes_db_proxy("t"))
                    asyncio.run(z3_proxy("t"))
                asyncio.run(oracle_module.notes_db_proxy("t"))
                check(_same(notes_db_proxy.__defaults__[0], {})
                      and _same(z3_proxy.__defaults__[0], {})
                      and _same(oracle_module.notes_db_proxy.__defaults__[0], {}),
                      "the shared mutable {} default is never mutated — in the original OR here; "
                      "the surface is kept without the bug that shape usually implies")
                check(all(call[2] == {} for call in _FakeClient.calls),
                      "an omitted `args` forwards {} to the service, as in the original")

            # ── 7. _build_app() vs the oracle ────────────────────────────────
            print("[7] _build_app() — differential: banner, mounts, why5, UI bridge", file=out)
            os.environ["JAZZ_ROOT"] = root
            with open(build_path, "w", encoding="utf-8") as h:
                json.dump({"version": "2.4.0"}, h)
            app_cfg = _fake_config(jazz_root={"env": "JAZZ_ROOT", "default": root})

            # 7a: no why5 available — the situation that actually holds in this package today
            with _stubbed_world():
                _FakeHttp.reset()
                _FakeClient.reset()
                want_app, want_lines = _oracle_build_app()
                _FakeHttp.reset()
                _FakeClient.reset()
                with using_config(app_cfg):
                    reset_paths()
                    got_app, got_lines = _rewrite_build_app()

                ok = got_lines == want_lines
                check(ok, "the banner is line-for-line identical to the original's, including "
                          "the `[warn] why5 not available` line and `ui (port 8142)`%s"
                          % ("" if ok else "\n        oracle : %r\n        rewrite: %r"
                             % (want_lines, got_lines)))
                check(_app_tools(got_app) == _app_tools(want_app),
                      "exactly the tools the original registers, and no others: %s"
                      % (_app_tools(got_app),))
                check(_app_mounts(got_app) == _app_mounts(want_app) == ["notes_db", "z3"],
                      "both jazz services are mounted under the same namespaces, in the same "
                      "order")
                check(not isinstance(got_app, _Raised) and not isinstance(want_app, _Raised)
                      and _same(got_app.name, want_app.name),
                      "the app carries the same server name as the original's")

                # the mount is gated on the interpreter path EXISTING, and skips silently
                os.environ["COUPLER_PYTHON"] = os.path.join(isolated, "no-such-python")
                want_app2, want_lines2 = _oracle_build_app()
                with using_config(app_cfg):
                    reset_paths()
                    got_app2, got_lines2 = _rewrite_build_app()
                os.environ.pop("COUPLER_PYTHON", None)
                check(got_lines2 == want_lines2
                      and _app_mounts(got_app2) == _app_mounts(want_app2) == []
                      and not [l for l in got_lines2 if "could not mount" in l],
                      "a non-existent interpreter skips every mount SILENTLY in both — no mount "
                      "line and no warning, exactly as the original's `if Path(python).exists()`")

            # a mount that raises is warned about, and does not stop the others
            print("[7a] a failing mount warns per service and the app still builds", file=out)
            with _stubbed_world():
                boom_server = types.ModuleType("fastmcp.server")
                boom_server.create_proxy = _exploding_create_proxy
                sys.modules["fastmcp.server"] = boom_server
                want_app, want_lines = _oracle_build_app()
                boom = _fake_config(jazz_root={"env": "JAZZ_ROOT", "default": root})
                boom["providers"]["create_proxy"] = "%s:_exploding_create_proxy" % __name__
                with using_config(boom):
                    reset_paths()
                    got_app, got_lines = _rewrite_build_app()
                ok = got_lines == want_lines and not isinstance(got_app, _Raised)
                check(ok, "a failing create_proxy produces the original's exact per-service "
                          "warnings and the app still BUILDS — it does not propagate%s"
                          % ("" if ok else "\n        oracle : %r / %r\n        rewrite: %r / %r"
                             % (want_lines, want_app, got_lines, got_app)))
                check("  [warn] could not mount notes_db: kaboom" in got_lines
                      and "  [warn] could not mount z3: kaboom" in got_lines
                      and _app_mounts(got_app) == [],
                      "and those warnings name each service and its error")

            # ── 7b. why5 — the unused import is load-bearing ─────────────────
            print("[7b] why5 — the unused import is load-bearing", file=out)
            with _stubbed_world(why5=_make_fake_why5(WHY5_MODULE, complete=False)):
                want_app, want_lines = _oracle_build_app()
                with using_config(app_cfg):
                    reset_paths()
                    got_app, got_lines = _rewrite_build_app()
                ok = got_lines == want_lines
                check(ok, "a why5 module missing the UNUSED `from_commit_failure` produces the "
                          "original's EXACT warning — proof `_from_import`'s reconstructed "
                          "ImportError matches CPython's `from ... import`%s"
                          % ("" if ok else "\n        oracle : %r\n        rewrite: %r"
                             % (want_lines, got_lines)))
                check(any("[warn] why5 not available: cannot import name "
                          "'from_commit_failure'" in l for l in got_lines),
                      "and that warning is the ImportError for the unused name — dropping that "
                      "import would mount why5 where the original did not")
                check(not [t for t in _app_tools(got_app) if t.startswith("why5_")]
                      and not [t for t in _app_tools(want_app) if t.startswith("why5_")],
                      "no why5 tool is registered in either when the why5 import fails")
                check(any("mounted      : ui (port 8142)" in l for l in got_lines),
                      "the UI bridge still mounts after why5 fails — the original's "
                      "warn-and-continue")

            # ── 7c. the why5 tools, mounted, tool for tool ───────────────────
            print("[7c] the why5 tools — differential, with a fake why5 staged for both",
                  file=out)
            with _stubbed_world(why5=_make_fake_why5(WHY5_MODULE)):
                want_app, want_lines = _oracle_build_app()
                with using_config(app_cfg):
                    reset_paths()
                    got_app, got_lines = _rewrite_build_app()
                ok = got_lines == want_lines
                check(ok, "with why5 importable, the banner matches the original's exactly, "
                          "including `mounted      : why5`%s"
                          % ("" if ok else "\n        oracle : %r\n        rewrite: %r"
                             % (want_lines, got_lines)))
                check(_app_tools(got_app) == _app_tools(want_app)
                      and len(_app_tools(got_app)) == 11,
                      "exactly the original's 11 tools are registered: %s"
                      % (_app_tools(got_app),))

                # Every tool, called identically on both, compared value AND type.
                calls = [
                    ("why5_new", ("s1", "ci broke"), {}),
                    ("why5_fact", ("s1", "tests_ran", True), {}),
                    ("why5_link", ("s1", "L1", "a", "b"), {}),
                    ("why5_check", ("s1",), {}),
                    ("why5_check", ("nope",), {}),
                    ("why5_fact", ("nope", "x", True), {}),
                    ("why5_from_ci_failure", ("s2", "main", "abc123", "F"), {}),
                    ("why5_check", ("s2",), {}),
                    ("why5_new", ("s1", ""), {}),
                ]
                bad = []
                for name, a, k in calls:
                    want = _call(want_app, name, *a, **k)
                    got = _call(got_app, name, *a, **k)
                    if not _same_result(got, want):
                        bad.append((name, a, want, got))
                check(not bad, "all %d why5 tool calls return exactly what the original returns "
                               "(incl. why5_check's 'not found' STRING and why5_fact's KeyError "
                               "for an unknown session — the original's asymmetry, preserved)%s"
                               % (len(calls), "" if not bad else " — mismatches: %s" % bad))

            # ── 7d. the UI bridge, tool for tool ─────────────────────────────
            print("[7d] the UI bridge — differential, tool for tool", file=out)
            with _stubbed_world(why5=_make_fake_why5(WHY5_MODULE)):
                want_app, _ = _oracle_build_app()
                with using_config(app_cfg):
                    reset_paths()
                    got_app, _ = _rewrite_build_app()

                    ui_calls = [
                        ({"ok": True}, None, "ui_set_page", ({"name": "p1", "x": 1},)),
                        ({"ok": True}, None, "ui_set_page", ({"x": 1},)),
                        ({"ok": True}, None, "ui_set_page", ({"name": "", "x": 1},)),
                        ({"a": 1}, None, "ui_get_state", ("p1",)),
                        (["p1", "p2"], None, "ui_list_pages", ()),
                        ([], None, "ui_list_pages", ()),
                        ({"ok": True}, None, "ui_add_message", ("p", "chat", "user", "hi")),
                        ([{"c": 1}], None, "ui_get_log", ()),
                        ([{"c": 1}], None, "ui_get_log", (5,)),
                        ([], None, "ui_get_log", ()),
                        ({}, RuntimeError("connection refused"), "ui_set_page", ({"name": "p"},)),
                        ({}, RuntimeError("connection refused"), "ui_get_state", ("p",)),
                        ({}, RuntimeError("connection refused"), "ui_list_pages", ()),
                        ({}, RuntimeError("connection refused"),
                         "ui_add_message", ("p", "c", "user", "t")),
                        ({}, RuntimeError("connection refused"), "ui_get_log", ()),
                    ]
                    bad = []
                    for payload, raises, name, a in ui_calls:
                        _FakeHttp.reset(payload=payload, raises=raises)
                        want = _call(want_app, name, *a)
                        want_req = list(_FakeHttp.requests)
                        _FakeHttp.reset(payload=payload, raises=raises)
                        got = _call(got_app, name, *a)
                        got_req = list(_FakeHttp.requests)
                        if not (_same_result(got, want) and got_req == want_req):
                            bad.append((name, a, want, got, want_req, got_req))
                    check(not bad,
                          "all %d UI tool calls return exactly what the original returns AND "
                          "issue exactly the same HTTP requests (URL, body/params, timeout) — "
                          "including 'no pages registered'/'no changes yet' for empty results "
                          "and 'error: <e>' when the UI is unreachable%s"
                          % (len(ui_calls), "" if not bad else "\n        mismatches: %s" % bad))

                    # the value-coercion table — the original's own int()/float() quirks
                    table = ["true", "TRUE", "True", "false", "False", "FALSE",
                             "10", " 10 ", "1_0", "-3", "+7", "0", "1.5", "-0.0", "1e3",
                             "inf", "-inf", "nan", "abc", "0x10", "", "  ", "None", "1,000"]
                    bad = []
                    for raw in table:
                        _FakeHttp.reset(payload={"ok": True})
                        want = _call(want_app, "ui_set_value", "p", "c", raw)
                        want_req = list(_FakeHttp.requests)
                        _FakeHttp.reset(payload={"ok": True})
                        got = _call(got_app, "ui_set_value", "p", "c", raw)
                        got_req = list(_FakeHttp.requests)
                        # The PUT body is where the coerced value actually goes, so compare the
                        # value AND its type there, not just the returned string.
                        want_val = want_req[0][2]["value"] if want_req else _MISSING
                        got_val = got_req[0][2]["value"] if got_req else _MISSING
                        # `_same_result`, not `_same`: "nan" coerces to a float nan, which is
                        # never equal to itself, so a plain == would report the one case that
                        # exercises float() most sharply as a mismatch.
                        if not (_same_result(got, want) and _same_result(got_val, want_val)):
                            bad.append((raw, want, got, want_val, got_val))
                    check(not bad,
                          "%d/%d ui_set_value coercions match the original exactly, in value AND "
                          "type — the whole job of this tool is to pick a type%s"
                          % (len(table) - len(bad), len(table),
                             "" if not bad else " — mismatches: %s" % bad))
                    _FakeHttp.reset()

            # ── 7e. the UI banner reflects the configured base (divergence 2) ─
            print("[7e] the UI banner reflects the configured base (divergence 2 — the ONE "
                  "line where the two intentionally disagree)", file=out)
            os.environ["JSON_CONTROLS_URL"] = "http://127.0.0.1:9999"
            with _stubbed_world():
                _, want_lines = _oracle_build_app()
                with using_config(app_cfg):
                    reset_paths()
                    _, got_lines = _rewrite_build_app()
                check(any("mounted      : ui (port 9999)" in l for l in got_lines),
                      "$JSON_CONTROLS_URL moves the UI base AND the banner follows it")
                check(any("mounted      : ui (port 8142)" in l for l in want_lines),
                      "the ORIGINAL prints a literal 8142 here even though the base moved — it "
                      "was simply wrong, and requirement 4 forbids keeping the hardcoded port")
                differing = [(w, g) for w, g in zip(want_lines, got_lines) if w != g]
                check(len(differing) == 1 and "ui (port" in differing[0][0],
                      "and that banner line is the ONLY line of the whole run that differs from "
                      "the original%s" % ("" if len(differing) == 1
                                          else " — also differing: %s" % differing))
            os.environ.pop("JSON_CONTROLS_URL", None)
            check(_same(_ui_port("http://localhost"), "localhost")
                  and _same(_ui_port("http://127.0.0.1:8142"), 8142)
                  and _same(_ui_port("http://h:notaport"), "http://h:notaport"),
                  "a base with no port falls back to its host, and a malformed one to the base "
                  "itself, rather than printing None or taking the app down for a log line")

            # ── 7f. the module-level `mcp` server (divergence 3) ─────────────
            print("[7f] the module-level `mcp` server (divergence 3)", file=out)
            with _stubbed_world():
                oracle_module = _oracle()
                with using_config(cfg):
                    server = __getattr__("mcp")
                    check(isinstance(server, _FakeServer)
                          and _same(server.name, oracle_module.mcp.name),
                          "`mcp` is a server named exactly as the original's is (%r), built on "
                          "first access instead of at import" % (server.name,))
                    check(_same(sorted(server.tools), sorted(oracle_module.mcp.tools))
                          and sorted(server.tools) == ["notes_db_proxy", "z3_proxy"],
                          "`mcp` carries exactly the two proxy tools the original registered on "
                          "it%s" % ("" if sorted(server.tools) == ["notes_db_proxy", "z3_proxy"]
                                    else " — got %s" % sorted(server.tools)))
                    check(__getattr__("mcp") is server,
                          "`mcp` is a singleton — repeated access does not rebuild it")
            got = _attempt(lambda: __getattr__("no_such_attribute"))
            check(isinstance(got, _Raised) and got.type is AttributeError,
                  "an unknown module attribute still raises AttributeError, not ConfigError")

            # ── 8. the callable surface ──────────────────────────────────────
            #    Checked by LOWERING THIS FILE'S OWN SOURCE the way the ticket's surface was
            #    produced — codebean's `lower_node` (#183) walks the AST — and comparing to the
            #    ticket's strings verbatim. Runtime introspection is the WRONG oracle here,
            #    twice over: `from __future__ import annotations` makes inspect.signature render
            #    `-> 'Client'` (quoted), and the ORIGINAL, whose `Client` was a real imported
            #    class, renders `-> fastmcp.client.client.Client` — so neither module's runtime
            #    signature is the ticket's text. The AST is what the ticket lowered, so the AST
            #    is what must agree.
            print("[8] callable surface — this file's own AST, lowered as the ticket lowered "
                  "the original's", file=out)
            with open(os.path.abspath(__file__), "r", encoding="utf-8") as handle:
                lowered = _lower_surface(handle.read(), os.path.abspath(__file__))
            for want in SURFACE:
                name = want.split("(")[0].replace("async ", "")
                check(lowered.get(name) == want,
                      "%s%s" % (want, "" if lowered.get(name) == want
                                else "  — this file lowers to %r" % (lowered.get(name),)))

            # The ticket's surface is itself checked against the ORIGINAL, so a typo in SURFACE
            # cannot make this rewrite look right.
            print("[8a] the ticket's surface list agrees with the ORIGINAL's own AST", file=out)
            original_lowered = _lower_surface(ORIGINAL_SOURCE, "<ORIGINAL_SOURCE>")
            for want in SURFACE:
                name = want.split("(")[0].replace("async ", "")
                check(original_lowered.get(name) == want,
                      "the original lowers %s to exactly the string ticket #369 records%s"
                      % (name, "" if original_lowered.get(name) == want
                         else " — original lowers to %r" % (original_lowered.get(name),)))
            check(sorted(original_lowered) == sorted(n.split("(")[0].replace("async ", "")
                                                     for n in SURFACE),
                  "and the original has no top-level callable the ticket's surface omits")

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

    def __eq__(self, other):
        return (isinstance(other, _Raised) and self.type is other.type
                and self.exception == other.exception)

    def __hash__(self):
        return hash((self.type, self.exception))


def _attempt(thunk):
    """Call `thunk` and return its result, or a `_Raised` if it raised anything."""
    try:
        return thunk()
    except BaseException as exc:  # noqa: BLE001 — a test net must survive anything
        return _Raised(exc)


def _call(app, name, *a, **k):
    """Invoke a registered tool, returning a `_Raised` rather than propagating.

    Every tool check goes through here, for the oracle and the rewrite alike. A tool that raises
    unexpectedly must be a reported FAIL — `_Raised` matches no expected string — instead of
    aborting `selftest` and hiding every check behind it. It also lets a check compare a RAISE
    against a raise: `why5_fact` is supposed to raise KeyError for an unknown session, in both
    programs.
    """
    return _attempt(lambda: app.call(name, *a, **k))


def _same(got, want):
    """Compare like the oracle does: equal in value AND in type.

    `==` alone would call a returned `True` a pass where the original returned the int `1`, and
    `1.5` a pass for `"1.5"`. `ui_set_value`'s whole job is to pick a TYPE, so type is part of
    the behavior being preserved.
    """
    return type(got) is type(want) and got == want


def _same_result(got, want):
    """Compare two tool outcomes, where either may be a `_Raised`.

    A raise is an outcome like any other: the two agree only if both raised the same exception
    type with the same message, or both returned the same value with the same type. `nan` is the
    one value that is never equal to itself, so it is compared by repr — `ui_set_value("nan")`
    must yield a float nan in both, and `_same` alone would call that a mismatch.
    """
    if isinstance(want, _Raised) or isinstance(got, _Raised):
        return isinstance(want, _Raised) and isinstance(got, _Raised) and got == want
    if isinstance(got, float) and isinstance(want, float) and got != got and want != want:
        return True
    return _same(got, want)


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ... Filename
    - function name - time of occurance - methods to reproduce - possible cause"). Best-effort
    and silent on failure: a tool that cannot file a report must still report its original
    error. No report is filed for a ConfigError, which is designed behavior rather than a bug.
    Returns the path written, or None.
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
        "note": "%s (ticket #369, module key forge-rw:74c24d09f565e96d)" % UNIT,
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
        prog="forge2-coupler",
        description="forge2 rewrite of the forge unit "
                    "code__code-invalid__coupler:coupler/__main__.py (ticket #369) — the stable "
                    "MCP entry point for Claude Desktop. Config-driven: every command below "
                    "except `emit-config` and `selftest` throws if it cannot see its config "
                    "object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="config is read from the file named by $%s, else from the %s section of the "
               "nearest %s found by walking up from this module. This package ships one at its "
               "root, so `serve` works from a source checkout or an editable install that has "
               "fastmcp installed. Run `emit-config` for a template."
               % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="build the coupler app and run it (the original's entry point; "
                                 "needs fastmcp)")
    sub.add_parser("selftest", help="prove this rewrite against the ORIGINAL it embeds, plus the "
                                    "config gate (needs no config, no fastmcp and no network)")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and its source")
    return parser


def main(argv=None):
    """Entry point for the `forge2-coupler` console script. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at it."
                  "\n# Until it is installed, every command throws — it will not guess a default."
                  % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV), file=sys.stderr)
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
