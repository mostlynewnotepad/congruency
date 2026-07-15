# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 testmonkeyalpha — Claude & Co.

r"""forge2 / code__code__jazz__kokoro__dz_debug / dz_debug / setup — the `dz_debug` setup script.

A behavior-preserving rewrite of the forge unit
`code__code__jazz__kokoro__dz_debug:dz_debug/setup.py` (module key forge-rw:82b6b5996ba08df6,
git blob 1344e10aab28254463c51929f15324eece651363, 352 bytes), filed under ticket #371 against
the FORGE-wide refactor standard #200. (#371 supersedes #303, which named its source only as a
`git cat-file` the sandboxed worker cannot run; #371 embeds the source, so the work is done here.)

The same module lives at seven forge tips (six copies plus the canonical one); this ONE rewrite
satisfies all of them, which is why nothing here is named for the kokoro copy in particular
except the registry address it reads its config from.

WHAT THIS IS
------------
The original is a setuptools setup script — a `setup()` call carrying five metadata literals and
a `find_packages()` call:

    setup(name='dz_debug', version='0.1.0', packages=find_packages(),
          description='A simple logging utility package', author='The Dude',
          author_email='29155646+dudezilla@users.noreply.github.com')

Its whole behavior is that call. `python3 setup.py --name` prints `dz_debug`; `python3 setup.py
--version` prints `0.1.0`; `python3 setup.py` with no command exits 1 with distutils' usage; and
`packages` is DISCOVERED by scanning the working directory rather than listed.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and adds the three things #200 requires that the original
lacked: it is part of a proper installable package, it is driven by a configuration object, and
it refuses to run when it cannot see that configuration.

THE THING THAT IS EASY TO GET BACKWARDS
---------------------------------------
This module is a setup script that is ITSELF a module of a package built by a DIFFERENT setup
system. Two distributions are in play and they are not the same:

  * `forge2-code-code-jazz-kokoro-dz-debug` — the package THIS FILE IS A MODULE OF. It is built
    from `pyproject.toml` in the directory above this one. That is the package #200 requirement 3
    and acceptance item (c) are about, and `pip install -e .` installs it.
  * `dz_debug` — the distribution THIS FILE DESCRIBES, in the forge repo it was rewritten from.
    Its name, version and metadata are what `setup()` below declares. Nothing here builds it as
    part of the forge2 package; running this file as a setup script is what does that, exactly as
    running the original did.

So `setup.py --name` printing `dz_debug` is this module's BEHAVIOR (the thing being preserved),
and it says nothing about the forge2 distribution that ships it. `pyproject.toml` never consults
this file: it declares the forge2 package with a build backend of its own, and `pip install -e .`
does not run this setup script.

THE ONE PLACE THE TWO DO TOUCH, WHICH WILL SURPRISE YOU IF NOBODY SAYS IT
-------------------------------------------------------------------------
Run this setup script from a directory that CONTAINS a `pyproject.toml` with a `[project]` table,
and setuptools reads that file and MERGES its metadata over the `setup()` call. That is
setuptools' own behavior — it discovers `pyproject.toml` from the WORKING DIRECTORY — and it is
nothing this module does. It means:

    cd dz_debug && python3 setup.py --name      ->  dz_debug           (no pyproject.toml here)
    python3 dz_debug/setup.py --name            ->  forge2-code-code-jazz-kokoro-dz-debug
                                                     ^ the package root HAS a pyproject.toml, and
                                                       setuptools merged ITS [project] name over

The second line is not a defect and it is not a divergence: the ORIGINAL, run from a directory
with a `pyproject.toml` in it, prints exactly the same thing. Selftest section [3] proves that
rather than claiming it — it plants a `pyproject.toml` beside BOTH modules and checks they agree.
The forge repo has no `pyproject.toml` in `dz_debug/`, which is why the original always printed
`dz_debug`; this rewrite reproduces that from the same directory. Behavior is preserved for the
same inputs, and the working directory is one of the inputs.

So: run this setup script from `dz_debug/`, the directory it lives in, exactly as the forge repo
had it. Every command under RUNNING IT below is written that way.

TERMS USED HERE (nothing below assumes you have read another file)
------------------------------------------------------------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a single
    `.json` file at the root of a package holding the configuration for every tool in that
    packaging. `note-for-claude` states the contract in its own words — ".json will have all the
    configuration - for all tools in this set of packaging. (a configuration registry) -if a tool
    cannot see the registry it will throw an exeption." This package ships its own
    `registry.json` at its root, one directory above this file.
config object
    The chunk of that registry belonging to this unit — the section at
    `forge2 -> code__code__jazz__kokoro__dz_debug -> setup`. It is what drives this module.
    `emit-config` prints a template of it.
metadata
    The config's `metadata` section: the keyword arguments handed to `setup()`. The original
    hardcoded five of them (name, version, description, author, author_email).
packages spec
    The config's `packages` section: HOW the `packages=` argument is produced. The original wrote
    `find_packages()`, so the shipped spec is `{"find": {...}}` carrying that call's own default
    arguments. See THE PACKAGES SPEC below.
setup script
    A file whose job is to be executed by Python with distutils/setuptools command arguments
    (`python3 setup.py --name`, `python3 setup.py sdist`). That is what the original is and what
    this file still is.

THE CALLABLE SURFACE (unchanged, so existing callers keep working — acceptance item (b))
----------------------------------------------------------------------------------------
Ticket #371 states it exactly: "this module defines no top-level function or method. Its behavior
is whatever its module-level code does — read the source above." So the surface of the ORIGINAL
is not a signature list. It is what EXECUTING the file does, and that is preserved in full. Run
from `dz_debug/`, the directory this file lives in and the one the forge repo ran it from (see
THE ONE PLACE THE TWO DO TOUCH, below, for why the directory is part of the answer):

    python3 setup.py --name             -> dz_debug            (exit 0)
    python3 setup.py --version          -> 0.1.0               (exit 0)
    python3 setup.py --description      -> A simple logging utility package
    python3 setup.py --author           -> The Dude
    python3 setup.py --author-email     -> 29155646+dudezilla@users.noreply.github.com
    python3 setup.py --fullname         -> dz_debug-0.1.0
    python3 setup.py                    -> distutils usage on stderr (exit 1)
    python3 setup.py --help             -> distutils' help, exactly as the ORIGINAL's did
    python3 setup.py <any distutils command, e.g. sdist, egg_info, --help-commands>

Every one of those is driven through `setup()` with the config's metadata, so every one behaves
as the original's. `selftest` section [3] runs each against BOTH modules as real processes and
compares exit code, stdout and stderr byte for byte, rather than asserting the table above.

`run_setup()` is this module's name for the original's module-level `setup(...)` call — see
divergence 1. The rest of this module's top-level names (`main`, `selftest`, the config helpers,
`ORIGINAL_SOURCE`) are machinery the original had none of; `__all__` is declared below so
`from dz_debug.setup import *` binds them deliberately rather than by accident.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params — acceptance item (d))
---------------------------------------------------------------------------------------
The config object is resolved on first use, from the first source that answers:

  1. the file named by the `DZ_DEBUG_SETUP_CONFIG` environment variable, which holds the unit
     config object ITSELF — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code__jazz__kokoro__dz_debug -> setup` section of the
     nearest `registry.json` found by walking UP from THIS FILE's directory;
  3. otherwise, the `registry.json` this distribution ships as package data inside its top-level
     `code__code__jazz__kokoro__dz_debug` package.

The walk-up starts at this file, never at the working directory, so which directory you run from
does not change what config is found. Step 3 never SHADOWS a nearer registry: it runs only after
the walk-up has failed outright. If none of the three answers, running the setup script raises
`ConfigError`, naming all three sources that were tried. It never guesses a default — it will not
fall back to the original's own literals, which is the whole point of requirement 4.

`configure(config)` and `using_config(config)` inject a config object directly, in-process, for
callers that hold their configuration in memory rather than on disk.

The variable is named for THIS unit rather than something forge2-wide on purpose: it names a file
holding ONE unit's config object, so a variable shared across forge2 units could only ever point
at one unit's object at a time, and pointing it at a sibling's would break this one. The sibling
units in this package read `DZ_DEBUG_CONFIG` (logger, #349), `DZ_DEBUG_INIT_CONFIG` (__init__,
#351) and `DZ_DEBUG_LOG_CONFIG` (log, #363); none of the four collide.

WHY STEP 3 EXISTS
-----------------
It is what makes a NON-editable `pip install .` work. In a source checkout or an editable
install, `dz_debug/` sits INSIDE the package root next to `registry.json`, so step 2 finds it one
directory up. A non-editable install has no such root: setuptools installs `dz_debug/` and
`code__code__jazz__kokoro__dz_debug/` as two SEPARATE top-level directories in site-packages, and
the registry ships as package data inside the second (`pyproject.toml`'s
`[tool.setuptools.package-data]`). Walking up from an installed `dz_debug/setup.py` then reaches
site-packages and beyond without ever passing the registry. Step 3 asks the installed sibling
package where it is, which is the only thing that knows. `selftest` section [7] walks the three
sources in order and shows which one answers here.

WHAT IS A SETTING, AND WHAT IS NOT
----------------------------------
#200 requires no hardcoded paths or params. This file draws the line in one place and states it,
so a reader can check it rather than guess:

  A value is a SETTING — and lives in the config object — if the ORIGINAL fixed it as a tunable:
  the five metadata literals it passed to `setup()`, and the arguments of the `find_packages()`
  call it produced `packages` with. `grep` this file for `'dz_debug'`, `'0.1.0'`, `'The Dude'` or
  the author email and every hit is in one of exactly three places, none of which is a live code
  path — `config_template()` (the template an operator installs), `ORIGINAL_SOURCE` (the oracle's
  bytes), and this docstring. The code that runs reads every one of those values out of the
  config object and has no opinion of its own. Section [2] of the selftest proves that
  mechanically: it parses the ORIGINAL's own syntax tree and checks the template against the
  literals it finds there, so the config cannot drift from the original's values without failing.

  What that grep DOES still hit in live code, and why it is not a setting: the config's own
  section names and keys (`UNIT_PATH`, `REQUIRED_METADATA`, `"find"`). A config-driven tool has to
  know which section is its own and what its keys are called; those are the document's SCHEMA,
  not its values.

  A value is CODE if changing it would change what the module MEANS rather than how it is tuned:
  that it calls `setup()` at all, that `packages` is computed at call time rather than frozen,
  that a distutils command argument is handed to setuptools untouched, and that the metadata keys
  are passed as keyword arguments. Those are the unit's contract with setuptools and with whoever
  runs it, and #200 exists to stop them moving, not to make them configurable.

THE PACKAGES SPEC
-----------------
The original wrote `find_packages()` — a call with no arguments, whose defaults are
`where='.'`, `exclude=()`, `include=('*',)`. That is a DISCOVERY, not a list: it scans the
working directory when `setup()` runs, so the answer depends on where you run it. Preserving that
means the config must configure the CALL, not freeze its result. So the shipped spec is:

    "packages": {"find": {"where": ".", "exclude": [], "include": ["*"]}}

which is `find_packages()`'s own signature defaults written out, i.e. exactly the original's
no-argument call. An operator who wants a fixed list instead may write `{"list": [...]}`; exactly
one of `find` and `list` may be given. Both paths are exercised by selftest section [5].

`where` is handed to `find_packages` VERBATIM, and is NOT rebased against the directory the
registry was found in. That is deliberate and it is what preserves behavior: the original's
`find_packages()` resolved `.` against the WORKING DIRECTORY, so a relative `where` here must too.
The registry's directory (`active_base()`) is package-wide infrastructure only — it is what the
CLI resolves `bug_reports` against, and nothing else. This is the same line the sibling `log`
unit draws for its own paths (#363).

DELIBERATE, DOCUMENTED DIVERGENCES (three)
------------------------------------------
Everything else is intended to be indistinguishable, and that is measured, not asserted: selftest
section [3] runs every caller scenario against BOTH modules and compares the results byte for
byte, and section [6] pins the divergences below to exactly what they are.

  1. WHEN `setup()` IS CALLED. The original called `setup(...)` at MODULE level, so IMPORTING it
     ran the whole setup script — setuptools parsed the importer's `sys.argv` and usually exited.
     Here `setup()` is called when this file is EXECUTED as a setup script (`__name__ ==
     "__main__"`, which is how a setup script is run and the only way the original was ever
     actually used), and NOT on import. That is what makes the module importable, installable and
     provable at all: `pip install -e .` declares `dz_debug` as a package, and a module that ran
     a setup script on import could not be a member of one, nor could `emit-config` — the command
     whose whole job is to print the config you do not yet have — ever run.

     The gate is not weakened by that, it is MOVED: `run_setup()` is the original's module-level
     call, whole. `import dz_debug.setup; dz_debug.setup.run_setup()` is the original's `import
     setup`, including its failure modes and its reading of `sys.argv`. Nothing observable about
     the setup script is reachable without passing the config gate.
  2. WHEN `setuptools` IS IMPORTED. The original imported it at module level (its line 4), so
     `import setup` raised `ModuleNotFoundError` when setuptools was absent. Here the import is
     inside `run_setup()`/`discover_packages()`, so this module imports without setuptools and
     `emit-config` and most of `selftest` run without it. Running the setup script still raises
     the identical `ModuleNotFoundError`, and still raises it BEFORE the config is resolved —
     `run_setup()` imports setuptools first, exactly as the original's line 4 came before its
     `setup()` call, so a machine missing both reports the missing setuptools, as the original
     did. Selftest section [3] reports honestly when setuptools is absent rather than skipping
     silently; see THE PROOF.
  3. THE RESERVED CLI VERBS, and this module's own top-level names. `python3 dz_debug/setup.py
     <args>` hands `<args>` to setuptools untouched — with FOUR exceptions, the verbs this
     module's own CLI answers: `selftest`, `emit-config`, `show-config`, `show-metadata`. This is
     the only argv on which this file differs from the original, and it is confined to argv the
     ORIGINAL REJECTED: each of the four makes the original exit 1 with `invalid command`, so the
     CLI shadows an error path and never a working one. Section [6] proves that by running all
     four against the ORIGINAL and checking each exits 1. Every distutils command and option —
     everything that ever WORKED — is untouched.

THE PROOF (acceptance item (a))
-------------------------------
#371 captured NO behavioral exemplars, and says what that means: "you must write the equivalence
exemplars by hand from the original's behavior before rewriting, and they are what settles this
ticket." So `selftest` does not compare against hand-copied expectations, where a mistake in the
copy passes silently. It compares against THE ORIGINAL ITSELF:

  * `ORIGINAL_SOURCE` below holds the ticket's embedded bytes verbatim. The selftest checks them
    against the ticket's stated SIZE (352) **and recomputes the git blob sha1** and checks it
    against the one the ticket names (1344e10a...). A blob sha1 is a hash of the bytes, so that
    check cannot pass unless the oracle is the forge's file, byte for byte — it is what makes
    everything below a comparison against the real original. (Worth knowing if you ever re-derive
    it: the original has NO trailing newline. With one it is 353 bytes and hashes differently.)
  * Section [2] parses that source's SYNTAX TREE and checks the shipped config template against
    the literals in the original's own `setup()` call — so "the config carries the original's
    values" is proven from the original, not from a table someone typed. This needs no setuptools
    and always runs.
  * Section [3] plants BOTH modules in sibling temp repos with identical contents, runs each as a
    real subprocess across every caller scenario, and compares exit code, stdout and stderr. It
    needs setuptools to be importable; when it is not, it says so in its own output and reports
    the sections it could not run, rather than passing quietly. That honesty is the point: run
    `python3 -m pip install setuptools` (in a venv) and re-run to get the full comparison.

Everything it creates lives in a temp directory it removes. It runs no pip and needs no network.

`selftest` also stands on its own: sections [1]-[7] plant everything they need in a temp tree, so
a LONE copy of this file — vendored somewhere, or landed without its scaffolding — still proves
its whole behavior. Only section [8] inspects the package around this file, and when there is no
package there it says so and names the missing file rather than raising. A test net that dies on
the first absent file hides every check after it and reports a traceback where it owes a verdict.

RUNNING IT
----------
Every command below is executable as written FROM THIS FILE'S OWN DIRECTORY (`dz_debug/`), which
is where the forge repo kept the setup script and the directory that reproduces the original's
answers. From anywhere else, give the path to `setup.py` — the four CLI verbs behave the same from
any directory, because the config walk-up starts at this file and never at the working directory.
Only the setuptools passthrough is directory-sensitive, and that is setuptools' doing: see THE ONE
PLACE THE TWO DO TOUCH above before running it from the package root.

    cd dz_debug
    python3 setup.py selftest        # prove the behavior against the ORIGINAL's bytes
    python3 setup.py emit-config     # print a config-object template
    python3 setup.py show-config     # print the resolved config + where it came from
    python3 setup.py show-metadata   # print the setup() call this config produces, including the
                                     #   packages it discovers in the working directory right now
    python3 setup.py --name          # the ORIGINAL's behavior: hands argv to setuptools

`selftest` and `emit-config` need no config object; `show-config` and `show-metadata` throw
without one, exiting 2 with a single self-explaining line and no traceback. The installed console
script `forge2-dz-debug-setup` takes the same four verbs, and passes anything else to setuptools
just as the file does.

INSTALLABLE (#200 requirement 3 — acceptance item (c))
------------------------------------------------------
This file is one module of the package that surrounds it, committed in full beside it. From the
PACKAGE ROOT (the directory above this one, holding `pyproject.toml`):

    python3 -m venv .venv && .venv/bin/pip install -e .
    .venv/bin/forge2-dz-debug-setup selftest
    .venv/bin/python -c "from dz_debug.setup import distribution_metadata as m; print(m()['name'])"

The venv is not decoration — a bare `pip install -e .` on a system Python managed by a package
manager is refused with "externally-managed-environment" (PEP 668), which is that Python's rule
and nothing to do with this package.

`pyproject.toml` declares the import package as `dz_debug`, so an installed copy is imported by
the name the forge unit was always addressed by. `dz_debug` has no `__init__.py` in this package
— it is a PEP 420 namespace package — because `dz_debug/__init__.py` is a SEPARATE forge rewrite
unit (ticket #351) that has not landed here yet. `import dz_debug.setup` works either way, and
when that unit lands beside this file nothing here needs to change.

A NOTE ON `pyproject.toml`, WHICH THIS UNIT HAD TO REPAIR
---------------------------------------------------------
`congruency/tools/forge_package.py` (#410) generates this repo's scaffolding, and its generated
`pyproject.toml` did not install this package's modules AT ALL. The cause is structural rather
than a typo: `module_stems()` lists only top-level `*.py` files and does not recurse
(`forge_package.py:111-122`), so for a repo whose modules live in a nested `dz_debug/` directory
it finds NO modules, and renders `packages = ["code__code__jazz__kokoro__dz_debug"]` with
`package-dir` mapping that name onto "." (`forge_package.py:138-182`). Building that wheel yields
exactly two files — `__init__.py` and `registry.json` — and not one module of `dz_debug/`. That
is measured, not inferred: selftest section [8] reads `pyproject.toml` back and checks it declares
`dz_debug`, which is the assertion that failed before this unit and passes now.

So acceptance item (c) could not be met without repairing it, and this unit repaired it the way
the sibling repo `code__code__jazz__litellm__dz_debug` already had under ticket #361 — by
declaring the nested import package explicitly. The change is strictly ADDITIVE, which is #410's
whole property and is preserved here: `code__code__jazz__kokoro__dz_debug` is still declared, still
mapped onto ".", and still ships `registry.json` as package data, so the sibling units' step-3
config fallback (WHY STEP 3 EXISTS, above) keeps working exactly as it did. `dz_debug` and
`dz_debug.tests` are declared ALONGSIDE it, so every module already landed in this package —
`log.py` (#363), `_config.py` (#349), `_init_config.py` (#351), `tests/test_dz_debug.py` (#359) —
now installs where before none of them did. Nothing was removed, and no sibling's file was edited.

SIDE EFFECTS
------------
Importing this module resolves NO config, reads NO file, imports NO setuptools and calls NO
`setup()` (divergences 1 and 2). Running the setup script does whatever the distutils command you
gave it does — which is the original's behavior and the point of the unit. `selftest` writes only
inside a temp directory it removes; `emit-config`, `show-config` and `show-metadata` write no
files at all.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception is
thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path if it hits
an UNEXPECTED exception — that is, a defect in this tool. A `ConfigError` is designed behavior,
not a bug: it files no report and prints no traceback, and exits 2 with a single self-explaining
line. A `SystemExit` from setuptools — how a setup script reports its own outcome, including the
original's exit-1 usage — is likewise designed behavior and passes through untouched.

(CPython writes its own `__pycache__/*.pyc` when it imports this file, as it does for any module;
that is the interpreter's doing and the package's `.gitignore` excludes it.)
"""

