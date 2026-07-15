#!/usr/bin/env python3
"""forge2 / artifact_tree_gen / slugify — a behavior-preserving rewrite of the forge unit
`artifact_tree_gen:slugify.py` (module key forge-rw:b4188f4af592d160), filed under ticket
#381 against the FORGE-wide refactor standard #200. (#381 supersedes #273, which named its
source only as a `git cat-file` the sandboxed worker cannot run; #381 embeds the bytes.)

WHAT THIS IS
------------
The original forge unit was 220 bytes: it imported a telemetry decorator from
`code_pipeline`, applied it to a one-argument function, and that function turned a string
into a URL-style slug with three `re.sub` passes followed by `.lower()`. This file is an
entirely new implementation of that unit. It keeps the original's observable behavior and
its callable surface, and it adds the three things #200 requires that the original lacked:
it is a proper installable package, it is driven by a configuration object, and it refuses
to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    slugify(s)

`slugify` rewrites `s` into a slug in three passes, IN THIS ORDER — the order is the
behavior, not an implementation detail:

  1. every character outside `[a-zA-Z0-9]` becomes a single `-`;
  2. every run of consecutive `-` collapses to one `-`;
  3. one leading `-` and one trailing `-` are removed, and the result is lowercased.

Four consequences of that exact spelling — each verified against the original in `selftest`
— are part of the behavior, and each is a way an "obvious" rewrite gets it WRONG:

  * THE CHARACTER CLASS IS ASCII-ONLY, and it is a literal class, not a category. It is
    `[a-zA-Z0-9]` — NOT `str.isalnum()`, which is Unicode-aware and answers True for `é`,
    `²` and `٣`. So `slugify('café') == 'caf'`, not `'café'`: the `é` is not in the class,
    so it becomes `-`, and step 3 then strips it as a trailing dash. A rewrite built from
    `c.isalnum()` returns `'café'` here and is therefore NOT this function.
  * IT IS ALSO NOT `\\w`, which includes the underscore. `slugify('a_b') == 'a-b'`, not
    `'a_b'` — `_` is outside `[a-zA-Z0-9]`, so it becomes a dash like any other punctuation.
  * COLLAPSE HAPPENS BEFORE STRIP, and step 3 removes at most ONE dash from each end (it is
    a regex alternation `^-|-$`, not a `strip`). The two only agree because step 2 already
    guaranteed no run of two or more dashes survives to reach step 3. Reverse the two steps
    and `slugify('--a--')` returns `'-a-'` instead of `'a'`.
  * `.lower()` IS APPLIED LAST, to the result of step 3. This is unobservable — only ASCII
    alphanumerics survive step 1, and lowercasing those can neither create nor destroy a
    dash — but it is what the original does, so it is what this does.

The result is always a plain `str`. It is USUALLY a new object, but not always: for an input
that is already its own slug, CPython may hand the input straight back — `slugify('') is ''`
is True, because the empty string is a singleton. That is not a choice this rewrite makes,
it is what the original does, and `selftest` check [6] pins the two together by comparing
their identity behavior rather than asserting either.

A NON-STRING ARGUMENT RAISES `TypeError`, from the regex substitution itself, exactly as it
did in the original: `slugify(None)`, `slugify(5)` and `slugify(b'ab')` all raise. This
module adds no type check of its own — adding one would change the behavior it must
preserve.

TERMS USED HERE
---------------
slug
    A string reduced to ASCII alphanumerics and single dashes, with no dash at either end —
    the URL-safe form of a title.
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a
    single `.json` file holding the configuration for every tool in a package, which
    registry-gated tools "walk UP the tree to find" and "throw if it cannot see". This
    package ships its own at `registry.json`, beside this file.
config object
    The chunk of that registry belonging to this unit — the `forge2.artifact_tree_gen.slugify`
    section. It is what drives this module. `emit-config` prints a template of it.
trace hook
    The telemetry decorator. The original HARDCODED this as `from code_pipeline import trace
    as debug_decorator`. A hardcoded dependency is exactly what #200's control-config
    requirement forbids, and `code_pipeline` is not importable everywhere this unit must run,
    so here the hook is named BY THE CONFIG instead (the `"trace"` key). A trace hook is
    telemetry: it records the call and returns the wrapped result unchanged, so it does not
    alter what `slugify` returns. That pass-through property is what the original's captured
    exemplars encode — they are plain values, not traced ones — and `selftest` proves the
    results are identical with the hook on and off.
exemplar
    A real `(input, output)` pair taken from the ORIGINAL acting as the oracle — #200's
    "verified, not asserted". `EXEMPLARS` below is the table; `selftest` replays it.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
`slugify()` resolves its config object on first use, from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. This file holds the unit
     config object itself — exactly what `emit-config` prints.
  2. otherwise, the `forge2.artifact_tree_gen.slugify` section of the nearest `registry.json`
     found by walking UP from THIS FILE's directory. This package ships one there, WITH a
     `slugify` section in it, so an unmodified checkout resolves and `slugify` runs.

If NEITHER answers, `slugify()` raises `ConfigError` and does not compute a value. It never
guesses a default — that is `note-for-claude`'s rule and this ticket's acceptance item (d).
A config object that is found but is missing a key this operation needs is also a
`ConfigError`, naming the key. `selftest` check [2] proves the gate by staging exactly that.

`configure(config)` and `using_config(config)` inject a config object directly, in-process,
for callers that hold their configuration in memory rather than on disk.

The only config key `slugify()` itself needs is `"trace"`, which must be present and is
either `null` (call the function undecorated) or a `"module:attr"` string naming the trace
hook to apply. Nothing is defaulted.

RUNNING IT
----------
Every command below is executable as written from this file's own directory; from anywhere
else, give the full path to `slugify.py` instead of the bare name. Which directory you run
from does not change what config is found — the registry walk-up starts at THIS FILE, never
at the working directory.

    python3 slugify.py slugify 'Hello World'    # -> hello-world
    python3 slugify.py slugify --repr 'café'    # -> 'caf'
    python3 slugify.py selftest                 # prove the exemplars, edges and config gate
    python3 slugify.py check-package            # prove this package's pyproject.toml is coherent
    python3 slugify.py emit-config              # print a config-object template
    python3 slugify.py show-config              # print the resolved config + where it came from

`slugify TEXT` takes TEXT literally — it is not parsed, quoted or unescaped — and prints the
slug followed by a newline. A slug can legitimately be EMPTY (`slugify '!!!'` is `''`), which
prints as a bare empty line; pass `--repr` to print the Python repr instead, which shows
`''` unambiguously. TEXT beginning with `-` would be read as an option, so pass it after a
`--` separator: `python3 slugify.py slugify -- -a-`.

To prove acceptance item (d) — that this throws rather than guessing — point the config
environment variable at a file that does not exist:

    FORGE2_CONFIG=/nonexistent.json python3 slugify.py slugify 'Hello World'   # exit 2

INSTALLABLE (#200 requirement 3)
--------------------------------
This directory IS the package, and ticket #381 lands the whole of it — `pyproject.toml`,
`registry.json`, `__init__.py` and this module — so it installs from its own source with no
generation step:

    pip install -e .        # from this directory
    forge2-slugify slugify 'Hello World'        # -> hello-world
    python3 -c "from artifact_tree_gen.slugify import slugify; print(slugify('Hello World'))"

`pyproject.toml` maps the import package `artifact_tree_gen` onto this directory and declares
the `forge2-slugify` console script pointing at this module's `main`. It is GENERATED by
`congruency/tools/forge_package.py` (#410) as a pure function of the modules present, so it
is a superset that never drops a sibling's script; this unit ran that generator rather than
hand-editing it, and the resulting change to `pyproject.toml` is one added line — the
`forge2-slugify` script. This unit's config section was likewise added with that tool's own
`merge_registry_section()` helper, which sets only the `forge2.artifact_tree_gen.slugify` key
and leaves every sibling's section exactly as it found it; the resulting change to
`registry.json` is one added section. Both diffs are pure insertions — nothing in this
package was deleted or rewritten to land this unit.

HOW FAR THIS WAS VERIFIED — and where it stops
----------------------------------------------
Everything `selftest` and `check-package` print was RUN, and you can re-run both with nothing
but `python3`.

`pip install -e .` WAS executed for real when this was written — into a throwaway `--prefix`
outside the repo — and the installed `forge2-slugify` console script and `from
artifact_tree_gen.slugify import slugify` were both run from that install. So acceptance item
(c) is observed here, not asserted. (Note for a reader comparing this with the sibling
`clamp.py`, which reaches the opposite conclusion: it says "`pip install -e .` ITSELF was NOT
executed when this was written: the sandbox that builds this ticket permits no `pip install`
and has no `setuptools` to build with". The `setuptools` half is right — this checkout's
`python3` has none — but that does not settle it, because `python3 -m pip install -e .`
provisions the build backend into an isolated build env itself. Run here, it succeeds.
`check-package` is still worth running: it needs no network and no build backend.)

The exemplars below are a strong refactor-drift net, NOT a proof of total equivalence —
criteria_miner's own honest limit, which #381 records. `EDGE_CASES` is this unit's answer to
that limit: each entry was read off the ORIGINAL as the oracle, and each targets something
the sampled grid cannot reach. See `EDGE_CASES` for which wrong rewrite each one kills.

SIDE EFFECTS
------------
`slugify()`, `emit-config`, `show-config`, `check-package` and `selftest` create no files and
write nothing; `selftest` builds its config objects in memory and restores every global and
environment variable it touches.

`check-package` imports this package in order to resolve its console script, which would
normally leave a `__pycache__` directory beside the source — it switches bytecode writing off
for the duration so that it does not. (Importing this package from your OWN code writes
`__pycache__` just as it would for any package; that is Python's doing, not a command of this
module's.)

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception
is thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path if it
hits an UNEXPECTED exception. A `ConfigError` is designed behavior, not a bug, so it files no
report and prints no traceback: it exits 2 with a single self-explaining line. A `TypeError`
from a non-string argument is likewise the original's own designed behavior, and the CLI
cannot even produce one — argparse hands it a `str`.
"""

