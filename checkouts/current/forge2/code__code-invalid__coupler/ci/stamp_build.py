#!/usr/bin/env python3
r"""forge2 / code__code-invalid__coupler / ci / stamp_build — write build.json from the
environment.

A behavior-preserving rewrite of the forge unit `code__code-invalid__coupler:ci/stamp_build.py`
(module key forge-rw:b6dafc0b6df757ae, git blob b300908d9e1f24830616dd0d1e830729ceccbdcf,
1267 bytes), filed under ticket #383 against the FORGE-wide refactor standard #200. (#383
supersedes #283, which named its source only as a `git cat-file` the sandboxed worker cannot
run; #383 embeds the source, so the work is done here.)

The same module lives at three forge tips — `code__code-invalid__coupler:ci/stamp_build.py`,
`coupler:ci/stamp_build.py` and `gitlab__testmonkeyalpha__coupler:ci/stamp_build.py`. This ONE
rewrite satisfies all three; nothing below is named for any one copy except the registry
address it reads its config from.

WHAT THIS IS
------------
The original is a CI build stamper. Its own docstring says: "write conf/env/build.json from
environment variables. Called by .gitlab-ci.yml version stage." It reads six environment
variables, refuses to run if any one of them is unset OR empty, derives a major/minor pair by
splitting VERSION on ".", writes a nine-key JSON document to `conf/env/build.json`, and prints
a one-line confirmation naming the version, the tag, and the first eight characters of the
commit sha.

The original is a SCRIPT: it defines no function and no class, and every one of its values —
the six variable names, the output path, the JSON indent, the exit code, both message layouts
and the 8-character sha preview — is a literal in its body.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and adds the three things #200 requires that the original lacked: it is part of a
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
    `forge2 -> code__code-invalid__coupler -> stamp_build`. It is what drives this module.
    `forge2-coupler-stamp-build emit-config` prints a template of it.
role
    What this module COMPUTES a value for: `version`, `tag`, `build`, `major`, `minor`, `sha`,
    `branch`, `pipeline`, `built_at` — the nine values the original's `data` dict held. A role
    is CODE: which roles exist, and how each one's value is derived and typed, is this module's
    algorithm. The environment variable a role is read from, and the JSON key it is written
    under, are CONFIG. See WHAT IS A SETTING, AND WHAT IS NOT below.
field
    One entry of the config's `fields` list: a role plus the JSON key it is written under. The
    list's ORDER is the order of the keys in the build.json this writes.

THE CALLABLE SURFACE (acceptance item (b))
------------------------------------------
Ticket #383 states it in full: "this module defines no top-level function or method. Its
behavior is whatever its module-level code does." The original binds no name a caller could
import and call — it is executed, not imported, and its one documented caller is the
`.gitlab-ci.yml` version stage that runs it. So the surface that must keep working is the
SCRIPT invocation, and it is kept exactly:

    python3 ci/stamp_build.py        # identical to `python3 stamp_build.py` on the original

`main()` ignores its argv, exactly as the original does — the original never inspects
`sys.argv`, so extra arguments are accepted and ignored by both. This module therefore adds NO
subcommands of its own: operator commands (`emit-config`, `show-config`, `selftest`) live in
the sibling `stamp_build_tool.py`, reached by the console script
`forge2-coupler-stamp-build`. Putting them here instead would have made
`python3 ci/stamp_build.py emit-config` print a template where the original would have stamped
a build.json — a divergence on the one surface this ticket must preserve.

The one deliberate difference from "whatever its module-level code does": the original stamps
AT IMPORT, because its body IS its work. This module does its work only when called. That is
forced by #200 requirements 3 and 4 — an installable, config-gated module that stamped a file
into the current directory merely because something imported it could not be installed, tested,
or introspected — and it costs nothing on the real surface, because the original's caller runs
it as a script and a script's body runs either way. `selftest` proves the script surface is
equivalent by running BOTH files and comparing everything a caller can observe.

The library surface this adds (`stamp`, `build_document`, `load_config`, ...) is additive:
nothing in the forge calls it, and it exists so the unit can be driven and tested in-process.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The config object is resolved on first use, from the first source that answers:

  1. the file named by the `COUPLER_STAMP_BUILD_CONFIG` environment variable, which holds the
     unit config object ITSELF — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code-invalid__coupler -> stamp_build` section of the
     nearest `registry.json` found by walking UP from THIS FILE's directory;
  3. otherwise, the `registry.json` this distribution ships as package data inside its
     top-level `code__code_invalid__coupler` package.

The walk-up starts at THIS FILE, never at the working directory, so which directory you run
from does not change what config is found. That matters here more than for most units, because
this tool is DESIGNED to be run from the directory it writes into: were the walk-up rooted at
the CWD, a CI job would pick up whatever registry happened to sit above its checkout. Step 3
never SHADOWS a nearer registry — it runs only after the walk-up has failed outright. If none
of the three answers, `stamp` raises `ConfigError` naming all three sources that were tried. It
never guesses a default. That is `note-for-claude`'s rule and this ticket's acceptance item (d).

`configure(config)` and `using_config(config)` inject a config object directly, in-process, for
callers that hold their configuration in memory rather than on disk.

The variable is named for THIS unit on purpose: it names a file holding ONE unit's config
object, so a variable shared across forge2 units could only ever point at one unit's object at
a time, and pointing it at a sibling's would break this one. The sibling unit in this package
reads `COUPLER_CONFIG` (see `coupler/_config.py`); `COUPLER_STAMP_BUILD_CONFIG` does not
collide with it.

WHY STEP 3 EXISTS
-----------------
It is what makes a NON-editable install work. `pip install -e .` leaves this file in the source
tree next to the package's own `registry.json`, so step 2 finds it one directory up. A plain
`pip install .` copies this file to
`<site-packages>/code__code_invalid__coupler/ci/stamp_build.py`, and the walk-up from there
reaches `<site-packages>/code__code_invalid__coupler/registry.json` — which the distribution
ships as package data — so step 2 still answers. Step 3 is the belt-and-braces for a layout
where it does not (a zip/wheel loader, or a future move of this file out from under the package
root): it asks importlib where the top-level package's registry actually is, rather than
assuming the walk-up passes it.

WHAT IS A SETTING, AND WHAT IS NOT
----------------------------------
Config holds every value an operator could reasonably want to change without changing what this
unit IS: the six environment variable names, the output path, the JSON indent, the sha preview
length, the version separator, the exit code for the missing-variable refusal, both message
templates, and the nine JSON keys with their order.

Three things are deliberately CODE, not config, and each has a reason:

  * WHICH ROLES EXIST and how each is derived/typed (`build` and `pipeline` go through `int`,
    `built_at` is the UTC clock, `major`/`minor` come from the version split). This is the
    unit's algorithm. A config that could add a role would be a config that could ask for a
    value this module has no way to compute.
  * THE ORDER the values are computed in — `build`, then `pipeline`, then the version split,
    then `major`, then `minor`. The original computes them in that order, so when two inputs
    are BOTH malformed, that order decides which ValueError a caller sees. It is observable
    behavior, so it is pinned in code and `selftest` asserts it.
  * THE VERSION SPLIT'S ARITY — exactly three parts. The original's `major, minor, _ =
    version.split(".")` IS a three-name unpack, and a version with two or four parts raises
    CPython's own `ValueError: not enough values to unpack (expected 3, got 2)` / `too many
    values to unpack (expected 3, got 4)`. This module performs a real three-name unpack so the
    INTERPRETER raises those errors verbatim. Making the arity a setting would mean
    hand-writing those message strings, which are the interpreter's to word and have changed
    wording across releases — the rewrite would then diverge from the original on any
    interpreter that words them differently. Preserving behavior wins; the separator, which is
    a genuine parameter and not an unpack arity, IS config.

RELATIVE PATHS RESOLVE AGAINST THE WORKING DIRECTORY
----------------------------------------------------
The original writes `Path("conf/env/build.json")` — a relative path, resolved by the process's
current working directory, which for its caller is the CI checkout root. So a relative `output`
in the config resolves against the CWD, NOT against the directory the registry was found in.
This is the one place where this unit deliberately does not follow the package's usual
"relative to the config's base" habit, and it has to: resolving `conf/env/build.json` against
the registry's directory would stamp the file into the installed package instead of the CI
workspace. An absolute `output` is used as given.

SIDE EFFECTS
------------
Exactly one, and it is the unit's whole purpose: `stamp` writes the file named by the config's
`output`. It creates NO other file. In particular it does NOT create the output's parent
directories — the original does not (`Path.write_text` does not create parents), so a missing
`conf/env` raises `FileNotFoundError` and writes nothing, and this module reproduces that
exactly rather than "helpfully" creating them. A sibling forge unit in another repo
(`code__code__jazz__kokoro__dz_debug:ci/stamp_build.py`, a DIFFERENT module — 1403 bytes,
blob 4916d8f6) does mkdir its parents; this one does not, and `selftest` pins the difference.
Everything else here opens files for reading only. (CPython still writes its own
`__pycache__/*.pyc` when it imports this file, as it does for any module; that is the
interpreter's doing and `.gitignore` excludes it.)

THE PROOF (acceptance item (a))
-------------------------------
Ticket #383 captured NO exemplars — "no function in this module is minable ... you must write
the equivalence exemplars by hand from the original's behavior". They are written, and they run
as a differential: `stamp_build_tool.py` embeds the original's 1267 bytes VERBATIM, checks
those bytes against the git blob sha1 the ticket names (so the oracle cannot silently drift
from what the ticket filed), then runs the ORIGINAL and this REWRITE as scripts over the same
cases in the same interpreter and compares stdout, stderr, exit code, and the bytes of the file
written. Run it:

    forge2-coupler-stamp-build selftest       # installed
    python3 ci/stamp_build_tool.py selftest   # from a source checkout

The `built_at` value is the wall clock and cannot match across two runs; the differential
compares it by SHAPE (both sides parse as an ISO-8601 UTC instant) and compares every other
key byte for byte. It does NOT mask digits: a normalizer that blanked digits would also hide a
wrong `build` or a wrong exit code.
"""

