#!/usr/bin/env python3
"""forge2 / code__code-invalid__coupler / coupler.server — a behavior-preserving rewrite of the
forge unit `code__code-invalid__coupler:coupler/server.py` (module key
forge-rw:b94f61804a14beb2), filed under ticket #385 against the FORGE-wide refactor standard
#200.

(#385 supersedes #288, which named its source only as a `git cat-file` against the forge's bare
repos that the sandboxed pair_loop worker cannot run. #385 embeds the source instead, so the
rewrite needs no forge access, and the work is done HERE. `ORIGINAL_SOURCE` below is that
embedded copy, and `selftest` check [0] proves it is the real forge blob by hashing it — see
THE EQUIVALENCE BASIS.)

WHAT THIS IS
------------
The original forge unit was 13835 bytes: the coupler's HTTP MCP server. It is a long-lived
daemon that mounts a list of downstream jazz MCP servers as namespaced proxies, exposes a
`coupler_status` tool that re-probes them, serves a plain `/health` endpoint for a k8s
readiness probe, optionally mounts a `why5` root-cause-analysis toolset, and bridges a browser
UI over HTTP. `coupler/bridge.py` (the sibling rewritten under #357) is what Claude Desktop
runs; it proxies stdio to THIS server's SSE endpoint.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and it adds the three things #200 requires that the original
lacked: it is part of a proper installable package, it is driven by a configuration object, and
it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
Quoted from ticket #385, which lowered the original with codebean's `lower_node` (#183):

    _env_port(name: str, default: int) -> int
    _load_build() -> dict
    _disabled_services() -> set
    _notes_python() -> str
    build_app() -> FastMCP
    main()

All six are preserved exactly: same names, same parameters, same defaults, same annotations.
`selftest` check [4] proves each by inspection against the ORIGINAL's own signatures rather
than asserting them.

The original also bound five module-level names that its own functions read and that callers
and tests rebind — `JAZZ_ROOT`, `JAZZ_DEV`, `PORT`, `JAZZ_SERVICES`, and the telemetry pair
`telemetry` / `service_running`. They are part of the surface in practice, so they are still
module globals here, and `_load_build`, `_disabled_services`, `build_app` and `main` still read
them at CALL time (not captured at import), so `import coupler.server as s; s.JAZZ_ROOT = p`
keeps working exactly as it did. `selftest` check [3] rebinds `JAZZ_ROOT` on both modules and
requires them to agree, which is what proves the call-time read rather than merely claiming it.

`JAZZ_SERVICES` is a list of `(name, module)` TUPLES here, as it was originally, even though it
arrives from JSON as a list of lists — see `_load`. A rewrite that left them as lists would
still satisfy `for name, module in JAZZ_SERVICES` and would silently break any caller doing
`("z3", "z3_mcp") in JAZZ_SERVICES`.

WHAT THE ORIGINAL ACTUALLY DID — READ OFF THE CODE, NOT ASSUMED
---------------------------------------------------------------
Several details are easy to "fix" and wrong to. Each is preserved deliberately, and every one
is proven against THE ORIGINAL AS IT RUNS by `selftest` checks [2] and [3]:

  * `_env_port` falls back to the URL's TRAILING port, not to the default, whenever `int(raw)`
    fails but `int(raw.rsplit(":", 1)[-1])` succeeds. So `COUPLER_PORT="8000:9000"` yields
    **9000**, not 8000 and not the default. That is a consequence of the rsplit, not an
    intention, but it is the behavior.
  * `int()` is Python's, so `_env_port` accepts whitespace, a leading `+`, underscores
    (`"1_000"` -> 1000), NEGATIVE ports (`"-1"` -> -1), and non-ASCII decimal digits
    (`"٨"` -> 8). None of these is validated and none is rejected.
  * `_disabled_services` tests `v is False`, NOT falsiness. `{"coupler": {"z3": 0}}` therefore
    does NOT disable z3, because `0 is False` is False. A rewrite using `not v` would disable
    it and would be wrong.
  * `set(cfg.get("disabled", []))` iterates a STRING character by character:
    `{"disabled": "z3"}` disables `{"z", "3"}`, not `{"z3"}`. Preserved, not fixed.
  * `{"disabled": false}` raises `TypeError: 'bool' object is not iterable` out of
    `_disabled_services`. It is NOT guarded, and it is not guarded here either.
  * `_load_build` does not catch anything: a `build.json` that exists but is not valid JSON
    raises `JSONDecodeError`, and one holding a JSON array makes `_disabled_services` raise
    `AttributeError: 'list' object has no attribute 'get'`. Both propagate.
  * `.get("coupler", {}) or {}` is what makes `{"coupler": null}` safe — the `or {}` catches
    the None the `.get` default cannot.
  * `build_app`'s per-service mount guard is `except Exception`, so a service that fails to
    mount is recorded "down" and the loop continues; `BaseException` is not caught.
  * the why5 block's guard is also `except Exception`, and it wraps the IMPORT as well as the
    five registrations. `coupler.why5` does not exist in this package, so in practice the
    import raises and the five why5 tools are NOT registered — the observable result is one
    `  [warn] why5: No module named 'coupler.why5'` line on stderr. That is the original's
    behavior here and it is reproduced, warning text included.
  * the UI-mounted line reads `  mounted      : ui (port 8142)` — a literal, with 8142 baked
    into the TEXT even when `$JSON_CONTROLS_URL` points somewhere else entirely. The message
    is preserved verbatim rather than "corrected" to interpolate the real port, because a
    rewrite that fixed it would print something the original never printed.

THE `fastmcp` / `httpx` / `starlette` DEPENDENCIES, AND THE ONE DELIBERATE DEVIATION
------------------------------------------------------------------------------------
The original imported `httpx`, `fastmcp` and (inside `build_app`) `starlette` at module scope,
so `import coupler.server` raised `ImportError` wherever any of them was absent — and all three
ARE absent from the interpreter this package was built and verified against, and none is
declared by this package's `pyproject.toml`.

This module imports them INSIDE `build_app()` instead, via `_load_deps()`. That is the one place
this rewrite knowingly departs from the original, so it is stated plainly rather than buried:

  * what is preserved — `build_app()` still raises `ImportError` when they are missing, and
    still raises it BEFORE it prints anything or builds anything, because `_load_deps()` is the
    first thing it calls. Every caller that builds the app sees what it always saw.
  * what changes — `import coupler.server` no longer requires fastmcp/httpx. Under the original,
    a caller that only wanted `_env_port` still had to have all three installed.
  * why — #200 requirement 3 is that `pip install -e .` installs clean from this package's own
    pyproject.toml. Declaring fastmcp would make that install depend on a package index being
    reachable, and a module-scope import of an undeclared dependency would make
    `import coupler.server` fail for everyone. The deviation makes the module importable and
    testable while leaving `build_app()`'s behavior intact.

One consequence is worth naming precisely, because it is a real (if obscure) difference rather
than a pure win. The original's tool bodies resolved `httpx`, `Client` and `StdioTransport` as
MODULE GLOBALS at tool-call time; this rewrite resolves them once inside `build_app()` and the
tools close over them. The two are observationally identical unless a caller swaps
`sys.modules["httpx"]` (or rebinds `coupler.server.httpx`) BETWEEN `build_app()` and a tool
call, which nothing does. `selftest` installs its stand-ins before `build_app()` and leaves them
in place for the tool calls, so both modules are driven through the same objects.

THE EQUIVALENCE BASIS (#200 requirement 1, acceptance item (a))
---------------------------------------------------------------
Ticket #385 records that criteria_miner captured NO exemplars for this module — "no function in
this module is minable ... criteria_miner mines only self-contained pure functions (it refuses
anything that mentions a world-touching or non-deterministic name, plus methods and no-arg
functions), and nothing here qualified" — and states that this "does NOT weaken the ticket's
bar — it MOVES the work: you must write the equivalence exemplars by hand from the original's
behavior before rewriting, and they are what settles this ticket."

`EXEMPLARS` and `EDGE_CASES` below are that hand-written table. Their expected values are NOT
hand-copied and hoped to be right: `selftest` runs each scenario against the ORIGINAL and
against this rewrite, under identically staged conditions, and compares the two observations
field by field. The original is therefore the oracle, and a disagreement is a FAIL — this is the
differential idiom ticket #355's `test_build.py` established in this package and #357's
`bridge.py` followed.

That is only worth anything if the embedded original is really the forge's module, so `selftest`
check [0] hashes `ORIGINAL_SOURCE` as git hashes a blob and compares the digest to the blob sha1
ticket #385 records (`257bf1163cd84c3cdd1fe82da9c7ce2c8b323e0a`). It also checks the length
against the ticket's stated 13835 bytes. If either differs the whole selftest is worthless, so
it is the first thing checked and it fails loudly.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a single
    `.json` file at the root of a package holding the configuration for every tool in that
    package. `note-for-claude` states the contract in its own words — ".json will have all the
    configuration - for all tools in this set of packaging. (a configuration registry) -if a
    tool cannot see the registry it will throw an exeption." [sic] This package ships its own
    `registry.json` at its root, one directory above this file.
config object
    The chunk of that registry belonging to this unit — the section at
    `forge2 -> code__code-invalid__coupler -> coupler.server`. It is what drives this module.
    `emit-config` prints a template of it.
exemplar
    One (scenario -> expected outcome) pair the rewrite must reproduce, standing in for the
    automated captures ticket #385 could not mine.
MCP
    Model Context Protocol — the tool/resource protocol this server speaks. A "tool" is one
    callable the protocol exposes to a client.
SSE
    Server-Sent Events, the HTTP transport this server exposes at `/sse` and the one
    `coupler/bridge.py` dials.
mount / namespace
    fastmcp's composition primitive: `app.mount(proxy, namespace="z3")` republishes every tool
    of a downstream server under the `z3` prefix, so one coupler session reaches them all.
service-link var
    A `<SERVICENAME>_PORT=tcp://<clusterip>:<port>` environment variable Kubernetes injects for
    every Service in a namespace. It is why `_env_port` exists: a Service named `coupler`
    clobbers this server's own `COUPLER_PORT` with a URL.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The original hardcoded every parameter it had: the jazz_telemetry search path under `$HOME`,
the `JAZZ_ROOT` / `JAZZ_DEV` variable names and their `code/workspace/main` and `code/jazz`
defaults, the `COUPLER_PORT` variable and its 7770 default, the `conf/env/build.json` path, the
seven-entry `JAZZ_SERVICES` table, the `COUPLER_DISABLE` and `COUPLER_PYTHON` variable names,
the `coupler` server name, the `/health` route and its payload values, the `JSON_CONTROLS_URL`
variable and its `http://127.0.0.1:8142` default, the 5.0- and 2.0-second timeouts, the 500
degraded threshold, the `indent=2`, every stderr line, every tool description, every tool return
string, every UI path, the `COUPLER_HOST` variable and its `127.0.0.1` default, and the `sse`
transport. Those are exactly the params #200's fourth requirement forbids hardcoding, so every
one of them is read from this unit's config object and NOTHING is defaulted in code.

Two things in the config are deliberately NOT parameters, and it is worth saying which and why,
because "everything is config" is otherwise unfalsifiable:

  * `UNIT_PATH` is this unit's own ADDRESS inside the config document. A config-driven tool has
    to know which section is its own; that is not a setting it could read from the section it
    has not found yet.
  * the FIELD NAMES of the `/health` payload and of `coupler_status`'s JSON are the wire
    contract those endpoints publish — a k8s readiness probe and an MCP client parse them by
    name. They are config here anyway (`health.fields`, `status.fields`) so that nothing is
    baked in, but renaming them changes the contract rather than tuning the tool. The
    construction ORDER is fixed in code, because JSON object order is observable and the
    original's order is part of what is being preserved.

This package ships a `registry.json` carrying precisely the original's values, so an ordinary
`import coupler.server` from a source checkout or an editable install behaves exactly as the
original did. `selftest` check [2] is what proves that claim: it runs the shipped config against
the original and requires the observations to match.

The config is read at IMPORT, because the original bound `JAZZ_ROOT`, `JAZZ_DEV` and `PORT` at
import and that is the behavior being preserved. So `import coupler.server` raises `ConfigError`
when no config object can be resolved: ticket #385's acceptance item (d) and `note-for-claude`'s
rule. It does not guess 7770, it does not guess `127.0.0.1`, and it does not quietly leave the
globals unbound. `selftest` check [1] proves it.

The gate is checked at import, OUTSIDE every `except Exception` in this file, so the guards that
implement the mount fallback and the why5 fallback can never swallow a `ConfigError` and report
a config mistake as a downed service.

Resolution order — the first source that answers wins:

  1. the file named by the `COUPLER_SERVER_CONFIG` environment variable, which holds this unit's
     config object itself — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code-invalid__coupler -> coupler.server` section of the
     nearest `registry.json` found by walking UP from THIS FILE's directory;
  3. otherwise, the `registry.json` shipped as package data inside the installed
     `code__code_invalid__coupler` package, located with `importlib.util.find_spec`.

The walk-up starts at this file, never at the working directory, so which directory you run from
does not change what config is found. Step 3 exists because a plain (non-editable)
`pip install .` puts this module at `site-packages/coupler/server.py`, and the walk-up from
there passes no registry at all — `site-packages` has none. See `find_registry`.

The variable is named for THIS unit rather than something forge2-wide on purpose: it names a file
holding ONE unit's config object, and a variable shared across units could only ever point at one
unit's object at a time.

SIDE EFFECTS
------------
Importing this module reads one JSON file, binds globals, and — reproducing the original's
module-level code exactly — INSERTS the configured jazz_telemetry directory at the front of
`sys.path` and then tries to import `jazz_telemetry` from it, falling back to no-op stubs if
that fails. The `sys.path` insert is a real side effect of importing the original, so it is a
real side effect of importing this module; `selftest` check [5] measures it rather than letting
it go unmentioned. Importing opens no socket, starts no server and writes nothing.

`build_app()` spawns no subprocess by itself (fastmcp's stdio clients are constructed, not
started, until a session opens) and writes its progress lines to stderr. `main()` binds a TCP
port and serves until killed, which is its whole purpose.

Every command in RUNNING IT except `run` creates no files, modifies none and deletes none, and
opens no sockets: `selftest` drives both modules against in-memory stand-ins for fastmcp, httpx
and starlette, and check [7] proves the no-files claim by listing this package's tree before and
after a full run and diffing it. (The interpreter still writes its usual `__pycache__` bytecode
for any module it imports; that is CPython's import machinery rather than this code, and ticket
#385 lists `__pycache__` among the build artifacts that are regenerated by any install and never
committed.)

The one thing that can write is the command line, which per `note-for-claude` ("all tools need to
pass a bug-report automatically (timestamped if an exception is thrown)") appends one timestamped
JSON line to the config's `bug_reports` path if it hits an UNEXPECTED exception — a defect in this
tool. A `ConfigError` is designed behavior, not a bug: it files no report, prints no traceback,
and exits with a single self-explaining line.

RUNNING IT
----------
Every command below is executable as written FROM THE PACKAGE ROOT — the directory holding
`pyproject.toml`, one level above `coupler/`. The `-m` form is what makes them run without
installing anything: it puts the package root on the import path, so `coupler.server` resolves.
Running the file by path (`python3 coupler/server.py`) does NOT work uninstalled, because Python
would put `coupler/` on the import path instead of the package root and the `coupler` package
would not be importable; that invocation answers with one `UsageError` line saying so rather
than a traceback.

    python3 -m coupler.server selftest       # the equivalence proof: [0]-[8], vs the ORIGINAL
    python3 -m coupler.server install-check  # prove the install by RUNNING pip, both layouts
    python3 -m coupler.server show-config    # print the resolved config object and its source
    python3 -m coupler.server emit-config    # print a config-object template
    python3 -m coupler.server show-services  # print the service table and what is disabled
    python3 -m coupler.server run            # run the server — needs fastmcp/httpx installed

Once installed (see INSTALLABLE), the console script runs from any directory:

    forge2-coupler-server selftest

The server proper is `run`, and `main()` is what a daemon supervisor invokes. The original's
`python -m coupler.server [--port 7770]` ran the server; that spelling is preserved exactly —
any argv that is not one of the subcommands above is handed to `main()` untouched, so
`python3 -m coupler.server --port 8080 --host 0.0.0.0` still works byte for byte. `selftest`
check [8] proves that, including the no-argument form.

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, committed in full beside it. From the
package root:

    pip install -e .
    forge2-coupler-server selftest

`pyproject.toml` declares `coupler` as a package, so an installed copy imports as
`coupler.server` — the path the forge unit was originally addressed by (repo
`code__code-invalid__coupler`, path `coupler/server.py`). It declares NO dependencies, so that
install needs no package index to resolve any; that is why `build_app()` imports fastmcp lazily
rather than the package declaring it.

`install-check` proves this by RUNNING pip, not by reasoning about it: it builds a throwaway
prefix, runs a real `pip install -e .` and a real `pip install .` into it, activates each with
`site.addsitedir`, and imports `coupler.server` from the result in a child interpreter. The
non-editable layout is the one that matters most, because the registry walk-up passes nothing
above `site-packages/coupler/server.py` — that is what `find_registry`'s `_installed_registry`
fallback exists for, and `install-check` proves both that it finds the shipped registry and that
deleting it brings the config gate back.

A PACKAGING DEFECT THIS UNIT HAD TO REPAIR, STATED PLAINLY
-----------------------------------------------------------
Before this ticket, `pyproject.toml` declared only `code__code_invalid__coupler` (mapped onto the
package ROOT) and did NOT declare the nested `coupler` package. A real `pip install -e .` of the
package as it stood therefore shipped no `coupler/` at all, and `import coupler.server` — the
very import acceptance item (c) is about — failed with `ModuleNotFoundError: No module named
'coupler'`. That was measured, not assumed, by installing the unmodified package into a scratch
prefix and importing from it.

So this ticket adds `"coupler"` to `tool.setuptools.packages` and its own console script to
`pyproject.toml`, and adds its own `coupler.server` section to `registry.json`. Both edits are
strictly ADDITIVE — no existing declaration is removed or changed — and both are required by
this ticket's own acceptance items (c) and (d). Ticket #385 is explicit that they land: "the
harness commits the WHOLE of checkouts/current/forge2/code__code-invalid__coupler/ — so build the
package there in full (its pyproject.toml, its config, its console entry points, any submodules)
and every part of it lands together."

Two neighbouring defects are NOT repaired here, because #385 "covers ONE module — the one
identified below — and nothing else". They are recorded so a reader who trips over them knows
they are known, and `install-check` prints the evidence for each rather than letting this
module's own result imply the package is healthy:

  * `registry.json` carries no `coupler.bridge` section, so `import coupler.bridge` (#357) raises
    ConfigError before it can do anything. That unit's config template is in its own
    `config_template()`; installing it is #357's business, not #385's.
  * `coupler/_config.py` (#397) has no installed-registry fallback, so in a NON-editable layout
    `import coupler` — which runs first, being the package `__init__` — throws before this module
    is reached. Its own documented escape hatch, `$COUPLER_CONFIG`, is what `install-check` uses
    to isolate this unit's behavior from that gap.
"""

import argparse
import hashlib
import io
import json
import os
import sys
import traceback
import types
from contextlib import contextmanager as _cm
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────── configuration ───────────────────────────────
#
# Self-contained ON PURPOSE, following the pattern ticket #355's `coupler/tests/test_build.py`
# established in this package and #357's `coupler/bridge.py` followed: a forge rewrite unit's
# deliverable is ONE module, and a sibling helper it depends on may not be present or may not be
# runnable. `coupler/_config.py` exists but has no installed-registry fallback, and
# `coupler/tests/test_bridge.py` (#393) imports `coupler.config`, which does not exist here at
# all. This file has no such dependency and runs against the package as it actually is.

#: Environment variable naming a file that holds THIS unit's config object.
CONFIG_ENV = "COUPLER_SERVER_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in
#: the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own.
UNIT_PATH = ("forge2", "code__code-invalid__coupler", "coupler.server")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code-invalid__coupler/coupler/server"

