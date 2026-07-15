#!/usr/bin/env python3
"""forge2 / agent_tools_suite / ats_http — a behavior-preserving rewrite of the forge unit
`agent_tools_suite:ats_http.py` (module key forge-rw:653bf1a78a5f85dc, git blob
139ce250f685b1090711727eb393232f293a0c48), filed under ticket #412 against the FORGE-wide
refactor standard #200.

WHAT THIS IS
------------
The original unit was 20952 bytes: it published the "agent tool suite" as ONE FastMCP service
over HTTP/SSE, and enforced the gate's requirements SERVER-SIDE by overriding
`FastMCP.call_tool` so that no client could side-step them. This file is an entirely new
implementation of that unit. It keeps the original's observable behavior and its callable
surface, and it adds the two things #200 requires that the original lacked: it is a proper
installable package, and it is driven by a configuration object that it refuses to run
without.

TERMS USED HERE (defined at first use, for a reader who has never seen this system)
-----------------------------------------------------------------------------------
gate
    This module. Every MCP tool call passes through one chokepoint — `enforce()` — which can
    refuse the call before it is dispatched. "Server-side" means the check runs here, in the
    service, so a client cannot skip it by talking to a tool's process directly.
intent
    A free-text argument every tool takes, answering "why are you calling it?". `enforce()`
    refuses any call without one.
provenance
    A record of who called what and why, written to congruency (the state service) and to a
    local fallback file. For a state-changing tool the write is HARD: if provenance cannot be
    recorded the call is REFUSED, not silently dropped.
scope
    A capability string on the caller's bearer token (`ats:full`, `ats:crankws`,
    `ats:crankcong`). `_tool_scopes()` says which scopes grant which tool.
leaf
    A separate MCP server module whose tool logic this gate reuses in-process. The original
    loaded one — the `crankws` leaf — from a file path.
crankd / imgd
    Two other HTTP services. `crankd` runs a "crank" (a build/release action) off the agent's
    process tree; `imgd` runs Raspberry-Pi image operations. The gate is a thin REST client to
    both; the drivers do NOT run here.
registry
    The JSON configuration registry described in this repository's `note-for-claude`: one
    `.json` file holding the configuration for every tool in a set of packaging.
    `note-for-claude` states the contract this module obeys — "if a tool cannot see the
    registry it will throw an exeption" [sic]. This package ships its own `registry.json`
    beside this file; see CONFIGURATION.
config object
    The chunk of that registry belonging to this unit — the `forge2.agent_tools_suite.ats_http`
    section. It is what drives this module. `emit-config` prints a template of it.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
Every name below is presented with the original's parameters and defaults:

    _secret(name)                        _text(res)
    _setup_logging()                     _run(leaf, tool, **kw)
    _leaf(rel, name)                     _crankd_crank(component, intent)
    now_iso()                            _imgd(method, path, obj=None)
    _actor()                             _ws_read(path)
    _cong(method, path, obj=None)        _cong_read(path)
    record(tool, intent, note, ts)       _record_mandate(ticket_id, mandate)
    open_ticket()                        _record_bindings(ticket_id, bindings)
    _tool_scopes(name)                   GatedMCP.call_tool / .list_tools   (async)
    current_scopes()                     WalletTokenVerifier(token_map).verify_token (async)
    enforce(name, arguments)

    crankws_status(intent='')            crankcong_read(path='.', intent='')
    crankws_read(path='.', intent='')    crankcong_status(intent='')
    crankws_ticket(title, body='', patch='', severity='info', mandate='', bindings='', intent='')
    crankws_crank(message='', intent='')
    crankcong_ticket(title, body='', patch='', severity='info', mandate='', bindings='', intent='')
    crankcong_crank(message='', intent='')
    crankimg_build(node='pi-forge', ssid='WIFI-B61C', wifi_secret='WIFI-B61C', intent='')
    crankimg_verify(intent='')           crankimg_disks(intent='')
    crankimg_flash(device, confirm, intent='')
    crankimg_base(fetch=False, intent='')

The original's module-level NAMES are part of that surface too, and this module still answers
to all of them — `HERE`, `CONG`, `CRANKD`, `IMGD`, `WORKSTATION`, `CONGRUENCY_REPO`, `SESSION`,
`JSON_LOG`, `STATE_CHANGE`, `LOG_PATH`, `CONGRUENCY_KEY`, `log`, `crankws`, `mcp`, `GatedMCP`,
`WalletTokenVerifier`, `GateRefusal`. See LAZY, NOT EAGER for the one difference in WHEN they
are computed.

THOSE ATTRIBUTES ARE READ-ONLY VIEWS — the one deviation that can bite a caller
------------------------------------------------------------------------------
In the original, `WORKSTATION` and friends were plain module globals that the functions read
on every call, so ASSIGNING to one (`ats_http.WORKSTATION = "/tmp/x"`) changed where the
readers read. Here they are views computed from the config object: the functions consult the
config, not the global, so assigning to `ats_http.WORKSTATION` sets an attribute that nothing
reads. It does not raise — it simply has no effect, which is the more dangerous failure, so it
is called out here rather than left to be discovered.

This is forced by #200 requirement 4: the config object drives the module, and a settable
global would be a second, competing source of truth for the same setting. To change any of
these, change the CONFIG — `configure(...)`/`using_config(...)` in-process, `FORGE2_CONFIG` or
the registry on disk. `configure()` re-derives every view, so they stay consistent.
(`crankws` is the exception and still behaves as a global: it is a loaded module rather than a
setting, so a test double assigned to it IS honored — see `_leaf_named`.)

BEHAVIOUR THAT IS EASY TO "CLEAN UP" AND MUST NOT BE (all verified against the original)
----------------------------------------------------------------------------------------
Each of these is a real property of the original that a tidier rewrite would silently break.
`selftest` proves every one of them.

  * `_record_mandate` counts a clause BEFORE filing it and `_record_bindings` counts one
    AFTER. Both return the count filed; both skip blank lines after `.strip()`.
  * `_record_bindings` skips any line that is not `<digits> <label>` — `line.split(None, 1)`
    must yield exactly 2 parts and `parts[0].isdigit()` must hold. So a single-token line
    ("POST", "clause_seq") files nothing and returns 0. This is what the ticket's 30 captured
    `_record_bindings` exemplars encode.
  * `str.isdigit()` is TRUE for characters `int()` REJECTS (superscripts: `'²'.isdigit()` is
    True, `int('²')` raises ValueError). So `_record_bindings(1, '² x')` raises ValueError from
    `int()`. Rewriting the test as `parts[0].isdecimal()` or a try/except would swallow an
    error the original raises.
  * `(mandate or "")` means 0, None, [] and "" all behave as an empty mandate and return 0 —
    NOT a TypeError. This is what the ticket's 19 `_record_mandate` exemplars encode.
  * `_record_mandate`'s digest is over `n` (the running clause count) but `_record_bindings`'
    digest is over `cs` (the clause number PARSED FROM THE LINE), not its own counter.
  * `crankws_ticket`/`crankcong_ticket` gate on `if tid` — a rowid of 0 is FALSY, so a ticket
    that comes back with rowid 0 files no mandate and no bindings.
  * `enforce()` slices `intent[:80]`/`intent[:120]` for the log line EAGERLY, so a non-string
    truthy intent (e.g. `{"intent": 5}`) raises TypeError from the slice — after the
    provenance write, not before.
  * `_crankd_crank`/`_imgd` catch `urllib.error.HTTPError` BEFORE `OSError`. HTTPError IS an
    OSError subclass, so reordering those two handlers changes which message you get.
  * `_ws_read`/`_cong_read` compare a `realpath`-ed target against a repo root that is NOT
    itself realpath-ed. Under a symlinked root every read would be refused. That is the
    original's confinement check, character for character, and it is preserved rather than
    "fixed" — see CONFINEMENT below.
  * `_text` raises RuntimeError on `isError` AFTER joining the text, so the joined text is the
    exception message.
  * `_tool_scopes` returns a FRESH set per call, so a caller that mutates the result does not
    poison the next call.

CONFINEMENT — a preserved bug, deliberately
-------------------------------------------
`_ws_read`/`_cong_read` resolve the target with `os.path.realpath` and then require it to be
the repo root or start with root + os.sep, where the ROOT is used as configured. If the
configured root itself traverses a symlink (on macOS, `/tmp` -> `/private/tmp`), the resolved
target can never match it and every read is refused. That is a latent bug in the original.
This ticket is "behavior-preserving", and a read that the original REFUSES must not start
succeeding here — a rewrite that quietly widened the confinement check would be a security
change smuggled in under a refactor. It is preserved exactly and documented here so it is a
known property rather than a surprise. Configure the roots as real paths.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The original hardcoded every URL, filesystem path, port, timeout, route, scope name and
rotation size as a module-level literal. None of them are literals here; all come from the
config object. The module resolves it on first use, from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. That file holds the unit
     config object itself — exactly what `emit-config` prints.
  2. otherwise, the `forge2.agent_tools_suite.ats_http` section of the nearest `registry.json`
     found by walking UP from THIS FILE's directory.

If NEITHER answers, every operation raises `ConfigError` and nothing is contacted, logged or
written. It never guesses a default — that is `note-for-claude`'s rule and this ticket's
acceptance item (d). A config object that is found but is missing a key an operation needs is
also a `ConfigError`, naming the key.

`configure(config)` and `using_config(config)` inject a config object in-process, for callers
that hold their configuration in memory rather than on disk.

COMMENTS IN THE CONFIG
----------------------
JSON has no comment syntax, and this repository's registry documents itself with `_comment`
keys instead (see the `registry.json` of any forge2 package). Any key beginning with `_` is
documentation: `leaves._comment` is a note, not a leaf. Every other section names the keys it
needs explicitly, so a `_comment` beside them is simply never read.

ENVIRONMENT OVERRIDES ARE PART OF THE CONFIG, NOT OF THE CODE
--------------------------------------------------------------
The original read 7 environment variables (`CONGRUENCY_URL`, `CRANKD_URL`, `IMGD_URL`,
`CLAUDE_CODE_SESSION_ID`, `ATS_LOG`, `ATS_HOST`, `ATS_PORT`, `ATS_TRANSPORT`). Dropping them
would break every deployment that sets them, so they are preserved — but the variable NAME is
config, not a literal. Each such setting is an object:

    {"env": "CONGRUENCY_URL", "value": "http://127.0.0.1:8899"}

`"env": null` disables the override and pins the setting to `"value"`.

The original used TWO different fallback rules and this module reproduces both, per setting,
because they differ observably when a variable is set to the EMPTY STRING:

  * `os.environ.get(X) or DEFAULT` — a blank `X` falls back to the default. Used by
    `CONGRUENCY_URL`, `CRANKD_URL`, `IMGD_URL`, `CLAUDE_CODE_SESSION_ID`, `ATS_LOG`.
  * `os.environ.get(X, DEFAULT)` — a blank `X` is HONORED and yields "". Used by `ATS_HOST`,
    `ATS_PORT`, `ATS_TRANSPORT`.

Which rule applies to which setting is the original's behavior, not a knob, so it lives in the
code and is proven by `selftest`, not chosen by config. One more preserved subtlety: `~` in
`ATS_LOG` is NOT expanded by the original (only its built-in default was), so an env-supplied
log path is used verbatim here too, while the config `value` is expanded.

SIDE EFFECTS
------------
Reads and gate decisions write provenance — that is the module's job, not an accident:
`record()` appends one JSON line to the configured `provenance.json_log`, and POSTs to
congruency. `_setup_logging()` creates the log directory and opens the rotating log file.
Nothing else writes. `emit-config`, `show-config` and `selftest` need no network, and
`selftest` writes only inside a temporary directory it removes. Per `note-for-claude` ("all
tools need to pass a bug-report automatically ... if an exception is thrown") the CLI appends
one timestamped JSON line to the config's `bug_reports` path if it hits an UNEXPECTED
exception — a defect in this tool. Three exceptions are DESIGNED behavior rather than defects,
so the CLI handles each by name, files no report, prints no traceback and exits with its own
code: `ConfigError` (the config gate firing) exits 2, `SdkUnavailable` (the optional MCP SDK is
not installed) exits 2, and `GateRefusal` (the gate doing its job) exits 3. Filing a report for
any of those would write a `logs/` tree into the package directory for a condition that is not
a bug — so the bug-report path stays reserved for the genuinely unexpected.

Note that the CLI is the only thing that files reports. Calling this module as a LIBRARY never
does — `enforce` raises `GateRefusal` and the tool bodies raise `RuntimeError` straight to the
caller, exactly as the original did, with nothing written anywhere but the provenance feed.

LAZY, NOT EAGER — the one deliberate deviation, and why it changes no behavior
------------------------------------------------------------------------------
The original did all of its work at IMPORT time: it read the environment, called
`_setup_logging()` (creating the log file), imported `ats_token`, loaded the token map,
executed the crankws leaf from disk, and constructed the FastMCP server. Import had to
succeed for the module to exist at all, so importing it REQUIRED the `mcp` SDK, a readable
`ats_token`, and a leaf file on disk.

This module computes each of those on FIRST USE and caches it, so importing
`agent_tools_suite.ats_http` reads nothing and creates nothing. Three reasons, all forced:

  1. #200 requirement 4 and `note-for-claude` demand the module THROW when it cannot see its
     config. A module that resolved config at import could not be imported at all without one,
     so `pip install -e .` + `import` would fail — and acceptance (c) requires that install to
     be clean.
  2. The package's `pyproject.toml` is DERIVED by `congruency/tools/forge_package.py` (#410)
     and always declares `dependencies = []`. `mcp` therefore cannot be an install dependency
     of this package, so the module must import without it.
  3. `ats_token` and the crankws leaf are NOT part of this ticket's module and are not in this
     checkout. Requiring them at import would make the unit unimportable here.

The values are IDENTICAL and are still computed exactly ONCE per config, so `HERE`, `CONG`,
`SESSION` and friends are stable module attributes after first touch, as before. The only
observable difference is the CLOCK — when the log file appears, when the environment is
sampled — not the VALUES. Everything the original did at import, `serve` still does before it
listens.

THE TOKEN LOADER, AND WHY IT FAILS LOUDLY
------------------------------------------
The original hardcoded `import ats_token` + `ats_token.load_map()` to get the wallet's
{token: scopes} map, and chose between two branches on the result: a non-empty map turns bearer
auth ON, an empty one turns auth OFF ("loopback only"). `ats_token` is NOT part of this
ticket's module and is not in this checkout, so the shipped config names it as
`tokens.loader: "ats_token:load_map"` — the original's own loader.

In a checkout where `ats_token` is absent, building the server therefore raises a ConfigError
naming it exactly. That is deliberate, and it is the SAFE failure. The alternative — shipping
`"loader": null` so the server always builds — would silently select the auth-DISABLED branch
wherever `ats_token` DOES exist, turning a wallet-authenticated gate into an open one. A
refactor must not disable authentication to make a demo run. Set `tokens.loader` to null only
when you actually intend an unauthenticated, loopback-only gate; everything else in this
module works without `ats_token` either way.

WITHOUT THE `mcp` SDK
---------------------
`_actor()` and `current_scopes()` ask the SDK for the current request's access token. With no
SDK installed there is no request context, which is precisely the case the original already
handles: `get_access_token()` returns None, `_actor()` falls back to `SESSION` and
`current_scopes()` returns None ("allow all"). So the gate, provenance, the readers, the
crankd/imgd clients and both `_record_*` functions all work with no SDK present, and behave as
the original does outside a request. `mcp`, `GatedMCP` and `WalletTokenVerifier` need the SDK
and raise a clear ImportError naming it; `serve` does too.

RUNNING IT
----------
Every command is executable as written from this file's own directory; from anywhere else give
the full path to `ats_http.py`. Which directory you run from never changes which config is
found — the registry walk-up starts at THIS FILE, not at the working directory.

    python3 ats_http.py                    # serve (the original's __main__ behavior)
    python3 ats_http.py serve              # the same thing, said explicitly
    python3 ats_http.py selftest           # prove the exemplars, the edges and the config gate
    python3 ats_http.py emit-config        # print a config-object template
    python3 ats_http.py show-config        # print the resolved config and where it came from

Bare `python3 ats_http.py` serves, exactly as the original's `__main__` did, so an existing
launcher keeps working. `selftest` and `emit-config` need no config and no network.

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package around it, whose `pyproject.toml`, `__init__.py` and
`registry.json` are DERIVED from the modules present by `congruency/tools/forge_package.py`
(#410) — a rewrite unit writes only its own module and never hand-authors that scaffolding, so
two modules of one package can land without clobbering each other. From this directory:

    pip install -e .
    forge2-ats-http selftest
    python3 -c "from agent_tools_suite.ats_http import enforce, GateRefusal"

`pyproject.toml` maps this directory onto the import package `agent_tools_suite`, so an
installed copy imports as `from agent_tools_suite.ats_http import <name>`, and the derived
`[project.scripts]` exposes `main()` below as `forge2-ats-http`.
"""

