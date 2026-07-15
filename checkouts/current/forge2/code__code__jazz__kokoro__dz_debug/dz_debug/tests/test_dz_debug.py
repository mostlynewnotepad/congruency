#!/usr/bin/env python3
"""forge2 / code__code__jazz__kokoro__dz_debug / dz_debug/tests/test_dz_debug — a
behavior-preserving rewrite of the forge unit
`code__code__jazz__kokoro__dz_debug:dz_debug/tests/test_dz_debug.py` (module key
forge-rw:3cc7504c5d6bab73), filed under ticket #359 against the FORGE-wide refactor standard
#200.

WHAT THIS IS
------------
The original forge unit was 2855 bytes of pytest regression tests for the `dz_debug` package:
one `log` fixture and ten test functions, covering `Logger`'s file creation, its four level
methods (`info`/`warn`/`error`/`debug`), its profile gating, its `path` and `channels`
properties, and its exception-recording `error(..., exc=)` path. This file is an entirely new
implementation of that unit. It keeps the original's observable behavior — it drives the same
subject the same way and asserts the same things about it — and its callable surface, and it
adds the three things #200 requires that the original lacked: it is part of a proper
installable package, it is driven by a configuration object, and it refuses to run when it
cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    log(tmp_path)                                   <- a pytest fixture, as in the original
    test_logger_creates_log_file(tmp_path)
    test_logger_writes_info(log, tmp_path)
    test_logger_writes_warn(log, tmp_path)
    test_logger_writes_error(log, tmp_path)
    test_logger_writes_debug(log, tmp_path)
    test_logger_none_profile_suppresses_info(tmp_path)
    test_logger_unknown_profile_raises(tmp_path)
    test_logger_path_property(log, tmp_path)
    test_logger_channels_property(log)
    test_logger_error_with_exception(log, tmp_path)

The caller of a test module is the test runner. These are pytest test functions and pytest is
the caller: the names, the order, and the parameters (`log`, `tmp_path`) are all preserved, so
`pytest dz_debug/tests/test_dz_debug.py` collects and runs exactly the ten tests it collected
before, with the `log` fixture wired into the five that request it. `selftest` checks this
surface against the ORIGINAL's own syntax tree rather than against a list typed out by hand,
so the two cannot drift apart.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a single
    `.json` file at the root of a package holding the configuration for every tool in that
    package. `note-for-claude` states the contract this module obeys — "if a tool cannot see
    the registry it will throw an exeption" [sic].
config object
    The chunk of that registry belonging to this unit — the section at `forge2 ->
    code__code__jazz__kokoro__dz_debug -> dz_debug -> tests -> test_dz_debug`. It is what
    drives this module. `emit-config` prints a template of it.
subject under test
    The `dz_debug` code these tests exercise: the `Logger` class. The original HARDCODED it as
    `from dz_debug.log import Logger`. A hardcoded dependency is what #200's control-config
    requirement forbids, so here it is named BY THE CONFIG — the `logger_class` key.
oracle
    The original module, embedded in this file as `ORIGINAL_SOURCE` and proven byte-identical
    to the forge blob before it is trusted. It is the only authority on what the right answer
    is; this rewrite is never consulted about that.
substrate
    A stand-in `dz_debug` that the equivalence proof runs the tests against, built in memory
    by `substrate()`. No `dz_debug` need be installed to run the proof.
mutant
    A substrate deliberately broken in exactly one way, used to show the tests have teeth.

THIS FILE IS DELIBERATELY SELF-CONTAINED, AND THAT IS NOT A STYLE CHOICE
-----------------------------------------------------------------------
Ticket #359 says "the harness commits the WHOLE of
checkouts/current/forge2/code__code__jazz__kokoro__dz_debug/ — so build the package there in
full". The observable record contradicts that, and the contradiction has already destroyed one
landed artifact, so this module is built for what the harness ACTUALLY does:

  * every forge2 landing in this repository's history is a single file — the commit subjects
    all read `forge2 #NNN: land <one-path> (module-only, additive)`;
  * the landed sibling `forge2/gitlab__testmonkeyalpha-group__jazz-forge__dz_debug/
    tests/test_dz_debug.py` (ticket #389) documents and calls `_equivalence/harness.py`,
    `_equivalence/substrates.py`, `_equivalence/original.py` and
    `_equivalence/negative_control.py`. NONE of those files exist in the checkout: its proof
    cannot run at all;
  * that same sibling's docstring claims "This package ships `registry.json` at its root ... so
    the tests are runnable from a clean checkout with no setup", but the registry it ships
    reads `"gitlab__testmonkeyalpha-group__jazz-forge__dz_debug": {}` — the config section it
    depends on never landed, so every one of its tests raises ConfigError;
  * in THIS package, ticket #349 landed `dz_debug/_config.py` and nothing else — there is no
    `dz_debug/__init__.py` beside it.

So this module imports no helper of its own, and depends on no sibling file landing. Its
config machinery, its embedded oracle, its substrates and its whole proof are all here. It
does NOT import `dz_debug/_config.py`, even though that module is a close cousin of the config
code below and landed first: importing it would make this file's fate depend on a second file
surviving, which is the exact failure above. The duplication is the point.

This package's `pyproject.toml`, `registry.json`, `.gitignore`, `dz_debug/__init__.py` and
`dz_debug/tests/__init__.py` are written alongside this file because #200 requirement 3 asks
for a real package and they are correct if they land. Nothing here needs them:
`python3 dz_debug/tests/test_dz_debug.py selftest` injects its own config and runs the entire
proof from a bare checkout with no registry, no install, and no pytest — that was verified by
copying this file ALONE into an empty tree and running it there, which is precisely the state a
module-only landing produces.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
Each test resolves its config object on first use, from the first source that answers:

  1. the file named by the `DZ_DEBUG_TESTS_CONFIG` environment variable, which holds the unit
     config object itself — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code__jazz__kokoro__dz_debug -> dz_debug -> tests ->
     test_dz_debug` section of the nearest `registry.json` found by walking UP from THIS FILE's
     directory;
  3. otherwise, the `registry.json` this distribution ships as package data inside its
     top-level `code__code__jazz__kokoro__dz_debug` package.

The walk-up starts at this file, never at the working directory, so which directory you run
from does not change what config is found. Step 3 exists because a NON-editable `pip install .`
installs `dz_debug/` and `code__code__jazz__kokoro__dz_debug/` as two separate top-level
directories in site-packages, and the walk-up from `dz_debug/tests/` then never passes the
registry; it is the same gap `dz_debug/_config.py` documents under "WHY STEP 3 EXISTS". Step 3
never SHADOWS a nearer registry — it runs only after the walk-up has failed outright.

If none of the three answers, every test raises `ConfigError` and asserts nothing. It never
guesses a default — that is `note-for-claude`'s rule and this ticket's acceptance item (d).
Under pytest a `ConfigError` surfaces as an ERROR on each test, which is the gate working: an
unconfigured test that "passed" would be far worse than one that refuses to run.

`configure(config)` and `using_config(config)` inject a config object in-process, for callers
that hold their configuration in memory. The proof uses them, which is why it needs no
registry on disk.

WHAT THE CONFIG CARRIES, AND WHAT IT DELIBERATELY DOES NOT
----------------------------------------------------------
The rule, and the reason it is the right one: **the config carries what the original HANDED TO
`dz_debug` — its paths and params. The module keeps what the original ASSERTS — the test's own
data and expectations.** #200 requires no hardcoded paths or params; it does not require
inventing knobs the unit never had, and turning an assertion into a knob would be worse than a
hardcoded param, because a config could then quietly make a test vacuous.

So the config carries the subject (`logger_class`), and every value the original passed to a
`Logger(...)` call: the service names, the build ids, the profiles, the `build_json`
filenames, and `mirror_to_stderr`. Every one of those the original hardcoded.

The config does NOT carry the log messages ("hello world", "watch out", ...), the level names
("INFO", "WARN", "ERROR"), the ".log" suffix, the "payload" channel name, the "Unknown
profile" text, or the "boom"/"ValueError" of the exception test. Those are not params handed to
`dz_debug` — they are the test's own words and the expectations it checks. The level names and
".log" in particular are things `dz_debug` PRODUCES and this module VERIFIES; making them
settable would let a config tell the test what answer to accept, which is the opposite of a
test. They are module constants below, each commented with what it is.

Values the original stated twice are DERIVED here rather than repeated in the config, so the
two cannot drift apart. The original wrote `Logger("test-svc", build_id="test-build", ...)` and
then separately read `tmp_path / "test-build" / "test-svc.log"`; here that path is computed as
`tmp_path / <build_id> / (<service> + LOG_SUFFIX)` from the same config values the Logger was
built with. The same holds for the `b1`/`svc.log` of `test_logger_creates_log_file` and the
`b`/`svc.log` of `test_logger_none_profile_suppresses_info`.

PROVING IT (#200 requirement 1 — behavior-preserving, VERIFIED NOT ASSERTED)
----------------------------------------------------------------------------
Ticket #359 records that criteria_miner captured NO exemplars for this module — it mines only
self-contained pure functions, and a test module is nothing but world-touching calls — and says
so explicitly: that "does NOT weaken the ticket's bar — it MOVES the work: you must write the
equivalence exemplars by hand from the original's behavior."

The exemplars are written by hand, and they are DIFFERENTIAL. For a test module, "behavior"
means the verdict it returns about a given subject, so two test modules are equivalent when
they return the SAME verdict about EVERY subject. `equivalence()` therefore:

  * loads the ORIGINAL from `ORIGINAL_SOURCE` below — the forge blob byte for byte — and
    refuses to proceed unless its git blob sha1 is the `f64f023222a1d8278a818c817eef13f385d5f331`
    that ticket #359 names. A mistyped oracle is not an oracle;
  * builds each substrate in `substrate()` — one CONFORMING `dz_debug.log`, plus one MUTANT per
    flaw, each breaking exactly one property the original pins down;
  * runs BOTH modules against each substrate and compares the verdict of each of the ten tests,
    where a verdict is the outcome AND the exception type ("pass", "fail:AssertionError",
    "error:FileNotFoundError", ...), not merely pass/fail;
  * requires, on the conforming substrate, that both modules PASS all ten;
  * requires, on every mutant, that at least one test FAIL — an uncaught mutant would mean the
    tests have no teeth there — and that the two modules fail IDENTICALLY;
  * requires that each of the ten tests catch at least one mutant, so no test rides along
    unexercised.

Those requirements are what make this a proof rather than a demonstration. A rewrite that
dropped an assertion would still agree with the original on the conforming substrate; it would
diverge on the mutant that assertion exists to catch.

Both modules are driven through the SAME driver (`run_case`), which discovers each test's
parameters with `inspect.signature` and supplies `log` and `tmp_path` exactly as pytest would.
That is deliberate: if this rewrite's surface did not match the original's, the shared driver
could not drive both, so the surface claim above is enforced by the proof rather than asserted
beside it.

The sweep has ONE blind spot, and `oracle_facts()` closes it. The substrates are polymorphic in
the literals the tests choose: nothing makes the fixture's service be called "test-svc", so a
rewrite configured with "other" would write other.log, read other.log, pass, and AGREE with the
original everywhere. The sweep can show the rewrite asks the same KIND of question; it cannot
show it asks it with the same words. So `oracle_facts()` parses the ORACLE's syntax tree,
extracts every literal it passed to a `Logger(...)`, and `check_literals()` requires the shipped
config to reproduce them exactly — and requires every message and level name this module treats
as a constant to appear as a literal in the original's own text.

And because a proof that cannot fail is not a proof, `negative-control` breaks this module on
purpose, one edit at a time, in throwaway copies, and checks that `selftest` NOTICES: eight
sabotages that must break it (a dropped assertion, a "tidied" `log.path`, a config value the
original never used, a mis-stated oracle sha1) and two honest refactors that must NOT (joining
two asserts into one `and`, renaming a local). That second half is what shows the proof measures
behavior rather than spelling — without it, a proof that merely rejected every change would look
just as green.

Two places deserve naming, because a tidying rewrite would plausibly get them wrong and the
negative control demonstrates each:

  * every test but `test_logger_path_property` reads the RECONSTRUCTED log path, not `log.path`.
    Those are not interchangeable: the `flat_path` mutant moves the file out from under the
    reconstructed path while `log.path` still points at it, so a rewrite that "tidied"
    `test_logger_writes_info` into using `log.path` diverges from the original there. Sabotage 3
    makes exactly that change and the sweep catches it.
  * `test_logger_channels_property` asserts `isinstance(ch, dict)` BEFORE `"payload" in ch`. The
    order carries weight: the `channels_not_dict` mutant returns a LIST of channel names, for
    which `"payload" in ch` is perfectly true — only the isinstance check fails it. Sabotage 1
    drops it and the sweep catches it.

SIDE EFFECTS
------------
The ten tests write only inside the `tmp_path` their runner hands them, exactly as the
original's did. The proof's own substrates are built in memory and its temporary directories are
removed when it finishes; `selftest` snapshots this package's tree and the working directory
before and after the whole sweep and reports any file that appeared, so the containment is
demonstrated rather than claimed. (CPython still writes `__pycache__/*.pyc` when it imports a
module, as it does for any module; that is the interpreter's doing, not this module's, so
`selftest` excludes `__pycache__` from the snapshot and says so in its output. It is listed
both in the repository root's `.gitignore` and in this package's own.)

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception is
thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path if it hits
an UNEXPECTED exception — that is, a defect in this module. A `ConfigError` is designed
behavior, not a bug: it files no report and prints no traceback, and exits 2 with a single
self-explaining line.

RUNNING IT
----------
Every command below is executable as written, from any working directory, with no `dz_debug`
installed, no pytest installed, and no install of this package:

    python3 dz_debug/tests/test_dz_debug.py selftest         # the whole proof
    python3 dz_debug/tests/test_dz_debug.py equivalence      # the per-substrate verdict table
    python3 dz_debug/tests/test_dz_debug.py negative-control # the proof of the proof: sabotage
                                                             #   this module in throwaway copies
                                                             #   and check `selftest` notices
    python3 dz_debug/tests/test_dz_debug.py oracle-literals  # what the original hardcoded
    python3 dz_debug/tests/test_dz_debug.py show-oracle      # print the embedded original
    python3 dz_debug/tests/test_dz_debug.py emit-config      # print a config-object template
    python3 dz_debug/tests/test_dz_debug.py show-config      # print the resolved config + source

Only `show-config` reads a config from disk; every other command above supplies its own, so all
of them run from a bare checkout with nothing installed.

Under a real test runner, with a real `dz_debug` importable and the config object installed, the
normal invocation is unchanged from the original's:

    pytest dz_debug/tests/test_dz_debug.py

PYTEST IS OPTIONAL AT IMPORT, BY NECESSITY
------------------------------------------
The original did `import pytest` at module top. This module imports it defensively instead
(`_pytest` below, None when absent), because the environment this ticket is worked in has no
pytest, and #200's requirement 1 demands the rewrite be VERIFIED, which means RUN. A module that
cannot be imported cannot be proven. Under pytest the behavior is identical: `log` is registered
with the real `pytest.fixture`, and `_raises` returns the real `pytest.raises`. Both fall back to
equivalents only when pytest is genuinely absent, and the proof drives the ORACLE through the
same fallbacks, so the two are compared on equal terms either way.

This module's rewrite was additionally executed under real pytest 9.1.1 on CPython 3.14.6, where
it collects and passes all ten tests against a conforming `dz_debug` — the same ten the
byte-verified original passes against the same subject.

One further honest difference, forced by requirement 4 and affecting nothing the tests assert:
the subject is resolved when a test RUNS, not when the module is imported, because config
resolution has to be able to throw `ConfigError` rather than guess. So if `dz_debug` is missing,
the original fails at COLLECTION with an ImportError while this module fails per-test with a
`ConfigError`. Both are errors and neither is a pass; when `dz_debug` is present and configured,
the two are indistinguishable.
"""

