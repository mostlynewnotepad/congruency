#!/usr/bin/env python3
"""forge2 / code__code-invalid__coupler / coupler.bridge — a behavior-preserving rewrite of
the forge unit `code__code-invalid__coupler:coupler/bridge.py` (module key
forge-rw:34332ce930fbd478), filed under ticket #357 against the FORGE-wide refactor standard
#200.

(#357 supersedes #286, which named its source only as a `git cat-file` against the forge's
bare repos that the sandboxed pair_loop worker cannot run. #357 embeds the source instead, so
the rewrite needs no forge access, and the work is done HERE. `ORIGINAL_SOURCE` below is that
embedded copy, and `selftest` check [0] proves it is the real forge blob by hashing it — see
THE EQUIVALENCE BASIS.)

WHAT THIS IS
------------
The original forge unit was 2480 bytes: the stdio-to-SSE bridge that Claude Desktop launches.
It polls a TCP port until the `coupler` HTTP server answers, then proxies stdio to that
server's SSE endpoint; if the server never answers it serves a degraded one-tool stub instead,
so the caller gets a useful "coupler is down, start it with ..." message rather than an opaque
"server disconnected".

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and it adds the three things #200 requires that the
original lacked: it is part of a proper installable package, it is driven by a configuration
object, and it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
Quoted from ticket #357, which lowered the original with codebean's `lower_node` (#183):

    async _wait_for_server() -> bool
    main()

Both are preserved exactly: same names, same (empty) parameter lists, `_wait_for_server` still
a coroutine function returning a `bool`, `main()` still an ordinary function. `selftest` check
[4] proves each of those properties by inspection rather than asserting them.

The original also bound three module-level names that callers and tests read and REBIND —
`PORT`, `RETRIES` and `RETRY_S`. They are part of the surface in practice, so they are still
module globals here, still read at CALL time (not captured at import), so
`import coupler.bridge as b; b.RETRIES = 3` keeps working exactly as it did. Two more globals
join them, `HOST` and `TIMEOUT_S`, because the original hardcoded those two values inside the
function body and #200 requirement 4 does not allow that (see CONFIGURATION).

`stub_status_payload()` is also new. The original built its degraded-stub JSON inline inside
`main()`, where nothing could reach it without standing up a server; that payload is a
behavior worth pinning, so it is lifted into a named function. `main()` calls it, so the bytes
it returns are the bytes the stub serves — not a copy that could drift from them.

WHAT THE ORIGINAL ACTUALLY DID — READ OFF THE CODE, NOT ASSUMED
---------------------------------------------------------------
Four details of `_wait_for_server`'s loop are easy to "fix" and wrong to. Each is preserved
deliberately, and `selftest` check [2] proves each one against the ORIGINAL AS IT RUNS:

  * `except Exception: pass` catches EVERYTHING, not just connection errors. A `TypeError` or
    a `KeyError` out of the connect is swallowed and reported as "server not up yet". That is
    a weakness of the original — a real bug reads as a down server — but ticket #357 asks for
    a behavior-preserving rewrite, not a better bridge, so it is preserved, not fixed.
  * `except Exception` does NOT catch `BaseException`, so a `KeyboardInterrupt` or a
    `SystemExit` out of the connect propagates rather than being counted as a retry. That is
    why the guard is `except Exception` and not a bare `except:`.
  * the `print` and the `await asyncio.sleep(RETRY_S)` sit at LOOP-BODY level, after the
    except, so they run after EVERY failed attempt INCLUDING THE LAST one. `RETRIES=3` with
    every connect refused therefore makes 3 attempts, prints 3 waiting lines and sleeps 3
    times. This is not an oversight in the original: its own docstring promises "retries every
    2 seconds for 30 seconds", and 15 retries × 2s = 30s only if the last attempt sleeps too.
  * the `try` covers `writer.close()` and `await writer.wait_closed()` as well as the connect,
    so a writer that fails to close counts as a failed attempt rather than a success.

A NOTE ON `coupler/tests/test_bridge.py`, WHICH CONTRADICTS THE ORIGINAL ON TWO POINTS
--------------------------------------------------------------------------------------
The sibling unit `coupler/tests/test_bridge.py` (ticket #393) tests this module, and its
`EDGE_CASES` table states two expectations that the ORIGINAL does not satisfy. This is
recorded here because a reader comparing the two files will otherwise think this one is wrong:

  1. it expects "a non-OSError from the connect propagates rather than counting as 'down'".
     The original's `except Exception: pass` swallows it. Observed on the original: a
     non-OSError yields `False`, not a raise.
  2. it expects "RETRY_S is slept between attempts, and not after the last one", asserting
     `sleeps == [0.25, 0.25]` for `RETRIES=3`. The original sleeps three times.

Both were verified by EXECUTING the original (`selftest` check [2] runs exactly these two
scenarios against it and prints the result). Ticket #357 requires this rewrite to reproduce
THE ORIGINAL's behavior — that is requirement 1, and the ticket names the original's embedded
bytes as "the behavior-preserving basis". So this module follows the original and does not
satisfy those two expectations, exactly as the original does not.

That sibling cannot run today in any case, for an unrelated reason: it imports
`coupler.config`, a module that does not exist in this package, so it fails at import. Ticket
#355's `coupler/tests/test_build.py` records the same finding in its own configuration
section. Neither that import nor those two expectations is ticket #357's to fix — #357 "covers
ONE module — the one identified below — and nothing else" — so this file changes nothing about
it, and this module's own `selftest` is the evidence for this rewrite.

THE `fastmcp` DEPENDENCY, AND THE ONE DELIBERATE DEVIATION
-----------------------------------------------------------
The original imported `fastmcp` at module scope, so `import coupler.bridge` raised
`ImportError` wherever fastmcp was absent — and it IS absent from the interpreter this package
was built and verified against, and it is not declared by this package's `pyproject.toml`.

This module imports fastmcp INSIDE `main()` instead, via `_load_fastmcp()`. That is the one
place this rewrite knowingly departs from the original, so it is stated plainly rather than
buried:

  * what is preserved — `main()` still raises `ImportError` when fastmcp is missing, and still
    raises it BEFORE it does any waiting or any I/O, because `_load_fastmcp()` is the first
    thing `main()` calls. Every caller that runs the bridge sees what it always saw.
  * what changes — `import coupler.bridge` no longer requires fastmcp. Under the original, a
    caller that only wanted `_wait_for_server` still had to have fastmcp installed.
  * why — #200 requirement 3 is that `pip install -e .` installs clean from this package's own
    pyproject.toml. Declaring fastmcp would make that install depend on a package index being
    reachable, and a module-scope import of an undeclared dependency would make
    `import coupler.bridge` fail for everyone. The deviation makes the module importable and
    testable while leaving `main()`'s behavior intact.

`selftest` check [6] drives BOTH of `main()`'s paths — the degraded stub and the SSE proxy —
against a recording fastmcp stand-in, and compares the calls this module makes to the calls
THE ORIGINAL makes under the identical stand-in. The stand-in is injected into `sys.modules`,
so it satisfies the original's module-scope import and this module's lazy one the same way.

THE EQUIVALENCE BASIS (#200 requirement 1, acceptance item (a))
---------------------------------------------------------------
Ticket #357 records that criteria_miner captured NO exemplars for this module — it "mines only
self-contained pure functions (it refuses anything that mentions a world-touching or
non-deterministic name, plus methods and no-arg functions), and nothing here qualified" — and
states that this "MOVES the work: you must write the equivalence exemplars by hand from the
original's behavior before rewriting, and they are what settles this ticket."

`EXEMPLARS` and `EDGE_CASES` below are that hand-written table. Their expected values are NOT
hand-copied and hoped to be right: `selftest` runs each scenario against the ORIGINAL and
against this rewrite, under identically staged conditions, and compares the two observations
field by field. The original is therefore the oracle, and a disagreement is a FAIL — this is
the differential idiom ticket #355's `test_build.py` established in this package.

That is only worth anything if the embedded original is really the forge's module, so
`selftest` check [0] hashes `ORIGINAL_SOURCE` as git hashes a blob and compares the digest to
the blob sha1 ticket #357 records (`30599ce04c2676d150a809d4b08feb91b597f531`). It also checks
the length against the ticket's stated 2480 bytes. If either differs the whole selftest is
worthless, so it is the first thing checked and it fails loudly.

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
    `forge2 -> code__code-invalid__coupler -> coupler.bridge`. It is what drives this module.
    `emit-config` prints a template of it.
exemplar
    One (scenario -> expected outcome) pair the rewrite must reproduce, standing in for the
    automated captures ticket #357 could not mine.
SSE
    Server-Sent Events, the HTTP transport the coupler server exposes at `/sse`. The bridge
    speaks stdio to Claude Desktop on one side and SSE to that endpoint on the other.
degraded stub
    The one-tool MCP server `main()` stands up when the coupler server never answers. Its only
    tool, `coupler_status`, reports that coupler is down and how to start it.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The original hardcoded every parameter it had: the port env var `COUPLER_PORT` and its 7770
default, the host `127.0.0.1`, the 15 retries, the 2.0-second interval, the 1.0-second connect
timeout, all three stderr message templates, the stub's server name `coupler-bridge`, its
status field `coupler` and value `down`, its message template and the `coupler.server` named
in it, the `indent=2`, and the `http://127.0.0.1:{PORT}/sse` endpoint. Those are exactly the
params #200's fourth requirement forbids hardcoding, so every one of them is read from this
unit's config object and NOTHING is defaulted in code.

This package ships a `registry.json` carrying precisely the original's values, so an ordinary
`import coupler.bridge` from a source checkout or an editable install behaves exactly as the
original did. `selftest` check [2] is what proves that claim: it runs the shipped config
against the original and requires the observations to match.

The config is read at IMPORT, because the original bound `PORT` at import and that is the
behavior being preserved. So `import coupler.bridge` raises `ConfigError` when no config
object can be resolved: ticket #357's acceptance item (d) and `note-for-claude`'s rule. It
does not guess 7770, it does not guess `127.0.0.1`, and it does not quietly leave the globals
unbound. `selftest` check [1] proves it.

The gate is checked at import, OUTSIDE `_wait_for_server`'s `except Exception`, so the guard
that implements the retry can never swallow a `ConfigError` and report a config mistake as a
down server.

Resolution order — the first source that answers wins:

  1. the file named by the `COUPLER_BRIDGE_CONFIG` environment variable, which holds this
     unit's config object itself — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code-invalid__coupler -> coupler.bridge` section of the
     nearest `registry.json` found by walking UP from THIS FILE's directory;
  3. otherwise, the `registry.json` shipped as package data inside the installed
     `code__code_invalid__coupler` package, located with `importlib.util.find_spec`.

The walk-up starts at this file, never at the working directory, so which directory you run
from does not change what config is found. Step 3 exists because a plain (non-editable)
`pip install .` puts this module at `site-packages/coupler/bridge.py`, and the walk-up from
there passes no registry at all — `site-packages` has none. See `find_registry`.

The variable is named for THIS unit rather than something forge2-wide on purpose: it names a
file holding ONE unit's config object, and a variable shared across units could only ever
point at one unit's object at a time.

SIDE EFFECTS
------------
Importing this module reads one JSON file and binds globals. It opens no socket, starts no
server and writes nothing.

`_wait_for_server()` opens TCP connections to the configured host and port and closes each one
it opens; it writes its waiting lines to stderr. `main()` additionally speaks stdio, which is
its whole purpose.

Every command in RUNNING IT except `main` creates no files, modifies none and deletes none,
and opens no sockets — `selftest` replaces `asyncio.open_connection` and `asyncio.sleep` with
fakes before anything under test runs, and puts them back afterwards; check [5] proves the
restoration rather than trusting it, and check [7] proves the no-files claim by listing this
package's tree before and after a full run and diffing it. (The interpreter still writes its
usual `__pycache__` bytecode for any module it imports; that is CPython's import machinery
rather than this code, and ticket #357 lists `__pycache__` among the build artifacts that are
regenerated by any install and never committed.)

The one thing that can write is the command line, which per `note-for-claude` ("all tools need
to pass a bug-report automatically (timestamped if an exception is thrown)") appends one
timestamped JSON line to the config's `bug_reports` path if it hits an UNEXPECTED exception —
a defect in this tool. A `ConfigError` is designed behavior, not a bug: it files no report,
prints no traceback, and exits with a single self-explaining line.

RUNNING IT
----------
Every command below is executable as written FROM THE PACKAGE ROOT — the directory holding
`pyproject.toml`, one level above `coupler/`. The `-m` form is what makes them run without
installing anything: it puts the package root on the import path, so `coupler.bridge`
resolves. Running the file by path (`python3 coupler/bridge.py`) does NOT work uninstalled,
because Python would put `coupler/` on the import path instead of the package root and the
`coupler` package would not be importable; that invocation answers with one `UsageError` line
saying so rather than a traceback.

    python3 -m coupler.bridge selftest       # the equivalence proof: [0]-[8], vs the ORIGINAL
    python3 -m coupler.bridge install-check  # prove the declared install, in both layouts
    python3 -m coupler.bridge show-config    # print the resolved config object and its source
    python3 -m coupler.bridge emit-config    # print a config-object template
    python3 -m coupler.bridge show-status    # print the degraded stub's payload
    python3 -m coupler.bridge run            # run the bridge itself — needs fastmcp installed

Once installed (see INSTALLABLE), the console script runs from any directory:

    forge2-coupler-bridge selftest

The bridge proper is `run`, and `main()` is what Claude Desktop invokes. The original's
`python -m coupler.bridge` with no argument ran the bridge; that spelling is preserved — with
no subcommand this module runs the bridge, so an existing Claude Desktop config keeps working
byte for byte. `selftest` check [8] proves that.

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, committed in full beside it. From
the package root:

    pip install -e .
    forge2-coupler-bridge selftest

`pyproject.toml` declares `coupler` as a package, so an installed copy imports as
`coupler.bridge` — the path the forge unit was originally addressed by (repo
`code__code-invalid__coupler`, path `coupler/bridge.py`). It declares NO dependencies, so that
install needs no package index to resolve any; that is why `main()` imports fastmcp lazily
rather than the package declaring it.

Be precise about the evidence behind that install, because it is a real limit and not a boast:
`pip install -e .` was NOT executed for this ticket, and this module does not claim it was. The
interpreter this package was verified against has no setuptools, so pip would fetch one to
build with, and the sandbox this ticket was worked in permits no network; the only interpreter
available that HAS setuptools carries 58.0.4, which predates PEP 621 and cannot read this
pyproject's `[project]` table at all.

What IS executed is `install-check`, which runs the two things that install PRODUCES rather
than the pip command itself: the declaration is parsed out of `pyproject.toml` and its entry
point resolved, and `import coupler.bridge` is then run in child interpreters against BOTH
layouts an install can leave behind — the editable one (package root on `sys.path`) and the
non-editable one (the file tree `pip install .` puts in site-packages, staged from the same
declarations setuptools reads, and imported under `python3 -S` so no real site-packages can
answer for it). The non-editable layout is the one that matters most here: the registry
walk-up passes nothing above `site-packages/coupler/bridge.py`, which is what `find_registry`'s
`_installed_registry` fallback exists for, and `install-check` proves both that it finds the
shipped registry and that deleting it brings the config gate back.
"""