import contextlib
import importlib.util
import json
import os
import sys
import traceback
from datetime import datetime

__all__ = [
    # ── the ORIGINAL's behavior, as a callable ──
    "run_setup",
    # ── the config surface this rewrite adds (#200 requirement 4) ──
    "CONFIG_ENV",
    "ConfigError",
    "ORIGINAL_BLOB",
    "ORIGINAL_SIZE",
    "ORIGINAL_SOURCE",
    "REGISTRY_NAME",
    "REQUIRED_METADATA",
    "SHIPPING_PKG",
    "UNIT",
    "UNIT_PATH",
    "active_base",
    "active_config",
    "active_source",
    "build_config",
    "config_template",
    "configure",
    "discover_packages",
    "distribution_metadata",
    "find_registry",
    "load_config",
    "main",
    "reset_config",
    "selftest",
    "shipped_registry",
    "using_config",
]

#: The ORIGINAL unit's bytes, quoted verbatim from ticket #371's embedded source block. This is
#: the behavior-preserving basis and `selftest`'s ORACLE: it is written to disk and run, so the
#: rewrite is compared against the original EXECUTING, not against a description of it.
#: `selftest` recomputes its git blob sha1 and checks it against ORIGINAL_BLOB below, so a
#: transcription slip here cannot silently weaken the proof.
#:
#: NOTE THE ENDING: the string stops at the `)` with NO trailing newline, because the forge's file
#: has none. That is not a detail — it is the difference between 352 bytes hashing to the blob the
#: ticket names and 353 bytes hashing to something else.
ORIGINAL_SOURCE = r'''# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 testmonkeyalpha — Claude & Co.

from setuptools import setup, find_packages

setup(
    name='dz_debug',
    version='0.1.0',
    packages=find_packages(),
    description='A simple logging utility package',
    author='The Dude',
    author_email='29155646+dudezilla@users.noreply.github.com'
)'''

