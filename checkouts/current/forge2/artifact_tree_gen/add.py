#!/usr/bin/env python3
"""forge2 / artifact_tree_gen / add — a behavior-preserving rewrite of the forge unit
`artifact_tree_gen:add.py` (module key forge-rw:e42d2d08fe5ef45b), filed under ticket #401
against the FORGE-wide refactor standard #200.

WHAT THIS IS
------------
The original forge unit was 102 bytes: it imported a telemetry decorator from
`code_pipeline`, applied it to a two-argument function, and returned `a + b`. This file is
an entirely new implementation of that unit. It keeps the original's observable behavior
and its callable surface, and it adds the three things #200 requires that the original
lacked: it is a proper installable package, it is driven by a configuration object, and it
refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    add(a, b)

`add` returns the sum of its two arguments, in that order, by delegating to Python's `+`.
`+` is polymorphic, so `add` inherits every meaning `+` has for the types it is handed:
integers and floats add numerically, `bool` is a subclass of `int` so `add(True, True)` is
`2`, strings and lists and tuples concatenate, and a pair of types that `+` rejects raises
`TypeError` from the operator itself. The original did exactly this and so does this
rewrite. Argument ORDER is part of the surface: `add("a", "b") == "ab"`, never `"ba"`.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a
    single `.json` file at the package root holding the configuration for every tool in the
    package. This repository's copy is `registry.json` at the repo root, and its own
    `_comment` states the contract that registry-gated tools "walk UP the tree to find this
    file and throw if it cannot see it".
config object
    The chunk of that registry belonging to this unit — the `forge2.artifact_tree_gen.add`
    section. It is what drives this module. `emit-config` prints a template of it.
trace hook
    The telemetry decorator. The original HARDCODED this as `from code_pipeline import
    trace`. A hardcoded dependency is exactly what #200's control-config requirement
    forbids, and `code_pipeline` is not importable everywhere this unit must run, so here
    the hook is named BY THE CONFIG instead (`"trace"`). A trace hook is telemetry: it
    records the call and returns the wrapped result unchanged, so it does not alter what
    `add` returns. That pass-through property is what the original's captured exemplars
    encode.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
`add()` resolves its config object on first use, from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. This file holds the unit
     config object itself — exactly what `emit-config` prints.
  2. otherwise, the `forge2.artifact_tree_gen.add` section of the nearest `registry.json`
     found by walking UP from this file's directory.

If NEITHER answers, `add()` raises `ConfigError` and does not compute a sum. It never
guesses a default — that is `note-for-claude`'s rule ("if a tool cannot see the registry it
will throw an exception") and this ticket's acceptance item (d). A config object that is
found but is missing a key this operation needs is also a `ConfigError`, naming the key.

`configure(config)` and `using_config(config)` inject a config object directly, in-process,
for callers that hold their configuration in memory rather than on disk.

The only config key `add()` itself needs is `"trace"`, which must be present and is either
`null` (call the function undecorated) or a `"module:attr"` string naming the trace hook to
apply. `emit-package` additionally needs the `"package"` block. Nothing is defaulted.

RUNNING IT
----------
Every command below is executable as written from this file's own directory; from anywhere
else, give the full path to `add.py` instead of the bare name. Which directory you run from
does not change what config is found — the registry walk-up starts at THIS FILE, never at
the working directory.

    python3 add.py emit-config                 # print a config-object template
    python3 add.py show-config                 # print the resolved config + where it came from
    python3 add.py selftest                    # prove the exemplars and the config gate
    python3 add.py add 2 3                     # -> 5   (needs config; throws without it)
    python3 add.py emit-package --target DIR   # write an installable package into DIR

`add A B` reads each argument as a Python literal (`ast.literal_eval`), so `add 2 3` passes
integers and `add '"a"' '"b"'` passes strings.

In THIS repository `add` and `show-config` exit 2 with a one-line config error, because the
repo's own `registry.json` carries no `forge2` section. That is acceptance item (d) working,
not a defect. `selftest` needs no installed config and proves the behavior regardless.

INSTALLABLE (#200 requirement 3)
--------------------------------
Ticket #401's deliverable is this single file and it may touch nothing else, so the package
is not committed beside it — this file CARRIES its package and writes it on demand:

    python3 add.py emit-package --target /tmp/pkg --with-registry
    pip install -e /tmp/pkg
    forge2-add add 2 3                         # -> 5

`emit-package` writes a `pyproject.toml` plus a package directory holding a copy of this
module, so `pip install -e` installs it clean. The distribution name, version, import
package name and console-script name all come from the config's `package` block — with the
template's values the import package is `artifact_tree_gen` and the command is `forge2-add`,
but nothing about those names is baked into this file. `--with-registry` also writes a
`registry.json` into the target so the installed copy can see its config; without it the
installed copy finds no config and throws, which is intended behavior, not a defect.

SIDE EFFECTS
------------
`add()`, `emit-config`, `show-config` and `selftest` create no files and write nothing.
`emit-package` writes only inside the target directory you name. Per `note-for-claude`
("all tools need to pass a bug-report automatically ... if an exception is thrown") the CLI
appends one timestamped JSON line to the config's `bug_reports` path if it hits an
UNEXPECTED exception. A `ConfigError` is designed behavior, not a bug, so it files no
report and prints no traceback: it exits 2 with a single self-explaining line.
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

__all__ = ["add", "ConfigError", "load_config", "configure", "using_config", "reset_config"]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own
#: ADDRESS in the config document, not a configurable setting — a config-driven tool has to
#: know which section is its own.
UNIT_PATH = ("forge2", "artifact_tree_gen", "add")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:artifact_tree_gen/add"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.
    """