#: This module's own dotted import name. It is `UNIT_PATH`'s last element by construction — a
#: unit's address inside the registry IS its dotted path within the package — so it is derived
#: rather than written twice and cannot drift from it. Used only to print an invocation a reader
#: can retype; `__name__` is "__main__" under `-m` and `__spec__` is None when this file is run
#: by path, so neither can answer this on its own.
DOTTED_NAME = UNIT_PATH[-1]

#: The installed package that ships `registry.json` as package data. `find_registry` falls back
#: to it so a NON-editable `pip install .` can still find the config: this module then lives at
#: `site-packages/coupler/server.py` and the walk-up passes no registry at all.
PACKAGE_WITH_REGISTRY = "code__code_invalid__coupler"

#: The ticket this unit was rewritten under, recorded in bug reports.
TICKET = 385


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and ticket #385's acceptance item (d): a tool that cannot
    see its config throws rather than guessing a default.

    It is raised at IMPORT, outside every `except Exception` in this file, so the guards that
    implement the mount fallback and the why5 fallback can never mistake a config mistake for a
    downed service.
    """


class UsageError(RuntimeError):
    """Raised when this module was INVOKED in a way that cannot work — not a defect in it.

    Kept apart from every other exception for the same reason `ConfigError` is: the command line
    reports both as one self-explaining line and files NO bug report, because a bug report is
    supposed to mean "this tool is broken". The foreseeable case is running this file by path
    (`python3 coupler/server.py`), which puts `coupler/` on the import path instead of the
    package root and so leaves the `coupler` package unimportable. That is a mistake the message
    can fix in one line; answering it with a traceback and a filed bug report would blame the
    tool for the invocation and put a false record in the sink.
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do this module throws `ConfigError` at import. Every
    value below is one the ORIGINAL hardcoded, so a config built from this template makes the
    server behave exactly as the original's did — which is not a claim, it is what `selftest`
    check [2] measures against the original itself.
    """
    return {
        # ── module-level bindings the original computed at import ──
        "telemetry_path": "code/forge/work/jazz_telemetry",
        "jazz_root_env": "JAZZ_ROOT",
        "jazz_root_default": "code/workspace/main",
        "jazz_dev_env": "JAZZ_DEV",
        "jazz_dev_default": "code/jazz",
        "port_env": "COUPLER_PORT",
        "default_port": 7770,

        # ── build.json ──
        "build_json_path": "conf/env/build.json",
        "build_section": "coupler",
        "disabled_key": "disabled",
        "version_key": "version",
        "version_unknown": "unknown",

        # ── downstream services ──
        "services": [
            ["notes_db", "notes_db_mcp"],
            ["z3", "z3_mcp"],
            ["codebean", "codebean_mcp"],
            ["bootstrap", "bootstrap_mcp"],
            ["services", "service_registry_mcp"],
            ["volctl", "volctl"],
            ["gs", "git_surface_mcp"],
        ],
        "disable_env": "COUPLER_DISABLE",
        "disable_separator": ",",
        "python_env": "COUPLER_PYTHON",
        "service_module_flag": "-m",

        # ── the app ──
        "server_name": "coupler",
        "why5_module": "coupler.why5",
        "json_indent": 2,
        "host_env": "COUPLER_HOST",
        "default_host": "127.0.0.1",
        "transport": "sse",

        "health": {
            "path": "/health",
            "methods": ["GET"],
            "status": "ok",
            "role": "coupler",
            "transport": "sse",
            "fields": {"status": "status", "role": "role", "version": "version",
                       "transport": "transport"},
        },

        "status": {
            "ok": "ok",
            "down": "down",
            "off": "off",
            "degraded": "degraded",
            "fields": {"ui": "ui", "self": "coupler", "version": "jazz_version"},
        },

        "ui": {
            "url_env": "JSON_CONTROLS_URL",
            "url_default": "http://127.0.0.1:8142",
            "timeout_seconds": 5.0,
            "probe_timeout_seconds": 2.0,
            "probe_path": "/pages",
            "degraded_status": 500,
            "page_path": "/page/{name}",
            "state_path": "/state/{page}",
            "value_path": "/state/{page}/{name}",
            "pages_path": "/pages",
            "message_path": "/message/{page}/{control}",
            "log_path": "/log",
            "log_limit_param": "limit",
            "default_log_limit": 20,
            "value_field": "value",
            "name_field": "name",
            "role_field": "role",
            "text_field": "text",
            "true_literal": "true",
            "false_literal": "false",
        },

        "telemetry": {
            "module": "jazz_telemetry",
            "service": "coupler",
            "build_event": "build_app",
            "mount_event": "mount",
        },

        # ── every line the original wrote to stderr ──
        "messages": {
            "starting": "  coupler/server starting",
            "version": "  jazz version : {version}",
            "python": "  notes python : {python}",
            "port": "  port         : {port}",
            "disabled": "  disabled     : {names}",
            "disabled_join": ", ",
            "skipped": "  skipped      : {name} (disabled)",
            "mounted": "  mounted      : {name} ({module})",
            "mount_failed": "  [warn] {name}: {error}",
            "why5_mounted": "  mounted      : why5",
            "why5_failed": "  [warn] why5: {error}",
            "ui_mounted": "  mounted      : ui (port 8142)",
        },

        # ── every string the original's tools RETURN ──
        "tool_messages": {
            "why5_started": "why5 session '{session_id}' started",
            "why5_fact": "fact '{name}' = {value}",
            "why5_link": "link [{label}] {because} → {cause}",
            "why5_missing": "error: session '{session_id}' not found",
            "ui_no_name": "error: config must have a 'name' field",
            "ui_page_registered": "page '{name}' registered",
            "ui_error": "error: {error}",
            "ui_value_set": "set {page}.{name} = {value!r}",
            "ui_no_pages": "no pages registered",
            "ui_message_added": "message added to {page}.{control}",
            "ui_no_changes": "no changes yet",
        },

        # ── every tool description an MCP client sees (the original spelled these as docstrings;
        #    fastmcp publishes a tool's docstring as its description) ──
        #
        # `coupler_status`'s value is DEDENTED, and that is not a tidying — it is what the
        # original actually produces. CPython 3.13+ strips a docstring's common leading
        # whitespace AT COMPILE TIME (gh-81283), so the original's indented triple-quoted
        # docstring reaches an MCP client with no indentation at all. A config string gets no
        # such treatment, so carrying the indented source text here would make this rewrite
        # publish a description the original never published. The differential caught exactly
        # that; the value below is the one the original yields on the interpreter this package is
        # verified against, and `selftest` check [2] compares the two byte for byte.
        #
        # On Python <= 3.12 the compiler did not dedent, so the ORIGINAL itself published the
        # indented form there. That is a difference in the original's own output across
        # interpreters, not one this rewrite can resolve: the description is data here, and an
        # operator running an older interpreter who wants the old spelling puts it in the config.
        "tool_descriptions": {
            "coupler_status": "\nCheck which coupler services are available right now.\n"
                              "Call this if a tool fails unexpectedly, before retrying, or to "
                              "decide\nwhether to proceed with a workflow that depends on a "
                              "specific service.\nReturns a JSON object: {service: \"ok\" | "
                              "\"degraded\" | \"down\"}.\n",
            "why5_new": "Start a new 5-why root cause analysis session.",
            "why5_fact": "Assert a known observable fact into a why5 session.",
            "why5_link": "Add a causal link: if `because` is true then `cause` must be true.",
            "why5_check": "Verify the causal chain with Z3. Optionally save to notes_db.",
            "why5_from_ci_failure": "Build and verify a why5 chain from CI pytest output.",
            "ui_set_page": "Push a page config to the browser UI.",
            "ui_get_state": "Get the current value of every control on a UI page.",
            "ui_set_value": "Set a control value on a UI page.",
            "ui_list_pages": "List all registered UI pages.",
            "ui_add_message": "Append a message to a chatbox control on a UI page.",
            "ui_get_log": "Get recent control change events from the browser.",
        },
    }


def find_registry(start=None):
    """Return the path of the registry this unit should read, or None if there is none.

    Walks UP from `start` (default: this file's directory) looking for `REGISTRY_NAME`. If the
    walk reaches the filesystem root without finding one, falls back to the copy shipped as
    package data inside `PACKAGE_WITH_REGISTRY`, which is the only one a non-editable install
    has. An explicit `start` suppresses that fallback: a caller naming a directory to search is
    asking about THAT tree, and quietly answering with the installed package's registry instead
    would report a config the caller never pointed at.
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

    if start is not None:
        return None
    return _installed_registry()


def _installed_registry():
    """Return the registry shipped as package data in `PACKAGE_WITH_REGISTRY`, or None.

    `pyproject.toml` maps that package onto this package's ROOT directory and ships
    `registry.json` as its package data, so locating the package locates the registry. Import
    machinery answers this without importing the package, which matters: importing it is not free
    and this is called from the import of a module inside it.
    """
    try:
        import importlib.util

        spec = importlib.util.find_spec(PACKAGE_WITH_REGISTRY)
    except Exception:  # noqa: BLE001 — a missing/broken package is simply "no registry here"
        return None
    if spec is None:
        return None
    for location in list(getattr(spec, "submodule_search_locations", None) or []):
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
        ConfigError: if no config object can be found, naming every source that was tried.
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
        return (config,
                os.path.dirname(os.path.abspath(env_path)),
                "%s=%s" % (CONFIG_ENV, env_path))

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s: %s is unset, no %s was found by walking up from %s, and no "
            "%s package ships one. Run `%s emit-config` for a template of the config object to "
            "install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))),
               PACKAGE_WITH_REGISTRY, _cli_name())
        )

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. "
                "Run `%s emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), _cli_name(),
                   " -> ".join(UNIT_PATH))
            )
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError(
            "the registry section %s at %s must be a JSON object, not %s"
            % (".".join(UNIT_PATH), registry_path, type(node).__name__)
        )

    config = dict(node)
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit section
    # may state its own to override it. This is inheritance inside ONE config document, not a
    # guessed default — if neither states it, the key stays absent and the CLI files no report.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


def require(section, key, where, types_):
    """Return `section[key]`, proving it is present and of the right type; else raise.

    Type-checking here rather than letting a bad value flow onward is deliberate. `build_app`
    swallows `Exception` around every mount and around the whole why5 block (the original did,
    and that is preserved), so a non-string module name or a malformed service table reaching
    them would raise INSIDE those guards and be silently reported as "that service is down" —
    turning an operator's config mistake into a plausible-looking wrong answer. A malformed config
    object is a config error, and it is raised as one, at import, before any guard is entered.

    Args:
        section: the config object (or sub-object) to read.
        key: the key to require.
        where: human-readable description of the section, for the error message.
        types_: a type or tuple of types the value must be an instance of.

    Raises:
        ConfigError: if the key is absent or the value is of the wrong type.
    """
    if not isinstance(section, dict):
        raise ConfigError(
            "the config section %s for %s must be a JSON object, not %s"
            % (where, UNIT, type(section).__name__)
        )
    if key not in section:
        raise ConfigError(
            "the config section %s for %s is missing the required key %r. Run `%s emit-config` "
            "for a template." % (where, UNIT, key, _cli_name())
        )
    value = section[key]
    # `bool` is a subclass of `int`, so isinstance(True, int) is True. A `true` where a port or a
    # timeout belongs is a config mistake, and silently accepting it as 1 would make the server
    # bind port 1 and call that the operator's intent.
    wanted = types_ if isinstance(types_, tuple) else (types_,)
    if isinstance(value, bool) and bool not in wanted:
        raise ConfigError(
            "the config key %r in %s for %s must be %s, not a boolean"
            % (key, where, UNIT, _type_names(wanted))
        )
    if not isinstance(value, wanted):
        raise ConfigError(
            "the config key %r in %s for %s must be %s, not %s"
            % (key, where, UNIT, _type_names(wanted), type(value).__name__)
        )
    return value


def _type_names(wanted):
    return " or ".join(t.__name__ for t in wanted)


def _cli_name():
    """Name an invocation of this tool that the reader can actually retype.

    The `-m` form, which is what works from a source checkout and is what every command in the
    module docstring's RUNNING IT uses.
    """
    return "python3 -m " + DOTTED_NAME


# ─────────────────────────────── the config in force ───────────────────────────────

_ACTIVE = None      # config injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution, so repeat calls re-read no files


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

    Injecting a config does NOT rebind this module's globals: the original bound `PORT`,
    `JAZZ_ROOT` and `JAZZ_DEV` once, at import, and that is preserved.
    `importlib.reload(coupler.server)` is what re-reads the config, exactly as it is what
    re-read the environment for the original.
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


@_cm
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


def _load() -> dict:
    """Read, validate and flatten this unit's config object into the module globals' values.

    Every value the original hardcoded is required here and NONE is defaulted, so a config object
    missing any one of them raises `ConfigError` naming it rather than letting this module fall
    back to the original's constant. That is acceptance item (d).
    """
    config = active_config()
    health = require(config, "health", UNIT, dict)
    status = require(config, "status", UNIT, dict)
    ui = require(config, "ui", UNIT, dict)
    tel = require(config, "telemetry", UNIT, dict)
    messages = require(config, "messages", UNIT, dict)
    tool_messages = require(config, "tool_messages", UNIT, dict)
    tool_descriptions = require(config, "tool_descriptions", UNIT, dict)
    health_fields = require(health, "fields", "%s -> health" % UNIT, dict)
    status_fields = require(status, "fields", "%s -> status" % UNIT, dict)

    where_h, where_s, where_u = ("%s -> health" % UNIT, "%s -> status" % UNIT, "%s -> ui" % UNIT)
    where_t = "%s -> telemetry" % UNIT
    where_m, where_tm = ("%s -> messages" % UNIT, "%s -> tool_messages" % UNIT)
    where_td = "%s -> tool_descriptions" % UNIT
    where_hf, where_sf = ("%s -> health -> fields" % UNIT, "%s -> status -> fields" % UNIT)

    settings = {
        "telemetry_path": require(config, "telemetry_path", UNIT, str),
        "jazz_root_env": require(config, "jazz_root_env", UNIT, str),
        "jazz_root_default": require(config, "jazz_root_default", UNIT, str),
        "jazz_dev_env": require(config, "jazz_dev_env", UNIT, str),
        "jazz_dev_default": require(config, "jazz_dev_default", UNIT, str),
        "port_env": require(config, "port_env", UNIT, str),
        "default_port": require(config, "default_port", UNIT, int),
        "build_json_path": require(config, "build_json_path", UNIT, str),
        "build_section": require(config, "build_section", UNIT, str),
        "disabled_key": require(config, "disabled_key", UNIT, str),
        "version_key": require(config, "version_key", UNIT, str),
        "version_unknown": require(config, "version_unknown", UNIT, str),
        "disable_env": require(config, "disable_env", UNIT, str),
        "disable_separator": require(config, "disable_separator", UNIT, str),
        "python_env": require(config, "python_env", UNIT, str),
        "service_module_flag": require(config, "service_module_flag", UNIT, str),
        "server_name": require(config, "server_name", UNIT, str),
        "why5_module": require(config, "why5_module", UNIT, str),
        "json_indent": require(config, "json_indent", UNIT, int),
        "host_env": require(config, "host_env", UNIT, str),
        "default_host": require(config, "default_host", UNIT, str),
        "transport": require(config, "transport", UNIT, str),

        "health_path": require(health, "path", where_h, str),
        "health_methods": list(require(health, "methods", where_h, list)),
        "health_status": require(health, "status", where_h, str),
        "health_role": require(health, "role", where_h, str),
        "health_transport": require(health, "transport", where_h, str),
        "health_field_status": require(health_fields, "status", where_hf, str),
        "health_field_role": require(health_fields, "role", where_hf, str),
        "health_field_version": require(health_fields, "version", where_hf, str),
        "health_field_transport": require(health_fields, "transport", where_hf, str),

        "status_ok": require(status, "ok", where_s, str),
        "status_down": require(status, "down", where_s, str),
        "status_off": require(status, "off", where_s, str),
        "status_degraded": require(status, "degraded", where_s, str),
        "status_field_ui": require(status_fields, "ui", where_sf, str),
        "status_field_self": require(status_fields, "self", where_sf, str),
        "status_field_version": require(status_fields, "version", where_sf, str),

        "ui_url_env": require(ui, "url_env", where_u, str),
        "ui_url_default": require(ui, "url_default", where_u, str),
        "ui_timeout_seconds": require(ui, "timeout_seconds", where_u, (int, float)),
        "ui_probe_timeout_seconds": require(ui, "probe_timeout_seconds", where_u, (int, float)),
        "ui_probe_path": require(ui, "probe_path", where_u, str),
        "ui_degraded_status": require(ui, "degraded_status", where_u, int),
        "ui_page_path": require(ui, "page_path", where_u, str),
        "ui_state_path": require(ui, "state_path", where_u, str),
        "ui_value_path": require(ui, "value_path", where_u, str),
        "ui_pages_path": require(ui, "pages_path", where_u, str),
        "ui_message_path": require(ui, "message_path", where_u, str),
        "ui_log_path": require(ui, "log_path", where_u, str),
        "ui_log_limit_param": require(ui, "log_limit_param", where_u, str),
        "ui_default_log_limit": require(ui, "default_log_limit", where_u, int),
        "ui_value_field": require(ui, "value_field", where_u, str),
        "ui_name_field": require(ui, "name_field", where_u, str),
        "ui_role_field": require(ui, "role_field", where_u, str),
        "ui_text_field": require(ui, "text_field", where_u, str),
        "ui_true_literal": require(ui, "true_literal", where_u, str),
        "ui_false_literal": require(ui, "false_literal", where_u, str),

        "telemetry_module": require(tel, "module", where_t, str),
        "telemetry_service": require(tel, "service", where_t, str),
        "telemetry_build_event": require(tel, "build_event", where_t, str),
        "telemetry_mount_event": require(tel, "mount_event", where_t, str),
    }

    for key in ("starting", "version", "python", "port", "disabled", "disabled_join", "skipped",
                "mounted", "mount_failed", "why5_mounted", "why5_failed", "ui_mounted"):
        settings["msg_" + key] = require(messages, key, where_m, str)
    for key in ("why5_started", "why5_fact", "why5_link", "why5_missing", "ui_no_name",
                "ui_page_registered", "ui_error", "ui_value_set", "ui_no_pages",
                "ui_message_added", "ui_no_changes"):
        settings["tmsg_" + key] = require(tool_messages, key, where_tm, str)
    for key in ("coupler_status", "why5_new", "why5_fact", "why5_link", "why5_check",
                "why5_from_ci_failure", "ui_set_page", "ui_get_state", "ui_set_value",
                "ui_list_pages", "ui_add_message", "ui_get_log"):
        settings["doc_" + key] = require(tool_descriptions, key, where_td, str)

    # The service table. The original's was a list of 2-TUPLES; JSON can only carry lists, so it
    # is converted back — see THE CALLABLE SURFACE. Validated element by element because
    # build_app unpacks `for name, module in JAZZ_SERVICES`, and a malformed row would raise
    # inside the mount guard's `except Exception` and be reported as a downed service.
    services = require(config, "services", UNIT, list)
    table = []
    for index, row in enumerate(services):
        if not isinstance(row, list) or len(row) != 2:
            raise ConfigError(
                "the config key 'services' in %s for %s must hold [name, module] pairs; entry %d "
                "is %r" % (UNIT, UNIT, index, row)
            )
        if not all(isinstance(item, str) for item in row):
            raise ConfigError(
                "the config key 'services' in %s for %s must hold [name, module] pairs of "
                "STRINGS; entry %d is %r" % (UNIT, UNIT, index, row)
            )
        table.append((row[0], row[1]))
    settings["services"] = table
    return settings


