"""forge2 / code__code__jazz__kokoro__dz_debug / dz_debug / _init_config — config resolution
for the `dz_debug/__init__.py` unit (ticket #351, module key forge-rw:23bc4068239387f4).

This module holds the #200 requirement-4 machinery — "NO hardcoded paths or params. A
JSON/registry config object drives it ... and per note-for-claude a tool that cannot see its
config THROWS rather than guessing a default" — kept apart from `dz_debug/__init__.py` so that
the rewritten unit itself reads as the unit and nothing else. That separation is the idiom
ticket #349 established for the sibling `logger` unit in `dz_debug/_config.py`; this module
follows it.

WHY THIS EXISTS ALONGSIDE `_config.py` RATHER THAN REUSING IT
-------------------------------------------------------------
`dz_debug/_config.py` is ticket #349's deliverable for the `logger` unit. Its `UNIT_PATH`,
`UNIT` and `CONFIG_ENV` are module-level constants naming THAT unit, and its `load_config`
reads them directly rather than taking them as arguments, so it cannot resolve a different
unit's section as it stands. Making it parameterized would mean rewriting another ticket's
landed module, which this programme's governance forbids — history is append-only, and a unit
adds its OWN module and nothing central (#410). So the `__init__` unit brings its own
resolver, addressed at its own registry section. The two are deliberately independent: neither
imports the other, and adding this file cannot change how `logger` resolves its config.

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
    `forge2 -> code__code__jazz__kokoro__dz_debug -> __init__`. It is what drives the unit.
    `forge2-dz-debug-init emit-config` prints a template of it.
export
    One entry of the config's `exports` list: a submodule to import and the names to bind
    from it. The ORIGINAL hardcoded two — `from .logger import debug_decorator, save` and
    `from .log import Logger`. See `require_exports`.

RESOLUTION ORDER
----------------
The config object is resolved from the first source that answers:

  1. the file named by the `DZ_DEBUG_INIT_CONFIG` environment variable, which holds the unit
     config object itself — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code__jazz__kokoro__dz_debug -> __init__` section of the
     nearest `registry.json` found by walking UP from THIS FILE's directory;
  3. otherwise, the `registry.json` this distribution ships as package data inside its
     top-level `code__code__jazz__kokoro__dz_debug` package.

The walk-up starts at this file, never at the working directory, so which directory you run
from does not change what config is found.

WHY STEP 3 EXISTS
-----------------
It is what makes a NON-editable `pip install .` work, and it is verified, not assumed: this
package's `pyproject.toml` installs `dz_debug/` and `code__code__jazz__kokoro__dz_debug/` as
two SEPARATE top-level directories in site-packages, and the registry ships as package data
inside the second. Walking up from an installed `dz_debug/_init_config.py` then reaches
site-packages and beyond without ever passing the registry, so without step 3 the unit would
throw `ConfigError` on a perfectly good install. Step 3 asks the installed sibling package
where it is, which is the only thing that knows. In a source checkout or an editable install
`dz_debug/` sits INSIDE the package root next to `registry.json`, so step 2 answers first.

Step 3 never SHADOWS a nearer registry: it runs only after the walk-up has failed outright.

If none of the three answers, `load_config` raises `ConfigError`. It never guesses a default.

WHY `DZ_DEBUG_INIT_CONFIG` AND NOT A SHARED FORGE2-WIDE VARIABLE
----------------------------------------------------------------
The variable names a file holding ONE unit's config object. A variable shared across forge2
units could only ever point at one unit's object at a time, so pointing it at another unit's
config would break this one. The name is therefore specific to this unit — the sibling
`logger` unit reads `DZ_DEBUG_CONFIG`, and the two never collide.

SIDE EFFECTS
------------
No code in this module writes to disk; it opens files for reading only. (CPython still writes
its own `__pycache__/*.pyc` when it imports this file, as it does for any module; that is the
interpreter's doing.)
"""

import contextlib
import importlib.util
import json
import os