import contextlib
import json
import os
import string
import sys
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "CONFIG_ENV",
    "ConfigError",
    "DERIVED_ROLES",
    "ENV_ROLES",
    "REGISTRY_NAME",
    "ROLES",
    "UNIT",
    "UNIT_PATH",
    "active_base",
    "active_config",
    "active_source",
    "build_document",
    "config_template",
    "configure",
    "document_value",
    "find_registry",
    "load_config",
    "main",
    "packaged_registry",
    "reset_config",
    "stamp",
    "using_config",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "COUPLER_STAMP_BUILD_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: This distribution's top-level package, which ships `registry.json` as package data (see
#: WHY STEP 3 EXISTS). Named as a string rather than imported: this module must run as a plain
#: script from a source checkout, where that package is not necessarily importable.
TOP_PACKAGE = "code__code_invalid__coupler"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in
#: the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own.
UNIT_PATH = ("forge2", "code__code-invalid__coupler", "stamp_build")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code-invalid__coupler/ci/stamp_build"

#: The roles read straight from the environment, in the order the original's `required` list
#: names them. That order is the order the missing-variable message lists names in; the config's
#: `env` list restates it, and this tuple is what a config `env` list is checked against.
ENV_ROLES = ("version", "tag", "build", "sha", "branch", "pipeline")

