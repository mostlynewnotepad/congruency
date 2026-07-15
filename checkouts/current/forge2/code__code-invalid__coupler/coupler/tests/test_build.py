#!/usr/bin/env python3
"""forge2 / code__code-invalid__coupler / coupler.tests.test_build — a behavior-preserving
rewrite of the forge unit `code__code-invalid__coupler:coupler/tests/test_build.py` (module
key forge-rw:300ba60b5fceb278), filed under ticket #355 against the FORGE-wide refactor
standard #200.

(#355 supersedes #290, which named its source only as a `git cat-file` against the forge's
bare repos that the sandboxed pair_loop worker cannot run. #355 embeds the source instead, so
the rewrite needs no forge access, and the work is done HERE.)

WHAT THIS IS
------------
The original forge unit was 2907 bytes: a pytest module holding two fixtures and four unit
tests for `coupler.server`'s build resolution — `_load_build`, which reads jazz's
`build.json`, and `_notes_python`, which picks the interpreter for downstream notes services.
It needs no live services: it builds a fake jazz tree in a temp directory and points
`$JAZZ_ROOT` at it.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and it adds the three things #200 requires that the
original lacked: it is part of a proper installable package, it is driven by a configuration
object, and it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
Quoted from ticket #355, which lowered the original with codebean's `lower_node` (#183):

    fake_jazz(tmp_path, monkeypatch)
    mod(fake_jazz)
    test_load_build_reads_version(mod)
    test_load_build_missing_returns_empty(tmp_path, monkeypatch)
    test_notes_python_fallback_when_env_missing(mod)
    test_notes_python_uses_versioned_env(tmp_path, monkeypatch)

The "existing caller" of a pytest module is pytest itself, so the surface is preserved in the
way that matters to it: the same six names, the same parameters, the first two still fixtures
and the last four still tests. pytest collects and runs this module exactly as it collected
and ran the original. `selftest` check [4] PROVES this by re-lowering THIS file's own AST the
way #183 lowers a module and comparing the result to the six lines above, rather than
asserting it.

WHAT "BEHAVIOR-PRESERVING" MEANS FOR A TEST MODULE, AND HOW IT IS PROVEN HERE
-----------------------------------------------------------------------------
A test module's observable behavior is the VERDICT it reaches about the code under test: for
which implementations of `coupler.server` it passes, and for which it fails. Preserving it
means this file must reach the same verdict as the original for every implementation — no
stricter, so nothing the original accepted is failed here, and no laxer, so nothing the
original caught slips through.

That is a claim about a pair of programs, so `selftest` proves it as one, differentially. It
EMBEDS the original's own 2907 bytes (see `ORIGINAL_SOURCE`), executes them with a stubbed
`pytest`, and runs the original's four tests and this file's four tests against the SAME
`coupler.server` implementation, under identically staged conditions. It does that for seven
implementations — one faithful reference and six mutants — and compares the two verdict
vectors. The expected values are not hand-copied into a table and hoped to be right: they are
taken from the original AS IT RUNS. Ticket #355 records that criteria_miner captured NO
exemplars for this module ("nothing here qualified"), which "MOVES the work: you must write
the equivalence exemplars by hand" — `EXEMPLARS` and `EDGE_CASES` below are that hand-written
table, and the differential is what settles them.

THE MODULE UNDER TEST DOES NOT EXIST YET — AND THAT IS NOT THIS TICKET'S TO FIX
-------------------------------------------------------------------------------
`coupler.server` is a DIFFERENT forge module with its OWN rewrite ticket; it has not landed in
`forge2/code__code-invalid__coupler/` yet, and ticket #355 is explicit that it "covers ONE
module — the one identified below — and nothing else." So this file does not ship one, and
must not.

Two consequences, both deliberate:

  * Under pytest, these four tests import whatever the config's `server_module` names — by
    default `coupler.server`, exactly as the original did. Until that module lands they fail
    with `ModuleNotFoundError`, which is precisely what the original does today. That is the
    behavior preserved, not a defect introduced.
  * `selftest` therefore supplies its own `coupler.server` to test against: `REFERENCE_SERVER`
    below, a faithful reconstruction of the module under test, DERIVED FROM THE ORIGINAL
    TEST'S OWN STATEMENTS about it (see `REFERENCE_SERVER`'s comment for the line-by-line
    derivation). It is selftest scaffolding and nothing else — it is not a rewrite of
    `coupler/server.py`, it is not installed, it is not importable from this package, and it
    never touches the source tree: it is written into a temp directory that is removed
    afterwards. What makes it legitimate as evidence is that the ORIGINAL runs against it too,
    green, through the same import path — so it is a fair oracle rather than a target this
    rewrite was fitted to.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a single
    `.json` file at the root of a package holding the configuration for every tool in that
    package. `note-for-claude` states the contract in its own words — ".json will have all the
    configuration - for all tools in this set of packaging. (a configuration registry) -if a
    tool cannot see the registry it will throw an exeption." [sic] This package ships its own
    `registry.json` at its root, two directories above this file.
config object
    The chunk of that registry belonging to this unit — the section at
    `forge2 -> code__code-invalid__coupler -> coupler.tests.test_build`. It is what drives the
    four tests. `emit-config` prints a template of it.
fixture
    A pytest function whose return value is injected into any test that names it as a
    parameter. `fake_jazz` and `mod` are fixtures; `mod` itself names `fake_jazz`, so pytest
    builds the fake jazz tree first and hands the reloaded module to the test.
monkeypatch
    pytest's built-in fixture for setting an environment variable or an attribute for the
    duration of ONE test and putting it back afterwards. The original used it for both, which
    is what lets these tests move `$JAZZ_ROOT` without leaking it into the next test.
tmp_path
    pytest's built-in fixture handing each test a fresh, empty temp directory as a `Path`.
exemplar
    One (scenario -> expected outcome) pair the rewrite must reproduce, standing in for the
    automated captures ticket #355 could not mine.
mutant
    A deliberately broken `coupler.server` used by `selftest` to prove these tests actually
    DISCRIMINATE — a test that cannot fail proves nothing, so each mutant records which tests
    must fail against it, and the original is run against it to confirm that expectation.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The original hardcoded every parameter of its four scenarios: the module under test
(`coupler.server`), the env var names (`JAZZ_ROOT`, `JAZZ_DEV`) and the `/nonexistent` it
pinned the second to, the `conf/env/build.json` location, the whole build document (version
`1.0.42`, tag `v1.0.42`, build `42`, notes env `notes-jazz-1.0.42`), the versions and env
names it then ASSERTED, the `"python"` substring, the `envs/<name>/bin/python` layout, the
`0o755` mode, and the conda base interpreter path. Those are exactly the params #200's fourth
requirement forbids hardcoding, so every one of them is read from this unit's config object
and NOTHING is defaulted in code. Run `emit-config` to see the object; its values are the
original's own, which is what makes this rewrite behave identically in practice — the values
did not change, only their location did.

The config is read INSIDE each test, not at import time, deliberately: pytest must still be
able to import and collect this module, so a missing config object surfaces as four honest
`ConfigError` test failures naming what is missing, rather than one collection error that
hides which tests exist. `selftest` check [1] proves each test throws `ConfigError` — and
reaches no verdict about the server — when its config cannot be resolved.

WHY SOME VALUES APPEAR TWICE IN THE CONFIG, ON PURPOSE
------------------------------------------------------
`build_json.version` and `expected_version` both read `"1.0.42"`; `build_json.envs.notes`,
`versioned_env.build_json.envs.notes` and `versioned_env.env_name` all read
`"notes-jazz-1.0.42"`. That is not duplication to be collapsed. The original names each of
these strings twice or more — once in the fixture DATA it writes to disk, once in the
ASSERTION it makes about what came back, and (for the env name) once in the directory it
creates. Those are different roles. Collapse them into one key and the assertion checks the
fixture against itself: it could never fail, and a check the original made would be quietly
deleted. `selftest`'s mutants [2] and [3] fail precisely because these are kept apart.

RESOLUTION ORDER
----------------
The config object is resolved from the first source that answers:

  1. the file named by the `COUPLER_TEST_BUILD_CONFIG` environment variable, which holds this
     unit's config object itself — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code-invalid__coupler -> coupler.tests.test_build`
     section of the nearest `registry.json` found by walking UP from THIS FILE's directory.

If neither answers, every test raises `ConfigError`. It never guesses a default. The walk-up
starts at this file, never at the working directory, so which directory you run from does not
change what config is found.

The variable is named for THIS UNIT rather than shared across the package for the reason
`coupler/_config.py` (#397) already records: a variable holding ONE unit's config object could
only ever point at one unit's object at a time, so a shared name would mean pointing it at a
sibling's config breaks this one. `$COUPLER_CONFIG` is #397's; this unit does not read it and
does not collide with it.

THE PYTEST DEPENDENCY, AND WHY THIS MODULE STILL RUNS WITHOUT IT
----------------------------------------------------------------
The original imports `pytest` at module scope, so it cannot be imported at all where pytest is
absent — and pytest is absent from the BARE interpreter this package is developed against
(Homebrew CPython 3.14, where a direct `pip install` is refused by PEP 668's
"externally-managed-environment"). This rewrite declares pytest in `pyproject.toml`'s `test`
EXTRA, so `pip install -e ".[test]"` into a virtualenv supplies it and pytest runs this module
as it ran the original. That is the primary path, and it has been run: see WHAT HAS ACTUALLY
BEEN RUN below.

It is an extra rather than a required dependency on purpose. Ticket #355's acceptance item (c)
is that `pip install -e .` installs CLEAN from this package's own pyproject.toml, and a
required pytest would make that install depend on a package index being reachable. The package
does not need pytest to be installed or used — only to be tested through pytest — so nothing
is required and the plain install always succeeds.

Where pytest is not installed, this module falls back to a minimal stand-in providing the only
pieces of pytest these tests use: `pytest.fixture`, and a `monkeypatch` with `setenv`,
`setattr` and `undo`. The fallback exists so `selftest` can prove this rewrite's behavior on a
bare interpreter, and it is inert whenever real pytest is importable — under pytest, the real
decorator and the real fixtures are used and NOTHING here is in the path. `selftest` reports
which of the two it ran under, so the reader is never guessing; `show-pytest` reports the same
on its own.

Why the stand-ins cannot fake an agreement that is not there: they touch only how a test is
INVOKED (a decorator that returns the function, a fixture that sets and restores), never what
it ASSERTS, and the differential runs the ORIGINAL through those SAME stand-ins — so any
distortion they introduced lands on both sides equally. `selftest` also reports which path it
took, so a reader can see it rather than infer it.

WHAT HAS ACTUALLY BEEN RUN, AND WHAT HAS NOT
--------------------------------------------
Stated plainly rather than left for the reader to discover. All of the following were executed
against this file as it stands:

  * `selftest` on the bare interpreter, through the stand-ins — 45 checks, 0 failures.
  * `pip install -e ".[test]"` into a virtualenv, from a copy of this package in a temp tree —
    exit 0. It builds the editable wheel and installs pytest. The package copy is what gets
    installed, so the source tree never receives an `.egg-info`. The venv is the reason this is
    possible at all: a direct `pip install` on the system interpreter is refused by PEP 668,
    but `python3 -m venv` + that venv's pip is not.
  * `forge2-coupler-test-build selftest`, the console script `pyproject.toml` declares, from
    the installed venv — it exists and runs.
  * REAL pytest (9.1.1) collecting this file — all four tests collected under their ticket
    names. This is the one thing the stand-in path cannot cover, and it is covered.
  * REAL pytest running this file AND the ORIGINAL's 2907 bytes side by side against the same
    `coupler.server` — 8 passed. The differential therefore holds under real pytest, not only
    under the stand-ins.

Not run, and not claimed: nothing about pytest's behavior on versions other than the 9.1.1 this
was exercised on. The two places pytest's own API could bite are handled by not depending on
it — `_fixture_impl` reaches the fixtures' `_*_impl` twins rather than calling a decorated
fixture (pytest 8.4+ returns a `FixtureFunctionDefinition` that refuses a direct call), and the
surface check reads this file's AST rather than any marker attribute (the `_pytestfixturefunction`
attribute those versions removed).

ONE VERDICT THAT DEPENDS ON THE ENVIRONMENT
-------------------------------------------
  * Exemplar 3's verdict is environment-dependent, in the original exactly as here. It asserts
    the fallback interpreter EXISTS, so against a real conda-hunting `coupler.server` on a host
    with no conda it fails — for the original and this rewrite alike, since both call the same
    `mod._notes_python()`. The reference server's base interpreter is `sys.executable`, which
    exists and contains "python", so exemplar 3 is genuinely exercised here rather than
    vacuously skipped. See EDGE_CASES.

RUNNING IT
----------
Every command below is executable as written FROM THE PACKAGE ROOT — the directory holding
`pyproject.toml`, two levels above this file. The `-m` form is what makes them run without
installing anything: it puts the package root on the import path, so `coupler` resolves.
Running the file by path (`python3 coupler/tests/test_build.py`) does NOT work uninstalled,
because Python would put `coupler/tests/` on the import path instead of the package root, and
the `coupler` package would not be importable. That mistake is foreseeable, so it is ANSWERED
rather than merely warned about here: it exits 2 with a `usage error:` line naming the
invocation that does work — no traceback, and no bug report, because the tool is not the thing
that is broken. See `UsageError`.

    python3 -m coupler.tests.test_build selftest        # the differential, mutants, gate, surface
    python3 -m coupler.tests.test_build install-check   # what can be checked of the package
    python3 -m coupler.tests.test_build show-pytest     # report whether real pytest is in use
    python3 -m coupler.tests.test_build emit-config     # print a config-object template
    python3 -m coupler.tests.test_build show-config     # print the resolved config + its source

Once installed (see INSTALLABLE), the console script runs from any directory:

    forge2-coupler-test-build selftest

Under real pytest the ordinary invocation works and is the point — pytest puts the rootdir on
the import path itself, so the `-m` dance is not needed:

    pip install -e ".[test]"
    pytest coupler/tests/test_build.py -v    # collects and runs the four tests above

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, committed in full beside it:
`pyproject.toml`, `registry.json`, `coupler/__init__.py`, `coupler/_config.py`,
`coupler/tests/__init__.py`. From the package root:

    pip install -e .
    forge2-coupler-test-build selftest

`pyproject.toml` declares `coupler` and `coupler.tests` in `[tool.setuptools] packages`, so an
installed copy imports as `coupler.tests.test_build` — the path the forge unit was originally
addressed by (repo `code__code-invalid__coupler`, path `coupler/tests/test_build.py`). See the
comment in `pyproject.toml` for why those two entries are added to a file
`congruency/tools/forge_package.py` (#410) otherwise generates: that generator enumerates only
TOP-LEVEL modules of a forge package, and this package's units live in the `coupler/`
subpackage, so its generated form declares no package this module is in.

SIDE EFFECTS
------------
The four tests create files, and always have: that is what they are for. Each writes a fake
jazz tree — `conf/env/build.json`, and for exemplar 4 an `envs/<name>/bin/python` — INSIDE the
temp directory `tmp_path` hands it, and nothing outside it. Under pytest, pytest owns that
directory's lifetime; under the built-in runner, `selftest` removes it. They set `$JAZZ_ROOT`
and `$JAZZ_DEV` through `monkeypatch`, which restores both when the test ends. They open no
sockets and reach no network.

`selftest` additionally writes its reference/mutant `coupler.server` into a temp directory it
removes, and appends that directory to `coupler.__path__` for the duration of the run so the
module is importable and RELOADABLE the way the tests require; both are undone in a `finally`.
It writes nothing into the source tree.

The one thing that can write outside a temp directory is the command line, which per
`note-for-claude` ("all tools need to pass a bug-report automatically (timestamped if an
exception is thrown)") appends one timestamped JSON line to the config's `bug_reports` path if
it hits an UNEXPECTED exception — a defect in this tool. The report records the invocation that
ACTUALLY ran (`_invocation`) rather than a fixed string, so a reader can reproduce what
happened. `ConfigError` and `UsageError` are designed behavior, not bugs, and neither is
reported: a sink that fired on a mistyped command would bury the real defects under false
ones. Each files no report, prints no traceback, and exits 2 with a single self-explaining
line. (CPython still writes its usual `__pycache__` bytecode for any module it imports; that
is the interpreter's doing, and #355 lists `__pycache__` among the build artifacts that are
regenerated by any install and never committed.)
"""