#: The ticket's stated SIZE for the original module, in bytes.
ORIGINAL_SIZE = 352

#: The ticket's stated git blob sha1 for the original module. `selftest` recomputes this over
#: ORIGINAL_SOURCE. A git blob sha1 is sha1("blob <len>\0" + bytes), so it pins both the length
#: and every byte — the oracle cannot drift from the forge's file without this failing.
ORIGINAL_BLOB = "1344e10aab28254463c51929f15324eece651363"

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "DZ_DEBUG_SETUP_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: This distribution's top-level package, which ships `registry.json` as package data (see
#: pyproject.toml's `[tool.setuptools.package-data]`). Consulted only when the walk-up finds
#: nothing, which is the non-editable-install case — see WHY STEP 3 EXISTS in the docstring.
SHIPPING_PKG = "code__code__jazz__kokoro__dz_debug"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in
#: the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own.
UNIT_PATH = ("forge2", "code__code__jazz__kokoro__dz_debug", "setup")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code__jazz__kokoro__dz_debug/dz_debug/setup"

#: The metadata keys the ORIGINAL passed to `setup()`, in its order. The config must carry every
#: one: dropping `author` would change the metadata the distribution declares, which is exactly
#: what this ticket exists to prevent. Extra keys are allowed and passed through — the original's
#: `setup()` took arbitrary keywords and so does this.
REQUIRED_METADATA = ("name", "version", "description", "author", "author_email")

#: Metadata keys the config may NOT carry, and why. `packages` is produced by the config's own
#: `packages` spec, so stating it twice would make it ambiguous which one wins; `script_args` is
#: the distutils command line, which belongs to whoever RUNS the setup script, not to its config.
FORBIDDEN_METADATA = ("packages", "script_args")

#: `find_packages()`'s own signature, as the config spells it: the parameter name, the JSON type
#: it must have, and the Python value the original's no-argument call used. `config_template()`
#: writes these out, and selftest section [2] checks them against the ORIGINAL's syntax tree.
FIND_PARAMS = ("where", "exclude", "include")

#: The CLI verbs this module answers instead of handing to setuptools. Every one makes the
#: ORIGINAL exit 1 with `invalid command`, so intercepting them shadows an error path and never a
#: working one — divergence 3, proven by selftest section [6].
RESERVED_VERBS = ("selftest", "emit-config", "show-config", "show-metadata")


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or malformed.

    This is the #200 requirement-4 gate and ticket #371's acceptance item (d): a tool that cannot
    see its config throws rather than guessing a default.

    It is deliberately NOT raised for the original's own failures. A distutils command line the
    original rejected still raises the `SystemExit` setuptools raises, with the same message and
    exit code; a missing setuptools still raises `ModuleNotFoundError` from the same point.
    Reproducing those exactly is what acceptance item (a) asks for, and dressing them up as
    ConfigError would change what a caller's `except` catches.
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do the setup script throws. Every value below is exactly
    one thing the ORIGINAL hardcoded — the five metadata literals it passed to `setup()`, and the
    arguments of the `find_packages()` call it produced `packages` with. Making them data rather
    than source is #200 requirement 4; keeping them EQUAL to the original's is what makes the
    rewrite behavior-preserving, and selftest section [2] proves that equality against the
    original's own syntax tree rather than trusting this function.
    """
    return {
        # ── the ORIGINAL's five setup() metadata literals, in its order ──
        "metadata": {
            "name": "dz_debug",
            "version": "0.1.0",
            "description": "A simple logging utility package",
            "author": "The Dude",
            "author_email": "29155646+dudezilla@users.noreply.github.com",
        },
        # ── the ORIGINAL's `packages=find_packages()`. These three are find_packages()'s own
        #    signature defaults, which is what its no-argument call used. See THE PACKAGES SPEC:
        #    `where` is handed over verbatim and resolved against the WORKING DIRECTORY, exactly
        #    as the original's `.` was. ──
        "packages": {"find": {"where": ".", "exclude": [], "include": ["*"]}},
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────────────── reading the config ───────────────────────────────

def shipped_registry():
    """Return the path of the `registry.json` this distribution ships as package data, or None.

    Asks the installed `code__code__jazz__kokoro__dz_debug` package where it lives. This is the
    only way to find the registry from a NON-editable install, where it is not on any path above
    this file — see WHY STEP 3 EXISTS in the module docstring.

    Uses `find_spec` rather than importing: locating a file must not run a sibling package's code.
    Returns None rather than raising if the package is absent (a `dz_debug/` vendored on its own,
    say), so the caller can report the whole picture at once.
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
    back to the copy this distribution ships as package data. The walk-up wins when both exist, so
    a checkout's own registry is never shadowed by an installed one.
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


