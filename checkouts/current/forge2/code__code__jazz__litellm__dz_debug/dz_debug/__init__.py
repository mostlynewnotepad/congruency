"""forge2 / code__code__jazz__litellm__dz_debug / dz_debug / __init__ — a behavior-preserving
rewrite of the forge unit `code__code__jazz__litellm__dz_debug:dz_debug/__init__.py` (module key
forge-rw:47eb5d42f7f1d8fc), filed under ticket #361 against the FORGE-wide refactor standard #200.
(#361 supersedes #306, which named its source only as a `git cat-file` the sandboxed worker cannot
run; #361 embeds the source and is done here.)

WHAT THIS IS
------------
The original forge unit is 115 bytes — a package `__init__` that does nothing but RE-EXPORT three
names out of two sibling submodules. Its bytes, quoted from the ticket and reproduced verbatim in
`ORIGINAL_SOURCE` below, are:

    from .logger import debug_decorator, save
    from .log import Logger

    __all__ = ["debug_decorator", "save", "Logger"]

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and it adds the three things #200 requires that the original
lacked: it is a proper installable package, it is driven by a configuration object, and it refuses
to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
Ticket #361 states it exactly: "this module defines no top-level function or method. Its behavior
is whatever its module-level code does". So the surface of the ORIGINAL is not a signature list —
it is the NAMESPACE a caller sees after `import dz_debug`:

    dz_debug.debug_decorator     the object `.logger` binds to that name
    dz_debug.save                the object `.logger` binds to that name
    dz_debug.Logger              the object `.log`    binds to that name
    dz_debug.__all__             == ["debug_decorator", "save", "Logger"], in that order
    dz_debug.logger              the `.logger` submodule (a side effect of importing it)
    dz_debug.log                 the `.log`    submodule (a side effect of importing it)

Every one of those is reproduced here, including the two submodule attributes and the ORDER of
`__all__` — which is behavior, because it is the order `from dz_debug import *` binds in.
`selftest` proves the whole namespace against the ORIGINAL's own bytes rather than asserting it;
see THE PROOF below.

This rewrite necessarily defines top-level names the original did not (`bind`, `main`, `selftest`,
the config helpers, the imports at the top of this file). That does not widen the surface a caller
sees: `__all__` is derived from the config and holds EXACTLY the three original names, so
`from dz_debug import *` binds exactly what it always bound. Nothing here is exported implicitly.

THE CENTRAL DESIGN DECISION: THE IMPORTS ARE THE CONFIG
------------------------------------------------------
The original module IS four hardcoded parameters — two module paths (`.logger`, `.log`) and three
names to lift out of them. #200 requirement 4 says "NO hardcoded paths or params. A JSON/registry
config object drives it", so those paths and names are what has to move into the config. The config
object's `exports` list is therefore a direct, ordered transcription of the original's import
statements: one entry per exported name, each naming its source as `"module:attr"`.

  * With the shipped `registry.json` — which carries EXACTLY the original's own values — this
    module binds precisely what the original bound, in precisely the original's order. The values
    did not change, only their location did. That is what makes the rewrite behavior-preserving.
  * With no config object at all, every part of the surface raises `ConfigError` and this module
    binds nothing. It never guesses a default. That is `note-for-claude`'s rule ("if a tool cannot
    see the registry it will throw an exeption" [sic]) and this ticket's acceptance item (d).
  * `selftest` can point `exports` at stand-in modules and prove the binding through the very same
    code path the shipped config uses — no parallel test-only path exists.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a single
    `.json` file at the root of a package holding the configuration for every tool in that
    packaging. This package ships its own `registry.json` at its root, one directory above this
    file.
config object
    The chunk of that registry belonging to this unit — the section at
    `forge2 -> code__code__jazz__litellm__dz_debug -> dz_debug`. It is what drives this module.
    `emit-config` prints a template of it.
export
    One entry of the config's `exports` list: `{"name": ..., "source": "module:attr"}`. It stands
    for one name in one of the original's `from ... import ...` statements. `source` is a module
    (relative, like `.logger`, or absolute) and the attribute to lift out of it, separated by a
    colon — always spelled out in full, so nothing is ever inferred.
bind
    To perform the original's import-time work: import each export's source module in config
    order, lift each attribute out, set the three names on this module, and set `__all__`.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The config object is resolved on first use, from the first source that answers:

  1. the file named by the `DZ_DEBUG_CONFIG` environment variable, which holds the unit config
     object ITSELF — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code__jazz__litellm__dz_debug -> dz_debug` section of the
     nearest `registry.json` found by walking UP from THIS FILE's directory.

The walk-up starts at this file, never at the working directory, so which directory you run from
does not change what config is found. If neither source answers, every part of the surface raises
`ConfigError`, naming both sources that were tried. A config object that is found but is missing a
key, or holds one of the wrong JSON type, is also a `ConfigError`, naming the key.

`configure(config)` and `using_config(config)` inject a config object directly, in-process, for
callers that hold their configuration in memory rather than on disk.

The variable is named for THIS unit rather than something forge2-wide on purpose: it names a file
holding ONE unit's config object, so a variable shared across forge2 units could only ever point at
one unit's object at a time, and pointing it at a sibling's would break this one.

WHY THE SHIPPED REGISTRY IS NOT A DEFAULT
-----------------------------------------
This package ships `registry.json` at its root, so source 2 answers and the unit works from a clean
checkout with no setup. That file is the config object this unit RUNS ON; it is not a fallback
baked into the code. Delete it (with `DZ_DEBUG_CONFIG` unset and no other `registry.json` above
this directory) and every part of the surface throws — the gate is in the code, not in the file's
presence. `selftest` proves the gate directly, without deleting anything, by pointing
`DZ_DEBUG_CONFIG` at a file that does not exist.

The registry sits at the package root because `note-for-claude` puts it there (".json will be in
the root of the folder"). One consequence is worth stating rather than leaving to be discovered:
`pip install -e .` (this ticket's acceptance item (c)) leaves this file where it is, so the walk-up
still finds that registry and the unit works. A NON-editable `pip install` copies only the
`dz_debug` package into site-packages and leaves the root registry behind, so the walk-up finds no
config and the unit throws — correctly, and with a message naming both sources. Point
`DZ_DEBUG_CONFIG` at a config object to use this unit from a non-editable install.

WHAT IS A SETTING, AND WHAT IS NOT
----------------------------------
#200 requires no hardcoded paths or params; it does not require inventing knobs the unit never had.
SETTINGS are the things the original BAKED IN: the two source modules, the three attribute names
lifted out of them, the three names they are bound to, and their order. NOT settings, because they
are this module's structure rather than its configuration: the fact that `__all__` mirrors the
imports, the fact that a source module is imported once per config order, and the exception each
failure raises. Changing those would change behavior, which is what this ticket exists to prevent.

DELIBERATE, DOCUMENTED DIVERGENCES (four; everything else is intended to be indistinguishable)
---------------------------------------------------------------------------------------------
Each is forced by the ticket's own requirements, and each is MEASURED by `selftest` against the
original's bytes rather than asserted. Section [10] of the selftest runs the list below as its
specification: every caller operation named here as preserved is run against BOTH modules and
compared, and every difference named here as remaining is shown to be exactly that and no more.

  1. WHEN THE BINDING HAPPENS. The original bound at IMPORT time: `import dz_debug` either bound
     all three names or raised. This rewrite binds on FIRST TOUCH of the surface, so importing this
     module resolves no config and imports no submodule. That is what makes the module importable,
     installable and provable at all — see THE MISSING SIBLINGS below — and it is why `selftest`
     can run in a checkout where `.logger` and `.log` do not exist yet. The binding it then performs
     is the original's, whole and in order: touching ANY one of the three names imports BOTH source
     modules and binds ALL three, exactly as the original's two import statements did, so no caller
     can observe a half-bound module. `bind()` makes it explicit for a caller who wants the
     original's import-time semantics: `import dz_debug; dz_debug.bind()` is the original's
     `import dz_debug`, including its failure modes.

     What this costs, stated exactly. The difference lives in the WINDOW between `import dz_debug`
     and the first touch of the surface, and it is confined to reading the module's `__dict__`
     DIRECTLY: in that window `vars(dz_debug)`, `dz_debug.__dict__` and `dir(dz_debug)` do not list
     `debug_decorator`, `save`, `Logger` or `__all__`, where the original's would. `vars()` reads
     the dict without going through the module at all, so no module can hook it; this is the
     irreducible price of not binding at import, and it is inspection-only — it reports the
     namespace, it cannot change it. From the first touch onwards `vars(dz_debug)` carries the
     ORIGINAL's whole surface, under the original's names and bound to the same objects (the
     machinery of divergence 4 sits alongside it, as it does at every other moment).

     What it does NOT cost, because it would otherwise be a trap rather than a difference: every
     operation a caller performs THROUGH the module behaves as the original's, in the window as
     much as after it. In particular a caller's WRITE in the window is not lost and does not
     poison anything — `dz_debug.save = stub` then touching the surface leaves `save` as the stub,
     because the original's bind happened before that write and the write won, so the bind here
     declines to overwrite what a caller already put there (`_caller_owns`). A `del dz_debug.save`
     in the window succeeds and stays deleted, rather than raising or quietly coming back
     (`_LazyModule.__delattr__`, `_materialized`). Reads, `hasattr`, `from dz_debug import *`,
     `importlib.reload` and dunder probes are likewise indistinguishable. None of that is claimed
     here on inspection of the code: selftest section [10] performs each of these operations on the
     ORIGINAL and on this module and checks the results are equal.
  2. THE MODULE'S TYPE. `type(dz_debug)` is `_LazyModule`, a `types.ModuleType` SUBCLASS this
     module installs on itself, rather than `types.ModuleType` exactly. It is what gives the module
     the `__delattr__` hook that divergence 1 needs to keep `del` behaving as the original's; PEP
     562's module-level `__getattr__` covers reads only. `isinstance(dz_debug, ModuleType)` — the
     way this is actually asked — stays True, and every other module behavior is inherited
     untouched; only the exact-type test `type(dz_debug) is ModuleType` sees it.
  3. THE MODULE DOCSTRING. The original had none, so `dz_debug.__doc__` was `None` and is now this
     text. Nothing in the surface reads `__doc__`; it is recorded here because it is a real, if
     inert, difference between the two modules.
  4. THIS MODULE'S OWN TOP-LEVEL NAMES. See THE CALLABLE SURFACE above: they do not reach
     `__all__`, so `from dz_debug import *` is unchanged. Their one real consequence is that an
     export name that collides with one of them (a config saying `{"name": "bind", ...}`) would
     silently overwrite this module's own machinery, so `bind()` refuses it as a `ConfigError`
     naming the collision. That check is made against `_OWN_NAMES` — a snapshot of this module's
     own names taken once, at import, BEFORE anything can bind — and never against the live
     `globals()`, which by then also holds bound exports and whatever a caller has assigned.
     Testing the live dict would turn an ordinary `dz_debug.save = stub` into a reported collision
     with "this module's own save" and raise a ConfigError against a config that is correct. The
     original, having no other names, could not collide at all.

THE MISSING SIBLINGS (read this before concluding something is broken)
---------------------------------------------------------------------
`dz_debug/logger.py` and `dz_debug/log.py` — the two modules the shipped config's exports name —
are SEPARATE forge units with their own rewrite tickets, and they have not landed in this package
yet. Ticket #361 covers ONE module, this one, "and nothing else", so this unit does not write them.
Until they land:

    import dz_debug                # works: importing binds nothing (divergence 1)
    dz_debug.selftest()            # works: proves the behavior against stand-in modules
    dz_debug.surface()             # works: reports the declared surface without importing it
    dz_debug.debug_decorator       # ModuleNotFoundError: No module named 'dz_debug.logger'

That last line is not a defect in this file, and it is not the config gate either — the config is
present and correct; the module it names is absent. It is EXACTLY what the original raised when its
own `from .logger import ...` could not find `.logger`, reproduced deliberately: `bind()` lets the
import error propagate untouched rather than dressing it up as a `ConfigError`, so the exception
type, the message and any `except ModuleNotFoundError` around a caller's import all still behave as
they did. When `logger.py` and `log.py` land beside this file, the shipped config binds them with
no change here — `selftest` proves that end state today by standing in for them.

THE PROOF (this ticket's acceptance item (a))
---------------------------------------------
#361 captured NO behavioral exemplars ("no function in this module is minable"), and says so: "you
must write the equivalence exemplars by hand from the original's behavior before rewriting, and
they are what settles this ticket." So `selftest` does not compare against hand-copied expectations
— it compares against THE ORIGINAL ITSELF. It writes the ticket's 115 bytes (`ORIGINAL_SOURCE`,
whose length it checks against the ticket's stated SIZE) and a copy of THIS file into two sibling
temp packages, gives both the same stand-in `logger.py`/`log.py`, imports both, and compares their
observable namespaces name by name — including the star-import result, the submodule attributes,
and the exception raised for a missing module and for a missing name. Everything it creates lives
in a temp directory it removes.

RUNNING IT
----------
Every command below is executable as written from this file's own directory or from the package
root above it; from anywhere else, give the full path to `__init__.py` instead of the relative one.
Which directory you run from does not change what config is found.

    python3 dz_debug/__init__.py selftest       # prove the behavior, the edges and the config gate
    python3 dz_debug/__init__.py emit-config    # print a config-object template
    python3 dz_debug/__init__.py show-config    # print the resolved config + where it came from
    python3 dz_debug/__init__.py surface        # print the surface the config declares, and
                                                #   whether each name resolves right now
    python3 dz_debug/__init__.py bind           # do what `import dz_debug` did in the ORIGINAL,
                                                #   and report what bound

`selftest` and `emit-config` need no config object; the other three throw without one, exiting 2
with a single self-explaining line. `bind` is the only command that imports the configured source
modules, so today — with `.logger` and `.log` not yet landed (see THE MISSING SIBLINGS) — it is
the one command that fails, exiting 3 with the ModuleNotFoundError the ORIGINAL raised in exactly
the same situation. None of the five writes a file outside a temp directory it removes.

`selftest` runs the other four as real processes from an unrelated working directory — each with a
config and again without one — and checks their exit codes and that none of them prints a
traceback, so the paragraph above is checked rather than claimed. It does not re-run itself, for
the obvious reason.

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, and the package is committed in full
beside it — `pyproject.toml`, `registry.json`, `.gitignore`. From the PACKAGE ROOT (the directory
above this one, the one holding `pyproject.toml`):

    python3 -m venv .venv && .venv/bin/pip install -e .
    .venv/bin/forge2-dz-debug selftest
    .venv/bin/python -c "import dz_debug; print(dz_debug.surface())"

The venv is not decoration — a bare `pip install -e .` on a system Python managed by a package
manager is refused with "externally-managed-environment" (PEP 668), which is that Python's rule and
nothing to do with this package.

WHAT IS PROVEN ABOUT THAT, AND WHAT IS NOT. `selftest` does NOT run pip: it is deliberately
hermetic, so it needs no network and no writable environment and can be run anywhere, by anyone, to
check this file's claims. Section [8] proves everything the install depends on and stops exactly
where honesty requires — it reads `pyproject.toml` back and checks that it declares a build
backend, the forge2 distribution name, and the import package `dz_debug`; that the declared package
is on disk where setuptools will look for it; that the `forge2-dz-debug` console script resolves to
a callable in this module; and it runs `import dz_debug` in a SUBPROCESS from an unrelated working
directory with only the package root on the path, which is the end state an editable install
produces. What it does not do — invoke pip and let setuptools build the editable wheel — is stated
in its own output rather than glossed over, and the three commands above are how to do it.

`pyproject.toml` declares the import package as `dz_debug`, so an installed copy is imported by the
name the forge unit was always addressed by — `from dz_debug import debug_decorator, save, Logger`
keeps working, which is acceptance item (b). It also declares the `forge2-dz-debug` console script
pointing at `main()` below.

SIDE EFFECTS
------------
Importing this module resolves NO config, reads NO file and imports NO submodule (divergence 1).
Touching the surface imports the configured source modules — which is the original's behavior, and
whatever those modules do on import is theirs, not this file's.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception is
thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path if it hits an
UNEXPECTED exception — that is, a defect in this tool. A `ConfigError` is designed behavior, not a
bug: it files no report and prints no traceback, and exits 2 with a single self-explaining line. A
`ModuleNotFoundError` from an export's source module is likewise designed behavior — the original
raised it too — so it is reported as one line and exits 3, and files no report.

(CPython writes its own `__pycache__/*.pyc` when it imports this file, as it does for any module;
that is the interpreter's doing and `.gitignore` excludes it.)
"""

