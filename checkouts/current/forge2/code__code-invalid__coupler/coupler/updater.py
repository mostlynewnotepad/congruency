#!/usr/bin/env python3
"""forge2 / code__code-invalid__coupler / coupler.updater — a behavior-preserving rewrite of
the forge unit `code__code-invalid__coupler:coupler/updater.py` (module key
forge-rw:8968b64101a54fde), filed under ticket #375 against the FORGE-wide refactor standard
#200.

(#375 supersedes #294, which named its source only as a `git cat-file` against the forge's
bare repos that the sandboxed pair_loop worker cannot run. #375 embeds the source instead, so
the rewrite needs no forge access, and the work is done HERE. `ORIGINAL_SOURCE` below is that
embedded copy, and `selftest` check [0] proves it is the real forge blob by hashing it — see
THE EQUIVALENCE BASIS.)

WHAT THIS IS
------------
The original forge unit was 3106 bytes: the auto-updater launchd runs on a timer. It fetches
the `coupler` git repo, compares the locally installed version against the latest tag
reachable from `origin/stable`, and — if they differ — pulls, reinstalls with pip, and kicks
the launchd service so the server restarts.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and it adds the three things #200 requires that the
original lacked: it is part of a proper installable package, it is driven by a configuration
object, and it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
Quoted from ticket #375, which lowered the original with codebean's `lower_node` (#183):

    _run(cmd: list, **kw) -> subprocess.CompletedProcess
    _current_version() -> str
    _remote_version() -> str | None
    _pull_and_install() -> bool
    _restart_server()
    main()

All six are preserved exactly: same names, same parameters, same annotations. `selftest`
check [4] proves each of those properties by inspection rather than asserting them.

The original also bound module-level names that callers and tests read and REBIND. They are
part of the surface in practice, so they are still module globals here, and every function
still reads them at CALL time (not captured at import), so `import coupler.updater as u;
u.REPO = other` keeps working exactly as it did:

    REPO       the git checkout every git/pip command runs in     (a `pathlib.Path`)
    PYTHON     the interpreter, `sys.executable`
    PIP        the pip command prefix, `[PYTHON, "-m", "pip"]`
    LAUNCHCTL  the launchctl binary                                (a `str`)
    SERVICE    the launchd service label                           (a `str`)
    LOG_FILE   the log file `logging.basicConfig` is pointed at    (a `pathlib.Path`)
    log        the module's `logging.Logger`

`json` is bound too, because the original imported it and never used it. That unused import
leaked a module-level name, so `coupler.updater.json` resolved; this module imports `json` as
well (its config reader needs it), so that name still resolves. It is named here rather than
left to coincidence.

`logging_config()` is new. The original passed its `logging.basicConfig` keywords inline at
module scope, where nothing could read them back without re-importing the module. Those
keywords are a behavior worth pinning, so they are lifted into a named function. The import
below calls it, so what it returns IS what configures logging — not a copy that could drift.

WHAT THE ORIGINAL ACTUALLY DID — READ OFF THE CODE, NOT ASSUMED
---------------------------------------------------------------
Six details are easy to "fix" and wrong to. Each is preserved deliberately, and `selftest`
checks [2] and [3] prove each one against the ORIGINAL AS IT RUNS:

  * `_restart_server` calls `subprocess.run` DIRECTLY, not through `_run`. So the kickstart —
    alone among every subprocess this module spawns — runs with NO `cwd`, i.e. in whatever
    directory the process was started in, while every git and pip command runs with
    `cwd=REPO`. It reads as an oversight and it is preserved, not repaired.
  * `.lstrip("v")` strips EVERY leading "v", not one prefix. `"vv2.0"` becomes `"2.0"`, and a
    tag named `"version9"` becomes `"ersion9"`. `str.lstrip` takes a SET of characters, which
    is a classic misreading; the original's behavior is what is preserved.
  * `main()` calls `_remote_version()` BEFORE `_current_version()`. The fetch therefore
    happens first, and when it fails `_current_version()` is never called at all — so a
    machine with no local tag never reaches the `importlib.metadata` fallback on an offline
    run. The order is load-bearing and is preserved.
  * `_current_version`'s fallback is UNGUARDED. When `git describe` fails AND the
    distribution is not installed, `importlib.metadata.version` raises
    `PackageNotFoundError` straight out of `main()`. The original did not catch it; neither
    does this.
  * `_pull_and_install` returns False on the FIRST failing step, so a failed `git pull` means
    pip is never invoked.
  * `logging.basicConfig` runs at IMPORT, which OPENS (and therefore creates) the log file as
    a side effect of importing the module. See SIDE EFFECTS — it is preserved, not hidden.

THE EQUIVALENCE BASIS (#200 requirement 1, acceptance item (a))
---------------------------------------------------------------
Ticket #375 records that criteria_miner captured NO exemplars for this module — it "mines only
self-contained pure functions (it refuses anything that mentions a world-touching or
non-deterministic name, plus methods and no-arg functions), and nothing here qualified" — and
states that this "MOVES the work: you must write the equivalence exemplars by hand from the
original's behavior before rewriting, and they are what settles this ticket."

`EXEMPLARS` and `EDGE_CASES` below are that hand-written table. Their expected values are NOT
hand-copied and hoped to be right: `selftest` runs each scenario against the ORIGINAL and
against this rewrite, under identically staged conditions, and compares the observations field
by field. The original is therefore the oracle, and a disagreement is a FAIL — this is the
differential idiom this package established (`coupler/bridge.py`, #357).

That is only worth anything if the embedded original is really the forge's module, so
`selftest` check [0] hashes `ORIGINAL_SOURCE` as git hashes a blob and compares the digest to
the blob sha1 ticket #375 records (`3800ae29cb412ff82b508a1493649e900074fbe0`). It also checks
the length against the ticket's stated 3106 bytes. If either differs the whole selftest is
worthless, so it is the first thing checked and it fails loudly.

TERMS USED HERE
---------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a single
    `.json` file at the root of a package holding the configuration for every tool in that
    package. `note-for-claude` states the contract in its own words — ".json will have all the
    configuration - for all tools in this set of packaging. (a configuration registry) -if a
    tool cannot see the registry it will throw an exeption." [sic] This package ships its own
    `registry.json` at its root, one directory above this file.
config object
    The chunk of that registry belonging to this unit — the section at
    `forge2 -> code__code-invalid__coupler -> coupler.updater`. It is what drives this module.
    `emit-config` prints a template of it.
exemplar
    One (scenario -> expected outcome) pair the rewrite must reproduce, standing in for the
    automated captures ticket #375 could not mine.
oracle
    The embedded original, executed. Every expected value in this file's proof is read off it
    at run time rather than written down here.
launchd / launchctl
    macOS's service manager and its command-line client. `launchctl kickstart -k gui/<uid>/
    <label>` restarts the named per-user service, which is how the updater bounces the coupler
    server after an update.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The original hardcoded every parameter it had: the repo location (`__file__`'s grandparent),
the launchctl path `/bin/launchctl`, the service label `com.coupler.server`, the log path
`~/Library/Logs/coupler-updater.log`, the log level/format/datefmt, the logger name
`coupler.updater`, the distribution name `coupler`, the `"v"` stripped off tags, the git
executable, the `origin` remote and `stable` branch, every git argument list
(`describe --tags --abbrev=0`, `fetch --tags`, `pull --ff-only`), the pip command
`[sys.executable, "-m", "pip"]` and its `install -e . -q` arguments, the launchctl
`kickstart -k` arguments and the `gui/{uid}/{service}` target, and all eleven log message
templates. Those are exactly the params #200's fourth requirement forbids hardcoding, so every
one of them is read from this unit's config object and NOTHING is defaulted in code.

This package ships a `registry.json` carrying precisely the original's values, so an ordinary
`import coupler.updater` from a source checkout or an editable install behaves exactly as the
original did. `selftest` check [2] is what proves that claim: it runs the shipped config
against the original and requires the observations to match, and check [6] proves by AST that
none of those values survives as a literal in this module's executable code.

The config is read at IMPORT, because the original bound `REPO`, `PIP`, `LOG_FILE` and the
rest at import and that is the behavior being preserved. So `import coupler.updater` raises
`ConfigError` when no config object can be resolved: ticket #375's acceptance item (d) and
`note-for-claude`'s rule. It does not guess `/bin/launchctl`, it does not guess
`com.coupler.server`, and it does not quietly leave the globals unbound. `selftest` check [1]
proves it, in child interpreters.

Resolution order — the first source that answers wins:

  1. the file named by the `COUPLER_UPDATER_CONFIG` environment variable, which holds this
     unit's config object itself — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code-invalid__coupler -> coupler.updater` section of the
     nearest `registry.json` found by walking UP from THIS FILE's directory;
  3. otherwise, the `registry.json` shipped as package data inside the installed
     `code__code_invalid__coupler` package, located with `importlib.util.find_spec`.

The walk-up starts at this file, never at the working directory, so which directory you run
from does not change what config is found. Step 3 exists because a plain (non-editable)
`pip install .` puts this module at `site-packages/coupler/updater.py`, and the walk-up from
there passes no registry at all — `site-packages` has none. See `find_registry`.

The variable is named for THIS unit rather than something forge2-wide on purpose: it names a
file holding ONE unit's config object, and a variable shared across units could only ever
point at one unit's object at a time.

`repo_path` and `log_file` are resolved against the directory holding the registry that
supplied them (`active_base()`), so the shipped `"."` names this package root — which is
exactly what the original's `Path(__file__).parent.parent` computed. That is not an argument;
`selftest` check [6] compares this module's `REPO` and `LOG_FILE` against the ORACLE's,
computed from the original's own expressions, and requires them equal.

SIDE EFFECTS
------------
Stated plainly, because one of them is a file and "creates no files" would be false:

  * IMPORTING this module reads one JSON file and then calls `logging.basicConfig`, which
    OPENS the configured `LOG_FILE` in append mode — CREATING it if it does not exist — and
    installs a handler on the ROOT logger. That is the original's behavior, preserved. With
    the shipped config the file is `~/Library/Logs/coupler-updater.log`, so importing this
    module (including to run `selftest`) creates that file if it is absent. Point `log_file`
    elsewhere to move it. Two of the original's quirks come along: `basicConfig` is a no-op
    when the root logger already has handlers, so an application that configured logging
    first silences this; and the log file's PARENT directory is not created, so importing
    this module where that directory is missing raises `FileNotFoundError`, as the original
    did.
  * `_run`, `_current_version`, `_remote_version` and `_pull_and_install` spawn git and pip in
    `REPO`; `_pull_and_install` reinstalls the package; `_restart_server` spawns launchctl and
    restarts a service; `main()` does all of it. That is the tool's whole purpose.
  * Every command in RUNNING IT except `run` spawns nothing and touches no service.
    `selftest` replaces `subprocess`, `os` and this module's logger with recording stand-ins
    before anything under test runs and puts them back afterwards; check [5] proves the
    restoration rather than trusting it, and check [7] proves this package's tree is unchanged
    by the whole run. `selftest` writes no file outside a temporary directory it removes.
  * `install-check` really does run `pip install`, into a throwaway `--prefix`/`--target`
    directory it removes; it never installs into the running interpreter. It is the only
    command that reaches the network, and only if pip needs a build backend it has not cached.
    It DOES leave setuptools' usual `build/` and `*.egg-info/` scaffolding in the package root
    — named here rather than glossed over, because it is a real change to the directory. Those
    are precisely the build artifacts ticket #375 says are "regenerated by any install" and
    never committed, and `.gitignore` excludes both. `selftest` check [7]'s before/after
    snapshot skips them for that reason and for that reason only; it is proving the SOURCE tree
    is untouched, which it is.
  * The command line, per `note-for-claude` ("all tools need to pass a bug-report
    automatically (timestamped if an exception is thrown)"), appends one timestamped JSON line
    to the config's `bug_reports` path if it hits an UNEXPECTED exception — a defect in this
    tool. A `ConfigError` is designed behavior rather than a defect, so it NEVER files one.

HOW A ConfigError ACTUALLY SURFACES — the two paths differ, and saying so is the point
----------------------------------------------------------------------------------------
  * The config gate fires at IMPORT, which happens BEFORE `cli()` exists — `-m` and the console
    script both have to import this module to reach it. So `python3 -m coupler.updater
    <anything>` with an unresolvable config exits 1 with a Python TRACEBACK whose last line is
    the self-explaining `ConfigError`. That is not a tidy one-liner and this file does not
    claim it is; it is exactly what "throws rather than guessing a default" looks like when the
    throw precedes the argument parser, and it is what acceptance item (d) asks for. `selftest`
    check [1] measures that exact exit, in child interpreters.
  * A `ConfigError` raised while a command is already RUNNING is caught by `cli()`, which
    prints one self-explaining line to stderr, files no report, and exits 2. That path is the
    safety net, not the common case.
  * The interpreter still writes its usual `__pycache__` bytecode for any module it imports;
    that is CPython's import machinery rather than this code, and ticket #375 lists
    `__pycache__` among the build artifacts that are regenerated by any install and never
    committed.

RUNNING IT
----------
Every command below is executable as written FROM THE PACKAGE ROOT — the directory holding
`pyproject.toml`, one level above `coupler/`. The `-m` form is what makes them run without
installing anything: it puts the package root on the import path, so `coupler.updater`
resolves. Running the file by path (`python3 coupler/updater.py`) does NOT work uninstalled,
because Python would put `coupler/` on the import path instead of the package root and the
`coupler` package would not be importable; that invocation answers with one `UsageError` line
saying so rather than a traceback.

    python3 -m coupler.updater selftest       # the equivalence proof: [0]-[8], vs the ORIGINAL
    python3 -m coupler.updater install-check  # really runs pip, in both install layouts
    python3 -m coupler.updater show-config    # print the resolved config object and its source
    python3 -m coupler.updater emit-config    # print a config-object template
    python3 -m coupler.updater plan           # print the exact commands `run` would spawn
    python3 -m coupler.updater run            # THE UPDATER — pulls, reinstalls, restarts

Once installed (see INSTALLABLE), the console script runs from any directory:

    forge2-coupler-updater selftest

`run` is the updater proper, and `main()` is what launchd invokes. The original's
`python -m coupler.updater` with no argument ran the update check; that spelling is preserved
— with no subcommand this module runs `main()`, so an existing launchd plist keeps working
byte for byte. `selftest` check [8] proves that.

`plan` exists because `run` is destructive and this module is config-driven: it renders the
git, pip and launchctl command lines the CURRENT config produces, without spawning any of
them, so an operator can see what a config change did before it reinstalls anything.

INSTALLABLE (#200 requirement 3, acceptance item (c))
-----------------------------------------------------
This file is one module of the package that surrounds it, committed in full beside it. From
the package root:

    pip install -e .
    forge2-coupler-updater selftest

Unlike some siblings in this package, that claim is EXECUTED rather than asserted:
`install-check` runs `python3 -m pip install -e . --prefix <tmp>` and then imports
`coupler.updater` out of the result in a child interpreter, and also runs a NON-editable
`pip install . --target <tmp>` and imports it under `python3 -S` so no real site-packages can
answer for it. Both temporary trees are removed afterwards. The non-editable layout is the one
that matters most here: the registry walk-up passes nothing above
`site-packages/coupler/updater.py`, which is what `find_registry`'s `_installed_registry`
fallback exists for, and `install-check` proves both that it finds the shipped registry and
that removing it brings the config gate back.

A NOTE ON THIS PACKAGE'S `pyproject.toml`, WHICH THIS TICKET HAD TO CORRECT
---------------------------------------------------------------------------
`pyproject.toml` is generated by `congruency/tools/forge_package.py` (#410) from the modules
present, and its generator does not recurse into subdirectories: it declared only the
top-level package `code__code_invalid__coupler` mapped onto `.`, and NOT the `coupler` package
that this file, `__init__.py`, `_config.py`, `bridge.py` and `__main__.py` all live in. A
`pip install .` therefore shipped none of them, and `import coupler.updater` could not resolve
from an installed copy at all — which acceptance item (c) requires. `coupler` is declared
now, alongside the console entry point for this unit. The declaration is additive: every
previously declared package, entry point and package-data rule is still declared, so no
sibling unit loses anything. `install-check` is what proves the corrected declaration, in both
layouts.

Requires Python 3.10+, and says so here because this package's generated `requires-python` says
3.8: the original's `_remote_version() -> str | None` annotation is a PEP 604 union evaluated
at function definition time, so the module cannot even be imported on 3.9 or older. Preserving
that annotation is preserving the surface ticket #375 states, so the floor is the original's
floor. The generated `requires-python` is left alone because it is package-wide and the
siblings really do run on 3.8.
"""