import argparse
import ast
import contextlib
import importlib
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
import types
from datetime import datetime, timezone
from pathlib import Path

# ── the pytest dependency ─────────────────────────────────────────────────────────────────
#
# Real pytest when it is installed — the original imported it at module scope, and under
# pytest this rewrite uses exactly what the original used. The stand-ins below are reached
# only on an interpreter where pytest is absent, and provide the only pieces of it this module
# needs. See THE PYTEST DEPENDENCY in the module docstring.

try:
    import pytest

    HAVE_PYTEST = True
except ImportError:  # pragma: no cover — depends on the interpreter, not on a branch
    HAVE_PYTEST = False


class _FixtureStandIn:
    """Stand-in for `pytest.fixture`, used only where pytest is not installed.

    Under real pytest, `@pytest.fixture` marks a function so that any test naming it as a
    parameter receives its return value. With no pytest to read the mark, the stand-in records
    it and returns the function UNCHANGED, and `_run_test` below resolves fixtures itself.
    Accepting `*args`/`**kwargs` mirrors the real decorator's `@pytest.fixture(scope=...)`
    call form, so a future use of it here would not trip over the stand-in.
    """

    def __call__(self, *args, **kwargs):
        if len(args) == 1 and not kwargs and callable(args[0]):
            args[0].__is_fixture__ = True
            return args[0]

        def decorator(func):
            func.__is_fixture__ = True
            return func

        return decorator