def _strip_comments(section):
    """Drop the registry's `_comment` keys, which document a section rather than configure it."""
    return {k: v for k, v in section.items() if not k.startswith("_comment")}


def load_config(start=None):
    """Resolve this unit's config object from disk, ignoring any injected config.

    Returns a `(config, base, source)` triple: the config object, the directory the registry was
    found in, and a human-readable description of where the config came from. `start` overrides
    the directory the registry walk-up begins at.

    `base` is NOT used to rebase the packages spec's `where`. That is handed to `find_packages`
    the way the ORIGINAL handed its own `.`, so a relative `where` is relative to the working
    directory exactly as the original's was — see THE PACKAGES SPEC. `base` is package-wide
    infrastructure only: it is what the CLI resolves `bug_reports` against.

    Raises:
        ConfigError: if no config object can be found, naming all three sources that were tried.
    """
    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        if not os.path.isfile(env_path):
            raise ConfigError("%s is set to %r, but no such file exists" % (CONFIG_ENV, env_path))
        config = _read_json(env_path, "the config object named by " + CONFIG_ENV)
        if not isinstance(config, dict):
            raise ConfigError("the config object at %s must be a JSON object, not %s"
                              % (env_path, type(config).__name__))
        return (_strip_comments(config),
                os.path.dirname(os.path.abspath(env_path)),
                "%s=%s" % (CONFIG_ENV, env_path))

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s. All three sources were tried and none answered: (1) $%s is "
            "unset; (2) no %s was found by walking up from %s; (3) %s. Run "
            "`forge2-dz-debug-setup emit-config` for a template of the config object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))),
               _shipping_pkg_status()))

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. "
                "Run `forge2-dz-debug-setup emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH)))
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError("the registry section %s at %s must be a JSON object, not %s"
                          % (".".join(UNIT_PATH), registry_path, type(node).__name__))

    config = _strip_comments(node)
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit section
    # may state its own to override it. This is inheritance inside ONE config document, not a
    # guessed default — if neither states it, the key stays absent and the CLI files no report.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


# ─────────────────────────── validating the config object ───────────────────────────
#
# Every failure below is a `ConfigError` that names the key, says what was wrong with it, and
# points at `emit-config`. That is Theme 5 of the playbook applied to a config file: the operator
# who mistyped it is not reading this source, so the message has to carry the answer.

def _require_key(config, key):
    if not isinstance(config, dict):
        raise ConfigError("the config object for %s must be a JSON object, not %s"
                          % (UNIT, type(config).__name__))
    if key not in config:
        raise ConfigError("the config object for %s is missing the required key %r. The required "
                          "keys are: 'metadata', 'packages'. Run `forge2-dz-debug-setup "
                          "emit-config` for a template." % (UNIT, key))
    return config[key]


def _require_metadata(config):
    """The `metadata` section: the keyword arguments the ORIGINAL passed to `setup()`.

    Returns a plain dict of setup() keywords. Extra keys are KEPT, not rejected: the original's
    `setup()` accepted arbitrary keywords and an operator adding `url` or `license` is configuring
    the distribution, which is what this section is for. Only the two keys that would collide with
    machinery are refused (FORBIDDEN_METADATA).
    """
    section = _require_key(config, "metadata")
    if not isinstance(section, dict):
        raise ConfigError("config key 'metadata' for %s must be a JSON object of setup() keyword "
                          "arguments, not %s" % (UNIT, type(section).__name__))
    section = _strip_comments(section)

    for key in REQUIRED_METADATA:
        if key not in section:
            raise ConfigError(
                "config key 'metadata.%s' for %s is missing. 'metadata' is the ORIGINAL's setup() "
                "call and needs every one of its keys: %s. Run `forge2-dz-debug-setup emit-config` "
                "for a template." % (key, UNIT, ", ".join(REQUIRED_METADATA)))
        value = section[key]
        if not isinstance(value, str) or not value:
            raise ConfigError("config key 'metadata.%s' for %s must be a non-empty string; got %r"
                              % (key, UNIT, value))

    for key in FORBIDDEN_METADATA:
        if key in section:
            reason = ("it is produced by the config's own 'packages' spec — stating it here too "
                      "would make it ambiguous which one wins"
                      if key == "packages" else
                      "it is the distutils command line, which belongs to whoever RUNS the setup "
                      "script, not to its config")
            raise ConfigError("config key 'metadata.%s' for %s is not allowed: %s."
                              % (key, UNIT, reason))

    for key in section:
        if not isinstance(key, str) or not key.isidentifier():
            raise ConfigError("config key 'metadata' for %s has the key %r, which is not a usable "
                              "setup() keyword argument name" % (UNIT, key))
    return dict(section)


def _require_packages(config):
    """The `packages` spec: HOW the `packages=` argument is produced. See THE PACKAGES SPEC.

    Returns a `(kind, value)` pair — `("find", {kwargs})` or `("list", [names])` — so the caller
    knows whether to DISCOVER at setup() time (the original's `find_packages()`) or to hand over a
    fixed list.
    """
    section = _require_key(config, "packages")
    if not isinstance(section, dict):
        raise ConfigError(
            'config key \'packages\' for %s must be a JSON object — either {"find": {...}} to '
            'discover packages the way the ORIGINAL\'s find_packages() did, or {"list": [...]} to '
            "state them outright — not %s" % (UNIT, type(section).__name__))
    section = _strip_comments(section)

    given = [k for k in ("find", "list") if k in section]
    if len(given) != 1:
        raise ConfigError(
            "config key 'packages' for %s must give exactly one of 'find' (discover, as the "
            "ORIGINAL's find_packages() did) or 'list' (a fixed list of package names); got %s. "
            "Run `forge2-dz-debug-setup emit-config` for a template."
            % (UNIT, "neither" if not given else "both"))
    unknown = sorted(set(section) - {"find", "list"})
    if unknown:
        raise ConfigError("config key 'packages' for %s has the unknown key(s) %s; it takes only "
                          "'find' or 'list'" % (UNIT, ", ".join(repr(k) for k in unknown)))

    if given[0] == "list":
        names = section["list"]
        if not isinstance(names, list):
            raise ConfigError("config key 'packages.list' for %s must be a JSON array of package "
                              "names, not %s" % (UNIT, type(names).__name__))
        for index, name in enumerate(names):
            if not isinstance(name, str) or not name:
                raise ConfigError("config key 'packages.list[%d]' for %s must be a non-empty "
                                  "string; got %r" % (index, UNIT, name))
        return "list", list(names)

    find = section["find"]
    if not isinstance(find, dict):
        raise ConfigError("config key 'packages.find' for %s must be a JSON object of "
                          "find_packages() arguments (%s), not %s"
                          % (UNIT, ", ".join(FIND_PARAMS), type(find).__name__))
    find = _strip_comments(find)
    unknown = sorted(set(find) - set(FIND_PARAMS))
    if unknown:
        raise ConfigError("config key 'packages.find' for %s has the unknown argument(s) %s. "
                          "find_packages() takes only: %s."
                          % (UNIT, ", ".join(repr(k) for k in unknown), ", ".join(FIND_PARAMS)))

    kwargs = {}
    if "where" in find:
        where = find["where"]
        if not isinstance(where, str) or not where:
            raise ConfigError("config key 'packages.find.where' for %s must be a non-empty "
                              "directory string (the ORIGINAL's was '.', resolved against the "
                              "working directory); got %r" % (UNIT, where))
        kwargs["where"] = where
    for key in ("exclude", "include"):
        if key in find:
            value = find[key]
            if not isinstance(value, list):
                raise ConfigError("config key 'packages.find.%s' for %s must be a JSON array of "
                                  "package-name patterns, not %s"
                                  % (key, UNIT, type(value).__name__))
            for index, item in enumerate(value):
                if not isinstance(item, str) or not item:
                    raise ConfigError("config key 'packages.find.%s[%d]' for %s must be a "
                                      "non-empty string; got %r" % (key, index, UNIT, item))
            # find_packages' own signature takes tuples; JSON has only arrays.
            kwargs[key] = tuple(value)
    return "find", kwargs


