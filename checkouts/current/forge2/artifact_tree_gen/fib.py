#!/usr/bin/env python3
"""forge2 / artifact_tree_gen / fib — a behavior-preserving rewrite of the forge unit
`artifact_tree_gen:fib.py` (module key forge-rw:f3df615229b4c9f7), filed under ticket #405
against the FORGE-wide refactor standard #200.

WHAT THIS IS
------------
The original forge unit was 201 bytes: it imported a telemetry decorator from
`code_pipeline`, applied it to a one-argument function, returned `n` unchanged when
`n <= 1`, and otherwise walked the Fibonacci recurrence iteratively from `(0, 1)` up to
`n`. This file is an entirely new implementation of that unit. It keeps the original's
observable behavior and its callable surface, and it adds the three things #200 requires
that the original lacked: it is a proper installable package, it is driven by a
configuration object, and it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    fib(n)

`fib` returns the n-th Fibonacci number, counting from `fib(0) == 0` and `fib(1) == 1`.

Two properties of that sentence are easy to get wrong, and both are load-bearing here
because the original had them:

  * For `n <= 1`, the original returns `n` ITSELF — the very object it was handed, not a
    freshly built int. So `fib(True)` is the bool `True`, not the int `1`; `fib(0.5)` is
    `0.5`; `fib(-1)` is `-1` (negative inputs are returned, not rejected); and for an `int`
    SUBCLASS the instance comes back with its subclass intact. A rewrite that "cleaned this
    up" to `return int(n)` would reproduce every captured exemplar's VALUE and still be
    wrong, because `fib(True)` would stop being a bool.
  * For `n >= 2` the recurrence is walked ITERATIVELY, so `fib(2000)` returns a 418-digit
    int. A recursive rewrite would raise `RecursionError` there and so would not preserve
    behavior.

Inputs the original rejects are rejected the same way, by the same operators, with no
coercion and no sentinel: `fib(1.5)` and `fib(2.0)` raise `TypeError` from `range()`
("'float' object cannot be interpreted as an integer") because a float that is not `<= 1`
reaches `range(2, n + 1)`; `fib("a")`, `fib(None)` and `fib([1])` raise `TypeError` from the
`<=` comparison itself. All of this is verified by `selftest` (see RUNNING IT), against
values taken from the ORIGINAL acting as the oracle.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a
    single `.json` file holding the configuration for every tool in a set of packaging.
    `note-for-claude` states the contract this module obeys — "if a tool cannot see the
    registry it will throw an exeption" [sic]. THIS package ships its own `registry.json`
    beside this file; see CONFIGURATION.
config object
    The chunk of that registry belonging to this unit — the `forge2.artifact_tree_gen.fib`
    section. It is what drives this module. `emit-config` prints a template of it.
trace hook
    The telemetry decorator. The original HARDCODED this as `from code_pipeline import
    trace`. A hardcoded dependency is exactly what #200's control-config requirement
    forbids, and `code_pipeline` is not importable everywhere this unit must run, so here
    the hook is named BY THE CONFIG instead (the `"trace"` key). A trace hook is telemetry:
    it records the call and returns the wrapped result unchanged, so it does not alter what
    `fib` returns. That pass-through property is what the original's captured exemplars
    encode, and `selftest` proves it by running every exemplar BOTH undecorated and through
    a config-named hook and requiring identical results.

WHY THE CONFIG HAS EXACTLY ONE BEHAVIORAL KEY
---------------------------------------------
`trace` is the only setting this unit has, because it is the only thing the original
hardcoded that is not part of its definition. The seeds `(0, 1)` and the `n <= 1` base case
are not settings — they ARE the Fibonacci sequence, and making them configurable would
change the function's behavior and break the exemplars this ticket exists to preserve.
#200 requires no hardcoded paths or params; it does not require inventing knobs the unit
never had. The remaining key, `bug_reports`, is infrastructure required by
`note-for-claude`, not a behavioral setting.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
`fib()` resolves its config object on first use, from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. This file holds the unit
     config object itself — exactly what `emit-config` prints.
  2. otherwise, the `forge2.artifact_tree_gen.fib` section of the nearest `registry.json`
     found by walking UP from THIS FILE's directory.

If NEITHER answers, `fib()` raises `ConfigError` and does not compute a number. It never
guesses a default — that is `note-for-claude`'s rule and this ticket's acceptance item (d).
A config object that is found but is missing a key this operation needs is also a
`ConfigError`, naming the key.

This package ships `registry.json` NEXT TO this file, so source 2 answers and `fib` works
from a clean checkout with no setup. That shipped registry is the config object this unit
runs on; it is not a fallback baked into the code. Delete it (with `FORGE2_CONFIG` unset
and no other `registry.json` above this directory) and `fib()` throws — the gate is in the
code, not in the file's presence. `selftest` proves the gate directly, without deleting
anything, by pointing `FORGE2_CONFIG` at a file that does not exist.

The shipped registry deliberately carries ONLY this unit's `fib` section: ticket #405
covers one module. Sibling modules in this package resolve their own config independently
and throw if their own section is absent, which is the designed gate doing its job rather
than a defect in this file.

`configure(config)` and `using_config(config)` inject a config object directly, in-process,
for callers that hold their configuration in memory rather than on disk.

RUNNING IT
----------
Every command below is executable as written from this file's own directory; from anywhere
else, give the full path to `fib.py` instead of the bare name. Which directory you run from
does not change what config is found — the registry walk-up starts at THIS FILE, never at
the working directory.

    python3 fib.py fib 10                      # -> 55
    python3 fib.py selftest                    # prove the exemplars, the edges, the gate
    python3 fib.py emit-config                 # print a config-object template
    python3 fib.py show-config                 # print the resolved config + where it came from

`fib N` reads its argument as a Python literal (`ast.literal_eval`), so `fib 10` passes the
int `10` and `fib True` passes the bool `True`. `selftest` and `emit-config` need no config
and write no files.

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, and the package is committed in
full beside it — `pyproject.toml`, `__init__.py`, `registry.json`. From THIS file's
directory:

    pip install -e .
    forge2-fib fib 10                          # -> 55

`pyproject.toml` maps this directory onto the import package `artifact_tree_gen`, so an
installed copy imports as `from artifact_tree_gen.fib import fib`, and declares the
`forge2-fib` console script pointing at `main()` below.

Note that `artifact_tree_gen/__init__.py` re-exports the FUNCTION `fib` for convenience, so
after `import artifact_tree_gen` the attribute `artifact_tree_gen.fib` is that function and
not this module. `from artifact_tree_gen.fib import fib` is unaffected and is the form to
prefer.

SIDE EFFECTS
------------
`fib()`, `emit-config`, `show-config` and `selftest` create no files and write nothing.
Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an
exception is thrown") the CLI appends one timestamped JSON line to the config's
`bug_reports` path if it hits an UNEXPECTED exception — that is, a defect in this tool. A
`ConfigError` is designed behavior, not a bug, and neither is the `TypeError` the original
itself raises for an operand it rejects: both file no report and print no traceback, and
exit with a single self-explaining line.
"""