class _PytestStandIn:
    """Stand-in for the `pytest` module, used only where pytest is not installed."""

    fixture = _FixtureStandIn()


if not HAVE_PYTEST:  # pragma: no cover — depends on the interpreter, not on a branch
    pytest = _PytestStandIn()


class MonkeyPatch:
    """A minimal stand-in for pytest's `monkeypatch` fixture: set, then undo.

    Used by the built-in runner on an interpreter with no pytest, and never used when pytest
    supplies the real fixture. It implements only what these tests ask of it — `setenv`,
    `setattr`, `undo` — and matches the real fixture on the three behaviors they depend on:
    `setattr` raises `AttributeError` rather than creating an attribute that was not already
    there, `setenv` remembers an ABSENT variable as absent (not as the empty string) so undo
    removes it again, and `undo` restores in reverse order.
    """

    def __init__(self):
        self._undo = []

    def setenv(self, name, value):
        self._undo.append(("env", (name, None), os.environ.get(name)))
        os.environ[name] = str(value)

    def setattr(self, target, name, value):
        previous = getattr(target, name)  # AttributeError here mirrors the real fixture
        self._undo.append(("attr", (target, name), previous))
        setattr(target, name, value)

    def undo(self):
        while self._undo:
            kind, key, previous = self._undo.pop()
            if kind == "env":
                if previous is None:
                    os.environ.pop(key[0], None)
                else:
                    os.environ[key[0]] = previous
            else:
                setattr(key[0], key[1], previous)


# ─────────────────────────────── configuration ───────────────────────────────
#
# Self-contained ON PURPOSE. This module resolves its own config rather than importing a
# helper from a sibling file, because a forge rewrite unit's deliverable is ONE module and a
# sibling it depends on may not be present: `coupler/tests/test_bridge.py` (#393) imports
# `coupler.config`, which does not exist in this package, and is unimportable today as a
# result. This file has no such dependency and runs against the package as it actually is.

#: Environment variable naming a file that holds THIS unit's config object.
CONFIG_ENV = "COUPLER_TEST_BUILD_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS
#: in the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own.
UNIT_PATH = ("forge2", "code__code-invalid__coupler", "coupler.tests.test_build")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code-invalid__coupler/coupler/tests/test_build"

#: This module's own dotted import name. It is `UNIT_PATH`'s last element by construction — a
#: unit's address inside the registry IS its dotted path within the package — so it is derived
#: rather than written twice and cannot drift from it. Used only to print an invocation a
#: reader can retype; `__name__` is "__main__" under `-m` and `__spec__` is None when this file
#: is run by path, so neither can answer this on its own.
DOTTED_NAME = UNIT_PATH[-1]


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and ticket #355's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.
    """


class UsageError(RuntimeError):
    """Raised when this module was INVOKED in a way that cannot work — not a defect in it.

    Kept apart from every other exception for the same reason `ConfigError` is: the command
    line reports both as one self-explaining line and files NO bug report, because a bug report
    is supposed to mean "this tool is broken". The foreseeable case is running this file by
    path (`python3 coupler/tests/test_build.py`), which puts `coupler/tests/` on the import
    path instead of the package root and so leaves the `coupler` package unimportable. That is
    a mistake the message can fix in one line; answering it with a traceback and a filed bug
    report would blame the tool for the invocation and put a false record in the sink.
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do the four tests throw `ConfigError`. Every value
    below is one the ORIGINAL hardcoded, so a config built from this template makes the tests
    behave exactly as the original's did.
    """
    return {
        "server_module": "coupler.server",
        "jazz_root_env": "JAZZ_ROOT",
        "jazz_dev_env": "JAZZ_DEV",
        "jazz_dev_value": "/nonexistent",
        "build_json_path": "conf/env/build.json",
        "build_json": {
            "version": "1.0.42",
            "tag": "v1.0.42",
            "build": 42,
            "envs": {"notes": "notes-jazz-1.0.42"},
        },
        "expected_version": "1.0.42",
        "expected_notes_env": "notes-jazz-1.0.42",
        "expected_empty_build": {},
        "python_name_fragment": "python",
        "versioned_env": {
            "build_json": {
                "version": "1.0.42",
                "envs": {"notes": "notes-jazz-1.0.42"},
            },
            "env_name": "notes-jazz-1.0.42",
            "python_relpath": "envs/{env_name}/bin/python",
            "python_mode": 493,
            "conda_base_python": "/opt/homebrew/Caskroom/miniconda/base/bin/python",
        },
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


def require(section, key, where, types_):
    """Return `section[key]`, proving it is present and of the right type; else ConfigError.

    Type-checking here rather than letting a bad value flow onward is deliberate: a config
    mistake must surface as a config error naming the key, not as a puzzling `TypeError` from
    inside a test, where a reader would take it for a verdict about `coupler.server`.

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
    if not isinstance(value, types_) or isinstance(value, bool) and bool not in _as_tuple(types_):
        names = " or ".join(t.__name__ for t in _as_tuple(types_))
        raise ConfigError("config key %r under %s for %s must be %s, not %s"
                          % (key, where, UNIT, names, type(value).__name__))
    return value


def _as_tuple(types_):
    return types_ if isinstance(types_, tuple) else (types_,)


def _config():
    """Return this unit's config object, throwing if it cannot be seen.

    Every test calls this FIRST, before it touches the module under test, so a missing config
    is reported as a config error rather than as a verdict about `coupler.server`.
    """
    return active_config()


# ─────────────────────────────── the fixtures ───────────────────────────────
#
# Each fixture's body lives in a plain `_*_impl` function so the built-in runner can call it
# directly. Under real pytest, `@pytest.fixture` may return a wrapper that is not callable as
# an ordinary function, and the runner must not depend on which. The decorated names keep the
# ticket's surface exactly; the impls are internals.


def _fake_jazz_impl(tmp_path, monkeypatch):
    """Build a fake jazz tree in `tmp_path`, point the jazz env vars at it, and return it.

    Reproduces the original's `fake_jazz`: write the configured build document at the
    configured path under `tmp_path`, set the jazz-root variable to `tmp_path` and the
    jazz-dev variable to the configured (deliberately absent) path, and hand back `tmp_path`.
    """
    config = _config()
    build_json_path = require(config, "build_json_path", UNIT, str)
    build_json = require(config, "build_json", UNIT, dict)

    env_file = tmp_path / build_json_path
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(json.dumps(build_json))

    monkeypatch.setenv(require(config, "jazz_root_env", UNIT, str), str(tmp_path))
    monkeypatch.setenv(require(config, "jazz_dev_env", UNIT, str),
                       require(config, "jazz_dev_value", UNIT, str))
    return tmp_path


def _mod_impl(fake_jazz):
    """Import the configured module under test and RELOAD it, returning the module.

    The reload is the point, not a formality: the module under test snapshots the jazz root
    from the environment at import time, so it must be re-executed AFTER `fake_jazz` has moved
    `$JAZZ_ROOT`. `fake_jazz` is named as a parameter for its EFFECT — the tree and the env
    vars — rather than for its value, exactly as in the original.
    """
    module_name = require(_config(), "server_module", UNIT, str)
    module = importlib.import_module(module_name)
    importlib.reload(module)
    return module


@pytest.fixture
def fake_jazz(tmp_path, monkeypatch):
    """A fake jazz tree with a build document, with `$JAZZ_ROOT`/`$JAZZ_DEV` pointed at it."""
    return _fake_jazz_impl(tmp_path, monkeypatch)


@pytest.fixture
def mod(fake_jazz):
    """The module under test, reloaded so it picks up the fake jazz tree."""
    return _mod_impl(fake_jazz)


# ─────────────────────────────── build resolution ───────────────────────────────


def test_load_build_reads_version(mod):
    """_load_build reads the build document the fake jazz tree holds."""
    config = _config()
    b = mod._load_build()
    assert b["version"] == require(config, "expected_version", UNIT, str)
    assert b["envs"]["notes"] == require(config, "expected_notes_env", UNIT, str)


def test_load_build_missing_returns_empty(tmp_path, monkeypatch):
    """_load_build returns an empty document when there is no build file at all."""
    config = _config()
    monkeypatch.setenv(require(config, "jazz_root_env", UNIT, str), str(tmp_path))
    monkeypatch.setenv(require(config, "jazz_dev_env", UNIT, str),
                       require(config, "jazz_dev_value", UNIT, str))
    m = importlib.import_module(require(config, "server_module", UNIT, str))
    importlib.reload(m)
    assert m._load_build() == require(config, "expected_empty_build", UNIT, dict)


# ─────────────────────────────── interpreter resolution ───────────────────────────────


def test_notes_python_fallback_when_env_missing(mod):
    """Versioned conda env doesn't exist → falls back to base python."""
    config = _config()
    python = mod._notes_python()
    assert Path(python).exists()
    assert require(config, "python_name_fragment", UNIT, str) in python


