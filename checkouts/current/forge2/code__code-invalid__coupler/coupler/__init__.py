"""forge2 / code__code-invalid__coupler / coupler — a behavior-preserving rewrite of the
forge unit `code__code-invalid__coupler:coupler/__init__.py` (module key
forge-rw:d80efda05c1fe99b), filed under ticket #397 against the FORGE-wide refactor
standard #200.

WHAT THIS IS
------------
The original forge unit was 132 bytes. It tried to import `importlib.metadata.version`, tried
to look up the installed version of the distribution named `"coupler"`, and — if ANYTHING at
all went wrong — set `__version__` to the string `"0.0.dev0"` instead. This file is an
entirely new implementation of that unit. It keeps the original's observable behavior and its
surface, and it adds the things #200 requires that the original lacked: it is part of a proper
installable package, it is driven by a configuration object, and it refuses to run when it
cannot see that configuration.

THE SURFACE (unchanged, so existing callers keep working)
---------------------------------------------------------
Ticket #397 records that this module "defines no top-level function or method. Its behavior is
whatever its module-level code does". Its surface is therefore the module-level NAMES it
binds, and there are exactly two:

`coupler.__version__`
    A string. The installed version of the configured distribution, or the configured
    fallback string if that version cannot be determined for any reason whatsoever.

`coupler.version`
    `importlib.metadata.version` itself, re-exported as a side effect of the original's
    `from importlib.metadata import version` running at module level. This name is part of
    the surface and is preserved exactly, INCLUDING the condition under which it exists:

      - the import succeeded  ->  `coupler.version` exists (even when the lookup it was
        imported for went on to fail, because the `from ... import` statement had already
        bound the name by then);
      - the import failed     ->  `coupler.version` does NOT exist, and `coupler.version`
        raises `AttributeError` / `from coupler import version` raises `ImportError`.

    Both cases are reproduced here. See `resolve_version` below.

Two consequences of the original's shape are also preserved deliberately:

  - `except Exception` does not catch `BaseException`. A `KeyboardInterrupt` raised out of
    the version lookup propagated in the original and propagates here; it is not turned into
    the fallback.
  - `__version__` starts with an underscore, so `from coupler import *` never exported it.
    This module's `__all__` does not list it either, for the same reason. `__all__` lists the
    new configuration API and — when it is bound — `version`.

WHAT CHANGED, AND WHY
---------------------
The original hardcoded its two parameters: the distribution name `"coupler"` and the fallback
string `"0.0.dev0"`. #200 requirement 4 forbids exactly that ("NO hardcoded paths or params.
A JSON/registry config object drives it"). Here BOTH are read from this unit's config object
and neither has a default anywhere in this file. This package ships a `registry.json` at its
root carrying the original's two values, so an ordinary `import coupler` from a source
checkout or an editable install behaves exactly as the original did.

CONFIGURATION (#200 requirement 4)
----------------------------------
The config object is resolved by `coupler._config`, from the file named by `$COUPLER_CONFIG`
if it is set, else from the `forge2 -> code__code-invalid__coupler -> coupler` section of the
nearest `registry.json` found by walking UP from the package directory. See `_config.py` for
the full contract. Its two keys are:

    {"distribution": "coupler", "fallback": "0.0.dev0"}

`distribution` is the non-empty string handed to `importlib.metadata.version`; `fallback` is
the string `__version__` takes when the lookup does not produce a version (it may be empty).
Neither is defaulted: a missing, non-string, or empty-where-forbidden value raises
`ConfigError` naming the key. Run `coupler-version emit-config` for a template.

IMPORTING THIS MODULE THROWS WITHOUT A CONFIG — ON PURPOSE
----------------------------------------------------------
This is ticket #397's acceptance item (d) and `note-for-claude`'s rule ("if a tool cannot see
the registry it will throw an exeption"), and it is the ONE place this rewrite intentionally
does not mirror the original, which could not have a missing config because it had no config
at all. `import coupler` raises `ConfigError` when no config object can be resolved. It does
not guess `"coupler"`, it does not guess `"0.0.dev0"`, and it does not quietly leave
`__version__` unset.

The gate is checked BEFORE the guarded lookup is entered, never inside it, so the
`except Exception` that implements the fallback can never swallow a `ConfigError` and report
a config mistake as `"0.0.dev0"`.

The version is resolved once, at import, and `__version__` is a plain string attribute in the
module namespace from then on — as it was in the original. It is not recomputed lazily and not
recomputed when a config is injected later; `version_from_config()` is the way to ask what
some other config object would yield.

SIDE EFFECTS
------------
Importing this module reads its config (one JSON file) and reads installed-distribution
metadata. This module itself writes nothing and creates no files. The one thing that appears
on disk when you import it is CPython's own `coupler/__pycache__/*.pyc` bytecode cache, which
the interpreter writes for any module it imports and which `.gitignore` excludes — named here
rather than claimed away, because "creates no files" would otherwise be false.

RUNNING IT
----------
    python3 -c "import coupler; print(coupler.__version__)"
    coupler-version show          # the resolved version, once installed
    coupler-version selftest      # prove this rewrite against the original, which it embeds

`coupler-version` is the console script this package installs; before installation the same
tooling is `python3 coupler_tool.py ...` from the package root. See `coupler_tool.py`, which
holds the CLI and the selftest and which lives OUTSIDE this package on purpose — importing
any module inside `coupler/` imports this file first, config gate and all, so a CLI in here
could not report a config error as one clean line, nor could a selftest in here run without
the very config it needs to test the absence of.
"""