import argparse
import ast
import contextlib
import importlib
import inspect
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime

__all__ = ["fib", "ConfigError", "load_config", "configure", "using_config", "reset_config"]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own
#: ADDRESS in the config document, not a configurable setting — a config-driven tool has to
#: know which section is its own.
UNIT_PATH = ("forge2", "artifact_tree_gen", "fib")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:artifact_tree_gen/fib"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.
    """


# ─────────────────────────────── the unit itself ───────────────────────────────

def _core(n):
    """The rewritten unit body: the n-th Fibonacci number, counting fib(0) == 0, fib(1) == 1.

    `n` is returned UNCHANGED — the same object, not a rebuilt one — whenever `n <= 1`, and
    the recurrence is walked iteratively otherwise. Both are the original's behavior; see
    this module's docstring for why each matters.
    """
    if n <= 1:
        return n
    previous, current = 0, 1
    for _ in range(2, n + 1):
        previous, current = current, previous + current
    return current


def fib(n):
    """Return the n-th Fibonacci number — the rewrite of the forge unit `artifact_tree_gen:fib.py`.

    Counts from `fib(0) == 0` and `fib(1) == 1`, so `fib(10) == 55`.

    For `n <= 1` the argument is returned as it was handed in, so the result keeps `n`'s own
    type and identity: `fib(True)` is the bool `True`, `fib(-1)` is `-1`. For `n >= 2` the
    recurrence is walked iteratively, so large `n` is fine (`fib(2000)` has 418 digits).
    Operands the underlying operators reject raise `TypeError` from those operators, exactly
    as the original did: `fib(1.5)` from `range()`, `fib("a")` from `<=`.

    If the config object names a trace hook, the hook wraps the call; a trace hook is
    telemetry and returns the wrapped result unchanged, so the value below is the same
    either way.

    Raises:
        ConfigError: if no config object can be resolved, or it lacks the `trace` key.
        TypeError: for an operand `<=` or `range()` rejects, from the operator itself.
    """
    return _traced_core()(n)


_IMPL_CACHE = {}


def _traced_core():
    """Return `_core`, wrapped in the config's trace hook when one is named."""
    cfg = active_config()
    if "trace" not in cfg:
        raise ConfigError(
            "config object for %s is missing the required key 'trace' (use null for no "
            "trace hook, or a \"module:attr\" string). Run `emit-config` for a template."
            % UNIT
        )
    spec = cfg["trace"]
    if spec is not None and not isinstance(spec, str):
        raise ConfigError(
            "config key 'trace' for %s must be null or a \"module:attr\" string, not %s"
            % (UNIT, type(spec).__name__)
        )
    if spec not in _IMPL_CACHE:
        _IMPL_CACHE[spec] = _core if spec is None else _load_attr(spec)(_core)
    return _IMPL_CACHE[spec]


