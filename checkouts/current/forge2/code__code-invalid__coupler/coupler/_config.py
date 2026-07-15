"""forge2 / code__code-invalid__coupler / coupler / _config — config resolution for the
`coupler` unit (ticket #397, module key forge-rw:d80efda05c1fe99b).

This module holds the #200 requirement-4 machinery — "NO hardcoded paths or params. A
JSON/registry config object drives it ... and per note-for-claude a tool that cannot see its
config THROWS rather than guessing a default" — kept apart from `coupler/__init__.py` so
that the rewritten unit itself reads as the unit and nothing else.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a
    single `.json` file at the root of a package holding the configuration for every tool in
    that package. `note-for-claude` states the contract in its own words — ".json will have
    all the configuration - for all tools in this set of packaging. (a configuration
    registry) -if a tool cannot see the registry it will throw an exeption." This package
    ships its own `registry.json` at its root, one directory above this file.
config object
    The chunk of that registry belonging to this unit — the section at
    `forge2 -> code__code-invalid__coupler -> coupler`. It is what drives the unit.
    `coupler-version emit-config` prints a template of it.

RESOLUTION ORDER
----------------
The config object is resolved from the first source that answers:

  1. the file named by the `COUPLER_CONFIG` environment variable, which holds the unit
     config object itself — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code-invalid__coupler -> coupler` section of the
     nearest `registry.json` found by walking UP from THIS FILE's directory.

The walk-up starts at this file, never at the working directory, so which directory you run
from does not change what config is found.

If neither answers, `load_config` raises `ConfigError`. It never guesses a default.

WHY `COUPLER_CONFIG` AND NOT A SHARED FORGE2-WIDE VARIABLE
---------------------------------------------------------
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
import json
import os

__all__ = [
    "ConfigError",
    "CONFIG_ENV",
    "REGISTRY_NAME",
    "UNIT",
    "UNIT_PATH",
    "active_base",
    "active_config",
    "active_source",
    "config_template",
    "configure",
    "find_registry",
    "load_config",
    "require_str",
    "reset_config",
    "using_config",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "COUPLER_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS
#: in the config document, not a configurable setting — a config-driven tool has to know
#: which section is its own.
UNIT_PATH = ("forge2", "code__code-invalid__coupler", "coupler")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code-invalid__coupler/coupler"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and ticket #397's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.

    It is deliberately NOT a subclass of anything the unit's guarded version lookup catches.
    `coupler.resolve_version` swallows `Exception` the way the original module did, so
    config resolution is done BEFORE that guard is entered and a `ConfigError` can never be
    mistaken for "the version lookup failed, use the fallback".
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do the unit throws. The two keys are exactly the two
    values the ORIGINAL module hardcoded — the distribution name it looked up, and the string
    it fell back to — which is what makes this unit control-config'd rather than hardwired.
    """
    return {
        "distribution": "coupler",
        "fallback": "0.0.dev0",
    }


# ─────────────────────────────── reading the config ───────────────────────────────

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
        return (config,
                os.path.dirname(os.path.abspath(env_path)),
                "%s=%s" % (CONFIG_ENV, env_path))

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s: %s is unset and no %s was found by walking up from %s. "
            "Run `coupler-version emit-config` for a template of the config object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))))
        )

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r "
                "section. Run `coupler-version emit-config` and add the printed object at %s."
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


def require_str(config, key, allow_empty):
    """Return `config[key]`, proving it is present and a string; else raise ConfigError.

    Type-checking here rather than letting a bad value flow onward is deliberate. The unit's
    version lookup swallows `Exception` (the original module did, and that is preserved), so
    a non-string distribution name handed to `importlib.metadata.version` would raise inside
    that guard and be silently reported as "not installed" — turning an operator's config
    mistake into a plausible-looking wrong answer. A malformed config object is a config
    error, and it is raised as one, before the guard is ever entered.

    Args:
        config: the config object to read.
        key: the key to require.
        allow_empty: whether the empty string is a legitimate value for this key.

    Raises:
        ConfigError: if the key is absent, is not a string, or is empty when
            `allow_empty` is False.
    """
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the required key %r. Run "
            "`coupler-version emit-config` for a template." % (UNIT, key)
        )
    value = config[key]
    if not isinstance(value, str):
        raise ConfigError(
            "config key %r for %s must be a string, not %s"
            % (key, UNIT, type(value).__name__)
        )
    if not value and not allow_empty:
        raise ConfigError(
            "config key %r for %s must not be empty" % (key, UNIT)
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

    Injecting a config does NOT recompute `coupler.__version__`: the original module set its
    version once, at import, and that is preserved. Use `coupler.version_from_config()` to
    read the version a given config object yields.
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