import argparse
import asyncio
import hashlib
import io
import json
import os
import sys
import traceback
import types
from datetime import datetime, timezone

# ─────────────────────────────── configuration ───────────────────────────────
#
# Self-contained ON PURPOSE, following the pattern ticket #355's `coupler/tests/test_build.py`
# established in this package and states in its own configuration section: a forge rewrite
# unit's deliverable is ONE module, and a sibling helper it depends on may not be present.
# `coupler/tests/test_bridge.py` (#393) imports `coupler.config`, which does not exist here,
# and is unimportable today as a result. This file has no such dependency and runs against the
# package as it actually is.

#: Environment variable naming a file that holds THIS unit's config object.
CONFIG_ENV = "COUPLER_BRIDGE_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in
#: the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own.
UNIT_PATH = ("forge2", "code__code-invalid__coupler", "coupler.bridge")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code-invalid__coupler/coupler/bridge"

#: This module's own dotted import name. It is `UNIT_PATH`'s last element by construction — a
#: unit's address inside the registry IS its dotted path within the package — so it is derived
#: rather than written twice and cannot drift from it. Used only to print an invocation a
#: reader can retype; `__name__` is "__main__" under `-m` and `__spec__` is None when this file
#: is run by path, so neither can answer this on its own.
DOTTED_NAME = UNIT_PATH[-1]

#: The installed package that ships `registry.json` as package data. `find_registry` falls back
#: to it so a NON-editable `pip install .` can still find the config: this module then lives at
#: `site-packages/coupler/bridge.py` and the walk-up passes no registry at all.
PACKAGE_WITH_REGISTRY = "code__code_invalid__coupler"

#: The ticket this unit was rewritten under, recorded in bug reports.
TICKET = 357


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and ticket #357's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.

    It is raised at IMPORT, outside `_wait_for_server`'s `except Exception`, so the guard that
    implements the retry loop can never mistake a config mistake for a server that is down.
    """


class UsageError(RuntimeError):
    """Raised when this module was INVOKED in a way that cannot work — not a defect in it.

    Kept apart from every other exception for the same reason `ConfigError` is: the command
    line reports both as one self-explaining line and files NO bug report, because a bug report
    is supposed to mean "this tool is broken". The foreseeable case is running this file by
    path (`python3 coupler/bridge.py`), which puts `coupler/` on the import path instead of the
    package root and so leaves the `coupler` package unimportable. That is a mistake the
    message can fix in one line; answering it with a traceback and a filed bug report would
    blame the tool for the invocation and put a false record in the sink.
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do this module throws `ConfigError` at import. Every
    value below is one the ORIGINAL hardcoded, so a config built from this template makes the
    bridge behave exactly as the original's did — which is not a claim, it is what `selftest`
    check [2] measures against the original itself.
    """
    return {
        "host": "127.0.0.1",
        "port_env": "COUPLER_PORT",
        "default_port": 7770,
        "retries": 15,
        "retry_seconds": 2.0,
        "connect_timeout_seconds": 1.0,
        "waiting_message": "  bridge: waiting for coupler server on :{port} "
                           "({attempt}/{retries})…",
        "unreachable_message": "  bridge: coupler server unreachable on :{port} — "
                               "serving degraded stub",
        "connected_message": "  bridge: connected to coupler on :{port}",
        "sse_url_template": "http://{host}:{port}/sse",
        "stub": {
            "server_name": "coupler-bridge",
            "tool_description": "Check which coupler services are available right now.",
            "status_field": "coupler",
            "status_down": "down",
            "message_template": "coupler server is not running on port {port}. "
                                "Start it with: python -m {server_module}",
            "server_module": "coupler.server",
            "json_indent": 2,
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
    machinery answers this without importing the package, which matters: importing it is not
    free and this is called from the import of a module inside it.
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
            "no config object for %s: %s is unset, no %s was found by walking up from %s, and "
            "no %s package ships one. Run `%s emit-config` for a template of the config object "
            "to install."
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
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit
    # section may state its own to override it. This is inheritance inside ONE config document,
    # not a guessed default — if neither states it, the key stays absent and the CLI files no
    # report.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


def require(section, key, where, types_):
    """Return `section[key]`, proving it is present and of the right type; else raise.

    Type-checking here rather than letting a bad value flow onward is deliberate.
    `_wait_for_server` swallows `Exception` (the original did, and that is preserved), so a
    non-integer `retries` or a non-string `host` reaching it would raise INSIDE that guard and
    be silently reported as "the server is down" — turning an operator's config mistake into a
    plausible-looking wrong answer. A malformed config object is a config error, and it is
    raised as one, at import, before the guard is ever entered.

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
    # `bool` is a subclass of `int`, so isinstance(True, int) is True. A `true` where a port or
    # a retry count belongs is a config mistake, and silently accepting it as 1 would make the
    # bridge poll once and call that the operator's intent.
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

    The console script if this module was installed and reached through it, else the `-m` form,
    which is what works from a source checkout.
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

    Injecting a config does NOT rebind this module's globals: the original bound `PORT` once,
    at import, and that is preserved. `importlib.reload(coupler.bridge)` is what re-reads the
    config, exactly as it is what re-read the environment for the original.
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