def _load_attr(spec):
    """Resolve a `"module:attr"` string to the attribute it names."""
    if ":" not in spec:
        raise ConfigError(
            "config key 'trace' for %s must look like \"module:attr\" (for example "
            "\"code_pipeline:trace\"); got %r" % (UNIT, spec)
        )
    mod_name, _, attr = spec.partition(":")
    module = sys.modules.get(mod_name)
    if module is None:
        try:
            module = importlib.import_module(mod_name)
        except ImportError as exc:
            raise ConfigError(
                "config key 'trace' for %s names module %r, which cannot be imported: %s"
                % (UNIT, mod_name, exc)
            ) from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ConfigError(
            "config key 'trace' for %s names %r, but module %r has no attribute %r"
            % (UNIT, spec, mod_name, attr)
        ) from exc


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None      # config object injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution, so fib() re-reads no files


def find_registry(start=None):
    """Walk UP from `start` (default: this file's directory) and return the nearest
    registry path, or None if the walk reaches the filesystem root without finding one."""
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

    Returns a `(config, base, source)` triple: the config object, the directory that
    relative paths inside it resolve against, and a human-readable description of where it
    came from. `start` overrides the directory the registry walk-up begins at.

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
            "no config object for %s: %s is unset and no %s was found by walking up from "
            "%s. Run `emit-config` for a template of the config object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))))
        )

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r "
                "section. Run `emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]),
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
            raise ConfigError(
                "a config object must be a dict, not %s" % type(config).__name__
            )
        _ACTIVE = (config, base or os.getcwd(), source)
    _IMPL_CACHE.clear()
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
        _IMPL_CACHE.clear()


