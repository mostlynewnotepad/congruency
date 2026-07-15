# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 testmonkeyalpha — Claude & Co.
#
# The two lines above are the ORIGINAL unit's license grant and copyright notice, carried
# forward deliberately. This file is an entirely new implementation (see the docstring), but
# it is a derived work of an Apache-2.0 unit, so its license header travels with it. A
# comment is not behavior — the module identity this ticket was filed under is AST-normalized
# and ignores comments entirely — so these lines are provenance, not preserved code.
"""forge2 / audio_tagger / tests / test_stub — a behavior-preserving rewrite of the forge
unit `audio_tagger:audio_tagger/tests/test_stub.py` (module key forge-rw:f5a5302ef988bc20),
filed under ticket #407 against the FORGE-wide refactor standard #200.

WHAT THIS IS
------------
The original forge unit was 306 bytes: it imported `unittest`, declared one
`unittest.TestCase` subclass named `TestStub` holding one test method named
`test_placeholder` whose body was `self.assertTrue(True)` and whose docstring was "Stub test
— replace with real tests.", and ran `unittest.main()` when executed as a script. It is a
STUB: a test that always passes, standing in for tests not yet written.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and it adds the three things #200 requires that the
original lacked: it is a proper installable package, it is driven by a configuration object,
and it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    TestStub.test_placeholder(self)

That is the surface this ticket names, and it is reproduced exactly: `TestStub` is a
`unittest.TestCase` subclass, `test_placeholder` takes only `self`, asserts a true value,
returns None, and passes.

Three properties of that sentence are easy to get wrong, and all three are load-bearing
because the original had them:

  * The DOCSTRING IS BEHAVIOR, not decoration. `unittest.TestCase.shortDescription()`
    returns the first line of a test's docstring, and the verbose runner PRINTS it: `python3
    test_stub.py -v` writes "Stub test — replace with real tests. ... ok" to stderr. A
    rewrite that reworded the docstring — or dropped it, which makes `shortDescription()`
    return None and changes the verbose output — would change observable output. It is
    therefore reproduced byte for byte, em dash and trailing period included.
  * EXACTLY ONE test is discovered. `unittest` collects every attribute whose name starts
    with `test`, so a helper method named `test_anything` on this class, or a second
    TestCase in this module, would turn "Ran 1 test" into "Ran 2 tests". Every helper in this
    module is therefore a module-level function or is underscore-prefixed, and `TestStub` is
    the only TestCase here.
  * The test PASSES WITHOUT ANY SETUP, under any runner that imports it — `python3 -m
    unittest discover`, `pytest`, a CI harness. See "WHAT IS CONFIG-GATED, AND WHAT IS NOT"
    below, which is where that property meets #200's requirement 4.

WHAT IS CONFIG-GATED, AND WHAT IS NOT (and why)
-----------------------------------------------
This is the one design decision in this file worth reading, so it is stated plainly rather
than left to be inferred.

GATED — the RUNNER. `main()`, which is what `python3 test_stub.py` and the console script
`forge2-audio-tagger-test-stub` invoke, resolves a config object before it runs anything. If
it cannot see one it raises `ConfigError`, prints one self-explaining line and exits 2
WITHOUT running a test. That is #200's requirement 4 and this ticket's acceptance item (d).

NOT GATED — the TEST CASE. `TestStub.test_placeholder` needs no config and passes without
one. This is deliberate, and it is required by the SAME ticket:

  * Acceptance (a) says the rewrite reproduces the original's behavior and (b) that existing
    callers keep working. A caller of a test module is a test runner. The original's test
    passes under a bare `pytest` or `unittest discover` with no registry in sight; a rewrite
    whose test ERRORED with `ConfigError` under those runners would reproduce neither (a)
    nor (b) — it would break every existing caller, which is the precise thing (b) forbids.
  * Requirement 4's words are "NO hardcoded paths or params". `self.assertTrue(True)` has no
    params and touches no paths. The always-true assertion is not a setting — it IS the
    unit's definition, the thing that makes a stub a stub, exactly as the seeds `(0, 1)` are
    the Fibonacci sequence rather than a setting in this package's sibling rewrite
    `artifact_tree_gen/fib.py` (ticket #405, its "WHY THE CONFIG HAS EXACTLY ONE BEHAVIORAL
    KEY" section). Making the assertion configurable would let a config turn a passing test
    into a failing one — changing the very behavior this ticket exists to preserve — and
    #200 "does not require inventing knobs the unit never had".

So: what DID the original hardcode that is not part of its definition? Exactly one thing —
the bare call `unittest.main()`. That call has nine behavioral parameters (`verbosity`,
`failfast`, `catchbreak`, `buffer`, `warnings`, `tb_locals`, `exit`, `defaultTest`,
`testRunner`), and the original froze every one of them at the stdlib default by passing
none of them. Those are params, they were hardcoded, and they are what this unit's config
object drives — the whole param surface of the one call, nothing invented and nothing left
behind. The shipped `registry.json` sets them to the values that reproduce the original.

COMMAND-LINE ARGUMENTS BELONG TO UNITTEST
-----------------------------------------
`unittest.main()` parses `sys.argv` itself, so the original supports `python3 test_stub.py
-v`, `-q`, `-f`, `-c`, `-b`, `-k PATTERN`, `--locals`, `--durations N`, `-h`, and naming
tests directly (`python3 test_stub.py TestStub.test_placeholder`). All of that is behavior.
This file therefore adds NO argument parser of its own and reserves NO subcommand: every
argument goes to `unittest.main()` untouched, so each of those invocations behaves exactly
as it did before. `python3 test_stub.py selftest` still fails the way the original did (there
is no test named `selftest`), because intercepting a word would be a behavior change.

That is why the config template printer, the config inspector and the equivalence proof live
in the SIBLING module `stub_selftest.py` rather than behind a flag here. See RUNNING IT.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a
    single `.json` file holding the configuration for every tool in a set of packaging.
    `note-for-claude` states the contract this module obeys — "if a tool cannot see the
    registry it will throw an exeption" [sic]. THIS package ships its own `registry.json` at
    the root of the import package; see CONFIGURATION.
config object
    The chunk of that registry belonging to this unit — the
    `forge2.audio_tagger.tests.test_stub` section. It is what drives this module.
    `stub_selftest.py emit-config` prints a template of it.
runner parameter
    One of the nine keyword arguments of `unittest.main()` listed above. The config names
    each one; this module passes them through, and nothing else, to that call.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
`main()` resolves its config object on first use, from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. This file holds the unit
     config object itself — exactly what `stub_selftest.py emit-config` prints.
  2. otherwise, the `forge2.audio_tagger.tests.test_stub` section of the nearest
     `registry.json` found by walking UP from THIS FILE's directory.

If NEITHER answers, `main()` raises `ConfigError` and runs no test. It never guesses a
default — that is `note-for-claude`'s rule and this ticket's acceptance item (d). A config
object that is found but is missing a runner parameter is also a `ConfigError`, naming the
key; a value of the wrong JSON type is a `ConfigError` naming the key and the type it wants.

This package ships `registry.json` at the root of the import package (beside
`audio_tagger/__init__.py`, one directory above this file), so source 2 answers and `python3
test_stub.py` works from a clean checkout with no setup. It lives INSIDE the import package
rather than at the project root on purpose: a non-editable `pip install` copies only the
import package into site-packages, and `pyproject.toml` ships the registry as package-data,
so the walk-up from an INSTALLED copy of this file finds it too. A project-root registry
would answer for the editable install and vanish for the real one.

That shipped registry is the config object this unit runs on; it is not a fallback baked
into the code. Delete it (with `FORGE2_CONFIG` unset and no other `registry.json` above this
directory) and `main()` throws — the gate is in the code, not in the file's presence.
`stub_selftest.py selftest` proves the gate directly, without deleting anything, by pointing
`FORGE2_CONFIG` at a file that does not exist.

The shipped registry deliberately carries ONLY this unit's section: ticket #407 covers one
module. A sibling unit resolves its own config independently and throws if its own section is
absent, which is the designed gate doing its job rather than a defect in this file.

`configure(config)` and `using_config(config)` inject a config object directly, in-process,
for callers that hold their configuration in memory rather than on disk.

RUNNING IT
----------
Every command below is executable as written from this file's own directory; from anywhere
else, give the full path to `test_stub.py` instead of the bare name. Which directory you run
from does not change what config is found — the registry walk-up starts at THIS FILE, never
at the working directory.

    python3 test_stub.py                    # -> Ran 1 test / OK          (exit 0)
    python3 test_stub.py -v                 # -> prints the docstring, ok (exit 0)
    python3 test_stub.py -h                 # -> unittest's own help      (exit 0)
    python3 stub_selftest.py                # prove equivalence vs the ORIGINAL, and the gate
    python3 stub_selftest.py emit-config    # print a config-object template
    python3 stub_selftest.py show-config    # print the resolved config + where it came from

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, and the package is committed in
full beside it — `pyproject.toml`, `audio_tagger/__init__.py`, `audio_tagger/tests/__init__.py`,
`audio_tagger/registry.json`, `stub_selftest.py`. From the directory holding `pyproject.toml`
(two above this file):

    pip install -e .
    forge2-audio-tagger-test-stub           # -> Ran 1 test / OK
    forge2-audio-tagger-stub-selftest       # -> the equivalence proof

`pyproject.toml` keeps the import path the forge unit was originally addressed by (repo
`audio_tagger`, path `audio_tagger/tests/test_stub.py`), so an installed copy imports as
`from audio_tagger.tests.test_stub import TestStub`.

SIDE EFFECTS
------------
Importing this module resolves NO config, reads NO file and runs no test: a runner that
merely collects `TestStub` must not be able to trip the gate, or requirement (b) would
break. Config is resolved only when `main()` is called. `main()` itself creates no files.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception
is thrown") `main()` appends one timestamped JSON line to the config's `bug_reports` path if
it hits an UNEXPECTED exception — that is, a defect in this tool. A `ConfigError` is designed
behavior, not a bug, and neither is the `SystemExit` that `unittest.main()` raises to report
a test result or a bad command line: none of them file a report or print a traceback.
"""