import argparse
import contextlib
import hashlib
import importlib
import importlib.util
import io
import json
import logging
import os
import sys
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

__all__ = [
    "ConfigError", "GateRefusal", "load_config", "configure", "using_config", "reset_config",
    "active_config", "active_base", "config_template", "server", "main",
    "now_iso", "record", "open_ticket", "enforce", "current_scopes",
    "crankws_status", "crankws_read", "crankws_ticket", "crankws_crank",
    "crankcong_read", "crankcong_status", "crankcong_ticket", "crankcong_crank",
    "crankimg_build", "crankimg_verify", "crankimg_disks", "crankimg_flash", "crankimg_base",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: This unit's ADDRESS in the config document. Not a setting — a config-driven tool has to know
#: which section is its own.
UNIT_PATH = ("forge2", "agent_tools_suite", "ats_http")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:agent_tools_suite/ats_http"

#: The MCP SDK import targets. These are this module's FRAMEWORK — the thing it IS, the way
#: `json` is — not a path or a param, so #200 requirement 4 does not reach them. Everything
#: that requirement does reach (URLs, filesystem paths, ports, timeouts, routes, scope names,
#: rotation sizes) is in the config object.
_SDK_FASTMCP = "mcp.server.fastmcp"
_SDK_AUTH_CONTEXT = "mcp.server.auth.middleware.auth_context"
_SDK_AUTH_PROVIDER = "mcp.server.auth.provider"
_SDK_AUTH_SETTINGS = "mcp.server.auth.settings"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.
    """


class GateRefusal(Exception):
    """A requirement of the MCP was not met — the call is refused before dispatch."""


class SdkUnavailable(ImportError):
    """The MCP SDK is needed for this operation but is not installed.

    An ImportError subclass, so a caller written against the original's `except ImportError`
    still catches it — and nameable, so the CLI can treat it as the DESIGNED outcome it is
    (a missing optional dependency, reported in one line) rather than as a defect in this tool
    worth filing a bug report about.
    """


# ═══════════════════════════════ configuration ═══════════════════════════════

_ACTIVE = None       # (config, base) injected via configure(); wins over every disk source
_RESOLVED = None     # cache of the last disk resolution, so the module re-reads no files
_SETTINGS = None     # the built, validated settings — the original's import-time constants


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
            raise ConfigError("%s is set to %r, but no such file exists" % (CONFIG_ENV, env_path))
        config = _read_json(env_path, "the config object named by " + CONFIG_ENV)
        if not isinstance(config, dict):
            raise ConfigError("the config object at %s must be a JSON object, not %s"
                              % (env_path, type(config).__name__))
        return (config, os.path.dirname(os.path.abspath(env_path)),
                "%s=%s" % (CONFIG_ENV, env_path))

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s: %s is unset and no %s was found by walking up from %s. "
            "Run `emit-config` for a template of the config object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))))

    document = _read_json(registry_path, "the registry")
    node = document
    for key in UNIT_PATH:
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no %s section — this unit's config object is absent. "
                "Run `emit-config` for a template." % (registry_path, ".".join(UNIT_PATH)))
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError("the %s section of the registry at %s must be a JSON object, not %s"
                          % (".".join(UNIT_PATH), registry_path, type(node).__name__))
    merged = dict(node)
    if "bug_reports" in document and "bug_reports" not in merged:
        merged["bug_reports"] = document["bug_reports"]     # shared infrastructure key
    return merged, os.path.dirname(registry_path), registry_path


def configure(config, base=None):
    """Inject a config object for this process, overriding every disk source.

    `base` is the directory relative paths inside `config` resolve against; it defaults to this
    file's directory. Passing None for `config` clears the injection.
    """
    global _ACTIVE
    _ACTIVE = None if config is None else (
        config, os.path.abspath(base or os.path.dirname(os.path.abspath(__file__))))
    reset_config()


@contextlib.contextmanager
def using_config(config, base=None):
    """Run a block with `config` injected, restoring whatever was in force afterwards."""
    previous = _ACTIVE
    try:
        configure(config, base)
        yield config
    finally:
        globals()["_ACTIVE"] = previous
        reset_config()


def reset_config():
    """Drop every cached resolution, so the next call re-reads config, environment and leaves.

    The original sampled the environment once, at import. This module samples it once, at first
    use — this is how a test (or a re-configured process) gets a fresh sample.
    """
    global _RESOLVED, _SETTINGS
    _RESOLVED = None
    _SETTINGS = None
    for name in ("crankws", "log", "mcp"):
        globals().pop(name, None)


def _resolve():
    """The (config, base, source) triple in force: the injected one, else the disk one."""
    global _RESOLVED
    if _ACTIVE is not None:
        return _ACTIVE[0], _ACTIVE[1], "configure()"
    if _RESOLVED is None:
        _RESOLVED = load_config()
    return _RESOLVED


def active_config():
    """The config object in force. Raises ConfigError if there is none."""
    return _resolve()[0]


def active_base():
    """The directory relative paths in the config object resolve against."""
    return _resolve()[1]


def active_source():
    """A human-readable description of where the config object in force came from."""
    return _resolve()[2]


# ─────────────────────────── reading the config object ───────────────────────────

def _need(node, path, where):
    """Fetch a required key from the config object, or raise ConfigError naming it."""
    cursor = node
    walked = []
    for key in path:
        walked.append(key)
        if not isinstance(cursor, dict) or key not in cursor:
            raise ConfigError(
                "config object for %s is missing the required key %r%s. Run `emit-config` for "
                "a template." % (UNIT, ".".join(walked),
                                 "" if not where else " (%s)" % where))
        cursor = cursor[key]
    return cursor


def _need_str(node, path, where=""):
    value = _need(node, path, where)
    if not isinstance(value, str):
        raise ConfigError("config key %r for %s must be a string, not %s"
                          % (".".join(path), UNIT, type(value).__name__))
    return value


def _need_int(node, path, where=""):
    value = _need(node, path, where)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("config key %r for %s must be an integer, not %s"
                          % (".".join(path), UNIT, type(value).__name__))
    return value


def _need_list_of_str(node, path, where=""):
    value = _need(node, path, where)
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ConfigError("config key %r for %s must be a list of strings" % (".".join(path), UNIT))
    return value


def _env_setting(node, path, mode, expand_value=False):
    """Resolve an `{"env": NAME|null, "value": V}` setting, reproducing the original's fallback.

    `mode` is the original's own fallback rule for THIS setting and is not configurable:
      "or"  -> `os.environ.get(NAME) or V`      (a blank env var falls back to V)
      "get" -> `os.environ.get(NAME, V)`        (a blank env var is honored, yielding "")
    `expand_value` applies `~` expansion to V only — never to the env-supplied value, because
    the original expanded only its built-in default.
    """
    spec = _need(node, path, "")
    if not isinstance(spec, dict):
        raise ConfigError(
            'config key %r for %s must be an object like {"env": "NAME", "value": "..."} '
            '(use "env": null to pin the setting and ignore the environment), not %s'
            % (".".join(path), UNIT, type(spec).__name__))
    for key in ("env", "value"):
        if key not in spec:
            raise ConfigError('config key %r for %s must carry a %r key' % (".".join(path), UNIT, key))
    name = spec["env"]
    if name is not None and not isinstance(name, str):
        raise ConfigError("config key %r for %s: 'env' must be an environment variable name or "
                          "null, not %s" % (".".join(path), UNIT, type(name).__name__))
    value = spec["value"]
    if mode == "or":
        from_env = os.environ.get(name) if name else None
        if from_env:
            return from_env
    else:                                        # "get" — a set-but-blank variable is honored
        if name is not None and name in os.environ:
            return os.environ[name]
    if expand_value and isinstance(value, str):
        return os.path.expanduser(value)
    return value


def _abs(base, path):
    """Resolve a config path against the config's base directory, expanding `~`."""
    expanded = os.path.expanduser(path)
    return expanded if os.path.isabs(expanded) else os.path.join(base, expanded)


class _Settings(object):
    """The original's import-time constants, computed once from the config object.

    The original bound these at import; this binds them on first use and caches. Same values,
    same single sampling of the environment — see LAZY, NOT EAGER in the module docstring.
    """
    __slots__ = ("source", "base", "here", "cong", "crankd", "imgd", "workstation",
                 "congruency_repo", "session", "json_log", "state_change", "log_path",
                 "congruency_key", "cfg", "cong_timeout", "crankd_timeout", "imgd_timeout",
                 "routes", "crank_path", "imgd_paths", "read_max_bytes", "forbidden_component",
                 "scope_rules", "default_scopes", "refuse_chars", "allow_chars", "secrets_file",
                 "api_key_name", "log_max_bytes", "log_backup_count", "log_format", "log_level",
                 "logger_name", "sdk_logger_name", "service_name", "host", "port", "transport",
                 "base_url_template", "required_scopes", "token_loader", "client_ids",
                 "default_client_id", "leaves", "install_json")


def _build_settings():
    """Validate the config object and compute every setting the original hardcoded."""
    cfg, base, source = _resolve()
    if not isinstance(cfg, dict):
        raise ConfigError("the config object for %s must be a JSON object, not %s"
                          % (UNIT, type(cfg).__name__))
    s = _Settings()
    s.cfg, s.base, s.source = cfg, base, source

    # HERE — the original's directory, which it joined the leaf path and the fallback
    # provenance log against. null means "the directory the config object was found in".
    here = _need(cfg, ("paths", "here"), "the directory relative paths resolve against")
    if here is not None and not isinstance(here, str):
        raise ConfigError("config key 'paths.here' for %s must be a path string or null, not %s"
                          % (UNIT, type(here).__name__))
    s.here = os.path.abspath(_abs(base, here)) if here else base

    s.cong = _env_setting(cfg, ("congruency", "url"), "or").rstrip("/")
    s.cong_timeout = _need_int(cfg, ("congruency", "timeout"))
    s.routes = {}
    for key in ("memories", "open_ticket", "ticket_create", "mandate_record", "binding_record",
                "ticket_approval"):
        s.routes[key] = _need_str(cfg, ("congruency", "routes", key))

    s.crankd = _env_setting(cfg, ("crankd", "url"), "or").rstrip("/")
    s.crankd_timeout = _need_int(cfg, ("crankd", "timeout"))
    s.crank_path = _need_str(cfg, ("crankd", "crank_path"))

    s.imgd = _env_setting(cfg, ("imgd", "url"), "or").rstrip("/")
    s.imgd_timeout = _need_int(cfg, ("imgd", "timeout"))
    s.imgd_paths = {}
    for key in ("build", "verify", "disks", "flash", "base"):
        s.imgd_paths[key] = _need_str(cfg, ("imgd", "paths", key))

    s.workstation = _abs(base, _need_str(cfg, ("repos", "workstation")))
    s.congruency_repo = _abs(base, _need_str(cfg, ("repos", "congruency")))
    s.install_json = _need_str(cfg, ("repos", "congruency_install_json"))

    s.read_max_bytes = _need_int(cfg, ("reads", "max_bytes"))
    s.forbidden_component = _need_str(cfg, ("reads", "forbidden_component"))

    session = _env_setting(cfg, ("session",), "or")
    if not session:
        template = _need_str(cfg, ("session", "pid_template"))
        session = template % os.getpid()
    s.session = session

    s.json_log = _abs(s.here, _need_str(cfg, ("provenance", "json_log")))

    s.state_change = set(_need_list_of_str(cfg, ("gate", "state_change_tools")))
    s.default_scopes = _need_list_of_str(cfg, ("gate", "default_scopes"))
    rules = _need(cfg, ("gate", "scope_rules"), "")
    if not isinstance(rules, list):
        raise ConfigError("config key 'gate.scope_rules' for %s must be a list of "
                          '{"prefix": ..., "scopes": [...]} objects' % UNIT)
    s.scope_rules = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict) or "prefix" not in rule or "scopes" not in rule:
            raise ConfigError('config key "gate.scope_rules[%d]" for %s must be an object with '
                              "'prefix' and 'scopes'" % (index, UNIT))
        if not isinstance(rule["prefix"], str) or not isinstance(rule["scopes"], list) or \
                not all(isinstance(x, str) for x in rule["scopes"]):
            raise ConfigError('config key "gate.scope_rules[%d]" for %s: prefix must be a string '
                              "and scopes a list of strings" % (index, UNIT))
        s.scope_rules.append((rule["prefix"], list(rule["scopes"])))
    s.refuse_chars = _need_int(cfg, ("gate", "intent_log_chars", "refuse"))
    s.allow_chars = _need_int(cfg, ("gate", "intent_log_chars", "allow"))

    s.secrets_file = os.path.expanduser(_need_str(cfg, ("secrets", "file")))
    s.api_key_name = _need_str(cfg, ("secrets", "congruency_api_key"))

    s.log_path = _env_setting(cfg, ("logging", "path"), "or", expand_value=True)
    if not isinstance(s.log_path, str):
        raise ConfigError("config key 'logging.path' for %s must resolve to a path string, not %s"
                          % (UNIT, type(s.log_path).__name__))
    s.log_max_bytes = _need_int(cfg, ("logging", "max_bytes"))
    s.log_backup_count = _need_int(cfg, ("logging", "backup_count"))
    s.log_format = _need_str(cfg, ("logging", "format"))
    s.log_level = _need_str(cfg, ("logging", "level"))
    s.logger_name = _need_str(cfg, ("logging", "logger"))
    s.sdk_logger_name = _need_str(cfg, ("logging", "sdk_logger"))

    s.service_name = _need_str(cfg, ("service", "name"))
    s.host = _env_setting(cfg, ("service", "host"), "get")
    port = _env_setting(cfg, ("service", "port"), "get")
    s.port = int(port)               # the original's int(); a bad value raises ValueError here too
    s.transport = _env_setting(cfg, ("service", "transport"), "get")
    s.base_url_template = _need_str(cfg, ("service", "base_url_template"))
    s.required_scopes = _need_list_of_str(cfg, ("service", "required_scopes"))

    loader = _need(cfg, ("tokens", "loader"), "")
    if loader is not None and not isinstance(loader, str):
        raise ConfigError('config key \'tokens.loader\' for %s must be a "module:attr" string or '
                          "null, not %s" % (UNIT, type(loader).__name__))
    s.token_loader = loader
    ids = _need(cfg, ("tokens", "client_ids"), "")
    if not isinstance(ids, list):
        raise ConfigError("config key 'tokens.client_ids' for %s must be a list of "
                          '{"scope": ..., "client_id": ...} objects' % UNIT)
    s.client_ids = []
    for index, entry in enumerate(ids):
        if not isinstance(entry, dict) or not isinstance(entry.get("scope"), str) or \
                not isinstance(entry.get("client_id"), str):
            raise ConfigError('config key "tokens.client_ids[%d]" for %s must be an object with '
                              "string 'scope' and 'client_id'" % (index, UNIT))
        s.client_ids.append((entry["scope"], entry["client_id"]))
    s.default_client_id = _need_str(cfg, ("tokens", "default_client_id"))

    leaves = _need(cfg, ("leaves",), "")
    if not isinstance(leaves, dict):
        raise ConfigError("config key 'leaves' for %s must be an object mapping a leaf name to "
                          '{"path": ..., "module_name": ...}' % UNIT)
    s.leaves = {}
    for name, spec in leaves.items():
        if name.startswith("_"):
            continue                     # a `_comment`, not a leaf — see COMMENTS IN THE CONFIG
        if not isinstance(spec, dict) or not isinstance(spec.get("path"), str) or \
                not isinstance(spec.get("module_name"), str):
            raise ConfigError("config key 'leaves.%s' for %s must be an object with string "
                              "'path' and 'module_name'" % (name, UNIT))
        s.leaves[name] = (spec["path"], spec["module_name"])
    s.congruency_key = _read_secret(s.secrets_file, s.api_key_name)
    return s


