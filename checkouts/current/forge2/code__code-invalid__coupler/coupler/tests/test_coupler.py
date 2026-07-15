#!/usr/bin/env python3
"""forge2 / code__code-invalid__coupler / coupler.tests.test_coupler — a behavior-preserving
rewrite of the forge unit `code__code-invalid__coupler:coupler/tests/test_coupler.py`
(module key forge-rw:dc95cfcf8d8037c8), filed under ticket #399 against the FORGE-wide
refactor standard #200.

WHAT THIS IS
------------
The original forge unit was 1922 bytes of pytest: one fixture that built a fake jazz tree in
a temporary directory, and three tests that pointed a coupler at that tree and checked it
resolved its build and its notes interpreter "without live jazz services". This file is an
entirely new implementation of that unit. It keeps the original's observable behavior — the
same three verdicts about the same subject — and its callable surface, and it adds the three
things #200 requires that the original lacked: it is a proper installable package, it is
driven by a configuration object, and it refuses to run when it cannot see that
configuration.

TERMS USED HERE, AT FIRST USE
-----------------------------
subject
    The module under test — the one whose functions these tests call and assert about. A
    test module has no behavior of its own without one. The original named its subject in an
    `import` statement (`import coupler.__main__ as m`); this rewrite names it in the config
    object instead. See THE SUBJECT below.
jazz tree
    A directory laid out the way a jazz install is: a `conf/env/build.json` build manifest,
    and an `envs/<name>/bin/python` interpreter per environment. The fixture below builds a
    fake one in a temporary directory, which is what "without live jazz services" means.
build manifest
    `conf/env/build.json` inside a jazz tree — the JSON object naming the version, the tag,
    the build number, and the per-environment names.
versioned env / base env
    The notes environment for a specific build (`envs/notes-jazz-1.0.42`), versus the
    fallback environment shared by every build (`envs/base`). The middle test exists to pin
    what happens when the versioned one is absent.
registry
    The JSON configuration registry described in this repository's `note-for-claude`: one
    `.json` file holding the configuration for every tool in a set of packaging.
    `note-for-claude` states the contract this module obeys — "if a tool cannot see the
    registry it will throw an exeption" [sic]. This package ships its own `registry.json` at
    the root of the folder that holds it; see CONFIGURATION.
config object
    The chunk of that registry belonging to this unit — the
    `forge2 -> code__code-invalid__coupler -> coupler -> tests -> test_coupler` section. It
    is what drives this module. `emit-config` prints a template of it.
fixture / monkeypatch / tmp_path
    pytest vocabulary. A FIXTURE is a function pytest calls to build a test's input; a test
    that declares a parameter named after a fixture receives that fixture's RETURN VALUE, not
    the function. `tmp_path` and `monkeypatch` are two fixtures pytest itself provides: a
    fresh temporary directory as a `pathlib.Path`, and an object whose `setenv` sets an
    environment variable and undoes it when the test ends. This module runs under pytest
    unchanged, and also without it; see RUNNING IT.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    fake_jazz(tmp_path)
    test_load_build(fake_jazz, monkeypatch)
    test_notes_python_fallback(fake_jazz, monkeypatch)
    test_build_json_missing(tmp_path, monkeypatch)

`fake_jazz` is the fixture; the other three are the tests, and each takes the fixture values
pytest hands it. Note the asymmetry, which is load-bearing and preserved: the first two tests
take `fake_jazz`, so they see a tree WITH a build manifest, while the third takes `tmp_path`
directly, so it sees an EMPTY tree. That is how the third test stages "no build.json".

WHAT EACH TEST ASSERTS (read off the original, which is the oracle)
------------------------------------------------------------------
Every test first points the subject at its tree by setting the jazz-root variable, sets the
development-root variable to a sentinel that does not exist, and then RELOADS the subject.
The reload is not decoration: the subject reads the environment when its body runs, so a
subject imported before the variables were set would still be looking at the old tree. The
`selftest` below proves the reload is load-bearing rather than assuming it.

    test_load_build
        The manifest round-trips. Exactly two values are checked — the version and the notes
        env name. The tag and the build number in the manifest are NOT checked, and a rewrite
        that "improved" the test by checking them too would reject subjects the original
        accepts. A manifest missing a checked key raises KeyError here rather than failing an
        assertion; that is the original's behavior, and it is a failed test either way.

    test_notes_python_fallback
        With the versioned env absent, the subject falls back and returns a path that (1)
        looks like a base python — it contains "base" OR ends with "python" — and (2) exists.
        The OR is the original's, and it is deliberately loose; both arms are preserved.

    test_build_json_missing
        With no manifest at all, the subject returns an empty dict rather than raising or
        inventing a build, and still resolves an interpreter path that exists. Note that only
        EXISTENCE is checked here — not the "base"/"python" shape the middle test checks.

THE SUBJECT (#200 requirement 4, applied to the one thing this unit hardcoded)
-----------------------------------------------------------------------------
The original hardcoded its subject as `import coupler.__main__ as m`. That module is not part
of this package: it is a different forge unit with its own rewrite ticket (#403, filed
against the `coupler` repo), and #399 covers this test module and nothing else. So the
subject is named by the config object's `subject.module` key, and this package ships
`coupler/tests/reference_main.py` — a documented stand-in that implements the contract these
tests pin — as the subject the shipped registry names. That is why the suite is executable
from a clean checkout instead of skipping.

Point `subject.module` at `coupler.__main__` once that module is importable and these same
three tests run against it unchanged. Naming the subject in config rather than in an `import`
is the whole point: it is what makes this suite reusable against the real unit without
editing a line of it.

THE ONE DELIBERATE DIVERGENCE, AND WHY
--------------------------------------
The original's `fake_jazz` created ONLY the build manifest. But `test_notes_python_fallback`
asserts that the base python it gets back EXISTS — and the original's fixture never created
one. So the original passes only where the machine already happened to provide a path
matching its check: a real jazz `base` env, or an interpreter whose path ends in `python`
(the shape of a virtualenv's `bin/python`, which is what `sys.executable` is under a venv).
That is an undeclared dependency on machine state, and it is exactly what #200's
control-config requirement exists to remove.

So the fake jazz tree is DECLARED BY THE CONFIG, and the shipped config declares the base env
the assertion presumes: `fake_jazz` writes the manifest, and also links `envs/base/bin/python`
to the interpreter running the tests. The verdicts are preserved — on a machine that
satisfies the original, both fixtures lead all three tests to the same PASS — and they stop
depending on a fact nobody wrote down. Set `fake_jazz.base_env_python_path` to null to get the
original's exact tree back, and with it the original's exact machine dependence. `selftest`
check [6] demonstrates that dependence rather than asserting it: it runs the original's tree
shape and requires the verdict to be whatever THIS interpreter's path implies.

CONFIGURATION
-------------
The config object is resolved on first use, from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. That file holds the unit
     config object itself — exactly what `emit-config` prints.
  2. otherwise, the `forge2 -> code__code-invalid__coupler -> coupler -> tests ->
     test_coupler` section of the nearest `registry.json` found by walking UP from THIS
     FILE's directory.

If NEITHER answers, every fixture and test here raises `ConfigError` and asserts nothing. It
never guesses a default — that is `note-for-claude`'s rule and this ticket's acceptance item
(d). A config object that is found but missing a key an operation needs is also a
`ConfigError`, naming the key.

This package ships `registry.json` at the root of the folder that holds it, so source 2
answers and the suite runs from a clean checkout with no setup. That shipped registry is the
config object this unit runs on; it is not a fallback baked into the code. `selftest` proves
the gate directly, without deleting anything, by pointing `FORGE2_CONFIG` at a file that does
not exist.

An INSTALLED copy resolves the registry the same way, by walking up from the installed file,
which is why `pip install -e .` (this ticket's acceptance item (c)) is the supported install:
the editable install leaves this file in the checkout, with the registry above it. After a
NON-editable install there is no registry above `site-packages/coupler/tests/`, so point
`$FORGE2_CONFIG` at your config object — or the suite throws, which is the gate working.

`configure(config)` and `using_config(config)` inject a config object directly, in-process,
for callers that hold their configuration in memory rather than on disk.

RUNNING IT
----------
Under pytest, unchanged from the original — this is the invocation the original was written
for, and it needs pytest installed:

    pytest coupler/tests/test_coupler.py

Without pytest, this module runs itself. Every command below is executable as written from
the root of the folder that holds this package:

    python3 -m coupler.tests.test_coupler run          # run the three tests, print verdicts
    python3 -m coupler.tests.test_coupler selftest     # prove the exemplars and the gate
    python3 -m coupler.tests.test_coupler emit-config  # print a config-object template
    python3 -m coupler.tests.test_coupler show-config  # print the resolved config + source

`run` builds the same fixtures pytest would and calls the same three test functions, so its
verdicts are the suite's verdicts. It exits 0 when every test passes, 1 when one fails, and 2
on a config error. `selftest` needs no config object of its own — it builds them in memory and
generates its own stand-in subjects — so it passes even where nothing is installed. Its last
check READS the shipped registry, to cross-check that registry against what `emit-config`
prints and against the stand-in subject it names, and reports n/a when there is no registry to
read. Nothing in `selftest` writes to the registry or anywhere else outside its own temporary
directory.

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, and the package is committed in
full beside it — `pyproject.toml`, `coupler/__init__.py`, `coupler/tests/__init__.py`,
`coupler/tests/reference_main.py`, `registry.json`. From the root of that folder:

    pip install -e .
    forge2-coupler-test-coupler run

`pyproject.toml` declares the `forge2-coupler-test-coupler` console script pointing at
`main()` below, and declares pytest as the optional `test` extra (`pip install -e .[test]`)
because the suite runs with or without it.

SIDE EFFECTS
------------
`run` creates one temporary directory per test — the fake jazz tree, exactly what pytest's
`tmp_path` fixture would create — and removes each one before it returns. `selftest`
additionally writes its generated stand-in subjects into one temporary directory and removes
it. Nothing outside those temporary directories is written by either, and `emit-config` and
`show-config` write nothing at all.

Two process-level effects are the original's and are preserved. Running a test leaves the
subject module imported and reloaded, holding the environment the test set; and the tests set
environment variables, which `monkeypatch` (pytest's, or the stand-in below) restores when
each test ends.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception
is thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path if it
hits an UNEXPECTED exception — that is, a defect in this tool. A `ConfigError` is designed
behavior, not a bug, and neither is a failing test: both file no report and print no
traceback, and exit with a self-explaining line.
"""