# ─────────────────────────────── the unit itself ───────────────────────────────

def _core(a, b):
    """The rewritten unit body: the sum of a and b, in that order."""
    return a + b


def add(a, b):
    """Return the sum of `a` and `b` — the rewrite of the forge unit `artifact_tree_gen:add.py`.

    Delegates to Python's `+`, so the result is whatever `+` means for these two operands
    (numeric addition, sequence concatenation, or `TypeError` raised by the operator).
    Argument order is preserved: `add("a", "b") == "ab"`.

    If the config object names a trace hook, the hook wraps the call; a trace hook is
    telemetry and returns the wrapped result unchanged, so the value below is the same
    either way.

    Raises:
        ConfigError: if no config object can be resolved, or it lacks the `trace` key.
    """
    return _traced_core()(a, b)


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
_RESOLVED = None    # cache of the last disk resolution, so add() re-reads no files


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
    operator installs it, and until they do `add()` throws.
    """
    return {
        "trace": None,
        "package": {
            "name": "forge2-artifact-tree-gen-add",
            "version": "1.0.0",
            "distribution": "artifact_tree_gen",
            "console_script": "forge2-add",
            "target": None,
        },
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────────── the installable package ───────────────────────────

PYPROJECT_TEMPLATE = """\
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = %(name)s
version = %(version)s
description = "forge2 rewrite of the forge unit artifact_tree_gen:add.py (module key forge-rw:e42d2d08fe5ef45b, ticket #401)"
requires-python = ">=3.8"
dependencies = []

[project.scripts]
%(console_script)s = "%(distribution)s.add:main"