# ─────────────────────────────── the module-level surface ───────────────────────────────
#
# Everything here reproduces what the original's module-level code left in this namespace, with
# the values it hardcoded now read from the config object. `active_config()` raises ConfigError
# right here, at import, if this unit cannot see its config: acceptance item (d). That call is
# outside every `except Exception` in this file, so the gate cannot be mistaken for a failed
# mount.
#
# These are module GLOBALS, and the functions below read them at CALL time, because the
# original's did and callers rebind them (`s.JAZZ_ROOT = tmp`). Binding them into a closure or a
# frozen settings object at import would look tidier and would break those callers.

_SETTINGS = _load()


def _stub_telemetry(*_a, **_k):
    """The original's no-op telemetry stand-in, used when `jazz_telemetry` cannot be imported.

    Reproduced exactly: a callable returning an object whose `emit` accepts anything and does
    nothing. The original spelled it as a local class inside its `except Exception` block.
    """
    class _N:
        def emit(self, *a, **k):
            pass
    return _N()


@_cm
def _stub_service_running(*_a, **_k):
    """The original's no-op `service_running` stand-in: a context manager yielding None."""
    yield None


def _install_telemetry(path):
    """Put `path` at the front of `sys.path`, then import telemetry from it — or fall back.

    This is the original's module-level telemetry block, rewritten. Three of its properties are
    load-bearing and preserved exactly:

      * the `sys.path.insert(0, ...)` happens UNCONDITIONALLY, before the import is attempted,
        and is NOT undone. Importing the original mutated `sys.path`, so importing this module
        mutates it identically — `selftest` check [5] measures that rather than claiming it away.
      * the guard is `except Exception`, so a `jazz_telemetry` that raises on import falls back
        to the stubs exactly as an absent one does. `BaseException` is not caught.
      * both names are taken from the same import, so a `jazz_telemetry` exporting only one of
        them falls back for BOTH — the original's `from jazz_telemetry import telemetry,
        service_running` was a single statement and either name missing meant neither was bound.

    Returns:
        A `(telemetry, service_running)` pair: the real ones if the import worked, else the
        module-level stubs above.
    """
    sys.path.insert(0, path)
    try:
        module = __import__(_SETTINGS["telemetry_module"], fromlist=["telemetry",
                                                                     "service_running"])
        return module.telemetry, module.service_running
    except Exception:  # pragma: no cover - telemetry is best-effort, exactly as the original
        return _stub_telemetry, _stub_service_running


#: The jazz_telemetry directory prepended to `sys.path` at import. The original hardcoded
#: `Path.home() / "code" / "forge" / "work" / "jazz_telemetry"`.
TELEMETRY_PATH = str(Path.home() / _SETTINGS["telemetry_path"])

#: `jazz_telemetry`'s two names, or the no-op stubs. Module globals because `build_app` and
#: `main` read them at call time, as the original's did.
telemetry, service_running = _install_telemetry(TELEMETRY_PATH)

#: The jazz workspace root. The original was
#: `Path(os.environ.get("JAZZ_ROOT", Path.home() / "code/workspace/main"))`; the variable name
#: and the default are config now, and the environment still overrides both.
JAZZ_ROOT = Path(os.environ.get(_SETTINGS["jazz_root_env"],
                                Path.home() / _SETTINGS["jazz_root_default"]))

#: The jazz development checkout. Bound exactly as the original bound it — and, exactly as in the
#: original, nothing in this module reads it. It is part of the surface because the original
#: exported it and callers import it; it is not dead config.
JAZZ_DEV = Path(os.environ.get(_SETTINGS["jazz_dev_env"],
                               Path.home() / _SETTINGS["jazz_dev_default"]))


def _env_port(name: str, default: int) -> int:
    """Read an integer port from env, tolerating Kubernetes service-link vars.

    k8s injects `<SERVICENAME>_PORT=tcp://<clusterip>:<port>` for every Service in the namespace.
    When the Service is named 'coupler', that clobbers our own `COUPLER_PORT` with a 'tcp://…'
    URL. Fall back to the default (or the URL's trailing port) instead of crashing on
    `int('tcp://…')`.

    The resolution, in the original's order — `selftest` checks [2] and [3] prove each branch
    against the original AS IT RUNS:

      1. the variable is unset            -> `default`
      2. `int(raw)` succeeds              -> that integer
      3. else `int(raw.rsplit(":", 1)[-1])` succeeds -> that integer
      4. else                             -> `default`

    Three properties of that are easy to get wrong and are preserved deliberately:

      * step 3 takes the TRAILING colon-separated field of ANY value, not just a URL. So
        `"8000:9000"` yields 9000 — the last field, not the first, and not the default.
      * the parsing is Python's `int()`, so whitespace, a leading `+`, underscore separators
        (`"1_000"` -> 1000), negative values (`"-1"` -> -1) and non-ASCII decimal digits
        (`"٨"` -> 8) are all accepted. None is validated away.
      * only `ValueError` is caught. `int()` raises `TypeError` for a non-string, but
        `os.environ.get` only ever yields `str` or None, so that branch was unreachable in the
        original and is unreachable here.

    Args:
        name: the environment variable to read.
        default: the port to fall back to when nothing usable is there.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        tail = raw.rsplit(":", 1)[-1]  # 'tcp://10.43.0.1:8000' -> '8000'
        try:
            return int(tail)
        except ValueError:
            return default


#: The port this server binds. The original was `_env_port("COUPLER_PORT", 7770)`, evaluated at
#: import; the variable name and the default are config now, and the environment still overrides
#: both, through exactly the same `_env_port` resolution.
PORT = _env_port(_SETTINGS["port_env"], _SETTINGS["default_port"])


def _load_build() -> dict:
    """Return the parsed `build.json`, or `{}` when there is none.

    Reads `JAZZ_ROOT` as a module global at call time, so rebinding it on the module takes effect
    on the next call — as it did for the original, and as `selftest` check [3] proves.

    NOTHING is caught. A `build.json` that exists but is not valid JSON raises `JSONDecodeError`
    out of this function, and one holding a JSON array or scalar is returned AS IS — the `-> dict`
    annotation is the original's and it is not enforced by it, so a list flows onward and makes
    `_disabled_services` raise `AttributeError: 'list' object has no attribute 'get'`. Both are
    the original's behavior, measured against it, and neither is "fixed" here.
    """
    p = JAZZ_ROOT / _SETTINGS["build_json_path"]
    return json.loads(p.read_text()) if p.exists() else {}


#: Downstream jazz MCP servers the coupler can mount — single source of truth.
#:
#: The original's comment is worth keeping with the data: notes_mcp is retired — it was a JSON
#: tree-of-notes prototype over conf/notes/notes.json, NOT a notes_db client (a red herring). The
#: real brain is notes_db (:8001) / notes_db_mcp (:8002). `gs` is the git surface + VM control
#: (vm_* tools, machine time-travel).
#:
#: Config-driven now, but still a module global holding 2-TUPLES, because the original's was and
#: callers read and rebind it.
JAZZ_SERVICES = _SETTINGS["services"]


def _disabled_services() -> set:
    """Which MCP servers to skip. Sources, merged:
      • env  `COUPLER_DISABLE="z3,notes"`   (comma-separated)
      • build.json  `{"coupler": {"disabled": ["z3"]}}`   or   `{"coupler": {"z3": false}}`
    Default: everything enabled.

    Four properties of the original's set algebra are preserved deliberately, and `selftest`
    check [3] proves each against the original AS IT RUNS:

      * the build-section test is `v is False`, NOT falsiness. `{"z3": 0}` does NOT disable z3,
        because `0 is False` is False. `{"z3": ""}` and `{"z3": null}` likewise do not.
      * `set(cfg.get("disabled", []))` iterates whatever it is given, so a STRING is taken
        character by character: `{"disabled": "z3"}` disables `{"z", "3"}`. Not fixed.
      * `{"disabled": false}` raises `TypeError: 'bool' object is not iterable`. Not guarded.
      * `.get(section, {}) or {}` is what makes `{"coupler": null}` safe — the `or {}` catches
        the None that the `.get` default cannot, because the key IS present.

    The env var is split on the separator and empty/whitespace-only fields are dropped, so
    `"z3, notes ,, "` yields `{"z3", "notes"}` and an unset or empty variable yields nothing.

    Raises:
        Whatever `_load_build` raises — a malformed build.json is not caught here.
    """
    names = {s.strip()
             for s in os.environ.get(_SETTINGS["disable_env"], "")
             .split(_SETTINGS["disable_separator"]) if s.strip()}
    cfg = _load_build().get(_SETTINGS["build_section"], {}) or {}
    disabled_key = _SETTINGS["disabled_key"]
    names |= set(cfg.get(disabled_key, []))
    names |= {k for k, v in cfg.items() if k != disabled_key and v is False}
    return names


def _notes_python() -> str:
    """Interpreter used to launch downstream MCP subprocesses.

    They run under the SAME venv as coupler — whatever Python is running this server.
    (Historically this hunted a conda env via build.json; conda is gone since old_jazz.) Override
    with `COUPLER_PYTHON` if a downstream needs a different interpreter.

    `sys.executable` is read at CALL time, as the original read it, so a caller that rebinds it
    sees the change.
    """
    return os.environ.get(_SETTINGS["python_env"], sys.executable)


def _load_deps():
    """Import the third-party names `build_app` needs, and return them.

    The original imported these at MODULE scope. Importing them here instead is this rewrite's
    one deliberate deviation, and `build_app()` calls this FIRST so the `ImportError` still lands
    before anything is printed or built. See THE `fastmcp` / `httpx` / `starlette` DEPENDENCIES in
    the module docstring for why.

    `starlette.responses.JSONResponse` is included even though the original imported it inside
    `build_app` rather than at module scope: gathering all five in one place is what lets
    `build_app` fail fast on any missing dependency instead of getting halfway through and then
    dying on the `/health` route.

    Returns:
        A `(FastMCP, Client, StdioTransport, create_proxy, httpx, JSONResponse)` tuple.

    Raises:
        ImportError: if fastmcp, httpx or starlette is not installed — exactly as importing the
            original did.
    """
    import httpx
    from fastmcp import Client, FastMCP
    from fastmcp.client.transports import StdioTransport
    from fastmcp.server import create_proxy
    from starlette.responses import JSONResponse

    return FastMCP, Client, StdioTransport, create_proxy, httpx, JSONResponse


def _import_names(dotted, names):
    """`from <dotted> import <names>`, by name, with the original's exact failure modes.

    `build_app`'s why5 block is spelled `from coupler.why5 import Why5, from_ci_failure` in the
    original. The module name is config here, so the statement cannot be written literally — but
    the two ways it fails are observable, because the `except Exception` around the block prints
    the exception's text. Both are reproduced:

      * the module does not exist -> `ModuleNotFoundError: No module named '<dotted>'`, which is
        what `importlib.import_module` raises on its own. This is the case that actually happens:
        `coupler.why5` does not exist in this package.
      * the module exists but lacks a name -> `ImportError: cannot import name 'X' from '<dotted>'
        (<file>)`, which is CPython's own wording for a failed `from ... import ...`. `getattr`
        would raise `AttributeError` with different text, so it is converted here.

    `selftest` check [3] proves both against the original by injecting a stand-in `coupler.why5`
    into `sys.modules` — with the names, and then without them — and comparing the two modules'
    stderr byte for byte.
    """
    import importlib

    module = importlib.import_module(dotted)
    out = []
    for name in names:
        try:
            out.append(getattr(module, name))
        except AttributeError:
            raise ImportError(
                "cannot import name %r from %r (%s)"
                % (name, dotted, getattr(module, "__file__", None) or "unknown location")
            ) from None
    return out


def build_app() -> "FastMCP":
    """Construct the coupler MCP server: mount every enabled service, register every tool.

    This is the original's `build_app`, rewritten. It prints its four banner lines to stderr,
    creates the `FastMCP` app, registers the plain-HTTP `/health` route, emits one telemetry
    `build_app` event, mounts each enabled downstream service as a namespaced proxy (recording
    each as "ok"/"down"/"off" for `coupler_status`), registers `coupler_status`, tries to register
    the five why5 tools, and registers the six UI tools.

    The return annotation is the forward reference `"FastMCP"` rather than the class itself,
    because fastmcp is imported lazily (see the module docstring). With fastmcp installed,
    `inspect.signature(build_app, eval_str=True, globals={"FastMCP": fastmcp.FastMCP})` resolves
    to exactly the annotation the ORIGINAL carries; `selftest` check [4] does precisely that and
    compares the two renderings, so the surface `build_app() -> FastMCP` is proven rather than
    approximated.

    Reads `PORT`, `JAZZ_SERVICES`, `JAZZ_ROOT` (through `_load_build`) and `telemetry` as module
    globals at call time, so rebinding any of them takes effect on the next call — as it did for
    the original.

    Returns:
        The configured `FastMCP` app, ready for `run_http_async`.

    Raises:
        ImportError: if fastmcp, httpx or starlette is missing, before anything is printed.
        Whatever `_load_build` raises: a malformed build.json is not caught.
    """
    # First, so a missing dependency fails immediately rather than halfway through the build. The
    # original's module-scope imports gave it the same immediacy.
    FastMCP, Client, StdioTransport, create_proxy, httpx, JSONResponse = _load_deps()

    S = _SETTINGS
    python = _notes_python()
    build = _load_build()
    version = build.get(S["version_key"], S["version_unknown"])

    print(S["msg_starting"], file=sys.stderr)
    print(S["msg_version"].format(version=version), file=sys.stderr)
    print(S["msg_python"].format(python=python), file=sys.stderr)
    print(S["msg_port"].format(port=PORT), file=sys.stderr)

    app = FastMCP(S["server_name"])

    # Plain HTTP liveness/readiness endpoint (no MCP session needed). Lets a k8s readiness probe /
    # reverse proxy confirm the server is up without opening an SSE stream. Mirrors the POC stub's
    # /health contract.
    #
    # The four field NAMES are that contract — a probe parses them — and the construction order is
    # the original's, because JSON object order is observable. Both the names and the values are
    # config; only the ORDER is fixed here.
    async def _health(_request):
        return JSONResponse({S["health_field_status"]: S["health_status"],
                             S["health_field_role"]: S["health_role"],
                             S["health_field_version"]: version,
                             S["health_field_transport"]: S["health_transport"]})

    app.custom_route(S["health_path"], methods=list(S["health_methods"]))(_health)

    _tel = telemetry(S["telemetry_service"], version=version)
    # app constructed; lifecycle start is in main()
    _tel.emit(S["telemetry_build_event"], status=S["status_ok"], port=PORT)

    # track which services mounted successfully for the status tool
    _services: dict[str, str] = {}   # name → "ok" | "down" | "off"

    disabled = _disabled_services()
    if disabled:
        print(S["msg_disabled"].format(names=S["msg_disabled_join"].join(sorted(disabled))),
              file=sys.stderr)

    # ── jazz service proxies ─────────────────────────────────────────────────
    for name, module in JAZZ_SERVICES:
        if name in disabled:
            _services[name] = S["status_off"]
            _tel.emit(S["telemetry_mount_event"], status=S["status_off"], service=name,
                      module=module)
            print(S["msg_skipped"].format(name=name), file=sys.stderr)
            continue
        try:
            proxy = create_proxy(
                # env={**os.environ}: the MCP stdio client strips custom vars by default, so
                # downstream MCPs never saw CODEBEAN_ROOT etc. (BUG-0002). Pass it through.
                Client(StdioTransport(command=python,
                                      args=[S["service_module_flag"], module],
                                      env={**os.environ}))
            )
            app.mount(proxy, namespace=name)
            _services[name] = S["status_ok"]
            _tel.emit(S["telemetry_mount_event"], status=S["status_ok"], service=name,
                      module=module)
            print(S["msg_mounted"].format(name=name, module=module), file=sys.stderr)
        except Exception as e:
            # Deliberately broad, and deliberately not `BaseException`: this is the original's
            # guard. One service that cannot mount is recorded "down" and the loop goes on.
            _services[name] = S["status_down"]
            _tel.emit(S["telemetry_mount_event"], status=S["status_down"], service=name,
                      module=module, error=f"{type(e).__name__}: {e}")
            print(S["msg_mount_failed"].format(name=name, error=e), file=sys.stderr)

    # ── status tool ──────────────────────────────────────────────────────────
    async def coupler_status() -> str:
        status = dict(_services)

        # re-probe each jazz service with a quick list-tools ping (skip disabled)
        for name, module in JAZZ_SERVICES:
            if name in disabled:
                status[name] = S["status_off"]
                continue
            try:
                async with Client(StdioTransport(command=python,
                                                 args=[S["service_module_flag"], module],
                                                 env={**os.environ})) as c:
                    await c.list_tools()
                status[name] = S["status_ok"]
            except Exception:
                status[name] = S["status_down"]

        # probe UI
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(
                    os.environ.get(S["ui_url_env"], S["ui_url_default"]) + S["ui_probe_path"],
                    timeout=S["ui_probe_timeout_seconds"])
                status[S["status_field_ui"]] = (S["status_ok"]
                                                if r.status_code < S["ui_degraded_status"]
                                                else S["status_degraded"])
        except Exception:
            status[S["status_field_ui"]] = S["status_down"]

        status[S["status_field_self"]] = S["status_ok"]
        status[S["status_field_version"]] = version
        return json.dumps(status, indent=S["json_indent"])

    # The description MUST be assigned BEFORE the decorator runs: fastmcp reads `__doc__` off the
    # function as it registers it, so decorating first and assigning after registers the tool with
    # no description at all. That is not a guess — it is the defect #357's selftest caught in
    # `bridge.py` and the reason this file never writes `@app.tool()` above a config-described
    # tool. `_register` below does the two steps in the right order, once, for all twelve.
    _register(app, coupler_status, S["doc_coupler_status"])

    # ── why5 (ported into the coupler package; z3_mcp via forge editable) ─────
    try:
        Why5, from_ci_failure = _import_names(S["why5_module"], ("Why5", "from_ci_failure"))
        _sessions: dict = {}

        def why5_new(session_id: str, trigger: str = "") -> str:
            _sessions[session_id] = Why5(session_id=session_id, trigger=trigger)
            return S["tmsg_why5_started"].format(session_id=session_id)

        def why5_fact(session_id: str, name: str, value: bool) -> str:
            _sessions[session_id].fact(name, value)
            return S["tmsg_why5_fact"].format(name=name, value=value)

        def why5_link(session_id: str, label: str, cause: str, because: str) -> str:
            _sessions[session_id].link(label, cause=cause, because=because)
            return S["tmsg_why5_link"].format(label=label, because=because, cause=cause)

        def why5_check(session_id: str, save: bool = False) -> str:
            w = _sessions.get(session_id)
            if not w:
                return S["tmsg_why5_missing"].format(session_id=session_id)
            result = w.check()
            if save:
                w.save()
            return json.dumps(result, indent=S["json_indent"])

        def why5_from_ci_failure(session_id: str, branch: str, sha: str,
                                 pytest_output: str, save: bool = False) -> str:
            w = from_ci_failure(session_id, branch=branch, pre_sha=sha,
                                pytest_output=pytest_output)
            _sessions[session_id] = w
            result = w.check()
            if save:
                w.save()
            return json.dumps(result, indent=S["json_indent"])

        _register(app, why5_new, S["doc_why5_new"])
        _register(app, why5_fact, S["doc_why5_fact"])
        _register(app, why5_link, S["doc_why5_link"])
        _register(app, why5_check, S["doc_why5_check"])
        _register(app, why5_from_ci_failure, S["doc_why5_from_ci_failure"])

        print(S["msg_why5_mounted"], file=sys.stderr)
    except Exception as e:
        # The original's guard covers the IMPORT and all five registrations. `coupler.why5` does
        # not exist in this package, so in practice this is the branch that runs and the five why5
        # tools are never registered.
        print(S["msg_why5_failed"].format(error=e), file=sys.stderr)

    # ── UI bridge ────────────────────────────────────────────────────────────
    UI_BASE = os.environ.get(S["ui_url_env"], S["ui_url_default"])
    T = S["ui_timeout_seconds"]

    def _get(path, **p):
        r = httpx.get(f"{UI_BASE}{path}", params=p, timeout=T); r.raise_for_status(); return r.json()

    def _post(path, body):
        r = httpx.post(f"{UI_BASE}{path}", json=body, timeout=T); r.raise_for_status(); return r.json()

    def _put(path, body):
        r = httpx.put(f"{UI_BASE}{path}", json=body, timeout=T); r.raise_for_status(); return r.json()

    def ui_set_page(config: dict) -> str:
        name = config.get(S["ui_name_field"])
        if not name:
            return S["tmsg_ui_no_name"]
        try:
            _post(S["ui_page_path"].format(name=name), config)
            return S["tmsg_ui_page_registered"].format(name=name)
        except Exception as e:
            return S["tmsg_ui_error"].format(error=e)

    def ui_get_state(page: str) -> str:
        try:
            return json.dumps(_get(S["ui_state_path"].format(page=page)), indent=S["json_indent"])
        except Exception as e:
            return S["tmsg_ui_error"].format(error=e)

    def ui_set_value(page: str, name: str, value: str) -> str:
        # The original's literal ladder: "true"/"false" (case-insensitively) become bools, else
        # int, else float, else the string is left alone. `float()` accepts "inf" and "nan", so
        # those become floats rather than staying strings — preserved, not fixed.
        parsed: object = value
        if value.lower() == S["ui_true_literal"]:
            parsed = True
        elif value.lower() == S["ui_false_literal"]:
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
            _put(S["ui_value_path"].format(page=page, name=name), {S["ui_value_field"]: parsed})
            return S["tmsg_ui_value_set"].format(page=page, name=name, value=parsed)
        except Exception as e:
            return S["tmsg_ui_error"].format(error=e)

    def ui_list_pages() -> str:
        try:
            pages = _get(S["ui_pages_path"])
            return (json.dumps(pages, indent=S["json_indent"]) if pages
                    else S["tmsg_ui_no_pages"])
        except Exception as e:
            return S["tmsg_ui_error"].format(error=e)

    def ui_add_message(page: str, control: str, role: str, text: str) -> str:
        try:
            _post(S["ui_message_path"].format(page=page, control=control),
                  {S["ui_role_field"]: role, S["ui_text_field"]: text})
            return S["tmsg_ui_message_added"].format(page=page, control=control)
        except Exception as e:
            return S["tmsg_ui_error"].format(error=e)

    def ui_get_log(limit: int = _SETTINGS["ui_default_log_limit"]) -> str:
        try:
            log = _get(S["ui_log_path"], **{S["ui_log_limit_param"]: limit})
            return json.dumps(log, indent=S["json_indent"]) if log else S["tmsg_ui_no_changes"]
        except Exception as e:
            return S["tmsg_ui_error"].format(error=e)

    _register(app, ui_set_page, S["doc_ui_set_page"])
    _register(app, ui_get_state, S["doc_ui_get_state"])
    _register(app, ui_set_value, S["doc_ui_set_value"])
    _register(app, ui_list_pages, S["doc_ui_list_pages"])
    _register(app, ui_add_message, S["doc_ui_add_message"])
    _register(app, ui_get_log, S["doc_ui_get_log"])

    print(S["msg_ui_mounted"], file=sys.stderr)
    return app


def _register(app, fn, description):
    """Give `fn` its description, THEN register it as a tool. Order matters — see below.

    fastmcp publishes a tool's `__doc__` as the description MCP clients see, and it reads that
    attribute AS IT REGISTERS the function. So the assignment must happen before `app.tool()`
    runs, or the tool is registered with no description at all. The original got this for free by
    spelling each description as a real docstring; the descriptions are config here (a docstring
    cannot be an f-string), so the two steps are explicit — and in this order.

    Returns `fn`, so it can be used as a plain call rather than a decorator.
    """
    fn.__doc__ = description
    app.tool()(fn)
    return fn


def main():
    """Parse the original's arguments and serve until killed.

    Takes no parameters and reads `sys.argv`, exactly as the original's did — so
    `python -m coupler.server --port 8080 --host 0.0.0.0` behaves byte for byte as before, and
    `cli()` stages `sys.argv` around this rather than passing an argv through, which would have
    changed the signature the ticket's surface fixes.

    `--port` defaults to the module global `PORT` (so `$COUPLER_PORT` reaches it through
    `_env_port`) and `--host` to `$COUPLER_HOST` or the configured default. Bind host defaults to
    loopback so the local (blue) deployment is unchanged; set `--host 0.0.0.0` or
    `COUPLER_HOST=0.0.0.0` when running inside a container / k8s pod so the SSE endpoint is
    reachable through the cluster (Caddy proxy).

    Blocks until the served session ends. Raises `ImportError` if fastmcp/httpx/starlette are not
    installed, from `build_app()`.
    """
    import asyncio
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--host", default=os.environ.get(_SETTINGS["host_env"],
                                                         _SETTINGS["default_host"]))
    args = parser.parse_args()

    app = build_app()
    # service_running emits service.start + periodic service.heartbeat + service.stop
    with service_running(_SETTINGS["telemetry_service"], port=args.port):
        asyncio.run(app.run_http_async(transport=_SETTINGS["transport"], host=args.host,
                                       port=args.port))


# ─────────────────────────────── the original, embedded ───────────────────────────────

#: The forge unit this file rewrites, verbatim — ticket #385 embeds it as "the authoritative copy
#: and the behavior-preserving basis", and it is the ORACLE `selftest` measures against.
#: `selftest` check [0] proves these are the real forge bytes by hashing them the way git hashes a
#: blob and comparing to the sha1 the ticket records, so no check below rests on a transcription
#: anyone has to take on trust.
ORIGINAL_SOURCE = '''#!/usr/bin/env python3
"""
coupler/server.py — HTTP MCP server on localhost:7770.