#: The roles this module computes rather than reads.
DERIVED_ROLES = ("major", "minor", "built_at")

#: Every role, and the only role names a config may name.
ROLES = ENV_ROLES + DERIVED_ROLES

# Which roles go through `int()`, and the arity of the version split, are deliberately NOT
# declared as constants here: `build_document` states both in the statements that DO them, and a
# second declaration of the same fact is a fact that can drift from the code. See WHAT IS A
# SETTING, AND WHAT IS NOT above for why they are code rather than config.


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing/malforming a key.

    This is the #200 requirement-4 gate and ticket #383's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.

    It is NOT raised for a malformed ENVIRONMENT: a bad `BUILD` or a two-part `VERSION` is the
    original's own `ValueError`, and a missing `conf/env` is the original's own
    `FileNotFoundError`. Those are the behavior acceptance item (a) asks for, and dressing them
    up as ConfigError would change what a caller sees. Config is the operator's; the
    environment is the CI job's.
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do the unit throws. Every value below is one the
    ORIGINAL module hardcoded, which is what makes this unit control-config'd rather than
    hardwired — the six variable names and the `required` order, the output path, the indent,
    the sha preview length, the version separator, the exit code, both message layouts, and the
    nine JSON keys in the order the original's `data` dict listed them.
    """
    return {
        "output": "conf/env/build.json",
        "indent": 2,
        "sha_preview": 8,
        "version_separator": ".",
        "missing_exit_code": 1,
        "missing_separator": ", ",
        "messages": {
            "missing": "[err] missing env vars: {names}",
            "stamped": "  stamped build.json: {version}  tag={tag}  sha={sha}",
        },
        "env": [
            {"role": "version", "var": "VERSION"},
            {"role": "tag", "var": "TAG"},
            {"role": "build", "var": "BUILD"},
            {"role": "sha", "var": "CI_COMMIT_SHA"},
            {"role": "branch", "var": "CI_COMMIT_BRANCH"},
            {"role": "pipeline", "var": "CI_PIPELINE_IID"},
        ],
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
    }


# ─────────────────────────────── finding the config ───────────────────────────────

def packaged_registry():
    """Return the path of the `registry.json` this distribution ships as package data, or None.

    This is resolution step 3 (see WHY STEP 3 EXISTS). It asks importlib where the top-level
    package lives rather than assuming the walk-up passes it. It never raises: a missing or
    unimportable package just means this step has no answer, and the caller reports every
    source it tried.
    """
    try:
        import importlib.util
        spec = importlib.util.find_spec(TOP_PACKAGE)
    except Exception:
        return None
    if spec is None:
        return None
    locations = list(getattr(spec, "submodule_search_locations", None) or [])
    if not locations and getattr(spec, "origin", None):
        locations = [os.path.dirname(spec.origin)]
    for location in locations:
        candidate = os.path.join(location, REGISTRY_NAME)
        if os.path.isfile(candidate):
            return candidate
    return None


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


def _section(document, registry_path):
    """Return this unit's section of a registry document, or raise ConfigError."""
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. "
                "Run `forge2-coupler-stamp-build emit-config` and add the printed object at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH))
            )
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError(
            "the registry section %s at %s must be a JSON object, not %s"
            % (".".join(UNIT_PATH), registry_path, type(node).__name__)
        )
    return node