__all__ = [
    "ConfigError",
    "CONFIG_ENV",
    "REGISTRY_NAME",
    "REQUIRED_KEYS",
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
    "require_exports",
    "require_str",
    "reset_config",
    "shipped_registry",
    "using_config",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "DZ_DEBUG_INIT_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: This distribution's top-level package, which ships `registry.json` as package data (see
#: pyproject.toml's `[tool.setuptools.package-data]`). Consulted only when the walk-up finds
#: nothing, which is the non-editable-install case — see WHY STEP 3 EXISTS above.
SHIPPING_PKG = "code__code__jazz__kokoro__dz_debug"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS
#: in the config document, not a configurable setting — a config-driven tool has to know
#: which section is its own.
UNIT_PATH = ("forge2", "code__code__jazz__kokoro__dz_debug", "__init__")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code__jazz__kokoro__dz_debug/dz_debug/__init__"

#: The config keys the unit needs. Listed so `emit-config` and the missing-key error can name
#: them; each is a param the ORIGINAL hardcoded.
REQUIRED_KEYS = ("exports", "distribution", "fallback_version")


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and ticket #351's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.

    `dz_debug/__init__.py` resolves every value it needs from the config BEFORE it enters the
    `try:` that guards the version lookup, precisely so that a `ConfigError` can never be
    swallowed by that block's `except Exception`. A missing config makes `import dz_debug`
    fail loudly; it never silently produces a fallback version.
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do `import dz_debug` throws. Every value below is
    exactly one thing the ORIGINAL module hardcoded — the two submodules it imported and the
    names it took from each, the distribution name it asked `importlib.metadata.version` for,
    and the version string it fell back to. Making them data rather than source is #200
    requirement 4.
    """
    return {
        "exports": [
            {"module": ".logger", "names": ["debug_decorator", "save"]},
            {"module": ".log", "names": ["Logger"]},
        ],
        "distribution": "dz_debug",
        "fallback_version": "0.0.dev0",
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

    `base` is package-wide infrastructure only — it is what the CLI resolves `bug_reports`
    against. Nothing in this unit is a filesystem path, so nothing is rebased against it.

    Raises:
        ConfigError: if no config object can be found, naming every source that was tried.
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
            "`forge2-dz-debug-init emit-config` for a template of the config object to install."
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
                "section. Run `forge2-dz-debug-init emit-config` and add the printed object "
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

    config = {k: v for k, v in node.items() if not k.startswith("_comment")}
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit
    # section may state its own to override it. This is inheritance inside ONE config
    # document, not a guessed default — if neither states it, the key stays absent and the
    # CLI files no report.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


# ─────────────────────────────── validating the config ───────────────────────────────

def _require(config, key):
    if not isinstance(config, dict):
        raise ConfigError("a config object must be a dict, not %s" % type(config).__name__)
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the required key %r. The required keys are: "
            "%s. Run `forge2-dz-debug-init emit-config` for a template."
            % (UNIT, key, ", ".join(REQUIRED_KEYS))
        )
    return config[key]


def require_str(config, key, allow_empty=False):
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


def require_exports(config):
    """Return the config's `exports` as a tuple of `(module, names)` pairs.

    `exports` is a JSON list of objects, each with a `module` string and a `names` list of
    strings. It drives BOTH the imports the unit performs and the `__all__` it publishes, in
    the order given — the original stated the same fact twice (it imported three names and
    then listed those same three in `__all__`), and deriving the second from the first is what
    stops the two drifting apart in config.

    A `module` may be relative (`".logger"`, the original's own form) or absolute; it is passed
    to `importlib.import_module` anchored on the package, which is what makes a leading dot
    mean the same thing it meant in the original's `from .logger import ...`.

    Raises:
        ConfigError: if `exports` is absent, is not a non-empty list of well-formed entries,
            or names the same export twice. Every failure names what was wrong and where.
    """
    exports = _require(config, "exports")
    if not isinstance(exports, list) or not exports:
        raise ConfigError(
            "config key 'exports' for %s must be a non-empty list of {\"module\", \"names\"} "
            "objects, not %s. Run `forge2-dz-debug-init emit-config` for a template."
            % (UNIT, type(exports).__name__ if not isinstance(exports, list) else "an empty list")
        )

    resolved = []
    seen = {}
    for index, entry in enumerate(exports):
        where = "exports[%d]" % index
        if not isinstance(entry, dict):
            raise ConfigError(
                "config entry %s for %s must be an object with 'module' and 'names', not %s"
                % (where, UNIT, type(entry).__name__)
            )
        module = entry.get("module")
        if not isinstance(module, str) or not module:
            raise ConfigError(
                "config entry %s for %s must have a non-empty string 'module' (for example "
                "\".logger\"); got %r" % (where, UNIT, module)
            )
        names = entry.get("names")
        if not isinstance(names, list) or not names:
            raise ConfigError(
                "config entry %s ('module': %r) for %s must have a non-empty list of string "
                "'names'; got %r" % (where, module, UNIT, names)
            )
        for name in names:
            if not isinstance(name, str) or not name:
                raise ConfigError(
                    "config entry %s ('module': %r) for %s lists %r as a name; every name "
                    "must be a non-empty string" % (where, module, UNIT, name)
                )
            if name in seen:
                raise ConfigError(
                    "config for %s exports the name %r twice — from %r and from %r. Each "
                    "exported name must be bound exactly once, or which module wins would "
                    "depend on the order of the list."
                    % (UNIT, name, seen[name], module)
                )
            seen[name] = module
        resolved.append((module, tuple(names)))
    return tuple(resolved)


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

    This is what the CLI resolves a relative `bug_reports` path against.
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

    Injecting a config does NOT re-configure an ALREADY-IMPORTED `dz_debug`: that package
    reads its config once, at import, exactly as the original fixed its own literals at
    import. To exercise `dz_debug` under a different config, inject before the first import of
    it, or point `$DZ_DEBUG_INIT_CONFIG` at a config file and import in a fresh interpreter —
    which is what `forge2-dz-debug-init selftest` does.
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