Run this as a long-lived daemon. Restart it to deploy updates.
Claude Desktop never needs to restart — bridge.py reconnects automatically.

Usage:
  python -m coupler.server [--port 7770]
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from fastmcp import FastMCP, Client
from fastmcp.client.transports import StdioTransport
from fastmcp.server import create_proxy

# ── jazz_telemetry (graceful: never hard-fail if the lib isn't present) ─────────
sys.path.insert(0, str(Path.home() / "code" / "forge" / "work" / "jazz_telemetry"))
try:
    from jazz_telemetry import telemetry, service_running
except Exception:  # pragma: no cover - telemetry is best-effort
    from contextlib import contextmanager as _cm

    def telemetry(*_a, **_k):
        class _N:
            def emit(self, *a, **k):
                pass
        return _N()

    @_cm
    def service_running(*_a, **_k):
        yield None

JAZZ_ROOT = Path(os.environ.get("JAZZ_ROOT", Path.home() / "code/workspace/main"))
JAZZ_DEV  = Path(os.environ.get("JAZZ_DEV",  Path.home() / "code/jazz"))


def _env_port(name: str, default: int) -> int:
    """Read an integer port from env, tolerating Kubernetes service-link vars.

    k8s injects <SERVICENAME>_PORT=tcp://<clusterip>:<port> for every Service in
    the namespace. When the Service is named 'coupler', that clobbers our own
    COUPLER_PORT with a 'tcp://…' URL. Fall back to the default (or the URL's
    trailing port) instead of crashing on int('tcp://…')."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        tail = raw.rsplit(":", 1)[-1]  # 'tcp://10.43.0.1:8000' -> '8000'
        try:
            return int(tail)
        except ValueError:
            return default


PORT      = _env_port("COUPLER_PORT", 7770)


def _load_build() -> dict:
    p = JAZZ_ROOT / "conf/env/build.json"
    return json.loads(p.read_text()) if p.exists() else {}


# Downstream jazz MCP servers the coupler can mount — single source of truth.
# notes_mcp retired: a JSON tree-of-notes prototype over conf/notes/notes.json, NOT a
# notes_db client (a red herring). The real brain is notes_db (:8001) / notes_db_mcp (:8002).
JAZZ_SERVICES = [
    ("notes_db",  "notes_db_mcp"),
    ("z3",        "z3_mcp"),
    ("codebean",  "codebean_mcp"),
    ("bootstrap", "bootstrap_mcp"),
    ("services",  "service_registry_mcp"),
    ("volctl",    "volctl"),
    ("gs",        "git_surface_mcp"),   # git surface + VM control (vm_* tools, machine time-travel)
]


def _disabled_services() -> set:
    """Which MCP servers to skip. Sources, merged:
      • env  COUPLER_DISABLE="z3,notes"   (comma-separated)
      • build.json  {"coupler": {"disabled": ["z3"]}}   or   {"coupler": {"z3": false}}
    Default: everything enabled."""
    names = {s.strip() for s in os.environ.get("COUPLER_DISABLE", "").split(",") if s.strip()}
    cfg = _load_build().get("coupler", {}) or {}
    names |= set(cfg.get("disabled", []))
    names |= {k for k, v in cfg.items() if k != "disabled" and v is False}
    return names


def _notes_python() -> str:
    """Interpreter used to launch downstream MCP subprocesses.

    They run under the SAME venv as coupler — whatever Python is running this server.
    (Historically this hunted a conda env via build.json; conda is gone since old_jazz.)
    Override with COUPLER_PYTHON if a downstream needs a different interpreter.
    """
    return os.environ.get("COUPLER_PYTHON", sys.executable)


def build_app() -> FastMCP:
    python  = _notes_python()
    build   = _load_build()
    version = build.get("version", "unknown")

    print(f"  coupler/server starting", file=sys.stderr)
    print(f"  jazz version : {version}", file=sys.stderr)
    print(f"  notes python : {python}", file=sys.stderr)
    print(f"  port         : {PORT}", file=sys.stderr)

    app = FastMCP("coupler")

    # Plain HTTP liveness/readiness endpoint (no MCP session needed). Lets a k8s
    # readiness probe / reverse proxy confirm the server is up without opening an
    # SSE stream. Mirrors the POC stub's /health contract.
    from starlette.responses import JSONResponse as _JSONResponse

    @app.custom_route("/health", methods=["GET"])
    async def _health(_request):
        return _JSONResponse({"status": "ok", "role": "coupler",
                              "version": version, "transport": "sse"})

    _tel = telemetry("coupler", version=version)
    _tel.emit("build_app", status="ok", port=PORT)  # app constructed; lifecycle start is in main()

    # track which services mounted successfully for the status tool
    _services: dict[str, str] = {}   # name → "ok" | "down" | "off"

    disabled = _disabled_services()
    if disabled:
        print(f"  disabled     : {', '.join(sorted(disabled))}", file=sys.stderr)

    # ── jazz service proxies ─────────────────────────────────────────────────
    for name, module in JAZZ_SERVICES:
        if name in disabled:
            _services[name] = "off"
            _tel.emit("mount", status="off", service=name, module=module)
            print(f"  skipped      : {name} (disabled)", file=sys.stderr)
            continue
        try:
            proxy = create_proxy(
                # env={**os.environ}: the MCP stdio client strips custom vars by default,
                # so downstream MCPs never saw CODEBEAN_ROOT etc. (BUG-0002). Pass it through.
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
        for name, module in JAZZ_SERVICES:
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

        # probe UI
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(
                    os.environ.get("JSON_CONTROLS_URL", "http://127.0.0.1:8142")
                    + "/pages", timeout=2.0)
                status["ui"] = "ok" if r.status_code < 500 else "degraded"
        except Exception:
            status["ui"] = "down"

        status["coupler"] = "ok"
        status["jazz_version"] = version
        return json.dumps(status, indent=2)

    # ── why5 (ported into the coupler package; z3_mcp via forge editable) ─────
    try:
        from coupler.why5 import Why5, from_ci_failure
        _sessions: dict = {}

        @app.tool()
        def why5_new(session_id: str, trigger: str = "") -> str:
            """Start a new 5-why root cause analysis session."""
            _sessions[session_id] = Why5(session_id=session_id, trigger=trigger)
            return f"why5 session '{session_id}' started"

        @app.tool()
        def why5_fact(session_id: str, name: str, value: bool) -> str:
            """Assert a known observable fact into a why5 session."""
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
    UI_BASE = os.environ.get("JSON_CONTROLS_URL", "http://127.0.0.1:8142")
    T = 5.0

    def _get(path, **p):
        r = httpx.get(f"{UI_BASE}{path}", params=p, timeout=T); r.raise_for_status(); return r.json()

    def _post(path, body):
        r = httpx.post(f"{UI_BASE}{path}", json=body, timeout=T); r.raise_for_status(); return r.json()

    def _put(path, body):
        r = httpx.put(f"{UI_BASE}{path}", json=body, timeout=T); r.raise_for_status(); return r.json()

    @app.tool()
    def ui_set_page(config: dict) -> str:
        """Push a page config to the browser UI."""
        name = config.get("name")
        if not name: return "error: config must have a 'name' field"
        try: _post(f"/page/{name}", config); return f"page '{name}' registered"
        except Exception as e: return f"error: {e}"

    @app.tool()
    def ui_get_state(page: str) -> str:
        """Get the current value of every control on a UI page."""
        try: return json.dumps(_get(f"/state/{page}"), indent=2)
        except Exception as e: return f"error: {e}"

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
        try: _put(f"/state/{page}/{name}", {"value": parsed}); return f"set {page}.{name} = {parsed!r}"
        except Exception as e: return f"error: {e}"

    @app.tool()
    def ui_list_pages() -> str:
        """List all registered UI pages."""
        try:
            pages = _get("/pages")
            return json.dumps(pages, indent=2) if pages else "no pages registered"
        except Exception as e: return f"error: {e}"

    @app.tool()
    def ui_add_message(page: str, control: str, role: str, text: str) -> str:
        """Append a message to a chatbox control on a UI page."""
        try: _post(f"/message/{page}/{control}", {"role": role, "text": text}); return f"message added to {page}.{control}"
        except Exception as e: return f"error: {e}"

    @app.tool()
    def ui_get_log(limit: int = 20) -> str:
        """Get recent control change events from the browser."""
        try:
            log = _get("/log", limit=limit)
            return json.dumps(log, indent=2) if log else "no changes yet"
        except Exception as e: return f"error: {e}"

    print(f"  mounted      : ui (port 8142)", file=sys.stderr)
    return app


def main():
    import asyncio
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT)
    # Bind host. Defaults to loopback so the local (blue) deployment is unchanged;
    # set --host 0.0.0.0 or COUPLER_HOST=0.0.0.0 when running inside a container /
    # k8s pod so the SSE endpoint is reachable through the cluster (Caddy proxy).
    parser.add_argument("--host", default=os.environ.get("COUPLER_HOST", "127.0.0.1"))
    args = parser.parse_args()

    app = build_app()
    # service_running emits service.start + periodic service.heartbeat + service.stop
    with service_running("coupler", port=args.port):
        asyncio.run(app.run_http_async(transport="sse", host=args.host, port=args.port))


if __name__ == "__main__":
    main()
'''


#: The git blob sha1 and byte length ticket #385 records for the module above, under CANONICAL
#: SOURCE. Check [0] recomputes both from `ORIGINAL_SOURCE`.
ORIGINAL_BLOB_SHA1 = "257bf1163cd84c3cdd1fe82da9c7ce2c8b323e0a"
ORIGINAL_SIZE = 13835


def _git_blob_sha1(data: bytes) -> str:
    """Hash `data` the way git hashes a blob: sha1 over `blob <len>\\0` + the bytes.

    This is git's object-id rule, so the digest is directly comparable to the blob sha1 the ticket
    records — no forge access required to check that the embedded copy is genuine.
    """
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# ─────────────────────────────── the equivalence tables ───────────────────────────────

#: The exemplars this rewrite must reproduce. Ticket #385 captured none — "no function in this
#: module is minable", because criteria_miner "refuses anything that mentions a world-touching or
#: non-deterministic name, plus methods and no-arg functions", which between them exclude all six
#: — so this table is the hand-written equivalence basis the ticket asks for in its place.
#:
#: Each entry is (label, what is staged, the property it pins down). Every one is RUN against the
#: ORIGINAL and against this rewrite by `selftest` check [2] and the observations compared, so the
#: expected values are taken from the original as it runs rather than from this table.
EXEMPLARS = [
    ("_env_port: the variable is unset",
     "$COUPLER_PORT absent from the environment",
     "returns the `default` argument unchanged, and returns an int"),
    ("_env_port: a plain integer",
     "$COUPLER_PORT='8080'",
     "returns 8080 — the ordinary case the k8s handling must not disturb"),
    ("_env_port: a k8s service-link URL",
     "$COUPLER_PORT='tcp://10.43.0.1:8000'",
     "returns 8000 — the URL's trailing port, which is the whole reason this function exists"),
    ("_env_port: an unparseable value",
     "$COUPLER_PORT='tcp://host' (no trailing number)",
     "returns the default rather than raising ValueError"),
    ("_load_build: no build.json",
     "JAZZ_ROOT points at a directory with no conf/env/build.json",
     "returns {} — not None, not a raise"),
    ("_load_build: a real build.json",
     "JAZZ_ROOT/conf/env/build.json holds {'version': '1.2.3'}",
     "returns that document parsed"),
    ("_disabled_services: the env var",
     "$COUPLER_DISABLE='z3,notes', no build.json",
     "returns {'z3','notes'} as a set"),
    ("_disabled_services: build.json's disabled list",
     "build.json holds {'coupler': {'disabled': ['z3']}}",
     "returns {'z3'}"),
    ("_disabled_services: build.json's false-valued key",
     "build.json holds {'coupler': {'z3': false}}",
     "returns {'z3'} — the second spelling the docstring documents"),
    ("_disabled_services: nothing disabled",
     "no env var, no build.json",
     "returns an empty set — the default is everything enabled"),
    ("_notes_python: no override",
     "$COUPLER_PYTHON absent",
     "returns sys.executable — the same venv the server runs under"),
    ("_notes_python: an override",
     "$COUPLER_PYTHON='/x/py'",
     "returns '/x/py'"),
    ("build_app: the whole construction",
     "in-memory stand-ins for fastmcp, httpx and starlette",
     "the same FastMCP name, the same /health route and payload, the same telemetry events, the "
     "same mounts in the same order, the same tools with the same descriptions, and the same "
     "four banner lines on stderr — compared call for call against the original"),
]

#: Edge cases the exemplars cannot reach on their own. #385 asks for "the edge cases you add for
#: what sampling cannot reach", and these are they: each pins down a property the exemplars leave
#: free, which a wrong rewrite could violate while still reproducing every one of them. Every one
#: is likewise run differentially against the ORIGINAL.
#:
#: Each entry is (label, why the exemplars cannot reach it).
EDGE_CASES = [
    ("_env_port: '8000:9000' yields 9000, the TRAILING field — not 8000, not the default",
     "exemplar 3 only shows a tcp:// URL, where taking the last field looks like URL parsing; "
     "this is the case that reveals it is a blind rsplit, and a 'smarter' rewrite would differ"),
    ("_env_port: ':8000' yields 8000",
     "no exemplar has an empty leading field; int(':8000') fails but the tail parses"),
    ("_env_port: '' yields the default",
     "exemplar 1 covers ABSENT, not EMPTY — a different branch entirely (rsplit of '' is [''])"),
    ("_env_port: '  8000  ' yields 8000 and '+8000' yields 8000",
     "int() tolerates whitespace and a sign; a rewrite validating with .isdigit() would reject "
     "both and no exemplar would notice"),
    ("_env_port: '1_000' yields 1000",
     "int() accepts PEP 515 underscores; .isdigit() and a regex would both refuse"),
    ("_env_port: '-1' yields -1 — a negative port is accepted, not rejected",
     "no exemplar tests a value that is a valid int but an invalid port; the original does not "
     "range-check and a rewrite that did would be wrong"),
    ("_env_port: a non-ASCII decimal digit ('٨') yields 8",
     "int() accepts any Unicode decimal digit; str.isdigit()-based parsing diverges here and "
     "nowhere else"),
    ("_env_port: '0x1f' and 'tcp://10.43.0.1:80.5' yield the default",
     "the exemplars' failure case has no trailing digits at all; these have trailing text that "
     "ALMOST parses, which is where a float() or an int(x, 0) rewrite would diverge"),
    ("_load_build: build.json is invalid JSON -> JSONDecodeError propagates",
     "no exemplar has a corrupt file; the original catches nothing and a rewrite that returned "
     "{} on a parse error would look more robust and be wrong"),
    ("_load_build: JAZZ_ROOT is read at CALL time, not captured at import",
     "the exemplars never rebind it; callers and tests do, and a rewrite that froze it into a "
     "closure would reproduce every exemplar and break them"),
    ("_disabled_services: {'coupler': {'z3': 0}} does NOT disable z3",
     "exemplar 9 uses `false`; `0 is False` is False, so a rewrite testing `not v` would "
     "reproduce exemplar 9 exactly and still be wrong here"),
    ("_disabled_services: {'disabled': 'z3'} disables {'z','3'}, character by character",
     "exemplar 8 passes a list; set() of a string iterates it, and a rewrite that special-cased "
     "a string would be 'better' and would not be the original"),
    ("_disabled_services: {'coupler': null} yields an empty set rather than raising",
     "no exemplar has a null section; `.get(k, {})` returns None here and only the `or {}` saves "
     "it — a rewrite dropping the `or {}` would pass every exemplar and crash on this"),
    ("_disabled_services: {'disabled': false} raises TypeError",
     "the original does not guard set(False); a rewrite that did would be more robust and would "
     "not be behavior-preserving"),
    ("_disabled_services: env and build.json are MERGED, not one-or-the-other",
     "exemplars 7-9 exercise one source at a time, so a rewrite returning early on a non-empty "
     "env var would reproduce all three"),
    ("_disabled_services: a non-bool build value ({'version': '1.0'}) disables nothing",
     "no exemplar puts an ordinary setting beside the flags; a rewrite collecting every key "
     "would disable 'version'"),
    ("build_app: a service that fails to mount is recorded 'down' and the loop CONTINUES",
     "the exemplar's stand-in mounts everything; nothing else reaches the except branch, where a "
     "rewrite might abort the whole build"),
    ("build_app: a disabled service is 'off', is never mounted, and still emits a mount event",
     "the exemplar has nothing disabled; 'off' vs 'down' vs absent is invisible to it"),
    ("build_app: with no why5 module, the five why5 tools are NOT registered and stderr carries "
     "`  [warn] why5: No module named 'coupler.why5'`",
     "the exemplar cannot distinguish 'why5 absent' from 'why5 silently skipped'; the warning "
     "text is the only observable, and it is what actually happens in this package"),
    ("build_app: with a why5 module present, all five tools ARE registered, with their "
     "descriptions, and stderr carries `  mounted      : why5`",
     "nothing else exercises that branch at all — it is dead code in this package, so only an "
     "injected stand-in can compare it against the original"),
    ("build_app: a why5 module lacking `from_ci_failure` fails as an ImportError naming it, not "
     "an AttributeError",
     "`from x import y` and getattr fail with different text, and the text reaches stderr; only "
     "a stand-in exporting one name of the two can tell them apart"),
    ("build_app: every tool is registered WITH its description",
     "fastmcp reads __doc__ at registration, so a rewrite assigning it after the decorator "
     "registers a description-less tool — the exact defect #357's selftest caught in bridge.py"),
    ("build_app: the /health payload's four fields, in the original's ORDER",
     "no exemplar reads the route; JSON object order is observable to a probe, and a rewrite "
     "building the dict from a config mapping would reorder it"),
    ("build_app: the banner prints the LIVE PORT, and the ui line says 'port 8142' literally",
     "the ui line's 8142 is baked into the text even when $JSON_CONTROLS_URL points elsewhere; "
     "a rewrite that interpolated the real port would print what the original never printed"),
    ("coupler_status: reports ok/down/off per service, probes the UI, and appends coupler + "
     "jazz_version",
     "the exemplar builds the app but never calls its tools; the whole re-probe path is unseen"),
    ("coupler_status: a UI answering >= 500 is 'degraded', < 500 is 'ok', unreachable is 'down'",
     "three branches on one comparison, none reached by any exemplar"),
    ("ui_set_value: 'true'/'false' parse to bools, then int, then float, else the raw string",
     "no exemplar calls it; the ladder's ORDER is observable ('1' must be int 1, not float 1.0)"),
    ("ui_set_value: 'inf' and 'nan' become floats, not strings",
     "float() accepts both; a rewrite rejecting non-finite values would differ, and no exemplar "
     "would see it"),
    ("ui_set_page: a config with no 'name' is refused before any HTTP call",
     "the exemplar never calls it; a rewrite that posted first would hit the network for nothing"),
    ("the UI tools return `error: <e>` rather than raising, for every failure",
     "the exemplar never calls them; every one of the six swallows its exception and a rewrite "
     "that let one propagate would break the MCP session"),
    ("importing the module INSERTS the telemetry path at sys.path[0]",
     "the exemplars all run post-import; this is a side effect of import itself, and it is the "
     "original's — a rewrite that tidied it away would change what importing does"),
    ("main(): --port defaults to PORT, --host to $COUPLER_HOST, and run_http_async gets "
     "transport='sse'",
     "no exemplar calls main(); its argument wiring is where the configured values actually "
     "reach the server"),
]


#: What the differential CANNOT distinguish, established by mutation-testing this selftest — each
#: entry is a change to this module that the checks below do not catch, together with the reason
#: it is not a defect. Recorded because "17 of 18 mutations caught" invites the question "what was
#: the 18th", and the honest answer is better than a silent gap.
#:
#: The harness was mutation-tested by breaking this module 18 ways and requiring a FAIL from each.
#: Three real holes surfaced that way and were fixed (a corrupt build.json was poisoning the
#: build_app fixture, so an aborting mount loop, a wrong UI threshold and a wrong why5 exception
#: type all survived undetected — see `_canary`). The entry below is the one survivor, and it
#: survives because it is not a defect: it is an EQUIVALENT MUTANT.
EQUIVALENT_MUTANTS = [
    ("_env_port validates with `raw.isdigit()` before `int(raw)`",
     "Provably equivalent, so no check can or should catch it. Whenever `int(raw)` would have "
     "succeeded but `isdigit()` is False — ' 8000 ', '+8000', '1_000', '-1' — the guard falls "
     "through to the tail path, and `raw.rsplit(':', 1)[-1]` on a value with no colon IS `raw`, "
     "which is then parsed by `int()` anyway and yields the same number. `int(raw)` can never "
     "succeed when `raw` contains a colon, so the two forms cannot diverge on any input."),
]


# ─────────────────────────────── the differential harness ───────────────────────────────

class _Recorder:
    """Recording stand-ins for fastmcp, httpx and starlette — the world `build_app` touches.

    Injected into `sys.modules` so they satisfy the ORIGINAL's module-scope imports and this
    module's lazy `_load_deps()` identically, which is what makes the comparison fair rather than
    staged. Every call made against them is recorded, so "the rewrite drives fastmcp the way the
    original does" becomes a comparison of two lists rather than an assertion.

    `ui_status` and `ui_raises` stage what the UI probe answers, so `coupler_status`'s three
    branches can be reached without a socket.
    """

    def __init__(self, mount_fails=(), ui_status=200, ui_raises=False, probe_fails=()):
        self.calls = []
        self.tools = {}
        self.routes = []
        self.mount_fails = set(mount_fails)
        self.ui_status = ui_status
        self.ui_raises = ui_raises
        self.probe_fails = set(probe_fails)

    # ── the fake modules ──
    def modules(self):
        rec = self

        class FastMCP:
            def __init__(self, name):
                self.name = name
                rec.calls.append(("FastMCP(name)", name))

            def custom_route(self, path, methods):
                def deco(fn):
                    rec.calls.append(("custom_route", path, tuple(methods), fn.__name__))
                    rec.routes.append((path, tuple(methods), fn))
                    return fn
                return deco

            def tool(self):
                def deco(fn):
                    # __doc__ is read HERE, exactly as fastmcp reads it at registration — which is
                    # what makes a description assigned after the decorator invisible.
                    rec.calls.append(("tool", fn.__name__, fn.__doc__))
                    rec.tools[fn.__name__] = fn
                    return fn
                return deco

            def mount(self, proxy, namespace=None):
                if namespace in rec.mount_fails:
                    raise RuntimeError("mount refused for %s" % namespace)
                rec.calls.append(("mount", namespace, proxy))

            async def run_http_async(self, **kw):
                rec.calls.append(("run_http_async", tuple(sorted(kw.items()))))

        class Client:
            def __init__(self, transport):
                self.transport = transport
                rec.calls.append(("Client(transport)", transport))

            async def __aenter__(self):
                name = self.transport[2][1] if len(self.transport[2]) > 1 else None
                if name in rec.probe_fails:
                    raise RuntimeError("probe refused for %s" % name)
                return self

            async def __aexit__(self, *a):
                return False

            async def list_tools(self):
                rec.calls.append(("list_tools", self.transport))
                return []

        def StdioTransport(command=None, args=None, env=None):
            # `env is os.environ` would be a bug (the original copies), so the copy is recorded as
            # a fact rather than the whole environment, which is not comparable across runs.
            return ("stdio", command, tuple(args or ()),
                    ("env==os.environ", env == dict(os.environ)))

        def create_proxy(client):
            rec.calls.append(("create_proxy", client.transport))
            return ("proxy", client.transport)

        class JSONResponse:
            def __init__(self, payload):
                # tuple(payload.items()) — the ORDER of the /health fields is observable to a
                # probe, so it is compared, not just the mapping.
                self.payload = tuple(payload.items())

        class _Response:
            def __init__(self, status):
                self.status_code = status

        class _AsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, timeout=None):
                rec.calls.append(("httpx.AsyncClient.get", url, timeout))
                if rec.ui_raises:
                    raise ConnectionError("ui unreachable")
                return _Response(rec.ui_status)

        fastmcp = types.ModuleType("fastmcp")
        fastmcp.FastMCP = FastMCP
        fastmcp.Client = Client
        client_mod = types.ModuleType("fastmcp.client")
        transports = types.ModuleType("fastmcp.client.transports")
        transports.StdioTransport = StdioTransport
        server_mod = types.ModuleType("fastmcp.server")
        server_mod.create_proxy = create_proxy
        fastmcp.client = client_mod
        client_mod.transports = transports
        fastmcp.server = server_mod

        httpx = types.ModuleType("httpx")
        httpx.AsyncClient = _AsyncClient
        httpx.get = lambda url, params=None, timeout=None: _UIStub(rec, "GET", url, params, None)
        httpx.post = lambda url, json=None, timeout=None: _UIStub(rec, "POST", url, None, json)
        httpx.put = lambda url, json=None, timeout=None: _UIStub(rec, "PUT", url, None, json)

        starlette = types.ModuleType("starlette")
        responses = types.ModuleType("starlette.responses")
        responses.JSONResponse = JSONResponse
        starlette.responses = responses

        return {"fastmcp": fastmcp, "fastmcp.client": client_mod,
                "fastmcp.client.transports": transports, "fastmcp.server": server_mod,
                "httpx": httpx, "starlette": starlette, "starlette.responses": responses}

    def install(self):
        """Put the stand-ins into sys.modules; return the modules they displaced."""
        fakes = self.modules()
        saved = {name: sys.modules.get(name) for name in _FAKE_MODULES}
        for name, module in fakes.items():
            sys.modules[name] = module
        return saved

    @staticmethod
    def restore(saved):
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


#: Every module name `_Recorder` displaces, so restoring is exact and nothing is left behind.
_FAKE_MODULES = ("fastmcp", "fastmcp.client", "fastmcp.client.transports", "fastmcp.server",
                 "httpx", "starlette", "starlette.responses")


class _UIStub:
    """The object httpx's sync verbs return: records the call, then answers `raise_for_status`.

    `ui_http_raises` on the recorder decides whether `raise_for_status` raises and `ui_payload`
    what `.json()` yields, so the six UI tools' success and failure paths are both reachable
    without a socket.

    The params and body are recorded as `repr` STRINGS rather than as the objects themselves, and
    that is not cosmetic. `ui_set_value` sends whatever its parse ladder produced, and one of the
    values that ladder produces is `float('nan')` — which is not equal to itself. A recorded
    `{'value': nan}` therefore compares UNEQUAL to an identical `{'value': nan}`, and the
    differential reports a difference where the two modules did exactly the same thing. That is a
    false FAILURE, the mirror image of the false pass a sloppy normalizer gives, and it was
    observed here before this line existed. `repr` fixes it without weakening anything: it
    separates `True` from `1`, `42` from `42.0`, and `nan` from `'nan'`, so every distinction the
    ladder can make is still visible — only self-inequality is removed.
    """

    def __init__(self, rec, verb, url, params, body):
        self.rec = rec
        rec.calls.append(("httpx." + verb.lower(), url, repr(params), repr(body)))

    def raise_for_status(self):
        if getattr(self.rec, "ui_http_raises", False):
            raise RuntimeError("400 Bad Request")

    def json(self):
        return getattr(self.rec, "ui_payload", {"ok": True})


def load_original(env=None):
    """Execute `ORIGINAL_SOURCE` and return it as a live module — the differential's oracle.

    The original imports httpx and fastmcp at module scope, so stand-ins are installed for the
    duration of the exec; that is the ONLY accommodation made, and it changes nothing about the
    logic under test. Nothing is written to disk: the source is compiled from the embedded string.

    The original ALSO does `sys.path.insert(0, ...)` at module scope. That insert is undone here
    afterwards — not to hide it (check [5] measures the insert this module performs at ITS import,
    which is the one that counts) but so that exec'ing the oracle a dozen times during a selftest
    does not grow `sys.path` by a dozen entries.

    Args:
        env: environment variables to stage for the duration of the exec, as a mapping; a value
            of None removes the variable. The original reads $JAZZ_ROOT, $JAZZ_DEV and
            $COUPLER_PORT at import, so this is the only way to observe those bindings.
    """
    recorder = _Recorder()
    saved_modules = recorder.install()
    path_before = list(sys.path)
    with _staged_env(env or {}):
        try:
            module = types.ModuleType("original_server")
            module.__file__ = "<ORIGINAL_SOURCE embedded in %s>" % DOTTED_NAME
            exec(compile(ORIGINAL_SOURCE, module.__file__, "exec"), module.__dict__)
            return module
        finally:
            sys.path[:] = path_before
            _Recorder.restore(saved_modules)


@_cm
def _staged_env(values):
    """Set each name in `values` for the duration of the block, then put the environment back.

    A value of None means "make sure this variable is ABSENT", which is a distinct state from
    empty and one several edge cases turn on.
    """
    saved = {name: os.environ.get(name) for name in values}
    try:
        for name, value in values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


#: The names the ORIGINAL bound at module scope from its third-party imports, and where each
#: comes from. `(attribute, module, name-in-that-module or None to bind the module itself)`.
#:
#: This module binds NONE of them at module scope — `_load_deps()` reads `sys.modules` afresh on
#: every `build_app()` — so `_bind_deps` finds nothing to rebind here and adds nothing. Only names
#: a module ALREADY has are touched, so the two are driven through their own real import paths and
#: neither is given a shortcut the other lacks.
_DEP_NAMES = (
    ("httpx", "httpx", None),
    ("FastMCP", "fastmcp", "FastMCP"),
    ("Client", "fastmcp", "Client"),
    ("StdioTransport", "fastmcp.client.transports", "StdioTransport"),
    ("create_proxy", "fastmcp.server", "create_proxy"),
)


def _bind_deps(module):
    """Point `module` at the stand-ins currently in `sys.modules`; return what was there before.

    This is what makes the build_app differential fair, and it is worth being precise about
    because it is the one place the two modules genuinely differ in structure.

    The ORIGINAL imports its dependencies at MODULE scope, so `httpx`, `FastMCP`, `Client`,
    `StdioTransport` and `create_proxy` were bound into its namespace once, when `load_original()`
    exec'd it — and they still refer to whatever recorder was installed at that moment.
    Installing a fresh recorder in `sys.modules` afterwards would not reach them, so the original
    would drive the stale one and record nothing. Rebinding the five names is how a module-scope
    importer is pointed at a new stand-in; it is the exact analogue of this module's
    `_load_deps()` reading `sys.modules` afresh on every call.
    """
    saved = {}
    for attr, source, name in _DEP_NAMES:
        if hasattr(module, attr):
            saved[attr] = getattr(module, attr)
            setattr(module, attr, sys.modules[source] if name is None
                    else getattr(sys.modules[source], name))
    return saved


def _restore_attrs(module, saved):
    for name, value in saved.items():
        setattr(module, name, value)


def _write_build(root, doc):
    """Stage `<root>/conf/env/build.json` as `doc`, and return `root` as a Path.

    `doc` of None means "there is NO build.json" — and the file is REMOVED to make that true,
    rather than merely not written. That distinction is not pedantic: the scenarios reuse one
    temporary directory, so a leftover build.json from the previous case would silently answer
    for the next one, and a case labelled "nothing disabled" would quietly measure the last case's
    document. The differential would still pass — both modules read the same stale file — while
    the label on it lied. Removing it is what makes each case mean what it says.

    `doc` may be a str, which is written raw — that is how the invalid-JSON edge case is staged.
    Writes only under the caller's temporary directory, never in this package.
    """
    path = Path(root) / "conf/env/build.json"
    if doc is None:
        if path.exists():
            path.unlink()
        return Path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc if isinstance(doc, str) else json.dumps(doc))
    return Path(root)


def _call(fn, *args, **kwargs):
    """Call `fn` and return `("ok", value)` or `("raised", "Type: message")`.

    The raise IS part of the observation for several edge cases (a corrupt build.json, a
    non-iterable `disabled`), so it is captured as a comparable value rather than propagated.
    `BaseException` is caught because one edge case is specifically about what does NOT get
    swallowed.
    """
    try:
        return ("ok", fn(*args, **kwargs))
    except BaseException as exc:  # noqa: BLE001 — the raise IS the observation
        return ("raised", "%s: %s" % (type(exc).__name__, exc))


def observe_env_port(module, value, default=7770):
    """Run `module._env_port` with $COUPLER_PORT staged to `value` (None = absent)."""
    with _staged_env({"COUPLER_PORT_PROBE": value}):
        return _call(module._env_port, "COUPLER_PORT_PROBE", default)


def observe_load_build(module, doc, root):
    """Run `module._load_build` with JAZZ_ROOT rebound to `root` (`doc` None = no build.json)."""
    saved = module.JAZZ_ROOT
    try:
        module.JAZZ_ROOT = _write_build(root, doc)
        return _call(module._load_build)
    finally:
        module.JAZZ_ROOT = saved


def observe_disabled(module, doc, root, env=None):
    """Run `module._disabled_services` with build.json and $COUPLER_DISABLE staged."""
    saved = module.JAZZ_ROOT
    try:
        module.JAZZ_ROOT = _write_build(root, doc)
        with _staged_env({"COUPLER_DISABLE": env}):
            kind, value = _call(module._disabled_services)
            # A set's repr order is not stable across processes; sort it so the comparison is
            # about membership, which is what the function promises.
            return (kind, sorted(value)) if kind == "ok" else (kind, value)
    finally:
        module.JAZZ_ROOT = saved


def observe_notes_python(module, value):
    """Run `module._notes_python` with $COUPLER_PYTHON staged to `value` (None = absent)."""
    with _staged_env({"COUPLER_PYTHON": value}):
        return _call(module._notes_python)


def observe_build_app(module, recorder=None, jazz_root=None, env=None, why5=None, drive=None):
    """Build the app under recording stand-ins and record everything it did.

    Stages the SAME conditions for either module — the original or this rewrite — which is what
    makes the comparison a proof rather than a demonstration. Every stand-in is installed before
    the call and removed in a `finally`, so nothing here opens a socket, spawns a process or
    outlives the call.

    Args:
        module: the module under observation; its globals are rebound for the run.
        recorder: a `_Recorder` staging the outcomes (mount failures, UI status); a default one
            is made if omitted.
        jazz_root: a directory to rebind JAZZ_ROOT to, for build.json-driven behavior.
        env: environment to stage for the duration.
        why5: a module object to install as `coupler.why5`, or None to leave it absent (which is
            the real state of this package).
        drive: an optional `(module, app, recorder) -> extra` callable, run while the stand-ins
            are still installed, for exercising the registered tools.

    Returns:
        A `(calls, stderr, extra, raised)` tuple — every field comparable between the two modules.
    """
    recorder = recorder or _Recorder()
    saved_modules = recorder.install()
    saved_deps = None
    saved_root = getattr(module, "JAZZ_ROOT", None)
    saved_why5 = sys.modules.get("coupler.why5")
    real_stderr = sys.stderr
    captured = io.StringIO()
    extra, raised = None, None
    try:
        saved_deps = _bind_deps(module)
        if jazz_root is not None:
            module.JAZZ_ROOT = Path(jazz_root)
        if why5 is not None:
            sys.modules["coupler.why5"] = why5
        else:
            sys.modules.pop("coupler.why5", None)
        sys.stderr = captured
        with _staged_env(env or {}):
            try:
                app = module.build_app()
                if drive is not None:
                    extra = drive(module, app, recorder)
            except BaseException as exc:  # noqa: BLE001 — the raise IS the observation
                raised = "%s: %s" % (type(exc).__name__, exc)
    finally:
        sys.stderr = real_stderr
        if saved_deps:
            _restore_attrs(module, saved_deps)
        if saved_root is not None:
            module.JAZZ_ROOT = saved_root
        if saved_why5 is None:
            sys.modules.pop("coupler.why5", None)
        else:
            sys.modules["coupler.why5"] = saved_why5
        _Recorder.restore(saved_modules)
    return (tuple(recorder.calls), captured.getvalue(), extra, raised)


def observe_main(module, argv, env=None):
    """Run `module.main()` with `sys.argv` staged, under recording stand-ins.

    `main()` takes no arguments and reads `sys.argv` — that is the surface ticket #385 fixes — so
    staging `sys.argv` is the only way to drive it, and it is how `cli()` drives it too.
    """
    recorder = _Recorder()
    saved_modules = recorder.install()
    saved_deps = None
    saved_argv = sys.argv
    real_stderr = sys.stderr
    captured = io.StringIO()
    raised = None
    try:
        saved_deps = _bind_deps(module)
        sys.argv = ["coupler.server"] + list(argv)
        sys.stderr = captured
        sys.modules.pop("coupler.why5", None)
        with _staged_env(env or {}):
            try:
                module.main()
            except BaseException as exc:  # noqa: BLE001 — a SystemExit from argparse is an
                # observation too: `--port zzz` must fail the same way in both modules.
                raised = "%s: %s" % (type(exc).__name__, exc)
    finally:
        sys.argv = saved_argv
        sys.stderr = real_stderr
        if saved_deps:
            _restore_attrs(module, saved_deps)
        _Recorder.restore(saved_modules)
    # Only the run_http_async call matters here; the rest is build_app's, already compared.
    served = tuple(c for c in recorder.calls if c[0] == "run_http_async")
    return (served, raised)


def _fake_why5(with_names=True):
    """A stand-in `coupler.why5`, so the why5 branch — dead code in this package — is comparable.

    With `with_names=False` it exports `Why5` but NOT `from_ci_failure`, which is what
    distinguishes the original's `from ... import ...` (an ImportError naming the missing name)
    from a naive getattr rewrite (an AttributeError). The text reaches stderr, so the difference
    is observable.
    """
    module = types.ModuleType("coupler.why5")
    module.__file__ = "<fake coupler.why5>"

    class Why5:
        def __init__(self, session_id=None, trigger=None):
            self.session_id, self.trigger, self.facts, self.links = session_id, trigger, [], []

        def fact(self, name, value):
            self.facts.append((name, value))

        def link(self, label, cause=None, because=None):
            self.links.append((label, cause, because))

        def check(self):
            return {"ok": True, "facts": self.facts, "links": self.links}

        def save(self):
            self.saved = True

    module.Why5 = Why5
    if with_names:
        def from_ci_failure(session_id, branch=None, pre_sha=None, pytest_output=None):
            w = Why5(session_id=session_id, trigger=branch)
            w.link("ci", cause=pre_sha, because=pytest_output)
            return w
        module.from_ci_failure = from_ci_failure
    return module


def _drive_tools(module, app, recorder):
    """Call every registered tool and return what each answered — the tools' real behavior.

    `build_app` only REGISTERS the tools; nothing in the exemplars calls them, so without this the
    whole of `coupler_status` and the six UI tools would be unmeasured. Runs under the same
    stand-ins the build ran under.
    """
    import asyncio

    out = []
    for name in sorted(recorder.tools):
        fn = recorder.tools[name]
        args = _TOOL_ARGS.get(name, ())
        try:
            result = fn(*args)
            if asyncio.iscoroutine(result):
                result = asyncio.run(result)
            out.append((name, result))
        except BaseException as exc:  # noqa: BLE001 — a raising tool IS the observation
            out.append((name, "RAISED %s: %s" % (type(exc).__name__, exc)))
    # the /health route, which is not a tool
    for path, methods, fn in recorder.routes:
        result = fn(None)
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)
        out.append(("route " + path, tuple(methods), getattr(result, "payload", result)))
    return tuple(out)


#: Arguments for each tool `_drive_tools` calls. Chosen to reach the interesting branch of each:
#: `ui_set_value` gets a value that must climb the whole parse ladder, `ui_set_page` a config
#: WITHOUT a name (the guard), and the why5 tools a coherent little session.
_TOOL_ARGS = {
    "coupler_status": (),
    "ui_set_page": ({"title": "no name here"},),
    "ui_get_state": ("home",),
    "ui_set_value": ("home", "volume", "42"),
    "ui_list_pages": (),
    "ui_add_message": ("home", "chat", "user", "hi"),
    "ui_get_log": (),
    "why5_new": ("s1", "ci failed"),
    "why5_fact": ("s1", "tests_green", False),
    "why5_link": ("s1", "L1", "build broke", "tests red"),
    "why5_check": ("s1",),
    "why5_from_ci_failure": ("s2", "main", "abc123", "E   assert 1 == 2"),
}


# ─────────────────────────────── the selftest ───────────────────────────────

def selftest(stream=None):
    """Prove this rewrite against ticket #385's acceptance items (a), (b) and (d).

    Runs every scenario against the EMBEDDED ORIGINAL and against this module, under identically
    staged conditions, and compares the observations field by field. Builds its own config objects
    and build.json files inside a temporary directory, writes nothing into this package, opens no
    sockets, spawns no MCP subprocess, and leaves no configuration behind. Returns the number of
    failures.

    Checks, in order:
      0. the oracle is genuine — ORIGINAL_SOURCE hashes to the blob sha1 the ticket records;
      1. the config gate — this module throws ConfigError, and binds nothing, without a config;
      2. the exemplars — differential against the original;
      3. the edge cases the exemplars cannot reach — differential against the original;
      4. the callable surface — the names, parameters and annotations the ticket states;
      5. side effects — the sys.path insert is the original's, and every stand-in was removed;
      6. main() — differential against the original, argument wiring included;
      7. no files — this package's tree is unchanged by the whole run;
      8. the console spelling — `python -m coupler.server [--port N]` still runs the server.
    """
    import tempfile

    out = stream or sys.stdout
    failures = []
    checks = [0]

    def check(ok, label):
        checks[0] += 1
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    def compare(label, mine, theirs):
        """The differential itself: one scenario, both modules, field-by-field equality."""
        check(mine == theirs,
              "%s\n         original: %r\n         rewrite : %r" % (label, theirs, mine)
              if mine != theirs else "%s [%s]" % (label, _brief(theirs)))

    tree_before = _tree_snapshot()
    me = sys.modules[__name__]

    print("differential selftest for %s\n  oracle: the ORIGINAL, embedded (%d bytes) and "
          "executed\n  config: %s" % (UNIT, len(ORIGINAL_SOURCE.encode("utf-8")),
                                      _describe_source()), file=out)

    # ── 0. the oracle is genuine ──────────────────────────────────────────────
    print("\n[0] the embedded original is the forge's blob", file=out)
    raw = ORIGINAL_SOURCE.encode("utf-8")
    digest = _git_blob_sha1(raw)
    check(len(raw) == ORIGINAL_SIZE,
          "ORIGINAL_SOURCE is %d bytes, the size ticket #385 records (%d)"
          % (len(raw), ORIGINAL_SIZE))
    check(digest == ORIGINAL_BLOB_SHA1,
          "ORIGINAL_SOURCE hashes to the git blob sha1 ticket #385 records\n"
          "         computed: %s\n         ticket  : %s" % (digest, ORIGINAL_BLOB_SHA1))
    if digest != ORIGINAL_BLOB_SHA1:
        print("\n  the oracle is not the forge's module — every check below would be "
              "meaningless.", file=out)
        return len(failures)

    original = load_original()

    try:
        # ── 1. the config gate ────────────────────────────────────────────────
        print("\n[1] config gate — this module throws when it cannot see its config", file=out)
        _selftest_gate(check, out)
        _selftest_template_matches_registry(check)

        # ── 2. the exemplars ──────────────────────────────────────────────────
        print("\n[2] exemplars — differential against the ORIGINAL", file=out)
        with tempfile.TemporaryDirectory() as tmp:
            for label, value in (("1: the variable is unset", None),
                                 ("2: a plain integer '8080'", "8080"),
                                 ("3: a k8s service-link URL 'tcp://10.43.0.1:8000'",
                                  "tcp://10.43.0.1:8000"),
                                 ("4: an unparseable 'tcp://host'", "tcp://host")):
                compare("exemplar %s -> _env_port" % label,
                        observe_env_port(me, value), observe_env_port(original, value))

            compare("exemplar 5: _load_build with no build.json",
                    observe_load_build(me, None, tmp), observe_load_build(original, None, tmp))
            compare("exemplar 6: _load_build with {'version': '1.2.3'}",
                    observe_load_build(me, {"version": "1.2.3"}, tmp),
                    observe_load_build(original, {"version": "1.2.3"}, tmp))

            compare("exemplar 7: _disabled_services from $COUPLER_DISABLE='z3,notes'",
                    observe_disabled(me, None, tmp, env="z3,notes"),
                    observe_disabled(original, None, tmp, env="z3,notes"))
            compare("exemplar 8: _disabled_services from {'coupler': {'disabled': ['z3']}}",
                    observe_disabled(me, {"coupler": {"disabled": ["z3"]}}, tmp),
                    observe_disabled(original, {"coupler": {"disabled": ["z3"]}}, tmp))
            compare("exemplar 9: _disabled_services from {'coupler': {'z3': false}}",
                    observe_disabled(me, {"coupler": {"z3": False}}, tmp),
                    observe_disabled(original, {"coupler": {"z3": False}}, tmp))
            compare("exemplar 10: _disabled_services with nothing disabled",
                    observe_disabled(me, None, tmp), observe_disabled(original, None, tmp))

            compare("exemplar 11: _notes_python with no override (is sys.executable)",
                    observe_notes_python(me, None), observe_notes_python(original, None))
            compare("exemplar 12: _notes_python with $COUPLER_PYTHON='/x/py'",
                    observe_notes_python(me, "/x/py"), observe_notes_python(original, "/x/py"))

            compare("exemplar 13: build_app — every call, in order, plus stderr",
                    observe_build_app(me, jazz_root=tmp),
                    observe_build_app(original, jazz_root=tmp))

        # ── 3. the edge cases ─────────────────────────────────────────────────
        print("\n[3] edge cases the exemplars cannot reach — differential", file=out)
        _selftest_edges(compare, check, out, me, original)

        # ── 4. the callable surface ───────────────────────────────────────────
        print("\n[4] callable surface — the ticket's, and the original's", file=out)
        _selftest_surface(check, me, original)

        # ── 5. side effects ───────────────────────────────────────────────────
        print("\n[5] side effects", file=out)
        _selftest_side_effects(check, original)

        # ── 6. main() ─────────────────────────────────────────────────────────
        print("\n[6] main() — differential under recording stand-ins", file=out)
        _selftest_main(compare, check, me, original)

        # ── 7. no files ───────────────────────────────────────────────────────
        print("\n[7] no files created, modified or deleted", file=out)
        tree_after = _tree_snapshot()
        check(tree_before == tree_after,
              "this package's tree is byte-identical after the whole run (%d files, ignoring "
              "__pycache__ which CPython writes for any import)%s"
              % (len(tree_after), "" if tree_before == tree_after
                 else "\n         changed: %r" % (_tree_diff(tree_before, tree_after),)))

        # ── 8. the console spelling ───────────────────────────────────────────
        print("\n[8] the original's invocation still runs the server", file=out)
        _selftest_argv(check)

    finally:
        reset_config()

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED", checks[0],
             len(failures)), file=out)
    for failure in failures:
        print("  failed: %s" % failure.splitlines()[0], file=out)
    return len(failures)


def _brief(value, limit=110):
    """Render an observation short enough to read on one line, without hiding a disagreement.

    Only ever used on values that ALREADY compared equal, so nothing a reader needs to diff is
    truncated — a mismatch is printed in full by `compare`.
    """
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "…(%d chars)" % len(text)


def _describe_source():
    try:
        return active_source()
    except ConfigError as exc:
        return "UNRESOLVED (%s)" % exc


def _package_root():
    """The directory holding `pyproject.toml` — the import path `coupler` resolves from."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _selftest_gate(check, out):
    """Check [1]: with an unresolvable config, importing this module throws ConfigError.

    Proven in a CHILD interpreter, because this module is already imported in this one and its
    globals are already bound — asking the live module to prove what it does at import would prove
    nothing. The child points `COUPLER_SERVER_CONFIG` at a file that does not exist: that source
    outranks the walk-up, so the gate is staged the same way whether or not a registry sits above
    this module — and this package SHIPS one, so a bare import would otherwise succeed and prove
    nothing.
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as isolated:
        env = dict(os.environ)
        env[CONFIG_ENV] = os.path.join(isolated, "no-such-config.json")
        env["PYTHONPATH"] = _package_root() + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run([sys.executable, "-c", "import %s" % DOTTED_NAME],
                              env=env, capture_output=True, text=True, cwd=isolated)
        check(proc.returncode != 0 and "ConfigError" in proc.stderr,
              "`import %s` with an unresolvable config raises ConfigError and does NOT guess a "
              "default (rc=%d, stderr tail: %r)"
              % (DOTTED_NAME, proc.returncode, proc.stderr.strip().splitlines()[-1:]))
        check("7770" not in proc.stderr.replace(env[CONFIG_ENV], ""),
              "the ConfigError names no port — the gate throws rather than falling back to the "
              "original's 7770")

        # And with a config, the same child import succeeds — so check [1] is measuring the gate,
        # not a module that cannot import at all.
        template = config_template()
        config_path = os.path.join(isolated, "config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(template, handle)
        env[CONFIG_ENV] = config_path
        proc = subprocess.run(
            [sys.executable, "-c",
             "import %s as s; print(s.PORT, s.JAZZ_SERVICES[1][0], len(s.JAZZ_SERVICES))"
             % DOTTED_NAME],
            env=env, capture_output=True, text=True, cwd=isolated)
        check(proc.returncode == 0 and proc.stdout.strip() == "7770 z3 7",
              "the SAME import succeeds against a config object, binding it rather than a default "
              "(rc=%d, stdout=%r, stderr=%r)"
              % (proc.returncode, proc.stdout.strip(), proc.stderr.strip()[-160:]))

        # A config object missing one key throws, naming the key — not a silent default.
        del template["default_port"]
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(template, handle)
        proc = subprocess.run([sys.executable, "-c", "import %s" % DOTTED_NAME],
                              env=env, capture_output=True, text=True, cwd=isolated)
        check(proc.returncode != 0 and "ConfigError" in proc.stderr
              and "'default_port'" in proc.stderr,
              "a config object missing one key throws ConfigError NAMING that key rather than "
              "defaulting it (rc=%d)" % proc.returncode)

        # A nested key is required just as strictly as a top-level one.
        template = config_template()
        del template["ui"]["probe_timeout_seconds"]
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(template, handle)
        proc = subprocess.run([sys.executable, "-c", "import %s" % DOTTED_NAME],
                              env=env, capture_output=True, text=True, cwd=isolated)
        check(proc.returncode != 0 and "probe_timeout_seconds" in proc.stderr
              and "ui" in proc.stderr,
              "a NESTED config key is required too, and the error names its section (rc=%d)"
              % proc.returncode)


def _strip_prose(node):
    """Drop the keys that are documentation or package-wide, leaving the settings themselves.

    `_comment` is prose for a human reading the registry, and `bug_reports` is inherited from the
    registry's top level rather than stated by this unit's section; neither is a setting this unit
    reads, so neither belongs in a comparison of settings.
    """
    if isinstance(node, list):
        return [_strip_prose(item) for item in node]
    if not isinstance(node, dict):
        return node
    return {key: _strip_prose(value) for key, value in node.items()
            if key not in ("_comment", "bug_reports")}


def _selftest_template_matches_registry(check):
    """The template `emit-config` prints must equal the config this package actually ships.

    `emit-config` tells an operator "this is the config object to install", so if it drifted from
    the section in `registry.json`, the module would be handing out a config that is not the one
    it was proven against — and every check that measures the shipped values would still pass
    while the printed advice quietly went wrong. Comparing them is what keeps the two from
    parting.
    """
    shipped, _base, _source = load_config()
    same = _strip_prose(shipped) == _strip_prose(config_template())
    check(same,
          "the config object `emit-config` prints is exactly the one this package ships in %s — "
          "the template cannot drift from the config the checks above measure%s"
          % (REGISTRY_NAME,
             "" if same else "\n         shipped : %r\n         template: %r"
                             % (_strip_prose(shipped), _strip_prose(config_template()))))


def _selftest_edges(compare, check, out, me, original):
    """Check [3]: every entry in `EDGE_CASES`, run against the ORIGINAL and compared.

    These are the properties the exemplars leave free — each one a place a plausible rewrite could
    diverge while still reproducing every exemplar. The expected value is never written down here:
    it is whatever the original does.
    """
    import tempfile

    # ── _env_port: the parsing ladder ──
    for label, value in (
        ("'8000:9000' -> the TRAILING field, not the first and not the default", "8000:9000"),
        ("':8000' -> 8000", ":8000"),
        ("'' (empty, not absent) -> the default", ""),
        ("'  8000  ' -> 8000 (int() tolerates whitespace)", "  8000  "),
        ("'+8000' -> 8000 (int() tolerates a sign)", "+8000"),
        ("'1_000' -> 1000 (int() accepts PEP 515 underscores)", "1_000"),
        ("'-1' -> -1 (a negative port is accepted, not rejected)", "-1"),
        ("'٨' -> 8 (int() accepts any Unicode decimal digit)", "٨"),
        ("'0x1f' -> the default (int() is base 10)", "0x1f"),
        ("'tcp://10.43.0.1:80.5' -> the default (the tail is not an int)",
         "tcp://10.43.0.1:80.5"),
        ("'a:b:8000' -> 8000 (rsplit takes the last field of anything)", "a:b:8000"),
        ("'true' -> the default", "true"),
    ):
        compare("_env_port %s" % label,
                observe_env_port(me, value), observe_env_port(original, value))

    check(observe_env_port(me, None, default=1234)[1] == 1234,
          "_env_port returns the `default` ARGUMENT, not the configured port — passing 1234 "
          "yields 1234, so the function is not secretly reading PORT")

    with tempfile.TemporaryDirectory() as tmp:
        # ── _load_build: the unguarded paths ──
        compare("_load_build: invalid JSON raises rather than returning {}",
                observe_load_build(me, "{not json", tmp),
                observe_load_build(original, "{not json", tmp))
        compare("_load_build: a JSON array is returned AS IS (the -> dict annotation is not "
                "enforced)",
                observe_load_build(me, [1, 2], tmp), observe_load_build(original, [1, 2], tmp))

        # JAZZ_ROOT is read at CALL time — the whole point of keeping it a module global.
        compare("_load_build: JAZZ_ROOT is read at CALL time, so rebinding the module global "
                "takes effect on the next call",
                observe_load_build(me, {"version": "call-time"}, tmp),
                observe_load_build(original, {"version": "call-time"}, tmp))

        # ── _disabled_services: the set algebra ──
        for label, doc, env in (
            ("{'z3': 0} does NOT disable z3 (`v is False`, not falsiness)",
             {"coupler": {"z3": 0}}, None),
            ("{'z3': ''} does NOT disable z3", {"coupler": {"z3": ""}}, None),
            ("{'z3': null} does NOT disable z3", {"coupler": {"z3": None}}, None),
            ("{'disabled': 'z3'} disables {'z','3'} — set() iterates the string",
             {"coupler": {"disabled": "z3"}}, None),
            ("{'coupler': null} yields an empty set (the `or {}` catches the None)",
             {"coupler": None}, None),
            ("{'disabled': false} raises TypeError, unguarded",
             {"coupler": {"disabled": False}}, None),
            ("env and build.json are MERGED, not one-or-the-other",
             {"coupler": {"gs": False}}, "z3"),
            ("a non-bool setting beside the flags disables nothing",
             {"coupler": {"version": "1.0", "z3": False}}, None),
            ("'z3, notes ,, ' -> {'z3','notes'} (stripped, empties dropped)", None,
             "z3, notes ,, "),
            ("an empty $COUPLER_DISABLE disables nothing", None, ""),
            ("a corrupt build.json raises out of _disabled_services too", "{not json", None),
        ):
            compare("_disabled_services: %s" % label,
                    observe_disabled(me, doc, tmp, env=env),
                    observe_disabled(original, doc, tmp, env=env))

        # ── build_app: the branches the exemplar cannot reach ──
        #
        # A DEDICATED clean root, not the `tmp` the loop above used. That loop's last case writes
        # a CORRUPT build.json into `tmp`, and `_load_build` does not catch — so every build_app
        # check below, run against `tmp`, would raise JSONDecodeError before reaching the mount
        # loop, the why5 block or coupler_status. Both modules would raise identically, so every
        # comparison would PASS while measuring nothing at all. That is not hypothetical: it was
        # the state of this harness until a mutation test showed three real defects surviving it
        # (an aborting mount loop, a wrong UI threshold, a wrong why5 exception type). The clean
        # root is the fix; `_canary` below is what stops it coming back silently.
        build_root = _write_build(os.path.join(tmp, "plain"), None)
        _canary(check, me, original, build_root)

        compare("build_app: a service that fails to mount is 'down' and the loop CONTINUES",
                observe_build_app(me, _Recorder(mount_fails=("z3",)), jazz_root=build_root),
                observe_build_app(original, _Recorder(mount_fails=("z3",)), jazz_root=build_root))
        compare("build_app: two failures, and the rest still mount",
                observe_build_app(me, _Recorder(mount_fails=("z3", "gs")), jazz_root=build_root),
                observe_build_app(original, _Recorder(mount_fails=("z3", "gs")),
                                  jazz_root=build_root))

        disabled_root = _write_build(os.path.join(tmp, "disabled"),
                                     {"coupler": {"disabled": ["z3", "gs"]}, "version": "9.9"})
        compare("build_app: disabled services are 'off', are never mounted, and still emit a "
                "mount event — and the banner shows them sorted",
                observe_build_app(me, jazz_root=disabled_root),
                observe_build_app(original, jazz_root=disabled_root))

        compare("build_app: the version reaches the banner, /health and coupler_status",
                observe_build_app(me, jazz_root=disabled_root, drive=_drive_tools),
                observe_build_app(original, jazz_root=disabled_root, drive=_drive_tools))

        # ── the why5 branch: dead code in this package, so it is staged ──
        compare("build_app: with NO why5 module the five why5 tools are not registered and "
                "stderr carries the warning",
                observe_build_app(me, jazz_root=build_root, why5=None),
                observe_build_app(original, jazz_root=build_root, why5=None))
        compare("build_app: with a why5 module PRESENT all five register, with descriptions, and "
                "the tools work",
                observe_build_app(me, jazz_root=build_root, why5=_fake_why5(), drive=_drive_tools),
                observe_build_app(original, jazz_root=build_root, why5=_fake_why5(),
                                  drive=_drive_tools))
        compare("build_app: a why5 module missing `from_ci_failure` fails as an ImportError "
                "naming it — not an AttributeError",
                observe_build_app(me, jazz_root=build_root, why5=_fake_why5(with_names=False)),
                observe_build_app(original, jazz_root=build_root, why5=_fake_why5(with_names=False)))

        # ── the tools ──
        compare("the tools: every registered tool called, answers compared",
                observe_build_app(me, jazz_root=build_root, drive=_drive_tools),
                observe_build_app(original, jazz_root=build_root, drive=_drive_tools))

        for label, rec_kwargs in (
            ("a UI answering 200 is 'ok'", {"ui_status": 200}),
            ("a UI answering 499 is 'ok' (the threshold is < 500)", {"ui_status": 499}),
            ("a UI answering 500 is 'degraded'", {"ui_status": 500}),
            ("a UI answering 503 is 'degraded'", {"ui_status": 503}),
            ("an unreachable UI is 'down'", {"ui_raises": True}),
        ):
            compare("coupler_status: %s" % label,
                    observe_build_app(me, _Recorder(**rec_kwargs), jazz_root=build_root,
                                      drive=_drive_tools),
                    observe_build_app(original, _Recorder(**rec_kwargs), jazz_root=build_root,
                                      drive=_drive_tools))

        compare("coupler_status: a service whose probe fails is 'down' while the others are 'ok'",
                observe_build_app(me, _Recorder(probe_fails=("z3_mcp",)), jazz_root=build_root,
                                  drive=_drive_tools),
                observe_build_app(original, _Recorder(probe_fails=("z3_mcp",)), jazz_root=build_root,
                                  drive=_drive_tools))

        # ui_set_value's parse ladder — the one piece of pure logic inside a tool.
        compare("ui_set_value: the whole parse ladder, value by value",
                observe_build_app(me, jazz_root=build_root, drive=_drive_set_value),
                observe_build_app(original, jazz_root=build_root, drive=_drive_set_value))

        # every UI tool's failure path: raise_for_status blows up, the tool must answer `error: `
        failing = _Recorder()
        failing.ui_http_raises = True
        failing_o = _Recorder()
        failing_o.ui_http_raises = True
        compare("the UI tools return `error: <e>` rather than raising, for every failure",
                observe_build_app(me, failing, jazz_root=build_root, drive=_drive_tools),
                observe_build_app(original, failing_o, jazz_root=build_root, drive=_drive_tools))

        # a UI base from the environment must reach the tools' URLs — and NOT the ui banner line
        compare("$JSON_CONTROLS_URL reaches every UI URL, while the `ui (port 8142)` banner "
                "stays literal",
                observe_build_app(me, jazz_root=build_root, env={"JSON_CONTROLS_URL": "http://ui:9999"},
                                  drive=_drive_tools),
                observe_build_app(original, jazz_root=build_root,
                                  env={"JSON_CONTROLS_URL": "http://ui:9999"},
                                  drive=_drive_tools))

        # $COUPLER_PYTHON must reach the StdioTransport commands
        compare("$COUPLER_PYTHON reaches every downstream StdioTransport command",
                observe_build_app(me, jazz_root=build_root, env={"COUPLER_PYTHON": "/x/py"}),
                observe_build_app(original, jazz_root=build_root, env={"COUPLER_PYTHON": "/x/py"}))


def _drive_set_value(module, app, recorder):
    """Call `ui_set_value` across the whole parse ladder and return what each answered.

    The ladder's ORDER is observable — '1' must become int 1 rather than float 1.0, and 'inf'
    must become a float rather than staying a string — and `_drive_tools` only ever passes one
    value, so this drives the rest.
    """
    fn = recorder.tools.get("ui_set_value")
    if fn is None:
        return ("ui_set_value was not registered",)
    values = ["true", "TRUE", "True", "false", "FALSE", "42", "-7", "+3", "3.14", "1_0", "0x10",
              "inf", "-inf", "nan", "1e3", "", "abc", "  5  ", "٨"]
    return tuple((v, fn("home", "ctl", v)) for v in values)


def _selftest_surface(check, me, original):
    """Check [4]: the callable surface ticket #385 states, proven by inspection.

    Compared against the ORIGINAL's own signatures rather than against the ticket's text, so the
    check cannot pass by agreeing with a typo.

    A stand-in fastmcp is installed for the duration: `build_app`'s return annotation is the
    forward reference "FastMCP", and resolving it needs SOME fastmcp to resolve against. The
    original was exec'd against a stand-in too, so both are measured against the same class object
    — which is the whole claim being checked, and it is why this is not staging in this module's
    favour.
    """
    import inspect

    recorder = _Recorder()
    saved_modules = recorder.install()
    try:
        _selftest_surface_inner(check, me, original)
    finally:
        _Recorder.restore(saved_modules)


def _selftest_surface_inner(check, me, original):
    import inspect

    for name in ("_env_port", "_load_build", "_disabled_services", "_notes_python", "build_app",
                 "main"):
        mine = getattr(me, name, None)
        theirs = getattr(original, name, None)
        check(callable(mine), "%s is importable from this module and callable" % name)
        check(inspect.iscoroutinefunction(mine) is inspect.iscoroutinefunction(theirs),
              "%s is a coroutine function in this module exactly if it is in the ORIGINAL (%s)"
              % (name, inspect.iscoroutinefunction(theirs)))
        if name == "build_app":
            # The one signature that cannot be compared directly: the ORIGINAL annotates with the
            # fastmcp class it imported at module scope, and this module imports fastmcp lazily,
            # so its annotation is the forward reference "FastMCP". Resolving it against the
            # fastmcp in force yields the very same class object the original annotated with —
            # which is the real claim, and this is what proves it.
            fastmcp = sys.modules.get("fastmcp")
            resolved = inspect.signature(mine, eval_str=True,
                                         globals={"FastMCP": fastmcp.FastMCP})
            check(str(resolved) == str(inspect.signature(theirs)),
                  "build_app's signature RESOLVES to the ORIGINAL's exactly — `%s` (the "
                  "annotation is the forward reference 'FastMCP' because fastmcp is imported "
                  "lazily; resolved against the fastmcp in force it is the same class)"
                  % (resolved,))
            check(resolved.return_annotation is fastmcp.FastMCP,
                  "build_app is annotated `-> FastMCP` — the resolved annotation IS the FastMCP "
                  "class, as the ticket's surface says")
            continue
        check(str(inspect.signature(mine)) == str(inspect.signature(theirs)),
              "%s's signature matches the ORIGINAL's exactly — `%s%s`"
              % (name, name, inspect.signature(mine)))

    # The ticket's surface, spelled out, so a reader can compare it to the ticket without trusting
    # the loop above to have used the right names.
    expected = {
        "_env_port": "(name: str, default: int) -> int",
        "_load_build": "() -> dict",
        "_disabled_services": "() -> set",
        "_notes_python": "() -> str",
        "main": "()",
    }
    import inspect as _i
    for name, rendering in expected.items():
        actual = str(_i.signature(getattr(me, name)))
        check(actual == rendering,
              "%s%s is exactly the surface ticket #385 states (%s%s)"
              % (name, actual, name, rendering))

    for name in ("JAZZ_ROOT", "JAZZ_DEV", "PORT", "JAZZ_SERVICES", "telemetry",
                 "service_running"):
        check(hasattr(me, name) and hasattr(original, name),
              "the module global %s the original bound is still bound here — callers and tests "
              "read and rebind it (%s)" % (name, _brief(getattr(me, name, None), 60)))

    check(me.JAZZ_SERVICES == original.JAZZ_SERVICES,
          "JAZZ_SERVICES equals the ORIGINAL's exactly, TUPLES included — %r"
          % (me.JAZZ_SERVICES,))
    check(all(isinstance(row, tuple) for row in me.JAZZ_SERVICES),
          "every JAZZ_SERVICES row is a tuple, as the original's were — a list of lists would "
          "satisfy `for name, module in ...` and break `('z3','z3_mcp') in JAZZ_SERVICES`")
    check(me.PORT == original.PORT == 7770,
          "PORT is the original's 7770 under the shipped config (rewrite %r, original %r)"
          % (me.PORT, original.PORT))
    check(str(me.JAZZ_ROOT) == str(original.JAZZ_ROOT)
          and str(me.JAZZ_DEV) == str(original.JAZZ_DEV),
          "JAZZ_ROOT and JAZZ_DEV are the original's paths under the shipped config (%s, %s)"
          % (me.JAZZ_ROOT, me.JAZZ_DEV))


def _selftest_side_effects(check, original):
    """Check [5]: the sys.path insert is the ORIGINAL's, and no stand-in outlived the run."""
    import subprocess
    import tempfile

    # What the ORIGINAL inserts, measured by exec'ing it and reading sys.path[0].
    #
    # sys.path[0] — NOT a set-difference against a `before` snapshot. This module's own import
    # already put the telemetry path on sys.path, so the original's insert only ever adds a
    # DUPLICATE of an entry that is already there, and a difference would come back empty and be
    # read as "the original inserts nothing". The insert is positional and unconditional, so
    # position 0 is the thing to look at.
    recorder = _Recorder()
    saved_modules = recorder.install()
    path_before = list(sys.path)
    try:
        module = types.ModuleType("original_probe")
        exec(compile(ORIGINAL_SOURCE, "<original>", "exec"), module.__dict__)
        original_head = sys.path[0]
    finally:
        sys.path[:] = path_before
        _Recorder.restore(saved_modules)

    # What THIS module inserts, measured in a child interpreter — this one imported it long ago.
    with tempfile.TemporaryDirectory() as isolated:
        env = dict(os.environ)
        env.pop(CONFIG_ENV, None)
        env["PYTHONPATH"] = _package_root() + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; import %s as s; print(sys.path[0]); print(s.TELEMETRY_PATH)"
             % DOTTED_NAME],
            env=env, capture_output=True, text=True, cwd=isolated)
        # NOT .strip() before splitlines(): with the insert absent, sys.path[0] is the EMPTY
        # string, and stripping would swallow that blank first line, leaving one line where two
        # were printed — which silently misaligns the two values below and, when this check was
        # first written, crashed it with a TypeError instead of reporting the defect it had just
        # detected. Padding keeps the message printable no matter what the child did.
        lines = proc.stdout.splitlines()
        head = (lines + ["<no output>", "<no output>"])[:2]

    expected = str(Path.home() / "code/forge/work/jazz_telemetry")
    check(proc.returncode == 0 and len(lines) == 2 and lines[0] == lines[1] == expected,
          "importing this module inserts the telemetry path at sys.path[0], exactly as importing "
          "the original does — this is a real side effect of the original's module-level code, so "
          "it is reproduced rather than tidied away (child sys.path[0]=%r, TELEMETRY_PATH=%r)"
          % (head[0], head[1]))
    check(original_head == expected,
          "and that is the path the ORIGINAL puts at sys.path[0], measured by exec'ing it "
          "(original sys.path[0]=%r)" % (original_head,))

    check(all(sys.modules.get(name) is None or "types" not in type(sys.modules[name]).__module__
              or not getattr(sys.modules.get(name), "__name__", "").startswith("fastmcp")
              for name in ("fastmcp",)) and "fastmcp" not in sys.modules,
          "the recording stand-ins were removed from sys.modules — a real fastmcp import after "
          "this selftest gets the real one")
    check("httpx" not in sys.modules and "starlette" not in sys.modules,
          "the httpx and starlette stand-ins were removed too")
    check("coupler.why5" not in sys.modules,
          "the fake `coupler.why5` was removed — a later import must not find a test double")


