#!/usr/bin/env python3
"""forge2 / code__code-invalid__coupler / coupler.tests.test_bridge — a behavior-preserving
rewrite of the forge unit `code__code-invalid__coupler:coupler/tests/test_bridge.py` (module
key forge-rw:cf2f7825dcd810b2), filed under ticket #393 against the FORGE-wide refactor
standard #200.

WHAT THIS IS
------------
The original forge unit was 2409 bytes: a pytest module holding three unit tests for the
`coupler.bridge` health check and its stub status message, mocking the TCP connect so no live
server is needed. This file is an entirely new implementation of that unit. It keeps the
original's observable behavior and its callable surface, and it adds the three things #200
requires that the original lacked: it is part of a proper installable package, it is driven
by a configuration object, and it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    async test_wait_for_server_succeeds_when_port_open(monkeypatch)
    async test_wait_for_server_fails_after_retries(monkeypatch)
    test_stub_status_message_contains_port()

The "existing caller" of a pytest module is pytest itself, so the surface is preserved in the
way that matters to it: the same three names, the same parameters, the first two still
coroutine functions carrying the `asyncio` mark, the third still an ordinary function. pytest
collects and runs this module exactly as it collected and ran the original. `selftest` proves
each of those properties rather than asserting them (check [4]).

WHAT "BEHAVIOR-PRESERVING" MEANS FOR A TEST MODULE
--------------------------------------------------
A test module's observable behavior is the verdict it reaches about the code under test: for
which implementations of `coupler.bridge` it passes, and for which it fails. Preserving it
means this file must assert the SAME properties, from the SAME mocked conditions, as the
original — no fewer, so nothing the original caught slips through, and no more, so a bridge
the original accepted is not failed here. Every assertion below is one the original made; the
three additions #200 asks for are in the CONFIGURATION section, not in the assertions.

Two consequences worth being explicit about, because both are easy to "improve" and wrong to:

  * The third test BUILDS the payload it inspects, rather than calling anything in
    `coupler.bridge`. That is the original's design, and its own comment says why — "the stub
    tool function is defined inline in main() — test the JSON shape directly". The test is
    therefore a check on the message TEMPLATE (rendered with the real `b.PORT` and
    round-tripped through JSON), not on `main()`. Rewiring it to call the real stub would
    make it a different test with a different verdict, so it is left as the original had it.
    `selftest` check [3] separately proves the shipped bridge's real stub satisfies the same
    three assertions, which is where that stronger claim belongs.
  * `assert str(b.PORT) in data["message"]` is satisfied by construction, since the template
    interpolates the port. That is a weakness of the original test; it is preserved, not
    fixed. Ticket #393 asks for a behavior-preserving rewrite, not a better test suite.

THE EQUIVALENCE BASIS (#200 requirement 1, acceptance item (a))
---------------------------------------------------------------
Ticket #393 records that criteria_miner captured NO exemplars for this module — it "mines
only self-contained pure functions (it refuses anything that mentions a world-touching or
non-deterministic name, plus methods and no-arg functions), and nothing here qualified" —
and states that this "MOVES the work: you must write the equivalence exemplars by hand from
the original's behavior before rewriting, and they are what settles this ticket."

`EXEMPLARS` below is that hand-written table. Every expected outcome in it was read off the
ORIGINAL's source, which ticket #393 embeds in full, statement by statement — never off this
rewrite. `EDGE_CASES` covers what the original's three scenarios cannot reach on their own;
each entry says which unstated property it pins down. The `selftest` command runs both tables
and prints a verdict; see RUNNING IT for how to invoke it.

TERMS USED HERE
---------------
registry / config object
    See `coupler.config`, which resolves both and documents the gate. In short: a single JSON
    file holds the configuration for every tool in this package, each unit reads only its own
    section, and a unit that cannot see its section throws instead of guessing a default.
monkeypatch
    pytest's built-in fixture for setting an attribute for the duration of one test and
    putting it back afterwards. The original used it to swap `asyncio.open_connection` for a
    fake, which is what lets these tests run with no live server. See THE PYTEST DEPENDENCY.
exemplar
    One (scenario -> expected outcome) pair that the rewrite must reproduce, standing in for
    the automated captures ticket #393 could not mine.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The original hardcoded every parameter of its three scenarios: the retry counts `1` and `2`,
the retry interval `0.01`, the refusal text `"no server"`, and the whole stub payload — its
status field `"coupler"`, its value `"down"`, the message template, the `indent=2`, and the
`"coupler.server"` the message is asserted to contain. Those are exactly the params #200's
fourth requirement forbids hardcoding, so every one of them is read from this unit's config
object — the `forge2 -> code__code-invalid__coupler -> coupler.tests.test_bridge` section of
the registry — and nothing is defaulted in code.

The config is read INSIDE each test, not at import time, deliberately: pytest must still be
able to import and collect this module, so a missing config object surfaces as three honest
`ConfigError` test failures naming what is missing, rather than one collection error that
hides which tests exist. `selftest` check [1] proves each test throws `ConfigError` — and
reaches no verdict about the bridge — when its config cannot be resolved.

The config carries `server_module` AND `expected_server_hint`, which both read
`"coupler.server"` in the shipped registry. That is not an oversight or a duplicated setting:
the original names that string twice, once inside the message template it builds and once in
the assertion it makes about the result, and those are two different roles. Collapsing them
into one key would make the assertion unable to fail — it would be checking the template
against itself — and would quietly delete a check the original made.

THE PYTEST DEPENDENCY, AND WHY THIS MODULE STILL RUNS WITHOUT IT
----------------------------------------------------------------
The original imports `pytest` and `pytest_asyncio` at module scope, so it cannot be imported
at all where those are absent — and they ARE absent from the interpreter this package was
built and verified against. This rewrite declares both in `pyproject.toml`'s `test` EXTRA, so
`pip install -e ".[test]"` supplies them and pytest runs this module as it ran the original.
That is the primary path.

They are an extra rather than a required dependency on purpose. Ticket #393's acceptance item
(c) is that `pip install -e .` installs CLEAN from this package's own pyproject.toml, and a
required pytest would make that install depend on a package index being reachable. The
package itself does not need pytest to be installed or used — only to be tested through
pytest — so nothing is required and the plain install always succeeds.

Where they are not installed, this module falls back to a minimal stand-in providing the only
two pieces of pytest the original used: `pytest.mark.asyncio` (as a decorator that returns
the function unchanged) and a `monkeypatch` with `setattr` and `undo`. The fallback exists so
that `selftest` can prove this rewrite's behavior on a bare interpreter, and it is inert
whenever real pytest is importable — under pytest, the real mark and the real fixture are
used and NOTHING here is in the path. `selftest` reports which of the two it ran under, so
the reader is never guessing; `show-pytest` reports the same thing on its own.

Be precise about what that means for the evidence behind this module, because it is a real
limit and not a boast: the interpreter this was written and run on has no pytest and no way
to install one, so the runs that back this rewrite are `selftest` runs, taken through the
stand-ins. What `selftest` proves is the BEHAVIOR — the exemplars, the edges, the gate and
the surface — and that is what ticket #393's acceptance turns on. What it cannot prove is
pytest's own collection of this file. The two are kept apart deliberately: the stand-ins
touch only how a test is INVOKED (a decorator that records a mark, a fixture that sets and
restores an attribute), never what it ASSERTS, so a test that passes here asserts exactly
what it asserts under pytest. The mark each async test carries is a real
`pytest.mark.asyncio` whenever pytest is importable, applied by pytest's own MarkDecorator
and landing in `pytestmark` where pytest reads it — `selftest` check [4] reads the mark back
from whichever of the two paths is live.

This is a fallback for the test HARNESS, not for the config object. Nothing about the config
gate is softened by it: with or without pytest, a test that cannot see its config throws.

RUNNING IT
----------
Every command below is executable as written FROM THE PACKAGE ROOT — the directory holding
`pyproject.toml`, one level above `coupler/`. The `-m` form is what makes them run without
installing anything: it puts the package root on the import path, so `coupler.config` and
`coupler.bridge` resolve. Running the file by path (`python3 coupler/tests/test_bridge.py`)
does NOT work uninstalled, because Python would put `coupler/tests/` on the import path
instead of the package root, and the `coupler` package would not be importable.

    python3 -m coupler.tests.test_bridge selftest      # the exemplars, edges, gate, surface
    python3 -m coupler.tests.test_bridge show-pytest   # report whether real pytest is in use
    python3 -m coupler.tests.test_bridge emit-config   # print a config-object template
    python3 -m coupler.tests.test_bridge show-config   # print the resolved config + source

Once installed (see INSTALLABLE), the console script runs from any directory:

    forge2-coupler-test-bridge selftest

Which directory you run from never changes which config is found: the registry walk-up starts
at THIS FILE, not at the working directory.

Under real pytest, the ordinary invocation works and is the point. pytest puts the rootdir on
the import path itself, so the `-m` dance is not needed — but pytest is an EXTRA, since the
package installs clean without it (see `pyproject.toml`):

    pip install -e ".[test]"
    pytest coupler/tests/test_bridge.py -v   # collects and runs the three tests above

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, committed in full beside it —
`pyproject.toml`, `registry.json`, `coupler/__init__.py`, `coupler/config.py`,
`coupler/bridge.py`, `coupler/tests/__init__.py`. From the package root:

    pip install -e .
    forge2-coupler-test-bridge selftest

`pyproject.toml` declares `coupler` and `coupler.tests` as packages, so an installed copy
imports as `coupler.tests.test_bridge` — the path the forge unit was originally addressed by
(repo `code__code-invalid__coupler`, path `coupler/tests/test_bridge.py`).

SIDE EFFECTS
------------
The three tests and every command here create no files, modify none, and delete none. (The
interpreter still writes its usual `__pycache__` bytecode for any module it imports; that is
CPython's import machinery rather than this code, and ticket #393 lists `__pycache__` among
the build artifacts that are regenerated by any install and never committed.)

They open no sockets: `asyncio.open_connection` is replaced with a fake before the code under
test runs, and put back afterwards — `selftest` check [5] proves the restoration rather than
trusting it, and check [3] drives every retry path with `asyncio.sleep` faked too, so nothing
here waits on a clock or a network.

The one thing that can write is the command line, which per `note-for-claude` ("all tools
need to pass a bug-report automatically (timestamped if an exception is thrown)") appends one
timestamped JSON line to the config's `bug_reports` path if it hits an UNEXPECTED exception —
a defect in this tool. A `ConfigError` is designed behavior, not a bug: it files no report,
prints no traceback, and exits with a single self-explaining line.
"""

