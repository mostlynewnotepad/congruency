#!/usr/bin/env python3
"""forge2 / agent_tools_suite / coupler — a behavior-preserving rewrite of the forge unit
`agent_tools_suite:coupler.py` (module key forge-rw:5bda83c2edbfad97), filed under ticket #417
against the FORGE-wide refactor standard #200.

WHAT THIS IS
------------
The original forge unit was a 5162-byte zero-dependency MCP aggregator, owned by the gate. It
fronts N downstream MCP servers as one: it spawns each, aggregates every tool into a single
list namespaced `<server>__<tool>`, routes each call to the owning downstream, and isolates a
dead downstream so it never sinks the coupler. This file is an entirely new implementation of
that unit. It keeps the original's observable behavior and its callable surface, and adds the
three things #200 requires that the original lacked: it is a proper installable package, it is
driven by a configuration object, and it refuses to run when it cannot see that configuration.

TERMS USED HERE (defined at first use, for a reader who has never seen this system)
-----------------------------------------------------------------------------------
MCP
    Model Context Protocol — what an agent host speaks to tool servers. Its stdio form, the
    only one this unit uses, is newline-delimited JSON-RPC 2.0 over a child process's
    stdin/stdout.
downstream
    A child MCP server this process spawns and talks to as a client. `mcplib.Downstream` is
    the class that does it.
the gate
    The top MCP server, `agent_tools_suite:gate.py`. It owns this coupler and is its ONLY
    caller — see THE CALLABLE SURFACE.
leaf
    A downstream that serves its own tools rather than aggregating others'.
namespacing
    Rewriting a downstream tool `ping` on server `alpha` as `alpha__ping`, so N servers' tools
    can share one flat list without colliding. `__` is the separator.
meta tool
    A tool the coupler serves itself rather than routing: `coupler__status` and
    `coupler__reconnect`.
mcplib
    `agent_tools_suite:mcplib.py`, the zero-dependency stdio helper the original imports. It
    supplies `Server`, `Downstream`, `text_result` and `load_registry`. THIS PACKAGE DOES NOT
    SHIP IT — see THE TWO REGISTRIES and WHAT THIS PACKAGE DOES NOT SHIP.
config object
    The chunk of the forge2 config registry belonging to this unit — the
    `forge2.agent_tools_suite.coupler` section. It is what drives this module.
    `config_template()` returns a template of it.
exemplar
    A real (input, output) pair taken from the ORIGINAL acting as the oracle — #200's
    "verified, not asserted". `selftest()` replays them.

THE TWO REGISTRIES — read this before anything else confuses you
----------------------------------------------------------------
Two different JSON files are called "the registry" in this system, and this module touches
BOTH. They are not the same thing:

  1. THE DOWNSTREAM REGISTRY — the original's own runtime input. `mcplib.load_registry(HERE)`
     reads `registry.json` (or the file named by the `ATS_REGISTRY` environment variable)
     beside the module, and this unit takes its `servers` block: the downstreams to spawn.
     This module does NOT parse that file itself; it calls `mcplib.load_registry`, so the
     `ATS_REGISTRY` override and the "registry not found" refusal are mcplib's behavior,
     preserved by delegation rather than re-implemented.
  2. THE FORGE2 CONFIG REGISTRY — #200 requirement 4's config object. The nearest
     `registry.json` found by walking UP from THIS FILE, of which this unit reads ONLY its own
     `forge2.agent_tools_suite.coupler` section. It holds the settings the original hardcoded.

They MAY be one file — the keys are disjoint, so one `registry.json` can carry both a
`servers` block and a `forge2` section, and in the original's own layout they would be the
same file. `base_dir` is what points registry 1 at wherever it lives; registry 2 is always
found by walking up from this file. Keep the two straight and everything below is simple.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    load_servers()
    sanitize(s)
    Coupler.__init__(self)
    Coupler._build(self)
    Coupler._allowed(self, server_name, tool_name)
    Coupler.connect(self)
    Coupler.list_tools(self)
    Coupler.status_text(self)
    Coupler.call_tool(self, name, args)

WHO ACTUALLY CALLS THIS, and why that settles the entry-point question. The original's real
caller is `gate.py`, which does NOT import this module — it SPAWNS it as a subprocess
(`mcplib.Downstream("coupler", {"command": <python>, "args": ["coupler.py"]}, HERE)`) and
speaks MCP stdio to it. So the contract that must not move is the STDIO PROTOCOL: what
`python3 coupler.py` writes on stdout in response to what arrives on stdin. That contract is
preserved exactly; it is what this rewrite was verified against.

BEHAVIOR THAT IS EASY TO GET WRONG (each one MEASURED from the original, not inferred)
--------------------------------------------------------------------------------------
Every item below was observed by RUNNING the original — reconstructed from ticket #417's
embedded source and confirmed byte-identical to forge blob
5ae87e7885b46adee7dd0bc1af953fe14b6fff34 — against the real `mcplib` and real leaf servers.
Each is replayed by `selftest()`:

  * AN EMPTY `servers` BLOCK FALLS THROUGH TO `mcpServers`. `load_servers()` chains with `or`,
    not with `in`, so `{"servers": {}}` is falsy and `mcpServers` is consulted next. A rewrite
    using `if "servers" in raw` would diverge.
  * `only: []` MEANS OPPOSITE THINGS DEPENDING ON WHETHER `exclude` IS PRESENT. `_build()`
    registers a filter only `if spec.get("only") or spec.get("exclude")`. An empty `only` is
    falsy, so with no `exclude` NO filter is registered and EVERY tool is allowed; add any
    `exclude` and the filter IS registered, whereupon `_allowed()`'s `only is not None` test
    passes and `tool_name not in []` hides EVERY tool. Measured: 2 tools shown in the first
    case, "0 tools (2 hidden)" in the second. This is preserved exactly.
  * TWO SERVER NAMES THAT SANITIZE ALIKE COLLIDE, AND THE LAST ONE WINS. `a.b` and `a b` both
    namespace to `a_b__go`; `tools/list` advertises the name TWICE and `toolmap` keeps only the
    last, so the call routes to `a b`. Measured, and preserved.
  * A DEAD DOWNSTREAM'S TOOL IS "unknown", NOT "down". `call_tool()` re-runs `list_tools()`,
    which SKIPS dead downstreams, so their tools are absent from `toolmap` and the lookup fails
    first. The `"downstream '%s' is down"` branch below is therefore unreachable through the
    protocol — it is kept because removing it would be a rewrite of the surface, not of the
    behavior.
  * A TOOL WITH NO `name` KEY CRASHES THE WHOLE SERVER. `list_tools()` reads `t["name"]`, and
    `mcplib.Server` does NOT guard `tools/list` (it guards only `tools/call`), so the KeyError
    escapes `serve()` and the process exits 1 with a traceback. `status_text()`, by contrast,
    reads `t.get("name", "")` and tolerates the same tool. The asymmetry is real and preserved.
  * A TOOL WITH NO `description` BECOMES `"[server]"` — the `"[%s] %s"` format leaves a
    trailing space that `.strip()` removes. Measured exactly, including the strip.
  * `status_text()` USES THE RAW SERVER NAME, `list_tools()` NAMESPACES WITH THE SANITIZED ONE,
    AND THE DESCRIPTION TAG USES THE RAW ONE. So `my.server 1` advertises `my_server_1__go`
    described as `[my.server 1] ...` and reports as `- my.server 1:` in status. Three
    spellings of one name, all preserved.
  * `list(self.META)` IS A SHALLOW COPY. The meta tool dicts returned by `list_tools()` are the
    SAME objects every call, including across a reconnect. Preserved — see `_meta_tools()`.
  * "· not started" IS UNREACHABLE THROUGH THE PROTOCOL. Both paths that reach `status_text()`
    call `connect()` first. It is preserved for the in-process caller that does not.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The original hardcoded every path and parameter it used: `HERE`, the `sys.path` entry it
imported mcplib from, the module name `mcplib`, the `servers`/`mcpServers` key chain, the `__`
namespace separator, the `coupler` meta-tool prefix, and the server name and version it
announced. All of them are now config keys, and NONE has a default. The config object is
resolved on first use from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. That file holds the unit
     config object itself — exactly what `config_template()` returns.
  2. otherwise, the `forge2.agent_tools_suite.coupler` section of the nearest `registry.json`
     found by walking UP from THIS FILE's directory. This package ships one there, so an
     unmodified checkout resolves to it and the module runs.

If NEITHER answers, every operation raises `ConfigError` and NOTHING is spawned, aggregated or
printed. It never guesses a default — that is `note-for-claude`'s rule ("if a tool cannot see
the registry it will throw an exeption" [sic]) and this ticket's acceptance item (d). A config
object that is found but lacks a key the attempted operation needs is also a `ConfigError`,
naming the key.

The keys, and the original constant each replaces:

    base_dir       str   "."                        HERE — where the DOWNSTREAM registry is
                                                    read from, and the cwd/base every
                                                    downstream is spawned against
    mcplib         obj   {"module": "mcplib",       `sys.path.insert(0, HERE)` + `import mcplib`
                          "path": "."}              `path` is prepended to sys.path (null = do
                                                    not touch sys.path); `module` is imported
    namespace      str   "__"                       NS
    meta_prefix    str   "coupler"                  the "coupler" in `coupler__status` AND the
                                                    "[coupler]" tag on the meta descriptions
    server_name    str   "mcp-coupler"              Server("mcp-coupler", ...)
    server_version str   "1.0.0"                    Server(..., "1.0.0", ...)
    servers_keys   list  ["servers", "mcpServers"]  the `raw.get("servers") or
                                                    raw.get("mcpServers")` fallback chain, in
                                                    order; the first TRUTHY value wins
    bug_reports    str   "logs/bug_reports.jsonl"   note-for-claude's bug-report sink

A path key may be absolute, may start with `~` (expanded), or may be relative — in which case
it resolves against the directory the config came FROM (the registry's directory), never
against the current working directory. So `"base_dir": "."` means "the directory holding the
config registry", which for an unmodified checkout is this package — exactly what the
original's `HERE` meant for the original's layout.

`configure(config)` and `using_config(config)` inject a config object in-process, for callers
that hold their configuration in memory rather than on disk.

WHAT THIS PACKAGE DOES NOT SHIP, and why that is not a defect
-------------------------------------------------------------
`mcplib` IS NOT HERE. It is a SEPARATE forge module (`agent_tools_suite:mcplib.py`, blob
c3796f354363df36faeb4f7a35de2f790d81166b) with its own rewrite ticket, and #200 requirement 3
is explicit that a unit writes ONLY its own module file — so shipping a copy of mcplib here
would clobber a sibling unit's deliverable. It is therefore named by the config and imported
on first use.

The consequence, stated plainly rather than left to be discovered: with the shipped
`registry.json` and nothing else installed, `forge2-coupler` raises a `ConfigError` naming
`mcplib` and the path it searched. That is not a divergence — the ORIGINAL fails identically
when run away from its own directory, with `ModuleNotFoundError: No module named 'mcplib'`.
Point `base_dir` and `mcplib.path` at a real `agent_tools_suite` checkout and everything below
runs exactly as the original does. The shipped registry ALSO has no `servers` block, so even
with mcplib present the unmodified checkout couples zero downstreams and reports
"(no servers configured)" — which is, again, precisely what the original does with such a
registry. That block belongs to a deployment, not to this package: adding one here would mean
writing a sibling's config, which #200 requirement 4 forbids.

RUNNING IT
----------
The original had no command line at all — it served the moment it was imported. That is
preserved for the only invocation that ever existed:

    python3 coupler.py            # serve MCP over stdio, exactly as the gate spawns it
    forge2-coupler                # the same thing, via the installed console script

Any argument is IGNORED, because the original ignored `sys.argv` entirely. The diagnostics are
module functions rather than verbs, so that no argument the original defined changes meaning:

    python3 -B -c "import coupler; raise SystemExit(coupler.selftest())"
    python3 -B -c "import coupler; raise SystemExit(coupler.check_package())"
    python3 -B -c "import coupler, json; print(json.dumps(coupler.config_template(), indent=2))"
    python3 -B -c "import coupler, json; print(json.dumps(coupler.show_config(), indent=2))"

(`python3 -c` puts the current directory on the import path, which is why these run as written
from the package directory. `selftest()` and `check_package()` return 0 on success and 1 on
failure, so `raise SystemExit(...)` makes that the process exit code. `-B` merely stops Python
caching bytecode, so the command leaves no `__pycache__`; drop it and everything still works.)

To prove acceptance item (d) — that this throws rather than guessing:

    FORGE2_CONFIG=/nonexistent.json python3 coupler.py     # -> exit 2, one config-error line

INSTALLABLE (#200 requirement 3)
--------------------------------
This directory IS the import package `agent_tools_suite`, and it installs from its own source:

    pip install -e .                     # from this directory
    forge2-coupler                       # the console script
    python3 -c "from agent_tools_suite.coupler import Coupler"

`pyproject.toml` and `__init__.py` are NOT hand-authored: per #200 requirement 3 they are
DERIVED from the modules present by `congruency/tools/forge_package.py` (#410), so a sibling
module of this package can land later without either unit clobbering the other. They were
generated by running that tool against this directory. `registry.json` gained ONLY this unit's
own `forge2.agent_tools_suite.coupler` section, added additively via that tool's
`merge_registry_section()`; no sibling's section was read, edited or dropped.

THE DELIBERATE DIVERGENCES — all four, stated plainly rather than buried
------------------------------------------------------------------------
1. IMPORTING THIS MODULE NO LONGER SERVES. The original ran `_c = Coupler()` and
   `mcplib.Server(...).serve()` at MODULE level, so `import coupler` spawned every downstream
   and blocked forever on stdin. #200 requirement 3 demands this be an importable package
   module; a module that serves on import cannot be one. So that pair of statements moved,
   verbatim in effect, into `main()`, under an `if __name__ == "__main__"` guard.
   This breaks no caller, and the claim is checkable: the original's importers are exactly the
   set of programs that could survive an import that never returns — the empty set. `gate.py`,
   the one real caller, spawns `python3 coupler.py`, which still serves identically. The
   module-level name `_c` is gone for the same reason; nothing could ever have read it,
   because the import that would have defined it never returned.
2. NO CONFIG MEANS EXIT 2, NOT EXIT 1. Where a missing `registry.json` made the original exit 1
   with mcplib's `registry not found: <path>`, this rewrite exits 2 with `config error: ...`
   naming the same file — because it is now the CONFIG gate that fires first, which is what
   acceptance item (d) demands. Requirements 1 and 4 genuinely conflict here and the ticket
   resolves it: (d) wins. The gate cannot observe the difference — it reads the coupler's exit
   code never, only its dead pipe — and both refuse to start.
3. AN UNEXPECTED EXCEPTION ALSO FILES A BUG REPORT. Per `note-for-claude` ("all tools need to
   pass a bug-report automatically ... if an exception is thrown") `main()` appends one
   timestamped JSON line to the config's `bug_reports` path and prints one extra
   `EXCEPTION — ...` line to stderr saying where it went — then RE-RAISES, so the exception,
   its traceback and the exit code the original produced are unchanged. Verified on the
   nameless-tool crash: both exit 1, both end with `KeyError: 'name'`. Filing is best-effort
   and never masks the real exception. A `ConfigError` is designed behavior, not a bug: it
   files no report and prints no traceback.
4. `META` IS PER-INSTANCE, NOT A CLASS CONSTANT. Its content now depends on `meta_prefix` and
   `namespace`, which come from the config — and a class attribute is evaluated at class-
   definition time, when no config has been resolved and none can be. So META is built in
   `__init__`. `self.META` — the only way the original's own code ever read it — is unchanged
   in content, in type, and in object identity across a reconnect.
   Stated exactly, because it is the one thing here a caller could notice: the ORIGINAL had a
   class attribute `Coupler.META` (a list, readable without an instance); this rewrite has
   NONE, so `Coupler.META` raises `AttributeError` where the original returned the list. Only
   `Coupler().META` exists. Nothing in the original's own code, and nothing in `gate.py` (which
   does not import this module at all — it spawns it), ever read META off the class; the
   ticket's callable surface does not include it; and an in-process caller that wants it can
   read it from an instance exactly as before.

HOW FAR THIS WAS VERIFIED — and where it stops
----------------------------------------------
  * BEHAVIOR was verified DIFFERENTIALLY against the ORIGINAL, not against expectations. The
    original was reconstructed from ticket #417's embedded source and confirmed byte-identical
    to forge blob 5ae87e7885b46adee7dd0bc1af953fe14b6fff34 (5162 bytes, sha1 of the git blob
    recomputed from the reconstruction) — so the oracle is the real unit, not a paraphrase of
    it. Both were then run side by side through 43 scenarios in byte-identical worlds — same
    real `mcplib`, same `registry.json`, same real leaf MCP servers — each driven as a REAL
    stdio subprocess speaking real JSON-RPC, exactly as `gate.py` drives it. All 43 agreed on
    every JSON-RPC reply, on stderr, and on exit code, with only the divergences listed above.
    The scenarios cover both `only: []` cases, the sanitize collision, the `mcpServers`
    fallback, dead and missing and non-MCP downstreams, a leaf that dies mid-call, a leaf that
    throws, the nameless- and descriptionless-tool shapes, `ATS_REGISTRY`, and the protocol's
    own ping/unknown-method/notification/EOF paths.

    Exactly TWO things are normalised before comparison, both unmaskable by construction: the
    WORLD PATH (the two worlds must sit at different directories to run side by side), and
    traceback FRAME lines and depth (a rewrite is a different file, so it cannot share the
    original's line numbers, and `main()` adds one frame — divergence 1). The exception's own
    `Type: message` line, the exit code, and every non-traceback stderr line ARE compared.

  * THAT HARNESS WAS MUTATION-TESTED, because a differential that cannot fail proves nothing.
    Eight defects were seeded into this module in turn; SEVEN were caught by at least one
    scenario: dropping the `or` chain, treating `only: []` as an allowlist, sanitizing the
    description tag, dropping the `.strip()`, using `.get("name", "")` in `list_tools()`,
    not skipping a dead downstream, and totalling `len(d.tools)` in `status_text()`.

    The EIGHTH — deep-copying META — escaped, and that is a fact about the wire, not a hole in
    the check: object identity does not survive a JSON boundary, so NO protocol-level test can
    ever see it. It is caught in-process by `selftest()` instead ("list_tools copies the list
    shallowly — same dicts"). `selftest()` was itself mutation-tested for the same reason, and
    caught all four defects put to it, including both META-identity ones.

    Two of the seven were only caught after the escape they exposed was closed, and the
    scenarios that close them are worth naming, because each is a shape that looks redundant
    and is not: a nameless tool needs a server with a filter REGISTERED (with no filter,
    `_allowed()` returns before it reads the name, so a `.get()` rewrite looks identical), and
    a dead downstream needs a `tools/list` AFTER a leaf died MID-CALL (one that fails to START
    has `tools == []`, so skipping it or not looks identical).

  * BOTH INSTALLS were executed, not asserted: `pip install -e .` and `pip install .` each
    built and installed this package into a fresh venv and exited 0. In both, the module
    imports as `agent_tools_suite.coupler`, resolves its shipped config from a NEUTRAL working
    directory (the package-data path — the case a non-editable install is apt to lose), and the
    installed `forge2-coupler` console script served real MCP over stdio and routed a real call
    to a real leaf. Both were installed from a COPY, so the deliverable directory never gained
    an `egg-info`/`build` stray.
  * THE SCAFFOLDING WAS PROVEN DERIVED, NOT HAND-AUTHORED: `pyproject.toml` is byte-identical
    to what `congruency/tools/forge_package.py`'s `render_pyproject()` generates for this
    directory, and `registry.json` is the base checkout's document plus THIS unit's section and
    nothing else — every other key byte-identical, no sibling section dropped.
  * `selftest()` (115 checks) and `check_package()` (15 checks) pass.

Where it stops, stated so no one mistakes the scope:
  * `selftest()` drives STAND-IN mcplib fakes, because the real `mcplib` is a separate forge
    module that this package does not ship — it proves this module's own logic, its config gate
    and its object identities, NOT the stdio wire. The wire is what the 43-scenario
    differential proves, and that ran against the real `mcplib`.
  * Neither proves anything about what a downstream does once spawned; that was never this
    unit's scope.
  * The differential proves agreement on the 43 shapes it drives. It is evidence, not a proof
    of total equivalence — no finite scenario set is.

SIDE EFFECTS — what this module writes, and when
------------------------------------------------
Serving spawns the configured downstream processes and `coupler__reconnect` terminates and
respawns them; that is the unit's entire job and the original's behavior exactly. Nothing else
here writes anything, with one exception: `main()` appends to the config's `bug_reports` path
on the crash path described in divergence 3. `list_tools()`, `status_text()`,
`config_template()` and `show_config()` create nothing. `selftest()` works entirely inside a
temporary directory it removes and restores every global it touches. `check_package()` only
READS this directory's `pyproject.toml` and `registry.json`.
"""

