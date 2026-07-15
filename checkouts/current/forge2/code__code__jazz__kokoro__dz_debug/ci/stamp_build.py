#!/usr/bin/env python3

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 testmonkeyalpha — Claude & Co.

r"""forge2 / code__code__jazz__kokoro__dz_debug / ci / stamp_build — write build.json from the
environment.

A behavior-preserving rewrite of the forge unit
`code__code__jazz__kokoro__dz_debug:ci/stamp_build.py` (module key forge-rw:742fec59a1578e91,
git blob 4916d8f6a3b9439bad5c1767adb58df3c6131587, 1403 bytes), filed under ticket #367
against the FORGE-wide refactor standard #200. (#367 supersedes #298, which named its source
only as a `git cat-file` the sandboxed worker cannot run; #367 embeds the source, so the work
is done here.)

The same module lives at three forge tips (two copies plus the canonical one); this ONE
rewrite satisfies all of them, which is why nothing here is named for the kokoro copy in
particular except the registry address it reads its config from.

WHAT THIS IS
------------
The original is a CI build stamper. Its own docstring says: "write conf/env/build.json from
environment variables. Called by .gitlab-ci.yml version stage." It reads six environment
variables, refuses to run if any is unset or empty, derives a major/minor pair by splitting
VERSION on ".", and writes a nine-key JSON document to `conf/env/build.json` — creating the
parent directories — then prints a one-line confirmation naming the version, the tag and the
first eight characters of the commit sha.

The original is a SCRIPT: it has no functions and no classes, and every one of its values —
the six variable names, the output path, the JSON indent, the exit code, both message layouts
and the 8-character sha preview — is a literal in its body.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior, and adds the three things #200 requires that the original lacked: it is part of a
proper installable package, it is driven by a configuration object, and it refuses to run when
it cannot see that configuration.

TERMS USED HERE (nothing below assumes you have read another file)
------------------------------------------------------------------
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a single
    `.json` file at the root of a package holding the configuration for every tool in that
    packaging. `note-for-claude` states the contract in its own words — ".json will have all
    the configuration - for all tools in this set of packaging. (a configuration registry) -if
    a tool cannot see the registry it will throw an exeption." This package ships its own
    `registry.json` at its root, one directory above this file.
config object
    The chunk of that registry belonging to this unit — the section at
    `forge2 -> code__code__jazz__kokoro__dz_debug -> stamp_build`. It is what drives this
    module. `emit-config` prints a template of it.
role
    What this module COMPUTES a value for: `version`, `tag`, `build`, `major`, `minor`, `sha`,
    `branch`, `pipeline`, `built_at` — the nine values the original's `data` dict held. A role
    is code; the environment variable it is read from and the JSON key it is written under are
    config. See WHAT IS A SETTING below.
field
    One entry of the config's `fields` list: a role plus the JSON key it is written under. The
    list's ORDER is the order of the keys in the build.json this writes.

THE CALLABLE SURFACE (acceptance item (b))
------------------------------------------
Ticket #367 states it in full: "this module defines no top-level function or method. Its
behavior is whatever its module-level code does." The original binds NO name a caller could
import and call — it is executed, not imported, and its one caller is the `.gitlab-ci.yml`
version stage that runs it. So the surface to keep working is the SCRIPT invocation, and it is
kept exactly:

    python3 ci/stamp_build.py        # identical to `python3 stamp_build.py` on the original

`selftest` proves that equivalence by running BOTH files as scripts and comparing what a
caller can see — see THE PROOF below.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The config object is resolved on first use, from the first source that answers:

  1. the file named by the `DZ_DEBUG_STAMP_BUILD_CONFIG` environment variable, which holds the
     unit config object ITSELF — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code__jazz__kokoro__dz_debug -> stamp_build` section of
     the nearest `registry.json` found by walking UP from THIS FILE's directory;
  3. otherwise, the `registry.json` this distribution ships as package data inside its
     top-level `code__code__jazz__kokoro__dz_debug` package.

The walk-up starts at this file, never at the working directory, so which directory you run
from does not change what config is found — which matters here more than for most units,
because this tool is DESIGNED to be run from the directory it writes into. Step 3 never
SHADOWS a nearer registry: it runs only after the walk-up has failed outright. If none of the
three answers, `stamp` raises `ConfigError`, naming all three sources that were tried. It
never guesses a default. That is `note-for-claude`'s rule and this ticket's acceptance item
(d).

`configure(config)` and `using_config(config)` inject a config object directly, in-process, for
callers that hold their configuration in memory rather than on disk.

The variable is named for THIS unit rather than something forge2-wide on purpose: it names a
file holding ONE unit's config object, so a variable shared across forge2 units could only ever
point at one unit's object at a time, and pointing it at a sibling's would break this one. The
sibling units in this package read `DZ_DEBUG_CONFIG`, `DZ_DEBUG_LOG_CONFIG` and
`DZ_DEBUG_INIT_CONFIG`; none of the four collide.

WHY STEP 3 EXISTS
-----------------
It is what makes a NON-editable `pip install .` work, and it was written because building this
package's wheel and installing it PROVED the unit broken without it — not on a hunch. In a
source checkout or an editable install, `ci/` sits INSIDE the package root next to
`registry.json`, so step 2 finds it one directory up. A non-editable install has no such root:
setuptools installs `ci/`, `dz_debug/` and `code__code__jazz__kokoro__dz_debug/` as three
SEPARATE top-level directories, and the registry ships as package data inside the third.
Walking up from an installed `ci/stamp_build.py` then reaches site-packages and beyond without
ever passing the registry, so without step 3 the unit throws `ConfigError` on a perfectly good
install. Step 3 asks the installed sibling package where it is, which is the only thing that
knows.

What `selftest` can check of that from inside a sandbox with no pip is stated exactly where it
is checked — see section [8]'s own NOTE, which says what it does and does not cover rather
than glossing it.

WHAT IS A SETTING, AND WHAT IS NOT
----------------------------------
#200 requires no hardcoded paths or params. This file draws the line in one place and states
it, so a reader can check it rather than guess:

  A value is a SETTING — and lives in the config object — if the ORIGINAL fixed it as a
  tunable: the six environment variable NAMES, the `required` list it checked them against,
  the output path, the `json.dumps` indent, the exit code it used for a missing variable, the
  two message layouts it printed, the separator it split VERSION on, the 8 characters of sha
  it previewed, and the nine JSON KEYS it wrote (and their order). No setting's VALUE is
  written in the code that runs, and that is checkable rather than asserted: `grep` this file
  for `"conf/env/build.json"`, `"VERSION"`, `"[err]"` or `[:8]`, and not one hit is a value
  this module USES. Every hit is one of five things —
    * `config_template()`, the template an operator installs;
    * `ORIGINAL_SOURCE`, the oracle's bytes;
    * `selftest`, which asserts against them;
    * a docstring or comment quoting the original so a reader can check the claim;
    * exactly one live string, in `_require_env`'s ConfigError: it quotes the
      `[err] missing env vars:` line to tell an operator which message their mis-configuration
      would have broken. It is help text about a value, not the value.
  The code between them reads every one of those settings out of the config object and has no
  opinion of its own.

  A value is CODE if changing it would change what the module MEANS rather than how it is
  tuned:
    * the nine ROLES and what each one is — that `build` and `pipeline` are `int()`s of their
      variables while `tag` and `branch` are strings, that `major` and `minor` are the first
      two parts of the split VERSION, that `built_at` is the current UTC time in ISO 8601;
    * the ORDER the roles are evaluated in. This is not cosmetic and it is not free: with a
      non-numeric BUILD *and* a non-numeric CI_PIPELINE_IID, the original fails on BUILD,
      because it converted that one first. `selftest` case `both-ints-bad` pins it;
    * that VERSION splits into exactly THREE parts, the third discarded. The arity is a
      literal `major, minor, _ = version.split(sep)` here for a concrete reason: it is what
      makes a mis-shaped VERSION raise CPython's OWN unpacking ValueError, word for word, on
      every Python. Hand-writing that message would have hard-coded one interpreter's
      wording — `"too many values to unpack (expected 3, got 4)"` is not what every CPython
      says. The separator is the tunable; the shape is the meaning;
    * that a missing variable is reported and nothing is written, that the parent directories
      are created, that the file is written with no trailing newline.
  Those are the unit's contract with its CI job and with every reader of build.json, and #200
  exists to stop them moving, not to make them configurable.

  The coupling between the two is CHECKED, not left to chance: every environment variable the
  config's `env` names must also appear in its `required_env` list, or a variable this module
  reads would go unchecked and raise a bare `KeyError` instead of the designed
  `[err] missing env vars:` line. A config that names one and forgets the other is rejected at
  load with a message naming it, rather than failing later at the first run. Likewise `fields`
  must cover every one of the nine roles exactly once, or the build.json would silently lose a
  key.

DELIBERATE, DOCUMENTED DIVERGENCES (three)
------------------------------------------
Everything else is intended to be indistinguishable, and that is measured, not asserted:
selftest section [3] runs every case against BOTH files as scripts and compares the results.

  1. THE WORK IS UNDER `if __name__ == "__main__"`, so IMPORTING this module stamps nothing,
     whereas importing the original would run it. This is forced by #200 itself and is not a
     free choice: requirement 3 asks for a package with console entry points, and an entry
     point is a name that gets imported and then called — a module that does its work at
     import time would stamp once on import and again on call. It could not be tested, and it
     could not even be imported by the config gate that requirement 4 asks for. The behavior
     the original's one caller depends on — `python3 ci/stamp_build.py` — is unchanged, and
     that is what selftest compares.
  2. THE COMMAND LINE. The original ignored `sys.argv` entirely. This file accepts optional
     subcommands (`stamp`, `emit-config`, `show-config`, `selftest`). Invoked with NO
     arguments it stamps, which is the original's behavior and the form the CI job uses;
     `stamp` names that explicitly. Passing an argument the original would have ignored is now
     an argparse error, exit 2.
  3. AN UNEXPECTED EXCEPTION FILES A BUG REPORT. `note-for-claude` requires that "all tools
     need to pass a bug-report automatically (timestamped if an exception is thrown)", so a
     failure the original let escape as a traceback — a non-numeric BUILD, a mis-shaped
     VERSION — additionally appends one JSON line to the config's `bug_reports` path and
     prints one line naming it. The exception is then RE-RAISED untouched, so the exception
     type, its message and the exit code are the original's exactly; only the extra file and
     that one stderr line are new. This is the one place this rewrite writes something the
     original would not have, and it is required rather than incidental. A `ConfigError` is
     designed behavior, not a bug: it files no report and prints no traceback, and exits 2
     with a single self-explaining line.

THE PROOF (acceptance item (a))
-------------------------------
#367 captured NO behavioral exemplars, and says what that means: "you must write the
equivalence exemplars by hand from the original's behavior before rewriting, and they are what
settles this ticket." So `selftest` does not compare against hand-copied expectations, where a
mistake in the copy passes silently. It compares against THE ORIGINAL ITSELF:

  * `ORIGINAL_SOURCE` below holds the ticket's embedded bytes verbatim. The selftest checks
    them against the ticket's stated SIZE (1403) **and recomputes the git blob sha1** and
    checks it against the one the ticket names (4916d8f6...). A blob sha1 is a hash of the
    bytes, so that check cannot pass unless the oracle is the forge's file, byte for byte — it
    is what makes everything below a comparison against the real original.
  * Both files are planted in temp directories, run as scripts under the SAME environment, and
    compared on everything a caller can see: the exit code, stdout byte for byte, stderr, and
    the exact bytes of the build.json produced — plus the full list of files each run created,
    so a stray write cannot hide.
  * Two things are normalized, because they are the only two that legitimately differ between
    two runs of the SAME program: the `built_at` timestamp, and the file paths and line numbers
    inside a traceback (compared as exception type + message + exit code, which is what a
    caller actually sees). Both normalizations are stated at the point they are applied.

Everything it creates lives in a temp directory it removes. It runs no pip and writes nothing
outside that temp directory — which matters, because the ORIGINAL writes `conf/env/build.json`
into the CURRENT directory and a careless oracle would have stamped this checkout.

RUNNING IT
----------
Every command is executable as written from this file's directory or from the package root
above it; from anywhere else give the full path to `stamp_build.py`.

    python3 ci/stamp_build.py                # stamp — exactly what the original does
    python3 ci/stamp_build.py stamp          # the same thing, named
    python3 ci/stamp_build.py selftest       # prove the behavior against the ORIGINAL's bytes
    python3 ci/stamp_build.py emit-config    # print a config-object template
    python3 ci/stamp_build.py show-config    # print the resolved config + where it came from

`selftest` and `emit-config` need no config object; `stamp` and `show-config` throw without
one, exiting 2 with a single self-explaining line and no traceback.

INSTALLABLE (#200 requirement 3 — acceptance item (c))
------------------------------------------------------
This file is one module of the package that surrounds it, committed in full beside it. From
the PACKAGE ROOT (the directory above this one, holding `pyproject.toml`):

    python3 -m venv .venv && .venv/bin/pip install -e .
    .venv/bin/forge2-dz-debug-stamp-build selftest

The venv is not decoration — a bare `pip install -e .` on a system Python managed by a package
manager is refused with "externally-managed-environment" (PEP 668), which is that Python's
rule and nothing to do with this package.

`pyproject.toml` declares `ci` as an import package, so the console script can resolve
`ci.stamp_build:main`. `ci` has no `__init__.py` — it is a PEP 420 namespace package — for the
same reason `dz_debug` next door has none: this ticket covers ONE module, and inventing an
`__init__.py` for a directory whose other files are not here would be work no ticket
authorized. `python3 ci/stamp_build.py` and `import ci.stamp_build` both work either way.

SIDE EFFECTS
------------
Importing this module resolves NO config, reads NO file and writes NO file. Running it (the
`stamp` command, or no command at all) creates the output path's parent directories and writes
the output file — which is the original's behavior and the point of the unit. On a MISSING
environment variable it writes nothing at all, exactly as the original does; the directories
are created only after every value has been converted successfully.

(CPython writes its own `__pycache__/*.pyc` when it imports this file, as it does for any
module; that is the interpreter's doing and `.gitignore` excludes it.)
"""