from ._config import (
    CONFIG_ENV,
    REGISTRY_NAME,
    UNIT,
    UNIT_PATH,
    ConfigError,
    active_base,
    active_config,
    active_source,
    config_template,
    configure,
    find_registry,
    load_config,
    require_str,
    reset_config,
    using_config,
)

__all__ = [
    "CONFIG_ENV",
    "REGISTRY_NAME",
    "UNIT",
    "UNIT_PATH",
    "ConfigError",
    "active_base",
    "active_config",
    "active_source",
    "config_template",
    "configure",
    "find_registry",
    "load_config",
    "require_str",
    "reset_config",
    "resolve_version",
    "using_config",
    "version_from_config",
]


def resolve_version(distribution, fallback):
    """Determine the version string for `distribution`, falling back to `fallback`.

    This is the rewritten body of the forge unit, lifted out of module scope into a named
    function so that both of its outputs are explicit and testable. It returns a
    `(version_string, version_callable)` pair:

      - `version_string` is what `__version__` becomes;
      - `version_callable` is `importlib.metadata.version` if the import succeeded, else
        `None`. The caller binds the module-level name `version` from it, which is how the
        original's leaked `from importlib.metadata import version` is reproduced without
        copying the original's structure.

    The three outcomes, matching the original one for one:

      1. the import works and the lookup works  -> (the looked-up version, the callable)
      2. the import works, the lookup raises    -> (`fallback`, the callable)
      3. the import raises                      -> (`fallback`, None)

    Outcome 2 keeping the callable is not an accident of this implementation; it is the
    original's behavior. Its `from importlib.metadata import version` had already bound
    `version` in the module namespace before `version("coupler")` was called, so a failing
    lookup left the name behind. A rewrite that dropped it there would break
    `from coupler import version` for the overwhelmingly common case of a distribution that
    simply is not installed.

    `Exception` is caught, `BaseException` is not — so a `KeyboardInterrupt` or `SystemExit`
    out of the lookup propagates rather than being reported as `fallback`. That, too, is the
    original's behavior, and it is why these are two narrow guards around single statements
    rather than one broad one.

    Neither argument is defaulted. `distribution` and `fallback` come from the config object;
    see `version_from_config`.

    Args:
        distribution: the distribution name to look up, e.g. `"coupler"`.
        fallback: the string to use when no version can be determined.

    Returns:
        A `(version_string, version_callable_or_None)` tuple.
    """
    try:
        from importlib.metadata import version as _version
    except Exception:
        # importlib.metadata is unavailable (it is stdlib from Python 3.8, but this unit ran
        # anywhere its distribution did). Nothing to look up, and nothing to re-export.
        return fallback, None

    try:
        return _version(distribution), _version
    except Exception:
        # The overwhelmingly common case: PackageNotFoundError, because the distribution is
        # not installed — running from a source checkout, say. Any other Exception the
        # metadata backend raises lands here too, exactly as it did in the original.
        return fallback, _version


def version_from_config(config=None):
    """Resolve the version from a config object, or from the config in force.

    Reads and validates the `distribution` and `fallback` keys, then calls `resolve_version`.
    Validation happens here, OUTSIDE `resolve_version`'s guards, so a bad config raises
    `ConfigError` instead of being swallowed and reported as the fallback.

    Args:
        config: a config object to read; omit it to use the config in force (the one injected
            via `configure()`, else the one resolved from disk).

    Returns:
        A `(version_string, version_callable_or_None)` tuple, as `resolve_version` returns.

    Raises:
        ConfigError: if there is no config object to be had, or the one in hand is missing
            `distribution` or `fallback`, or either is not a string, or `distribution` is
            empty.
    """
    cfg = active_config() if config is None else config
    if not isinstance(cfg, dict):
        raise ConfigError("a config object must be a dict, not %s" % type(cfg).__name__)
    distribution = require_str(cfg, "distribution", allow_empty=False)
    fallback = require_str(cfg, "fallback", allow_empty=True)
    return resolve_version(distribution, fallback)


# ─────────────────────────── the module-level surface ───────────────────────────
# Everything below reproduces what the original's module-level code left in this namespace.
# `version_from_config()` raises ConfigError here, at import, if this unit cannot see its
# config: acceptance item (d). That call is outside every `except Exception` in this file, so
# the gate cannot be mistaken for a failed lookup.

__version__, _version_callable = version_from_config()

if _version_callable is not None:
    #: `importlib.metadata.version`, re-exported exactly as the original's module-level
    #: `from importlib.metadata import version` did. Absent when that import fails.
    version = _version_callable
    __all__.append("version")

del _version_callable