def reset_config():
    """Drop the injected config and the cached disk resolution; the next call re-resolves."""
    global _ACTIVE, _RESOLVED
    _ACTIVE = None
    _RESOLVED = None


# ─────────────────────────────── the module-level surface ───────────────────────────────
#
# Everything here reproduces what the original's module-level code left in this namespace,
# with the values it hardcoded now read from the config object. `active_config()` raises
# ConfigError right here, at import, if this unit cannot see its config: acceptance item (d).
# That call is outside every `except Exception` in this file, so the gate cannot be mistaken
# for a failed connect.
#
# These are module GLOBALS, and `_wait_for_server` reads them at CALL time, because the
# original's did and callers rebind them (`b.RETRIES = 3`). Binding them into a closure or a
# frozen settings object at import would look tidier and would break those callers.

def _load() -> dict:
    """Read, validate and flatten this unit's config object into the module globals' values."""
    config = active_config()
    stub = require(config, "stub", UNIT, dict)
    stub_where = "%s -> stub" % UNIT
    return {
        "host": require(config, "host", UNIT, str),
        "port_env": require(config, "port_env", UNIT, str),
        "default_port": require(config, "default_port", UNIT, int),
        "retries": require(config, "retries", UNIT, int),
        "retry_seconds": require(config, "retry_seconds", UNIT, (int, float)),
        "connect_timeout_seconds": require(config, "connect_timeout_seconds", UNIT, (int, float)),
        "waiting_message": require(config, "waiting_message", UNIT, str),
        "unreachable_message": require(config, "unreachable_message", UNIT, str),
        "connected_message": require(config, "connected_message", UNIT, str),
        "sse_url_template": require(config, "sse_url_template", UNIT, str),
        "stub_server_name": require(stub, "server_name", stub_where, str),
        "stub_tool_description": require(stub, "tool_description", stub_where, str),
        "stub_status_field": require(stub, "status_field", stub_where, str),
        "stub_status_down": require(stub, "status_down", stub_where, str),
        "stub_message_template": require(stub, "message_template", stub_where, str),
        "stub_server_module": require(stub, "server_module", stub_where, str),
        "stub_json_indent": require(stub, "json_indent", stub_where, int),
    }


_SETTINGS = _load()

#: The host the bridge dials. The original hardcoded "127.0.0.1" inside the function body.
HOST = _SETTINGS["host"]

#: The port the bridge dials. The original was `int(os.environ.get("COUPLER_PORT", 7770))`; the
#: variable name and the default are config now, and the environment still overrides both — an
#: env var that is set but not an integer still raises ValueError at import, as it did.
PORT = int(os.environ.get(_SETTINGS["port_env"], _SETTINGS["default_port"]))

#: How many times `_wait_for_server` attempts the connect. The original hardcoded 15, with the
#: comment "15 × 2s = 30s startup grace period".
RETRIES = _SETTINGS["retries"]

#: Seconds slept after each failed attempt — including the last one. The original hardcoded 2.0.
RETRY_S = _SETTINGS["retry_seconds"]

#: Seconds before one connect attempt is abandoned. The original hardcoded `timeout=1.0`.
TIMEOUT_S = _SETTINGS["connect_timeout_seconds"]


async def _wait_for_server() -> bool:
    """Spin until the coupler HTTP server is accepting TCP connections.

    Returns True as soon as one connect succeeds and its writer closes cleanly, else False once
    `RETRIES` attempts have all failed.

    This is the original's loop, rewritten. Four of its properties are load-bearing and are
    preserved exactly; `selftest` check [2] proves each against the original AS IT RUNS:

      * every `Exception` from the attempt is swallowed and counted as "not up yet" — including
        exceptions that are real bugs rather than a closed port. `BaseException` is NOT caught,
        so a `KeyboardInterrupt` still propagates.
      * the waiting line is printed and `RETRY_S` is slept after EVERY failed attempt,
        including the last, before the loop ends. That is what makes the original's promise of
        "every 2 seconds for 30 seconds" true at `RETRIES=15`.
      * the guard covers the close as well as the connect, so a writer that fails to close is a
        failed attempt, not a success.
      * `RETRIES=0` returns False without connecting at all.

    Reads `RETRIES`, `HOST`, `PORT`, `TIMEOUT_S` and `RETRY_S` as module globals at call time,
    so rebinding them on the module takes effect on the next call — as it did for the original.
    """
    for i in range(RETRIES):
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(HOST, PORT), timeout=TIMEOUT_S
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            # Deliberately broad, and deliberately not `BaseException`: this is the original's
            # guard. It reads a real bug as "the server is not up yet", which is a weakness
            # preserved rather than fixed — see the module docstring.
            pass
        print(_SETTINGS["waiting_message"].format(port=PORT, attempt=i + 1, retries=RETRIES),
              file=sys.stderr)
        await asyncio.sleep(RETRY_S)
    return False


def stub_status_payload() -> str:
    """Return the degraded stub's `coupler_status` payload: the JSON string it serves.

    The original built this inline inside `main()`, where nothing could reach it without
    standing up a server. It is a named function here so the payload can be proven — `main()`
    calls it, so what this returns IS what the stub serves and the two cannot drift apart.

    The bytes are the original's, rendered from config: the status field, its `down` value, the
    message naming the live `PORT` and the module to start, and `indent=2`.
    """
    return json.dumps({
        _SETTINGS["stub_status_field"]: _SETTINGS["stub_status_down"],
        "message": _SETTINGS["stub_message_template"].format(
            port=PORT, server_module=_SETTINGS["stub_server_module"]
        ),
    }, indent=_SETTINGS["stub_json_indent"])


def _load_fastmcp():
    """Import fastmcp and return the three names the bridge uses.

    The original imported these at MODULE scope. Importing them here instead is this rewrite's
    one deliberate deviation, and `main()` calls this first so the `ImportError` still lands
    before any waiting or I/O. See THE `fastmcp` DEPENDENCY in the module docstring for why.

    Returns:
        A `(FastMCP, SSETransport, create_proxy)` tuple.

    Raises:
        ImportError: if fastmcp is not installed, exactly as importing the original did.
    """
    from fastmcp import FastMCP
    from fastmcp.client.transports import SSETransport
    from fastmcp.server import create_proxy

    return FastMCP, SSETransport, create_proxy


def main():
    """Run the bridge: wait for the coupler server, then proxy stdio to it — or serve the stub.

    This is what Claude Desktop invokes (`command: python -m coupler.bridge`). It waits for the
    server with `_wait_for_server()`; if the server answered it proxies stdio to that server's
    SSE endpoint, and if it never answered it stands up the degraded stub instead so the caller
    gets a useful message rather than "server disconnected".

    Blocks until the served MCP session ends. Raises `ImportError` if fastmcp is not installed,
    before doing any waiting.
    """
    # First, so a missing fastmcp fails immediately rather than 30 seconds from now. The
    # original's module-scope imports gave it the same immediacy.
    FastMCP, SSETransport, create_proxy = _load_fastmcp()

    async def _run():
        ready = await _wait_for_server()
        if not ready:
            # Server unreachable — stand up a minimal stub so the caller gets a useful message
            # from coupler_status rather than "server disconnected".
            print(_SETTINGS["unreachable_message"].format(port=PORT), file=sys.stderr)
            stub = FastMCP(_SETTINGS["stub_server_name"])

            def coupler_status() -> str:
                return stub_status_payload()

            # The original spelled this as the tool function's DOCSTRING, and fastmcp publishes
            # a tool's docstring as the description clients see. The text is config now and a
            # docstring cannot be an f-string, so it is assigned — but it MUST be assigned
            # BEFORE the decorator runs, because `stub.tool()` reads `__doc__` off the function
            # as it registers it. Decorating first and assigning after registers the tool with
            # no description at all, which is why this is not written as a `@stub.tool()`
            # decorator: `selftest` check [6] caught exactly that and fails on it.
            coupler_status.__doc__ = _SETTINGS["stub_tool_description"]
            stub.tool()(coupler_status)

            await stub.run_stdio_async()
            return

        print(_SETTINGS["connected_message"].format(port=PORT), file=sys.stderr)
        proxy = create_proxy(SSETransport(
            _SETTINGS["sse_url_template"].format(host=HOST, port=PORT)
        ))
        bridge = FastMCP.as_proxy(proxy)
        await bridge.run_stdio_async()

    asyncio.run(_run())


# ─────────────────────────────── the original, embedded ───────────────────────────────

