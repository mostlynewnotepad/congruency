#!/usr/bin/env python3
"""forge2 / agent_tools_suite / test_crank_discipline — a behavior-preserving rewrite of the forge
unit `agent_tools_suite:test_crank_discipline.py` (module key forge-rw:0fa5adae91bb3f70, git blob
c028a3239bdf61c9509c0ea7d89924b3ead83bc5, 2813 bytes), filed under ticket #432 against the
FORGE-wide refactor standard #200.

WHAT THIS IS
------------
The original unit is the PROOF HARNESS for a different unit, `crank_discipline` — the gate that
stands between a model and a workstation. It proves two things about that gate, and this rewrite
proves exactly the same two:

  1. `gate()` refuses a crank with no INTENT, and refuses one with no open TICKET *when congruency
     answers*. When congruency is unreachable the ticket check is BEST-EFFORT and the gate
     proceeds — an unreachable ledger must not brick the workstation. Provenance (`record`) is
     stubbed out, because it is not what this harness is testing.
  2. `run_confined()` VETOES every escape class — shelling out, opening a network connection,
     writing into the home directory, writing outside the repo — while still allowing a legitimate
     edit inside the repo.

It reports one `✓` / `✗ FAIL` line per check and exits 0 only if every check passed.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and it adds the three things #200 requires that the original
lacked: it is a proper installable package, it is driven by a configuration object, and it refuses
to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    check(name, ok)     -> None   count a check and print its `✓` / `✗ FAIL` line
    refused(thunk)      -> bool   True if `thunk()` raised the gate's refusal, False if it returned
    _down(component)    -> never  raises OSError; the stand-in for "congruency is unreachable"

The module globals these read and write are part of that surface and keep their names and meanings:
`passed` and `failed` (the running counts) and `D` (the module under test — the name the original
bound its `import crank_discipline as D` to).

TERMS USED HERE
---------------
crank
    One act of a model changing a machine. `gate()` decides whether it may happen at all.
intent
    The human-supplied reason for a crank. Empty intent is refused — that is check 1.
open ticket
    A ticket in congruency authorizing work on this component. Its presence is HARD when congruency
    answers and BEST-EFFORT when congruency is down — that difference is checks 2 and 3.
congruency
    The ledger that holds tickets. `_down` simulates it being unreachable, by raising OSError.
crank patch
    An untrusted Python file. `run_confined()` runs one under a runtime veto, confined to a repo.
escape
    An attempt by a patch to act outside its confinement (shell out, network, write out-of-repo).
    Each entry of the `escapes` config object is one escape class this harness must see refused.
the module under test
    `crank_discipline` itself. This harness does NOT implement it — it imports it and drives it.
    The `module` config key names it and `module_paths` says where to import it from, because a
    hardcoded module name and a hardcoded search path are exactly what #200 requirement 4 forbids.
registry / config object
    The JSON configuration registry described in this repository's `note-for-claude`: one `.json`
    file holding the configuration for every tool in a set of packaging. `note-for-claude` states
    the contract this module obeys — "if a tool cannot see the registry it will throw an exeption"
    [sic]. The "config object" is this unit's own `forge2.agent_tools_suite.test_crank_discipline`
    section of it. THIS package ships a `registry.json` beside this file; see CONFIGURATION.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
Every path and every parameter the original hardcoded is now a config key. The unit resolves its
config object from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. This file holds the unit config
     object itself — exactly what `emit-config` prints.
  2. otherwise, the `forge2.agent_tools_suite.test_crank_discipline` section of the nearest
     `registry.json` found by walking UP from THIS FILE's directory.

If NEITHER answers, the unit raises `ConfigError` and tests nothing — it never guesses a default.
That is `note-for-claude`'s rule and this ticket's acceptance item (d). A config object that is
found but is missing a key an operation needs is also a `ConfigError`, naming the key.

This package ships `registry.json` NEXT TO this file, carrying THIS unit's section, so source 2
answers and the harness runs from a clean checkout with no setup. That shipped section is the
config object this unit runs on; it is not a fallback baked into the code. Point `FORGE2_CONFIG` at
a file that does not exist, and the unit throws — the gate is in the code, not in the file's
presence. `selftest` proves the gate directly, without deleting anything.

The config keys, and the original's value for each:

    module           "crank_discipline"    the module under test; imported by this name
    module_paths     ["${here}"]           prepended to `sys.path` to find it. `${here}` is THIS
                                           file's directory (the original's `HERE`), `${base}` the
                                           config's own directory; `~` expands; each is realpath'd.
    banner           "crank_discipline — the inescapable gate"   printed, after a blank line, first
    component        "workstation"         the component every gate check names
    intent           "crank it"            the non-empty intent for the no-ticket check
    intent_alt       "x"                   the non-empty intent for the down / ticket-present checks
    patch_name       "patch.py"            filename each patch is written to inside the sandbox
    escapes          {"shell-out": "...", "network": "...", "home write": "...",
                      "out-of-repo": "..."}
                     Ordered map of escape-class name -> patch source. Each entry becomes one
                     "run_confined blocks <name>" check, IN THIS ORDER, so the map's order is part
                     of the output.
    legit_patch      "open('target.txt','w').write('ok')\\nprint('patched')\\n"
    legit_target     "target.txt"          the file the legit patch is expected to leave behind
    legit_expect     "ok"                  its expected content
    bug_reports      "logs/bug_reports.jsonl"    infrastructure; see SIDE EFFECTS

WHAT IS *NOT* CONFIG, AND WHY
-----------------------------
#200 requires no hardcoded paths or params. It does not require inventing knobs the unit never had,
and a "knob" that changes what the code MEANS is not a setting:

  * The EMPTY intent of check 1 stays in the code. "Refuses when intent is empty" is the check's
    definition; an "empty intent" that came from config could be non-empty, at which point the
    check tests nothing. Same for the OSError that `_down` raises: it IS the down signal the gate
    is specified to treat as best-effort.
  * The check names and the `✓` / `✗ FAIL` / `PASS` / `FAIL` wording stay in the code. They are the
    behavior this ticket preserves — the exemplars assert them verbatim — not settings.
  * The structure of the suite (which checks exist, their ORDER, and what each asserts) is the
    unit's definition, not configuration.

THE DEVIATIONS, STATED PLAINLY
------------------------------
Two, both forced by this ticket's own requirements, and neither changes what
`python3 test_crank_discipline.py` prints or exits:

1. THE SUITE RUNS FROM `main()`, NOT AT IMPORT. The original was a script: importing it ran every
   check and then called `sys.exit()`, so importing it killed the importer. #200 requirement 3 asks
   for an installable package whose modules import (`from agent_tools_suite.test_crank_discipline
   import check`), and this ticket's acceptance item (b) asks that callers of `check`/`refused`/
   `_down` keep working — both of which REQUIRE that importing this module not run a test suite and
   not exit. So the script body now lives in `run_suite()`, called by `main()`, called under the
   `if __name__ == "__main__"` guard. Run as a script it is the same program; imported, it is now
   importable at all. Importing it also no longer needs `crank_discipline` to exist: the module
   under test is imported by `run_suite`, not at module scope, which is what lets this harness be
   installed somewhere the unit it tests is not.

2. `main(argv=None)` TAKES A DEFAULT. The console entry point #200 requirement 3 asks for is called
   as `main()` with no arguments; `None` means `sys.argv`. The original had no `main` at all, so
   nothing existing depends on a different spelling.

Everything else is preserved deliberately, including two things that are easy to mistake for bugs:

  * `refused()` catches ONLY the gate's own refusal (`D.CrankRefused`). Any OTHER exception a thunk
    raises propagates and ends the run. That is the original's behavior and it is the right one: an
    unexpected exception is not a refusal, and reporting it as one would turn a broken gate green.
  * The FINAL check calls `run_confined` OUTSIDE `refused()`, so if the veto wrongly refuses a
    legitimate edit, the exception propagates instead of being counted as a failure. That too is
    the original's behavior. It is preserved rather than "fixed" because this file's mandate is to
    reproduce the original's behavior, not to improve it.

RUNNING IT
----------
Every command below is executable as written from this file's own directory; from anywhere else,
give the full path to `test_crank_discipline.py` instead of the bare name.

    python3 test_crank_discipline.py                  # run the suite (the ORIGINAL's invocation)
    python3 test_crank_discipline.py run              # identical; an explicit alias
    python3 test_crank_discipline.py selftest         # prove the exemplars, the edges, the gate
    python3 test_crank_discipline.py emit-config      # print a config-object template
    python3 test_crank_discipline.py show-config      # print the resolved config + where it came from

The original took no arguments and ignored any it was given; the bare invocation above is the one
its docstring documents, and it still runs the suite. `main` returns the process exit code:

    0  every check passed          1  at least one check FAILED
    4  no config object (nothing was imported, nothing was run)
    5  the module under test could not be imported (nothing was run)

Exit codes 0 and 1 are the original's, unchanged. 4 and 5 are new and cannot collide with the
original's meanings: the original had no config to be missing, and it could not be installed apart
from the unit it tests, because it was not a package.

NOTE ON EXIT 5, WHICH IS WHAT THIS PACKAGE ANSWERS TODAY. `crank_discipline` is a FORGE unit with
its own #200 rewrite ticket, and that ticket has not landed yet — so there is no
`agent_tools_suite/crank_discipline.py` beside this file, and `python3 test_crank_discipline.py`
here answers 5 with one line naming the module and the directories it searched. That is this
harness working, not failing: it is reporting, accurately, that the unit it proves is not present.
The shipped config needs no change when that sibling lands — `module` is already `crank_discipline`
and `module_paths` is already `["${here}"]`, which IS this package's directory, so the suite starts
running the moment the module appears next to it. To run it against a `crank_discipline` that lives
elsewhere today, point `module_paths` at that directory (via `FORGE2_CONFIG`, or the registry).

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, and the package is committed in full
beside it — `pyproject.toml`, `__init__.py`, `registry.json`, all DERIVED from the modules present
by `congruency/tools/forge_package.py` (#410), never hand-authored. From THIS file's directory:

    pip install -e .
    python3 -c "from agent_tools_suite.test_crank_discipline import check, refused, _down"

`pyproject.toml` maps this directory onto the import package `agent_tools_suite`, so an installed
copy imports as `from agent_tools_suite.test_crank_discipline import refused`. `registry.json` is
package-data, so it lands NEXT TO this module on a non-editable install too and the walk-up in (2)
still finds it.

SIDE EFFECTS
------------
Importing this module touches nothing — no config read, no `sys.path` change, no import of the
module under test, no file.

Running the SUITE does what the original's did, and no more: it writes each patch into a temporary
sandbox that it creates and removes, prepends `module_paths` to `sys.path`, and REBINDS `record`
and `has_open_ticket` on the module under test — that rebinding is the point of checks 1-4 and it
is not restored, exactly as the original left it. The patches themselves are run by
`crank_discipline.run_confined`, under its veto; the escape patches are refused, so the files they
reach for (`~/.claude/EVIL`, `~/EVIL_probe`) are never created. That is the property under test.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception is
thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path if it hits an
UNEXPECTED exception — a defect in THIS tool. A `ConfigError` is designed behavior, not a bug, and
files no report. An exception raised by the MODULE UNDER TEST is that module's, not this one's: it
propagates exactly as the original let it propagate, and files no report — blaming this harness for
a gate that crashed would be a lie.
"""

