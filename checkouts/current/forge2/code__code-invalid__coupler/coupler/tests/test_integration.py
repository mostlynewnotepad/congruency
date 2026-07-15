#!/usr/bin/env python3
"""forge2 / code__code-invalid__coupler / coupler.tests.test_integration — a
behavior-preserving rewrite of the forge unit
`code__code-invalid__coupler:coupler/tests/test_integration.py` (module key
forge-rw:993656d6360bc88d), filed under ticket #377 against the FORGE-wide refactor
standard #200.

(#377 supersedes #292, which named its source only as a `git cat-file` against the forge's
bare repos that the sandboxed pair_loop worker cannot run. #377 embeds the source instead,
so the rewrite needs no forge access, and the work is done HERE.)

WHAT THIS IS
------------
The original forge unit was 4058 bytes: a pytest module holding one helper, one
module-scoped fixture and three async integration tests. The fixture spawns
`coupler/server.py` as a REAL subprocess on a REAL free TCP port, waits for it to accept
connections, and yields the port; each test then connects a FastMCP client over SSE and
exercises an actual tool round-trip. It needs no live jazz services — it points `$JAZZ_ROOT`
at a temp tree holding a minimal `build.json` and pins `$JAZZ_DEV` at a path that does not
exist.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and it adds the three things #200 requires that the
original lacked: it is part of a proper installable package, it is driven by a configuration
object, and it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
Quoted from ticket #377, which lowered the original with codebean's `lower_node` (#183):

    _free_port() -> int
    server_port(tmp_path_factory)
    async test_coupler_status_via_sse(server_port)
    async test_ui_tool_available_via_sse(server_port)
    async test_why5_tool_available_via_sse(server_port)

The "existing caller" of a pytest module is pytest itself, so the surface is preserved in
the way that matters to it: the same five names, the same parameters, the same `-> int`
annotation, `server_port` still a `scope="module"` fixture that YIELDS, and the same three
tests still `async` and still carrying `@pytest.mark.slow` and `@pytest.mark.asyncio`.
pytest collects and runs this module exactly as it collected and ran the original.
`selftest` check [5] PROVES this by re-lowering THIS file's own AST the way #183 lowers a
module and comparing the result to the five lines above, rather than asserting it.

WHY THE TWO MARKS AND THE FIXTURE SCOPE ARE LITERAL AND NOT CONFIG-DRIVEN
------------------------------------------------------------------------
`@pytest.mark.slow`, `@pytest.mark.asyncio` and `scope="module"` stay written out, and that
is not an oversight about #200's fourth requirement. They are not PARAMETERS of what these
tests assert; they are part of how pytest ADDRESSES and schedules them, exactly as the
function names are. The original's own docstring makes the first one a published contract —
"Marked with @pytest.mark.slow — skip with: pytest -m 'not slow'" — so `pytest -m "not
slow"` must keep deselecting these three tests, and a mark that materialised out of a config
file could not be read by pytest at collection time, when marks are needed. `scope="module"`
is likewise observable behavior, not a setting: it is what makes ONE server serve all three
tests. `selftest` check [5] pins all three down off this file's AST, and check [12] proves
the single-server behavior by counting the servers actually spawned.

WHAT "BEHAVIOR-PRESERVING" MEANS FOR A TEST MODULE, AND HOW IT IS PROVEN HERE
-----------------------------------------------------------------------------
A test module's observable behavior is the VERDICT it reaches about the code under test: for
which implementations of `coupler.server` it passes, and for which it fails. Preserving it
means this file must reach the same verdict as the original for every implementation — no
stricter, so nothing the original accepted is failed here, and no laxer, so nothing the
original caught slips through.

That is a claim about a pair of programs, so `selftest` proves it as one, differentially. It
EMBEDS the original's own 4058 bytes (see `ORIGINAL_SOURCE`), executes them, and runs the
original's three tests and this file's three tests against the SAME `coupler.server`
implementation, under identically staged conditions and against the same client. It does
that for twelve implementations — two faithful references and ten mutants — and compares
the two verdict vectors test by test. It also compares the LAUNCH itself: check [14] records
the argv and the four environment keys each module hands the child, and requires them to be
identical. A verdict can agree by luck; the launch cannot. The expected values are not
hand-copied into a table
and hoped to be right: they are taken from the original AS IT RUNS. Ticket #377 records that
criteria_miner captured NO exemplars for this module ("nothing here qualified"), which
"MOVES the work: you must write the equivalence exemplars by hand" — `EXEMPLARS` and
`EDGE_CASES` below are that hand-written table, and the differential is what settles them.

THE ORACLE IS THE FORGE'S OWN BLOB, PROVEN CRYPTOGRAPHICALLY
------------------------------------------------------------
An embedded copy of the original is only as good as its fidelity, so that is not taken on
trust. Ticket #377 records the original's git blob sha1 as
`200447c35c9708ee1659c72a6c168e944c3026a3`, and `selftest` check [2] recomputes that hash
over `ORIGINAL_SOURCE` — `sha1("blob " + len + "\\0" + bytes)`, git's own object rule — and
compares. It passes, which means the bytes this rewrite is measured against ARE the bytes at
`refs/heads/stable`, not a paraphrase of them. Any edit to them — a "fixed" typo, a
re-indent, a dropped unused import — moves the hash and fails the check instead of quietly
changing what this rewrite is compared to. Check [1] pins the 4058-byte size for the same
reason.

THE MODULE UNDER TEST DOES NOT EXIST YET — AND THAT IS NOT THIS TICKET'S TO FIX
-------------------------------------------------------------------------------
`coupler.server` is a DIFFERENT forge module with its OWN rewrite ticket; it has not landed
in `forge2/code__code-invalid__coupler/` yet, and ticket #377 is explicit that it "covers
ONE module — the one identified below — and nothing else." So this file does not ship one,
and must not.

Two consequences, both deliberate:

  * Under pytest, these three tests drive whatever the config's `server_module` names — by
    default `coupler.server`, exactly as the original did. Until that module lands the
    fixture fails the same way the original's does today. That is the behavior preserved,
    not a defect introduced.
  * `selftest` therefore supplies its own `coupler.server` to test against: `REFERENCE_SERVER`
    below, a faithful reconstruction of the module under test, DERIVED FROM THE ORIGINAL
    TEST'S OWN STATEMENTS about it (see `REFERENCE_SERVER`'s comment for the line-by-line
    derivation). It is selftest scaffolding and nothing else — it is not a rewrite of
    `coupler/server.py`, it is not installed, it is not importable from this package, and it
    never touches the source tree: it is written into a temp directory that is removed
    afterwards. What makes it legitimate as evidence is that the ORIGINAL runs against it
    too, green, through the same import path — so it is a fair oracle rather than a target
    this rewrite was fitted to.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a
    single `.json` file at the root of a package holding the configuration for every tool in
    that package. `note-for-claude` states the contract in its own words — ".json will have
    all the configuration - for all tools in this set of packaging. (a configuration
    registry) -if a tool cannot see the registry it will throw an exeption." [sic] This
    package ships its own `registry.json` at its root, two directories above this file.
config object
    The chunk of that registry belonging to this unit — the section at
    `forge2 -> code__code-invalid__coupler -> coupler.tests.test_integration`. It is what
    drives the three tests. `emit-config` prints a template of it.
fixture
    A pytest function whose return value is injected into any test that names it as a
    parameter. `server_port` is a fixture; all three tests name it, so pytest builds the
    server first and hands each test the port.
module-scoped
    A fixture built ONCE for the whole module and shared by every test in it, rather than
    rebuilt per test. `server_port` is `scope="module"`, so one server subprocess serves all
    three tests and is terminated after the last. Proven by check [12].
yield fixture
    A fixture that `yield`s its value instead of returning it; everything after the `yield`
    is teardown, run once the last test that used it has finished. This is how the server is
    terminated.
tmp_path_factory
    pytest's built-in session-scoped fixture handing out fresh temp directories via
    `mktemp(name)`. A module-scoped fixture cannot use the function-scoped `tmp_path`, which
    is why the original reaches for the factory instead.
SSE
    Server-Sent Events — the long-lived HTTP transport FastMCP uses to carry MCP traffic.
    `SSETransport(url)` is the client end of it.
exemplar
    One (scenario -> expected outcome) pair the rewrite must reproduce, standing in for the
    automated captures ticket #377 could not mine.
mutant
    A deliberately broken `coupler.server` used by `selftest` to prove these tests actually
    DISCRIMINATE — a test that cannot fail proves nothing, so each mutant records which tests
    must fail against it, and the original is run against it to confirm that expectation.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The original hardcoded every parameter of its three scenarios: the module it spawns
(`coupler.server`) and its `--port` argument, the env var names (`JAZZ_ROOT`, `JAZZ_DEV`,
`COUPLER_PORT`, `PYTHONPATH`) and the `/nonexistent` it pinned `JAZZ_DEV` to, the
`conf/env/build.json` location and the whole build document, the `jazz` temp prefix, the
`127.0.0.1` it binds and probes, the `http://127.0.0.1:{port}/sse` URL, the three-parent walk
that builds `PYTHONPATH`, every timeout and sleep (10, 0.5, 0.2, 5, 5), the failure message,
the tool names (`coupler_status`, `ui_list_pages`, `why5_new`), the response keys (`coupler`,
`jazz_version`), the values it asserts (`ok`; the `notes`/`notes_db`/`z3` services; the
`ok`/`down`/`degraded` states), and the why5 arguments and the substring it expects back.
Those are exactly the params #200's fourth requirement forbids hardcoding, so every one of
them is read from this unit's config object and NOTHING is defaulted in code. Run
`emit-config` to see the object; its values are the original's own, which is what makes this
rewrite behave identically in practice — the values did not change, only their location did.

The config is read INSIDE each test and inside `_free_port`, not at import time,
deliberately: pytest must still be able to import and collect this module, so a missing
config object surfaces as honest `ConfigError` failures naming what is missing, rather than
one collection error that hides which tests exist. `selftest` check [10] proves each test and
`_free_port` throw `ConfigError` — and reach no verdict about the server — when the config
cannot be resolved.

WHY SOME VALUES APPEAR TWICE IN THE CONFIG, ON PURPOSE
------------------------------------------------------
`bind_host` reads `"127.0.0.1"` and `sse_url` contains `"127.0.0.1"` again;
`why5_arguments.session_id` and `why5_expect_substring` both read `"test-session"`. That is
not duplication to be collapsed. The original names each of these strings twice, in
different ROLES: `bind_host` is the address the fixture BINDS and PROBES, while `sse_url` is
the address the client DIALS; `why5_arguments.session_id` is what the test SENDS, while
`why5_expect_substring` is what it ASSERTS came back. Collapse either pair into one key and
the assertion checks the fixture against itself — it could never fail, and a check the
original made would be quietly deleted. Mutant [9] fails precisely because the why5 pair is
kept apart.

RESOLUTION ORDER
----------------
The config object is resolved from the first source that answers:

  1. the file named by the `COUPLER_TEST_INTEGRATION_CONFIG` environment variable, which
     holds this unit's config object itself — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code-invalid__coupler -> coupler.tests.test_integration`
     section of the nearest `registry.json` found by walking UP from THIS FILE's directory.

If neither answers, every test raises `ConfigError`. It never guesses a default. The walk-up
starts at this file, never at the working directory, so which directory you run from does not
change what config is found.

The variable is named for THIS UNIT rather than shared across the package for the reason
`coupler/_config.py` (#397) already records: a variable holding ONE unit's config object
could only ever point at one unit's object at a time, so a shared name would mean pointing it
at a sibling's config breaks this one. `$COUPLER_CONFIG` is #397's and
`$COUPLER_TEST_BUILD_CONFIG` is #355's; this unit reads neither and collides with neither.

THIS MODULE IS SELF-CONTAINED ON PURPOSE
----------------------------------------
It resolves its own config rather than importing a helper from a sibling file, even though
`coupler/_config.py` holds very similar machinery. A forge rewrite unit's deliverable is ONE
module, and a sibling it depends on may not be present: `coupler/tests/test_bridge.py` (#393)
imports `coupler.config`, which does not exist in this package, and is unimportable today as
a result. This file has no such dependency and runs against the package as it actually is.

THE THREE THIRD-PARTY DEPENDENCIES, AND WHAT THIS MODULE DOES WITHOUT EACH
--------------------------------------------------------------------------
The original imports `pytest`, `pytest_asyncio` and `fastmcp` at module scope, so it cannot
be imported at all where any of them is absent — and all three are absent from the BARE
interpreter this package is developed against (Homebrew CPython 3.14, where a direct
`pip install` is refused by PEP 668's "externally-managed-environment"). This rewrite
declares all three in `pyproject.toml`'s `test` EXTRA, so `pip install -e ".[test]"` into a
virtualenv is where they come from.

Stated precisely, because the difference matters: `pip install -e .` was RUN here and exits
0; pytest and pytest-asyncio were obtained and this module was run under both, really. The
`.[test]` install as a whole was NOT run, because `fastmcp` is not reachable from this
sandbox — so that the extra installs cleanly is a declaration, not a demonstration. See WHAT
HAS ACTUALLY BEEN RUN, which draws the same line.

They are an extra rather than required dependencies on purpose. Ticket #377's acceptance item
(c) is that `pip install -e .` installs CLEAN from this package's own pyproject.toml, and a
required pytest would make that install depend on a package index being reachable. The
package does not need them to be installed or used — only to be tested through pytest — so
nothing is required and the plain install always succeeds.

The three are handled DIFFERENTLY, because what they do here differs:

  * `pytest` supplies the `@pytest.fixture`/`@pytest.mark` decorators and `pytest.fail`, all
    of which run at IMPORT time — there is nowhere to defer them to. Where pytest is absent, a
    minimal stand-in supplies exactly those three things, so `selftest` can prove this
    rewrite on a bare interpreter. It is inert whenever real pytest is importable: under
    pytest the real decorators and the real `fail` are used and NOTHING of the stand-in is in
    the path.
  * `pytest_asyncio` is imported by the original and never referenced by it — importing it is
    the whole of its use, since the plugin registers itself with pytest through an entry
    point. So this module records whether it is importable and needs no stand-in for it.
  * `fastmcp` gets NO fallback stand-in, and that is the important one. A stand-in client
    cannot speak real MCP to a real server, so falling back to one would make these tests
    report FAILURE against a perfectly good `coupler.server` — a wrong verdict, and a false
    accusation, where the original merely raised `ImportError`. Instead `Client` and
    `SSETransport` are `None` when fastmcp is absent, and each test raises `ImportError`
    naming fastmcp — the SAME exception type the original raises, differing only in WHEN
    (at the call rather than at collection), for the same reason the config is read late.
    Check [11] proves it.

Why the stand-ins cannot fake an agreement that is not there: they touch only how a test is
INVOKED (a decorator that returns the function, a fixture that sets and restores), never what
it ASSERTS, and the differential runs the ORIGINAL through those SAME stand-ins and the same
injected client — so any distortion they introduced lands on both sides equally. `selftest`
also reports which path it took, so a reader can see it rather than infer it; `show-deps`
reports the same on its own.

WHAT HAS ACTUALLY BEEN RUN, AND WHAT HAS NOT
--------------------------------------------
Stated plainly rather than left for the reader to discover. All of the following were
executed against this file as it stands; the counts are in the `selftest` output, not
asserted here.

  * `selftest` on the bare interpreter (Homebrew CPython 3.14.6), through the stand-ins —
    125 checks, 0 failures. It spawns real subprocesses on real TCP ports and drives real HTTP
    round-trips; the twelve scenarios take roughly a minute, most of it mutant [1] honouring
    the original's own 10-second startup deadline twice.
  * REAL pytest 9.1.1 + REAL pytest-asyncio 1.4.0 running this file — the three tests
    collected under their ticket names and all three PASSED, against a staged reference
    `coupler.server` spawned as a real subprocess.
  * REAL pytest running the ORIGINAL's 4058 bytes verbatim, against the SAME reference server
    and the SAME injected client — also 3 passed. Same verdicts as this file. The differential
    therefore holds under real pytest, not only under the built-in runner's stand-ins.
  * REAL pytest with `-m "not slow"` on this file — "3 deselected, 0 selected", which is the
    original docstring's published contract, and clean of warnings because `pyproject.toml`
    registers the `slow` marker.
  * `pip install -e .` into a virtualenv, from a copy of this package in a temp tree — exit 0.
    `import coupler.tests.test_integration` then works from the installed copy with the cwd
    OUTSIDE the package, the `forge2-coupler-test-integration` console script runs, and
    `install-check` resolves the config object by walking up to the shipped `registry.json`
    with no environment variable set. The package COPY is what gets installed, so the source
    tree never receives an `.egg-info`; a before/after listing of the source tree confirmed it
    was byte-for-byte untouched.
  * The two additions this ticket makes to the surrounding package — `coupler/tests/__init__.py`
    and the hand-written `pyproject.toml` entries — were checked for collateral damage by
    importing every sibling unit with and without them. The results are identical either way:
    `test_build` and `test_coupler` import cleanly both times, and `test_bridge`
    (`No module named 'coupler.config'`) and `_status_contract_double` (`No module named
    'httpx'`) fail identically both times. Both of those failures predate this ticket and are
    not its to fix.

Not run, and not claimed:

  * REAL `fastmcp` was never installed here — it is not reachable from this sandbox (it pulls
    `fastmcp-slim[client,server]`, which needs compiled dependencies). So the assertion that
    a REAL FastMCP client speaks to a REAL `coupler.server` over a REAL SSE transport is NOT
    demonstrated by this file, and is not claimed to be. What IS demonstrated is that this
    rewrite issues the same client calls, in the same order, with the same arguments, and
    reaches the same verdict from the same answers as the original — because both were run
    against the same injected client. The MCP wire format is fastmcp's behavior, not this
    unit's, and the original could not test it without fastmcp either.
  * Nothing about pytest's behavior on versions other than the 9.1.1/1.4.0 exercised here.
    The two places pytest's own API could bite are handled by not depending on it —
    `_fixture_impl` reaches `_server_port_impl` rather than calling a decorated fixture
    (pytest 8.4+ returns a `FixtureFunctionDefinition` that refuses a direct call), and the
    surface check reads this file's AST rather than any marker attribute (the
    `_pytestfixturefunction` attribute those versions removed).

RUNNING IT
----------
Every command below is executable as written FROM THE PACKAGE ROOT — the directory holding
`pyproject.toml`, two levels above this file. The `-m` form is what makes them run without
installing anything: it puts the package root on the import path, so `coupler` resolves.
Running the file by path (`python3 coupler/tests/test_integration.py`) does NOT work
uninstalled, because Python would put `coupler/tests/` on the import path instead of the
package root, and the `coupler` package would not be importable. That mistake is foreseeable,
so it is ANSWERED rather than merely warned about: it exits 2 with a `usage error:` line
naming the invocation that does work — no traceback, and no bug report, because the tool is
not the thing that is broken. See `UsageError`.

    python3 -m coupler.tests.test_integration selftest       # differential, mutants, gate, surface
    python3 -m coupler.tests.test_integration install-check  # what can be checked of the package
    python3 -m coupler.tests.test_integration show-deps      # report pytest/pytest_asyncio/fastmcp
    python3 -m coupler.tests.test_integration emit-config    # print a config-object template
    python3 -m coupler.tests.test_integration show-config    # print the resolved config + its source

Once installed (see INSTALLABLE), the console script runs from any directory:

    forge2-coupler-test-integration selftest

Under real pytest the ordinary invocation works and is the point — pytest puts the rootdir on
the import path itself, so the `-m` dance is not needed:

    pip install -e ".[test]"
    pytest coupler/tests/test_integration.py -v     # runs the three tests above
    pytest coupler/tests/test_integration.py -m "not slow"   # deselects all three

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, committed in full beside it:
`pyproject.toml`, `registry.json`, `coupler/__init__.py`, `coupler/_config.py`,
`coupler/tests/__init__.py`. From the package root:

    pip install -e .
    forge2-coupler-test-integration selftest

`pyproject.toml` declares `coupler` and `coupler.tests` in `[tool.setuptools] packages`, so an
installed copy imports as `coupler.tests.test_integration` — the path the forge unit was
originally addressed by (repo `code__code-invalid__coupler`, path
`coupler/tests/test_integration.py`). See the comment in `pyproject.toml` for why those
entries are needed on top of what `congruency/tools/forge_package.py` (#410) generates: that
generator enumerates only TOP-LEVEL modules of a forge package, and this package's units live
in the `coupler/` subpackage, so its generated form declares no package this module is in.

SIDE EFFECTS
------------
The three tests spawn a subprocess, open sockets and create files, and always have: that is
what an integration test is for. Specifically, `server_port` writes the configured build
document inside the temp directory `tmp_path_factory` hands it and nothing outside it; binds
a socket to port 0 on the configured host to find a free port; spawns the configured server
module as a child process with a COPY of the environment (`os.environ` itself is never
mutated, so nothing leaks into the next test); connects to it on loopback; and always
terminates it — `terminate()`, then `kill()` if it outlives the configured timeout. Under
pytest, pytest owns the temp directory's lifetime; under the built-in runner, `selftest`
removes it.

Traffic is loopback-only: the fixture probes `bind_host` and the tests dial `sse_url`, both
`127.0.0.1` in the shipped config. Nothing here reaches the network.

`selftest` additionally writes its reference/mutant `coupler.server` into a temp directory it
removes, and it never writes into the source tree. It spawns those servers as real
subprocesses and reaps every one of them in a `finally`; check [13] proves no server outlives
the run.

The one thing that can write outside a temp directory is the command line, which per
`note-for-claude` ("all tools need to pass a bug-report automatically (timestamped if an
exception is thrown)") appends one timestamped JSON line to the config's `bug_reports` path if
it hits an UNEXPECTED exception — a defect in this tool. The report records the invocation that
ACTUALLY ran (`_invocation`) rather than a fixed string, so a reader can reproduce what
happened. `ConfigError` and `UsageError` are designed behavior, not bugs, and neither is
reported: a sink that fired on a mistyped command would bury the real defects under false
ones. Each files no report, prints no traceback, and exits 2 with a single self-explaining
line. (CPython still writes its usual `__pycache__` bytecode for any module it imports; that
is the interpreter's doing, and #377 lists `__pycache__` among the build artifacts that are
regenerated by any install and never committed.)
"""