[tool.setuptools]
packages = [%(distribution_q)s]
"""


def _require(config, key, operation):
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the key %r, which `%s` needs. Run "
            "`emit-config` for a template." % (UNIT, key, operation)
        )
    return config[key]


def emit_package(target=None):
    """Write an installable package for this unit into `target`; return the paths written.

    The package's name, version, distribution (import) name and console script all come
    from the config's `package` block — nothing about it is hardcoded. `target` defaults to
    the config's `package.target`, and it is a `ConfigError` if neither names a directory.
    """
    config = active_config()
    package = _require(config, "package", "emit-package")
    if not isinstance(package, dict):
        raise ConfigError(
            "config key 'package' for %s must be a JSON object, not %s"
            % (UNIT, type(package).__name__)
        )
    for key in ("name", "version", "distribution", "console_script"):
        if not package.get(key):
            raise ConfigError(
                "config key 'package.%s' for %s is required by `emit-package` and is not set"
                % (key, UNIT)
            )

    target = target or package.get("target")
    if not target:
        raise ConfigError(
            "`emit-package` needs a target directory: pass --target DIR, or set "
            "'package.target' in the config object for %s" % UNIT
        )
    target = os.path.abspath(os.path.expanduser(target))
    distribution = package["distribution"]

    source = open(os.path.abspath(__file__), "r", encoding="utf-8").read()
    package_dir = os.path.join(target, distribution)
    os.makedirs(package_dir, exist_ok=True)

    written = []

    pyproject = os.path.join(target, "pyproject.toml")
    with open(pyproject, "w", encoding="utf-8") as handle:
        handle.write(PYPROJECT_TEMPLATE % {
            "name": json.dumps(package["name"]),
            "version": json.dumps(str(package["version"])),
            "console_script": package["console_script"],
            "distribution": distribution,
            "distribution_q": json.dumps(distribution),
        })
    written.append(pyproject)

    init = os.path.join(package_dir, "__init__.py")
    with open(init, "w", encoding="utf-8") as handle:
        handle.write(
            '"""forge2 rewrite of the forge unit artifact_tree_gen:add.py (ticket #401)."""\n'
            "from .add import add, ConfigError, configure, using_config  # noqa: F401\n\n"
            '__all__ = ["add", "ConfigError", "configure", "using_config"]\n'
        )
    written.append(init)

    module = os.path.join(package_dir, "add.py")
    with open(module, "w", encoding="utf-8") as handle:
        handle.write(source)
    written.append(module)

    return {"target": target, "written": written}


def emit_registry(target):
    """Write a registry into `target` holding the config object in force, so a package
    installed from `target` can see its configuration. Returns the path written."""
    config = active_config()
    document = {
        "_comment": "Configuration registry for the forge2 %s package. Tools walk UP the "
                    "tree to find this file and throw if they cannot see it (see the "
                    "congruency repo's note-for-claude)." % UNIT,
        "schema": 1,
    }
    node = document
    for key in UNIT_PATH[:-1]:
        node = node.setdefault(key, {})
    node[UNIT_PATH[-1]] = {k: v for k, v in config.items() if k != "bug_reports"}
    if "bug_reports" in config:
        document["bug_reports"] = config["bug_reports"]
    target = os.path.abspath(os.path.expanduser(target))
    os.makedirs(target, exist_ok=True)
    path = os.path.join(target, REGISTRY_NAME)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(document, indent=2) + "\n")
    return path


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


#: The exemplars this rewrite must reproduce. The first six are the pairs ticket #401 quotes
#: verbatim, in the ticket's own order; the rest complete the 5x5 grid over the constants
#: those six are drawn from ({0, 1, -1, 1.5, True}). Every expected value here was taken
#: from the ORIGINAL unit acting as the oracle, never from this rewrite.
EXEMPLARS = [
    ((0, 0), 0), ((0, 1), 1), ((0, -1), -1), ((0, 1.5), 1.5), ((0, True), 1),
    ((1, 0), 1), ((1, 1), 2), ((1, -1), 0), ((1, 1.5), 2.5), ((1, True), 2),
    ((-1, 0), -1), ((-1, 1), 0), ((-1, -1), -2), ((-1, 1.5), 0.5), ((-1, True), 0),
    ((1.5, 0), 1.5), ((1.5, 1), 2.5), ((1.5, -1), 0.5), ((1.5, 1.5), 3.0), ((1.5, True), 2.5),
    ((True, 0), 1), ((True, 1), 2), ((True, -1), 0), ((True, 1.5), 2.5), ((True, True), 2),
]