import contextlib
import importlib.util
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    # ── the config surface this rewrite adds (#200 requirement 4) ──
    "CONFIG_ENV",
    "ConfigError",
    "REGISTRY_NAME",
    "REQUIRED_KEYS",
    "ROLES",
    "SHIPPING_PKG",
    "UNIT",
    "UNIT_PATH",
    "active_base",
    "active_config",
    "active_source",
    "build_config",
    "config_template",
    "configure",
    "find_registry",
    "load_config",
    "main",
    "reset_config",
    "selftest",
    "shipped_registry",
    "stamp",
    "using_config",
]

#: The ORIGINAL unit's bytes, quoted verbatim from ticket #367's embedded source block. This is
#: the behavior-preserving basis and `selftest`'s ORACLE: it is written to disk and RUN, so the
#: rewrite is compared against the original executing, not against a description of it.
#: `selftest` recomputes its git blob sha1 and checks it against ORIGINAL_BLOB below, so a
#: transcription slip here cannot silently weaken the proof.
#:
#: It is a RAW triple-single-quoted string: raw so that any backslash in the original stays the
#: character it is in the file, and single-quoted so the original's `"""` docstring needs no
#: escaping. The result is the file's bytes, unaltered.
ORIGINAL_SOURCE = r'''#!/usr/bin/env python3

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 testmonkeyalpha — Claude & Co.

"""
ci/stamp_build.py — write conf/env/build.json from environment variables.

Called by .gitlab-ci.yml version stage.
Required env vars: VERSION, TAG, BUILD, CI_COMMIT_SHA, CI_COMMIT_BRANCH, CI_PIPELINE_IID
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

required = ["VERSION", "TAG", "BUILD", "CI_COMMIT_SHA", "CI_COMMIT_BRANCH", "CI_PIPELINE_IID"]
missing  = [k for k in required if not os.environ.get(k)]
if missing:
    print(f"[err] missing env vars: {', '.join(missing)}", file=sys.stderr)
    sys.exit(1)

version  = os.environ["VERSION"]
tag      = os.environ["TAG"]
build    = int(os.environ["BUILD"])
sha      = os.environ["CI_COMMIT_SHA"]
branch   = os.environ["CI_COMMIT_BRANCH"]
pipeline = int(os.environ["CI_PIPELINE_IID"])

major, minor, _ = version.split(".")

data = {
    "version":  version,
    "tag":      tag,
    "build":    build,
    "major":    int(major),
    "minor":    int(minor),
    "sha":      sha,
    "branch":   branch,
    "pipeline": pipeline,
    "built_at": datetime.now(timezone.utc).isoformat(),
}

out = Path("conf/env/build.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(data, indent=2))
print(f"  stamped build.json: {version}  tag={tag}  sha={sha[:8]}")
'''