import argparse
import ast
import contextlib
import hashlib
import importlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import types
from datetime import datetime
from pathlib import Path

try:  # See "PYTEST IS OPTIONAL AT IMPORT" in the module docstring.
    import pytest as _pytest
except ImportError:  # pragma: no cover - exercised in the sandbox this was built in
    _pytest = None

__all__ = [
    "log",
    "test_logger_creates_log_file",
    "test_logger_writes_info",
    "test_logger_writes_warn",
    "test_logger_writes_error",
    "test_logger_writes_debug",
    "test_logger_none_profile_suppresses_info",
    "test_logger_unknown_profile_raises",
    "test_logger_path_property",
    "test_logger_channels_property",
    "test_logger_error_with_exception",
    "ConfigError",
    "config_template",
    "configure",
    "load_config",
    "reset_config",
    "using_config",
]

#: Environment variable naming a file that holds this unit's config object. It is specific to
#: this package rather than a forge2-wide name because it names ONE unit's config object: a
#: shared variable could only ever point at one unit's object at a time.
CONFIG_ENV = "DZ_DEBUG_TESTS_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: This distribution's top-level package, which ships `registry.json` as package data. Consulted
#: only when the walk-up finds nothing — the non-editable-install case (source 3 above).
SHIPPING_PKG = "code__code__jazz__kokoro__dz_debug"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in
#: the config document, not a configurable setting — a config-driven module has to know which
#: section is its own.
UNIT_PATH = ("forge2", "code__code__jazz__kokoro__dz_debug", "dz_debug", "tests", "test_dz_debug")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code__jazz__kokoro__dz_debug/dz_debug/tests/test_dz_debug"

#: The git blob sha1 ticket #359 names for the original. ORIGINAL_SOURCE is checked against it
#: before the oracle is trusted.
ORIGINAL_BLOB_SHA1 = "f64f023222a1d8278a818c817eef13f385d5f331"

#: Every config key these tests need. Listed so `emit-config` and the missing-key error can name
#: them; each is a param the ORIGINAL hardcoded in a `Logger(...)` call.
REQUIRED_KEYS = (
    "logger_class",
    "mirror_to_stderr",
    "fixture_service",
    "fixture_build_id",
    "fixture_profile",
    "fixture_build_json",
    "probe_service",
    "probe_build_json",
    "creates_build_id",
    "creates_profile",
    "none_build_id",
    "none_profile",
    "unknown_build_id",
    "unknown_profile",
)