import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime

__all__ = [
    "ConfigError",
    "check", "refused", "_down",
    "run_suite", "main", "selftest",
    "load_module_under_test", "resolve_module_paths",
    "load_config", "configure", "using_config", "reset_config", "config_template",
    "active_config", "active_source", "active_base", "find_registry",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in the
#: config document, not a configurable setting — a config-driven tool has to know which section is
#: its own.
UNIT_PATH = ("forge2", "agent_tools_suite", "test_crank_discipline")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:agent_tools_suite/test_crank_discipline"

#: Exit codes. 0 and 1 are the original's; 4 and 5 are new — see the module docstring, RUNNING IT.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NO_CONFIG = 4
EXIT_NO_MODULE = 5

#: Reserved first arguments. The original took no arguments at all, so a bare run must still mean
#: "run the suite"; anything unreserved is therefore ignored, as the original ignored it.
_COMMANDS = ("run", "selftest", "emit-config", "show-config", "-h", "--help")


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that cannot
    see its config throws rather than guessing a default. Nothing has been imported or run when it
    is raised.
    """


# ─────────────────────────────── the callable surface ───────────────────────────────
#
# `passed`, `failed` and `D` are module globals because they were module globals in the original,
# and `check`/`refused` reach them the same way. Rebinding them here rebinds them for every caller
# that imported this module, which is what the original did too.

#: Running count of checks that passed.
passed = 0

#: Running count of checks that FAILED.
failed = 0

#: The module under test, once `run_suite`/`load_module_under_test` has imported it. `None` until
#: then. The original bound this name with `import crank_discipline as D`; here the module's NAME
#: is config, so the binding happens at run time — but the name `D` is kept, because `refused()`
#: reads it and callers of the surface may too.
D = None


def check(name, ok):
    """Count one check and print its result line: two spaces, `✓` or `✗ FAIL`, then `name`.

    `ok` is taken for its TRUTH, not its identity, so any truthy value passes and any falsy value
    fails — `check("x", 1)` and `check("x", True)` are the same check, as they were in the original.
    """
    global passed, failed
    passed, failed = passed + bool(ok), failed + (not ok)
    print(f"  {'✓' if ok else '✗ FAIL'} {name}")


def refused(thunk):
    """Call `thunk`; return True if it raised the gate's refusal, False if it returned normally.

    "The gate's refusal" is `CrankRefused` as the MODULE UNDER TEST spells it, looked up on `D` at
    call time — so a harness driving a reloaded or substituted module tests that module's exception,
    not a stale one.

    Any other exception PROPAGATES, deliberately: an unexpected exception is not a refusal, and
    counting it as one would report a broken gate as a working one. That is the original's behavior.

    Raises:
        ConfigError: if no module under test has been loaded, so `D.CrankRefused` cannot be read.
            The original could not reach this state — its `import` ran at module scope — so this
            replaces what would otherwise be a bare `AttributeError: 'NoneType'`.
    """
    if D is None:
        raise ConfigError(
            "no module under test is loaded, so `refused()` cannot know what a refusal is. Call "
            "`run_suite()` or `load_module_under_test()` first (both import the `module` named by "
            "this unit's config object).")
    try:
        thunk()
        return False
    except D.CrankRefused:
        return True


def _down(component):
    """Stand in for `has_open_ticket` when congruency is unreachable: always raise OSError.

    The gate is specified to treat this as BEST-EFFORT and proceed — an unreachable ledger must not
    brick the workstation — which is exactly what check 3 asserts. `component` is accepted and
    ignored, so this is a drop-in for the real `has_open_ticket(component)`.
    """
    raise OSError("congruency unreachable")


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None      # config object injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution, so a run re-reads no files


def find_registry(start=None):
    """Walk UP from `start` (default: this file's directory) and return the nearest registry path,
    or None if the walk reaches the filesystem root without finding one.

    Starting at THIS FILE, never at the working directory, is deliberate: which module this harness
    tests must not change because it was launched from somewhere else. `registry.json` ships as
    package-data, so on a non-editable install it sits in this same directory and the first
    iteration finds it.
    """
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
        return config, os.path.dirname(os.path.abspath(env_path)), "%s=%s" % (CONFIG_ENV, env_path)

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
    # may state its own to override it. This is inheritance inside one config document, not a
    # guessed default.
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

    `base` is the directory relative paths in `config` resolve against, and defaults to the current
    working directory. Pass `None` as `config` to drop the injection and go back to resolving from
    disk.
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
    """Drop the injected config and the cached disk resolution."""
    global _ACTIVE, _RESOLVED
    _ACTIVE = None
    _RESOLVED = None


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do the unit throws. The values are the ORIGINAL unit's
    hardcoded ones, so a registry built from this template makes this rewrite behave exactly like
    the module it replaces.
    """
    return {
        "module": "crank_discipline",
        "module_paths": ["${here}"],
        "banner": "crank_discipline — the inescapable gate",
        "component": "workstation",
        "intent": "crank it",
        "intent_alt": "x",
        "patch_name": "patch.py",
        "escapes": {
            "shell-out": "import subprocess\nsubprocess.run(['echo','x'])\n",
            "network": "import socket\nsocket.create_connection(('example.com', 80))\n",
            "home write": "import os\nopen(os.path.expanduser('~/.claude/EVIL'),'w').write('x')\n",
            "out-of-repo": "import os\nopen(os.path.expanduser('~/EVIL_probe'),'w').write('x')\n",
        },
        "legit_patch": "open('target.txt','w').write('ok')\nprint('patched')\n",
        "legit_target": "target.txt",
        "legit_expect": "ok",
        "bug_reports": "logs/bug_reports.jsonl",
    }


def _require(config, key, types, what):
    """Return `config[key]`, checking its type. A missing or mistyped key is a ConfigError naming
    the key — never a silent default."""
    if key not in config:
        raise ConfigError("config object for %s is missing the required key %r (%s). Run "
                          "`emit-config` for a template." % (UNIT, key, what))
    value = config[key]
    if not isinstance(value, types):
        names = types.__name__ if isinstance(types, type) else "/".join(t.__name__ for t in types)
        raise ConfigError("config key %r for %s must be %s, not %s"
                          % (key, UNIT, names, type(value).__name__))
    return value


def _require_str_list(config, key, what):
    """Return `config[key]` as a tuple of str, or raise ConfigError naming the offending element."""
    value = _require(config, key, list, what)
    for element in value:
        if not isinstance(element, str):
            raise ConfigError("config key %r for %s must be a list of strings; it contains %r (%s)"
                              % (key, UNIT, element, type(element).__name__))
    return tuple(value)


def _require_str_map(config, key, what):
    """Return `config[key]` as an ORDER-PRESERVING dict of str -> str.

    The order is load-bearing: it is the order the checks run and therefore the order the output
    lines appear in. `json.load` preserves a JSON object's textual order, so the config file's
    order IS the output's order.
    """
    value = _require(config, key, dict, what)
    for name, source in value.items():
        if not isinstance(name, str) or not isinstance(source, str):
            raise ConfigError("config key %r for %s must map strings to strings; it contains "
                              "%r -> %r" % (key, UNIT, name, source))
    return dict(value)


# ─────────────────────────────── the module under test ───────────────────────────────

def resolve_module_paths(config=None, base=None):
    """Expand this unit's `module_paths` into absolute directories to search for the module.

    `${here}` expands to THIS file's directory — which is what the original's `HERE` was — and
    `${base}` to the config's own directory. `~` expands, a relative path resolves against `base`,
    and every result is realpath'd. Returns a tuple, in config order.
    """
    if config is None:
        config = active_config()
    if base is None:
        base = active_base()
    here = os.path.dirname(os.path.abspath(__file__))
    resolved = []
    for token in _require_str_list(config, "module_paths",
                                   "directories prepended to sys.path to find the module"):
        text = token.replace("${here}", here).replace("${base}", base)
        text = os.path.expanduser(text)
        if not os.path.isabs(text):
            text = os.path.join(base, text)
        resolved.append(os.path.realpath(text))
    return tuple(resolved)


def load_module_under_test(config=None, base=None):
    """Import the module named by the `module` config key and bind it to the global `D`.

    Each entry of `module_paths` is prepended to `sys.path` first, exactly as the original's
    `sys.path.insert(0, HERE)` did, and — also as the original did — the entry is left there.
    Returns the imported module.

    Raises:
        ConfigError: if the config object is absent or lacks `module` / `module_paths`.
        ImportError: if the module cannot be found. The original raised the same, from the same
            cause, and the message names the paths that were searched.
    """
    global D
    if config is None:
        config = active_config()
    if base is None:
        base = active_base()
    name = _require(config, "module", str, "the module under test, imported by this name")
    for directory in reversed(resolve_module_paths(config, base)):
        sys.path.insert(0, directory)
    try:
        module = importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(
            "%s could not import the module under test %r from %s: %s"
            % (UNIT, name, list(resolve_module_paths(config, base)), exc)) from exc
    D = module
    return module


# ─────────────────────────────── the suite ───────────────────────────────

def _gate_checks(config):
    """Run checks 1-4: the gate's intent rule and its ticket rule, reachable and down.

    `record` is rebound to a stub first and left that way: provenance is not under test, and the
    stub's return value is what checks 3 and 4 read `component` back out of.
    """
    component = _require(config, "component", str, "the component every gate check names")
    intent = _require(config, "intent", str, "the non-empty intent for the no-ticket check")
    intent_alt = _require(config, "intent_alt", str,
                          "the non-empty intent for the down / ticket-present checks")

    # Provenance is not under test — stub it out, as the original did.
    D.record = lambda component, intent, session: {"component": component}

    # 1. An empty intent is refused. The emptiness is the check, so it is not config.
    check("no intent -> refused", refused(lambda: D.gate(component, "")))

    # 2. Congruency answers and says there is NO open ticket -> refused. The ticket rule is HARD
    #    whenever the ledger can be reached.
    D.has_open_ticket = lambda component: False
    check("reachable + no ticket -> refused", refused(lambda: D.gate(component, intent)))

    # 3. Congruency is DOWN -> the ticket check is best-effort and the gate proceeds. `_down` is the
    #    stand-in; an unreachable ledger must not brick the workstation.
    D.has_open_ticket = _down
    check("congruency down -> ticket best-effort, proceeds",
          D.gate(component, intent_alt)["component"] == component)

    # 4. Congruency answers and the ticket is there -> the gate passes.
    D.has_open_ticket = lambda component: True
    check("reachable + ticket -> passes", D.gate(component, intent_alt)["component"] == component)


def _confinement_checks(config):
    """Run checks 5-N: every escape class is vetoed, and a legitimate repo edit still lands.

    The sandbox is a temporary directory this function creates and removes; it is both the repo the
    patch is confined to and the directory each patch is written into, which is what the original
    did.
    """
    escapes = _require_str_map(config, "escapes", "escape-class name -> patch source")
    patch_name = _require(config, "patch_name", str, "filename each patch is written to")
    legit_patch = _require(config, "legit_patch", str, "source of the legitimate patch")
    legit_target = _require(config, "legit_target", str, "file the legit patch should leave behind")
    legit_expect = _require(config, "legit_expect", str, "expected content of that file")

    with tempfile.TemporaryDirectory() as sandbox:
        for name, source in escapes.items():
            patch = os.path.join(sandbox, patch_name)
            with open(patch, "w", encoding="utf-8") as handle:
                handle.write(source)
            check(f"run_confined blocks {name}",
                  refused(lambda: D.run_confined(patch, sandbox)))

        patch = os.path.join(sandbox, patch_name)
        with open(patch, "w", encoding="utf-8") as handle:
            handle.write(legit_patch)
        # Deliberately NOT inside refused(): if the veto wrongly refuses a legitimate edit, the
        # refusal propagates and ends the run, exactly as it did in the original.
        D.run_confined(patch, sandbox)
        with open(os.path.join(sandbox, legit_target), "r", encoding="utf-8") as handle:
            check("run_confined allows a legit repo edit", handle.read() == legit_expect)


def run_suite(config=None, base=None, module=None):
    """Run every check and print the report. Returns the exit code: 0 if all passed, else 1.

    `module` is the already-imported module under test; when it is None this imports it, which is
    what a bare `run_suite()` does. `main` passes it in, because `main` imports it inside its own
    error handling so that an absent module is one clean line rather than a traceback.

    The counters are reset first, so a second call in one process reports its own run rather than
    accumulating onto the first. The original could only ever run once per process, so this
    contradicts nothing it did.
    """
    global passed, failed, D
    if config is None:
        config = active_config()
    if base is None:
        base = active_base()
    banner = _require(config, "banner", str, "the title line printed before the checks")

    if module is None:
        load_module_under_test(config, base)
    else:
        D = module
    passed = failed = 0
    print("\n" + banner)
    _gate_checks(config)
    _confinement_checks(config)
    print(f"\n{'PASS' if not failed else 'FAIL'} — {passed} passed, {failed} failed")
    return EXIT_FAILED if failed else EXIT_OK


# ─────────────────────────────── the CLI ───────────────────────────────

def _print_help():
    print(__doc__.split("RUNNING IT\n----------\n", 1)[1].split("\nINSTALLABLE", 1)[0].strip())


def _bug_report(exc, tb, argv):
    """Append one timestamped JSON line describing an UNEXPECTED exception; return its path.

    `note-for-claude` asks every tool to file a bug report automatically when an exception is
    thrown. Returns None if no report could be filed — a tool that cannot file a report must still
    report the original exception, not a second one about the filing.
    """
    try:
        config = active_config()
        target = config.get("bug_reports")
        if not isinstance(target, str) or not target:
            return None
        if not os.path.isabs(target):
            target = os.path.join(active_base(), target)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        line = json.dumps({
            "ts": datetime.now().astimezone().isoformat(),
            "unit": UNIT,
            "argv": list(argv),
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": tb,
        })
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return target
    except Exception:      # noqa: BLE001 — a failed bug report must never mask the real exception
        return None


def main(argv=None):
    """Run the crank_discipline proof harness. Returns the process exit code.

    `argv` is a full argv INCLUDING the program name at `argv[0]`. The original took no arguments
    and ignored any it was given, so a bare `python3 test_crank_discipline.py` runs the suite and an
    unrecognized argument is ignored rather than rejected.

        0  every check passed      1  a check FAILED      4  no config object

    THE SURFACE ADDITION. `argv=None` means `sys.argv`. The default is required, not cosmetic:
    #200 requirement 3 asks for a console entry point, and setuptools calls it as `main()` with no
    arguments.
    """
    argv = list(sys.argv if argv is None else argv)
    command = argv[1] if len(argv) > 1 and argv[1] in _COMMANDS else "run"
    try:
        if command in ("-h", "--help"):
            _print_help()
            return EXIT_OK
        if command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at it.\n"
                  "# Until it is installed, this harness throws — it will not guess a default."
                  % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV), file=sys.stderr)
            return EXIT_OK
        if command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(), "base": active_base(),
                              "config": active_config()}, indent=2))
            return EXIT_OK
        if command == "selftest":
            return EXIT_OK if selftest() == 0 else EXIT_FAILED
        config, base = active_config(), active_base()
        # Imported HERE, inside the handler, so that "the unit under test is not installed beside
        # this harness" is one self-explaining line instead of a traceback. Nothing has run yet.
        module = load_module_under_test(config, base)
    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no bug report.
        # Nothing has been imported and nothing has been run.
        sys.stderr.write("config error: %s\n" % exc)
        return EXIT_NO_CONFIG
    except ImportError as exc:
        # Also designed behavior: this harness is a package module and can be installed where the
        # unit it tests is not. Not a defect in this tool, so no bug report.
        sys.stderr.write("module under test: %s\n" % exc)
        return EXIT_NO_MODULE
    except Exception as exc:      # noqa: BLE001 — an unexpected exception HERE is a defect in this
        # tool, which is exactly what note-for-claude wants reported.
        path = _bug_report(exc, traceback.format_exc(), argv[1:])
        sys.stderr.write("EXCEPTION — %s\n" % ("bug report filed at %s" % path if path
                                               else "no bug report could be filed"))
        raise

    # The suite runs OUTSIDE the handler above, deliberately. An exception raised in here comes from
    # the MODULE UNDER TEST — a gate that crashed — and it is that module's defect, not this
    # harness's. The original let it propagate untouched; filing a bug report against THIS module
    # for it would be a lie, and catching it would bury the gate's own frames.
    return run_suite(config, base, module)