def load_config(start=None):
    """Resolve this unit's config object from disk, ignoring any injected config.

    Returns a `(config, base, source)` triple: the config object, the directory the config was
    found in, and a human-readable description of where it came from. `start` overrides the
    directory the registry walk-up begins at.

    NOTE `base` is NOT what a relative `output` resolves against — that is the working
    directory, as it is for the original (see RELATIVE PATHS above). `base` describes where the
    config came from, for messages and for callers that want to know.

    Raises:
        ConfigError: if no config object can be found, naming all three sources that were tried.
    """
    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        if not os.path.isfile(env_path):
            raise ConfigError("%s is set to %r, but no such file exists" % (CONFIG_ENV, env_path))
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
        registry_path = packaged_registry()
    if registry_path is None:
        raise ConfigError(
            "no config object for %s. Tried, in order: (1) %s, which is unset; (2) the nearest "
            "%s found by walking up from %s, and there is none; (3) the %s shipped as package "
            "data by the %s package, which is not importable or ships none. Run "
            "`forge2-coupler-stamp-build emit-config` for a template of the config object to "
            "install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))),
               REGISTRY_NAME, TOP_PACKAGE)
        )

    document = _read_json(registry_path, "the registry")
    return dict(_section(document, registry_path)), os.path.dirname(registry_path), registry_path


# ─────────────────────────────── validating the config ───────────────────────────────
#
# Every failure below is a ConfigError that names the key, says what was wrong with it, and
# never substitutes a default. A config object that reaches `stamp` has been proven whole, so
# no later code needs a `.get(key, something)` — which is exactly what "zero hardcoded
# settings" means in practice.

def _require(config, key):
    if not isinstance(config, dict):
        raise ConfigError(
            "the config object for %s must be a JSON object, not %s" % (UNIT, type(config).__name__)
        )
    if key not in config:
        raise ConfigError(
            "the config object for %s is missing the required key %r. Run "
            "`forge2-coupler-stamp-build emit-config` for a template." % (UNIT, key)
        )
    return config[key]


def _require_int(config, key):
    value = _require(config, key)
    # bool is an int subclass; `"indent": true` is a config mistake, not an indent of 1.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(
            "config key %r for %s must be an integer, not %s" % (key, UNIT, type(value).__name__)
        )
    return value