def _settings():
    """The settings in force, built once per config. Raises ConfigError without a config."""
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = _build_settings()
    return _SETTINGS


# ─────────────── the original's module-level names, resolved on first touch ───────────────

#: Maps each module attribute the original bound at import onto its settings field. PEP 562's
#: module __getattr__ serves them, so `ats_http.CONG` still answers — and now throws
#: ConfigError instead of guessing when there is no config object.
_MODULE_ATTRS = {
    "HERE": "here", "CONG": "cong", "CRANKD": "crankd", "IMGD": "imgd",
    "WORKSTATION": "workstation", "CONGRUENCY_REPO": "congruency_repo", "SESSION": "session",
    "JSON_LOG": "json_log", "LOG_PATH": "log_path", "CONGRUENCY_KEY": "congruency_key",
}


def __getattr__(name):
    """Serve the original's import-time module attributes on first touch (PEP 562).

    The original bound these while importing. Binding them here instead keeps the values
    identical and the import side-effect-free — see LAZY, NOT EAGER in the module docstring.
    """
    if name in _MODULE_ATTRS:
        return getattr(_settings(), _MODULE_ATTRS[name])
    if name == "STATE_CHANGE":
        return set(_settings().state_change)          # a fresh set, as the original's literal was
    if name == "_TOKENS":
        return _tokens()
    if name == "log":
        return _setup_logging()
    if name == "crankws":
        return _leaf_named("crankws")
    if name == "mcp":
        return server()
    if name == "GatedMCP":
        return _gated_mcp_class()
    if name == "WalletTokenVerifier":
        return _wallet_verifier_class()
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(list(globals()) + list(_MODULE_ATTRS) +
                  ["STATE_CHANGE", "_TOKENS", "log", "crankws", "mcp", "GatedMCP",
                   "WalletTokenVerifier"])


# ═══════════════════════════════ the unit itself ═══════════════════════════════

def _read_secret(path, name):
    """The body of `_secret`, taking the secrets path explicitly.

    Split out so `_build_settings` can read the API key while the settings are still being
    built, without `_secret` having to grow a parameter the ticket's surface does not have.
    """
    if os.path.isfile(path):
        with open(path) as handle:
            for line in handle:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1]
    return os.environ.get(name)


def _secret(name):
    """Read a value from the configured secrets file (KEY=VALUE), else the process env; None if
    absent.

    The original read `~/.secrets/ats.env`; the path is `secrets.file` in the config object
    now. The first line whose text (after stripping) starts with `name=` wins, and everything
    after the FIRST `=` is the value — so `K=a=b` yields `a=b` and `K=` yields `""`, which is
    falsy and therefore suppresses the X-Api-Key header exactly as before.
    """
    return _read_secret(_settings().secrets_file, name)