def test_notes_python_uses_versioned_env(tmp_path, monkeypatch):
    """Uses versioned env python when the path exists."""
    config = _config()
    versioned = require(config, "versioned_env", UNIT, dict)
    where = "%s -> versioned_env" % UNIT
    env_name = require(versioned, "env_name", where, str)
    python_relpath = require(versioned, "python_relpath", where, str)
    conda_base_python = require(versioned, "conda_base_python", where, str)

    # create a fake versioned python
    fake_python = tmp_path / python_relpath.format(env_name=env_name)
    fake_python.parent.mkdir(parents=True)
    fake_python.touch()
    fake_python.chmod(require(versioned, "python_mode", where, int))

    env_file = tmp_path / require(config, "build_json_path", UNIT, str)
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(json.dumps(require(versioned, "build_json", where, dict)))

    monkeypatch.setenv(require(config, "jazz_root_env", UNIT, str), str(tmp_path))
    monkeypatch.setenv(require(config, "jazz_dev_env", UNIT, str),
                       require(config, "jazz_dev_value", UNIT, str))

    # patch the conda base path
    m = importlib.import_module(require(config, "server_module", UNIT, str))
    # Reads `__code__` off the module's own `_notes_python`. The value is unused — in the
    # original too — but the ACCESS is a real check and is preserved: it raises AttributeError
    # unless `_notes_python` is a Python function, which is how mutant [6] is caught.
    m._notes_python.__code__

    # monkeypatch the base path inside _notes_python by overriding the candidate path
    def patched():
        build = m._load_build()
        envs = build.get("envs", {})
        notes_env = envs.get("notes", "")
        if notes_env:
            candidate = str(tmp_path / python_relpath.format(env_name=notes_env))
            if Path(candidate).exists():
                return candidate
        return conda_base_python

    monkeypatch.setattr(m, "_notes_python", patched)
    importlib.reload(m)
    # reload resets the monkeypatch — just call patched directly
    result = patched()
    assert result == str(tmp_path / python_relpath.format(env_name=env_name))


# ─────────────────────────────── the equivalence tables ───────────────────────────────

#: The exemplars this rewrite must reproduce: the four scenarios the ORIGINAL defines, with
#: the verdict each reaches. Ticket #355 captured no exemplars (criteria_miner "mines only
#: self-contained pure functions ... and nothing here qualified"), so this table is the
#: hand-written equivalence basis the ticket asks for in its place. Every expected outcome was
#: read off the ORIGINAL's embedded source, never off this rewrite — and `selftest` does not
#: trust even that: it RUNS the original and compares.
#:
#: Each entry is (test name, what the scenario stages, the property it pins down).
EXEMPLARS = [
    (
        "test_load_build_reads_version",
        "a fake jazz tree whose conf/env/build.json holds the full build document",
        "_load_build() parses the document under $JAZZ_ROOT — its version and its notes env "
        "name come back exactly as written",
    ),
    (
        "test_load_build_missing_returns_empty",
        "a $JAZZ_ROOT with no conf/env/build.json at all",
        "_load_build() returns {} for a missing build file — it does not raise, and does not "
        "invent a document",
    ),
    (
        "test_notes_python_fallback_when_env_missing",
        "a build document naming a notes env, but no envs/<name>/bin/python on disk",
        "_notes_python() falls back to a base interpreter that EXISTS and whose path contains "
        "'python'",
    ),
    (
        "test_notes_python_uses_versioned_env",
        "a build document naming a notes env, WITH envs/<name>/bin/python created 0o755",
        "the versioned env's python is chosen when it exists. Note what this actually pins "
        "down: the original asserts on a `patched()` defined inside the test, so the property "
        "verified is _load_build()'s — that a reloaded module reads the CURRENT $JAZZ_ROOT — "
        "plus the requirement that the module expose `_notes_python` as a Python function. "
        "See EDGE_CASES; this weakness is the original's and is preserved, not fixed",
    ),
]

#: Edge cases the four exemplars cannot reach on their own. #355 asks for "the edge cases you
#: add for what sampling cannot reach", and these are they. Each entry is (label, why the
#: exemplars cannot reach it) — and each is PROVEN by a numbered check in `selftest`, not
#: merely listed.
EDGE_CASES = [
    ("the four tests DISCRIMINATE — each mutant server is failed by exactly the tests that "
     "should fail it, and the original agrees test-for-test",
     "all four exemplars passing proves only that a correct server passes; a test that cannot "
     "fail would pass them just as happily. MUTANTS is the negative half of the differential"),
    ("a broken _notes_python is NOT caught by test_notes_python_uses_versioned_env",
     "the original asserts on a `patched()` it defines itself, never on the module's own "
     "_notes_python, so mutant [3] — which always ignores the versioned env — passes all four "
     "tests. Preserved deliberately: #355 asks for a behavior-preserving rewrite, not a better "
     "test suite. Proven rather than asserted, and the original is run against it to confirm "
     "it passes there too"),
    ("_load_build must re-read $JAZZ_ROOT on every reload",
     "no single exemplar can show this; it is visible only because exemplars 1, 2 and 4 each "
     "use a DIFFERENT tmp_path and all three still reach their verdict, which a module that "
     "snapshotted the root once could not do"),
    ("the config gate — each test throws ConfigError, and reaches NO verdict, when its config "
     "cannot be resolved",
     "the exemplars all run WITH a config, so none of them can show what happens without one; "
     "acceptance item (d) is exactly that case"),
    ("exemplar 3's verdict is environment-dependent, in the original exactly as here",
     "it asserts the fallback interpreter EXISTS, so against a real conda-hunting server on a "
     "host with no conda it fails — for BOTH modules, since both call the same "
     "mod._notes_python(). The reference's base interpreter is sys.executable, which exists "
     "and contains 'python', so the exemplar is genuinely exercised rather than vacuously "
     "skipped"),
    ("the callable surface is the ticket's, lowered from this file's own AST",
     "running the tests cannot show that they present the right names and parameters to "
     "pytest; only lowering the source can"),
]


# ─────────────────────────────── the oracle ───────────────────────────────

#: The ORIGINAL forge unit, embedded verbatim from ticket #355 — 2907 bytes, byte for byte.
#: This is the behavior-preserving basis, and `selftest` does not merely read it: it EXECUTES
#: it against the same servers this rewrite is run against and compares the verdicts. Keeping
#: the original here is what makes the equivalence a measurement rather than an assertion.
ORIGINAL_SOURCE = '''"""
Unit tests for build resolution — _load_build, _notes_python.
No live services required.
"""
import json
from pathlib import Path

import pytest


@pytest.fixture
def fake_jazz(tmp_path, monkeypatch):
    env_dir = tmp_path / "conf" / "env"
    env_dir.mkdir(parents=True)
    (env_dir / "build.json").write_text(json.dumps({
        "version": "1.0.42",
        "tag": "v1.0.42",
        "build": 42,
        "envs": {"notes": "notes-jazz-1.0.42"},
    }))
    monkeypatch.setenv("JAZZ_ROOT", str(tmp_path))
    monkeypatch.setenv("JAZZ_DEV",  "/nonexistent")
    return tmp_path


@pytest.fixture
def mod(fake_jazz):
    import importlib
    import coupler.server as m
    importlib.reload(m)
    return m


def test_load_build_reads_version(mod):
    b = mod._load_build()
    assert b["version"] == "1.0.42"
    assert b["envs"]["notes"] == "notes-jazz-1.0.42"


def test_load_build_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("JAZZ_ROOT", str(tmp_path))
    monkeypatch.setenv("JAZZ_DEV",  "/nonexistent")
    import importlib
    import coupler.server as m
    importlib.reload(m)
    assert m._load_build() == {}


def test_notes_python_fallback_when_env_missing(mod):
    """Versioned conda env doesn\'t exist → falls back to base python."""
    python = mod._notes_python()
    assert Path(python).exists()
    assert "python" in python


def test_notes_python_uses_versioned_env(tmp_path, monkeypatch):
    """Uses versioned env python when the path exists."""
    # create a fake versioned python
    fake_env = tmp_path / "envs" / "notes-jazz-1.0.42" / "bin"
    fake_env.mkdir(parents=True)
    fake_python = fake_env / "python"
    fake_python.touch()
    fake_python.chmod(0o755)

    env_dir = tmp_path / "conf" / "env"
    env_dir.mkdir(parents=True)
    (env_dir / "build.json").write_text(json.dumps({
        "version": "1.0.42",
        "envs": {"notes": "notes-jazz-1.0.42"},
    }))

    monkeypatch.setenv("JAZZ_ROOT", str(tmp_path))
    monkeypatch.setenv("JAZZ_DEV",  "/nonexistent")

    # patch the conda base path
    import importlib
    import coupler.server as m
    original = m._notes_python.__code__
    # monkeypatch the base path inside _notes_python by overriding the candidate path
    real_fn = m._notes_python

    def patched():
        build = m._load_build()
        envs = build.get("envs", {})
        notes_env = envs.get("notes", "")
        if notes_env:
            candidate = str(tmp_path / "envs" / notes_env / "bin" / "python")
            if Path(candidate).exists():
                return candidate
        return "/opt/homebrew/Caskroom/miniconda/base/bin/python"

    monkeypatch.setattr(m, "_notes_python", patched)
    importlib.reload(m)
    # reload resets the monkeypatch — just call patched directly
    result = patched()
    assert result == str(tmp_path / "envs" / "notes-jazz-1.0.42" / "bin" / "python")
'''