import contextlib
import importlib
import inspect
import json
import os
import sys
import traceback
import unittest
from datetime import datetime

__all__ = [
    "TestStub",
    "ConfigError",
    "load_config",
    "configure",
    "using_config",
    "reset_config",
    "runner_kwargs",
    "config_template",
    "main",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS
#: in the config document, not a configurable setting — a config-driven tool has to know
#: which section is its own.
UNIT_PATH = ("forge2", "audio_tagger", "tests", "test_stub")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:audio_tagger/tests/test_stub"

#: The sibling tool that prints a config template, for error messages to point at.
HELPER = "stub_selftest.py"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a runner parameter.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.
    """


# ─────────────────────────────── the unit itself ───────────────────────────────


class TestStub(unittest.TestCase):
    """The rewritten unit: one always-passing placeholder test.

    A STUB stands in for tests not yet written, so its single test asserts a value that is
    true by construction and therefore always passes. That is the unit's definition, not a
    setting — see this module's docstring, "WHAT IS CONFIG-GATED, AND WHAT IS NOT".

    This class needs no config object and is safe to import, collect and run under any
    runner with no setup at all, exactly as the original was.
    """

    def test_placeholder(self):
        """Stub test — replace with real tests."""
        self.assertTrue(True)


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None      # config object injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution, so main() re-reads no files


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
            "Run `%s emit-config` for a template of the config object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))), HELPER)
        )

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r "
                "section. Run `%s emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), HELPER,
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


# ───────────────────────── the runner parameters ─────────────────────────

#: The config's keys, mapped to the `unittest.main()` keyword each one drives. These nine are
#: the COMPLETE behavioral parameter surface of the single call the original hardcoded — see
#: this module's docstring. `module` and `argv` are not here because they are structural
#: rather than settings (this module is always the module under test, and argv belongs to
#: unittest per "COMMAND-LINE ARGUMENTS BELONG TO UNITTEST"), and `testLoader` is not here
#: because it takes a loader OBJECT that JSON cannot name.
RUNNER_KEYS = (
    ("verbosity", "verbosity"),
    ("failfast", "failfast"),
    ("catchbreak", "catchbreak"),
    ("buffer", "buffer"),
    ("warnings", "warnings"),
    ("tb_locals", "tb_locals"),
    ("exit", "exit"),
    ("default_test", "defaultTest"),
    ("test_runner", "testRunner"),
)

#: The parameters THIS Python's `unittest.main()` actually accepts. Read from the live
#: signature rather than assumed, so an optional key this interpreter is too old for is
#: refused with a clear message instead of a TypeError from deep inside unittest.
_MAIN_PARAMS = frozenset(inspect.signature(unittest.TestProgram.__init__).parameters)


def _bad(key, wants, got):
    return ConfigError(
        "config key %r for %s must be %s, not %s. Run `%s emit-config` for a template."
        % (key, UNIT, wants, type(got).__name__, HELPER)
    )


def _load_attr(key, spec):
    """Resolve a `"module:attr"` string to the attribute it names."""
    if ":" not in spec:
        raise ConfigError(
            "config key %r for %s must look like \"module:attr\" (for example "
            "\"unittest:TextTestRunner\"); got %r" % (key, UNIT, spec)
        )
    mod_name, _, attr = spec.partition(":")
    module = sys.modules.get(mod_name)
    if module is None:
        try:
            module = importlib.import_module(mod_name)
        except ImportError as exc:
            raise ConfigError(
                "config key %r for %s names module %r, which cannot be imported: %s"
                % (key, UNIT, mod_name, exc)
            ) from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ConfigError(
            "config key %r for %s names %r, but module %r has no attribute %r"
            % (key, UNIT, spec, mod_name, attr)
        ) from exc


def _check_bool(key, value, allow_null):
    if value is None and allow_null:
        return value
    # `type(...) is bool` rather than isinstance: JSON true/false must not be spelled 1/0,
    # and bool is a subclass of int so isinstance would let an integer through.
    if type(value) is not bool:
        raise _bad(key, "a boolean" + (" or null" if allow_null else ""), value)
    return value


def runner_kwargs():
    """Return the `unittest.main()` keyword arguments this unit's config object names.

    Every one of the nine runner parameters must be present: this tool does not guess a
    default for a key its config forgot to state. The optional tenth key `durations` is
    accepted when this Python's `unittest.main()` supports it (3.12 and later).

    Raises:
        ConfigError: if the config cannot be resolved, is missing a key, or gives one a value
            of the wrong type — always naming the key at fault.
    """
    config = active_config()
    kwargs = {}
    for key, param in RUNNER_KEYS:
        if key not in config:
            raise ConfigError(
                "config object for %s is missing the required runner parameter %r (it drives "
                "unittest.main(%s=...)). Run `%s emit-config` for a template."
                % (UNIT, key, param, HELPER)
            )
        value = config[key]

        if key == "verbosity":
            # bool is an int subclass, so `type(...) is int` keeps `true` from meaning 1.
            if type(value) is not int:
                raise _bad(key, "an integer (0 quiet, 1 default, 2 verbose)", value)
        elif key in ("failfast", "catchbreak", "buffer"):
            # These three MUST be allowed to stay null. unittest.main() only adds the -f/-c/-b
            # command-line options when the corresponding parameter is None; pinning one to a
            # boolean silently REMOVES its flag from the parser, so `python3 test_stub.py -f`
            # would stop working. null is what the original passed and what preserves them.
            _check_bool(key, value, allow_null=True)
        elif key in ("tb_locals", "exit"):
            _check_bool(key, value, allow_null=False)
        elif key == "warnings":
            if value is not None and not isinstance(value, str):
                raise _bad(key, "a warnings filter string (\"default\", \"ignore\", ...) "
                                "or null", value)
        elif key == "default_test":
            if value is not None and not isinstance(value, str):
                if not (isinstance(value, list) and all(isinstance(n, str) for n in value)):
                    raise _bad(key, "a test name, a list of test names, or null", value)
                value = list(value)
        elif key == "test_runner":
            if value is not None:
                if not isinstance(value, str):
                    raise _bad(key, "a \"module:attr\" string naming a test runner, or null",
                               value)
                value = _load_attr(key, value)

        kwargs[param] = value

    if "durations" in config and config["durations"] is not None:
        if "durations" not in _MAIN_PARAMS:
            raise ConfigError(
                "config key 'durations' for %s needs unittest.main(durations=...), which "
                "Python %s does not have (it arrived in 3.12). Set it to null."
                % (UNIT, "%d.%d" % sys.version_info[:2])
            )
        if type(config["durations"]) is not int:
            raise _bad("durations", "an integer or null", config["durations"])
        kwargs["durations"] = config["durations"]

    return kwargs


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do `main()` throws. The values shown are the ones
    that reproduce the ORIGINAL unit's bare `unittest.main()`.
    """
    return {
        "verbosity": 1,
        "failfast": None,
        "catchbreak": None,
        "buffer": None,
        "warnings": None,
        "tb_locals": False,
        "exit": True,
        "default_test": None,
        "test_runner": None,
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────────────── the command line ───────────────────────────────


def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report its
    original error. No report is filed for a ConfigError, nor for the SystemExit unittest
    raises to report a test result — both are designed behavior rather than bugs. Returns the
    path written, or None.
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
                                                   " ".join(argv[1:])),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": formatted.strip().splitlines()[-6:],
        "note": "%s (ticket #407, module key forge-rw:f5a5302ef988bc20)" % UNIT,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except OSError:
        return None


def main(argv=None):
    """Run this module's tests through `unittest.main()`, with the config's runner parameters.

    `argv` is a FULL argv including the program name at index 0, defaulting to `sys.argv`,
    and every element after index 0 is handed to `unittest.main()` untouched — see
    "COMMAND-LINE ARGUMENTS BELONG TO UNITTEST" in this module's docstring.

    With the shipped config (`exit` true) this does not return: `unittest.main()` raises
    SystemExit carrying the test result, exactly as the original did. It returns an exit code
    only when the config sets `exit` false, or when the config gate stops it first.

    Returns:
        int: 2 if the config object cannot be resolved (nothing is run), otherwise 0 for a
            successful run and 1 for a failing one.
    """
    argv = list(sys.argv if argv is None else argv)
    if not argv:
        argv = [os.path.basename(os.path.abspath(__file__))]

    try:
        kwargs = runner_kwargs()
    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report,
        # and NO test is run.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — anything else here is a defect in this tool
        path = _bug_report(exc, traceback.format_exc(), argv)
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise

    # SystemExit from unittest (a test result, or argparse rejecting a bad flag) is a
    # BaseException, so it passes through this handler untouched — which is what preserves
    # the original's exit codes.
    try:
        program = unittest.main(module=sys.modules[__name__], argv=argv, **kwargs)
    except Exception as exc:  # noqa: BLE001
        path = _bug_report(exc, traceback.format_exc(), argv)
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise

    result = getattr(program, "result", None)
    return 0 if result is None or result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