def build_config(config):
    """Validate a config object and return this module's operating tables.

    Returns `{"metadata": {...}, "packages": (kind, value)}`, with every value checked and
    converted. This is a pure function of its argument: it reads no file, no environment variable
    and no module state, so `build_config(json.load(open(...)))` is the whole of the check and the
    selftest can drive it with any config object it likes.

    Raises:
        ConfigError: naming the key, what was wrong with it, and how to print a template.
    """
    return {"metadata": _require_metadata(config), "packages": _require_packages(config)}


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

    This is what the CLI resolves a relative `bug_reports` path against. It is deliberately NOT
    applied to the packages spec's `where` — see `load_config`.
    """
    if _ACTIVE is not None:
        return _ACTIVE[1]
    active_config()
    return _RESOLVED[1]


def configure(config, base=None, source="injected via configure()"):
    """Inject `config` as the config object for this process; return the previous state.

    `base` is the directory a relative `bug_reports` path resolves against, and defaults to the
    current working directory. Pass `None` as `config` to drop the injection and go back to
    resolving from disk.

    Unlike the sibling units, this one has nothing to re-bind: `run_setup()` reads the config in
    force at the moment it is CALLED, so injecting a config always takes effect on the next call,
    with no import-order caveat.
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


def _built():
    """The validated operating tables for the config in force.

    Raises:
        ConfigError: if there is no config object, or it is malformed.
    """
    return build_config(active_config())


# ─────────────────────── the ORIGINAL's module-level code, as callables ───────────────────────

def discover_packages(spec=None):
    """Produce the `packages=` argument, as the ORIGINAL's `find_packages()` did.

    With the shipped config this IS `find_packages()`: the spec carries that call's own signature
    defaults, so the discovery scans the WORKING DIRECTORY at the moment it is called and returns
    what the original returned. A `{"list": [...]}` spec hands back that list instead.

    `spec` overrides the config's own `(kind, value)` pair, for a caller — or a test — that has
    one in hand.

    Raises:
        ConfigError: if there is no config object, or its packages spec is malformed.
        ModuleNotFoundError: if setuptools is not importable, as the ORIGINAL's line 4 did.
    """
    kind, value = spec if spec is not None else _built()["packages"]
    if kind == "list":
        return list(value)
    from setuptools import find_packages  # lazy — divergence 2
    return find_packages(**value)


def distribution_metadata():
    """The complete keyword arguments for `setup()`, exactly as the ORIGINAL assembled them.

    That is the config's metadata plus a freshly DISCOVERED `packages` — computed here, at call
    time, because the original computed it at call time too (`packages=find_packages()` is an
    argument expression, evaluated when `setup(...)` runs). Freezing it would change behavior for
    anyone whose working directory differs between calls.

    Raises:
        ConfigError: if there is no config object, or it is malformed.
        ModuleNotFoundError: if setuptools is not importable.
    """
    built = _built()
    metadata = dict(built["metadata"])
    metadata["packages"] = discover_packages(built["packages"])
    return metadata


def run_setup(argv=None):
    """Run the setup script: the ORIGINAL's module-level `setup(...)` call, whole.

    `import dz_debug.setup; dz_debug.setup.run_setup()` is the original's `import setup` — see
    divergence 1. With `argv` None, setuptools reads `sys.argv[1:]` exactly as it did for the
    original; with `argv` given, those are handed to setuptools as the command line instead
    (through distutils' own `script_args`, which is the supported way to say it).

    THE ORDER HERE IS BEHAVIOR, not housekeeping. setuptools is imported FIRST, before the config
    is resolved, because the original's line 4 (`from setuptools import setup, find_packages`)
    came before its `setup(...)` call: on a machine that has neither setuptools nor a config, the
    original reported the missing setuptools, and so does this.

    Returns whatever `setup()` returns (a `Distribution`).

    Raises:
        ModuleNotFoundError: if setuptools is not importable, as the ORIGINAL did.
        ConfigError: if there is no config object, or it is malformed.
        SystemExit: whatever setuptools raises for the command line it was given — including the
            exit-1 usage the original printed when given no command. Passed through untouched.
    """
    from setuptools import setup  # lazy, and FIRST — divergence 2, and see the note above
    kwargs = distribution_metadata()
    if argv is not None:
        kwargs["script_args"] = list(argv)
    return setup(**kwargs)


# ═══════════════════════════════ the selftest ═══════════════════════════════
#
# #371 captured NO behavioral exemplars, and says what that means: "you must write the equivalence
# exemplars by hand from the original's behavior before rewriting, and they are what settles this
# ticket." Rather than hand-copy the original's behavior into expectations — where a mistake in
# the copy passes silently — the checks below run the ORIGINAL ITSELF, from the ticket's own
# bytes, and compare the two. Every file written lives inside a temp directory that is removed.

#: The caller scenarios section [3] runs against BOTH modules. Every one is an argv the ORIGINAL
#: ACCEPTS, so each is a behavior that must be preserved rather than an error path.
SCENARIOS = (
    ["--name"],
    ["--version"],
    ["--description"],
    ["--author"],
    ["--author-email"],
    ["--fullname"],
    ["--help-commands"],
    [],                       # no command: distutils usage on stderr, exit 1
    ["--name", "--version"],  # two display options at once
    ["egg_info", "--help"],
    ["nonexistent-command"],  # an error the ORIGINAL raises, which must stay identical
    # `--help` is NOT one of the reserved verbs: run as a setup script it belongs to setuptools,
    # exactly as the original's did. It is listed here so divergence 3's claim — that the four
    # verbs are the ONLY argv this file treats differently — is measured rather than asserted.
    ["--help"],
    ["--help", "egg_info"],
)

#: A pyproject.toml for a DIFFERENT distribution, planted beside both modules to prove that
#: setuptools' merge of a cwd `pyproject.toml` over `setup()` happens to the ORIGINAL exactly as
#: it happens here — see THE ONE PLACE THE TWO DO TOUCH in the module docstring. The name is
#: deliberately nothing like `dz_debug`, so a check that sees it cannot mistake it for the
#: config's own value.
_FOREIGN_PYPROJECT = '''[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "a-different-distribution"
version = "7.7.7"
'''

#: Files planted in BOTH temp repos, so `find_packages()` has the same thing to discover in each.
#: The layout mirrors the forge repo: `dz_debug/` holds setup.py beside the package's modules and
#: a `tests/` subpackage, which is what makes `find_packages()` return ['tests'] from there.
_REPLICA = {
    "__init__.py": "# dz_debug package\n",
    "log.py": "# a module\n",
    "logger.py": "# a module\n",
    os.path.join("tests", "__init__.py"): "# the tests package\n",
    os.path.join("tests", "test_dz_debug.py"): "# a test module\n",
}


def _blob_sha1(data):
    """The git blob sha1 of `data`: sha1("blob <len>\\0" + data). What `git hash-object` prints."""
    import hashlib
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _have_setuptools():
    """Is setuptools importable? Section [3] needs it; most of the selftest does not."""
    try:
        return importlib.util.find_spec("setuptools") is not None
    except (ImportError, ValueError):
        return False


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _plant_repo(root, setup_source, registry=None):
    """Write a replica forge repo under `root` and return the directory holding its setup.py.

    `setup_source` becomes `<root>/dz_debug/setup.py`; the replica modules are written beside it.
    `registry`, when given, goes to `<root>/registry.json` — the same place this package's real
    registry sits relative to this file, so the rewrite copy resolves its config by exactly the
    walk-up the shipped one uses, and `find_packages()` run from `dz_debug/` cannot see it.
    """
    pkg = os.path.join(root, "dz_debug")
    with open(os.path.join(_ensure(pkg), "setup.py"), "w", encoding="utf-8") as handle:
        handle.write(setup_source)
    for name, text in _REPLICA.items():
        _write(os.path.join(pkg, name), text)
    if registry is not None:
        _write(os.path.join(root, REGISTRY_NAME), json.dumps(registry, indent=2) + "\n")
    return pkg


def _ensure(directory):
    os.makedirs(directory, exist_ok=True)
    return directory


def _registry_for(config):
    """A registry document carrying `config` at this unit's own address in it."""
    return {"schema": 1, "forge2": {UNIT_PATH[1]: {UNIT_PATH[2]: config}}}