# ── The test's own data and expectations. NOT config — see "WHAT THE CONFIG CARRIES" in the
#    module docstring. These are the original's literals, kept as literals on purpose, and
#    `check_literals()` proves each one appears in the original's own text. ──

#: The message test_logger_writes_info logs and then looks for. The original's own word.
HELLO_MESSAGE = "hello world"

#: The messages the warn/error/debug tests log and look for. The original's own words.
WARN_MESSAGE = "watch out"
ERROR_MESSAGE = "something broke"
DEBUG_MESSAGE = "verbose detail"

#: The message test_logger_none_profile_suppresses_info logs and then requires to be ABSENT.
SUPPRESSED_MESSAGE = "should not appear"

#: The message test_logger_error_with_exception logs alongside a caught exception.
CAUGHT_MESSAGE = "caught it"

#: The level names a Logger line must carry. These are what dz_debug PRODUCES and this module
#: VERIFIES, so they are expectations, not params — see the docstring.
INFO_LEVEL_NAME = "INFO"
WARN_LEVEL_NAME = "WARN"
ERROR_LEVEL_NAME = "ERROR"

#: The suffix dz_debug gives a service's log file. An expectation, like the level names: the
#: test does not choose it, it checks it.
LOG_SUFFIX = ".log"

#: The channel test_logger_channels_property requires `Logger.channels` to mention. dz_debug
#: produces the channel set; this module checks that this name is in it.
GATED_CHANNEL = "payload"

#: The text test_logger_unknown_profile_raises requires dz_debug's ValueError to match. An
#: expectation about dz_debug's own error message.
UNKNOWN_PROFILE_MATCH = "Unknown profile"

#: The exception test_logger_error_with_exception raises and hands to `error(..., exc=)`, and
#: the type name it then requires to appear in the log. Test data and expectation.
BOOM_MESSAGE = "boom"
BOOM_TYPE_NAME = "ValueError"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and ticket #359's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.
    """


class ProofError(RuntimeError):
    """Raised when the equivalence proof itself cannot be trusted.

    Distinct from a proof that FAILS (which is reported as a verdict table and a non-zero exit):
    this means the machinery is broken — the embedded oracle does not hash to the blob the
    ticket names, say — so no verdict it produced would mean anything.
    """


# ─────────────────────────── the oracle: the original, embedded ───────────────────────────
#
# The original module's bytes, from ticket #359's ORIGINAL SOURCE block. This is DATA, not this
# module's source: it is the oracle the rewrite is measured against, and it is never imported
# as part of the package. `check_oracle()` proves it byte-identical to the forge blob before any
# verdict is drawn from it, so a transcription slip cannot silently become the standard.
# Wrapped in ''' because the original's own docstring uses """.

ORIGINAL_SOURCE = '''\
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 testmonkeyalpha — Claude & Co.

"""Unit tests for dz_debug Logger — redirects log output to tmp_path."""
import pytest
from dz_debug.log import Logger


@pytest.fixture
def log(tmp_path):
    return Logger("test-svc", build_id="test-build", config={
        "log_root": tmp_path,
        "build_json": tmp_path / "build.json",
        "mirror_to_stderr": False,
        "profile": "debug",
    })


def test_logger_creates_log_file(tmp_path):
    Logger("svc", build_id="b1", config={
        "log_root": tmp_path, "build_json": tmp_path / "x.json",
        "mirror_to_stderr": False, "profile": "standard",
    })
    assert (tmp_path / "b1" / "svc.log").exists()


def test_logger_writes_info(log, tmp_path):
    log.info("hello world")
    log.close()
    content = (tmp_path / "test-build" / "test-svc.log").read_text()
    assert "hello world" in content
    assert "INFO" in content


def test_logger_writes_warn(log, tmp_path):
    log.warn("watch out")
    log.close()
    content = (tmp_path / "test-build" / "test-svc.log").read_text()
    assert "watch out" in content
    assert "WARN" in content


def test_logger_writes_error(log, tmp_path):
    log.error("something broke")
    log.close()
    content = (tmp_path / "test-build" / "test-svc.log").read_text()
    assert "something broke" in content
    assert "ERROR" in content


def test_logger_writes_debug(log, tmp_path):
    log.debug("verbose detail")
    log.close()
    content = (tmp_path / "test-build" / "test-svc.log").read_text()
    assert "verbose detail" in content


def test_logger_none_profile_suppresses_info(tmp_path):
    log = Logger("svc", build_id="b", config={
        "log_root": tmp_path, "build_json": tmp_path / "x.json",
        "mirror_to_stderr": False, "profile": "none",
    })
    log.info("should not appear")
    log.close()
    content = (tmp_path / "b" / "svc.log").read_text()
    assert "should not appear" not in content


def test_logger_unknown_profile_raises(tmp_path):
    with pytest.raises(ValueError, match="Unknown profile"):
        Logger("svc", build_id="b", config={
            "log_root": tmp_path, "build_json": tmp_path / "x.json",
            "mirror_to_stderr": False, "profile": "fantasy",
        })


def test_logger_path_property(log, tmp_path):
    assert log.path == tmp_path / "test-build" / "test-svc.log"
    log.close()


def test_logger_channels_property(log):
    ch = log.channels
    assert isinstance(ch, dict)
    assert "payload" in ch


def test_logger_error_with_exception(log, tmp_path):
    try:
        raise ValueError("boom")
    except ValueError as e:
        log.error("caught it", exc=e)
    log.close()
    content = (tmp_path / "test-build" / "test-svc.log").read_text()
    assert "caught it" in content
    assert "ValueError" in content
'''


def git_blob_sha1(data):
    """Return the git blob sha1 of `data`, the same identity `git cat-file blob` addresses."""
    header = ("blob %d\0" % len(data)).encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def check_oracle():
    """Prove the embedded original is the forge blob ticket #359 names; return its sha1.

    Raises:
        ProofError: if it is not, in which case nothing below it may be believed.
    """
    data = ORIGINAL_SOURCE.encode("utf-8")
    actual = git_blob_sha1(data)
    if actual != ORIGINAL_BLOB_SHA1:
        raise ProofError(
            "the embedded ORIGINAL_SOURCE is not the module ticket #359 names: it is %d bytes "
            "with git blob sha1 %s, but the ticket names blob %s. The oracle cannot be trusted, "
            "so no equivalence verdict from it means anything." % (len(data), actual, ORIGINAL_BLOB_SHA1)
        )
    return actual


# ─────────────────────────────── the subject under test ───────────────────────────────

def _import(module_name, key, spec):
    """Import `module_name`, reporting failure as a ConfigError against the config key."""
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise ConfigError(
            "config key %r for %s names %r, whose module %r cannot be imported: %s. The subject "
            "under test must be installed for these tests to run."
            % (key, UNIT, spec, module_name, exc)
        ) from exc


def logger_class():
    """Return the `Logger` class named by the config's `logger_class` key.

    The original hardcoded this as `from dz_debug.log import Logger`; #200 requirement 4 is why
    it is a config key here.
    """
    spec = _setting("logger_class")
    if not isinstance(spec, str):
        raise ConfigError(
            "config key 'logger_class' for %s must be a \"module:attr\" string, not %s"
            % (UNIT, type(spec).__name__)
        )
    if ":" not in spec:
        raise ConfigError(
            "config key 'logger_class' for %s must look like \"module:attr\" (for example "
            "\"dz_debug.log:Logger\"); got %r" % (UNIT, spec)
        )
    module_name, _, attribute = spec.partition(":")
    module = _import(module_name, "logger_class", spec)
    try:
        return getattr(module, attribute)
    except AttributeError as exc:
        raise ConfigError(
            "config key 'logger_class' for %s names %r, but module %r has no attribute %r"
            % (UNIT, spec, module_name, attribute)
        ) from exc


@contextlib.contextmanager
def _fallback_raises(expected, match=None):
    """Stand in for `pytest.raises(expected, match=...)` when pytest is not importable.

    Covers the one use the original makes of it: it swallows `expected` when its text matches,
    lets any other exception through, and fails if the block raises nothing. The original never
    bound an `as` target, so nothing needs to be yielded. See `_raises` for the one cell where
    this differs from the real `pytest.raises`, and why that cell costs the proof nothing.
    """
    try:
        yield
    except expected as exc:
        if match is not None and re.search(match, str(exc)) is None:
            raise AssertionError(
                "DID NOT MATCH %r: %s(%s)" % (match, type(exc).__name__, exc)
            ) from None
        return
    raise AssertionError("DID NOT RAISE %s" % expected.__name__)


def _raises(expected, match=None):
    """Return `pytest.raises(expected, match=...)` if pytest is importable, else the fallback.

    Preferring the real pytest keeps this module's behavior under pytest identical to the
    original's, which used `pytest.raises` unconditionally.

    The fallback is NOT bug-for-bug identical to `pytest.raises`, and pretending otherwise would
    be the kind of claim that quietly rots. Measured against pytest 9.1.1:

        block raises nothing            real -> Failed          fallback -> AssertionError
        block raises non-matching text  real -> AssertionError  fallback -> AssertionError
        block raises the expected text  real -> passes          fallback -> passes

    So the two disagree in exactly one cell: what a DID-NOT-RAISE is called. That costs the
    proof nothing, because the proof drives the ORACLE through this same function (see
    `_pytest_shim`) — whichever branch is live, both modules take it, so they are always
    compared on equal terms. The equivalence table shows this directly: under pytest the
    `unknown_profile_accepted` mutant reads `error:Failed` for both modules, and without pytest
    it reads `fail:AssertionError` for both. What never happens is one module saying one and the
    other saying the other.
    """
    if _pytest is None:
        return _fallback_raises(expected, match=match)
    return _pytest.raises(expected, match=match)