#: Edge cases the mining could not reach. #401 records criteria_miner's own honest limit —
#: the exemplars "cover the SAMPLED inputs" and are "NOT a proof of total equivalence" — and
#: asks for the edges sampling misses. These probe what a sum of two small numbers cannot:
#: that `+` is delegated rather than reimplemented, that argument ORDER survives (a rewrite
#: computing `b + a` passes every numeric exemplar above and fails here), that operands `+`
#: rejects still raise TypeError, and that float and big-integer results are not rounded,
#: widened or clamped.
EDGE_CASES = [
    (("a", "b"), "ab"),                      # str concatenation; ORDER-sensitive
    (("b", "a"), "ba"),                      # the mirror: proves add(a,b) is not add(b,a)
    (([1], [2]), [1, 2]),                    # list concatenation
    (((1,), (2,)), (1, 2)),                  # tuple concatenation
    ((0.1, 0.2), 0.30000000000000004),       # float result is unrounded
    ((2 ** 63, 2 ** 63), 2 ** 64),           # big integers do not overflow
    ((1 + 2j, 3), 4 + 2j),                   # complex operands
    ((-1.5, 1.5), 0.0),                      # float zero
    (("", ""), ""),                          # empty-string identity
]

#: Pairs `+` itself rejects: the original raised TypeError from the operator, so this
#: rewrite must too rather than coercing or returning a sentinel.
TYPE_ERRORS = [(1, "x"), (None, None), ("a", 1), ([1], (2,))]