import argparse
import ast
import hashlib
import json
import logging
import os
import subprocess
import sys
import traceback
import types
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────── configuration ───────────────────────────────
#
# Self-contained ON PURPOSE, following the pattern this package established (`coupler/bridge.py`
# #357, `coupler/tests/test_build.py` #355): a forge rewrite unit's deliverable is ONE module,
# and a sibling helper it depends on may not be present. `coupler/tests/test_bridge.py` (#393)
# imports `coupler.config`, which does not exist here, and is unimportable today as a result.
# This file has no such dependency and runs against the package as it actually is.

#: Environment variable naming a file that holds THIS unit's config object.
CONFIG_ENV = "COUPLER_UPDATER_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in
#: the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own. Check [6]'s "no hardcoded values" AST scan skips this assignment for
#: exactly that reason, and says so.
UNIT_PATH = ("forge2", "code__code-invalid__coupler", "coupler.updater")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code-invalid__coupler/coupler/updater"

#: This module's own dotted import name. It is `UNIT_PATH`'s last element by construction — a
#: unit's address inside the registry IS its dotted path within the package — so it is derived
#: rather than written twice and cannot drift from it. Used only to print an invocation a
#: reader can retype; `__name__` is "__main__" under `-m` and `__spec__` is None when this file
#: is run by path, so neither can answer this on its own.
DOTTED_NAME = UNIT_PATH[-1]

#: The installed package that ships `registry.json` as package data. `find_registry` falls back
#: to it so a NON-editable `pip install .` can still find the config: this module then lives at
#: `site-packages/coupler/updater.py` and the walk-up passes no registry at all.
PACKAGE_WITH_REGISTRY = "code__code_invalid__coupler"

#: The ticket this unit was rewritten under, recorded in bug reports.
TICKET = 375

#: The sibling unit `coupler/__init__.py` (#397) — this module's own package — and the env var
#: IT reads its config from. `install-check` needs both, and the reason is a fact about the
#: package rather than a setting of this unit: importing ANY module inside the `coupler` package
#: runs `coupler/__init__.py` FIRST, and that sibling gates on its own config object. Unlike
#: this module it has no installed-registry fallback (its `_config.find_registry` only walks
#: up), so from a NON-EDITABLE install it cannot resolve one and `import coupler.updater` dies
#: in the sibling before this module is reached. That gap is #397's, and ticket #375 "covers ONE
#: module — the one identified below — and nothing else", so this file changes nothing about it:
#: `install-check` reports it, then uses the sibling's OWN documented escape hatch — $COUPLER_
#: CONFIG — to get past it and prove THIS module's fallback. Derived from DOTTED_NAME rather
#: than spelled out, so it cannot drift from the package this module actually lives in.
SIBLING_PACKAGE = DOTTED_NAME.split(".")[0]
SIBLING_UNIT_PATH = UNIT_PATH[:-1] + (SIBLING_PACKAGE,)
SIBLING_CONFIG_ENV = "COUPLER_CONFIG"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and ticket #375's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.

    It is raised at IMPORT, before any command is spawned, so a config mistake can never be
    mistaken for a failed git fetch and reported as "no update available".
    """


class UsageError(RuntimeError):
    """Raised when this module was INVOKED in a way that cannot work — not a defect in it.

    Kept apart from every other exception for the same reason `ConfigError` is: the command
    line reports both as one self-explaining line and files NO bug report, because a bug report
    is supposed to mean "this tool is broken". The foreseeable case is running this file by
    path (`python3 coupler/updater.py`), which puts `coupler/` on the import path instead of
    the package root and so leaves the `coupler` package unimportable. That is a mistake the
    message can fix in one line; answering it with a traceback and a filed bug report would
    blame the tool for the invocation and put a false record in the sink.
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do this module throws `ConfigError` at import. Every
    value below is one the ORIGINAL hardcoded, so a config built from this template makes the
    updater behave exactly as the original's did — which is not a claim, it is what `selftest`
    check [2] measures against the original itself.

    Check [6]'s AST scan skips this function: it is the ONE place the original's values are
    allowed to appear as literals, because printing a template is what makes the values
    installable data rather than behavior. Check [6] also proves this template equals the
    section the shipped `registry.json` carries, so the printed template is the running config.
    """
    return {
        "repo_path": ".",
        "git_executable": "git",
        "remote": "origin",
        "branch": "stable",
        "describe_args": ["describe", "--tags", "--abbrev=0"],
        "fetch_args": ["fetch", "--tags"],
        "pull_args": ["pull", "--ff-only"],
        "pip_command": ["{python}", "-m", "pip"],
        "pip_install_args": ["install", "-e", ".", "-q"],
        "launchctl_path": "/bin/launchctl",
        "launchctl_kickstart_args": ["kickstart", "-k"],
        "kickstart_target_template": "gui/{uid}/{service}",
        "service": "com.coupler.server",
        "distribution": "coupler",
        "version_prefix": "v",
        "log_file": "~/Library/Logs/coupler-updater.log",
        "log_level": "INFO",
        "log_format": "%(asctime)s  %(levelname)s  %(message)s",
        "log_datefmt": "%Y-%m-%d %H:%M:%S",
        "logger_name": "coupler.updater",
        "labels": {
            "pull": "git pull",
            "install": "pip install",
        },
        "messages": {
            "update_check": "update check",
            "fetch_failed": "git fetch failed: %s",
            "no_remote_tag": "no remote tag yet: %s",
            "step_failed": "%s failed:\n%s",
            "step_ok": "%s ok",
            "up_to_date": "up to date (%s)",
            "update_available": "update available: %s → %s",
            "update_failed": "update failed — server not restarted",
            "updated_to": "updated to %s",
            "server_restarted": "server restarted",
            "kickstart_failed": "kickstart failed: %s",
        },
    }


def find_registry(start=None):
    """Return the path of the registry this unit should read, or None if there is none.

    Walks UP from `start` (default: this file's directory) looking for `REGISTRY_NAME`. If the
    walk reaches the filesystem root without finding one, falls back to the copy shipped as
    package data inside `PACKAGE_WITH_REGISTRY`, which is the only one a non-editable install
    has. An explicit `start` suppresses that fallback: a caller naming a directory to search is
    asking about THAT tree, and quietly answering with the installed package's registry instead
    would report a config the caller never pointed at.
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

    if start is not None:
        return None
    return _installed_registry()


def _installed_registry():
    """Return the registry shipped as package data in `PACKAGE_WITH_REGISTRY`, or None.

    `pyproject.toml` maps that package onto this package's ROOT directory and ships
    `registry.json` as its package data, so locating the package locates the registry. Import
    machinery answers this without importing the package, which matters: importing it is not
    free and this is called from the import of a module inside it.
    """
    try:
        import importlib.util

        spec = importlib.util.find_spec(PACKAGE_WITH_REGISTRY)
    except Exception:  # noqa: BLE001 — a missing/broken package is simply "no registry here"
        return None
    if spec is None:
        return None
    for location in list(getattr(spec, "submodule_search_locations", None) or []):
        candidate = os.path.join(location, REGISTRY_NAME)
        if os.path.isfile(candidate):
            return candidate
    return None


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
            "no config object for %s: %s is unset, no %s was found by walking up from %s, and "
            "the installed package %s ships none. Run `%s emit-config` for a template of the "
            "config object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))),
               PACKAGE_WITH_REGISTRY, _cli_name())
        )

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. "
                "Run `%s emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), _cli_name(),
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
    # section may state its own to override it. This is inheritance inside ONE config document,
    # not a guessed default — if neither states it, the key stays absent and the CLI files no
    # report.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