#: The ticket's stated SIZE for the original module, in bytes.
ORIGINAL_SIZE = 1403

#: The ticket's stated git blob sha1 for the original module. `selftest` recomputes this over
#: ORIGINAL_SOURCE. A git blob sha1 is sha1("blob <len>\0" + bytes), so it pins both the length
#: and every byte — the oracle cannot drift from the forge's file without this failing.
ORIGINAL_BLOB = "4916d8f6a3b9439bad5c1767adb58df3c6131587"

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "DZ_DEBUG_STAMP_BUILD_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: This distribution's top-level package, which ships `registry.json` as package data (see
#: pyproject.toml's `[tool.setuptools.package-data]`). Consulted only when the walk-up finds
#: nothing, which is the non-editable-install case — see WHY STEP 3 EXISTS in the docstring.
SHIPPING_PKG = "code__code__jazz__kokoro__dz_debug"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in
#: the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own. The last component is the module's stem, which is the address the
#: sibling units in this package use (`log`, `logger`, `__init__`).
UNIT_PATH = ("forge2", "code__code__jazz__kokoro__dz_debug", "stamp_build")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code__jazz__kokoro__dz_debug/ci/stamp_build"

#: The nine values this module computes — the keys of the ORIGINAL's `data` dict. A role is
#: CODE, not a setting: see WHAT IS A SETTING in the module docstring. Listing them here is what
#: lets a `fields` list that drops one be rejected at load, naming it, instead of silently
#: writing a build.json with a key missing.
ROLES = ("version", "tag", "build", "major", "minor", "sha", "branch", "pipeline", "built_at")

#: The roles read straight out of the environment, so the config's `env` section must name a
#: variable for each. `major`/`minor` are derived from `version` and `built_at` from the clock,
#: so none of the three has an environment variable.
ENV_ROLES = ("version", "tag", "build", "sha", "branch", "pipeline")

#: Each `formats` template and the fields it may use. The dummy values are what `build_config`
#: test-formats the template with, so a config that misspells a field is rejected at load with a
#: message naming the fields — rather than raising KeyError from inside a run later.
FORMAT_FIELDS = {
    "missing_env": {"missing": "X"},
    "stamped": {"version": "v", "tag": "t", "sha_preview": "s"},
}

#: `formats.missing_join` is validated apart from FORMAT_FIELDS: it is a separator, not a
#: template, so test-formatting it would be meaningless. The empty string is a legitimate value.
JOIN_FORMAT_KEY = "missing_join"

#: The sections a config object must carry. Named here so a missing one can list them all.
REQUIRED_KEYS = ("required_env", "env", "fields", "output", "indent", "version_separator",
                 "sha_preview_chars", "exit_code_missing_env", "formats")


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or malformed.

    This is the #200 requirement-4 gate and ticket #367's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.

    It is deliberately NOT raised for the ORIGINAL's own errors, which are reproduced exactly:
    a non-numeric BUILD or CI_PIPELINE_IID still raises `ValueError` with CPython's own
    "invalid literal for int()" message, and a VERSION that does not split into three parts
    still raises CPython's own unpacking `ValueError`. Reproducing those exactly is what
    acceptance item (a) asks for, and dressing them up as ConfigError would change what a
    caller's `except` catches and what the CI job's log shows.
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do every run of this module throws. Every value below
    is a transcription of something the ORIGINAL module hardcoded — its `required` list, the
    six `os.environ[...]` names, the nine keys of its `data` dict in its order, the path it
    wrote, the indent it dumped with, the exit code it used, the separator it split VERSION on,
    the 8 characters of sha it previewed, and its two message layouts. Making them data rather
    than source is #200 requirement 4; keeping them EQUAL to the original's is what makes the
    rewrite behavior-preserving.
    """
    return {
        # ── the ORIGINAL's `required` list, in its order. The order is the order the
        #    `[err] missing env vars:` line names them in. ──
        "required_env": ["VERSION", "TAG", "BUILD", "CI_COMMIT_SHA", "CI_COMMIT_BRANCH",
                         "CI_PIPELINE_IID"],
        # ── the six `os.environ[...]` names, by the role each one feeds ──
        "env": {
            "version": "VERSION",
            "tag": "TAG",
            "build": "BUILD",
            "sha": "CI_COMMIT_SHA",
            "branch": "CI_COMMIT_BRANCH",
            "pipeline": "CI_PIPELINE_IID",
        },
        # ── the nine keys of the ORIGINAL's `data` dict, in its order. `key` is what is
        #    written to build.json; `role` is what this module computes for it. ──
        "fields": [
            {"key": "version", "role": "version"},
            {"key": "tag", "role": "tag"},
            {"key": "build", "role": "build"},
            {"key": "major", "role": "major"},
            {"key": "minor", "role": "minor"},
            {"key": "sha", "role": "sha"},
            {"key": "branch", "role": "branch"},
            {"key": "pipeline", "role": "pipeline"},
            {"key": "built_at", "role": "built_at"},
        ],
        # ── `out = Path("conf/env/build.json")`. Relative, and resolved against the working
        #    directory exactly as the original's literal was — see `load_config`. ──
        "output": "conf/env/build.json",
        # ── `json.dumps(data, indent=2)` ──
        "indent": 2,
        # ── `version.split(".")` ──
        "version_separator": ".",
        # ── `sha[:8]` ──
        "sha_preview_chars": 8,
        # ── `sys.exit(1)` on a missing variable ──
        "exit_code_missing_env": 1,
        # ── the layouts the ORIGINAL formatted its two messages with ──
        "formats": {
            "missing_env": "[err] missing env vars: {missing}",
            "missing_join": ", ",
            "stamped": "  stamped build.json: {version}  tag={tag}  sha={sha_preview}",
        },
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────────────── reading the config ───────────────────────────────

def shipped_registry():
    """Return the path of the `registry.json` this distribution ships as package data, or None.

    Asks the installed `code__code__jazz__kokoro__dz_debug` package where it lives. This is the
    only way to find the registry from a NON-editable install, where it is not on any path above
    this file — see WHY STEP 3 EXISTS in the module docstring.

    Uses `find_spec` rather than importing: locating a file must not run a sibling package's
    code. Returns None rather than raising if the package is absent (a `ci/` vendored on its
    own, say), so the caller can report the whole picture at once.
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