def _require_str(config, key, allow_empty=False):
    value = _require(config, key)
    if not isinstance(value, str):
        raise ConfigError(
            "config key %r for %s must be a string, not %s" % (key, UNIT, type(value).__name__)
        )
    if not value and not allow_empty:
        raise ConfigError("config key %r for %s must not be empty" % (key, UNIT))
    return value


def _require_env(config):
    """Return the config's env list as an ordered tuple of (role, var) pairs."""
    entries = _require(config, "env")
    if not isinstance(entries, list) or not entries:
        raise ConfigError(
            "config key 'env' for %s must be a non-empty JSON array of {'role': ..., 'var': ...} "
            "objects" % UNIT
        )
    pairs = []
    seen_roles = set()
    seen_vars = set()
    for index, entry in enumerate(entries):
        where = "config key 'env[%d]' for %s" % (index, UNIT)
        if not isinstance(entry, dict):
            raise ConfigError(
                "%s must be an object with 'role' and 'var', not %s" % (where, type(entry).__name__)
            )
        for field in ("role", "var"):
            if field not in entry:
                raise ConfigError("%s is missing %r" % (where, field))
            if not isinstance(entry[field], str) or not entry[field]:
                raise ConfigError(
                    "%s must have a non-empty string %r; got %r" % (where, field, entry[field])
                )
        role, var = entry["role"], entry["var"]
        if role not in ENV_ROLES:
            raise ConfigError(
                "%s names role %r, which is not a role this module reads from the environment. "
                "The roles it reads are: %s." % (where, role, ", ".join(ENV_ROLES))
            )
        if role in seen_roles:
            raise ConfigError("config key 'env' for %s names role %r twice" % (UNIT, role))
        if var in seen_vars:
            raise ConfigError(
                "config key 'env' for %s reads two roles from the same variable %r" % (UNIT, var)
            )
        seen_roles.add(role)
        seen_vars.add(var)
        pairs.append((role, var))
    missing_roles = [role for role in ENV_ROLES if role not in seen_roles]
    if missing_roles:
        raise ConfigError(
            "config key 'env' for %s does not name a variable for every role this module reads: "
            "%s missing. Run `forge2-coupler-stamp-build emit-config` for a template."
            % (UNIT, ", ".join(missing_roles))
        )
    return tuple(pairs)


def _require_fields(config):
    """Return the config's fields list as an ordered tuple of (key, role) pairs."""
    entries = _require(config, "fields")
    if not isinstance(entries, list) or not entries:
        raise ConfigError(
            "config key 'fields' for %s must be a non-empty JSON array of {'key': ..., 'role': "
            "...} objects" % UNIT
        )
    pairs = []
    seen_keys = set()
    for index, entry in enumerate(entries):
        where = "config key 'fields[%d]' for %s" % (index, UNIT)
        if not isinstance(entry, dict):
            raise ConfigError(
                "%s must be an object with 'key' and 'role', not %s" % (where, type(entry).__name__)
            )
        for field in ("key", "role"):
            if field not in entry:
                raise ConfigError("%s is missing %r" % (where, field))
            if not isinstance(entry[field], str) or not entry[field]:
                raise ConfigError(
                    "%s must have a non-empty string %r; got %r" % (where, field, entry[field])
                )
        key, role = entry["key"], entry["role"]
        if role not in ROLES:
            raise ConfigError(
                "%s names role %r, which is not a role this module computes. The roles it "
                "computes are: %s." % (where, role, ", ".join(ROLES))
            )
        if key in seen_keys:
            raise ConfigError("config key 'fields' for %s writes the key %r twice" % (UNIT, key))
        seen_keys.add(key)
        pairs.append((key, role))
    return tuple(pairs)


def _placeholders(template):
    """Return the set of named placeholders `template` uses."""
    return {name for _text, name, _spec, _conv in string.Formatter().parse(template)
            if name is not None}