import argparse
import contextlib
import importlib
import inspect
import json
import os
import shutil
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

__all__ = [
    "fake_jazz",
    "test_load_build",
    "test_notes_python_fallback",
    "test_build_json_missing",
    "ConfigError",
    "load_config",
    "configure",
    "using_config",
    "reset_config",
    "run_tests",
    "selftest",
    "main",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS
#: in the config document, not a configurable setting — a config-driven tool has to know
#: which section is its own.
UNIT_PATH = ("forge2", "code__code-invalid__coupler", "coupler", "tests", "test_coupler")

#: The same, for the stand-in subject this package ships. `emit-config --unit reference_main`
#: prints its template, and `selftest` check [7] cross-checks the two sections agree.
REFERENCE_UNIT_PATH = ("forge2", "code__code-invalid__coupler", "coupler", "tests",
                       "reference_main")

#: The module the stand-in subject lives in, used by `emit-config --unit reference_main`.
REFERENCE_MODULE = "coupler.tests.reference_main"

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code-invalid__coupler/coupler.tests.test_coupler"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default. It is NOT a test failure —
    a test that cannot see its configuration has not made a judgement about anything — so
    `run_tests` lets it propagate rather than counting it as a FAIL.
    """


# ─────────────────────────── running with or without pytest ───────────────────────────
#
# The original did a bare `import pytest`, so it could not even be imported where pytest is
# absent, and had no behavior there to preserve. This rewrite keeps the original's behavior
# exactly where pytest exists — `fake_jazz` is a real fixture and pytest drives the suite —
# and additionally runs itself where pytest does not, through `run_tests` below. That is what
# makes acceptance item (a)'s "paste the runs as evidence" reachable on a bare interpreter.

try:
    import pytest as _pytest
except ImportError:  # pragma: no cover — depends on the installed environment, not on input
    _pytest = None


def _fixture(function):
    """`pytest.fixture` when pytest is importable, identity otherwise.

    Under pytest this makes `fake_jazz` a fixture, exactly as the original's `@pytest.fixture`
    did, so a test declaring a `fake_jazz` parameter receives the fixture's return value.
    Without pytest it leaves `fake_jazz` an ordinary function, which is what lets `run_tests`
    call it.
    """
    return function if _pytest is None else _pytest.fixture(function)


class _MonkeyPatch:
    """The slice of pytest's `monkeypatch` fixture this suite uses, for running without it.

    `setenv` sets an environment variable and remembers what was there; `undo` puts every one
    of them back. pytest's own fixture does the undo automatically when a test ends, so
    `run_tests` calls `undo` in a `finally` to match.
    """

    def __init__(self):
        self._saved = []

    def setenv(self, name, value):
        """Set environment variable `name` to `str(value)` until `undo`."""
        self._saved.append((name, os.environ.get(name)))
        os.environ[name] = str(value)

    def undo(self):
        """Restore every variable `setenv` touched, in reverse order."""
        while self._saved:
            name, previous = self._saved.pop()
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous


# ─────────────────────────────── the config object ───────────────────────────────

_ACTIVE = None      # config injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution, so a test re-reads no files


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


def load_config(start=None, unit_path=None):
    """Resolve a unit's config object from disk, ignoring any injected config.

    Returns a `(config, base, source)` triple: the config object, the directory that relative
    paths inside it resolve against, and a human-readable description of where it came from.
    `start` overrides the directory the registry walk-up begins at; `unit_path` overrides
    which section is read, and defaults to this unit's own.

    Raises:
        ConfigError: if no config object can be found, naming both sources that were tried.
    """
    unit_path = tuple(unit_path or UNIT_PATH)
    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        if not os.path.isfile(env_path):
            raise ConfigError("%s is set to %r, but no such file exists"
                              % (CONFIG_ENV, env_path))
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
    for depth, key in enumerate(unit_path):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r "
                "section. Run `emit-config` and add the printed object at %s."
                % (registry_path, ".".join(unit_path), ".".join(unit_path[: depth + 1]),
                   " -> ".join(unit_path)))
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError("the registry section %s at %s must be a JSON object, not %s"
                          % (".".join(unit_path), registry_path, type(node).__name__))

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


def _need(config, key, wanted, described_as, where=UNIT):
    """Return `config[key]`, or raise ConfigError naming the key and the shape wanted.

    A config object that is found but incomplete is a ConfigError like an absent one: this
    unit states what it needs and refuses, rather than filling the hole with a guess.
    """
    if not isinstance(config, dict) or key not in config:
        raise ConfigError("config object for %s is missing the required key %r (%s). Run "
                          "`emit-config` for a template." % (where, key, described_as))
    value = config[key]
    if not isinstance(value, wanted):
        raise ConfigError("config key %r for %s must be %s, not %s"
                          % (key, where, described_as, type(value).__name__))
    return value


def _section(name, described_as):
    """Return one top-level section of the config object in force."""
    return _need(active_config(), name, dict, described_as)


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do every test throws. It is a fresh object on every
    call, so a caller may edit it freely — `selftest` relies on that.
    """
    return {
        "subject": {
            "module": REFERENCE_MODULE,
            "load_build": "_load_build",
            "notes_python": "_notes_python",
        },
        "env": {
            "root_var": "JAZZ_ROOT",
            "dev_var": "JAZZ_DEV",
            "dev_value": "/nonexistent",
        },
        "fake_jazz": {
            "build_json_path": ["conf", "env", "build.json"],
            "build_json": {
                "version": "1.0.42",
                "tag": "v1.0.42",
                "build": 42,
                "envs": {
                    "notes": "notes-jazz-1.0.42",
                },
            },
            "base_env_python_path": ["envs", "base", "bin", "python"],
            "base_env_python_target": "interpreter",
        },
        "expect": {
            "build_paths": [["version"], ["envs", "notes"]],
            "notes_python_substrings": ["base"],
            "notes_python_suffixes": ["python"],
            "missing_build": {},
        },
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────────────── the subject ───────────────────────────────

def _reload_subject():
    """Import the configured subject and reload it, and return the module.

    This is the original's `import coupler.__main__ as m; importlib.reload(m)`, with the
    module NAMED BY THE CONFIG instead of by an import statement. The reload is what makes a
    test's `setenv` visible to a subject that reads the environment when its body runs; see
    WHAT EACH TEST ASSERTS in the module docstring.

    Raises:
        ConfigError: if the config object cannot be resolved, lacks `subject.module`, or
            names a module that cannot be imported. An unimportable subject is a
            configuration fault, not a verdict about the subject's behavior.
    """
    subject = _section("subject", "an object naming the module under test and its functions")
    name = _need(subject, "module", str,
                 "a string naming the module under test, e.g. \"coupler.__main__\"")
    try:
        module = importlib.import_module(name)
    except ImportError as exc:
        raise ConfigError(
            "config key 'subject.module' for %s names %r, which cannot be imported: %s. This "
            "package ships %r as a stand-in subject; the forge unit `coupler.__main__` is a "
            "different unit (ticket #403) and is not installed here."
            % (UNIT, name, exc, REFERENCE_MODULE)) from exc
    return importlib.reload(module)


def _subject_call(module, key):
    """Return the subject function the config names under `subject.<key>`."""
    subject = _section("subject", "an object naming the module under test and its functions")
    attribute = _need(subject, key, str,
                      "a string naming the subject's %s function, e.g. \"_%s\"" % (key, key))
    try:
        return getattr(module, attribute)
    except AttributeError as exc:
        raise ConfigError("config key 'subject.%s' for %s names %r, but the subject module %r "
                          "has no such attribute"
                          % (key, UNIT, attribute, module.__name__)) from exc


def _point_at(monkeypatch, root):
    """Point the subject at the jazz tree `root`, exactly as every original test opened.

    Sets the jazz-root variable to `root` and the development-root variable to the config's
    sentinel — the original's `/nonexistent`, whose whole job is to name a tree that is not
    there, so the subject cannot resolve anything from a developer's own checkout.
    """
    env = _section("env", "an object naming the environment variables the subject reads")
    monkeypatch.setenv(_need(env, "root_var", str,
                             "a string naming the jazz-root env var, e.g. \"JAZZ_ROOT\""),
                       str(root))
    monkeypatch.setenv(_need(env, "dev_var", str,
                             "a string naming the development-root env var, e.g. \"JAZZ_DEV\""),
                       _need(env, "dev_value", str,
                             "a string naming a tree that does not exist, e.g. \"/nonexistent\""))


# ─────────────────────────────── the fixture ───────────────────────────────

def _build_fake_jazz(tmp_path):
    """Build the fake jazz tree the config declares under `tmp_path`, and return `tmp_path`.

    This is the fixture's body, kept as a plain function so that `run_tests` can call it even
    when pytest has turned `fake_jazz` into a fixture object that refuses a direct call.

    It writes the build manifest, and — unless `fake_jazz.base_env_python_path` is null — a
    base env whose interpreter is a symlink to `base_env_python_target`. See THE ONE
    DELIBERATE DIVERGENCE in the module docstring for why the base env is here and how to
    turn it off.

    Raises:
        ConfigError: if the config object cannot be resolved or lacks a key.
    """
    tmp_path = Path(tmp_path)
    fake = _section("fake_jazz", "an object declaring the fake jazz tree to build")

    manifest_path = _need(fake, "build_json_path", list,
                          "a list of path segments, e.g. [\"conf\", \"env\", \"build.json\"]")
    build = _need(fake, "build_json", dict,
                  "the JSON object to write as the build manifest")
    manifest = tmp_path.joinpath(*[str(part) for part in manifest_path])
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(build), encoding="utf-8")

    if "base_env_python_path" not in fake:
        raise ConfigError(
            "config object for %s is missing the required key 'fake_jazz.base_env_python_path' "
            "(a list of path segments to the base env's interpreter, e.g. [\"envs\", \"base\", "
            "\"bin\", \"python\"], or null to build the tree the ORIGINAL fixture built — see "
            "this module's docstring, THE ONE DELIBERATE DIVERGENCE). Run `emit-config` for a "
            "template." % UNIT)
    base_path = fake["base_env_python_path"]
    if base_path is not None:
        if not isinstance(base_path, list):
            raise ConfigError("config key 'fake_jazz.base_env_python_path' for %s must be a "
                              "list of path segments or null, not %s"
                              % (UNIT, type(base_path).__name__))
        target = _need(fake, "base_env_python_target", str,
                       "\"interpreter\" for the interpreter running the tests, or an absolute "
                       "path to one")
        if target == "interpreter":
            target = sys.executable
        elif not os.path.isabs(target):
            raise ConfigError("config key 'fake_jazz.base_env_python_target' for %s must be "
                              "\"interpreter\" or an ABSOLUTE path, not %r" % (UNIT, target))
        python = tmp_path.joinpath(*[str(part) for part in base_path])
        python.parent.mkdir(parents=True, exist_ok=True)
        try:
            python.symlink_to(target)
        except OSError:
            # A filesystem or platform that refuses symlinks. The tests only ask whether this
            # path exists and what it looks like — they never execute it — so a plain file
            # keeps every verdict identical where a link cannot be made.
            python.write_text("# stand-in for the base env interpreter at %s\n" % target,
                              encoding="utf-8")
    return tmp_path


@_fixture
def fake_jazz(tmp_path):
    """Build a fake jazz tree under `tmp_path` and return it, for use as JAZZ_ROOT.

    The tree is declared by the config object's `fake_jazz` section: a build manifest holding
    the version, tag, build number and env names, plus the base env the fallback test needs.
    Returns the `tmp_path` it built under, so a test that declares a `fake_jazz` parameter
    receives the root of the tree.
    """
    return _build_fake_jazz(tmp_path)


# ─────────────────────────────── the tests ───────────────────────────────

def _dig(node, path):
    """Index `node` through `path`, the way the original indexed its build dict.

    Uses plain `[]`, so a key the subject did not return raises KeyError from here just as it
    did from the original's `build["version"]`.
    """
    for key in path:
        node = node[key]
    return node


def _expected_build_paths():
    """Return `[(path, expected_value), ...]` — what `test_load_build` checks and wants.

    The wanted values are read out of the very manifest `fake_jazz` writes, so the fixture and
    the assertion cannot drift apart. The original repeated the literals in both places; this
    is the same two checks, stated once.
    """
    fake = _section("fake_jazz", "an object declaring the fake jazz tree to build")
    build = _need(fake, "build_json", dict, "the JSON object to write as the build manifest")
    expect = _section("expect", "an object declaring what the tests check")
    paths = _need(expect, "build_paths", list,
                  "a list of key paths into the manifest, e.g. [[\"version\"], "
                  "[\"envs\", \"notes\"]]")
    wanted = []
    for path in paths:
        if not isinstance(path, list) or not path:
            raise ConfigError("config key 'expect.build_paths' for %s must hold non-empty "
                              "lists of keys; got %r" % (UNIT, path))
        node = build
        for key in path:
            if not isinstance(node, dict) or key not in node:
                raise ConfigError(
                    "config for %s: 'expect.build_paths' asks to check %s, but "
                    "'fake_jazz.build_json' has no value there, so there is nothing to expect"
                    % (UNIT, "".join("[%r]" % k for k in path)))
            node = node[key]
        wanted.append((list(path), node))
    return wanted


def test_load_build(fake_jazz, monkeypatch):
    """The subject reads the build manifest out of the jazz tree it is pointed at.

    Checks exactly the key paths the config's `expect.build_paths` names — the version and the
    notes env name — against the values `fake_jazz` wrote. The tag and build number in the
    manifest are deliberately not checked; see WHAT EACH TEST ASSERTS in the module docstring.
    """
    _point_at(monkeypatch, fake_jazz)
    wanted = _expected_build_paths()
    module = _reload_subject()
    build = _subject_call(module, "load_build")()
    for path, expected in wanted:
        got = _dig(build, path)
        assert got == expected, ("build%s is %r, expected %r"
                                 % ("".join("[%r]" % k for k in path), got, expected))


def test_notes_python_fallback(fake_jazz, monkeypatch):
    """Falls back to the base python when the versioned env doesn't exist.

    The tree `fake_jazz` builds has no `envs/<notes env>`, so the subject must fall back. The
    path it returns must look like a base python — contain one of the config's
    `expect.notes_python_substrings` OR end with one of its `expect.notes_python_suffixes` —
    and must exist. The OR is the original's and both arms are preserved.
    """
    _point_at(monkeypatch, fake_jazz)
    expect = _section("expect", "an object declaring what the tests check")
    substrings = _need(expect, "notes_python_substrings", list,
                       "a list of substrings a base python's path may contain, e.g. [\"base\"]")
    suffixes = _need(expect, "notes_python_suffixes", list,
                     "a list of suffixes a base python's path may end with, e.g. [\"python\"]")

    module = _reload_subject()
    python = _subject_call(module, "notes_python")()

    # versioned env doesn't exist → falls back to base
    assert (any(s in python for s in substrings)
            or any(python.endswith(s) for s in suffixes)), (
        "%r does not look like a base python: it contains none of %r and ends with none of %r"
        % (python, substrings, suffixes))
    assert Path(python).exists(), "%r does not exist" % python


def test_build_json_missing(tmp_path, monkeypatch):
    """No build.json → returns empty dict, falls back gracefully.

    `tmp_path` here is a bare temporary directory, NOT the `fake_jazz` tree: that is how this
    test stages a jazz root with no manifest in it. The subject must return the config's
    `expect.missing_build` (an empty dict) rather than raising or inventing a build, and must
    still resolve an interpreter path that exists. Only existence is checked — not the
    base-python shape the fallback test checks.
    """
    _point_at(monkeypatch, tmp_path)
    expect = _section("expect", "an object declaring what the tests check")
    if "missing_build" not in expect:
        raise ConfigError("config object for %s is missing the required key "
                          "'expect.missing_build' (what the subject must return when there is "
                          "no manifest, e.g. {}). Run `emit-config` for a template." % UNIT)
    wanted = expect["missing_build"]

    module = _reload_subject()
    build = _subject_call(module, "load_build")()
    assert build == wanted, "with no manifest the subject returned %r, expected %r" % (build,
                                                                                       wanted)
    python = _subject_call(module, "notes_python")()
    assert Path(python).exists(), "%r does not exist" % python


#: The three tests, in the original's order, each paired with whether it takes the `fake_jazz`
#: tree (True) or a bare `tmp_path` (False). `run_tests` reads this to build each test's input
#: the way pytest would.
TESTS = (
    ("test_load_build", test_load_build, True),
    ("test_notes_python_fallback", test_notes_python_fallback, True),
    ("test_build_json_missing", test_build_json_missing, False),
)


# ─────────────────────────────── running without pytest ───────────────────────────────

def run_tests(names=None):
    """Run the three tests against the configured subject and return `{name: (ok, detail)}`.

    Builds each test's input the way pytest would — a fresh temporary directory per test,
    grown into the fake jazz tree for the two tests that take `fake_jazz` — and restores every
    environment variable a test set before moving on. `names` limits which tests run.

    A test that raises anything is a FAIL with the exception in its detail, so one broken test
    cannot hide the ones behind it. A `ConfigError` is the exception: it means no test could
    judge anything, so it propagates rather than being reported as a verdict.

    Raises:
        ConfigError: if the config object cannot be resolved or is missing a key.
        RuntimeError: if run under `python -O`, which strips the `assert` statements these
            tests are made of and would make every one of them pass vacuously.
    """
    if not __debug__:
        raise RuntimeError(
            "refusing to run: this interpreter has assertions disabled (-O / PYTHONOPTIMIZE), "
            "which strips the `assert` statements these tests are made of, so every test would "
            "pass without checking anything. Re-run without -O.")
    results = {}
    for name, function, needs_tree in TESTS:
        if names and name not in names:
            continue
        with tempfile.TemporaryDirectory(prefix="forge2-t399-") as scratch:
            monkeypatch = _MonkeyPatch()
            try:
                argument = _build_fake_jazz(Path(scratch)) if needs_tree else Path(scratch)
                function(argument, monkeypatch)
                results[name] = (True, "")
            except ConfigError:
                raise
            except BaseException as exc:  # noqa: BLE001 — a runner must survive any verdict
                results[name] = (False, "%s: %s" % (type(exc).__name__, exc) if str(exc)
                                 else type(exc).__name__)
            finally:
                monkeypatch.undo()
    return results


def _print_results(results, out):
    for name, (ok, detail) in results.items():
        print("  %s  %s%s" % ("PASS" if ok else "FAIL", name,
                              "" if ok else "\n          %s" % detail), file=out)
    return sum(1 for ok, _ in results.values() if not ok)


# ─────────────────────────────── the selftest ───────────────────────────────
#
# Ticket #399 records that criteria_miner captured NO behavioral exemplars for this module —
# it mines only self-contained pure functions, and a test module is not one — and says so
# explicitly: "you must write the equivalence exemplars by hand from the original's behavior
# before rewriting, and they are what settles this ticket." EXEMPLARS below is that hand
# written table, and this selftest is the run of it.
#
# The exemplar for a TEST module is not an (input, output) pair; it is a (SUBJECT, VERDICT)
# pair. Read off the original's source: for a given subject, what does each of its three tests
# decide? Each row below states that, and pins one assertion of the original by breaking
# exactly one thing about the subject and requiring the matching test — and only that test —
# to turn red. A rewrite that dropped an assertion, or added one the original did not have,
# fails a row.

#: The stand-in subjects the selftest generates, and the verdict the ORIGINAL's three tests
#: reach for each, given the fake jazz tree the shipped config declares (manifest + base env).
#: `_SUBJECT_SOURCES` builds the module for each name.
EXEMPLARS = (
    ("conforming",
     {"test_load_build": True, "test_notes_python_fallback": True,
      "test_build_json_missing": True},
     "a subject that honours the whole contract: every test passes"),
    ("wrong_version",
     {"test_load_build": False, "test_notes_python_fallback": True,
      "test_build_json_missing": True},
     "the manifest's version comes back wrong — only test_load_build may notice"),
    ("wrong_notes_env",
     {"test_load_build": False, "test_notes_python_fallback": True,
      "test_build_json_missing": True},
     "the manifest's envs.notes comes back wrong — only test_load_build may notice"),
    ("no_version",
     {"test_load_build": False, "test_notes_python_fallback": True,
      "test_build_json_missing": True},
     "the manifest comes back without a version at all: the original raises KeyError from "
     "build[\"version\"] rather than failing an assert, and the test is red either way"),
    ("wrong_tag",
     {"test_load_build": True, "test_notes_python_fallback": True,
      "test_build_json_missing": True},
     "the manifest's tag and build number come back wrong and NO test may notice — the "
     "original checks the version and the notes env and nothing else. A rewrite that tightened "
     "the test would fail this row"),
    ("never_empty",
     {"test_load_build": True, "test_notes_python_fallback": True,
      "test_build_json_missing": False},
     "the subject invents a build when there is no manifest — only test_build_json_missing "
     "may notice"),
    ("missing_python",
     {"test_load_build": True, "test_notes_python_fallback": False,
      "test_build_json_missing": False},
     "the interpreter path looks like a base python but does not exist — both tests that "
     "check existence must notice"),
    ("unmarked_python",
     {"test_load_build": True, "test_notes_python_fallback": False,
      "test_build_json_missing": True},
     "the interpreter path exists but looks like no base python — only the fallback test "
     "checks the shape, so only it may notice"),
)

#: Common body of every generated stand-in subject: an honest reading of the contract the
#: original's three tests pin. `%(root_var)r` and friends are filled from the selftest's own
#: config object, so a stand-in can never disagree with the config driving the tests.
_SUBJECT_COMMON = '''\
"""A stand-in subject generated by test_coupler.py's selftest, in a temporary directory that
the selftest deletes when it is done. Not shipped and not installed."""
import json
import os
import sys
from pathlib import Path

_ENV = dict(os.environ)          # snapshot at import — the suite reloads this module to refresh it


def _tree_build():
    for var in (%(dev_var)r, %(root_var)r):
        root = _ENV.get(var)
        if not root:
            continue
        try:
            build = json.loads(Path(root, *%(manifest)r).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(build, dict):
            return build
    return {}


def _tree_python():
    build = _tree_build()
    envs = build.get("envs")
    versioned = envs.get("notes") if isinstance(envs, dict) else None
    for var in (%(dev_var)r, %(root_var)r):
        root = _ENV.get(var)
        if not root:
            continue
        for name in ([versioned, "base"] if versioned else ["base"]):
            candidate = Path(root, "envs", name, "bin", "python")
            if candidate.exists():
                return str(candidate)
    return sys.executable


_load_build = _tree_build
_notes_python = _tree_python
'''

#: Per-exemplar overrides appended to `_SUBJECT_COMMON`. Each breaks exactly one thing.
_SUBJECT_SOURCES = {
    "conforming": "",
    "wrong_version": '''
def _load_build():
    build = _tree_build()
    if "version" in build:
        build["version"] = "9.9.9"
    return build
''',
    "wrong_notes_env": '''
def _load_build():
    build = _tree_build()
    if isinstance(build.get("envs"), dict):
        build["envs"]["notes"] = "notes-jazz-0.0.0"
    return build
''',
    "no_version": '''
def _load_build():
    build = _tree_build()
    build.pop("version", None)
    return build
''',
    "wrong_tag": '''
def _load_build():
    build = _tree_build()
    if build:
        build["tag"] = "v0.0.0"
        build["build"] = 0
    return build
''',
    "never_empty": '''
def _load_build():
    return _tree_build() or {"version": "0.0.0", "tag": "v0.0.0", "build": 0,
                             "envs": {"notes": "invented"}}
''',
    "missing_python": '''
def _notes_python():
    return "/nonexistent/envs/base/bin/python"
''',
    "unmarked_python": '''
def _notes_python():
    # This module's own source file: it exists, it does not end with "python", and — unless
    # the temp directory holding it happens to contain "base", which the selftest checks for
    # and reports rather than assuming — it contains no "base" either.
    return __file__
''',
}

#: Prefix of every generated stand-in's module name, so a purge can find them all.
_SUBJECT_PREFIX = "_forge2_t399_subject_"


@contextlib.contextmanager
def _generated_subjects(config):
    """Write a stand-in subject module per exemplar into a temp dir on `sys.path`; clean up.

    They are written to disk, rather than built with `types.ModuleType`, because the tests
    RELOAD their subject and `importlib.reload` needs a module with a real loader behind it.
    Yields the temp directory. On exit the directory is removed, `sys.path` is restored, and
    every generated module is dropped from `sys.modules`.
    """
    env = _need(config, "env", dict, "an object naming the environment variables")
    fake = _need(config, "fake_jazz", dict, "an object declaring the fake jazz tree")
    filling = {
        "root_var": env["root_var"],
        "dev_var": env["dev_var"],
        "manifest": [str(part) for part in fake["build_json_path"]],
    }
    scratch = tempfile.mkdtemp(prefix="forge2-t399-selftest-")
    sys.path.insert(0, scratch)
    try:
        for name in _SUBJECT_SOURCES:
            source = (_SUBJECT_COMMON % filling) + _SUBJECT_SOURCES[name]
            Path(scratch, _SUBJECT_PREFIX + name + ".py").write_text(source, encoding="utf-8")
        yield scratch
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(scratch)
        for module in [m for m in sys.modules if m.startswith(_SUBJECT_PREFIX)]:
            del sys.modules[module]
        # rmtree rather than unlinking what was written: importing the stand-ins leaves a
        # __pycache__ beside them, and a selftest that tidied only its own files would leak
        # the directory. Nothing but this selftest's own scratch is ever passed here.
        shutil.rmtree(scratch, ignore_errors=True)


def _config_for(subject_module, base_env=True):
    """Return a fresh selftest config object naming `subject_module` as the subject.

    Built from `config_template()`, so the selftest exercises the same config SHAPE the
    shipped registry uses. `base_env=False` drops the base env from the fake tree, which is
    the tree the ORIGINAL's fixture built.
    """
    config = config_template()
    config["subject"]["module"] = subject_module
    if not base_env:
        config["fake_jazz"]["base_env_python_path"] = None
    return config


def selftest(stream=None):
    """Prove this rewrite against ticket #399's acceptance items (a), (b) and (d).

    Builds its own config objects in memory and its own stand-in subjects in a temporary
    directory it removes, so checks [1] to [6] need no registry and leave nothing behind.
    Check [7] is the exception and reads the shipped registry deliberately — to cross-check
    it — and reports n/a rather than failing when there is none to read. Nothing here writes
    outside that temporary directory. Returns the number of failed checks.

    Checks, in order:
      1. the config gate — resolution throws ConfigError where no registry exists;
      2. every test refuses to judge anything, rather than passing, when its config cannot be
         resolved or is incomplete;
      3. the callable surface this ticket names;
      4. every exemplar in EXEMPLARS — the hand-written (subject, verdict) table;
      5. the subject reload is load-bearing;
      6. the original's fixture tree, and the machine dependence it carries;
      7. the shipped registry agrees with the template and with the stand-in subject it names.
    """
    out = stream or sys.stdout
    failures = []
    checks = [0]

    def check(ok, label):
        checks[0] += 1
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    def note(text):
        print("  n/a   %s" % text, file=out)

    saved_active = configure(None)
    saved_env = os.environ.pop(CONFIG_ENV, None)
    try:
        reset_config()

        # 1. the config gate, proven from a directory with no registry above it.
        print("[1] config gate — a tool that cannot see its config throws", file=out)
        with tempfile.TemporaryDirectory(prefix="forge2-t399-") as isolated:
            if find_registry(isolated) is not None:
                note("a %s exists above the temp dir %s, so 'no registry anywhere' cannot be "
                     "staged here; check [2] proves the gate instead" % (REGISTRY_NAME, isolated))
            else:
                try:
                    load_config(start=isolated)
                    check(False, "load_config() where no %s exists raises ConfigError"
                          % REGISTRY_NAME)
                except ConfigError:
                    check(True, "load_config() where no %s exists raises ConfigError"
                          % REGISTRY_NAME)

        # 2. the tests refuse to judge when the config cannot be resolved or is incomplete.
        #    Staged by pointing FORGE2_CONFIG at a file that does not exist: the env source
        #    outranks the registry walk-up, so this proves the gate the same way whether or not
        #    a registry happens to sit above this module — and this package SHIPS one, so a
        #    bare run here would otherwise succeed. Check [1] cannot do that on its own.
        print("[2] the tests refuse to judge anything without a config object", file=out)
        with tempfile.TemporaryDirectory(prefix="forge2-t399-") as isolated:
            os.environ[CONFIG_ENV] = os.path.join(isolated, "no-such-config.json")
            reset_config()
            try:
                results = run_tests()
                check(False, "run_tests() with an unresolvable config raises ConfigError (it "
                             "returned %r instead)" % (results,))
            except ConfigError:
                check(True, "run_tests() with an unresolvable config raises ConfigError — no "
                            "test reports a verdict and no default is guessed")
            except Exception as exc:  # noqa: BLE001
                check(False, "run_tests() with an unresolvable config raised %s, not "
                             "ConfigError" % type(exc).__name__)
            finally:
                os.environ.pop(CONFIG_ENV, None)
                reset_config()

        incomplete = _config_for("nothing.importable")
        del incomplete["expect"]["notes_python_suffixes"]
        with using_config(incomplete):
            try:
                run_tests(names=["test_notes_python_fallback"])
                check(False, "a config object missing a key raises ConfigError naming it")
            except ConfigError as exc:
                check("notes_python_suffixes" in str(exc),
                      "a config object missing a key raises ConfigError naming it (%s)" % exc)

        with using_config(_config_for("nothing.importable")):
            try:
                run_tests(names=["test_load_build"])
                check(False, "a subject that cannot be imported raises ConfigError, not a FAIL")
            except ConfigError as exc:
                check("nothing.importable" in str(exc),
                      "a subject that cannot be imported raises ConfigError naming it, rather "
                      "than being reported as a failing test")

        # 3. the callable surface.
        print("[3] callable surface — the four callables #399 names", file=out)
        wanted_surface = (
            ("test_load_build", test_load_build, "(fake_jazz, monkeypatch)"),
            ("test_notes_python_fallback", test_notes_python_fallback, "(fake_jazz, monkeypatch)"),
            ("test_build_json_missing", test_build_json_missing, "(tmp_path, monkeypatch)"),
        )
        for name, function, signature in wanted_surface:
            got = str(inspect.signature(function))
            check(got == signature, "%s%s matches the ticket's surface %s%s"
                  % (name, got, name, signature))
        if _pytest is None:
            got = str(inspect.signature(fake_jazz))
            check(got == "(tmp_path)",
                  "fake_jazz%s matches the ticket's surface fake_jazz(tmp_path)" % got)
        else:
            note("pytest is installed, so `fake_jazz` is a fixture object rather than a plain "
                 "function and has no signature of its own to read; it wraps `def "
                 "fake_jazz(tmp_path)`, so the fixture pytest registers is named fake_jazz and "
                 "takes tmp_path")
        check(all(name in globals() for name, _, _ in wanted_surface) and "fake_jazz" in globals(),
              "all four callables are module-level names")

        # 4. the exemplars.
        print("[4] exemplars — the hand-written (subject, verdict) table", file=out)
        with _generated_subjects(config_template()) as scratch:
            unmarked_ok = "base" not in str(Path(scratch, _SUBJECT_PREFIX + "unmarked_python.py"))
            for name, wanted, why in EXEMPLARS:
                if name == "unmarked_python" and not unmarked_ok:
                    note("the temp directory %s happens to contain \"base\", so the "
                         "'unmarked_python' exemplar cannot be staged in this run" % scratch)
                    continue
                with using_config(_config_for(_SUBJECT_PREFIX + name)):
                    got = {test: ok for test, (ok, _) in run_tests().items()}
                    details = {test: detail for test, (ok, detail) in run_tests().items()
                               if not ok}
                check(got == wanted, "subject %r → %s%s\n          (%s)"
                      % (name, _verdicts(got),
                         "" if got == wanted else "  — EXPECTED %s" % _verdicts(wanted), why))
                if got != wanted:
                    for test, detail in details.items():
                        print("          %s: %s" % (test, detail), file=out)

            # 5. the reload is load-bearing.
            print("[5] the subject reload is load-bearing", file=out)
            module_name = _SUBJECT_PREFIX + "conforming"
            env = config_template()["env"]
            stashed = {var: os.environ.pop(var, None) for var in (env["root_var"], env["dev_var"])}
            try:
                sys.modules.pop(module_name, None)
                importlib.import_module(module_name)   # snapshots an environment with no root
            finally:
                for var, value in stashed.items():
                    if value is not None:
                        os.environ[var] = value
            with using_config(_config_for(module_name)):
                ok = run_tests(names=["test_load_build"])["test_load_build"][0]
            check(ok, "a subject imported BEFORE the test set JAZZ_ROOT still sees the test's "
                      "tree — the test reloads it. A rewrite that dropped importlib.reload "
                      "fails this check")

            # 6. the original's fixture tree, and the machine dependence it carries.
            print("[6] the original's fixture tree (base_env_python_path = null)", file=out)
            interpreter = sys.executable
            implied = ("base" in interpreter) or interpreter.endswith("python")
            with using_config(_config_for(module_name, base_env=False)):
                results = run_tests()
            got = results["test_notes_python_fallback"][0]
            check(got == implied,
                  "with the ORIGINAL's tree the fallback test's verdict is decided by this "
                  "interpreter's path, not by the subject: %s → verdict %s, as %r implies. "
                  "That undeclared machine dependence is what the shipped tree removes"
                  % (interpreter, "PASS" if got else "FAIL", interpreter))
            check(results["test_load_build"][0] and results["test_build_json_missing"][0],
                  "with the ORIGINAL's tree the other two tests are unaffected and still pass "
                  "— the base env the shipped config adds changes nothing but the fallback "
                  "test's machine dependence")

        # 7. the shipped registry.
        print("[7] the shipped registry", file=out)
        reset_config()
        try:
            shipped, _, source = load_config()
        except ConfigError as exc:
            note("no shipped registry is resolvable from this file (%s), so it cannot be "
                 "cross-checked here" % exc)
        else:
            template = config_template()
            check(_settings(shipped) == _settings(template),
                  "the shipped config object at %s has exactly the keys `emit-config` prints "
                  "(%s)" % (source, ", ".join(sorted(_settings(template)))))
            subject_name = shipped.get("subject", {}).get("module")
            if subject_name != REFERENCE_MODULE:
                note("the shipped registry names %r as the subject rather than this package's "
                     "stand-in, so there is no stand-in section to cross-check against"
                     % subject_name)
            else:
                try:
                    reference, _, _ = load_config(unit_path=REFERENCE_UNIT_PATH)
                except ConfigError as exc:
                    check(False, "the shipped registry has a config object for the stand-in "
                                 "subject it names (%s)" % exc)
                else:
                    check(shipped["env"]["root_var"] == reference.get("root_var")
                          and shipped["env"]["dev_var"] == reference.get("dev_var"),
                          "the shipped registry's test-side env var names match the stand-in "
                          "subject's own section")
                    check(shipped["fake_jazz"]["build_json_path"]
                          == reference.get("build_json_path"),
                          "the shipped registry's manifest path matches the stand-in subject's "
                          "own section")
                    where_subject_looks = ([reference.get("envs_dir"), reference.get("base_env")]
                                           + list(reference.get("python_relpath") or []))
                    check(shipped["fake_jazz"]["base_env_python_path"] == where_subject_looks,
                          "the shipped fixture puts the base env exactly where the stand-in "
                          "subject looks for it (%s)" % "/".join(str(p) for p in
                                                                 where_subject_looks))
    finally:
        os.environ.pop(CONFIG_ENV, None)
        if saved_env is not None:
            os.environ[CONFIG_ENV] = saved_env
        reset_config()
        globals()["_ACTIVE"] = saved_active

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED", checks[0], len(failures)),
          file=out)
    for failure in failures:
        print("  failed: %s" % failure.splitlines()[0], file=out)
    return len(failures)