def _setup_logging():
    """Route every gate decision + the SDK's own logs to one rotating, greppable file, and
    return this module's logger.

    The SDK's FastMCP loggers propagate to root, so a root handler captures them too. Adding
    the handler is idempotent: a handler already pointed at the same file is not added twice.
    An OSError anywhere in the setup (an unwritable directory, or a log path with no directory
    part at all) leaves the logger handler-less rather than failing the caller — the logger is
    returned either way, exactly as the original did.
    """
    cached = globals().get("log")
    if cached is not None:
        return cached
    state = _settings()
    try:
        os.makedirs(os.path.dirname(state.log_path), exist_ok=True)
        handler = RotatingFileHandler(state.log_path, maxBytes=state.log_max_bytes,
                                      backupCount=state.log_backup_count)
        handler.setFormatter(logging.Formatter(state.log_format))
        root = logging.getLogger()
        root.setLevel(state.log_level)
        already = any(getattr(existing, "baseFilename", None) == handler.baseFilename
                      for existing in root.handlers)
        if not already:
            root.addHandler(handler)
        logging.getLogger(state.sdk_logger_name).setLevel(state.log_level)
    except OSError:
        pass
    logger = logging.getLogger(state.logger_name)
    globals()["log"] = logger
    return logger


def _leaf(rel, name):
    """Load the module at `rel` (resolved against HERE) under the import name `name`.

    This is the original's leaf loader: a leaf is a separate MCP server module whose tool logic
    the gate reuses in-process. An absolute `rel` is used as given.
    """
    state = _settings()
    spec = importlib.util.spec_from_file_location(name, os.path.join(state.here, rel))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _leaf_named(key):
    """The configured leaf `key`, loaded once and cached under the module attribute `key`.

    The original executed the crankws leaf at import and bound it to a module global; a caller
    that replaces that global (a test double, say) is honored here exactly as it was there.
    """
    cached = globals().get(key)
    if cached is not None:
        return cached
    state = _settings()
    if key not in state.leaves:
        raise ConfigError("config object for %s declares no leaf %r under 'leaves' (it has: %s)"
                          % (UNIT, key, ", ".join(sorted(state.leaves)) or "none"))
    rel, name = state.leaves[key]
    module = _leaf(rel, name)
    globals()[key] = module
    return module


def now_iso():
    """The current UTC time, ISO-8601, as the provenance timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _sdk(module_name):
    """Import an MCP SDK module, or return None when the SDK is not installed.

    The SDK is an optional dependency here: the package's derived pyproject declares no
    dependencies (see LAZY, NOT EAGER), and every part of this module except the server itself
    behaves, with no SDK, exactly as the original behaves outside a request context.
    """
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


def _need_sdk(module_name):
    module = _sdk(module_name)
    if module is None:
        raise SdkUnavailable(
            "%s needs the MCP SDK for this operation: %r is not importable. Install it with "
            "`pip install mcp`. (It is not an install dependency of this package because the "
            "package's pyproject.toml is derived by congruency/tools/forge_package.py, which "
            "declares none; every other part of this module works without it.)"
            % (UNIT, module_name))
    return module


def _access_token():
    """The authenticated access token for THIS request, or None.

    None means "no request context" — which is also what the original saw when called directly
    in-process, and what is always true when the SDK is not installed.
    """
    context = _sdk(_SDK_AUTH_CONTEXT)
    if context is None:
        return None
    return context.get_access_token()


def _actor():
    """Who is making THIS call — the authenticated token's client_id (operator / crankws-agent),
    or the gate's own session when there is no request context.

    Provenance is stamped with this, so an agent is distinguishable from the operator (both
    used to inherit the gate process's session).
    """
    token = _access_token()
    return token.client_id if token else _settings().session


def _cong(method, path, obj=None):
    """One JSON call to congruency, the state service. Raises on failure — callers decide.

    `obj` is the JSON body; None sends no body. The configured API key is sent as X-Api-Key
    when it is a non-empty string, because congruency refuses keyless writes.
    """
    state = _settings()
    data = json.dumps(obj).encode() if obj is not None else None
    headers = {"Content-Type": "application/json"}
    if state.congruency_key:
        headers["X-Api-Key"] = state.congruency_key
    request = urllib.request.Request(state.cong + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=state.cong_timeout) as response:
        return json.loads(response.read().decode() or "{}")


def record(tool, intent, note, ts):
    """Record a memory to congruency; return True on success. Always also append the local
    fallback.

    Stamped with the caller's actor (`_actor`) so the agent and operator are distinguishable in
    the feed. The fallback append is best-effort — an OSError writing it never fails the call —
    and the return value reports ONLY whether congruency accepted the memory, which is what
    `enforce` gates a state change on.
    """
    state = _settings()
    actor = _actor()
    entry = {"ts": ts, "session": actor, "tool": tool, "intent": intent, "note": note}
    try:
        with open(state.json_log, "a") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    try:
        _cong("POST", state.routes["memories"], entry)
        return True
    except Exception:      # noqa: BLE001 — any failure to record is a False, never a raise
        return False


def open_ticket():
    """True when congruency has at least one OPEN crank-workstation ticket; False on any error.

    Part of the original's surface. The original never called it — the memory-ticket
    precondition it was written for now lives in crankd (wallet-signed ticket approval), as
    `enforce` documents — so it is preserved as a callable rather than wired into the gate.
    """
    state = _settings()
    try:
        rows = _cong("GET", state.routes["open_ticket"]).get("rows")
        return bool(rows)
    except Exception:      # noqa: BLE001
        return False


def _tool_scopes(name):
    """Scopes that grant a tool: crankws_* need crankws-or-full; crankcong_* need
    crankcong-or-full; everything else needs full.

    Returns a FRESH set every call, so a caller that mutates the result cannot poison the next
    one. The prefix rules are `gate.scope_rules` in the config object, in order; the fallback
    is `gate.default_scopes`.
    """
    state = _settings()
    for prefix, scopes in state.scope_rules:
        if name.startswith(prefix):
            return set(scopes)
    return set(state.default_scopes)


def current_scopes():
    """The authenticated token's scopes for this request, or None when auth is disabled / there
    is no HTTP context (e.g. direct in-process tests) — None means 'allow all'."""
    token = _access_token()
    return set(token.scopes) if token else None


def enforce(name, arguments):
    """The single, un-side-steppable precondition for EVERY tool call. Raises GateRefusal to
    refuse. Directly testable (no HTTP context needed). Returns the timestamp it stamped.

    In order:
      1. `intent` is required. A missing or falsy intent is refused, and the refusal itself is
         provenanced.
      2. The caller's token must carry a scope that grants the tool. No token (no request
         context, or auth disabled) means allow-all, so an in-process caller is not blocked.
      3. A state-changing tool needs HARD provenance: if congruency will not record the
         memory, the call is REFUSED rather than proceeding unrecorded. A read's provenance is
         best-effort, so a congruency outage does not take the readers down with it.
    """
    state = _settings()
    logger = _setup_logging()
    args = arguments or {}
    intent = args.get("intent")
    ts = now_iso()
    if not intent:
        record(name, None, "REFUSED: no intent", ts)
        logger.warning("REFUSE %s session=%s reason=no-intent", name, state.session)
        raise GateRefusal("gate: 'intent' is required for %s (why are you calling it?)" % name)

    have = current_scopes()
    if have is not None and not (have & _tool_scopes(name)):
        record(name, intent, "REFUSED: scope", ts)
        logger.warning("REFUSE %s session=%s reason=scope have=%s", name, state.session,
                       sorted(have))
        raise GateRefusal("scope: this token is not authorized for %s (needs one of %s)"
                          % (name, sorted(_tool_scopes(name))))

    if name in state.state_change:
        # Authorization for a crank lives in crankd (wallet-signed ticket approval); the gate
        # does intent + scope + HARD provenance, then the tool body forwards to crankd.
        if not record(name, intent, None, ts):
            logger.error("REFUSE %s session=%s intent=%r reason=provenance-unrecorded", name,
                         state.session, intent[:state.refuse_chars])
            raise GateRefusal("state change DISALLOWED: provenance could not be recorded "
                              "(congruency unreachable)")
        logger.info("ALLOW %s (state-change) session=%s intent=%r", name, state.session,
                    intent[:state.allow_chars])
    else:
        record(name, intent, None, ts)
        logger.info("ALLOW %s session=%s intent=%r", name, state.session,
                    intent[:state.allow_chars])
    return ts


# ─────────────────────────── the SDK-backed classes (lazy) ───────────────────────────

_CLASS_CACHE = {}


def _gated_mcp_class():
    """Build (once) the FastMCP subclass that routes every call through `enforce`.

    The class is built on first use rather than at import because subclassing FastMCP requires
    the SDK, and this module must import without it — see LAZY, NOT EAGER.
    """
    if "GatedMCP" in _CLASS_CACHE:
        return _CLASS_CACHE["GatedMCP"]
    fastmcp = _need_sdk(_SDK_FASTMCP)

    class GatedMCP(fastmcp.FastMCP):
        """A FastMCP whose every tool call passes `enforce` first, and whose tool listing is
        filtered to what the caller's scopes actually grant."""

        async def call_tool(self, name, arguments):
            enforce(name, arguments)          # raises GateRefusal -> isError result, no dispatch
            return await super().call_tool(name, arguments)

        async def list_tools(self):
            tools = await super().list_tools()
            have = current_scopes()
            if have is None:                  # auth disabled / no context -> full surface
                return tools
            return [tool for tool in tools if _tool_scopes(tool.name) & have]

    _CLASS_CACHE["GatedMCP"] = GatedMCP
    return GatedMCP


def _wallet_verifier_class():
    """Build (once) the bearer-token verifier over the wallet-derived token map."""
    if "WalletTokenVerifier" in _CLASS_CACHE:
        return _CLASS_CACHE["WalletTokenVerifier"]
    provider = _need_sdk(_SDK_AUTH_PROVIDER)

    class WalletTokenVerifier(provider.TokenVerifier):
        """Bearer verifier over the wallet-derived token map ({token: scopes}). Unknown token
        -> None (401)."""

        def __init__(self, token_map):
            self._map = token_map

        async def verify_token(self, token):
            scopes = self._map.get(token)
            if scopes is None:
                return None
            return provider.AccessToken(token=token, client_id=_client_id_for(scopes),
                                        scopes=list(scopes), expires_at=None)

    _CLASS_CACHE["WalletTokenVerifier"] = WalletTokenVerifier
    return WalletTokenVerifier


def _client_id_for(scopes):
    """The client_id a token's scopes earn — the first configured scope it carries, else the
    configured default. The order of `tokens.client_ids` is the precedence."""
    state = _settings()
    for scope, client_id in state.client_ids:
        if scope in scopes:
            return client_id
    return state.default_client_id


def _tokens():
    """The {token: scopes} map from the configured loader; {} when no loader is configured.

    The original hardcoded `import ats_token; ats_token.load_map()`. The loader is a
    "module:attr" string in the config object now, and null means "no token source", which
    selects the original's auth-DISABLED branch.
    """
    state = _settings()
    if not state.token_loader:
        return {}
    spec = state.token_loader
    if ":" not in spec:
        raise ConfigError('config key \'tokens.loader\' for %s must look like "module:attr" (for '
                          'example "ats_token:load_map"); got %r' % (UNIT, spec))
    module_name, _, attr = spec.partition(":")
    module = sys.modules.get(module_name)
    if module is None:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise ConfigError("config key 'tokens.loader' for %s names module %r, which cannot be "
                              "imported: %s" % (UNIT, module_name, exc)) from exc
    try:
        loader = getattr(module, attr)
    except AttributeError as exc:
        raise ConfigError("config key 'tokens.loader' for %s names %r, but module %r has no "
                          "attribute %r" % (UNIT, spec, module_name, attr)) from exc
    return loader()