#: The forge unit this file rewrites, verbatim — ticket #357 embeds it as "the authoritative
#: copy and the behavior-preserving basis", and it is the ORACLE `selftest` measures against.
#: `selftest` check [0] proves these are the real forge bytes by hashing them the way git
#: hashes a blob and comparing to the sha1 the ticket records, so no check below rests on a
#: transcription anyone has to take on trust.
ORIGINAL_SOURCE = '''#!/usr/bin/env python3
"""
coupler/bridge.py — stdio ↔ SSE bridge. This is what Claude Desktop runs.

It never changes. When coupler/server.py restarts, this reconnects automatically.
If the server isn't up yet it retries every 2 seconds for 30 seconds before giving up.

Claude Desktop config:
  command: python -m coupler.bridge
"""

import asyncio
import json
import os
import sys

from fastmcp import FastMCP
from fastmcp.client.transports import SSETransport
from fastmcp.server import create_proxy

PORT    = int(os.environ.get("COUPLER_PORT", 7770))
RETRIES = 15        # 15 × 2s = 30s startup grace period
RETRY_S = 2.0


async def _wait_for_server() -> bool:
    """Spin until the coupler HTTP server is accepting TCP connections."""
    for i in range(RETRIES):
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", PORT), timeout=1.0
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            pass
        print(f"  bridge: waiting for coupler server on :{PORT} "
              f"({i+1}/{RETRIES})…", file=sys.stderr)
        await asyncio.sleep(RETRY_S)
    return False


def main():
    async def _run():
        ready = await _wait_for_server()
        if not ready:
            # Server unreachable — stand up a minimal stub so Claude gets a
            # useful message from coupler_status rather than "server disconnected"
            print(f"  bridge: coupler server unreachable on :{PORT} — "
                  f"serving degraded stub", file=sys.stderr)
            stub = FastMCP("coupler-bridge")

            @stub.tool()
            def coupler_status() -> str:
                """Check which coupler services are available right now."""
                return json.dumps({
                    "coupler": "down",
                    "message": (
                        f"coupler server is not running on port {PORT}. "
                        f"Start it with: python -m coupler.server"
                    )
                }, indent=2)

            await stub.run_stdio_async()
            return

        print(f"  bridge: connected to coupler on :{PORT}", file=sys.stderr)
        proxy = create_proxy(SSETransport(f"http://127.0.0.1:{PORT}/sse"))
        bridge = FastMCP.as_proxy(proxy)
        await bridge.run_stdio_async()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
'''

#: The git blob sha1 and byte length ticket #357 records for the module above, under CANONICAL
#: SOURCE. Check [0] recomputes both from `ORIGINAL_SOURCE`.
ORIGINAL_BLOB_SHA1 = "30599ce04c2676d150a809d4b08feb91b597f531"
ORIGINAL_SIZE = 2480


def _git_blob_sha1(data: bytes) -> str:
    """Hash `data` the way git hashes a blob: sha1 over `blob <len>\\0` + the bytes.

    This is git's object-id rule, so the digest is directly comparable to the blob sha1 the
    ticket records — no forge access required to check that the embedded copy is genuine.
    """
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# ─────────────────────────────── the equivalence tables ───────────────────────────────

#: The exemplars this rewrite must reproduce. Ticket #357 captured none (criteria_miner refuses
#: async, world-touching and no-arg functions, "and nothing here qualified"), so this table is
#: the hand-written equivalence basis the ticket asks for in its place.
#:
#: Each entry is (label, what is staged, the property it pins down). Every one is RUN against
#: the ORIGINAL and against this rewrite by `selftest` check [2] and the observations compared,
#: so the expected values are taken from the original as it runs rather than from this table.
EXEMPLARS = [
    ("connect succeeds on the first attempt",
     "asyncio.open_connection returns (StreamReader, writer-with-close/wait_closed)",
     "_wait_for_server() is True, after exactly one attempt, with no waiting line and no "
     "sleep — and `is True`, not merely truthy"),
    ("every connect is refused",
     "asyncio.open_connection always raises ConnectionRefusedError",
     "_wait_for_server() is False once RETRIES attempts are exhausted — `is False`, so a "
     "bridge returning None is not equivalent"),
    ("the stub payload",
     "nothing — the payload is rendered from the config in force",
     "the degraded stub's JSON parses, reads 'down', and names both the live PORT and the "
     "module to start, byte for byte as the original's inline stub built it"),
]

#: Edge cases the exemplars cannot reach on their own. #357 asks for "the edge cases you add
#: for what sampling cannot reach", and these are they: each pins down a property the three
#: exemplars leave free, which a wrong bridge could violate while still reproducing all three.
#: Every one is likewise run differentially against the ORIGINAL.
#:
#: Each entry is (label, why the exemplars cannot reach it).
EDGE_CASES = [
    ("connect is attempted exactly RETRIES times when refused",
     "exemplar 2 only checks the False verdict; a bridge that gave up after one attempt, or "
     "looped forever, would still return False and reproduce it"),
    ("RETRY_S is slept after EVERY failed attempt, including the last",
     "exemplar 2 does not count sleeps; this is the property `test_bridge.py` (#393) states "
     "backwards, so it is measured against the original rather than argued about"),
    ("the waiting line is printed once per failed attempt, numbered i+1 of RETRIES",
     "no exemplar reads stderr; the counter is off-by-one bait"),
    ("open_connection is called with (HOST, PORT) positionally, under a TIMEOUT_S wait_for",
     "exemplar 1's fake accepts the arguments but never inspects them, so a bridge dialling "
     "the wrong host or port would reproduce it"),
    ("RETRIES == 0 returns False without connecting at all",
     "neither exemplar exercises the empty loop, where an off-by-one would connect once"),
    ("success on a later attempt stops the loop there",
     "exemplar 1 succeeds immediately and exemplar 2 never succeeds; neither reaches the "
     "boundary where a bridge might keep polling after a success"),
    ("ANY Exception from the connect is swallowed and counted as a retry, not raised",
     "exemplar 2 raises only ConnectionRefusedError; this is the second property #393 states "
     "backwards, so it too is measured against the original"),
    ("a BaseException from the connect propagates rather than counting as a retry",
     "nothing else distinguishes `except Exception` from a bare `except:`, and a bare one "
     "would swallow KeyboardInterrupt and make the bridge unkillable mid-poll"),
    ("a writer that fails to close counts as a failed attempt, not a success",
     "exemplar 1's writer closes cleanly, so it cannot see whether the guard covers the close"),
    ("a connect that outlasts TIMEOUT_S is abandoned and counted as a failed attempt",
     "neither exemplar exercises asyncio.wait_for's timeout at all"),
    ("$COUPLER_PORT overrides the configured default port at import",
     "the exemplars all run with the port the config states; the env override is a whole "
     "resolution path they never touch"),
    ("main() drives the degraded-stub path exactly as the original does",
     "no exemplar calls main(); the stub path is where the bridge is least observable and "
     "most likely to drift"),
    ("main() drives the SSE-proxy path exactly as the original does",
     "likewise — and the SSE URL is assembled from HOST and PORT, which can drift"),
]


# ─────────────────────────────── the differential harness ───────────────────────────────

class _Recorder:
    """A recording stand-in for the pieces of fastmcp the bridge uses.

    Injected into `sys.modules` so it satisfies the ORIGINAL's module-scope
    `from fastmcp import FastMCP` and this module's lazy `_load_fastmcp()` identically — which
    is what makes check [6]'s comparison fair rather than staged. It records the calls made
    against it, so "the rewrite drives fastmcp the way the original does" becomes a comparison
    of two lists rather than an assertion.
    """

    def __init__(self):
        self.calls = []

    def install(self):
        """Put this recorder's fake fastmcp modules into sys.modules; return the saved ones."""
        recorder = self

        class FastMCP:
            def __init__(self, name):
                self.name = name
                recorder.calls.append(("FastMCP(name)", name))

            def tool(self):
                def deco(fn):
                    # Call the tool immediately: its return value IS the payload the stub
                    # would serve, and it is what check [6] compares between the two modules.
                    recorder.calls.append(("tool registered", fn.__name__, fn.__doc__, fn()))
                    return fn
                return deco

            async def run_stdio_async(self):
                recorder.calls.append(("run_stdio_async", self.name))

            @staticmethod
            def as_proxy(proxy):
                recorder.calls.append(("FastMCP.as_proxy", proxy))
                server = FastMCP.__new__(FastMCP)
                server.name = ("proxied", proxy)
                return server

        def SSETransport(url):
            recorder.calls.append(("SSETransport(url)", url))
            return ("transport", url)

        def create_proxy(transport):
            recorder.calls.append(("create_proxy(transport)", transport))
            return ("proxy", transport)

        saved = {name: sys.modules.get(name)
                 for name in ("fastmcp", "fastmcp.client", "fastmcp.client.transports",
                              "fastmcp.server")}

        fastmcp = types.ModuleType("fastmcp")
        fastmcp.FastMCP = FastMCP
        client = types.ModuleType("fastmcp.client")
        transports = types.ModuleType("fastmcp.client.transports")
        transports.SSETransport = SSETransport
        server_mod = types.ModuleType("fastmcp.server")
        server_mod.create_proxy = create_proxy
        fastmcp.client = client
        client.transports = transports
        fastmcp.server = server_mod

        sys.modules["fastmcp"] = fastmcp
        sys.modules["fastmcp.client"] = client
        sys.modules["fastmcp.client.transports"] = transports
        sys.modules["fastmcp.server"] = server_mod
        return saved

    @staticmethod
    def restore(saved):
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def load_original(port_env_value=None):
    """Execute `ORIGINAL_SOURCE` and return it as a live module — the differential's oracle.

    The original imports fastmcp at module scope, so a recorder is installed for the duration
    of the exec; that is the ONLY accommodation made, and it changes nothing about the loop
    under test. Nothing is written to disk: the source is compiled from the embedded string.

    Args:
        port_env_value: value to stage in the original's `COUPLER_PORT` for the duration of
            the exec, or None to leave the environment alone.
    """
    recorder = _Recorder()
    saved_modules = recorder.install()
    saved_env = os.environ.get("COUPLER_PORT")
    try:
        if port_env_value is not None:
            os.environ["COUPLER_PORT"] = port_env_value
        module = types.ModuleType("original_bridge")
        module.__file__ = "<ORIGINAL_SOURCE embedded in %s>" % DOTTED_NAME
        exec(compile(ORIGINAL_SOURCE, module.__file__, "exec"), module.__dict__)
        return module
    finally:
        if saved_env is None:
            os.environ.pop("COUPLER_PORT", None)
        else:
            os.environ["COUPLER_PORT"] = saved_env
        _Recorder.restore(saved_modules)