import argparse
import asyncio
import importlib
import inspect
import json
import os
import sys
import tempfile
import traceback

from coupler.config import REGISTRY_ENV, REGISTRY_NAME, ConfigError, Unit, bug_report, require

# ── the pytest dependency ─────────────────────────────────────────────────────────────────
#
# Real pytest and pytest_asyncio when they are installed — the original imported both at
# module scope, and under pytest this rewrite uses exactly what the original used. The
# stand-ins below are reached only on an interpreter where they are absent, and provide the
# only two pieces of pytest this module needs. See THE PYTEST DEPENDENCY in the module
# docstring.

try:
    import pytest

    HAVE_PYTEST = True
except ImportError:  # pragma: no cover — depends on the interpreter, not on a branch
    HAVE_PYTEST = False

try:
    import pytest_asyncio  # noqa: F401 — imported for the plugin, exactly as the original did

    HAVE_PYTEST_ASYNCIO = True
except ImportError:  # pragma: no cover — depends on the interpreter, not on a branch
    HAVE_PYTEST_ASYNCIO = False


class _MarkStandIn:
    """Stand-in for `pytest.mark`, used only where pytest is not installed.

    `pytest.mark.asyncio` is a decorator that, under real pytest, attaches a mark and returns
    the function unchanged; pytest-asyncio later reads that mark and runs the coroutine in an
    event loop. With no pytest to read it, the mark carries no information, so the stand-in
    returns the function unchanged and `selftest` supplies the event loop itself. The
    attribute is accepted by name, so `mark.anything` works the way `pytest.mark.anything`
    does rather than raising.
    """

    def __getattr__(self, name):
        def decorator(func):
            marks = getattr(func, "pytestmark_standin", [])
            func.pytestmark_standin = marks + [name]
            return func

        return decorator