def reset_config():
    """Drop the injected config and the cached disk resolution; the next call re-resolves."""
    global _ACTIVE, _RESOLVED
    _ACTIVE = None
    _RESOLVED = None
    _IMPL_CACHE.clear()


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do `fib()` throws.
    """
    return {
        "trace": None,
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────────────── the selftest ───────────────────────────────

def _selftest_trace(fn):
    """A pass-through trace hook, used by `selftest` to exercise the config's trace path.

    It mirrors what the ORIGINAL unit's `code_pipeline.trace` decorator does to the return
    value, which is nothing: it records the call and hands the result back unchanged.
    """
    calls = []

    def wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        return fn(*args, **kwargs)

    wrapper.calls = calls
    wrapper.__name__ = getattr(fn, "__name__", "wrapped")
    wrapper.__doc__ = getattr(fn, "__doc__", None)
    return wrapper


class _IntSubclass(int):
    """An `int` subclass, used to prove `fib` returns `n` itself for `n <= 1`."""


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
    """Call `thunk` and return its result, or a `_Raised` if it raised anything.

    `_Raised` matches no expected value and is not an int, so every check below turns an
    unexpected exception into a reported FAIL. RecursionError is the one that matters: a
    recursive rewrite of this unit raises it at `fib(2000)`, and that must be a legible
    failing check, not a traceback out of `selftest`.
    """
    try:
        return thunk()
    except BaseException as exc:  # noqa: BLE001 — a test net must survive anything
        return _Raised(exc)


def _mismatches(cases):
    """Return `(args, want, got)` for every case whose result is not `want`.

    A case that RAISES is a mismatch, not a crash: `_attempt` reports the exception as the
    result it got, so one broken input cannot hide the checks behind it.
    """
    bad = []
    for args, want in cases:
        got = _attempt(lambda a=args: fib(*a))
        if not _same(got, want):
            bad.append((args, want, got))
    return bad


#: The exemplars this rewrite must reproduce. These are the six pairs ticket #405 quotes
#: verbatim, in the ticket's own order. Every expected value was taken from the ORIGINAL
#: unit acting as the oracle, never from this rewrite.
EXEMPLARS = [
    ((-1,), -1),
    ((0,), 0),
    ((1,), 1),
    ((2,), 1),
    ((3,), 2),
    ((True,), True),
]

#: Edge cases the mining could not reach. #405 records criteria_miner's own honest limit —
#: the exemplars "cover the SAMPLED inputs", probed "around the function's own branch
#: constants", and are "NOT a proof of total equivalence" — and asks for the edges sampling
#: misses. Every value here was likewise read off the ORIGINAL as the oracle. They probe
#: what six small samples around `n <= 1` cannot:
#:   * the recurrence past the sampled tail (4, 5, 10, 30, 100) — the six exemplars only
#:     ever run the loop 0, 1 or 2 times, so a rewrite with an off-by-one in `range` or the
#:     wrong seeds can pass all six and still be wrong from fib(4) on;
#:   * arbitrary-precision results (100) — not truncated or floated;
#:   * the OTHER bool (False) and non-int operands that pass `<= 1` (0.5, 1.0) — the result
#:     keeps the argument's own type, which `fib(True) == True` alone only hints at;
#:   * a deep negative (-100) — returned, not rejected, and the loop is never entered.
EDGE_CASES = [
    ((4,), 3),
    ((5,), 5),
    ((10,), 55),
    ((30,), 832040),
    ((100,), 354224848179261915075),
    ((False,), False),
    ((0.5,), 0.5),
    ((1.0,), 1.0),
    ((-100,), -100),
]

#: Operands the original itself rejects, and the operator each rejection comes from. The
#: original raised TypeError here, so this rewrite must too, rather than coercing the
#: operand or returning a sentinel. A float that is not `<= 1` survives the comparison and
#: dies in `range()`; a non-number dies in the comparison itself.
TYPE_ERRORS = [
    (1.5, "range() — a float above the base case reaches range(2, n + 1)"),
    (2.0, "range() — a float above the base case reaches range(2, n + 1)"),
    ("a", "<= — str vs int is not ordered"),
    (None, "<= — NoneType vs int is not ordered"),
    ([1], "<= — list vs int is not ordered"),
]


def selftest(stream=None):
    """Prove this rewrite against ticket #405's acceptance items (a), (b) and (d).

    Builds its own config objects in memory, so it needs no registry, writes no files, and
    leaves no configuration behind. Returns the number of failures.

    Checks, in order:
      1. the config gate — resolution throws ConfigError where no registry exists;
      2. `fib()` throws ConfigError, rather than computing a number, when its config cannot
         be resolved — staged so the result does not depend on whether a registry happens
         to be installed near this module;
      3. every exemplar and edge case, with `trace` null (undecorated);
      4. every exemplar and edge case again, with a trace hook named by the config, which
         is the shape the ORIGINAL ran in — the results must be identical;
      5. the callable surface `fib(n)`, including by keyword.
    """
    out = stream or sys.stdout
    failures = []
    checks = [0]

    def check(ok, label):
        checks[0] += 1
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    saved = configure(None)
    saved_env = os.environ.pop(CONFIG_ENV, None)
    try:
        reset_config()

        with tempfile.TemporaryDirectory() as isolated:
            # 1. the config gate, proven from a directory with no registry above it.
            print("[1] config gate — a tool that cannot see its config throws", file=out)
            if find_registry(isolated) is not None:
                print("  n/a   a %s exists above the temp dir %s, so 'no registry anywhere' "
                      "cannot be staged here; check [2] proves the gate instead"
                      % (REGISTRY_NAME, isolated), file=out)
            else:
                try:
                    load_config(start=isolated)
                    check(False, "load_config() where no %s exists raises ConfigError"
                          % REGISTRY_NAME)
                except ConfigError:
                    check(True, "load_config() where no %s exists raises ConfigError"
                          % REGISTRY_NAME)

            # 2. fib() refuses to compute when its config cannot be resolved.
            #    Staged by pointing FORGE2_CONFIG at a file that does not exist: the env
            #    source outranks the registry walk-up, so this proves the gate the same way
            #    whether or not a registry happens to be installed near this module — and
            #    this package SHIPS one, so a bare fib() here would succeed. Check [1]
            #    cannot do that on its own.
            print("[2] fib() refuses to compute when its config cannot be resolved", file=out)
            os.environ[CONFIG_ENV] = os.path.join(isolated, "no-such-config.json")
            reset_config()
            try:
                got = fib(10)
                check(False, "fib() with an unresolvable config raises ConfigError "
                             "(it returned %r instead)" % (got,))
            except ConfigError:
                check(True, "fib() with an unresolvable config raises ConfigError — no "
                            "number is returned and no default is guessed")
            except Exception as exc:  # noqa: BLE001
                check(False, "fib() with an unresolvable config raised %s, not ConfigError"
                      % type(exc).__name__)
            finally:
                os.environ.pop(CONFIG_ENV, None)
                reset_config()

        # 3 and 4. behavior, undecorated and through a config-named trace hook.
        hook = "%s:_selftest_trace" % __name__
        for label, cfg in (("trace null (undecorated)", {"trace": None}),
                           ("trace hook %r (the shape the original ran in)" % hook,
                            {"trace": hook})):
            print("[%s] behavior with %s" % ("3" if cfg["trace"] is None else "4", label),
                  file=out)
            with using_config(cfg):
                bad = _mismatches(EXEMPLARS)
                check(not bad, "%d/%d ticket exemplars reproduced%s"
                      % (len(EXEMPLARS) - len(bad), len(EXEMPLARS),
                         "" if not bad else " — mismatches: %s" % bad))

                bad = _mismatches(EDGE_CASES)
                check(not bad, "%d/%d edge cases reproduced%s"
                      % (len(EDGE_CASES) - len(bad), len(EDGE_CASES),
                         "" if not bad else " — mismatches: %s" % bad))

                bad = []
                for operand, _why in TYPE_ERRORS:
                    got = _attempt(lambda o=operand: fib(o))
                    # Anything other than a raised TypeError is wrong here: a returned
                    # value means the operand was coerced, and a different exception type
                    # is not the failure the original produced.
                    if not (isinstance(got, _Raised)
                            and got.exception.startswith("TypeError:")):
                        bad.append((operand, got))
                check(not bad, "%d/%d operands the original rejects raise TypeError%s"
                      % (len(TYPE_ERRORS) - len(bad), len(TYPE_ERRORS),
                         "" if not bad else " — wrong outcome: %s" % bad))

                # `n <= 1` returns the ARGUMENT ITSELF in the original. Identity is the
                # sharpest statement of that: a rewrite returning `int(n)` passes every
                # value-comparison above for ints and fails here.
                probe = _IntSubclass(0)
                got = _attempt(lambda: fib(probe))
                check(got is probe and type(got) is _IntSubclass,
                      "fib(n) for n <= 1 returns the argument itself (int-subclass "
                      "instance survives with its type and identity intact)")

                # The original is iterative, so deep n is a plain loop, not a stack. A
                # recursive implementation raises RecursionError here; `_attempt` turns that
                # into a reported FAIL rather than letting it abort the whole selftest.
                deep = _attempt(lambda: fib(2000))
                check(type(deep) is int and len(str(deep)) == 418 and deep % 10 == 5,
                      "fib(2000) computes iteratively — a 418-digit int, no RecursionError"
                      + (" (raised %s)" % deep.exception if isinstance(deep, _Raised) else ""))

        # 5. the callable surface.
        print("[5] callable surface", file=out)
        with using_config({"trace": None}):
            signature = str(inspect.signature(fib))
            check(signature == "(n)", "fib%s matches the ticket's surface fib(n)" % signature)
            check(_same(fib(n=10), 55), "fib(n=10) == 55 — the parameter is named n")
    finally:
        os.environ.pop(CONFIG_ENV, None)
        if saved_env is not None:
            os.environ[CONFIG_ENV] = saved_env
        reset_config()
        globals()["_ACTIVE"] = saved

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED",
             checks[0], len(failures)), file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


def _same(got, want):
    """Compare like the oracle does: equal in value AND in type.

    `==` alone would call `fib(True) == True` a pass even if it returned the int `1`, and
    `fib(3) == 2` a pass for `2.0`. The original returns `n` itself below the base case and
    an int above it, so the type is part of the behavior being preserved.
    """
    return type(got) is type(want) and got == want


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report
    its original error. No report is filed for a ConfigError or for the TypeError the
    original itself raises — both are designed behavior rather than bugs. Returns the path
    written, or None.
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
                                                   " ".join(argv)),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": formatted.strip().splitlines()[-6:],
        "note": "%s (ticket #405, module key forge-rw:f3df615229b4c9f7)" % UNIT,
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
        prog="forge2-fib",
        description="forge2 rewrite of the forge unit artifact_tree_gen:fib.py "
                    "(ticket #405). Config-driven: every command below except "
                    "`emit-config` and `selftest` throws if it cannot see its config "
                    "object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="config is read from the file named by $%s, else from the %s section of the "
               "nearest %s found by walking up from this module. This package ships one "
               "beside the module, so `fib` works from a clean checkout. Run `emit-config` "
               "for a template." % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_fib = sub.add_parser("fib", help="print the n-th Fibonacci number")
    p_fib.add_argument("n", help="index, as a Python literal (10, 0, -1, True)")

    sub.add_parser("selftest", help="prove the exemplars, the edges and the config gate")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and its source")
    return parser


def main(argv=None):
    """Entry point for the `forge2-fib` console script. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at "
                  "it.\n# Until it is installed, `fib` throws — it will not guess a default."
                  % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV), file=sys.stderr)
            return 0

        if args.command == "selftest":
            return 0 if selftest() == 0 else 1

        if args.command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(),
                              "base": active_base(), "config": active_config()}, indent=2))
            return 0

        if args.command == "fib":
            try:
                n = ast.literal_eval(args.n)
            except (ValueError, SyntaxError) as exc:
                print("fib: n must be a Python literal (10, 0, -1, True): %s" % exc,
                      file=sys.stderr)
                return 2
            try:
                result = fib(n)
            except TypeError as exc:
                # The operand reached an operator that rejects it; the original raised this
                # too, so it is designed behavior and files no bug report. Scoped to this
                # one call on purpose — a TypeError raised anywhere else is a defect in this
                # tool, and must fall through to the bug-report handler below rather than be
                # reported as a bad operand.
                print("fib: %s" % exc, file=sys.stderr)
                return 1
            print(repr(result))
            return 0

    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        path = _bug_report(exc, traceback.format_exc(), argv)
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise

    return 0


if __name__ == "__main__":
    sys.exit(main())
