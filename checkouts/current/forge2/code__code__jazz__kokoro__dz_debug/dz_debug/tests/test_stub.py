#!/usr/bin/env python3
"""forge2 / code__code__jazz__kokoro__dz_debug / dz_debug/tests/test_stub — a
behavior-preserving rewrite of the forge unit
`code__code__jazz__kokoro__dz_debug:dz_debug/tests/test_stub.py` (module key
forge-rw:7085cf4c6d8c909f), filed under ticket #365 against the FORGE-wide refactor standard
#200.

WHAT THIS IS
------------
The original forge unit was 427 bytes: one `unittest.TestCase` with one test method. That method
decorated a two-argument `add` with `dz_debug`'s `debug_decorator`, called it, and asserted the
call still returned the sum. This file is an entirely new implementation of that unit. It keeps
the original's observable behavior — it drives the same subject the same way and asserts the same
thing about it — and its callable surface, and it adds the three things #200 requires that the
original lacked: it is part of a proper installable package, it is driven by a configuration
object, and it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    TestDebugDecorator.test_decorator_returns_result(self)

That is ticket #365's stated surface, verbatim. The caller of a test module is the test runner,
so the class name, the method name and the parameter are all preserved: `unittest`, `pytest` and
`python3 dz_debug/tests/test_stub.py` each collect and run exactly the one test they collected
before. `check_surface()` checks this against the ORIGINAL's own syntax tree rather than against
a list typed out by hand, so the two cannot drift apart.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a single
    `.json` file at the root of a package holding the configuration for every tool in that
    package. `note-for-claude` states the contract this module obeys — ".json will have all the
    configuration - for all tools in this set of packaging. (a configuration registry) -if a tool
    cannot see the registry it will throw an exeption" [sic].
config object
    The chunk of that registry belonging to this unit — the section at `forge2 ->
    code__code__jazz__kokoro__dz_debug -> dz_debug -> tests -> test_stub`. It is what drives this
    module. `emit-config` prints a template of it.
subject under test
    The `dz_debug` code this test exercises: the `debug_decorator` decorator. The original
    HARDCODED it as `from dz_debug.logger import debug_decorator`. A hardcoded dependency is what
    #200's control-config requirement forbids, so here it is named BY THE CONFIG — the
    `decorator` key.
oracle
    The original module, embedded in this file as `ORIGINAL_SOURCE` and proven byte-identical to
    the forge blob before it is trusted. It is the only authority on what the right answer is;
    this rewrite is never consulted about that.
substrate
    A stand-in `dz_debug.logger` that the equivalence proof runs the tests against, built in
    memory by `substrate()`. No `dz_debug` need be installed to run the proof.
mutant
    A substrate whose `debug_decorator` is deliberately broken in exactly one way.

THIS FILE IS DELIBERATELY SELF-CONTAINED, AND THAT IS NOT A STYLE CHOICE
-----------------------------------------------------------------------
Ticket #365 says "the harness commits the WHOLE of
checkouts/current/forge2/code__code__jazz__kokoro__dz_debug/ — so build the package there in
full". The observable record of this checkout only partly bears that out, and the gap has already
cost one landed artifact its proof, so this module is built for what the harness has ACTUALLY
been seen to do:

  * every forge2 landing in this repository's git history is a single file — the commit subjects
    all read `forge2 #NNN: land <one-path> (module-only, additive)`;
  * the landed sibling `dz_debug/tests/test_dz_debug.py` (ticket #359) states in its own docstring
    that it writes `dz_debug/__init__.py` and `dz_debug/tests/__init__.py` "alongside this file".
    NEITHER exists in this checkout. Only its own module landed;
  * that same sibling depends on a registry section `forge2 -> ... -> dz_debug -> tests ->
    test_dz_debug` which is likewise absent from this package's `registry.json`, so every one of
    its ten tests raises ConfigError today.

So this module imports no helper of its own and depends on no sibling file landing. Its config
machinery, its embedded oracle, its substrates and its whole proof are all here. It does NOT
import `dz_debug/_config.py` or `dz_debug/_init_config.py`, even though both are close cousins of
the config code below and landed first: importing them would make this file's fate depend on a
second file surviving, which is the exact failure above. The duplication is the point.

Unlike #359, this module does not merely hope its registry section lands — this ticket ADDS that
section to this package's `registry.json`, additively, disturbing no sibling's section. And
because a module-only landing would drop even that, every command below still supplies its own
config and runs from a bare checkout regardless.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The test resolves its config object on first use, from the first source that answers:

  1. the file named by the `DZ_DEBUG_TEST_STUB_CONFIG` environment variable, which holds the unit
     config object itself — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code__jazz__kokoro__dz_debug -> dz_debug -> tests ->
     test_stub` section of the nearest `registry.json` found by walking UP from THIS FILE's
     directory;
  3. otherwise, the `registry.json` this distribution ships as package data inside its top-level
     `code__code__jazz__kokoro__dz_debug` package.

The walk-up starts at this file, never at the working directory, so which directory you run from
does not change what config is found. Step 3 exists because a NON-editable `pip install .`
installs `dz_debug/` and `code__code__jazz__kokoro__dz_debug/` as two separate top-level
directories in site-packages, and the walk-up from `dz_debug/tests/` then never passes the
registry; it is the same gap `dz_debug/_config.py` documents under "WHY STEP 3 EXISTS". Step 3
never SHADOWS a nearer registry — it runs only after the walk-up has failed outright.

If none of the three answers, the test raises `ConfigError` and asserts nothing. It never guesses
a default — that is `note-for-claude`'s rule and this ticket's acceptance item (d). Under a runner
a `ConfigError` surfaces as an ERROR on the test, which is the gate working: an unconfigured test
that "passed" would be far worse than one that refuses to run.

`configure(config)` and `using_config(config)` inject a config object in-process, for callers that
hold their configuration in memory. The proof uses them, which is why it needs no registry on
disk.

WHAT THE CONFIG CARRIES, AND WHAT IT DELIBERATELY DOES NOT
----------------------------------------------------------
The rule, and the reason it is the right one: **the config carries what the original TOOK FROM or
HANDED TO `dz_debug`. The module keeps what the original ASSERTS — the test's own data and its
expectation.** #200 requires no hardcoded paths or params; it does not require inventing knobs the
unit never had, and turning an assertion into a knob would be worse than a hardcoded param,
because a config could then quietly make the test vacuous.

The original touches `dz_debug` in exactly ONE place — `from dz_debug.logger import
debug_decorator` — and hands it nothing. So the config carries exactly one setting, `decorator`,
and that is not an oversight or a thin gesture at the requirement: it is the whole of what this
unit hardcoded about `dz_debug`. `check_literals()` proves that key reproduces the oracle's own
import, and step 4 of `selftest` proves the test actually FOLLOWS it rather than merely carrying
it — see "PROVING THE CONFIG DRIVES IT" below.

The config does NOT carry `add`'s body, the arguments `(1, 2)`, or the expected `3`. Those are not
params handed to `dz_debug` — `add` is the TEST's own throwaway function, and `3` is the
expectation the test exists to check. Making the expected value settable would let a config tell
the test what answer to accept, which is the opposite of a test. They are module constants below,
each commented with what it is, and `check_literals()` proves each is the original's own literal.

PROVING IT (#200 requirement 1 — behavior-preserving, VERIFIED NOT ASSERTED)
----------------------------------------------------------------------------
Ticket #365 records that criteria_miner captured NO exemplars for this module — it mines only
self-contained pure functions, and a test module is nothing but world-touching calls — and says
so explicitly: that "does NOT weaken the ticket's bar — it MOVES the work: you must write the
equivalence exemplars by hand from the original's behavior."

The exemplars are written by hand, and they are DIFFERENTIAL. For a test module, "behavior" means
the verdict it returns about a given subject, so two test modules are equivalent when they return
the SAME verdict about EVERY subject. `equivalence()` therefore:

  * loads the ORIGINAL from `ORIGINAL_SOURCE` below — the forge blob byte for byte — and refuses
    to proceed unless its git blob sha1 is the `ba528b6bf26d8f442129226008a6eea7296820c4` that
    ticket #365 names. A mistyped oracle is not an oracle;
  * builds each substrate in `substrate()` — one CONFORMING `dz_debug.logger`, plus one MUTANT per
    flaw in `FLAWS`;
  * runs BOTH modules against each substrate through the SAME driver and compares the verdict,
    where a verdict is the outcome AND the exception type ("pass", "fail:AssertionError",
    "error:TypeError"), not merely pass/fail;
  * requires the two modules to AGREE on every substrate — that is the equivalence claim itself.

THE ONE PROPERTY, AND THE HONEST LIMITS OF IT
---------------------------------------------
This is where a rewrite of a 427-byte test earns or loses its claim, so it is worth being exact
rather than impressive. The original makes ONE assertion, and it pins down exactly ONE property:

    a function decorated with `debug_decorator` still returns what it would have returned
    undecorated.

That is a real property and the sweep gives it teeth: nine of the sixteen substrates below break
it, each in a different way, and the proof requires BOTH modules to reject all nine identically —
and, separately, requires the test to be the thing that rejects them (`equivalence()` fails if any
"caught" mutant is not actually caught).

But the original CANNOT see anything else, and a rewrite that could see more would not be
behavior-preserving — it would be a different test. So the sweep also carries six BLIND
substrates: flaws that a real `debug_decorator` could plausibly have and that the original passes
anyway. `no_logging` is the sharpest of them — the original never checks that `debug_decorator`
LOGS ANYTHING, so a decorator that is a pure pass-through and records nothing at all sails
through. `swaps_args` is the subtlest: the wrapper calls `add(2, 1)`, which for addition is still
3, so the assertion cannot tell. On every one of those six the proof requires BOTH modules to
PASS. That half of the table is not padding; it is what stops this rewrite from quietly ADDING
teeth the original did not have, which would be divergence in the other direction.

Naming the blind spots is the honest form of the claim: this module is equivalent to the original,
INCLUDING where the original is weak. Strengthening it is not this ticket's business — #200 asks
for behavior-preserving, and #365 covers this module and nothing else.

Both modules are driven through the SAME driver (`run_case`), which loads the named test off each
module's `TestDebugDecorator` with `unittest`'s own loader and runs it against a shared
`TestResult`. That is deliberate: if this rewrite's surface did not match the original's, the
shared driver could not drive both, so the surface claim above is enforced by the proof rather
than asserted beside it.

The sweep has ONE blind spot of its own, and `oracle_facts()` closes it. The substrates are
polymorphic in the literals the test chooses: nothing makes the arguments be `(1, 2)`, so a
rewrite configured to call `add(10, 20)` and expect `30` would agree with the original on every
substrate above. The sweep can show the rewrite asks the same KIND of question; it cannot show it
asks it with the same words. So `oracle_facts()` parses the ORACLE's syntax tree — its import, its
decorated helper, that helper's parameters, the arguments it is called with, the assertion method
used and the value expected — and `check_literals()` requires this module's config and constants
to reproduce every one of them exactly.

PROVING THE CONFIG DRIVES IT (#200 requirement 4, acceptance item d)
--------------------------------------------------------------------
Carrying a config key proves nothing on its own: a rewrite could read the config, ignore it, and
import `dz_debug.logger` directly, and every check above would still pass. `config_drives_test()`
closes that, and it is the reason sabotage 8 below cannot slip through. It runs the test twice
with NO `dz_debug` in existence at all:

  * given a config object with no `decorator` key, the test must return `error:ConfigError` — it
    must throw rather than guess (acceptance d);
  * given a config naming a decorator installed under a module name that has nothing to do with
    `dz_debug`, the test must PASS — which is only possible if the config is what chose the
    subject. A hardcoded `from dz_debug.logger import ...` fails this half with
    `error:ModuleNotFoundError`, and cannot be made to pass it.

And because a proof that cannot fail is not a proof, `negative-control` breaks this module on
purpose, one edit at a time, in throwaway copies, and checks that `selftest` NOTICES: eight
sabotages that must break it (a dropped assertion, a changed expectation, data the original never
used, a mis-stated oracle sha1, a config pointed at the wrong subject, a subject hardcoded behind
the config's back) and two honest refactors that must NOT (renaming a local, splitting an
expression into a temporary). That second half is what shows the proof measures behavior rather
than spelling — without it, a proof that merely rejected every change would look just as green.

Each sabotage also asserts its target string occurs EXACTLY once before editing, so a sabotage can
never silently strike the embedded oracle instead of the code under test. That count is taken over
this file's CODE REGION only — everything above the negative-control section — because the
sabotage tables quote fragments of the code they edit, and a count over the whole file would find
every fragment twice and refuse to run. See `_code_region()`.

SIDE EFFECTS
------------
The test writes nothing: it decorates a local function, calls it, and compares a number. Neither
did the original. The proof's substrates are built in memory and its temporary directories are
removed when it finishes; `selftest` snapshots this package's tree and the working directory
before and after the whole sweep and reports any file that appeared, so the containment is
demonstrated rather than claimed. (CPython still writes `__pycache__/*.pyc` when it imports a
module, as it does for any module; that is the interpreter's doing, not this module's, so
`selftest` excludes `__pycache__` from the snapshot and says so in its output.)

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception is
thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path if it hits
an UNEXPECTED exception — that is, a defect in this module. A `ConfigError` is designed behavior,
not a bug: it files no report and prints no traceback, and exits 2 with a single self-explaining
line.

RUNNING IT
----------
Every command below is executable as written, from any working directory, with no `dz_debug`
installed and no install of this package:

    python3 dz_debug/tests/test_stub.py selftest         # the whole proof
    python3 dz_debug/tests/test_stub.py equivalence      # the per-substrate verdict table
    python3 dz_debug/tests/test_stub.py negative-control # the proof of the proof: sabotage this
                                                         #   module in throwaway copies and check
                                                         #   `selftest` notices
    python3 dz_debug/tests/test_stub.py oracle-literals  # what the original hardcoded
    python3 dz_debug/tests/test_stub.py show-oracle      # print the embedded original
    python3 dz_debug/tests/test_stub.py emit-config      # print a config-object template
    python3 dz_debug/tests/test_stub.py show-config      # print the resolved config + source

Only `show-config` reads a config from disk; every other command above supplies its own, so all of
them run from a bare checkout with nothing installed.

Under a real test runner, with a real `dz_debug` importable and the config object installed, the
invocation is unchanged from the original's:

    python3 -m unittest dz_debug.tests.test_stub
    python3 dz_debug/tests/test_stub.py          # the original's own `unittest.main()` entry
    pytest dz_debug/tests/test_stub.py

THE BARE `python3 dz_debug/tests/test_stub.py` ENTRY IS PRESERVED
-----------------------------------------------------------------
The original ended with `if __name__ == "__main__": unittest.main()`, so running the file directly
ran the test. That is behavior, and it is kept: with no arguments — or with any argument that is
not one of the seven commands listed above — this module hands straight to `unittest.main()`, so
`-v`, `-f`, and `TestDebugDecorator.test_decorator_returns_result` all still work exactly as they
did. The seven commands are the only additions, and `-h`/`--help` prints their usage rather than
unittest's. That entry needs a real `dz_debug` and an installed config, as the original needed a
real `dz_debug`; `selftest` is the one that needs nothing.

One further honest difference, forced by requirement 4 and affecting nothing the test asserts: the
subject is resolved when the test RUNS, not when the module is imported, because config resolution
has to be able to throw `ConfigError` rather than guess. So if `dz_debug` is missing, the original
fails at COLLECTION with an ImportError while this module fails on the test itself with a
`ConfigError`. Both are errors and neither is a pass; when `dz_debug` is present and configured,
the two are indistinguishable.
"""