def _selftest_main(compare, check, me, original):
    """Check [6]: main()'s argument wiring, differential against the ORIGINAL."""
    compare("main(): no arguments -> serves on the configured host and PORT, transport 'sse'",
            observe_main(me, []), observe_main(original, []))
    compare("main(): --port 8080 --host 0.0.0.0 reaches run_http_async",
            observe_main(me, ["--port", "8080", "--host", "0.0.0.0"]),
            observe_main(original, ["--port", "8080", "--host", "0.0.0.0"]))
    compare("main(): $COUPLER_HOST supplies the --host default",
            observe_main(me, [], env={"COUPLER_HOST": "0.0.0.0"}),
            observe_main(original, [], env={"COUPLER_HOST": "0.0.0.0"}))
    compare("main(): --port zzz exits 2 through argparse, in both",
            observe_main(me, ["--port", "zzz"]), observe_main(original, ["--port", "zzz"]))

    served, _raised = observe_main(me, [])
    check(served and served[0][1] == (("host", "127.0.0.1"), ("port", 7770),
                                      ("transport", "sse")),
          "the SHIPPED config reproduces the original's run_http_async(transport='sse', "
          "host='127.0.0.1', port=7770) — %r" % (served[0][1] if served else None,))


def _selftest_argv(check):
    """Check [8]: the original's `python -m coupler.server [--port N]` spelling still serves.

    The original's argv went straight to `main()`; this module adds subcommands, so anything that
    is NOT a subcommand must still reach `main()` untouched. Proven by calling `cli` with a
    recording `main` and reading back the `sys.argv` it saw — not by reading the parser and
    reasoning about it.
    """
    me = sys.modules[__name__]
    saved = me.main
    seen = []
    try:
        me.main = lambda: seen.append(list(sys.argv[1:]))
        codes = [cli([]), cli(["--port", "8080"]), cli(["--port", "8080", "--host", "0.0.0.0"]),
                 cli(["run", "--port", "9"])]
    finally:
        me.main = saved
    check(seen == [[], ["--port", "8080"], ["--port", "8080", "--host", "0.0.0.0"],
                   ["--port", "9"]] and codes == [0, 0, 0, 0],
          "`python -m %s`, `--port 8080`, `--port 8080 --host 0.0.0.0` and the explicit `run` all "
          "reach main() with the original's argv (saw %r, rc=%r)" % (DOTTED_NAME, seen, codes))