import argparse
import contextlib
import importlib
import inspect
import json
import os
import re
import sys
import tempfile
import traceback
from datetime import datetime

__all__ = ["slugify", "ConfigError", "load_config", "configure", "using_config", "reset_config"]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS
#: in the config document, not a configurable setting — a config-driven tool has to know
#: which section is its own.
UNIT_PATH = ("forge2", "artifact_tree_gen", "slugify")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:artifact_tree_gen/slugify"

#: The import package this module belongs to, as `pyproject.toml` declares it. Used only by
#: `check-package`, to check the packaging against itself.
IMPORT_PACKAGE = "artifact_tree_gen"


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that
    cannot see its config throws rather than guessing a default.
    """


# ─────────────────────────────── the unit itself ───────────────────────────────

#: The three patterns of the unit's three passes, compiled once at import rather than on
#: every call (the original re-ran `import re` per call and let `re.sub` consult its own
#: cache). Compiling is a performance detail only: a compiled pattern's `.sub` and the
#: module-level `re.sub` of the same pattern string are the same operation, including the
#: TypeError each raises on a non-string subject. `selftest` checks that equivalence
#: directly, against the original's own three pattern strings.
_NON_ALNUM = re.compile("[^a-zA-Z0-9]")     # anything outside the ASCII alphanumerics
_DASH_RUN = re.compile("-+")                # a run of one or more dashes
_EDGE_DASH = re.compile("^-|-$")            # a dash at the very start, or one at the very end


def _core(s):
    """The rewritten unit body: `s` reduced to a slug.

    Three passes, in this order — the order IS the behavior:
      1. `_NON_ALNUM.sub('-', s)` maps every character outside `[a-zA-Z0-9]` to a dash. The
         class is ASCII and literal, so `é`, `²` and `_` are all outside it.
      2. `_DASH_RUN.sub('-', ...)` collapses each run of dashes to one. After this no run of
         two or more dashes exists anywhere in the string.
      3. `_EDGE_DASH.sub('', ...)` deletes a dash at the start and a dash at the end — at
         most one from each end, which is sufficient precisely because pass 2 already ran.
         `.lower()` then folds the surviving ASCII letters.

    Raises:
        TypeError: if `s` is not a string — raised by pass 1's substitution, as in the
            original.
    """
    dashed = _NON_ALNUM.sub("-", s)
    collapsed = _DASH_RUN.sub("-", dashed)
    return _EDGE_DASH.sub("", collapsed).lower()


def slugify(s):
    """Return `s` as a slug — the rewrite of the forge unit `artifact_tree_gen:slugify.py`.

    Every character outside `[a-zA-Z0-9]` becomes a dash, runs of dashes collapse to one, a
    dash at each end is dropped, and the result is lowercased. The character class is ASCII
    and literal, so `slugify('café')` is `'caf'` and `slugify('a_b')` is `'a-b'`. The result
    is always a new `str`.

    If the config object names a trace hook, the hook wraps the call; a trace hook is
    telemetry and returns the wrapped result unchanged, so the value below is the same either
    way.

    Raises:
        ConfigError: if no config object can be resolved, or it lacks the `trace` key.
        TypeError: if `s` is not a string — raised by the substitution, as in the original.
    """
    return _traced_core()(s)


_IMPL_CACHE = {}


def _traced_core():
    """Return `_core`, wrapped in the config's trace hook when one is named."""
    cfg = active_config()
    if "trace" not in cfg:
        raise ConfigError(
            "config object for %s is missing the required key 'trace' (use null for no "
            "trace hook, or a \"module:attr\" string). Run `emit-config` for a template."
            % UNIT
        )
    spec = cfg["trace"]
    if spec is not None and not isinstance(spec, str):
        raise ConfigError(
            "config key 'trace' for %s must be null or a \"module:attr\" string, not %s"
            % (UNIT, type(spec).__name__)
        )
    if spec not in _IMPL_CACHE:
        _IMPL_CACHE[spec] = _core if spec is None else _load_attr(spec)(_core)
    return _IMPL_CACHE[spec]