import argparse
import ast
import contextlib
import functools
import hashlib
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
import unittest
from datetime import datetime

__all__ = [
    "TestDebugDecorator",
    "ConfigError",
    "ProofError",
    "config_template",
    "configure",
    "configured_decorator",
    "load_config",
    "reset_config",
    "using_config",
]

#: Environment variable naming a file that holds this unit's config object. It is specific to this
#: unit rather than a forge2-wide name because it names ONE unit's config object: a shared variable
#: could only ever point at one unit's object at a time. The sibling units read `DZ_DEBUG_CONFIG`
#: and `DZ_DEBUG_INIT_CONFIG`; none of the three collide.
CONFIG_ENV = "DZ_DEBUG_TEST_STUB_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: This distribution's top-level package, which ships `registry.json` as package data (see
#: pyproject.toml's `[tool.setuptools.package-data]`). Consulted only when the walk-up finds
#: nothing — the non-editable-install case (source 3 in the module docstring).
SHIPPING_PKG = "code__code__jazz__kokoro__dz_debug"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in the
#: config document, not a configurable setting — a config-driven module has to know which section
#: is its own.
UNIT_PATH = ("forge2", "code__code__jazz__kokoro__dz_debug", "dz_debug", "tests", "test_stub")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code__jazz__kokoro__dz_debug/dz_debug/tests/test_stub"

