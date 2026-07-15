"""forge2 / code__code__jazz__kokoro__dz_debug / dz_debug / _config — config resolution for
the `logger` unit (ticket #349, module key forge-rw:2392bc58a6ac8d39).

This module holds the #200 requirement-4 machinery — "NO hardcoded paths or params. A
JSON/registry config object drives it ... and per note-for-claude a tool that cannot see its
config THROWS rather than guessing a default" — kept apart from `dz_debug/logger.py` so that
the rewritten unit itself reads as the unit and nothing else.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a
    single `.json` file at the root of a package holding the configuration for every tool in
    that package. `note-for-claude` states the contract in its own words — ".json will have
    all the configuration - for all tools in this set of packaging. (a configuration
    registry) -if a tool cannot see the registry it will throw an exeption." This package
    ships its own `registry.json` at its root, two directories above this file.
config object
    The chunk of that registry belonging to this unit — the section at
    `forge2 -> code__code__jazz__kokoro__dz_debug -> logger`. It is what drives the unit.
    `forge2-dz-debug-tool emit-config` prints a template of it.

RESOLUTION ORDER
----------------
The config object is resolved from the first source that answers:

  1. the file named by the `DZ_DEBUG_CONFIG` environment variable, which holds the unit
     config object itself — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code__jazz__kokoro__dz_debug -> logger` section of the
     nearest `registry.json` found by walking UP from THIS FILE's directory;
  3. otherwise, the `registry.json` this distribution ships as package data inside its
     top-level `code__code__jazz__kokoro__dz_debug` package.

The walk-up starts at this file, never at the working directory, so which directory you run
from does not change what config is found.

WHY STEP 3 EXISTS
-----------------
It is what makes a NON-editable `pip install .` work, and it was added because testing proved
the package broken without it — not on a hunch. In a source checkout or an editable install,
`dz_debug/` sits INSIDE the package root next to `registry.json`, so step 2 finds it one
directory up. A non-editable install has no such root: setuptools installs `dz_debug/` and
`code__code__jazz__kokoro__dz_debug/` as two SEPARATE top-level directories in site-packages,
and the registry ships as package data inside the second. Walking up from `dz_debug/_config.py`
then reaches site-packages and beyond without ever passing the registry, and the unit threw
`ConfigError` on a perfectly good install. Step 3 asks the installed sibling package where it
is, which is the only thing that knows.

Step 3 never SHADOWS a nearer registry: it runs only after the walk-up has failed outright.

If none of the three answers, `load_config` raises `ConfigError`. It never guesses a default.

WHY `DZ_DEBUG_CONFIG` AND NOT A SHARED FORGE2-WIDE VARIABLE
-----------------------------------------------------------
The variable names a file holding ONE unit's config object. A variable shared across forge2
units could only ever point at one unit's object at a time, so pointing it at another unit's
config would break this one. The name is therefore specific to this package.

SIDE EFFECTS
------------
No code in this module writes to disk; it opens files for reading only. (CPython still writes
its own `__pycache__/*.pyc` when it imports this file, as it does for any module; that is the
interpreter's doing and `.gitignore` excludes it.)
"""

import contextlib
import importlib.util
import json
import os