def _run(cwd, args, env_extra=None):
    """Run `python3 setup.py <args>` in `cwd` and return (exit, stdout, stderr)."""
    import subprocess
    env = dict(os.environ)
    env.pop(CONFIG_ENV, None)
    env.update(env_extra or {})
    proc = subprocess.run([sys.executable, "setup.py"] + list(args), cwd=cwd, env=env,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _normalize(text, *roots):
    """Blank out what legitimately differs between two runs: the temp paths and the module name.

    Two copies of the setup script live in two different directories, so any path either of them
    prints differs for that reason alone. Everything else must match exactly.
    """
    for root in roots:
        text = text.replace(root, "<root>")
        text = text.replace(os.path.realpath(root), "<root>")
    return text


def _original_setup_call():
    """The ORIGINAL's `setup()` call, read out of its own syntax tree.

    Returns `(constants, find_kwargs)`: every keyword whose value is a plain literal, and the
    keyword arguments of the `find_packages()` call the original produced `packages` with. This is
    what lets section [2] prove the shipped config carries the ORIGINAL's values without anyone
    typing them out a second time — the original's bytes are the only source.

    Raises:
        AssertionError: if the original's source is not the shape this describes. That cannot
            happen unless ORIGINAL_SOURCE has been altered, which section [1] catches first.
    """
    import ast

    tree = ast.parse(ORIGINAL_SOURCE)
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "setup"]
    assert len(calls) == 1, "expected exactly one setup() call, found %d" % len(calls)
    constants, find_kwargs = {}, None
    for keyword in calls[0].keywords:
        value = keyword.value
        if isinstance(value, ast.Constant):
            constants[keyword.arg] = value.value
        elif (keyword.arg == "packages" and isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name) and value.func.id == "find_packages"):
            find_kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in value.keywords}
            assert not value.args, "find_packages() was called with positional arguments"
    assert find_kwargs is not None, "the original's packages= is not a find_packages() call"
    return constants, find_kwargs