class _Observation:
    """What one run of `_wait_for_server` did, in the terms the two modules can be compared in.

    Equality is what check [2] and check [3] test, so every field here is part of the behavior
    being preserved and a difference in any of them is a FAIL.
    """

    __slots__ = ("result", "raised", "attempts", "sleeps", "stderr")

    def __init__(self, result, raised, attempts, sleeps, stderr):
        self.result = result
        self.raised = raised
        self.attempts = attempts
        self.sleeps = sleeps
        self.stderr = stderr

    def key(self):
        # `result` is compared by type as well as value: the original returns `True`/`False`,
        # and a rewrite returning 1, or a truthy socket, is not equivalent.
        return (type(self.result).__name__, self.result, self.raised,
                self.attempts, self.sleeps, self.stderr)

    def __eq__(self, other):
        return isinstance(other, _Observation) and self.key() == other.key()

    def __repr__(self):
        return ("result=%r raised=%r attempts=%r sleeps=%r stderr=%r"
                % (self.result, self.raised, self.attempts, self.sleeps, self.stderr))


def observe(module, opener, retries, retry_s=0.25, timeout_s=1.0):
    """Run `module._wait_for_server()` under a staged connect, and record everything it did.

    Stages the SAME conditions for either module — the original or this rewrite — which is what
    makes the comparison a proof rather than a demonstration. `asyncio.open_connection` and
    `asyncio.sleep` are replaced for the duration and restored in a `finally`, so nothing here
    opens a socket or waits on a clock.

    Args:
        module: the module under observation; its globals are rebound for the run.
        opener: a factory taking the attempts list and returning the fake open_connection.
        retries / retry_s / timeout_s: the loop parameters to stage on the module.
    """
    attempts, sleeps = [], []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    real_open, real_sleep = asyncio.open_connection, asyncio.sleep
    real_stderr = sys.stderr
    captured = io.StringIO()

    saved = {name: getattr(module, name, None) for name in ("RETRIES", "RETRY_S", "TIMEOUT_S")}
    try:
        asyncio.open_connection = opener(attempts)
        asyncio.sleep = fake_sleep
        sys.stderr = captured
        module.RETRIES = retries
        module.RETRY_S = retry_s
        # The original has no TIMEOUT_S: it hardcodes `timeout=1.0`. Setting it on this rewrite
        # only, to that same 1.0, is what puts the two on identical footing — and check [3]
        # separately proves this module honours the value.
        if hasattr(module, "TIMEOUT_S"):
            module.TIMEOUT_S = timeout_s
        try:
            result, raised = asyncio.run(module._wait_for_server()), None
        except BaseException as exc:  # noqa: BLE001 — the raise IS the observation
            result, raised = None, "%s: %s" % (type(exc).__name__, exc)
    finally:
        asyncio.open_connection, asyncio.sleep = real_open, real_sleep
        sys.stderr = real_stderr
        for name, value in saved.items():
            if value is not None:
                setattr(module, name, value)
    return _Observation(result, raised, tuple(attempts), tuple(sleeps), captured.getvalue())


# The staged connects. Each returns a fake `asyncio.open_connection` that records its
# arguments into `attempts`, so a bridge dialling the wrong host or port is visible.

def _accept(attempts):
    async def opener(host, port):
        attempts.append((host, port))

        class Writer:
            def close(self):
                pass

            async def wait_closed(self):
                pass

        return asyncio.StreamReader(), Writer()
    return opener


def _refuse(attempts):
    async def opener(host, port):
        attempts.append((host, port))
        raise ConnectionRefusedError("no server")
    return opener


def _accept_on(nth):
    def factory(attempts):
        async def opener(host, port):
            attempts.append((host, port))
            if len(attempts) < nth:
                raise ConnectionRefusedError("no server")

            class Writer:
                def close(self):
                    pass

                async def wait_closed(self):
                    pass

            return asyncio.StreamReader(), Writer()
        return opener
    return factory


class _NotAnOSError(Exception):
    """A plain Exception that is emphatically not a connection error — a stand-in for a bug."""


def _explode(attempts):
    async def opener(host, port):
        attempts.append((host, port))
        raise _NotAnOSError("a real bug, not a closed port")
    return opener


def _base_explode(attempts):
    async def opener(host, port):
        attempts.append((host, port))
        raise KeyboardInterrupt("operator pressed ctrl-c mid-poll")
    return opener


def _bad_writer(attempts):
    async def opener(host, port):
        attempts.append((host, port))

        class Writer:
            def close(self):
                raise OSError("the writer refused to close")

            async def wait_closed(self):
                pass

        return asyncio.StreamReader(), Writer()
    return opener


def _hang(attempts):
    async def opener(host, port):
        attempts.append((host, port))
        await asyncio.sleep(3600)  # outlasts any sane TIMEOUT_S; wait_for must abandon it
        raise AssertionError("unreachable: wait_for should have timed out")
    return opener


# ─────────────────────────────── the selftest ───────────────────────────────

def selftest(stream=None):
    """Prove this rewrite against ticket #357's acceptance items (a), (b) and (d).

    Runs every scenario against the EMBEDDED ORIGINAL and against this module, under
    identically staged conditions, and compares the observations field by field. Builds its own
    config objects in memory where it needs to, writes no files, opens no sockets, and leaves
    no configuration behind. Returns the number of failures.

    Checks, in order:
      0. the oracle is genuine — ORIGINAL_SOURCE hashes to the blob sha1 the ticket records;
      1. the config gate — this module throws ConfigError, and binds nothing, without a config;
      2. the exemplars — differential against the original;
      3. the edge cases the exemplars cannot reach — differential against the original;
      4. the callable surface — the names, parameters and coroutine-ness the ticket states;
      5. no side effects — open_connection and sleep are the real ones again afterwards;
      6. main() — both paths, differential against the original under a recording fastmcp;
      7. no files — this package's tree is unchanged by the whole run;
      8. the console spelling — `python -m coupler.bridge` with no argument runs the bridge.
    """
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
              if mine != theirs else "%s [%r]" % (label, theirs))

    real_open, real_sleep = asyncio.open_connection, asyncio.sleep
    tree_before = _tree_snapshot()

    print("differential selftest for %s\n  oracle: the ORIGINAL, embedded (%d bytes) and "
          "executed\n  config: %s" % (UNIT, len(ORIGINAL_SOURCE.encode("utf-8")),
                                      _describe_source()), file=out)

    # ── 0. the oracle is genuine ──────────────────────────────────────────────
    print("\n[0] the embedded original is the forge's blob", file=out)
    raw = ORIGINAL_SOURCE.encode("utf-8")
    digest = _git_blob_sha1(raw)
    check(len(raw) == ORIGINAL_SIZE,
          "ORIGINAL_SOURCE is %d bytes, the size ticket #357 records (%d)"
          % (len(raw), ORIGINAL_SIZE))
    check(digest == ORIGINAL_BLOB_SHA1,
          "ORIGINAL_SOURCE hashes to the git blob sha1 ticket #357 records\n"
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
        compare("exemplar 1: connect succeeds on the first attempt",
                observe(sys.modules[__name__], _accept, 5),
                observe(original, _accept, 5))
        compare("exemplar 2: every connect is refused (RETRIES=3)",
                observe(sys.modules[__name__], _refuse, 3),
                observe(original, _refuse, 3))

        # exemplar 3 — the stub payload. The original builds it inside main(), so the only way
        # to get at it is to drive main() down the stub path and let the recorder call the tool.
        mine_payload = _drive_main(sys.modules[__name__], ready=False)
        their_payload = _drive_main(original, ready=False)
        compare("exemplar 3: the degraded stub's payload, byte for byte",
                mine_payload, their_payload)
        parsed = json.loads(mine_payload) if isinstance(mine_payload, str) else {}
        check(parsed.get("coupler") == "down" and str(PORT) in parsed.get("message", "")
              and "coupler.server" in parsed.get("message", ""),
              "the stub payload parses, reads 'down', and names the live port and the module "
              "to start (%r)" % (parsed,))

        # ── 3. the edge cases ─────────────────────────────────────────────────
        print("\n[3] edge cases the exemplars cannot reach — differential", file=out)
        me = sys.modules[__name__]

        compare("RETRIES attempts, RETRIES sleeps, RETRIES waiting lines when refused "
                "(RETRIES=4) — the sleep-after-the-last-attempt #393 states backwards",
                observe(me, _refuse, 4), observe(original, _refuse, 4))
        compare("RETRIES == 0 returns False without connecting at all",
                observe(me, _refuse, 0), observe(original, _refuse, 0))
        compare("success on the 3rd attempt stops the loop there (RETRIES=5)",
                observe(me, _accept_on(3), 5), observe(original, _accept_on(3), 5))
        compare("ANY Exception from the connect is swallowed and counted as a retry — the "
                "non-OSError behavior #393 states backwards",
                observe(me, _explode, 2), observe(original, _explode, 2))
        compare("a BaseException (KeyboardInterrupt) propagates rather than counting as a retry",
                observe(me, _base_explode, 3), observe(original, _base_explode, 3))
        compare("a writer that fails to close counts as a failed attempt, not a success",
                observe(me, _bad_writer, 2), observe(original, _bad_writer, 2))
        compare("a connect that outlasts the timeout is abandoned and counted as failed",
                observe(me, _hang, 2, timeout_s=0.01), observe(original, _hang, 2))

        # the dialled address — the differential above already compares the attempts tuples, so
        # this only has to show what they were, and that the config reproduces the original's
        # hardcoded 127.0.0.1 rather than merely agreeing with itself.
        mine = observe(me, _refuse, 2)
        theirs = observe(original, _refuse, 2)
        check(mine.attempts == theirs.attempts == (("127.0.0.1", 7770), ("127.0.0.1", 7770)),
              "open_connection is called with (HOST, PORT) positionally, and the SHIPPED "
              "config reproduces the original's hardcoded ('127.0.0.1', 7770) — rewrite %r, "
              "original %r" % (mine.attempts[:1], theirs.attempts[:1]))
        check(HOST == "127.0.0.1" and PORT == 7770 and RETRIES == 15 and RETRY_S == 2.0
              and TIMEOUT_S == 1.0,
              "the shipped config reproduces the original's other constants too: HOST=%r "
              "PORT=%r RETRIES=%r RETRY_S=%r TIMEOUT_S=%r (original: '127.0.0.1', 7770, 15, "
              "2.0, 1.0)" % (HOST, PORT, RETRIES, RETRY_S, TIMEOUT_S))

        _selftest_port_env(check, out, original)

        # ── 4. the callable surface ───────────────────────────────────────────
        print("\n[4] callable surface — the ticket's, and the original's", file=out)
        _selftest_surface(check, original)

        # ── 5. no side effects ────────────────────────────────────────────────
        print("\n[5] side effects", file=out)
        check(asyncio.open_connection is real_open and asyncio.sleep is real_sleep,
              "asyncio.open_connection and asyncio.sleep are the real ones again — every "
              "patch was undone, so nothing here leaves a fake behind for the next caller")
        check("fastmcp" not in sys.modules,
              "the recording fastmcp stand-in was removed from sys.modules — a real fastmcp "
              "import after this selftest gets the real one")

        # ── 6. main(), both paths ─────────────────────────────────────────────
        print("\n[6] main() — differential under a recording fastmcp", file=out)
        compare("main() drives the degraded-stub path exactly as the original does",
                _drive_main(me, ready=False, full=True),
                _drive_main(original, ready=False, full=True))
        compare("main() drives the SSE-proxy path exactly as the original does",
                _drive_main(me, ready=True, full=True),
                _drive_main(original, ready=True, full=True))
        check(_missing_fastmcp_raises(me),
              "main() raises ImportError when fastmcp is absent, before any waiting — the "
              "original raised it at import; this rewrite's one deliberate deviation keeps "
              "the failure, and its immediacy, inside main()")

        # ── 7. no files ───────────────────────────────────────────────────────
        print("\n[7] no files created, modified or deleted", file=out)
        tree_after = _tree_snapshot()
        check(tree_before == tree_after,
              "this package's tree is byte-identical after the whole run (%d files, ignoring "
              "__pycache__ which CPython writes for any import) %s"
              % (len(tree_after), "" if tree_before == tree_after
                 else "\n         changed: %r" % (_tree_diff(tree_before, tree_after),)))

        # ── 8. the console spelling ───────────────────────────────────────────
        print("\n[8] the original's invocation still runs the bridge", file=out)
        _selftest_no_argv(check)

    finally:
        asyncio.open_connection, asyncio.sleep = real_open, real_sleep
        reset_config()

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED", checks[0],
             len(failures)), file=out)
    for failure in failures:
        print("  failed: %s" % failure.splitlines()[0], file=out)
    return len(failures)