#: The size ticket #355 records for the module under rewrite. `selftest` check [2] asserts the
#: embedded `ORIGINAL_SOURCE` weighs exactly this, which is what makes the oracle THE ORIGINAL
#: rather than a paraphrase of it: an edit to those bytes — a "fixed" typo, a re-indent, a
#: dropped dead assignment — moves the count and fails the check instead of silently changing
#: what this rewrite is measured against.
ORIGINAL_SIZE = 2907

#: The names of the four tests, in the ticket's order. Both modules are run through these.
TEST_NAMES = [
    "test_load_build_reads_version",
    "test_load_build_missing_returns_empty",
    "test_notes_python_fallback_when_env_missing",
    "test_notes_python_uses_versioned_env",
]

#: A faithful reconstruction of the MODULE UNDER TEST, used ONLY by `selftest`.
#:
#: `coupler.server` is a different forge module with its own rewrite ticket and has not landed
#: here; #355 covers "ONE module ... and nothing else", so this file does not ship one. But a
#: test module cannot be proven against nothing, so `selftest` writes THIS into a temp dir and
#: imports it as the configured `server_module`.
#:
#: Every line below is derived from the ORIGINAL TEST's own statements about `coupler.server`,
#: and from nothing else:
#:   * `JAZZ_ROOT` is read from the environment AT IMPORT into a module global — because the
#:     `mod` fixture reloads the module after setting `$JAZZ_ROOT`, which is only necessary if
#:     the module snapshots it at import.
#:   * `_load_build()` reads `conf/env/build.json` under that root and returns {} when the file
#:     is absent — `test_load_build_reads_version` and `test_load_build_missing_returns_empty`.
#:   * `_notes_python()` takes `envs.notes` from the build document, and returns
#:     `<root>/envs/<notes_env>/bin/python` when that path exists, else a base interpreter —
#:     this is the original's own `patched()`, which spells the algorithm out line by line.
#:   * `JAZZ_DEV` is read because the fixtures set it; nothing in the tests reads it back.
#: The base interpreter is `sys.executable` rather than the conda path the original's
#: `patched()` names, so that exemplar 3's `Path(python).exists()` is genuinely exercised on a
#: host with no conda. See EDGE_CASES.
#:
#: What makes this a fair oracle rather than a target this rewrite was fitted to: `selftest`
#: runs the ORIGINAL against it too, and the original passes all four.
REFERENCE_SERVER = '''"""Reference stand-in for coupler.server — selftest scaffolding only."""
import json
import os
import sys
from pathlib import Path

JAZZ_ROOT = Path(os.environ.get("JAZZ_ROOT", "/nonexistent"))
JAZZ_DEV = Path(os.environ.get("JAZZ_DEV", "/nonexistent"))
BASE_PYTHON = sys.executable


def _load_build():
    p = JAZZ_ROOT / "conf" / "env" / "build.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _notes_python():
    envs = _load_build().get("envs", {})
    notes_env = envs.get("notes", "")
    if notes_env:
        candidate = str(JAZZ_ROOT / "envs" / notes_env / "bin" / "python")
        if Path(candidate).exists():
            return candidate
    return BASE_PYTHON
'''


def _mutate(old, new):
    """Return REFERENCE_SERVER with `old` replaced by `new`, refusing a no-op replacement.

    A mutant that silently failed to apply would be a reference server wearing a mutant's
    label: every test would pass, and the check that expects failures would report a defect in
    this module that is not there. So the substitution is verified here rather than trusted.
    """
    if old not in REFERENCE_SERVER:
        raise AssertionError("mutation source not found in REFERENCE_SERVER: %r" % (old,))
    return REFERENCE_SERVER.replace(old, new, 1)


#: The mutants: deliberately broken `coupler.server` implementations, each with the tests that
#: MUST fail against it. This is the negative half of the differential — the half that proves
#: these tests can fail at all. `selftest` checks two things per mutant: that this rewrite
#: fails exactly the named tests, and that the ORIGINAL reaches the identical verdict.
#:
#: Each entry is (label, source, {names of tests that must FAIL}).
MUTANTS = [
    (
        "[1] _load_build always returns {} — it never reads the build file",
        _mutate("        return json.loads(p.read_text())", "        return {}"),
        {"test_load_build_reads_version", "test_notes_python_uses_versioned_env"},
    ),
    (
        "[2] _load_build invents a document when the build file is missing",
        _mutate('    return {}\n\n\ndef _notes_python',
                '    return {"version": "1.0.42", "envs": {"notes": "notes-jazz-1.0.42"}}'
                '\n\n\ndef _notes_python'),
        {"test_load_build_missing_returns_empty"},
    ),
    (
        "[3] _notes_python ignores the versioned env and always returns the base interpreter",
        _mutate('    envs = _load_build().get("envs", {})', "    return BASE_PYTHON\n    envs = {}"),
        set(),  # ← caught by NOTHING. See EDGE_CASES: this is the original's own blind spot.
    ),
    (
        "[4] _notes_python returns an interpreter path that does not exist",
        _mutate("    return BASE_PYTHON", '    return "/nonexistent/bin/python"'),
        {"test_notes_python_fallback_when_env_missing"},
    ),
    (
        "[5] _notes_python returns a real executable that is not a python",
        _mutate("    return BASE_PYTHON", '    return "/bin/sh"'),
        {"test_notes_python_fallback_when_env_missing"},
    ),
    (
        "[6] _notes_python is not a function at all",
        _mutate("def _notes_python():", '_notes_python = "/usr/bin/python3"\n\n\ndef _unused():'),
        {"test_notes_python_fallback_when_env_missing", "test_notes_python_uses_versioned_env"},
    ),
]


# ─────────────────────────────── the built-in runner ───────────────────────────────


def _resolve_fixture(name, namespace, cache, monkeypatch, tmp_path):
    """Resolve one fixture by name, the way pytest resolves a test's parameters.

    `tmp_path` and `monkeypatch` are pytest's built-ins and are supplied directly; any other
    name is looked up in `namespace` and called, with ITS parameters resolved the same way
    first. `cache` gives one test's fixtures function scope — `mod` and the test both naming
    `fake_jazz` must get the SAME tree, as under pytest.

    `namespace` is a dict rather than this module, so the ORIGINAL's fixtures resolve out of
    its exec'd namespace through this identical code path.
    """
    if name in cache:
        return cache[name]
    if name == "tmp_path":
        cache[name] = tmp_path
    elif name == "monkeypatch":
        cache[name] = monkeypatch
    else:
        if name not in namespace:
            raise LookupError("no fixture named %r" % name)
        func = _fixture_impl(namespace, name)
        args = [_resolve_fixture(p, namespace, cache, monkeypatch, tmp_path)
                for p in inspect.signature(func).parameters]
        cache[name] = func(*args)
    return cache[name]


def _fixture_impl(namespace, name):
    """Return a directly-callable implementation of the fixture `name` in `namespace`.

    THIS module routes `fake_jazz`/`mod` to their `_*_impl` twins, because under real pytest
    the decorated name may be a wrapper object that refuses a direct call. Any other namespace
    (the original's) hands back the decorated function itself, which the pytest stand-in leaves
    callable — and the original is only ever run under the stand-in, since the stand-in is what
    `selftest` execs it with.
    """
    if namespace is globals():
        impl = namespace.get("_%s_impl" % name)
        if impl is not None:
            return impl
    return namespace[name]


def _run_test(namespace, name):
    """Run one test out of `namespace` the way pytest would; return None on pass, else why.

    Gives the test a fresh empty `tmp_path`, resolves its fixtures, always undoes the
    monkeypatches and always removes the temp tree — the same guarantees pytest gives. A
    failing test is a VERDICT, so an exception becomes a description rather than an abort.
    """
    func = namespace[name]
    monkeypatch = MonkeyPatch()
    tmp_path = Path(tempfile.mkdtemp(prefix="test_build_"))
    try:
        args = [_resolve_fixture(p, namespace, {}, monkeypatch, tmp_path)
                for p in inspect.signature(func).parameters]
        func(*args)
        return None
    except BaseException as exc:  # noqa: BLE001 — a failing test is a verdict, not a crash
        return "%s: %s" % (type(exc).__name__, exc)
    finally:
        monkeypatch.undo()
        shutil.rmtree(tmp_path, ignore_errors=True)