def _tree_snapshot():
    """Map every file in this package to its size and mtime, ignoring build artifacts.

    `__pycache__`, `build`, `dist` and `*.egg-info` are excluded because CPython and pip write
    them for any import or install; ticket #385 lists them among the artifacts that are
    regenerated by any install and never committed. Everything else is a file this module must not
    touch, and check [7] diffs this before and after a whole selftest to prove it did not.
    """
    root = _package_root()
    snapshot = {}
    for directory, subdirs, files in os.walk(root):
        subdirs[:] = [d for d in subdirs
                      if d != "__pycache__" and not d.endswith(".egg-info")
                      and d not in ("build", "dist")]
        for name in files:
            path = os.path.join(directory, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            snapshot[os.path.relpath(path, root)] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def _tree_diff(before, after):
    changed = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) != after.get(path):
            changed.append(("created" if path not in before else
                            "deleted" if path not in after else "modified", path))
    return changed


def _canary(check, me, original, root):
    """Prove the build_app fixture actually BUILDS, before anything is compared against it.

    A differential compares two observations; it does not care whether they are observations of
    anything useful. If `_load_build` raises on a corrupt build.json staged by an earlier case,
    both modules raise identically and every later comparison passes while `build_app` never
    reaches its mount loop at all. This check is what makes that impossible to miss: it requires
    the fixture to produce a real build — no raise, and the mounts and tools actually present —
    so a poisoned root fails HERE, loudly, instead of turning the checks below into green noise.
    """
    mine = observe_build_app(me, jazz_root=root)
    theirs = observe_build_app(original, jazz_root=root)
    for label, obs in (("rewrite", mine), ("original", theirs)):
        calls, stderr, _extra, raised = obs
        check(raised is None,
              "canary: build_app on the clean root does not raise for the %s — the fixture is "
              "sound, so the checks below measure the build rather than a shared crash (%s)"
              % (label, raised))
        check(any(c[0] == "mount" for c in calls) and any(c[0] == "tool" for c in calls),
              "canary: build_app on the clean root really mounts services and registers tools "
              "for the %s (%d mounts, %d tools)"
              % (label, sum(c[0] == "mount" for c in calls), sum(c[0] == "tool" for c in calls)))


