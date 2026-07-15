#!/usr/bin/env python3
"""forge2 / gitlab__testmonkeyalpha-group__jazz-forge__dz_debug / tests/test_dz_debug — a
behavior-preserving rewrite of the forge unit `dz_debug:tests/test_dz_debug.py` (module key
forge-rw:c8f726c326f94dd3), filed under ticket #389 against the FORGE-wide refactor standard
#200.

WHAT THIS IS
------------
The original forge unit was 2301 bytes of pytest regression tests for the `dz_debug` package:
seven test functions and one `_logger` helper, covering `Logger`'s file writing, its
min-level filtering, its channel gating, its `path`/`channels` properties, and the
`debug_decorator` / `save` surface of `dz_debug.logger`. This file is an entirely new
implementation of that unit. It keeps the original's observable behavior — it drives the same
subject the same way and asserts the same things about it — and its callable surface, and it
adds the three things #200 requires that the original lacked: it is part of a proper
installable package, it is driven by a configuration object, and it refuses to run when it
cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    _logger(tmp_path, **cfg)
    test_logger_writes_line(tmp_path)
    test_min_level_filters(tmp_path)
    test_channel_tags_gate_debug(tmp_path)
    test_path_and_channels_properties(tmp_path)
    test_debug_decorator_records_and_returns()
    test_debug_decorator_reraises_and_records_exception(tmp_path, monkeypatch)
    test_save_writes_json(tmp_path)

The caller of a test module is the test runner. These are pytest test functions and pytest
is the caller: the names, the order, and the fixture parameters (`tmp_path`, `monkeypatch`)
are all preserved, so `pytest tests/test_dz_debug.py` collects and runs exactly the seven
tests it collected before. `_logger` keeps its `(tmp_path, **cfg)` shape, including the
detail that a keyword in `**cfg` overrides the base config the helper builds — that is what
the three profile-driving tests rely on.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a
    single `.json` file holding the configuration for every tool in a set of packaging.
    `note-for-claude` states the contract this module obeys — "if a tool cannot see the
    registry it will throw an exeption" [sic]. THIS package ships its own `registry.json` at
    its root; see CONFIGURATION.
config object
    The chunk of that registry belonging to this unit — the
    `forge2.gitlab__testmonkeyalpha-group__jazz-forge__dz_debug.tests.test_dz_debug` section.
    It is what drives this module. `emit-config` prints a template of it.
subject under test
    The `dz_debug` code these tests exercise: the `Logger` class and the `logger` module. The
    original HARDCODED both as `from dz_debug.log import Logger` and `from dz_debug import
    logger as dlog`. A hardcoded dependency is exactly what #200's control-config requirement
    forbids, so here both are named BY THE CONFIG — the `logger_class` and `debug_module`
    keys. This is the same fix ticket #405 applied to the `from code_pipeline import trace`
    that ITS original hardcoded.
substrate
    A stand-in `dz_debug` that the equivalence proof runs the tests against, built in memory
    by `_equivalence/substrates.py`. See PROVING IT.
mutant
    A substrate deliberately broken in one specific way, used to show the tests have teeth.

WHAT THE CONFIG CARRIES, AND WHAT IT DELIBERATELY DOES NOT
----------------------------------------------------------
The rule this module applies, and the reason it is the right one: **the config carries what
the original HANDED TO `dz_debug` — its paths and params. The module keeps what the original
ASSERTS — the test's own data and expectations.** #200 requires no hardcoded paths or params;
it does not require inventing knobs the unit never had, and turning an assertion into a knob
would be worse than a hardcoded param, because a config could then quietly make a test
vacuous.

So the config carries the subject (`logger_class`, `debug_module`), the Logger arguments
(`service`, `build_id`, `mirror_to_stderr`), the profiles the tests drive Logger with
(`filtering_profile`, `channel_profile`), the channel tags they pass (`enabled_channel`,
`disabled_channel`) and the filename they ask `save` to write (`trace_filename`). Every one
of those the original hardcoded.

The config does NOT carry the log messages (`"hello world"`, `"should-appear"`), the level
name `"INFO"`, the `".log"` suffix, or the `{"k": {"function": "x"}}` payload. Those are not
params handed to `dz_debug` — they are the test's own words and the expectations it checks.
`"INFO"` and `".log"` in particular are things `dz_debug` PRODUCES and this module VERIFIES;
making them settable would mean a config could tell the test what answer to accept, which is
the opposite of a test. They are module constants below, each commented with what it is.

Two values are derived rather than repeated, because the original hardcoded the same fact in
two places and repeating it in the config would let the two drift apart:

  * the service tag the written line must carry is `"[" + service + "]"` — the original wrote
    `Logger("svc", ...)` and asserted `"[svc]" in text`;
  * the log file `test_logger_writes_line` reads is `tmp_path / build_id / (service +
    ".log")` — the original wrote `build_id="test"` and then read `tmp_path / "test" /
    "svc.log"`.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
Each test resolves its config object on first use, from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. This file holds the unit
     config object itself — exactly what `emit-config` prints.
  2. otherwise, the `forge2 -> gitlab__testmonkeyalpha-group__jazz-forge__dz_debug -> tests
     -> test_dz_debug` section of the nearest `registry.json` found by walking UP from THIS
     FILE's directory.

If NEITHER answers, the test raises `ConfigError` and asserts nothing. It never guesses a
default — that is `note-for-claude`'s rule and this ticket's acceptance item (d). Under
pytest a `ConfigError` surfaces as an ERROR on each test, which is the gate working: an
unconfigured test that "passed" would be a far worse outcome than one that refuses to run. A
config object that is found but is missing a key an operation needs is also a `ConfigError`,
naming the key.

This package ships `registry.json` at its root, above this file, so source 2 answers and the
tests are runnable from a clean checkout with no setup. That shipped registry is the config
object this unit runs on; it is not a fallback baked into the code. Delete it (with
`FORGE2_CONFIG` unset and no other `registry.json` above this directory) and every test
throws — the gate is in the code, not in the file's presence. `selftest` proves the gate
directly, without deleting anything, by pointing `FORGE2_CONFIG` at a file that does not
exist.

`configure(config)` and `using_config(config)` inject a config object directly, in-process,
for callers that hold their configuration in memory rather than on disk. The equivalence
harness uses them.

PROVING IT (#200 requirement 1 — behavior-preserving, VERIFIED NOT ASSERTED)
----------------------------------------------------------------------------
Ticket #389 records that criteria_miner captured NO exemplars for this module — it mines only
self-contained pure functions, and a test module is nothing but world-touching calls — and
says so explicitly: that "does NOT weaken the ticket's bar — it MOVES the work: you must
write the equivalence exemplars by hand from the original's behavior."

The exemplars are written by hand, and they are DIFFERENTIAL. For a test module, "behavior"
means the verdict it returns about a given subject, so two test modules are equivalent when
they return the SAME verdict about EVERY subject. `_equivalence/harness.py` therefore:

  * loads the ORIGINAL module — `_equivalence/original.py`, the forge blob byte for byte,
    whose git blob sha1 is checked against the one ticket #389 names
    (08863df5ccd3fc3c06e3ccd81ad7f3dcddd97d9f) before it is trusted as the oracle;
  * builds each substrate in `_equivalence/substrates.py` — one CONFORMING `dz_debug`, plus
    one MUTANT per flaw, each breaking exactly one property the original pins down;
  * runs BOTH modules against each substrate and compares the verdict of each of the seven
    tests, where a verdict is the outcome AND the exception type (`pass`, `fail:
    AssertionError`, `error: FileNotFoundError`, ...), not merely pass/fail;
  * requires, on the conforming substrate, that both modules PASS all seven;
  * requires, on every mutant, that at least one test FAIL — an uncaught mutant would mean
    the tests have no teeth there — and that the two modules fail identically;
  * requires that each of the seven tests catch at least one mutant, so no test rides along
    unexercised.

Those requirements are what make this a proof rather than a demonstration. A rewrite that
dropped an assertion would still agree with the original on the conforming substrate; it
would diverge on the mutant that assertion exists to catch. The rewrite is never consulted
about what the right answer is — the original is the only oracle, and the substrate is a
measuring stick applied equally to both. See `substrates.py`'s docstring for why building the
subject does not make this circular.

The sweep has ONE blind spot, and `_equivalence/oracle.py` exists to close it. The substrates
are polymorphic in the literals the tests choose: nothing makes the service be called "svc",
so a rewrite configured with "other" would write other.log, assert `"[other]"`, pass, and
AGREE with the original — which passed on "svc". The sweep can show the rewrite asks the same
KIND of question; it cannot show it asks it with the same words. So `oracle.py` parses the
ORACLE's syntax tree and extracts every literal it hardcodes, and the proof checks the shipped
`registry.json` and this module's own constants against them. This was not designed in — it
was found, by a negative-control run that changed the shipped service to "other" and was not
caught.

And because a proof that cannot fail is not a proof, `_equivalence/negative_control.py` breaks
this module on purpose, one change at a time, in throwaway copies of the package, and checks
that the proof NOTICES: eleven sabotages that must break it (a dropped assertion, `== True`
for `is True`, a wrong config value) and two honest refactors that must NOT, so the proof is
shown to mean "behaves the same" rather than "looks the same".

The proof also covers the two places where the rewrite could pass every value check and still
be subtly wrong, because the original's own text is load-bearing there. Both are things a
tidying rewrite would plausibly get wrong, and both are demonstrated — the negative control
in the ticket's report makes each change and watches the sweep catch it:

  * `test_logger_writes_line` reads a RECONSTRUCTED path (`tmp_path / build_id / service +
    ".log"`), while `test_min_level_filters` reads `log.path`. Those are not
    interchangeable — the `flat_path` mutant moves the file out from under the reconstructed
    path while `log.path` still points at it, so the two tests must disagree about it, and a
    rewrite that "tidied" the first test into using `log.path` diverges here.
  * `test_path_and_channels_properties` asserts `log.channels[...] is True` — an IDENTITY
    check. A `dz_debug` whose channels are truthy `1` rather than the bool `True` must fail
    it, so `== True` is not a safe simplification; the `channels_truthy_not_true` mutant
    catches that.

One thing that is NOT subtle, recorded because the first draft of this docstring claimed it
was: writing that assertion as one `and` expression rather than two statements makes no
difference to the verdict. `assert A and B` and `assert A` / `assert B` fail identically —
when `A` is false the split form's first assert raises AssertionError too, which is the same
verdict the short-circuit produces. The single expression is kept here for fidelity to the
original, not because anything rests on it. The negative control that split it found no
divergence, which is how the claim was caught.

RUNNING IT
----------
Every command below is executable as written from the PACKAGE ROOT — the directory holding
`pyproject.toml` and `registry.json`, one level above this file. Any path to this file works
just as well, from any working directory: what config is found does not depend on where you
run from, because the registry walk-up starts at THIS FILE and never at the working
directory.

    python3 tests/test_dz_debug.py selftest          # the whole proof: gate, literals,
                                                     #   equivalence, surface, side effects
    python3 tests/test_dz_debug.py equivalence       # the full per-substrate verdict table
    python3 tests/test_dz_debug.py negative-control  # the proof of the proof: sabotage this
                                                     #   module in throwaway copies of the
                                                     #   package, check `selftest` notices
    python3 tests/test_dz_debug.py emit-config       # print a config-object template
    python3 tests/test_dz_debug.py show-config       # print the resolved config + its source

Every command above needs no `dz_debug` and no pytest installed: the subjects are built in
memory. None writes a file outside a temporary directory it deletes — `selftest` proves that
rather than claiming it, by diffing this package's tree and the working directory across the
whole sweep.

Under a real test runner, with a real `dz_debug` importable, the normal invocation is
unchanged from the original's:

    pytest tests/test_dz_debug.py

PYTEST IS OPTIONAL AT IMPORT, BY NECESSITY
------------------------------------------
The original did `import pytest` at module top. This module does not: it imports pytest
lazily, inside `_raises`, and falls back to an equivalent context manager when pytest is
absent (`_fallback_raises`). `pytest.raises` is the only thing the original used pytest for.

This is a deliberate, documented difference, and it is the only one. Under pytest the
behavior is identical, because `_raises` prefers the real `pytest.raises` whenever pytest can
be imported. Without it, the module could not be executed at all in an environment that has
no pytest — which is the environment this ticket is worked in — and #200's requirement 1
demands the rewrite be VERIFIED, which means run. A module that cannot run cannot be proven.

Two further honest differences, both forced by requirement 4 and neither affecting what the
tests assert:

  * the subject is resolved when a test runs, not when the module is imported, because config
    resolution has to be able to throw `ConfigError` rather than guess. So if `dz_debug` is
    missing, the original fails at COLLECTION with an ImportError while this module fails
    per-test with a `ConfigError`. Both are errors and neither is a pass; when `dz_debug` is
    present, the two are indistinguishable.
  * `test_debug_decorator_records_and_returns` and the exception test resolve the subject at
    the point the original's top-level import had already bound it — before their first
    statement — so statement order is otherwise preserved exactly.

SIDE EFFECTS
------------
The seven tests write only inside the `tmp_path` fixture their runner hands them, exactly as
the original's did. The exception test additionally `monkeypatch.chdir`s into `tmp_path`
first, because `dz_debug`'s decorator dumps a trace file into the current working directory
on the exception path — the original's own comment calls this out as "contain the trace.json
side effect", and this module keeps that containment. `selftest` and `equivalence` snapshot
this package's directory tree and the working directory before and after the whole sweep and
report any file that appeared, so the containment is demonstrated rather than asserted.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception
is thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path if
it hits an UNEXPECTED exception — that is, a defect in this module. A `ConfigError` is
designed behavior, not a bug: it files no report and prints no traceback, and exits with a
single self-explaining line.
"""