import contextlib
import importlib
import json
import os
import sys
import traceback
import types
from datetime import datetime

#: The ORIGINAL unit's bytes, quoted verbatim from ticket #361's embedded source block. This is the
#: behavior-preserving basis and `selftest`'s ORACLE: it is written to disk and imported, so the
#: rewrite is compared against the original running, not against a description of it. Its length is
#: checked against the ticket's stated SIZE of 115 bytes, so a typo here cannot silently weaken the
#: proof.
ORIGINAL_SOURCE = (
    'from .logger import debug_decorator, save\n'
    'from .log import Logger\n'
    '\n'
    '__all__ = ["debug_decorator", "save", "Logger"]\n'
)

#: The ticket's stated SIZE for the original module, in bytes.
ORIGINAL_SIZE = 115

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "DZ_DEBUG_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in the
#: config document, not a configurable setting — a config-driven tool has to know which section is
#: its own.
UNIT_PATH = ("forge2", "code__code__jazz__litellm__dz_debug", "dz_debug")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code__jazz__litellm__dz_debug/dz_debug"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or malformed.

    This is the #200 requirement-4 gate and ticket #361's acceptance item (d): a tool that cannot
    see its config throws rather than guessing a default.

    It is deliberately NOT raised for a source module that cannot be imported, or a name that is
    not in it. Those are the original's own failures — `from .logger import debug_decorator` raises
    `ModuleNotFoundError` and `ImportError` respectively — and reproducing them exactly is what
    acceptance item (a) asks for. A config that NAMES a missing module is not a broken config; it
    is a correct config for a module that is not there yet. See THE MISSING SIBLINGS.
    """


# ─────────────────────────────── reading the config ───────────────────────────────

def find_registry(start=None):
    """Walk UP from `start` (default: this file's directory) and return the nearest registry path,
    or None if the walk reaches the filesystem root without finding one."""
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

    Returns a `(config, base, source)` triple: the config object, the directory that relative paths
    inside it resolve against, and a human-readable description of where it came from. `start`
    overrides the directory the registry walk-up begins at.

    Raises:
        ConfigError: if no config object can be found, naming both sources that were tried.
    """
    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        if not os.path.isfile(env_path):
            raise ConfigError("%s is set to %r, but no such file exists" % (CONFIG_ENV, env_path))
        config = _read_json(env_path, "the config object named by " + CONFIG_ENV)
        if not isinstance(config, dict):
            raise ConfigError("the config object at %s must be a JSON object, not %s"
                              % (env_path, type(config).__name__))
        return (config,
                os.path.dirname(os.path.abspath(env_path)),
                "%s=%s" % (CONFIG_ENV, env_path))

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s: %s is unset and no %s was found by walking up from %s. Run "
            "`emit-config` for a template of the config object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))))

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. Run "
                "`emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH)))
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError("the registry section %s at %s must be a JSON object, not %s"
                          % (".".join(UNIT_PATH), registry_path, type(node).__name__))

    config = dict(node)
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit section
    # may state its own to override it. This is inheritance inside ONE config document, not a
    # guessed default — if neither states it, the key stays absent and the CLI files no report.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do the unit throws. The `exports` list below is a direct
    transcription of the ORIGINAL's two import statements and its `__all__`, which is what makes
    this unit control-config'd rather than hardwired.
    """
    return {
        "exports": [
            {"name": "debug_decorator", "source": ".logger:debug_decorator"},
            {"name": "save", "source": ".logger:save"},
            {"name": "Logger", "source": ".log:Logger"},
        ],
        "bug_reports": "logs/bug_reports.jsonl",
    }


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

    `base` is the directory relative paths in `config` resolve against, and defaults to the current
    working directory. Pass `None` as `config` to drop the injection and go back to resolving from
    disk. Injecting a config UNBINDS the surface, so the next touch of it re-binds from the config
    now in force rather than serving what the previous one bound.
    """
    global _ACTIVE
    previous = _ACTIVE
    if config is None:
        _ACTIVE = None
    else:
        if not isinstance(config, dict):
            raise ConfigError("a config object must be a dict, not %s" % type(config).__name__)
        _ACTIVE = (config, base or os.getcwd(), source)
    _unbind()
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
        _unbind()


def reset_config():
    """Drop the injected config, the cached disk resolution and the bound surface; the next touch
    re-resolves from scratch."""
    global _ACTIVE, _RESOLVED
    _ACTIVE = None
    _RESOLVED = None
    _unbind()


# ─────────────────────────── the exports: the original's imports, as data ───────────────────────

def _exports():
    """Return the config's exports as an ordered list of `(name, module, attr)` triples.

    Every failure below is a malformed CONFIG OBJECT — a `ConfigError` naming the key — rather than
    something that could be mistaken for the module's own behavior. Nothing is inferred: an export
    must state its name and the full `module:attr` it comes from.

    Raises:
        ConfigError: if no config object can be resolved, or `exports` is absent or malformed.
    """
    config = active_config()
    if "exports" not in config:
        raise ConfigError("config object for %s is missing the required key 'exports'. Run "
                          "`emit-config` for a template." % UNIT)
    exports = config["exports"]
    if not isinstance(exports, list):
        raise ConfigError("config key 'exports' for %s must be a JSON array of "
                          '{"name": ..., "source": "module:attr"} objects, not %s'
                          % (UNIT, type(exports).__name__))
    if not exports:
        raise ConfigError("config key 'exports' for %s is empty; it must name at least one export. "
                          "The original re-exported three." % UNIT)

    resolved, seen = [], set()
    for index, entry in enumerate(exports):
        where = "config key 'exports[%d]' for %s" % (index, UNIT)
        if not isinstance(entry, dict):
            raise ConfigError('%s must be a JSON object like {"name": "save", "source": '
                              '".logger:save"}, not %s' % (where, type(entry).__name__))
        for key in ("name", "source"):
            if key not in entry:
                raise ConfigError("%s is missing the required key %r" % (where, key))
            if not isinstance(entry[key], str) or not entry[key]:
                raise ConfigError("%s: key %r must be a non-empty string, not %r"
                                  % (where, key, entry[key]))
        name, spec = entry["name"], entry["source"]
        if not name.isidentifier():
            raise ConfigError("%s: %r is not a usable Python name" % (where, name))
        if name.startswith("__"):
            raise ConfigError(
                "%s: %r cannot be exported. This module binds its surface lazily, through a "
                "__getattr__ that Python consults only for names the module does not already "
                "define — and every dunder it would need is already defined. A dunder export could "
                "never be reached, so it is refused rather than silently ignored."
                % (where, name))
        if name in seen:
            raise ConfigError("%s: %r is exported twice; each name may be exported once"
                              % (where, name))
        seen.add(name)
        module, colon, attr = spec.partition(":")
        if not colon or not module or not attr:
            raise ConfigError('%s: source %r must be spelled "module:attr" (e.g. ".logger:save") — '
                              "the module to import and the name to take out of it" % (where, spec))
        resolved.append((name, module, attr))
    return resolved


# ─────────────────────────────── binding the surface ───────────────────────────────

#: What THIS MODULE bound, name -> value, including the `__all__` it derived. It is the record of
#: what is this module's to overwrite; anything else on the module belongs to a caller (see
#: `_caller_owns`). Two invariants make it trustworthy:
#:
#:   * it is read out of `globals()` rather than assigned fresh, so `importlib.reload` — which
#:     re-executes this body in the module's EXISTING `__dict__`, without clearing it — does not
#:     desync the record from the names actually bound. A plain `_BOUND = {}` here would reset the
#:     record while the names it describes stayed in the module dict, and every one of them would
#:     then look caller-owned;
#:   * `_unbind()` is the only thing that removes from it, and it removes from the module dict in
#:     the same breath.
_BOUND = globals().get("_BOUND", {})


def _materialized():
    """Has the ORIGINAL's import-time bind already been performed, for the config now in force?

    This is what stops the lazy binding from being observable AFTER the fact. The original bound
    once, at import, and from then on a name it had not bound was simply absent: `del dz_debug.save`
    then `dz_debug.save` raised AttributeError. Once the bind here has been materialized this module
    is in that same state, so it must stop binding on demand — a second bind would RESURRECT a name
    the caller deleted and turn that AttributeError into a working attribute.

    `configure()`/`reset_config()` unbind, which clears this: the next touch then binds the config
    that is newly in force. Read through `globals()` so that, like `_BOUND`, it survives a reload.
    """
    return globals().get("_MATERIALIZED", False)


#: Set by `bind()`, cleared by `_unbind()`. See `_materialized`.
_MATERIALIZED = globals().get("_MATERIALIZED", False)


def _unbind():
    """Remove whatever `bind()` bound, so the next touch of the surface re-binds from the config
    now in force. The submodule attributes the import system set (`dz_debug.logger`) are left
    alone: the original never removed them either, and `sys.modules` keeps them consistent.

    Only names in `_BOUND` are removed — never a caller's own — and `__all__` rides along in
    `_BOUND` as an ordinary key, so it is dropped here exactly when the names it lists are.
    """
    for name in list(_BOUND):
        globals().pop(name, None)
    _BOUND.clear()
    globals()["_MATERIALIZED"] = False


def _caller_owns(name):
    """Is `name` on this module because a CALLER put it there, rather than this module?

    This is what makes the lazy binding invisible to a caller that writes into the window between
    `import dz_debug` and the first touch of the surface. In the ORIGINAL the bind happened at
    import, so a caller's `dz_debug.save = stub` always landed AFTER it and won. Here the bind is
    materialized later, so it must not undo that write: a name the caller already put on the module
    is left exactly as the caller left it.

    A name is the caller's when it is on the module but is neither something this module bound
    (`_BOUND`) nor one of this module's own top-level names (`_OWN_NAMES`).
    """
    return name in globals() and name not in _BOUND and name not in _OWN_NAMES


def _package():
    """The package name a relative export source resolves against.

    Raises:
        ConfigError: if this module has no package — which happens when `__init__.py` is executed
            as a plain script rather than imported. The CLI at the bottom of this file re-imports
            the package precisely so this cannot happen there.
    """
    package = __package__ or ""
    if not package:
        raise ConfigError(
            "a relative export source cannot be resolved because this module has no package "
            "(__package__ is %r) — it was executed as a plain file rather than imported as "
            "`dz_debug`. Put the package root (the directory holding pyproject.toml) on sys.path "
            "and `import dz_debug`, or use absolute module names in the config." % package)
    return package


def _import_source(module):
    """Import an export's source module: relative (`.logger`) against this package, else absolute.

    Whatever the import raises propagates UNTOUCHED — `ModuleNotFoundError` for a module that is
    not there, and anything the module itself raises on import. That is the original's behavior:
    `from .logger import debug_decorator` reports the import failure as an import failure. Wrapping
    it in a `ConfigError` would change the exception type a caller catches and would blame the
    config for a module's absence. See THE MISSING SIBLINGS in the module docstring.
    """
    if module.startswith("."):
        return importlib.import_module(module, _package())
    return importlib.import_module(module)


def _from_import(module, attr, spec):
    """Take `attr` off `module`, raising ImportError — not AttributeError — when it is absent.

    `from .logger import save` raises ImportError for a missing name; going through a bare getattr
    would raise AttributeError and change what a caller catches. The ImportError is reconstructed
    here with the phrasing the `from ... import` form uses, plus the config key that asked for it.
    """
    try:
        return getattr(module, attr)
    except AttributeError:
        raise ImportError(
            "cannot import name %r from %r (%s) — %s's config exports it as %r"
            % (attr, module.__name__, getattr(module, "__file__", "unknown location"), UNIT, spec)
        ) from None


def _is_passthrough_dunder(name):
    """Is `name` a dunder this module must answer for WITHOUT resolving any config?

    `__all__` is excluded because it IS part of the surface — in the original there was no `__all__`
    to read unless both imports had succeeded, and that is preserved. Every other dunder is Python's
    own business: a config gate that fired on `dz_debug.__wrapped__` would break every library that
    probes for optional dunders.
    """
    return name.startswith("__") and name.endswith("__") and name != "__all__"


def bind():
    """Do the ORIGINAL's import-time work now, and return the resulting `__all__`.

    `import dz_debug; dz_debug.bind()` is the original's `import dz_debug`: it imports each export's
    source module in config order, lifts each attribute out, binds the names onto this module and
    sets `__all__` — with the original's failure modes intact (see `_import_source` and
    `_from_import`). It is called automatically on the first touch of the surface, so a caller only
    needs it to force the original's import-time timing (divergence 1).

    The ORDER here is behavior, not housekeeping:

      1. the config is validated first, so a malformed config object throws before anything is
         imported or bound;
      2. then EVERY export's source module is imported and EVERY attribute lifted, before a single
         name is bound. The original's two `from ... import ...` statements either all succeeded or
         raised, so a caller could never see a half-bound module; doing all the work up front keeps
         that true, and keeps a missing module or a missing name raising at the same point;
      3. only then are the names written onto the module — skipping any the CALLER owns
         (`_caller_owns`), because in the original the caller's write happened after the
         import-time bind and won.

    Idempotent: re-binding re-reads the config in force and re-imports through `sys.modules`. A
    source module named twice is imported once, because `sys.modules` caches it — exactly as the
    original's single `from .logger import debug_decorator, save` did.

    Raises:
        ConfigError: if no config object can be resolved or `exports` is malformed, or if an export
            name would overwrite one of this module's own (see divergence 4).
        ImportError: whatever the original's import statements would have raised, untouched —
            including `ModuleNotFoundError` for a source module that is not there.
    """
    exports = _exports()

    # Divergence 4, and ONLY divergence 4: an export may not be named after one of this module's own
    # top-level names, because binding it would overwrite this module's machinery. The comparison is
    # against `_OWN_NAMES` — a snapshot of what this module itself defines, taken once at import —
    # and never against the live `globals()`, which also holds whatever previous binds and CALLERS
    # have put there. Testing the live dict would report a caller's own `dz_debug.save = stub`, or a
    # name left behind by an earlier bind, as a collision with this module's machinery: a false
    # ConfigError against a correct config, blaming the config for the caller's ordinary write.
    for name, _module, _attr in exports:
        if name in _OWN_NAMES:
            raise ConfigError(
                "config object for %s exports %r, but this module defines a top-level %r of its "
                "own. Binding it would overwrite this module's own %r and break it. The original "
                "had no other top-level names and so could not collide; rename the export, or "
                "export it from a module that does not shadow this one."
                % (UNIT, name, name, name))

    lifted = []
    for name, module, attr in exports:
        spec = "%s:%s" % (module, attr)
        lifted.append((name, _from_import(_import_source(module), attr, spec)))

    values = {name: value for name, value in lifted if not _caller_owns(name)}
    if not _caller_owns("__all__"):
        values["__all__"] = [name for name, _module, _attr in exports]
    globals().update(values)
    _BOUND.update(values)
    globals()["_MATERIALIZED"] = True
    return list(globals()["__all__"])


class _LazyModule(types.ModuleType):
    """The type `dz_debug` takes on, so a touch of the surface materializes the ORIGINAL's bind.

    The original bound at import; this module cannot (see THE MISSING SIBLINGS in the module
    docstring), so it binds on first touch instead. A plain PEP 562 module `__getattr__` would cover
    reads and nothing else, which leaves `del dz_debug.save` in the unbound window raising
    AttributeError where the original — having bound the name at import — deletes it. Hooking
    `__delattr__` needs a real type, so this module installs one on itself at the bottom of this
    file. `types.ModuleType` is the base, so `isinstance(dz_debug, ModuleType)` is unaffected.
    """

    def __getattr__(self, name):
        """Serve a name the module dict does not hold, binding the surface first.

        Python calls this only when normal lookup fails, so once the surface is bound the three
        names and `__all__` are served straight out of the module dict and this never runs for them.
        """
        if _is_passthrough_dunder(name) or _materialized():
            # Already materialized means the module is in the state the original was in after its
            # import: a name that is not here is simply not here. Binding again would resurrect a
            # name the caller deleted.
            raise AttributeError("module %r has no attribute %r" % (self.__name__, name))
        bind()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError("module %r has no attribute %r"
                                 % (self.__name__, name)) from None

    def __delattr__(self, name):
        """Delete an attribute, binding the surface first if the name is not there yet.

        `import dz_debug; del dz_debug.save` succeeds in the original because `save` was bound at
        import. Materializing the bind before the delete makes it succeed here too, with the same
        end state: the name gone, the rest of the surface bound, and a later read of it raising
        AttributeError rather than quietly binding it again.
        """
        if name not in self.__dict__ and not _materialized() and not _is_passthrough_dunder(name):
            bind()
        super().__delattr__(name)
        # Keep the record honest: what the caller deleted is no longer bound, and no longer this
        # module's to overwrite.
        _BOUND.pop(name, None)


def surface():
    """Report the surface the config declares, without importing anything.

    Returns a list of `{name, source, bound}` dicts in `__all__` order. `bound` says whether that
    name is bound into this module RIGHT NOW, and it is answered by looking in the module dict —
    the one place that cannot disagree with what a caller sees. Answering it from this module's own
    bookkeeping instead would let the two drift apart and make `bound` lie: report False for a name
    that `'save' in vars(dz_debug)` says is there.

    This reads the config and nothing else — it is the way to inspect the declared surface in a
    checkout where the source modules are not present, which is what `dz_debug/__init__.py surface`
    prints.

    Raises:
        ConfigError: if no config object can be resolved or `exports` is malformed.
    """
    return [{"name": name, "source": "%s:%s" % (module, attr), "bound": name in globals()}
            for name, module, attr in _exports()]


# ═══════════════════════════════ the selftest ═══════════════════════════════
#
# #361 captured NO behavioral exemplars, and says what that means: "you must write the equivalence
# exemplars by hand from the original's behavior before rewriting, and they are what settles this
# ticket." Rather than hand-copy the original's behavior into expectations — where a mistake in the
# copy passes silently — the checks below run the ORIGINAL ITSELF, from the ticket's own bytes, and
# compare the two modules' namespaces. Every file it writes is inside a temp directory it removes.

_STANDIN_LOGGER = '''\
"""Stand-in for the `.logger` submodule: a separate forge unit that has not landed here yet.

Written into a TEMP package by `selftest` only. It gives both the ORIGINAL and the rewrite the same
two names to lift, so what is compared is the re-export, not the modules being re-exported.
"""

IMPORTED = []


def debug_decorator(fn):
    return fn


def save(*args, **kwargs):
    return ("save", args, kwargs)


IMPORTED.append(__name__)
'''

_STANDIN_LOG = '''\
"""Stand-in for the `.log` submodule. See the stand-in for `.logger`."""


class Logger:
    def __init__(self, name=None):
        self.name = name
'''


class _Raised:
    """A stand-in for a call that raised, so a check can FAIL instead of aborting.

    A test net that dies on the first unexpected exception hides every check after it and reports a
    traceback where it owes a verdict. `_attempt` returns one of these instead.
    """

    def __init__(self, exception):
        self.type = type(exception)
        self.text = "%s: %s" % (type(exception).__name__, exception)

    def __repr__(self):
        return "<raised %s>" % self.text


def _attempt(thunk):
    """Call `thunk` and return its result, or a `_Raised` if it raised anything."""
    try:
        return thunk()
    except BaseException as exc:  # noqa: BLE001 — a test net must survive anything
        return _Raised(exc)


def _raised(thunk):
    """The NAME of the exception `thunk` raises, or "no exception" — as a comparable value.

    A check that only asked whether both modules raised SOMETHING would pass when one raised
    AttributeError and the other ConfigError, which is the whole question. Naming the type makes
    the two answers comparable across the two packages, where the exception objects cannot be.
    """
    got = _attempt(thunk)
    return got.type.__name__ if isinstance(got, _Raised) else "no exception: %r" % (got,)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _plant(root, package, source, *, registry=None, logger=True, log=True):
    """Write a one-package tree under `root` and return its import name.

    `source` becomes `<root>/<package>/__init__.py`; the stand-in submodules are written beside it
    unless suppressed. `registry`, when given, is written to `<root>/registry.json` — the same
    place this package's real registry sits relative to this file, so the rewrite copy resolves its
    config by exactly the walk-up the shipped one uses.
    """
    _write(os.path.join(root, package, "__init__.py"), source)
    if logger:
        _write(os.path.join(root, package, "logger.py"), _STANDIN_LOGGER)
    if log:
        _write(os.path.join(root, package, "log.py"), _STANDIN_LOG)
    if registry is not None:
        _write(os.path.join(root, REGISTRY_NAME), json.dumps(registry, indent=2) + "\n")
    return package


def _registry_for(exports):
    """A registry document carrying `exports` at this unit's own address in it."""
    config = config_template()
    config["exports"] = exports
    return {"schema": 1, "forge2": {UNIT_PATH[1]: {UNIT_PATH[2]: config}}}


def _import_fresh(root, package):
    """Import `package` out of `root`, with no interference from anything already imported."""
    for name in [n for n in sys.modules if n == package or n.startswith(package + ".")]:
        del sys.modules[name]
    sys.path.insert(0, root)
    try:
        importlib.invalidate_caches()
        return importlib.import_module(package)
    finally:
        sys.path.remove(root)


def _star_import(package):
    """The namespace `from <package> import *` produces, minus Python's own bookkeeping."""
    namespace = {}
    exec("from %s import *" % package, namespace)  # noqa: S102 — the behavior under test
    return {k: v for k, v in namespace.items() if k != "__builtins__"}


def _describe(module):
    """Everything the surface is made of, as a value comparable ACROSS the two temp packages.

    The ORIGINAL and the rewrite are planted as SEPARATE packages, so each imports its own copy of
    the stand-in `logger.py`/`log.py` and their objects cannot be identical across the two — `is`
    would be the wrong question. The right one is where each name comes from WITHIN its own
    package, so every module name here is normalized to `<pkg>` and each exported object is
    described by which submodule attribute it IS. Two packages that describe identically bind the
    same objects out of the same modules under the same names, which is the equivalence #361 asks
    for. What the description cannot carry — that the objects actually WORK — is checked separately.
    """
    package = module.__name__

    def norm(text):
        return text.replace(package, "<pkg>")

    # The SURFACE's names as they are actually bound into the module dict — `__all__`'s names plus
    # the two submodule attributes the imports leave behind. NOT every public name in `vars()`: the
    # rewrite also defines its own top-level machinery (`bind`, `main`, the config helpers), which
    # the original had none of. That is divergence 4, and it is checked on its own terms below —
    # what matters is that none of it reaches `__all__`, not that the two dicts are the same size.
    surface_names = set(module.__all__) | {"logger", "log"}
    out = {"__all__": list(module.__all__),
           "surface-bound-into-the-module": sorted(n for n in vars(module) if n in surface_names)}
    submodules = {name: getattr(module, name) for name in ("logger", "log")}
    for name in ("debug_decorator", "save", "Logger"):
        value = getattr(module, name)
        out[name] = {
            "qualname": norm(getattr(value, "__qualname__", repr(value))),
            "defined-in": norm(getattr(value, "__module__", "?")),
            # The load-bearing line: which submodule attribute this name IS, inside this package.
            "lifted-from": sorted(norm(sub.__name__) + ":" + attr
                                  for sub in submodules.values()
                                  for attr in dir(sub) if getattr(sub, attr, None) is value),
        }
    for name, sub in submodules.items():
        out[name] = {"module": norm(sub.__name__),
                     "file": os.path.basename(sub.__file__),
                     "in-sys-modules": sys.modules.get(sub.__name__) is sub}
    return out


def selftest(stream=None):
    """Prove this rewrite against ticket #361's acceptance items (a)-(d). Returns the failure count.

    It needs no config on disk, no network and no third-party package; it writes only inside a temp
    directory it removes, and it restores every global it touches. `python3 dz_debug/__init__.py
    selftest` runs it.
    """
    import subprocess
    import tempfile

    out = stream or sys.stdout
    checks, failures = [0], []

    def check(ok, label):
        checks[0] += 1
        print("  %s  %s" % ("ok  " if ok else "FAIL", label), file=out)
        if not ok:
            failures.append(label)

    saved_env = {CONFIG_ENV: os.environ.get(CONFIG_ENV)}
    saved_active, saved_resolved = _ACTIVE, _RESOLVED
    # `_BOUND` and `_MATERIALIZED` describe the SAME state and are saved and restored together.
    # Putting the names back while leaving `_MATERIALIZED` false would leave this module bound but
    # believing it was not, and the next read of a name it does not have would try to bind again
    # instead of raising AttributeError — the very desync `_materialized` exists to prevent.
    saved_bound = dict(_BOUND)
    saved_materialized = _materialized()
    here = os.path.dirname(os.path.abspath(__file__))
    package_root = os.path.dirname(here)

    print("== selftest: %s (ticket #361, module key forge-rw:47eb5d42f7f1d8fc)" % UNIT, file=out)
    try:
        os.environ.pop(CONFIG_ENV, None)
        reset_config()

        # ── 1. the oracle is the ticket's own bytes ──────────────────────────────────
        print("[1] the oracle — ticket #361's embedded ORIGINAL SOURCE, verbatim", file=out)
        check(len(ORIGINAL_SOURCE.encode("utf-8")) == ORIGINAL_SIZE,
              "ORIGINAL_SOURCE is %d bytes, the SIZE ticket #361 states (%d)"
              % (len(ORIGINAL_SOURCE.encode("utf-8")), ORIGINAL_SIZE))
        check(compile(ORIGINAL_SOURCE, "<original>", "exec") is not None,
              "ORIGINAL_SOURCE is valid Python")

        with tempfile.TemporaryDirectory(prefix="dz_debug_selftest_") as tmp:
            rewrite_source = open(os.path.abspath(__file__), "r", encoding="utf-8").read()

            # ── 2. equivalence: the ORIGINAL and the rewrite, side by side ───────────
            #     Two sibling temp packages get the SAME stand-in logger.py/log.py. The
            #     original is imported as-is; the rewrite is imported with the SHIPPED
            #     config's exports (".logger:debug_decorator" etc.), resolved by the same
            #     registry walk-up the real package uses. Nothing is injected into either.
            print("[2] equivalence — the rewrite's namespace vs the ORIGINAL's, both running",
                  file=out)
            orig_root = os.path.join(tmp, "oracle")
            rw_root = os.path.join(tmp, "rewrite")
            _plant(orig_root, "_dz_original", ORIGINAL_SOURCE)
            _plant(rw_root, "_dz_rewrite", rewrite_source,
                   registry=_registry_for(config_template()["exports"]))

            original = _import_fresh(orig_root, "_dz_original")
            rewrite = _import_fresh(rw_root, "_dz_rewrite")

            check("debug_decorator" not in vars(rewrite) and "__all__" not in vars(rewrite),
                  "divergence 1: importing the rewrite binds nothing — no config read, no "
                  "submodule imported")
            check("debug_decorator" in vars(original),
                  "...while importing the ORIGINAL binds eagerly, as it always did")

            want, got = _describe(original), _describe(rewrite)  # touching the surface binds it
            check(got["__all__"] == want["__all__"] == ["debug_decorator", "save", "Logger"],
                  "__all__ == %r, in the ORIGINAL's order" % (want["__all__"],))
            for name in ("debug_decorator", "save", "Logger"):
                check(got[name] == want[name],
                      "dz_debug.%s is what the ORIGINAL binds: %s"
                      % (name, json.dumps(want[name]) if got[name] == want[name]
                         else "%s  != the ORIGINAL's %s" % (json.dumps(got[name]),
                                                            json.dumps(want[name]))))
            for name in ("logger", "log"):
                check(got[name] == want[name],
                      "dz_debug.%s is the submodule the ORIGINAL's import left on the package: %s"
                      % (name, json.dumps(want[name])))
            check(got["surface-bound-into-the-module"] == want["surface-bound-into-the-module"],
                  "after the first touch the rewrite has the ORIGINAL's whole surface bound into "
                  "its module dict: %r" % (want["surface-bound-into-the-module"],))
            check(got == want,
                  "...and the two descriptions are EQUAL in every part — nothing above was missed")

            # Divergence 3, measured rather than asserted: the rewrite's extra top-level names.
            extra = sorted(set(n for n in vars(rewrite) if not n.startswith("_"))
                           - set(n for n in vars(original) if not n.startswith("_")))
            check(extra and not (set(extra) & set(rewrite.__all__)),
                  "divergence 4: the rewrite's %d extra top-level names (%s) are its own "
                  "machinery, and NOT ONE of them reaches __all__, so no caller sees them"
                  % (len(extra), ", ".join(extra)))

            star_want, star_got = _star_import("_dz_original"), _star_import("_dz_rewrite")
            check(sorted(star_got) == sorted(star_want) == ["Logger", "debug_decorator", "save"]
                  and all(star_got[n] is getattr(rewrite, n) for n in star_got)
                  and all(star_want[n] is getattr(original, n) for n in star_want),
                  "`from dz_debug import *` binds exactly the names the ORIGINAL's did — %r — and "
                  "each to that package's own attribute" % (sorted(star_want),))
            check("bind" not in star_got and "main" not in star_got and "json" not in star_got,
                  "...and none of the rewrite's own top-level names leak into it (divergence 4)")
            check(callable(rewrite.debug_decorator) and rewrite.debug_decorator(len) is len
                  and rewrite.debug_decorator(len) is original.debug_decorator(len),
                  "the re-exported debug_decorator WORKS, and identically to the ORIGINAL's: it "
                  "returns the function it decorates, unwrapped")
            check(rewrite.save(1, k=2) == original.save(1, k=2) == ("save", (1,), {"k": 2})
                  and isinstance(rewrite.Logger("x"), rewrite.log.Logger)
                  and rewrite.Logger("x").name == original.Logger("x").name == "x",
                  "the re-exported save and Logger work, and identically to the ORIGINAL's")

            # ── 3. the edges: what each module does when a source is missing ─────────
            #     Sampling cannot reach these — the ticket captured no exemplars at all — so
            #     they are written by hand and checked against the ORIGINAL, not asserted.
            print("[3] edges — a missing source module, and a missing name in one", file=out)
            no_logger_o = os.path.join(tmp, "oracle_nologger")
            no_logger_r = os.path.join(tmp, "rewrite_nologger")
            _plant(no_logger_o, "_dz_original_nl", ORIGINAL_SOURCE, logger=False)
            _plant(no_logger_r, "_dz_rewrite_nl", rewrite_source, logger=False,
                   registry=_registry_for(config_template()["exports"]))

            o_fail = _attempt(lambda: _import_fresh(no_logger_o, "_dz_original_nl"))
            check(isinstance(o_fail, _Raised) and o_fail.type is ModuleNotFoundError,
                  "the ORIGINAL cannot even be IMPORTED without .logger: %r" % (o_fail,))
            r_mod = _attempt(lambda: _import_fresh(no_logger_r, "_dz_rewrite_nl"))
            check(not isinstance(r_mod, _Raised),
                  "the rewrite IMPORTS fine without .logger (divergence 1 — this is what makes "
                  "the unit installable and provable before its sibling units land)")
            r_fail = _attempt(lambda: r_mod.debug_decorator)
            check(isinstance(r_fail, _Raised) and r_fail.type is ModuleNotFoundError,
                  "...and raises the ORIGINAL's exception, unwrapped, on the first touch: %r"
                  % (r_fail,))
            check(isinstance(r_fail, _Raised) and isinstance(o_fail, _Raised)
                  and r_fail.text.replace("_dz_rewrite_nl", "P") == o_fail.text.replace(
                      "_dz_original_nl", "P"),
                  "...with the ORIGINAL's message, module name for module name")
            check(isinstance(r_fail, _Raised) and not issubclass(r_fail.type, ConfigError),
                  "a missing source module is NOT reported as a ConfigError — the config is fine, "
                  "the module is absent")

            # `surface` looks WITHOUT touching, and must answer per name: this package has .log but
            # no .logger, so two of the three are unresolvable and the third is fine. One reason
            # reported for every name would be a wrong answer for the name that resolves.
            declared = _attempt(r_mod.surface)
            check(not isinstance(declared, _Raised)
                  and [e["name"] for e in declared] == ["debug_decorator", "save", "Logger"]
                  and [e["bound"] for e in declared] == [False, False, False],
                  "surface() still reports the declared surface here, unbound, without importing "
                  "anything: %s" % json.dumps(declared))
            diagnosis = [(e["name"],) + r_mod._resolves(e["source"]) for e in declared]
            check([(n, ok) for n, ok, _why in diagnosis]
                  == [("debug_decorator", False), ("save", False), ("Logger", True)]
                  and "No module named" in diagnosis[0][2]
                  and diagnosis[2][2] == "",
                  "...and diagnoses each name on its own: %s"
                  % "; ".join("%s -> %s" % (n, why or "resolves") for n, _ok, why in diagnosis))

            partial_o = os.path.join(tmp, "oracle_nosave")
            partial_r = os.path.join(tmp, "rewrite_nosave")
            stripped = _STANDIN_LOGGER.replace("def save(*args, **kwargs):", "def _save(*a, **k):")
            _plant(partial_o, "_dz_original_ns", ORIGINAL_SOURCE, logger=False)
            _plant(partial_r, "_dz_rewrite_ns", rewrite_source, logger=False,
                   registry=_registry_for(config_template()["exports"]))
            _write(os.path.join(partial_o, "_dz_original_ns", "logger.py"), stripped)
            _write(os.path.join(partial_r, "_dz_rewrite_ns", "logger.py"), stripped)
            o_ns = _attempt(lambda: _import_fresh(partial_o, "_dz_original_ns"))
            r_ns = _import_fresh(partial_r, "_dz_rewrite_ns")
            r_ns_fail = _attempt(lambda: r_ns.save)
            check(isinstance(o_ns, _Raised) and o_ns.type is ImportError,
                  "the ORIGINAL raises ImportError when .logger has no `save`: %r" % (o_ns,))
            check(isinstance(r_ns_fail, _Raised) and r_ns_fail.type is ImportError
                  and "cannot import name 'save'" in r_ns_fail.text,
                  "...and so does the rewrite — ImportError, not AttributeError: %r"
                  % (r_ns_fail,))

            # ── 4. the config gate (acceptance item (d)) ────────────────────────────
            print("[4] the config gate — no config object means no surface, and no guessing",
                  file=out)
            missing = os.path.join(tmp, "there-is-no-config-here.json")
            os.environ[CONFIG_ENV] = missing
            gated = _import_fresh(rw_root, "_dz_rewrite")
            for label, thunk in (("dz_debug.__all__", lambda: gated.__all__),
                                 ("dz_debug.debug_decorator", lambda: gated.debug_decorator),
                                 ("bind()", gated.bind),
                                 ("surface()", gated.surface),
                                 ("from dz_debug import *", lambda: _star_import("_dz_rewrite"))):
                got = _attempt(thunk)
                check(isinstance(got, _Raised) and issubclass(got.type, gated.ConfigError),
                      "%s throws ConfigError when it cannot see its config: %r" % (label, got))
            got = _attempt(lambda: gated.__all__)
            check(isinstance(got, _Raised) and missing in got.text and CONFIG_ENV in got.text,
                  "...and the error names the variable and the file it pointed at, so it explains "
                  "itself")
            check(_attempt(lambda: gated.__wrapped__).type is AttributeError,
                  "an unrelated dunder still raises AttributeError, not ConfigError — a gate that "
                  "fired on every dunder probe would break libraries that look for them")
            os.environ.pop(CONFIG_ENV, None)

            # ── 5. a malformed config object is a ConfigError naming the key ────────
            print("[5] a malformed config object names the key, and never guesses", file=out)
            good = config_template()["exports"]
            for label, exports in (
                ("exports absent", None),
                ("exports is not an array", {"name": "save"}),
                ("exports is empty", []),
                ("an entry is not an object", ["save"]),
                ("an entry has no 'source'", [{"name": "save"}]),
                ("an entry has no 'name'", [{"source": ".logger:save"}]),
                ("a source is not module:attr", [{"name": "save", "source": ".logger"}]),
                ("a name is not an identifier", [{"name": "no-hyphens", "source": ".l:s"}]),
                ("a name is a dunder", [{"name": "__spec__", "source": ".l:s"}]),
                ("a name is exported twice", good + [{"name": "save", "source": ".log:save"}]),
                ("a name collides with the module's own", [{"name": "bind", "source": ".l:s"}]),
            ):
                config = config_template()
                if exports is None:
                    del config["exports"]
                else:
                    config["exports"] = exports
                with using_config(config, base=tmp):
                    got = _attempt(bind)
                check(isinstance(got, _Raised) and issubclass(got.type, ConfigError),
                      "%s -> ConfigError: %s" % (label, getattr(got, "text", got)))
            check(_ACTIVE is None, "using_config put the previous config back afterwards")

            # ── 6. the shipped registry carries the ORIGINAL's own values ───────────
            print("[6] the shipped registry — the original's imports, moved to data", file=out)
            reset_config()
            shipped_path = find_registry()
            check(shipped_path == os.path.join(package_root, REGISTRY_NAME),
                  "the walk-up from this file finds the package's own registry at %s"
                  % (shipped_path,))
            shipped, base, source = load_config()
            check(shipped.get("exports") == config_template()["exports"],
                  "its exports ARE the original's two import statements, transcribed: %s"
                  % json.dumps(shipped.get("exports")))
            check(base == package_root and source == shipped_path,
                  "and it resolves with the package root as its base")
            for start in (tmp, os.path.dirname(package_root), "/"):
                found = _attempt(lambda start=start: load_config()[2])
                check(found == shipped_path,
                      "the config found does not depend on the working directory (cwd=%s)" % start)

            # ── 7. the shipped config, end to end, with the sibling units stood in ──
            #     The real registry, resolved off disk, with `.logger`/`.log` present. This is
            #     the state the package reaches the day those two units land.
            print("[7] the shipped config binds the ORIGINAL's surface once .logger/.log exist",
                  file=out)
            landed = os.path.join(tmp, "landed")
            _plant(landed, "_dz_rewrite_landed", rewrite_source,
                   registry=_registry_for(config_template()["exports"]))
            live = _import_fresh(landed, "_dz_rewrite_landed")
            check(live.__all__ == ["debug_decorator", "save", "Logger"],
                  "dz_debug.__all__ == %r, from the registry on disk — nothing injected"
                  % (live.__all__,))
            check(callable(live.debug_decorator) and callable(live.save)
                  and isinstance(live.Logger, type),
                  "all three names bind to the objects .logger/.log define")
            check([e["bound"] for e in live.surface()] == [True, True, True],
                  "surface() reports every declared name as bound: %s" % json.dumps(live.surface()))
            check(live.logger.IMPORTED == [live.logger.__name__],
                  "each source module is imported exactly ONCE, though two exports name .logger — "
                  "as the original's single `from .logger import debug_decorator, save` did")

            # ── 8. installable (acceptance item (c)) ────────────────────────────────
            print("[8] installable — pyproject.toml, and the end state `pip install -e .` gives",
                  file=out)
            try:
                import tomllib          # the stdlib TOML reader, Python 3.11+
            except ImportError:         # this package declares requires-python >= 3.8
                tomllib = None
                print("  note  no tomllib (Python < 3.11): pyproject.toml is not parsed here. The "
                      "import\n        proof below still runs, and does not depend on it.",
                      file=out)
            if tomllib is not None:
                with open(os.path.join(package_root, "pyproject.toml"), "rb") as handle:
                    project = tomllib.load(handle)
                packages = project["tool"]["setuptools"]["packages"]
                check(packages == ["dz_debug"],
                      "pyproject declares the import package as `dz_debug` (%r), so an installed "
                      "copy is imported by the name the forge unit was always addressed by"
                      % (packages,))
                check(os.path.isfile(os.path.join(package_root, "dz_debug", "__init__.py")),
                      "the declared package exists on disk where setuptools will look for it")
                check(project["build-system"]["build-backend"] == "setuptools.build_meta"
                      and project["project"]["name"] == "forge2-code-code-jazz-litellm-dz-debug",
                      "it names a build backend and the forge2 distribution name")
                script = project["project"]["scripts"]["forge2-dz-debug"]
                module_name, _, attr = script.partition(":")
                check(module_name == "dz_debug" and callable(globals().get(attr)),
                      "the console script %r resolves to a callable in this module" % script)

            probe = ("import dz_debug, sys; "
                     "assert dz_debug.__file__ == sys.argv[1], dz_debug.__file__; "
                     "print(dz_debug.surface()[0]['source'])")
            run = subprocess.run([sys.executable, "-c", probe,
                                  os.path.join(package_root, "dz_debug", "__init__.py")],
                                 cwd=tmp, env=dict(os.environ, PYTHONPATH=package_root),
                                 capture_output=True, text=True)
            check(run.returncode == 0 and run.stdout.strip() == ".logger:debug_decorator",
                  "`import dz_debug` works from an unrelated directory with only the package root "
                  "on the path — the end state an editable install produces (%s)"
                  % (run.stdout.strip() or run.stderr.strip().splitlines()[-1:]))
            print("  note  `pip install -e .` is not run from here — it needs a writable\n"
                  "        environment and a network for build isolation, and this selftest is\n"
                  "        deliberately hermetic. What it proves instead is the END STATE that\n"
                  "        install produces, which is the part this package is responsible for.\n"
                  "        To run the install itself:  python3 -m venv .venv && .venv/bin/pip "
                  "install -e .", file=out)

            # ── 9. bind() gives a caller the original's import-time timing ──────────
            print("[9] bind() — the original's import-time semantics, on demand", file=out)
            eager = _import_fresh(landed, "_dz_rewrite_landed")
            check("debug_decorator" not in vars(eager), "freshly imported, the surface is unbound")
            check(eager.bind() == ["debug_decorator", "save", "Logger"]
                  and "debug_decorator" in vars(eager),
                  "bind() binds the whole surface at once and returns __all__")
            check(eager.bind() == ["debug_decorator", "save", "Logger"],
                  "bind() is idempotent — calling it twice binds the same surface")
            first = eager.save
            eager.configure(dict(config_template(),
                                 exports=[{"name": "save", "source": ".log:Logger"}]), base=landed)
            check("save" not in vars(eager) and eager.__all__ == ["save"]
                  and eager.save is eager.log.Logger and eager.save is not first,
                  "configure() unbinds the old surface, so the next touch serves the config now in "
                  "force")
            eager.reset_config()

            # ── 10. the lazy window — divergence 1's cost, measured against the ─────
            #     ORIGINAL rather than described.
            #
            #     Divergence 1 is the whole of this rewrite's behavioral risk, so the
            #     docstring's account of it is the thing most worth disbelieving. Every
            #     operation below is run on the ORIGINAL and on the rewrite and the results
            #     compared, so the account is checked and not taken on trust. The WRITE cases
            #     matter most: a write into the window that the bind later undid, or that
            #     poisoned the bind, would be a silent trap for `monkeypatch.setattr` and
            #     every other ordinary caller — observable long after the window closed.
            print("[10] the window between `import dz_debug` and the first touch, probed "
                  "against the ORIGINAL", file=out)

            def in_window(root, package, operation):
                """Run `operation` on a freshly imported copy, before anything touches it."""
                return _attempt(lambda: operation(_import_fresh(root, package)))

            def both(operation):
                """The ORIGINAL's result and the rewrite's, for the same operation."""
                return (in_window(orig_root, "_dz_original", operation),
                        in_window(landed, "_dz_rewrite_landed", operation))

            def probe(label, operation):
                want, got = both(operation)
                same = not isinstance(want, _Raised) and got == want
                check(same, "%s — the ORIGINAL: %s%s"
                      % (label, json.dumps(want) if same else repr(want),
                         "" if same else "   BUT THE REWRITE: %r" % (got,)))

            def write_then_touch(module):
                stub = "a caller's stub"
                module.save = stub                       # the write, in the window
                other = module.Logger("n").name          # the touch that binds
                return {"the touch works": other,
                        "the write survives it": module.save is stub,
                        "__all__ is the original's": list(module.__all__),
                        "star-import binds the stub": _star_import(module.__name__)["save"] is stub}

            probe("a caller's `dz_debug.save = stub` in the window, then a touch", write_then_touch)

            def delete_then_read(module):
                del module.save                          # the delete, in the window
                return {"gone from the module dict": "save" in vars(module),
                        "the rest still binds": module.Logger("n").name,
                        "reading it now raises": _raised(lambda: module.save),
                        "__all__ still lists it": list(module.__all__)}

            probe("a caller's `del dz_debug.save` in the window, then a read", delete_then_read)

            def caller_all_wins(module):
                module.__all__ = ["save"]
                module.Logger                            # the touch
                return {"the caller's __all__ survives": list(module.__all__)}

            probe("a caller's `dz_debug.__all__ = [...]` in the window survives the bind",
                  caller_all_wins)

            def probes(module):
                return {"hasattr(save)": hasattr(module, "save"),
                        "hasattr(nope)": hasattr(module, "nope"),
                        "hasattr(__wrapped__)": hasattr(module, "__wrapped__"),
                        "isinstance ModuleType": isinstance(module, types.ModuleType),
                        "reading a name that is not there": _raised(lambda: module.nope)}

            probe("hasattr, a dunder probe, isinstance and a missing name", probes)

            # `importlib.reload` re-runs the module's FINDER, so unlike every other probe here
            # the package's root has to still be on sys.path while it happens — `_import_fresh`
            # takes it back off. These two run with the root kept in place.
            def touch_reload_then_use(root, package):
                def operation(module):
                    module.save                          # bind BEFORE the reload
                    sys.path.insert(0, root)
                    try:
                        reloaded = importlib.reload(module)
                    finally:
                        sys.path.remove(root)
                    return {"the surface still works": reloaded.save(1, k=2),
                            "__all__": list(reloaded.__all__),
                            # A reload re-executes the module body, which is where round-1's
                            # `_BOUND = {}` desynced the record from a module dict the reload
                            # does NOT clear — and every already-bound name then looked like a
                            # collision with this module's own machinery.
                            "an explicit bind() after it": _raised(reloaded.bind)
                                                           if hasattr(reloaded, "bind") else "n/a"}
                return in_window(root, package, operation)

            r_reload = touch_reload_then_use(landed, "_dz_rewrite_landed")
            o_reload = touch_reload_then_use(orig_root, "_dz_original")
            check(not isinstance(r_reload, _Raised) and not isinstance(o_reload, _Raised)
                  and r_reload["the surface still works"] == o_reload["the surface still works"]
                  and r_reload["__all__"] == o_reload["__all__"]
                  and r_reload["an explicit bind() after it"].startswith("no exception"),
                  "importlib.reload after a bind leaves the ORIGINAL's surface, and an explicit "
                  "bind() after it succeeds rather than reporting a false collision: %r"
                  % (r_reload,))

            def reload_then_surface(module):
                module.save
                sys.path.insert(0, landed)
                try:
                    reloaded = importlib.reload(module)
                finally:
                    sys.path.remove(landed)
                return {"surface() says bound": [e["bound"] for e in reloaded.surface()],
                        "and the module dict says": [n in vars(reloaded)
                                                     for n in ("debug_decorator", "save", "Logger")]}
            after = in_window(landed, "_dz_rewrite_landed", reload_then_surface)
            check(not isinstance(after, _Raised)
                  and after["surface() says bound"] == after["and the module dict says"]
                  == [True, True, True],
                  "...and surface()'s `bound` still agrees with the module dict after a reload, "
                  "rather than contradicting it: %s" % json.dumps(after))

            # The cost, stated exactly and shown to be exactly that: `vars()` reads the module
            # dict without going through the module, so nothing can hook it. This is the ONE
            # thing divergence 1 costs, and it converges the moment the surface is touched.
            windowed = _import_fresh(landed, "_dz_rewrite_landed")
            in_window_names = sorted(n for n in vars(windowed) if n in ("save", "__all__"))
            windowed.save
            check(in_window_names == []
                  and sorted(n for n in vars(windowed) if n in ("save", "__all__"))
                  == ["__all__", "save"],
                  "divergence 1's whole cost: vars() does not show the surface in the window "
                  "(%r), and shows all of it after the first touch — nothing else differs"
                  % (in_window_names,))

            # ── 11. the command line, as actual processes ───────────────────────────
            #     Run from an unrelated cwd, so each one also proves the claim that the
            #     working directory does not change what config is found.
            print("[11] the command line — every command run as a process, from cwd=%s" % tmp,
                  file=out)
            gate_env = dict(os.environ, DZ_DEBUG_CONFIG=missing)
            for argv, env, want_code, want_text in (
                (["emit-config"], None, 0, '".logger:debug_decorator"'),
                (["show-config"], None, 0, shipped_path),
                (["surface"], None, 0, '"__all__"'),
                (["selftest"], None, None, None),      # not re-run: it is what is running
                # `bind` IS the original's `import dz_debug`, so today — with .logger and .log
                # not yet landed — it must fail the way the original failed, on one line and
                # without a traceback, rather than pretend to succeed.
                (["bind"], None, 3, "No module named 'dz_debug.logger'"),
                (["surface"], gate_env, 2, "config error:"),
                (["bind"], gate_env, 2, "config error:"),
                (["emit-config"], gate_env, 0, '".logger:debug_decorator"'),
            ):
                if want_code is None:
                    continue
                run = subprocess.run([sys.executable, os.path.abspath(__file__)] + argv, cwd=tmp,
                                     env=env or os.environ, capture_output=True, text=True)
                blob = run.stdout + run.stderr
                check(run.returncode == want_code and want_text in blob
                      and "Traceback" not in blob,
                      "`%s%s` exits %d, says %r, and prints no traceback%s"
                      % ("DZ_DEBUG_CONFIG=<missing file> " if env else "",
                         "dz_debug/__init__.py " + " ".join(argv), want_code, want_text,
                         "" if run.returncode == want_code and want_text in blob
                         else "  — got exit %d: %s" % (run.returncode, blob.strip()[-200:])))
            check("emit-config" in subprocess.run(
                      [sys.executable, os.path.abspath(__file__), "--help"], cwd=tmp,
                      capture_output=True, text=True).stdout,
                  "`--help` documents the commands, so the tool explains itself with no outside "
                  "context")
    finally:
        for key, value in saved_env.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value
        for name in [n for n in list(sys.modules) if n.startswith("_dz_original")
                     or n.startswith("_dz_rewrite")]:
            del sys.modules[name]
        _unbind()
        globals()["_ACTIVE"] = saved_active
        globals()["_RESOLVED"] = saved_resolved
        # `__all__` rides along in `_BOUND` as an ordinary key, so restoring the record restores
        # the module dict with it — there is nothing to put back by hand.
        _BOUND.update(saved_bound)
        globals().update(saved_bound)
        globals()["_MATERIALIZED"] = saved_materialized

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED", checks[0], len(failures)),
          file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ... Filename -
    function name - time of occurance - methods to reproduce - possible cause"). Best-effort and
    silent on failure: a tool that cannot file a report must still report its original error. No
    report is filed for a ConfigError or for an ImportError out of a configured source module —
    both are designed behavior rather than a bug. Returns the path written, or None.
    """
    try:
        config, base = active_config(), active_base()
    except ConfigError:
        return None
    relative = config.get("bug_reports")
    if not relative:
        return None
    path = relative if os.path.isabs(relative) else os.path.join(base, relative)
    frames = traceback.extract_tb(exc.__traceback__)
    entry = {
        "filename": os.path.abspath(__file__),
        "function": frames[-1].name if frames else "?",
        "time-of-occurance": datetime.now().isoformat(),
        "methods-to-reproduce": "python3 %s %s" % (os.path.abspath(__file__), " ".join(argv)),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": formatted.strip().splitlines()[-6:],
        "note": "%s (ticket #361, module key forge-rw:47eb5d42f7f1d8fc)" % UNIT,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except OSError:
        return None


def _build_parser():
    import argparse
    parser = argparse.ArgumentParser(
        prog="forge2-dz-debug",
        description="forge2 rewrite of the forge unit "
                    "code__code__jazz__litellm__dz_debug:dz_debug/__init__.py (ticket #361) — a "
                    "package __init__ that re-exports debug_decorator, save and Logger out of the "
                    "sibling modules its CONFIG names. Config-driven: every command below except "
                    "`emit-config` and `selftest` throws if it cannot see its config object.",
        epilog="config is read from the file named by $%s, else from the %s section of the nearest "
               "%s found by walking UP from this module (never from the working directory). This "
               "package ships one at its root, so the commands work from a clean checkout. Run "
               "`emit-config` for a template."
               % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="prove the rewrite against the ORIGINAL's own bytes, plus the "
                                    "edges and the config gate (needs no config, writes no files)")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and where it came from")
    sub.add_parser("surface", help="print the surface the config declares, and whether each name "
                                   "resolves right now (imports nothing)")
    sub.add_parser("bind", help="do what `import dz_debug` did in the ORIGINAL — import every "
                                "source module and bind the surface — and report what bound")
    return parser


def main(argv=None):
    """Entry point for the `forge2-dz-debug` console script. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at it.\n"
                  "# Until it is installed, every part of the surface throws — this unit will not "
                  "guess a default." % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV),
                  file=sys.stderr)
            return 0
        if args.command == "selftest":
            return 0 if selftest() == 0 else 1
        if args.command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(), "base": active_base(),
                              "config": active_config()}, indent=2))
            return 0
        if args.command == "surface":
            declared = surface()
            print(json.dumps({"unit": UNIT, "__all__": [e["name"] for e in declared],
                              "exports": declared}, indent=2))
            # Each name is asked about SEPARATELY, and reports its own reason: two names can fail
            # for different reasons (a module that is absent, a module that lacks the name), and
            # one reason pasted onto every line would be a wrong answer for most of them.
            for entry in declared:
                ok, reason = _resolves(entry["source"])
                if not ok:
                    print("  %s (%s): not resolvable here — %s"
                          % (entry["name"], entry["source"], reason), file=sys.stderr)
            return 0
        if args.command == "bind":
            # The ORIGINAL's `import dz_debug`, exposed as a command: it imports every source
            # module and binds all three names, or fails exactly as the original's import did.
            bound = bind()
            print(json.dumps({"unit": UNIT, "source": active_source(), "__all__": bound,
                              "bound": {name: repr(globals()[name]) for name in bound}}, indent=2))
            return 0
    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except ImportError as exc:
        # Also designed behavior: the config is fine, a module or a name it names is not there.
        # This is exactly what the ORIGINAL's own import statements raised.
        print("import error: %s\n(the config names this module; the module, or the name in it, is "
              "not present — see THE MISSING SIBLINGS in this file's docstring)" % exc,
              file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001
        path = _bug_report(exc, traceback.format_exc(), argv)
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise
    return 0


def _resolves(spec):
    """Report whether `spec` can be resolved right now, as `(ok, reason)`.

    Used only to annotate `surface`'s output: looking is not touching, so this must not raise the
    way `bind()` would. It reports the FULL `module:attr` — a module that imports but does not hold
    the name is just as unresolvable as one that is not there, and the two say different things.
    """
    module, _colon, attr = spec.partition(":")
    try:
        _from_import(_import_source(module), attr, spec)
        return True, ""
    except Exception as exc:  # noqa: BLE001 — reporting, not binding
        return False, "%s: %s" % (type(exc).__name__, exc)


# ──────────────── what this module is, fixed once, before anything can bind ────────────────
#
# Everything above is now defined, so `globals()` at this point holds exactly THIS MODULE'S OWN
# top-level names and nothing else. That set is what `bind()` refuses to let a config overwrite
# (divergence 4), and what `_caller_owns` subtracts to recognise a caller's write. It must be a
# SNAPSHOT rather than a live read of `globals()`, because from the first bind onwards the module
# dict also holds bound exports and whatever callers have assigned.
#
# Like `_BOUND` it is read back out of `globals()` first, so it survives `importlib.reload`.
# Recomputing it on a reload would take the snapshot in a dict that ALREADY holds the previously
# bound exports and any caller's writes, and would silently swear they are this module's own —
# which is exactly the confusion this snapshot exists to prevent. `__all__` is deliberately NOT in
# it: `__all__` is part of the surface this module binds, not machinery a config may not touch.
_OWN_NAMES = globals().get("_OWN_NAMES") or frozenset(
    set(globals()) - {"__all__"} | {"_OWN_NAMES"})

# Give this module the type whose `__getattr__`/`__delattr__` materialize the bind. Assigning
# `__class__` on a module is supported for exactly this purpose, and `_LazyModule` derives from
# `types.ModuleType`, so `dz_debug` remains a module by every test but `type(m) is ModuleType`.
# Reload re-runs this line against the same module object, which is idempotent.
#
# Not when this file is being run as a plain script: `__name__` is then `"__main__"` and
# `sys.modules["__main__"]` is the script itself, which has no surface to bind and must keep
# raising plain AttributeError for a name it does not have. The `__main__` block below re-imports
# the package under its real name, and THAT copy gets the type.
if __name__ != "__main__":
    sys.modules[__name__].__class__ = _LazyModule


if __name__ == "__main__":
    # Executing a package's __init__.py as a plain file leaves it with no package, so its relative
    # export sources could not be resolved (see `_package`). Re-import the package properly by its
    # real name and delegate — so `python3 dz_debug/__init__.py <command>` and the installed
    # `forge2-dz-debug <command>` do exactly the same thing.
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    import dz_debug as _package_self

    if os.path.abspath(_package_self.__file__) != os.path.abspath(__file__):
        # Another dz_debug won the import — running this file would then prove the wrong module.
        print("refusing to run: `import dz_debug` resolves to %s, not this file (%s). Remove the "
              "other one from your path, or run this one's console script."
              % (_package_self.__file__, os.path.abspath(__file__)), file=sys.stderr)
        sys.exit(2)
    sys.exit(_package_self.main())