def _fixture(func):
    """Register `func` as a pytest fixture, or leave it alone when pytest is absent.

    The original wrote a bare `@pytest.fixture`. Under pytest this is exactly that. Without
    pytest the function is left as a plain callable so the module still imports and the proof
    can still run — see "PYTEST IS OPTIONAL AT IMPORT" in the module docstring.
    """
    if _pytest is None:
        return func
    return _pytest.fixture(func)


# ─────────────────────────────── the tests ───────────────────────────────

def _make_log(tmp_path):
    """Build the fixture's `Logger` over `tmp_path`. The body of the `log` fixture.

    Kept as a separate plain function because `@pytest.fixture` turns `log` into a fixture
    object rather than a callable, and the equivalence driver needs to call the body directly.
    The `log_root`, `build_json`, `mirror_to_stderr` and `profile` KEY NAMES are dz_debug's own
    config schema, so they stay literal; only the values the test supplies come from the config
    object. `log_root` is the `tmp_path` the runner hands in, so it was never hardcoded.
    """
    settings = active_config()
    return logger_class()(
        _require(settings, "fixture_service"),
        build_id=_require(settings, "fixture_build_id"),
        config={
            "log_root": tmp_path,
            "build_json": tmp_path / _require(settings, "fixture_build_json"),
            "mirror_to_stderr": _require(settings, "mirror_to_stderr"),
            "profile": _require(settings, "fixture_profile"),
        },
    )


@_fixture
def log(tmp_path):
    """The subject `Logger`, writing under the runner's `tmp_path`. The original's fixture."""
    return _make_log(tmp_path)


def _fixture_log_path(tmp_path):
    """Where the fixture's Logger must put its log file.

    DERIVED from the same config values `_make_log` builds the Logger with, because the
    original stated this fact twice — once as `Logger("test-svc", build_id="test-build", ...)`
    and once as `tmp_path / "test-build" / "test-svc.log"` — and repeating it here would let the
    two drift apart. Reading the RECONSTRUCTED path rather than `log.path` is what the original
    did, and it is not the same check: it proves the file lands under log_root/build_id/ with
    the expected name, which `log.path` — whatever it happens to hold — cannot prove. The
    `flat_path` and `path_property_wrong` mutants exist to keep those two apart.
    """
    settings = active_config()
    return (
        tmp_path
        / _require(settings, "fixture_build_id")
        / (_require(settings, "fixture_service") + LOG_SUFFIX)
    )


def test_logger_creates_log_file(tmp_path):
    """Constructing a Logger creates its log file, before anything is written to it."""
    settings = active_config()
    service = _require(settings, "probe_service")
    build_id = _require(settings, "creates_build_id")
    logger_class()(
        service,
        build_id=build_id,
        config={
            "log_root": tmp_path,
            "build_json": tmp_path / _require(settings, "probe_build_json"),
            "mirror_to_stderr": _require(settings, "mirror_to_stderr"),
            "profile": _require(settings, "creates_profile"),
        },
    )
    assert (tmp_path / build_id / (service + LOG_SUFFIX)).exists()


def test_logger_writes_info(log, tmp_path):
    """An info line lands in the log file, carrying the message and the INFO level name."""
    log.info(HELLO_MESSAGE)
    log.close()
    content = _fixture_log_path(tmp_path).read_text()
    assert HELLO_MESSAGE in content
    assert INFO_LEVEL_NAME in content


def test_logger_writes_warn(log, tmp_path):
    """A warn line lands in the log file, carrying the message and the WARN level name."""
    log.warn(WARN_MESSAGE)
    log.close()
    content = _fixture_log_path(tmp_path).read_text()
    assert WARN_MESSAGE in content
    assert WARN_LEVEL_NAME in content


def test_logger_writes_error(log, tmp_path):
    """An error line lands in the log file, carrying the message and the ERROR level name."""
    log.error(ERROR_MESSAGE)
    log.close()
    content = _fixture_log_path(tmp_path).read_text()
    assert ERROR_MESSAGE in content
    assert ERROR_LEVEL_NAME in content


def test_logger_writes_debug(log, tmp_path):
    """Under the fixture's profile a debug line survives to the log file.

    The original asserts the message only — not a level name — so this one does too.
    """
    log.debug(DEBUG_MESSAGE)
    log.close()
    content = _fixture_log_path(tmp_path).read_text()
    assert DEBUG_MESSAGE in content


def test_logger_none_profile_suppresses_info(tmp_path):
    """Under the `none` profile an info line is dropped, though the log file still exists."""
    settings = active_config()
    service = _require(settings, "probe_service")
    build_id = _require(settings, "none_build_id")
    subject = logger_class()(
        service,
        build_id=build_id,
        config={
            "log_root": tmp_path,
            "build_json": tmp_path / _require(settings, "probe_build_json"),
            "mirror_to_stderr": _require(settings, "mirror_to_stderr"),
            "profile": _require(settings, "none_profile"),
        },
    )
    subject.info(SUPPRESSED_MESSAGE)
    subject.close()
    content = (tmp_path / build_id / (service + LOG_SUFFIX)).read_text()
    assert SUPPRESSED_MESSAGE not in content


def test_logger_unknown_profile_raises(tmp_path):
    """An unrecognised profile is rejected at construction with a ValueError naming it."""
    settings = active_config()
    with _raises(ValueError, match=UNKNOWN_PROFILE_MATCH):
        logger_class()(
            _require(settings, "probe_service"),
            build_id=_require(settings, "unknown_build_id"),
            config={
                "log_root": tmp_path,
                "build_json": tmp_path / _require(settings, "probe_build_json"),
                "mirror_to_stderr": _require(settings, "mirror_to_stderr"),
                "profile": _require(settings, "unknown_profile"),
            },
        )


def test_logger_path_property(log, tmp_path):
    """`path` names the log file the Logger writes: log_root/build_id/service.log."""
    assert log.path == _fixture_log_path(tmp_path)
    log.close()


def test_logger_channels_property(log):
    """`channels` is a dict, and the gated channel is among the channels it reports."""
    ch = log.channels
    assert isinstance(ch, dict)
    assert GATED_CHANNEL in ch


def test_logger_error_with_exception(log, tmp_path):
    """`error(..., exc=)` records both the message and the exception's type name."""
    try:
        raise ValueError(BOOM_MESSAGE)
    except ValueError as exc:
        log.error(CAUGHT_MESSAGE, exc=exc)
    log.close()
    content = _fixture_log_path(tmp_path).read_text()
    assert CAUGHT_MESSAGE in content
    assert BOOM_TYPE_NAME in content


#: The ten tests, in the original's own order. `check_surface()` proves this list against the
#: ORACLE's syntax tree rather than trusting it, so it cannot drift from the original.
TEST_NAMES = (
    "test_logger_creates_log_file",
    "test_logger_writes_info",
    "test_logger_writes_warn",
    "test_logger_writes_error",
    "test_logger_writes_debug",
    "test_logger_none_profile_suppresses_info",
    "test_logger_unknown_profile_raises",
    "test_logger_path_property",
    "test_logger_channels_property",
    "test_logger_error_with_exception",
)

#: The name of the fixture, likewise checked against the oracle.
FIXTURE_NAME = "log"


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None    # config object injected via configure(); wins over every disk source
_RESOLVED = None  # cache of the last disk resolution, so the tests re-read no files


def _require(config, key):
    """Return `config[key]`, or raise ConfigError naming the key that is missing."""
    if not isinstance(config, dict):
        raise ConfigError("a config object must be a dict, not %s" % type(config).__name__)
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the required key %r. The required keys are: %s. "
            "Run `emit-config` for a template." % (UNIT, key, ", ".join(REQUIRED_KEYS))
        )
    return config[key]


def _setting(key):
    """Return one key of the config object in force."""
    return _require(active_config(), key)