def _strip_comments(section):
    """Drop the registry's `_comment` keys, which document a section rather than configure it."""
    return {k: v for k, v in section.items() if not k.startswith("_comment")}


def load_config(start=None):
    """Resolve this unit's config object from disk, ignoring any injected config.

    Returns a `(config, base, source)` triple: the config object, the directory the registry was
    found in, and a human-readable description of where the config came from. `start` overrides
    the directory the registry walk-up begins at.

    `base` is NOT used to rebase `output`. That path is handed to `Path` the way the ORIGINAL
    handed its own literal, so a relative one is relative to the WORKING DIRECTORY exactly as
    the original's `Path("conf/env/build.json")` was. Rebasing it would break the unit's one
    caller: the `.gitlab-ci.yml` version stage runs this from the checkout root and expects the
    file under that root, not under wherever the registry happens to live. `base` is
    package-wide infrastructure only: it is what the CLI resolves `bug_reports` against.

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
            "no config object for %s. All three sources were tried and none answered: (1) $%s "
            "is unset; (2) no %s was found by walking up from %s; (3) %s. Run "
            "`forge2-dz-debug-stamp-build emit-config` for a template of the config object to "
            "install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))),
               _shipping_pkg_status()))

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. "
                "Run `forge2-dz-debug-stamp-build emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH)))
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError("the registry section %s at %s must be a JSON object, not %s"
                          % (".".join(UNIT_PATH), registry_path, type(node).__name__))

    config = _strip_comments(node)
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit
    # section may state its own to override it. This is inheritance inside ONE config document,
    # not a guessed default — if neither states it, the key stays absent and the CLI files no
    # report.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


# ─────────────────────────── validating the config object ───────────────────────────
#
# Every failure below is a `ConfigError` that names the key, says what was wrong with it, and
# points at `emit-config`. That is Theme 5 of the playbook applied to a config file: the
# operator who mistyped it is not reading this source, so the message has to carry the answer.

def _require_key(config, key):
    if not isinstance(config, dict):
        raise ConfigError("the config object for %s must be a JSON object, not %s"
                          % (UNIT, type(config).__name__))
    if key not in config:
        raise ConfigError("the config object for %s is missing the required key %r. The "
                          "required keys are: %s. Run `forge2-dz-debug-stamp-build emit-config` "
                          "for a template." % (UNIT, key, ", ".join(REQUIRED_KEYS)))
    return config[key]


def _require_int(config, key):
    """An integer setting. `bool` is refused though it is an `int` subclass: a config saying
    `"indent": true` is an operator mistake, and `json.dumps(indent=True)` would silently indent
    by one space rather than fail."""
    value = _require_key(config, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("config key %r for %s must be an integer, not %s"
                          % (key, UNIT, type(value).__name__))
    return value


def _require_str(config, key):
    value = _require_key(config, key)
    if not isinstance(value, str) or not value:
        raise ConfigError("config key %r for %s must be a non-empty string; got %r"
                          % (key, UNIT, value))
    return value


def _require_required_env(config):
    """The `required_env` list: the ORIGINAL's `required`. Its ORDER is the order the missing
    line names them in, so it is preserved as given."""
    names = _require_key(config, "required_env")
    if not isinstance(names, list) or not names:
        raise ConfigError("config key 'required_env' for %s must be a non-empty JSON array of "
                          "environment variable names, not %s"
                          % (UNIT, type(names).__name__ if not isinstance(names, list)
                             else "an empty array"))
    seen = []
    for index, name in enumerate(names):
        if not isinstance(name, str) or not name:
            raise ConfigError("config key 'required_env[%d]' for %s must be a non-empty string; "
                              "got %r" % (index, UNIT, name))
        if name in seen:
            raise ConfigError("config key 'required_env' for %s names %r twice" % (UNIT, name))
        seen.append(name)
    return tuple(seen)


def _require_env(config, required_env):
    """The `env` section: role -> environment variable name, for the six roles read from it.

    Every variable named here must also be in `required_env`. That coupling is checked rather
    than hoped for: an `env` entry the `required_env` list forgets would be read with
    `environ[name]` after the missing-check has already passed, so a caller who left it unset
    would get a bare `KeyError` traceback instead of the designed `[err] missing env vars:`
    line. See WHAT IS A SETTING in the module docstring.
    """
    section = _require_key(config, "env")
    if not isinstance(section, dict):
        raise ConfigError("config key 'env' for %s must be a JSON object mapping each role to "
                          "an environment variable name, not %s" % (UNIT, type(section).__name__))
    section = _strip_comments(section)
    resolved = {}
    for role in ENV_ROLES:
        if role not in section:
            raise ConfigError("config key 'env' for %s does not name an environment variable for "
                              "the %r role. It must name one for every one of: %s. Run "
                              "`forge2-dz-debug-stamp-build emit-config` for a template."
                              % (UNIT, role, ", ".join(ENV_ROLES)))
        name = section[role]
        if not isinstance(name, str) or not name:
            raise ConfigError("config key 'env.%s' for %s must be a non-empty environment "
                              "variable name; got %r" % (role, UNIT, name))
        if name not in required_env:
            raise ConfigError(
                "config key 'env.%s' for %s names the environment variable %r, which the "
                "config's 'required_env' list does not check for. Every variable this module "
                "reads must be in 'required_env' (%s), or leaving it unset would raise a bare "
                "KeyError instead of the '%s' line."
                % (role, UNIT, name, ", ".join(required_env), "[err] missing env vars: ..."))
        resolved[role] = name
    for extra in section:
        if extra not in ENV_ROLES:
            raise ConfigError("config key 'env' for %s names %r, which is not a role this module "
                              "reads from the environment. The roles are: %s."
                              % (UNIT, extra, ", ".join(ENV_ROLES)))
    return resolved


def _require_fields(config):
    """The `fields` list: the ORIGINAL's `data` dict, as (JSON key, role) in write order.

    Must cover every role exactly once — a missing one would silently drop a key from the
    build.json every downstream reader depends on, and a duplicated one would make which value
    wins depend on the order of the list.
    """
    fields = _require_key(config, "fields")
    if not isinstance(fields, list) or not fields:
        raise ConfigError('config key \'fields\' for %s must be a non-empty JSON array of '
                          '{"key", "role"} objects, not %s'
                          % (UNIT, type(fields).__name__ if not isinstance(fields, list)
                             else "an empty array"))
    resolved = []
    keys_seen = {}
    roles_seen = {}
    for index, entry in enumerate(fields):
        where = "config key 'fields[%d]' for %s" % (index, UNIT)
        if not isinstance(entry, dict):
            raise ConfigError("%s must be an object with 'key' and 'role', not %s"
                              % (where, type(entry).__name__))
        key = entry.get("key")
        if not isinstance(key, str) or not key:
            raise ConfigError("%s must have a non-empty string 'key' (the name it is written "
                              "under in the output JSON); got %r" % (where, key))
        role = entry.get("role")
        if role not in ROLES:
            raise ConfigError("%s ('key': %r) has role %r, which this module does not compute. "
                              "The roles are: %s." % (where, key, role, ", ".join(ROLES)))
        if key in keys_seen:
            raise ConfigError("config key 'fields' for %s writes the output key %r twice — for "
                              "the %r role and the %r role. Each output key must be written "
                              "once, or which value wins would depend on the order of the list."
                              % (UNIT, key, keys_seen[key], role))
        if role in roles_seen:
            raise ConfigError("config key 'fields' for %s writes the %r role twice — as %r and "
                              "as %r. Each role must be written exactly once."
                              % (UNIT, role, roles_seen[role], key))
        keys_seen[key] = role
        roles_seen[role] = key
        resolved.append((key, role))
    for role in ROLES:
        if role not in roles_seen:
            raise ConfigError("config key 'fields' for %s never writes the %r role, so the "
                              "output JSON would silently lose it. It must write every one of: "
                              "%s. Run `forge2-dz-debug-stamp-build emit-config` for a template."
                              % (UNIT, role, ", ".join(ROLES)))
    return tuple(resolved)


def _require_formats(config):
    """The `formats` section: the layouts the ORIGINAL printed its two messages with."""
    section = _require_key(config, "formats")
    if not isinstance(section, dict):
        raise ConfigError("config key 'formats' for %s must be a JSON object, not %s"
                          % (UNIT, type(section).__name__))
    section = _strip_comments(section)
    formats = {}
    for key in list(FORMAT_FIELDS) + [JOIN_FORMAT_KEY]:
        where = "config key 'formats.%s' for %s" % (key, UNIT)
        if key not in section:
            raise ConfigError("%s is missing. The required templates are: %s. Run "
                              "`forge2-dz-debug-stamp-build emit-config` for a template."
                              % (where, ", ".join(list(FORMAT_FIELDS) + [JOIN_FORMAT_KEY])))
        value = section[key]
        # missing_join is a separator, not a template: the empty string is legitimate for it.
        if not isinstance(value, str) or (not value and key != JOIN_FORMAT_KEY):
            raise ConfigError("%s must be a non-empty string, not %r" % (where, value))
        formats[key] = value
    # Test-format each template with dummy fields, so a misspelled field is a ConfigError naming
    # the fields rather than a KeyError from inside a run later.
    for key, dummies in FORMAT_FIELDS.items():
        try:
            formats[key].format(**dummies)
        except (KeyError, IndexError, ValueError) as exc:
            raise ConfigError("config key 'formats.%s' for %s is not a usable template (%s: %s). "
                              "The fields it may use are: %s."
                              % (key, UNIT, type(exc).__name__, exc,
                                 ", ".join("{%s}" % f for f in dummies))) from exc
    return formats


def build_config(config):
    """Validate a config object and return this module's operating settings.

    Returns a dict with one key per section of the config object, with every value checked, and
    the cross-section couplings this module depends on (every variable it reads is checked for;
    every role it computes is written) proven here, once, at load — rather than failing later
    mid-run, after some of the work has already been done.

    This is a pure function of its argument: it reads no file, no environment variable and no
    module state, so `build_config(json.load(open(...)))` is the whole of the check and the
    selftest can drive it with any config object it likes.

    Raises:
        ConfigError: naming the key, what was wrong with it, and how to print a template.
    """
    required_env = _require_required_env(config)
    return {
        "required_env": required_env,
        "env": _require_env(config, required_env),
        "fields": _require_fields(config),
        "output": _require_str(config, "output"),
        "indent": _require_int(config, "indent"),
        "version_separator": _require_str(config, "version_separator"),
        "sha_preview_chars": _require_int(config, "sha_preview_chars"),
        "exit_code_missing_env": _require_int(config, "exit_code_missing_env"),
        "formats": _require_formats(config),
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
    """Return the directory the registry was found in.

    This is what the CLI resolves a relative `bug_reports` path against. It is deliberately NOT
    applied to `output` — see `load_config`.
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

    Unlike this package's `dz_debug.log`, injecting a config here re-configures the module for
    every LATER call: `stamp()` resolves its config when it runs, not at import, because the
    original resolved its own literals when it ran — it was a script, and running it was the
    only thing it did.
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