class _PytestStandIn:
    """Stand-in for the `pytest` module, used only where pytest is not installed."""

    mark = _MarkStandIn()


if not HAVE_PYTEST:  # pragma: no cover — depends on the interpreter, not on a branch
    pytest = _PytestStandIn()


class MonkeyPatch:
    """A minimal stand-in for pytest's `monkeypatch` fixture: set an attribute, then undo.

    Used by `selftest` to drive the tests on an interpreter with no pytest, and never used
    when pytest supplies the real fixture. It implements only what these tests ask of it, and
    matches the real fixture on the two behaviors they depend on: `setattr` raises
    `AttributeError` rather than creating an attribute that was not already there, and `undo`
    restores the previous values in reverse order.
    """

    def __init__(self):
        self._undo = []

    def setattr(self, target, name, value):
        previous = getattr(target, name)  # AttributeError here mirrors the real fixture
        self._undo.append((target, name, previous))
        setattr(target, name, value)

    def undo(self):
        while self._undo:
            target, name, previous = self._undo.pop()
            setattr(target, name, previous)


# ── configuration ─────────────────────────────────────────────────────────────────────────

#: This module's handle on its own config object. See `coupler.config`.
UNIT = Unit(__file__, "coupler.tests.test_bridge")


def _stub_config():
    """Return this unit's `stub` config object, throwing if it or any key it needs is absent."""
    stub = UNIT.get("stub", dict)
    where = "%s -> stub" % UNIT.name
    return {
        "status_field": require(stub, "status_field", where, str),
        "status_down": require(stub, "status_down", where, str),
        "message_template": require(stub, "message_template", where, str),
        "server_module": require(stub, "server_module", where, str),
        "json_indent": require(stub, "json_indent", where, int),
        "expected_server_hint": require(stub, "expected_server_hint", where, str),
    }


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do these tests throw `ConfigError`.
    """
    return {
        "retries_when_port_open": 1,
        "retries_when_refused": 2,
        "retry_seconds_when_refused": 0.01,
        "refusal_message": "no server",
        "stub": {
            "status_field": "coupler",
            "status_down": "down",
            "message_template": "coupler server is not running on port {port}. "
                                "Start it with: python -m {server_module}",
            "server_module": "coupler.server",
            "json_indent": 2,
            "expected_server_hint": "coupler.server",
        },
    }


# ── health check ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wait_for_server_succeeds_when_port_open(monkeypatch):
    """Health check returns True when TCP connect succeeds."""
    retries = UNIT.get("retries_when_port_open", int)

    async def fake_open(host, port):
        reader = asyncio.StreamReader()

        # minimal writer mock: the health check closes what it opens, so the fake has to
        # answer both halves of that — the synchronous close and the awaitable wait.
        class FakeWriter:
            def close(self):
                pass

            async def wait_closed(self):
                pass

        return reader, FakeWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open)

    import coupler.bridge as b

    importlib.reload(b)
    b.RETRIES = retries
    result = await b._wait_for_server()
    assert result is True


@pytest.mark.asyncio
async def test_wait_for_server_fails_after_retries(monkeypatch):
    """Health check returns False after all retries exhausted."""
    retries = UNIT.get("retries_when_refused", int)
    retry_s = UNIT.get("retry_seconds_when_refused", (int, float))
    refusal = UNIT.get("refusal_message", str)

    async def fake_open(host, port):
        raise ConnectionRefusedError(refusal)

    monkeypatch.setattr(asyncio, "open_connection", fake_open)

    import coupler.bridge as b

    importlib.reload(b)
    b.RETRIES = retries
    b.RETRY_S = retry_s  # don't actually wait in tests
    result = await b._wait_for_server()
    assert result is False


# ── stub content ──────────────────────────────────────────────────────────────

def test_stub_status_message_contains_port():
    """The stub coupler_status message names the port so the user knows what to start."""
    stub = _stub_config()

    import coupler.bridge as b

    importlib.reload(b)
    # the stub tool function is defined inline in main() — test the JSON shape directly
    payload = json.dumps({
        stub["status_field"]: stub["status_down"],
        "message": stub["message_template"].format(
            port=b.PORT, server_module=stub["server_module"]
        ),
    }, indent=stub["json_indent"])
    data = json.loads(payload)
    assert data[stub["status_field"]] == stub["status_down"]
    assert str(b.PORT) in data["message"]
    assert stub["expected_server_hint"] in data["message"]


# ─────────────────────────────── the equivalence tables ───────────────────────────────

#: The exemplars this rewrite must reproduce: the three scenarios the ORIGINAL defines, with
#: the verdict each reaches. Ticket #393 captured no exemplars (criteria_miner refuses async,
#: mock-driven and no-arg functions), so this table is the hand-written equivalence basis the
#: ticket asks for in its place. Every expected outcome was read off the ORIGINAL's embedded
#: source, never off this rewrite.
#:
#: Each entry is (test function, what the original mocks, the property it pins down).
EXEMPLARS = [
    (
        "test_wait_for_server_succeeds_when_port_open",
        "asyncio.open_connection returns (StreamReader, writer-with-close/wait_closed)",
        "_wait_for_server() is True when the connect succeeds — and `is True`, not merely "
        "truthy, so a bridge returning a socket or a 1 fails here exactly as it did before",
    ),
    (
        "test_wait_for_server_fails_after_retries",
        "asyncio.open_connection always raises ConnectionRefusedError",
        "_wait_for_server() is False once RETRIES attempts are exhausted — `is False`, so a "
        "bridge returning None fails here exactly as it did before",
    ),
    (
        "test_stub_status_message_contains_port",
        "nothing — the payload is built in the test and round-tripped through JSON",
        "the stub payload parses, its status field reads 'down', and its message names both "
        "the live b.PORT and the server module",
    ),
]

#: Edge cases the original's three scenarios cannot reach on their own. #393 asks for "the
#: edge cases you add for what sampling cannot reach", and these are they: each pins down a
#: property the three tests above leave free, which a wrong bridge could violate while still
#: passing all three. Every expectation was likewise derived from the ORIGINAL test's own
#: statements about the bridge (see `coupler.bridge`'s docstring for that derivation).
#:
#: Each entry is (label, why the three exemplars cannot reach it).
EDGE_CASES = [
    ("connect is attempted exactly RETRIES times when refused",
     "exemplar 2 only checks the False verdict; a bridge that gave up after one attempt, or "
     "looped forever, would still return False and pass it"),
    ("no further attempt is made once the connect succeeds",
     "exemplar 1 uses retries_when_port_open == 1, so a bridge that ignored success and kept "
     "connecting could not be distinguished by it"),
    ("the writer is closed and awaited on the success path",
     "exemplar 1's FakeWriter records nothing; a bridge that leaked every socket it opened "
     "would pass it unchanged"),
    ("open_connection is called with (HOST, PORT) positionally",
     "exemplar 1's fake accepts the arguments but never inspects them, so a bridge dialling "
     "the wrong host or port would pass it"),
    ("RETRY_S is slept between attempts, and not after the last one",
     "exemplar 2 sets RETRY_S to 0.01 so the wait is invisible; a bridge that never slept, "
     "or that slept once more than needed, would pass it"),
    ("RETRIES == 0 returns False without connecting at all",
     "neither exemplar exercises the empty loop, where an off-by-one would connect once"),
    ("a non-OSError from the connect propagates rather than counting as 'down'",
     "exemplar 2 raises only ConnectionRefusedError; a bridge with a bare `except:` would "
     "swallow a real bug and report the server down, and would still pass it"),
    ("the bridge's REAL shipped stub satisfies exemplar 3's three assertions",
     "exemplar 3 builds its own payload and never calls the bridge, so the shipped stub "
     "could contradict it entirely and exemplar 3 would still pass"),
]


# ─────────────────────────────── the selftest ───────────────────────────────

class _Raised:
    """A stand-in for a call that raised, so a check can FAIL instead of aborting.

    A test net that dies on the first unexpected exception hides every check after it, and
    reports a traceback where it owes a verdict. `_attempt` returns one of these instead.
    """

    def __init__(self, exception):
        self.exception = "%s: %s" % (type(exception).__name__, exception)

    def __repr__(self):
        return "<raised %s>" % self.exception


def _attempt(thunk):
    """Call `thunk` — awaiting it if it returns a coroutine — and return its result, or a
    `_Raised` if it raised anything.

    `_Raised` matches no expected value, so every check below turns an unexpected exception
    into a reported FAIL rather than an abort.
    """
    try:
        result = thunk()
        if inspect.iscoroutine(result):
            result = asyncio.run(result)
        return result
    except BaseException as exc:  # noqa: BLE001 — a test net must survive anything
        return _Raised(exc)


def _run_test(func):
    """Run one of this module's test functions the way pytest would, and return None on pass.

    Supplies the `monkeypatch` fixture when the function asks for one, runs a coroutine test
    in a fresh event loop, and always undoes the patches — the same guarantees pytest gives.
    Returns a short description of the failure, or None if the test passed.
    """
    patch = MonkeyPatch()
    try:
        args = () if not _wants_monkeypatch(func) else (patch,)
        result = func(*args)
        if inspect.iscoroutine(result):
            asyncio.run(result)
        return None
    except BaseException as exc:  # noqa: BLE001 — a failing test is a verdict, not a crash
        return "%s: %s" % (type(exc).__name__, exc)
    finally:
        patch.undo()


def _wants_monkeypatch(func):
    return "monkeypatch" in inspect.signature(func).parameters


def _fake_writer():
    class FakeWriter:
        closed = False
        awaited = False

        def close(self):
            FakeWriter.closed = True

        async def wait_closed(self):
            FakeWriter.awaited = True

    return FakeWriter


def selftest(stream=None):
    """Prove this rewrite against ticket #393's acceptance items (a), (b) and (d).

    Builds its own config objects in memory where it needs to, writes no files, opens no
    sockets, and leaves no configuration behind. Returns the number of failures.

    Checks, in order:
      1. the config gate — each test throws ConfigError, and reaches no verdict, when its
         config cannot be resolved;
      2. the exemplars — the three tests the ORIGINAL defines, run against `coupler.bridge`;
      3. the edge cases the three exemplars cannot reach;
      4. the callable surface — the three names, their parameters, and which are coroutines;
      5. no side effects — `asyncio.open_connection` is the real one again afterwards.
    """
    out = stream or sys.stdout
    failures = []
    checks = [0]

    def check(ok, label):
        checks[0] += 1
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    print("running under %s"
          % ("real pytest %s / pytest_asyncio %s"
             % (getattr(pytest, "__version__", "?"),
                "present" if HAVE_PYTEST_ASYNCIO else "ABSENT")
             if HAVE_PYTEST else
             "the built-in stand-ins (pytest is not installed on this interpreter)"),
          file=out)

    tests = [
        test_wait_for_server_succeeds_when_port_open,
        test_wait_for_server_fails_after_retries,
        test_stub_status_message_contains_port,
    ]

    saved_env = os.environ.get(REGISTRY_ENV)
    real_open_connection = asyncio.open_connection

    def restore_env():
        """Put `REGISTRY_ENV` back exactly as the operator had it — set or unset.

        Check [1] has to point the variable at a file that does not exist, and every check
        after it must run against the operator's OWN configuration. Popping the variable
        instead of restoring it would silently fall back to the walk-up, and since this
        package SHIPS a registry the walk-up always answers — so the rest of the selftest
        would report PASS on a registry the operator never named.
        """
        if saved_env is None:
            os.environ.pop(REGISTRY_ENV, None)
        else:
            os.environ[REGISTRY_ENV] = saved_env

    try:
        # ── 1. the config gate ────────────────────────────────────────────────
        print("\n[1] config gate — a test that cannot see its config throws", file=out)
        with tempfile.TemporaryDirectory() as isolated:
            # Point the registry env var at a file that does not exist. That source outranks
            # the walk-up, so the gate is staged the same way whether or not a registry
            # happens to sit above this module — and this package SHIPS one, so a bare call
            # here would otherwise succeed and prove nothing.
            os.environ[REGISTRY_ENV] = os.path.join(isolated, "no-such-registry.json")
            UNIT.reset()
            try:
                for func in tests:
                    outcome = _run_test(func)
                    check(outcome is not None and outcome.startswith("ConfigError:"),
                          "%s throws ConfigError with an unresolvable config (got %s)"
                          % (func.__name__, outcome or "a PASS — no config was needed"))
            finally:
                restore_env()
                UNIT.reset()

        # ── 2. the exemplars ──────────────────────────────────────────────────
        print("\n[2] exemplars — the three tests the ORIGINAL defines", file=out)
        for (name, mocks, prop), func in zip(EXEMPLARS, tests):
            check(func.__name__ == name,
                  "exemplar %d is %s" % (EXEMPLARS.index((name, mocks, prop)) + 1, name))
            outcome = _run_test(func)
            check(outcome is None, "%s passes — %s%s"
                  % (name, prop, "" if outcome is None else " [FAILED: %s]" % outcome))

        # ── 3. the edge cases ─────────────────────────────────────────────────
        print("\n[3] edge cases the exemplars cannot reach", file=out)
        try:
            _selftest_edges(check, out)
        except Exception as exc:  # noqa: BLE001 — a test net must survive anything
            # An incomplete config object is a verdict this selftest owes, not a reason to
            # abort it and hide checks [4] and [5] behind a traceback. It surfaces here as a
            # ConfigError when this unit's own section is short a key, and as a NameError
            # when the BRIDGE's section is absent — its module globals are then never bound.
            check(False, "the edge cases ran against a complete config object (%s: %s)"
                  % (type(exc).__name__, exc))

        # ── 4. the callable surface ───────────────────────────────────────────
        print("\n[4] callable surface", file=out)
        expected_surface = [
            ("test_wait_for_server_succeeds_when_port_open", "(monkeypatch)", True),
            ("test_wait_for_server_fails_after_retries", "(monkeypatch)", True),
            ("test_stub_status_message_contains_port", "()", False),
        ]
        for (name, signature, is_async), func in zip(expected_surface, tests):
            got = str(inspect.signature(func))
            check(func.__name__ == name and got == signature,
                  "%s%s matches the ticket's surface %s%s" % (func.__name__, got, name,
                                                              signature))
            check(inspect.iscoroutinefunction(func) is is_async,
                  "%s is %sa coroutine function, as the ticket's surface says"
                  % (name, "" if is_async else "not "))
            check(callable(getattr(sys.modules[__name__], name, None)),
                  "%s is importable from this module under that name" % name)

        # Under real pytest the mark is what makes an async test run at all; under the
        # stand-in it is recorded so this check can still read it back.
        for func in tests[:2]:
            marks = ([m.name for m in getattr(func, "pytestmark", [])] if HAVE_PYTEST
                     else getattr(func, "pytestmark_standin", []))
            check("asyncio" in marks,
                  "%s carries the asyncio mark, as the original did" % func.__name__)

        # ── 5. no side effects ────────────────────────────────────────────────
        print("\n[5] side effects", file=out)
        check(asyncio.open_connection is real_open_connection,
              "asyncio.open_connection is the real one again — every patch was undone, so "
              "these tests leave no fake behind for the next test to trip over")
    finally:
        restore_env()
        UNIT.reset()
        asyncio.open_connection = real_open_connection
        # The tests reload the bridge and rebind its globals; put it back on the config the
        # operator actually named, so an importer after `selftest` sees an unmutated module.
        # This runs after restore_env() for that reason — reloading first would rebind the
        # bridge from whichever registry check [1] had staged.
        try:
            import coupler.bridge as b

            importlib.reload(b)
        except ConfigError:
            # No config to reload against. The selftest's verdict above already says so, and
            # a bridge left unreloaded is not worth masking that verdict with a traceback.
            pass

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED",
             checks[0], len(failures)), file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


def _selftest_edges(check, out):
    """Run the EDGE_CASES table. Split out of `selftest` only to keep each readable."""
    import coupler.bridge as b

    patch = MonkeyPatch()
    try:
        importlib.reload(b)

        # ── attempts are counted, and the loop stops when refused RETRIES times ──
        attempts = []
        sleeps = []

        async def refuse(host, port):
            attempts.append((host, port))
            raise ConnectionRefusedError(UNIT.get("refusal_message", str))

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        patch.setattr(asyncio, "open_connection", refuse)
        patch.setattr(asyncio, "sleep", fake_sleep)

        b.RETRIES = 3
        b.RETRY_S = 0.25
        result = _attempt(lambda: b._wait_for_server())
        check(result is False and len(attempts) == 3,
              "connect is attempted exactly RETRIES times when refused (RETRIES=3 -> %d "
              "attempts, result %r)" % (len(attempts), result))
        check(sleeps == [0.25, 0.25],
              "RETRY_S is slept between attempts and not after the last one (RETRIES=3 -> "
              "slept %r, expected [0.25, 0.25])" % (sleeps,))
        check(all(a == (b.HOST, b.PORT) for a in attempts) and attempts,
              "open_connection is called with (HOST, PORT) positionally (got %r, HOST/PORT "
              "are %r)" % (attempts[:1], (b.HOST, b.PORT)))

        # ── RETRIES == 0 connects not at all ──
        attempts.clear()
        sleeps.clear()
        b.RETRIES = 0
        result = _attempt(lambda: b._wait_for_server())
        check(result is False and attempts == [] and sleeps == [],
              "RETRIES == 0 returns False without connecting at all (result %r, %d attempts)"
              % (result, len(attempts)))

        # ── success stops the loop, and the writer is closed and awaited ──
        attempts.clear()
        sleeps.clear()
        writer = _fake_writer()

        async def accept(host, port):
            attempts.append((host, port))
            return asyncio.StreamReader(), writer()

        patch.setattr(asyncio, "open_connection", accept)
        b.RETRIES = 5
        result = _attempt(lambda: b._wait_for_server())
        check(result is True and len(attempts) == 1,
              "no further attempt is made once the connect succeeds (RETRIES=5 -> %d "
              "attempt(s), result %r)" % (len(attempts), result))
        check(writer.closed and writer.awaited,
              "the writer is closed and awaited on the success path (close called: %s, "
              "wait_closed awaited: %s)" % (writer.closed, writer.awaited))
        check(sleeps == [],
              "a successful connect never sleeps (slept %r)" % (sleeps,))

        # ── a non-OSError propagates rather than counting as 'down' ──
        class _NotAnOSError(Exception):
            pass

        async def explode(host, port):
            raise _NotAnOSError("a real bug, not a closed port")

        patch.setattr(asyncio, "open_connection", explode)
        b.RETRIES = 2
        result = _attempt(lambda: b._wait_for_server())
        check(isinstance(result, _Raised) and result.exception.startswith("_NotAnOSError:"),
              "a non-OSError from the connect propagates rather than counting as 'down' "
              "(got %r)" % (result,))

        # ── the bridge's REAL shipped stub satisfies exemplar 3's assertions ──
        stub = _stub_config()
        payload = _attempt(lambda: b.stub_status_payload())
        if isinstance(payload, _Raised):
            check(False, "the bridge's real shipped stub is emittable (raised %s)"
                  % payload.exception)
        else:
            data = json.loads(payload)
            check(data.get(stub["status_field"]) == stub["status_down"]
                  and str(b.PORT) in data.get("message", "")
                  and stub["expected_server_hint"] in data.get("message", ""),
                  "the bridge's REAL shipped stub satisfies exemplar 3's three assertions — "
                  "the template the test checks is the one the bridge actually emits (%r)"
                  % (data,))
    finally:
        patch.undo()
        importlib.reload(b)


# ─────────────────────────────── the command line ───────────────────────────────

def _build_parser():
    parser = argparse.ArgumentParser(
        prog="forge2-coupler-test-bridge",
        description="forge2 rewrite of the forge unit "
                    "code__code-invalid__coupler:coupler/tests/test_bridge.py (ticket #393). "
                    "Config-driven: the tests throw if they cannot see their config object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="config is read from the registry named by $%s, else from the %s section of "
               "the nearest %s found by walking up from this module. This package ships one, "
               "so these commands work from a clean checkout. Run `emit-config` for a "
               "template." % (REGISTRY_ENV, " -> ".join(UNIT.path), REGISTRY_NAME),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="prove the exemplars, the edges, the gate and the surface")
    sub.add_parser("show-pytest", help="report whether real pytest is in use")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and its source")
    return parser


def main(argv=None):
    """Entry point for the `forge2-coupler-test-bridge` console script. Returns an exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your registry.json, or save a registry "
                  "containing it\n# and point $%s at that file. Until it is installed "
                  "these tests throw\n# ConfigError — they will not guess a default."
                  % (" -> ".join(UNIT.path), REGISTRY_ENV), file=sys.stderr)
            return 0

        if args.command == "show-pytest":
            print(json.dumps({
                "pytest": getattr(pytest, "__version__", None) if HAVE_PYTEST else None,
                "pytest_asyncio": HAVE_PYTEST_ASYNCIO,
                "in_use": "real pytest" if HAVE_PYTEST else "built-in stand-ins",
                "note": "the stand-ins are inert whenever real pytest is importable; "
                        "`pip install -e \".[test]\"` supplies pytest and pytest-asyncio",
            }, indent=2))
            return 0

        if args.command == "show-config":
            print(json.dumps({"unit": UNIT.name, "source": UNIT.source(),
                              "base": UNIT.base(), "config": UNIT.config()}, indent=2))
            return 0

        if args.command == "selftest":
            return 0 if selftest() == 0 else 1

    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        path = bug_report(UNIT, exc, traceback.format_exc(),
                          "python3 %s %s" % (os.path.basename(os.path.abspath(__file__)),
                                             " ".join(argv)))
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise

    return 0


if __name__ == "__main__":
    sys.exit(main())