#: The git blob sha1 ticket #365 names for the original. ORIGINAL_SOURCE is checked against it
#: before the oracle is trusted.
ORIGINAL_BLOB_SHA1 = "ba528b6bf26d8f442129226008a6eea7296820c4"

#: The size in bytes ticket #365 names for the original. Checked alongside the sha1, so a mismatch
#: reports the useful number rather than only "the hash differs".
ORIGINAL_SIZE = 427

#: Every config key this test needs. Listed so `emit-config` and the missing-key error can name
#: them. There is exactly one, because the original hardcoded exactly one thing about `dz_debug` —
#: see "WHAT THE CONFIG CARRIES" in the module docstring.
REQUIRED_KEYS = ("decorator",)

# ── The test's own data and expectation. NOT config — see "WHAT THE CONFIG CARRIES" in the module
#    docstring. These are the original's literals, kept as literals on purpose, and
#    `check_literals()` proves each one against the original's own syntax tree. ──

#: The arguments the test calls its decorated helper with. The original's own `add(1, 2)`.
ADD_ARGS = (1, 2)

#: The value the test requires to come back. The original's own `3`. This is the EXPECTATION — the
#: one thing the test exists to check — so it is stated, exactly as the original stated it, and
#: never derived from ADD_ARGS: a test that computed its own expected answer would agree with
#: itself no matter what the subject did.
EXPECTED_SUM = 3

#: The name and parameters of the throwaway function the test decorates. The original's own
#: `def add(a, b)`. It belongs to the test, not to dz_debug.
HELPER_NAME = "add"
HELPER_PARAMS = ("a", "b")

#: The assertion the original used. `check_literals()` proves this module uses the same one — a
#: rewrite that swapped `assertEqual` for `assertIs` or `assertAlmostEqual` would be asking a
#: different question.
ASSERT_METHOD = "assertEqual"

#: The class and method the surface consists of, per ticket #365. `check_surface()` proves these
#: against the ORACLE's syntax tree rather than trusting the list.
TEST_CLASS_NAME = "TestDebugDecorator"
TEST_METHOD_NAME = "test_decorator_returns_result"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and ticket #365's acceptance item (d): a tool that cannot
    see its config throws rather than guessing a default.
    """


class ProofError(RuntimeError):
    """Raised when the equivalence proof itself cannot be trusted.

    Distinct from a proof that FAILS (which is reported as a verdict table and a non-zero exit):
    this means the machinery is broken — the embedded oracle does not hash to the blob the ticket
    names, say, or a sabotage's target string is not unique — so no verdict it produced would mean
    anything.
    """


# ─────────────────────────── the oracle: the original, embedded ───────────────────────────
#
# The original module's bytes, from ticket #365's ORIGINAL SOURCE block. This is DATA, not this
# module's source: it is the oracle the rewrite is measured against, and it is never imported as
# part of the package. `check_oracle()` proves it byte-identical to the forge blob before any
# verdict is drawn from it, so a transcription slip cannot silently become the standard.

ORIGINAL_SOURCE = '''\
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 testmonkeyalpha — Claude & Co.

import unittest
from dz_debug.logger import debug_decorator


class TestDebugDecorator(unittest.TestCase):
    def test_decorator_returns_result(self):
        @debug_decorator
        def add(a, b):
            return a + b

        result = add(1, 2)
        self.assertEqual(result, 3)


if __name__ == "__main__":
    unittest.main()
'''


def git_blob_sha1(data):
    """Return the git blob sha1 of `data`, the same identity `git cat-file blob` addresses."""
    header = ("blob %d\0" % len(data)).encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def check_oracle():
    """Prove the embedded original is the forge blob ticket #365 names; return its sha1.

    Raises:
        ProofError: if it is not, in which case nothing below it may be believed.
    """
    data = ORIGINAL_SOURCE.encode("utf-8")
    actual = git_blob_sha1(data)
    if actual != ORIGINAL_BLOB_SHA1 or len(data) != ORIGINAL_SIZE:
        raise ProofError(
            "the embedded ORIGINAL_SOURCE is not the module ticket #365 names: it is %d bytes with "
            "git blob sha1 %s, but the ticket names %d bytes with blob %s. The oracle cannot be "
            "trusted, so no equivalence verdict drawn from it means anything."
            % (len(data), actual, ORIGINAL_SIZE, ORIGINAL_BLOB_SHA1)
        )
    return actual


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None    # config object injected via configure(); wins over every disk source
_RESOLVED = None  # cache of the last disk resolution, so the test re-reads no files


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do the test throws. The `decorator` value is exactly what
    the ORIGINAL hardcoded — `check_literals()` proves it against the oracle's own import statement
    — so the proof below runs the rewrite on the original's own subject.
    """
    return {
        "decorator": "dz_debug.logger:debug_decorator",
        "bug_reports": "logs/bug_reports.jsonl",
    }


def _require(config, key):
    """Return `config[key]`, or raise ConfigError naming the key that is missing."""
    if not isinstance(config, dict):
        raise ConfigError("a config object must be a dict, not %s" % type(config).__name__)
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the required key %r. The required keys are: %s. Run "
            "`emit-config` for a template." % (UNIT, key, ", ".join(REQUIRED_KEYS))
        )
    return config[key]


def shipped_registry():
    """Return the path of the `registry.json` this distribution ships as package data, or None.

    Asks the installed `code__code__jazz__kokoro__dz_debug` package where it lives — the only way
    to find the registry from a NON-editable install, where it is not on any path above this file.
    Uses `find_spec` rather than importing: locating a file must not run a sibling package's code.
    Returns None rather than raising if the package is absent, so the caller can report the whole
    picture at once.
    """
    try:
        spec = importlib.util.find_spec(SHIPPING_PKG)
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    for location in spec.submodule_search_locations:
        candidate = os.path.join(location, REGISTRY_NAME)
        if os.path.isfile(candidate):
            return candidate
    return None


def _shipping_pkg_status():
    """One clause describing why the shipped-registry step found nothing, for the error."""
    try:
        spec = importlib.util.find_spec(SHIPPING_PKG)
    except (ImportError, ValueError):
        spec = None
    if spec is None or not spec.submodule_search_locations:
        return "the %s package is not importable, so it ships no registry either" % SHIPPING_PKG
    return "the %s package is at %s but has no %s in it" % (
        SHIPPING_PKG,
        list(spec.submodule_search_locations)[0],
        REGISTRY_NAME,
    )