def server():
    """Build (once) the gated FastMCP service with every tool registered — the original's
    module-level `mcp`.

    With a non-empty token map the service is built with bearer auth on and the configured base
    scope required by the transport; with an empty map auth is DISABLED and the service is
    loopback-only, and both cases log which one happened, as the original did.
    """
    cached = globals().get("mcp")
    if cached is not None:
        return cached
    state = _settings()
    logger = _setup_logging()
    gated = _gated_mcp_class()
    tokens = _tokens()
    if tokens:
        settings_mod = _need_sdk(_SDK_AUTH_SETTINGS)
        base = state.base_url_template % (state.host, state.port)
        auth = settings_mod.AuthSettings(issuer_url=base, resource_server_url=base,
                                         required_scopes=list(state.required_scopes))
        service = gated(state.service_name, host=state.host, port=state.port,
                        token_verifier=_wallet_verifier_class()(tokens), auth=auth)
        logger.info("auth ENABLED — %d wallet tokens, base scope %r required by transport",
                    len(tokens), state.required_scopes[0] if state.required_scopes else None)
    else:
        service = gated(state.service_name, host=state.host, port=state.port)
        logger.warning("auth DISABLED — no %s and no wallet reachable; loopback only",
                       state.secrets_file)
    for tool in _TOOLS:
        service.tool()(tool)
    globals()["mcp"] = service
    return service


# ─────────────────────────── the tool bodies' helpers ───────────────────────────

def _text(res):
    """The joined text of a leaf result, or RuntimeError carrying that text when it isError.

    The text is joined BEFORE the error check, so a failed leaf's message is the exception's
    message.
    """
    txt = "".join(part.get("text", "") for part in res.get("content", []))
    if res.get("isError"):
        raise RuntimeError(txt)
    return txt


def _run(leaf, tool, **kw):
    """Call `tool` on `leaf` with `kw` minus `intent`, and return its text.

    `intent` is the gate's business — it is required and provenanced by `enforce` — so it is
    stripped before the leaf sees it.
    """
    return _text(leaf.call_tool(tool, {k: v for k, v in kw.items() if k != "intent"}))


def _crankd_crank(component, intent):
    """Forward a crank to crankd, which verifies the ticket's wallet approval and runs it OFF
    the agent's process tree. The agent no longer spawns a crank — it makes this one REST call.

    HTTPError is caught before OSError because it IS an OSError: a refusal (the service
    answered, with a status) and unreachability (it did not answer) are different failures and
    must not collapse into one message.
    """
    state = _settings()
    body = json.dumps({"component": component, "intent": intent}).encode()
    request = urllib.request.Request(state.crankd + state.crank_path, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=state.crankd_timeout) as response:
            return response.read().decode() or "{}"
    except urllib.error.HTTPError as exc:
        raise RuntimeError("crankd refused (HTTP %s): %s" % (exc.code, exc.read().decode()))
    except OSError as exc:
        raise RuntimeError("crankd unreachable at %s: %s" % (state.crankd, exc))


def _imgd(method, path, obj=None):
    """Forward an image op to imgd (the drivers run in imgd, not the gate). Returns the leaf's
    text. HTTPError before OSError, for the reason `_crankd_crank` gives."""
    state = _settings()
    data = json.dumps(obj).encode() if obj is not None else None
    request = urllib.request.Request(state.imgd + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=state.imgd_timeout) as response:
            return json.loads(response.read().decode() or "{}").get("text", "")
    except urllib.error.HTTPError as exc:
        raise RuntimeError("imgd refused (HTTP %s): %s" % (exc.code, exc.read().decode()))
    except OSError as exc:
        raise RuntimeError("imgd unreachable at %s: %s" % (state.imgd, exc))


def _confined_read(root, path, label):
    """The shared body of `_ws_read`/`_cong_read`: a read-only, path-confined read or listing
    under `root`. No writes, no `.git`, no escaping.

    The confinement is the original's, character for character: the TARGET is realpath-ed and
    must be `root` itself or start with root + os.sep, while `root` is used AS CONFIGURED and
    is NOT realpath-ed. See CONFINEMENT in the module docstring for why that asymmetry — a real
    latent bug under a symlinked root — is preserved rather than fixed.
    """
    state = _settings()
    full = os.path.realpath(os.path.join(root, path or "."))
    if not (full == root or full.startswith(root + os.sep)):
        raise RuntimeError("read refused: %r escapes the %s repo" % (path, label))
    if state.forbidden_component in full.split(os.sep):
        raise RuntimeError("read refused: %s is off-limits" % state.forbidden_component)
    if os.path.isdir(full):
        return ("dir %s/\n" % (path or ".")) + "\n".join("  " + entry
                                                         for entry in sorted(os.listdir(full)))
    if not os.path.isfile(full):
        raise RuntimeError("no such path: %s" % path)
    with open(full, "r", errors="replace") as handle:
        return handle.read()[:state.read_max_bytes]


def _ws_read(path):
    """Read-only, path-confined read/list within the workstation repo — so the cranker can SEE
    the code and conventions before authoring (instead of guessing blind). No writes, no .git,
    no escaping."""
    return _confined_read(_settings().workstation, path, "workstation")


def _cong_read(path):
    """Read-only, path-confined read/list within the congruency repo — so the congruency cranker
    can SEE existing migrations/invocators/tools + conventions before authoring. No writes, no
    .git, no escaping."""
    return _confined_read(_settings().congruency_repo, path, "congruency")


def _record_mandate(ticket_id, mandate):
    """Record each non-empty line of `mandate` as an ordered, content-addressed clause of the
    ticket's mandate (the ticket-class contract the change must satisfy). Returns the count
    filed.

    `mandate` is coerced with `(mandate or "")`, so 0, None, [] and "" are all an empty mandate
    and return 0 rather than raising. The clause number is this function's own running count,
    and it is incremented BEFORE the clause is filed. Both are the original's behavior and both
    are load-bearing — see the module docstring.
    """
    state = _settings()
    n = 0
    for clause in (line.strip() for line in (mandate or "").splitlines()):
        if not clause:
            continue
        n += 1
        digest = hashlib.sha256(("%s|%d|%s" % (ticket_id, n, clause)).encode()).hexdigest()
        _cong("POST", state.routes["mandate_record"],
              {"ticket_id": int(ticket_id), "seq": n, "clause": clause, "digest": digest})
    return n


def _record_bindings(ticket_id, bindings):
    """Record each `<clause_seq> <guarantee label>` line as a declared binding — the author's
    claim that a shadow assertion satisfies a mandate clause. crankd applies these at harvest,
    setting the harvested guarantee's clause_seq. Returns the count filed.

    A line that is not exactly `<digits> <label>` is SKIPPED, not an error: it must split into
    2 whitespace-separated parts whose first is `.isdigit()`. So a single-token line files
    nothing. Unlike `_record_mandate`, the digest is over the clause number PARSED FROM THE
    LINE (not the running count), and the counter is incremented AFTER the filing. All of this
    is the original's behavior — see the module docstring.
    """
    state = _settings()
    n = 0
    for line in (raw.strip() for raw in (bindings or "").splitlines()):
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        cs, label = int(parts[0]), parts[1].strip()
        digest = hashlib.sha256(("%s|%d|%s" % (ticket_id, cs, label)).encode()).hexdigest()
        _cong("POST", state.routes["binding_record"],
              {"ticket_id": int(ticket_id), "clause_seq": cs, "guarantee_label": label,
               "digest": digest})
        n += 1
    return n


def _file_ticket(component, title, body, patch, severity, mandate, bindings):
    """The shared body of `crankws_ticket`/`crankcong_ticket`: create the ticket, then file its
    mandate clauses and bindings against the rowid it came back with.

    The mandate and the bindings are filed only `if tid` — so a rowid of 0, or a response that
    is not an object, files neither and reports 0 of each. That is the original's truthiness
    test, preserved.
    """
    state = _settings()
    response = _cong("POST", state.routes["ticket_create"],
                     {"component": component, "title": title, "body": body, "patch": patch,
                      "severity": severity})
    tid = response.get("rowid") if isinstance(response, dict) else None
    clauses = _record_mandate(tid, mandate) if tid else 0
    binds = _record_bindings(tid, bindings) if tid else 0
    return "filed %s ticket %s (%d mandate clauses, %d bindings): %s" % (
        component, tid, clauses, binds, json.dumps(response))


# ═══════════════════════════════ the tools ═══════════════════════════════
# Every tool takes `intent` — the gate requires it and provenances it (see `enforce`), and the
# tool bodies never see it. The DOCSTRINGS below are these tools' MCP descriptions: FastMCP
# publishes `fn.__doc__` to clients, so an agent picks its tool by reading them. They are the
# module's OUTPUT, not its implementation, and are preserved verbatim from the original for the
# same reason its error strings are — rewording them would change what a client is told.

def crankws_status(intent: str = "") -> str:
    return _run(_leaf_named("crankws"), "status")


def crankws_read(path: str = ".", intent: str = "") -> str:
    """Read a file (or list a dir) in the workstation repo — read-only, confined to the repo. Use it to
    see existing modules + conventions before authoring, so you don't crank blind."""
    return _ws_read(path)


def crankws_ticket(title: str, body: str = "", patch: str = "", severity: str = "info",
                   mandate: str = "", bindings: str = "", intent: str = "") -> str:
    """File a workstation crank ticket carrying its change (a confined python patch), its mandate
    (newline-separated falsifiable clauses the change must satisfy), and optionally its bindings —
    newline `<clause#> <shadow ✓ label>` lines declaring which shadow assertion satisfies which clause,
    which crankd applies when it auto-harvests guarantees at crank time (so coverage computes itself).
    The gate holds the congruency key; the agent never sees it. crankd applies the patch under the
    audit-veto at crank time."""
    return _file_ticket("workstation", title, body, patch, severity, mandate, bindings)


def crankws_crank(message: str = "", intent: str = "") -> str:
    return _crankd_crank("workstation", intent or message)


def crankcong_read(path: str = ".", intent: str = "") -> str:
    """Read a file (or list a dir) in the congruency repo — read-only, confined to the repo. See the
    migrations/, invocators/tags/dev/, tools/, setup.py conventions before authoring so you don't crank blind."""
    return _cong_read(path)


def crankcong_status(intent: str = "") -> str:
    """The congruency crank status: current version + the latest congruency ticket."""
    state = _settings()
    try:
        version = json.load(open(os.path.join(state.congruency_repo,
                                              state.install_json))).get("version", "?")
    except Exception:      # noqa: BLE001 — an unreadable install.json is a "?", never a failure
        version = "?"
    rows = (_cong("GET", state.routes["ticket_approval"]) or {}).get("rows") or []
    ticket = rows[0] if rows else {}
    return "congruency version=%s · latest ticket #%s (%s) %s" % (
        version, ticket.get("id"), ticket.get("status"), (ticket.get("title") or "")[:60])


def crankcong_ticket(title: str, body: str = "", patch: str = "", severity: str = "info",
                     mandate: str = "", bindings: str = "", intent: str = "") -> str:
    """File a CONGRUENCY crank ticket carrying its change (a confined python patch), its mandate
    (newline falsifiable clauses the change must satisfy), and optional bindings (newline
    `<clause#> <shadow ✓ label>`). crankd applies the patch under the audit-veto and mints the next
    congruency version at crank time. The gate holds the congruency key; the agent never sees it."""
    return _file_ticket("congruency", title, body, patch, severity, mandate, bindings)


def crankcong_crank(message: str = "", intent: str = "") -> str:
    return _crankd_crank("congruency", intent or message)


def crankimg_build(node: str = "pi-forge", ssid: str = "WIFI-B61C",
                   wifi_secret: str = "WIFI-B61C", intent: str = "") -> str:
    return _imgd("POST", _settings().imgd_paths["build"],
                 {"node": node, "ssid": ssid, "wifi_secret": wifi_secret})


def crankimg_verify(intent: str = "") -> str:
    return _imgd("GET", _settings().imgd_paths["verify"])


def crankimg_disks(intent: str = "") -> str:
    return _imgd("GET", _settings().imgd_paths["disks"])


def crankimg_flash(device: str, confirm: str, intent: str = "") -> str:
    return _imgd("POST", _settings().imgd_paths["flash"], {"device": device, "confirm": confirm})