def _run_all(namespace):
    """Run the four tests out of `namespace`; return {name: None-or-failure-description}."""
    return {name: _run_test(namespace, name) for name in TEST_NAMES}


def _exec_original():
    """Execute the embedded ORIGINAL with a stubbed `pytest`, and return its namespace.

    The original imports pytest at module scope, so on an interpreter without it the module
    cannot even be executed — and its behavior could not be measured at all. Stubbing
    `sys.modules["pytest"]` for the duration of the exec is what makes the oracle runnable
    here. The stub is the SAME `_FixtureStandIn` this module uses, so any distortion it
    introduces lands on both sides of the differential equally and cannot manufacture an
    agreement that is not there. `sys.modules` is put back exactly as it was, set or unset.
    """
    namespace = {"__name__": "coupler_tests_test_build_original_oracle"}
    stub = types.ModuleType("pytest")
    stub.fixture = _FixtureStandIn()
    saved, had = sys.modules.get("pytest"), "pytest" in sys.modules
    sys.modules["pytest"] = stub
    try:
        exec(compile(ORIGINAL_SOURCE, "<original forge unit #355>", "exec"), namespace)
    finally:
        if had:
            sys.modules["pytest"] = saved
        else:
            sys.modules.pop("pytest", None)
    return namespace


#: Every temp directory `_server` has created in this process. Recorded as it goes so that
#: `selftest` check [5] can prove no module is still loaded from one of THEM specifically.
#:
#: The obvious shortcut — "no module in sys.modules was loaded from anywhere under
#: `tempfile.gettempdir()`" — is WRONG, and wrong in the direction that matters: the package
#: itself may perfectly legitimately live under a temp dir. Proving acceptance item (c) means
#: copying this package to a temp tree and `pip install -e .`-ing it into a venv built there,
#: and then EVERY module — `coupler`, `pytest`, the console script's `__main__` — is "loaded
#: from a temp directory". The shortcut passes on the bare sandbox, where nothing is installed,
#: and fails the moment anyone installs the package properly, which is exactly when a reader
#: would trust it most.
_SERVER_DIRS = []


@contextlib.contextmanager
def _server(source, module_name):
    """Install `source` as the importable, RELOADABLE module `module_name`, then remove it.

    The tests do `importlib.import_module(name)` followed by `importlib.reload(...)`, and
    reload re-finds the module's spec through its parent package's `__path__` — so a module
    faked directly into `sys.modules` cannot be reloaded, and a module injected under a
    fabricated spec cannot either. The only mechanism that gives BOTH is a real file in a real
    directory the parent package can see, so this writes one into a temp dir and appends that
    dir to the parent's `__path__` for the duration.

    Everything is undone in the `finally`: the `__path__` entry, the `sys.modules` entries, and
    the temp directory. The source tree is never written to.
    """
    parent_name, _, child = module_name.rpartition(".")
    if not parent_name:
        raise ConfigError("server_module %r must name a module inside a package (e.g. "
                          "'coupler.server'), so the selftest can make it reloadable"
                          % module_name)
    try:
        parent = importlib.import_module(parent_name)
    except ImportError as exc:
        # The package this module lives in is not importable, so there is nothing to hang a
        # reference server off. Overwhelmingly this means the package root is not on the import
        # path — see UsageError. Reported as a usage mistake with the invocation that works,
        # not as a crash: the ModuleNotFoundError the tests raise when the module UNDER TEST is
        # absent is a verdict, but this one is about how the tool itself was started.
        raise UsageError(
            "cannot import %r, the package %r lives in (%s). The package root — the directory "
            "holding pyproject.toml — is probably not on the import path. Run it as a module "
            "FROM the package root:\n"
            "    python3 -m %s selftest\n"
            "or install the package and use its console script:\n"
            "    pip install -e . && forge2-coupler-test-build selftest\n"
            "Running this file by path cannot work: Python then puts this file's own directory "
            "on the import path instead of the package root."
            % (parent_name, module_name, exc, DOTTED_NAME)) from exc
    directory = tempfile.mkdtemp(prefix="test_build_server_")
    _SERVER_DIRS.append(directory)
    saved_child = sys.modules.get(module_name)
    had_child = module_name in sys.modules
    try:
        with open(os.path.join(directory, child + ".py"), "w", encoding="utf-8") as handle:
            handle.write(source)
        # PREPENDED, not appended. A package's __path__ is searched in order, so appending
        # only works while no real `coupler/server.py` exists — and the moment that unit lands
        # (it has its own ticket) the real module would win every lookup, every mutant would
        # silently become the reference server, and the mutant checks would report a defect in
        # THIS module that is not there. Prepending makes the staged server shadow whatever is
        # really installed, which is what a test of the TEST module needs.
        parent.__path__.insert(0, directory)
        importlib.invalidate_caches()
        sys.modules.pop(module_name, None)

        # Prove the shadowing actually took, rather than trusting it. find_spec resolves the
        # module the way the import system will, WITHOUT executing it — so if anything ever
        # out-ranks this directory again, the selftest says so loudly instead of quietly
        # measuring the wrong server and blaming the tests for the difference.
        spec = importlib.util.find_spec(module_name)
        origin = os.path.realpath(spec.origin) if spec and spec.origin else None
        if origin is None or not origin.startswith(os.path.realpath(directory) + os.sep):
            raise AssertionError(
                "the staged %s did not win the import: %r resolves to %s, not to the file just "
                "written under %s. The selftest would have measured a different module than the "
                "one it staged." % (module_name, module_name, origin or "nothing", directory))
        yield
    finally:
        with contextlib.suppress(ValueError):
            parent.__path__.remove(directory)
        sys.modules.pop(module_name, None)
        if had_child:
            sys.modules[module_name] = saved_child
        with contextlib.suppress(AttributeError):
            delattr(parent, child)
        importlib.invalidate_caches()
        shutil.rmtree(directory, ignore_errors=True)


def _strip_comments(obj):
    """Drop every `_`-prefixed key, recursively.

    This repository's registry idiom embeds `_comment` keys inside the objects they describe.
    They are documentation for a reader of the JSON, never settings, so a comparison against
    `config_template()` has to ignore them — and so must anything else that treats a config
    section as data.
    """
    if isinstance(obj, dict):
        return {key: _strip_comments(value) for key, value in obj.items()
                if not key.startswith("_")}
    return obj


def _verdicts(results):
    """Reduce a {name: None-or-failure} map to the SET of names that failed."""
    return {name for name, outcome in results.items() if outcome is not None}


def _describe(results):
    """One readable line for a verdict map: which tests passed and which failed."""
    return ", ".join("%s=%s" % (name.replace("test_", ""), "PASS" if outcome is None else "FAIL")
                     for name, outcome in results.items())


# ─────────────────────────────── the selftest ───────────────────────────────