# ─────────────────────────────── the install check ───────────────────────────────

#: The child-interpreter bootstrap that ACTIVATES an install and then runs a statement.
#:
#: `site.addsitedir` is what activates it, and it is not interchangeable with `$PYTHONPATH`: an
#: editable install works through a `.pth` file that registers setuptools' import finder, and
#: `.pth` files are only processed for genuine site directories. A `$PYTHONPATH` entry never has
#: its `.pth` read, so the finder never loads and the import fails for a reason that has nothing
#: to do with the module under test.
#:
#: Run under `-S`, so this machine's real site-packages cannot answer for the staged one and the
#: import can only succeed if the INSTALL provides it.
_ACTIVATE = "import site, sys; site.addsitedir(%r); "


def install_check(stream=None):
    """Prove ticket #385's acceptance item (c) by RUNNING pip. Returns the number of failures.

    This does not simulate an install and does not reason about one: it runs a real
    `pip install -e .` and a real `pip install .` into throwaway prefixes, activates each with
    `site.addsitedir`, and imports `coupler.server` from the result in a child interpreter started
    with `-S` so no other site-packages can answer for it. Both layouts matter and they fail
    differently:

      * the EDITABLE layout is what acceptance item (c) names. It installs a finder pointing back
        at this source tree.
      * the NON-EDITABLE layout is what `pip install .` produces, and it is where the config is
        hardest to find: this module lands at `site-packages/coupler/server.py` and the registry
        walk-up passes nothing at all above it. That is what `find_registry`'s
        `_installed_registry` fallback exists for, and it is checked here both ways — that the
        shipped registry IS found, and that deleting it brings the config gate back.

    Everything is written under a temporary directory except pip's own build artifacts in this
    package (`*.egg-info/`, `build/`), which `.gitignore` excludes precisely because any install
    regenerates them.
    """
    import shutil
    import subprocess
    import tempfile

    out = stream or sys.stdout
    failures = []

    def check(ok, label):
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    root = _package_root()
    print("install check for %s\n  package root: %s\n  pip         : %s"
          % (UNIT, root, _pip_version()), file=out)

    # ── 1. the declaration ────────────────────────────────────────────────────
    print("\n[1] pyproject.toml declares this module", file=out)
    try:
        import tomllib
    except ImportError:  # pragma: no cover — Python < 3.11
        tomllib = None

    if tomllib is None:
        check(False, "tomllib is available to parse pyproject.toml (needs Python 3.11+)")
    else:
        with open(os.path.join(root, "pyproject.toml"), "rb") as handle:
            pyproject = tomllib.load(handle)
        setuptools_cfg = pyproject.get("tool", {}).get("setuptools", {})
        packages = setuptools_cfg.get("packages", [])
        package_dir = setuptools_cfg.get("package-dir", {})
        scripts = pyproject.get("project", {}).get("scripts", {})
        check("coupler" in packages,
              "`coupler` is declared in tool.setuptools.packages (%r) — without it an install "
              "ships no coupler/ and `import coupler.server` fails" % (packages,))
        check(os.path.isfile(os.path.join(root, package_dir.get("coupler", "coupler"),
                                          "server.py")),
              "the directory `coupler` maps to actually holds server.py")
        check(scripts.get("forge2-coupler-server") == "coupler.server:cli",
              "the console script forge2-coupler-server points at coupler.server:cli (%r)"
              % (scripts.get("forge2-coupler-server"),))
        check(callable(cli), "that entry point, coupler.server:cli, resolves to a callable")
        check(pyproject.get("project", {}).get("dependencies") == [],
              "the package declares NO dependencies, so a `pip install -e .` needs no index to "
              "resolve any (fastmcp/httpx are imported lazily by build_app for exactly this "
              "reason)")

    # ── 2. a REAL editable install ────────────────────────────────────────────
    print("\n[2] `pip install -e .` — RUN, not simulated", file=out)
    with tempfile.TemporaryDirectory() as prefix:
        ok, log = _pip_install(root, prefix, editable=True)
        check(ok, "`pip install -e .` completes successfully into a throwaway prefix%s"
                  % ("" if ok else "\n         %s" % log[-400:]))
        if ok:
            site_dir = _site_dir(prefix)
            check(site_dir is not None, "the editable install produced a site-packages (%s)"
                                        % site_dir)
            if site_dir:
                _check_import(check, site_dir, "the EDITABLE install", editable=True)
                _check_console_script(check, prefix, "the editable install")

    # ── 3. a REAL non-editable install ────────────────────────────────────────
    print("\n[3] `pip install .` — the layout where the registry walk-up finds nothing", file=out)
    with tempfile.TemporaryDirectory() as prefix:
        ok, log = _pip_install(root, prefix, editable=False)
        check(ok, "`pip install .` completes successfully into a throwaway prefix%s"
                  % ("" if ok else "\n         %s" % log[-400:]))
        if not ok:
            return _install_verdict(out, failures)
        site_dir = _site_dir(prefix)
        if site_dir is None:
            check(False, "the non-editable install produced a site-packages")
            return _install_verdict(out, failures)

        installed_module = os.path.join(site_dir, "coupler", "server.py")
        check(os.path.isfile(installed_module),
              "`pip install .` really shipped coupler/server.py into site-packages (%s)"
              % installed_module)
        check(not os.path.isfile(os.path.join(site_dir, REGISTRY_NAME)),
              "the installed site-packages has NO registry.json at its root — so the walk-up from "
              "coupler/server.py finds nothing, which is the case the find_spec fallback exists "
              "for")
        shipped = os.path.join(site_dir, PACKAGE_WITH_REGISTRY, REGISTRY_NAME)
        check(os.path.isfile(shipped),
              "the registry IS shipped as package data inside %s, which is the only copy this "
              "layout has (%s)" % (PACKAGE_WITH_REGISTRY, shipped))

        _check_import(check, site_dir, "the NON-EDITABLE install", editable=False)

        # The gate still holds there: remove the shipped registry and it must throw — from THIS
        # module, naming THIS unit, not from the sibling.
        os.remove(shipped)
        rc, stdout, stderr = _child(site_dir, "import %s" % DOTTED_NAME, sibling_config=True)
        check(rc != 0 and "ConfigError" in stderr and UNIT in stderr,
              "with the shipped registry deleted, that same install throws ConfigError naming "
              "THIS unit rather than guessing a default — the gate is not an artifact of the "
              "source tree (rc=%d)" % rc)
        shutil.copy2(os.path.join(root, REGISTRY_NAME), shipped)

        # ── the siblings' gaps, reported rather than absorbed ──
        rc, stdout, stderr = _child(site_dir, "import %s" % DOTTED_NAME, sibling_config=False)
        blocked = rc != 0 and "_config.py" in stderr
        print("\n  NOTE (a sibling's gap, NOT this unit's, and NOT ticket #385's to fix):\n"
              "  in the non-editable layout with no $COUPLER_CONFIG set, `import coupler.server`\n"
              "  fails in `coupler/__init__.py` -> `coupler/_config.py` (ticket #397) before this\n"
              "  module runs: that unit's registry walk-up has no package-data fallback, so it\n"
              "  finds nothing above site-packages/coupler/. Observed: %s\n"
              "  This unit's own resolution is unaffected and is what check [3] measures, using\n"
              "  that sibling's own documented $COUPLER_CONFIG escape hatch to isolate it."
              % ("yes — %s" % (stderr.strip().splitlines()[-1:] or [""])[0]
                 if blocked else "NO — the sibling resolved after all; this note is stale"),
              file=out)

    _report_bridge_gap(out)
    return _install_verdict(out, failures)