import argparse
import contextlib
import importlib
import importlib.util
import json
import os
import sys
import traceback
from datetime import datetime

__all__ = [
    "_logger",
    "test_logger_writes_line",
    "test_min_level_filters",
    "test_channel_tags_gate_debug",
    "test_path_and_channels_properties",
    "test_debug_decorator_records_and_returns",
    "test_debug_decorator_reraises_and_records_exception",
    "test_save_writes_json",
    "ConfigError",
    "load_config",
    "configure",
    "using_config",
    "reset_config",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS
#: in the config document, not a configurable setting — a config-driven module has to know
#: which section is its own.
UNIT_PATH = (
    "forge2",
    "gitlab__testmonkeyalpha-group__jazz-forge__dz_debug",
    "tests",
    "test_dz_debug",
)

#: Human-readable unit identity, used in messages.
UNIT = "forge2:gitlab__testmonkeyalpha-group__jazz-forge__dz_debug/tests/test_dz_debug"

#: The config keys every one of these tests needs. Listed so `emit-config` and the missing-key
#: error can name them; each is a param or path the ORIGINAL hardcoded.
REQUIRED_KEYS = (
    "logger_class",
    "debug_module",
    "service",
    "build_id",
    "mirror_to_stderr",
    "filtering_profile",
    "channel_profile",
    "enabled_channel",
    "disabled_channel",
    "trace_filename",
)

# ── The test's own data and expectations. NOT config — see the docstring's "WHAT THE CONFIG
#    CARRIES" section. These are the original's literals, kept as literals on purpose. ──

#: The message test_logger_writes_line logs and then looks for. The original's own word.
HELLO_MESSAGE = "hello world"

#: The INFO message test_min_level_filters requires to survive the min-level gate, and the
#: DEBUG message it requires to be dropped. The original's own words, and self-describing.
#: Note they are not substrings of one another, which is what makes the original's pair of
#: `in` / `not in` checks sound; keeping the exact strings keeps that property.
KEPT_MESSAGE = "should-appear"
DROPPED_MESSAGE = "should-not-appear"

#: What test_channel_tags_gate_debug appends to a channel name to make that channel's message
#: ("perf" -> "perf-line"). Derived rather than hardcoded twice, so the message and the tag it
#: rides on cannot drift apart; with the shipped config it reproduces the original's
#: "perf-line" and "payload-line" exactly.
LINE_SUFFIX = "-line"

#: The level name a `Logger.info(...)` line must carry. This is what dz_debug PRODUCES and
#: this module VERIFIES, so it is an expectation, not a param — see the docstring.
INFO_LEVEL_NAME = "INFO"

#: The suffix dz_debug gives a service's log file. An expectation, like INFO_LEVEL_NAME: the
#: test does not choose it, it checks it.
LOG_SUFFIX = ".log"

#: The entry test_save_writes_json plants in `L` and then reads back out of the saved JSON.
#: Test data, not a param — the original's own literals.
SAVE_KEY = "k"
SAVE_ENTRY = {"function": "x"}


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.
    """


# ─────────────────────────── the subject under test ───────────────────────────

def _load_attr(spec, key):
    """Resolve a `"module:attr"` string from the config to the attribute it names."""
    if ":" not in spec:
        raise ConfigError(
            "config key %r for %s must look like \"module:attr\" (for example "
            "\"dz_debug.log:Logger\"); got %r" % (key, UNIT, spec)
        )
    module_name, _, attribute = spec.partition(":")
    module = _import(module_name, key, spec)
    try:
        return getattr(module, attribute)
    except AttributeError as exc:
        raise ConfigError(
            "config key %r for %s names %r, but module %r has no attribute %r"
            % (key, UNIT, spec, module_name, attribute)
        ) from exc


def _import(module_name, key, spec):
    """Import `module_name`, reporting failure as a ConfigError against the config key."""
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise ConfigError(
            "config key %r for %s names %r, whose module %r cannot be imported: %s. The "
            "subject under test must be installed for these tests to run."
            % (key, UNIT, spec, module_name, exc)
        ) from exc


def _logger_class():
    """Return the `Logger` class named by the config's `logger_class` key.

    The original hardcoded this as `from dz_debug.log import Logger`.
    """
    spec = _setting("logger_class")
    if not isinstance(spec, str):
        raise ConfigError(
            "config key 'logger_class' for %s must be a \"module:attr\" string, not %s"
            % (UNIT, type(spec).__name__)
        )
    return _load_attr(spec, "logger_class")


def _debug_module():
    """Return the module named by the config's `debug_module` key.

    The original hardcoded this as `from dz_debug import logger as dlog`. It is a plain module
    path, with no `:`, because the original bound the MODULE rather than an attribute of it.
    """
    spec = _setting("debug_module")
    if not isinstance(spec, str):
        raise ConfigError(
            "config key 'debug_module' for %s must be a module-path string, not %s"
            % (UNIT, type(spec).__name__)
        )
    if ":" in spec:
        raise ConfigError(
            "config key 'debug_module' for %s must be a plain module path (for example "
            "\"dz_debug.logger\"), not a \"module:attr\" string; got %r" % (UNIT, spec)
        )
    return _import(spec, "debug_module", spec)


@contextlib.contextmanager
def _fallback_raises(expected):
    """Stand in for `pytest.raises(expected)` when pytest is not importable.

    Equivalent for the one use the original makes of it: it swallows `expected`, lets any
    other exception through, and fails if the block raises nothing. The original never bound
    the `as` target, so nothing needs to be yielded.
    """
    try:
        yield
    except expected:
        return
    raise AssertionError("DID NOT RAISE %s" % expected.__name__)


def _raises(expected):
    """Return `pytest.raises(expected)` when pytest is importable, else the fallback.

    Preferring the real pytest is what keeps this module's behavior under pytest identical to
    the original's, which used `pytest.raises` unconditionally.
    """
    try:
        import pytest
    except ImportError:
        return _fallback_raises(expected)
    return pytest.raises(expected)


# ─────────────────────────────── the tests ───────────────────────────────

def _logger(tmp_path, **cfg):
    """Build the subject `Logger` over `tmp_path`, with `cfg` overriding the base settings.

    The rewrite of the original's helper of the same name and shape. `service`, `build_id`
    and `mirror_to_stderr` come from the config object; the original hardcoded them as
    `"svc"`, `"test"` and `False`, which is what this package's shipped registry says.

    The `log_root` and `mirror_to_stderr` KEY NAMES are dz_debug's own config schema, so they
    stay literal here; only the values the test supplies are configurable. `log_root` is the
    `tmp_path` the test runner hands in, so it was never hardcoded to begin with.
    """
    settings = active_config()
    base = {"log_root": str(tmp_path), "mirror_to_stderr": _require(settings, "mirror_to_stderr")}
    base.update(cfg)
    return _logger_class()(
        _require(settings, "service"),
        build_id=_require(settings, "build_id"),
        config=base,
    )


def test_logger_writes_line(tmp_path):
    """A logged INFO line lands in the log file, tagged with the service and the level."""
    settings = active_config()
    log = _logger(tmp_path)
    log.info(HELLO_MESSAGE)
    log.close()
    # Read the RECONSTRUCTED path, not `log.path`. The original did this deliberately: it is
    # what checks that the file lands under log_root/build_id/ with the expected name, which
    # `log.path` — whatever it happens to hold — cannot check. See the docstring's note on
    # the `flat_path` mutant.
    text = (
        tmp_path
        / _require(settings, "build_id")
        / (_require(settings, "service") + LOG_SUFFIX)
    ).read_text()
    # Split into three checks; the original wrote one `and` chain. Every branch still raises
    # AssertionError, so the verdict is identical, and a failure now names which part missed.
    assert HELLO_MESSAGE in text
    assert "[%s]" % _require(settings, "service") in text
    assert INFO_LEVEL_NAME in text


def test_min_level_filters(tmp_path):
    """Under the filtering profile the min level is INFO, so a DEBUG line is dropped."""
    settings = active_config()
    log = _logger(tmp_path, profile=_require(settings, "filtering_profile"))
    log.debug(DROPPED_MESSAGE)
    log.info(KEPT_MESSAGE)
    log.close()
    text = log.path.read_text()
    assert KEPT_MESSAGE in text
    assert DROPPED_MESSAGE not in text


def test_channel_tags_gate_debug(tmp_path):
    """Under the channel profile the enabled channel's line survives and the disabled one does not."""
    settings = active_config()
    enabled = _require(settings, "enabled_channel")
    disabled = _require(settings, "disabled_channel")
    log = _logger(tmp_path, profile=_require(settings, "channel_profile"))
    log.debug(enabled + LINE_SUFFIX, tags=[enabled])
    log.debug(disabled + LINE_SUFFIX, tags=[disabled])
    log.close()
    text = log.path.read_text()
    assert enabled + LINE_SUFFIX in text
    assert disabled + LINE_SUFFIX not in text


def test_path_and_channels_properties(tmp_path):
    """`path` names the service's log file and `channels` is a dict of real bools."""
    settings = active_config()
    log = _logger(tmp_path, profile=_require(settings, "channel_profile"))
    assert log.path.name == _require(settings, "service") + LOG_SUFFIX
    # `is True` is an IDENTITY check: a channels dict whose values are truthy 1 rather than
    # the bool True must fail here, so `== True` would not be equivalent. Kept as ONE `and`
    # expression because that is how the original wrote it; splitting it would be
    # verdict-identical (a false `A` raises AssertionError either way), so nothing rests on
    # the short-circuit.
    assert isinstance(log.channels, dict) and log.channels[_require(settings, "enabled_channel")] is True
    log.close()


def test_debug_decorator_records_and_returns():
    """The decorator returns the wrapped result and records the call with its timing."""
    dlog = _debug_module()
    dlog.L.clear()

    @dlog.debug_decorator
    def add(a, b):
        return a + b

    assert add(2, 3) == 5
    assert any(
        e.get("function") == "add" and "execution_time" in e for e in dlog.L.values()
    )


def test_debug_decorator_reraises_and_records_exception(tmp_path, monkeypatch):
    """The decorator records the exception and lets it propagate."""
    dlog = _debug_module()
    monkeypatch.chdir(tmp_path)  # contain the trace file the decorator dumps into the cwd
    dlog.L.clear()

    @dlog.debug_decorator
    def boom():
        raise ValueError("nope")

    with _raises(ValueError):
        boom()
    assert any("exception" in e for e in dlog.L.values())


def test_save_writes_json(tmp_path):
    """`save` writes the recorded entries to the given path as JSON."""
    settings = active_config()
    dlog = _debug_module()
    dlog.L.clear()
    dlog.L[SAVE_KEY] = dict(SAVE_ENTRY)
    out = tmp_path / _require(settings, "trace_filename")
    dlog.save(str(out))
    assert json.loads(out.read_text())[SAVE_KEY]["function"] == SAVE_ENTRY["function"]


#: The seven tests, in the original's own order. The harness sweeps this list, and
#: `selftest` checks it against what the original module actually defines, so the two cannot
#: drift apart.
TEST_NAMES = (
    "test_logger_writes_line",
    "test_min_level_filters",
    "test_channel_tags_gate_debug",
    "test_path_and_channels_properties",
    "test_debug_decorator_records_and_returns",
    "test_debug_decorator_reraises_and_records_exception",
    "test_save_writes_json",
)


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None    # config object injected via configure(); wins over every disk source
_RESOLVED = None  # cache of the last disk resolution, so the tests re-read no files


def _require(config, key):
    """Return `config[key]`, or raise ConfigError naming the key that is missing."""
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the required key %r. The required keys are: "
            "%s. Run `emit-config` for a template."
            % (UNIT, key, ", ".join(REQUIRED_KEYS))
        )
    return config[key]