def _settings(config):
    """Return the SETTING names in a config object — every key that is not a comment.

    A key whose name starts with `_` is documentation for whoever opens the registry, not a
    setting: the shipped `registry.json` carries an `_comment` in each section explaining what
    that section is for, and `emit-config`'s template carries none.
    """
    return {key for key in config if not key.startswith("_")}


def _verdicts(verdicts):
    """Render a {test: ok} mapping compactly, in the tests' declared order."""
    return " ".join("%s=%s" % (name.replace("test_", ""),
                               "PASS" if verdicts.get(name) else "FAIL")
                    for name, _, _ in TESTS)


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by `note-for-claude` ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report its
    original error. No report is filed for a ConfigError or for a failing test — both are
    designed behavior rather than bugs. Returns the path written, or None.
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
        "methods-to-reproduce": "python3 -m coupler.tests.test_coupler %s" % " ".join(argv),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": formatted.strip().splitlines()[-6:],
        "note": "%s (ticket #399, module key forge-rw:dc95cfcf8d8037c8)" % UNIT,
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
        prog="forge2-coupler-test-coupler",
        description="forge2 rewrite of the forge unit "
                    "code__code-invalid__coupler:coupler/tests/test_coupler.py (ticket #399). "
                    "Verifies that a coupler resolves its build and its notes interpreter "
                    "without live jazz services. Runs under pytest unchanged; `run` below is "
                    "the same three tests on a bare interpreter. Config-driven: every command "
                    "except `emit-config` and `selftest` throws if it cannot see its config "
                    "object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="config is read from the file named by $%s, else from the %s section of the "
               "nearest %s found by walking up from this module. This package ships one at the "
               "root of the folder holding it, so `run` works from a clean checkout. Run "
               "`emit-config` for a template." % (CONFIG_ENV, " -> ".join(UNIT_PATH),
                                                  REGISTRY_NAME),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="run the three tests against the configured subject")
    sub.add_parser("selftest", help="prove the exemplars, the surface and the config gate")
    emit = sub.add_parser("emit-config", help="print a template of a unit's config object")
    emit.add_argument("--unit", choices=["test_coupler", "reference_main"],
                      default="test_coupler",
                      help="which unit's config object to print (default: test_coupler)")
    sub.add_parser("show-config", help="print the config object in force and its source")
    return parser