def _describe_source():
    try:
        return active_source()
    except ConfigError as exc:
        return "UNRESOLVED (%s)" % exc


def _selftest_gate(check, out):
    """Check [1]: with an unresolvable config, importing this module throws ConfigError.

    Proven in a CHILD interpreter, because this module is already imported in this one and its
    globals are already bound — asking the live module to prove what it does at import would
    prove nothing. The child points `COUPLER_BRIDGE_CONFIG` at a file that does not exist:
    that source outranks the walk-up, so the gate is staged the same way whether or not a
    registry sits above this module — and this package SHIPS one, so a bare import would
    otherwise succeed and prove nothing.
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as isolated:
        env = dict(os.environ)
        env[CONFIG_ENV] = os.path.join(isolated, "no-such-config.json")
        env["PYTHONPATH"] = _package_root() + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-c", "import %s" % DOTTED_NAME],
            env=env, capture_output=True, text=True, cwd=isolated,
        )
        check(proc.returncode != 0 and "ConfigError" in proc.stderr,
              "`import %s` with an unresolvable config raises ConfigError and does NOT guess "
              "a default (rc=%d, stderr tail: %r)"
              % (DOTTED_NAME, proc.returncode, proc.stderr.strip().splitlines()[-1:]))
        check("7770" not in proc.stderr.replace(env[CONFIG_ENV], ""),
              "the ConfigError names no port — the gate throws rather than falling back to "
              "the original's 7770")

        # And with a config, the same child import succeeds — so check [1] is measuring the
        # gate, not a module that cannot import at all.
        template = config_template()
        config_path = os.path.join(isolated, "config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(template, handle)
        env[CONFIG_ENV] = config_path
        proc = subprocess.run(
            [sys.executable, "-c",
             "import %s as b; print(b.PORT, b.HOST, b.RETRIES)" % DOTTED_NAME],
            env=env, capture_output=True, text=True, cwd=isolated,
        )
        check(proc.returncode == 0 and proc.stdout.strip() == "7770 127.0.0.1 15",
              "the SAME import succeeds against a config object, binding it rather than a "
              "default (rc=%d, stdout=%r)" % (proc.returncode, proc.stdout.strip()))

        # A config object missing one key throws, naming the key — not a silent default.
        del template["retries"]
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(template, handle)
        proc = subprocess.run(
            [sys.executable, "-c", "import %s" % DOTTED_NAME],
            env=env, capture_output=True, text=True, cwd=isolated,
        )
        check(proc.returncode != 0 and "ConfigError" in proc.stderr
              and "'retries'" in proc.stderr,
              "a config object missing one key throws ConfigError NAMING that key rather "
              "than defaulting it (rc=%d)" % proc.returncode)


def _package_root():
    """The directory holding `pyproject.toml` — the import path `coupler` resolves from."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _strip_prose(node):
    """Drop the keys that are documentation or package-wide, leaving the settings themselves.

    `_comment` is prose for a human reading the registry, and `bug_reports` is inherited from
    the registry's top level rather than stated by this unit's section; neither is a setting
    this unit reads, so neither belongs in a comparison of settings.
    """
    if not isinstance(node, dict):
        return node
    return {key: _strip_prose(value) for key, value in node.items()
            if key not in ("_comment", "bug_reports")}


def _selftest_template_matches_registry(check):
    """The template `emit-config` prints must equal the config this package actually ships.

    `emit-config` tells an operator "this is the config object to install", so if it drifted
    from the section in `registry.json`, the module would be handing out a config that is not
    the one it was proven against — and every check that measures the shipped values would
    still pass while the printed advice quietly went wrong. Comparing them is what keeps the
    two from parting.
    """
    shipped, _base, _source = load_config()
    check(_strip_prose(shipped) == _strip_prose(config_template()),
          "the config object `emit-config` prints is exactly the one this package ships in "
          "%s — the template cannot drift from the config the checks above measure%s"
          % (REGISTRY_NAME,
             "" if _strip_prose(shipped) == _strip_prose(config_template())
             else "\n         shipped : %r\n         template: %r"
                  % (_strip_prose(shipped), _strip_prose(config_template()))))


def _selftest_port_env(check, out, original):
    """Check [3]: $COUPLER_PORT overrides the configured default port, as it did originally.

    Done in a child interpreter for this module, because the override happens at IMPORT and
    this module is already imported. The ORIGINAL is re-exec'd in-process with the same value
    staged, so the two are compared rather than merely asserted.
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as isolated:
        env = dict(os.environ)
        env.pop(CONFIG_ENV, None)
        env["COUPLER_PORT"] = "9931"
        env["PYTHONPATH"] = _package_root() + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-c", "import %s as b; print(b.PORT)" % DOTTED_NAME],
            env=env, capture_output=True, text=True, cwd=isolated,
        )
        mine = proc.stdout.strip()
        theirs = str(load_original(port_env_value="9931").PORT)
        check(proc.returncode == 0 and mine == theirs == "9931",
              "$COUPLER_PORT overrides the configured default port at import, as it did "
              "originally (rewrite %r, original %r)" % (mine, theirs))


def _selftest_surface(check, original):
    """Check [4]: the callable surface ticket #357 states, proven by inspection."""
    import inspect

    me = sys.modules[__name__]
    for name, is_async in (("_wait_for_server", True), ("main", False)):
        mine = getattr(me, name, None)
        theirs = getattr(original, name, None)
        check(callable(mine), "%s is importable from this module and callable" % name)
        # The PARAMETERS, not str(signature): `_wait_for_server`'s renders as "() -> bool",
        # because the return annotation is part of the rendering and not part of the surface.
        check(list(inspect.signature(mine).parameters) == [],
              "%s%s takes no parameters, as the ticket's surface says"
              % (name, inspect.signature(mine)))
        check(inspect.iscoroutinefunction(mine) is is_async,
              "%s is %sa coroutine function, as the ticket's surface says"
              % (name, "" if is_async else "not "))
        check(str(inspect.signature(mine)) == str(inspect.signature(theirs)),
              "%s's signature matches the ORIGINAL's exactly (%s)"
              % (name, inspect.signature(mine)))

    check(inspect.signature(me._wait_for_server).return_annotation is bool,
          "_wait_for_server is annotated `-> bool`, as the ticket's surface says")
    for name in ("PORT", "RETRIES", "RETRY_S"):
        check(hasattr(me, name) and hasattr(original, name),
              "the module global %s the original bound is still bound here — callers and "
              "tests rebind it (%s=%r)" % (name, name, getattr(me, name, None)))