def _require_messages(config):
    """Return (missing, stamped, stamped_roles), proving each template has its placeholders.

    A template is checked by formatting it with the placeholders it is allowed to use, so a typo
    is a ConfigError naming the template — not a KeyError from inside the stamp, half a run
    later. `stamped_roles` is the set of roles the confirmation line actually names, which
    `_Settings` uses to prove the `fields` list can supply them BEFORE anything is written.
    """
    messages = _require(config, "messages")
    if not isinstance(messages, dict):
        raise ConfigError(
            "config key 'messages' for %s must be a JSON object with 'missing' and 'stamped', "
            "not %s" % (UNIT, type(messages).__name__)
        )
    allowed = {
        "missing": {"names": ""},
        "stamped": {"version": "", "tag": "", "sha": ""},
    }
    out = {}
    for name, sample in allowed.items():
        if name not in messages:
            raise ConfigError(
                "config key 'messages' for %s is missing %r. Run "
                "`forge2-coupler-stamp-build emit-config` for a template." % (UNIT, name)
            )
        template = messages[name]
        if not isinstance(template, str):
            raise ConfigError(
                "config key 'messages.%s' for %s must be a string, not %s"
                % (name, UNIT, type(template).__name__)
            )
        try:
            template.format(**sample)
        except (KeyError, IndexError, ValueError) as exc:
            raise ConfigError(
                "config key 'messages.%s' for %s is not a usable template (%s: %s). It may use "
                "only these placeholders: %s."
                % (name, UNIT, type(exc).__name__, exc,
                   ", ".join("{%s}" % key for key in sorted(sample)))
            ) from exc
        out[name] = template
    return out["missing"], out["stamped"], _placeholders(out["stamped"])


class _Settings(object):
    """The whole config object, proven and unpacked into attributes.

    Building this is the only place config is read. If it constructs, every setting is present
    and well-typed, so nothing downstream needs a default.
    """

    __slots__ = ("output", "indent", "sha_preview", "version_separator", "missing_exit_code",
                 "missing_separator", "missing_message", "stamped_message", "stamped_roles",
                 "env", "fields")

    def __init__(self, config):
        self.output = _require_str(config, "output")
        self.indent = _require_int(config, "indent")
        self.sha_preview = _require_int(config, "sha_preview")
        self.version_separator = _require_str(config, "version_separator")
        self.missing_exit_code = _require_int(config, "missing_exit_code")
        self.missing_separator = _require_str(config, "missing_separator", allow_empty=True)
        self.missing_message, self.stamped_message, self.stamped_roles = _require_messages(config)
        self.env = _require_env(config)
        self.fields = _require_fields(config)
        if self.sha_preview < 0:
            raise ConfigError(
                "config key 'sha_preview' for %s must not be negative; got %d"
                % (UNIT, self.sha_preview)
            )
        # The confirmation line names roles; the `fields` list is what maps a role to the key it
        # is written under. If the line names a role no field writes, this config is
        # self-contradictory — and it is caught HERE, before the environment is read and before
        # anything is written, rather than after the file has already landed.
        unwritable = sorted(self.stamped_roles - {role for _key, role in self.fields})
        if unwritable:
            raise ConfigError(
                "config for %s is contradictory: 'messages.stamped' names %s, but 'fields' "
                "writes no key for %s. Add the field(s), or drop the placeholder(s) from the "
                "message."
                % (UNIT, ", ".join("{%s}" % role for role in unwritable),
                   ", ".join(repr(role) for role in unwritable))
            )


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
    """Return the directory the config object in force was found in.

    This is NOT what a relative `output` resolves against — see RELATIVE PATHS above.
    """
    if _ACTIVE is not None:
        return _ACTIVE[1]
    active_config()
    return _RESOLVED[1]


def configure(config, base=None, source="injected via configure()"):
    """Inject `config` as the config object for this process; return the previous state.

    Pass `None` as `config` to drop the injection and go back to resolving from disk.
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


# ─────────────────────────────── the unit's work ───────────────────────────────

def _utc_now():
    """The original's clock: `datetime.now(timezone.utc)`."""
    return datetime.now(timezone.utc)