def main(argv=None):
    """Entry point for the `forge2-coupler-test-coupler` console script.

    Returns a process exit code: 0 on success, 1 when a test or a selftest check fails, 2 on a
    config error.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "emit-config":
            if args.unit == "reference_main":
                template = importlib.import_module(REFERENCE_MODULE).config_template()
                where = " -> ".join(REFERENCE_UNIT_PATH)
            else:
                template = config_template()
                where = " -> ".join(UNIT_PATH)
            print(json.dumps(template, indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at "
                  "it.\n# Until it is installed, this unit throws — it will not guess a default."
                  % (where, REGISTRY_NAME, CONFIG_ENV), file=sys.stderr)
            return 0

        if args.command == "selftest":
            return 0 if selftest() == 0 else 1

        if args.command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(), "base": active_base(),
                              "config": active_config()}, indent=2))
            return 0

        if args.command == "run":
            print("running %d test(s) against subject %r"
                  % (len(TESTS), _section("subject", "an object naming the module under "
                                                     "test")["module"]))
            results = run_tests()
            failed = _print_results(results, sys.stdout)
            print("\n%s — %d test(s), %d failure(s)"
                  % ("PASSED" if not failed else "FAILED", len(results), failed))
            return 0 if not failed else 1

    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        # `run_tests` refusing to run under -O. Also designed behavior.
        print("%s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        path = _bug_report(exc, traceback.format_exc(), argv)
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise

    return 0


if __name__ == "__main__":
    sys.exit(main())