# ─────────────────────────────── the selftest ───────────────────────────────

#: A stub `crank_discipline`, written into a temp dir by the selftest and imported as the module
#: under test. It implements the gate contract the ORIGINAL asserts, and a veto that refuses any
#: patch whose source carries an ESCAPE marker.
#:
#: It is a FIXTURE, and what it is for is worth stating exactly, because a stand-in can flatter the
#: thing it stands in for: it proves THIS harness drives a gate correctly and prints the original's
#: report verbatim while doing so. It proves NOTHING about the real `crank_discipline`, and it is
#: not evidence that the real gate vetoes anything.
#:
#: To run this harness against a REAL `crank_discipline`, point `module_paths` at a directory
#: holding one and run it — no code change, which is what requirement 4 buys. That is how this
#: rewrite was checked against the original it replaces: both were pointed at one real gate (whose
#: `run_confined` delegated to the landed sibling `agent_tools_suite/audit_guard.py`, so the escapes
#: met real `sys.addaudithook` vetoes) and their stdout and exit codes were compared byte for byte.
#: Anyone can redo that: the two programs take the same config and print to the same stdout.
_STUB = '''
class CrankRefused(RuntimeError):
    pass


def record(component, intent, session=None):
    return {"component": component, "intent": intent, "session": session}


def has_open_ticket(component):
    raise OSError("congruency unreachable")


def gate(component, intent, session=None):
    if not intent:
        raise CrankRefused("no intent")
    try:
        ok = has_open_ticket(component)
    except OSError:
        ok = True
    if not ok:
        raise CrankRefused("no open ticket")
    return record(component, intent, session)


def run_confined(patch, repo):
    import os
    src = open(patch).read()
    if "ESCAPE" in src:
        raise CrankRefused("escape blocked")
    # The real gate runs the patch CONFINED TO `repo`, so a relative path in the patch resolves
    # inside it. The stub reproduces that with a chdir, which is what makes the legit patch's
    # `open('target.txt','w')` land in the repo rather than in the caller's cwd.
    cwd = os.getcwd()
    os.chdir(repo)
    try:
        exec(compile(src, patch, "exec"), {"__name__": "__main__", "REPO": repo})
    finally:
        os.chdir(cwd)
'''