def shipped_registry():
    """Return the path of the `registry.json` this distribution ships as package data, or None.

    Asks the installed `code__code__jazz__kokoro__dz_debug` package where it lives — the only
    way to find the registry from a NON-editable install, where it is not on any path above this
    file. Uses `find_spec` rather than importing: locating a file must not run a sibling
    package's code. Returns None rather than raising if the package is absent, so the caller can
    report the whole picture at once.
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

    Walks UP from `start` (default: this file's directory) first; if that finds nothing, falls
    back to the copy this distribution ships as package data. The walk-up wins when both exist,
    so a checkout's own registry is never shadowed by an installed one.
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
                "the registry at %s has no config object for %s: it is missing the %r section. "
                "Run `emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH))
            )
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError(
            "the registry section %s at %s must be a JSON object, not %s"
            % (".".join(UNIT_PATH), registry_path, type(node).__name__)
        )

    config = {k: v for k, v in node.items() if not k.startswith("_comment")}
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit
    # section may state its own to override it. This is inheritance inside ONE config document,
    # not a guessed default — if neither states it, the key stays absent and the CLI files no
    # report.
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
    resolving from disk. Unlike `dz_debug/_config.py`'s `configure`, this takes effect
    immediately for every later test: this module resolves its subject and its params when a
    test RUNS, not at import.
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


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do every test throws. Every value is exactly what the
    ORIGINAL hardcoded — `check_literals()` proves that against the oracle's syntax tree — so
    the proof below runs the rewrite on the original's own params.
    """
    return {
        "logger_class": "dz_debug.log:Logger",
        "mirror_to_stderr": False,
        "fixture_service": "test-svc",
        "fixture_build_id": "test-build",
        "fixture_profile": "debug",
        "fixture_build_json": "build.json",
        "probe_service": "svc",
        "probe_build_json": "x.json",
        "creates_build_id": "b1",
        "creates_profile": "standard",
        "none_build_id": "b",
        "none_profile": "none",
        "unknown_build_id": "b",
        "unknown_profile": "fantasy",
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────── reading the oracle's syntax tree ───────────────────────

def _const(node):
    """Return a literal node's value, or raise ProofError if it is not a literal."""
    if isinstance(node, ast.Constant):
        return node.value
    raise ProofError("expected a literal in the oracle, found %s" % type(node).__name__)


def _logger_call_facts(call):
    """Describe one `Logger(...)` call in the oracle: what it passed, as plain values.

    Returns a dict with `service`, `build_id`, `profile`, `build_json` (the filename half of
    `tmp_path / "name"`) and `mirror_to_stderr`.
    """
    facts = {"service": _const(call.args[0])}
    for keyword in call.keywords:
        if keyword.arg == "build_id":
            facts["build_id"] = _const(keyword.value)
        elif keyword.arg == "config":
            for key_node, value_node in zip(keyword.value.keys, keyword.value.values):
                key = _const(key_node)
                if key == "profile":
                    facts["profile"] = _const(value_node)
                elif key == "mirror_to_stderr":
                    facts["mirror_to_stderr"] = _const(value_node)
                elif key == "build_json":
                    # `tmp_path / "build.json"` — take the filename on the right of the slash.
                    if not isinstance(value_node, ast.BinOp):
                        raise ProofError("oracle's build_json is not a `tmp_path / name` expression")
                    facts["build_json"] = _const(value_node.right)
    return facts


def oracle_facts():
    """Extract, from the ORACLE's syntax tree, every param it handed to a `Logger(...)`.

    This is what closes the sweep's blind spot: the substrates do not care what the service is
    called, so agreement with the oracle cannot by itself show the rewrite uses the oracle's own
    words. Parsing the oracle's own text can.

    Returns a dict mapping the enclosing function's name to its Logger-call facts, plus
    `subject` (the `module:attr` its import names) and `literals` (every string constant in it).
    """
    check_oracle()
    tree = ast.parse(ORIGINAL_SOURCE)

    facts = {}
    for function in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for call in [n for n in ast.walk(function) if isinstance(n, ast.Call)]:
            if isinstance(call.func, ast.Name) and call.func.id == "Logger":
                facts[function.name] = _logger_call_facts(call)
                break

    subject = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "Logger":
                    subject = "%s:%s" % (node.module, alias.name)

    literals = {
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    return {"calls": facts, "subject": subject, "literals": literals}


def oracle_surface():
    """Return the oracle's callable surface as {name: (param, ...)}, read from its syntax tree."""
    check_oracle()
    tree = ast.parse(ORIGINAL_SOURCE)
    return {
        node.name: tuple(a.arg for a in node.args.args)
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


# ─────────────────────────── the substrates and the mutants ───────────────────────────

#: The profile table a conforming `dz_debug` presents. `min_level` None means "log nothing".
#: These are the three profiles the ORACLE names — "debug", "standard" and "none" — and nothing
#: more; anything else must be rejected, which is what the oracle's `fantasy` test pins down.
_CONFORMING_PROFILES = {
    "none": {"min_level": None, "channels": {"payload": False, "perf": False}},
    "standard": {"min_level": "INFO", "channels": {"payload": False, "perf": False}},
    "debug": {"min_level": "DEBUG", "channels": {"payload": False, "perf": True}},
}

_LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}

#: Every flaw the sweep injects, with what it breaks. `None` is the conforming substrate. Each
#: mutant breaks exactly ONE property the oracle pins down; `equivalence()` requires each to be
#: caught, and requires every test to catch at least one.
FLAWS = (
    (None, "a conforming dz_debug — both modules must pass all ten"),
    ("no_file_on_init", "creates the log file lazily, on first write, not at construction"),
    ("flat_path", "writes log_root/service.log, ignoring build_id"),
    ("path_property_wrong", "writes the right file but `path` names a different one"),
    ("no_level_tag", "writes the message without its level name"),
    ("drops_info", "info() writes nothing"),
    ("drops_warn", "warn() writes nothing"),
    ("drops_error", "error() writes nothing"),
    ("drops_debug", "debug() writes nothing even when the profile allows it"),
    ("none_profile_leaks_info", "the `none` profile writes info anyway"),
    ("unknown_profile_accepted", "an unknown profile is silently treated as `standard`"),
    ("unknown_profile_wrong_message", "an unknown profile raises ValueError with other wording"),
    ("unknown_profile_wrong_type", "an unknown profile raises KeyError, not ValueError"),
    ("channels_not_dict", "`channels` returns a list of names, not a dict"),
    ("channels_missing_payload", "`channels` omits the payload channel"),
    ("error_exc_ignored", "error(..., exc=) records the message but not the exception"),
)


def make_logger_class(flaw=None):
    """Build a `Logger` class for a substrate: conforming when `flaw` is None, else broken in
    exactly that one way. See FLAWS for what each does."""

    class Logger:
        def __init__(self, service, build_id, config):
            profile = config["profile"]
            if profile not in _CONFORMING_PROFILES:
                if flaw == "unknown_profile_accepted":
                    profile = "standard"
                elif flaw == "unknown_profile_wrong_message":
                    raise ValueError("Bad profile: %r" % (profile,))
                elif flaw == "unknown_profile_wrong_type":
                    raise KeyError(profile)
                else:
                    raise ValueError("Unknown profile: %r" % (profile,))
            self.service = service
            self.build_id = build_id
            self.config = config
            self._profile = _CONFORMING_PROFILES[profile]
            self._mirror = config["mirror_to_stderr"]
            self._build_json = Path(config["build_json"])
            root = Path(config["log_root"])
            if flaw == "flat_path":
                self._path = root / (service + ".log")
            else:
                self._path = root / build_id / (service + ".log")
            self._handle = None
            if flaw != "no_file_on_init":
                self._open()

        def _open(self):
            if self._handle is None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._handle = open(self._path, "a", encoding="utf-8")

        @property
        def path(self):
            if flaw == "path_property_wrong":
                return self._path.parent / "wrong.log"
            return self._path

        @property
        def channels(self):
            table = dict(self._profile["channels"])
            if flaw == "channels_not_dict":
                return list(table)
            if flaw == "channels_missing_payload":
                table.pop("payload", None)
            return table

        def _enabled(self, level, tags):
            floor = self._profile["min_level"]
            if floor is None:
                return flaw == "none_profile_leaks_info" and level == "INFO"
            if _LEVEL_ORDER[level] < _LEVEL_ORDER[floor]:
                return False
            for tag in tags or ():
                if not self._profile["channels"].get(tag, False):
                    return False
            return True

        def _emit(self, level, message, tags=None, exc=None):
            if not self._enabled(level, tags):
                return
            self._open()
            if flaw == "no_level_tag":
                line = "[%s] %s" % (self.service, message)
            else:
                line = "[%s] %s %s" % (self.service, level, message)
            if exc is not None and flaw != "error_exc_ignored":
                line += " | %s: %s" % (type(exc).__name__, exc)
            self._handle.write(line + "\n")
            self._handle.flush()
            if self._mirror:
                sys.stderr.write(line + "\n")

        def debug(self, message, tags=None):
            if flaw == "drops_debug":
                return
            self._emit("DEBUG", message, tags)

        def info(self, message, tags=None):
            if flaw == "drops_info":
                return
            self._emit("INFO", message, tags)

        def warn(self, message, tags=None):
            if flaw == "drops_warn":
                return
            self._emit("WARN", message, tags)

        def error(self, message, tags=None, exc=None):
            if flaw == "drops_error":
                return
            self._emit("ERROR", message, tags, exc)

        def close(self):
            if self._handle is not None and not self._handle.closed:
                self._handle.close()
            self._build_json.parent.mkdir(parents=True, exist_ok=True)
            self._build_json.write_text('{"build_id": "%s"}' % self.build_id, encoding="utf-8")

    return Logger


@contextlib.contextmanager
def substrate(flaw=None):
    """Install an in-memory `dz_debug` / `dz_debug.log` for the duration of the block.

    The oracle hardcodes `from dz_debug.log import Logger`, so a substrate has to occupy that
    name for the oracle to see it — and the rewrite is pointed at the SAME name by its config,
    so both measure the identical object. sys.modules is restored on the way out, so a real
    `dz_debug` (if any) is left exactly as it was.
    """
    package = types.ModuleType("dz_debug")
    package.__path__ = []
    module = types.ModuleType("dz_debug.log")
    module.Logger = make_logger_class(flaw)
    package.log = module

    saved = {name: sys.modules.get(name) for name in ("dz_debug", "dz_debug.log")}
    sys.modules["dz_debug"] = package
    sys.modules["dz_debug.log"] = module
    try:
        yield module
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


# ─────────────────────────── driving both modules identically ───────────────────────────

@contextlib.contextmanager
def _pytest_shim():
    """Give the oracle a `pytest` whose `fixture` is a plain pass-through.

    The oracle's `@pytest.fixture` would otherwise turn its `log` into a fixture object that
    only a running pytest can call, and the point here is to call it directly. `raises` is this
    module's own `_raises`, which prefers the REAL `pytest.raises` — so the oracle and the
    rewrite get identical raise-checking semantics and cannot diverge on that account.
    sys.modules is restored on the way out; the real pytest is untouched afterwards.
    """
    shim = types.ModuleType("pytest")
    shim.fixture = lambda func: func
    shim.raises = _raises
    saved = sys.modules.get("pytest")
    sys.modules["pytest"] = shim
    try:
        yield shim
    finally:
        if saved is None:
            sys.modules.pop("pytest", None)
        else:
            sys.modules["pytest"] = saved


def load_oracle():
    """Exec the byte-verified ORIGINAL_SOURCE and return it as a module.

    Must be called inside `substrate()`, because the oracle imports `dz_debug.log` at its top.
    """
    check_oracle()
    module = types.ModuleType("forge2_dz_debug_tests_oracle")
    module.__file__ = "<ORIGINAL_SOURCE of %s>" % UNIT
    with _pytest_shim():
        exec(compile(ORIGINAL_SOURCE, module.__file__, "exec"), module.__dict__)
    return module


def _build_log(module, tmp_path):
    """Call a module's `log` fixture body, whichever form it is in.

    The oracle's `log` is a plain function (the shim's `fixture` passed it through). This
    module's `log` is a real pytest fixture when pytest is installed, so its body is reached
    through `_make_log`. Both take `tmp_path` and return a Logger.
    """
    maker = getattr(module, "_make_log", None)
    return (maker or module.log)(tmp_path)


def _params(module, name):
    """Return the parameter names of a module's test, in order."""
    return tuple(inspect.signature(getattr(module, name)).parameters)


def run_case(module, name, root):
    """Run one test of one module against whatever substrate is installed; return its verdict.

    A verdict is the outcome AND the exception type — "pass", "fail:AssertionError",
    "error:FileNotFoundError" — because two modules that both "fail" for different reasons are
    not equivalent. AssertionError is a `fail`; anything else is an `error`, which is how pytest
    itself splits them.

    Each call gets a FRESH temporary directory, exactly as pytest's `tmp_path` fixture does, so
    no test can see another's files. The `log` fixture is built BEFORE the test runs and an
    exception from it is an `error`, again as pytest does it.
    """
    tmp_path = Path(tempfile.mkdtemp(dir=root))
    try:
        needed = _params(module, name)
        kwargs = {}
        if FIXTURE_NAME in needed:
            kwargs[FIXTURE_NAME] = _build_log(module, tmp_path)
        if "tmp_path" in needed:
            kwargs["tmp_path"] = tmp_path
        getattr(module, name)(**kwargs)
        return "pass"
    except AssertionError:
        return "fail:AssertionError"
    except BaseException as exc:  # noqa: BLE001 - the verdict is the point, not the traceback
        return "error:%s" % type(exc).__name__


def sweep():
    """Run BOTH modules against every substrate; return the full verdict table.

    Returns a list of dicts, one per flaw: `flaw`, `description`, and `verdicts` mapping each
    test name to `{"oracle": ..., "rewrite": ...}`.
    """
    rows = []
    root = tempfile.mkdtemp(prefix="forge2-dz-debug-tests-")
    try:
        for flaw, description in FLAWS:
            with substrate(flaw):
                oracle = load_oracle()
                verdicts = {}
                for name in TEST_NAMES:
                    with using_config(config_template()):
                        oracle_verdict = run_case(oracle, name, root)
                        rewrite_verdict = run_case(sys.modules[__name__], name, root)
                    verdicts[name] = {"oracle": oracle_verdict, "rewrite": rewrite_verdict}
            rows.append({"flaw": flaw, "description": description, "verdicts": verdicts})
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return rows


# ─────────────────────────────── the checks ───────────────────────────────

def check_surface():
    """Prove this module presents the ORACLE's callable surface, read from the oracle's own AST.

    Compares names AND parameter lists. This module's `log` is compared through `_make_log`,
    which carries the fixture's real signature — `log` itself is a pytest fixture object under a
    real pytest, exactly as the original's was.
    """
    problems = []
    expected = oracle_surface()
    for name, params in sorted(expected.items()):
        mine = getattr(sys.modules[__name__], name, None)
        if mine is None:
            problems.append("missing callable %s(%s)" % (name, ", ".join(params)))
            continue
        actual = _params(sys.modules[__name__], "_make_log" if name == FIXTURE_NAME else name)
        if actual != params:
            problems.append(
                "%s takes (%s) but the oracle's takes (%s)"
                % (name, ", ".join(actual), ", ".join(params))
            )
    if tuple(n for n in expected if n != FIXTURE_NAME) != TEST_NAMES:
        problems.append(
            "TEST_NAMES %r does not match the oracle's test order %r"
            % (TEST_NAMES, tuple(n for n in expected if n != FIXTURE_NAME))
        )
    if _pytest is not None and isinstance(log, types.FunctionType):
        problems.append("pytest is installed but `log` was not registered as a fixture")
    return problems


def check_literals():
    """Prove the shipped config reproduces the ORACLE's own params, and the constants its words.

    This is the check that closes the sweep's blind spot — see PROVING IT in the module
    docstring. Every value is compared against what the oracle's syntax tree actually says,
    never against a second copy typed out here.
    """
    problems = []
    facts = oracle_facts()
    config = config_template()

    if config["logger_class"] != facts["subject"]:
        problems.append(
            "config logger_class is %r but the oracle imports %r"
            % (config["logger_class"], facts["subject"])
        )

    # Each config key against the oracle's own Logger call in the named function.
    expected = [
        ("fixture_service", "log", "service"),
        ("fixture_build_id", "log", "build_id"),
        ("fixture_profile", "log", "profile"),
        ("fixture_build_json", "log", "build_json"),
        ("mirror_to_stderr", "log", "mirror_to_stderr"),
        ("probe_service", "test_logger_creates_log_file", "service"),
        ("probe_build_json", "test_logger_creates_log_file", "build_json"),
        ("creates_build_id", "test_logger_creates_log_file", "build_id"),
        ("creates_profile", "test_logger_creates_log_file", "profile"),
        ("none_build_id", "test_logger_none_profile_suppresses_info", "build_id"),
        ("none_profile", "test_logger_none_profile_suppresses_info", "profile"),
        ("unknown_build_id", "test_logger_unknown_profile_raises", "build_id"),
        ("unknown_profile", "test_logger_unknown_profile_raises", "profile"),
    ]
    for key, function, fact in expected:
        want = facts["calls"][function][fact]
        got = config[key]
        if got != want:
            problems.append(
                "config %r is %r but the oracle's %s passes %s=%r" % (key, got, function, fact, want)
            )

    # The oracle uses the same service and build_json filename in all three non-fixture tests;
    # this module collapses them into one key each, so prove the oracle really does agree.
    for function in (
        "test_logger_none_profile_suppresses_info",
        "test_logger_unknown_profile_raises",
    ):
        if facts["calls"][function]["service"] != config["probe_service"]:
            problems.append(
                "probe_service %r does not match the oracle's %s service %r"
                % (config["probe_service"], function, facts["calls"][function]["service"])
            )
        if facts["calls"][function]["build_json"] != config["probe_build_json"]:
            problems.append(
                "probe_build_json %r does not match the oracle's %s build_json %r"
                % (config["probe_build_json"], function, facts["calls"][function]["build_json"])
            )

    # The constants: each must be a word the oracle itself uses.
    constants = {
        "HELLO_MESSAGE": HELLO_MESSAGE,
        "WARN_MESSAGE": WARN_MESSAGE,
        "ERROR_MESSAGE": ERROR_MESSAGE,
        "DEBUG_MESSAGE": DEBUG_MESSAGE,
        "SUPPRESSED_MESSAGE": SUPPRESSED_MESSAGE,
        "CAUGHT_MESSAGE": CAUGHT_MESSAGE,
        "INFO_LEVEL_NAME": INFO_LEVEL_NAME,
        "WARN_LEVEL_NAME": WARN_LEVEL_NAME,
        "ERROR_LEVEL_NAME": ERROR_LEVEL_NAME,
        "GATED_CHANNEL": GATED_CHANNEL,
        "UNKNOWN_PROFILE_MATCH": UNKNOWN_PROFILE_MATCH,
        "BOOM_MESSAGE": BOOM_MESSAGE,
        "BOOM_TYPE_NAME": BOOM_TYPE_NAME,
    }
    for name, value in sorted(constants.items()):
        if value not in facts["literals"]:
            problems.append("%s is %r, which the oracle never says" % (name, value))

    # LOG_SUFFIX is derived, not quoted, in the oracle: it writes "test-svc.log" whole. Prove it
    # by reconstructing the filename the oracle reads from the config's own service name.
    if config["fixture_service"] + LOG_SUFFIX not in facts["literals"]:
        problems.append(
            "LOG_SUFFIX %r gives %r, which the oracle never says"
            % (LOG_SUFFIX, config["fixture_service"] + LOG_SUFFIX)
        )
    if config["probe_service"] + LOG_SUFFIX not in facts["literals"]:
        problems.append(
            "LOG_SUFFIX %r gives %r, which the oracle never says"
            % (LOG_SUFFIX, config["probe_service"] + LOG_SUFFIX)
        )
    return problems


def check_equivalence(rows):
    """Turn a sweep into findings: divergence, a toothless mutant, or an unexercised test."""
    problems = []
    caught_by = {name: [] for name in TEST_NAMES}

    for row in rows:
        flaw = row["flaw"] or "(conforming)"
        failing = []
        for name, verdict in row["verdicts"].items():
            if verdict["oracle"] != verdict["rewrite"]:
                problems.append(
                    "DIVERGENCE on %s / %s: oracle says %s, rewrite says %s"
                    % (flaw, name, verdict["oracle"], verdict["rewrite"])
                )
            if verdict["oracle"] != "pass":
                failing.append(name)
                caught_by[name].append(flaw)

        if row["flaw"] is None:
            if failing:
                problems.append(
                    "the conforming substrate must pass all ten, but the oracle did not pass: %s"
                    % ", ".join(failing)
                )
        elif not failing:
            problems.append(
                "mutant %r was caught by NO test — the tests have no teeth there" % flaw
            )

    for name, flaws in sorted(caught_by.items()):
        if not flaws:
            problems.append("test %s catches no mutant — it rides along unexercised" % name)
    return problems


def check_config_gate():
    """Prove the unit THROWS rather than guessing when it cannot see its config.

    #200 requirement 4 and acceptance item (d). Proven three ways, in a throwaway directory, so
    nothing on the real tree is touched or deleted.
    """
    problems = []
    root = tempfile.mkdtemp(prefix="forge2-dz-debug-gate-")
    saved_env = os.environ.get(CONFIG_ENV)
    try:
        # 1. $DZ_DEBUG_TESTS_CONFIG points at a file that does not exist.
        os.environ[CONFIG_ENV] = os.path.join(root, "nope.json")
        try:
            load_config()
            problems.append("a missing $%s file did not raise ConfigError" % CONFIG_ENV)
        except ConfigError:
            pass

        # 2. A registry that exists but has no section for this unit.
        os.environ.pop(CONFIG_ENV, None)
        empty = os.path.join(root, "empty")
        os.makedirs(empty, exist_ok=True)
        with open(os.path.join(empty, REGISTRY_NAME), "w", encoding="utf-8") as handle:
            json.dump({"schema": 1, "forge2": {}}, handle)
        try:
            load_config(start=empty)
            problems.append("a registry with no section for this unit did not raise ConfigError")
        except ConfigError:
            pass

        # 3. A config object that is found but is missing a key a test needs. This is the case
        #    that matters most: a half-filled config must not be silently completed.
        with using_config({"logger_class": "dz_debug.log:Logger"}):
            try:
                _make_log(Path(root))
                problems.append("a config missing 'fixture_service' did not raise ConfigError")
            except ConfigError:
                pass
    finally:
        if saved_env is None:
            os.environ.pop(CONFIG_ENV, None)
        else:
            os.environ[CONFIG_ENV] = saved_env
        shutil.rmtree(root, ignore_errors=True)
    return problems


def _tree(directory):
    """Snapshot every file under `directory`, ignoring __pycache__ — see SIDE EFFECTS."""
    found = set()
    for base, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            found.add(os.path.join(base, name))
    return found


# ─────────────────────────────── the reports ───────────────────────────────

def report_equivalence():
    """Print the full per-substrate verdict table. Returns a process exit code."""
    rows = sweep()
    problems = check_equivalence(rows)
    width = max(len(n) for n in TEST_NAMES)
    for row in rows:
        print("\n%s  — %s" % (row["flaw"] or "(conforming)", row["description"]))
        for name in TEST_NAMES:
            verdict = row["verdicts"][name]
            agree = "agree" if verdict["oracle"] == verdict["rewrite"] else "DIVERGE"
            print(
                "    %-*s  oracle=%-24s rewrite=%-24s %s"
                % (width, name, verdict["oracle"], verdict["rewrite"], agree)
            )
    print("\n%d substrate(s) x %d test(s) = %d verdict pair(s)"
          % (len(rows), len(TEST_NAMES), len(rows) * len(TEST_NAMES)))
    for problem in problems:
        print("  FAIL: %s" % problem)
    print("equivalence: %s" % ("OK" if not problems else "%d PROBLEM(S)" % len(problems)))
    return 0 if not problems else 1


def selftest():
    """Run the whole proof: oracle, literals, surface, equivalence, config gate, side effects.

    Injects its own config, so it needs no registry, no install, no `dz_debug` and no pytest.
    Returns a process exit code.
    """
    package_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    before_pkg, before_cwd = _tree(package_root), _tree(os.getcwd())
    failures = []

    print("oracle")
    sha1 = check_oracle()
    print("    ORIGINAL_SOURCE is %d bytes, git blob sha1 %s" % (len(ORIGINAL_SOURCE.encode()), sha1))
    print("    matches the blob ticket #359 names: OK")

    for title, problems in (
        ("callable surface (read from the oracle's AST)", check_surface()),
        ("literals + config vs the oracle's own params", check_literals()),
        ("config gate (#200 req 4 / acceptance d)", check_config_gate()),
    ):
        print("\n%s" % title)
        if problems:
            failures.extend(problems)
            for problem in problems:
                print("    FAIL: %s" % problem)
        else:
            print("    OK")

    print("\nequivalence sweep (%d substrates x %d tests)" % (len(FLAWS), len(TEST_NAMES)))
    rows = sweep()
    problems = check_equivalence(rows)
    if problems:
        failures.extend(problems)
        for problem in problems:
            print("    FAIL: %s" % problem)
    else:
        caught = sum(
            1
            for row in rows
            if row["flaw"] and any(v["oracle"] != "pass" for v in row["verdicts"].values())
        )
        print("    all %d verdict pairs agree" % (len(rows) * len(TEST_NAMES)))
        print("    conforming substrate: oracle and rewrite both pass all %d" % len(TEST_NAMES))
        print("    all %d mutants caught, every test catches at least one: OK" % caught)

    print("\nside effects")
    new_pkg = _tree(package_root) - before_pkg
    new_cwd = _tree(os.getcwd()) - before_cwd
    if new_pkg or new_cwd:
        for path in sorted(new_pkg | new_cwd):
            failures.append("created %s" % path)
            print("    FAIL: created %s" % path)
    else:
        print("    no file created under %s or the cwd" % package_root)
        print("    (__pycache__ is excluded from this check: CPython writes it for any import,")
        print("    and both /.gitignore and this package's own .gitignore list it)")

    print("\nselftest: %s" % ("OK" if not failures else "%d FAILURE(S)" % len(failures)))
    return 0 if not failures else 1


#: Exit codes `negative-control` expects a sabotaged copy's `selftest` to return. Naming the
#: code rather than just "did it fail" is what stops a sabotage from being scored green for the
#: WRONG reason — an edit that happened to corrupt the embedded oracle would exit PROOF_BROKEN,
#: which is a broken proof rather than a proof that caught something, and only sabotage 7 is
#: allowed to do that.
CAUGHT = 1        # selftest ran and reported failures: the proof did its job
PROOF_BROKEN = 3  # ProofError: the oracle itself no longer checks out
UNNOTICED = 0     # selftest passed: the edit changed no behavior

#: The proof of the proof. Each entry is (find, replace, description, expected exit code): one
#: exact edit to THIS file's own source, applied in a throwaway copy, and what its `selftest`
#: must then return. A proof that cannot fail is not a proof — the eight CAUGHT/PROOF_BROKEN
#: entries show the checks have teeth, and the two UNNOTICED entries show they test behavior
#: rather than spelling, which is what stops the proof from being a copy-detector.
#:
#: Every `find` must match exactly once ABOVE this table (see `negative_control`). That guard
#: is load-bearing, not ceremony: several of these strings also occur inside ORIGINAL_SOURCE,
#: whose text must never be edited by a sabotage — an edit there would break the oracle instead
#: of testing the rewrite. Where a target collided with the oracle's own wording, it is
#: disambiguated by including a line only the rewrite has (`GATED_CHANNEL` rather than the
#: oracle's `"payload"`).
SABOTAGES = (
    (
        "    assert INFO_LEVEL_NAME in content",
        "    pass  # sabotage: assertion dropped",
        "drop test_logger_writes_info's level-name assertion",
        CAUGHT,
    ),
    (
        "    ch = log.channels\n    assert isinstance(ch, dict)\n    assert GATED_CHANNEL in ch",
        "    ch = log.channels\n    assert GATED_CHANNEL in ch",
        "drop test_logger_channels_property's dict check (a list of names would then pass)",
        CAUGHT,
    ),
    (
        "    assert BOOM_TYPE_NAME in content",
        "    pass  # sabotage: assertion dropped",
        "drop test_logger_error_with_exception's exception-type assertion",
        CAUGHT,
    ),
    (
        "    log.info(HELLO_MESSAGE)\n    log.close()\n    content = _fixture_log_path(tmp_path).read_text()",
        "    log.info(HELLO_MESSAGE)\n    log.close()\n    content = log.path.read_text()",
        "'tidy' test_logger_writes_info to trust log.path instead of the reconstructed path",
        CAUGHT,
    ),
    (
        '        "fixture_service": "test-svc",',
        '        "fixture_service": "other-svc",',
        "configure a service the original never used",
        CAUGHT,
    ),
    (
        'LOG_SUFFIX = ".log"',
        'LOG_SUFFIX = ".txt"',
        "expect a log-file suffix the original never used",
        CAUGHT,
    ),
    (
        'GATED_CHANNEL = "payload"',
        'GATED_CHANNEL = "perf"',
        "check a channel the original never checked",
        CAUGHT,
    ),
    (
        'ORIGINAL_BLOB_SHA1 = "f64f023222a1d8278a818c817eef13f385d5f331"',
        'ORIGINAL_BLOB_SHA1 = "0000000000000000000000000000000000000000"',
        "claim a blob sha1 the embedded oracle does not have",
        PROOF_BROKEN,
    ),
    (
        "    ch = log.channels\n    assert isinstance(ch, dict)\n    assert GATED_CHANNEL in ch",
        "    ch = log.channels\n    assert isinstance(ch, dict) and GATED_CHANNEL in ch",
        "HONEST REFACTOR: join two asserts into one `and` (verdict-identical)",
        UNNOTICED,
    ),
    (
        "    log.warn(WARN_MESSAGE)\n    log.close()\n    content = _fixture_log_path(tmp_path).read_text()\n"
        "    assert WARN_MESSAGE in content\n    assert WARN_LEVEL_NAME in content",
        "    log.warn(WARN_MESSAGE)\n    log.close()\n    text = _fixture_log_path(tmp_path).read_text()\n"
        "    assert WARN_MESSAGE in text\n    assert WARN_LEVEL_NAME in text",
        "HONEST REFACTOR: rename a local variable",
        UNNOTICED,
    ),
)


def negative_control():
    """Sabotage THIS module in throwaway copies and check `selftest` notices. Exit code.

    Each sabotage is applied to a copy of this file placed at the same depth in a temporary
    tree, and that copy's own `selftest` is run in a FRESH interpreter. Nothing here writes to
    this package or to the working directory. Requires this file to be readable on disk, which
    is the one thing it cannot prove about itself.
    """
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as handle:
        source = handle.read()

    # Every sabotage target appears at least TWICE in this file: once in the code it edits, and
    # once inside the SABOTAGES table quoting it. So the edits are applied only to the part of
    # the file ABOVE that table — where all the constants, the config template and the tests
    # live — and the table is carried through untouched. Splitting here rather than replacing
    # blindly is what lets the uniqueness guard below stay strict, and the guard is worth
    # keeping strict: it is what will say so out loud if a later edit moves one of these
    # targets or makes it ambiguous, instead of silently sabotaging nothing and reporting green.
    head, separator, table = source.partition("\nSABOTAGES = (")
    if not separator:
        print("  the SABOTAGES table could not be located in this file")
        return 1

    outcome = {UNNOTICED: "ignored", CAUGHT: "caught", PROOF_BROKEN: "oracle!"}
    failures = []
    root = tempfile.mkdtemp(prefix="forge2-dz-debug-negctl-")
    try:
        for index, (find, replace, description, expected) in enumerate(SABOTAGES):
            occurrences = head.count(find)
            if occurrences != 1:
                failures.append(
                    "sabotage %d (%s) matches its target %d times above the SABOTAGES table, "
                    "not once — it no longer describes this file"
                    % (index, description, occurrences)
                )
                print("  %-2d BROKEN  %s" % (index, description))
                continue

            case = os.path.join(root, "case%d" % index, "dz_debug", "tests")
            os.makedirs(case)
            target = os.path.join(case, "test_dz_debug.py")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(head.replace(find, replace) + separator + table)

            proc = subprocess.run(
                [sys.executable, target, "selftest"],
                capture_output=True,
                text=True,
                cwd=root,
            )
            if proc.returncode != expected:
                failures.append(
                    "%s: its selftest exited %d (%s), but it must exit %d (%s)"
                    % (
                        description,
                        proc.returncode,
                        outcome.get(proc.returncode, "unexpected"),
                        expected,
                        outcome[expected],
                    )
                )
                print("  %-2d WRONG   %s (exit %d)" % (index, description, proc.returncode))
            else:
                print("  %-2d %-7s %s" % (index, outcome[expected], description))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(
        "\nnegative control: %s"
        % ("OK — the proof notices what it must, for the reason it must, and only that"
           if not failures else "%d FAILURE(S)" % len(failures))
    )
    for failure in failures:
        print("  FAIL: %s" % failure)
    return 0 if not failures else 1


def report_oracle_literals():
    """Print what the original hardcoded, straight from its syntax tree. Returns an exit code."""
    facts = oracle_facts()
    print("subject imported by the oracle: %s" % facts["subject"])
    for function in sorted(facts["calls"]):
        print("\n%s() passes to Logger(...):" % function)
        for key, value in sorted(facts["calls"][function].items()):
            print("    %-16s %r" % (key, value))
    print("\nevery string literal in the oracle:")
    for literal in sorted(facts["literals"]):
        print("    %r" % (literal,))
    return 0


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ... Filename
    - function name - time of occurance - methods to reproduce - possible cause"). Best-effort
    and silent on failure: a tool that cannot file a report must still report its original
    error. No report is filed for a ConfigError, which is designed behavior rather than a bug.
    Returns the path written, or None.
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
        "methods-to-reproduce": "python3 %s %s"
        % (os.path.basename(os.path.abspath(__file__)), " ".join(argv)),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": formatted.strip().splitlines()[-6:],
        "note": "%s (ticket #359, module key forge-rw:3cc7504c5d6bab73)" % UNIT,
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
        prog="forge2-dz-debug-tests",
        description=(
            "forge2 rewrite of the forge unit "
            "code__code__jazz__kokoro__dz_debug:dz_debug/tests/test_dz_debug.py (ticket #359). "
            "These are pytest tests; run them with `pytest dz_debug/tests/test_dz_debug.py` "
            "against a real dz_debug. The commands here prove the rewrite instead, against "
            "in-memory stand-ins, and need no dz_debug and no pytest installed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "config is read from the file named by $%s, else from the %s section of the nearest "
            "%s found by walking up from this module, else from the registry this distribution "
            "ships as package data. If none answers, every test throws — none guesses a default. "
            "Run `emit-config` for a template. NOTE: `selftest` injects its own config and needs "
            "none of the above." % (CONFIG_ENV, " -> ".join(UNIT_PATH), REGISTRY_NAME)
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="the whole proof: oracle, surface, literals, gate, equivalence, side effects")
    sub.add_parser("equivalence", help="print the full per-substrate verdict table")
    sub.add_parser(
        "negative-control",
        help="the proof of the proof: sabotage this module in throwaway copies and check "
        "`selftest` notices",
    )
    sub.add_parser("oracle-literals", help="print what the original hardcoded, from its syntax tree")
    sub.add_parser("show-oracle", help="print the embedded original and its git blob sha1")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and its source")
    return parser


def main(argv=None):
    """Entry point for the `forge2-dz-debug-tests` console script. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "selftest":
            return selftest()
        if args.command == "equivalence":
            return report_equivalence()
        if args.command == "negative-control":
            return negative_control()
        if args.command == "oracle-literals":
            return report_oracle_literals()
        if args.command == "show-oracle":
            sys.stdout.write(ORIGINAL_SOURCE)
            print(
                "\n# %d bytes, git blob sha1 %s (ticket #359 names %s)"
                % (
                    len(ORIGINAL_SOURCE.encode("utf-8")),
                    git_blob_sha1(ORIGINAL_SOURCE.encode("utf-8")),
                    ORIGINAL_BLOB_SHA1,
                ),
                file=sys.stderr,
            )
            return 0
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print(
                "\n# Install this at %s in your %s, or save it to a file and point $%s at it.\n"
                "# Until it is installed, every test throws — none will guess a default."
                % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV),
                file=sys.stderr,
            )
            return 0
        if args.command == "show-config":
            print(
                json.dumps(
                    {
                        "unit": UNIT,
                        "source": active_source(),
                        "base": active_base(),
                        "config": active_config(),
                    },
                    indent=2,
                )
            )
            return 0
    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except ProofError as exc:
        print("proof error: %s" % exc, file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001
        path = _bug_report(exc, traceback.format_exc(), argv)
        print(
            "EXCEPTION — %s"
            % ("bug report filed at %s" % path if path else "no bug report could be filed"),
            file=sys.stderr,
        )
        raise

    return 0


if __name__ == "__main__":
    sys.exit(main())