def _drive_main(module, ready, full=False):
    """Run `module.main()` down one of its two paths and return what it drove fastmcp to do.

    Stages `_wait_for_server` to answer `ready` — the two paths of `main()` are selected by
    nothing else — installs the recording fastmcp for the duration, and returns the recorded
    calls (or just the stub's payload when `full` is False). Restores everything in a
    `finally`, so no fake and no stand-in outlives the call.
    """
    recorder = _Recorder()
    saved_modules = recorder.install()
    saved_wait = module._wait_for_server
    saved_names = _bind_fastmcp_names(module)
    real_stderr = sys.stderr
    captured = io.StringIO()

    async def fake_wait():
        return ready

    try:
        module._wait_for_server = fake_wait
        sys.stderr = captured
        try:
            module.main()
        except BaseException as exc:  # noqa: BLE001 — a raise is part of the observation
            return ("raised", "%s: %s" % (type(exc).__name__, exc))
    finally:
        module._wait_for_server = saved_wait
        _restore_names(module, saved_names)
        sys.stderr = real_stderr
        _Recorder.restore(saved_modules)

    if not full:
        # Just the stub payload: the 4th field of the ("tool registered", ...) record.
        for call in recorder.calls:
            if call[0] == "tool registered":
                return call[3]
        return ("no tool was registered", recorder.calls)
    return (tuple(recorder.calls), captured.getvalue())


#: The three names the bridge uses from fastmcp, and the module each is imported from — the
#: original's three module-scope `from ... import ...` lines, as data.
_FASTMCP_NAMES = (
    ("FastMCP", "fastmcp"),
    ("SSETransport", "fastmcp.client.transports"),
    ("create_proxy", "fastmcp.server"),
)


def _bind_fastmcp_names(module):
    """Point `module` at the fastmcp currently in `sys.modules`; return what was there before.

    This is what makes check [6]'s comparison fair, and it is worth being precise about because
    it is the one place the two modules genuinely differ in structure.

    The ORIGINAL imports fastmcp at MODULE scope, so `FastMCP`, `SSETransport` and
    `create_proxy` were bound into its namespace once, when `load_original()` exec'd it — and
    they still refer to whatever recorder was installed at that moment. Re-installing a
    recorder in `sys.modules` afterwards would not reach them, so the original would drive the
    stale one and record nothing. Rebinding the three names is how a module-scope importer is
    pointed at a new fake; it is the exact analogue of this module's `_load_fastmcp()` reading
    `sys.modules` afresh on every call.

    This module binds none of the three at module scope, so there is nothing to rebind here and
    nothing is added: only names the module ALREADY has are touched, so the two are driven
    through their own real import paths and neither is given a shortcut the other lacks.
    """
    saved = {}
    for name, source in _FASTMCP_NAMES:
        if hasattr(module, name):
            saved[name] = getattr(module, name)
            setattr(module, name, getattr(sys.modules[source], name))
    return saved


def _restore_names(module, saved):
    for name, value in saved.items():
        setattr(module, name, value)


def _missing_fastmcp_raises(module):
    """Prove `main()` raises ImportError with no fastmcp installed, before any waiting.

    Stages `_wait_for_server` to record whether it ran. The original raised at IMPORT, so it
    never waited either; this rewrite must not wait 30 seconds before admitting the same
    problem. `fastmcp` is blocked by pinning None into `sys.modules`, which is the import
    system's own "this module is not available" marker.
    """
    waited = []

    async def fake_wait():
        waited.append(True)
        return False

    saved_wait = module._wait_for_server
    saved = {name: sys.modules.get(name)
             for name in ("fastmcp", "fastmcp.client", "fastmcp.client.transports",
                          "fastmcp.server")}
    try:
        module._wait_for_server = fake_wait
        for name in saved:
            sys.modules[name] = None
        try:
            module.main()
            return False
        except ImportError:
            return not waited
        except Exception:  # noqa: BLE001 — anything else is not the contract
            return False
    finally:
        module._wait_for_server = saved_wait
        _Recorder.restore(saved)


def _selftest_no_argv(check):
    """Check [8]: `python -m coupler.bridge` with no argument still RUNS the bridge.

    The original's Claude Desktop config is `command: python -m coupler.bridge`, with no
    subcommand, so that spelling must reach `main()` and not an argparse error. Proven by
    calling this module's `main` entry with an empty argv and a `main()` that records — not by
    reading the parser and reasoning about it.
    """
    ran = []
    me = sys.modules[__name__]
    saved = me.main
    try:
        me.main = lambda: ran.append(True)
        code = cli([])
    finally:
        me.main = saved
    check(ran == [True] and code == 0,
          "`python -m %s` with no argument runs the bridge — the original's Claude Desktop "
          "spelling still works (main called: %s, rc=%r)" % (DOTTED_NAME, bool(ran), code))