def selftest(stream=None):
    """Prove this rewrite against ticket #371's acceptance items (a)-(d). Returns the failure count.

    It needs no config on disk, no network and no pip; it writes only inside a temp directory it
    removes, and it restores every global it touches. Section [3] additionally needs setuptools to
    be importable — when it is not, that is REPORTED rather than skipped silently, and the summary
    says how many checks could not run. `python3 dz_debug/setup.py selftest` runs it.
    """
    import tempfile

    out = stream or sys.stdout
    checks, failures, skipped = [0], [], []

    def check(ok, label):
        checks[0] += 1
        print("  %s  %s" % ("ok  " if ok else "FAIL", label), file=out)
        if not ok:
            failures.append(label)

    def skip(label):
        skipped.append(label)
        print("  SKIP  %s" % label, file=out)

    saved_env = os.environ.get(CONFIG_ENV)
    saved_active, saved_resolved = _ACTIVE, _RESOLVED
    here = os.path.dirname(os.path.abspath(__file__))
    package_root = os.path.dirname(here)

    print("== selftest: %s (ticket #371, module key forge-rw:82b6b5996ba08df6)" % UNIT, file=out)
    try:
        os.environ.pop(CONFIG_ENV, None)
        reset_config()

        # ── 1. the oracle is the ticket's own bytes ──────────────────────────────────
        print("[1] the oracle — ticket #371's embedded ORIGINAL SOURCE, verbatim", file=out)
        raw = ORIGINAL_SOURCE.encode("utf-8")
        check(len(raw) == ORIGINAL_SIZE,
              "ORIGINAL_SOURCE is %d bytes, the SIZE ticket #371 states (%d)"
              % (len(raw), ORIGINAL_SIZE))
        got_blob = _blob_sha1(raw)
        check(got_blob == ORIGINAL_BLOB,
              "its git blob sha1 is %s, the blob ticket #371 names%s"
              % (got_blob, "" if got_blob == ORIGINAL_BLOB else " (expected %s)" % ORIGINAL_BLOB))
        check(compile(ORIGINAL_SOURCE, "<original>", "exec") is not None,
              "ORIGINAL_SOURCE is valid Python")

        # ── 2. the config carries the ORIGINAL's values — proven from its syntax tree ──
        print("[2] the config object IS the ORIGINAL's literals (read from its own AST, not "
              "typed out)", file=out)
        constants, find_kwargs = _original_setup_call()
        template = config_template()
        check(template["metadata"] == constants,
              "config_template()['metadata'] == the ORIGINAL's setup() literals: %s"
              % json.dumps(constants, sort_keys=True))
        check(list(template["metadata"]) == list(constants),
              "...in the ORIGINAL's own key order: %s" % ", ".join(constants))
        check(tuple(constants) == REQUIRED_METADATA,
              "REQUIRED_METADATA names exactly the keys the ORIGINAL passed: %s"
              % ", ".join(REQUIRED_METADATA))
        check(find_kwargs == {},
              "the ORIGINAL's packages= is find_packages() with NO arguments, so its defaults "
              "are what the config must reproduce")
        # find_packages' real signature defaults are the authority on what a no-argument call
        # means. Read them off the function itself rather than trusting the template.
        if _have_setuptools():
            import inspect
            from setuptools import find_packages
            defaults = {name: param.default
                        for name, param in inspect.signature(find_packages).parameters.items()
                        if name in FIND_PARAMS}
            shipped = template["packages"]["find"]
            same = {k: (tuple(v) if isinstance(v, list) else v) for k, v in shipped.items()}
            check(same == defaults,
                  "config_template()['packages']['find'] == find_packages()'s own signature "
                  "defaults %s, i.e. the ORIGINAL's no-argument call" % (defaults,))
        else:
            skip("config template vs find_packages()'s signature defaults (needs setuptools)")
        built = build_config(template)
        check(built["packages"][0] == "find",
              "the shipped spec DISCOVERS packages (it does not freeze a list), as the ORIGINAL "
              "did")

        with tempfile.TemporaryDirectory(prefix="dz_debug_setup_selftest_") as tmp:
            with open(os.path.abspath(__file__), "r", encoding="utf-8") as handle:
                rewrite_source = handle.read()

            oracle_root = os.path.join(tmp, "oracle")
            rewrite_root = os.path.join(tmp, "rewrite")
            oracle = _plant_repo(oracle_root, ORIGINAL_SOURCE)
            rewrite = _plant_repo(rewrite_root, rewrite_source, registry=_registry_for(template))

            # ── 3. equivalence: the ORIGINAL and the rewrite, run side by side ────────
            print("[3] equivalence — the rewrite RUN against the ORIGINAL RUN, scenario by "
                  "scenario", file=out)
            if not _have_setuptools():
                skip("all %d caller scenarios: setuptools is not importable, so neither the "
                     "ORIGINAL nor this rewrite can run. This is REPORTED, not glossed over: run "
                     "`python3 -m pip install setuptools` (in a venv) and re-run selftest for the "
                     "full comparison. Sections [1], [2], [4]-[8] cover everything else and ran "
                     "above/below." % len(SCENARIOS))
            else:
                for args in SCENARIOS:
                    want = _run(oracle, args)
                    got = _run(rewrite, args)
                    same = (want[0] == got[0]
                            and (_normalize(want[1], oracle_root)
                                 == _normalize(got[1], rewrite_root))
                            and (_normalize(want[2], oracle_root)
                                 == _normalize(got[2], rewrite_root)))
                    label = "python3 setup.py %s" % (" ".join(args) if args else "(no args)")
                    check(same, "%-34s -> exit %d, stdout %r%s"
                          % (label, want[0], want[1][:60],
                             "" if same else "  != the ORIGINAL's: got exit %d, stdout %r, stderr "
                                             "%r" % (got[0], got[1][:200], got[2][-300:])))
                # The discovery is the point of find_packages(): prove BOTH modules actually scan
                # the directory and find the same thing, rather than both printing metadata.
                want = _run(oracle, ["--name", "--fullname"])
                got = _run(rewrite, ["--name", "--fullname"])
                check(want[1] == got[1] == "dz_debug\ndz_debug-0.1.0\n",
                      "both print the ORIGINAL's name and fullname: %r" % (want[1],))

                # THE ONE PLACE THE TWO DO TOUCH (see the module docstring), measured. setuptools
                # discovers a pyproject.toml from the WORKING DIRECTORY and merges its [project]
                # over the setup() call. That surprises people, so rather than assert that the
                # ORIGINAL does it too, plant one beside BOTH and check they agree.
                for directory in (oracle, rewrite):
                    _write(os.path.join(directory, "pyproject.toml"), _FOREIGN_PYPROJECT)
                try:
                    want = _run(oracle, ["--name"])
                    got = _run(rewrite, ["--name"])
                    check(want[1] == got[1],
                          "with a foreign pyproject.toml in the cwd, the rewrite prints what the "
                          "ORIGINAL prints (%r) — setuptools merges its [project] over setup() "
                          "for BOTH, so this is setuptools' behavior, faithfully kept"
                          % want[1].strip())
                    check(want[1].strip() == "a-different-distribution",
                          "...and that IS the merge happening: both print the pyproject's name, "
                          "not the config's 'dz_debug'. Run the setup script from dz_debug/, "
                          "which has no pyproject.toml — as the forge repo did.")
                finally:
                    for directory in (oracle, rewrite):
                        os.remove(os.path.join(directory, "pyproject.toml"))

            # ── 4. the config gate (#200 req 4, acceptance item (d)) ─────────────────
            print("[4] the gate — with NO config object, the setup script THROWS, and never "
                  "guesses", file=out)
            gateless_root = os.path.join(tmp, "gateless")
            gateless = _plant_repo(gateless_root, rewrite_source)  # note: no registry planted
            # The walk-up starts at the planted file and would escape the temp dir into this
            # checkout, which HAS a registry — so point CONFIG_ENV at a file that does not exist,
            # which is a source that answers "no" before the walk-up ever runs.
            missing = os.path.join(tmp, "no-such-config.json")
            code, stdout, stderr = _run(gateless, ["show-config"], {CONFIG_ENV: missing})
            check(code == 2, "show-config with no config object exits 2 (got %d)" % code)
            check("config error" in stderr.lower() and "Traceback" not in stderr,
                  "...with ONE self-explaining line and no traceback: %r" % stderr.strip()[:110])
            code2, stdout2, stderr2 = _run(gateless, ["--name"], {CONFIG_ENV: missing})
            check(code2 != 0 and "dz_debug" not in stdout2,
                  "`setup.py --name` with no config object FAILS rather than falling back to the "
                  "ORIGINAL's literals (exit %d, stdout %r)" % (code2, stdout2))
            if _have_setuptools():
                check("config error" in stderr2.lower(),
                      "...and says it is a config problem: %r" % stderr2.strip()[:70])
            else:
                # Divergence 2's ordering claim, and this is the machine that proves it: with
                # NEITHER setuptools nor a config, run_setup() reports the missing setuptools,
                # because the ORIGINAL's line 4 came before its setup() call and did the same.
                check("ModuleNotFoundError" in stderr2 and "setuptools" in stderr2,
                      "...and with setuptools ALSO missing it reports setuptools FIRST, exactly "
                      "as the ORIGINAL's line 4 did (divergence 2's documented ordering)")
            for thunk, label in (
                (lambda: build_config({"packages": {"find": {}}}), "metadata missing"),
                (lambda: build_config({"metadata": {}, "packages": {"find": {}}}),
                 "metadata.name missing"),
                (lambda: build_config({"metadata": dict(constants), "packages": {}}),
                 "packages gives neither find nor list"),
                (lambda: build_config({"metadata": dict(constants),
                                       "packages": {"find": {}, "list": []}}),
                 "packages gives both find and list"),
                (lambda: build_config({"metadata": dict(constants, packages=["x"]),
                                       "packages": {"find": {}}}),
                 "metadata states the forbidden 'packages' key"),
                (lambda: build_config({"metadata": dict(constants),
                                       "packages": {"find": {"nope": 1}}}),
                 "packages.find has an argument find_packages() does not take"),
                (lambda: build_config({"metadata": dict(constants, name=""),
                                       "packages": {"find": {}}}), "metadata.name is empty"),
            ):
                raised = None
                try:
                    thunk()
                except ConfigError as exc:
                    raised = exc
                except Exception as exc:  # noqa: BLE001 — any other type is itself the failure
                    raised = exc
                check(isinstance(raised, ConfigError),
                      "a config where %-46s -> ConfigError: %s"
                      % (label, str(raised)[:78] if raised else "NOTHING RAISED"))

            # ── 5. the packages spec drives the discovery ────────────────────────────
            print("[5] control-config'd — the config, and only the config, decides the packages",
                  file=out)
            listed = dict(template, packages={"list": ["alpha", "beta"]})
            with using_config(listed):
                check(discover_packages() == ["alpha", "beta"],
                      "a {'list': [...]} spec hands back exactly that list, importing nothing")
            if _have_setuptools():
                # Run from the replica repo, where the ORIGINAL's find_packages() finds ['tests'].
                cwd = os.getcwd()
                try:
                    os.chdir(oracle)
                    with using_config(template):
                        found = discover_packages()
                    check(found == ["tests"],
                          "the shipped {'find': ...} spec DISCOVERS %r from the replica repo — "
                          "the same scan the ORIGINAL's find_packages() performs there" % (found,))
                    with using_config(dict(template,
                                           packages={"find": {"where": ".",
                                                              "exclude": ["tests"]}})):
                        check(discover_packages() == [],
                              "...and an `exclude` in the config really reaches find_packages()")
                finally:
                    os.chdir(cwd)
                with using_config(dict(template, metadata=dict(constants, name="renamed"))):
                    cwd = os.getcwd()
                    try:
                        os.chdir(oracle)
                        check(distribution_metadata()["name"] == "renamed",
                              "distribution_metadata() reads name from the config, not from source")
                    finally:
                        os.chdir(cwd)
            else:
                skip("find-spec discovery and distribution_metadata() (need setuptools)")

            # ── 6. divergence 3: the reserved verbs shadow ERROR paths only ──────────
            print("[6] divergence 3 — the four CLI verbs shadow argv the ORIGINAL REJECTED",
                  file=out)
            if _have_setuptools():
                for verb in RESERVED_VERBS:
                    code, _, stderr = _run(oracle, [verb])
                    check(code == 1 and "invalid command" in stderr,
                          "the ORIGINAL exits 1 on `setup.py %-13s` (%r), so answering it here "
                          "shadows no working behavior"
                          % (verb, stderr.strip().splitlines()[-1][:56] if stderr.strip() else ""))
                code, stdout, _ = _run(rewrite, ["emit-config"])
                check(code == 0 and json.loads(stdout) == template,
                      "...and `setup.py emit-config` prints this unit's config template instead")
            else:
                skip("the reserved-verb divergence against the ORIGINAL (needs setuptools)")

            # ── 7. resolution order ──────────────────────────────────────────────────
            print("[7] where the config comes from — the three sources, in order", file=out)
            env_config = os.path.join(tmp, "env-config.json")
            _write(env_config, json.dumps(dict(template,
                                               metadata=dict(constants, version="9.9.9"))))
            code, stdout, _ = _run(rewrite, ["show-config"], {CONFIG_ENV: env_config})
            check(code == 0 and json.loads(stdout)["config"]["metadata"]["version"] == "9.9.9",
                  "[1] $%s wins: its config object is the one in force" % CONFIG_ENV)
            code, stdout, _ = _run(rewrite, ["show-config"])
            check(code == 0 and json.loads(stdout)["source"].endswith(REGISTRY_NAME)
                  and json.loads(stdout)["config"]["metadata"]["version"] == "0.1.0",
                  "[2] with $%s unset, the walk-up from the module finds the planted %s"
                  % (CONFIG_ENV, REGISTRY_NAME))
            code, stdout, _ = _run(rewrite, ["show-config", "--any", "--junk"])
            check(code == 0, "...and the walk-up does not depend on the working directory or argv")
            shipped_reg = os.path.join(package_root, REGISTRY_NAME)
            if os.path.isfile(shipped_reg):
                check(find_registry(start=here) == shipped_reg,
                      "in THIS checkout the walk-up from %s finds %s"
                      % (os.path.basename(here), shipped_reg))
            else:
                skip("the walk-up in THIS checkout (there is no %s at %s — see A LONE COPY below)"
                     % (REGISTRY_NAME, package_root))
            check(callable(shipped_registry) and (shipped_registry() is None
                                                  or shipped_registry().endswith(REGISTRY_NAME)),
                  "[3] the shipped-registry fallback answers %r here (it is what a NON-editable "
                  "install relies on)" % (shipped_registry(),))

            # ── 8. installable (#200 req 3, acceptance item (c)) ─────────────────────
            #
            # A LONE COPY. Everything below inspects the PACKAGE AROUND THIS FILE, so it is the
            # one part of the selftest that needs this file to be sitting in its package. Run a
            # lone `setup.py` on its own — vendored somewhere, or landed without its scaffolding —
            # and there is no package to check. That is REPORTED as a skip naming the missing
            # file, never a traceback: a test net that dies on the first absent file hides every
            # check after it, and sections [1]-[7] proved the unit's whole behavior without ever
            # reading these two files.
            print("[8] installable — what `pip install -e .` depends on, checked WITHOUT running "
                  "pip", file=out)
            pyproject = os.path.join(package_root, "pyproject.toml")
            if not os.path.isfile(pyproject):
                skip("every check of the package around this file: there is no pyproject.toml at "
                     "%s, so this copy of setup.py is not inside its package. Sections [1]-[7] "
                     "above do not depend on it and ran." % package_root)
            else:
                check(True, "the package root has a pyproject.toml: %s" % pyproject)
                with open(pyproject, "r", encoding="utf-8") as handle:
                    toml_text = handle.read()
                check('build-backend = "setuptools.build_meta"' in toml_text,
                      "...it declares a build backend")
                # THE assertion that failed before this unit: the generated pyproject declared
                # only the outer package, so NOTHING under dz_debug/ was installed. See the
                # docstring's note on pyproject.toml.
                check('"dz_debug"' in toml_text,
                      "...it declares the import package `dz_debug`, so THIS module installs (the "
                      "generated scaffolding did not, and could not: forge_package.py:111-122)")
                check('"%s"' % SHIPPING_PKG in toml_text,
                      "...and it STILL declares %s, so the siblings' shipped-registry fallback "
                      "keeps working — the repair was additive" % SHIPPING_PKG)
                check('%s = ["registry.json"]' % SHIPPING_PKG in toml_text,
                      "...and %s still ships %s as package data" % (SHIPPING_PKG, REGISTRY_NAME))
                check('forge2-dz-debug-setup = "dz_debug.setup:main"' in toml_text,
                      "...and the console entry point points at this module's main()")

            if not os.path.isfile(shipped_reg):
                skip("the shipped config object (there is no %s at %s — same reason)"
                     % (REGISTRY_NAME, package_root))
            else:
                check(True, "the package root has a %s for the walk-up to find" % REGISTRY_NAME)
                node = _read_json(shipped_reg, "the registry")
                for key in UNIT_PATH:
                    node = node.get(key) if isinstance(node, dict) else None
                ok = isinstance(node, dict)
                check(ok and build_config(node) is not None,
                      "...carrying a VALID config object for this unit at %s"
                      % " -> ".join(UNIT_PATH))
                # Compare what the two PRODUCE, not their raw bytes: the registry documents its
                # sections with `_comment` keys (which `load_config` and `build_config` strip and
                # the template has no reason to carry), so raw equality would fail over prose. The
                # operating tables are the thing that has to match — they are what setup() is
                # called with.
                check(ok and build_config(node) == build_config(template),
                      "...producing the same setup() call as the template `emit-config` prints, "
                      "so a clean checkout runs")
                check(ok and node.get("bug_reports") == template["bug_reports"],
                      "...and naming the same bug_reports path (%s)" % template["bug_reports"])
            # An installed console script does `from dz_debug.setup import main; main()`. Prove
            # that resolves to something callable, which is the end state the entry point needs.
            check(callable(main) and main.__module__ == __name__,
                  "`dz_debug.setup:main` resolves to a callable in this module")
            code, stdout, stderr = _run(rewrite, ["show-metadata"])
            if _have_setuptools():
                check(code == 0 and json.loads(stdout)["name"] == "dz_debug",
                      "`setup.py show-metadata` prints the setup() call the config produces")
            else:
                skip("show-metadata end-to-end (needs setuptools)")

    finally:
        if saved_env is None:
            os.environ.pop(CONFIG_ENV, None)
        else:
            os.environ[CONFIG_ENV] = saved_env
        globals()["_ACTIVE"], globals()["_RESOLVED"] = saved_active, saved_resolved

    print("\n%d checks, %d failed%s"
          % (checks[0], len(failures),
             ", %d skipped (reported above)" % len(skipped) if skipped else ""), file=out)
    for label in failures:
        print("  FAILED: %s" % label, file=out)
    if skipped:
        print("  NOTE: %d check-group(s) could not run here; they are listed as SKIP above and "
              "are NOT counted as passes." % len(skipped), file=out)
    return len(failures)