def selftest(stream=None):
    """Prove this rewrite against ticket #355's acceptance items (a), (b) and (d).

    Builds its own config objects in memory, writes only into temp directories it removes,
    reaches no network, and leaves no configuration behind. Returns the number of failures.

    Checks, in order:
      1. the config gate — each test throws ConfigError, and reaches no verdict, when its
         config cannot be resolved (acceptance item (d));
      2. the exemplars — the four tests, against the reference server, with the ORIGINAL run
         against the same server and the two verdict vectors compared (acceptance item (a));
      3. the mutants — each broken server is failed by exactly the tests that should fail it,
         and the ORIGINAL agrees test-for-test (acceptance item (a), the negative half);
      4. the callable surface, lowered from this file's own AST (acceptance item (b));
      5. no side effects — the environment, sys.modules and coupler.__path__ are as they were.
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
          % ("real pytest %s" % getattr(pytest, "__version__", "?") if HAVE_PYTEST else
             "the built-in stand-ins (pytest is not installed on this interpreter)"), file=out)

    saved_env = {name: os.environ.get(name) for name in (CONFIG_ENV, "JAZZ_ROOT", "JAZZ_DEV")}

    def restore_env():
        """Put every variable back exactly as the operator had it — set or unset.

        Check [1] has to point CONFIG_ENV at a file that does not exist, and every check after
        it must run against the operator's OWN configuration. Popping the variable instead of
        restoring it would silently fall back to the walk-up, and since this package SHIPS a
        registry the walk-up always answers — so the rest of the selftest would report PASS on
        a registry the operator never named.
        """
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    try:
        # ── 1. the config gate ────────────────────────────────────────────────
        print("\n[1] config gate — a test that cannot see its config throws (item (d))", file=out)
        with tempfile.TemporaryDirectory() as isolated:
            # Point CONFIG_ENV at a file that does not exist. That source outranks the walk-up,
            # so the gate is staged the same way whether or not a registry happens to sit above
            # this module — and this package SHIPS one, so a bare call here would otherwise
            # succeed and prove nothing.
            os.environ[CONFIG_ENV] = os.path.join(isolated, "no-such-config.json")
            reset_config()
            try:
                for name in TEST_NAMES:
                    outcome = _run_test(globals(), name)
                    check(outcome is not None and outcome.startswith("ConfigError:"),
                          "%s throws ConfigError with an unresolvable config (got %s)"
                          % (name, outcome or "a PASS — no config was needed"))
            finally:
                restore_env()
                reset_config()

        config = _config()
        module_name = require(config, "server_module", UNIT, str)
        original_ns = _exec_original()

        # `emit-config`'s template claims to be what an operator should install, and the module
        # docstring claims the shipped values are the original's. Both are claims about this
        # package as it stands, so they are checked against it rather than trusted: a template
        # that had drifted from the registry would send an operator to a config that is not the
        # one these tests actually run on. `bug_reports` is excluded because it is inherited
        # from the registry's package-wide key rather than stated by this unit's section.
        shipped = {key: value for key, value in _strip_comments(config).items()
                   if key != "bug_reports"}
        check(shipped == config_template(),
              "the config object this package SHIPS is exactly what `emit-config` prints, so "
              "the template is not a lie an operator would install%s"
              % ("" if shipped == config_template() else
                 " (registry has %r, template has %r)"
                 % (sorted(shipped), sorted(config_template()))))

        # ── 2. the exemplars, differentially against the ORIGINAL ─────────────
        print("\n[2] exemplars — the four tests the ORIGINAL defines, and the ORIGINAL's own "
              "verdict on the same server (item (a))", file=out)
        embedded = len(ORIGINAL_SOURCE.encode("utf-8"))
        check(embedded == ORIGINAL_SIZE,
              "the embedded ORIGINAL weighs exactly the %d bytes ticket #355 records, so the "
              "oracle below is THE original and not a paraphrase of it (got %d)"
              % (ORIGINAL_SIZE, embedded))
        with _server(REFERENCE_SERVER, module_name):
            mine = _run_all(globals())
            theirs = _run_all(original_ns)

        for (name, stages, prop), key in zip(EXEMPLARS, TEST_NAMES):
            check(name == key, "exemplar %d is %s" % (TEST_NAMES.index(key) + 1, name))
            check(mine[key] is None, "%s passes against the reference server — %s%s"
                  % (key, prop, "" if mine[key] is None else " [FAILED: %s]" % mine[key]))
        check(_verdicts(mine) == _verdicts(theirs),
              "the ORIGINAL reaches the IDENTICAL verdict on every one of the four "
              "(original: %s | rewrite: %s)" % (_describe(theirs), _describe(mine)))
        check(_verdicts(theirs) == set(),
              "...and the ORIGINAL passes all four against the reference server, so it is a "
              "fair oracle and not a target this rewrite was fitted to (original: %s)"
              % _describe(theirs))

        # ── 3. the mutants ────────────────────────────────────────────────────
        print("\n[3] mutants — a test that cannot fail proves nothing (item (a), the negative "
              "half)", file=out)
        for label, source, must_fail in MUTANTS:
            with _server(source, module_name):
                mine = _run_all(globals())
                theirs = _run_all(original_ns)
            check(_verdicts(mine) == must_fail,
                  "%s -> failed by exactly %s (got %s)"
                  % (label, sorted(must_fail) or "NOTHING", _describe(mine)))
            check(_verdicts(mine) == _verdicts(theirs),
                  "    ...and the ORIGINAL agrees test-for-test (original: %s)"
                  % _describe(theirs))

        # ── 4. the callable surface ───────────────────────────────────────────
        print("\n[4] callable surface — lowered from this file's own AST (item (b))", file=out)
        lowered = _lower_surface(os.path.abspath(__file__))
        for signature in SURFACE:
            name = signature.split("(", 1)[0]
            check(lowered.get(name) == signature,
                  "%s presents the ticket's surface %r (got %r)"
                  % (name, signature, lowered.get(name)))
            check(callable(globals().get(name)),
                  "%s is importable from this module under that name" % name)
        check([s.split("(", 1)[0] for s in SURFACE] == [n for n in lowered
                                                        if n in {s.split("(", 1)[0]
                                                                 for s in SURFACE}],
              "the six surface names appear in the ticket's order")

        # ── 5. no side effects ────────────────────────────────────────────────
        print("\n[5] side effects", file=out)
        check(all(os.environ.get(n) == v for n, v in saved_env.items()),
              "$%s, $JAZZ_ROOT and $JAZZ_DEV are exactly as they were — every monkeypatch was "
              "undone, so these tests leave no environment behind for the next to trip over"
              % CONFIG_ENV)
        check(module_name not in sys.modules,
              "%s is gone from sys.modules — the reference/mutant servers left nothing behind"
              % module_name)
        # Checked against the directories `_server` ACTUALLY created (see _SERVER_DIRS), not
        # against tempfile.gettempdir() at large: this catches a server left loaded under any
        # name, while staying correct when the package itself is installed from a temp tree.
        # A plain set-difference against a sys.modules snapshot cannot say this either — the
        # stdlib imports lazily (ast.unparse pulls in _ast_unparse, tempfile registers atexit),
        # so it reports normal interpreter behavior as a leak.
        owned = [os.path.realpath(directory) + os.sep for directory in _SERVER_DIRS]
        leaked = sorted(
            name for name, module in list(sys.modules.items())
            if getattr(module, "__file__", None)
            and any(os.path.realpath(module.__file__).startswith(d) for d in owned))
        check(not leaked,
              "no module survives in sys.modules from any of the %d temp directories the "
              "reference and mutant servers were written to (leaked: %s)"
              % (len(_SERVER_DIRS), leaked or "none"))
        parent = sys.modules.get(module_name.rpartition(".")[0])
        check(parent is None or all(not p.startswith(tempfile.gettempdir())
                                    for p in parent.__path__),
              "no temp directory is left on %s.__path__" % module_name.rpartition(".")[0])
    finally:
        restore_env()
        reset_config()

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED", checks[0], len(failures)),
          file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


#: THE CALLABLE SURFACE, quoted verbatim from ticket #355 — the six signatures codebean's
#: `lower_node` (#183) produced from the ORIGINAL's AST, in the ticket's own order. Acceptance
#: item (b) is that this rewrite "presents the callable surface above, so existing callers keep
#: working", and `_lower_surface` lowers THIS file the same way to prove it.
SURFACE = [
    "fake_jazz(tmp_path, monkeypatch)",
    "mod(fake_jazz)",
    "test_load_build_reads_version(mod)",
    "test_load_build_missing_returns_empty(tmp_path, monkeypatch)",
    "test_notes_python_fallback_when_env_missing(mod)",
    "test_notes_python_uses_versioned_env(tmp_path, monkeypatch)",
]


def _lower_surface(path):
    """Lower every TOP-LEVEL function in `path` to the ticket's signature form.

    Mirrors codebean's `lower_node` (#183) closely enough to be compared against the ticket's
    own output: `name(params) -> returns`, each parameter as `name: annotation=default` with
    annotations and defaults unparsed straight from the AST, no ` -> ` at all when the function
    has no return annotation, and an `async ` prefix for a coroutine.

    Reads the SOURCE rather than the live objects on purpose: under real pytest, `@pytest.fixture`
    may replace `fake_jazz` and `mod` with wrapper objects whose `inspect.signature` is pytest's
    business rather than this module's. The ticket's surface is a claim about the module as
    written, so it is checked against the module as written — and that answer is the same with
    or without pytest installed.

    Needs `ast.unparse`, i.e. Python 3.9+, while `pyproject.toml` says `requires-python = ">=3.8"`
    (the generator's value, shared with this package's other units, and not this unit's to move).
    The gap is confined to this function and to `install_check`: importing this module and running
    its four TESTS uses nothing newer than 3.8, so the unit itself honors that floor and only the
    two self-verification commands need 3.9. Stated rather than papered over.
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


# ─────────────────────────────── the install check ───────────────────────────────


def install_check(stream=None):
    """Check what can be checked of ticket #355's acceptance item (c) WITHOUT running pip.

    Item (c) is that `pip install -e .` installs clean from this package's own pyproject.toml.
    That install CANNOT be run on the interpreter this unit was built on: setuptools is not
    importable and no package index is reachable, so the PEP 517 build backend pyproject.toml
    names cannot be fetched. Rather than claim an install that did not happen, this checks
    every property of the package that is checkable without one, and says plainly what is left.

    Returns the number of failures.
    """
    out = stream or sys.stdout
    failures = []

    def check(ok, label):
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    root = Path(__file__).resolve().parents[2]
    print("package root: %s" % root, file=out)

    try:
        import tomllib
    except ImportError:  # pragma: no cover — tomllib is stdlib from 3.11
        print("  SKIP  tomllib is unavailable, so pyproject.toml cannot be parsed here",
              file=out)
        return 0

    pyproject_path = root / "pyproject.toml"
    check(pyproject_path.is_file(), "pyproject.toml exists at the package root")
    if not pyproject_path.is_file():
        return len(failures)

    try:
        with open(pyproject_path, "rb") as handle:
            pyproject = tomllib.load(handle)
        check(True, "pyproject.toml parses as TOML")
    except Exception as exc:  # noqa: BLE001
        check(False, "pyproject.toml parses as TOML (%s: %s)" % (type(exc).__name__, exc))
        return len(failures)

    project = pyproject.get("project", {})
    check(bool(project.get("name")), "[project] declares a name (%r)" % project.get("name"))
    check(bool(project.get("version")), "[project] declares a version (%r)"
          % project.get("version"))
    check(pyproject.get("build-system", {}).get("build-backend") is not None,
          "[build-system] names a build backend (%r)"
          % pyproject.get("build-system", {}).get("build-backend"))
    check(project.get("dependencies") == [],
          "[project] requires no runtime dependencies, so `pip install -e .` needs no index "
          "beyond the build backend (got %r)" % (project.get("dependencies"),))

    packages = pyproject.get("tool", {}).get("setuptools", {}).get("packages", [])
    package_dir = pyproject.get("tool", {}).get("setuptools", {}).get("package-dir", {})
    check("coupler" in packages and "coupler.tests" in packages,
          "[tool.setuptools] declares both `coupler` and `coupler.tests`, so THIS module is "
          "installed (declares: %s)" % (packages,))
    for package in packages:
        directory = root / package_dir.get(package, package.replace(".", os.sep))
        check(directory.is_dir(), "declared package %r has a directory (%s)"
              % (package, directory))
        if package_dir.get(package) != ".":
            check((directory / "__init__.py").is_file(),
                  "declared package %r has an __init__.py, so setuptools installs it" % package)

    scripts = project.get("scripts", {})
    check("forge2-coupler-test-build" in scripts,
          "[project.scripts] declares this unit's console script (declares: %s)"
          % (sorted(scripts),))
    check(scripts.get("forge2-coupler-tool") == "code__code_invalid__coupler.coupler_tool:main",
          "...and the sibling unit's console script is still there, not clobbered (#410's "
          "additivity: got %r)" % scripts.get("forge2-coupler-tool"))

    for name, target in sorted(scripts.items()):
        module_name, _, attribute = target.partition(":")
        relative = module_name.replace(".", os.sep)
        source = package_dir.get(module_name.split(".")[0])
        path = ((root / (module_name.split(".", 1)[1].replace(".", os.sep) + ".py"))
                if source == "." and "." in module_name else root / (relative + ".py"))
        check(path.is_file(), "console script %r targets %s, whose file exists (%s)"
              % (name, target, path))
        if path.is_file():
            with open(path, "r", encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            check(any(isinstance(n, ast.FunctionDef) and n.name == attribute
                      for n in tree.body),
                  "...and that file defines a top-level %s()" % attribute)

    extras = project.get("optional-dependencies", {})
    check("pytest" in " ".join(extras.get("test", [])),
          "[project.optional-dependencies] puts pytest in the `test` extra, so the plain "
          "install needs no index for it (test extra: %s)" % (extras.get("test"),))

    # The END STATE an editable install produces, proven rather than printed as homework: a
    # FRESH interpreter, whose working directory is an empty temp dir unrelated to this package
    # and unrelated to the checkout, with the package root as the only thing added to sys.path,
    # must import this module and run its whole selftest green. That is what `pip install -e .`
    # buys — the package importable by name from anywhere — and it is checkable without pip.
    # The subprocess inherits no state from this one, so nothing already imported here can
    # flatter the result.
    probe = ("import sys; sys.path.insert(0, %r); "
             "import coupler.tests.test_build as t; "
             "import io; sys.exit(t.selftest(io.StringIO()))" % str(root))
    with tempfile.TemporaryDirectory() as elsewhere:
        completed = subprocess.run([sys.executable, "-c", probe], cwd=elsewhere,
                                   capture_output=True, text=True)
    check(completed.returncode == 0,
          "a FRESH interpreter, run from an unrelated working directory with only the package "
          "root on sys.path, imports coupler.tests.test_build and passes its whole selftest — "
          "the end state an editable install produces (exit %d%s)"
          % (completed.returncode,
             "" if completed.returncode == 0 else "; stderr: %s" % completed.stderr.strip()[-300:]))

    print("\n  This command is HERMETIC: it runs no pip and reaches no network, so it works on a\n"
          "  bare interpreter and in an offline checkout. Nothing above is a claim that pip ran.\n"
          "  `pip install -e .` IS runnable and has been run for this package — not from here,\n"
          "  because a shipped check that needs a network is a check that fails on a bad day.\n"
          "  Run it yourself, in a virtualenv (a direct pip install on a system interpreter is\n"
          "  refused by PEP 668, which is not this package's doing):\n"
          "      cd %s\n"
          "      python3 -m venv /tmp/v && /tmp/v/bin/pip install -e '.[test]'\n"
          "      /tmp/v/bin/forge2-coupler-test-build selftest\n"
          "      /tmp/v/bin/pytest coupler/tests/test_build.py -v\n"
          "  The last command needs a coupler/server.py to test; until that unit lands, the four\n"
          "  tests fail with ModuleNotFoundError — which is exactly what the ORIGINAL does today.\n"
          % (str(root),), file=out)

    print("%s — %d failure(s)" % ("INSTALL-CHECK PASSED" if not failures else
                                  "INSTALL-CHECK FAILED", len(failures)), file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


# ─────────────────────────────── bug reports ───────────────────────────────


def bug_report(exc, formatted, invocation):
    """Append one timestamped JSON line describing an UNEXPECTED exception; return its path.

    This is `note-for-claude`'s rule — "all tools need to pass a bug-report automatically
    (timestamped if an exception is thrown)". It reports a DEFECT IN THIS TOOL and nothing
    else: a `ConfigError` is designed behavior and never lands here, and neither does a test
    FAILING, which is a verdict this module exists to reach.

    Returns None when no report could be filed (no config, or no `bug_reports` key, or the
    sink cannot be written) — a tool that crashed while reporting a crash would replace the
    real diagnosis with its own.
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
                "ticket": 355,
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

    Derived from the interpreter and `sys.argv` rather than written as a fixed string. A
    report is a record, and a record that states an invocation the operator did not type is
    worse than no record: it sends the next reader to reproduce something that never ran.
    `python3 -m pkg.mod` and `python3 path/to/mod.py` fail in different ways, and the sink has
    to be able to tell them apart.
    """
    if __name__ == "__main__" and __spec__ is not None:
        launcher = "-m " + __spec__.name          # python3 -m coupler.tests.test_build ...
    else:
        # Either this file was run by path (no spec), or main() was called through the
        # installed console script (this module is not __main__) — in both, argv[0] is what
        # the operator actually typed.
        launcher = sys.argv[0] or __file__
    return " ".join([os.path.basename(sys.executable), launcher] + argv)


def _build_parser():
    return _add_commands(argparse.ArgumentParser(
        prog="forge2-coupler-test-build",
        description="forge2 rewrite of the forge unit "
                    "code__code-invalid__coupler:coupler/tests/test_build.py (ticket #355). "
                    "Config-driven: the tests throw if they cannot see their config object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="config is read from the file named by $%s, else from the %s section of the "
               "nearest %s found by walking up from this module. This package ships one, so "
               "these commands work from a clean checkout. Run `emit-config` for a template."
               % (CONFIG_ENV, " -> ".join(UNIT_PATH), REGISTRY_NAME)))


def _add_commands(parser):
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="the differential against the original, the mutants, the "
                                    "config gate and the surface")
    sub.add_parser("install-check", help="check what can be checked of the package without pip")
    sub.add_parser("show-pytest", help="report whether real pytest is in use")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and its source")
    return parser


def main(argv=None):
    """Entry point for the `forge2-coupler-test-build` console script. Returns an exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your registry.json, or save a file containing it\n"
                  "# and point $%s at that file. Until it is installed these tests throw\n"
                  "# ConfigError — they will not guess a default."
                  % (" -> ".join(UNIT_PATH), CONFIG_ENV), file=sys.stderr)
            return 0

        if args.command == "show-pytest":
            print(json.dumps({
                "pytest": getattr(pytest, "__version__", None) if HAVE_PYTEST else None,
                "in_use": "real pytest" if HAVE_PYTEST else "built-in stand-ins",
                "note": "the stand-ins are inert whenever real pytest is importable; "
                        "`pip install -e \".[test]\"` supplies pytest",
            }, indent=2))
            return 0

        if args.command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(), "base": active_base(),
                              "config": active_config()}, indent=2))
            return 0

        if args.command == "selftest":
            return 0 if selftest() == 0 else 1

        if args.command == "install-check":
            return 0 if install_check() == 0 else 1

    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except UsageError as exc:
        # Also designed behavior: the tool is fine, the invocation is not. Same treatment —
        # explain it and exit 2, rather than blame this module for how it was started.
        print("usage error: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        path = bug_report(exc, traceback.format_exc(), _invocation(argv))
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise

    return 0


if __name__ == "__main__":
    sys.exit(main())