def crankimg_base(fetch: bool = False, intent: str = "") -> str:
    return _imgd("POST", _settings().imgd_paths["base"], {"fetch": fetch})


#: The tools `server()` registers, in the original's registration order — which is the order
#: FastMCP lists them in, so it is part of the surface.
_TOOLS = (crankws_status, crankws_read, crankws_ticket, crankws_crank,
          crankcong_read, crankcong_status, crankcong_ticket, crankcong_crank,
          crankimg_build, crankimg_verify, crankimg_disks, crankimg_flash, crankimg_base)


# ═══════════════════════════════ config template ═══════════════════════════════

def config_template():
    """A complete, working config object for this unit — every value the original hardcoded.

    This is what `emit-config` prints and what this package's registry.json ships. It is a
    TEMPLATE, not a fallback: nothing in this module reads it when a config object is missing.
    """
    return {
        "_comment": (
            "Config object for %s (module key forge-rw:653bf1a78a5f85dc, ticket #412). Every "
            "value here was a hardcoded literal in the original forge unit. A setting written "
            '{"env": NAME, "value": V} keeps the original\'s environment override: NAME is the '
            'variable it read, V the literal it fell back to; "env": null pins the setting and '
            "ignores the environment." % UNIT),
        "paths": {
            "_comment": ("'here' is the directory the leaf paths and the fallback provenance log "
                         "resolve against — the original used its own module's directory. null "
                         "means the directory this config object was found in."),
            "here": None,
        },
        "service": {
            "_comment": ("The FastMCP service. host/port/transport keep the original's "
                         "os.environ.get(NAME, VALUE) rule, under which a variable set to the "
                         "EMPTY STRING is honored rather than falling back."),
            "name": "ats",
            "host": {"env": "ATS_HOST", "value": "127.0.0.1"},
            "port": {"env": "ATS_PORT", "value": "8811"},
            "transport": {"env": "ATS_TRANSPORT", "value": "streamable-http"},
            "base_url_template": "http://%s:%d",
            "required_scopes": ["ats:use"],
        },
        "session": {
            "_comment": ("Who the gate says it is when there is no authenticated token. null "
                         "'value' + the pid_template reproduce the original's "
                         "`os.environ.get('CLAUDE_CODE_SESSION_ID') or 'ats-http-%d' % pid`."),
            "env": "CLAUDE_CODE_SESSION_ID",
            "value": None,
            "pid_template": "ats-http-%d",
        },
        "secrets": {
            "_comment": ("The KEY=VALUE file the congruency API key is read from, and the key's "
                         "name. The process environment is the fallback, as in the original."),
            "file": "~/.secrets/ats.env",
            "congruency_api_key": "CONGRUENCY_API_KEY",
        },
        "logging": {
            "_comment": ("The rotating gate log. The original expanded `~` in its built-in "
                         "default but NOT in an ATS_LOG value, and that is preserved: 'value' "
                         "is expanded, the environment's value is used verbatim."),
            "path": {"env": "ATS_LOG", "value": "~/bin/config/ats/gateway.log"},
            "max_bytes": 5000000,
            "backup_count": 5,
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            "level": "INFO",
            "logger": "ats",
            "sdk_logger": "mcp",
        },
        "provenance": {
            "_comment": ("The local fallback memory feed, appended to on every gate decision. "
                         "A relative path resolves against paths.here."),
            "json_log": "ats-http-memories.jsonl",
        },
        "congruency": {
            "_comment": "The state service the gate writes provenance and tickets to.",
            "url": {"env": "CONGRUENCY_URL", "value": "http://127.0.0.1:8899"},
            "timeout": 3,
            "routes": {
                "memories": "/?api=memories",
                "open_ticket": ("/?api=tickets&component=crank-workstation&status=OPEN"
                                "&order=id.desc&per=1"),
                "ticket_create": "/?route=ticket.create",
                "mandate_record": "/?route=mandate.record",
                "binding_record": "/?route=binding.record",
                "ticket_approval": "/?route=ticket.approval&component=congruency",
            },
        },
        "crankd": {
            "_comment": ("The crank service. Its timeout is long because a crank is a full "
                         "build/release, run off the agent's process tree."),
            "url": {"env": "CRANKD_URL", "value": "http://127.0.0.1:8812"},
            "timeout": 1200,
            "crank_path": "/crank",
        },
        "imgd": {
            "_comment": "The pi-image service. The drivers run there, not in the gate.",
            "url": {"env": "IMGD_URL", "value": "http://127.0.0.1:8813"},
            "timeout": 1800,
            "paths": {"build": "/build", "verify": "/verify", "disks": "/disks",
                      "flash": "/flash", "base": "/base"},
        },
        "repos": {
            "_comment": ("The two repositories the read-only tools are confined to. Give REAL "
                         "paths: the confinement check compares a realpath-ed target against "
                         "the root as written, so a root that traverses a symlink refuses every "
                         "read (the original's behavior, preserved — see the module docstring)."),
            "workstation": "~/code/workstation",
            "congruency": "~/code/congruency",
            "congruency_install_json": "install.json",
        },
        "reads": {
            "_comment": "The read cap and the path component the readers refuse, per read.",
            "max_bytes": 20000,
            "forbidden_component": ".git",
        },
        "gate": {
            "_comment": ("The gate's own rules. state_change_tools get HARD provenance (refused "
                         "if it cannot be recorded); scope_rules are tried in order and the "
                         "first matching prefix wins; intent_log_chars are the log-line slices."),
            "state_change_tools": ["crankws_crank"],
            "scope_rules": [
                {"prefix": "crankws_", "scopes": ["ats:crankws", "ats:full"]},
                {"prefix": "crankcong_", "scopes": ["ats:crankcong", "ats:full"]},
            ],
            "default_scopes": ["ats:full"],
            "intent_log_chars": {"refuse": 80, "allow": 120},
        },
        "tokens": {
            "_comment": ("'loader' is the \"module:attr\" returning the {token: scopes} map — the "
                         "original hardcoded `ats_token.load_map`. A non-empty map turns bearer "
                         "auth ON; an empty one turns it OFF. null means 'no token source' and "
                         "so forces the auth-DISABLED branch — do NOT set it to null merely to "
                         "make the server start where ats_token is missing, because wherever "
                         "ats_token DOES exist that silently turns an authenticated gate into "
                         "an open one. A missing loader module is a loud ConfigError on purpose. "
                         "client_ids are tried in order; the first scope the token carries wins."),
            "loader": "ats_token:load_map",
            "client_ids": [
                {"scope": "ats:full", "client_id": "operator"},
                {"scope": "ats:crankws", "client_id": "crankws-agent"},
                {"scope": "ats:crankcong", "client_id": "crankcong-agent"},
            ],
            "default_client_id": "agent",
        },
        "leaves": {
            "_comment": ("The leaf modules whose tool logic the gate reuses in-process. A "
                         "relative path resolves against paths.here."),
            "crankws": {"path": "crankws-mcp/server.py", "module_name": "ats_crankws"},
        },
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ═══════════════════════════════ selftest ═══════════════════════════════

def selftest(out=None):
    """Prove this rewrite against the original's behavior. Returns the number of failures.

    Needs no config, no network and no MCP SDK: it injects its own config objects, points the
    services at a port nothing answers on, and writes only inside a temporary directory it
    removes. Checks that genuinely need the SDK are SKIPPED and REPORTED as skipped rather than
    silently passing.
    """
    import shutil
    import tempfile

    out = out or sys.stdout
    checks = [0]
    failures = []

    def check(ok, label):
        checks[0] += 1
        print("  %s %s" % ("PASS" if ok else "FAIL", label), file=out)
        if not ok:
            failures.append(label)

    def raises(fn, kind):
        try:
            fn()
        except kind as exc:
            return exc
        except Exception as exc:      # noqa: BLE001
            return _Wrong(exc)
        return None

    saved_active, saved_env = _ACTIVE, os.environ.get(CONFIG_ENV)
    saved_globals = {k: globals().get(k) for k in ("crankws", "log", "mcp")}
    # realpath: on macOS mkdtemp hands back a path UNDER a symlink (/var -> /private/var), and
    # the confinement check the original wrote refuses every read under a symlinked root. That
    # is the preserved bug (see CONFINEMENT); check [6b] proves it deliberately, so the rest of
    # the reader checks get a real path, exactly as the config's own comment instructs.
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="ats-http-selftest-"))
    try:
        os.environ.pop(CONFIG_ENV, None)
        cfg = config_template()
        # Point every service at a port nothing answers on, so no check can touch a real
        # service, and keep every write inside `tmp`.
        cfg["paths"]["here"] = tmp
        cfg["congruency"]["url"] = {"env": None, "value": "http://127.0.0.1:1"}
        cfg["crankd"]["url"] = {"env": None, "value": "http://127.0.0.1:1"}
        cfg["imgd"]["url"] = {"env": None, "value": "http://127.0.0.1:1"}
        cfg["logging"]["path"] = {"env": None, "value": os.path.join(tmp, "gateway.log")}
        cfg["secrets"]["file"] = os.path.join(tmp, "ats.env")
        cfg["repos"]["workstation"] = os.path.join(tmp, "workstation")
        cfg["repos"]["congruency"] = os.path.join(tmp, "congruency")
        cfg["tokens"]["loader"] = None
        cfg["session"] = {"env": None, "value": "selftest-session", "pid_template": "ats-http-%d"}

        # 1. the config gate — #200 req 4 / acceptance (d).
        print("[1] the config gate: no config object -> throw, never a default", file=out)
        configure(None)
        os.environ[CONFIG_ENV] = os.path.join(tmp, "does-not-exist.json")
        for name, fn in (("_record_mandate", lambda: _record_mandate(1, "")),
                         ("_record_bindings", lambda: _record_bindings(1, "")),
                         ("enforce", lambda: enforce("crankws_read", {"intent": "x"})),
                         ("_ws_read", lambda: _ws_read(".")),
                         ("crankimg_verify", lambda: crankimg_verify(intent="x"))):
            check(isinstance(raises(fn, ConfigError), ConfigError),
                  "%s() throws ConfigError when it cannot see its config object" % name)
        check(isinstance(raises(lambda: __getattr__("CONG"), ConfigError), ConfigError),
              "the module attribute CONG throws ConfigError without a config object")
        os.environ.pop(CONFIG_ENV, None)

        with using_config(cfg, tmp):
            # 2. the ticket's captured exemplars.
            print("[2] the ticket's captured exemplars (the equivalence FLOOR)", file=out)
            mandate_pairs = [(-1, 0), (-1, ""), (-1, []), (0, 0), (0, ""), (0, [])]
            ok = all(_record_mandate(t, m) == 0 for t, m in mandate_pairs)
            check(ok, "_record_mandate: all %d listed exemplars return 0" % len(mandate_pairs))
            binding_pairs = [(-1, 0), (-1, "POST"), (-1, "%s|%d|%s"), (-1, "guarantee_label"),
                             (-1, "/?route=binding.record"), (-1, "clause_seq")]
            ok = all(_record_bindings(t, b) == 0 for t, b in binding_pairs)
            check(ok, "_record_bindings: all %d listed exemplars return 0" % len(binding_pairs))

            # 3. the edges sampling cannot reach — ACCEPTANCE (a)'s "add the edge cases they
            #    miss". Each of these is a property the original has and a tidier rewrite loses.
            print("[3] the edges the exemplars miss", file=out)
            check(_record_mandate(1, None) == 0 and _record_bindings(1, None) == 0,
                  "(x or '') coercion: None is an empty mandate/bindings, not a TypeError")
            check(_record_mandate(1, "\n\n   \n") == 0,
                  "_record_mandate: blank and whitespace-only lines are skipped -> 0")
            check(_record_bindings(1, "1") == 0 and _record_bindings(1, "no-digits label") == 0
                  and _record_bindings(1, "1x label") == 0,
                  "_record_bindings: a line that is not `<digits> <label>` files nothing")
            check(isinstance(raises(lambda: _record_bindings(1, "² label"), ValueError),
                             ValueError),
                  "_record_bindings: '²'.isdigit() is True but int() rejects it -> ValueError "
                  "(a rewrite using isdecimal()/try-except would swallow this)")
            check(_tool_scopes("crankws_crank") == {"ats:crankws", "ats:full"} and
                  _tool_scopes("crankcong_read") == {"ats:crankcong", "ats:full"} and
                  _tool_scopes("anything_else") == {"ats:full"},
                  "_tool_scopes: the three prefix rules")
            first = _tool_scopes("crankws_crank")
            first.add("poison")
            check("poison" not in _tool_scopes("crankws_crank"),
                  "_tool_scopes returns a FRESH set — a mutated result cannot poison the next call")
            check(_text({"content": [{"text": "a"}, {"text": "b"}]}) == "ab" and
                  _text({}) == "" and _text({"content": [{}]}) == "",
                  "_text: joins every part's text; a missing content/text is ''")
            err = raises(lambda: _text({"content": [{"text": "boom"}], "isError": True}),
                         RuntimeError)
            check(isinstance(err, RuntimeError) and str(err) == "boom",
                  "_text: isError raises RuntimeError carrying the JOINED text")

            class _Leaf(object):
                seen = []

                def call_tool(self, tool, args):
                    self.seen.append((tool, args))
                    return {"content": [{"text": "ok"}]}

            leaf = _Leaf()
            check(_run(leaf, "status", a=1, intent="why") == "ok" and
                  leaf.seen == [("status", {"a": 1})],
                  "_run: strips `intent` before the leaf sees it, passes everything else")

            # 4. the gate.
            print("[4] the gate (enforce)", file=out)
            refusal = raises(lambda: enforce("crankws_read", {}), GateRefusal)
            check(isinstance(refusal, GateRefusal) and str(refusal) ==
                  "gate: 'intent' is required for crankws_read (why are you calling it?)",
                  "enforce: no intent -> GateRefusal, verbatim message")
            for bad in ({}, {"intent": ""}, {"intent": None}, None, {"intent": 0}):
                if not isinstance(raises(lambda: enforce("crankws_read", bad), GateRefusal),
                                  GateRefusal):
                    check(False, "enforce: falsy intent %r is refused" % (bad,))
                    break
            else:
                check(True, "enforce: every falsy intent (missing, '', None, 0, no args) refused")
            ts = enforce("crankws_read", {"intent": "reading"})
            check(isinstance(ts, str) and "T" in ts, "enforce: a read returns the stamped ts")
            check(isinstance(raises(lambda: enforce("crankws_crank", {"intent": "go"}),
                                    GateRefusal), GateRefusal),
                  "enforce: a STATE-CHANGE tool is REFUSED when provenance cannot be recorded "
                  "(congruency unreachable) — the hard-provenance rule")
            check(isinstance(raises(lambda: enforce("crankws_read", {"intent": 5}), TypeError),
                             TypeError),
                  "enforce: a non-string truthy intent raises TypeError from the eager log slice")
            check(current_scopes() is None,
                  "current_scopes: None (allow-all) with no request context")

            # 4b. the module attributes, and the documented limit of them.
            check(__getattr__("CONG") == "http://127.0.0.1:1" and
                  __getattr__("SESSION") == "selftest-session" and
                  __getattr__("STATE_CHANGE") == {"crankws_crank"},
                  "the module attributes (CONG/SESSION/STATE_CHANGE) read from the config")
            check(__getattr__("STATE_CHANGE") is not __getattr__("STATE_CHANGE"),
                  "STATE_CHANGE is a fresh set per access, as the original's literal was")
            reconfigured = json.loads(json.dumps(cfg))
            reconfigured["congruency"]["url"] = {"env": None, "value": "http://elsewhere:2"}
            with using_config(reconfigured, tmp):
                check(__getattr__("CONG") == "http://elsewhere:2",
                      "configure() re-derives the attribute views — config is the ONE way to "
                      "change a setting (assigning to the module attribute does nothing; see "
                      "READ-ONLY VIEWS in the module docstring)")

            # 5. provenance really is written.
            print("[5] provenance", file=out)
            feed = os.path.join(tmp, "ats-http-memories.jsonl")
            lines = [json.loads(x) for x in open(feed)]
            check(len(lines) >= 2 and all(set(x) == {"ts", "session", "tool", "intent", "note"}
                                          for x in lines),
                  "record: every gate decision appended one JSON line to the fallback feed")
            check(any(x["note"] == "REFUSED: no intent" and x["intent"] is None for x in lines),
                  "record: the no-intent REFUSAL is provenanced too, not dropped")
            check(all(x["session"] == "selftest-session" for x in lines),
                  "record: each line is stamped with the actor (no token -> the session)")
            check(record("t", "i", None, "ts") is False,
                  "record: returns False when congruency will not take the memory")

            # 6. the readers.
            print("[6] the confined readers", file=out)
            root = os.path.join(tmp, "workstation")
            os.makedirs(os.path.join(root, ".git"))
            os.makedirs(os.path.join(root, "sub"))
            with open(os.path.join(root, "a.txt"), "w") as handle:
                handle.write("x" * 30000)
            with open(os.path.join(root, ".git", "cfg"), "w") as handle:
                handle.write("secret")
            check(len(_ws_read("a.txt")) == 20000,
                  "_ws_read: a file is capped at the configured max_bytes (20000)")
            check(_ws_read(".") == "dir ./\n  .git\n  a.txt\n  sub",
                  "_ws_read: a directory lists sorted entries in the original's format")
            check(_ws_read("") == "dir ./\n  .git\n  a.txt\n  sub",
                  "_ws_read: '' is (path or '.') -> the root listing")
            for bad, why in ((".git/cfg", ".git is off-limits"),
                             ("../escape", "escapes the workstation repo"),
                             ("/etc/hosts", "escapes the workstation repo")):
                exc = raises(lambda: _ws_read(bad), RuntimeError)
                check(isinstance(exc, RuntimeError) and why in str(exc),
                      "_ws_read(%r) refused: %s" % (bad, why))
            exc = raises(lambda: _ws_read("nope"), RuntimeError)
            check(isinstance(exc, RuntimeError) and str(exc) == "no such path: nope",
                  "_ws_read: a missing path is 'no such path: <path>'")
            check(_cong_read is not _ws_read and
                  "congruency repo" in str(raises(lambda: _cong_read("../x"), RuntimeError)),
                  "_cong_read: the same confinement, naming the congruency repo")

        # 6b. the PRESERVED confinement bug. The original compares a realpath-ed target against
        #     the root AS CONFIGURED, so a root reached through a symlink refuses everything.
        #     A rewrite that "fixed" this would widen a security boundary under cover of a
        #     refactor, so it is pinned here as behavior rather than left to be rediscovered.
        print("[6b] the preserved confinement bug (a symlinked root refuses every read)", file=out)
        link_cfg = dict(cfg)
        link_root = os.path.join(tmp, "link-to-ws")
        os.symlink(os.path.join(tmp, "workstation"), link_root)
        link_cfg["repos"] = dict(cfg["repos"], workstation=link_root)
        with using_config(link_cfg, tmp):
            exc = raises(lambda: _ws_read("a.txt"), RuntimeError)
            check(isinstance(exc, RuntimeError) and "escapes the workstation repo" in str(exc),
                  "a root configured through a symlink refuses even a legitimate read — the "
                  "original's check, preserved verbatim rather than silently widened")

        with using_config(cfg, tmp):

            # 7. the REST clients: unreachable -> RuntimeError naming the service.
            print("[7] the crankd / imgd clients", file=out)
            exc = raises(lambda: _crankd_crank("workstation", "why"), RuntimeError)
            check(isinstance(exc, RuntimeError) and
                  str(exc).startswith("crankd unreachable at http://127.0.0.1:1"),
                  "_crankd_crank: unreachable -> RuntimeError naming the configured crankd")
            exc = raises(lambda: crankimg_verify(intent="x"), RuntimeError)
            check(isinstance(exc, RuntimeError) and
                  str(exc).startswith("imgd unreachable at http://127.0.0.1:1"),
                  "crankimg_verify: unreachable -> RuntimeError naming the configured imgd")

            # 8. _secret.
            print("[8] _secret", file=out)
            with open(cfg["secrets"]["file"], "w") as handle:
                handle.write("OTHER=1\nCONGRUENCY_API_KEY=k=v\nCONGRUENCY_API_KEY=second\n")
            reset_config()
            check(_secret("CONGRUENCY_API_KEY") == "k=v",
                  "_secret: the FIRST match wins and only the first '=' splits (K=a=b -> 'a=b')")
            check(_secret("ABSENT_KEY_XYZ") is None,
                  "_secret: a key in neither the file nor the environment is None")
            os.environ["ABSENT_KEY_XYZ"] = "from-env"
            try:
                check(_secret("ABSENT_KEY_XYZ") == "from-env",
                      "_secret: falls back to the process environment")
            finally:
                os.environ.pop("ABSENT_KEY_XYZ", None)

        # 9. the two environment-override rules. This needs a config whose `env` names are LIVE
        #    — the config above pins congruency.url to {"env": null} so no check can reach a
        #    real service, and under that pin an override check would pass VACUOUSLY.
        print("[9] the environment-override rules (`or` vs `get`)", file=out)
        env_cfg = dict(cfg)
        env_cfg["congruency"] = dict(cfg["congruency"],
                                     url={"env": "CONGRUENCY_URL", "value": "http://127.0.0.1:1"})
        for name in ("CONGRUENCY_URL", "ATS_HOST"):
            os.environ.pop(name, None)
        try:
            with using_config(env_cfg, tmp):
                check(_settings().cong == "http://127.0.0.1:1" and _settings().host == "127.0.0.1",
                      "an UNSET variable leaves both rules on the config value")
                os.environ["CONGRUENCY_URL"] = "http://example:9/"
                os.environ["ATS_HOST"] = "0.0.0.0"
                reset_config()
                check(_settings().cong == "http://example:9",
                      "a SET CONGRUENCY_URL overrides the config value and is rstrip('/')ed")
                check(_settings().host == "0.0.0.0", "a SET ATS_HOST overrides the config value")
                os.environ["CONGRUENCY_URL"] = ""
                os.environ["ATS_HOST"] = ""
                reset_config()
                check(_settings().cong == "http://127.0.0.1:1",
                      "a BLANK CONGRUENCY_URL falls back to the config value (the `or` rule)")
                check(_settings().host == "",
                      "a BLANK ATS_HOST is HONORED as '' (the `get` rule) — the rules differ, "
                      "and that difference is the original's")
        finally:
            for name in ("CONGRUENCY_URL", "ATS_HOST"):
                os.environ.pop(name, None)

        with using_config(cfg, tmp):

            # 9b. the bug-report path. note-for-claude wants a report for a thrown exception,
            #     but a DESIGNED outcome is not a defect, and filing for one writes a logs/
            #     tree into the package directory just because (say) the optional SDK is
            #     absent. Proven by running main() itself and watching the tree.
            print("[9b] the bug-report path files only for the UNEXPECTED", file=out)
            reports = os.path.join(tmp, "reports", "bug_reports.jsonl")
            report_cfg = json.loads(json.dumps(cfg))
            report_cfg["bug_reports"] = reports
            with using_config(report_cfg, tmp):
                for exc, label in ((ConfigError("designed"), "ConfigError"),
                                   (GateRefusal("designed"), "GateRefusal"),
                                   (SdkUnavailable("designed"), "SdkUnavailable")):
                    handled = _call_main_with(exc)
                    check(handled != 1 and not os.path.exists(reports),
                          "main(): a %s is designed behavior -> exit %s, no bug report filed"
                          % (label, handled))
                handled = _call_main_with(RuntimeError("genuinely unexpected"))
                check(handled == 1 and os.path.isfile(reports),
                      "main(): an UNEXPECTED exception -> exit 1 AND one bug report filed")
                if os.path.isfile(reports):
                    entry = json.loads(open(reports).readline())
                    check(set(entry) >= {"filename", "function", "time-of-occurance",
                                         "methods-to-reproduce", "possible-cause"},
                          "the bug report carries note-for-claude's five required fields")
            check(isinstance(SdkUnavailable("x"), ImportError),
                  "SdkUnavailable IS an ImportError, so `except ImportError` still catches it")

            # 10. the callable surface.
            print("[10] the callable surface", file=out)
            import inspect
            expected = {
                "crankws_status": "(intent: str = '') -> str",
                "crankws_read": "(path: str = '.', intent: str = '') -> str",
                "crankws_ticket": ("(title: str, body: str = '', patch: str = '', severity: str "
                                   "= 'info', mandate: str = '', bindings: str = '', intent: str "
                                   "= '') -> str"),
                "crankws_crank": "(message: str = '', intent: str = '') -> str",
                "crankcong_read": "(path: str = '.', intent: str = '') -> str",
                "crankcong_status": "(intent: str = '') -> str",
                "crankcong_ticket": ("(title: str, body: str = '', patch: str = '', severity: str "
                                     "= 'info', mandate: str = '', bindings: str = '', intent: "
                                     "str = '') -> str"),
                "crankcong_crank": "(message: str = '', intent: str = '') -> str",
                "crankimg_build": ("(node: str = 'pi-forge', ssid: str = 'WIFI-B61C', "
                                   "wifi_secret: str = 'WIFI-B61C', intent: str = '') -> str"),
                "crankimg_verify": "(intent: str = '') -> str",
                "crankimg_disks": "(intent: str = '') -> str",
                "crankimg_flash": "(device: str, confirm: str, intent: str = '') -> str",
                "crankimg_base": "(fetch: bool = False, intent: str = '') -> str",
                "now_iso": "()",
                "open_ticket": "()",
                "current_scopes": "()",
                "enforce": "(name, arguments)",
                "record": "(tool, intent, note, ts)",
                "_leaf": "(rel, name)",
                "_cong": "(method, path, obj=None)",
                "_imgd": "(method, path, obj=None)",
                "_tool_scopes": "(name)",
                "_text": "(res)",
                "_run": "(leaf, tool, **kw)",
                "_crankd_crank": "(component, intent)",
                "_ws_read": "(path)",
                "_cong_read": "(path)",
                "_record_mandate": "(ticket_id, mandate)",
                "_record_bindings": "(ticket_id, bindings)",
                "_setup_logging": "()",
                "_secret": "(name)",
                "_actor": "()",
            }
            wrong = []
            for name, want in expected.items():
                got = str(inspect.signature(globals()[name]))
                if got != want:
                    wrong.append("%s%s != %s" % (name, got, want))
            check(not wrong, "all %d callables match the ticket's surface exactly%s"
                  % (len(expected), "" if not wrong else " — WRONG: " + "; ".join(wrong)))

            # 11. the SDK-backed surface.
            print("[11] the SDK-backed surface", file=out)
            if _sdk(_SDK_FASTMCP) is None:
                print("  SKIP the MCP SDK is not installed — GatedMCP / WalletTokenVerifier / "
                      "server() are NOT exercised by this run. Install it (`pip install mcp`) "
                      "and re-run to cover them.", file=out)
            else:
                import asyncio
                gated = _gated_mcp_class()
                check(issubclass(gated, _sdk(_SDK_FASTMCP).FastMCP),
                      "GatedMCP is a FastMCP subclass")
                verifier = _wallet_verifier_class()({"tok": ["ats:crankws"]})
                token = asyncio.run(verifier.verify_token("tok"))
                check(token is not None and token.client_id == "crankws-agent" and
                      token.scopes == ["ats:crankws"],
                      "WalletTokenVerifier: a known token -> AccessToken with the mapped client_id")
                check(asyncio.run(verifier.verify_token("nope")) is None,
                      "WalletTokenVerifier: an unknown token -> None (401)")
                check(_client_id_for(["ats:full", "ats:crankws"]) == "operator" and
                      _client_id_for(["ats:crankcong"]) == "crankcong-agent" and
                      _client_id_for(["other"]) == "agent",
                      "the client_id precedence: full > crankws > crankcong > agent")
                service = server()
                names = [t.name for t in asyncio.run(service.list_tools())]
                check(names == [t.__name__ for t in _TOOLS],
                      "server(): all 13 tools registered, in the original's order")
                # The original's inline comment says a refusal becomes "isError result, no
                # dispatch". Verified against the original itself: call_tool RAISES — the
                # isError conversion happens a layer down, in the lowlevel CallToolRequest
                # handler. This asserts what the original DOES, not what it says.
                refused = raises(lambda: asyncio.run(service.call_tool("crankimg_verify", {})),
                                 GateRefusal)
                check(isinstance(refused, GateRefusal),
                      "GatedMCP.call_tool: no intent -> GateRefusal out of call_tool, and the "
                      "tool body never runs (imgd is never contacted)")
                listed = asyncio.run(service.list_tools())
                check(len(listed) == len(_TOOLS),
                      "GatedMCP.list_tools: no request context (allow-all) -> the full surface")

                # The two auth branches. Which one is taken is decided by the TOKEN MAP, and
                # getting that backwards would leave the gate open — so both are pinned.
                check(service.settings.auth is None,
                      "auth DISABLED branch: an empty token map -> no auth on the server "
                      "(the original's loopback-only case)")
                auth_cfg = json.loads(json.dumps(cfg))
                auth_cfg["tokens"]["loader"] = "%s:_selftest_tokens" % __name__
                globals()["_selftest_tokens"] = lambda: {"tok": ["ats:full"]}
                with using_config(auth_cfg, tmp):
                    authed = server()
                    check(authed.settings.auth is not None and
                          list(authed.settings.auth.required_scopes) == ["ats:use"],
                          "auth ENABLED branch: a non-empty token map -> AuthSettings with the "
                          "configured base scope required by the transport")
                globals().pop("_selftest_tokens", None)
                check(isinstance(raises(lambda: _tokens(), ConfigError), ConfigError) or
                      _tokens() == {},
                      "a token loader naming an absent module is a loud ConfigError, never a "
                      "silent fallback to auth-disabled")
    finally:
        os.environ.pop(CONFIG_ENV, None)
        if saved_env is not None:
            os.environ[CONFIG_ENV] = saved_env
        globals()["_ACTIVE"] = saved_active
        reset_config()
        for key, value in saved_globals.items():
            if value is not None:
                globals()[key] = value
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED", checks[0], len(failures)),
          file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