def find_registry(start=None):
    """Return the registry path, or None if there is none to be found.

    Walks UP from `start` (default: this file's directory) first; if that finds nothing, falls back
    to the copy this distribution ships as package data. The walk-up wins when both exist, so a
    checkout's own registry is never shadowed by an installed one.
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
    return shipped_registry()


def _read_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise ConfigError("%s at %s could not be read as JSON: %s" % (what, path, exc)) from exc


def load_config(start=None):
    """Resolve this unit's config object from disk, ignoring any injected config.

    Returns a `(config, base, source)` triple: the config object, the directory relative paths
    inside it resolve against, and a human-readable description of where it came from. `start`
    overrides the directory the registry walk-up begins at.

    Raises:
        ConfigError: if no config object can be found, naming every source that was tried.
    """
    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        if not os.path.isfile(env_path):
            raise ConfigError("%s is set to %r, but no such file exists" % (CONFIG_ENV, env_path))
        config = _read_json(env_path, "the config object named by " + CONFIG_ENV)
        if not isinstance(config, dict):
            raise ConfigError(
                "the config object at %s must be a JSON object, not %s"
                % (env_path, type(config).__name__)
            )
        return (
            config,
            os.path.dirname(os.path.abspath(env_path)),
            "%s=%s" % (CONFIG_ENV, env_path),
        )

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s. All three sources were tried and none answered: (1) $%s is "
            "unset; (2) no %s was found by walking up from %s; (3) %s. Run `emit-config` for a "
            "template of the config object to install."
            % (
                UNIT,
                CONFIG_ENV,
                REGISTRY_NAME,
                os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))),
                _shipping_pkg_status(),
            )
        )

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. Run "
                "`emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH))
            )
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError(
            "the registry section %s at %s must be a JSON object, not %s"
            % (".".join(UNIT_PATH), registry_path, type(node).__name__)
        )

    config = {k: v for k, v in node.items() if not k.startswith("_comment")}
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit section
    # may state its own to override it. This is inheritance inside ONE config document, not a
    # guessed default — if neither states it, the key stays absent and the CLI files no report.
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

    `base` is the directory a relative `bug_reports` path resolves against, and defaults to the
    current working directory. Pass `None` as `config` to drop the injection and go back to
    resolving from disk. This takes effect immediately for every later run of the test: this module
    resolves its subject when the test RUNS, not at import.
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


# ─────────────────────────────── the subject under test ───────────────────────────────

def configured_decorator():
    """Return the `debug_decorator` named by the config's `decorator` key.

    The original hardcoded this as `from dz_debug.logger import debug_decorator`; #200 requirement
    4 is why it is a config key here. The value is a `"module:attr"` string.

    Raises:
        ConfigError: if there is no config, if the key is absent or malformed, or if the module or
            attribute it names cannot be reached. Every message names the key and what it expected,
            so a misconfiguration explains itself without a traceback.
    """
    spec = _require(active_config(), "decorator")
    if not isinstance(spec, str):
        raise ConfigError(
            "config key 'decorator' for %s must be a \"module:attr\" string, not %s"
            % (UNIT, type(spec).__name__)
        )
    if ":" not in spec:
        raise ConfigError(
            "config key 'decorator' for %s must look like \"module:attr\" (for example "
            "\"dz_debug.logger:debug_decorator\"); got %r" % (UNIT, spec)
        )
    module_name, _, attribute = spec.partition(":")
    module = sys.modules.get(module_name)
    if module is None:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise ConfigError(
                "config key 'decorator' for %s names %r, whose module %r cannot be imported: %s. "
                "The subject under test must be installed for this test to run."
                % (UNIT, spec, module_name, exc)
            ) from exc
    try:
        return getattr(module, attribute)
    except AttributeError as exc:
        raise ConfigError(
            "config key 'decorator' for %s names %r, but module %r has no attribute %r"
            % (UNIT, spec, module_name, attribute)
        ) from exc


# ─────────────────────────────── the test ───────────────────────────────

class TestDebugDecorator(unittest.TestCase):
    """The original's test case: `debug_decorator` must not disturb a return value.

    The class name and the method name below are ticket #365's stated callable surface, and
    `check_surface()` proves them against the original's own syntax tree.
    """

    def test_decorator_returns_result(self):
        """A decorated `add(1, 2)` still returns 3 — the decorator passes the result through.

        This is the original's one assertion, and it pins down its one property. The subject comes
        from the config rather than from a hardcoded import (#200 requirement 4); `add`, its
        arguments and the expected sum are the test's own, exactly as the original wrote them. See
        "THE ONE PROPERTY, AND THE HONEST LIMITS OF IT" in the module docstring for what this does
        and does not catch.
        """
        decorator = configured_decorator()

        @decorator
        def add(a, b):
            return a + b

        result = add(*ADD_ARGS)
        self.assertEqual(result, EXPECTED_SUM)


# ─────────────────────── reading the oracle's syntax tree ───────────────────────

def _const(node):
    """Return a literal node's value, or raise ProofError if it is not a literal."""
    if isinstance(node, ast.Constant):
        return node.value
    raise ProofError("expected a literal in the oracle, found %s" % type(node).__name__)


def oracle_facts():
    """Extract, from the ORACLE's syntax tree, every word this rewrite must reproduce.

    This is what closes the sweep's blind spot: the substrates do not care what the arguments are,
    so agreement with the oracle cannot by itself show the rewrite uses the oracle's own words.
    Parsing the oracle's own text can.

    Returns a dict with `subject` (the `module:attr` its import names), `helper` / `helper_params`
    (the function it decorates), `decorated_with` (the names it decorates that function with),
    `call_args` (what it calls it with), `assert_method` and `expected`.
    """
    check_oracle()
    tree = ast.parse(ORIGINAL_SOURCE)

    subject = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                subject = "%s:%s" % (node.module, alias.name)

    helper = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.decorator_list:
            helper = node
    if helper is None:
        raise ProofError("the oracle decorates no function; its subject cannot be located")
    decorated_with = tuple(d.id for d in helper.decorator_list if isinstance(d, ast.Name))

    call_args = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == helper.name
        ):
            call_args = tuple(_const(a) for a in node.args)

    assert_method = None
    expected = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            assert_method = node.func.attr
            expected = _const(node.args[1])

    return {
        "subject": subject,
        "helper": helper.name,
        "helper_params": tuple(a.arg for a in helper.args.args),
        "decorated_with": decorated_with,
        "call_args": call_args,
        "assert_method": assert_method,
        "expected": expected,
    }


def oracle_surface():
    """Return the oracle's callable surface as {"Class.method": (param, ...)}, from its AST."""
    check_oracle()
    tree = ast.parse(ORIGINAL_SOURCE)
    surface = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    surface["%s.%s" % (node.name, item.name)] = tuple(a.arg for a in item.args.args)
    return surface


def check_surface():
    """Prove this module presents the ORACLE's callable surface; return it.

    Reads the surface off the oracle's own syntax tree rather than off ticket #365's prose, then
    checks this module against it by reflection. Acceptance item (b).

    Raises:
        ProofError: if a name, a class, or a parameter list differs.
    """
    surface = oracle_surface()
    if not surface:
        raise ProofError("the oracle presents no class methods; the surface cannot be checked")
    for qualified, params in sorted(surface.items()):
        class_name, _, method_name = qualified.partition(".")
        cls = getattr(sys.modules[__name__], class_name, None)
        if cls is None:
            raise ProofError(
                "the oracle defines class %r but this module does not; existing callers of %s would "
                "break" % (class_name, qualified)
            )
        if not (isinstance(cls, type) and issubclass(cls, unittest.TestCase)):
            raise ProofError(
                "the oracle's %r is a unittest.TestCase; this module's is %r, which a test runner "
                "would not collect" % (class_name, cls)
            )
        method = getattr(cls, method_name, None)
        if method is None:
            raise ProofError(
                "the oracle defines %s but this module's %r has no %r; existing callers would break"
                % (qualified, class_name, method_name)
            )
        actual = tuple(inspect.signature(method).parameters)
        if actual != params:
            raise ProofError(
                "the oracle's %s takes %r; this module's takes %r" % (qualified, params, actual)
            )
    return surface


def _own_source():
    """Return this module's own source text, read from its file."""
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as handle:
        return handle.read()


def check_literals(config=None):
    """Prove this module's config and constants are the ORACLE'S OWN WORDS; return the facts.

    The equivalence sweep shows this rewrite asks the same KIND of question as the original. It
    cannot show it asks it with the same words, because the substrates are polymorphic in those
    words — a rewrite calling `add(10, 20)` and expecting `30` would agree with the original on
    every substrate. This closes that gap by reading the oracle's syntax tree.

    Args:
        config: the config object to check; defaults to `config_template()`, which is what an
            operator is told to install.

    Raises:
        ProofError: if any config value or module constant is not the original's own.
    """
    facts = oracle_facts()
    config = config_template() if config is None else config

    checks = (
        ("config key 'decorator'", config.get("decorator"), facts["subject"]),
        ("ADD_ARGS", ADD_ARGS, facts["call_args"]),
        ("EXPECTED_SUM", EXPECTED_SUM, facts["expected"]),
        ("HELPER_NAME", HELPER_NAME, facts["helper"]),
        ("HELPER_PARAMS", HELPER_PARAMS, facts["helper_params"]),
        ("ASSERT_METHOD", ASSERT_METHOD, facts["assert_method"]),
    )
    for what, mine, oracles in checks:
        if mine != oracles:
            raise ProofError(
                "%s is %r, but the ORIGINAL's own source says %r. This rewrite would be asking a "
                "different question from the one the original asked." % (what, mine, oracles)
            )

    # The surface names are ticket #365's prose; prove they are the oracle's too, from its tree.
    if "%s.%s" % (TEST_CLASS_NAME, TEST_METHOD_NAME) not in oracle_surface():
        raise ProofError(
            "TEST_CLASS_NAME/TEST_METHOD_NAME name %s.%s, which the ORIGINAL does not define"
            % (TEST_CLASS_NAME, TEST_METHOD_NAME)
        )

    # The helper must actually be decorated. The original's whole point is that `add` goes through
    # `debug_decorator`; a rewrite that quietly stopped decorating would still return 3.
    if not _own_decorator_names():
        raise ProofError(
            "this module's %s decorates nothing. The original decorated its helper with %s, and a "
            "test that does not decorate is not testing the decorator."
            % (TEST_CLASS_NAME, ", ".join(facts["decorated_with"]))
        )
    return facts