def _load_attr(spec):
    """Resolve a `"module:attr"` string to the attribute it names."""
    if ":" not in spec:
        raise ConfigError(
            "config key 'trace' for %s must look like \"module:attr\" (for example "
            "\"code_pipeline:trace\"); got %r" % (UNIT, spec)
        )
    mod_name, _, attr = spec.partition(":")
    module = sys.modules.get(mod_name)
    if module is None:
        try:
            module = importlib.import_module(mod_name)
        except ImportError as exc:
            raise ConfigError(
                "config key 'trace' for %s names module %r, which cannot be imported: %s"
                % (UNIT, mod_name, exc)
            ) from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ConfigError(
            "config key 'trace' for %s names %r, but module %r has no attribute %r"
            % (UNIT, spec, mod_name, attr)
        ) from exc


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None      # config object injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution, so slugify() re-reads no files


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
        return config, os.path.dirname(os.path.abspath(env_path)), "%s=%s" % (CONFIG_ENV, env_path)

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s: %s is unset and no %s was found by walking up from "
            "%s. Run `emit-config` for a template of the config object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))))
        )

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r "
                "section. Run `emit-config` and add the printed object at %s."
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
    # section may state its own to override it. This is inheritance inside one config
    # document, not a guessed default.
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

    `base` is the directory relative paths in `config` resolve against, and defaults to the
    current working directory. Pass `None` as `config` to drop the injection and go back to
    resolving from disk.
    """
    global _ACTIVE
    previous = _ACTIVE
    if config is None:
        _ACTIVE = None
    else:
        if not isinstance(config, dict):
            raise ConfigError(
                "a config object must be a dict, not %s" % type(config).__name__
            )
        _ACTIVE = (config, base or os.getcwd(), source)
    _IMPL_CACHE.clear()
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
        _IMPL_CACHE.clear()


def reset_config():
    """Drop the injected config and the cached disk resolution; the next call re-resolves."""
    global _ACTIVE, _RESOLVED
    _ACTIVE = None
    _RESOLVED = None
    _IMPL_CACHE.clear()


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do `slugify()` throws.
    """
    return {
        "trace": None,
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ───────────────────────── the exemplars and the edges ─────────────────────────

#: The captured exemplars this rewrite must reproduce, taken from the ORIGINAL unit acting as
#: the oracle — never from this rewrite.
#:
#: Ticket #381 quotes 6 pairs verbatim and says "2 more" (8 captured), probed "around the
#: function's own branch constants". This unit's branch constants are the five string literals
#: in its body — '[^a-zA-Z0-9]', '-', '-+', '^-|-$' and '' — and all five appear below, as do
#: all 6 quoted pairs, verbatim. The rest of the table extends the probe set to the boundaries
#: of the character class ('a'/'z'/'A'/'Z'/'0'/'9'), to the class innards, and to short
#: dash/case shapes. So this table is a superset of any 8 the miner could have drawn from those
#: constants, and every row was read off the original.
#:
#: The original cannot be imported as-is (`code_pipeline` is absent from this checkout), so the
#: oracle was reconstructed from the bytes #381 embeds, with a pass-through in the trace slot.
#: The reconstruction is not taken on trust: its git blob sha1 is
#: b24a9e809bc260f677682d6ed223a29939cf1512 — byte-identical to the blob #381 names under
#: CANONICAL SOURCE — and it reproduces all 6 quoted pairs. `selftest` re-derives that same
#: oracle from ORIGINAL_SOURCE below and re-checks both facts, so the table is auditable
#: without the forge.
EXEMPLARS = [
    # The unit's own five branch constants, fed back through it.
    ("[^a-zA-Z0-9]", "a-za-z0-9"),      # quoted verbatim in #381
    ("-", ""),                          # quoted verbatim in #381
    ("-+", ""),                         # quoted verbatim in #381
    ("^-|-$", ""),                      # quoted verbatim in #381
    ("", ""),                           # quoted verbatim in #381
    ("a", "a"),                         # quoted verbatim in #381
    # Single characters at the character class's boundaries.
    ("A", "a"), ("0", "0"), ("9", "9"), ("z", "z"), ("Z", "z"),
    # The class innards, as strings.
    ("a-z", "a-z"), ("A-Z", "a-z"), ("0-9", "0-9"), ("a-zA-Z0-9", "a-za-z0-9"),
    # Short dash shapes: collapse and strip.
    ("--", ""), ("---", ""), ("-a", "a"), ("a-", "a"), ("-a-", "a"), ("--a--", "a"),
    ("a--b", "a-b"),
    # Case folding and the ordinary happy path.
    ("aA0", "aa0"), ("Hello World", "hello-world"), ("hello-world", "hello-world"),
]

#: Edge cases the mining could not reach. #381 records criteria_miner's own honest limit — the
#: exemplars "cover the SAMPLED inputs" and are "NOT a proof of total equivalence" — and asks
#: for the edges sampling misses. Every expected value here was likewise read off the ORIGINAL
#: as the oracle.
#:
#: The sampled grid above cannot reach any of these, because every probe in it is pure ASCII
#: punctuation or ASCII alphanumerics — and on exactly that alphabet the three most plausible
#: WRONG rewrites all look right. Each group below kills one of them; each was confirmed to
#: diverge, not merely suspected:
#:   * `str.isalnum()` instead of the literal class — Unicode-aware, so it KEEPS 'é'/'²'/'٣'.
#:   * `[^\w]` instead of the literal class — \w includes '_' and Unicode letters.
#:   * strip-before-collapse — removes only one dash per end, so '--a--' survives as '-a-'.
EDGE_CASES = [
    # '_' is in \w but is NOT in [a-zA-Z0-9]. Kills the `[^\w]` rewrite.
    ("_", ""), ("a_b", "a-b"), ("__a__", "a"),
    # Unicode letters. `str.isalnum()` and `\w` both say True; the literal ASCII class says
    # False. Kills the isalnum() rewrite AND the \w rewrite.
    ("café", "caf"), ("naïve", "na-ve"), ("é", ""), ("É", ""),
    # Unicode NUMERICS: '²'.isalnum() and '٠'.isalnum() are True. Kills the isalnum() rewrite
    # in the digit direction too, which the letter cases above do not cover.
    ("²", ""), ("٠١", ""),
    # Characters whose .lower() is exotic — 'İ'.lower() is TWO code points, 'ß'.lower() is
    # 'ß'. Both are outside the class, so they become dashes in pass 1 and never reach
    # .lower() at all. A rewrite that lowercases FIRST still agrees here; these pin the
    # behavior rather than kill a rival.
    ("İ", ""), ("ß", ""),
    # Multi-dash runs at the ends and in the middle. Kills the strip-before-collapse rewrite.
    ("--a--b--", "a-b"), ("a----------b", "a-b"), ("-" * 50, ""),
    # Whitespace, including runs and edges.
    ("a b", "a-b"), ("a   b", "a-b"), ("  a  ", "a"), ("\ta\t", "a"), (" ", ""),
    # Newlines. Python's `$` also matches just BEFORE a trailing newline, which would matter
    # to pass 3 — except pass 1 has already turned every newline into a dash, so pass 3 never
    # sees one. These prove that reasoning rather than assume it.
    ("a\n", "a"), ("\na", "a"), ("a\nb", "a-b"), ("a\n\n", "a"), ("\n", ""),
    # Strings with no alphanumeric at all collapse to the empty slug.
    ("!!!", ""), ("...", ""), ("!@#$%^&*()", ""),
    # Digits are kept, including a leading zero (no numeric coercion anywhere).
    ("123", "123"), ("0123", "0123"), ("a1b2", "a1b2"),
    # Case folding.
    ("HELLO", "hello"), ("MiXeD CaSe", "mixed-case"),
    # Punctuation between words.
    ("a.b.c", "a-b-c"), ("a..b", "a-b"),
    # NUL is an ordinary non-alnum character here, not a terminator.
    ("\x00", ""), ("a\x00b", "a-b"),
    # Astral-plane characters are single code points to Python, and outside the class.
    ("\U0001f600", ""), ("a\U0001f600b", "a-b"),
]

#: Arguments that are not strings: the original raised TypeError from the substitution in its
#: first pass, so this rewrite must too, rather than coercing, stringifying or returning a
#: sentinel. `True` is here on purpose — it is an int, and a rewrite that reached for
#: `str(s)` would silently slugify it to 'true'.
TYPE_ERRORS = [None, 5, 1.5, b"ab", ["a"], ("a",), {"a": 1}, True]

#: The ORIGINAL unit's source, byte for byte, as ticket #381 embeds it — 220 bytes, git blob
#: sha1 b24a9e809bc260f677682d6ed223a29939cf1512. It is carried here so `selftest` can build
#: the oracle and check THIS rewrite against the ORIGINAL directly, rather than against a
#: table someone typed. That makes the equivalence evidence reproducible by a reader who has
#: no forge access — which is the whole point of #346, the fix that put these bytes on the
#: ticket. `selftest` check [3] verifies the size and the blob sha1 before trusting it.
ORIGINAL_SOURCE = (
    "from code_pipeline import trace as debug_decorator\n"
    "\n"
    "\n"
    "@debug_decorator\n"
    "def slugify(s):\n"
    "    import re\n"
    "    s = re.sub('[^a-zA-Z0-9]', '-', s)\n"
    "    s = re.sub('-+', '-', s)\n"
    "    s = re.sub('^-|-$', '', s).lower()\n"
    "    return s\n"
)

#: The git blob sha1 and size #381 records for ORIGINAL_SOURCE, under CANONICAL SOURCE.
ORIGINAL_BLOB_SHA1 = "b24a9e809bc260f677682d6ed223a29939cf1512"
ORIGINAL_SIZE = 220


def _same(got, want):
    """Compare like the oracle does: equal in value AND in type.

    The original returns whatever `re.sub(...).lower()` returns, which is always a plain
    `str`. `==` alone would accept a `str` SUBCLASS, or a bytes/str mix-up on some Python
    versions, so the type is checked too — it is part of the behavior being preserved.
    """
    return type(got) is type(want) and got == want


def build_oracle():
    """Reconstruct the ORIGINAL unit as a callable, and return `(slugify_fn, facts)`.

    The original's first line is `from code_pipeline import trace as debug_decorator`, and
    `code_pipeline` is not importable in this checkout — so a pass-through is staged in
    `sys.modules` under that name for the duration of the exec, and taken back out afterwards.
    That substitution is sound, and is not an assumption this module makes quietly: a trace
    hook is telemetry that returns the wrapped result unchanged, which is exactly why #381's
    captured exemplars are plain values (`slugify('-') == ''`) rather than traced ones. If the
    real decorator altered the return value, those exemplars could not read as they do.

    `facts` reports the size and blob sha1 actually computed, so the caller can prove the
    reconstruction is the canonical blob rather than take it on trust.

    Writes nothing, imports nothing, and leaves `sys.modules` exactly as it found it.
    """
    import hashlib
    import types

    raw = ORIGINAL_SOURCE.encode("utf-8")
    facts = {
        "size": len(raw),
        "blob_sha1": hashlib.sha1(b"blob %d\x00" % len(raw) + raw).hexdigest(),
    }

    stub = types.ModuleType("code_pipeline")
    stub.trace = lambda fn: fn                       # a trace hook returns the result unchanged
    had = "code_pipeline" in sys.modules
    saved = sys.modules.get("code_pipeline")
    sys.modules["code_pipeline"] = stub
    try:
        namespace = {}
        exec(compile(ORIGINAL_SOURCE, "<the original artifact_tree_gen:slugify.py>", "exec"),
             namespace)
        return namespace["slugify"], facts
    finally:
        if had:
            sys.modules["code_pipeline"] = saved
        else:
            del sys.modules["code_pipeline"]


# ─────────────────────────────── the selftest ───────────────────────────────

def _selftest_trace(fn):
    """A pass-through trace hook, used by `selftest` to exercise the config's trace path.

    It mirrors what the ORIGINAL unit's `code_pipeline.trace` decorator does to the return
    value, which is nothing: it records the call and hands the result back unchanged.
    """
    calls = []

    def wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        return fn(*args, **kwargs)

    wrapper.calls = calls
    wrapper.__name__ = getattr(fn, "__name__", "wrapped")
    wrapper.__doc__ = getattr(fn, "__doc__", None)
    return wrapper


#: The alphabet `selftest` check [3] fuzzes over. Deliberately mixes the class boundaries, the
#: dash itself, ASCII punctuation, whitespace, a newline, NUL, and Unicode letters/digits that
#: `str.isalnum()` and `\w` disagree with the literal ASCII class about.
_FUZZ_ALPHABET = "aZ09-_ .!\t\n\x00éÉ²٣İß\U0001f600"


def selftest(stream=None):
    """Prove this rewrite against ticket #381's acceptance items (a), (b) and (d).

    Builds its own config objects in memory, so it needs no registry, writes no files, and
    leaves no configuration behind. Returns the number of failures.

    Checks, in order:
      1. the config gate — resolution throws ConfigError where no registry exists;
      2. `slugify()` throws ConfigError, rather than computing a value, when its config cannot
         be resolved — staged via the environment variable so the result does not depend on
         this package's own shipped registry being present;
      3. this rewrite against the ORIGINAL ITSELF, rebuilt from the embedded bytes and
         verified to be the canonical blob: every exemplar, every edge case, and a
         differential fuzz over an alphabet chosen to break the plausible wrong rewrites;
      4. every exemplar and edge case against the recorded tables, with `trace` null;
      5. the same again through a trace hook named by the config, which is the shape the
         ORIGINAL ran in — the results must be identical;
      6. the callable surface `slugify(s)`, including by keyword.
    """
    out = stream or sys.stdout
    failures = []
    checks = [0]

    def check(ok, label):
        checks[0] += 1
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    saved = configure(None)
    saved_env = os.environ.pop(CONFIG_ENV, None)
    try:
        reset_config()

        with tempfile.TemporaryDirectory() as isolated:
            # 1. the config gate, proven from a directory with no registry above it.
            print("[1] config gate — a tool that cannot see its config throws", file=out)
            if find_registry(isolated) is not None:
                print("  n/a   a %s exists above the temp dir %s, so 'no registry anywhere' "
                      "cannot be staged here; check [2] proves the gate instead"
                      % (REGISTRY_NAME, isolated), file=out)
            else:
                try:
                    load_config(start=isolated)
                    check(False, "load_config() where no %s exists raises ConfigError"
                          % REGISTRY_NAME)
                except ConfigError:
                    check(True, "load_config() where no %s exists raises ConfigError"
                          % REGISTRY_NAME)

            # 2. slugify() refuses to compute when its config cannot be resolved.
            #    Staged by pointing FORGE2_CONFIG at a file that does not exist: the env
            #    source outranks the registry walk-up, so this proves the gate even though
            #    this package ships a registry of its own right beside this module. Check [1]
            #    cannot do that on its own.
            print("[2] slugify() refuses to compute when its config cannot be resolved", file=out)
            os.environ[CONFIG_ENV] = os.path.join(isolated, "no-such-config.json")
            reset_config()
            try:
                got = slugify("Hello World")
                check(False, "slugify() with an unresolvable config raises ConfigError "
                             "(it returned %r instead)" % (got,))
            except ConfigError:
                check(True, "slugify() with an unresolvable config raises ConfigError — no "
                            "value is returned and no default is guessed")
            except Exception as exc:  # noqa: BLE001
                check(False, "slugify() with an unresolvable config raised %s, not ConfigError"
                      % type(exc).__name__)
            finally:
                os.environ.pop(CONFIG_ENV, None)
                reset_config()

        # 3. differential, against the ORIGINAL rebuilt from the bytes #381 embeds.
        print("[3] differential vs the ORIGINAL itself (rebuilt from the embedded bytes)",
              file=out)
        oracle, facts = build_oracle()
        check(facts["size"] == ORIGINAL_SIZE,
              "the embedded original is %d bytes — #381's stated SIZE is %d"
              % (facts["size"], ORIGINAL_SIZE))
        check(facts["blob_sha1"] == ORIGINAL_BLOB_SHA1,
              "its git blob sha1 is %s — #381's stated blob is %s"
              % (facts["blob_sha1"], ORIGINAL_BLOB_SHA1))
        with using_config({"trace": None}):
            probes = [case[0] for case in EXEMPLARS] + [case[0] for case in EDGE_CASES]
            bad = [(p, oracle(p), slugify(p)) for p in probes
                   if not _same(slugify(p), oracle(p))]
            check(not bad, "%d/%d exemplar+edge inputs agree with the original%s"
                  % (len(probes) - len(bad), len(probes),
                     "" if not bad else " — mismatches (input, original, rewrite): %s" % bad))

            # A differential fuzz: every string up to length 3 over an alphabet built to break
            # the plausible wrong rewrites. Deterministic — it is the full product, not a
            # random sample, so it cannot pass by luck and needs no seed.
            fuzz = [""]
            for _ in range(3):
                fuzz += [prefix + ch for prefix in fuzz for ch in _FUZZ_ALPHABET
                         if len(prefix) < 3]
            fuzz = sorted(set(fuzz))
            bad = [(p, oracle(p), slugify(p)) for p in fuzz if not _same(slugify(p), oracle(p))]
            check(not bad, "%d/%d fuzz inputs (every string of length 0-3 over %r) agree "
                           "with the original%s"
                  % (len(fuzz) - len(bad), len(fuzz), _FUZZ_ALPHABET,
                     "" if not bad else " — first mismatches: %s" % bad[:5]))

            # The compiled patterns must be the same operation as the original's inline
            # `re.sub` on the same pattern strings — including on a non-string subject.
            bad = [p for p in probes
                   if _NON_ALNUM.sub("-", p) != re.sub("[^a-zA-Z0-9]", "-", p)
                   or _DASH_RUN.sub("-", p) != re.sub("-+", "-", p)
                   or _EDGE_DASH.sub("", p) != re.sub("^-|-$", "", p)]
            check(not bad, "the three precompiled patterns match the original's inline "
                           "re.sub on all %d inputs%s"
                  % (len(probes), "" if not bad else " — differ on: %s" % bad))

            # Non-strings raise TypeError, and raise it from the ORIGINAL's line too.
            bad = []
            for arg in TYPE_ERRORS:
                try:
                    oracle(arg)
                    original_raised = False
                except TypeError:
                    original_raised = True
                try:
                    slugify(arg)
                    rewrite_raised = False
                except TypeError:
                    rewrite_raised = True
                if not (original_raised and rewrite_raised):
                    bad.append((arg, original_raised, rewrite_raised))
            check(not bad, "%d/%d non-string arguments raise TypeError in BOTH the original "
                           "and this rewrite%s"
                  % (len(TYPE_ERRORS) - len(bad), len(TYPE_ERRORS),
                     "" if not bad else " — (arg, original raised, rewrite raised): %s" % bad))

        # 4 and 5. the recorded tables, undecorated and through a config-named trace hook.
        hook = "%s:_selftest_trace" % __name__
        for number, label, cfg in (
                ("4", "trace null (undecorated)", {"trace": None}),
                ("5", "trace hook %r (the shape the original ran in)" % hook, {"trace": hook})):
            print("[%s] behavior with %s" % (number, label), file=out)
            with using_config(cfg):
                bad = [(arg, want, slugify(arg)) for arg, want in EXEMPLARS
                       if not _same(slugify(arg), want)]
                check(not bad, "%d/%d captured exemplars reproduced%s"
                      % (len(EXEMPLARS) - len(bad), len(EXEMPLARS),
                         "" if not bad else " — mismatches: %s" % bad))

                bad = [(arg, want, slugify(arg)) for arg, want in EDGE_CASES
                       if not _same(slugify(arg), want)]
                check(not bad, "%d/%d edge cases reproduced%s"
                      % (len(EDGE_CASES) - len(bad), len(EDGE_CASES),
                         "" if not bad else " — mismatches: %s" % bad))

                bad = []
                for arg in TYPE_ERRORS:
                    try:
                        slugify(arg)
                        bad.append(arg)
                    except TypeError:
                        pass
                check(not bad, "%d/%d non-string arguments raise TypeError%s"
                      % (len(TYPE_ERRORS) - len(bad), len(TYPE_ERRORS),
                         "" if not bad else " — did not raise: %s" % bad))

        # 6. the callable surface.
        print("[6] callable surface", file=out)
        with using_config({"trace": None}):
            signature = str(inspect.signature(slugify))
            check(signature == "(s)",
                  "slugify%s matches the ticket's surface slugify(s)" % signature)
            check(slugify(s="Hello World") == "hello-world",
                  "slugify(s='Hello World') == 'hello-world' — the parameter is named s")
            check(all(type(slugify(p)) is str for p in ("abc", "", "Hello World", "café")),
                  "the result is a plain str")
            # Whether the result IS the input object is not something to assert — for an
            # already-slug input CPython may hand `s` straight back (slugify('') is '' is
            # True, the empty string being a singleton). What matters is that this rewrite
            # AGREES with the original, so ask the original rather than guess.
            suspects = ["", "a", "abc", "hello-world", "0", "123", "Hello World", "!!!"]
            disagree = [(p, oracle(p) is p, slugify(p) is p) for p in suspects
                        if (oracle(p) is p) != (slugify(p) is p)]
            check(not disagree,
                  "result-identity agrees with the original on all %d already-slug inputs "
                  "(both return the input object itself for '', both build a new string "
                  "otherwise)%s"
                  % (len(suspects),
                     "" if not disagree
                     else " — (input, original is-input, rewrite is-input): %s" % disagree))
    finally:
        os.environ.pop(CONFIG_ENV, None)
        if saved_env is not None:
            os.environ[CONFIG_ENV] = saved_env
        reset_config()
        globals()["_ACTIVE"] = saved

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED",
             checks[0], len(failures)), file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