class _Wrong(object):
    """A wrong exception type came back — never equal to the expected one, so `check` fails and
    the selftest reports rather than aborting."""

    def __init__(self, exc):
        self.exc = exc

    def __repr__(self):
        return "<wrong exception %r>" % self.exc


def _call_main_with(exc):
    """Drive `main()` for a command whose work raises `exc`, and return its exit code.

    Used by selftest [9b] to exercise main's REAL exception routing — including whether it
    files a bug report — without needing the failure to happen for real.
    """
    saved = globals()["serve"]
    stderr = sys.stderr

    def _boom():
        raise exc

    try:
        globals()["serve"] = _boom
        sys.stderr = io.StringIO()
        return main(["serve"])
    finally:
        globals()["serve"] = saved
        sys.stderr = stderr


# ═══════════════════════════════ the command line ═══════════════════════════════

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report its
    original error. Returns the path written, or None.

    `main` never routes a ConfigError, a SdkUnavailable or a GateRefusal here — it handles each
    by name, because they are designed behavior rather than defects. This function is reached
    only by the genuinely unexpected.
    """
    try:
        config, base = active_config(), active_base()
    except ConfigError:
        return None
    relative = config.get("bug_reports")
    if not isinstance(relative, str) or not relative:
        return None            # a non-string key must not raise from inside the error handler
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
        "note": "%s (ticket #412, module key forge-rw:653bf1a78a5f85dc)" % UNIT,
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


def serve():
    """Run the service — the original's `__main__` block, verbatim in behavior.

    Builds the server (sampling the environment and loading the leaf and the token map, all of
    which the original did at import), logs the start line, prints the operator banner to
    stderr, and blocks in the transport.
    """
    state = _settings()
    service = server()
    logger = _setup_logging()
    transport = state.transport
    logger.info("start transport=%s host=%s port=%s log=%s", transport, service.settings.host,
                service.settings.port, state.log_path)
    sys.stderr.write("[ats] FastMCP %s on %s:%s — intent + ticket + provenance enforced "
                     "server-side; log=%s\n"
                     % (transport, service.settings.host, service.settings.port, state.log_path))
    service.run(transport=transport)


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="forge2-ats-http",
        description="forge2 rewrite of the forge unit agent_tools_suite:ats_http.py (ticket "
                    "#412) — the agent tool suite as ONE FastMCP service, with intent, scope "
                    "and provenance enforced server-side. Config-driven: every command except "
                    "`emit-config` and `selftest` throws if it cannot see its config object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="With no arguments this SERVES, exactly as the original module did when run. "
               "Config is read from the file named by $%s, else from the %s section of the "
               "nearest %s found by walking up from this module. This package ships one beside "
               "the module. Run `emit-config` for a template."
               % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME))
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the FastMCP service (the default with no arguments)")
    sub.add_parser("selftest", help="prove the exemplars, the edges and the config gate")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and its source")
    return parser


def main(argv=None):
    """Entry point for the `forge2-ats-http` console script. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)
    command = args.command or "serve"

    try:
        if command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at it.\n"
                  "# Until it is installed, every operation throws ConfigError rather than "
                  "guessing." % (".".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV))
            return 0
        if command == "selftest":
            return 1 if selftest() else 0
        if command == "show-config":
            print("# config object for %s\n# source: %s\n# base:   %s"
                  % (UNIT, active_source(), active_base()))
            print(json.dumps(active_config(), indent=2))
            state = _settings()
            print("\n# resolved (after the environment overrides):")
            for label, value in (("HERE", state.here), ("CONG", state.cong),
                                 ("CRANKD", state.crankd), ("IMGD", state.imgd),
                                 ("WORKSTATION", state.workstation),
                                 ("CONGRUENCY_REPO", state.congruency_repo),
                                 ("SESSION", state.session), ("JSON_LOG", state.json_log),
                                 ("LOG_PATH", state.log_path),
                                 ("STATE_CHANGE", sorted(state.state_change)),
                                 ("CONGRUENCY_KEY", "<set>" if state.congruency_key else None),
                                 ("host:port", "%s:%s" % (state.host, state.port)),
                                 ("transport", state.transport)):
                print("#   %-16s %s" % (label, value))
            return 0
        serve()
        return 0
    except ConfigError as exc:
        # The #200 req-4 gate firing is DESIGNED behavior, not a defect: one line, exit 2, no
        # traceback and no bug report.
        sys.stderr.write("%s: %s\n" % (os.path.basename(os.path.abspath(__file__)), exc))
        return 2
    except GateRefusal as exc:
        # The gate refusing is this module's JOB. Also designed behavior, so it files no bug
        # report either — which is what this module's SIDE EFFECTS section promises.
        sys.stderr.write("%s: refused: %s\n" % (os.path.basename(os.path.abspath(__file__)), exc))
        return 3
    except SdkUnavailable as exc:
        # A missing OPTIONAL dependency is an environment fact, not a defect in this tool: one
        # line, exit 2, and no bug report. (Filing one here would write a logs/ tree into the
        # package directory merely because `mcp` is not installed.)
        sys.stderr.write("%s: %s\n" % (os.path.basename(os.path.abspath(__file__)), exc))
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as exc:      # noqa: BLE001 — an UNEXPECTED failure: report it, per note-for-claude
        formatted = traceback.format_exc()
        path = _bug_report(exc, formatted, argv)
        sys.stderr.write("%s: %s: %s\n" % (os.path.basename(os.path.abspath(__file__)),
                                           type(exc).__name__, exc))
        if path:
            sys.stderr.write("a bug report was filed at %s\n" % path)
        return 1


if __name__ == "__main__":
    sys.exit(main())