import argparse
import ast
import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── the pytest dependency ─────────────────────────────────────────────────────────────────
#
# Real pytest when it is installed — the original imported it at module scope, and under
# pytest this rewrite uses exactly what the original used. The stand-ins below are reached
# only on an interpreter where pytest is absent, and supply the only three things this module
# needs from it: `fixture`, `mark` and `fail`. See THE THREE THIRD-PARTY DEPENDENCIES in the
# module docstring.

try:
    import pytest

    HAVE_PYTEST = True
except ImportError:  # pragma: no cover — depends on the interpreter, not on a branch
    HAVE_PYTEST = False

# The original imports pytest_asyncio and never references it: the import IS the use, because
# the plugin registers with pytest through an entry point rather than through this name. So
# there is nothing to stand in for — only something to report. `show-deps` prints this.
try:
    import pytest_asyncio  # noqa: F401 — imported for its plugin, exactly as the original did

    HAVE_PYTEST_ASYNCIO = True
except ImportError:  # pragma: no cover — depends on the interpreter, not on a branch
    HAVE_PYTEST_ASYNCIO = False


class _FixtureStandIn:
    """Stand-in for `pytest.fixture`, used only where pytest is not installed.

    Under real pytest, `@pytest.fixture(scope="module")` marks a function so that any test
    naming it as a parameter receives its value, built once per module. With no pytest to read
    the mark, the stand-in records it and returns the function UNCHANGED, and `_run_module`
    below resolves and scopes the fixture itself. Both call forms are accepted — bare
    `@fixture` and `@fixture(scope=...)` — because the original uses the second.
    """

    def __call__(self, *args, **kwargs):
        if len(args) == 1 and not kwargs and callable(args[0]):
            args[0].__is_fixture__ = True
            args[0].__fixture_scope__ = "function"
            return args[0]

        def decorator(func):
            func.__is_fixture__ = True
            func.__fixture_scope__ = kwargs.get("scope", "function")
            return func

        return decorator