def _report_bridge_gap(out):
    """State the OTHER sibling gap this unit deliberately did not fix, with live evidence.

    `registry.json` carries no `coupler.bridge` section, so #357's module raises ConfigError at
    import. Adding it would be doing #357's work, and #385 "covers ONE module — the one identified
    below — and nothing else". It is reported rather than absorbed so that a reader who finds
    bridge.py broken knows this ticket saw it and left it alone on purpose.
    """
    try:
        document, _b, path = load_config()
    except ConfigError:
        return
    try:
        with open(find_registry() or "", "r", encoding="utf-8") as handle:
            registry = json.load(handle)
    except Exception:  # noqa: BLE001 — this is a courtesy note; it must never fail the check
        return
    section = registry.get("forge2", {}).get("code__code-invalid__coupler", {})
    print("\n  NOTE (a second sibling gap, likewise not #385's to fix):\n"
          "  registry.json's %r section holds %r.\n"
          "  `coupler.bridge` (#357) is absent, so `python3 -m coupler.bridge` raises ConfigError\n"
          "  at import and that unit cannot run. Its config template is in its own\n"
          "  `config_template()`; installing it belongs to #357, not here."
          % ("forge2 -> code__code-invalid__coupler", sorted(section)), file=out)


def _install_verdict(out, failures):
    print("\n%s — %d failure(s)"
          % ("INSTALL-CHECK PASSED" if not failures else "INSTALL-CHECK FAILED", len(failures)),
          file=out)
    for failure in failures:
        print("  failed: %s" % failure.splitlines()[0], file=out)
    return len(failures)


def _pip_version():
    import subprocess
    try:
        proc = subprocess.run([sys.executable, "-m", "pip", "--version"],
                              capture_output=True, text=True)
        return proc.stdout.strip() or "unavailable"
    except Exception as exc:  # noqa: BLE001
        return "unavailable (%s)" % exc


def _pip_install(root, prefix, editable):
    """Run a real pip install of `root` into `prefix`. Returns `(ok, log)`."""
    import subprocess

    argv = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
            "--prefix", prefix]
    if editable:
        argv.append("-e")
    argv.append(root)
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode == 0, proc.stdout + proc.stderr


def _site_dir(prefix):
    """Find the site-packages directory pip created under `prefix`."""
    for base, dirs, _files in os.walk(prefix):
        if os.path.basename(base) == "site-packages":
            return base
    return None


def _child(site_dir, statement, sibling_config=True):
    """Run `statement` in a `-S` child with `site_dir` activated. Returns (rc, stdout, stderr).

    `-S` keeps this machine's real site-packages out, so an import can only succeed if the INSTALL
    under test provides it. `sibling_config` satisfies `coupler/__init__.py`'s own config gate
    (#397) through its documented $COUPLER_CONFIG hatch, which isolates THIS unit's resolution
    from that sibling's missing fallback — see the NOTE `install_check` prints.
    """
    import subprocess
    import tempfile

    env = dict(os.environ)
    env.pop(CONFIG_ENV, None)
    env.pop("PYTHONPATH", None)
    if sibling_config:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"distribution": "coupler", "fallback": "0.0.dev0"}, handle)
        handle.close()
        env["COUPLER_CONFIG"] = handle.name
    else:
        env.pop("COUPLER_CONFIG", None)

    with tempfile.TemporaryDirectory() as elsewhere:
        proc = subprocess.run(
            [sys.executable, "-S", "-c", (_ACTIVATE % site_dir) + statement],
            env=env, capture_output=True, text=True, cwd=elsewhere)
    return proc.returncode, proc.stdout, proc.stderr


def _check_import(check, site_dir, what, editable):
    """Import `coupler.server` from an activated install and confirm it found its config."""
    rc, stdout, stderr = _child(
        site_dir,
        "import %s as s; print(s.PORT, len(s.JAZZ_SERVICES), s.active_source() != '')"
        % DOTTED_NAME)
    check(rc == 0 and stdout.strip() == "7770 7 True",
          "`import coupler.server` works from %s, from an unrelated working directory, under "
          "`python3 -S`, and finds its config (rc=%d, stdout=%r, stderr=%r)"
          % (what, rc, stdout.strip(), stderr.strip()[-200:]))

    rc, stdout, stderr = _child(
        site_dir, "import sys; from %s import cli; sys.exit(cli(['show-services']))"
                  % DOTTED_NAME)
    check(rc == 0 and "notes_db" in stdout,
          "the console script's entry point runs from %s (rc=%d)" % (what, rc))


def _check_console_script(check, prefix, what):
    """Confirm pip actually wrote the console script the pyproject declares."""
    script = os.path.join(prefix, "bin", "forge2-coupler-server")
    check(os.path.isfile(script),
          "pip installed the `forge2-coupler-server` console script from %s (%s)"
          % (what, script))


# ─────────────────────────────── bug reports ───────────────────────────────

def bug_report(exc, formatted, invocation):
    """Append one timestamped JSON line describing an UNEXPECTED exception; return its path.

    This is `note-for-claude`'s rule — "all tools need to pass a bug-report automatically
    (timestamped if an exception is thrown)". It reports a DEFECT IN THIS TOOL and nothing else: a
    `ConfigError` and a `UsageError` are designed behavior and never land here, and neither does a
    selftest check FAILING, which is a verdict this module exists to reach.

    Returns None when no report could be filed (no config, or no `bug_reports` key, or the sink
    cannot be written) — a tool that crashed while reporting a crash would replace the real
    diagnosis with its own.
    """
    try:
        config, base = active_config(), active_base()
        sink = config.get("bug_reports")
        if not sink:
            return None
        path = sink if os.path.isabs(sink) else os.path.join(base, sink)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "unit": UNIT,
                "ticket": TICKET,
                "invocation": invocation,
                "error": "%s: %s" % (type(exc).__name__, exc),
                "traceback": formatted,
            }) + "\n")
        return path
    except Exception:  # noqa: BLE001 — reporting a bug must never raise a second one
        return None


# ─────────────────────────────── the command line ───────────────────────────────

#: The subcommands this module adds. Anything else in argv is the ORIGINAL's own spelling and is
#: handed to `main()` untouched — see `cli`.
_SUBCOMMANDS = ("run", "selftest", "install-check", "show-config", "emit-config", "show-services")


def _invocation(argv):
    """Describe how this process was ACTUALLY started, for a bug report to record.

    Derived from the interpreter and `sys.argv` rather than written as a fixed string. A report is
    a record, and a record that states an invocation the operator did not type is worse than no
    record: it sends the next reader to reproduce something that never ran.
    """
    if __name__ == "__main__" and __spec__ is not None:
        launcher = "-m " + __spec__.name
    else:
        launcher = sys.argv[0] if sys.argv and sys.argv[0] else DOTTED_NAME
    return " ".join([os.path.basename(sys.executable), launcher] + list(argv))


def _run_main(rest):
    """Hand `rest` to `main()` by staging `sys.argv`, and put argv back afterwards.

    `main()` takes no parameters and parses `sys.argv` — that is the surface ticket #385 fixes, so
    it cannot be given an argv parameter. Staging `sys.argv` is therefore how the original's
    spelling is preserved exactly: `python3 -m coupler.server --port 8080` reaches the same
    `parse_args()` it always did.
    """
    saved = sys.argv
    try:
        sys.argv = [saved[0] if saved else DOTTED_NAME] + list(rest)
        main()
    finally:
        sys.argv = saved
    return 0


def _print_help(out=None):
    """Print the usage for this module's subcommands, and for the original's own spelling."""
    print(
        "usage: forge2-coupler-server [run|selftest|install-check|show-config|emit-config|"
        "show-services]\n"
        "       forge2-coupler-server [--port N] [--host H]        (the ORIGINAL's spelling)\n"
        "\n"
        "forge2 rewrite of the forge unit code__code-invalid__coupler:coupler/server.py\n"
        "(ticket #385) — the coupler HTTP MCP server. Config-driven: it throws if it cannot\n"
        "see its config object.\n"
        "\n"
        "  run             run the server (the default; needs fastmcp/httpx installed)\n"
        "  selftest        prove this rewrite against the ORIGINAL, which it embeds\n"
        "  install-check   prove the package's install by RUNNING pip, both layouts\n"
        "  show-config     print the config object in force and its source\n"
        "  emit-config     print a template of this unit's config object\n"
        "  show-services   print the service table and which entries are disabled\n"
        "\n"
        "With NO subcommand — or with any argument that is not one of the above — the argv is\n"
        "handed to main() untouched, which is the original's spelling:\n"
        "  python3 -m %s --port 8080 --host 0.0.0.0\n"
        "\n"
        "Config is read from the file named by $%s, else from the %s section of the nearest\n"
        "%s found by walking up from this module, else from the copy shipped as package data\n"
        "in %s. This package ships one, so these commands work from a clean checkout.\n"
        "Run `emit-config` for a template."
        % (DOTTED_NAME, CONFIG_ENV, " -> ".join(UNIT_PATH), REGISTRY_NAME, PACKAGE_WITH_REGISTRY),
        file=out or sys.stdout)


def cli(argv=None):
    """Entry point for the `forge2-coupler-server` console script. Returns an exit code.

    Any argv whose first token is not one of `_SUBCOMMANDS` is the ORIGINAL's own spelling and is
    handed to `main()` untouched, so `python -m coupler.server`, `--port 8080` and
    `--host 0.0.0.0` all keep working exactly as before. `main()` is the server itself and is kept
    free of subcommand parsing, because it is the surface ticket #385 requires.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else None
    try:
        if command in ("-h", "--help", "help"):
            _print_help()
            return 0

        if command == "emit-config":
            print(json.dumps(config_template(), indent=2, ensure_ascii=False))
            print("\n# Install this at %s in your registry.json, or save a file containing just "
                  "it\n# and point $%s at that file. Until it is installed, importing this "
                  "module\n# throws ConfigError — it will not guess a default."
                  % (" -> ".join(UNIT_PATH), CONFIG_ENV), file=sys.stderr)
            return 0

        if command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(), "base": active_base(),
                              "resolved": {"PORT": PORT, "JAZZ_ROOT": str(JAZZ_ROOT),
                                           "JAZZ_DEV": str(JAZZ_DEV),
                                           "TELEMETRY_PATH": TELEMETRY_PATH,
                                           "JAZZ_SERVICES": [list(r) for r in JAZZ_SERVICES]},
                              "config": active_config()}, indent=2, ensure_ascii=False))
            return 0

        if command == "show-services":
            disabled = _disabled_services()
            print(json.dumps(
                {"port": PORT, "jazz_root": str(JAZZ_ROOT),
                 "telemetry": "real" if telemetry is not _stub_telemetry else "stub (no "
                              "jazz_telemetry on %s)" % TELEMETRY_PATH,
                 "services": [{"name": n, "module": m,
                               "state": _SETTINGS["status_off"] if n in disabled else "enabled"}
                              for n, m in JAZZ_SERVICES],
                 "disabled": sorted(disabled)}, indent=2, ensure_ascii=False))
            return 0

        if command == "selftest":
            return 0 if selftest() == 0 else 1

        if command == "install-check":
            return 0 if install_check() == 0 else 1

        if command == "run":
            return _run_main(argv[1:])

        # Not a subcommand: the ORIGINAL's spelling. Hand it to main() untouched.
        return _run_main(argv)

    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except UsageError as exc:
        print("usage error: %s" % exc, file=sys.stderr)
        return 2
    except ImportError as exc:
        # `run` without fastmcp/httpx/starlette. Not a defect in this tool, and the original could
        # not even be imported in this situation — so it is answered as a usage problem, not a bug
        # report.
        print("cannot run the server: %s\n"
              "The server needs fastmcp, httpx and starlette, which this package does not declare "
              "(see the module docstring). Install them with: pip install fastmcp httpx starlette"
              % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        path = bug_report(exc, traceback.format_exc(), _invocation(argv))
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise


if __name__ == "__main__":
    if __spec__ is None:
        # Run by path: `coupler/` went onto the import path instead of the package root, so the
        # `coupler` package is not importable and `-m` semantics are gone. One line that fixes it
        # beats a traceback that blames the tool.
        print("usage error: run this module as `python3 -m %s ...` from the package root (the "
              "directory holding pyproject.toml), not by path. Running it by path puts %s on the "
              "import path instead of the package root, so the `coupler` package cannot be "
              "imported." % (DOTTED_NAME, os.path.dirname(os.path.abspath(__file__))),
              file=sys.stderr)
        sys.exit(2)
    sys.exit(cli())