# ═══════════════════════════════ the CLI ═══════════════════════════════

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by `note-for-claude` ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report its
    original error. No report is filed for a ConfigError — that is designed behavior rather than a
    bug. Returns the path written, or None.
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
        "note": "%s (ticket #371, module key forge-rw:82b6b5996ba08df6)" % UNIT,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except OSError:
        return None


USAGE = """\
forge2-dz-debug-setup — the forge2 rewrite of the forge unit
code__code__jazz__kokoro__dz_debug:dz_debug/setup.py (ticket #371). It is a setuptools SETUP
SCRIPT for the `dz_debug` distribution, driven by a config object instead of hardcoded literals.

  %(prog)s selftest        prove this rewrite against the ORIGINAL's own bytes (its git blob
                           sha1 is checked), the config gate, the divergences and the install.
                           Needs no config; writes only to a temp dir it removes.
  %(prog)s emit-config     print a template of this unit's config object. Needs no config.
  %(prog)s show-config     print the config object in force and where it came from.
  %(prog)s show-metadata   print the setup() call this config produces, including the packages
                           it discovers in the working directory right now.

  %(prog)s <anything else> hand it to setuptools, exactly as the ORIGINAL did:
                           `--name`, `--version`, `--fullname`, `sdist`, `--help-commands`, ...

Run as a SETUP SCRIPT (`python3 dz_debug/setup.py ...`), those four verbs are the ONLY argv this
file treats differently from the original, and the original exits 1 with `invalid command` on
every one of them — so no working behavior is shadowed. Everything else, `--help` included, goes
to setuptools untouched. Run as THIS console script, a bare `--help` prints the text you are
reading, because a console script has no distutils command line of its own to describe.

config is read from the file named by $%(env)s, else from the %(path)s section of the nearest
%(registry)s found by walking UP from this module (never from the working directory), else from
the %(registry)s this distribution ships as package data. This package ships one at its root, so
the commands work from a clean checkout. `show-config`, `show-metadata` and any setuptools
command throw without a config object, exiting 2 with one line; they never guess a default.
""" % {"prog": "forge2-dz-debug-setup", "env": CONFIG_ENV, "path": ".".join(UNIT_PATH),
       "registry": REGISTRY_NAME}


def _invoked_as_setup_script():
    """Was this run as `python3 .../setup.py`, rather than as the console script?

    Only `--help` asks: as a setup script it belongs to setuptools (the ORIGINAL printed distutils'
    help), and as a console script there is no distutils command line to describe, so it prints
    USAGE. Nothing else in the CLI depends on this.
    """
    return os.path.basename(sys.argv[0]) == "setup.py"


def main(argv=None):
    """Entry point for the `forge2-dz-debug-setup` console script. Returns a process exit code.

    ALWAYS returns an `int` (or raises). `run_setup()` returns setuptools' `Distribution`, which
    must never be returned from here: `sys.exit(main())` would print the object and exit 1.

    Everything that is not one of `RESERVED_VERBS` is handed to setuptools by `run_setup()`,
    which is what makes `python3 dz_debug/setup.py --name` behave as the ORIGINAL did. argparse is
    deliberately NOT used for that passthrough: it would claim `-h`/`--help` and mangle the
    distutils command line, which belongs to setuptools.

    Raises:
        SystemExit: whatever setuptools raises for the command line it was given. That is how a
            setup script reports its outcome — including the original's exit-1 usage — so it is
            passed through untouched rather than converted to a return code.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    verb = argv[0] if argv else None
    try:
        if verb in ("-h", "--help") and len(argv) == 1 and not _invoked_as_setup_script():
            # The ORIGINAL's `setup.py --help` prints distutils' help, so `--help` is NOT
            # intercepted for the setup script — only for the console script, whose `--help` never
            # meant anything else. Selftest section [3] runs `setup.py --help` against the
            # ORIGINAL to keep that true.
            sys.stdout.write(USAGE)
            return 0
        if verb == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at it.\n"
                  "# Until it is installed, the setup script throws — it will not guess a default."
                  % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV), file=sys.stderr)
            return 0
        if verb == "selftest":
            return 0 if selftest() == 0 else 1
        if verb == "show-config":
            print(json.dumps({"unit": UNIT,
                              "source": active_source(),
                              "base": active_base(),
                              "config": active_config()}, indent=2, default=str))
            return 0
        if verb == "show-metadata":
            metadata = distribution_metadata()
            print(json.dumps(metadata, indent=2, default=str))
            print("\n# The setup() call `%s` produces from the config at %s, with `packages` "
                  "discovered in %s just now." % (UNIT, active_source(), os.getcwd()),
                  file=sys.stderr)
            return 0
        # Everything else is the ORIGINAL's behavior: setuptools' command line, untouched.
        run_setup(argv)
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


if __name__ == "__main__":
    # Divergence 1: the ORIGINAL called setup() at module level, so importing it ran the setup
    # script. Here that call happens HERE — when the file is executed, which is how a setup script
    # is run and the only way the original was ever actually used. `run_setup()` is the same call
    # for a caller who wants the original's import-time semantics.
    #
    # This module has no relative imports, so running it as a plain file behaves exactly as the
    # installed `forge2-dz-debug-setup` console script does — there is nothing to re-import.
    sys.exit(main())