class _MarkStandIn:
    """Stand-in for `pytest.mark`, used only where pytest is not installed.

    `pytest.mark.slow` and `pytest.mark.asyncio` are attribute lookups that yield a decorator.
    With no pytest to collect the marks, the stand-in records the name on the function and
    hands the function back untouched — a mark changes SELECTION and scheduling, never what a
    test asserts, so recording it is the whole job. `selftest` reads the marks off this file's
    AST rather than off these attributes, so this stand-in is not what check [5] trusts.
    """

    def __getattr__(self, name):
        def decorator(func):
            marks = getattr(func, "__pytest_marks__", ())
            func.__pytest_marks__ = marks + (name,)
            return func

        return decorator


class _Failed(AssertionError):
    """What the stand-in `pytest.fail` raises. An AssertionError, because a failed fixture is
    a failing verdict rather than a crash — which is how real `pytest.fail` reads too."""


class _PytestStandIn:
    """Stand-in for the `pytest` module, used only where pytest is not installed."""

    fixture = _FixtureStandIn()
    mark = _MarkStandIn()
    Failed = _Failed

    @staticmethod
    def fail(msg="", pytrace=True):
        """Fail the calling test outright, as `pytest.fail` does."""
        raise _Failed(msg)


if not HAVE_PYTEST:  # pragma: no cover — depends on the interpreter, not on a branch
    pytest = _PytestStandIn()

# ── the fastmcp dependency ────────────────────────────────────────────────────────────────
#
# Deliberately NOT given a fallback stand-in. See THE THREE THIRD-PARTY DEPENDENCIES in the
# module docstring: a stand-in client cannot speak real MCP to a real server, so falling back
# to one would make these tests report a wrong verdict — FAILURE against a good server — where
# the original merely raised ImportError. `None` here, plus `_require_fastmcp()` inside each
# test, preserves the original's exception type while still letting pytest collect the module.
#
# These two are module-level names looked up at CALL time, which is what lets `selftest`
# inject its own client. Binding them into a local or a default argument would make the
# injection invisible.

try:
    from fastmcp import Client
    from fastmcp.client.transports import SSETransport

    HAVE_FASTMCP = True
except ImportError:  # pragma: no cover — depends on the interpreter, not on a branch
    Client = None
    SSETransport = None
    HAVE_FASTMCP = False


# ─────────────────────────────── configuration ───────────────────────────────

#: Environment variable naming a file that holds THIS unit's config object.
CONFIG_ENV = "COUPLER_TEST_INTEGRATION_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS
#: in the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own.
UNIT_PATH = ("forge2", "code__code-invalid__coupler", "coupler.tests.test_integration")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code-invalid__coupler/coupler/tests/test_integration"