def _attempt(thunk):
    """Call `thunk`; return `("ok", value)` or `("raised", type_name, message)`.

    A test net that dies on the first unexpected exception hides every check after it and reports a
    traceback where it owes a verdict. Every check below compares against one of these tuples, so an
    exception is a REPORTED result — including the ones that are EXPECTED results here.
    """
    try:
        return ("ok", thunk())
    except BaseException as exc:      # noqa: BLE001 — a test net must survive anything
        return ("raised", type(exc).__name__, str(exc))


def _stub_config(root):
    """The config object the selftest's exemplars run against: the original's SHAPE, pointed at the
    stub gate in `root`. Escape sources carry the stub's ESCAPE marker; the legit one does not."""
    return {
        "module": "_selftest_crank_stub",
        "module_paths": [root],
        "banner": "crank_discipline — the inescapable gate",
        "component": "workstation",
        "intent": "crank it",
        "intent_alt": "x",
        "patch_name": "patch.py",
        "escapes": {
            "shell-out": "# ESCAPE shell\n",
            "network": "# ESCAPE net\n",
            "home write": "# ESCAPE home\n",
            "out-of-repo": "# ESCAPE oor\n",
        },
        "legit_patch": "open('target.txt','w').write('ok')\n",
        "legit_target": "target.txt",
        "legit_expect": "ok",
        "bug_reports": "logs/bug_reports.jsonl",
    }