def require(section, key, where, types_):
    """Return `section[key]`, proving it is present and of the right type; else raise.

    Type-checking here rather than letting a bad value flow onward is deliberate. A non-string
    `launchctl_path` or a non-list `describe_args` reaching `subprocess.run` would raise deep
    inside a command spawn, where the traceback names subprocess rather than the config key an
    operator got wrong. A malformed config object is a config error, and it is raised as one,
    at import, naming the key.

    Args:
        section: the config object (or sub-object) to read.
        key: the key to require.
        where: human-readable description of the section, for the error message.
        types_: a type or tuple of types the value must be an instance of.

    Raises:
        ConfigError: if the key is absent or the value is of the wrong type.
    """
    if not isinstance(section, dict):
        raise ConfigError(
            "the config section %s for %s must be a JSON object, not %s"
            % (where, UNIT, type(section).__name__)
        )
    if key not in section:
        raise ConfigError(
            "the config section %s for %s is missing the required key %r. Run `%s emit-config` "
            "for a template." % (where, UNIT, key, _cli_name())
        )
    value = section[key]
    # `bool` is a subclass of `int`, so isinstance(True, int) is True. A `true` where a string
    # or a list belongs is a config mistake, and silently accepting it would let it flow into a
    # command line.
    wanted = types_ if isinstance(types_, tuple) else (types_,)
    if isinstance(value, bool) and bool not in wanted:
        raise ConfigError(
            "the config key %r in %s for %s must be %s, not a boolean"
            % (key, where, UNIT, _type_names(wanted))
        )
    if not isinstance(value, wanted):
        raise ConfigError(
            "the config key %r in %s for %s must be %s, not %s"
            % (key, where, UNIT, _type_names(wanted), type(value).__name__)
        )
    return value


def require_str_list(section, key, where):
    """Return `section[key]`, proving it is a list of strings; else raise ConfigError.

    Every one of these becomes part of a command line. A list with a non-string in it would
    reach `subprocess.run` and raise there, blaming subprocess for a config mistake, so the
    element type is proven here and the offending index is named.
    """
    value = require(section, key, where, list)
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigError(
                "the config key %r in %s for %s must be a list of strings, but element %d is "
                "%s" % (key, where, UNIT, index, type(item).__name__)
            )
    return list(value)


def _type_names(wanted):
    return " or ".join(t.__name__ for t in wanted)


def _cli_name():
    """Name an invocation of this tool that the reader can actually retype.

    The `-m` form, which is what works from a source checkout whether or not this package has
    been installed.
    """
    return "python3 -m " + DOTTED_NAME


def _log_level(name):
    """Translate a config log-level NAME into the integer `logging` uses.

    Raises:
        ConfigError: if the name is not one of logging's level names. `getattr` on the logging
            module would also answer `getLogger` and friends, so the value is proven to be an
            int and proven not to be a bool before it is accepted.
    """
    value = getattr(logging, name, None)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            "the config key 'log_level' for %s must name a logging level (CRITICAL, ERROR, "
            "WARNING, INFO or DEBUG), not %r" % (UNIT, name)
        )
    return value


def _resolve_path(value, base):
    """Resolve a config path against `base`, expanding a leading `~`.

    `base` is the directory holding the registry that supplied the value, never the working
    directory, so which directory you run from does not move the repo or the log file.
    """
    expanded = os.path.expanduser(value)
    if not os.path.isabs(expanded):
        expanded = os.path.join(base, expanded)
    return Path(os.path.abspath(expanded))


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


def active_base():
    """Return the directory that relative paths in the config resolve against."""
    if _ACTIVE is not None:
        return _ACTIVE[1]
    active_config()
    return _RESOLVED[1]


def active_source():
    """Describe where the config object in force came from."""
    if _ACTIVE is not None:
        return _ACTIVE[2]
    active_config()
    return _RESOLVED[2]


def configure(config, base=None, source="injected via configure()"):
    """Inject `config` as the config object for this process; return the previous state.

    `base` is the directory relative paths in `config` resolve against, and defaults to the
    current working directory. Pass `None` as `config` to drop the injection and go back to
    resolving from disk.

    Injecting a config does NOT rebind this module's globals: the original bound `REPO`, `PIP`
    and the rest once, at import, and that is preserved. `settings_from_config()` is the way to
    ask what some other config object would yield.
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


def reset_config():
    """Drop the injected config and the cached disk resolution; the next call re-resolves."""
    global _ACTIVE, _RESOLVED
    _ACTIVE = None
    _RESOLVED = None


def settings_from_config(config=None, base=None):
    """Read and validate a config object into this module's flattened settings.

    Args:
        config: a config object to read; omit it to use the config in force.
        base: the directory relative paths resolve against; omit it to use `active_base()`.

    Returns:
        A dict of validated settings — the values this module's globals are bound from.

    Raises:
        ConfigError: if there is no config object to be had, or a required key is missing or
            of the wrong type.
    """
    cfg = active_config() if config is None else config
    if not isinstance(cfg, dict):
        raise ConfigError("a config object must be a dict, not %s" % type(cfg).__name__)
    if base is None:
        base = active_base() if config is None else os.getcwd()

    labels = require(cfg, "labels", UNIT, dict)
    messages = require(cfg, "messages", UNIT, dict)
    labels_where = "%s -> labels" % UNIT
    messages_where = "%s -> messages" % UNIT

    settings = {
        "repo": _resolve_path(require(cfg, "repo_path", UNIT, str), base),
        "git_executable": require(cfg, "git_executable", UNIT, str),
        "remote": require(cfg, "remote", UNIT, str),
        "branch": require(cfg, "branch", UNIT, str),
        "describe_args": require_str_list(cfg, "describe_args", UNIT),
        "fetch_args": require_str_list(cfg, "fetch_args", UNIT),
        "pull_args": require_str_list(cfg, "pull_args", UNIT),
        "pip_command": require_str_list(cfg, "pip_command", UNIT),
        "pip_install_args": require_str_list(cfg, "pip_install_args", UNIT),
        "launchctl_path": require(cfg, "launchctl_path", UNIT, str),
        "launchctl_kickstart_args": require_str_list(cfg, "launchctl_kickstart_args", UNIT),
        "kickstart_target_template": require(cfg, "kickstart_target_template", UNIT, str),
        "service": require(cfg, "service", UNIT, str),
        "distribution": require(cfg, "distribution", UNIT, str),
        "version_prefix": require(cfg, "version_prefix", UNIT, str),
        "log_file": _resolve_path(require(cfg, "log_file", UNIT, str), base),
        "log_level": _log_level(require(cfg, "log_level", UNIT, str)),
        "log_format": require(cfg, "log_format", UNIT, str),
        "log_datefmt": require(cfg, "log_datefmt", UNIT, str),
        "logger_name": require(cfg, "logger_name", UNIT, str),
        "labels": {key: require(labels, key, labels_where, str)
                   for key in ("pull", "install")},
        "messages": {key: require(messages, key, messages_where, str)
                     for key in ("update_check", "fetch_failed", "no_remote_tag", "step_failed",
                                 "step_ok", "up_to_date", "update_available", "update_failed",
                                 "updated_to", "server_restarted", "kickstart_failed")},
    }
    return settings


# ─────────────────────────────── the module-level surface ───────────────────────────────
#
# Everything here reproduces what the original's module-level code left in this namespace, with
# the values it hardcoded now read from the config object. `settings_from_config()` raises
# ConfigError right here, at import, if this unit cannot see its config: acceptance item (d).
#
# These are module GLOBALS, and every function below reads them at CALL time, because the
# original's did and callers rebind them (`u.REPO = other`). Binding them into a closure or a
# frozen settings object at import would look tidier and would break those callers.

_SETTINGS = settings_from_config()

#: The git checkout every git and pip command runs in. The original computed
#: `Path(__file__).parent.parent`; the shipped `repo_path` of "." resolves against the registry's
#: own directory to exactly that same path, which `selftest` check [6] proves against the oracle.
REPO = _SETTINGS["repo"]

#: The interpreter pip is invoked through. `sys.executable`, as the original had it — this is
#: read off the running process, not hardcoded, so there is nothing here to configure.
PYTHON = sys.executable

#: The pip command prefix. The original hardcoded `[PYTHON, "-m", "pip"]`; the `{python}`
#: placeholder in the configured `pip_command` is filled with `PYTHON` to reproduce it.
PIP = [part.format(python=PYTHON) for part in _SETTINGS["pip_command"]]

#: The launchctl binary. The original hardcoded "/bin/launchctl".
LAUNCHCTL = _SETTINGS["launchctl_path"]

#: The launchd service label to kick. The original hardcoded "com.coupler.server".
SERVICE = _SETTINGS["service"]

#: The log file. The original hardcoded `Path.home() / "Library/Logs/coupler-updater.log"`.
LOG_FILE = _SETTINGS["log_file"]


def logging_config() -> dict:
    """Return the keyword arguments this unit hands to `logging.basicConfig`.

    The original passed these inline at module scope. They are a named function here so the
    configuration can be read back and compared to the original's — the import below calls it,
    so what this returns IS what configures logging and the two cannot drift apart.
    `selftest` check [8] compares this dict to the keywords the ORACLE passes.
    """
    return {
        "filename": str(LOG_FILE),
        "level": _SETTINGS["log_level"],
        "format": _SETTINGS["log_format"],
        "datefmt": _SETTINGS["log_datefmt"],
    }


# Opens (and creates) LOG_FILE and installs a handler on the ROOT logger, at import — the
# original's behavior, preserved. See SIDE EFFECTS. It is a no-op when the root logger already
# has handlers, which is `logging`'s own rule and was true of the original too.
logging.basicConfig(**logging_config())

#: This unit's logger. The original hardcoded the name "coupler.updater".
log = logging.getLogger(_SETTINGS["logger_name"])


def _git(args):
    """Build a git command line: the configured git executable followed by `args`."""
    return [_SETTINGS["git_executable"]] + list(args)


def _remote_ref():
    """The `<remote>/<branch>` ref `git describe` is pointed at. The original hardcoded
    "origin/stable"."""
    return "%s/%s" % (_SETTINGS["remote"], _SETTINGS["branch"])


def _strip_version_prefix(text: str) -> str:
    """Strip the configured version prefix off a tag, exactly as the original's `.lstrip("v")`.

    `str.lstrip` takes a SET OF CHARACTERS, not a prefix, so it removes EVERY leading character
    that appears in the configured prefix: `"vv2.0"` -> `"2.0"` and `"version9"` -> `"ersion9"`.
    That is the original's behavior and it is preserved, not repaired — `selftest` check [3]
    measures it against the oracle rather than arguing about it.
    """
    return text.lstrip(_SETTINGS["version_prefix"])


def _run(cmd: list, **kw) -> subprocess.CompletedProcess:
    """Run `cmd` in `REPO`, capturing its output as text.

    Reads `REPO` as a module global at call time, so rebinding `REPO` on this module redirects
    every subsequent command — as it did for the original.

    `kw` is forwarded to `subprocess.run`, and naming `cwd` in it raises TypeError for a
    duplicate keyword argument, because `cwd=REPO` is already passed. That is the original's
    behavior; the way to run somewhere else is to rebind `REPO`.
    """
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO, **kw)


def _current_version() -> str:
    """Version the running package reports (from git describe or importlib).

    Runs `git describe --tags --abbrev=0` in `REPO`; on success returns its output with the
    configured version prefix stripped. On failure falls back to `importlib.metadata.version`
    for the configured distribution.

    That fallback is UNGUARDED, exactly as the original left it: when there is no local tag AND
    the distribution is not installed, `PackageNotFoundError` propagates out of this function
    and out of `main()`. `selftest` check [3] proves the raise against the oracle.
    """
    r = _run(_git(_SETTINGS["describe_args"]))
    if r.returncode == 0:
        return _strip_version_prefix(r.stdout.strip())
    # fall back to importlib if no local tag
    from importlib.metadata import version
    return version(_SETTINGS["distribution"])


def _remote_version() -> str | None:
    """Latest tag reachable from the configured remote branch after a fetch.

    Returns the tag with the configured version prefix stripped, or None if either the fetch or
    the describe fails — the fetch failure is logged at WARNING and the missing tag at DEBUG,
    which is the original's asymmetry and is preserved.
    """
    r = _run(_git(_SETTINGS["fetch_args"] + [_SETTINGS["remote"], _SETTINGS["branch"]]))
    if r.returncode != 0:
        log.warning(_SETTINGS["messages"]["fetch_failed"], r.stderr.strip())
        return None
    r = _run(_git(_SETTINGS["describe_args"] + [_remote_ref()]))
    if r.returncode != 0:
        log.debug(_SETTINGS["messages"]["no_remote_tag"], r.stderr.strip())
        return None
    return _strip_version_prefix(r.stdout.strip())


def _pull_and_install() -> bool:
    """Fast-forward the checkout and reinstall it; return whether both steps succeeded.

    Returns False at the FIRST failing step, so a failed pull means pip is never invoked — the
    original's short-circuit, preserved. Reads `PIP` as a module global at call time.
    """
    for cmd, label in [
        (_git(_SETTINGS["pull_args"] + [_SETTINGS["remote"], _SETTINGS["branch"]]),
         _SETTINGS["labels"]["pull"]),
        (PIP + _SETTINGS["pip_install_args"], _SETTINGS["labels"]["install"]),
    ]:
        r = _run(cmd)
        if r.returncode != 0:
            log.error(_SETTINGS["messages"]["step_failed"], label, r.stderr.strip())
            return False
        log.info(_SETTINGS["messages"]["step_ok"], label)
    return True


def _restart_server():
    """Kick the launchd service so the server restarts. Returns None.

    Calls `subprocess.run` DIRECTLY rather than `_run`, so — alone among this module's commands
    — the kickstart runs with NO `cwd` and inherits the process's working directory. That is
    the original's shape, preserved rather than repaired; `selftest` check [3] pins it against
    the oracle. Reads `LAUNCHCTL` and `SERVICE` as module globals at call time.
    """
    uid = os.getuid()
    r = subprocess.run(
        [LAUNCHCTL] + list(_SETTINGS["launchctl_kickstart_args"])
        + [_SETTINGS["kickstart_target_template"].format(uid=uid, service=SERVICE)],
        capture_output=True, text=True,
    )
    if r.returncode == 0:
        log.info(_SETTINGS["messages"]["server_restarted"])
    else:
        log.error(_SETTINGS["messages"]["kickstart_failed"], r.stderr.strip())


def main():
    """Check for an update and, if there is one, pull, reinstall and restart. Returns None.

    This is what launchd invokes on its timer. The order is the original's and is load-bearing:
    `_remote_version()` runs FIRST, so a failed fetch returns before `_current_version()` is
    ever called and the `importlib.metadata` fallback is never reached on an offline run.
    """
    log.debug(_SETTINGS["messages"]["update_check"])

    remote = _remote_version()
    if remote is None:
        return

    current = _current_version()
    if current == remote:
        log.debug(_SETTINGS["messages"]["up_to_date"], current)
        return

    log.info(_SETTINGS["messages"]["update_available"], current, remote)

    if not _pull_and_install():
        log.error(_SETTINGS["messages"]["update_failed"])
        return

    log.info(_SETTINGS["messages"]["updated_to"], remote)
    _restart_server()


def plan():
    """Render the command lines the CURRENT config produces, spawning none of them.

    `run` is destructive — it reinstalls a package and restarts a service — and this module is
    config-driven, so an operator needs to be able to see what a config change did before it
    takes effect. Every list below is built by the same expression the corresponding function
    uses, so what is printed is what would be spawned.
    """
    uid = os.getuid()
    return {
        "repo (cwd for every git/pip command)": str(REPO),
        "describe local": _git(_SETTINGS["describe_args"]),
        "fetch": _git(_SETTINGS["fetch_args"] + [_SETTINGS["remote"], _SETTINGS["branch"]]),
        "describe remote": _git(_SETTINGS["describe_args"] + [_remote_ref()]),
        "pull": _git(_SETTINGS["pull_args"] + [_SETTINGS["remote"], _SETTINGS["branch"]]),
        "install": PIP + _SETTINGS["pip_install_args"],
        "restart (NOTE: no cwd — the original ran launchctl outside REPO)":
            [LAUNCHCTL] + list(_SETTINGS["launchctl_kickstart_args"])
            + [_SETTINGS["kickstart_target_template"].format(uid=uid, service=SERVICE)],
        "log file": str(LOG_FILE),
    }


# ─────────────────────────────── the original, embedded ───────────────────────────────
#
# Ticket #375 embeds this module's own bytes (#346) and names them "the authoritative copy and
# the behavior-preserving basis". They are reproduced here VERBATIM so the proof below can run
# them: `selftest` check [0] hashes this string exactly as git hashes a blob and compares the
# digest to the blob sha1 the ticket records, which is what makes the oracle trustworthy
# without any forge access.
#
# A RAW string is required, not decoration: the source contains `"%s failed:\n%s"`, and in a
# cooked string that `\n` would become a real newline and change the bytes — the hash in check
# [0] would fail, which is exactly the point of hashing it.

ORIGINAL_SOURCE = r'''#!/usr/bin/env python3
"""
coupler/updater.py — pull and reinstall when a new git tag lands on stable.