#: This module's own dotted import name. It is `UNIT_PATH`'s last element by construction — a
#: unit's address inside the registry IS its dotted path within the package — so it is derived
#: rather than written twice and cannot drift from it. Used only to print an invocation a
#: reader can retype; `__name__` is "__main__" under `-m` and `__spec__` is None when this file
#: is run by path, so neither can answer this on its own.
DOTTED_NAME = UNIT_PATH[-1]


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and ticket #377's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.
    """


class UsageError(RuntimeError):
    """Raised when this module was INVOKED in a way that cannot work — not a defect in it.

    Kept apart from every other exception for the same reason `ConfigError` is: the command
    line reports both as one self-explaining line and files NO bug report, because a bug report
    is supposed to mean "this tool is broken". The foreseeable case is running this file by
    path (`python3 coupler/tests/test_integration.py`), which puts `coupler/tests/` on the
    import path instead of the package root and so leaves the `coupler` package unimportable.
    That is a mistake the message can fix in one line; answering it with a traceback and a
    filed bug report would blame the tool for the invocation and put a false record in the sink.
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do the three tests throw `ConfigError`. Every value
    below is one the ORIGINAL hardcoded, so a config built from this template makes the tests
    behave exactly as the original's did.
    """
    return {
        "server_module": "coupler.server",
        "server_args": ["--port", "{port}"],
        "bind_host": "127.0.0.1",
        "sse_url": "http://127.0.0.1:{port}/sse",
        "tmp_prefix": "jazz",
        "build_json_path": "conf/env/build.json",
        "build_json": {"version": "1.0.0", "envs": {}},
        "jazz_root_env": "JAZZ_ROOT",
        "jazz_dev_env": "JAZZ_DEV",
        "jazz_dev_value": "/nonexistent",
        "port_env": "COUPLER_PORT",
        "pythonpath_env": "PYTHONPATH",
        "pythonpath_parents": 3,
        "startup_timeout": 10,
        "connect_timeout": 0.5,
        "poll_interval": 0.2,
        "communicate_timeout": 5,
        "terminate_timeout": 5,
        "startup_failure_message": "Server did not start in time.\nstdout: {out}\nstderr: {err}",
        "status_tool": "coupler_status",
        "status_self_key": "coupler",
        "status_self_ok": "ok",
        "status_version_key": "jazz_version",
        "status_services": ["notes", "notes_db", "z3"],
        "status_legal_states": ["ok", "down", "degraded"],
        "ui_tool": "ui_list_pages",
        "why5_tool": "why5_new",
        "why5_arguments": {"session_id": "test-session", "trigger": "integration test"},
        "why5_expect_substring": "test-session",
    }


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
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. "
                "Run `emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH)))
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError("the registry section %s at %s must be a JSON object, not %s"
                          % (".".join(UNIT_PATH), registry_path, type(node).__name__))

    config = dict(node)
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit
    # section may state its own to override it. This is inheritance inside ONE config
    # document, not a guessed default — if neither states it, the key stays absent and the CLI
    # files no report.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


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


def _as_tuple(types_):
    return types_ if isinstance(types_, tuple) else (types_,)


def require(section, key, where, types_):
    """Return `section[key]`, proving it is present and of the right type; else ConfigError.

    Type-checking here rather than letting a bad value flow onward is deliberate: a config
    mistake must surface as a config error naming the key, not as a puzzling `TypeError` from
    inside a test, where a reader would take it for a verdict about `coupler.server`.

    `bool` is rejected wherever `int` is asked for and `bool` was not itself named. Python
    makes `True` an `int`, so `"startup_timeout": true` would otherwise sail through and be
    used as a one-second deadline — a config mistake silently reshaping a timeout.

    Args:
        section: the config object (or sub-object) to read.
        key: the key to require.
        where: how to describe `section` in an error message.
        types_: a type or tuple of types the value must be an instance of.

    Raises:
        ConfigError: if the key is absent or holds the wrong type.
    """
    if not isinstance(section, dict) or key not in section:
        raise ConfigError("config object for %s is missing the required key %r under %s. Run "
                          "`emit-config` for a template." % (UNIT, key, where))
    value = section[key]
    wanted = _as_tuple(types_)
    if not isinstance(value, wanted) or (isinstance(value, bool) and bool not in wanted):
        names = " or ".join(t.__name__ for t in wanted)
        raise ConfigError("config key %r under %s for %s must be %s, not %s"
                          % (key, where, UNIT, names, type(value).__name__))
    return value


def require_number(section, key, where):
    """Return `section[key]` as a number (int or float, never bool); else ConfigError.

    The original's timeouts are a mix of ints (10, 5) and floats (0.5, 0.2), so both are
    legitimate here and the pair is asked for together.
    """
    return require(section, key, where, (int, float))


def require_str_list(section, key, where):
    """Return `section[key]` as a list of strings; else ConfigError.

    The element type is checked here rather than at use, so a config holding
    `"status_services": ["notes", 3]` is a config error naming the key, not a `TypeError`
    surfacing from inside an assertion where it would read as a verdict about the server.
    """
    value = require(section, key, where, list)
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigError("config key %r under %s for %s must hold only strings; item %d "
                              "is %s" % (key, where, UNIT, index, type(item).__name__))
    return value


def _config():
    """Return this unit's config object, throwing if it cannot be seen.

    Every test and `_free_port` call this FIRST, before touching the server, so a missing
    config is reported as a config error rather than as a verdict about `coupler.server`.
    """
    return active_config()


def _require_fastmcp():
    """Prove a FastMCP client is available; else raise the ImportError the original raised.

    The original reached `from fastmcp import Client` at module scope, so a missing fastmcp
    stopped it with `ImportError` before any test ran. This module defers that to the call so
    pytest can still collect and list the three tests, but the exception TYPE and the thing it
    names are the original's. See THE THREE THIRD-PARTY DEPENDENCIES in the module docstring
    for why fastmcp gets no stand-in fallback.
    """
    if Client is None or SSETransport is None:
        raise ImportError(
            "%s drives a real FastMCP client, and fastmcp is not importable. These tests "
            "cannot reach a verdict without it — install it with `pip install -e \".[test]\"` "
            "from the package root. (The original module raised ImportError at import for the "
            "same reason; this raises it here so pytest can still collect the test list.)"
            % UNIT
        )


def _server_pythonpath(config):
    """Return the directory the spawned server gets on its `PYTHONPATH`.

    The original wrote `str(Path(__file__).parent.parent.parent)`: walk three parents up from
    the test file — `tests` -> `coupler` -> the package root — so the child can
    `import coupler.server`. The walk length is `pythonpath_parents`, and with the shipped
    value of 3 this computes the original's expression exactly; `selftest` check [4] proves
    that equality rather than asserting it.

    `server_pythonpath` overrides the walk with an explicit directory. It exists because the
    walk is only correct when this file sits at its installed depth, and `selftest` must point
    the child at a temp tree holding the reference server instead. It is optional: absent, the
    walk decides, which is the original's behavior.

    Raises:
        ConfigError: if neither key is usable.
    """
    explicit = config.get("server_pythonpath")
    if explicit is not None:
        if not isinstance(explicit, str):
            raise ConfigError("config key 'server_pythonpath' under %s for %s must be str, not %s"
                              % (UNIT, UNIT, type(explicit).__name__))
        return explicit
    parents = require(config, "pythonpath_parents", UNIT, int)
    if parents < 0:
        raise ConfigError("config key 'pythonpath_parents' for %s must not be negative, got %d"
                          % (UNIT, parents))
    here = Path(__file__)
    for _ in range(parents):
        here = here.parent
    return str(here)


# ─────────────────────────────── the surface ───────────────────────────────


def _free_port() -> int:
    """Bind port 0 on the configured host and hand back the port the OS chose.

    Reproduces the original's `_free_port`: open a socket, bind it to port 0 — which asks the
    kernel for any free port — read the port back, and close the socket so the server can take
    it. There is an unavoidable race in that (the port is free when we look, and could be
    taken before the child binds it); it is the original's race, and closing this over would
    change behavior rather than preserve it.

    Raises:
        ConfigError: if the config object cannot be seen.
    """
    config = _config()
    host = require(config, "bind_host", UNIT, str)
    with socket.socket() as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _server_port_impl(tmp_path_factory):
    """Start the configured server module on a free port, yield the port, then terminate it.

    Reproduces the original's `server_port` step for step: build a fake jazz tree holding the
    configured build document, pick a free port, spawn the server as a child with the jazz env
    vars and `PYTHONPATH` pointed at the package root, poll the port until it accepts a
    connection, yield it to the tests, and tear the child down afterwards.

    The environment handed to the child is a COPY of `os.environ` with four keys overridden;
    `os.environ` itself is never mutated, so nothing leaks out of this fixture. Startup is
    polled rather than slept on, so a fast server costs one poll interval, not the full
    deadline. If the deadline passes with no connection, the child is terminated, its output
    is collected, and `pytest.fail` reports both streams — that is the original's `while/else`,
    and the reason it reads `out`/`err` is so a reader sees WHY the server never came up.

    Teardown always runs: `terminate()`, then `kill()` if the child outlives the configured
    timeout. This is the body of a `yield` fixture, so pytest runs it after the last test in
    the module.

    Raises:
        ConfigError: if the config object cannot be seen.
    """
    config = _config()

    tmp = tmp_path_factory.mktemp(require(config, "tmp_prefix", UNIT, str))
    env_file = tmp / require(config, "build_json_path", UNIT, str)
    env_file.parent.mkdir(parents=True)
    env_file.write_text(json.dumps(require(config, "build_json", UNIT, dict)))

    port = _free_port()
    env = {
        **os.environ,
        require(config, "jazz_root_env", UNIT, str): str(tmp),
        require(config, "jazz_dev_env", UNIT, str): require(config, "jazz_dev_value", UNIT, str),
        require(config, "port_env", UNIT, str): str(port),
        require(config, "pythonpath_env", UNIT, str): _server_pythonpath(config),
    }

    argv = [sys.executable, "-m", require(config, "server_module", UNIT, str)]
    for arg in require_str_list(config, "server_args", UNIT):
        argv.append(arg.format(port=port))

    proc = subprocess.Popen(
        argv,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    host = require(config, "bind_host", UNIT, str)
    # wait up to the configured deadline for the server to accept connections
    deadline = time.time() + require_number(config, "startup_timeout", UNIT)
    while time.time() < deadline:
        try:
            with socket.create_connection(
                (host, port), timeout=require_number(config, "connect_timeout", UNIT)
            ):
                break
        except OSError:
            time.sleep(require_number(config, "poll_interval", UNIT))
    else:
        proc.terminate()
        out, err = proc.communicate(timeout=require_number(config, "communicate_timeout", UNIT))
        pytest.fail(
            require(config, "startup_failure_message", UNIT, str).format(out=out, err=err)
        )

    yield port

    proc.terminate()
    try:
        proc.wait(timeout=require_number(config, "terminate_timeout", UNIT))
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def server_port(tmp_path_factory):
    """Start coupler/server.py on a free port, yield port, then terminate."""
    yield from _server_port_impl(tmp_path_factory)


async def _test_coupler_status_via_sse_impl(server_port):
    """coupler_status returns valid JSON over a real SSE connection.

    Reproduces the original's first test: connect over SSE, prove the status tool is listed,
    call it, parse its answer as JSON, and check the three things the original checked — that
    the coupler reports itself ok, that a jazz version is present (its VALUE is never
    asserted, only the key), and that every configured service reports one of the legal
    states. The services are expected to be down here: there is no real jazz install behind
    them, which is exactly why "down" is legal rather than a failure.
    """
    # Every config value is read, and type-checked, BEFORE anything else happens. The order is
    # load-bearing: a tool that cannot see its config must throw ConfigError (acceptance item
    # (d)), so the config gate has to fire ahead of the fastmcp check and ahead of any contact
    # with the server. Check [10] pins this down by running the tests with an empty config and
    # requiring ConfigError — on an interpreter with no fastmcp, which is exactly where a
    # later gate would report the wrong problem.
    config = _config()
    url = require(config, "sse_url", UNIT, str).format(port=server_port)
    status_tool = require(config, "status_tool", UNIT, str)
    self_key = require(config, "status_self_key", UNIT, str)
    self_ok = require(config, "status_self_ok", UNIT, str)
    version_key = require(config, "status_version_key", UNIT, str)
    legal = require_str_list(config, "status_legal_states", UNIT)
    services = require_str_list(config, "status_services", UNIT)
    _require_fastmcp()

    async with Client(SSETransport(url)) as c:
        tools = await c.list_tools()
        names = {t.name for t in tools}
        assert status_tool in names

        result = await c.call_tool(status_tool, {})
        text = result.content[0].text
        data = json.loads(text)

        assert data[self_key] == self_ok
        assert version_key in data
        # jazz services will be down (no real jazz install) — that's expected
        for svc in services:
            assert data[svc] in legal


async def _test_ui_tool_available_via_sse_impl(server_port):
    """UI tools are registered and callable (returns error when UI not running).

    Reproduces the original's second test. Note what it does and does not pin down: the tool
    must be listed and must answer with a non-empty STRING. It deliberately does not care what
    the string says, because with no UI running the honest answer is an error message — and
    returning one cleanly, rather than raising, is the property under test.
    """
    config = _config()  # the config gate fires first — see _test_coupler_status_via_sse_impl
    url = require(config, "sse_url", UNIT, str).format(port=server_port)
    ui_tool = require(config, "ui_tool", UNIT, str)
    _require_fastmcp()

    async with Client(SSETransport(url)) as c:
        tools = {t.name for t in await c.list_tools()}
        assert ui_tool in tools

        result = await c.call_tool(ui_tool, {})
        text = result.content[0].text
        # either works or returns a clean error string — not an exception
        assert isinstance(text, str)
        assert len(text) > 0


async def _test_why5_tool_available_via_sse_impl(server_port):
    """why5 tools are present if jazz dev tree is available, absent otherwise.

    Reproduces the original's third test, INCLUDING its conditional: the why5 tools are
    optional, so if the configured tool is not listed the test passes having asserted nothing.
    That is not a defect to be fixed here — it is the original's behavior, and #377 asks for a
    behavior-preserving rewrite rather than a better test suite. It matters in practice: the
    fixture pins `$JAZZ_DEV` at a path that does not exist, so a server that offers why5 only
    when the jazz dev tree is there does not list it and this test is VACUOUS in the shipped
    configuration. See EDGE_CASES, and scenarios [R1], [R2] and mutant [10], which between them
    prove both halves of the branch — and prove the assertion is live rather than decorative.
    """
    config = _config()  # the config gate fires first — see _test_coupler_status_via_sse_impl
    url = require(config, "sse_url", UNIT, str).format(port=server_port)
    why5_tool = require(config, "why5_tool", UNIT, str)
    why5_arguments = require(config, "why5_arguments", UNIT, dict)
    why5_expect = require(config, "why5_expect_substring", UNIT, str)
    _require_fastmcp()

    async with Client(SSETransport(url)) as c:
        tools = {t.name for t in await c.list_tools()}
        # why5 tools are optional — just verify no crash either way
        if why5_tool in tools:
            result = await c.call_tool(why5_tool, why5_arguments)
            assert why5_expect in result.content[0].text


@pytest.mark.slow
@pytest.mark.asyncio
async def test_coupler_status_via_sse(server_port):
    """coupler_status returns valid JSON over a real SSE connection."""
    await _test_coupler_status_via_sse_impl(server_port)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_ui_tool_available_via_sse(server_port):
    """UI tools are registered and callable (returns error when UI not running)."""
    await _test_ui_tool_available_via_sse_impl(server_port)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_why5_tool_available_via_sse(server_port):
    """why5 tools are present if jazz dev tree is available, absent otherwise."""
    await _test_why5_tool_available_via_sse_impl(server_port)


# ─────────────────────────────── the equivalence tables ───────────────────────────────

#: The exemplars this rewrite must reproduce: the three scenarios the ORIGINAL defines, plus
#: the fixture they all depend on, with the verdict each reaches. Ticket #377 captured no
#: exemplars (criteria_miner "mines only self-contained pure functions ... and nothing here
#: qualified"), so this table is the hand-written equivalence basis the ticket asks for in its
#: place. Every expected outcome was read off the ORIGINAL's embedded source, never off this
#: rewrite — and `selftest` does not trust even that: it RUNS the original and compares.
#:
#: Each entry is (name, what the scenario stages, the property it pins down).
EXEMPLARS = [
    (
        "server_port",
        "a temp jazz tree holding conf/env/build.json, a free port, and the server module "
        "spawned as a real child process with JAZZ_ROOT/JAZZ_DEV/COUPLER_PORT/PYTHONPATH set",
        "the fixture yields the port only once the server ACCEPTS a TCP connection, and "
        "terminates the child afterwards. If the server never comes up before the deadline it "
        "calls pytest.fail with the child's stdout and stderr, so all three tests fail rather "
        "than hang",
    ),
    (
        "test_coupler_status_via_sse",
        "a live server on the yielded port, dialled over SSE",
        "coupler_status is listed; calling it answers with parseable JSON in which the coupler "
        "reports 'ok', a jazz_version key is PRESENT (its value is never asserted), and each of "
        "notes/notes_db/z3 reports one of ok/down/degraded — down is legal, because no real "
        "jazz install is behind them",
    ),
    (
        "test_ui_tool_available_via_sse",
        "the same live server, dialled over SSE",
        "ui_list_pages is listed, and calling it returns a non-empty string rather than raising "
        "— with no UI running a clean error string is a PASS, which is the whole point of the "
        "test; what the string says is deliberately not asserted",
    ),
    (
        "test_why5_tool_available_via_sse",
        "the same live server, dialled over SSE, with JAZZ_DEV pointed at a path that does not "
        "exist",
        "why5_new is OPTIONAL: if it is listed, calling it must echo the session id back in its "
        "answer; if it is not listed, the test passes having asserted nothing. Both halves are "
        "the original's, and both are proven — see EDGE_CASES",
    ),
]

#: Edge cases the four exemplars cannot reach on their own. #377 asks for "the edge cases you
#: add for what sampling cannot reach", and these are they. Each entry is (label, why the
#: exemplars cannot reach it) — and each is PROVEN by a numbered check in `selftest`, not
#: merely listed.
EDGE_CASES = [
    ("the three tests DISCRIMINATE — each mutant server is failed by exactly the tests that "
     "should fail it, and the original agrees test-for-test",
     "all three exemplars passing proves only that a correct server passes; a test that cannot "
     "fail would pass them just as happily. MUTANTS is the negative half of the differential"),
    ("test_why5_tool_available_via_sse is VACUOUS in the shipped configuration",
     "the fixture pins JAZZ_DEV at a path that does not exist, so a server that offers why5 "
     "only when the jazz dev tree is there never lists why5_new and the test asserts NOTHING. "
     "No exemplar can show this, because a passing test looks identical whether its assertion "
     "ran or was skipped. Scenarios [R1], [R2] and mutant [10] separate the two: [R1] leaves "
     "the assertion unreached, [R2] lists why5_new so the assertion runs and passes, and [10] "
     "lists it with a wrong echo so the assertion runs and FAILS — which is what proves the "
     "assertion is live rather than decorative. Preserved deliberately: #377 asks for a "
     "behavior-preserving rewrite, not a better test suite"),
    ("a server that never starts fails all three tests through the FIXTURE, and does not hang",
     "the exemplars all run against a server that DID start, so none of them can show what the "
     "10-second deadline and the while/else are for. Mutant [1] is that case, and it also "
     "proves the failure message carries the child's stdout and stderr"),
    ("one server serves all three tests — scope='module', not per-test",
     "no single exemplar can show this; it is visible only by counting the servers actually "
     "spawned across a whole module run, which check [12] does. A function-scoped rewrite "
     "would pass every exemplar while spawning three servers and taking three times as long"),
    ("no server outlives the run, on any path",
     "a test that passes says nothing about whether the child was reaped. Check [13] proves "
     "every spawned port is dead once the module run is over, including the mutant path where "
     "the fixture itself failed"),
    ("the config gate — each test and _free_port throws ConfigError, and reaches NO verdict, "
     "when the config cannot be resolved",
     "the exemplars all run WITH a config, so none of them can show what happens without one; "
     "acceptance item (d) is exactly that case"),
    ("without fastmcp, each test raises ImportError naming fastmcp — the original's exception "
     "type, and not a wrong verdict about the server",
     "the exemplars all run WITH a client injected, so none of them can show the absent-fastmcp "
     "path, which is the path a bare interpreter actually takes"),
    ("the PYTHONPATH handed to the child equals the original's own expression",
     "the exemplars run against a temp tree with an explicit server_pythonpath, so none of them "
     "exercises the three-parent walk the shipped config uses. Check [4] evaluates the "
     "original's `Path(__file__).parent.parent.parent` against this file and compares"),
    ("the callable surface, the two marks and the fixture scope are the ticket's, lowered from "
     "this file's own AST",
     "running the tests cannot show that they present the right names, parameters, marks and "
     "scope to pytest; only lowering the source can"),
]


# ─────────────────────────────── the oracle ───────────────────────────────

#: The ORIGINAL forge unit, embedded verbatim from ticket #377 — 4058 bytes, byte for byte.
#: This is the behavior-preserving basis, and `selftest` does not merely read it: it EXECUTES
#: it against the same servers this rewrite is run against and compares the verdicts. Keeping
#: the original here is what makes the equivalence a measurement rather than an assertion.
#:
#: A RAW string, deliberately. The original contains `\n` escapes inside its f-string failure
#: message; in a cooked string those would become real newlines and the embedded copy would no
#: longer be the original's bytes. Checks [1] and [2] would both catch that — which is what
#: they are for.
ORIGINAL_SOURCE = r'''"""
Integration tests — real server, real FastMCP client.