__all__ = [
    "ConfigError",
    "CONFIG_ENV",
    "REGISTRY_NAME",
    "SHIPPING_PKG",
    "UNIT",
    "UNIT_PATH",
    "active_base",
    "active_config",
    "active_source",
    "config_template",
    "configure",
    "find_registry",
    "load_config",
    "require_bool",
    "require_int",
    "require_str",
    "reset_config",
    "using_config",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "DZ_DEBUG_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: This distribution's top-level package, which ships `registry.json` as package data (see
#: pyproject.toml's `[tool.setuptools.package-data]`). Consulted only when the walk-up finds
#: nothing, which is the non-editable-install case — see WHY STEP 3 EXISTS above.
SHIPPING_PKG = "code__code__jazz__kokoro__dz_debug"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS
#: in the config document, not a configurable setting — a config-driven tool has to know
#: which section is its own.
UNIT_PATH = ("forge2", "code__code__jazz__kokoro__dz_debug", "logger")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code__jazz__kokoro__dz_debug/dz_debug/logger"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and ticket #349's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.

    It is raised only while `dz_debug.logger` is being imported — that is, strictly BEFORE any
    decorated call can run. It can therefore never be confused with the exception a decorated
    call records: `debug_decorator`'s `except Exception` swallows nothing at import time,
    because at import time there is no decorated call in flight.
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do the unit throws. Every key below is exactly one
    value the ORIGINAL module hardcoded — the trace filename it wrote, the two `json.dumps`
    parameters it passed, the counter it started at, and the fact that it registered its save
    with `atexit`. Making them data rather than source is #200 requirement 4.
    """
    return {
        "trace_file": "trace.json",
        "indent": 4,
        "sort_keys": True,
        "save_at_exit": True,
        "initial_counter": 0,
    }


# ─────────────────────────────── reading the config ───────────────────────────────

def shipped_registry():
    """Return the path of the `registry.json` this distribution ships as package data, or None.

    Asks the installed `code__code__jazz__kokoro__dz_debug` package where it lives. This is the
    only way to find the registry from a NON-editable install, where it is not on any path
    above this file — see WHY STEP 3 EXISTS in the module docstring.

    Uses `find_spec` rather than importing: locating a file must not run a sibling package's
    code. Returns None rather than raising if the package is absent (a `dz_debug/` vendored on
    its own, say), so the caller can report the whole picture at once.
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
    return ("the %s package is at %s but has no %s in it"
            % (SHIPPING_PKG, list(spec.submodule_search_locations)[0], REGISTRY_NAME))


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

    Returns a `(config, base, source)` triple: the config object, the directory that the
    registry was found in, and a human-readable description of where the config came from.
    `start` overrides the directory the registry walk-up begins at.

    `base` is NOT used to rebase `trace_file`; see `dz_debug/logger.py`, which hands that
    value to `open()` verbatim exactly as the original handed it its own literal. `base` is
    package-wide infrastructure only — it is what the CLI resolves `bug_reports` against.

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
        return (config,
                os.path.dirname(os.path.abspath(env_path)),
                "%s=%s" % (CONFIG_ENV, env_path))

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s. All three sources were tried and none answered: "
            "(1) $%s is unset; (2) no %s was found by walking up from %s; (3) %s. Run "
            "`forge2-dz-debug-tool emit-config` for a template of the config object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))),
               _shipping_pkg_status())
        )

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r "
                "section. Run `forge2-dz-debug-tool emit-config` and add the printed object "
                "at %s."
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
    # section may state its own to override it. This is inheritance inside ONE config
    # document, not a guessed default — if neither states it, the key stays absent and the
    # CLI files no report.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


def _require(config, key):
    if not isinstance(config, dict):
        raise ConfigError("a config object must be a dict, not %s" % type(config).__name__)
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the required key %r. Run "
            "`forge2-dz-debug-tool emit-config` for a template." % (UNIT, key)
        )
    return config[key]


def require_str(config, key, allow_empty):
    """Return `config[key]`, proving it is present and a string; else raise ConfigError.

    Args:
        config: the config object to read.
        key: the key to require.
        allow_empty: whether the empty string is a legitimate value for this key.

    Raises:
        ConfigError: if the key is absent, is not a string, or is empty when
            `allow_empty` is False.
    """
    value = _require(config, key)
    if not isinstance(value, str):
        raise ConfigError(
            "config key %r for %s must be a string, not %s"
            % (key, UNIT, type(value).__name__)
        )
    if not value and not allow_empty:
        raise ConfigError("config key %r for %s must not be empty" % (key, UNIT))
    return value


def require_bool(config, key):
    """Return `config[key]`, proving it is present and a JSON boolean; else raise ConfigError.

    `bool` is checked exactly, not truthiness. A config saying `"sort_keys": "false"` is an
    operator mistake — the string "false" is truthy, so accepting it would silently do the
    OPPOSITE of what it says.

    Raises:
        ConfigError: if the key is absent or is not a bool.
    """
    value = _require(config, key)
    if not isinstance(value, bool):
        raise ConfigError(
            "config key %r for %s must be a boolean (true or false), not %s"
            % (key, UNIT, type(value).__name__)
        )
    return value


def require_int(config, key):
    """Return `config[key]`, proving it is present and a JSON integer; else raise ConfigError.

    `bool` is rejected even though it is a subclass of `int` in Python: a config saying
    `"indent": true` is an operator mistake, and `json.dumps(indent=True)` would silently
    indent by one space rather than fail.

    Raises:
        ConfigError: if the key is absent, is a bool, or is not an int.
    """
    value = _require(config, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            "config key %r for %s must be an integer, not %s"
            % (key, UNIT, type(value).__name__)
        )
    return value


# ─────────────────────────────── the config in force ───────────────────────────────

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
    """Return the directory the registry was found in.

    This is what the CLI resolves a relative `bug_reports` path against. It is deliberately
    NOT applied to `trace_file` — see `load_config`.
    """
    if _ACTIVE is not None:
        return _ACTIVE[1]
    active_config()
    return _RESOLVED[1]


def configure(config, base=None, source="injected via configure()"):
    """Inject `config` as the config object for this process; return the previous state.

    `base` is the directory a relative `bug_reports` path resolves against, and defaults to
    the current working directory. Pass `None` as `config` to drop the injection and go back
    to resolving from disk.

    Injecting a config does NOT re-configure an ALREADY-IMPORTED `dz_debug.logger`: that
    module reads its config once, at import, exactly as the original fixed its own literals at
    import. To exercise `logger` under a different config, inject before the first import of
    it, or point `$DZ_DEBUG_CONFIG` at a config file and import in a fresh interpreter — which
    is what `forge2-dz-debug-tool selftest` does.
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
