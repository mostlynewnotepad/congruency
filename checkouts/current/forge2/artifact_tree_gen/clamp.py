#!/usr/bin/env python3
"""forge2 / artifact_tree_gen / clamp — a behavior-preserving rewrite of the forge unit
`artifact_tree_gen:clamp.py` (module key forge-rw:cf943417270f2863), filed under ticket #395
against the FORGE-wide refactor standard #200.

WHAT THIS IS
------------
The original forge unit was 123 bytes: it imported a telemetry decorator from
`code_pipeline`, applied it to a three-argument function, and returned that function's one
expression. This file is an entirely new implementation of that unit. It keeps the
original's observable behavior and its callable surface, and it adds the three things #200
requires that the original lacked: it is a proper installable package, it is driven by a
configuration object, and it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    clamp(x, lo, hi)

`clamp` confines `x` to a range: it takes the SMALLER of `x` and `hi`, then the LARGER of
`lo` and that. It is built from the `min` and `max` builtins, in that composition and that
argument order, and three consequences of this — each verified against the original in
`selftest` — are part of the behavior, not accidents:

  * `lo` WINS. The lower bound is applied last, so when the bounds are inverted (`lo > hi`)
    the answer is `lo`: `clamp(2, 1, 0) == 1`, NOT `0`. A rewrite built from the more
    obvious `if x < lo: return lo; if x > hi: return hi; return x` returns `0` here and is
    therefore NOT this function.
  * The RESULT OBJECT is one of the three arguments — `min`/`max` select, they do not
    compute — so its TYPE comes from whichever argument won: `clamp(1.5, 0, True)` is
    `True`, a `bool`, not `1`; `clamp(1, 1.0, 2)` is `1.0`, a `float`. Ties go to the
    incumbent, because `min(a, b)` returns `a` unless `b` is strictly smaller and
    `max(a, b)` returns `a` unless `b` is strictly greater.
  * `min`/`max` are generic, so `clamp` inherits every meaning `<` and `>` have for the
    types it is handed: strings order lexicographically (`clamp("m", "a", "z") == "m"`), and
    a set of operands Python refuses to order raises `TypeError` from the comparison itself.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a
    single `.json` file holding the configuration for every tool in a package, which
    registry-gated tools "walk UP the tree to find" and "throw if it cannot see". This
    package ships its own at `registry.json`, beside this file.
config object
    The chunk of that registry belonging to this unit — the `forge2.artifact_tree_gen.clamp`
    section. It is what drives this module. `emit-config` prints a template of it.
trace hook
    The telemetry decorator. The original HARDCODED this as `from code_pipeline import
    trace`. A hardcoded dependency is exactly what #200's control-config requirement
    forbids, and `code_pipeline` is not importable everywhere this unit must run, so here
    the hook is named BY THE CONFIG instead (the `"trace"` key). A trace hook is telemetry:
    it records the call and returns the wrapped result unchanged, so it does not alter what
    `clamp` returns. That pass-through property is what the original's captured exemplars
    encode, and `selftest` proves the results are identical with the hook on and off.
exemplar
    A real `(input, output)` pair taken from the ORIGINAL acting as the oracle — #200's
    "verified, not asserted". `EXEMPLARS` below is the table; `selftest` replays it.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
`clamp()` resolves its config object on first use, from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. This file holds the unit
     config object itself — exactly what `emit-config` prints.
  2. otherwise, the `forge2.artifact_tree_gen.clamp` section of the nearest `registry.json`
     found by walking UP from THIS FILE's directory. This package ships one there, so an
     unmodified checkout resolves to it and `clamp` runs.

If NEITHER answers, `clamp()` raises `ConfigError` and does not compute a value. It never
guesses a default — that is `note-for-claude`'s rule and this ticket's acceptance item (d).
A config object that is found but is missing a key this operation needs is also a
`ConfigError`, naming the key. `selftest` check [2] proves the gate by staging exactly that.

`configure(config)` and `using_config(config)` inject a config object directly, in-process,
for callers that hold their configuration in memory rather than on disk.

The only config key `clamp()` itself needs is `"trace"`, which must be present and is either
`null` (call the function undecorated) or a `"module:attr"` string naming the trace hook to
apply. Nothing is defaulted.

RUNNING IT
----------
Every command below is executable as written from this file's own directory; from anywhere
else, give the full path to `clamp.py` instead of the bare name. Which directory you run
from does not change what config is found — the registry walk-up starts at THIS FILE, never
at the working directory.

    python3 clamp.py clamp 5 0 3          # -> 3   (needs config; throws without it)
    python3 clamp.py clamp -5 0 3         # -> 0   (a leading '-' is fine; see below)
    python3 clamp.py selftest             # prove the exemplars, the edges and the config gate
    python3 clamp.py check-package        # prove this package's pyproject.toml is coherent
    python3 clamp.py emit-config          # print a config-object template
    python3 clamp.py show-config          # print the resolved config + where it came from

`clamp X LO HI` reads each argument as a Python literal (`ast.literal_eval`), so `clamp 5 0
3` passes integers and `clamp '"m"' '"a"' '"z"'` passes strings. Negative numbers work
bare, but an operand that starts with `-` and is not a plain number (`-1e5`) must follow a
`--` separator: `python3 clamp.py clamp -- -1e5 0 3`.

To prove acceptance item (d) — that this throws rather than guessing — point the config
environment variable at a file that does not exist:

    FORGE2_CONFIG=/nonexistent.json python3 clamp.py clamp 5 0 3    # -> exit 2, config error

INSTALLABLE (#200 requirement 3)
--------------------------------
This directory IS the package, and ticket #395 lands the whole of it — `pyproject.toml`,
`registry.json`, `__init__.py` and this module — so it installs from its own source with no
generation step:

    pip install -e .        # from this directory
    forge2-clamp clamp 5 0 3                 # -> 3
    python3 -c "from artifact_tree_gen.clamp import clamp"

`pyproject.toml` maps the import package `artifact_tree_gen` onto this directory and
declares the `forge2-clamp` console script pointing at this module's `main`.

HOW FAR THIS WAS VERIFIED — and where it stops
----------------------------------------------
Everything `selftest` and `check-package` print was RUN, and you can re-run both with
nothing but `python3`. `check-package` parses the real `pyproject.toml`, resolves the
console-script target to a live callable, and imports the package under the name the
pyproject declares — which is what makes an install work.

`pip install -e .` ITSELF was NOT executed when this was written: the sandbox that builds
this ticket permits no `pip install` and has no `setuptools` to build with, so the claim
would have been untestable there. It is stated here as the package's design, checked by
`check-package`, and NOT as something observed. Run it yourself in an environment that has
a build backend.

SIDE EFFECTS
------------
`clamp()`, `emit-config`, `show-config`, `check-package` and `selftest` create no files and
write nothing; `selftest` builds its config objects in memory and restores every global and
environment variable it touches.

`check-package` imports this package in order to resolve its console script, which would
normally leave a `__pycache__` directory beside the source — it switches bytecode writing
off for the duration so that it does not. (Importing this package from your OWN code writes
`__pycache__` just as it would for any package; that is Python's doing, not a command of
this module's.)

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an
exception is thrown") the CLI appends one timestamped JSON line to the config's
`bug_reports` path if it hits an UNEXPECTED exception. A `ConfigError` is designed behavior,
not a bug, so it files no report and prints no traceback: it exits 2 with a single
self-explaining line.
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

__all__ = ["clamp", "ConfigError", "load_config", "configure", "using_config", "reset_config"]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own
#: ADDRESS in the config document, not a configurable setting — a config-driven tool has to
#: know which section is its own.
UNIT_PATH = ("forge2", "artifact_tree_gen", "clamp")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:artifact_tree_gen/clamp"

#: The import package this module belongs to, as `pyproject.toml` declares it. Used only by
#: `check-package`, to check the packaging against itself.
IMPORT_PACKAGE = "artifact_tree_gen"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.
    """