Spins up coupler/server.py on a random port, connects a FastMCP client,
and exercises the actual tool round-trip. Requires the coupler package
installed and a working Python, but no live jazz services.

Marked with @pytest.mark.slow — skip with: pytest -m "not slow"
"""
import asyncio
import json
import os
import socket
import sys
import time
from pathlib import Path

import pytest
import pytest_asyncio

from fastmcp import Client
from fastmcp.client.transports import SSETransport


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server_port(tmp_path_factory):
    """Start coupler/server.py on a free port, yield port, then terminate."""
    tmp = tmp_path_factory.mktemp("jazz")
    env_dir = tmp / "conf" / "env"
    env_dir.mkdir(parents=True)
    (env_dir / "build.json").write_text(json.dumps({
        "version": "1.0.0",
        "envs": {},
    }))

    port = _free_port()
    env = {
        **os.environ,
        "JAZZ_ROOT": str(tmp),
        "JAZZ_DEV":  "/nonexistent",
        "COUPLER_PORT": str(port),
        "PYTHONPATH": str(Path(__file__).parent.parent.parent),
    }

    import subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "coupler.server", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # wait up to 10s for the server to accept connections
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    else:
        proc.terminate()
        out, err = proc.communicate(timeout=5)
        pytest.fail(f"Server did not start in time.\nstdout: {out}\nstderr: {err}")

    yield port

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.slow
@pytest.mark.asyncio
async def test_coupler_status_via_sse(server_port):
    """coupler_status returns valid JSON over a real SSE connection."""
    async with Client(SSETransport(f"http://127.0.0.1:{server_port}/sse")) as c:
        tools = await c.list_tools()
        names = {t.name for t in tools}
        assert "coupler_status" in names

        result = await c.call_tool("coupler_status", {})
        text = result.content[0].text
        data = json.loads(text)

        assert data["coupler"] == "ok"
        assert "jazz_version" in data
        # jazz services will be down (no real jazz install) — that's expected
        for svc in ("notes", "notes_db", "z3"):
            assert data[svc] in ("ok", "down", "degraded")


@pytest.mark.slow
@pytest.mark.asyncio
async def test_ui_tool_available_via_sse(server_port):
    """UI tools are registered and callable (returns error when UI not running)."""
    async with Client(SSETransport(f"http://127.0.0.1:{server_port}/sse")) as c:
        tools = {t.name for t in await c.list_tools()}
        assert "ui_list_pages" in tools

        result = await c.call_tool("ui_list_pages", {})
        text = result.content[0].text
        # either works or returns a clean error string — not an exception
        assert isinstance(text, str)
        assert len(text) > 0


@pytest.mark.slow
@pytest.mark.asyncio
async def test_why5_tool_available_via_sse(server_port):
    """why5 tools are present if jazz dev tree is available, absent otherwise."""
    async with Client(SSETransport(f"http://127.0.0.1:{server_port}/sse")) as c:
        tools = {t.name for t in await c.list_tools()}
        # why5 tools are optional — just verify no crash either way
        if "why5_new" in tools:
            result = await c.call_tool("why5_new", {
                "session_id": "test-session",
                "trigger": "integration test"
            })
            assert "test-session" in result.content[0].text
'''

#: The size ticket #377 records for the module under rewrite. Check [1] asserts the embedded
#: `ORIGINAL_SOURCE` weighs exactly this.
ORIGINAL_SIZE = 4058

#: The git blob sha1 ticket #377 records for the module under rewrite, at refs/heads/stable.
#: Check [2] recomputes it over `ORIGINAL_SOURCE` using git's own object rule —
#: sha1(b"blob " + len + b"\0" + bytes) — and compares. This is what makes the oracle THE
#: ORIGINAL rather than a plausible transcription of it: the hash cannot agree by accident.
ORIGINAL_BLOB_SHA1 = "200447c35c9708ee1659c72a6c168e944c3026a3"

#: The names of the three tests, in the ticket's order. Both modules are run through these.
TEST_NAMES = [
    "test_coupler_status_via_sse",
    "test_ui_tool_available_via_sse",
    "test_why5_tool_available_via_sse",
]

#: The ticket's callable surface, verbatim. Check [5] lowers this file's own AST and compares.
TICKET_SURFACE = [
    "_free_port() -> int",
    "server_port(tmp_path_factory)",
    "async test_coupler_status_via_sse(server_port)",
    "async test_ui_tool_available_via_sse(server_port)",
    "async test_why5_tool_available_via_sse(server_port)",
]

#: Environment variable the reference server reads to break exactly one clause of its contract.
MUTATION_ENV = "FORGE2_COUPLER_INTEGRATION_MUTATION"

#: A faithful reconstruction of the MODULE UNDER TEST, used ONLY by `selftest`.
#:
#: `coupler.server` is a different forge module with its own rewrite ticket and has not landed
#: here; #377 covers "ONE module ... and nothing else", so this file does not ship one. But a
#: test module cannot be proven against nothing, so `selftest` writes THIS into a temp tree and
#: spawns it as the configured `server_module`.
#:
#: Every line below is derived from the ORIGINAL TEST's own statements about `coupler.server`,
#: and from nothing else:
#:   * it is runnable as `python -m coupler.server --port N` and accepts a `--port` argument —
#:     that is the argv the fixture spawns.
#:   * it reads `JAZZ_ROOT` and `COUPLER_PORT` from the environment at import, because the
#:     fixture sets both before spawning it.
#:   * it listens on 127.0.0.1 and accepts TCP connections — the fixture polls the port with
#:     `socket.create_connection` and only yields once that succeeds.
#:   * it lists tools named `coupler_status` and `ui_list_pages` — `test_coupler_status_via_sse`
#:     and `test_ui_tool_available_via_sse` assert exactly that.
#:   * `coupler_status` answers with JSON carrying `coupler: "ok"`, a `jazz_version` read from
#:     the build document under JAZZ_ROOT, and one of ok/down/degraded for notes, notes_db and
#:     z3 — the first test spells this out key by key. The services report "down": the original
#:     says so in its own comment, "jazz services will be down (no real jazz install)".
#:   * `ui_list_pages` answers with a non-empty string even when no UI is running — the second
#:     test's comment says "either works or returns a clean error string".
#:   * `why5_new` is OPTIONAL, and echoes the session id it is given — the third test's
#:     docstring says "why5 tools are present if jazz dev tree is available, absent otherwise",
#:     and it asserts the echo when the tool is there. Whether this server lists it is switched
#:     by the MUTATION variable rather than by `JAZZ_DEV`; `_tool_names` explains why at the
#:     point of decision, and it is a fairness requirement of the differential rather than a
#:     shortcut. The shipped situation is that it is NOT listed, which is what makes the third
#:     test vacuous. See EDGE_CASES.
#:
#: It speaks JSON-over-HTTP rather than the MCP/SSE wire format, and the client `selftest`
#: injects speaks the same. That pairing is honest about what is and is not proven here: the
#: wire format is FASTMCP's behavior, not this unit's, and real fastmcp is not installable in
#: this sandbox (see WHAT HAS ACTUALLY BEEN RUN). What the differential does prove is that this
#: rewrite makes the same client calls with the same arguments and reaches the same verdicts
#: from the same answers as the original — while the subprocess, the port, the startup poll and
#: the teardown are all REAL.
#:
#: What makes this a fair oracle rather than a target this rewrite was fitted to: `selftest`
#: runs the ORIGINAL against it too, and the original passes all three.
REFERENCE_SERVER = r'''"""Reference stand-in for coupler.server — selftest scaffolding only."""
import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

MUTATION = os.environ.get("FORGE2_COUPLER_INTEGRATION_MUTATION", "")
JAZZ_ROOT = Path(os.environ.get("JAZZ_ROOT", "/nonexistent"))
JAZZ_DEV = Path(os.environ.get("JAZZ_DEV", "/nonexistent"))


def _load_build():
    p = JAZZ_ROOT / "conf" / "env" / "build.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _tool_names():
    names = []
    if MUTATION != "no-status-tool":
        names.append("coupler_status")
    if MUTATION != "no-ui-tool":
        names.append("ui_list_pages")
    # "why5 tools are present if jazz dev tree is available, absent otherwise" — the original
    # test's own docstring. why5 presence is switched by the MUTATION variable rather than by
    # JAZZ_DEV, and that is a correctness requirement of the differential, not a shortcut.
    # BOTH modules pin JAZZ_DEV at a path that does not exist — this rewrite from its config,
    # the ORIGINAL from a hardcoded "/nonexistent" it offers no way to steer — so a server that
    # keyed why5 off JAZZ_DEV could never list it for the original, and the why5-present branch
    # would be unreachable on one side of a comparison that is supposed to be like-for-like.
    # The MUTATION variable is read from the environment the fixture COPIES (`{**os.environ}`),
    # which both modules do identically, so both children see the same switch.
    if MUTATION in ("why5-present", "why5-wrong-echo"):
        names.append("why5_new")
    return names


def _status():
    answer = {}
    answer["coupler"] = "degraded" if MUTATION == "self-not-ok" else "ok"
    if MUTATION != "no-version-key":
        answer["jazz_version"] = _load_build().get("version")
    state = "unknown" if MUTATION == "illegal-state" else "down"
    for svc in ("notes", "notes_db", "z3"):
        if MUTATION == "missing-service" and svc == "z3":
            continue
        answer[svc] = state
    return json.dumps(answer)


def _call(name, arguments):
    if name == "coupler_status":
        if MUTATION == "status-not-json":
            return "coupler_status exploded: not json at all"
        return _status()
    if name == "ui_list_pages":
        if MUTATION == "ui-empty":
            return ""
        return json.dumps({"pages": [], "error": "UI not running"})
    if name == "why5_new":
        if MUTATION == "why5-wrong-echo":
            return json.dumps({"session": "a-different-session", "ok": True})
        return json.dumps({"session": arguments.get("session_id"),
                           "trigger": arguments.get("trigger")})
    raise KeyError(name)


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length) or b"{}")
        op = request.get("op")
        if op == "list_tools":
            body = {"tools": [{"name": n} for n in _tool_names()]}
        elif op == "call_tool":
            body = {"text": _call(request["name"], request.get("arguments") or {})}
        else:
            body = {"error": "unknown op %r" % (op,)}
        blob = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def log_message(self, *args):
        """Silence the access log: the fixture pipes stdout/stderr and only reads them when the
        server FAILED to start, where request noise would bury the reason."""


def main(argv=None):
    parser = argparse.ArgumentParser(prog="coupler.server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("COUPLER_PORT") or 0))
    args = parser.parse_args(argv)
    if MUTATION == "never-starts":
        sys.stderr.write("refusing to start: FORGE2_COUPLER_INTEGRATION_MUTATION=never-starts\n")
        return 1
    HTTPServer(("127.0.0.1", args.port), _Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

#: The mutants: deliberately broken `coupler.server` behaviors, each with the tests that MUST
#: fail against it. This is the negative half of the differential — the half that proves these
#: tests can fail at all. `selftest` checks two things per mutant: that this rewrite fails
#: exactly the named tests, and that the ORIGINAL reaches the identical verdict.
#:
#: Each entry is (label, mutation name, {names of tests that must FAIL}).
MUTANTS = [
    (
        "[1] the server never starts — the fixture's deadline expires",
        "never-starts",
        set(TEST_NAMES),  # every test depends on the fixture, so all three fail
    ),
    (
        "[2] coupler_status is not listed among the tools",
        "no-status-tool",
        {"test_coupler_status_via_sse"},
    ),
    (
        "[3] the coupler reports itself degraded rather than ok",
        "self-not-ok",
        {"test_coupler_status_via_sse"},
    ),
    (
        "[4] the jazz_version key is absent from the status answer",
        "no-version-key",
        {"test_coupler_status_via_sse"},
    ),
    (
        "[5] a service reports a state outside ok/down/degraded",
        "illegal-state",
        {"test_coupler_status_via_sse"},
    ),
    (
        "[6] a service is missing from the status answer entirely",
        "missing-service",
        {"test_coupler_status_via_sse"},
    ),
    (
        "[7] coupler_status answers with something that is not JSON",
        "status-not-json",
        {"test_coupler_status_via_sse"},
    ),
    (
        "[8] ui_list_pages is not listed among the tools",
        "no-ui-tool",
        {"test_ui_tool_available_via_sse"},
    ),
    (
        "[9] ui_list_pages answers with an empty string",
        "ui-empty",
        {"test_ui_tool_available_via_sse"},
    ),
    (
        "[10] why5_new is listed but does not echo the session id back",
        "why5-wrong-echo",
        {"test_why5_tool_available_via_sse"},
    ),
]

#: The two faithful references. Each entry is (label, mutation name, expected failures) — and
#: both expect NONE, which is the positive half of the differential.
#:
#: The pair exists because `test_why5_tool_available_via_sse` branches on whether why5_new is
#: listed, and only ONE of these reaches its assertion. [R1] is the shipped situation: why5 is
#: not listed, so the test passes having asserted nothing. [R2] switches why5 on so the echo is
#: genuinely checked. Without [R2], mutant [10] would be the only evidence that the test can
#: fail; without [R1], nothing would show that it is vacuous in the shipped configuration. See
#: EDGE_CASES.
#:
#: Both are driven by the MUTATION variable rather than by JAZZ_DEV, and `REFERENCE_SERVER`'s
#: `_tool_names` explains why at length: the ORIGINAL hardcodes `JAZZ_DEV: "/nonexistent"` and
#: offers no way to steer it, so a JAZZ_DEV-keyed switch would move this rewrite and leave the
#: original where it was — the two would be answering different questions, and the comparison
#: would prove nothing. An earlier draft of this selftest did exactly that; the differential
#: caught it, which is the point of running the original rather than trusting a table.
REFERENCES = [
    ("[R1] the reference server, why5 not listed (the shipped situation — JAZZ_DEV is pinned at "
     "a path that does not exist, so test_why5_tool_available_via_sse asserts nothing)",
     "", set()),
    ("[R2] the reference server, why5_new listed (so test_why5_tool_available_via_sse reaches "
     "its assertion and passes)", "why5-present", set()),
]


# ─────────────────────────────── the injected client ───────────────────────────────
#
# `selftest` scaffolding, and ONLY that. This is NOT the module-level fallback for a missing
# fastmcp — there deliberately is none (see THE THREE THIRD-PARTY DEPENDENCIES). It is injected
# into BOTH this module's globals and the original's namespace for the duration of a
# differential run, so both sides make the same calls against the same client and any
# distortion it introduces lands on both equally.
#
# It speaks JSON-over-HTTP to REFERENCE_SERVER over a REAL socket on a REAL port: the transport
# is faked, the round-trip is not.

#: How long the injected client waits on a round-trip. Scaffolding, not a unit setting: the
#: reference server answers from memory on loopback, so any expiry here means the server died,
#: and a test hanging forever on a dead server would be worse than a failure.
_CLIENT_TIMEOUT = 10


class _StandInTool:
    """One entry in `list_tools()`. The original reads only `.name`, so that is all there is."""

    def __init__(self, name):
        self.name = name


class _StandInTextBlock:
    """One content block. The original reads only `.text`."""

    def __init__(self, text):
        self.text = text


class _StandInToolResult:
    """What `call_tool()` answers. The original reads only `.content[0].text`."""

    def __init__(self, text):
        self.content = [_StandInTextBlock(text)]


class _StandInSSETransport:
    """Stand-in for `fastmcp.client.transports.SSETransport`: it carries the URL, nothing more.

    The original constructs it with one positional URL and passes it straight to `Client`, so
    that is the entire surface exercised.
    """

    def __init__(self, url):
        self.url = url


class _StandInClient:
    """Stand-in for `fastmcp.Client`: an async context manager over a real HTTP round-trip.

    Implements only what the three tests ask of it — `async with`, `list_tools()` and
    `call_tool(name, arguments)` — against the URL its transport carries. The calls are
    blocking urllib inside `async def`, which is fine here: each round-trip is loopback and
    there is nothing else on the loop to starve.
    """

    def __init__(self, transport):
        self.transport = transport

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def _post(self, payload):
        request = urllib.request.Request(
            self.transport.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=_CLIENT_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))

    async def list_tools(self):
        return [_StandInTool(t["name"]) for t in self._post({"op": "list_tools"})["tools"]]

    async def call_tool(self, name, arguments):
        answer = self._post({"op": "call_tool", "name": name, "arguments": arguments})
        return _StandInToolResult(answer["text"])


# ─────────────────────────────── the built-in runner ───────────────────────────────


class TmpPathFactory:
    """A minimal stand-in for pytest's `tmp_path_factory`, used only by the built-in runner.

    `mktemp(name)` hands back a fresh directory named for `name`, numbered so repeat calls
    never collide — which is what the real factory does, and what the fixture relies on.
    """

    def __init__(self, prefix="test_integration_"):
        self._root = Path(tempfile.mkdtemp(prefix=prefix))
        self._count = 0

    def mktemp(self, name):
        self._count += 1
        path = self._root / ("%s%d" % (name, self._count))
        path.mkdir(parents=True)
        return path

    def cleanup(self):
        shutil.rmtree(self._root, ignore_errors=True)


def _fixture_impl(namespace, name):
    """Return a directly-callable implementation of the fixture `name` in `namespace`.

    THIS module routes `server_port` to its `_server_port_impl` twin, because under real pytest
    the decorated name is a `FixtureFunctionDefinition` (8.4+) that refuses a direct call. Any
    other namespace (the original's) hands back the decorated function itself, which the pytest
    stand-in leaves callable — and the original is only ever run under the stand-in, since the
    stand-in is what `selftest` execs it with.
    """
    if namespace is globals():
        impl = namespace.get("_%s_impl" % name)
        if impl is not None:
            return impl
    return namespace[name]


def _test_impl(namespace, name):
    """Return a directly-awaitable implementation of the test `name` in `namespace`.

    Mirrors `_fixture_impl`. THIS module's tests are thin wrappers carrying the two marks; the
    `_*_impl` twin holds the body, so the runner calls the body and never depends on what a
    real `@pytest.mark` decorator returned.
    """
    if namespace is globals():
        impl = namespace.get("_%s_impl" % name)
        if impl is not None:
            return impl
    return namespace[name]


def _run_module(namespace, config, base=None):
    """Run the three tests out of `namespace` under `config`, as pytest would run the module.

    Builds `server_port` ONCE and shares it across all three tests — that is what
    `scope="module"` means, and reproducing it here is what makes the runner a fair stand-in
    for pytest. Teardown always runs, so no server outlives the call.

    A failing test is a VERDICT, not a crash, so every exception becomes a description. If the
    fixture itself fails, all three tests inherit that failure, which is what pytest does with
    a broken module-scoped fixture.

    Returns:
        A `(results, ports)` pair: `{test name: None-or-failure-description}`, and every port a
        server was started on, so check [13] can prove they are all dead afterwards.
    """
    factory = TmpPathFactory()
    results = {}
    ports = []
    generator = None
    setup_failure = None
    port = None

    previous = configure(config, base=base)
    try:
        try:
            generator = _fixture_impl(namespace, "server_port")(factory)
            port = next(generator)
            ports.append(port)
        except BaseException as exc:  # noqa: BLE001 — a failed fixture is a verdict
            setup_failure = "%s: %s" % (type(exc).__name__, exc)

        for name in TEST_NAMES:
            if setup_failure is not None:
                results[name] = "server_port fixture failed — %s" % setup_failure
                continue
            try:
                asyncio.run(_test_impl(namespace, name)(port))
                results[name] = None
            except BaseException as exc:  # noqa: BLE001 — a failing test is a verdict
                results[name] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        if generator is not None and setup_failure is None:
            # Drive the fixture past its yield so the teardown half — terminate, then kill —
            # actually runs. StopIteration is the expected way out.
            try:
                next(generator)
            except StopIteration:
                pass
            except BaseException:  # noqa: BLE001 — teardown trouble must not mask a verdict
                pass
        generator = None
        configure(previous[0] if previous else None,
                  base=previous[1] if previous else None,
                  source=previous[2] if previous else "injected via configure()")
        factory.cleanup()
    return results, ports


@contextlib.contextmanager
def _injected_modules(modules):
    """Put `modules` into `sys.modules` for the duration of the block, then put back what was.

    Used to exec the ORIGINAL, which imports pytest, pytest_asyncio and fastmcp at module
    scope. Restoring rather than deleting matters: on an interpreter where real pytest IS
    installed, the original must not be left holding a stand-in.
    """
    saved = {name: sys.modules.get(name) for name in modules}
    try:
        sys.modules.update(modules)
        yield
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def _standin_modules():
    """Build the stand-in module objects the ORIGINAL's imports resolve against.

    `fastmcp` and `fastmcp.client.transports` are synthesised so `from fastmcp import Client`
    and `from fastmcp.client.transports import SSETransport` both work; `pytest_asyncio` is a
    bare module because the original imports it and never uses it. `pytest` is whatever THIS
    module resolved — real pytest if it is installed, the stand-in otherwise — so the original
    and this rewrite always run under the same one.
    """
    import types as _types

    fastmcp = _types.ModuleType("fastmcp")
    fastmcp.Client = _StandInClient
    client_pkg = _types.ModuleType("fastmcp.client")
    transports = _types.ModuleType("fastmcp.client.transports")
    transports.SSETransport = _StandInSSETransport
    client_pkg.transports = transports
    fastmcp.client = client_pkg

    return {
        "pytest": pytest,
        "pytest_asyncio": _types.ModuleType("pytest_asyncio"),
        "fastmcp": fastmcp,
        "fastmcp.client": client_pkg,
        "fastmcp.client.transports": transports,
    }


def _load_original(pkgroot):
    """Exec the embedded ORIGINAL and return its namespace.

    `__file__` is set to where the original WOULD live inside the staged tree —
    `<pkgroot>/coupler/tests/test_integration.py` — because the original derives the child's
    PYTHONPATH from `Path(__file__).parent.parent.parent`. Setting it here is what makes the
    original point at the same staged package root this rewrite is told about explicitly, so
    the two are compared on identical ground. Check [3] proves they agree.
    """
    namespace = {
        "__name__": "forge2_original_test_integration",
        "__file__": str(Path(pkgroot) / "coupler" / "tests" / "test_integration.py"),
        "__builtins__": __builtins__,
    }
    with _injected_modules(_standin_modules()):
        exec(compile(ORIGINAL_SOURCE, "<original test_integration.py>", "exec"), namespace)
    return namespace


@contextlib.contextmanager
def _injected_client():
    """Point THIS module's `Client`/`SSETransport` at the stand-in for the duration of the block.

    The two are module globals looked up at call time, which is what makes this possible — and
    it is the same client the original's namespace gets, so the differential compares like with
    like. Always put back, so nothing leaks into a later check.
    """
    global Client, SSETransport
    previous = (Client, SSETransport)
    Client, SSETransport = _StandInClient, _StandInSSETransport
    try:
        yield
    finally:
        Client, SSETransport = previous


def _stage_server(root):
    """Write the reference server into a temp package tree and return its package root.

    The tree mirrors the real layout — `<pkgroot>/coupler/server.py`, with a `coupler/tests/`
    that exists only so the original's three-parent walk from its notional `__file__` lands on
    `pkgroot`. Nothing is written outside `root`, and `root` is removed by the caller.
    """
    pkgroot = Path(root) / "pkgroot"
    (pkgroot / "coupler" / "tests").mkdir(parents=True)
    (pkgroot / "coupler" / "__init__.py").write_text("")
    (pkgroot / "coupler" / "tests" / "__init__.py").write_text("")
    (pkgroot / "coupler" / "server.py").write_text(REFERENCE_SERVER)
    return pkgroot


def _scenario_config(pkgroot):
    """Build the config object a differential scenario runs under.

    It is `config_template()` — the ORIGINAL's own values, unchanged — with exactly ONE
    override: `server_pythonpath`, pointing at the staged package root, which is the only way
    to aim this rewrite at a `coupler.server` that exists. Everything else is left at the
    original's value, including `jazz_dev_value` ("/nonexistent") and the 10-second startup
    deadline, because a scenario that handed this rewrite a value the ORIGINAL hardcodes and
    cannot be told would not be comparing like with like. `_recorded_launches` proves the
    override lands both modules on the same package root.
    """
    config = config_template()
    config["server_pythonpath"] = str(pkgroot)
    return config


@contextlib.contextmanager
def _recording_popen(recorder):
    """Record every `subprocess.Popen(argv, env=...)` into `recorder`, then delegate to the real one.

    Both modules reach `subprocess.Popen` as an attribute of the `subprocess` MODULE at call
    time — this rewrite from a module-level import, the ORIGINAL from an `import subprocess`
    inside its fixture — so patching the attribute catches both, and neither had to be written
    to allow it. The real Popen still runs, so the servers really start and the scenario is
    unaffected: this observes, it does not stub.
    """
    real = subprocess.Popen

    def recording(argv, **kwargs):
        recorder.append((list(argv), dict(kwargs.get("env") or {})))
        return real(argv, **kwargs)

    subprocess.Popen = recording
    try:
        yield
    finally:
        subprocess.Popen = real


def _normalise_launch(argv, env, config):
    """Reduce one recorded launch to what SHOULD be identical between the two modules.

    Two things legitimately differ every run and are replaced by a marker rather than compared:
    the temp jazz root (a fresh directory per fixture) and the chosen port (whatever the kernel
    handed out, and `--port N` carries it into argv too). Everything else — the interpreter,
    the `-m <module>` form, the argument order, and every one of the four environment keys the
    fixture sets — must match exactly, or this rewrite is not launching the server the original
    launched.
    """
    root_env = config["jazz_root_env"]
    port_env = config["port_env"]
    port = env.get(port_env, "")
    root = env.get(root_env, "")

    def scrub(text):
        if port and port in text:
            text = text.replace(port, "<PORT>")
        if root and root in text:
            text = text.replace(root, "<JAZZ_ROOT>")
        return text

    keys = [root_env, config["jazz_dev_env"], port_env, config["pythonpath_env"]]
    return (
        [scrub(a) for a in argv],
        {k: scrub(env.get(k, "<ABSENT>")) for k in keys},
    )


def _port_is_dead(host, port):
    """True when nothing accepts a connection on `port` — i.e. the server is gone."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return False
    except OSError:
        return True


@contextlib.contextmanager
def _in_directory(path):
    """Run the block with the process cwd at `path`, then always put it back.

    The differential needs this, and the reason is worth stating because it looks like a
    detail and is not. The fixture spawns the child with `python -m <server_module>` and does
    NOT set `cwd` — the original does not either, so neither may this. But `-m` puts the
    CHILD'S CWD FIRST on its import path, ahead of `PYTHONPATH`. Run the differential from this
    package's own root and the child would find the REAL `coupler` package sitting there, which
    has no `server.py`, and every scenario would die with "No module named coupler.server"
    while the staged reference server three directories away went untouched.

    So the differential runs from the scenario's temp root — a directory containing no
    `coupler` at all. That makes the fixture's `PYTHONPATH` the ONLY route by which the child
    can import the staged server, which is a stronger arrangement than pointing cwd at the
    staged tree would be: if this rewrite ever stopped setting `PYTHONPATH` correctly, every
    scenario would fail loudly instead of being quietly rescued by the cwd.
    """
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


# ─────────────────────────────── the surface check ───────────────────────────────


def lowered_surface(source):
    """Lower `source`'s module-level callables the way codebean's `lower_node` (#183) does.

    Returns the ticket's own notation — `name(params) -> returns`, prefixed `async ` for a
    coroutine — for every function defined at module level whose name the ticket lists. Reading
    the AST is what makes check [5] a measurement: it is what pytest itself sees, rather than a
    marker attribute a stand-in could have faked.
    """
    wanted = {line.split("(")[0].replace("async ", "") for line in TICKET_SURFACE}
    lowered = []
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in wanted:
            continue
        params = ", ".join(arg.arg for arg in node.args.args)
        line = "%s%s(%s)" % (
            "async " if isinstance(node, ast.AsyncFunctionDef) else "",
            node.name,
            params,
        )
        if node.returns is not None:
            line += " -> %s" % ast.unparse(node.returns)
        lowered.append(line)
    return lowered


def decorators_of(source, name):
    """Return the decorator expressions on the module-level callable `name`, as source text."""
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return [ast.unparse(d) for d in node.decorator_list]
    return []


# ─────────────────────────────── selftest ───────────────────────────────


def git_blob_sha1(data):
    """Return git's blob sha1 for `data`: sha1(b"blob " + len + b"\\0" + data).

    This is git's own object rule, which is why check [2] can compare against the hash ticket
    #377 records without having any forge access at all.
    """
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class _Checks:
    """Collects PASS/FAIL lines so `selftest` reports every check, not just the first failure."""

    def __init__(self, verbose):
        self.verbose = verbose
        self.failures = 0
        self.count = 0

    def check(self, ok, label, detail=""):
        self.count += 1
        if ok:
            if self.verbose:
                print("  PASS  %s%s" % (label, ("  (%s)" % detail) if detail else ""))
        else:
            self.failures += 1
            print("  FAIL  %s%s" % (label, ("  (%s)" % detail) if detail else ""))
        return ok


def _describe(results):
    """Render a verdict vector as a compact, comparable string."""
    return ", ".join(
        "%s=%s" % (name, "PASS" if results[name] is None else "FAIL") for name in TEST_NAMES
    )


def _failed_names(results):
    return {name for name, outcome in results.items() if outcome is not None}


def selftest(verbose=False):
    """Prove this rewrite reproduces the original's behavior; return the number of failures.

    The whole argument of this module, run end to end:

      [1]  the embedded original weighs the 4058 bytes ticket #377 records;
      [2]  its git blob sha1 is the one #377 records — so the oracle IS the forge's blob;
      [3]  the original and this rewrite are handed the same package root, so the differential
           compares like with like;
      [4]  with the shipped config, the PYTHONPATH this rewrite derives equals the original's
           own `Path(__file__).parent.parent.parent`;
      [5]  this file's AST presents the ticket's callable surface, both marks and the module
           fixture scope;
      [6]  every mutation named in MUTANTS is one REFERENCE_SERVER actually implements;
      [6]  every mutation the tables name is one REFERENCE_SERVER actually implements — a
           typo'd one would behave like the conforming server and turn a negative control into
           a silent false PASS;
      [7]  the differential — for each reference and each mutant, this rewrite fails exactly
           the tests it should, and the ORIGINAL reaches the identical verdict;
      [10] the config gate: no config, and every test plus _free_port throws ConfigError;
      [11] no fastmcp, and every test raises ImportError naming it rather than a wrong verdict;
      [12] one server, one subprocess, serving all three tests (scope="module");
      [13] no server outlives a run, including when the fixture itself failed;
      [14] the argv and the four environment keys handed to the child are the original's.

    The scenarios are `REFERENCES + MUTANTS`; [R1] and [R2] are the two halves of the why5
    branch and are named in the output for that reason (see EDGE_CASES).
    """
    checks = _Checks(verbose)
    print("selftest — %s" % UNIT)
    print("  pytest        : %s" % ("REAL %s" % pytest.__version__ if HAVE_PYTEST
                                    else "stand-in (pytest not installed)"))
    print("  pytest_asyncio: %s" % ("REAL %s" % pytest_asyncio.__version__
                                    if HAVE_PYTEST_ASYNCIO else "absent (imported, never used)"))
    print("  fastmcp       : %s" % ("REAL" if HAVE_FASTMCP else
                                    "absent — the differential injects its own client"))
    print()

    this_source = Path(__file__).read_text(encoding="utf-8")

    # [1]/[2] — the oracle is the original, proven by size and by git's own hash.
    blob = ORIGINAL_SOURCE.encode("utf-8")
    checks.check(len(blob) == ORIGINAL_SIZE, "[1] embedded original is %d bytes" % ORIGINAL_SIZE,
                 "got %d" % len(blob))
    actual_sha = git_blob_sha1(blob)
    checks.check(actual_sha == ORIGINAL_BLOB_SHA1,
                 "[2] embedded original's git blob sha1 is the ticket's", actual_sha)

    # [5] — the callable surface, the marks and the fixture scope, off this file's AST.
    surface = lowered_surface(this_source)
    checks.check(surface == TICKET_SURFACE, "[5] callable surface is the ticket's",
                 " | ".join(surface))
    fixture_decorators = decorators_of(this_source, "server_port")
    checks.check(fixture_decorators == ["pytest.fixture(scope='module')"],
                 "[5] server_port is a module-scoped fixture", " | ".join(fixture_decorators))
    for name in TEST_NAMES:
        marks = decorators_of(this_source, name)
        checks.check(marks == ["pytest.mark.slow", "pytest.mark.asyncio"],
                     "[5] %s carries both marks" % name, " | ".join(marks))
    # The original must carry the same three, or "preserved" would be an empty word.
    for name in TEST_NAMES:
        checks.check(decorators_of(ORIGINAL_SOURCE, name) == decorators_of(this_source, name),
                     "[5] %s's marks match the original's" % name)
    checks.check(
        decorators_of(ORIGINAL_SOURCE, "server_port") == fixture_decorators,
        "[5] server_port's fixture scope matches the original's",
    )

    # [6] — every mutation named in MUTANTS is one the reference server implements. A typo'd
    # mutation name would silently behave like the conforming server: every test would pass,
    # and a check expecting failures would report a defect in this module that is not there.
    for label, mutation, _expected in MUTANTS + REFERENCES:
        if not mutation:
            continue
        checks.check('"%s"' % mutation in REFERENCE_SERVER,
                     "[6] REFERENCE_SERVER implements the mutation %r" % mutation, label)

    # [4] — the derived PYTHONPATH is the original's expression, evaluated here.
    with using_config(config_template()):
        derived = _server_pythonpath(active_config())
    original_expression = str(Path(__file__).parent.parent.parent)
    checks.check(derived == original_expression,
                 "[4] derived PYTHONPATH == Path(__file__).parent.parent.parent", derived)

    # [10] — the config gate. With no config resolvable, every test and _free_port must throw
    # ConfigError and reach NO verdict about the server.
    gate_dir = tempfile.mkdtemp(prefix="test_integration_nogate_")
    saved_env = os.environ.pop(CONFIG_ENV, None)
    reset_config()
    try:
        # Resolve from a directory with no registry above it, so the walk-up finds nothing.
        try:
            load_config(start=gate_dir)
            checks.check(False, "[10] load_config throws with no registry above it")
        except ConfigError as exc:
            checks.check(CONFIG_ENV in str(exc) and REGISTRY_NAME in str(exc),
                         "[10] load_config throws ConfigError naming both sources tried")

        empty = {}
        for name in TEST_NAMES:
            try:
                with using_config(empty):
                    asyncio.run(_test_impl(globals(), name)(12345))
                checks.check(False, "[10] %s throws ConfigError with an empty config" % name)
            except ConfigError:
                checks.check(True, "[10] %s throws ConfigError with an empty config" % name)
            except BaseException as exc:  # noqa: BLE001
                checks.check(False, "[10] %s throws ConfigError with an empty config" % name,
                             "raised %s instead" % type(exc).__name__)
        try:
            with using_config(empty):
                _free_port()
            checks.check(False, "[10] _free_port throws ConfigError with an empty config")
        except ConfigError:
            checks.check(True, "[10] _free_port throws ConfigError with an empty config")
    finally:
        if saved_env is not None:
            os.environ[CONFIG_ENV] = saved_env
        shutil.rmtree(gate_dir, ignore_errors=True)
        reset_config()

    # [11] — with no fastmcp, every test raises ImportError naming it. This runs with the REAL
    # module-level Client/SSETransport forced to None, which is the state a bare interpreter is
    # actually in, and it must NOT be a verdict about the server.
    global Client, SSETransport
    saved_client = (Client, SSETransport)
    Client, SSETransport = None, None
    try:
        for name in TEST_NAMES:
            try:
                with using_config(config_template()):
                    asyncio.run(_test_impl(globals(), name)(12345))
                checks.check(False, "[11] %s raises ImportError without fastmcp" % name)
            except ImportError as exc:
                checks.check("fastmcp" in str(exc),
                             "[11] %s raises ImportError naming fastmcp" % name)
            except BaseException as exc:  # noqa: BLE001
                checks.check(False, "[11] %s raises ImportError without fastmcp" % name,
                             "raised %s instead" % type(exc).__name__)
    finally:
        Client, SSETransport = saved_client

    # [7]/[8]/[9]/[12]/[13] — the differential, plus the scope and reaping proofs.
    print()
    print("  the differential — this rewrite vs the ORIGINAL's %d bytes, same server, same "
          "client" % ORIGINAL_SIZE)
    scenarios = REFERENCES + MUTANTS
    with _injected_client():
        for label, mutation, expected in scenarios:
            tag = label.split(" ")[0]
            root = tempfile.mkdtemp(prefix="test_integration_diff_")
            saved_mutation = os.environ.get(MUTATION_ENV)
            try:
                pkgroot = _stage_server(root)
                config = _scenario_config(pkgroot)
                if mutation:
                    os.environ[MUTATION_ENV] = mutation
                else:
                    os.environ.pop(MUTATION_ENV, None)

                original_ns = _load_original(pkgroot)

                # [3] — both sides are pointed at the same staged package root, so any verdict
                # difference is a difference in the CODE, never in what it was aimed at.
                original_pythonpath = str(
                    Path(original_ns["__file__"]).parent.parent.parent
                )
                checks.check(original_pythonpath == config["server_pythonpath"],
                             "[3] %s — original and rewrite share a package root" % tag)

                # Run from the scenario's temp root, so the child's cwd holds no `coupler` and
                # the fixture's PYTHONPATH is the only route to the staged server. See
                # `_in_directory` for why this is load-bearing rather than tidying.
                my_launches, their_launches = [], []
                with _in_directory(root):
                    with _recording_popen(my_launches):
                        mine, my_ports = _run_module(globals(), config)
                    with _recording_popen(their_launches):
                        theirs, their_ports = _run_module(original_ns, config)

                # [7] — the two verdict vectors must agree, test for test.
                checks.check(_describe(mine) == _describe(theirs),
                             "[7] %s — verdicts agree" % label,
                             "rewrite: %s || original: %s" % (_describe(mine), _describe(theirs)))
                # ...and both must be the verdict the table says, or "agree" would be satisfied
                # by two modules that are broken in the same way.
                checks.check(_failed_names(mine) == expected,
                             "[7] %s — rewrite fails exactly the expected tests" % label,
                             "expected %s, got %s" % (sorted(expected) or "none",
                                                      sorted(_failed_names(mine)) or "none"))
                checks.check(_failed_names(theirs) == expected,
                             "[7] %s — original fails exactly the expected tests" % label,
                             "expected %s, got %s" % (sorted(expected) or "none",
                                                      sorted(_failed_names(theirs)) or "none"))

                # [14] — the launch itself. Beyond agreeing on verdicts, this rewrite must hand
                # the child the same argv and the same four environment keys the ORIGINAL hands
                # it. A verdict can agree by luck; the launch cannot. This is what proves
                # JAZZ_ROOT/JAZZ_DEV/COUPLER_PORT/PYTHONPATH are set the way the original set
                # them — the temp root and the port are normalised out, since they differ every
                # run by design.
                if my_launches and their_launches:
                    mine_norm = _normalise_launch(*my_launches[0], config)
                    theirs_norm = _normalise_launch(*their_launches[0], config)
                    checks.check(mine_norm == theirs_norm,
                                 "[14] %s — argv and child environment match the original's" % tag,
                                 "rewrite: %s || original: %s" % (mine_norm, theirs_norm))

                # [12] — scope="module": ONE server for the three tests, not three.
                if mutation != "never-starts":
                    checks.check(len(my_ports) == 1,
                                 "[12] %s — one server served all three tests" % tag,
                                 "spawned %d" % len(my_ports))
                    checks.check(len(my_launches) == 1,
                                 "[12] %s — exactly one subprocess was spawned" % tag,
                                 "spawned %d" % len(my_launches))

                # [13] — nothing outlives the run.
                dead = all(_port_is_dead(config["bind_host"], p)
                           for p in my_ports + their_ports)
                checks.check(dead, "[13] %s — every server was reaped" % tag)
            finally:
                if saved_mutation is None:
                    os.environ.pop(MUTATION_ENV, None)
                else:
                    os.environ[MUTATION_ENV] = saved_mutation
                shutil.rmtree(root, ignore_errors=True)

    print()
    print("  %d checks, %d failure(s)" % (checks.count, checks.failures))
    return checks.failures


# ─────────────────────────────── the command line ───────────────────────────────


def _invocation():
    """Describe the command that ACTUALLY ran, for the bug report and for error messages.

    Built from `sys.argv` rather than written as a fixed string, so a report names what the
    reader would have to retype to reproduce it.
    """
    return " ".join([os.path.basename(sys.argv[0])] + sys.argv[1:])


def _file_bug_report(exc):
    """Append one timestamped JSON line about an UNEXPECTED exception; return where, or None.

    `note-for-claude` asks that "all tools need to pass a bug-report automatically (timestamped
    if an exception is thrown)". This fires only for defects in this tool: `ConfigError` and
    `UsageError` are designed behavior and never reach here. If the config cannot be resolved,
    or names no `bug_reports` path, nothing is written and None comes back — a tool that cannot
    see its config does not get to invent a place to write.
    """
    try:
        config = active_config()
        base = active_base()
    except ConfigError:
        return None
    path = config.get("bug_reports")
    if not isinstance(path, str) or not path:
        return None
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "unit": UNIT,
        "invocation": _invocation(),
        "error": "%s: %s" % (type(exc).__name__, exc),
        "traceback": traceback.format_exc(),
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError:
        return None
    return path


def _prove_importable():
    """Raise UsageError if this file was run by path, where the `coupler` package is unreachable.

    `python3 coupler/tests/test_integration.py` puts `coupler/tests/` on the import path
    instead of the package root, so `import coupler` fails and nothing here can work. That is a
    mistake about the INVOCATION, so it is answered with the invocation that does work rather
    than with a traceback. See `UsageError`.
    """
    if __package__:
        return
    try:
        import coupler.tests  # noqa: F401
    except ImportError:
        raise UsageError(
            "run this module with -m from the package root (the directory holding "
            "pyproject.toml), not by path: `python3 -m %s %s`. Running it by path puts %s on "
            "the import path instead of the package root, so the `coupler` package is not "
            "importable. Once installed (`pip install -e .`), "
            "`forge2-coupler-test-integration` works from anywhere."
            % (DOTTED_NAME, " ".join(sys.argv[1:]) or "selftest",
               os.path.dirname(os.path.abspath(__file__)))
        ) from None


def _cmd_selftest(args):
    return 1 if selftest(verbose=args.verbose) else 0


def _cmd_emit_config(args):
    print(json.dumps(config_template(), indent=2))
    return 0


def _cmd_show_config(args):
    config = active_config()
    print("unit  : %s" % UNIT)
    print("source: %s" % active_source())
    print("base  : %s" % active_base())
    print(json.dumps(config, indent=2))
    return 0


def _cmd_show_deps(args):
    print("pytest        : %s" % ("REAL %s" % pytest.__version__ if HAVE_PYTEST
                                  else "stand-in — pytest is not installed"))
    print("pytest_asyncio: %s" % ("REAL %s" % pytest_asyncio.__version__
                                  if HAVE_PYTEST_ASYNCIO
                                  else "absent — the original imports it and never uses it"))
    print("fastmcp       : %s" % ("REAL — Client and SSETransport imported" if HAVE_FASTMCP
                                  else "absent — every test raises ImportError naming it; "
                                       "there is deliberately no stand-in fallback"))
    if not HAVE_FASTMCP:
        print()
        print("Install the test extra to run these under pytest for real:")
        print("    pip install -e \".[test]\"")
    return 0


def _cmd_install_check(args):
    """Report what can be checked of the package from inside it, without installing anything."""
    root = Path(__file__).resolve().parent.parent.parent
    ok = True

    pyproject = root / "pyproject.toml"
    print("package root  : %s" % root)
    print("pyproject.toml: %s" % ("present" if pyproject.is_file() else "MISSING"))
    ok = ok and pyproject.is_file()

    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8")
        for needed in ('"coupler"', '"coupler.tests"'):
            found = needed in text
            print("  declares %-18s %s" % (needed, "yes" if found else "NO"))
            ok = ok and found

    registry = find_registry()
    print("registry      : %s" % (registry or "NOT FOUND"))
    ok = ok and registry is not None

    try:
        active_config()
        print("config object : resolved from %s" % active_source())
    except ConfigError as exc:
        print("config object : UNRESOLVED — %s" % exc)
        ok = False

    print("this module   : %s" % Path(__file__).resolve())
    print()
    print("install it with:  pip install -e .        (from %s)" % root)
    print("then run:         forge2-coupler-test-integration selftest")
    return 0 if ok else 1


def build_parser():
    """Build the argument parser. Every command is listed in the module docstring's RUNNING IT."""
    parser = argparse.ArgumentParser(
        prog=DOTTED_NAME,
        description="Behavior-preserving rewrite of the forge unit "
                    "code__code-invalid__coupler:coupler/tests/test_integration.py (ticket "
                    "#377). Under pytest this module IS the three integration tests; these "
                    "commands prove and describe it.",
    )
    subparsers = parser.add_subparsers(dest="command")

    p = subparsers.add_parser("selftest", help="run the differential against the embedded "
                                               "original, its mutants, the config gate and "
                                               "the callable surface")
    p.add_argument("-v", "--verbose", action="store_true", help="print every check, not just "
                                                                "the failures")
    p.set_defaults(func=_cmd_selftest)

    p = subparsers.add_parser("emit-config", help="print a template of this unit's config object")
    p.set_defaults(func=_cmd_emit_config)

    p = subparsers.add_parser("show-config", help="print the resolved config object and its source")
    p.set_defaults(func=_cmd_show_config)

    p = subparsers.add_parser("show-deps", help="report whether pytest, pytest_asyncio and "
                                                "fastmcp are real here")
    p.set_defaults(func=_cmd_show_deps)

    p = subparsers.add_parser("install-check", help="report what can be checked of the package "
                                                    "without installing it")
    p.set_defaults(func=_cmd_install_check)

    return parser


def main(argv=None):
    """Run the command line; return the process exit status.

    Exit statuses: 0 success; 1 a check failed; 2 a usage or config error — one
    self-explaining line, never a traceback, and no bug report filed, because neither is a
    defect in this tool. Any OTHER exception IS a defect: it files a timestamped bug report
    and re-raises, so the traceback is not swallowed.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "func", None) is None:
        parser.print_help()
        return 2
    try:
        _prove_importable()
        return args.func(args)
    except UsageError as exc:
        print("usage error: %s" % exc, file=sys.stderr)
        return 2
    except ConfigError as exc:
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:
        where = _file_bug_report(exc)
        if where:
            print("unexpected error — bug report appended to %s" % where, file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(main())