def build_document(settings, environ, clock):
    """Return the JSON document for `environ`, as an ordered dict of key -> value.

    This is the original's `data` dict, built in the original's order. Every exception it can
    raise is one the original raises for the same input:

      * ValueError from `int()` on a non-numeric `build`, `pipeline`, `major` or `minor`;
      * ValueError from the version unpack when the version does not split into exactly three
        parts — raised by the interpreter itself, so the message is CPython's own.

    The COMPUTE ORDER is load-bearing and matches the original statement for statement: build,
    pipeline, then the version split, then major, then minor. When two inputs are both bad, that
    order is what decides which error a caller sees.
    """
    values = {}
    for role, var in settings.env:
        values[role] = environ[var]

    # The original: `build = int(os.environ["BUILD"])`, then `pipeline = int(...)`. Both are
    # coerced BEFORE the version is split, so a bad BUILD beats a bad VERSION.
    values["build"] = int(values["build"])
    values["pipeline"] = int(values["pipeline"])

    # The original: `major, minor, _ = version.split(".")`. A real three-name unpack, so a
    # two- or four-part version raises the interpreter's own ValueError verbatim.
    major, minor, _rest = values["version"].split(settings.version_separator)

    # The original coerces these inside the `data` literal, in key order: major, then minor.
    values["major"] = int(major)
    values["minor"] = int(minor)

    values["built_at"] = clock().isoformat()

    return {key: values[role] for key, role in settings.fields}


def stamp(environ=None, stdout=None, stderr=None, clock=None, config=None):
    """Do the unit's work: refuse on missing variables, else write the file and print the line.

    Returns the process exit code the original would exit with: 0 on success, the config's
    `missing_exit_code` when a required variable is unset or empty.

    Args:
        environ: the environment mapping to read (default: `os.environ`).
        stdout: stream for the confirmation line (default: `sys.stdout`).
        stderr: stream for the refusal line (default: `sys.stderr`).
        clock: no-arg callable returning an aware datetime (default: `datetime.now(timezone.utc)`).
        config: config object to use, overriding the one in force (default: the one in force).

    Raises:
        ConfigError: if there is no config object, or it is malformed. Raised BEFORE the
            environment is read, so a config problem never masquerades as a CI problem.
        ValueError: exactly where the original raises it — a non-numeric build/pipeline/major/
            minor, or a version that does not split into three parts.
        FileNotFoundError: when the output's parent directory does not exist. The original does
            not create parents, so neither does this; see SIDE EFFECTS.
    """
    settings = _Settings(active_config() if config is None else config)
    environ = os.environ if environ is None else environ
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    clock = _utc_now if clock is None else clock

    # The original: `missing = [k for k in required if not os.environ.get(k)]` — an unset
    # variable and an EMPTY one are both missing, and the message lists them in `required`
    # order, which is the config's `env` order.
    missing = [var for _role, var in settings.env if not environ.get(var)]
    if missing:
        print(settings.missing_message.format(names=settings.missing_separator.join(missing)),
              file=stderr)
        return settings.missing_exit_code

    document = build_document(settings, environ, clock)

    # The original: `out.write_text(json.dumps(data, indent=2))` — no trailing newline, and no
    # parent directories created. `json.dumps` defaults to ensure_ascii=True, so the text is
    # pure ASCII and `write_text`'s locale encoding cannot change the bytes.
    Path(settings.output).write_text(json.dumps(document, indent=settings.indent))

    # The original: `print(f"  stamped build.json: {version}  tag={tag}  sha={sha[:8]}")`. Only
    # the roles the template actually names are looked up — `_Settings` has already proven the
    # `fields` list can supply every one of them.
    named = {role: document_value(document, settings, role) for role in settings.stamped_roles}
    if "sha" in named:
        named["sha"] = named["sha"][:settings.sha_preview]
    print(settings.stamped_message.format(**named), file=stdout)
    return 0


def document_value(document, settings, role):
    """Return the document value written for `role`, found through the config's field mapping.

    The confirmation line names the version, the tag and the sha — ROLES, not keys — so it has
    to ask which key each role was written under rather than assuming the original's names. A
    role no field writes cannot reach here: `_Settings` rejects that config up front.
    """
    for key, field_role in settings.fields:
        if field_role == role:
            return document[key]
    raise ConfigError(  # pragma: no cover — _Settings has already ruled this out
        "config key 'fields' for %s writes no key for the %r role, which the 'stamped' message "
        "names." % (UNIT, role)
    )


def main(argv=None):
    """Run the unit as the original's script does, and return its exit code.

    `argv` is accepted and IGNORED, exactly as the original ignores `sys.argv` — see THE
    CALLABLE SURFACE. Operator commands live in `stamp_build_tool.py`.
    """
    return stamp()


if __name__ == "__main__":
    sys.exit(main())