# ──────────────────────── the packaging, checked against itself ────────────────────────

def check_package(stream=None):
    """Check this package's `pyproject.toml` against this module. Returns failure count.

    Acceptance item (c) is `pip install -e .`, and that WAS run for real when this was
    written (see the module docstring). This check is the part that needs no network and no
    build backend, so any reader can re-run it with `python3` alone:

      * the pyproject exists, parses, and declares a build backend;
      * it carries the PEP 621 fields an install needs (`name`, `version`);
      * it maps the import package onto this directory, so this module ships inside it;
      * it declares THIS module's console script, and every console script it declares
        resolves to a real callable — resolved exactly the way an installed script's
        `module:attr` target is;
      * `from artifact_tree_gen.slugify import slugify` works under the name the pyproject
        declares, which is the import form this ticket's callable surface is used through.

    Reads only; writes nothing. Prints `n/a` and passes when there is no pyproject beside this
    module, which is the normal state of an INSTALLED copy.
    """
    out = stream or sys.stdout
    failures = []

    def check(ok, label):
        if not ok:
            failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=out)

    here = os.path.dirname(os.path.abspath(__file__))
    pyproject = os.path.join(here, "pyproject.toml")
    print("[package] %s" % pyproject, file=out)
    if not os.path.isfile(pyproject):
        print("  n/a   no pyproject.toml beside this module — the normal state of an "
              "installed copy; nothing to check", file=out)
        return 0
    try:
        import tomllib
    except ImportError:
        print("  n/a   tomllib needs Python 3.11+ (running %d.%d) — cannot parse the "
              "pyproject here" % (sys.version_info[0], sys.version_info[1]), file=out)
        return 0

    with open(pyproject, "rb") as handle:
        try:
            data = tomllib.load(handle)
        except Exception as exc:  # noqa: BLE001
            check(False, "pyproject.toml parses as TOML (%s)" % exc)
            return len(failures)
    check(True, "pyproject.toml parses as TOML")

    backend = data.get("build-system", {})
    check(bool(backend.get("build-backend")) and bool(backend.get("requires")),
          "declares a build backend and its requirements: %r / %r"
          % (backend.get("build-backend"), backend.get("requires")))

    project = data.get("project", {})
    check(bool(project.get("name")) and bool(project.get("version")),
          "declares the PEP 621 fields an install needs: name=%r version=%r"
          % (project.get("name"), project.get("version")))

    setup = data.get("tool", {}).get("setuptools", {})
    packages = setup.get("packages", [])
    check(IMPORT_PACKAGE in packages,
          "declares the import package %r in tool.setuptools.packages %r"
          % (IMPORT_PACKAGE, packages))
    check(setup.get("package-dir", {}).get(IMPORT_PACKAGE) == ".",
          "maps %r onto this directory, so %s ships inside it"
          % (IMPORT_PACKAGE, os.path.basename(os.path.abspath(__file__))))
    check(REGISTRY_NAME in setup.get("package-data", {}).get(IMPORT_PACKAGE, []),
          "ships %s as package-data, so a non-editable install can still see its config"
          % REGISTRY_NAME)

    # Resolve each console script the way an installed one is: import `module`, getattr
    # `attr`. The parent of this package directory is what an editable install effectively
    # puts on sys.path, so put it there for the duration and take it back off.
    #
    # Importing a package normally writes a __pycache__ directory beside its source. This
    # command promises to create no files, so bytecode writing is switched OFF for the
    # duration of the imports below and restored afterwards — the check reads the same answer
    # either way, so the option that touches nothing is the one to take.
    parent = os.path.dirname(here)
    added = parent not in sys.path
    if added:
        sys.path.insert(0, parent)
    bytecode_was = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        scripts = project.get("scripts", {})
        mine = "%s.%s:main" % (IMPORT_PACKAGE, os.path.basename(__file__)[:-3])
        check(mine in scripts.values(),
              "declares THIS module's console script (%r is in %r)" % (mine, scripts))
        for name, target in sorted(scripts.items()):
            mod_name, _, attr = target.partition(":")
            try:
                module = importlib.import_module(mod_name)
                entry = getattr(module, attr)
                ok = callable(entry)
            except (ImportError, AttributeError) as exc:
                ok, entry = False, exc
            check(ok, "console script %r -> %r resolves to a callable (%r)"
                  % (name, target, entry))
        # The ticket's callable surface, through the import form the pyproject guarantees.
        try:
            module = importlib.import_module("%s.slugify" % IMPORT_PACKAGE)
            ok = callable(getattr(module, "slugify", None))
        except ImportError as exc:
            ok, module = False, exc
        check(ok, "`from %s.slugify import slugify` works — %r" % (IMPORT_PACKAGE, module))
    finally:
        sys.dont_write_bytecode = bytecode_was
        if added and parent in sys.path:
            sys.path.remove(parent)

    print("\n%s — %d failure(s)"
          % ("PACKAGE CHECK PASSED" if not failures else "PACKAGE CHECK FAILED",
             len(failures)), file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report its
    original error, and a report is never filed for a ConfigError, which is designed behavior
    rather than a bug. Returns the path written, or None.
    """
    try:
        config = active_config()
        base = active_base()
    except ConfigError:
        return None
    relative = config.get("bug_reports")
    if not relative:
        return None
    path = relative if os.path.isabs(relative) else os.path.join(base, relative)
    frames = traceback.extract_tb(exc.__traceback__)
    entry = {
        "filename": os.path.basename(os.path.abspath(__file__)),
        "function": frames[-1].name if frames else "?",
        "time-of-occurance": datetime.now().isoformat(),
        "methods-to-reproduce": "python3 %s %s" % (os.path.basename(os.path.abspath(__file__)),
                                                   " ".join(argv)),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": formatted.strip().splitlines()[-6:],
        "note": "%s (ticket #381, module key forge-rw:b4188f4af592d160)" % UNIT,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except OSError:
        return None


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="forge2-slugify",
        description="forge2 rewrite of the forge unit artifact_tree_gen:slugify.py "
                    "(ticket #381). slugify(s) reduces a string to a slug: every character "
                    "outside [a-zA-Z0-9] becomes a dash, runs of dashes collapse to one, a "
                    "dash at each end is dropped, and the result is lowercased. The class is "
                    "ASCII and literal, so 'café' slugifies to 'caf'. Config-driven: "
                    "`slugify` and `show-config` throw if they cannot see their config object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="config is read from the file named by $%s, else from the %s section of the "
               "nearest %s found by walking up from this module. Run `emit-config` for a "
               "template." % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_slugify = sub.add_parser(
        "slugify", help="print the slug of TEXT",
        description="Print slugify(TEXT). TEXT is taken literally — it is not parsed, "
                    "unquoted or unescaped. The slug may legitimately be empty ('!!!' -> "
                    "''), which prints as an empty line; use --repr to see it unambiguously. "
                    "TEXT starting with '-' must follow a '--' separator: slugify -- -a-")
    p_slugify.add_argument("text", metavar="TEXT", help="the string to slugify")
    p_slugify.add_argument("--repr", action="store_true", dest="as_repr",
                           help="print the Python repr of the slug instead of the slug itself")

    sub.add_parser("selftest", help="prove the exemplars, the edges and the config gate")
    sub.add_parser("check-package", help="prove this package's pyproject.toml is coherent")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("show-config", help="print the config object in force and its source")
    return parser


def main(argv=None):
    """Entry point for the `forge2-slugify` console script. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at "
                  "it.\n# Until it is installed, `slugify` throws — it will not guess a default."
                  % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV), file=sys.stderr)
            return 0

        if args.command == "selftest":
            return 0 if selftest() == 0 else 1

        if args.command == "check-package":
            return 0 if check_package() == 0 else 1

        if args.command == "show-config":
            print(json.dumps({"unit": UNIT, "source": active_source(),
                              "base": active_base(), "config": active_config()}, indent=2))
            return 0

        if args.command == "slugify":
            # argparse always hands over a str, so the original's TypeError on a non-string
            # cannot arise here; there is nothing to catch.
            result = slugify(args.text)
            print(repr(result) if args.as_repr else result)
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