def selftest(stream=None):
    """Prove this rewrite against ticket #401's acceptance items (a), (b) and (d).

    Builds its own config objects in memory, so it needs no registry, writes no files, and
    leaves no configuration behind. Returns the number of failures.

    Checks, in order:
      1. the config gate — resolution throws ConfigError where no registry exists;
      2. `add()` throws ConfigError, rather than computing a sum, when its config cannot
         be resolved — staged so the result does not depend on whether a registry happens
         to be installed near this module;
      3. every exemplar and edge case, with `trace` null (undecorated);
      4. every exemplar and edge case again, with a trace hook named by the config, which
         is the shape the ORIGINAL ran in — the results must be identical;
      5. the callable surface `add(a, b)`, including by keyword.
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

            # 2. add() refuses to compute when its config cannot be resolved.
            #    Staged by pointing FORGE2_CONFIG at a file that does not exist: the env
            #    source outranks the registry walk-up, so this proves the gate the same way
            #    whether or not a registry happens to be installed near this module. Check
            #    [1] cannot do that on its own — an installed package that CAN see its
            #    config would make a bare add() succeed, which is correct behavior, not a
            #    failure.
            print("[2] add() refuses to compute when its config cannot be resolved", file=out)
            os.environ[CONFIG_ENV] = os.path.join(isolated, "no-such-config.json")
            reset_config()
            try:
                got = add(1, 2)
                check(False, "add() with an unresolvable config raises ConfigError "
                             "(it returned %r instead)" % (got,))
            except ConfigError:
                check(True, "add() with an unresolvable config raises ConfigError — no sum "
                            "is returned and no default is guessed")
            except Exception as exc:  # noqa: BLE001
                check(False, "add() with an unresolvable config raised %s, not ConfigError"
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
                bad = [(args, want, add(*args)) for args, want in EXEMPLARS
                       if not _same(add(*args), want)]
                check(not bad, "%d/%d exemplars reproduced%s"
                      % (len(EXEMPLARS) - len(bad), len(EXEMPLARS),
                         "" if not bad else " — mismatches: %s" % bad))

                bad = [(args, want, add(*args)) for args, want in EDGE_CASES
                       if not _same(add(*args), want)]
                check(not bad, "%d/%d edge cases reproduced%s"
                      % (len(EDGE_CASES) - len(bad), len(EDGE_CASES),
                         "" if not bad else " — mismatches: %s" % bad))

                bad = []
                for args in TYPE_ERRORS:
                    try:
                        add(*args)
                        bad.append(args)
                    except TypeError:
                        pass
                check(not bad, "%d/%d unsummable pairs raise TypeError%s"
                      % (len(TYPE_ERRORS) - len(bad), len(TYPE_ERRORS),
                         "" if not bad else " — did not raise: %s" % bad))

        # 5. the callable surface.
        print("[5] callable surface", file=out)
        with using_config({"trace": None}):
            signature = str(inspect.signature(add))
            check(signature == "(a, b)", "add%s matches the ticket's surface add(a, b)"
                  % signature)
            check(add(a=1, b=2) == 3, "add(a=1, b=2) == 3 — the parameters are named a, b")
            check(add("a", "b") == "ab" and add("b", "a") == "ba",
                  "argument order is preserved (add is not commutative-by-accident)")
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

    `==` alone would call `add(True, True) == 2` a pass even if it returned `True`, and
    `add(1, 1) == 2` a pass for `2.0`. The original returns an int for both, so the type
    is part of the behavior being preserved.
    """
    return type(got) is type(want) and got == want


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
        "note": "%s (ticket #401, module key forge-rw:e42d2d08fe5ef45b)" % UNIT,
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
        prog="forge2-add",
        description="forge2 rewrite of the forge unit artifact_tree_gen:add.py "
                    "(ticket #401). Config-driven: every command below except "
                    "`emit-config` and `selftest` throws if it cannot see its config "
                    "object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="config is read from the file named by $%s, else from the %s section of the "
               "nearest %s found by walking up from this module. Run `emit-config` for a "
               "template." % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="add two Python literals and print the result")
    p_add.add_argument("a", help="left operand, as a Python literal (2, 1.5, '\"text\"')")
    p_add.add_argument("b", help="right operand, as a Python literal")

    sub.add_parser("selftest", help="prove the exemplars, the edges and the config gate")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and its source")

    p_pkg = sub.add_parser("emit-package",
                           help="write an installable package (pyproject.toml + package)")
    p_pkg.add_argument("--target", help="directory to write into; defaults to the config's "
                                        "package.target")
    p_pkg.add_argument("--with-registry", action="store_true",
                       help="also write a %s into the target, so the installed package can "
                            "see its config" % REGISTRY_NAME)
    return parser


def main(argv=None):
    """Entry point for the `console_script` the config names. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at "
                  "it.\n# Until it is installed, `add` throws — it will not guess a default."
                  % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV), file=sys.stderr)
            return 0

        if args.command == "selftest":
            return 0 if selftest() == 0 else 1

        if args.command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(),
                              "base": active_base(), "config": active_config()}, indent=2))
            return 0

        if args.command == "emit-package":
            result = emit_package(args.target)
            if args.with_registry:
                result["written"].append(emit_registry(result["target"]))
            package = active_config()["package"]
            print(json.dumps(result, indent=2))
            print("\n# Now: pip install -e %s   ->   the `%s` command"
                  % (result["target"], package["console_script"]), file=sys.stderr)
            return 0

        if args.command == "add":
            try:
                a = ast.literal_eval(args.a)
                b = ast.literal_eval(args.b)
            except (ValueError, SyntaxError) as exc:
                print("add: operands must be Python literals (2, 1.5, '\"text\"', [1]): %s"
                      % exc, file=sys.stderr)
                return 2
            try:
                result = add(a, b)
            except TypeError as exc:
                # The operator handed `add` two operands `+` rejects; the original raised
                # this too. Scoped to this one call on purpose — a TypeError raised
                # anywhere else is a defect in this tool, and must fall through to the
                # bug-report handler below rather than be reported as bad operands.
                print("add: %s" % exc, file=sys.stderr)
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