def _own_decorator_names():
    """Return every bare-name decorator used on a function inside this module's test class."""
    tree = ast.parse(_own_source())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == TEST_CLASS_NAME:
            for inner in ast.walk(node):
                if isinstance(inner, ast.FunctionDef):
                    names.extend(d.id for d in inner.decorator_list if isinstance(d, ast.Name))
    return names


# ─────────────────────────── the substrates and the mutants ───────────────────────────

#: Every substrate the sweep runs both modules against, as `(flaw, expectation, description)`.
#:
#: The expectation is what the ORIGINAL's single assertion can see, and it is the point of the
#: table — see "THE ONE PROPERTY, AND THE HONEST LIMITS OF IT" in the module docstring:
#:
#:   "conforming"  a correct debug_decorator. Both modules must PASS.
#:   "caught"      a flaw that breaks the one property the original pins down — the return value no
#:                 longer survives decoration. Both modules must FAIL/ERROR, identically, and
#:                 `equivalence()` fails if any of these is NOT caught: a mutant that slipped
#:                 through would mean the test has no teeth there.
#:   "blind"       a flaw the ORIGINAL cannot see, because its one assertion does not look. Both
#:                 modules must PASS. These are not filler: they are what proves this rewrite did
#:                 not ADD teeth the original lacked, which would be divergence too.
FLAWS = (
    (None, "conforming",
     "a conforming debug_decorator — records the call and returns the result unchanged"),

    ("returns_none", "caught",
     "the wrapper swallows the return value and returns None"),
    ("off_by_one", "caught",
     "the wrapper returns result + 1"),
    ("stringifies", "caught",
     "the wrapper returns str(result) — the right answer with the wrong type"),
    ("returns_bool", "caught",
     "the wrapper returns bool(result) — True, which is not 3"),
    ("returns_first_arg", "caught",
     "the wrapper returns its first argument instead of the call's result"),
    ("returns_wrapper", "caught",
     "the wrapper returns itself, the classic 'forgot to return result' slip"),
    ("drops_args", "caught",
     "the wrapper calls the function with no arguments at all (TypeError)"),
    ("returns_non_callable", "caught",
     "the decorator returns None, so the decorated name is not callable (TypeError)"),
    ("raises_on_decorate", "caught",
     "the decorator raises at decoration time, before any call (RuntimeError)"),

    ("no_logging", "blind",
     "a pure pass-through that records NOTHING — the original never checks that it logs"),
    ("swaps_args", "blind",
     "the wrapper calls add(2, 1); addition is commutative, so the sum is still 3"),
    ("logs_wrong_name", "blind",
     "it records the wrapper's name, not the wrapped function's — never asserted on"),
    ("logs_to_nowhere", "blind",
     "it records to a sink that is discarded — the original never inspects the record"),
    ("swallows_exceptions", "blind",
     "it returns None if the call raises; add(1, 2) never raises, so this never fires"),
    ("double_calls", "blind",
     "it calls the function twice and returns the second result — add has no side effects"),
)


def make_debug_decorator(flaw=None):
    """Build a `debug_decorator` for a substrate: conforming when `flaw` is None, else broken in
    exactly that one way. See FLAWS for what each does.

    The conforming decorator models what a real `dz_debug.logger.debug_decorator` does — wrap the
    function, record that the call happened, return the result untouched — which is the only part
    of it the original's assertion can observe.
    """
    record = []

    def debug_decorator(func):
        if flaw == "raises_on_decorate":
            raise RuntimeError("debug_decorator exploded at decoration time")
        if flaw == "returns_non_callable":
            return None

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if flaw == "logs_wrong_name":
                record.append(("wrapper", args, kwargs))
            elif flaw == "logs_to_nowhere":
                [].append((func.__name__, args, kwargs))
            elif flaw != "no_logging":
                record.append((func.__name__, args, kwargs))

            try:
                if flaw == "drops_args":
                    result = func()
                elif flaw == "swaps_args":
                    result = func(*tuple(reversed(args)), **kwargs)
                elif flaw == "double_calls":
                    func(*args, **kwargs)
                    result = func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
            except Exception:
                if flaw == "swallows_exceptions":
                    return None
                raise

            if flaw == "returns_none":
                return None
            if flaw == "off_by_one":
                return result + 1
            if flaw == "stringifies":
                return str(result)
            if flaw == "returns_bool":
                return bool(result)
            if flaw == "returns_first_arg":
                return args[0] if args else None
            if flaw == "returns_wrapper":
                return wrapper
            return result

        return wrapper

    debug_decorator.record = record
    return debug_decorator


#: The module name the ORACLE hardcodes its import against. The substrate installs itself here so
#: the oracle's own `from dz_debug.logger import debug_decorator` reaches it.
ORACLE_SUBJECT_MODULE = "dz_debug.logger"

#: A module name that has NOTHING to do with dz_debug, used by `config_drives_test()` to prove the
#: config is what chooses the subject. A hardcoded import cannot reach this.
PROBE_SUBJECT_MODULE = "_forge2_probe_logger"


@contextlib.contextmanager
def substrate(flaw=None, module_name=ORACLE_SUBJECT_MODULE):
    """Install a stand-in module at `module_name` whose `debug_decorator` carries `flaw`.

    Yields the `"module:attr"` spec naming the installed decorator, which is exactly what the
    config's `decorator` key holds — so the rewrite reaches the substrate through its config, while
    the oracle reaches the same object through its own hardcoded import. Both see one decorator.

    The modules are built in memory and `sys.modules` is restored on the way out, so one substrate
    cannot leak into the next. Dotted names get their parent packages built and linked, which is
    what makes `from dz_debug.logger import ...` resolve against a package that is not on disk.
    """
    parts = module_name.split(".")
    created = {}
    for depth in range(1, len(parts)):
        package = types.ModuleType(".".join(parts[:depth]))
        package.__path__ = []  # marks it a package, so a submodule may be imported beneath it
        created[".".join(parts[:depth])] = package
    leaf = types.ModuleType(module_name)
    leaf.debug_decorator = make_debug_decorator(flaw)
    created[module_name] = leaf
    for depth in range(1, len(parts)):
        setattr(created[".".join(parts[:depth])], parts[depth], created[".".join(parts[: depth + 1])])

    saved = {name: sys.modules.get(name) for name in created}
    sys.modules.update(created)
    try:
        yield "%s:debug_decorator" % module_name
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def load_oracle():
    """Import the embedded ORIGINAL as a module object and return it.

    The oracle does `from dz_debug.logger import debug_decorator` at import, so a substrate must
    already be installed when this is called — that is why it is called inside `substrate()`. The
    module is given a name other than `__main__`, so its own `unittest.main()` never fires.
    """
    check_oracle()
    module = types.ModuleType("_forge2_oracle_test_stub")
    module.__file__ = "<ORIGINAL_SOURCE of %s>" % UNIT
    exec(compile(ORIGINAL_SOURCE, module.__file__, "exec"), module.__dict__)
    return module


# ─────────────────────────────── the differential proof ───────────────────────────────

class _VerdictResult(unittest.TestResult):
    """A TestResult that keeps the exception TYPE, not just the rendered traceback.

    `unittest`'s own result stores failures as formatted text. A verdict of "fail" and a verdict of
    "fail:AssertionError" are not the same evidence, and the coarser one would let a rewrite that
    failed for a different reason look identical to the original.
    """

    def __init__(self):
        super().__init__()
        self.verdict = "pass"

    def addError(self, test, err):
        super().addError(test, err)
        self.verdict = "error:%s" % err[0].__name__

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.verdict = "fail:%s" % err[0].__name__


def run_case(module, class_name=TEST_CLASS_NAME, method_name=TEST_METHOD_NAME):
    """Run one test off `module` and return its verdict as a string.

    The SAME driver runs the oracle and the rewrite — it finds the class by name on each module and
    loads the method with `unittest`'s own loader, exactly as a real runner would. If the rewrite's
    surface did not match the oracle's, this could not drive both, so the surface claim is enforced
    here rather than merely asserted.

    A verdict is the outcome AND the exception type: "pass", "fail:AssertionError",
    "error:TypeError". A ConfigError shows up as "error:ConfigError", which is a verdict like any
    other — and one the oracle can never produce, so a rewrite that lost its config would be
    visibly different rather than quietly so.
    """
    cls = getattr(module, class_name)
    suite = unittest.TestLoader().loadTestsFromName(method_name, cls)
    result = _VerdictResult()
    suite.run(result)
    return result.verdict