# ─────────────────────────────── the unit ───────────────────────────────

def stamp(environ=None, config=None, stdout=None, stderr=None):
    """Write the build document from the environment. Returns a process exit code.

    This is the ORIGINAL's module-level code, rewritten: every literal it held is now read from
    the config object, and nothing else about what it does has moved. The arguments exist so the
    selftest can drive it without a subprocess; every one of them defaults to what the original
    used.

    Args:
        environ: the environment to read (default: `os.environ`).
        config: the config object to obey (default: the config in force — see `active_config`).
        stdout: where the confirmation line goes (default: `sys.stdout`).
        stderr: where the missing-variables line goes (default: `sys.stderr`).

    Returns:
        0 after writing the document; the config's `exit_code_missing_env` if any required
        variable is unset or empty, in which case NOTHING is written — not even the output
        directory.

    Raises:
        ConfigError: if there is no config object, or it is malformed. Raised before anything is
            read or written.
        ValueError: exactly as the original does — CPython's own "invalid literal for int()" for
            a non-numeric BUILD or CI_PIPELINE_IID (in that order), and CPython's own unpacking
            message for a VERSION that does not split into three parts.
    """
    spec = build_config(active_config() if config is None else config)
    env = os.environ if environ is None else environ
    out_stream = sys.stdout if stdout is None else stdout
    err_stream = sys.stderr if stderr is None else stderr

    # `not env.get(k)` — an EMPTY variable counts as missing, exactly as the original's
    # `not os.environ.get(k)` did. `required_env`'s order is the order they are named in.
    missing = [name for name in spec["required_env"] if not env.get(name)]
    if missing:
        print(spec["formats"]["missing_env"].format(
            missing=spec["formats"][JOIN_FORMAT_KEY].join(missing)), file=err_stream)
        return spec["exit_code_missing_env"]

    # The order of the next four statements is the ORIGINAL's and is load-bearing: with both
    # BUILD and CI_PIPELINE_IID non-numeric, the error names BUILD, because BUILD converts
    # first; with a bad CI_PIPELINE_IID and a mis-shaped VERSION, the error names the pipeline,
    # because the conversions all precede the split. See WHAT IS A SETTING in the docstring.
    names = spec["env"]
    version = env[names["version"]]
    tag = env[names["tag"]]
    build = int(env[names["build"]])
    sha = env[names["sha"]]
    branch = env[names["branch"]]
    pipeline = int(env[names["pipeline"]])

    # A literal three-way unpack, so a mis-shaped VERSION raises CPython's own ValueError word
    # for word on every Python. The separator is config; the shape is what the unit means.
    major, minor, _ = version.split(spec["version_separator"])

    values = {
        "version": version,
        "tag": tag,
        "build": build,
        "major": int(major),
        "minor": int(minor),
        "sha": sha,
        "branch": branch,
        "pipeline": pipeline,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    data = {key: values[role] for key, role in spec["fields"]}

    # `Path(...)` on the config's path verbatim — a relative one is relative to the working
    # directory, exactly as the original's literal was. See `load_config` on why it is not
    # rebased against the registry.
    out = Path(spec["output"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=spec["indent"]))
    print(spec["formats"]["stamped"].format(
        version=version, tag=tag, sha_preview=sha[:spec["sha_preview_chars"]]), file=out_stream)
    return 0


# ─────────────────────────────── the proof ───────────────────────────────

def _blob_sha1(text):
    """The git blob sha1 of `text`: sha1("blob <len>\\0" + utf-8 bytes). What `git hash-object`
    computes, and what the ticket names — so this pins the oracle to the forge's actual file."""
    import hashlib

    raw = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest()


def _normalize_built_at(text, fields):
    """Replace the `built_at` TIMESTAMP in a build.json with a fixed marker, changing nothing else.

    The clock is the ONLY thing that legitimately differs between two runs of the same stamper:
    the original and the rewrite run milliseconds apart. `fields` says which output key carries
    the role, so this normalizes whatever key the config wrote it under.

    This is a TEXTUAL substitution, deliberately: re-parsing the JSON and re-dumping it would
    also normalize the indent, the separators and the trailing newline — the very things the
    comparison is supposed to catch. A rewrite that wrote `indent=4`, or that added a trailing
    newline the original does not write, would then have compared EQUAL. Substituting in place
    leaves every other byte to be compared as-is.
    """
    import re

    key = dict((role, k) for k, role in fields).get("built_at", "built_at")
    return re.sub(r'("%s"\s*:\s*)"[^"]*"' % re.escape(key), r'\1"<built_at>"', text)


def _tree(root):
    """Every path created under `root`, relative and sorted — so a stray write cannot hide."""
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*"))


def _last_line(text):
    """The last non-empty line of a traceback: the `ValueError: ...` a caller actually reads.

    Tracebacks are compared this way rather than byte for byte because the two files sit at
    different paths and the same error is raised from different line numbers — the frames differ
    for reasons that are not behavior. The exception TYPE and MESSAGE are behavior, and they are
    on this line.
    """
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def selftest(stream=None):
    """Prove this rewrite against the ORIGINAL's own bytes. Returns the number of failures.

    Needs no config object. Creates nothing outside a temp directory it removes, runs no pip and
    needs no network.
    """
    import shutil
    import subprocess
    import tempfile

    out = stream or sys.stdout
    failures = []
    checks = [0]

    def ck(label, ok, detail=""):
        checks[0] += 1
        print("  %s  %s%s" % ("PASS" if ok else "FAIL", label,
                              "" if ok else "  <- %s" % detail), file=out)
        if not ok:
            failures.append("%s: %s" % (label, detail))

    workdir = tempfile.mkdtemp(prefix="stamp_build_selftest_")
    try:
        # ── [1] the oracle is the forge's file, byte for byte ──
        print("\n[1] the ORACLE — is ORIGINAL_SOURCE really the forge's bytes?", file=out)
        ck("ORIGINAL_SOURCE is %d bytes (the ticket's SIZE)" % ORIGINAL_SIZE,
           len(ORIGINAL_SOURCE.encode("utf-8")) == ORIGINAL_SIZE,
           "got %d" % len(ORIGINAL_SOURCE.encode("utf-8")))
        actual_blob = _blob_sha1(ORIGINAL_SOURCE)
        ck("its git blob sha1 is the ticket's %s" % ORIGINAL_BLOB,
           actual_blob == ORIGINAL_BLOB, "got %s" % actual_blob)

        original = os.path.join(workdir, "original", "stamp_build.py")
        os.makedirs(os.path.dirname(original), exist_ok=True)
        with open(original, "w", encoding="utf-8") as handle:
            handle.write(ORIGINAL_SOURCE)
        rewrite = os.path.abspath(__file__)

        # The config that says exactly what the original hardcoded. Pointing $CONFIG_ENV at it
        # is how the rewrite is driven, so the two runs are configured identically by
        # construction rather than by hand-copying.
        config_path = os.path.join(workdir, "config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(config_template(), handle)
        fields = _require_fields(config_template())

        # ── [2] the config object the template prints is a valid one ──
        print("\n[2] the CONFIG TEMPLATE — does emit-config print something that loads?", file=out)
        try:
            spec = build_config(config_template())
            ck("build_config() accepts the template", True)
            ck("its required_env is the ORIGINAL's `required` list, in order",
               list(spec["required_env"]) == ["VERSION", "TAG", "BUILD", "CI_COMMIT_SHA",
                                              "CI_COMMIT_BRANCH", "CI_PIPELINE_IID"],
               str(spec["required_env"]))
            ck("its output is the ORIGINAL's path", spec["output"] == "conf/env/build.json",
               spec["output"])
            ck("its indent is the ORIGINAL's 2", spec["indent"] == 2, str(spec["indent"]))
            ck("its sha preview is the ORIGINAL's 8", spec["sha_preview_chars"] == 8,
               str(spec["sha_preview_chars"]))
            ck("its fields write the ORIGINAL's nine keys, in order",
               [k for k, _ in spec["fields"]] == ["version", "tag", "build", "major", "minor",
                                                  "sha", "branch", "pipeline", "built_at"],
               str([k for k, _ in spec["fields"]]))
        except ConfigError as exc:
            ck("build_config() accepts the template", False, str(exc))

        # ── [3] the differential run: BOTH files, as scripts, same environment ──
        print("\n[3] EQUIVALENCE — every case run against BOTH files as scripts", file=out)
        good = {"VERSION": "1.2.3", "TAG": "v1.2.3", "BUILD": "42",
                "CI_COMMIT_SHA": "abcdef1234567890deadbeef", "CI_COMMIT_BRANCH": "main",
                "CI_PIPELINE_IID": "7"}

        def scenario(**overrides):
            env = dict(good)
            for key, value in overrides.items():
                if value is None:
                    env.pop(key, None)
                else:
                    env[key] = value
            return env

        def run(script, env, extra=None):
            """Run one script in a private directory and report everything a caller can see."""
            cwd = tempfile.mkdtemp(dir=workdir)
            full = {k: v for k, v in os.environ.items()
                    if k not in good and k != CONFIG_ENV}
            full.update(env)
            if extra:
                full.update(extra)
            proc = subprocess.run([sys.executable, script], cwd=cwd, env=full,
                                  capture_output=True, text=True)
            produced = os.path.join(cwd, "conf", "env", "build.json")
            body = None
            if os.path.isfile(produced):
                with open(produced, "r", encoding="utf-8") as handle:
                    body = _normalize_built_at(handle.read(), fields)
            return {"rc": proc.returncode, "stdout": proc.stdout,
                    "stderr_last": _last_line(proc.stderr), "file": body, "tree": _tree(cwd)}

        cases = [
            ("happy-path", scenario()),
            ("version-missing", scenario(VERSION=None)),
            ("version-and-tag-empty", scenario(VERSION="", TAG="")),
            ("all-six-missing", scenario(**dict.fromkeys(good, None))),
            ("sha-missing-only", scenario(CI_COMMIT_SHA=None)),
            ("build-not-an-int", scenario(BUILD="abc")),
            ("pipeline-not-an-int", scenario(CI_PIPELINE_IID="xyz")),
            ("both-ints-bad", scenario(BUILD="zzz", CI_PIPELINE_IID="xyz")),
            ("version-two-parts", scenario(VERSION="1.2")),
            ("version-four-parts", scenario(VERSION="1.2.3.4")),
            ("version-one-part", scenario(VERSION="1")),
            ("major-minor-not-ints", scenario(VERSION="a.b.c")),
            ("pipeline-bad-and-version-bad", scenario(VERSION="x.y.z", CI_PIPELINE_IID="nope")),
            ("build-padded-with-spaces", scenario(BUILD=" 42 ")),
            ("build-zero", scenario(BUILD="0")),
            ("signed-ints", scenario(BUILD="+7", CI_PIPELINE_IID="-3")),
            ("sha-shorter-than-preview", scenario(CI_COMMIT_SHA="abc")),
            ("sha-exactly-eight", scenario(CI_COMMIT_SHA="abcdefgh")),
            ("branch-with-slash", scenario(CI_COMMIT_BRANCH="feature/x")),
            ("version-with-suffix", scenario(VERSION="1.2.3-rc1")),
            ("unicode-tag", scenario(TAG="v1.2.3-café")),
            ("big-numbers", scenario(BUILD="999999999999", CI_PIPELINE_IID="2147483647")),
        ]
        for label, env in cases:
            want = run(original, env)
            got = run(rewrite, env, extra={CONFIG_ENV: config_path})
            same = (want["rc"] == got["rc"] and want["stdout"] == got["stdout"]
                    and want["stderr_last"] == got["stderr_last"] and want["file"] == got["file"]
                    and want["tree"] == got["tree"])
            ck("%-28s rc/stdout/stderr/file/tree all match" % label, same,
               "\n        original=%r\n        rewrite =%r" % (want, got))

        # ── [3b] the one write the original would not do, measured ──
        # In the cases above, the rewrite's bug report lands beside its config file, which is
        # OUTSIDE each run's directory — that is why the tree comparison came out clean. That
        # would be a free pass if it were left there, so here the report is aimed INTO a
        # directory that is watched, and the whole of the difference is measured.
        print("\n[3b] THE ONE EXTRA WRITE — note-for-claude's bug report (DIVERGENCE 3)", file=out)
        bug_home = os.path.join(workdir, "bugs")
        os.makedirs(bug_home, exist_ok=True)
        bug_config = dict(config_template())
        bug_config["bug_reports"] = os.path.join(bug_home, "logs", "bug_reports.jsonl")
        bug_config_path = os.path.join(bug_home, "config.json")
        with open(bug_config_path, "w", encoding="utf-8") as handle:
            json.dump(bug_config, handle)
        env = scenario(BUILD="abc")
        want = run(original, env)
        got = run(rewrite, env, extra={CONFIG_ENV: bug_config_path})
        ck("a non-numeric BUILD still exits %d, exactly as the ORIGINAL" % want["rc"],
           got["rc"] == want["rc"], "original=%r rewrite=%r" % (want["rc"], got["rc"]))
        ck("...and still raises the ORIGINAL's exact exception (%s)" % want["stderr_last"],
           got["stderr_last"] == want["stderr_last"], got["stderr_last"])
        ck("...and still writes NO build document, exactly as the ORIGINAL",
           got["file"] is None and got["tree"] == want["tree"], str(got["tree"]))
        report = bug_config["bug_reports"]
        lines = []
        if os.path.isfile(report):
            with open(report, "r", encoding="utf-8") as handle:
                lines = [line for line in handle.read().splitlines() if line.strip()]
        ck("...and files EXACTLY ONE bug report — the whole of the divergence", len(lines) == 1,
           "%d line(s) at %s" % (len(lines), report))
        if lines:
            entry = json.loads(lines[0])
            ck("the report carries note-for-claude's five required fields",
               all(k in entry for k in ("filename", "function", "time-of-occurance",
                                        "methods-to-reproduce", "possible-cause")),
               str(sorted(entry)))

        # ── [4] the surface the ticket names ──
        print("\n[4] THE CALLABLE SURFACE — the ticket says the original defines none", file=out)
        import ast

        tree = ast.parse(ORIGINAL_SOURCE)
        defined = [n.name for n in tree.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        ck("the ORIGINAL defines no top-level function or class (as #367 states)",
           defined == [], str(defined))
        ck("so the surface to keep is the SCRIPT run, and section [3] proved it over %d cases"
           % len(cases), len(cases) > 0)

        # ── [5] the config gate: no config, no run ──
        print("\n[5] THE GATE — a tool that cannot see its config THROWS (acceptance (d))",
              file=out)
        gate_dir = os.path.join(workdir, "gate")
        os.makedirs(gate_dir, exist_ok=True)
        # A copy of this module with NO registry above it and NO shipping package importable:
        # `-S` keeps site-packages out, so step 3 finds nothing either.
        probe = os.path.join(gate_dir, "probe.py")
        shutil.copyfile(rewrite, probe)
        for argv, want_code, want_text in (
            ([], 2, "no config object"),
            (["stamp"], 2, "no config object"),
            (["show-config"], 2, "no config object"),
        ):
            env = {k: v for k, v in os.environ.items() if k != CONFIG_ENV}
            env.update(good)
            proc = subprocess.run([sys.executable, "-S", probe] + argv, cwd=gate_dir, env=env,
                                  capture_output=True, text=True)
            ck("`%s` with no config exits %d saying %r"
               % (" ".join(["probe.py"] + argv), want_code, want_text),
               proc.returncode == want_code and want_text in proc.stderr
               and "Traceback" not in proc.stderr,
               "rc=%d stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        ck("it wrote nothing while refusing", _tree(gate_dir) == ["probe.py"],
           str(_tree(gate_dir)))

        # ── [6] a malformed config is refused, by name ──
        print("\n[6] CONFIG VALIDATION — each mistake is refused with a message naming it",
              file=out)

        def broken(mutate):
            config = config_template()
            mutate(config)
            try:
                build_config(config)
            except ConfigError as exc:
                return str(exc)
            return None

        def drop_role(config):
            config["fields"] = [f for f in config["fields"] if f["role"] != "minor"]

        def unlisted_env(config):
            config["required_env"] = [n for n in config["required_env"] if n != "BUILD"]

        for label, mutate, must_say in (
            ("a dropped role is named", drop_role, "'minor'"),
            ("an env var missing from required_env is named", unlisted_env, "BUILD"),
            ("a bool indent is refused",
             lambda c: c.update(indent=True), "indent"),
            ("a non-string output is refused",
             lambda c: c.update(output=None), "output"),
            ("an empty required_env is refused",
             lambda c: c.update(required_env=[]), "required_env"),
            ("an unknown role is refused",
             lambda c: c["fields"].append({"key": "x", "role": "nope"}), "nope"),
            ("a duplicated output key is refused",
             lambda c: c["fields"].append({"key": "version", "role": "built_at"}), "twice"),
            ("a misspelled format field is refused",
             lambda c: c["formats"].update(stamped="{verzion}"), "formats.stamped"),
            ("a missing formats template is refused",
             lambda c: c["formats"].pop("missing_env"), "missing_env"),
            ("a missing env role is refused",
             lambda c: c["env"].pop("sha"), "'sha'"),
        ):
            message = broken(mutate)
            ck(label, message is not None and must_say in message,
               "message=%r" % message)
        ck("an empty missing_join is ACCEPTED (a separator, not a template)",
           broken(lambda c: c["formats"].update(missing_join="")) is None)

        # ── [7] which source answered here ──
        print("\n[7] RESOLUTION ORDER — the three sources, walked in order", file=out)
        reset_config()
        saved = os.environ.pop(CONFIG_ENV, None)
        try:
            walked = find_registry(os.path.dirname(rewrite))
            ck("the walk-up from this file finds this package's registry",
               walked is not None and os.path.isfile(walked), str(walked))
            os.environ[CONFIG_ENV] = config_path
            reset_config()
            ck("$%s wins over the walk-up" % CONFIG_ENV,
               active_source() == "%s=%s" % (CONFIG_ENV, config_path), active_source())
        finally:
            os.environ.pop(CONFIG_ENV, None)
            if saved is not None:
                os.environ[CONFIG_ENV] = saved
            reset_config()

        # ── [8] what the install depends on, without running pip ──
        print("\n[8] INSTALLABLE — checked WITHOUT running pip (see below for what that means)",
              file=out)
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pyproject = os.path.join(root, "pyproject.toml")
        ck("the package root above this file has a pyproject.toml", os.path.isfile(pyproject),
           pyproject)
        if os.path.isfile(pyproject):
            with open(pyproject, "r", encoding="utf-8") as handle:
                text = handle.read()
            ck("it declares `ci` as a package, so `ci.stamp_build` imports when installed",
               '"ci"' in text, "pyproject.toml does not list ci")
            ck("it declares the console script this module's messages name",
               "forge2-dz-debug-stamp-build" in text and "ci.stamp_build:main" in text)
            ck("it ships registry.json as package data (this is what step 3 finds)",
               "package-data" in text and "registry.json" in text)
        registry = os.path.join(root, REGISTRY_NAME)
        ck("the package root ships a %s" % REGISTRY_NAME, os.path.isfile(registry), registry)
        if os.path.isfile(registry):
            with open(registry, "r", encoding="utf-8") as handle:
                document = json.load(handle)
            node = document
            found = True
            for key in UNIT_PATH:
                if not isinstance(node, dict) or key not in node:
                    found = False
                    break
                node = node[key]
            ck("it carries this unit's section at %s" % " -> ".join(UNIT_PATH), found)
            if found:
                try:
                    build_config(node)
                    ck("the shipped section is a VALID config object", True)
                except ConfigError as exc:
                    ck("the shipped section is a VALID config object", False, str(exc))
        print("    NOTE: what this section does and does NOT cover. It does not run pip — the\n"
              "    sandbox this was written in gates it, and a selftest that shells out to the\n"
              "    network is not one you want in CI anyway. It checks what an install DEPENDS\n"
              "    ON: that the pyproject declares `ci` and the entry point, and that the\n"
              "    registry section exists and is a valid config object. The install ITSELF was\n"
              "    proven separately while writing this unit, by building the wheel with\n"
              "    setuptools' PEP 517 backend and running the installed copy: the wheel lays\n"
              "    `ci/`, `dz_debug/` and `code__code__jazz__kokoro__dz_debug/registry.json`\n"
              "    down as three top-level entries, `ci.stamp_build:main` resolves and stamps\n"
              "    identically to the ORIGINAL, and step 3 is what finds the config there —\n"
              "    hiding that registry makes the installed copy exit 2 rather than guess. To\n"
              "    reproduce it yourself, run the two commands under INSTALLABLE in the module\n"
              "    docstring.", file=out)

    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print("\n%d checks, %d failure(s)" % (checks[0], len(failures)), file=out)
    for failure in failures:
        print("  failed: %s" % failure.splitlines()[0], file=out)
    return len(failures)


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by `note-for-claude` ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report its
    original error. No report is filed for a ConfigError — that is designed behavior rather than
    a bug. Returns the path written, or None.
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
        "note": "%s (ticket #367, module key forge-rw:742fec59a1578e91)" % UNIT,
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
        prog="forge2-dz-debug-stamp-build",
        description="forge2 rewrite of the forge unit "
                    "code__code__jazz__kokoro__dz_debug:ci/stamp_build.py (ticket #367) — write "
                    "the build document from the environment, the way the .gitlab-ci.yml version "
                    "stage does. With NO arguments it stamps, which is exactly what the original "
                    "does. Config-driven: `stamp` and `show-config` throw if they cannot see the "
                    "config object; `selftest` and `emit-config` need none.",
        epilog="config is read from the file named by $%s, else from the %s section of the "
               "nearest %s found by walking UP from this module (never from the working "
               "directory), else from the %s this distribution ships as package data. This "
               "package ships one at its root, so the commands work from a clean checkout. Run "
               "`emit-config` for a template."
               % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME, REGISTRY_NAME))
    # `required=False`: running with no command at all must stamp, because that is what the
    # ORIGINAL does and what its one caller — the CI version stage — invokes.
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("stamp", help="write the build document from the environment (the default)")
    sub.add_parser("selftest", help="prove this rewrite against the ORIGINAL's own bytes (its "
                                    "blob sha1 is checked), plus the edges, the config gate and "
                                    "the CLI. Needs no config; writes only to a temp dir it "
                                    "removes.")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and where it came from")
    return parser


def main(argv=None):
    """Entry point for the `forge2-dz-debug-stamp-build` console script.

    Returns a process exit code. With no arguments it stamps — the original's behavior.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at it.\n"
                  "# Until it is installed, every run of this module throws — it will not guess "
                  "a default." % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV),
                  file=sys.stderr)
            return 0
        if args.command == "selftest":
            return 0 if selftest() == 0 else 1
        if args.command == "show-config":
            print(json.dumps({"unit": UNIT,
                              "source": active_source(),
                              "base": active_base(),
                              "config": active_config(),
                              "resolved": build_config(active_config())},
                             indent=2, default=str))
            return 0
        # None (no command at all) or "stamp" — the original's behavior.
        return stamp()
    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        # note-for-claude requires the report; the ORIGINAL's exit code and traceback are
        # preserved by re-raising untouched. See DIVERGENCE 3 in the module docstring.
        path = _bug_report(exc, traceback.format_exc(), argv)
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise


if __name__ == "__main__":
    # This module has no relative imports, so running it as a plain file behaves exactly as the
    # installed `forge2-dz-debug-stamp-build` console script does — there is nothing to
    # re-import. `python3 ci/stamp_build.py` with no arguments is the ORIGINAL's invocation.
    sys.exit(main())