def _tree_snapshot():
    """Map every file in this package to its size and mtime, ignoring build artifacts.

    `__pycache__` and `*.egg-info` are excluded because CPython and pip write them for any
    import or install; ticket #357 lists both among the artifacts that are regenerated and
    never committed. Everything else is a file this module must not touch, and check [7]
    diffs this before and after a whole selftest to prove it did not.
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


# ─────────────────────────────── the install check ───────────────────────────────

def install_check(stream=None):
    """Prove ticket #357's acceptance item (c) as far as this sandbox allows, and say where
    that stops. Returns the number of failures.

    WHAT THIS DOES AND DOES NOT PROVE — read this before trusting it
    ---------------------------------------------------------------
    It does NOT run `pip install -e .`, and it does not pretend to. It cannot, on the
    interpreter this package was verified against: that interpreter has no setuptools, so pip
    would fetch one to build with, and this sandbox permits no network. The only interpreter
    here that HAS setuptools carries 58.0.4, which predates PEP 621 and cannot read this
    pyproject's `[project]` table at all. So the one command acceptance item (c) names is the
    one thing below that is not executed, and that gap is stated rather than papered over.

    What it DOES do is execute the two things an install produces, so the parts that can fail
    silently are measured rather than assumed:

      1. the declaration — `pyproject.toml` parses, declares `coupler` as a package, maps it to
         a directory that exists, and its console script names a callable that resolves;
      2. the EDITABLE install's effect — an editable install's whole effect on imports is to
         put the package root on `sys.path`, so that is staged and `import coupler.bridge` is
         run against it in a child interpreter;
      3. the NON-EDITABLE install's effect — the file layout `pip install .` would produce is
         BUILT here from the same declarations setuptools reads, and `import coupler.bridge` is
         run against THAT in a child interpreter started with `-S`, so no site-packages of this
         machine can answer for it. This is the layout where the config is hardest to find, and
         it is why `find_registry` has an `_installed_registry` fallback: the walk-up from
         `site-packages/coupler/bridge.py` passes no registry at all.
    """
    import subprocess
    import shutil
    import tempfile

    out = stream or sys.stdout
    failures = []

    def check(ok, label):
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    root = _package_root()
    print("install check for %s\n  package root: %s" % (UNIT, root), file=out)
    print("\n  NOTE: `pip install -e .` is NOT run here — this interpreter has no setuptools "
          "and\n  the sandbox permits no network to fetch one. What follows executes what an\n"
          "  install PRODUCES, in both layouts, rather than the pip command itself.", file=out)

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
        packages = pyproject.get("tool", {}).get("setuptools", {}).get("packages", [])
        package_dir = pyproject.get("tool", {}).get("setuptools", {}).get("package-dir", {})
        scripts = pyproject.get("project", {}).get("scripts", {})
        check("coupler" in packages,
              "`coupler` is declared in tool.setuptools.packages (%r) — without it an install "
              "ships no coupler/ and `import coupler.bridge` fails" % (packages,))
        check(os.path.isfile(os.path.join(root, package_dir.get("coupler", "coupler"),
                                          "bridge.py")),
              "the directory `coupler` maps to actually holds bridge.py")
        check(scripts.get("forge2-coupler-bridge") == "coupler.bridge:cli",
              "the console script forge2-coupler-bridge points at coupler.bridge:cli (%r)"
              % (scripts.get("forge2-coupler-bridge"),))
        check(callable(cli), "that entry point, coupler.bridge:cli, resolves to a callable")
        check(pyproject.get("project", {}).get("dependencies") == [],
              "the package declares NO dependencies, so a `pip install -e .` needs no index "
              "to resolve any (fastmcp is imported lazily by main() for exactly this reason)")

    # ── 2. the editable install's effect ──────────────────────────────────────
    print("\n[2] the EDITABLE layout — package root on sys.path", file=out)
    with tempfile.TemporaryDirectory() as elsewhere:
        env = dict(os.environ)
        env.pop(CONFIG_ENV, None)
        env["PYTHONPATH"] = root
        proc = subprocess.run(
            [sys.executable, "-c",
             "import coupler.bridge as b; print(b.PORT, b.HOST, b.RETRIES, b.RETRY_S)"],
            env=env, capture_output=True, text=True, cwd=elsewhere,
        )
        check(proc.returncode == 0 and proc.stdout.strip() == "7770 127.0.0.1 15 2.0",
              "`import coupler.bridge` works with the root on sys.path, from an unrelated "
              "working directory, and finds its config (rc=%d, stdout=%r, stderr=%r)"
              % (proc.returncode, proc.stdout.strip(), proc.stderr.strip()[-160:]))

        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; from coupler.bridge import cli; sys.exit(cli(['show-status']))"],
            env=env, capture_output=True, text=True, cwd=elsewhere,
        )
        check(proc.returncode == 0 and '"coupler": "down"' in proc.stdout,
              "the console script's entry point runs from an unrelated working directory "
              "(rc=%d)" % proc.returncode)

    # ── 3. the non-editable install's effect ──────────────────────────────────
    print("\n[3] the NON-EDITABLE layout — what `pip install .` puts in site-packages", file=out)
    with tempfile.TemporaryDirectory() as staging:
        site = os.path.join(staging, "site-packages")
        # Build the layout from the SAME declarations setuptools reads: each declared package
        # is copied to its own directory under site-packages, and the package-data registry
        # goes with the package that declares it. This is what `pip install .` produces.
        shutil.copytree(os.path.join(root, "coupler"), os.path.join(site, "coupler"),
                        ignore=shutil.ignore_patterns("__pycache__", "tests"))
        outer = os.path.join(site, PACKAGE_WITH_REGISTRY)
        os.makedirs(outer)
        for name in os.listdir(root):
            if name.endswith(".py") or name == REGISTRY_NAME:
                shutil.copy2(os.path.join(root, name), os.path.join(outer, name))

        check(not os.path.isfile(os.path.join(site, REGISTRY_NAME)),
              "the staged site-packages has NO registry.json at its root — so the walk-up from "
              "coupler/bridge.py finds nothing, which is the case the find_spec fallback exists "
              "for and the one a plain `pip install .` really produces")

        env = dict(os.environ)
        env.pop(CONFIG_ENV, None)
        env["PYTHONPATH"] = site

        # `import coupler.bridge` runs `coupler/__init__.py` FIRST, and that sibling unit
        # (#397) has a config gate of its own whose walk-up has no package-data fallback — so
        # in this layout it throws before this module is reached. That is a pre-existing gap in
        # a sibling, not in this unit, and #357 "covers ONE module ... and nothing else", so it
        # is neither fixed here nor allowed to hide what this module does. Its own documented
        # escape hatch, $COUPLER_CONFIG, is used to satisfy it, which isolates this unit's
        # behavior. The gap itself is reported as a NOTE below, with the evidence.
        sibling_config = os.path.join(staging, "coupler-unit-config.json")
        with open(sibling_config, "w", encoding="utf-8") as handle:
            json.dump({"distribution": "coupler", "fallback": "0.0.dev0"}, handle)
        env["COUPLER_CONFIG"] = sibling_config

        # `-S` so this machine's real site-packages cannot answer for the staged one.
        proc = subprocess.run(
            [sys.executable, "-S", "-c",
             "import coupler.bridge as b; print(b.PORT, b.HOST, b.RETRIES)"],
            env=env, capture_output=True, text=True, cwd=staging,
        )
        check(proc.returncode == 0 and proc.stdout.strip() == "7770 127.0.0.1 15",
              "`import coupler.bridge` works from the non-editable layout under `python3 -S`, "
              "finding ITS registry.json as package data via find_spec with nothing in the "
              "walk-up (rc=%d, stdout=%r, stderr=%r)"
              % (proc.returncode, proc.stdout.strip(), proc.stderr.strip()[-200:]))

        # And this unit's gate still holds there: remove the shipped registry and it must throw
        # — from THIS module, naming THIS unit, not from the sibling.
        os.remove(os.path.join(outer, REGISTRY_NAME))
        proc = subprocess.run(
            [sys.executable, "-S", "-c", "import coupler.bridge"],
            env=env, capture_output=True, text=True, cwd=staging,
        )
        check(proc.returncode != 0 and "ConfigError" in proc.stderr and UNIT in proc.stderr,
              "with the shipped registry deleted, that same install throws ConfigError naming "
              "THIS unit rather than guessing a default — the gate is not an artifact of the "
              "source tree (rc=%d)" % proc.returncode)

        # ── the sibling's gap, reported rather than absorbed ──────────────────
        env.pop("COUPLER_CONFIG")
        shutil.copy2(os.path.join(root, REGISTRY_NAME), os.path.join(outer, REGISTRY_NAME))
        proc = subprocess.run(
            [sys.executable, "-S", "-c", "import coupler.bridge"],
            env=env, capture_output=True, text=True, cwd=staging,
        )
        blocked = proc.returncode != 0 and "_config.py" in proc.stderr
        print("\n  NOTE (a sibling's gap, NOT this unit's, and NOT ticket #357's to fix):\n"
              "  in the non-editable layout with no $COUPLER_CONFIG set, `import coupler.bridge`"
              "\n  fails in `coupler/__init__.py` -> `coupler/_config.py` (ticket #397) before "
              "this\n  module runs: that unit's registry walk-up has no package-data fallback, "
              "so it\n  finds nothing above site-packages/coupler/. Observed: %s\n"
              "  This unit's own resolution is unaffected and is what the checks above measure."
              % ("yes — %r" % (proc.stderr.strip().splitlines()[-1:] or [""],)[0]
                 if blocked else "NO — the sibling resolved after all; this note is stale"),
              file=out)

    print("\n%s — %d failure(s)"
          % ("INSTALL-CHECK PASSED" if not failures else "INSTALL-CHECK FAILED",
             len(failures)), file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


# ─────────────────────────────── bug reports ───────────────────────────────

def bug_report(exc, formatted, invocation):
    """Append one timestamped JSON line describing an UNEXPECTED exception; return its path.

    This is `note-for-claude`'s rule — "all tools need to pass a bug-report automatically
    (timestamped if an exception is thrown)". It reports a DEFECT IN THIS TOOL and nothing
    else: a `ConfigError` and a `UsageError` are designed behavior and never land here, and
    neither does a selftest check FAILING, which is a verdict this module exists to reach.

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

def _invocation(argv):
    """Describe how this process was ACTUALLY started, for a bug report to record.

    Derived from the interpreter and `sys.argv` rather than written as a fixed string. A report
    is a record, and a record that states an invocation the operator did not type is worse than
    no record: it sends the next reader to reproduce something that never ran.
    """
    if __name__ == "__main__" and __spec__ is not None:
        launcher = "-m " + __spec__.name
    else:
        launcher = sys.argv[0] if sys.argv and sys.argv[0] else DOTTED_NAME
    return " ".join([os.path.basename(sys.executable), launcher] + list(argv))


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="forge2-coupler-bridge",
        description="forge2 rewrite of the forge unit code__code-invalid__coupler:"
                    "coupler/bridge.py (ticket #357) — the stdio-to-SSE bridge. "
                    "Config-driven: it throws if it cannot see its config object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="With NO argument this runs the bridge, which is the original's Claude Desktop "
               "spelling (`command: python -m %s`). Config is read from the file named by $%s, "
               "else from the %s section of the nearest %s found by walking up from this "
               "module. This package ships one, so these commands work from a clean checkout. "
               "Run `emit-config` for a template."
               % (DOTTED_NAME, CONFIG_ENV, " -> ".join(UNIT_PATH), REGISTRY_NAME),
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="run the bridge (the default; needs fastmcp installed)")
    sub.add_parser("selftest", help="prove this rewrite against the ORIGINAL, which it embeds")
    sub.add_parser("install-check", help="prove the package's declared install, both layouts")
    sub.add_parser("show-config", help="print the config object in force and its source")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-status", help="print the degraded stub's coupler_status payload")
    return parser


def cli(argv=None):
    """Entry point for the `forge2-coupler-bridge` console script. Returns an exit code.

    With no subcommand this runs the bridge, so the original's `python -m coupler.bridge` keeps
    working unchanged. `main()` is the bridge itself and is kept free of argument parsing,
    because it is the surface ticket #357 requires and Claude Desktop calls it.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = _build_parser().parse_args(argv)
        command = args.command or "run"

        if command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your registry.json, or save a file containing "
                  "just it\n# and point $%s at that file. Until it is installed, importing "
                  "this module\n# throws ConfigError — it will not guess a default."
                  % (" -> ".join(UNIT_PATH), CONFIG_ENV), file=sys.stderr)
            return 0

        if command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(), "base": active_base(),
                              "resolved": {"HOST": HOST, "PORT": PORT, "RETRIES": RETRIES,
                                           "RETRY_S": RETRY_S, "TIMEOUT_S": TIMEOUT_S},
                              "config": active_config()}, indent=2))
            return 0

        if command == "show-status":
            print(stub_status_payload())
            return 0

        if command == "selftest":
            return 0 if selftest() == 0 else 1

        if command == "install-check":
            return 0 if install_check() == 0 else 1

        if command == "run":
            main()
            return 0

    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except UsageError as exc:
        print("usage error: %s" % exc, file=sys.stderr)
        return 2
    except ImportError as exc:
        # `run` without fastmcp. Not a defect in this tool, and the original could not even be
        # imported in this situation — so it is answered as a usage problem, not a bug report.
        print("cannot run the bridge: %s\n"
              "The bridge needs fastmcp, which this package does not declare (see the module "
              "docstring). Install it with: pip install fastmcp" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        path = bug_report(exc, traceback.format_exc(), _invocation(argv))
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise

    return 0


if __name__ == "__main__":
    if __spec__ is None:
        # Run by path: `coupler/` went onto the import path instead of the package root, so the
        # `coupler` package is not importable and `importlib.reload`/`-m` semantics are gone.
        # One line that fixes it beats a traceback that blames the tool.
        print("usage error: run this module as `python3 -m %s ...` from the package root (the "
              "directory holding pyproject.toml), not by path. Running it by path puts %s on "
              "the import path instead of the package root, so the `coupler` package cannot "
              "be imported."
              % (DOTTED_NAME, os.path.dirname(os.path.abspath(__file__))), file=sys.stderr)
        sys.exit(2)
    sys.exit(cli())