# ─────────────────────────────── the unit itself ───────────────────────────────

def _core(x, lo, hi):
    """The rewritten unit body: `x` confined to the range the bounds describe.

    Two selections, in this order — the order IS the behavior:
      1. `min(x, hi)` takes `x` unless `hi` is strictly smaller, capping `x` from above;
      2. `max(lo, ...)` takes `lo` unless that capped value is strictly greater.

    Because the lower bound is applied SECOND it wins outright when the bounds are inverted
    (`lo > hi` gives `lo`), and because `min`/`max` select an argument rather than compute a
    new value, the object returned is one of `x`, `lo`, `hi` itself.
    """
    capped_above = min(x, hi)
    return max(lo, capped_above)


def clamp(x, lo, hi):
    """Return `x` confined to the bounds `lo` and `hi` — the rewrite of the forge unit
    `artifact_tree_gen:clamp.py`.

    Equivalent to taking the smaller of `x` and `hi`, then the larger of `lo` and that. The
    lower bound is applied last, so it wins when the bounds are inverted: `clamp(2, 1, 0)`
    is `1`. The value returned is one of the three arguments, so its type is that
    argument's: `clamp(1.5, 0, True)` is `True`. Any operands Python cannot order raise
    `TypeError` from the comparison.

    If the config object names a trace hook, the hook wraps the call; a trace hook is
    telemetry and returns the wrapped result unchanged, so the value below is the same
    either way.

    Raises:
        ConfigError: if no config object can be resolved, or it lacks the `trace` key.
        TypeError: if the operands cannot be ordered — raised by the comparison, as in the
            original.
    """
    return _traced_core()(x, lo, hi)


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
_RESOLVED = None    # cache of the last disk resolution, so clamp() re-reads no files


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
    operator installs it, and until they do `clamp()` throws.
    """
    return {
        "trace": None,
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ───────────────────────── the exemplars and the edges ─────────────────────────

#: The captured exemplars this rewrite must reproduce, taken from the ORIGINAL unit acting
#: as the oracle — never from this rewrite.
#:
#: Ticket #395 quotes six pairs verbatim and says "18 more" (24 captured). Those 24 are the
#: first 24 of the nested product over the probe values {0, 1, -1, 1.5, True} with `hi`
#: varying fastest, then `lo`, then `x` — i.e. the `x = 0` slice, cut at the miner's 24-pair
#: cap. (The `add.py` unit of this same package, ticket #401, reports the same 24 cap.) The
#: table below is the WHOLE 5x5x5 = 125-row product, so it is a strict superset of the 24
#: that were captured, and every one of the six quoted pairs appears in it verbatim.
EXEMPLARS = [
    # x = 0
    ((0, 0, 0), 0), ((0, 0, 1), 0), ((0, 0, -1), 0), ((0, 0, 1.5), 0), ((0, 0, True), 0),
    ((0, 1, 0), 1), ((0, 1, 1), 1), ((0, 1, -1), 1), ((0, 1, 1.5), 1), ((0, 1, True), 1),
    ((0, -1, 0), 0), ((0, -1, 1), 0), ((0, -1, -1), -1), ((0, -1, 1.5), 0), ((0, -1, True), 0),
    ((0, 1.5, 0), 1.5), ((0, 1.5, 1), 1.5), ((0, 1.5, -1), 1.5), ((0, 1.5, 1.5), 1.5), ((0, 1.5, True), 1.5),
    ((0, True, 0), True), ((0, True, 1), True), ((0, True, -1), True), ((0, True, 1.5), True), ((0, True, True), True),
    # x = 1
    ((1, 0, 0), 0), ((1, 0, 1), 1), ((1, 0, -1), 0), ((1, 0, 1.5), 1), ((1, 0, True), 1),
    ((1, 1, 0), 1), ((1, 1, 1), 1), ((1, 1, -1), 1), ((1, 1, 1.5), 1), ((1, 1, True), 1),
    ((1, -1, 0), 0), ((1, -1, 1), 1), ((1, -1, -1), -1), ((1, -1, 1.5), 1), ((1, -1, True), 1),
    ((1, 1.5, 0), 1.5), ((1, 1.5, 1), 1.5), ((1, 1.5, -1), 1.5), ((1, 1.5, 1.5), 1.5), ((1, 1.5, True), 1.5),
    ((1, True, 0), True), ((1, True, 1), True), ((1, True, -1), True), ((1, True, 1.5), True), ((1, True, True), True),
    # x = -1
    ((-1, 0, 0), 0), ((-1, 0, 1), 0), ((-1, 0, -1), 0), ((-1, 0, 1.5), 0), ((-1, 0, True), 0),
    ((-1, 1, 0), 1), ((-1, 1, 1), 1), ((-1, 1, -1), 1), ((-1, 1, 1.5), 1), ((-1, 1, True), 1),
    ((-1, -1, 0), -1), ((-1, -1, 1), -1), ((-1, -1, -1), -1), ((-1, -1, 1.5), -1), ((-1, -1, True), -1),
    ((-1, 1.5, 0), 1.5), ((-1, 1.5, 1), 1.5), ((-1, 1.5, -1), 1.5), ((-1, 1.5, 1.5), 1.5), ((-1, 1.5, True), 1.5),
    ((-1, True, 0), True), ((-1, True, 1), True), ((-1, True, -1), True), ((-1, True, 1.5), True), ((-1, True, True), True),
    # x = 1.5
    ((1.5, 0, 0), 0), ((1.5, 0, 1), 1), ((1.5, 0, -1), 0), ((1.5, 0, 1.5), 1.5), ((1.5, 0, True), True),
    ((1.5, 1, 0), 1), ((1.5, 1, 1), 1), ((1.5, 1, -1), 1), ((1.5, 1, 1.5), 1.5), ((1.5, 1, True), 1),
    ((1.5, -1, 0), 0), ((1.5, -1, 1), 1), ((1.5, -1, -1), -1), ((1.5, -1, 1.5), 1.5), ((1.5, -1, True), True),
    ((1.5, 1.5, 0), 1.5), ((1.5, 1.5, 1), 1.5), ((1.5, 1.5, -1), 1.5), ((1.5, 1.5, 1.5), 1.5), ((1.5, 1.5, True), 1.5),
    ((1.5, True, 0), True), ((1.5, True, 1), True), ((1.5, True, -1), True), ((1.5, True, 1.5), 1.5), ((1.5, True, True), True),
    # x = True
    ((True, 0, 0), 0), ((True, 0, 1), True), ((True, 0, -1), 0), ((True, 0, 1.5), True), ((True, 0, True), True),
    ((True, 1, 0), 1), ((True, 1, 1), 1), ((True, 1, -1), 1), ((True, 1, 1.5), 1), ((True, 1, True), 1),
    ((True, -1, 0), 0), ((True, -1, 1), True), ((True, -1, -1), -1), ((True, -1, 1.5), True), ((True, -1, True), True),
    ((True, 1.5, 0), 1.5), ((True, 1.5, 1), 1.5), ((True, 1.5, -1), 1.5), ((True, 1.5, 1.5), 1.5), ((True, 1.5, True), 1.5),
    ((True, True, 0), True), ((True, True, 1), True), ((True, True, -1), True), ((True, True, 1.5), True), ((True, True, True), True),
]

_NAN = float("nan")

#: Edge cases the mining could not reach. #395 records criteria_miner's own honest limit —
#: the exemplars "cover the SAMPLED inputs" and are "NOT a proof of total equivalence" — and
#: asks for the edges sampling misses. Every expected value here was likewise read off the
#: ORIGINAL as the oracle. The sampled grid above cannot reach any of these, because every
#: probe value in it is a small number and 0/1/-1/1.5/True happen to make the two most
#: plausible WRONG rewrites look right.
EDGE_CASES = [
    # The inversion lo > hi. THE discriminator: the `if x < lo ... elif x > hi ...` rewrite
    # returns hi for these, the original returns lo. The sampled grid never catches it,
    # because whenever lo > hi there it also holds that x <= lo, which both spellings agree
    # on.
    ((2, 1, 0), 1),
    ((10, 5, 0), 5),
    ((2, 3, 10), 3),                # x below an ordinary range: lo
    # Ordinary clamping, above / below / inside.
    ((5, 0, 3), 3), ((-5, 0, 3), 0), ((2, 0, 3), 2),
    # Type is carried by the ARGUMENT THAT WON — min/max select, they never compute.
    ((1.5, 0, True), True),         # bool, not 1 — the winner is the `hi` object
    ((1, True, 2), True),           # bool, not 1 — ties go to `lo`, which is True
    ((1, 1.0, 2), 1.0),             # float, not 1 — max(1.0, 1) keeps the incumbent 1.0
    ((1.0, 1, 2), 1),               # int, not 1.0 — the mirror of the line above
    # min/max are generic: any orderable type works, exactly as it did in the original.
    (("m", "a", "z"), "m"), (("A", "a", "z"), "a"), (("~", "a", "z"), "z"),
    # No rounding, widening or overflow of the value that won.
    ((2 ** 63, 0, 2 ** 64), 2 ** 63),
    ((0.1 + 0.2, 0, 1), 0.30000000000000004),
    # NaN compares False against everything, so both selections keep their incumbent.
    ((_NAN, 0, 1), 0),              # min(nan,1) -> nan; max(0, nan) -> 0
    ((0, _NAN, 1), _NAN),           # min(0,1) -> 0;   max(nan, 0) -> nan
    ((0, 0, _NAN), 0),
]

#: Operand sets Python refuses to order: the original raised TypeError from the comparison
#: inside min/max, so this rewrite must too, rather than coercing or returning a sentinel.
TYPE_ERRORS = [(1, "x", 2), ("a", 1, 2), (1, 2, "x"), (None, 0, 1), ([1], 0, 1)]


def _same(got, want):
    """Compare like the oracle does: equal in value AND in type.

    `==` alone would call `clamp(1.5, 0, True) == 1` a pass even though the original returns
    the `bool` True, and would accept `1.0` where the original returns `1`. The original
    returns one of its ARGUMENTS, so the type is part of the behavior being preserved.

    NaN needs its own arm: it is never equal to itself, so the plain `==` below would report
    a correct NaN result as a mismatch. Two NaNs count as the same answer here.
    """
    if type(got) is not type(want):
        return False
    if isinstance(want, float) and want != want:        # want is NaN
        return got != got
    return got == want


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


def selftest(stream=None):
    """Prove this rewrite against ticket #395's acceptance items (a), (b) and (d).

    Builds its own config objects in memory, so it needs no registry, writes no files, and
    leaves no configuration behind. Returns the number of failures.

    Checks, in order:
      1. the config gate — resolution throws ConfigError where no registry exists;
      2. `clamp()` throws ConfigError, rather than computing a value, when its config cannot
         be resolved — staged via the environment variable so the result does not depend on
         this package's own shipped registry being present;
      3. every exemplar and edge case, with `trace` null (undecorated);
      4. every exemplar and edge case again, through a trace hook named by the config, which
         is the shape the ORIGINAL ran in — the results must be identical;
      5. the callable surface `clamp(x, lo, hi)`, including by keyword, and the
         result-is-an-argument-object property.
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

            # 2. clamp() refuses to compute when its config cannot be resolved.
            #    Staged by pointing FORGE2_CONFIG at a file that does not exist: the env
            #    source outranks the registry walk-up, so this proves the gate even though
            #    this package ships a registry of its own right beside this module. Check
            #    [1] cannot do that on its own.
            print("[2] clamp() refuses to compute when its config cannot be resolved", file=out)
            os.environ[CONFIG_ENV] = os.path.join(isolated, "no-such-config.json")
            reset_config()
            try:
                got = clamp(5, 0, 3)
                check(False, "clamp() with an unresolvable config raises ConfigError "
                             "(it returned %r instead)" % (got,))
            except ConfigError:
                check(True, "clamp() with an unresolvable config raises ConfigError — no "
                            "value is returned and no default is guessed")
            except Exception as exc:  # noqa: BLE001
                check(False, "clamp() with an unresolvable config raised %s, not ConfigError"
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
                bad = [(args, want, clamp(*args)) for args, want in EXEMPLARS
                       if not _same(clamp(*args), want)]
                check(not bad, "%d/%d captured exemplars reproduced%s"
                      % (len(EXEMPLARS) - len(bad), len(EXEMPLARS),
                         "" if not bad else " — mismatches: %s" % bad))

                bad = [(args, want, clamp(*args)) for args, want in EDGE_CASES
                       if not _same(clamp(*args), want)]
                check(not bad, "%d/%d edge cases reproduced%s"
                      % (len(EDGE_CASES) - len(bad), len(EDGE_CASES),
                         "" if not bad else " — mismatches: %s" % bad))

                bad = []
                for args in TYPE_ERRORS:
                    try:
                        clamp(*args)
                        bad.append(args)
                    except TypeError:
                        pass
                check(not bad, "%d/%d unorderable operand sets raise TypeError%s"
                      % (len(TYPE_ERRORS) - len(bad), len(TYPE_ERRORS),
                         "" if not bad else " — did not raise: %s" % bad))

        # 5. the callable surface.
        print("[5] callable surface", file=out)
        with using_config({"trace": None}):
            signature = str(inspect.signature(clamp))
            check(signature == "(x, lo, hi)",
                  "clamp%s matches the ticket's surface clamp(x, lo, hi)" % signature)
            check(clamp(x=5, lo=0, hi=3) == 3,
                  "clamp(x=5, lo=0, hi=3) == 3 — the parameters are named x, lo, hi")
            # min/max SELECT an argument; they never build a new object. Identity is how you
            # tell a selection from a computation, and `==` cannot see the difference.
            x_obj, lo_obj, hi_obj = [2], [1], [3]
            check(clamp(x_obj, lo_obj, hi_obj) is x_obj
                  and clamp([5], lo_obj, hi_obj) is hi_obj
                  and clamp([0], lo_obj, hi_obj) is lo_obj,
                  "the result IS the winning argument object (a selection, not a copy)")
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


# ──────────────────────── the packaging, checked against itself ────────────────────────

def check_package(stream=None):
    """Check this package's `pyproject.toml` against this module. Returns failure count.

    Acceptance item (c) is `pip install -e .`. That command cannot run in the sandbox this
    ticket was built in (no `pip install`, no build backend), so this check proves the parts
    of it that ARE checkable with the standard library alone, and claims nothing more:

      * the pyproject exists, parses, and declares a build backend;
      * it carries the PEP 621 fields an install needs (`name`, `version`);
      * it maps the import package onto this directory, so this module ships inside it;
      * every console script it declares resolves to a real callable — resolved exactly the
        way an installed script's `module:attr` target is;
      * the import package imports under the name the pyproject declares, and exposes clamp.

    Reads only; writes nothing. Prints `n/a` and passes when there is no pyproject beside
    this module, which is the normal state of an INSTALLED copy.
    """
    out = stream or sys.stdout
    failures = []

    def check(ok, label):
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    here = os.path.dirname(os.path.abspath(__file__))
    pyproject = os.path.join(here, "pyproject.toml")
    print("[package] %s" % pyproject, file=out)
    if not os.path.isfile(pyproject):
        print("  n/a   no pyproject.toml beside this module — the normal state of an "
              "installed copy; nothing to check", file=out)
        return 0
    try:
        import tomllib
    except ImportError:
        print("  n/a   tomllib needs Python 3.11+ (running %d.%d) — cannot parse the "
              "pyproject here" % (sys.version_info[0], sys.version_info[1]), file=out)
        return 0

    with open(pyproject, "rb") as handle:
        try:
            data = tomllib.load(handle)
        except Exception as exc:  # noqa: BLE001
            check(False, "pyproject.toml parses as TOML (%s)" % exc)
            return len(failures)
    check(True, "pyproject.toml parses as TOML")

    backend = data.get("build-system", {})
    check(bool(backend.get("build-backend")) and bool(backend.get("requires")),
          "declares a build backend and its requirements: %r / %r"
          % (backend.get("build-backend"), backend.get("requires")))

    project = data.get("project", {})
    check(bool(project.get("name")) and bool(project.get("version")),
          "declares the PEP 621 fields an install needs: name=%r version=%r"
          % (project.get("name"), project.get("version")))

    setup = data.get("tool", {}).get("setuptools", {})
    packages = setup.get("packages", [])
    check(IMPORT_PACKAGE in packages,
          "declares the import package %r in tool.setuptools.packages %r"
          % (IMPORT_PACKAGE, packages))
    check(setup.get("package-dir", {}).get(IMPORT_PACKAGE) == ".",
          "maps %r onto this directory, so %s ships inside it"
          % (IMPORT_PACKAGE, os.path.basename(os.path.abspath(__file__))))

    # Resolve each console script the way an installed one is: import `module`, getattr
    # `attr`. The parent of this package directory is what an editable install effectively
    # puts on sys.path, so put it there for the duration and take it back off.
    #
    # Importing a package normally writes a __pycache__ directory beside its source. This
    # command promises to create no files, so bytecode writing is switched OFF for the
    # duration of the imports below and restored afterwards — the check reads the same
    # answer either way, so the option that touches nothing is the one to take.
    parent = os.path.dirname(here)
    added = parent not in sys.path
    if added:
        sys.path.insert(0, parent)
    bytecode_was = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        scripts = project.get("scripts", {})
        check(bool(scripts), "declares at least one console script: %r" % (scripts,))
        for name, target in sorted(scripts.items()):
            mod_name, _, attr = target.partition(":")
            try:
                module = importlib.import_module(mod_name)
                entry = getattr(module, attr)
                ok = callable(entry)
            except (ImportError, AttributeError) as exc:
                ok, entry = False, exc
            check(ok, "console script %r -> %r resolves to a callable (%r)"
                  % (name, target, entry))
        try:
            package = importlib.import_module(IMPORT_PACKAGE)
            ok = callable(getattr(package, "clamp", None))
        except ImportError as exc:
            ok, package = False, exc
        check(ok, "`import %s` works and exposes clamp — %r" % (IMPORT_PACKAGE, package))
    finally:
        sys.dont_write_bytecode = bytecode_was
        if added and parent in sys.path:
            sys.path.remove(parent)

    print("\n%s — %d failure(s)"
          % ("PACKAGE CHECK PASSED" if not failures else "PACKAGE CHECK FAILED",
             len(failures)), file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report
    its original error, and a report is never filed for a ConfigError, which is designed
    behavior rather than a bug. Returns the path written, or None.
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
        "note": "%s (ticket #395, module key forge-rw:cf943417270f2863)" % UNIT,
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
        prog="forge2-clamp",
        description="forge2 rewrite of the forge unit artifact_tree_gen:clamp.py "
                    "(ticket #395). clamp(x, lo, hi) confines x to the bounds: the smaller "
                    "of x and hi, then the larger of lo and that. Config-driven: `clamp` "
                    "and `show-config` throw if they cannot see their config object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="config is read from the file named by $%s, else from the %s section of the "
               "nearest %s found by walking up from this module. Run `emit-config` for a "
               "template." % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_clamp = sub.add_parser(
        "clamp", help="clamp a Python literal to bounds and print the result",
        description="Read X, LO and HI as Python literals and print clamp(X, LO, HI). A "
                    "leading '-' is fine for plain negative numbers (clamp -5 0 3); for "
                    "anything else that starts with '-', use a '--' separator first: "
                    "clamp -- -1e5 0 3")
    p_clamp.add_argument("x", help="the value to confine, as a Python literal (5, 1.5, '\"m\"')")
    p_clamp.add_argument("lo", help="the lower bound, as a Python literal")
    p_clamp.add_argument("hi", help="the upper bound, as a Python literal")

    sub.add_parser("selftest", help="prove the exemplars, the edges and the config gate")
    sub.add_parser("check-package", help="prove this package's pyproject.toml is coherent")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and its source")
    return parser


def main(argv=None):
    """Entry point for the `forge2-clamp` console script. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at "
                  "it.\n# Until it is installed, `clamp` throws — it will not guess a default."
                  % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV), file=sys.stderr)
            return 0

        if args.command == "selftest":
            return 0 if selftest() == 0 else 1

        if args.command == "check-package":
            return 0 if check_package() == 0 else 1

        if args.command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(),
                              "base": active_base(), "config": active_config()}, indent=2))
            return 0

        if args.command == "clamp":
            try:
                x = ast.literal_eval(args.x)
                lo = ast.literal_eval(args.lo)
                hi = ast.literal_eval(args.hi)
            except (ValueError, SyntaxError) as exc:
                print("clamp: operands must be Python literals (5, 1.5, '\"m\"'): %s"
                      % exc, file=sys.stderr)
                return 2
            try:
                result = clamp(x, lo, hi)
            except TypeError as exc:
                # The operands cannot be ordered; the original raised this too. Scoped to
                # this one call on purpose — a TypeError raised anywhere else is a defect in
                # this tool, and must fall through to the bug-report handler below rather
                # than be reported as bad operands.
                print("clamp: %s" % exc, file=sys.stderr)
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