Run by launchd on a timer. Compares the locally installed version against the
latest tag reachable from origin/stable. If they differ, pulls, reinstalls,
and kicks the server. The bridge reconnects automatically — no downtime.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

REPO      = Path(__file__).parent.parent          # ~/code/coupler
PYTHON    = sys.executable
PIP       = [PYTHON, "-m", "pip"]
LAUNCHCTL = "/bin/launchctl"
SERVICE   = "com.coupler.server"
LOG_FILE  = Path.home() / "Library/Logs/coupler-updater.log"

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("coupler.updater")


def _run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO, **kw)


def _current_version() -> str:
    """Version the running package reports (from git describe or importlib)."""
    r = _run(["git", "describe", "--tags", "--abbrev=0"])
    if r.returncode == 0:
        return r.stdout.strip().lstrip("v")
    # fall back to importlib if no local tag
    from importlib.metadata import version
    return version("coupler")


def _remote_version() -> str | None:
    """Latest tag reachable from origin/stable after a fetch."""
    r = _run(["git", "fetch", "--tags", "origin", "stable"])
    if r.returncode != 0:
        log.warning("git fetch failed: %s", r.stderr.strip())
        return None
    r = _run(["git", "describe", "--tags", "--abbrev=0", "origin/stable"])
    if r.returncode != 0:
        log.debug("no remote tag yet: %s", r.stderr.strip())
        return None
    return r.stdout.strip().lstrip("v")


def _pull_and_install() -> bool:
    for cmd, label in [
        (["git", "pull", "--ff-only", "origin", "stable"], "git pull"),
        (PIP + ["install", "-e", ".", "-q"],               "pip install"),
    ]:
        r = _run(cmd)
        if r.returncode != 0:
            log.error("%s failed:\n%s", label, r.stderr.strip())
            return False
        log.info("%s ok", label)
    return True


def _restart_server():
    uid = os.getuid()
    r = subprocess.run(
        [LAUNCHCTL, "kickstart", "-k", f"gui/{uid}/{SERVICE}"],
        capture_output=True, text=True,
    )
    if r.returncode == 0:
        log.info("server restarted")
    else:
        log.error("kickstart failed: %s", r.stderr.strip())


def main():
    log.debug("update check")

    remote = _remote_version()
    if remote is None:
        return

    current = _current_version()
    if current == remote:
        log.debug("up to date (%s)", current)
        return

    log.info("update available: %s → %s", current, remote)

    if not _pull_and_install():
        log.error("update failed — server not restarted")
        return

    log.info("updated to %s", remote)
    _restart_server()


if __name__ == "__main__":
    main()