def equivalence(verbose=False):
    """Run both modules against every substrate and compare their verdicts.

    Returns an `(ok, rows, problems)` triple: whether the proof holds, one row per substrate as
    `(flaw, expectation, oracle_verdict, rewrite_verdict, agree)`, and a list of prose complaints.

    The proof holds when:
      * the two modules AGREE on every substrate — the equivalence claim itself;
      * both PASS on the conforming substrate and on every "blind" one;
      * both REJECT every "caught" one — a mutant that slipped through would mean the test has no
        teeth there, and a toothless test agrees with everything.
    """
    check_oracle()
    rows = []
    problems = []

    for flaw, expectation, description in FLAWS:
        with substrate(flaw) as spec:
            oracle = load_oracle()
            oracle_verdict = run_case(oracle)
            with using_config({"decorator": spec}):
                rewrite_verdict = run_case(sys.modules[__name__])

        agree = oracle_verdict == rewrite_verdict
        rows.append((flaw, expectation, oracle_verdict, rewrite_verdict, agree))

        label = flaw or "(conforming)"
        if not agree:
            problems.append(
                "substrate %s: the ORIGINAL says %r but this rewrite says %r. They are not "
                "equivalent — %s." % (label, oracle_verdict, rewrite_verdict, description)
            )
        if expectation in ("conforming", "blind") and oracle_verdict != "pass":
            problems.append(
                "substrate %s is marked %r, which claims the original PASSES it, but the original "
                "says %r. The table is wrong about the original."
                % (label, expectation, oracle_verdict)
            )
        if expectation == "caught" and oracle_verdict == "pass":
            problems.append(
                "substrate %s is marked 'caught', but the original PASSES it — the test has no "
                "teeth against %s, so agreement here proves nothing." % (label, description)
            )

    if not any(row[1] == "caught" for row in rows):
        problems.append("no substrate is marked 'caught': this sweep could not fail.")

    ok = not problems
    if verbose:
        _print_table(rows)
        for problem in problems:
            print("PROBLEM: %s" % problem)
    return ok, rows, problems


def _print_table(rows):
    """Print the per-substrate verdict table."""
    width = max(len(r[0] or "(conforming)") for r in rows)
    header = ("%-*s  %-10s  %-24s  %-24s  %s"
              % (width, "SUBSTRATE", "ORIGINAL", "the original's verdict",
                 "this rewrite's verdict", "AGREE"))
    print(header)
    print("-" * len(header))
    for flaw, expectation, oracle_verdict, rewrite_verdict, agree in rows:
        print("%-*s  %-10s  %-24s  %-24s  %s"
              % (width, flaw or "(conforming)", expectation, oracle_verdict, rewrite_verdict,
                 "yes" if agree else "NO"))


def config_drives_test():
    """Prove the CONFIG is what chooses the subject, and that a missing key THROWS.

    Carrying a config key proves nothing on its own: a rewrite could read the config, ignore it,
    and import `dz_debug.logger` directly. Both halves below run with NO `dz_debug` in existence.

      * a config object with no `decorator` key must give `error:ConfigError` — acceptance item (d);
      * a config naming a decorator under `PROBE_SUBJECT_MODULE`, a name with nothing to do with
        dz_debug, must give `pass` — which is possible only if the config chose the subject. A
        hardcoded import gives `error:ModuleNotFoundError` here and cannot be made to pass.

    Returns an `(ok, rows)` pair, one row per half as `(what, expected, actual, ok)`.
    """
    rows = []

    # Half one: no key -> throw. Guard against a real dz_debug being importable in this
    # environment, which would be a different experiment entirely.
    saved = {name: sys.modules.pop(name, None)
             for name in ("dz_debug", ORACLE_SUBJECT_MODULE)}
    try:
        with using_config({}):
            verdict = run_case(sys.modules[__name__])
    finally:
        for name, previous in saved.items():
            if previous is not None:
                sys.modules[name] = previous
    rows.append(("a config object with no 'decorator' key", "error:ConfigError", verdict,
                 verdict == "error:ConfigError"))

    # Half two: the config points somewhere no hardcoded import could reach -> pass.
    with substrate(None, module_name=PROBE_SUBJECT_MODULE) as spec:
        saved = {name: sys.modules.pop(name, None)
                 for name in ("dz_debug", ORACLE_SUBJECT_MODULE)}
        try:
            with using_config({"decorator": spec}):
                verdict = run_case(sys.modules[__name__])
        finally:
            for name, previous in saved.items():
                if previous is not None:
                    sys.modules[name] = previous
    rows.append(("a config naming %r, with no dz_debug at all" % spec, "pass", verdict,
                 verdict == "pass"))

    return all(row[3] for row in rows), rows


# ─────────────────────────────── the config gate, proven ───────────────────────────────

def _gate_proof():
    """Prove the CLI reports a missing config as one self-explaining line. Acceptance item (d).

    Runs a COPY of this file, alone, in an empty temporary tree with `$DZ_DEBUG_TEST_STUB_CONFIG`
    unset — so no registry lies above it — and requires `show-config` to exit 2 with a ConfigError
    rather than guessing anything. A subprocess is the only honest way to check this: this process
    has already resolved a config.

    The child runs under `-S` (no site-packages), which is what makes the result independent of
    whether this package happens to be installed: an installed `code__code__jazz__kokoro__dz_debug`
    ships a registry, and finding it would be the module working correctly, not the gate failing.

    Returns an `(ok, detail)` pair.
    """
    root = tempfile.mkdtemp(prefix="forge2-gate-")
    try:
        copy = os.path.join(root, "test_stub.py")
        shutil.copyfile(os.path.abspath(__file__), copy)
        env = {k: v for k, v in os.environ.items() if k != CONFIG_ENV}
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-S", copy, "show-config"],
            cwd=root, env=env, capture_output=True, text=True,
        )
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 2:
            return False, ("expected exit 2 from an unconfigured `show-config`, got %d. Output: %s"
                           % (proc.returncode, output))
        if "no config object" not in output:
            return False, "exit 2, but the message does not explain itself: %s" % output
        if "Traceback" in output:
            return False, "the gate printed a traceback rather than a single line: %s" % output
        return True, output.splitlines()[0]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ─────────────────────────────── side-effect containment ───────────────────────────────

def _snapshot(directory):
    """Return the set of paths under `directory`, ignoring `__pycache__`.

    `__pycache__` is excluded because CPython writes `*.pyc` when it imports ANY module; that is the
    interpreter's doing, not this module's. Everything else that appears is this module's
    responsibility. See SIDE EFFECTS in the module docstring.
    """
    found = set()
    for base, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            found.add(os.path.join(base, name))
    return found