def _setting(key):
    """Return one key of the config object in force."""
    return _require(active_config(), key)


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
            raise ConfigError(
                "the config object at %s must be a JSON object, not %s"
                % (env_path, type(config).__name__)
            )
        return config, os.path.dirname(os.path.abspath(env_path)), "%s=%s" % (CONFIG_ENV, env_path)

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s: %s is unset and no %s was found by walking up from %s. "
            "Run `emit-config` for a template of the config object to install."
            % (
                UNIT,
                CONFIG_ENV,
                REGISTRY_NAME,
                os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))),
            )
        )

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r "
                "section. Run `emit-config` and add the printed object at %s."
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


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do every test throws.
    """
    return {
        "logger_class": "dz_debug.log:Logger",
        "debug_module": "dz_debug.logger",
        "service": "svc",
        "build_id": "test",
        "mirror_to_stderr": False,
        "filtering_profile": "standard",
        "channel_profile": "debug",
        "enabled_channel": "perf",
        "disabled_channel": "payload",
        "trace_filename": "trace.json",
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────────────── the command line ───────────────────────────────

def _proof(name):
    """Import one module of the equivalence proof, imported-as-a-package or run as a script.

    As an installed package the relative import works; run as `python3 test_dz_debug.py`
    there is no parent package, so the module is loaded by path instead. These are imported
    lazily, here rather than at module top, because `harness` imports THIS module back and a
    top-level import would be circular — and because collecting these tests under pytest must
    not drag the proof machinery in.
    """
    # `__package__` is empty when this file is run as a script, and a relative import with no
    # anchor raises TypeError rather than ImportError — so it has to be checked, not caught.
    if __package__:
        try:
            return importlib.import_module("._equivalence." + name, __package__)
        except ImportError:
            pass
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_equivalence", name + ".py")
    spec = importlib.util.spec_from_file_location("_forge2_dz_debug_" + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report its
    original error. No report is filed for a ConfigError, which is designed behavior rather
    than a bug. Returns the path written, or None.
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
        "note": "%s (ticket #389, module key forge-rw:c8f726c326f94dd3)" % UNIT,
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
        description="forge2 rewrite of the forge unit dz_debug:tests/test_dz_debug.py "
        "(ticket #389). These are pytest tests; run them with `pytest "
        "tests/test_dz_debug.py` against a real dz_debug. The commands here prove the "
        "rewrite instead, against in-memory stand-ins, and need no dz_debug installed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="config is read from the file named by $%s, else from the %s section of the "
        "nearest %s found by walking up from this module. This package ships one at its "
        "root, so the tests are runnable from a clean checkout. Run `emit-config` for a "
        "template." % (CONFIG_ENV, " -> ".join(UNIT_PATH), REGISTRY_NAME),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="the whole proof: config gate, equivalence, surface, side effects")
    sub.add_parser("equivalence", help="print the full per-substrate verdict table")
    sub.add_parser(
        "negative-control",
        help="the proof of the proof: sabotage this module in a throwaway copy and check "
        "that `selftest` notices",
    )
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and its source")
    return parser


def main(argv=None):
    """Entry point for the `forge2-dz-debug-tests` console script. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print(
                "\n# Install this at %s in your %s, or save it to a file and point $%s at "
                "it.\n# Until it is installed, every test throws — none will guess a default."
                % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV),
                file=sys.stderr,
            )
            return 0

        if args.command == "selftest":
            return 0 if _proof("harness").selftest() == 0 else 1

        if args.command == "equivalence":
            return 0 if _proof("harness").report_equivalence() == 0 else 1

        if args.command == "negative-control":
            return 0 if _proof("negative_control").run() == 0 else 1

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