'''

#: The blob sha1 ticket #375 records for the canonical source, and the size it states. Check
#: [0] proves ORIGINAL_SOURCE against both.
ORIGINAL_BLOB_SHA1 = "3800ae29cb412ff82b508a1493649e900074fbe0"
ORIGINAL_SIZE = 3106


def _git_blob_sha1(data: bytes) -> str:
    """Hash `data` the way git hashes a blob: sha1 over `blob <len>\\0` + the bytes.

    This is git's object-id rule, so the digest is directly comparable to the blob sha1 the
    ticket records — no forge access required to check that the embedded copy is genuine.
    """
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# ─────────────────────────────── the equivalence tables ───────────────────────────────

#: The exemplars this rewrite must reproduce. Ticket #375 captured none (criteria_miner refuses
#: world-touching and no-arg functions, "and nothing here qualified"), so this table is the
#: hand-written equivalence basis the ticket asks for in its place.
#:
#: Each entry is (label, what is staged, the property it pins down). Every one is RUN against
#: the ORIGINAL and against this rewrite by `selftest` check [2] and the observations compared,
#: so the expected values are taken from the original as it runs rather than from this table.
EXEMPLARS = [
    ("_current_version reads the local tag",
     "git describe exits 0 printing 'v1.4.2\\n'",
     "returns '1.4.2' — the output stripped of whitespace and of the version prefix — having "
     "run `git describe --tags --abbrev=0` in REPO"),
    ("_remote_version reads the remote tag",
     "git fetch exits 0; git describe origin/stable exits 0 printing 'v1.5.0\\n'",
     "returns '1.5.0', having run the fetch FIRST and then the describe against origin/stable"),
    ("_remote_version when the fetch fails",
     "git fetch exits 1 with stderr 'fatal: unable to access'",
     "returns None, logs one WARNING naming the stderr, and never runs the describe"),
    ("_pull_and_install when both steps succeed",
     "git pull exits 0; pip install exits 0",
     "returns True, having run `git pull --ff-only origin stable` then `PIP install -e . -q`, "
     "logging one INFO per step"),
    ("_restart_server when the kickstart succeeds",
     "launchctl exits 0, os.getuid() is 501",
     "runs `/bin/launchctl kickstart -k gui/501/com.coupler.server` and logs one INFO"),
    ("main() on the full update path",
     "remote tag 1.5.0, local tag 1.4.2, pull/install/kickstart all exit 0",
     "runs fetch, describe-remote, describe-local, pull, install, kickstart — in that order — "
     "and logs the update-available and updated-to lines"),
]

#: Edge cases the exemplars cannot reach on their own. #375 asks for "the edge cases you add
#: for what sampling cannot reach", and these are they: each pins down a property the exemplars
#: leave free, which a wrong updater could violate while still reproducing all six. Every one is
#: likewise run differentially against the ORIGINAL.
#:
#: Each entry is (label, why the exemplars cannot reach it).
EDGE_CASES = [
    ("every git/pip command runs with cwd=REPO",
     "the exemplars check return values, not where the command ran; an updater that pulled in "
     "the wrong directory would reproduce every one of them"),
    ("_restart_server runs launchctl with NO cwd, unlike every other command",
     "no exemplar inspects the kickstart's kwargs; routing it through _run would look like a "
     "tidy-up and would silently change where launchctl runs"),
    ("the version prefix is lstrip'd, so EVERY leading 'v' goes, not one prefix",
     "exemplar 1's 'v1.4.2' has exactly one leading v, so it cannot tell `lstrip('v')` from "
     "`removeprefix('v')`; 'vv2.0' can"),
    ("a tag that merely STARTS with a prefix character is mangled the same way",
     "'version9' -> 'ersion9' is the same lstrip quirk seen from the other side; an updater "
     "that 'fixed' it to removeprefix would still pass the 'vv2.0' case if it stripped twice"),
    ("_current_version falls back to importlib.metadata when git describe fails",
     "exemplar 1 only exercises the rc==0 path; the fallback is a whole second source"),
    ("that fallback is UNGUARDED — PackageNotFoundError propagates out",
     "nothing else distinguishes the original's bare fallback from a guarded one that would "
     "return a placeholder version and let main() 'update' to nothing"),
    ("_remote_version returns None and logs at DEBUG when only the describe fails",
     "exemplar 3 fails the FETCH, which is the WARNING branch; this is the other branch and "
     "the other level"),
    ("_pull_and_install returns False on a failed pull and never invokes pip",
     "exemplar 4 succeeds at both steps, so it cannot see the short-circuit; an updater that "
     "ran pip anyway would reinstall an un-pulled checkout"),
    ("_pull_and_install returns False on a failed install, after the pull ran",
     "the pull-failure case cannot distinguish 'stops at step 1' from 'stops at any failure'"),
    ("main() returns early when _remote_version is None, WITHOUT calling _current_version",
     "the ordering is invisible on the happy path; an updater that read the local version "
     "first would reproduce exemplar 6 exactly and still behave differently offline"),
    ("main() logs 'up to date' and restarts nothing when the versions match",
     "exemplar 6 is the differing-versions path; the equal path is the common one in "
     "production and touches no service"),
    ("main() does NOT restart the server when _pull_and_install fails",
     "exemplar 6 has every step succeed; restarting after a failed install is the worst "
     "outcome this module can produce and no exemplar can see it"),
    ("_run forwards **kw to subprocess.run, and a duplicate cwd raises TypeError",
     "no exemplar passes **kw at all; the signature is surface and the duplicate-keyword "
     "behavior is what it implies"),
    ("REPO, PIP, LAUNCHCTL and SERVICE are read at CALL time, so rebinding them takes effect",
     "the exemplars never rebind a global; the differential harness rebinds all four on BOTH "
     "modules, so every scenario is also this test"),
]


# ─────────────────────────────── the differential harness ───────────────────────────────

class _SubprocessShim:
    """A recording stand-in for the `subprocess` module, scripted with results to return.

    Installed as `module.subprocess` on the ORIGINAL and on this module identically, which is
    what makes the comparison fair rather than staged: both call `subprocess.run(...)`, so both
    reach this. Records every call, so "the rewrite spawns what the original spawns" becomes a
    comparison of two lists rather than an assertion. Spawns nothing.
    """

    def __init__(self, results):
        #: Each item is a (returncode, stdout, stderr) triple, consumed in order.
        self.results = list(results)
        self.calls = []
        self.CompletedProcess = subprocess.CompletedProcess

    def run(self, cmd, **kw):
        self.calls.append((list(cmd), dict(kw)))
        if not self.results:
            raise AssertionError("the scenario ran more commands than it scripted: %r" % (cmd,))
        returncode, stdout, stderr = self.results.pop(0)
        return subprocess.CompletedProcess(list(cmd), returncode, stdout, stderr)

    def __getattr__(self, name):
        # Anything not overridden is the real subprocess module's — nothing under test reaches
        # it, but proxying keeps this a stand-in rather than a trap.
        return getattr(subprocess, name)


class _OsShim:
    """A stand-in for `os` that pins `getuid`, proxying everything else to the real module.

    `_restart_server` puts the uid in the launchctl target, so an unpinned uid would make the
    differential compare two host-dependent strings and pass for the wrong reason.
    """

    def __init__(self, uid):
        self._uid = uid

    def getuid(self):
        return self._uid

    def __getattr__(self, name):
        return getattr(os, name)


class _LogShim:
    """A recording stand-in for this module's `log`.

    Records (level, template, args) per call rather than formatted text, because the TEMPLATE
    is what the original hardcoded and this module reads from config — comparing the rendered
    string would let a wrong template pass whenever its arguments happened to render alike.
    """

    def __init__(self):
        self.records = []

    def _record(self, level):
        def emit(template, *args):
            self.records.append((level, template, args))
        return emit

    def __getattr__(self, name):
        if name in ("debug", "info", "warning", "error", "critical"):
            return self._record(name)
        raise AttributeError(name)


class _LoggingShim:
    """A stand-in for the `logging` module whose `basicConfig` records and does nothing.

    Installed in `sys.modules` for the duration of the ORACLE's exec. Two reasons, both
    load-bearing:

      * the original's module-level `logging.basicConfig(filename=...)` OPENS its log file, so
        exec'ing the oracle would create `~/Library/Logs/coupler-updater.log` and install a
        handler on the root logger of the process running the selftest. Recording instead of
        doing keeps the oracle inert.
      * the recorded keywords ARE the comparison: check [8] compares them to this module's
        `logging_config()`, which is how "the config reproduces the original's logging setup"
        is measured rather than argued.

    Everything else proxies to the real `logging`, so `logging.INFO` and `logging.getLogger`
    answer normally.
    """

    def __init__(self):
        self.basic_config_calls = []

    def basicConfig(self, **kw):  # noqa: N802 — this mirrors logging's own spelling
        self.basic_config_calls.append(dict(kw))

    def __getattr__(self, name):
        return getattr(logging, name)


def load_original(home=None):
    """Execute `ORIGINAL_SOURCE` and return `(module, logging_shim)` — the differential's oracle.

    Nothing is written to disk: the source is compiled from the embedded string, and the
    `logging` shim installed for the duration of the exec makes the original's module-level
    `basicConfig` inert, so the oracle creates no log file and leaves the root logger alone.

    Args:
        home: value to stage in `$HOME` for the duration of the exec, so the original's
            `Path.home() / "Library/Logs/..."` resolves somewhere known. `Path.home()` reads
            `$HOME`, so this is what makes `LOG_FILE` comparable. None leaves it alone.

    Returns:
        A `(module, logging_shim)` pair. The shim's `basic_config_calls` holds the keywords the
        original passed to `logging.basicConfig`.
    """
    shim = _LoggingShim()
    saved_logging = sys.modules.get("logging")
    saved_home = os.environ.get("HOME")
    try:
        sys.modules["logging"] = shim
        if home is not None:
            os.environ["HOME"] = home
        module = types.ModuleType("original_updater")
        # The original computes REPO as __file__'s grandparent, so the staged path decides it.
        module.__file__ = os.path.abspath(__file__)
        exec(compile(ORIGINAL_SOURCE, "<ORIGINAL_SOURCE embedded in %s>" % DOTTED_NAME, "exec"),
             module.__dict__)
        return module, shim
    finally:
        if saved_logging is None:
            sys.modules.pop("logging", None)
        else:
            sys.modules["logging"] = saved_logging
        if saved_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = saved_home


def _this_module():
    """This module as an object. `__name__` is "__main__" under `-m`, so it is looked up rather
    than imported — importing `coupler.updater` here would make a SECOND module object and the
    differential would then stage one and measure the other."""
    return sys.modules[__name__]


#: The globals the harness stages identically on the oracle and on this module. Staging all
#: four is itself the last EDGE_CASE: it only takes effect if both modules read them at CALL
#: time, which is the surface property callers depend on.
_STAGED_GLOBALS = ("REPO", "PIP", "LAUNCHCTL", "SERVICE", "subprocess", "os", "log")


def observe(module, call, results, uid=501, repo=None, pip=None, launchctl=None, service=None):
    """Run one scenario against `module` and return what it did, comparably.

    Stages the same globals on whichever module is passed — the oracle or this one — so the
    two runs differ only in the code under test. Every stand-in is removed afterwards, whatever
    happens, and check [5] proves that.

    Args:
        module: the oracle or this module.
        call: a callable taking the module and returning a value — the scenario proper.
        results: the (returncode, stdout, stderr) triples `subprocess.run` returns, in order.
        uid: what `os.getuid()` answers.
        repo, pip, launchctl, service: values to stage on the module's globals.

    Returns:
        A dict of (value, calls, log, exc) — the whole observable outcome of the run.
    """
    shim = _SubprocessShim(results)
    logger = _LogShim()
    saved = {name: getattr(module, name) for name in _STAGED_GLOBALS}
    try:
        module.subprocess = shim
        module.os = _OsShim(uid)
        module.log = logger
        module.REPO = repo if repo is not None else Path("/staged/repo")
        module.PIP = list(pip) if pip is not None else ["/staged/python", "-m", "pip"]
        module.LAUNCHCTL = launchctl if launchctl is not None else "/staged/launchctl"
        module.SERVICE = service if service is not None else "staged.service"
        try:
            value, exc = call(module), None
        except BaseException as error:  # noqa: BLE001 — the raise IS the observation
            value, exc = None, "%s: %s" % (type(error).__name__, error)
    finally:
        for name, original in saved.items():
            setattr(module, name, original)
    return {
        "value": _comparable_value(value),
        "calls": [(cmd, _comparable_kwargs(kw)) for cmd, kw in shim.calls],
        "log": logger.records,
        "exc": exc,
    }


def _comparable_value(value):
    """Render a returned value so two structurally identical results compare equal.

    `subprocess.CompletedProcess` defines no `__eq__`, so it falls back to identity — and the
    oracle and the rewrite necessarily return DIFFERENT objects. Comparing them directly would
    report a difference that is not one, on the single scenario (`_run`) that returns one.
    Comparing field by field is STRICTER than identity, not looser: every attribute the
    original's return value carries has to match.
    """
    if isinstance(value, subprocess.CompletedProcess):
        return ("CompletedProcess", list(value.args), value.returncode, value.stdout,
                value.stderr)
    return value


def _comparable_kwargs(kw):
    """Render `subprocess.run` kwargs comparably: `cwd` as a string, everything else as is.

    `cwd` arrives as a `pathlib.Path` from both modules; `str` keeps the comparison exact while
    making a mismatch readable in the FAIL line. The KEYS are preserved, so `cwd` being absent
    from the kickstart — the asymmetry EDGE_CASES pins — still shows up as a difference.
    """
    return {key: (str(value) if key == "cwd" else value) for key, value in sorted(kw.items())}


# The scenarios. Each is (label, call, results, extra kwargs for observe). Written once and run
# against both modules, so there is no way for the oracle and the rewrite to be given different
# work — which a hand-written expectation table could not promise.
_OK = (0, "", "")


def _scenarios():
    """Return the (label, call, results, kwargs) scenarios checks [2] and [3] run.

    A function rather than a constant because the calls close over nothing and the results are
    consumed in place — building them fresh per run keeps two runs from sharing a scripted list.
    """
    repo = Path("/staged/repo")
    common = {"repo": repo, "pip": ["/staged/python", "-m", "pip"],
              "launchctl": "/staged/launchctl", "service": "staged.service"}

    exemplars = [
        ("_current_version reads the local tag",
         lambda m: m._current_version(), [(0, "v1.4.2\n", "")], common),
        ("_remote_version reads the remote tag",
         lambda m: m._remote_version(), [_OK, (0, "v1.5.0\n", "")], common),
        ("_remote_version when the fetch fails",
         lambda m: m._remote_version(), [(1, "", "fatal: unable to access\n")], common),
        ("_pull_and_install when both steps succeed",
         lambda m: m._pull_and_install(), [_OK, _OK], common),
        ("_restart_server when the kickstart succeeds",
         lambda m: m._restart_server(), [_OK], common),
        ("main() on the full update path",
         lambda m: m.main(),
         [_OK, (0, "v1.5.0\n", ""), (0, "v1.4.2\n", ""), _OK, _OK, _OK], common),
    ]

    edges = [
        ("every git/pip command runs with cwd=REPO",
         lambda m: m._pull_and_install(), [_OK, _OK], common),
        ("_restart_server runs launchctl with NO cwd",
         lambda m: m._restart_server(), [_OK], common),
        ("the version prefix is lstrip'd — 'vv2.0' loses BOTH leading v's",
         lambda m: m._current_version(), [(0, "vv2.0\n", "")], common),
        ("a tag starting with a prefix char is mangled — 'version9' -> 'ersion9'",
         lambda m: m._current_version(), [(0, "version9\n", "")], common),
        ("_current_version falls back to importlib when git describe fails",
         lambda m: m._current_version(), [(1, "", "fatal: no names found\n")], common),
        ("_remote_version returns None at DEBUG when only the describe fails",
         lambda m: m._remote_version(), [_OK, (1, "", "fatal: no names found\n")], common),
        ("_pull_and_install returns False on a failed pull and never invokes pip",
         lambda m: m._pull_and_install(), [(1, "", "CONFLICT\n")], common),
        ("_pull_and_install returns False on a failed install, after the pull ran",
         lambda m: m._pull_and_install(), [_OK, (1, "", "ERROR: no setup.py\n")], common),
        ("main() returns early when the fetch fails, never reading the local version",
         lambda m: m.main(), [(1, "", "fatal: unable to access\n")], common),
        ("main() logs 'up to date' and restarts nothing when the versions match",
         lambda m: m.main(), [_OK, (0, "v1.4.2\n", ""), (0, "v1.4.2\n", "")], common),
        ("main() does NOT restart the server when the install fails",
         lambda m: m.main(),
         [_OK, (0, "v1.5.0\n", ""), (0, "v1.4.2\n", ""), _OK, (1, "", "ERROR\n")], common),
        ("_run forwards **kw to subprocess.run",
         lambda m: m._run(["git", "status"], check=False), [_OK], common),
        ("_run with a duplicate cwd raises TypeError",
         lambda m: m._run(["git", "status"], cwd="/elsewhere"), [], common),
        ("rebinding REPO/PIP/LAUNCHCTL/SERVICE redirects the next call",
         lambda m: m._pull_and_install(), [_OK, _OK],
         {"repo": Path("/other/repo"), "pip": ["/other/python", "-m", "pip3"],
          "launchctl": "/other/launchctl", "service": "other.service"}),
        ("_restart_server logs an ERROR when the kickstart fails",
         lambda m: m._restart_server(), [(1, "", "Could not find service\n")], common),
    ]
    return exemplars, edges


# ─────────────────────────────── the selftest ───────────────────────────────

def selftest(stream=None):
    """Prove this rewrite against ticket #375's acceptance items (a), (b) and (d).

    Runs every scenario against the EMBEDDED ORIGINAL and against this module, under
    identically staged conditions, and compares the observations field by field. Builds its own
    config objects in memory where it needs to, writes nothing outside a temporary directory it
    removes, spawns no git/pip/launchctl, and leaves no configuration behind. Returns the number
    of failures.

    Checks, in order:
      0. the oracle is genuine — ORIGINAL_SOURCE hashes to the blob sha1 the ticket records;
      1. the config gate — this module throws ConfigError, and binds nothing, without a config;
      2. the exemplars — differential against the original;
      3. the edge cases the exemplars cannot reach — differential against the original;
      4. the callable surface — the names, parameters and annotations the ticket states;
      5. no side effects — subprocess, os and log are the real ones again afterwards;
      6. control-config'd — the template is the shipped registry, no value survives as a
         literal, and REPO/LOG_FILE match what the ORIGINAL's own expressions compute;
      7. no files — this package's tree is unchanged by the whole run;
      8. the module-level surface — logging setup, leaked names, and the no-argument spelling.
    """
    out = stream or sys.stdout
    failures = []
    checks = [0]

    def check(ok, label):
        checks[0] += 1
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    tree_before = _package_tree()

    print("\n[0] the oracle is genuine — the embedded original IS the forge blob", file=out)
    raw = ORIGINAL_SOURCE.encode("utf-8")
    digest = _git_blob_sha1(raw)
    check(len(raw) == ORIGINAL_SIZE,
          "ORIGINAL_SOURCE is %d bytes, the size ticket #375 states (%d)"
          % (len(raw), ORIGINAL_SIZE))
    check(digest == ORIGINAL_BLOB_SHA1,
          "ORIGINAL_SOURCE hashes to the blob sha1 ticket #375 records (%s)" % digest)
    if digest != ORIGINAL_BLOB_SHA1:
        print("  ABORT — the oracle is not the forge's module; every check below would be "
              "worthless.", file=out)
        return len(failures)

    original, oracle_logging = load_original(home=os.path.expanduser("~"))
    check(oracle_logging.basic_config_calls != [],
          "the oracle executes, and its module-level logging.basicConfig was captured inert "
          "(no log file created, root logger untouched)")

    print("\n[1] the config gate — no config object, no import (acceptance (d))", file=out)
    _selftest_gate(check, out)

    print("\n[2] the exemplars — this module vs the ORIGINAL, same staged conditions", file=out)
    exemplars, edges = _scenarios()
    _differential(check, out, original, exemplars)

    print("\n[3] the edge cases the exemplars cannot reach — likewise differential", file=out)
    _, edges = _scenarios()
    _differential(check, out, original, edges)

    print("\n[4] the callable surface ticket #375 states (acceptance (b))", file=out)
    _selftest_surface(check, original)

    print("\n[5] no side effects — the stand-ins are gone", file=out)
    me = _this_module()
    check(me.subprocess is subprocess, "subprocess is the real module again")
    check(me.os is os, "os is the real module again")
    check(isinstance(me.log, logging.Logger), "log is the real logging.Logger again")
    check(me.REPO == _SETTINGS["repo"] and me.PIP == [p.format(python=PYTHON)
                                                      for p in _SETTINGS["pip_command"]],
          "REPO and PIP are their configured values again")

    print("\n[6] control-config'd — nothing is hardcoded (acceptance (d))", file=out)
    _selftest_config_driven(check, out, original)

    print("\n[7] no files — this package's tree is unchanged by the whole run", file=out)
    tree_after = _package_tree()
    added = sorted(set(tree_after) - set(tree_before))
    removed = sorted(set(tree_before) - set(tree_after))
    check(not added and not removed,
          "this package's tree is byte-identical after the run (added %r, removed %r)"
          % (added, removed))

    print("\n[8] the module-level surface — logging, leaked names, the default spelling", file=out)
    _selftest_module_surface(check, original, oracle_logging)

    print("\n%s — %d checks, %d failure(s)"
          % ("PASS" if not failures else "FAIL", checks[0], len(failures)), file=out)
    for failure in failures:
        print("  FAILED: %s" % failure, file=out)
    print("  config source: %s" % _describe_source(), file=out)
    return len(failures)


def _differential(check, out, original, scenarios):
    """Run each scenario against the ORACLE and against this module and compare the results."""
    me = _this_module()
    for label, call, results, kwargs in scenarios:
        want = observe(original, call, list(results), **kwargs)
        got = observe(me, call, list(results), **kwargs)
        ok = want == got
        check(ok, label)
        if not ok:
            print("      original: %r" % (want,), file=out)
            print("      rewrite : %r" % (got,), file=out)
        else:
            # Print what the ORACLE did, so the reader sees the behavior that was matched
            # rather than taking "PASS" on faith.
            print("      original == rewrite: value=%r calls=%r log=%r exc=%r"
                  % (want["value"], want["calls"], want["log"], want["exc"]), file=out)


def _selftest_gate(check, out):
    """Check [1]: with an unresolvable config, importing this module throws ConfigError.

    Proven in CHILD interpreters, because this module is already imported in this one and its
    globals are already bound — asking the live module to prove what it does at import would
    prove nothing. The child points `COUPLER_UPDATER_CONFIG` at a file that does not exist:
    that source outranks the walk-up AND the installed-package fallback, so the gate is staged
    the same way whether or not a registry sits above this module — and this package SHIPS one,
    so a bare import would otherwise succeed and prove nothing.

    Each child also points `$HOME` at the temporary directory, so a child that DOES import
    creates its log file there and not in the real home.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as isolated:
        logs = os.path.join(isolated, "Library", "Logs")
        os.makedirs(logs, exist_ok=True)
        env = dict(os.environ)
        env["HOME"] = isolated
        env["PYTHONPATH"] = _package_root() + os.pathsep + env.get("PYTHONPATH", "")
        env[CONFIG_ENV] = os.path.join(isolated, "no-such-config.json")

        proc = subprocess.run([sys.executable, "-c", "import %s" % DOTTED_NAME],
                              env=env, capture_output=True, text=True, cwd=isolated)
        check(proc.returncode != 0 and "ConfigError" in proc.stderr,
              "`import %s` with an unresolvable config raises ConfigError and does NOT guess a "
              "default (rc=%d, stderr tail: %r)"
              % (DOTTED_NAME, proc.returncode, proc.stderr.strip().splitlines()[-1:]))
        for guessed in ("/bin/launchctl", "com.coupler.server"):
            check(guessed not in proc.stderr,
                  "the ConfigError names no %r — the gate throws rather than falling back to "
                  "the original's value" % guessed)

        # The gate as an OPERATOR meets it. `-m` imports this module before `cli()` exists, so
        # the throw precedes the argument parser and surfaces as a traceback, exiting 1 — NOT
        # as cli()'s one-line/exit-2 path. The module docstring says exactly that under HOW A
        # ConfigError ACTUALLY SURFACES; this measures it, so the claim cannot drift from the
        # behavior.
        proc = subprocess.run([sys.executable, "-m", DOTTED_NAME, "plan"],
                              env=env, capture_output=True, text=True, cwd=isolated)
        tail = (proc.stderr.strip().splitlines() or [""])[-1]
        check(proc.returncode == 1 and "Traceback" in proc.stderr and "ConfigError:" in tail,
              "`%s plan` with no config exits 1 with a traceback whose LAST line is the "
              "self-explaining ConfigError — as documented, rather than the tidy one-liner it "
              "would be wrong to promise (rc=%d, last line: %r)"
              % (_cli_name(), proc.returncode, tail))

        # And with a config, the SAME import succeeds — so check [1] measures the gate, not a
        # module that cannot import at all.
        template = config_template()
        template["repo_path"] = isolated
        template["log_file"] = os.path.join(logs, "u.log")
        config_path = os.path.join(isolated, "config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(template, handle)
        env[CONFIG_ENV] = config_path
        proc = subprocess.run(
            [sys.executable, "-c",
             "import %s as u; print(u.LAUNCHCTL, u.SERVICE, u.REPO)" % DOTTED_NAME],
            env=env, capture_output=True, text=True, cwd=isolated)
        check(proc.returncode == 0
              and proc.stdout.strip() == "/bin/launchctl com.coupler.server %s" % isolated,
              "the SAME import succeeds against a config object, binding it rather than a "
              "default (rc=%d, stdout=%r)" % (proc.returncode, proc.stdout.strip()))

        # A config object missing one key throws, NAMING the key — not a silent default.
        del template["service"]
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(template, handle)
        proc = subprocess.run([sys.executable, "-c", "import %s" % DOTTED_NAME],
                              env=env, capture_output=True, text=True, cwd=isolated)
        check(proc.returncode != 0 and "ConfigError" in proc.stderr
              and "'service'" in proc.stderr,
              "a config object missing one key throws ConfigError NAMING that key rather than "
              "defaulting it (rc=%d)" % proc.returncode)

        # A config object whose value is the wrong type throws too, rather than letting it
        # reach a command line.
        template["service"] = "com.coupler.server"
        template["describe_args"] = ["describe", 7]
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(template, handle)
        proc = subprocess.run([sys.executable, "-c", "import %s" % DOTTED_NAME],
                              env=env, capture_output=True, text=True, cwd=isolated)
        check(proc.returncode != 0 and "ConfigError" in proc.stderr
              and "element 1" in proc.stderr,
              "a config list with a non-string in it throws ConfigError naming the element, "
              "rather than letting it reach subprocess (rc=%d)" % proc.returncode)


def _selftest_surface(check, original):
    """Check [4]: the six callables ticket #375 lowered are present, with the same shape."""
    import inspect

    for name in ("_run", "_current_version", "_remote_version", "_pull_and_install",
                 "_restart_server", "main"):
        mine = getattr(_this_module(), name, None)
        theirs = getattr(original, name, None)
        if mine is None or theirs is None:
            check(False, "%s() exists on both the original and this module" % name)
            continue
        mine_sig, their_sig = inspect.signature(mine), inspect.signature(theirs)
        check(str(mine_sig) == str(their_sig),
              "%s%s — signature matches the original's exactly" % (name, mine_sig))
        check(mine.__annotations__ == theirs.__annotations__,
              "%s() annotations match the original's (%r)" % (name, mine.__annotations__))
        check(not inspect.iscoroutinefunction(mine),
              "%s() is an ordinary function, as the original's is" % name)


def _selftest_config_driven(check, out, original):
    """Check [6]: the two halves of #200 requirement 4 — the config drives it, and no value is
    hardcoded — plus the proof that the shipped config reproduces the original's derived paths.
    """
    # (a) the template an operator is told to install IS the section the package ships.
    registry_path = find_registry()
    check(registry_path is not None, "a registry is found by walking up from this module")
    if registry_path:
        document = _read_json(registry_path, "the registry")
        node = document
        for key in UNIT_PATH:
            node = node.get(key, {}) if isinstance(node, dict) else {}
        shipped, template = _strip_prose(node), _strip_prose(config_template())
        check(shipped == template,
              "the shipped registry section equals `emit-config`'s template, so the template a "
              "reader is told to install is the config that actually runs%s"
              % ("" if shipped == template
                 else " — shipped %r vs template %r" % (shipped, template)))

    # (b) none of the original's values survives as a literal in the code that RUNS the unit.
    # The scanned list is proven to BE the unit first, so it cannot be narrowed to make the
    # scan pass: every function ticket #375 names as surface must be in it, and every name in
    # it must exist.
    me = _this_module()
    check(all(hasattr(me, name) for name in UNIT_FUNCTIONS),
          "every function in UNIT_FUNCTIONS exists — the scanned list names no phantom (%r)"
          % (UNIT_FUNCTIONS,))
    check(all(name in UNIT_FUNCTIONS for name in
              ("_run", "_current_version", "_remote_version", "_pull_and_install",
               "_restart_server", "main")),
          "every callable ticket #375 lists as surface is inside the scanned set, so the scan "
          "covers the whole unit rather than a convenient subset of it")
    literals = _executable_string_constants()
    for value in ("/bin/launchctl", "com.coupler.server", "~/Library/Logs/coupler-updater.log",
                  "%(asctime)s  %(levelname)s  %(message)s", "%Y-%m-%d %H:%M:%S",
                  "--abbrev=0", "--ff-only", "origin", "stable", "coupler",
                  "update available: %s → %s", "git pull", "pip install"):
        check(value not in literals,
              "%r does not appear as a literal in this module's executable code — it is config"
              % value)

    # (c) the shipped config reproduces the paths the ORIGINAL derived from its own __file__
    # and $HOME. This is the claim "repo_path of '.' IS Path(__file__).parent.parent", measured.
    check(str(REPO) == str(original.REPO),
          "REPO from config == the ORIGINAL's Path(__file__).parent.parent (%s)" % REPO)
    check(str(LOG_FILE) == str(original.LOG_FILE),
          "LOG_FILE from config == the ORIGINAL's Path.home()/'Library/Logs/coupler-updater.log' "
          "(%s)" % LOG_FILE)
    check(PIP == original.PIP,
          "PIP from config == the ORIGINAL's [sys.executable, '-m', 'pip'] (%r)" % (PIP,))
    check(LAUNCHCTL == original.LAUNCHCTL and SERVICE == original.SERVICE,
          "LAUNCHCTL and SERVICE from config == the ORIGINAL's hardcoded values")


def _selftest_module_surface(check, original, oracle_logging):
    """Check [8]: the module-level names and the logging setup the original left behind."""
    check(oracle_logging.basic_config_calls[0] == logging_config(),
          "logging_config() == the keywords the ORIGINAL passes to logging.basicConfig (%r)"
          % (logging_config(),))
    check(log.name == original.log.name,
          "the logger name matches the original's (%r)" % log.name)
    for name in ("REPO", "PYTHON", "PIP", "LAUNCHCTL", "SERVICE", "LOG_FILE", "log", "json"):
        check(hasattr(_this_module(), name),
              "the module-level name %r the original bound is still bound" % name)
    check(isinstance(REPO, Path) and isinstance(LOG_FILE, Path),
          "REPO and LOG_FILE are pathlib.Path, as the original's were")
    check(isinstance(original.REPO, Path) and isinstance(original.LOG_FILE, Path),
          "  (proven against the oracle's own types, not assumed)")

    # The no-subcommand spelling: `python -m coupler.updater` ran the update check for the
    # original, so it must here. Proven by parsing, not by spawning an updater at a real repo.
    args = _build_parser().parse_args([])
    check((args.command or "run") == "run",
          "`%s` with no subcommand resolves to `run`, so an existing launchd plist keeps "
          "working" % _cli_name())


def _describe_source():
    try:
        return active_source()
    except ConfigError as exc:
        return "UNRESOLVED (%s)" % exc


def _package_root():
    """The directory holding `pyproject.toml` — the import path `coupler` resolves from."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _package_tree():
    """Every source file under this package, with its size — check [7]'s before/after snapshot.

    Skips the build artifacts ticket #375 names (`__pycache__`, `*.egg-info`, `build`, `dist`)
    and the `logs/` bug-report sink, because the interpreter and any install regenerate those;
    what is being proven is that the SOURCE tree is untouched.
    """
    root = _package_root()
    skip = ("__pycache__", "build", "dist", "logs")
    tree = {}
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.endswith(".egg-info")]
        for filename in filenames:
            path = os.path.join(directory, filename)
            try:
                tree[os.path.relpath(path, root)] = os.path.getsize(path)
            except OSError:
                tree[os.path.relpath(path, root)] = -1
    return tree


def _strip_prose(node):
    """Drop the `_comment` and package-wide keys, leaving the settings themselves.

    The shipped registry carries `_comment` prose explaining itself to a reader, and inherits a
    package-wide `bug_reports`; neither is a setting this unit's template speaks to, so a
    comparison against the template has to ignore them or it would fail on documentation.
    """
    if not isinstance(node, dict):
        return node
    return {key: _strip_prose(value) for key, value in node.items()
            if not key.startswith("_") and key != "bug_reports"}


#: The functions that IMPLEMENT the unit — the code that runs when the updater runs, and the
#: only code a hardcoded parameter could do any harm in. Check [6](b) scans exactly these, plus
#: this module's top-level statements, and requires that none of the original's values appears
#: as a literal in any of them.
#:
#: The proof harness is deliberately NOT scanned, and that is a limitation worth stating rather
#: than hiding: `_selftest_config_driven` must NAME the values it hunts for, `config_template`
#: must CONTAIN them (printing a template is what makes them installable data), and
#: `ORIGINAL_SOURCE` must BE them. Scanning those would make the check fail on the very evidence
#: it is made of. What the check therefore proves is narrower than "this file never spells
#: `/bin/launchctl`" and is exactly the claim #200 requirement 4 makes: no value reaches a
#: command line, a log call or a path from anywhere but the config object. A reader can hold
#: this list against THE CALLABLE SURFACE above and see that it is the whole unit.
UNIT_FUNCTIONS = (
    "settings_from_config", "logging_config", "_git", "_remote_ref", "_strip_version_prefix",
    "_run", "_current_version", "_remote_version", "_pull_and_install", "_restart_server",
    "main", "plan",
)

#: Module-level assignments check [6](b)'s scan skips, each for a stated reason:
#:   ORIGINAL_SOURCE  the original's bytes, which MUST contain the original's literals;
#:   EXEMPLARS/EDGE_CASES  the equivalence tables, prose that names the values it pins;
#:   UNIT_PATH/UNIT  the unit's ADDRESS in the config document and its identity — not settings.
#:                   A config-driven tool has to know which section is its own.
_UNSCANNED_ASSIGNS = ("ORIGINAL_SOURCE", "EXEMPLARS", "EDGE_CASES", "UNIT_PATH", "UNIT")


def _string_literals_in(node):
    """Every string constant anywhere under `node`."""
    return [child.value for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)]


def _without_docstring(body):
    """`body` with a leading docstring statement dropped — prose is not a hardcoded value."""
    if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        return body[1:]
    return body


def _executable_string_constants():
    """Every string literal in the code that RUNS the unit — check [6](b)'s evidence.

    Scans this module's top-level statements (minus `_UNSCANNED_ASSIGNS`, minus the module
    docstring, and minus every function and class body) together with the bodies of
    `UNIT_FUNCTIONS`. Both exclusion lists are named constants above with their reasons.

    Reads this file off disk rather than trusting a copy, so what is scanned is what runs.
    """
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read())

    found = []
    for node in _without_docstring(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in _UNSCANNED_ASSIGNS
                for target in node.targets):
            continue
        found.extend(_string_literals_in(node))

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in UNIT_FUNCTIONS:
            for statement in _without_docstring(node.body):
                found.extend(_string_literals_in(statement))
    return found


# ─────────────────────────────── the install proof ───────────────────────────────

def install_check(stream=None):
    """Prove acceptance item (c) by RUNNING pip, in both layouts an install leaves behind.

    Returns the number of failures. Installs only into throwaway directories, which are removed
    afterwards; the running interpreter's site-packages is never touched.

      1. the declaration — `pyproject.toml` parses, declares the `coupler` package this module
         lives in, and declares this unit's console entry point;
      2. editable — `pip install -e . --prefix <tmp>`, then `import coupler.updater` from the
         result in a child interpreter;
      3. non-editable — `pip install . --target <tmp>`, then `import coupler.updater` under
         `python3 -S`, so no real site-packages can answer for it. This is the layout where the
         registry walk-up finds nothing and `_installed_registry` is the only thing that can:
         the child proves it resolves, and then, with the shipped registry removed, that the
         config gate comes back rather than a default being guessed.

    Needs the network only if pip has to fetch a build backend it has not cached.
    """
    import tempfile

    out = stream or sys.stdout
    failures = []

    def check(ok, label):
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    root = _package_root()

    print("\n[1] the declaration in pyproject.toml", file=out)
    try:
        import tomllib
        with open(os.path.join(root, "pyproject.toml"), "rb") as handle:
            declared = tomllib.load(handle)
    except Exception as exc:  # noqa: BLE001
        check(False, "pyproject.toml parses (%s)" % exc)
        return len(failures)

    packages = declared.get("tool", {}).get("setuptools", {}).get("packages", [])
    scripts = declared.get("project", {}).get("scripts", {})
    check("coupler" in packages,
          "pyproject.toml declares the `coupler` package this module lives in, so an install "
          "ships it (declares %r)" % (packages,))
    check(any(target.startswith(DOTTED_NAME + ":") for target in scripts.values()),
          "pyproject.toml declares a console entry point for this unit (%r)" % (scripts,))

    print("\n[2] the EDITABLE layout — pip install -e .", file=out)
    with tempfile.TemporaryDirectory() as prefix:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", ".", "--prefix", prefix,
             "--no-build-isolation" if _has_setuptools() else "--quiet"],
            cwd=root, capture_output=True, text=True)
        check(proc.returncode == 0,
              "`pip install -e . --prefix <tmp>` exits 0 (rc=%d)%s"
              % (proc.returncode, "" if proc.returncode == 0
                 else "\n      " + proc.stderr.strip()[-600:]))
        if proc.returncode == 0:
            _check_import(check, prefix, root, editable=True)

    print("\n[3] the NON-EDITABLE layout — pip install . --target", file=out)
    with tempfile.TemporaryDirectory() as target:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", ".", "--target", target, "--quiet"],
            cwd=root, capture_output=True, text=True)
        check(proc.returncode == 0,
              "`pip install . --target <tmp>` exits 0 (rc=%d)%s"
              % (proc.returncode, "" if proc.returncode == 0
                 else "\n      " + proc.stderr.strip()[-600:]))
        if proc.returncode != 0:
            print("\n%s — %d failure(s)" % ("PASS" if not failures else "FAIL", len(failures)),
                  file=out)
            return len(failures)

        installed_module = os.path.join(target, "coupler", "updater.py")
        check(os.path.isfile(installed_module),
              "the install really shipped coupler/updater.py into site-packages (%s)"
              % installed_module)
        shipped_registry = os.path.join(target, PACKAGE_WITH_REGISTRY, REGISTRY_NAME)
        check(os.path.isfile(shipped_registry),
              "the install shipped registry.json as package data (%s)" % shipped_registry)

        env = dict(os.environ)
        env.pop(CONFIG_ENV, None)
        env.pop(SIBLING_CONFIG_ENV, None)
        env["PYTHONPATH"] = target

        # First, RECORD the sibling gap rather than tripping over it. `coupler/__init__.py`
        # (#397) runs before this module and cannot find a registry from a non-editable install,
        # so this import dies in the sibling. Naming it here means the next reader sees a known,
        # diagnosed, out-of-scope defect instead of a mystery — see SIBLING_PACKAGE above.
        proc = subprocess.run(
            [sys.executable, "-S", "-c", "import %s" % SIBLING_PACKAGE],
            env=env, capture_output=True, text=True, cwd=target)
        sibling_blocks = proc.returncode != 0 and "ConfigError" in proc.stderr
        print("  NOTE  `import %s` from a non-editable install %s — %s. Ticket #375 covers "
              "ONE module and does not change it; this module's own fallback is proven below "
              "past it, with the sibling's own $%s."
              % (SIBLING_PACKAGE,
                 "raises ConfigError (its _config has no installed-registry fallback)"
                 if sibling_blocks else "imports cleanly",
                 "#397's gap, not this ticket's" if sibling_blocks else "nothing to work around",
                 SIBLING_CONFIG_ENV), file=out)

        # The sibling's config object, read OUT OF THE SHIPPED REGISTRY rather than written down
        # here, handed to it through the variable its own docstring documents.
        sibling_env = _stage_sibling_config(target, shipped_registry)
        env.update(sibling_env)

        # -S so the real site-packages cannot answer: what imports here is what pip installed.
        # $COUPLER_UPDATER_CONFIG stays UNSET, so THIS module gets no such help — its config can
        # only come from the package-data registry, which is exactly what is being proven.
        proc = subprocess.run(
            [sys.executable, "-S", "-c",
             "import %s as u; print(u.SERVICE, u.active_source())" % DOTTED_NAME],
            env=env, capture_output=True, text=True, cwd=target)
        check(proc.returncode == 0 and "com.coupler.server" in proc.stdout,
              "`import %s` from the NON-editable install resolves its config through the "
              "package-data registry — the walk-up finds none there (rc=%d, stdout=%r)%s"
              % (DOTTED_NAME, proc.returncode, proc.stdout.strip(),
                 "" if proc.returncode == 0 else "\n      " + proc.stderr.strip()[-400:]))
        # Compared by realpath, not by substring: macOS resolves /var to /private/var, so the
        # reported path and the expected one differ textually while naming the same file — and a
        # substring test would ALSO pass for a path that merely contained the expected one.
        reported = _reported_source(proc.stdout)
        check(_same_file(reported, shipped_registry),
              "  and it names the SHIPPED registry as its source, not one from the checkout "
              "(%s)" % reported)

        # Remove the only registry it can see: THIS module's gate must come back. The sibling
        # still has its $COUPLER_CONFIG, so the ConfigError proven here is this module's own.
        os.remove(shipped_registry)
        proc = subprocess.run(
            [sys.executable, "-S", "-c", "import %s" % DOTTED_NAME],
            env=env, capture_output=True, text=True, cwd=target)
        check(proc.returncode != 0 and "ConfigError" in proc.stderr
              and UNIT in proc.stderr,
              "with that registry removed the SAME import raises THIS unit's ConfigError "
              "rather than guessing a default (rc=%d)" % proc.returncode)

    print("\n%s — %d failure(s)" % ("PASS" if not failures else "FAIL", len(failures)), file=out)
    for failure in failures:
        print("  FAILED: %s" % failure, file=out)
    return len(failures)


def _has_setuptools():
    """Whether this interpreter can build without pip fetching a backend (offline-friendly)."""
    try:
        import importlib.util
        return importlib.util.find_spec("setuptools") is not None
    except Exception:  # noqa: BLE001
        return False


def _stage_sibling_config(directory, registry_path):
    """Write the SIBLING unit's config object to a file and return the env var naming it.

    Read out of the shipped registry rather than written down here, so this stages the config
    the package actually ships and cannot drift from it. See `SIBLING_PACKAGE` for why the
    sibling has to be got past at all. Returns {} if the registry carries no section for it, in
    which case nothing is staged and the import is left to speak for itself.
    """
    document = _read_json(registry_path, "the registry")
    node = document
    for key in SIBLING_UNIT_PATH:
        node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            return {}
    if not isinstance(node, dict):
        return {}
    path = os.path.join(directory, "sibling-config.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(node, handle)
    return {SIBLING_CONFIG_ENV: path}


def _check_import(check, prefix, root, editable):
    """Import this module out of an editable install rooted at `prefix`, in a child interpreter.

    An editable install works through a `.pth` file, and `.pth` files are executed by the `site`
    module ONLY for directories it knows about — putting the directory on `$PYTHONPATH` does NOT
    process them, so the editable finder would never load and the import would fail for a reason
    that has nothing to do with this module. The child therefore calls `site.addsitedir()`,
    which is the supported way to activate an install tree, and only then imports.
    """
    site_dirs = []
    for directory, dirnames, filenames in os.walk(prefix):
        if os.path.basename(directory) == "site-packages":
            site_dirs.append(directory)
            dirnames[:] = []
    if not site_dirs:
        check(False, "the install produced a site-packages under the prefix")
        return

    env = dict(os.environ)
    env.pop(CONFIG_ENV, None)
    env.pop(SIBLING_CONFIG_ENV, None)
    program = (
        "import site\n"
        + "".join("site.addsitedir(%r)\n" % d for d in site_dirs)
        + "import %s as u\nprint(u.SERVICE, u.active_source())\n" % DOTTED_NAME
    )
    proc = subprocess.run([sys.executable, "-c", program],
                          env=env, capture_output=True, text=True, cwd=prefix)
    check(proc.returncode == 0 and "com.coupler.server" in proc.stdout,
          "`import %s` from the EDITABLE install works and reads its config (rc=%d, stdout=%r)%s"
          % (DOTTED_NAME, proc.returncode, proc.stdout.strip(),
             "" if proc.returncode == 0 else "\n      " + proc.stderr.strip()[-400:]))
    check(_same_file(_reported_source(proc.stdout), os.path.join(root, REGISTRY_NAME)),
          "  and its config comes from the CHECKOUT's registry, as an editable install should "
          "(an editable install points back at the source tree)")


def _reported_source(stdout):
    """The config source path a child printed after its `SERVICE` — the last space-separated
    field. Returns "" if the child printed nothing, so a failed import reports as a mismatch
    rather than raising in the check itself."""
    text = stdout.strip()
    return text.rsplit(" ", 1)[-1] if text else ""


def _same_file(left, right):
    """Whether two paths name the same file, resolving symlinks. `/var` and `/private/var` are
    the same directory on macOS, and a substring test would confuse "names it" with
    "contains it"."""
    if not left or not right:
        return False
    return os.path.realpath(left) == os.path.realpath(right)


# ─────────────────────────────── the bug-report sink ───────────────────────────────

def bug_report(exc, formatted, invocation):
    """Append one timestamped JSON line about an UNEXPECTED exception; return its path or None.

    `note-for-claude` requires that "all tools need to pass a bug-report automatically
    (timestamped if an exception is thrown)". A report means "this tool is broken", so designed
    outcomes — `ConfigError`, `UsageError` — never file one.

    Never raises: a tool that fails while reporting a failure would replace a useful traceback
    with a useless one. If the config names no `bug_reports` path, no report is filed.
    """
    try:
        config = active_config()
        relative = config.get("bug_reports")
        if not isinstance(relative, str) or not relative:
            return None
        path = _resolve_path(relative, active_base())
        os.makedirs(os.path.dirname(str(path)), exist_ok=True)
        with open(str(path), "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "unit": UNIT,
                "ticket": TICKET,
                "invocation": invocation,
                "error": "%s: %s" % (type(exc).__name__, exc),
                "traceback": formatted,
            }) + "\n")
        return str(path)
    except Exception:  # noqa: BLE001 — reporting a bug must never raise a second one
        return None


# ─────────────────────────────── the command line ───────────────────────────────

def _invocation(argv):
    """Describe how this process was ACTUALLY started, for a bug report to record.

    Derived from the interpreter and `sys.argv` rather than written as a fixed string. A report
    is a record, and a record that states an invocation the operator did not type is worse than
    no record: it sends the next reader to reproduce something that never ran.
    """
    if __name__ == "__main__" and __spec__ is not None:
        launcher = "-m " + __spec__.name
    else:
        launcher = sys.argv[0] if sys.argv and sys.argv[0] else DOTTED_NAME
    return " ".join([os.path.basename(sys.executable), launcher] + list(argv))


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="forge2-coupler-updater",
        description="forge2 rewrite of the forge unit code__code-invalid__coupler:"
                    "coupler/updater.py (ticket #375) — the launchd auto-updater. "
                    "Config-driven: it throws if it cannot see its config object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="With NO argument this runs the update check, which is the original's launchd "
               "spelling (`python -m %s`). Config is read from the file named by $%s, else "
               "from the %s section of the nearest %s found by walking up from this module, "
               "else from the registry shipped inside the installed %s package. This package "
               "ships one, so these commands work from a clean checkout. Run `emit-config` for "
               "a template, and `plan` to see what `run` would spawn without spawning it."
               % (DOTTED_NAME, CONFIG_ENV, " -> ".join(UNIT_PATH), REGISTRY_NAME,
                  PACKAGE_WITH_REGISTRY),
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="run the update check (the default): pull, reinstall, restart")
    sub.add_parser("plan", help="print the commands `run` would spawn, spawning none of them")
    sub.add_parser("selftest", help="prove this rewrite against the ORIGINAL, which it embeds")
    sub.add_parser("install-check", help="really run pip, in both install layouts")
    sub.add_parser("show-config", help="print the config object in force and its source")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    return parser


def cli(argv=None):
    """Entry point for the `forge2-coupler-updater` console script. Returns an exit code.

    With no subcommand this runs the update check, so the original's `python -m coupler.updater`
    keeps working unchanged. `main()` is the updater itself and is kept free of argument
    parsing, because it is the surface ticket #375 requires and launchd calls it.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = _build_parser().parse_args(argv)
        command = args.command or "run"

        if command == "emit-config":
            print(json.dumps(config_template(), indent=2, ensure_ascii=False))
            print("\n# Install this at %s in your registry.json, or save a file containing just "
                  "it\n# and point $%s at that file. Until it is installed, importing this "
                  "module\n# throws ConfigError — it will not guess a default."
                  % (" -> ".join(UNIT_PATH), CONFIG_ENV), file=sys.stderr)
            return 0

        if command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(), "base": active_base(),
                              "resolved": {"REPO": str(REPO), "PYTHON": PYTHON, "PIP": PIP,
                                           "LAUNCHCTL": LAUNCHCTL, "SERVICE": SERVICE,
                                           "LOG_FILE": str(LOG_FILE)},
                              "config": active_config()}, indent=2, ensure_ascii=False))
            return 0

        if command == "plan":
            print(json.dumps(plan(), indent=2, ensure_ascii=False))
            return 0

        if command == "selftest":
            return 0 if selftest() == 0 else 1

        if command == "install-check":
            return 0 if install_check() == 0 else 1

        if command == "run":
            main()
            return 0

    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except UsageError as exc:
        print("usage error: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        path = bug_report(exc, traceback.format_exc(), _invocation(argv))
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise

    return 0


if __name__ == "__main__":
    if __spec__ is None:
        # Run by path: `coupler/` went onto the import path instead of the package root, so the
        # `coupler` package is not importable and the `-m` spelling's semantics are gone. One
        # line that fixes it beats a traceback that blames the tool.
        print("usage error: run this module as `python3 -m %s ...` from the package root (the "
              "directory holding pyproject.toml), not by path. Running it by path puts %s on "
              "the import path instead of the package root, so the `coupler` package cannot be "
              "imported." % (DOTTED_NAME, os.path.dirname(os.path.abspath(__file__))),
              file=sys.stderr)
        sys.exit(2)
    sys.exit(cli())