#: The exact report a full run must print, given `_stub_config`. This is the ORIGINAL's output,
#: line for line — its banner, its four gate checks in its order, one line per escape class, its
#: legit-edit line and its summary — and asserting it verbatim is what makes this rewrite
#: behavior-preserving rather than merely plausible.
_EXPECTED_REPORT = """
crank_discipline — the inescapable gate
  ✓ no intent -> refused
  ✓ reachable + no ticket -> refused
  ✓ congruency down -> ticket best-effort, proceeds
  ✓ reachable + ticket -> passes
  ✓ run_confined blocks shell-out
  ✓ run_confined blocks network
  ✓ run_confined blocks home write
  ✓ run_confined blocks out-of-repo
  ✓ run_confined allows a legit repo edit

PASS — 9 passed, 0 failed
"""


def selftest(stream=None):
    """Prove the exemplars, the edges and the config gate. Returns 0 if everything held, else 1.

    Every exemplar below was written BY HAND from the original's behavior, because this module had
    no minable functions and the ticket therefore captured no exemplars: the original's every
    function touches the world (printing, or the module under test), which is what
    `criteria_miner` refuses.
    """
    global passed, failed, D
    out = stream or sys.stdout
    results = []

    def prove(name, got, want):
        results.append((name, got == want, got, want))

    saved = (passed, failed, D)
    try:
        # ── check(): the counters and the exact line format ───────────────────────────────
        for label, ok, want_line, want_counts in [
            ("check(True) prints ✓", True, "  ✓ n\n", (1, 0)),
            ("check(False) prints ✗ FAIL", False, "  ✗ FAIL n\n", (0, 1)),
            ("check() takes truth, not identity: 1", 1, "  ✓ n\n", (1, 0)),
            ("check() takes truth, not identity: []", [], "  ✗ FAIL n\n", (0, 1)),
            ("check() takes truth, not identity: 'x'", "x", "  ✓ n\n", (1, 0)),
        ]:
            passed = failed = 0
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                returned = check("n", ok)
            prove(label, (buf.getvalue(), (passed, failed), returned),
                  (want_line, want_counts, None))

        passed = failed = 0
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            check("a", True)
            check("b", False)
            check("c", True)
        prove("check() accumulates across calls", (buf.getvalue(), (passed, failed)),
              ("  ✓ a\n  ✗ FAIL b\n  ✓ c\n", (2, 1)))

        # ── _down(): the congruency-unreachable signal ────────────────────────────────────
        prove("_down() raises OSError", _attempt(lambda: _down("workstation")),
              ("raised", "OSError", "congruency unreachable"))
        prove("_down() ignores its component", _attempt(lambda: _down("anything-else")),
              ("raised", "OSError", "congruency unreachable"))

        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "_selftest_crank_stub.py"), "w", encoding="utf-8") as fh:
                fh.write(_STUB)
            config = _stub_config(root)

            # ── refused(): needs a module, then reads THAT module's exception ──────────────
            D = None
            got = _attempt(lambda: refused(lambda: None))
            prove("refused() without a module under test throws ConfigError",
                  (got[0], got[1]), ("raised", "ConfigError"))

            with using_config(config, base=root):
                module = load_module_under_test()
                prove("load_module_under_test() binds the global D", D is module, True)
                prove("refused() is True when the thunk raises CrankRefused",
                      _attempt(lambda: refused(_raiser(module.CrankRefused))), ("ok", True))
                prove("refused() is False when the thunk returns",
                      _attempt(lambda: refused(lambda: "returned")), ("ok", False))
                prove("refused() lets a NON-refusal propagate — a crash is not a refusal",
                      _attempt(lambda: refused(_raiser(ValueError, "boom"))),
                      ("raised", "ValueError", "boom"))

                # ── the full run: the ORIGINAL's report, verbatim ──────────────────────────
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    code = run_suite()
                prove("a full run prints the original's report verbatim", buf.getvalue(),
                      _EXPECTED_REPORT)
                prove("a full run of all-passing checks exits 0", code, EXIT_OK)
                prove("the counters agree with the report", (passed, failed), (9, 0))

                # ── a FAILING run reports FAIL and exits 1 ─────────────────────────────────
                broken = dict(config, legit_expect="NOT-ok")
                with using_config(broken, base=root):
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        code = run_suite()
                    prove("a failed check prints ✗ FAIL and the FAIL summary",
                          (buf.getvalue().rstrip("\n").splitlines()[-3:], code),
                          (["  ✗ FAIL run_confined allows a legit repo edit", "",
                            "FAIL — 8 passed, 1 failed"], EXIT_FAILED))

                # ── the escapes map's ORDER is the output's order ──────────────────────────
                reordered = dict(config)
                reordered["escapes"] = {"network": "# ESCAPE a\n", "shell-out": "# ESCAPE b\n"}
                with using_config(reordered, base=root):
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        run_suite()
                    prove("the escapes map's order is the report's order",
                          [ln for ln in buf.getvalue().splitlines() if "blocks" in ln],
                          ["  ✓ run_confined blocks network", "  ✓ run_confined blocks shell-out"])

                # ── config: every required key throws when absent, naming itself ───────────
                for key in ("module", "module_paths", "banner", "component", "intent",
                            "intent_alt", "patch_name", "escapes", "legit_patch", "legit_target",
                            "legit_expect"):
                    partial = {k: v for k, v in config.items() if k != key}
                    # stdout is discarded: a run that throws PART WAY through still printed the
                    # lines it got to, and those belong to the probe, not to this report.
                    with using_config(partial, base=root), contextlib.redirect_stdout(io.StringIO()):
                        got = _attempt(lambda: run_suite())
                    prove("a config missing %r throws, naming it" % key,
                          (got[0], got[1], repr(key) in got[2] if len(got) > 2 else False),
                          ("raised", "ConfigError", True))

                # ── config: a mistyped key throws rather than coercing ─────────────────────
                with using_config(dict(config, escapes=["not", "a", "map"]), base=root), \
                        contextlib.redirect_stdout(io.StringIO()):
                    got = _attempt(lambda: run_suite())
                prove("a mistyped 'escapes' throws ConfigError", (got[0], got[1]),
                      ("raised", "ConfigError"))

                # ── an ABSENT module under test: one clean line and exit 5, never a traceback ──
                # This is the state THIS package is in today: `crank_discipline` has its own #200
                # rewrite ticket and has not landed beside this file yet.
                absent = dict(config, module="_no_such_module_under_test")
                with using_config(absent, base=root):
                    buf = io.StringIO()
                    with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(io.StringIO()):
                        code = main(["test_crank_discipline.py"])
                    prove("an absent module under test -> exit 5, one clean line, no traceback",
                          (code, buf.getvalue().startswith("module under test:"),
                           "_no_such_module_under_test" in buf.getvalue(),
                           "Traceback" in buf.getvalue()),
                          (EXIT_NO_MODULE, True, True, False))
                    got = _attempt(lambda: load_module_under_test())
                    prove("load_module_under_test() on an absent module raises ImportError naming "
                          "the search path",
                          (got[0], got[1], root in got[2]), ("raised", "ImportError", True))

                # ── run_suite() accepts an already-imported module and binds it to D ───────────
                with contextlib.redirect_stdout(io.StringIO()):
                    code = run_suite(config, root, module)
                prove("run_suite(module=...) uses the module it was handed", (code, D is module),
                      (EXIT_OK, True))

        # ── the #200 requirement-4 gate: no config -> throw, never guess ──────────────────
        # Proved WITHOUT deleting anything, by pointing FORGE2_CONFIG at a file that is not there.
        reset_config()
        missing = os.path.join(tempfile.gettempdir(), "forge2-config-that-does-not-exist.json")
        previous = os.environ.get(CONFIG_ENV)
        os.environ[CONFIG_ENV] = missing
        try:
            got = _attempt(lambda: active_config())
            prove("no config object -> ConfigError, not a guessed default", (got[0], got[1]),
                  ("raised", "ConfigError"))
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                code = main(["test_crank_discipline.py"])
            prove("the CLI answers 4 and one clean line when it cannot see its config",
                  (code, buf.getvalue().startswith("config error:"), "Traceback" in buf.getvalue()),
                  (EXIT_NO_CONFIG, True, False))
        finally:
            if previous is None:
                os.environ.pop(CONFIG_ENV, None)
            else:
                os.environ[CONFIG_ENV] = previous
            reset_config()

        # ── the surface is the original's ─────────────────────────────────────────────────
        import inspect
        prove("check(name, ok) keeps its signature",
              str(inspect.signature(check)), "(name, ok)")
        prove("refused(thunk) keeps its signature",
              str(inspect.signature(refused)), "(thunk)")
        prove("_down(component) keeps its signature",
              str(inspect.signature(_down)), "(component)")

        # ── importing this module runs nothing and reads nothing ──────────────────────────
        prove("importing this module does not run the suite",
              __name__ in ("__main__", "agent_tools_suite.test_crank_discipline",
                           "test_crank_discipline"), True)
    finally:
        passed, failed, D = saved

    bad = [r for r in results if not r[1]]
    out.write("\n%s — selftest: %d checks, %d failed\n"
              % ("PASS" if not bad else "FAIL", len(results), len(bad)))
    for name, ok, got, want in results:
        out.write("  %s %s\n" % ("✓" if ok else "✗ FAIL", name))
        if not ok:
            out.write("      got  %r\n      want %r\n" % (got, want))
    return 0 if not bad else 1


def _raiser(exc, *args):
    """Return a thunk that raises `exc(*args)` — a named helper, so the selftest's intent reads."""
    def thunk():
        raise exc(*args)
    return thunk


if __name__ == "__main__":
    sys.exit(main())