def _package_root():
    """Return the tree to watch for stray files: this package's root, else this file's directory.

    The package root is the nearest ancestor of THIS FILE holding `registry.json`, which in a
    checkout or an editable install is `code__code__jazz__kokoro__dz_debug/`. When there is none —
    a lone copy of this module in a temporary directory, which is exactly what `negative-control`
    and `_gate_proof` create — this file's own directory is the answer. Counting a fixed number of
    parents instead would make a lone copy in /tmp/x/ snapshot the whole of `/`.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    directory = here
    while True:
        if os.path.isfile(os.path.join(directory, REGISTRY_NAME)):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            return here
        directory = parent


# ─────────────────────────────── selftest ───────────────────────────────

def selftest():
    """Run the whole proof and return True if every part of it holds.

    The steps, in order, each printed with its verdict:
      1. the embedded oracle is the forge blob ticket #365 names;
      2. this module presents the oracle's callable surface (acceptance item b);
      3. this module's config and constants are the oracle's own words;
      4. the config is what chooses the subject, and a missing key throws (acceptance item d);
      5. the two modules agree on every substrate (acceptance item a);
      6. the CLI reports a missing config as one line, exit 2 (acceptance item d);
      7. nothing was created outside `__pycache__` while all of that ran.
    """
    before_pkg = _snapshot(_package_root())
    before_cwd = _snapshot(os.getcwd())
    ok = True

    print("=" * 96)
    print("SELFTEST: %s" % UNIT)
    print("=" * 96)

    print("\n[1] the embedded oracle IS the forge blob ticket #365 names")
    try:
        sha1 = check_oracle()
        print("    %d bytes, git blob sha1 %s == the ticket's -> OK"
              % (len(ORIGINAL_SOURCE.encode("utf-8")), sha1))
    except ProofError as exc:
        print("    FAIL: %s" % exc)
        return False  # nothing below this would mean anything

    print("\n[2] this module presents the ORIGINAL's callable surface (acceptance b)")
    try:
        for qualified, params in sorted(check_surface().items()):
            print("    %s(%s) -> present, same parameters -> OK" % (qualified, ", ".join(params)))
    except ProofError as exc:
        print("    FAIL: %s" % exc)
        ok = False

    print("\n[3] this module's config and constants are the ORIGINAL's own words")
    try:
        facts = check_literals()
        print("    config 'decorator' == the original's import %r -> OK" % facts["subject"])
        print("    ADD_ARGS == the original's call args %r -> OK" % (facts["call_args"],))
        print("    EXPECTED_SUM == the original's expected %r -> OK" % (facts["expected"],))
        print("    helper %s%r, decorated, asserted with %r -> OK"
              % (facts["helper"], facts["helper_params"], facts["assert_method"]))
    except ProofError as exc:
        print("    FAIL: %s" % exc)
        ok = False

    print("\n[4] the CONFIG is what chooses the subject, and a missing key THROWS (acceptance d)")
    try:
        drives_ok, drives_rows = config_drives_test()
        for what, expected, actual, row_ok in drives_rows:
            print("    %-52s -> %-22s %s" % (what, actual, "OK" if row_ok else
                                             "FAIL (expected %s)" % expected))
        if not drives_ok:
            ok = False
    except ProofError as exc:
        print("    FAIL: %s" % exc)
        ok = False

    print("\n[5] the ORIGINAL and this rewrite agree on every substrate (acceptance a)")
    try:
        agreed, rows, problems = equivalence()
        _print_table(rows)
        caught = sum(1 for r in rows if r[1] == "caught")
        blind = sum(1 for r in rows if r[1] == "blind")
        print("    %d substrates: 1 conforming, %d the original CATCHES (both reject identically), "
              "%d it is BLIND to (both pass)." % (len(rows), caught, blind))
        if agreed:
            print("    every verdict agrees -> OK")
        else:
            for problem in problems:
                print("    FAIL: %s" % problem)
            ok = False
    except ProofError as exc:
        print("    FAIL: the proof machinery is broken: %s" % exc)
        ok = False

    print("\n[6] the CLI reports a missing config as one line, exit 2 (acceptance d)")
    gate_ok, detail = _gate_proof()
    if gate_ok:
        print("    a lone copy in an empty tree, $%s unset: exit 2, no traceback -> OK" % CONFIG_ENV)
        print("    %s" % detail)
    else:
        print("    FAIL: %s" % detail)
        ok = False

    print("\n[7] nothing was created (outside __pycache__, which CPython writes for any import)")
    new_pkg = _snapshot(_package_root()) - before_pkg
    new_cwd = _snapshot(os.getcwd()) - before_cwd
    if new_pkg or new_cwd:
        for path in sorted(new_pkg | new_cwd):
            print("    FAIL: this run created %s" % path)
        ok = False
    else:
        print("    watched %s and %s: unchanged -> OK" % (_package_root(), os.getcwd()))

    print("\n" + "=" * 96)
    print("SELFTEST: %s" % ("PASS" if ok else "FAIL"))
    print("=" * 96)
    return ok


# ─────────────────────────────── the negative control ───────────────────────────────

#: `negative_control()` edits this module's own text. The sabotage tables below QUOTE fragments of
#: the code they edit, so a count over the whole file would find every fragment at least twice and
#: the uniqueness guard would refuse to run. `_code_region()` splits the file here — everything
#: above this marker is code, everything from it down is the tables that talk about the code — and
#: the guard counts, and the edit applies, in the code region only.
#:
#: The marker is this section's own header comment, whose first occurrence in the file is that
#: header rather than this line, because the header is written above it.
CODE_REGION_END = "# ─────────────────────────────── the negative control ───"

#: Sabotages that MUST break `selftest`. Each is a `(name, old, new, why)`, where `old` occurs
#: EXACTLY once in the code region — `negative_control()` raises ProofError otherwise, so a
#: sabotage can never silently strike the embedded oracle instead of the code under test.
SABOTAGES = (
    ("drop the assertion",
     "        result = add(*ADD_ARGS)\n        self.assertEqual(result, EXPECTED_SUM)",
     "        result = add(*ADD_ARGS)\n        del result",
     "a test that asserts nothing agrees with every mutant; the sweep must notice it has no teeth"),

    ("invert the assertion",
     "self.assertEqual(result, EXPECTED_SUM)",
     "self.assertNotEqual(result, EXPECTED_SUM)",
     "asking the opposite question must diverge from the original on the conforming substrate"),

    ("change the expectation",
     "EXPECTED_SUM = 3",
     "EXPECTED_SUM = 4",
     "expecting 4 is not what the original expected; the sweep and check_literals must both say so"),

    ("change the test data",
     "ADD_ARGS = (1, 2)",
     "ADD_ARGS = (2, 3)",
     "the original called add(1, 2); check_literals must reject data the original never used"),

    ("mis-implement the helper",
     "        @decorator\n        def add(a, b):\n            return a + b",
     "        @decorator\n        def add(a, b):\n            return a * b",
     "a helper that multiplies returns 2, not 3, and must diverge on the conforming substrate"),

    ("stop decorating the helper",
     "        @decorator\n        def add(a, b):\n            return a + b",
     "        def add(a, b):\n            return a + b",
     "a test that never applies the decorator is not testing the decorator, and must stop noticing "
     "every mutant"),

    ("mis-state the oracle's sha1",
     'ORIGINAL_BLOB_SHA1 = "ba528b6bf26d8f442129226008a6eea7296820c4"',
     'ORIGINAL_BLOB_SHA1 = "0000000000000000000000000000000000000000"',
     "an unverified oracle is not an oracle; check_oracle must refuse to proceed"),

    ("hardcode the subject, ignoring the config",
     "        decorator = configured_decorator()",
     "        from dz_debug.logger import debug_decorator as decorator",
     "reverting to the original's hardcoded import defeats #200 requirement 4; config_drives_test "
     "must notice the config is no longer what chooses the subject"),
)

#: Honest refactors that must NOT break `selftest`. Same shape as SABOTAGES. Without these, a proof
#: that merely rejected every edit would look just as green as one that measures behavior.
REFACTORS = (
    ("rename a local variable",
     "        result = add(*ADD_ARGS)\n        self.assertEqual(result, EXPECTED_SUM)",
     "        outcome = add(*ADD_ARGS)\n        self.assertEqual(outcome, EXPECTED_SUM)",
     "the name of a local is spelling, not behavior"),

    ("split an expression into a temporary",
     "        @decorator\n        def add(a, b):\n            return a + b",
     "        @decorator\n        def add(a, b):\n            total = a + b\n            return total",
     "the helper still returns the sum; how it gets there is spelling, not behavior"),
)


def _code_region(source):
    """Split `source` into (code, tables) at CODE_REGION_END. See that constant for why.

    Raises:
        ProofError: if the marker is missing, which would mean the split is silently wrong.
    """
    index = source.find(CODE_REGION_END)
    if index == -1:
        raise ProofError(
            "this module has no %r marker, so its code region cannot be told apart from the "
            "sabotage tables that quote it, and no sabotage's uniqueness could be trusted."
            % CODE_REGION_END
        )
    return source[:index], source[index:]


def _apply_edit(source, label, name, old, new):
    """Return `source` with `old` replaced by `new` in the code region; prove `old` is unique.

    Raises:
        ProofError: if `old` does not occur exactly once in the code region, or if the edit is a
            no-op. Either would make the case's verdict meaningless.
    """
    code, tables = _code_region(source)
    occurrences = code.count(old)
    if occurrences != 1:
        raise ProofError(
            "the %s %r targets a string that occurs %d times in this module's code region, not "
            "exactly once. It could strike the wrong place, and its verdict would mean nothing."
            % (label, name, occurrences)
        )
    edited = code.replace(old, new, 1) + tables
    if edited == source:
        raise ProofError("the %s %r changes nothing" % (label, name))
    return edited


def _run_selftest_copy(source, root):
    """Write `source` as a lone module in `root` and run its `selftest`; return (rc, output).

    The copy is ALONE in its tree and runs under `-S`, which is also what proves this file needs no
    sibling, no registry and no install to run its own proof.
    """
    copy = os.path.join(root, "test_stub.py")
    with open(copy, "w", encoding="utf-8") as handle:
        handle.write(source)
    env = {k: v for k, v in os.environ.items() if k != CONFIG_ENV}
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, "-S", copy, "selftest"],
        cwd=root, env=env, capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def negative_control(verbose=True):
    """Sabotage this module in throwaway copies and check `selftest` notices. Return True if so.

    A proof that cannot fail is not a proof. This breaks the module eight ways that MUST be caught,
    and refactors it two ways that must NOT be — the second half is what shows the proof measures
    behavior rather than spelling.

    Every copy is written under a temporary directory that is removed afterwards.
    """
    source = _own_source()
    ok = True

    print("=" * 96)
    print("NEGATIVE CONTROL: %s" % UNIT)
    print("=" * 96)
    print("\nEach row rewrites this module in a throwaway copy and runs THAT copy's `selftest`.")
    print("A sabotage selftest does not notice is a hole in the proof; a refactor it rejects means")
    print("the proof is measuring spelling rather than behavior.\n")

    root = tempfile.mkdtemp(prefix="forge2-negctl-")
    try:
        for label, cases, must_break in (("SABOTAGE", SABOTAGES, True),
                                         ("REFACTOR", REFACTORS, False)):
            for name, old, new, why in cases:
                edited = _apply_edit(source, label, name, old, new)
                case_root = os.path.join(root, "%s-%s" % (label.lower(), name.replace(" ", "-")))
                os.makedirs(case_root, exist_ok=True)
                rc, output = _run_selftest_copy(edited, case_root)
                noticed = rc != 0

                if must_break and not noticed:
                    print("  %s %-42s NOT NOTICED  <- HOLE IN THE PROOF" % (label, name))
                    print("      %s" % why)
                    ok = False
                elif must_break:
                    print("  %s %-42s noticed (exit %d)" % (label, name, rc))
                elif noticed:
                    print("  %s %-42s BROKE IT (exit %d)  <- proof is measuring spelling"
                          % (label, name, rc))
                    print("      %s" % why)
                    if verbose:
                        print("      " + "\n      ".join(output.strip().splitlines()[-8:]))
                    ok = False
                else:
                    print("  %s %-42s survives, as it must" % (label, name))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n" + "=" * 96)
    print("NEGATIVE CONTROL: %s — %d sabotages must break selftest, %d refactors must not"
          % ("PASS" if ok else "FAIL", len(SABOTAGES), len(REFACTORS)))
    print("=" * 96)
    return ok


# ─────────────────────────────── the bug report ───────────────────────────────

def file_bug_report(function_name, exc, reproduce):
    """Append one timestamped JSON bug report, per `note-for-claude`; return its path or None.

    `note-for-claude` requires "all tools need to pass a bug-report automatically (timestamped if an
    exception is thrown): Filename - function name - time of occurance - methods to reproduce -
    possible cause." Every one of those fields is below.

    This fires only for an UNEXPECTED exception — a defect in this module. A `ConfigError` is
    designed behavior, not a bug, and files nothing. Returns None if the config names no
    `bug_reports` path or if it cannot be written, because failing to file a report must not become
    a second, louder failure.
    """
    try:
        config = active_config()
        base = active_base()
    except ConfigError:
        return None
    target = config.get("bug_reports")
    if not target:
        return None
    path = target if os.path.isabs(target) else os.path.join(base, target)
    report = {
        "filename": os.path.abspath(__file__),
        "unit": UNIT,
        "function": function_name,
        "time": datetime.now().astimezone().isoformat(),
        "exception": "%s: %s" % (type(exc).__name__, exc),
        "reproduce": reproduce,
        "possible_cause": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )[-2000:],
    }
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(report) + "\n")
    except OSError:
        return None
    return path


# ─────────────────────────────── the command line ───────────────────────────────

#: The commands this module adds. Anything else — including nothing at all — is handed to
#: `unittest.main()`, which is what the ORIGINAL's `if __name__ == "__main__"` did. See "THE BARE
#: `python3 dz_debug/tests/test_stub.py` ENTRY IS PRESERVED" in the module docstring.
COMMANDS = (
    "selftest",
    "equivalence",
    "negative-control",
    "oracle-literals",
    "show-oracle",
    "emit-config",
    "show-config",
)


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="test_stub.py",
        description=(
            "The forge2 rewrite of %s. With NO arguments, or with any argument that is not one of "
            "the commands below, this hands to unittest.main() exactly as the original did — so "
            "`-v` and `TestDebugDecorator.test_decorator_returns_result` still work. The commands "
            "below are the additions; every one of them except `show-config` runs with no dz_debug "
            "installed and no config on disk." % UNIT
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.add_parser("selftest", help="run the whole proof: oracle, surface, literals, config gate, "
                                    "equivalence, side effects")
    sub.add_parser("equivalence", help="print the per-substrate verdict table")
    sub.add_parser("negative-control", help="sabotage this module in throwaway copies and check "
                                            "selftest notices")
    sub.add_parser("oracle-literals", help="print what the original hardcoded")
    sub.add_parser("show-oracle", help="print the embedded original")
    sub.add_parser("emit-config", help="print a config-object template")
    sub.add_parser("show-config", help="print the resolved config object and where it came from")
    return parser


def main(argv=None):
    """Run the CLI. Returns a process exit code.

    Exit codes: 0 success; 1 a proof or a test failed; 2 a ConfigError — the #200 requirement-4
    gate, reported as one self-explaining line and never a traceback.
    """
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] in ("-h", "--help"):
        _build_parser().print_help()
        return 0

    if not argv or argv[0] not in COMMANDS:
        # The ORIGINAL's own `if __name__ == "__main__": unittest.main()`, preserved in behavior:
        # everything is handed to unittest, flags and test names alike.
        outcome = unittest.main(module=sys.modules[__name__], argv=[sys.argv[0]] + argv, exit=False)
        return 0 if outcome.result.wasSuccessful() else 1

    args = _build_parser().parse_args(argv)
    try:
        if args.command == "selftest":
            return 0 if selftest() else 1

        if args.command == "equivalence":
            ok, _rows, _problems = equivalence(verbose=True)
            return 0 if ok else 1

        if args.command == "negative-control":
            return 0 if negative_control() else 1

        if args.command == "oracle-literals":
            facts = oracle_facts()
            print("What the ORIGINAL (%s, blob %s) hardcoded:\n" % (UNIT, ORIGINAL_BLOB_SHA1))
            print("  subject imported : %s" % facts["subject"])
            print("     -> the config key 'decorator' must reproduce this")
            print("  helper decorated : %s%r, decorated with %s"
                  % (facts["helper"], facts["helper_params"], ", ".join(facts["decorated_with"])))
            print("  called with      : %r    -> module constant ADD_ARGS" % (facts["call_args"],))
            print("  asserted         : self.%s(result, %r)    -> module constant EXPECTED_SUM"
                  % (facts["assert_method"], facts["expected"]))
            print("\nThe subject is the only one of these the config carries: it is the only thing")
            print("the original took from dz_debug. The rest is the test's own data and its")
            print("expectation — see WHAT THE CONFIG CARRIES in the module docstring.")
            return 0

        if args.command == "show-oracle":
            check_oracle()
            sys.stdout.write(ORIGINAL_SOURCE)
            return 0

        if args.command == "emit-config":
            print("# The config object for %s." % UNIT)
            print("# Install it in registry.json at: %s" % " -> ".join(UNIT_PATH))
            print("# Or save it to a file and point $%s at that file." % CONFIG_ENV)
            print(json.dumps(config_template(), indent=2, sort_keys=True))
            return 0

        if args.command == "show-config":
            config = active_config()
            print("source : %s" % active_source())
            print("base   : %s" % active_base())
            print("config : %s" % json.dumps(config, indent=2, sort_keys=True))
            missing = [k for k in REQUIRED_KEYS if k not in config]
            if missing:
                raise ConfigError(
                    "the config object for %s is missing: %s. Run `emit-config` for a template."
                    % (UNIT, ", ".join(missing))
                )
            print("\nevery required key is present: %s" % ", ".join(REQUIRED_KEYS))
            return 0

    except ConfigError as exc:
        # Designed behavior, not a defect: one line, no traceback, no bug report.
        sys.stderr.write("test_stub.py: %s\n" % exc)
        return 2
    except Exception as exc:  # a defect in THIS module — note-for-claude requires a report
        report = file_bug_report(
            function_name=args.command,
            exc=exc,
            reproduce="python3 %s %s" % (os.path.abspath(__file__), args.command),
        )
        sys.stderr.write("test_stub.py: unexpected %s: %s\n" % (type(exc).__name__, exc))
        if report:
            sys.stderr.write("test_stub.py: bug report appended to %s\n" % report)
        raise

    return 0


if __name__ == "__main__":
    sys.exit(main())