import contextlib
import fnmatch
import importlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import textwrap
import traceback
from datetime import datetime

__all__ = [
    "load_servers", "sanitize", "Coupler", "main",
    "ConfigError", "load_config", "configure", "using_config", "reset_config",
    "config_template", "show_config", "mcplib_module", "selftest", "check_package",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for. This is the FORGE2 CONFIG
#: registry (registry 2 in the docstring), not the downstream registry mcplib reads.
REGISTRY_NAME = "registry.json"

#: This unit's ADDRESS inside the config registry. Not a configurable setting — a config-driven
#: tool has to know which section is its own.
UNIT_PATH = ("forge2", "agent_tools_suite", "coupler")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:agent_tools_suite/coupler"

#: The import package this module belongs to, as the derived `pyproject.toml` declares it.
#: Used by `check_package()` and by the installed-registry fallback.
IMPORT_PACKAGE = "agent_tools_suite"

#: The mcplib attributes this unit uses. Named here so a config pointing at something that is
#: not mcplib-shaped fails with a message naming the missing attribute, rather than an
#: AttributeError from deep inside a call.
MCPLIB_ATTRS = ("Server", "Downstream", "text_result", "load_registry")


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.
    """


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None      # config injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution, so a run re-reads no files
_MCPLIB = None      # cache of the resolved mcplib module, keyed by (module, path)


def find_registry(start=None):
    """Walk UP from `start` (default: this file's directory) and return the nearest config
    registry path, or None if the walk reaches the filesystem root without finding one.

    The walk starts at THIS FILE, never at the working directory, so which directory you run
    from cannot change which config is found. If the walk fails — a layout where the module was
    installed without its package data beside it — it falls back to asking the import system
    where `agent_tools_suite` lives and looks there.
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
    # section may state its own to override it. This is inheritance inside ONE config document,
    # not a guessed default.
    if "bug_reports" not in config and isinstance(document, dict) and "bug_reports" in document:
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
    """Drop the injected config, the cached disk resolution and the cached mcplib; the next
    call re-resolves everything."""
    global _ACTIVE, _RESOLVED, _MCPLIB
    _ACTIVE = None
    _RESOLVED = None
    _MCPLIB = None


def config_template():
    """Return a template of this unit's config object — every key set to the value that
    reproduces the ORIGINAL unit's hardcoded constant.

    This is scaffolding returned on request, not a default: nothing here is applied unless an
    operator installs it, and until they do every operation throws.
    """
    return {
        "base_dir": ".",
        "mcplib": {"module": "mcplib", "path": "."},
        "namespace": "__",
        "meta_prefix": "coupler",
        "server_name": "mcp-coupler",
        "server_version": "1.0.0",
        "servers_keys": ["servers", "mcpServers"],
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
    """The config value for `key`, or ConfigError naming it."""
    config = active_config()
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the required key %r. This tool does not guess "
            "defaults; see config_template() for the full object and the value that reproduces "
            "the original." % (UNIT, key))
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
    return _resolve_path(_str_setting(key))


def _resolve_path(value):
    value = os.path.expanduser(value)
    if not os.path.isabs(value):
        value = os.path.join(active_base(), value)
    return os.path.normpath(value)


def _str_list_setting(key):
    """A config key holding a non-empty list of strings, order-significant."""
    value = _setting(key)
    if not isinstance(value, list) or not value:
        raise ConfigError("config key %r for %s must be a non-empty JSON array of strings, not %r"
                          % (key, UNIT, value))
    for item in value:
        if not isinstance(item, str):
            raise ConfigError("config key %r for %s must hold only strings; found %s"
                              % (key, UNIT, type(item).__name__))
    return value


def _mcplib_setting():
    """The mcplib provider: `{"module": str, "path": str|null}`.

    `path` is REQUIRED to be present and may be null, which means "do not touch sys.path" —
    stating that explicitly rather than letting an absent key silently mean it, because an
    absent key meaning something IS a guessed default.
    """
    value = _setting("mcplib")
    if not isinstance(value, dict):
        raise ConfigError("config key 'mcplib' for %s must be a JSON object with 'module' and "
                          "'path', not %s" % (UNIT, type(value).__name__))
    for key in ("module", "path"):
        if key not in value:
            raise ConfigError("config key 'mcplib' for %s is missing %r" % (UNIT, key))
    if not isinstance(value["module"], str) or not value["module"]:
        raise ConfigError("mcplib 'module' for %s must be a non-empty string, not %r"
                          % (UNIT, value["module"]))
    if value["path"] is not None and not isinstance(value["path"], str):
        raise ConfigError("mcplib 'path' for %s must be a string or null, not %s"
                          % (UNIT, type(value["path"]).__name__))
    return value


# ───────────────────────────── the mcplib provider ─────────────────────────────

def mcplib_module():
    """Import and return the mcplib the config names, caching it.

    This is the original's `sys.path.insert(0, HERE)` + `import mcplib`, with both the path and
    the module name taken from the config instead of hardcoded. The path is prepended (not
    appended) so a configured mcplib SHADOWS an installed one, exactly as the original's
    insert-at-0 did.

    Raises:
        ConfigError: if the module cannot be imported, or is not mcplib-shaped.
    """
    global _MCPLIB
    spec = _mcplib_setting()
    name = spec["module"]
    path = _resolve_path(spec["path"]) if spec["path"] is not None else None
    if _MCPLIB is not None and _MCPLIB[0] == (name, path):
        return _MCPLIB[1]
    if path is not None and (not sys.path or sys.path[0] != path):
        sys.path.insert(0, path)
    try:
        module = importlib.import_module(name)
    except Exception as exc:                 # noqa: BLE001 — any import failure is a config fault
        raise ConfigError(
            "config for %s names mcplib module %r%s, which could not be imported: %s: %s. "
            "This package does not ship mcplib — it is a separate forge module; point "
            "config['mcplib'] at a checkout that has it."
            % (UNIT, name, (" on path %s" % path) if path else " (no path configured)",
               type(exc).__name__, exc)) from exc
    missing = [a for a in MCPLIB_ATTRS if not hasattr(module, a)]
    if missing:
        raise ConfigError("the module %r at %s is not mcplib-shaped: it has no %s"
                          % (name, getattr(module, "__file__", "?"), ", ".join(missing)))
    _MCPLIB = ((name, path), module)
    return module


# ─────────────────────────────── the unit itself ───────────────────────────────

def load_servers():
    """The downstream specs: the first TRUTHY block among the configured `servers_keys`, else
    an empty dict.

    This is the original's `raw.get("servers") or raw.get("mcpServers") or {}` with the key
    chain configured. The `or` semantics matter and are preserved: an EMPTY `servers` block is
    falsy, so it falls through to `mcpServers` rather than winning as an explicit "no servers".

    The document itself comes from `mcplib.load_registry(base_dir)` — the DOWNSTREAM registry,
    not this unit's config registry. Delegating to mcplib is deliberate: the `ATS_REGISTRY`
    filename override and the "registry not found" refusal are mcplib's behavior, and calling
    it preserves them exactly rather than re-implementing them almost-right.

    Raises:
        ConfigError: if there is no config object, or it lacks `base_dir`/`mcplib`/`servers_keys`.
        SystemExit: from mcplib, if the downstream registry is not found. (The original's.)
    """
    raw = mcplib_module().load_registry(_path_setting("base_dir"))
    for key in _str_list_setting("servers_keys"):
        block = raw.get(key)
        if block:
            return block
    return {}


def sanitize(s):
    """The original's namespace sanitizer: every character outside `[A-Za-z0-9_-]` becomes `_`.

    `str(s)` first, so a non-string server name works exactly as it did. Note this is NOT
    injective — `a.b` and `a b` both become `a_b`, and the original lets the collision through.
    """
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(s))


class Coupler:
    """The aggregator: spawns the configured downstreams, fronts their tools as one namespaced
    list, and routes each call to the owning downstream.

    The config is read ONCE, here, into instance attributes — mirroring the original, whose
    `HERE` and `NS` were module constants evaluated once at import. The DOWNSTREAM registry is
    re-read on every `_build()`, which is also the original's behavior: a reconnect picks up an
    edited `servers` block.
    """

    def __init__(self):
        # Resolved in the original's order, so the first failure is the same failure:
        # `import mcplib` preceded `_c = Coupler()` there, so an mcplib fault outranks a
        # downstream-registry fault here too. The config gate necessarily precedes both — it is
        # what says where mcplib IS.
        self._mcplib = mcplib_module()
        self._ns = _str_setting("namespace")
        self._meta_prefix = _str_setting("meta_prefix")
        self._server_name = _str_setting("server_name")
        self._server_version = _str_setting("server_version")

        # Built once per instance, not per _build(): the original's META was a class constant,
        # so `list(self.META)` handed out the SAME dicts on every call, including across a
        # reconnect. Rebuilding it in _build() would quietly break that identity.
        self.META = self._meta_tools()

        self.downstreams = {}
        self.connected = False
        self.toolmap = {}          # namespaced name -> (downstream, original name)
        self._build()

    # -- meta tools ---------------------------------------------------------------

    def _meta(self, verb):
        """The full name of a meta tool: `coupler` + `__` + verb, from config."""
        return self._meta_prefix + self._ns + verb

    def _meta_tools(self):
        """The two meta tool descriptors. With the template's `meta_prefix`/`namespace` these
        are byte-identical to the original's `META` class constant.

        The `[coupler]` description tag is derived from `meta_prefix` rather than being a
        second literal, because it IS the coupler's own name in the same `"[%s] "` scheme
        `list_tools()` tags every downstream tool with — the original just happened to spell
        the same word twice.
        """
        empty_schema = {"type": "object", "properties": {}, "additionalProperties": False}
        return [
            {"name": self._meta("status"),
             "description": "[%s] Health of every coupled downstream server and its tool count."
                            % self._meta_prefix,
             "inputSchema": dict(empty_schema)},
            {"name": self._meta("reconnect"),
             "description": "[%s] Tear down and re-spawn all downstream servers, then "
                            "re-aggregate." % self._meta_prefix,
             "inputSchema": dict(empty_schema)},
        ]

    # -- construction -------------------------------------------------------------

    def _build(self):
        """(Re)read the downstream registry and rebuild the downstream set, unconnected.

        `self.filters` is created HERE, not in `__init__` — the original does the same, so a
        caller that reaches `_allowed()` without a `_build()` gets the original's
        AttributeError.
        """
        self.downstreams = {}
        self.filters = {}
        for name, spec in load_servers().items():
            self.downstreams[name] = self._mcplib.Downstream(name, spec, self._base_dir())
            # Registered only when at least one side is TRUTHY. An empty `only` with no
            # `exclude` therefore registers NOTHING and allows everything, while an empty `only`
            # WITH an exclude registers a filter that hides everything. Measured on the
            # original; see the module docstring.
            if spec.get("only") or spec.get("exclude"):
                self.filters[name] = {"only": spec.get("only"),
                                      "exclude": spec.get("exclude") or []}
        self.connected = False

    def _base_dir(self):
        """The original's `HERE`: where the downstream registry is read from, and the base every
        downstream resolves its `./` paths and cwd against."""
        return _path_setting("base_dir")

    def _allowed(self, server_name, tool_name):
        """Registry-driven per-downstream tool filter: `only` (allowlist of exact tool names)
        and/or `exclude` (denylist of fnmatch globs, e.g. `vm_*`).

        `server_name` is the RAW registry name, never the sanitized one — that is how
        `_build()` keyed `self.filters`.
        """
        f = self.filters.get(server_name)
        if not f:
            return True
        only = f.get("only")
        if only is not None and tool_name not in only:
            return False
        for pat in f.get("exclude") or []:
            if fnmatch.fnmatch(tool_name, pat):
                return False
        return True

    def connect(self):
        """Start every downstream, once. A downstream that fails to start marks itself dead and
        is isolated; it never sinks the coupler."""
        if self.connected:
            return
        for d in self.downstreams.values():
            d.start()
        self.connected = True

    # -- the MCP surface ----------------------------------------------------------

    def list_tools(self):
        """Every tool: the meta tools, then each live downstream's allowed tools, namespaced.

        Rebuilds `toolmap` as a side effect — that is how `call_tool()` routes. Dead
        downstreams are skipped entirely, so their tools appear nowhere and route nowhere.

        A downstream tool with no `name` raises KeyError, which `mcplib.Server` does NOT catch
        on `tools/list`, so it takes the whole server down with exit 1. That is the original's
        behavior, measured, and it is preserved deliberately.
        """
        self.connect()
        tools = list(self.META)       # shallow, like the original: the same meta dicts each call
        self.toolmap = {}
        for d in self.downstreams.values():
            if d.dead:
                continue
            for t in d.tools:
                if not self._allowed(d.name, t["name"]):
                    continue
                ns = "%s%s%s" % (sanitize(d.name), self._ns, t["name"])
                self.toolmap[ns] = (d, t["name"])
                nt = dict(t)
                nt["name"] = ns
                # The tag is the RAW name while the namespace above is the SANITIZED one; and
                # a tool with no description leaves a trailing space that .strip() removes.
                nt["description"] = ("[%s] %s" % (d.name, t.get("description", ""))).strip()
                tools.append(nt)
        return tools

    def status_text(self):
        """The `coupler__status` markdown: one line per downstream, plus the live-tool total.

        Reads `t.get("name", "")` where `list_tools()` reads `t["name"]` — so this tolerates a
        nameless tool that would crash `list_tools()`. The asymmetry is the original's.
        """
        lines = []
        total = 0
        for d in self.downstreams.values():
            if d.dead:
                state = "✗ down (%s)" % (d.error or "unknown")
            elif d.proc is not None:
                shown = sum(1 for t in d.tools if self._allowed(d.name, t.get("name", "")))
                hidden = len(d.tools) - shown
                state = "✓ up, %d tools%s" % (shown, (" (%d hidden)" % hidden) if hidden else "")
                total += shown
            else:
                # Unreachable through the protocol: both callers connect() first. Preserved for
                # the in-process caller that does not.
                state = "· not started"
            lines.append("- %s: %s" % (d.name, state))
        body = "\n".join(lines) or "(no servers configured)"
        return "## coupler status — %d server(s), %d live tool(s)\n\n%s" % (
            len(self.downstreams), total, body)

    def call_tool(self, name, args):
        """Serve a meta tool, or route to the owning downstream. Never raises: every downstream
        fault comes back as an MCP error result, which is what keeps one bad child from sinking
        the coupler."""
        mcplib = self._mcplib
        if name == self._meta("status"):
            self.connect()
            return mcplib.text_result(self.status_text())
        if name == self._meta("reconnect"):
            for d in self.downstreams.values():
                d.stop()
            self._build()
            self.connect()
            return mcplib.text_result(self.status_text())

        self.list_tools()  # ensure the map reflects live downstreams
        entry = self.toolmap.get(name)
        if not entry:
            return mcplib.text_result(
                'unknown tool "%s". Call tools/list for the current set.' % name, True)
        d, original = entry
        if d.dead:
            # Unreachable through the protocol — list_tools() above drops dead downstreams from
            # toolmap, so the `not entry` branch fires first. Preserved verbatim anyway.
            return mcplib.text_result("downstream '%s' is down (%s). Try %sreconnect."
                                      % (d.name, d.error, self._meta_prefix + self._ns), True)
        try:
            return d.call_tool(original, args)
        except Exception as e:                # noqa: BLE001 — isolate the downstream
            return mcplib.text_result("downstream '%s' failed on %s: %s"
                                      % (d.name, original, e), True)


# ─────────────────────────────── the bug report ───────────────────────────────

def _bug_report(exc, formatted):
    """Append one timestamped bug-report line for an UNEXPECTED exception. Returns the path
    written, or None.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").

    TRULY best-effort: the whole body is guarded, because this runs INSIDE an `except` block and
    any exception raised here would REPLACE the real one the operator needs to see. That
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
            "methods-to-reproduce": "python3 %s  (serving MCP stdio; see the traceback for the "
                                    "request that did it)" % os.path.basename(
                                        os.path.abspath(__file__)),
            "possible-cause": "%s: %s" % (type(exc).__name__, exc),
            "traceback": formatted.strip().splitlines()[-6:],
            "note": "%s (ticket #417, module key forge-rw:5bda83c2edbfad97)" % UNIT,
        }
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except Exception:                        # noqa: BLE001 — never mask the real exception
        return None


# ─────────────────────────────── the entry point ───────────────────────────────

def main():
    """Serve MCP over stdio — the original's module-level body, verbatim in effect.

    The original ran `_c = Coupler()` and `mcplib.Server(...).serve()` at import. Those two
    statements are these two, moved behind a function so this module can be imported (#200
    requirement 3). `sys.argv` is ignored, because the original ignored it — there are no verbs
    to add and none were added.

    Returns None, so the `forge2-coupler` console script — whose generated wrapper calls
    `sys.exit(main())` — exits 0 when the host closes stdin, exactly as the original did.
    """
    try:
        coupler = Coupler()
        mcplib_module().Server(coupler._server_name, coupler._server_version,
                               coupler.list_tools, coupler.call_tool).serve()
    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        raise SystemExit(2) from None
    except SystemExit:
        raise                                # mcplib's "registry not found" — the original's
    except Exception as exc:                 # noqa: BLE001
        path = _bug_report(exc, traceback.format_exc())
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        # Re-raise: the original crashed with a traceback and a non-zero exit, and filing a
        # report must not change that.
        raise


# ───────────────────────── the exemplars and the selftest ─────────────────────────

#: A stand-in mcplib. It has the four attributes this unit uses and records what the unit did
#: to it, so the selftest can assert on spawn/stop order without real child processes. The unit
#: reaches it through the SAME config-named-provider path the real mcplib comes through.
_FAKE_MCPLIB = textwrap.dedent('''\
    """A stand-in mcplib for coupler's selftest — same four attributes, no processes."""
    import json
    import os

    EVENTS = []
    REGISTRY = {}


    def text_result(text, is_error=False):
        return {"content": [{"type": "text", "text": text}], "isError": is_error}


    def load_registry(here):
        EVENTS.append(("load_registry", here))
        name = os.environ.get("ATS_REGISTRY", "registry.json")
        path = name if os.path.isabs(name) else os.path.join(here, name)
        if not os.path.isfile(path):
            raise SystemExit("registry not found: %s" % path)
        with open(path) as f:
            return json.load(f)


    class Downstream:
        def __init__(self, name, spec, base_dir):
            self.name = name
            self.spec = spec or {}
            self.base_dir = base_dir
            self.proc = None
            self.tools = []
            self.dead = False
            self.error = None
            EVENTS.append(("new", name, base_dir))

        def start(self):
            EVENTS.append(("start", self.name))
            if self.proc is not None or self.dead:
                return
            # `in`, not `.get()`: an EMPTY error string is a real state the real mcplib can
            # reach (`self.error = str(e)` on an exception with no message), and it is the only
            # way to exercise status_text()'s `d.error or "unknown"`.
            if "fail" in self.spec:
                self.dead = True
                self.error = self.spec["fail"]
                return
            self.proc = object()
            self.tools = [dict(t) for t in self.spec.get("tools", [])]

        def stop(self):
            EVENTS.append(("stop", self.name))

        def call_tool(self, name, arguments):
            EVENTS.append(("call", self.name, name, arguments))
            if self.spec.get("raise_on") == name:
                raise RuntimeError("downstream %r closed" % self.name)
            return text_result("%s:%s:%s" % (self.name, name, sorted((arguments or {}).items())))


    class Server:
        LAST = None

        def __init__(self, name, version, list_tools, call_tool, watch_tool_changes=False):
            self.name = name
            self.version = version
            self.list_tools = list_tools
            self.call_tool = call_tool
            self.watch = watch_tool_changes
            Server.LAST = self
            EVENTS.append(("server", name, version, watch_tool_changes))

        def serve(self):
            EVENTS.append(("serve", self.name))
    ''')


def _capture(fn, *args, **kwargs):
    """Run `fn`, returning (result_or_exception, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            result = fn(*args, **kwargs)
        except BaseException as exc:                     # noqa: BLE001
            result = exc
    return result, out.getvalue(), err.getvalue()


def selftest(stream=None):
    """Replay the exemplars — the behaviors MEASURED on the original — against this rewrite.

    Returns 0 if every check passes, 1 otherwise. Creates and removes one temporary directory,
    spawns no processes, and restores every global and environment variable it touches.

    What this proves and what it does not: the stand-in mcplib means this exercises THIS
    module's logic and its config gate, not the stdio wire. The wire was proven by the
    41-scenario differential against the real mcplib described in the module docstring.
    """
    stream = stream or sys.stdout
    checks = []

    def check(name, got, want):
        ok = got == want
        checks.append((ok, name, got, want))
        stream.write("%-4s %s\n" % ("ok" if ok else "FAIL", name))
        if not ok:
            stream.write("       got : %r\n       want: %r\n" % (got, want))
        return ok

    saved_active, saved_resolved, saved_mcplib = _ACTIVE, _RESOLVED, _MCPLIB
    saved_path = list(sys.path)
    saved_env = {k: os.environ.get(k) for k in (CONFIG_ENV, "ATS_REGISTRY")}
    saved_modules = dict(sys.modules)
    tmp = tempfile.mkdtemp(prefix="coupler-selftest-")
    try:
        os.environ.pop(CONFIG_ENV, None)
        os.environ.pop("ATS_REGISTRY", None)
        fake_dir = os.path.join(tmp, "fake")
        os.makedirs(fake_dir)
        with open(os.path.join(fake_dir, "fake_mcplib.py"), "w") as f:
            f.write(_FAKE_MCPLIB)

        def config(**over):
            c = config_template()
            c["mcplib"] = {"module": "fake_mcplib", "path": fake_dir}
            c["base_dir"] = tmp
            c.update(over)
            return c

        def registry(doc):
            with open(os.path.join(tmp, "registry.json"), "w") as f:
                json.dump(doc, f)

        def fresh(doc, **over):
            """A Coupler over `doc` as the downstream registry, with a fake mcplib."""
            registry(doc)
            reset_config()
            configure(config(**over), base=tmp)
            fake = mcplib_module()
            del fake.EVENTS[:]
            return Coupler(), fake

        def tools_of(doc, **over):
            c, _ = fresh(doc, **over)
            return [t["name"] for t in c.list_tools()]

        def leaf(*names, **spec):
            s = {"tools": [{"name": n, "description": "%s desc" % n} for n in names]}
            s.update(spec)
            return s

        # ── the config gate (acceptance item d) ─────────────────────────────────
        reset_config()
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        got, _, _ = _capture(load_config, start=empty)
        check("no registry anywhere -> ConfigError", isinstance(got, ConfigError), True)

        os.environ[CONFIG_ENV] = os.path.join(tmp, "nope.json")
        got, _, _ = _capture(load_config)
        check("FORGE2_CONFIG at a missing file -> ConfigError", isinstance(got, ConfigError), True)
        os.environ.pop(CONFIG_ENV)

        registry({"forge2": {"agent_tools_suite": {}}})
        reset_config()
        got, _, _ = _capture(load_config, start=tmp)
        check("registry without our section -> ConfigError", isinstance(got, ConfigError), True)
        check("...and it names the section", isinstance(got, ConfigError) and "coupler" in str(got),
              True)

        registry({"forge2": {"agent_tools_suite": {"coupler": config_template()}},
                  "bug_reports": "logs/x.jsonl"})
        reset_config()
        cfg, base, source = load_config(start=tmp)
        check("our section resolves", cfg["server_name"], "mcp-coupler")
        check("base is the registry's dir", base, tmp)
        check("our section's own bug_reports OUTRANKS the top-level one",
              cfg["bug_reports"], "logs/bug_reports.jsonl")

        section = config_template()
        del section["bug_reports"]
        registry({"forge2": {"agent_tools_suite": {"coupler": section}},
                  "bug_reports": "logs/x.jsonl"})
        reset_config()
        cfg, _, _ = load_config(start=tmp)
        check("a section with no bug_reports inherits the top-level one",
              cfg["bug_reports"], "logs/x.jsonl")

        registry({"forge2": {"agent_tools_suite": {"coupler": section}}})
        reset_config()
        cfg, _, _ = load_config(start=tmp)
        check("no bug_reports anywhere -> the key is simply absent, not guessed",
              "bug_reports" in cfg, False)

        reset_config()
        configure({"base_dir": tmp}, base=tmp)
        got, _, _ = _capture(mcplib_module)
        check("config missing 'mcplib' -> ConfigError", isinstance(got, ConfigError), True)
        configure({"mcplib": {"module": "json"}, "base_dir": tmp}, base=tmp)
        got, _, _ = _capture(mcplib_module)
        check("mcplib without 'path' -> ConfigError", isinstance(got, ConfigError), True)
        configure({"mcplib": {"module": "json", "path": None}, "base_dir": tmp}, base=tmp)
        got, _, _ = _capture(mcplib_module)
        check("a module that is not mcplib-shaped -> ConfigError", isinstance(got, ConfigError),
              True)
        check("...and it names a missing attribute",
              isinstance(got, ConfigError) and "Downstream" in str(got), True)
        configure({"mcplib": {"module": "no_such_mcplib_xyz", "path": None}, "base_dir": tmp},
                  base=tmp)
        got, _, _ = _capture(mcplib_module)
        check("an unimportable mcplib -> ConfigError", isinstance(got, ConfigError), True)

        # ── load_servers: the `or` chain ────────────────────────────────────────
        base_doc = {"forge2": {"agent_tools_suite": {"coupler": config_template()}}}
        reset_config()
        configure(config(), base=tmp)

        registry(dict(base_doc, servers={"a": leaf("t")}))
        check("servers block wins", sorted(load_servers()), ["a"])
        registry(dict(base_doc, servers={}, mcpServers={"m": leaf("t")}))
        check("EMPTY servers falls through to mcpServers", sorted(load_servers()), ["m"])
        registry(dict(base_doc, servers=None, mcpServers={"m": leaf("t")}))
        check("null servers falls through to mcpServers", sorted(load_servers()), ["m"])
        registry(dict(base_doc, mcpServers={"m": leaf("t")}))
        check("mcpServers alone", sorted(load_servers()), ["m"])
        registry(dict(base_doc, servers={"s": leaf("t")}, mcpServers={"m": leaf("t")}))
        check("both -> servers wins", sorted(load_servers()), ["s"])
        registry(dict(base_doc))
        check("neither -> empty dict", load_servers(), {})
        registry(dict(base_doc, other={"o": leaf("t")}))
        reset_config()
        configure(config(servers_keys=["other"]), base=tmp)
        check("servers_keys is honoured", sorted(load_servers()), ["o"])

        reset_config()
        configure(config(servers_keys=[]), base=tmp)
        got, _, _ = _capture(load_servers)
        check("empty servers_keys -> ConfigError", isinstance(got, ConfigError), True)
        configure(config(servers_keys="servers"), base=tmp)
        got, _, _ = _capture(load_servers)
        check("servers_keys as a string -> ConfigError", isinstance(got, ConfigError), True)

        # ── mcplib.load_registry is delegated, not re-implemented ───────────────
        reset_config()
        configure(config(base_dir=os.path.join(tmp, "empty")), base=tmp)
        got, _, _ = _capture(load_servers)
        check("no downstream registry -> mcplib's SystemExit", isinstance(got, SystemExit), True)
        check("...with mcplib's own message", "registry not found" in str(got), True)

        with open(os.path.join(tmp, "registry.alt.json"), "w") as f:
            json.dump({"servers": {"alt": leaf("atool")}}, f)
        registry(dict(base_doc, servers={"a": leaf("t")}))
        reset_config()
        configure(config(), base=tmp)
        os.environ["ATS_REGISTRY"] = "registry.alt.json"
        check("ATS_REGISTRY override reaches mcplib", sorted(load_servers()), ["alt"])
        os.environ.pop("ATS_REGISTRY")

        # ── sanitize ────────────────────────────────────────────────────────────
        check("sanitize keeps safe chars", sanitize("aZ0_-"), "aZ0_-")
        check("sanitize replaces a dot", sanitize("a.b"), "a_b")
        check("sanitize replaces a space", sanitize("a b"), "a_b")
        check("sanitize is not injective", sanitize("a.b") == sanitize("a b"), True)
        check("sanitize stringifies", sanitize(12), "12")
        check("sanitize stringifies None", sanitize(None), "None")
        check("sanitize handles unicode", sanitize("café"), "caf_")
        check("sanitize handles empty", sanitize(""), "")

        # ── the meta tools ──────────────────────────────────────────────────────
        c, fake = fresh(dict(base_doc))
        meta = c.META
        check("meta names", [t["name"] for t in meta], ["coupler__status", "coupler__reconnect"])
        check("meta status description", meta[0]["description"],
              "[coupler] Health of every coupled downstream server and its tool count.")
        check("meta reconnect description", meta[1]["description"],
              "[coupler] Tear down and re-spawn all downstream servers, then re-aggregate.")
        check("meta inputSchema", meta[0]["inputSchema"],
              {"type": "object", "properties": {}, "additionalProperties": False})
        check("list_tools copies the list shallowly — same dicts",
              c.list_tools()[0] is c.META[0], True)
        check("...and returns a NEW list each call", c.list_tools() is not c.list_tools(), True)
        first_meta = c.list_tools()[0]
        c.call_tool("coupler__reconnect", {})
        check("meta dict identity survives a reconnect", c.list_tools()[0] is first_meta, True)

        c, _ = fresh(dict(base_doc), meta_prefix="gate", namespace="::")
        check("meta_prefix and namespace drive the names",
              [t["name"] for t in c.META], ["gate::status", "gate::reconnect"])
        check("...and the description tag", c.META[0]["description"].startswith("[gate]"), True)

        # ── list_tools ──────────────────────────────────────────────────────────
        doc = dict(base_doc, servers={"alpha": leaf("ping", "echo"), "beta": leaf("stat")})
        check("namespaced tools, in registry order", tools_of(doc),
              ["coupler__status", "coupler__reconnect", "alpha__ping", "alpha__echo", "beta__stat"])

        c, _ = fresh(doc)
        listed = c.list_tools()
        check("description is tagged with the RAW name",
              [t["description"] for t in listed if t["name"] == "alpha__ping"], ["[alpha] ping desc"])
        check("toolmap maps namespaced -> original", sorted(c.toolmap),
              ["alpha__echo", "alpha__ping", "beta__stat"])
        check("toolmap keeps the ORIGINAL tool name", c.toolmap["alpha__ping"][1], "ping")

        c, _ = fresh(dict(base_doc, servers={"n": {"tools": [{"name": "t1"}]}}))
        check("a tool with no description -> just the tag",
              [t["description"] for t in c.list_tools() if t["name"] == "n__t1"], ["[n]"])

        c, _ = fresh(dict(base_doc, servers={"n": {"tools": [{"description": "d"}]}}))
        got, _, _ = _capture(c.list_tools)
        check("a tool with NO name -> KeyError escapes list_tools", isinstance(got, KeyError), True)

        c, _ = fresh(dict(base_doc, servers={"my.server 1": leaf("go")}))
        check("the namespace is SANITIZED", [t["name"] for t in c.list_tools()][2], "my_server_1__go")
        check("the description tag is RAW",
              [t["description"] for t in c.list_tools()][2], "[my.server 1] go desc")

        c, _ = fresh(dict(base_doc, servers={"a.b": leaf("go"), "a b": leaf("go")}))
        listed = [t["name"] for t in c.list_tools()]
        check("colliding names are BOTH advertised", listed,
              ["coupler__status", "coupler__reconnect", "a_b__go", "a_b__go"])
        check("...and the LAST one wins the route", c.toolmap["a_b__go"][0].name, "a b")

        c, _ = fresh(dict(base_doc, servers={"dead": leaf("t", fail="boom"), "live": leaf("u")}))
        check("a dead downstream contributes no tools",
              [t["name"] for t in c.list_tools()],
              ["coupler__status", "coupler__reconnect", "live__u"])

        # ── _allowed / the filters ──────────────────────────────────────────────
        doc = dict(base_doc, servers={"f": leaf("keep", "drop", only=["keep"])})
        check("only: allowlist", tools_of(doc)[2:], ["f__keep"])
        doc = dict(base_doc, servers={"f": leaf("vm_a", "vm_b", "safe", exclude=["vm_*"])})
        check("exclude: fnmatch glob", tools_of(doc)[2:], ["f__safe"])
        doc = dict(base_doc, servers={"f": leaf("a", "b", "c", only=["a", "b"], exclude=["b"])})
        check("only + exclude compose", tools_of(doc)[2:], ["f__a"])
        doc = dict(base_doc, servers={"f": leaf("a", "b", exclude=["*"])})
        check("exclude '*' hides everything", tools_of(doc)[2:], [])

        # THE TRAP, both halves:
        doc = dict(base_doc, servers={"f": leaf("a", "b", only=[])})
        check("only:[] ALONE -> no filter registered, all allowed",
              tools_of(doc)[2:], ["f__a", "f__b"])
        doc = dict(base_doc, servers={"f": leaf("a", "b", only=[], exclude=["zzz"])})
        check("only:[] WITH exclude -> filter registered, all hidden", tools_of(doc)[2:], [])

        doc = dict(base_doc, servers={"f": leaf("a", "b", exclude=[])})
        check("exclude:[] alone -> no filter", tools_of(doc)[2:], ["f__a", "f__b"])
        doc = dict(base_doc, servers={"f": leaf("a", "b", only=None, exclude=["a"])})
        check("only:null + exclude", tools_of(doc)[2:], ["f__b"])
        doc = dict(base_doc, servers={"f": leaf("a", "b", only=["a"], exclude=None)})
        check("exclude:null + only", tools_of(doc)[2:], ["f__a"])

        c, _ = fresh(dict(base_doc, servers={"f": leaf("a", only=["a"])}))
        check("_allowed keys off the RAW server name", c._allowed("f", "a"), True)
        check("_allowed on an unknown server allows", c._allowed("nope", "anything"), True)

        # ── status_text ─────────────────────────────────────────────────────────
        c, _ = fresh(dict(base_doc))
        c.connect()
        check("no servers configured", c.status_text(),
              "## coupler status — 0 server(s), 0 live tool(s)\n\n(no servers configured)")

        c, _ = fresh(dict(base_doc, servers={"alpha": leaf("ping", "echo"), "beta": leaf("stat")}))
        c.connect()
        check("status: all up", c.status_text(),
              "## coupler status — 2 server(s), 3 live tool(s)\n\n"
              "- alpha: ✓ up, 2 tools\n- beta: ✓ up, 1 tools")

        c, _ = fresh(dict(base_doc, servers={"d": leaf("t", fail="boom"), "u": leaf("v")}))
        c.connect()
        check("status: one down", c.status_text(),
              "## coupler status — 2 server(s), 1 live tool(s)\n\n"
              "- d: ✗ down (boom)\n- u: ✓ up, 1 tools")

        c, _ = fresh(dict(base_doc, servers={"d": leaf("t", fail="")}))
        c.connect()
        check("status: down with a blank error -> 'unknown'", c.status_text(),
              "## coupler status — 1 server(s), 0 live tool(s)\n\n- d: ✗ down (unknown)")

        c, _ = fresh(dict(base_doc, servers={"f": leaf("a", "b", "c", exclude=["b", "c"])}))
        c.connect()
        check("status: hidden count", c.status_text(),
              "## coupler status — 1 server(s), 1 live tool(s)\n\n- f: ✓ up, 1 tools (2 hidden)")

        c, _ = fresh(dict(base_doc, servers={"n": leaf("a")}))
        check("status BEFORE connect -> '· not started'", c.status_text(),
              "## coupler status — 1 server(s), 0 live tool(s)\n\n- n: · not started")

        c, _ = fresh(dict(base_doc, servers={"n": {"tools": [{"description": "d"}]}}))
        c.connect()
        check("status TOLERATES the nameless tool list_tools dies on", c.status_text(),
              "## coupler status — 1 server(s), 1 live tool(s)\n\n- n: ✓ up, 1 tools")

        # ── call_tool ───────────────────────────────────────────────────────────
        c, fake = fresh(dict(base_doc, servers={"alpha": leaf("ping")}))
        r = c.call_tool("coupler__status", {})
        check("status meta returns a text result", r["isError"], False)
        check("...and its text is status_text()", r["content"][0]["text"], c.status_text())

        r = c.call_tool("alpha__ping", {"x": 1})
        check("a routed call reaches the downstream", r["content"][0]["text"],
              "alpha:ping:[('x', 1)]")
        check("...with the ORIGINAL tool name", ("call", "alpha", "ping", {"x": 1}) in fake.EVENTS,
              True)

        r = c.call_tool("nope__nope", {})
        check("unknown tool is an error result", r["isError"], True)
        check("...with the original's wording", r["content"][0]["text"],
              'unknown tool "nope__nope". Call tools/list for the current set.')

        r = c.call_tool("coupler__bogus", {})
        check("a meta-looking name that is not meta is just unknown", r["content"][0]["text"],
              'unknown tool "coupler__bogus". Call tools/list for the current set.')

        c, fake = fresh(dict(base_doc, servers={"d": leaf("die", raise_on="die")}))
        r = c.call_tool("d__die", {})
        check("a throwing downstream is isolated, not propagated", r["isError"], True)
        check("...with the original's wording", r["content"][0]["text"],
              "downstream 'd' failed on die: downstream 'd' closed")

        c, fake = fresh(dict(base_doc, servers={"dead": leaf("t", fail="boom")}))
        r = c.call_tool("dead__t", {})
        check("a dead downstream's tool reads as UNKNOWN, not 'is down'",
              r["content"][0]["text"],
              'unknown tool "dead__t". Call tools/list for the current set.')

        # The 'is down' branch is unreachable through the protocol; reach it directly.
        c, _ = fresh(dict(base_doc, servers={"x": leaf("t")}))
        c.list_tools()
        c.downstreams["x"].dead = True
        c.downstreams["x"].error = "gone"
        c.toolmap["x__t"] = (c.downstreams["x"], "t")
        c.list_tools = lambda: None          # freeze the map so the branch is reachable
        r = c.call_tool("x__t", {})
        check("the unreachable 'is down' branch, forced", r["content"][0]["text"],
              "downstream 'x' is down (gone). Try coupler__reconnect.")

        # ── connect / reconnect ─────────────────────────────────────────────────
        c, fake = fresh(dict(base_doc, servers={"a": leaf("t"), "b": leaf("u")}))
        del fake.EVENTS[:]
        c.connect()
        c.connect()
        check("connect starts each downstream exactly once",
              [e for e in fake.EVENTS if e[0] == "start"], [("start", "a"), ("start", "b")])

        c, fake = fresh(dict(base_doc, servers={"a": leaf("t")}))
        c.connect()
        del fake.EVENTS[:]
        r = c.call_tool("coupler__reconnect", {})
        kinds = [e[0] for e in fake.EVENTS]
        check("reconnect stops before it rebuilds", kinds.index("stop") < kinds.index("new"), True)
        check("reconnect re-reads the downstream registry", "load_registry" in kinds, True)
        check("reconnect then starts again", kinds.count("start"), 1)
        check("reconnect returns the fresh status", r["content"][0]["text"], c.status_text())

        # A reconnect must pick up an EDITED registry — the original re-reads it every _build().
        c, fake = fresh(dict(base_doc, servers={"a": leaf("t")}))
        check("before the edit", [t["name"] for t in c.list_tools()][2:], ["a__t"])
        registry(dict(base_doc, servers={"b": leaf("u")}))
        c.call_tool("coupler__reconnect", {})
        check("reconnect picks up the edited registry",
              [t["name"] for t in c.list_tools()][2:], ["b__u"])

        # ── the Server handshake ────────────────────────────────────────────────
        registry(dict(base_doc, servers={"a": leaf("t")}))
        reset_config()
        configure(config(), base=tmp)
        fake = mcplib_module()
        del fake.EVENTS[:]
        main()
        srv = fake.Server.LAST
        check("main() announces the configured name", srv.name, "mcp-coupler")
        check("main() announces the configured version", srv.version, "1.0.0")
        check("main() does NOT ask for tool-change watching (the original did not)",
              srv.watch, False)
        check("main() served", ("serve", "mcp-coupler") in fake.EVENTS, True)
        check("main() wired list_tools", srv.list_tools.__name__, "list_tools")
        check("main() wired call_tool", srv.call_tool.__name__, "call_tool")
        check("main() built the Coupler BEFORE serving",
              [e[0] for e in fake.EVENTS].index("new") < [e[0] for e in fake.EVENTS].index("serve"),
              True)

        # ── main()'s config gate and its exit code ──────────────────────────────
        reset_config()
        os.environ[CONFIG_ENV] = os.path.join(tmp, "nope.json")
        got, out, err = _capture(main)
        check("main() with no config exits 2", isinstance(got, SystemExit) and got.code, 2)
        check("...with one self-explaining line, no traceback",
              err.strip().startswith("config error:") and "Traceback" not in err, True)
        check("...and prints nothing on stdout", out, "")
        os.environ.pop(CONFIG_ENV)

        # ── main()'s bug report (note-for-claude) ───────────────────────────────
        registry(dict(base_doc, servers={"n": {"tools": [{"description": "d"}]}}))
        reset_config()
        sink = os.path.join(tmp, "reports", "bugs.jsonl")
        configure(config(bug_reports=sink), base=tmp)
        fake = mcplib_module()

        class _Serving(fake.Server):
            def serve(self):                      # drive the crash the original crashes on
                self.list_tools()
        prev_server = fake.Server
        fake.Server = _Serving
        try:
            got, out, err = _capture(main)
        finally:
            fake.Server = prev_server
        check("an unexpected exception is RE-RAISED, not swallowed", isinstance(got, KeyError), True)
        check("...a bug report was filed", os.path.isfile(sink), True)
        if os.path.isfile(sink):
            with open(sink) as f:
                entry = json.loads(f.readline())
            check("...naming the file", entry["filename"], os.path.basename(__file__))
            check("...naming the function", entry["function"], "list_tools")
            check("...with a cause", entry["possible-cause"], "KeyError: 'name'")
            for field in ("time-of-occurance", "methods-to-reproduce", "traceback"):
                check("...with %s" % field, bool(entry.get(field)), True)
        check("...and said so on stderr", "EXCEPTION —" in err, True)

        # A non-string bug_reports must NOT replace the real exception (the #200 trap).
        reset_config()
        configure(config(bug_reports=123), base=tmp)
        fake = mcplib_module()
        fake.Server = _Serving
        try:
            got, out, err = _capture(main)
        finally:
            fake.Server = prev_server
        check("a non-string bug_reports never masks the real exception",
              isinstance(got, KeyError), True)
        check("...and says no report could be filed", "no bug report could be filed" in err, True)

        # ── the config gate covers every public entry point ─────────────────────
        reset_config()
        os.environ[CONFIG_ENV] = os.path.join(tmp, "nope.json")
        for name, fn in (("load_servers", load_servers), ("Coupler()", Coupler),
                         ("mcplib_module", mcplib_module), ("show_config", show_config)):
            got, _, _ = _capture(fn)
            check("%s throws without a config" % name, isinstance(got, ConfigError), True)
        os.environ.pop(CONFIG_ENV)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        globals()["_ACTIVE"] = saved_active
        globals()["_RESOLVED"] = saved_resolved
        globals()["_MCPLIB"] = saved_mcplib
        sys.path[:] = saved_path
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for k in [m for m in sys.modules if m not in saved_modules]:
            sys.modules.pop(k, None)

    bad = [c for c in checks if not c[0]]
    stream.write("\n%d/%d checks passed\n" % (len(checks) - len(bad), len(checks)))
    return 1 if bad else 0


# ──────────────────── the packaging, checked against itself ────────────────────

def check_package(stream=None):
    """Check this package's DERIVED scaffolding against this module. Returns 0 or 1.

    Reads `pyproject.toml` and `registry.json` from this file's directory and creates nothing.
    It verifies the things #200 requirement 3 asks for and that a hand-edit could silently
    break: that the package declares itself, that the console entry point resolves to this
    module's `main`, that the registry ships as package data, and that this unit's config
    section is present and complete WITHOUT any sibling's section having been disturbed.
    """
    stream = stream or sys.stdout
    checks = []

    def check(name, got, want=True):
        ok = got == want
        checks.append(ok)
        stream.write("%-4s %s\n" % ("ok" if ok else "FAIL", name))
        if not ok:
            stream.write("       got : %r\n       want: %r\n" % (got, want))

    here = os.path.dirname(os.path.abspath(__file__))
    stem = os.path.splitext(os.path.basename(os.path.abspath(__file__)))[0]

    path = os.path.join(here, "pyproject.toml")
    check("pyproject.toml exists", os.path.isfile(path))
    text = open(path).read() if os.path.isfile(path) else ""
    check("it declares the import package", 'packages = ["%s"]' % IMPORT_PACKAGE in text)
    check("it maps the package onto this directory", '%s = "."' % IMPORT_PACKAGE in text)
    check("it ships registry.json as package data", '%s = ["registry.json"]' % IMPORT_PACKAGE in text)
    check("it declares a console entry point for this module",
          '"%s.%s:main"' % (IMPORT_PACKAGE, stem) in text)
    check("this module actually defines that main()", callable(globals().get("main")))
    check("it names setuptools as the build backend", "setuptools.build_meta" in text)

    init = os.path.join(here, "__init__.py")
    check("__init__.py exists", os.path.isfile(init))
    check("__init__.py enumerates no modules (so siblings never conflict)",
          stem not in open(init).read() if os.path.isfile(init) else False)

    reg = os.path.join(here, "registry.json")
    check("registry.json exists", os.path.isfile(reg))
    doc = json.load(open(reg)) if os.path.isfile(reg) else {}
    node = doc
    for key in UNIT_PATH:
        node = node.get(key, {}) if isinstance(node, dict) else {}
    check("our config section is present", isinstance(node, dict) and bool(node))
    template = config_template()
    missing = [k for k in template if k not in node]
    check("our section has every key config_template() names (missing: %r)" % missing, not missing)
    extra = [k for k in node if k not in template]
    check("our section has no key config_template() does not name (extra: %r)" % extra, not extra)
    check("the registry carries a package-wide bug_reports sink", bool(doc.get("bug_reports")))

    # ADDITIVITY (#410) — the invariant a single snapshot CAN prove. Whether a sibling has a
    # config section is that sibling's business and none of ours; what must hold is that
    # regenerating the scaffolding for THIS module left every sibling's console entry point
    # standing. A generator that clobbered a sibling would drop its script here.
    siblings = sorted(s for s in _sibling_stems(here) if s != stem)
    lost = [s for s in siblings
            if _defines_main(os.path.join(here, s + ".py"))
            and '"%s.%s:main"' % (IMPORT_PACKAGE, s) not in text]
    check("every sibling's console entry point survives (siblings: %r, lost: %r)"
          % (siblings, lost), not lost)

    bad = checks.count(False)
    stream.write("\n%d/%d checks passed\n" % (len(checks) - bad, len(checks)))
    return 1 if bad else 0


def _sibling_stems(here):
    """The module stems in this package directory — the same rule forge_package.py uses."""
    return [os.path.splitext(n)[0] for n in os.listdir(here)
            if n.endswith(".py") and n != "__init__.py"]


def _defines_main(path):
    """True if the Python file defines a top-level `main()` — forge_package.py's own signal for
    a console entry point. Mirrors its `defines_main()`, by AST, so no sibling is imported."""
    import ast
    try:
        with open(path, "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
    except (OSError, SyntaxError, ValueError):
        return False
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "main"
               for n in tree.body)


if __name__ == "__main__":
    main()
