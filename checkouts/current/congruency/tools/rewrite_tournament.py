#!/usr/bin/env python3
"""rewrite_tournament.py — the competitive-rewrite tournament harness each forge2 rewrite
ticket runs (ticket #207).

WHAT THIS IS
------------
A forge2 rewrite ticket takes one small ORIGINAL forge unit and produces a
behavior-preserving rewrite of it that meets the FORGE-wide refactor standard #200. Until
now each ticket did that by hand and by taste. This tool makes it a TOURNAMENT: several
independent candidate rewrites are generated, each is GATED on behavioral equivalence with
the original, the survivors are BENCHMARKED against each other on one shared harness, an
ALL-AGENT PANEL of independent judges scores every survivor, the scores are aggregated and
ranked, a WINNER is selected with a rationale, and the whole thing is written up as a
per-module deep-dive doc and recorded to a queryable rebuild-scores table.

    T=checkouts/current/congruency/tools/rewrite_tournament.py     # from the repository root
    python3 $T emit-config > /tmp/rt.json
    python3 $T run --config /tmp/rt.json \\
        --from-rewrite checkouts/current/forge2/artifact_tree_gen/slugify.py --out /tmp/rt-out

Both commands are executable exactly as written from the repository root — the directory
holding `registry.json` — on a checkout with nothing installed but python3. RUNNING IT below
spells every command out in full. `run` writes ONLY inside its `--out` directory, which is
required and has no default — see SIDE EFFECTS.

TERMS USED HERE
---------------
forge unit / original
    The small Python module a rewrite ticket rewrites — typically 100-220 bytes: a hardcoded
    telemetry import, one decorated function, nothing else. It is the tournament's INPUT and
    the ORACLE its candidates are judged against.
candidate
    One generated rewrite of that original: a complete, standalone Python module. The
    tournament generates several and keeps the ones that pass the gate.
approach
    HOW a candidate is generated — a list of source-to-source `transforms` applied to the
    original's body, plus the `scaffold` (how much #200 config machinery is wrapped around
    it). Named entirely by config; see CONFIGURATION.
exemplar
    A real `(args -> result)` pair taken from the ORIGINAL acting as the oracle — #200's
    "verified, not asserted". Exemplars are the gate's evidence. See EXEMPLARS.
gate
    The behavioral-equivalence check. A candidate that disagrees with the original on any
    exemplar is DISCARDED, and the harness keeps generating from further candidate configs
    until `min_passing` candidates pass.
panel / judge
    The scoring step. Each judge independently scores every candidate on three criteria —
    config-completeness, efficiency, readability — and is BLIND to every other judge: a judge
    is handed one candidate and its bench row, and nothing else. See THE PANEL.
disagreement
    Judges scoring the same candidate+criterion more than `disagreement_threshold` apart. The
    aggregate flags it rather than hiding it inside the median.
rebuild-scores table
    The sqlite database this tool appends every run's numbers to. One database can hold every
    module of the whole forge2 rebuild, so `query` can answer best/worst by criterion ACROSS
    the rebuild, not just within one run. See THE SCORES TABLE.
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a single
    `.json` file holding the configuration for every tool in this packaging, which
    registry-gated tools "walk UP the tree to find" and "throw if it cannot see".

THE SIX STEPS, IN THE ORDER `run` EXECUTES THEM
----------------------------------------------
  1. GENERATE   — one candidate per entry in the config's `candidates` list, each with its own
                  model/approach. The model set is CONFIG, not code (#184).
  2. GATE       — each candidate is checked against the original for behavioral equivalence
                  over the exemplars. Failures are discarded; generation continues down the
                  candidate list until `min_passing` have passed. If the list runs out first,
                  `run` exits 1 and says how many passed.
  3. BENCHMARK  — every PASSING candidate is run on one shared workload, capturing runtime,
                  peak memory and retained blocks (#203 telemetry). See BENCHMARKING.
  4. PANEL      — every judge in the config scores every passing candidate on
                  config-completeness, efficiency (from the bench numbers) and readability.
  5. AGGREGATE  — per candidate+criterion: the MEDIAN across judges, the spread, and a
                  disagreement flag. Candidates are ranked by the criterion-weighted mean of
                  their medians; rank 1 is the WINNER; graftable ideas are collected from the
                  runners-up.
  6. RECORD     — the per-module deep-dive doc is written and every score is appended to the
                  rebuild-scores table.

THE FOUR TICKETS THIS BUILDS ON — WHAT IS REUSED AND WHAT IS A SEAM
-------------------------------------------------------------------
#207 says to reuse #185 tournament code, #184 litellm, #203 telemetry and #200 exemplars.
NONE OF THE FOUR EXISTS IN THIS CHECKOUT as importable code — verified by searching the tree
for each (there is no litellm module, no criteria_miner, no telemetry helper, and the
`tooling/tournament-*` trees are a chess/package tournament, unrelated to #185). `litellm`
itself is not installed either (`import litellm` raises ModuleNotFoundError here).

So each of the four is a CONFIG SEAM with a working built-in fallback behind it. Nothing here
pretends to call code that is absent:

  #184 litellm    — the `generator` and each judge's `backend` are config strings. Set them to
                    "litellm" and candidates/scores come from the models named by the config's
                    `model` fields, routed through `litellm.completion()`. The model set is
                    config, never code. The litellm backend is IMPLEMENTED and its call shape
                    is proven by `selftest` against a stand-in module injected into
                    sys.modules — it has NOT been run against a live model or API key, because
                    neither exists in this checkout. Selecting it without litellm installed
                    raises a ConfigError naming the missing package, not a traceback.
                    The built-in default is "builtin", described under GENERATION.
  #185 tournament — no tournament code exists to reuse; the tournament loop here is this
                    ticket's own. `run` is a library function as well as a CLI, so #185 (or a
                    later harness) can drive it.
  #203 telemetry  — the config's `telemetry` key is a "module:attr" hook. When it is null the
                    built-in `measure()` is used (`time.perf_counter` + `tracemalloc`); point
                    it at #203 when #203 lands and the bench rows come from there instead.
  #200 exemplars  — `--exemplars FILE` consumes a criteria_miner exemplar file (format under
                    EXEMPLARS). With no such file the built-in `mine_exemplars()` mines them
                    from the original itself, mirroring the behavior every landed forge2
                    rewrite records of criteria_miner: probes "around the function's own branch
                    constants", covering "the SAMPLED inputs" and so "NOT a proof of total
                    equivalence" (quoted from `forge2/artifact_tree_gen/slugify.py` and
                    `fib.py`). That honest limit is this gate's limit too.

THE INPUT: A MODULE
-------------------
`--module PATH` reads the original unit from a .py file.

`--from-rewrite PATH` reads it out of a LANDED forge2 rewrite instead. Every such rewrite
embeds the original byte-for-byte as `ORIGINAL_SOURCE` alongside the git blob sha1 it must
hash to (`ORIGINAL_BLOB_SHA1`); this tool extracts both and REFUSES to run if the bytes do not
hash to the recorded sha1. That is why the acceptance run needs no forge access: the original
is carried in the repository, and it is proven rather than trusted.

Either way the tool parses the original to find its callable surface: the module-level
function is the unit's entry point, its parameters are the surface, and any decorator coming
from a module that cannot be imported is the HARDCODED TELEMETRY the config's `oracle_stubs`
stands in for. That substitution is sound and is not assumed quietly: a trace hook is
telemetry — it records the call and returns the wrapped result unchanged — which is exactly
why the originals' captured exemplars are plain values rather than traced ones.

EXEMPLARS
---------
An exemplar file is JSON. Arguments and results are PYTHON LITERAL REPRS (read with
`ast.literal_eval`), because the real probe values include `bytes`, tuples and `None`, which
JSON cannot carry:

    {"unit": "slugify", "arity": 1,
     "cases": [{"args": "('Hello World',)", "result": "'hello-world'"},
               {"args": "(5,)", "raises": "TypeError"}]}

`mine_exemplars()` writes exactly this shape, so `mine` can produce a file that `run
--exemplars` reads back.

GENERATION (the built-in backend)
---------------------------------
The built-in generator builds a candidate by rewriting the original's own body with generic,
module-agnostic source-to-source transforms, then wrapping the result in a #200 scaffold.
Both halves are named by the approach config; the catalog is printed by `list-approaches`.

Transforms (each is real, each declares the idea it contributes, and each LEAVES THE UNIT
UNCHANGED and says so if it does not apply to this original):

    verbatim            the original's body, unchanged
    hoist_imports       function-local imports moved to module level (import once, not per call)
    precompile_literals `re.sub('lit', ...)` -> a module-level `re.compile('lit')` + `.sub(...)`
    chain_calls         `s = f(s); s = g(s); return s` folded to `return g(f(s))`
    memoize             the core wrapped in `functools.lru_cache`
    coerce_str_args     `str()` coercion prepended to every parameter

`coerce_str_args` is in the catalog ON PURPOSE. It is the single most plausible "helpful
cleanup" a model makes, and it silently destroys the original's behavior on non-string
arguments. It is what the gate is FOR, and the acceptance run below shows the gate catching
it. A transform is not required to be a good idea; the gate and the panel decide.

Scaffolds (how much #200 machinery wraps the core — this is what config-completeness measures):

    full        ConfigError + env-var config + registry walk-up + configure() + emit-config
                + bug_reports + the trace hook named by config
    env_only    the same, minus the registry walk-up and bug_reports
    minimal     the bare function, config hardcoded — passes the gate, scores near zero on
                config-completeness. A real model output, and a real tournament loser.

THE PANEL
---------
Each judge in the config's `judges` list scores every candidate on the three criteria, out of
10. A judge is BLIND to the other judges by construction: `judge_candidate()` is handed one
candidate, its bench row and its own judge config, and has no access to any other judge's
output. `selftest` proves this rather than asserting it — it permutes the judge order and
checks that every judge's scores are byte-identical, which cannot hold if judges influence one
another.

Judges differ by their `weights` (how much each sub-metric counts) and `strictness` (a gamma
on the final score: >1 is a harsher judge). Both are config, so a diverse panel is a config
change. Each judge also carries a `model` field, which the "litellm" backend uses and the
built-in "rubric" backend ignores.

What the three criteria actually measure — all of them REAL measurements of the candidate, not
opinions:

    config_completeness   eight #200-requirement-4 features, found in the candidate's AST:
                          a config error type; raising it rather than defaulting; env-var
                          resolution; registry walk-up; in-process configure(); a config
                          template; the telemetry hook named by config rather than hardcoded;
                          bug_reports honored.
    efficiency            the candidate's own bench row (runtime, peak bytes, retained blocks),
                          normalized against the best and worst candidate in THIS run.
    readability           docstring coverage, comment density, mean function length, maximum
                          nesting depth, long-line ratio, identifier quality.

BENCHMARKING
------------
Every passing candidate runs the SAME workload — the exemplar inputs the original answers — on
one shared harness. Runtime and memory are measured in separate passes, each set up the way its
own measurement needs:

  pass 1 (runtime, WARM)  untimed warmup sweeps first, so an import or a first-call regex
          compile lands outside the measurement; then `repeats` sweeps timed with
          `time.perf_counter` and no tracing. Timing under `tracemalloc` would report the
          tracer — it roughly doubles the runtime it is meant to be measuring.
  pass 2 (memory, COLD)   `re.purge()` first, then tracing starts, then the candidate module is
          re-executed INSIDE the traced window and the workload is swept.

Pass 2 is cold and purged for two reasons that a warm pass gets wrong, and both were found by
running it rather than reasoning about it:

  * A WARM module has already made its module-level allocations and filled its caches, so a warm
    memory pass reports ~zero blocks — it measures nothing while looking like a measurement.
  * The interesting caches are SHARED, not per-candidate: `re` keeps ONE process-wide
    compiled-pattern cache. Without the purge, whichever candidate ran first would be charged
    for filling it and every later candidate would look free — an order-dependent benchmark,
    which is no benchmark at all.

The three numbers, exactly:

  `runtime_s`        wall-clock seconds for `repeats` warm sweeps of the workload.
  `peak_bytes`       `tracemalloc.get_traced_memory()[1]` — the peak traced memory for the
                     process during pass 2, module load through the whole sweep.
  `retained_blocks`  memory blocks still LIVE at the end of pass 2 whose traceback passes
                     through the candidate's own file (`all_frames=True`, so an allocation `re`
                     made on the candidate's behalf counts as the candidate's). `retained_bytes`
                     is the same blocks in bytes.

RETAINED, not allocated — and the distinction is why the column is named this way. `tracemalloc`
snapshots what is LIVE, and CPython exposes no total-allocation counter, so "how many
allocations did this candidate make" is NOT a number that can honestly be reported here. What
can be reported is what the candidate still HOLDS after doing the work: its module-level
constants, its regex-cache entries, its `lru_cache`. That is a real cost and a real difference
between candidates — it is what charges a memoizing candidate for the cache that makes it fast.

Every number in the perf table is measured on the machine that ran it. None is modelled, and a
runtime is not stable to more than a couple of significant figures.

SIDE EFFECTS
------------
`run` writes ONLY inside the directory given by `--out`, which is REQUIRED and has no default
— so this tool cannot write anywhere by surprise. It creates that directory, and inside it the
deep-dive doc, one .py per generated candidate, and (unless `--scores-db` points elsewhere) the
rebuild-scores database. `--scores-db` is how a whole rebuild shares one database.

`emit-config`, `show-config`, `list-approaches`, `mine` (without `--write`) and `selftest`
create no files and write nothing. `query` opens the scores database STRICTLY read-only via the
sqlite URI `immutable=1` flag, so it creates no `-wal`/`-shm` sidecars even though a database
written by `run` is in WAL journal mode; it never writes.

Candidates are exec'd IN-PROCESS, in their own namespace, with bytecode writing switched off so
no `__pycache__` appears. That is the harness's one real limitation: a candidate that loops
forever hangs the tournament, and a candidate that calls `os._exit` takes the harness with it.
The built-in generator produces only this tool's own scaffolds, but a `litellm` candidate is
model output and is NOT sandboxed. Review generated candidates before trusting a run.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception
is thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path on an
UNEXPECTED exception. A `ConfigError` is designed behavior, not a bug: it files no report and
prints no traceback, and exits 2 with a single self-explaining line.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The config object is resolved from the first source that answers:

  1. `--config PATH` — the file holds the config object itself, exactly what `emit-config`
     prints;
  2. the file named by the `REWRITE_TOURNAMENT_CONFIG` environment variable;
  3. the `rewrite_tournament` section of the nearest `registry.json` found by walking UP from
     THIS FILE.

If none answers, the tool raises `ConfigError` and does nothing. It never guesses a default.
THE ROOT registry.json HAS NO `rewrite_tournament` SECTION TODAY — #207 authorizes this file
and nothing else, so it does not add one. Until an operator installs the section (paste what
`emit-config` prints), source 3 does not answer and sources 1 and 2 are how this tool runs.
That is the gate working, not a defect, and it is why every example below passes `--config`.

RUNNING IT
----------
Every command below is executable exactly as written from the repository root — the directory
holding `registry.json` — on a checkout with nothing installed but python3. `$T` is this file
and `$OUT` is any directory you can write to; nothing is written anywhere else.

    T=checkouts/current/congruency/tools/rewrite_tournament.py
    OUT=/tmp/rt                       # any writable directory; `run` writes only inside --out
    mkdir -p "$OUT"

    python3 $T list-approaches        # the transform/scaffold catalog the config names
    python3 $T selftest               # prove the harness end-to-end; needs no config
    python3 $T emit-config > "$OUT/rt.json"

    # the acceptance run: the real forge unit artifact_tree_gen:slugify.py, taken from the
    # bytes the landed rewrite embeds and verified against its recorded git blob sha1.
    python3 $T run --config "$OUT/rt.json" \\
        --from-rewrite checkouts/current/forge2/artifact_tree_gen/slugify.py \\
        --out "$OUT/tournament"

    # what the tournament learned, across EVERY module recorded in the database. Point every
    # module of a rebuild at one --scores-db and these answer across the whole rebuild.
    python3 $T query --scores-db "$OUT/tournament/rebuild_scores.sqlite" \\
        --criterion readability --best
    python3 $T query --scores-db "$OUT/tournament/rebuild_scores.sqlite" \\
        --criterion efficiency --worst

    # the exemplars alone, without running a tournament
    python3 $T mine --config "$OUT/rt.json" \\
        --from-rewrite checkouts/current/forge2/artifact_tree_gen/slugify.py

`selftest` needs no config and no network: it builds its config objects in memory, runs a whole
tournament end-to-end in a temporary directory, and removes it afterwards.

Note that `--config` belongs to the SUBCOMMAND, not before it: `run --config X`, not `--config
X run`. Without it the tool falls back to $REWRITE_TOURNAMENT_CONFIG and then to the registry
section, which does not exist yet — so a bare `run` exits 2 and tells you to run `emit-config`.

HOW FAR THIS WAS VERIFIED — and where it stops
----------------------------------------------
Everything `selftest` prints was RUN, and you can re-run it with nothing but python3: 35 checks,
0 failures, covering the config gate, the blob verification and its refusal of tampered bytes,
the miner, the gate discarding a non-equivalent candidate, a whole tournament end to end, the
panel's blindness, the disagreement flag, the litellm adapter, and the side-effect promises.

The acceptance run above was executed for real against the REAL forge unit
`artifact_tree_gen:slugify.py` — 220 bytes, git blob `b24a9e809bc260f677682d6ed223a29939cf1512`,
verified against the sha1 the landed rewrite records. It mined 32 exemplars, generated 6
candidates, DISCARDED one (`coerced`, which answers `'0'` where the original raises TypeError),
benchmarked the 5 survivors over 44,000 calls each, scored them with 3 judges on 3 criteria,
and selected `env-only`. Its deep-dive doc and its rebuild-scores rows are what this tool
writes. A second module was recorded into the same database and `query` answered best/worst
across both — so "across the whole rebuild" is observed, not asserted.

The miner was cross-checked against the REAL criteria_miner rather than trusted: the landed
`slugify.py` records the exemplar table #381 mined from the original, and on the 10 probes the
two share, this tool's miner agrees on all 10 and disagrees on none.

Where it stops, plainly:
  * NO LIVE MODEL was called. litellm is not installed here and no API key exists, so the #184
    generator and the litellm judge backend were proven against a stand-in module injected into
    sys.modules — call shape, config-supplied model, reply parsing — and NOT against a real
    model. The panel that ran is the built-in `rubric` backend: diverse RUBRICS, not diverse
    MODELS.
  * The bench numbers are one machine, one run. Runtimes are not reproducible to more than a
    couple of significant figures; the RANKING between candidates is the durable part.
  * The gate is the mined exemplars, which cover the SAMPLED inputs only.

REQUIREMENTS
------------
Python 3.9+ (this module renders candidate source with `ast.unparse`, which 3.8 lacks). The
tool checks this at startup and exits 2 with a one-line message rather than a traceback.
"""

import argparse
import ast
import contextlib
import hashlib
import importlib
import io
import json
import os
import re
import sqlite3
import statistics
import sys
import tempfile
import time
import tracemalloc
import traceback
from datetime import datetime, timezone

__all__ = [
    "ConfigError", "load_config", "configure", "using_config", "reset_config",
    "config_template", "load_original", "original_from_rewrite", "build_oracle",
    "mine_exemplars", "generate_candidate", "gate_candidate", "measure", "bench_candidate",
    "judge_candidate", "run_panel", "aggregate", "run_tournament",
]

#: Environment variable naming a file that holds this tool's config object.
CONFIG_ENV = "REWRITE_TOURNAMENT_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this tool's config object lives inside the registry. This is the tool's own ADDRESS in
#: the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own.
UNIT_PATH = ("rewrite_tournament",)

#: Human-readable tool identity, used in messages.
TOOL = "congruency:tools/rewrite_tournament"

#: The three criteria #207 names for the panel. Order is display order everywhere.
CRITERIA = ("config_completeness", "efficiency", "readability")


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate: a tool that cannot see its config throws rather than
    guessing a default. It is designed behavior, so the CLI reports it as one line and files no
    bug report.
    """


class TournamentError(RuntimeError):
    """Raised when a tournament cannot reach a verdict — for example when the candidate list is
    exhausted before `min_passing` candidates pass the gate. Like ConfigError this is designed
    behavior: the CLI reports it as one line, not a traceback."""


# ── registry gate (note-for-claude: a tool that cannot see the registry throws) ──────────────

def find_root(start):
    """Walk UP from `start` and return the directory holding registry.json.

    Raises:
        RuntimeError: if the walk reaches the filesystem root without finding one.
    """
    directory = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(directory, REGISTRY_NAME)):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            raise RuntimeError(
                "%s not found walking up from %s — refusing to run" % (REGISTRY_NAME, start)
            )
        directory = parent


ROOT = find_root(os.path.dirname(os.path.abspath(__file__)))


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None      # config injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution


def find_registry(start=None):
    """Return the nearest registry.json walking UP from `start` (default: this file's
    directory), or None if the walk reaches the filesystem root without finding one."""
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


def load_config(path=None, start=None):
    """Resolve this tool's config object from disk, ignoring any injected config.

    Returns a `(config, base, source)` triple: the config object, the directory relative paths
    inside it resolve against, and a human-readable description of where it came from. `path`
    is the `--config` file; `start` overrides where the registry walk-up begins.

    Raises:
        ConfigError: if no config object can be found, naming every source that was tried.
    """
    explicit = path or os.environ.get(CONFIG_ENV)
    if explicit:
        why = "--config" if path else CONFIG_ENV
        if not os.path.isfile(explicit):
            raise ConfigError("%s names %r, but no such file exists" % (why, explicit))
        config = _read_json(explicit, "the config object named by " + why)
        if not isinstance(config, dict):
            raise ConfigError(
                "the config object at %s must be a JSON object, not %s"
                % (explicit, type(config).__name__)
            )
        return config, os.path.dirname(os.path.abspath(explicit)), "%s=%s" % (why, explicit)

    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s: --config was not given, %s is unset, and no %s was found "
            "by walking up from %s. Run `emit-config` for a template."
            % (TOOL, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))))
        )

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. "
                "Run `emit-config` and either add the printed object at %s, or save it to a "
                "file and pass it with --config."
                % (registry_path, TOOL, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH))
            )
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError(
            "the registry section %s at %s must be a JSON object, not %s"
            % (".".join(UNIT_PATH), registry_path, type(node).__name__)
        )

    config = dict(node)
    # The registry's own top-level bug_reports path is package-wide infrastructure; this
    # section may state its own to override it. Inheritance inside one config document, not a
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


def active_base():
    """Return the directory relative paths in the config resolve against."""
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

    Pass `None` to drop the injection and go back to resolving from disk.
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


def require(config, key, why):
    """Return `config[key]`, or raise ConfigError naming the key and what needs it.

    Nothing is defaulted: #200 requirement 4 is that a tool which cannot see a setting throws
    rather than guessing one.
    """
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the required key %r (%s). Run `emit-config` for a "
            "template." % (TOOL, key, why)
        )
    return config[key]


def config_template():
    """Return a template of this tool's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it or passes it with --config, and until they do every command that needs
    config throws.

    The template is a WORKING tournament: nine candidate configs (so the gate can discard
    failures and still reach `min_passing` = 5) and three judges. Every model name below is
    inert until `generator`/`backend` is switched to "litellm" — the built-in backends ignore
    them, and they are here to show that the model set is config and not code.
    """
    return {
        "_comment": "Config object for congruency:tools/rewrite_tournament (ticket #207). "
                    "Install this at the 'rewrite_tournament' key of the root registry.json, "
                    "or save it to a file and pass it with --config.",
        "generator": "builtin",
        "min_passing": 5,
        "disagreement_threshold": 2.0,
        "criterion_weights": {
            "config_completeness": 1.0,
            "efficiency": 1.0,
            "readability": 1.0,
        },
        "bench": {"repeats": 2000, "warmup": 200, "trace_frames": 10},
        "telemetry": None,
        "oracle_stubs": {"code_pipeline": "passthrough"},
        "probe_pool": [
            "Hello World", "hello-world", "a b", "  a  ", "a_b", "a--b", "--a--", "a.b.c",
            "!!!", "café", "MiXeD CaSe", "123", "a1b2", "\n", "\t", " ", "-", "",
            0, 1, 2, 3, 10, -1, True, False, None, 1.5, "a",
        ],
        "max_exemplars": 240,
        # ORDER MATTERS, and it is a config choice rather than a code one: `run` generates down
        # this list and STOPS once `min_passing` have passed the gate, so anything after that
        # point is a spare that a discard promotes into the tournament. This ordering puts the
        # approach DIVERSITY inside the first few — a deliberately behavior-breaking approach
        # for the gate to catch, and all three scaffolds — so the panel has something to tell
        # apart. A list whose scaffolds are all `full` produces a config-completeness column
        # that is 10.0 for every candidate: true, and useless.
        "candidates": [
            {"name": "faithful",
             "model": "anthropic/claude-sonnet-5",
             "approach": {"transforms": ["verbatim"], "scaffold": "full"}},
            {"name": "coerced",
             "model": "anthropic/claude-haiku-4-5",
             "approach": {"transforms": ["hoist_imports", "coerce_str_args"],
                          "scaffold": "full"}},
            {"name": "precompiled",
             "model": "anthropic/claude-opus-4-8",
             "approach": {"transforms": ["hoist_imports", "precompile_literals"],
                          "scaffold": "full"}},
            {"name": "minimal",
             "model": "anthropic/claude-haiku-4-5",
             "approach": {"transforms": ["hoist_imports", "chain_calls"], "scaffold": "minimal"}},
            {"name": "env-only",
             "model": "anthropic/claude-haiku-4-5",
             "approach": {"transforms": ["hoist_imports", "precompile_literals"],
                          "scaffold": "env_only"}},
            {"name": "chained",
             "model": "anthropic/claude-sonnet-5",
             "approach": {"transforms": ["hoist_imports", "chain_calls"], "scaffold": "full"}},
            # Spares: generated only if one of the above is discarded by the gate.
            {"name": "memoized",
             "model": "anthropic/claude-opus-4-8",
             "approach": {"transforms": ["hoist_imports", "precompile_literals", "memoize"],
                          "scaffold": "full"}},
            {"name": "hoisted",
             "model": "anthropic/claude-opus-4-8",
             "approach": {"transforms": ["hoist_imports"], "scaffold": "full"}},
            {"name": "precompiled-chained",
             "model": "anthropic/claude-opus-4-8",
             "approach": {"transforms": ["hoist_imports", "precompile_literals", "chain_calls"],
                          "scaffold": "full"}},
        ],
        "judges": [
            {"name": "judge-a", "backend": "rubric", "model": "anthropic/claude-opus-4-8",
             "strictness": 1.0,
             "weights": {
                 "config_completeness": {"error_type": 1, "raises_when_absent": 2,
                                         "env_source": 1, "registry_walk_up": 1,
                                         "configure_hook": 1, "config_template": 1,
                                         "trace_from_config": 2, "bug_reports": 1},
                 "efficiency": {"runtime_s": 3, "peak_bytes": 1, "retained_blocks": 1},
                 "readability": {"docstring_coverage": 2, "comment_density": 1,
                                 "mean_function_length": 1, "max_nesting": 1,
                                 "long_line_ratio": 1, "identifier_quality": 1}}},
            {"name": "judge-b", "backend": "rubric", "model": "anthropic/claude-sonnet-5",
             "strictness": 1.3,
             "weights": {
                 "config_completeness": {"error_type": 1, "raises_when_absent": 3,
                                         "env_source": 2, "registry_walk_up": 2,
                                         "configure_hook": 1, "config_template": 1,
                                         "trace_from_config": 3, "bug_reports": 1},
                 "efficiency": {"runtime_s": 1, "peak_bytes": 2, "retained_blocks": 2},
                 "readability": {"docstring_coverage": 1, "comment_density": 1,
                                 "mean_function_length": 2, "max_nesting": 2,
                                 "long_line_ratio": 1, "identifier_quality": 2}}},
            {"name": "judge-c", "backend": "rubric", "model": "anthropic/claude-haiku-4-5",
             "strictness": 0.8,
             "weights": {
                 "config_completeness": {"error_type": 2, "raises_when_absent": 1,
                                         "env_source": 1, "registry_walk_up": 1,
                                         "configure_hook": 2, "config_template": 2,
                                         "trace_from_config": 1, "bug_reports": 2},
                 "efficiency": {"runtime_s": 2, "peak_bytes": 2, "retained_blocks": 1},
                 "readability": {"docstring_coverage": 3, "comment_density": 2,
                                 "mean_function_length": 1, "max_nesting": 1,
                                 "long_line_ratio": 2, "identifier_quality": 1}}},
        ],
        "litellm": {
            "_comment": "Used only when 'generator' or a judge's 'backend' is \"litellm\". "
                        "Routed through litellm.completion(model=..., messages=[...]) so the "
                        "model set is this config, never code. litellm is NOT installed in this "
                        "checkout; selecting it here raises a ConfigError naming it.",
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────────── the input: a module + its exemplars ───────────────────────────

def git_blob_sha1(raw):
    """Return the git blob sha1 of `raw` bytes — the same hash `git hash-object` prints."""
    return hashlib.sha1(b"blob %d\x00" % len(raw) + raw).hexdigest()


def load_original(path):
    """Read the original unit from a .py file. Returns a `(source, facts)` pair.

    `facts` carries the path, the byte size and the git blob sha1 actually computed, so a
    caller can prove which bytes ran.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise ConfigError("could not read the module at %s: %s" % (path, exc)) from exc
    return raw.decode("utf-8"), {
        "origin": os.path.abspath(path),
        "how": "--module",
        "size": len(raw),
        "blob_sha1": git_blob_sha1(raw),
        "blob_verified": False,
    }


def original_from_rewrite(path):
    """Extract the ORIGINAL unit from a landed forge2 rewrite. Returns a `(source, facts)` pair.

    Every landed forge2 rewrite embeds the original byte-for-byte as `ORIGINAL_SOURCE`, beside
    the git blob sha1 those bytes must hash to (`ORIGINAL_BLOB_SHA1`) and often their size
    (`ORIGINAL_SIZE`). This reads the rewrite's AST — it does not import or execute it — and
    REFUSES to return bytes that do not hash to the recorded sha1.

    Raises:
        ConfigError: if the file has no ORIGINAL_SOURCE, or the bytes do not match the sha1
            recorded beside them.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise ConfigError("could not read the rewrite at %s: %s" % (path, exc)) from exc

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ConfigError("the rewrite at %s does not parse as Python: %s" % (path, exc)) from exc

    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in (
                    "ORIGINAL_SOURCE", "ORIGINAL_BLOB_SHA1", "ORIGINAL_SIZE"):
                try:
                    found[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass

    if "ORIGINAL_SOURCE" not in found:
        raise ConfigError(
            "the rewrite at %s embeds no ORIGINAL_SOURCE, so the original cannot be recovered "
            "from it. Point --module at the original unit's own .py file instead." % path
        )

    raw = found["ORIGINAL_SOURCE"].encode("utf-8")
    facts = {
        "origin": os.path.abspath(path),
        "how": "--from-rewrite (ORIGINAL_SOURCE embedded in the landed rewrite)",
        "size": len(raw),
        "blob_sha1": git_blob_sha1(raw),
        "blob_verified": False,
    }

    recorded = found.get("ORIGINAL_BLOB_SHA1")
    if recorded:
        if facts["blob_sha1"] != recorded:
            raise ConfigError(
                "the ORIGINAL_SOURCE embedded in %s hashes to git blob %s, but the file records "
                "ORIGINAL_BLOB_SHA1 = %s. Refusing to run a tournament against bytes that are "
                "not the original." % (path, facts["blob_sha1"], recorded)
            )
        facts["blob_verified"] = True
        facts["recorded_blob_sha1"] = recorded
    if "ORIGINAL_SIZE" in found and found["ORIGINAL_SIZE"] != facts["size"]:
        raise ConfigError(
            "the ORIGINAL_SOURCE embedded in %s is %d bytes, but the file records "
            "ORIGINAL_SIZE = %d." % (path, facts["size"], found["ORIGINAL_SIZE"])
        )
    return found["ORIGINAL_SOURCE"], facts


def _passthrough_trace(fn):
    """A stand-in telemetry decorator: record nothing, return the wrapped result unchanged.

    This is what `oracle_stubs: {"code_pipeline": "passthrough"}` installs. It is sound because
    a trace hook IS telemetry — it returns the wrapped result unchanged — which is exactly why
    the originals' captured exemplars are plain values rather than traced ones.
    """
    return fn


def _stub_modules(stubs):
    """Yield a context in which each name in `stubs` is an importable stand-in module.

    `stubs` maps a module name to a stub kind; "passthrough" builds a module whose every
    attribute is the identity decorator, which is what an original's hardcoded telemetry import
    needs. sys.modules is left exactly as it was found.
    """
    import types

    class _Passthrough(types.ModuleType):
        def __getattr__(self, attr):
            if attr.startswith("__"):
                raise AttributeError(attr)
            return _passthrough_trace

    @contextlib.contextmanager
    def manager():
        saved = {}
        for name, kind in (stubs or {}).items():
            if kind != "passthrough":
                raise ConfigError(
                    "oracle_stubs[%r] is %r, but the only stub kind this tool knows is "
                    "\"passthrough\" (a telemetry decorator that returns the wrapped result "
                    "unchanged)" % (name, kind)
                )
            saved[name] = sys.modules.get(name, KeyError)
            sys.modules[name] = _Passthrough(name)
        try:
            yield
        finally:
            for name, previous in saved.items():
                if previous is KeyError:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous

    return manager()


def parse_unit(source, origin="<original>"):
    """Parse the original and return its shape as a dict.

    Returns keys:
        name        the entry point's name — the unit's callable surface
        params      its positional parameter names, in order
        body        its body, as AST statements
        decorators  the decorator expressions it carried, as source strings
        imports     the module-level import statements the original made

    The entry point is the LAST module-level function definition, which is what an original
    forge unit has exactly one of.

    Raises:
        ConfigError: if the source does not parse, or defines no module-level function.
    """
    try:
        tree = ast.parse(source, filename=origin)
    except SyntaxError as exc:
        raise ConfigError(
            "the original at %s does not parse as Python: %s" % (origin, exc)) from exc

    functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not functions:
        raise ConfigError(
            "the original at %s defines no module-level function, so it has no callable surface "
            "to rewrite" % origin
        )
    entry = functions[-1]
    if isinstance(entry, ast.AsyncFunctionDef):
        raise ConfigError(
            "the original at %s defines an async entry point (%s); this harness benchmarks and "
            "gates synchronous callables only" % (origin, entry.name)
        )

    args = entry.args
    if args.vararg or args.kwarg or args.kwonlyargs:
        raise ConfigError(
            "the original at %s has an entry point (%s) with *args/**kwargs/keyword-only "
            "parameters; this harness mines exemplars for positional parameters only"
            % (origin, entry.name)
        )

    return {
        "name": entry.name,
        "params": [a.arg for a in args.posonlyargs] + [a.arg for a in args.args],
        "body": entry.body,
        "decorators": [ast.unparse(d) for d in entry.decorator_list],
        "imports": [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))],
    }


def build_oracle(source, stubs, origin="<the original>"):
    """Execute the original and return its entry callable, plus the unit shape.

    Returns `(callable, unit)`. The original's hardcoded telemetry import is satisfied by
    `stubs` for the duration of the exec, and sys.modules is restored afterwards. Writes
    nothing and imports nothing beyond what the original itself imports.
    """
    unit = parse_unit(source, origin)
    namespace = {"__name__": "__forge_original__", "__file__": origin}
    with _stub_modules(stubs):
        bytecode_was = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            exec(compile(source, origin, "exec"), namespace)
        except Exception as exc:  # noqa: BLE001 — a bad original is a config error, not a crash
            raise ConfigError(
                "the original at %s could not be executed: %s: %s. If it imports a module this "
                "checkout lacks, name that module in the config's oracle_stubs."
                % (origin, type(exc).__name__, exc)
            ) from exc
        finally:
            sys.dont_write_bytecode = bytecode_was
    fn = namespace.get(unit["name"])
    if not callable(fn):
        raise ConfigError(
            "the original at %s defines %s, but it is not callable after execution"
            % (origin, unit["name"])
        )
    return fn, unit


# ─────────────────────────── exemplars (the #200 seam) ───────────────────────────

class Raised:
    """A stand-in for a call that raised, so a comparison can report it rather than abort.

    Carries the exception's TYPE NAME only. That is deliberate: the original's contract is the
    exception type it raises (`TypeError`), not the message text, which varies between Python
    versions and between an inline `re.sub` and a compiled pattern's `.sub`.
    """

    __slots__ = ("kind",)

    def __init__(self, exception):
        self.kind = type(exception).__name__

    def __eq__(self, other):
        return isinstance(other, Raised) and other.kind == self.kind

    def __hash__(self):
        return hash(("Raised", self.kind))

    def __repr__(self):
        return "<raised %s>" % self.kind


def attempt(fn, args):
    """Call `fn(*args)` and return its result, or a `Raised` if it raised anything."""
    try:
        return fn(*args)
    except BaseException as exc:  # noqa: BLE001 — an oracle probe must survive anything
        return Raised(exc)


def same(got, want):
    """Compare the way an oracle does: equal in VALUE and in TYPE.

    `==` alone would call the int `1` a match for the bool `True`, and `2.0` a match for `2`.
    The originals return their argument itself below a base case and a built value above it, so
    the type is part of the behavior being preserved.
    """
    if isinstance(want, Raised) or isinstance(got, Raised):
        return got == want
    return type(got) is type(want) and got == want


def branch_constants(unit):
    """Return the literal constants the unit's own body mentions, in source order.

    This is what every landed forge2 rewrite records of criteria_miner: it probes "around the
    function's own branch constants". A unit's branch constants are the literals in its body —
    for `slugify` those are its three regex patterns, its `'-'` replacement and its `''`.
    """
    out = []
    for node in unit["body"]:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, (str, int, float, bytes)):
                if not any(same(sub.value, seen) for seen in out):
                    out.append(sub.value)
    return out


def mine_exemplars(oracle, unit, config):
    """Mine behavioral exemplars from the ORIGINAL acting as the oracle. Returns a dict.

    This is the built-in stand-in for #200/criteria_miner, which does not exist in this
    checkout. It mirrors the behavior every landed forge2 rewrite records of that miner: probe
    around the function's own branch constants, plus the config's `probe_pool`, and record what
    the ORIGINAL answers — a value, or the TYPE of the exception it raised.

    Its honest limit is criteria_miner's own, and every landed rewrite records it: these cover
    the SAMPLED inputs and are NOT a proof of total equivalence. They are a refactor-drift net.

    For a unit of arity 1 every probe is tried once. For higher arity the probes are combined
    pairwise from the pool, capped at the config's `max_exemplars`, because the full product
    grows as pool**arity.
    """
    pool = list(branch_constants(unit))
    for extra in require(config, "probe_pool", "the inputs exemplars are mined at"):
        if not any(same(extra, seen) for seen in pool):
            pool.append(extra)
    cap = require(config, "max_exemplars", "the cap on how many exemplars are mined")

    arity = len(unit["params"])
    if arity == 0:
        arg_tuples = [()]
    elif arity == 1:
        arg_tuples = [(p,) for p in pool]
    else:
        arg_tuples = []
        for i, first in enumerate(pool):
            for second in pool[: max(1, cap // max(1, len(pool)))]:
                arg_tuples.append((first, second) + tuple(pool[0] for _ in range(arity - 2)))
            if len(arg_tuples) >= cap:
                break
    arg_tuples = arg_tuples[:cap]

    cases = []
    for args in arg_tuples:
        result = attempt(oracle, args)
        case = {"args": repr(tuple(args))}
        if isinstance(result, Raised):
            case["raises"] = result.kind
        else:
            case["result"] = repr(result)
            # Only keep a case whose result round-trips through repr/literal_eval, so the
            # exemplar file is a faithful record rather than a lossy one.
            try:
                if not same(ast.literal_eval(case["result"]), result):
                    continue
            except (ValueError, SyntaxError):
                continue
        cases.append(case)

    return {
        "unit": unit["name"],
        "arity": arity,
        "mined_by": "%s builtin mine_exemplars (the #200/criteria_miner seam)" % TOOL,
        "limit": "covers the SAMPLED inputs only — NOT a proof of total equivalence",
        "cases": cases,
    }


def decode_exemplars(exemplars):
    """Turn an exemplar document's literal reprs back into Python values.

    Returns a list of `(args_tuple, expected)` pairs, where `expected` is a value or a `Raised`.

    Raises:
        ConfigError: if a case's `args`, `result` or `raises` is not a readable Python literal.
    """
    out = []
    for index, case in enumerate(exemplars.get("cases", [])):
        try:
            args = ast.literal_eval(case["args"])
        except (KeyError, ValueError, SyntaxError) as exc:
            raise ConfigError(
                "exemplar case %d has no readable `args` literal: %s" % (index, exc)) from exc
        if not isinstance(args, tuple):
            args = (args,)
        if "raises" in case:
            marker = Raised.__new__(Raised)
            marker.kind = case["raises"]
            out.append((args, marker))
        else:
            try:
                out.append((args, ast.literal_eval(case["result"])))
            except (KeyError, ValueError, SyntaxError) as exc:
                raise ConfigError(
                    "exemplar case %d has no readable `result` literal: %s"
                    % (index, exc)) from exc
    return out


def load_exemplars(path):
    """Read a criteria_miner exemplar file. Returns the document.

    Raises:
        ConfigError: if it cannot be read as JSON or has no `cases` list.
    """
    document = _read_json(path, "the exemplar file")
    if not isinstance(document, dict) or not isinstance(document.get("cases"), list):
        raise ConfigError(
            "the exemplar file at %s must be a JSON object with a `cases` list; see this tool's "
            "docstring under EXEMPLARS for the shape" % path
        )
    return document


# ─────────────────────────── step 1: generate the candidates ───────────────────────────

#: The transform catalog. Each entry: what it does, and the IDEA it contributes — the idea text
#: is what `run` lists as graftable when a runner-up carrying it beats the winner.
TRANSFORMS = {
    "verbatim": "the original's body, unchanged — the baseline every other approach is a "
                "departure from",
    "hoist_imports": "function-local imports moved to module level, so the import machinery "
                     "runs once at load rather than on every call",
    "precompile_literals": "regex literals compiled once at module level instead of re-parsed "
                           "(from re's own cache) on every call",
    "chain_calls": "intermediate assignments folded into one expression, removing per-call "
                   "local stores",
    "memoize": "the core wrapped in functools.lru_cache, so a repeated argument is answered "
               "from cache",
    "coerce_str_args": "str() coercion prepended to every parameter — the plausible 'make it "
                       "robust' cleanup that silently changes behavior on non-string arguments",
}

SCAFFOLDS = {
    "full": "ConfigError + env-var config + registry walk-up + configure() + emit-config + "
            "bug_reports + the trace hook named by config",
    "env_only": "config from the environment variable only — no registry walk-up, no "
                "bug_reports",
    "minimal": "the bare function with the trace hook hardcoded off — no config at all",
}


def _copy(node):
    """Return a deep copy of an AST node, so a transform never mutates its input."""
    return ast.parse(ast.unparse(ast.Module(body=[node], type_ignores=[]))).body[0] \
        if isinstance(node, ast.stmt) else ast.parse(ast.unparse(node), mode="eval").body


class _Unit(dict):
    """A unit under transformation: the shape from `parse_unit`, plus a `preamble` of
    module-level statements the transforms have hoisted or created, and `notes` recording which
    transforms actually applied."""


def _fresh_unit(unit):
    parsed = _Unit(unit)
    parsed["body"] = [_copy(stmt) for stmt in unit["body"]]
    parsed["preamble"] = []
    parsed["decorate"] = []
    parsed["notes"] = []
    return parsed


def _t_verbatim(unit):
    unit["notes"].append("verbatim: the original's body, unchanged")
    return unit


def _t_hoist_imports(unit):
    """Move import statements out of the function body up to module level."""
    kept, hoisted = [], []
    for stmt in unit["body"]:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            hoisted.append(stmt)
        else:
            kept.append(stmt)
    if not hoisted:
        unit["notes"].append("hoist_imports: DID NOT APPLY — the body has no local imports")
        return unit
    unit["body"] = kept
    unit["preamble"].extend(hoisted)
    unit["notes"].append("hoist_imports: hoisted %s" % ", ".join(ast.unparse(h) for h in hoisted))
    return unit


#: The `re` functions whose FIRST argument is the pattern, so a string literal there can be
#: compiled once at module level and the call rewritten onto the compiled object.
_RE_PATTERN_FIRST = ("sub", "subn", "match", "search", "fullmatch", "findall", "finditer", "split")


def _t_precompile_literals(unit):
    """Hoist `re.<fn>('literal', ...)` into a module-level `re.compile('literal')`.

    A compiled pattern's `.sub` and the module-level `re.sub` of the same pattern string are the
    same operation — `re.sub` itself compiles and caches — including the TypeError each raises
    on a subject of the wrong type. The gate checks that rather than taking it on trust.
    """
    patterns = {}

    class Rewriter(ast.NodeTransformer):
        def visit_Call(self, node):  # noqa: N802 — the NodeTransformer protocol
            self.generic_visit(node)
            func = node.func
            if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                    and func.value.id == "re" and func.attr in _RE_PATTERN_FIRST
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                literal = node.args[0].value
                if literal not in patterns:
                    patterns[literal] = "_PATTERN_%d" % (len(patterns) + 1)
                return ast.Call(
                    func=ast.Attribute(value=ast.Name(id=patterns[literal], ctx=ast.Load()),
                                       attr=func.attr, ctx=ast.Load()),
                    args=node.args[1:], keywords=node.keywords)
            return node

    unit["body"] = [ast.fix_missing_locations(Rewriter().visit(stmt)) for stmt in unit["body"]]
    if not patterns:
        unit["notes"].append(
            "precompile_literals: DID NOT APPLY — the body has no re.<fn>('literal', ...) call")
        return unit

    if not any(isinstance(s, ast.Import) and any(a.name == "re" for a in s.names)
               for s in unit["preamble"]):
        unit["preamble"].insert(0, ast.parse("import re").body[0])
    for literal, name in patterns.items():
        unit["preamble"].append(
            ast.parse("%s = re.compile(%r)" % (name, literal)).body[0])
    unit["notes"].append(
        "precompile_literals: compiled %d pattern(s) once at module level: %s"
        % (len(patterns), ", ".join(sorted(repr(p) for p in patterns))))
    return unit


def _count_name(tree, name):
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == name)


class _Substituter(ast.NodeTransformer):
    def __init__(self, name, replacement):
        self.name = name
        self.replacement = replacement

    def visit_Name(self, node):  # noqa: N802 — the NodeTransformer protocol
        if node.id == self.name and isinstance(node.ctx, ast.Load):
            return self.replacement
        return node


def _t_chain_calls(unit):
    """Fold `x = f(x); x = g(x); return x` into `return g(f(x))`.

    Applies only when the body is a run of single-name assignments ending in `return <name>`,
    and only when each folded name appears EXACTLY ONCE in the expression that consumes it —
    substituting a name that appears twice would evaluate its expression twice and could change
    behavior. Anything else leaves the body alone.
    """
    env = {}
    folded_count = 0
    for stmt in unit["body"]:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                and isinstance(stmt.targets[0], ast.Name):
            value = stmt.value
            for name, expr in env.items():
                if _count_name(value, name) > 1:
                    unit["notes"].append(
                        "chain_calls: DID NOT APPLY — %r is consumed more than once, so folding "
                        "it would evaluate its expression twice" % name)
                    return unit
            for name, expr in list(env.items()):
                value = _Substituter(name, expr).visit(value)
            env[stmt.targets[0].id] = value
            folded_count += 1
        elif isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Name) \
                and stmt.value.id in env:
            folded = ast.Return(value=env[stmt.value.id])
            unit["body"] = [ast.fix_missing_locations(folded)]
            # Count ASSIGNMENTS folded, not names bound: `s` reassigned three times is three
            # assignments folded away and one name, and the count a reader wants is the former.
            unit["notes"].append("chain_calls: folded %d assignment(s) into one expression"
                                 % folded_count)
            return unit
        else:
            unit["notes"].append(
                "chain_calls: DID NOT APPLY — the body is not a run of single-name assignments "
                "ending in `return <name>` (stopped at `%s`)" % ast.unparse(stmt).splitlines()[0])
            return unit
    unit["notes"].append("chain_calls: DID NOT APPLY — the body does not end in `return <name>`")
    return unit


def _t_memoize(unit):
    """Wrap the core in functools.lru_cache."""
    if not any(isinstance(s, ast.Import) and any(a.name == "functools" for a in s.names)
               for s in unit["preamble"]):
        unit["preamble"].insert(0, ast.parse("import functools").body[0])
    unit["decorate"].append("functools.lru_cache(maxsize=None)")
    unit["notes"].append("memoize: the core is wrapped in functools.lru_cache(maxsize=None)")
    return unit


def _t_coerce_str_args(unit):
    """Prepend `p = str(p)` for every parameter.

    This is the plausible "make it robust" cleanup, and it is in the catalog because it is what
    the gate exists to catch: it makes the unit answer a value where the original raised.
    """
    if not unit["params"]:
        unit["notes"].append("coerce_str_args: DID NOT APPLY — the unit takes no parameters")
        return unit
    coercions = [ast.parse("%s = str(%s)" % (p, p)).body[0] for p in unit["params"]]
    unit["body"] = coercions + unit["body"]
    unit["notes"].append("coerce_str_args: str() coercion prepended for %s"
                         % ", ".join(unit["params"]))
    return unit


_TRANSFORM_FUNCTIONS = {
    "verbatim": _t_verbatim,
    "hoist_imports": _t_hoist_imports,
    "precompile_literals": _t_precompile_literals,
    "chain_calls": _t_chain_calls,
    "memoize": _t_memoize,
    "coerce_str_args": _t_coerce_str_args,
}


def _render_core(unit):
    """Render the transformed unit as the source of a module-level `_core` function."""
    decorators = "".join("@%s\n" % d for d in unit["decorate"])
    body = "\n".join("    " + line if line else ""
                     for stmt in unit["body"]
                     for line in ast.unparse(stmt).splitlines())
    signature = ", ".join(unit["params"])
    return "%sdef _core(%s):\n    \"\"\"The rewritten unit body.\"\"\"\n%s\n" % (
        decorators, signature, body)


def _render_preamble(unit):
    return "\n".join(ast.unparse(stmt) for stmt in unit["preamble"])


_CONFIG_BLOCK_FULL = '''
class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    #200 requirement 4: a unit that cannot see its config throws rather than guessing.
    """


_ACTIVE = None
_RESOLVED = None
_IMPL_CACHE = {}


def find_registry(start=None):
    """Walk UP from `start` (default: this file's directory) for the nearest registry."""
    directory = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))
    while True:
        candidate = os.path.join(directory, REGISTRY_NAME)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def load_config(start=None):
    """Resolve this unit's config object from disk: the env var first, then the registry."""
    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        if not os.path.isfile(env_path):
            raise ConfigError("%s is set to %r, but no such file exists" % (CONFIG_ENV, env_path))
        with open(env_path, "r", encoding="utf-8") as handle:
            return json.load(handle), "%s=%s" % (CONFIG_ENV, env_path)
    registry_path = find_registry(start)
    if registry_path is None:
        raise ConfigError(
            "no config object for %s: %s is unset and no %s was found by walking up from this "
            "module. Run `emit-config` for a template." % (UNIT, CONFIG_ENV, REGISTRY_NAME))
    with open(registry_path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    node = document
    for key in UNIT_PATH:
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section."
                % (registry_path, UNIT, key))
        node = node[key]
    if "bug_reports" not in node and "bug_reports" in document:
        node = dict(node, bug_reports=document["bug_reports"])
    return node, registry_path


def active_config():
    """Return the config object in force: the injected one, else the disk resolution."""
    global _RESOLVED
    if _ACTIVE is not None:
        return _ACTIVE[0]
    if _RESOLVED is None:
        _RESOLVED = load_config()
    return _RESOLVED[0]


def configure(config):
    """Inject `config` as this unit's config object for this process, in memory."""
    global _ACTIVE, _IMPL_CACHE
    previous = _ACTIVE
    _ACTIVE = None if config is None else (config, "injected via configure()")
    _IMPL_CACHE = {}
    return previous


def config_template():
    """Return a template of this unit's config object — scaffolding, never a default."""
    return {"trace": None, "bug_reports": "logs/bug_reports.jsonl"}


def _load_attr(spec):
    """Resolve a "module:attr" string to the attribute it names."""
    if ":" not in spec:
        raise ConfigError(
            "config key 'trace' for %s must look like \\"module:attr\\"; got %r" % (UNIT, spec))
    mod_name, _, attr = spec.partition(":")
    try:
        module = sys.modules.get(mod_name) or importlib.import_module(mod_name)
    except ImportError as exc:
        raise ConfigError(
            "config key 'trace' for %s names module %r, which cannot be imported: %s"
            % (UNIT, mod_name, exc)) from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ConfigError(
            "config key 'trace' for %s names %r, but %r has no attribute %r"
            % (UNIT, spec, mod_name, attr)) from exc


def _traced_core():
    """Return `_core`, wrapped in the config's trace hook when one is named."""
    cfg = active_config()
    if "trace" not in cfg:
        raise ConfigError(
            "config object for %s is missing the required key 'trace' (null for no hook, or a "
            "\\"module:attr\\" string). Run `emit-config` for a template." % UNIT)
    spec = cfg["trace"]
    if spec is not None and not isinstance(spec, str):
        raise ConfigError(
            "config key 'trace' for %s must be null or a \\"module:attr\\" string, not %s"
            % (UNIT, type(spec).__name__))
    if spec not in _IMPL_CACHE:
        _IMPL_CACHE[spec] = _core if spec is None else _load_attr(spec)(_core)
    return _IMPL_CACHE[spec]
'''

_CONFIG_BLOCK_ENV_ONLY = '''
class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key."""


_ACTIVE = None
_RESOLVED = None
_IMPL_CACHE = {}


def load_config():
    """Resolve this unit's config object from the environment variable. No registry walk-up."""
    env_path = os.environ.get(CONFIG_ENV)
    if not env_path:
        raise ConfigError(
            "no config object for %s: %s is unset. Run `emit-config` for a template."
            % (UNIT, CONFIG_ENV))
    if not os.path.isfile(env_path):
        raise ConfigError("%s is set to %r, but no such file exists" % (CONFIG_ENV, env_path))
    with open(env_path, "r", encoding="utf-8") as handle:
        return json.load(handle), "%s=%s" % (CONFIG_ENV, env_path)


def active_config():
    """Return the config object in force: the injected one, else the disk resolution."""
    global _RESOLVED
    if _ACTIVE is not None:
        return _ACTIVE[0]
    if _RESOLVED is None:
        _RESOLVED = load_config()
    return _RESOLVED[0]


def configure(config):
    """Inject `config` as this unit's config object for this process, in memory."""
    global _ACTIVE, _IMPL_CACHE
    previous = _ACTIVE
    _ACTIVE = None if config is None else (config, "injected via configure()")
    _IMPL_CACHE = {}
    return previous


def config_template():
    """Return a template of this unit's config object — scaffolding, never a default."""
    return {"trace": None}


def _load_attr(spec):
    """Resolve a "module:attr" string to the attribute it names."""
    mod_name, _, attr = spec.partition(":")
    module = sys.modules.get(mod_name) or importlib.import_module(mod_name)
    return getattr(module, attr)


def _traced_core():
    """Return `_core`, wrapped in the config's trace hook when one is named."""
    cfg = active_config()
    if "trace" not in cfg:
        raise ConfigError(
            "config object for %s is missing the required key 'trace'" % UNIT)
    spec = cfg["trace"]
    if spec not in _IMPL_CACHE:
        _IMPL_CACHE[spec] = _core if spec is None else _load_attr(spec)(_core)
    return _IMPL_CACHE[spec]
'''

_CONFIG_BLOCK_MINIMAL = '''
def _traced_core():
    """Return the core. This unit has no configuration: the trace hook is off, hardcoded."""
    return _core
'''

_SCAFFOLD_HEADERS = {
    "full": (
        "import importlib\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "\n"
        "CONFIG_ENV = 'FORGE2_CONFIG'\n"
        "REGISTRY_NAME = 'registry.json'\n"
        "UNIT_PATH = {unit_path!r}\n"
        "UNIT = {unit!r}\n"
    ),
    "env_only": (
        "import importlib\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "\n"
        "CONFIG_ENV = 'FORGE2_CONFIG'\n"
        "UNIT = {unit!r}\n"
    ),
    "minimal": "",
}

_SCAFFOLD_BLOCKS = {
    "full": _CONFIG_BLOCK_FULL,
    "env_only": _CONFIG_BLOCK_ENV_ONLY,
    "minimal": _CONFIG_BLOCK_MINIMAL,
}


def _candidate_docstring(unit_name, spec, notes):
    """Build the candidate module's docstring from the approach that produced it."""
    lines = [
        "forge2 rewrite candidate for the unit `%s` — generated by %s (ticket #207)." % (
            unit_name, TOOL),
        "",
        "Approach: transforms %s on the scaffold %r." % (
            ", ".join(spec["transforms"]), spec["scaffold"]),
        "",
        "Scaffold: %s." % SCAFFOLDS[spec["scaffold"]],
        "",
        "What each transform did to the original's body:",
    ]
    lines += ["  * %s" % note for note in notes]
    lines += [
        "",
        "This candidate is a TOURNAMENT ENTRY, not a landed rewrite. It has been gated on",
        "behavioral equivalence with the original over the mined exemplars; see the tournament's",
        "deep-dive document for its bench numbers and panel scores.",
    ]
    return "\n".join(lines)


def _builtin_generate(original_source, unit, spec, entry_name):
    """Generate one candidate's source with the built-in transform+scaffold backend.

    Returns `(source, notes)`. `notes` records what each transform actually did — including
    "DID NOT APPLY", because a transform that silently no-ops would make two candidate configs
    produce the same module and the reader deserves to know which.
    """
    for name in spec["transforms"]:
        if name not in _TRANSFORM_FUNCTIONS:
            raise ConfigError(
                "unknown transform %r — the catalog is %s (run `list-approaches`)"
                % (name, ", ".join(sorted(_TRANSFORM_FUNCTIONS))))
    if spec["scaffold"] not in _SCAFFOLD_BLOCKS:
        raise ConfigError(
            "unknown scaffold %r — the catalog is %s (run `list-approaches`)"
            % (spec["scaffold"], ", ".join(sorted(_SCAFFOLD_BLOCKS))))

    working = _fresh_unit(unit)
    for name in spec["transforms"]:
        working = _TRANSFORM_FUNCTIONS[name](working)

    unit_id = "forge2:%s" % entry_name
    header = _SCAFFOLD_HEADERS[spec["scaffold"]].format(
        unit_path=("forge2", entry_name), unit=unit_id)
    preamble = _render_preamble(working)
    core = _render_core(working)
    surface = ", ".join(working["params"])

    parts = ['"""%s\n"""' % _candidate_docstring(entry_name, spec, working["notes"])]
    if header:
        parts.append(header.rstrip("\n"))
    if preamble:
        parts.append(preamble)
    parts.append(core.rstrip("\n"))
    parts.append(_SCAFFOLD_BLOCKS[spec["scaffold"]].strip("\n"))
    parts.append(
        'def %s(%s):\n'
        '    """Return the unit\'s result for %s — the rewrite of the forge unit `%s`."""\n'
        '    return _traced_core()(%s)\n' % (entry_name, surface, surface, entry_name, surface))
    return "\n\n\n".join(parts) + "\n", working["notes"]


def _litellm_completion(config, model, prompt):
    """Route one completion through litellm — the #184 seam. Returns the model's text.

    The model is the caller's, which comes from the config: the model set is config, never code.

    Raises:
        ConfigError: if litellm is not importable, or answers in a shape this cannot read.
    """
    try:
        litellm = importlib.import_module("litellm")
    except ImportError as exc:
        raise ConfigError(
            "this run selects the \"litellm\" backend, but the litellm package is not importable "
            "here (%s). Install it, or set `generator`/the judge's `backend` to the built-in "
            "backend." % exc
        ) from exc
    options = config.get("litellm", {})
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=options.get("temperature", 0.7),
        max_tokens=options.get("max_tokens", 4096),
    )
    try:
        return response["choices"][0]["message"]["content"]
    except (TypeError, KeyError, IndexError) as exc:
        raise ConfigError(
            "litellm.completion(model=%r) answered in a shape this tool cannot read "
            "(expected choices[0].message.content): %r" % (model, response)
        ) from exc


_CODE_FENCE = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)


def _strip_fence(text):
    """Return the code inside the first ``` fence, or the text unchanged if it has none."""
    match = _CODE_FENCE.search(text or "")
    return match.group(1) if match else (text or "")


def _litellm_generate(original_source, unit, spec, entry_name, model, config):
    """Generate one candidate by asking the model named by the config to write it (#184)."""
    prompt = (
        "Rewrite the Python module below so that it preserves its observable behavior EXACTLY "
        "while meeting refactor standard #200: it must be driven by a configuration object and "
        "must raise rather than guess a default when it cannot see that configuration.\n\n"
        "Keep the callable surface `%s(%s)` unchanged.\n"
        "The original hardcodes a telemetry decorator; that hook must instead be named by the "
        "config's `trace` key (null, or a \"module:attr\" string).\n"
        "Approach to take: %s. Scaffold: %s.\n\n"
        "Answer with one Python module in a ``` fence and nothing else.\n\n"
        "```python\n%s```\n"
        % (entry_name, ", ".join(unit["params"]),
           "; ".join("%s (%s)" % (t, TRANSFORMS.get(t, "")) for t in spec["transforms"]),
           SCAFFOLDS.get(spec["scaffold"], spec["scaffold"]),
           original_source)
    )
    text = _litellm_completion(config, model, prompt)
    source = _strip_fence(text)
    try:
        ast.parse(source)
    except SyntaxError as exc:
        raise TournamentError(
            "the model %r answered with source that does not parse (%s); this candidate cannot "
            "be gated" % (model, exc)) from exc
    return source, ["litellm: generated by %s" % model]


def generate_candidate(original_source, unit, candidate_config, config):
    """Generate one candidate rewrite. Returns `(source, notes)`.

    The backend is the config's `generator`: "builtin" applies this tool's transform+scaffold
    catalog; "litellm" asks the model named by this candidate's `model` field (#184). Either
    way the model set and the approach set are config, never code.
    """
    spec = candidate_config.get("approach")
    if not isinstance(spec, dict) or "transforms" not in spec or "scaffold" not in spec:
        raise ConfigError(
            "candidate %r has no usable `approach`: it needs a `transforms` list and a "
            "`scaffold` name (run `list-approaches` for the catalog)"
            % candidate_config.get("name", "?"))

    backend = require(config, "generator", "which backend writes the candidates")
    entry_name = unit["name"]
    if backend == "builtin":
        return _builtin_generate(original_source, unit, spec, entry_name)
    if backend == "litellm":
        model = candidate_config.get("model")
        if not model:
            raise ConfigError(
                "the \"litellm\" generator needs a `model` on every candidate; candidate %r has "
                "none" % candidate_config.get("name", "?"))
        return _litellm_generate(original_source, unit, spec, entry_name, model, config)
    raise ConfigError(
        "config key 'generator' is %r, but the backends this tool has are \"builtin\" and "
        "\"litellm\"" % backend)


# ─────────────────────────── step 2: the equivalence gate ───────────────────────────

def load_candidate(source, name, base_dir):
    """Execute a candidate's source in its own namespace and return `(namespace, entry)`.

    `base_dir` is the directory the candidate's `__file__` is reported to live in, so that a
    candidate whose scaffold walks UP for a registry finds the same one an installed copy beside
    the original would. Nothing is written there — `__file__` need not exist.

    Bytecode writing is switched off for the duration, so no `__pycache__` appears.

    Raises:
        TournamentError: if the candidate does not parse or does not execute.
    """
    filename = os.path.join(base_dir, "%s.py" % name)
    namespace = {"__name__": "candidate_%s" % name, "__file__": filename}
    bytecode_was = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        exec(compile(source, filename, "exec"), namespace)
    except Exception as exc:  # noqa: BLE001 — a broken candidate is a gate failure, not a crash
        raise TournamentError(
            "candidate %r does not execute: %s: %s" % (name, type(exc).__name__, exc)) from exc
    finally:
        sys.dont_write_bytecode = bytecode_was
    return namespace, filename


def install_candidate_config(namespace, trace=None):
    """Give a candidate its config object in memory, if its scaffold takes one.

    A `minimal` scaffold has no `configure`, by design — it is the candidate that ignored #200
    requirement 4, and the panel scores it for that. Returns True if a config was installed.
    """
    configure_fn = namespace.get("configure")
    if callable(configure_fn):
        configure_fn({"trace": trace, "bug_reports": "logs/bug_reports.jsonl"})
        return True
    return False


def gate_candidate(source, name, oracle_cases, base_dir, limit=6):
    """Check one candidate for behavioral equivalence with the original. Returns a verdict dict.

    `oracle_cases` is the decoded exemplar list — `(args, expected)` pairs, where `expected` is a
    value the ORIGINAL returned or a `Raised` naming the exception type it raised. A candidate
    passes only if it agrees on EVERY case, in value and in type.

    The verdict carries `passed`, the counts, and up to `limit` mismatches as
    `(args, expected, got)` reprs — enough for a reader to see WHY a candidate was discarded
    without dumping the whole table.
    """
    verdict = {"name": name, "passed": False, "checked": len(oracle_cases), "agreed": 0,
               "mismatches": [], "error": None}
    try:
        namespace, _ = load_candidate(source, name, base_dir)
    except TournamentError as exc:
        verdict["error"] = str(exc)
        return verdict

    entry = namespace.get(_entry_name_of(source))
    if not callable(entry):
        verdict["error"] = "candidate %r exposes no callable entry point" % name
        return verdict

    install_candidate_config(namespace, trace=None)

    agreed = 0
    for args, expected in oracle_cases:
        got = attempt(entry, args)
        if same(got, expected):
            agreed += 1
        elif len(verdict["mismatches"]) < limit:
            verdict["mismatches"].append((repr(args), repr(expected), repr(got)))
    verdict["agreed"] = agreed
    verdict["passed"] = agreed == len(oracle_cases) and not verdict["mismatches"]
    return verdict


def _entry_name_of(source):
    """Return the name of a candidate's entry point: its LAST module-level function."""
    tree = ast.parse(source)
    functions = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    return functions[-1] if functions else ""


# ─────────────────────────── step 3: the benchmark (the #203 seam) ───────────────────────────

def measure(fn, workload, repeats, warmup, filename=None, fresh=None, trace_frames=10,
            reset=None):
    """Measure one callable over `workload`. Returns the bench row.

    Keys: `runtime_s`, `peak_bytes`, `retained_blocks`, `retained_bytes`, `calls`.

    Runtime and memory are measured in SEPARATE passes, and each pass is set up the way its own
    measurement needs — which is not the same way:

      pass 1 (runtime, WARM)  `warmup` untimed sweeps first, so an import or a first-call regex
              compile lands outside the measurement, then `repeats` sweeps timed with
              `time.perf_counter` and no tracing. This is steady-state per-call cost, which is
              what a caller of a hot unit actually pays. Timing under tracemalloc would report
              the tracer — it roughly doubles the runtime it is meant to measure.

      pass 2 (memory, COLD)   `reset()` is called first, then tracing starts, then `fresh()`
              builds a NEW instance of the candidate INSIDE the traced window, and the workload
              is swept. Cold on purpose: a warm module has already made its module-level
              allocations and filled its caches, so a warm memory pass reports ~zero and
              measures nothing. Cold, the measurement includes what loading the module costs and
              what its first calls retain.

    `reset` exists because the interesting caches are SHARED, not per-candidate: `re` keeps one
    process-wide compiled-pattern cache, so whichever candidate ran first would be charged for
    filling it and every later candidate would look free. That is an order-dependent benchmark,
    which is no benchmark at all. `bench_candidate` passes `re.purge` here, so every candidate
    meets the same cold cache.

    What the memory numbers are, exactly:
      `peak_bytes`       the peak traced memory for the process during pass 2 — module load
                         through the whole sweep.
      `retained_blocks`  memory blocks still LIVE at the end of pass 2 whose traceback passes
                         through `filename` — the candidate's own code. `all_frames=True`, so an
                         allocation made by `re` on the candidate's behalf counts as the
                         candidate's.
      `retained_bytes`   the same blocks, in bytes.

    RETAINED, not allocated: tracemalloc snapshots what is LIVE, and CPython exposes no
    total-allocation counter, so "how many allocations did this make" is not a number that can
    honestly be reported here. What CAN be reported is what the candidate still HOLDS after
    doing the work — its module-level constants, its regex-cache entries, its `lru_cache`. That
    is a real cost and a real difference between these candidates, which is why it is measured
    and why it is named for what it is.
    """
    for _ in range(warmup):
        for args in workload:
            attempt(fn, args)

    start = time.perf_counter()
    for _ in range(repeats):
        for args in workload:
            attempt(fn, args)
    runtime = time.perf_counter() - start

    if reset:
        reset()
    tracing_was = tracemalloc.is_tracing()
    if tracing_was:
        tracemalloc.stop()
    tracemalloc.start(trace_frames)
    try:
        target = fresh() if fresh else fn
        for _ in range(repeats):
            for args in workload:
                attempt(target, args)
        snapshot = tracemalloc.take_snapshot()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
        if tracing_was:
            tracemalloc.start()

    if filename:
        snapshot = snapshot.filter_traces(
            [tracemalloc.Filter(True, filename, all_frames=True)])
    stats = snapshot.statistics("filename")

    return {
        "runtime_s": runtime,
        "peak_bytes": peak,
        "retained_blocks": sum(stat.count for stat in stats),
        "retained_bytes": sum(stat.size for stat in stats),
        "calls": repeats * len(workload),
    }


def _telemetry(config):
    """Return the measurement function in force — the config's #203 hook, else the built-in."""
    spec = config.get("telemetry")
    if spec is None:
        return measure
    if not isinstance(spec, str) or ":" not in spec:
        raise ConfigError(
            "config key 'telemetry' must be null (use the built-in measure()) or a "
            "\"module:attr\" string naming a telemetry hook (#203); got %r" % (spec,))
    mod_name, _, attr = spec.partition(":")
    try:
        module = sys.modules.get(mod_name) or importlib.import_module(mod_name)
    except ImportError as exc:
        raise ConfigError(
            "config key 'telemetry' names module %r, which cannot be imported: %s"
            % (mod_name, exc)) from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ConfigError(
            "config key 'telemetry' names %r, but module %r has no attribute %r"
            % (spec, mod_name, attr)) from exc


def bench_candidate(source, name, workload, base_dir, config):
    """Benchmark one PASSING candidate on the shared workload. Returns the bench row.

    `fresh` re-executes the candidate's module so the memory pass measures a COLD instance, and
    `reset` purges `re`'s process-wide compiled-pattern cache so every candidate meets the same
    cold shared state rather than the leftovers of whichever ran first. See `measure()`.
    """
    entry_name = _entry_name_of(source)

    def fresh():
        namespace, _ = load_candidate(source, name, base_dir)
        install_candidate_config(namespace, trace=None)
        return namespace[entry_name]

    warm = fresh()
    _, filename = load_candidate(source, name, base_dir)
    bench = require(config, "bench", "how many times the benchmark sweeps the workload")
    row = _telemetry(config)(
        warm, workload,
        repeats=bench.get("repeats", 2000),
        warmup=bench.get("warmup", 200),
        filename=filename,
        fresh=fresh,
        trace_frames=bench.get("trace_frames", 10),
        reset=re.purge,
    )
    row["name"] = name
    return row


# ─────────────────────────── step 4: the all-agent panel ───────────────────────────

#: The eight #200-requirement-4 features `config_completeness` looks for in a candidate's AST.
#: Each maps to a predicate over the parsed candidate; the judge's weights decide what each is
#: worth, so a strict judge and a lenient one score the same candidate differently from the same
#: measurements.
_CONFIG_FEATURES = (
    "error_type", "raises_when_absent", "env_source", "registry_walk_up", "configure_hook",
    "config_template", "trace_from_config", "bug_reports",
)


def config_metrics(source):
    """Measure a candidate's #200-requirement-4 config machinery from its AST.

    Returns a dict of the eight features to 0.0/1.0. These are MEASUREMENTS, not opinions: each
    is a fact about the candidate's syntax tree.
    """
    tree = ast.parse(source)
    names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    text = source

    raises = [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]
    raises_config_error = any(
        isinstance(r.exc, ast.Call) and isinstance(r.exc.func, ast.Name)
        and r.exc.func.id.endswith("ConfigError") for r in raises)

    return {
        "error_type": 1.0 if any(
            isinstance(n, ast.ClassDef) and n.name.endswith("ConfigError")
            for n in ast.walk(tree)) else 0.0,
        "raises_when_absent": 1.0 if raises_config_error else 0.0,
        "env_source": 1.0 if "CONFIG_ENV" in text and "environ" in text else 0.0,
        "registry_walk_up": 1.0 if "find_registry" in names else 0.0,
        "configure_hook": 1.0 if "configure" in names else 0.0,
        "config_template": 1.0 if "config_template" in names else 0.0,
        "trace_from_config": 1.0 if "_traced_core" in names and "'trace'" in text else 0.0,
        "bug_reports": 1.0 if "bug_reports" in text else 0.0,
    }


def readability_metrics(source):
    """Measure a candidate's readability from its AST and its text. Returns 0..1 per sub-metric.

    Every sub-metric is a real measurement, normalized so that 1.0 is good:

      docstring_coverage    fraction of the module + its functions/classes carrying a docstring
      comment_density       comment lines per code line, saturating at 1 comment per 4 lines
      mean_function_length  mean statements per function, best at <= 5, zero at >= 30
      max_nesting           deepest block nesting, best at <= 2, zero at >= 6
      long_line_ratio       fraction of lines at most 99 characters (the repo's own width)
      identifier_quality    fraction of assigned/def'd names that are not cryptic (>= 3 chars,
                            or a conventional short name)
    """
    tree = ast.parse(source)
    lines = source.splitlines()
    code_lines = [ln for ln in lines if ln.strip()]

    documentable = [tree] + [n for n in ast.walk(tree)
                             if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    documented = sum(1 for n in documentable if ast.get_docstring(n))
    docstring_coverage = documented / len(documentable) if documentable else 0.0

    comments = sum(1 for ln in lines if ln.strip().startswith("#"))
    comment_density = min(1.0, (comments / max(1, len(code_lines))) / 0.25)

    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    if functions:
        mean_len = statistics.mean(len(list(ast.walk(f))) / 6.0 for f in functions)
    else:
        mean_len = 0.0
    mean_function_length = max(0.0, min(1.0, (30.0 - mean_len) / 25.0))

    def depth(node, level=0):
        deepest = level
        for child in ast.iter_child_nodes(node):
            step = 1 if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)) else 0
            deepest = max(deepest, depth(child, level + step))
        return deepest

    nesting = depth(tree)
    max_nesting = max(0.0, min(1.0, (6.0 - nesting) / 4.0))

    long_line_ratio = (sum(1 for ln in lines if len(ln) <= 99) / len(lines)) if lines else 1.0

    identifiers = [n.name for n in functions]
    identifiers += [t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
                    for t in n.targets if isinstance(t, ast.Name)]
    conventional = {"s", "n", "a", "b", "i", "x", "fn", "re", "os"}
    if identifiers:
        good = sum(1 for name in identifiers
                   if len(name.lstrip("_")) >= 3 or name.lstrip("_") in conventional)
        identifier_quality = good / len(identifiers)
    else:
        identifier_quality = 1.0

    return {
        "docstring_coverage": docstring_coverage,
        "comment_density": comment_density,
        "mean_function_length": mean_function_length,
        "max_nesting": max_nesting,
        "long_line_ratio": long_line_ratio,
        "identifier_quality": identifier_quality,
    }


def efficiency_metrics(row, bounds):
    """Normalize one bench row against the run's best and worst. Returns 0..1 per sub-metric.

    1.0 is the best candidate in THIS run on that measure and 0.0 the worst; when every
    candidate ties, all score 1.0. Lower is better for all three measures, so the scale is
    inverted. This is why efficiency is scored from the BENCH and not from taste — the numbers
    are the ones `measure()` recorded on this machine.
    """
    out = {}
    for key in ("runtime_s", "peak_bytes", "retained_blocks"):
        low, high = bounds[key]
        out[key] = 1.0 if high <= low else (high - row[key]) / (high - low)
    return out


def _weighted(metrics, weights, strictness):
    """Combine 0..1 sub-metrics into a 0..10 score using a judge's weights and strictness.

    `strictness` is a gamma: >1 makes a judge harsher (a 0.8 becomes 0.74 at 1.3), <1 kinder.
    A weight of 0 drops a sub-metric from that judge's view entirely.
    """
    total = sum(max(0.0, float(w)) for w in weights.values())
    if total <= 0:
        raise ConfigError(
            "a judge's weights sum to zero, so it has no rubric to score with: %r" % (weights,))
    blended = sum(metrics.get(k, 0.0) * max(0.0, float(w)) for k, w in weights.items()) / total
    blended = min(1.0, max(0.0, blended))
    return round(10.0 * (blended ** max(0.01, float(strictness))), 3)


def _judge_weights(judge_config, criterion, defaults):
    weights = judge_config.get("weights", {}).get(criterion)
    if not weights:
        raise ConfigError(
            "judge %r has no weights for the criterion %r; every judge must state a rubric for "
            "all of %s" % (judge_config.get("name", "?"), criterion, ", ".join(CRITERIA)))
    unknown = set(weights) - set(defaults)
    if unknown:
        raise ConfigError(
            "judge %r weights unknown %s sub-metric(s) %s; the sub-metrics are %s"
            % (judge_config.get("name", "?"), criterion, ", ".join(sorted(unknown)),
               ", ".join(sorted(defaults))))
    return weights


def _rubric_judge(candidate, bench_row, bounds, judge_config):
    """Score one candidate with the built-in rubric backend. Returns a score per criterion.

    Real measurements of the candidate (its AST, its text, its bench row), combined with THIS
    judge's own weights and strictness. Two judges given different weights reach different
    scores from the same measurements — which is what makes the panel's median and its
    disagreement flag mean something.
    """
    config_m = config_metrics(candidate["source"])
    read_m = readability_metrics(candidate["source"])
    eff_m = efficiency_metrics(bench_row, bounds)
    strictness = judge_config.get("strictness", 1.0)
    return {
        "config_completeness": _weighted(
            config_m, _judge_weights(judge_config, "config_completeness", set(_CONFIG_FEATURES)),
            strictness),
        "efficiency": _weighted(
            eff_m, _judge_weights(judge_config, "efficiency",
                                  {"runtime_s", "peak_bytes", "retained_blocks"}),
            strictness),
        "readability": _weighted(
            read_m, _judge_weights(judge_config, "readability", set(read_m)), strictness),
    }


def _litellm_judge(candidate, bench_row, judge_config, config):
    """Score one candidate by asking the model named by the judge's config (#184)."""
    prompt = (
        "You are one judge on a blind panel scoring rewrites of a Python module. Score the "
        "module below out of 10 on each of three criteria:\n"
        "  config_completeness — how completely it is driven by a configuration object and "
        "refuses to guess a default when it cannot see one (refactor standard #200);\n"
        "  efficiency — judged from the measured benchmark below, not from reading;\n"
        "  readability — how easily a newcomer follows it.\n\n"
        "Measured benchmark for this candidate: runtime %.6f s over %d calls, peak %d bytes, "
        "%d memory blocks retained by its own code after the run.\n\n"
        "Answer with one JSON object and nothing else: "
        "{\"config_completeness\": n, \"efficiency\": n, \"readability\": n}\n\n"
        "```python\n%s```\n"
        % (bench_row["runtime_s"], bench_row["calls"], bench_row["peak_bytes"],
           bench_row["retained_blocks"], candidate["source"])
    )
    text = _litellm_completion(config, judge_config.get("model"), prompt)
    try:
        scores = json.loads(_strip_fence(text).strip() or "{}")
        return {c: float(scores[c]) for c in CRITERIA}
    except (ValueError, KeyError, TypeError) as exc:
        raise TournamentError(
            "judge %r (model %r) did not answer with a JSON object carrying %s: %r"
            % (judge_config.get("name", "?"), judge_config.get("model"), ", ".join(CRITERIA),
               text)) from exc


def judge_candidate(candidate, bench_row, bounds, judge_config, config):
    """Score ONE candidate with ONE judge. Returns {criterion: score}.

    This is where the panel's blindness lives, and it is structural rather than promised: this
    function is handed one candidate, its own bench row, the run's normalization bounds and its
    own judge config — and nothing else. There is no argument through which one judge could see
    another's scores, so no judge can be influenced by one. `selftest` proves it by permuting
    the judge order and requiring identical scores.
    """
    backend = judge_config.get("backend", "rubric")
    if backend == "rubric":
        return _rubric_judge(candidate, bench_row, bounds, judge_config)
    if backend == "litellm":
        return _litellm_judge(candidate, bench_row, judge_config, config)
    raise ConfigError(
        "judge %r has backend %r, but the backends this tool has are \"rubric\" and \"litellm\""
        % (judge_config.get("name", "?"), backend))


def run_panel(candidates, bench_rows, config):
    """Run every judge over every candidate. Returns {candidate: {criterion: {judge: score}}}.

    Judges are independent: each is called through `judge_candidate` with only its own candidate
    and bench row, and results are collected here, after the fact. No judge sees this table.
    """
    judges = require(config, "judges", "who scores the candidates")
    if not judges:
        raise ConfigError("config key 'judges' is empty: a panel needs at least one judge")

    bounds = {}
    for key in ("runtime_s", "peak_bytes", "retained_blocks"):
        values = [row[key] for row in bench_rows.values()]
        bounds[key] = (min(values), max(values))

    scores = {}
    for candidate in candidates:
        per_criterion = {c: {} for c in CRITERIA}
        for judge_config in judges:
            name = judge_config.get("name")
            if not name:
                raise ConfigError("every judge needs a `name`; one in the config has none")
            verdict = judge_candidate(candidate, bench_rows[candidate["name"]], bounds,
                                      judge_config, config)
            for criterion in CRITERIA:
                per_criterion[criterion][name] = verdict[criterion]
        scores[candidate["name"]] = per_criterion
    return scores, bounds


# ─────────────────────────── step 5: aggregate, rank, select ───────────────────────────

def aggregate(scores, config):
    """Aggregate the panel into medians, disagreement flags and a ranking. Returns a dict.

    Per candidate and criterion: the MEDIAN across judges (not the mean — one outlying judge
    should not move the verdict), the SPREAD (max - min), and a `disagreement` flag when the
    spread exceeds the config's `disagreement_threshold`. The flag is raised rather than
    resolved: a panel that disagrees is a fact about the candidate, and hiding it inside a
    median is how a tournament lies.

    Candidates are ranked by `overall` — the criterion-weighted mean of their medians. Ties are
    broken by name so a rank is reproducible.
    """
    threshold = require(config, "disagreement_threshold",
                        "how far apart judges may be before it is flagged")
    weights = require(config, "criterion_weights", "how the criteria are weighted into a rank")
    missing = [c for c in CRITERIA if c not in weights]
    if missing:
        raise ConfigError(
            "config key 'criterion_weights' is missing %s; all of %s must be weighted"
            % (", ".join(missing), ", ".join(CRITERIA)))
    total_weight = sum(float(weights[c]) for c in CRITERIA)
    if total_weight <= 0:
        raise ConfigError("config key 'criterion_weights' sums to zero, so nothing can be ranked")

    table = {}
    for name, per_criterion in scores.items():
        row = {}
        for criterion in CRITERIA:
            values = list(per_criterion[criterion].values())
            spread = max(values) - min(values)
            row[criterion] = {
                "median": round(statistics.median(values), 3),
                "spread": round(spread, 3),
                "disagreement": spread > float(threshold),
                "by_judge": dict(per_criterion[criterion]),
            }
        row["overall"] = round(
            sum(row[c]["median"] * float(weights[c]) for c in CRITERIA) / total_weight, 3)
        table[name] = row

    ranking = sorted(table, key=lambda n: (-table[n]["overall"], n))
    for position, name in enumerate(ranking, start=1):
        table[name]["rank"] = position
    return {"table": table, "ranking": ranking, "winner": ranking[0] if ranking else None}


def _ideas_behind(approach, criterion):
    """Name the part of an approach that could explain a lead on `criterion`.

    Attribution has to match what the criterion actually measures, or the graft is nonsense: a
    lead on config-completeness comes from the SCAFFOLD — the config machinery wrapped around
    the unit — and never from a transform, which only ever rewrites the unit's body. Efficiency
    is the other way round. Citing "regex literals compiled once" as the reason a candidate
    scored better on config-completeness would be a sourced-looking claim that is simply false.
    """
    scaffold = "scaffold `%s`: %s" % (approach["scaffold"], SCAFFOLDS[approach["scaffold"]])
    transforms = [TRANSFORMS[t] for t in approach["transforms"] if t in TRANSFORMS]
    if criterion == "config_completeness":
        return [scaffold]
    if criterion == "efficiency":
        return transforms
    return [scaffold] + transforms


def graftable_ideas(verdict, candidates_by_name):
    """List what the runners-up do BETTER than the winner. Returns a list of dicts.

    A tournament that only names a winner throws away most of what it learned. For every
    runner-up and every criterion where the runner-up's median BEATS the winner's, this records
    the gap and the part of that runner-up's approach that could explain it — so the graft is a
    specific, sourced suggestion rather than "look at the others too".
    """
    table = verdict["table"]
    winner = verdict["winner"]
    if winner is None:
        return []
    out = []
    for name in verdict["ranking"][1:]:
        for criterion in CRITERIA:
            gap = table[name][criterion]["median"] - table[winner][criterion]["median"]
            if gap > 0:
                out.append({
                    "from": name,
                    "criterion": criterion,
                    "gap": round(gap, 3),
                    "beats_winner": "%.3f vs the winner's %.3f" % (
                        table[name][criterion]["median"], table[winner][criterion]["median"]),
                    "ideas": _ideas_behind(candidates_by_name[name]["approach"], criterion),
                })
    return sorted(out, key=lambda g: -g["gap"])


def winner_rationale(verdict, bench_rows, candidates_by_name, gate_log):
    """Build the winner's rationale from the numbers that selected it. Returns a string.

    Every clause cites a measurement the reader can find in the tables above it, so the
    selection can be checked rather than believed.
    """
    winner = verdict["winner"]
    if winner is None:
        return "No candidate passed the gate, so no winner was selected."
    row = verdict["table"][winner]
    bench = bench_rows[winner]
    approach = candidates_by_name[winner]["approach"]
    ranking = verdict["ranking"]
    runner_up = ranking[1] if len(ranking) > 1 else None

    parts = [
        "`%s` wins with an overall %.3f — the criterion-weighted mean of its panel medians "
        "(config-completeness %.3f, efficiency %.3f, readability %.3f)."
        % (winner, row["overall"], row["config_completeness"]["median"],
           row["efficiency"]["median"], row["readability"]["median"]),
        "Its approach is %s on the %r scaffold."
        % (", ".join(approach["transforms"]), approach["scaffold"]),
        "It passed the equivalence gate on all %d exemplars, and benchmarked at %.6f s over %d "
        "calls with a %d-byte peak, retaining %d blocks (%d bytes) of its own."
        % (gate_log[winner]["checked"], bench["runtime_s"], bench["calls"], bench["peak_bytes"],
           bench["retained_blocks"], bench["retained_bytes"]),
    ]
    if runner_up:
        margin = row["overall"] - verdict["table"][runner_up]["overall"]
        parts.append(
            "It beat `%s` by %.3f overall." % (runner_up, margin) if margin > 0 else
            "It ties `%s` on overall score and wins on name order, which is the tie-break."
            % runner_up)
    flagged = [c for c in CRITERIA if row[c]["disagreement"]]
    if flagged:
        parts.append(
            "CAVEAT: the panel DISAGREED about the winner on %s (spread %s). The median selected "
            "it anyway; a reader who weights those criteria differently should look at the "
            "per-judge scores before trusting this pick."
            % (", ".join(flagged), ", ".join("%.3f" % row[c]["spread"] for c in flagged)))
    else:
        parts.append("The panel did not disagree about it on any criterion.")
    return " ".join(parts)


# ─────────────────────────── step 6: the deep dive + the scores table ───────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    module      TEXT NOT NULL,
    unit        TEXT NOT NULL,
    origin      TEXT NOT NULL,
    blob_sha1   TEXT,
    generated   INTEGER NOT NULL,
    passing     INTEGER NOT NULL,
    exemplars   INTEGER NOT NULL,
    winner      TEXT,
    deep_dive   TEXT
);
CREATE TABLE IF NOT EXISTS candidates (
    run_id       TEXT NOT NULL,
    name         TEXT NOT NULL,
    model        TEXT,
    transforms   TEXT NOT NULL,
    scaffold     TEXT NOT NULL,
    gate         TEXT NOT NULL,
    gate_detail  TEXT,
    runtime_s    REAL,
    peak_bytes   INTEGER,
    retained_blocks INTEGER,
    retained_bytes  INTEGER,
    calls        INTEGER,
    overall      REAL,
    rank         INTEGER,
    PRIMARY KEY (run_id, name)
);
CREATE TABLE IF NOT EXISTS scores (
    run_id    TEXT NOT NULL,
    candidate TEXT NOT NULL,
    criterion TEXT NOT NULL,
    judge     TEXT NOT NULL,
    model     TEXT,
    score     REAL NOT NULL,
    PRIMARY KEY (run_id, candidate, criterion, judge)
);
CREATE TABLE IF NOT EXISTS aggregates (
    run_id       TEXT NOT NULL,
    candidate    TEXT NOT NULL,
    criterion    TEXT NOT NULL,
    median       REAL NOT NULL,
    spread       REAL NOT NULL,
    disagreement INTEGER NOT NULL,
    PRIMARY KEY (run_id, candidate, criterion)
);
-- The queryable rebuild-scores view: every scored candidate of every module ever recorded
-- here, one row per criterion. This is what `query --best/--worst` reads, and it is why one
-- database across the whole forge2 rebuild answers "best/worst by criterion" rather than
-- "best in this run".
CREATE VIEW IF NOT EXISTS rebuild_scores AS
SELECT r.module        AS module,
       r.unit          AS unit,
       r.ts            AS ts,
       r.run_id        AS run_id,
       a.candidate     AS candidate,
       a.criterion     AS criterion,
       a.median        AS median,
       a.spread        AS spread,
       a.disagreement  AS disagreement,
       c.rank          AS rank,
       c.overall       AS overall,
       (c.name = r.winner) AS is_winner
FROM aggregates a
JOIN runs r       ON r.run_id = a.run_id
JOIN candidates c ON c.run_id = a.run_id AND c.name = a.candidate;
"""


def connect_scores(db_path):
    """Open (creating if needed) the rebuild-scores database for WRITING.

    This is `run`'s output, so creating it is the point. `query` uses `connect_scores_ro`
    instead, which creates nothing.
    """
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.executescript(_SCHEMA)
    return connection


def connect_scores_ro(db_path):
    """Open the rebuild-scores database STRICTLY read-only: never writes, never creates a file.

    Uses the sqlite URI `immutable=1` flag rather than `mode=ro`. A database `run` has written
    is in WAL journal mode, and opening a WAL database with `mode=ro` makes sqlite create
    `-wal`/`-shm` sidecar files beside it. `immutable=1` promises sqlite the file will not
    change, so it reads the identical committed data with no locking and creates zero files.
    """
    if not os.path.isfile(db_path):
        raise ConfigError(
            "no rebuild-scores database at %s — run a tournament first, or point --scores-db at "
            "one" % db_path)
    return sqlite3.connect("file:%s?immutable=1" % os.path.abspath(db_path), uri=True)


def record_scores(db_path, run):
    """Append one completed run to the rebuild-scores table. Returns the run id.

    Append-only across runs: a database accumulates every module of the whole rebuild, which is
    what makes `query` able to answer across it. Re-recording the same run_id replaces that
    run's rows rather than duplicating them.
    """
    connection = connect_scores(db_path)
    try:
        with connection:
            connection.execute("DELETE FROM runs WHERE run_id = ?", (run["run_id"],))
            connection.execute("DELETE FROM candidates WHERE run_id = ?", (run["run_id"],))
            connection.execute("DELETE FROM scores WHERE run_id = ?", (run["run_id"],))
            connection.execute("DELETE FROM aggregates WHERE run_id = ?", (run["run_id"],))
            connection.execute(
                "INSERT INTO runs (run_id, ts, module, unit, origin, blob_sha1, generated, "
                "passing, exemplars, winner, deep_dive) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (run["run_id"], run["ts"], run["module"], run["unit"], run["facts"]["origin"],
                 run["facts"]["blob_sha1"], run["generated"], run["passing"], run["exemplars"],
                 run["winner"], run["deep_dive"]))
            for name, candidate in run["candidates"].items():
                bench = run["bench"].get(name, {})
                table = run["verdict"]["table"].get(name, {})
                connection.execute(
                    "INSERT INTO candidates (run_id, name, model, transforms, scaffold, gate, "
                    "gate_detail, runtime_s, peak_bytes, retained_blocks, retained_bytes, "
                    "calls, overall, rank) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run["run_id"], name, candidate.get("model"),
                     ",".join(candidate["approach"]["transforms"]),
                     candidate["approach"]["scaffold"],
                     "PASS" if run["gate"][name]["passed"] else "DISCARDED",
                     run["gate"][name].get("error") or json.dumps(run["gate"][name]["mismatches"]),
                     bench.get("runtime_s"), bench.get("peak_bytes"),
                     bench.get("retained_blocks"), bench.get("retained_bytes"),
                     bench.get("calls"), table.get("overall"), table.get("rank")))
            judge_models = {j["name"]: j.get("model") for j in run["judges"]}
            for name, per_criterion in run["scores"].items():
                for criterion, by_judge in per_criterion.items():
                    for judge, score in by_judge.items():
                        connection.execute(
                            "INSERT INTO scores (run_id, candidate, criterion, judge, model, "
                            "score) VALUES (?,?,?,?,?,?)",
                            (run["run_id"], name, criterion, judge, judge_models.get(judge),
                             score))
            for name, row in run["verdict"]["table"].items():
                for criterion in CRITERIA:
                    connection.execute(
                        "INSERT INTO aggregates (run_id, candidate, criterion, median, spread, "
                        "disagreement) VALUES (?,?,?,?,?,?)",
                        (run["run_id"], name, criterion, row[criterion]["median"],
                         row[criterion]["spread"], 1 if row[criterion]["disagreement"] else 0))
    finally:
        connection.close()
    return run["run_id"]


def _table(headers, rows):
    """Render a markdown table."""
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(out)


def deep_dive(run):
    """Render the per-module deep-dive document. Returns markdown.

    It is written for someone who was not here: it states which bytes were rewritten and how
    that was proven, what was generated and what was discarded and WHY, the measured perf table,
    the panel scorecard per criterion with the disagreements flagged, the winner and the
    reasoning that selected it, and what to graft from the runners-up.
    """
    facts = run["facts"]
    verdict = run["verdict"]
    table = verdict["table"]

    out = []
    out.append("# Rewrite tournament deep-dive: `%s`\n" % run["unit"])
    out.append("Run `%s`, recorded %s by `%s` (ticket #207).\n" % (
        run["run_id"], run["ts"], TOOL))

    out.append("\n## The module under rewrite\n")
    out.append(_table(
        ["fact", "value"],
        [["unit", "`%s`" % run["unit"]],
         ["surface", "`%s(%s)`" % (run["unit"], ", ".join(run["params"]))],
         ["origin", "`%s`" % facts["origin"]],
         ["how it was read", facts["how"]],
         ["size", "%d bytes" % facts["size"]],
         ["git blob sha1", "`%s`" % facts["blob_sha1"]],
         ["blob verified", "YES — matches the `ORIGINAL_BLOB_SHA1` recorded beside the bytes"
          if facts["blob_verified"] else
          "no — the source records no sha1 to check against"]]))
    out.append("\nThe original's source, byte for byte:\n")
    out.append("```python\n%s```\n" % run["original_source"])

    out.append("\n## Step 1-2 — generation and the equivalence gate\n")
    out.append(
        "\n%d candidates were generated from the config's candidate list and gated against the "
        "original over %d exemplars mined from it. %d passed; generation stopped once "
        "`min_passing` = %d was reached.\n"
        % (run["generated"], run["exemplars"], run["passing"], run["min_passing"]))
    out.append(
        "\nThe exemplars were mined by %s. Their honest limit — criteria_miner's own, recorded "
        "by every landed forge2 rewrite — is that they cover the SAMPLED inputs and are NOT a "
        "proof of total equivalence. This gate is a strong refactor-drift net, not a proof.\n"
        % run["exemplar_source"])
    out.append("\n" + _table(
        ["candidate", "model", "approach", "gate", "agreed", "why discarded"],
        [[("**%s**" % name) if run["gate"][name]["passed"] else name,
          "`%s`" % (run["candidates"][name].get("model") or "n/a"),
          "`%s` / `%s`" % (",".join(run["candidates"][name]["approach"]["transforms"]),
                           run["candidates"][name]["approach"]["scaffold"]),
          "PASS" if run["gate"][name]["passed"] else "DISCARDED",
          "%d/%d" % (run["gate"][name]["agreed"], run["gate"][name]["checked"]),
          run["gate"][name].get("error")
          or (", ".join("`%s` -> want %s, got %s" % m
                        for m in run["gate"][name]["mismatches"][:2]) or "—")]
         for name in run["gate_order"]]))

    discarded = [n for n in run["gate_order"] if not run["gate"][n]["passed"]]
    if discarded:
        out.append(
            "\n%d candidate(s) were DISCARDED by the gate and never reached the bench or the "
            "panel: %s. That is the gate doing its job — a candidate that disagrees with the "
            "original is not a rewrite of it, however good it looks.\n"
            % (len(discarded), ", ".join("`%s`" % n for n in discarded)))
    else:
        out.append("\nNo candidate was discarded: every one generated passed the gate.\n")

    out.append("\n### What each surviving approach did to the original's body\n")
    for name in run["ranking"]:
        out.append("\n* **`%s`** — %s" % (
            name, "; ".join(run["candidates"][name]["notes"])))
    out.append("\n")

    out.append("\n## Step 3 — the performance benchmark (real numbers)\n")
    bench = run["bench"]
    out.append(
        "\nEvery passing candidate ran the SAME workload of %d exemplar inputs — %d repeats after "
        "%d warmup sweeps, %d calls each — on one shared harness.\n"
        % (run["workload_size"], run["bench_config"]["repeats"], run["bench_config"]["warmup"],
           next(iter(bench.values()))["calls"] if bench else 0))
    out.append(
        "\nRuntime was timed WARM and untraced (`time.perf_counter`), because steady-state "
        "per-call cost is what a caller of a hot unit pays, and because timing under tracemalloc "
        "reports the tracer. Memory was measured in a second, COLD pass: `re.purge()` first, then "
        "tracing on, then the candidate module re-executed inside the traced window. Cold and "
        "purged for two reasons — a warm module has already filled its caches, so a warm memory "
        "pass reports ~zero; and `re`'s compiled-pattern cache is PROCESS-WIDE, so without the "
        "purge whichever candidate ran first would pay for filling it and the rest would look "
        "free.\n")
    out.append(
        "\n`peak_bytes` is the peak traced memory during that cold pass. `retained` is what the "
        "candidate still HOLDS at the end of it — blocks whose traceback passes through its own "
        "code (module-level constants, regex-cache entries, an lru_cache). It is RETAINED, not "
        "allocated: tracemalloc snapshots what is live and CPython has no total-allocation "
        "counter, so allocation churn is not a number this can honestly report. Retention is, "
        "and it is what charges a memoizing candidate for the cache that makes it fast.\n")
    out.append(
        "\nMeasured on this machine, this run. The last significant figure of a runtime is "
        "noise.\n")
    fastest = min(bench, key=lambda n: bench[n]["runtime_s"]) if bench else None
    out.append("\n" + _table(
        ["candidate", "runtime (s)", "vs fastest", "peak (bytes)", "retained blocks",
         "retained bytes", "calls"],
        [[("**%s**" % name) if name == fastest else name,
          "%.6f" % bench[name]["runtime_s"],
          "%.2fx" % (bench[name]["runtime_s"] / bench[fastest]["runtime_s"]),
          "%d" % bench[name]["peak_bytes"],
          "%d" % bench[name]["retained_blocks"],
          "%d" % bench[name]["retained_bytes"],
          "%d" % bench[name]["calls"]]
         for name in sorted(bench, key=lambda n: bench[n]["runtime_s"])]))
    out.append("\n\nTelemetry source: %s.\n" % run["telemetry_source"])

    out.append("\n## Step 4 — the all-agent panel scorecard\n")
    out.append(
        "\n%d judges scored every surviving candidate on each criterion, out of 10. Each judge "
        "is BLIND to the others: `judge_candidate()` receives one candidate, its bench row and "
        "its own rubric, and has no argument through which another judge's score could reach "
        "it. Judges differ by their weights and strictness, both of which are config.\n"
        % len(run["judges"]))
    out.append("\n" + _table(
        ["judge", "model", "backend", "strictness"],
        [["`%s`" % j["name"], "`%s`" % (j.get("model") or "n/a"), j.get("backend", "rubric"),
          "%.2f" % float(j.get("strictness", 1.0))] for j in run["judges"]]))
    judge_names = [j["name"] for j in run["judges"]]
    for criterion in CRITERIA:
        out.append("\n\n### %s\n" % criterion)
        out.append("\n" + _table(
            ["candidate"] + ["`%s`" % j for j in judge_names] + ["median", "spread", "flag"],
            [[name]
             + ["%.3f" % run["scores"][name][criterion][j] for j in judge_names]
             + ["**%.3f**" % table[name][criterion]["median"],
                "%.3f" % table[name][criterion]["spread"],
                "DISAGREEMENT" if table[name][criterion]["disagreement"] else "—"]
             for name in run["ranking"]]))
    flagged = [(n, c) for n in run["ranking"] for c in CRITERIA
               if table[n][c]["disagreement"]]
    out.append("\n\n%s\n" % (
        "The panel disagreed (spread > %s) on: %s. A flag is raised, never resolved: a median "
        "that hides a split panel is how a tournament lies."
        % (run["disagreement_threshold"],
           ", ".join("`%s`/%s" % (n, c) for n, c in flagged))
        if flagged else
        "No candidate/criterion exceeded the disagreement threshold of %s: the panel was "
        "consistent." % run["disagreement_threshold"]))

    out.append("\n## Step 5 — ranking and the selected winner\n")
    out.append(
        "\nRanked by `overall` — the criterion-weighted mean of the medians, weights %s.\n"
        % json.dumps(run["criterion_weights"]))
    out.append("\n" + _table(
        ["rank", "candidate"] + list(CRITERIA) + ["overall"],
        [[table[name]["rank"], ("**%s**" % name) if name == verdict["winner"] else name]
         + ["%.3f" % table[name][c]["median"] for c in CRITERIA]
         + ["**%.3f**" % table[name]["overall"]]
         for name in run["ranking"]]))
    out.append("\n\n### WINNER: `%s`\n" % verdict["winner"])
    out.append("\n%s\n" % run["rationale"])

    out.append("\n### Graftable ideas from the runners-up\n")
    if run["graftable"]:
        out.append(
            "\nWhere a runner-up beat the winner on a criterion — what to consider grafting into "
            "the winner before it lands. The last column names the part of that runner-up's "
            "approach that could explain the lead, matched to what the criterion measures: a "
            "config-completeness lead comes from the SCAFFOLD, an efficiency lead from the "
            "TRANSFORMS applied to the unit's body.\n")
        out.append("\n" + _table(
            ["from", "criterion", "gap", "beats the winner", "what could explain the lead"],
            [["`%s`" % g["from"], g["criterion"], "+%.3f" % g["gap"], g["beats_winner"],
              "; ".join(g["ideas"]) or "—"] for g in run["graftable"]]))
    else:
        out.append("\nNone: the winner is at least as good as every runner-up on every "
                   "criterion.\n")

    out.append("\n## Step 6 — where this is recorded\n")
    out.append(
        "\nEvery number above is appended to the rebuild-scores table at `%s`, so it can be "
        "queried across the whole forge2 rebuild rather than read only here:\n"
        % run["scores_db"])
    out.append(
        "\n```\npython3 %s query --scores-db %s --criterion readability --best\n"
        "python3 %s query --scores-db %s --criterion efficiency --worst\n```\n"
        % (os.path.relpath(os.path.abspath(__file__), ROOT), run["scores_db"],
           os.path.relpath(os.path.abspath(__file__), ROOT), run["scores_db"]))

    out.append("\n## What this run does NOT prove\n")
    out.append(
        "\n* The gate is the mined exemplars, and they cover the SAMPLED inputs only. Two "
        "candidates that agree on every exemplar can still differ on an input nobody probed.\n"
        "* The bench numbers are one machine, one run, one workload. They rank these candidates "
        "against each other; they are not absolute.\n"
        "* %s\n" % run["panel_caveat"])
    return "\n".join(out)


# ─────────────────────────── the tournament ───────────────────────────

def run_tournament(original_source, facts, config, out_dir, scores_db=None, exemplar_file=None,
                   stream=None):
    """Run the whole tournament, steps 1-6. Returns the run dict.

    Writes ONLY inside `out_dir`: the candidates, the deep-dive doc, and the scores database
    (unless `scores_db` points elsewhere). This is the library entry point — the CLI is a thin
    wrapper over it, so #185 or any later harness can drive a tournament directly.

    Raises:
        TournamentError: if fewer than `min_passing` candidates survive the gate.
        ConfigError: if the config is missing something this needs.
    """
    out = stream or sys.stdout
    os.makedirs(out_dir, exist_ok=True)
    scores_db = scores_db or os.path.join(out_dir, "rebuild_scores.sqlite")

    stubs = require(config, "oracle_stubs",
                    "which absent modules the original's hardcoded imports are stood in for")
    oracle, unit = build_oracle(original_source, stubs, facts["origin"])
    print("original: %s(%s) — %d bytes, git blob %s%s"
          % (unit["name"], ", ".join(unit["params"]), facts["size"], facts["blob_sha1"],
             " (VERIFIED against the recorded sha1)" if facts["blob_verified"] else ""),
          file=out)

    # ── the exemplars (#200 seam) ────────────────────────────────────────────────────────────
    if exemplar_file:
        document = load_exemplars(exemplar_file)
        exemplar_source = "the criteria_miner exemplar file at `%s`" % exemplar_file
    else:
        with _stub_modules(stubs):
            document = mine_exemplars(oracle, unit, config)
        exemplar_source = "this tool's built-in `mine_exemplars()` (the #200/criteria_miner seam)"
    cases = decode_exemplars(document)
    if not cases:
        raise TournamentError(
            "no exemplars: the gate would pass every candidate vacuously. Widen the config's "
            "probe_pool, or pass --exemplars.")
    print("exemplars: %d cases mined from the original as the oracle (%s)"
          % (len(cases), exemplar_source), file=out)

    # ── steps 1-2: generate, gate, regenerate until min_passing pass ─────────────────────────
    min_passing = require(config, "min_passing", "how many candidates must pass the gate")
    candidate_configs = require(config, "candidates", "the model/approach set to generate from")
    base_dir = os.path.dirname(facts["origin"]) or out_dir

    candidates, gate_log, gate_order, passing = {}, {}, [], []
    for candidate_config in candidate_configs:
        if len(passing) >= min_passing:
            break
        name = candidate_config.get("name")
        if not name:
            raise ConfigError("every candidate needs a `name`; one in the config has none")
        if name in candidates:
            raise ConfigError("two candidates in the config are both named %r" % name)

        with _stub_modules(stubs):
            source, notes = generate_candidate(original_source, unit, candidate_config, config)
        candidates[name] = dict(candidate_config, source=source, notes=notes)
        gate_order.append(name)

        with _stub_modules(stubs):
            verdict = gate_candidate(source, name, cases, base_dir)
        gate_log[name] = verdict
        if verdict["passed"]:
            passing.append(name)
        print("  %-20s %s  (%d/%d exemplars)%s"
              % (name, "PASS     " if verdict["passed"] else "DISCARDED",
                 verdict["agreed"], verdict["checked"],
                 "" if verdict["passed"] else
                 " — %s" % (verdict["error"]
                            or "%s -> want %s, got %s" % verdict["mismatches"][0])), file=out)

        path = os.path.join(out_dir, "candidate_%s.py" % name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)

    if len(passing) < min_passing:
        raise TournamentError(
            "only %d of %d generated candidates passed the equivalence gate, but min_passing is "
            "%d. Add more candidate configs to generate from, or lower min_passing."
            % (len(passing), len(gate_order), min_passing))
    print("gate: %d/%d passed; %d discarded" % (len(passing), len(gate_order),
                                                len(gate_order) - len(passing)), file=out)

    # ── step 3: benchmark every survivor on one shared workload ──────────────────────────────
    workload = [args for args, expected in cases if not isinstance(expected, Raised)]
    if not workload:
        raise TournamentError(
            "every exemplar raises, so there is no workload to benchmark. Widen the config's "
            "probe_pool with inputs the original answers.")
    bench_config = require(config, "bench", "how many times the benchmark sweeps the workload")
    bench_rows = {}
    for name in passing:
        with _stub_modules(stubs):
            bench_rows[name] = bench_candidate(candidates[name]["source"], name, workload,
                                               base_dir, config)
        print("  %-20s %.6f s over %d calls, peak %d bytes, retains %d blocks / %d bytes"
              % (name, bench_rows[name]["runtime_s"], bench_rows[name]["calls"],
                 bench_rows[name]["peak_bytes"], bench_rows[name]["retained_blocks"],
                 bench_rows[name]["retained_bytes"]), file=out)

    # ── step 4: the panel ────────────────────────────────────────────────────────────────────
    with _stub_modules(stubs):
        scores, _bounds = run_panel([candidates[n] for n in passing], bench_rows, config)

    # ── step 5: aggregate, rank, select ──────────────────────────────────────────────────────
    verdict = aggregate(scores, config)
    graftable = graftable_ideas(verdict, candidates)
    rationale = winner_rationale(verdict, bench_rows, candidates, gate_log)
    print("winner: %s (overall %.3f)"
          % (verdict["winner"], verdict["table"][verdict["winner"]]["overall"]), file=out)

    # ── step 6: the deep dive + the scores table ─────────────────────────────────────────────
    judges = config["judges"]
    backends = {j.get("backend", "rubric") for j in judges}
    run = {
        "run_id": "%s-%s" % (unit["name"], facts["blob_sha1"][:12]),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "module": os.path.basename(facts["origin"]),
        "unit": unit["name"],
        "params": unit["params"],
        "facts": facts,
        "original_source": original_source,
        "candidates": candidates,
        "gate": gate_log,
        "gate_order": gate_order,
        "generated": len(gate_order),
        "passing": len(passing),
        "min_passing": min_passing,
        "exemplars": len(cases),
        "exemplar_source": exemplar_source,
        "workload_size": len(workload),
        "bench": bench_rows,
        "bench_config": {"repeats": bench_config.get("repeats", 2000),
                         "warmup": bench_config.get("warmup", 200)},
        "telemetry_source": ("this tool's built-in `measure()` (time.perf_counter + tracemalloc) "
                             "— the config's `telemetry` hook is null"
                             if config.get("telemetry") is None else
                             "the #203 telemetry hook `%s` named by the config"
                             % config["telemetry"]),
        "judges": judges,
        "scores": scores,
        "verdict": verdict,
        "ranking": verdict["ranking"],
        "criterion_weights": config["criterion_weights"],
        "disagreement_threshold": config["disagreement_threshold"],
        "graftable": graftable,
        "rationale": rationale,
        "winner": verdict["winner"],
        "scores_db": os.path.abspath(scores_db),
        "panel_caveat": (
            "The panel scored with the built-in `rubric` backend: real measurements of each "
            "candidate combined with each judge's own config-given weights and strictness. These "
            "judges are diverse RUBRICS, not diverse MODELS. Set each judge's `backend` to "
            "\"litellm\" for the model panel #207 describes; litellm is not installed in this "
            "checkout, so that path has not been exercised against a live model here."
            if backends == {"rubric"} else
            "The panel used the %s backend(s)." % ", ".join(sorted(backends))),
    }
    doc_path = os.path.join(out_dir, "deep_dive_%s.md" % unit["name"])
    run["deep_dive"] = os.path.abspath(doc_path)
    with open(doc_path, "w", encoding="utf-8") as handle:
        handle.write(deep_dive(run))
    record_scores(scores_db, run)
    print("deep dive: %s\nscores:    %s (run_id %s)"
          % (doc_path, os.path.abspath(scores_db), run["run_id"]), file=out)
    return run


# ─────────────────────────── the command line ───────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report its
    original error. No report is filed for a ConfigError or a TournamentError — both are designed
    behavior rather than bugs. Returns the path written, or None.
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
        "note": "%s (ticket #207)" % TOOL,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except OSError:
        return None


def _resolve_original(args):
    """Read the original from --module or --from-rewrite. Returns `(source, facts)`."""
    if args.module:
        return load_original(args.module)
    return original_from_rewrite(args.from_rewrite)


def _add_module_arguments(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--module", metavar="PATH",
                       help="the original unit's own .py file")
    group.add_argument("--from-rewrite", metavar="PATH", dest="from_rewrite",
                       help="a landed forge2 rewrite; the original is taken from the "
                            "ORIGINAL_SOURCE it embeds and verified against the "
                            "ORIGINAL_BLOB_SHA1 recorded beside it")


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="rewrite_tournament.py",
        description="The competitive-rewrite tournament harness each forge2 rewrite ticket runs "
                    "(#207): generate candidates, gate them on behavioral equivalence, benchmark "
                    "the survivors, score them with a blind judge panel, rank and select a "
                    "winner, and write the deep-dive doc + the rebuild-scores table.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Config is read from --config, else $%s, else the %r section of the nearest %s "
               "found by walking up from this module. The root registry has no such section "
               "today, so pass --config. Run `emit-config` for a template. `run` writes only "
               "inside --out." % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # `--config` belongs to each subcommand that needs one, so `run --config X` — the form this
    # module's docstring documents — parses. It is deliberately NOT also on the top-level
    # parser: argparse would let the subparser's `None` default silently overwrite a value given
    # before the subcommand, and a config that is read but silently ignored is worse than one
    # that is refused.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", metavar="PATH",
                        help="the config object to run with (what `emit-config` prints). "
                             "Without it, $%s is tried, then the %r section of the nearest %s."
                             % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME))

    p_run = sub.add_parser(
        "run", parents=[common], help="run the whole tournament on one module",
        description="Generate candidates, gate them on behavioral equivalence with the original, "
                    "benchmark the survivors, score them with the panel, select a winner, and "
                    "write the deep-dive doc and the rebuild-scores rows. Writes only inside "
                    "--out.")
    _add_module_arguments(p_run)
    p_run.add_argument("--out", metavar="DIR", required=True,
                       help="the directory to write the candidates, the deep-dive doc and (by "
                            "default) the scores database into. Required: this tool will not "
                            "write anywhere by default.")
    p_run.add_argument("--scores-db", metavar="PATH", dest="scores_db",
                       help="the rebuild-scores database to append to (default: "
                            "<out>/rebuild_scores.sqlite). Point every module of a rebuild at "
                            "ONE database to query best/worst across the whole rebuild.")
    p_run.add_argument("--exemplars", metavar="PATH",
                       help="a criteria_miner (#200) exemplar file to gate against, instead of "
                            "mining the exemplars from the original here")

    p_mine = sub.add_parser(
        "mine", parents=[common], help="mine the exemplars from a module and print them",
        description="Mine behavioral exemplars from the original acting as the oracle and print "
                    "them as an exemplar document. Creates no files unless --write is given.")
    _add_module_arguments(p_mine)
    p_mine.add_argument("--write", metavar="PATH",
                        help="write the exemplar document to PATH instead of printing it")

    p_query = sub.add_parser(
        "query", help="query the rebuild-scores table across the whole rebuild",
        description="Read the rebuild-scores table. Opens it STRICTLY read-only (sqlite "
                    "immutable=1): writes nothing, creates no -wal/-shm sidecars.")
    p_query.add_argument("--scores-db", metavar="PATH", dest="scores_db", required=True,
                         help="the rebuild-scores database to read")
    p_query.add_argument("--criterion", choices=list(CRITERIA) + ["overall"], default="overall",
                         help="the criterion to rank by (default: overall)")
    order = p_query.add_mutually_exclusive_group()
    order.add_argument("--best", action="store_true",
                       help="the highest scorers (the default)")
    order.add_argument("--worst", action="store_true",
                       help="the lowest scorers")
    p_query.add_argument("--limit", type=int, default=10, help="how many rows (default: 10)")
    p_query.add_argument("--winners-only", action="store_true",
                         help="only the candidate that won each module's tournament")
    p_query.add_argument("--json", action="store_true", dest="as_json",
                         help="print the rows as JSON")

    sub.add_parser("list-approaches",
                   help="print the transform and scaffold catalog the config names")
    sub.add_parser("emit-config", help="print a template of this tool's config object")
    sub.add_parser("show-config", parents=[common],
                   help="print the config object in force and its source")
    sub.add_parser("selftest", help="prove the harness end-to-end, in a temporary directory")
    return parser


def _cmd_query(args):
    connection = connect_scores_ro(args.scores_db)
    try:
        where = "WHERE criterion = ?"
        params = [args.criterion]
        column = "median"
        if args.criterion == "overall":
            where = "WHERE criterion = ?"
            params = [CRITERIA[0]]     # one row per candidate; overall is the same on each
            column = "overall"
        if args.winners_only:
            where += " AND is_winner = 1"
        direction = "ASC" if args.worst else "DESC"
        rows = connection.execute(
            "SELECT module, unit, candidate, %s AS value, spread, disagreement, rank, ts, run_id "
            "FROM rebuild_scores %s ORDER BY value %s, module, candidate LIMIT ?"
            % (column, where, direction), params + [args.limit]).fetchall()
    finally:
        connection.close()

    if args.as_json:
        print(json.dumps([
            {"module": r[0], "unit": r[1], "candidate": r[2], args.criterion: r[3],
             "spread": r[4], "disagreement": bool(r[5]), "rank": r[6], "ts": r[7],
             "run_id": r[8]} for r in rows], indent=2))
        return 0

    if not rows:
        print("(none) — the rebuild-scores table at %s has no rows for criterion %r"
              % (args.scores_db, args.criterion))
        return 0
    print("%s by %s across every module recorded in %s"
          % ("WORST" if args.worst else "BEST", args.criterion, args.scores_db))
    print("%-22s %-22s %8s %8s %6s %5s" % ("module", "candidate", args.criterion[:8], "spread",
                                           "flag", "rank"))
    for module, _unit, candidate, value, spread, disagreement, rank, _ts, _run in rows:
        print("%-22s %-22s %8.3f %8.3f %6s %5s"
              % (module, candidate, value, spread or 0.0, "DISAG" if disagreement else "-",
                 rank if rank is not None else "-"))
    return 0


def _cmd_mine(args):
    config = active_config()
    source, facts = _resolve_original(args)
    stubs = require(config, "oracle_stubs",
                    "which absent modules the original's hardcoded imports are stood in for")
    with _stub_modules(stubs):
        oracle, unit = build_oracle(source, stubs, facts["origin"])
        document = mine_exemplars(oracle, unit, config)
    document["origin"] = facts["origin"]
    document["blob_sha1"] = facts["blob_sha1"]
    text = json.dumps(document, indent=2)
    if args.write:
        with open(args.write, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        print("wrote %d exemplars for %s to %s" % (len(document["cases"]), unit["name"],
                                                   args.write))
    else:
        print(text)
    return 0


def _cmd_list_approaches():
    print("TRANSFORMS — the config's approach.transforms names these, in order:\n")
    for name in sorted(TRANSFORMS):
        print("  %-22s %s" % (name, TRANSFORMS[name]))
    print("\nSCAFFOLDS — the config's approach.scaffold names one of these:\n")
    for name in ("full", "env_only", "minimal"):
        print("  %-22s %s" % (name, SCAFFOLDS[name]))
    print("\nA transform that does not apply to a given original leaves it unchanged and says\n"
          "so in the candidate's notes rather than failing the run.")
    return 0


def main(argv=None):
    """Entry point. Returns a process exit code."""
    # Checked BEFORE the arguments are parsed, so the version message is what a reader on an old
    # interpreter sees first, whatever they typed.
    if sys.version_info < (3, 9):
        print("rewrite_tournament: needs Python 3.9+ (this module renders candidate source with "
              "ast.unparse, which %d.%d lacks)" % sys.version_info[:2], file=sys.stderr)
        return 2

    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at the %r key of your %s, or save it to a file and pass it\n"
                  "# with --config. Until it is installed, every command that needs config\n"
                  "# throws — it will not guess a default."
                  % (".".join(UNIT_PATH), REGISTRY_NAME), file=sys.stderr)
            return 0

        if args.command == "list-approaches":
            return _cmd_list_approaches()

        if args.command == "selftest":
            return 0 if selftest() == 0 else 1

        if args.command == "query":
            return _cmd_query(args)

        # Everything below needs the config object.
        reset_config()
        global _RESOLVED
        _RESOLVED = load_config(path=args.config)

        if args.command == "show-config":
            print(json.dumps({"tool": TOOL, "source": active_source(), "base": active_base(),
                              "config": active_config()}, indent=2))
            return 0

        if args.command == "mine":
            return _cmd_mine(args)

        if args.command == "run":
            source, facts = _resolve_original(args)
            run_tournament(source, facts, active_config(), args.out,
                           scores_db=args.scores_db, exemplar_file=args.exemplars)
            return 0

    except ConfigError as exc:
        print("config error: %s" % exc, file=sys.stderr)
        return 2
    except TournamentError as exc:
        print("tournament: %s" % exc, file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        path = _bug_report(exc, traceback.format_exc(), argv)
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise

    return 0


# ─────────────────────────── the selftest ───────────────────────────

#: A miniature original in the shape every forge unit has: a hardcoded telemetry import, one
#: decorated function with local imports and a chain of assignments. `selftest` runs a whole
#: tournament on it, so the harness is proven end-to-end without needing the forge.
_SELFTEST_ORIGINAL = (
    "from code_pipeline import trace as debug_decorator\n"
    "\n"
    "\n"
    "@debug_decorator\n"
    "def normalize(s):\n"
    "    import re\n"
    "    s = re.sub('[^a-z0-9]', '_', s)\n"
    "    s = re.sub('_+', '_', s)\n"
    "    return s\n"
)


class _FakeLiteLLM:
    """A stand-in for the litellm package, so `selftest` can prove the #184 adapter's call shape.

    It records the model and prompt it was called with and answers in the real library's
    response shape. This proves the adapter routes the CONFIG's model and reads the answer
    correctly; it does NOT prove anything about a live model, which this checkout cannot reach.
    """

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def completion(self, model=None, messages=None, **kwargs):
        self.calls.append({"model": model, "messages": messages, "kwargs": kwargs})
        return {"choices": [{"message": {"content": self.reply}}]}


def selftest(stream=None):
    """Prove the harness end-to-end. Returns the number of failures.

    Builds its config objects in memory, runs a whole tournament in a temporary directory, and
    removes it afterwards. Needs no config file, no network and no forge access.

    Checks, in order:
      1. the config gate — every command that needs config throws when it cannot see one;
      2. the original is read, verified against a recorded blob sha1, and REFUSED when the bytes
         do not match it;
      3. exemplars are mined from the original as the oracle, and round-trip through the file
         format;
      4. the gate discards a candidate that is not equivalent, and passes ones that are;
      5. a whole tournament runs: >= min_passing candidates pass, the bench has real numbers,
         every judge scored every candidate, a winner is selected, the doc is written and the
         scores are recorded and queryable;
      6. the panel is BLIND — permuting the judge order changes no judge's score;
      7. the aggregate flags disagreement rather than hiding it;
      8. the #184 litellm adapter routes the config's model and reads the reply shape;
      9. `query` creates no files (the immutable=1 promise), and `run` writes only inside --out.
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
    config = config_template()
    config["bench"] = {"repeats": 50, "warmup": 5}     # keep the selftest quick
    config["probe_pool"] = ["hello world", "a b", "a__b", "__a__", "", "-", "a1", 5, None]
    config["max_exemplars"] = 40

    try:
        reset_config()
        with tempfile.TemporaryDirectory() as workspace:
            original_path = os.path.join(workspace, "normalize.py")
            with open(original_path, "w", encoding="utf-8") as handle:
                handle.write(_SELFTEST_ORIGINAL)

            # 1. the config gate.
            print("[1] config gate — a tool that cannot see its config throws", file=out)
            try:
                load_config(path=os.path.join(workspace, "no-such-config.json"))
                check(False, "load_config() with an unreadable --config raises ConfigError")
            except ConfigError:
                check(True, "load_config() with an unreadable --config raises ConfigError — no "
                            "default is guessed")
            try:
                require({}, "generator", "which backend writes the candidates")
                check(False, "require() on an absent key raises ConfigError")
            except ConfigError as exc:
                check("generator" in str(exc), "require() on an absent key raises ConfigError "
                                               "naming the key")

            # 2. reading and VERIFYING the original.
            print("[2] the original is read and its blob sha1 verified", file=out)
            source, facts = load_original(original_path)
            check(source == _SELFTEST_ORIGINAL and facts["size"] == len(
                _SELFTEST_ORIGINAL.encode()),
                  "--module reads the original's bytes exactly (%d bytes)" % facts["size"])
            check(facts["blob_sha1"] == git_blob_sha1(_SELFTEST_ORIGINAL.encode()),
                  "its git blob sha1 is computed the way `git hash-object` does (%s)"
                  % facts["blob_sha1"])

            good_rewrite = os.path.join(workspace, "landed_good.py")
            with open(good_rewrite, "w", encoding="utf-8") as handle:
                handle.write('"""a landed rewrite"""\nORIGINAL_SOURCE = %r\n'
                             'ORIGINAL_BLOB_SHA1 = %r\nORIGINAL_SIZE = %d\n'
                             % (_SELFTEST_ORIGINAL, facts["blob_sha1"],
                                len(_SELFTEST_ORIGINAL.encode())))
            recovered, recovered_facts = original_from_rewrite(good_rewrite)
            check(recovered == _SELFTEST_ORIGINAL and recovered_facts["blob_verified"],
                  "--from-rewrite recovers the original from ORIGINAL_SOURCE and verifies it "
                  "against the recorded ORIGINAL_BLOB_SHA1")

            bad_rewrite = os.path.join(workspace, "landed_bad.py")
            with open(bad_rewrite, "w", encoding="utf-8") as handle:
                handle.write('ORIGINAL_SOURCE = %r\nORIGINAL_BLOB_SHA1 = %r\n'
                             % (_SELFTEST_ORIGINAL + "# tampered\n", facts["blob_sha1"]))
            try:
                original_from_rewrite(bad_rewrite)
                check(False, "--from-rewrite REFUSES bytes that do not match the recorded sha1")
            except ConfigError as exc:
                check("Refusing" in str(exc),
                      "--from-rewrite REFUSES bytes that do not match the recorded sha1")

            # 3. mining the exemplars from the original as the oracle.
            print("[3] exemplars are mined from the ORIGINAL acting as the oracle", file=out)
            with using_config(config):
                stubs = config["oracle_stubs"]
                with _stub_modules(stubs):
                    oracle, unit = build_oracle(source, stubs, original_path)
                    document = mine_exemplars(oracle, unit, config)
                cases = decode_exemplars(document)
                check(unit["name"] == "normalize" and unit["params"] == ["s"],
                      "the callable surface is read off the original: normalize(s)")
                check(len(cases) >= 8, "%d exemplars mined" % len(cases))
                check(any(isinstance(e, Raised) and e.kind == "TypeError" for _a, e in cases),
                      "an input the ORIGINAL rejects is recorded as raising TypeError, not "
                      "dropped")
                check(("[^a-z0-9]" in [c for c in branch_constants(unit)]),
                      "the miner probes the unit's OWN branch constants (its regex literals are "
                      "in the probe pool)")
                round_tripped = decode_exemplars(json.loads(json.dumps(document)))
                check(round_tripped == cases,
                      "the exemplar document round-trips through JSON unchanged, so `mine "
                      "--write` and `run --exemplars` agree")

                # 4. the gate.
                print("[4] the gate discards a candidate that is not equivalent", file=out)
                equivalent, _notes = _builtin_generate(
                    source, unit, {"transforms": ["hoist_imports"], "scaffold": "full"},
                    unit["name"])
                broken, _notes = _builtin_generate(
                    source, unit, {"transforms": ["hoist_imports", "coerce_str_args"],
                                   "scaffold": "full"}, unit["name"])
                with _stub_modules(stubs):
                    good = gate_candidate(equivalent, "equivalent", cases, workspace)
                    bad = gate_candidate(broken, "broken", cases, workspace)
                check(good["passed"] and good["agreed"] == good["checked"],
                      "an equivalent candidate PASSES on all %d exemplars" % good["checked"])
                check(not bad["passed"] and bad["mismatches"],
                      "the str()-coercing candidate is DISCARDED (%d/%d, first mismatch %s)"
                      % (bad["agreed"], bad["checked"],
                         bad["mismatches"][0] if bad["mismatches"] else "—"))

                # 5. the whole tournament.
                print("[5] a whole tournament runs end-to-end", file=out)
                out_dir = os.path.join(workspace, "out")
                quiet = io.StringIO()
                run = run_tournament(source, facts, config, out_dir, stream=quiet)
                check(run["passing"] >= config["min_passing"],
                      "%d candidates passed the gate — min_passing is %d"
                      % (run["passing"], config["min_passing"]))
                check(run["generated"] > run["passing"],
                      "generation continued past %d discarded candidate(s) to reach it"
                      % (run["generated"] - run["passing"]))
                check(all(row["runtime_s"] > 0 and row["peak_bytes"] > 0 and row["calls"] > 0
                          for row in run["bench"].values()),
                      "every bench row carries real numbers (runtime > 0, peak > 0, calls > 0) "
                      "for all %d survivors" % len(run["bench"]))
                judge_names = [j["name"] for j in config["judges"]]
                check(all(sorted(run["scores"][n][c]) == sorted(judge_names)
                          for n in run["scores"] for c in CRITERIA),
                      "every one of the %d judges scored every candidate on every criterion"
                      % len(judge_names))
                check(run["winner"] in run["scores"] and run["verdict"]["table"][run["winner"]][
                    "rank"] == 1, "a winner was selected and it is rank 1: %r" % run["winner"])
                check(bool(run["rationale"]) and run["winner"] in run["rationale"],
                      "the winner has a rationale citing it by name")
                check(os.path.isfile(run["deep_dive"])
                      and os.path.getsize(run["deep_dive"]) > 2000,
                      "the deep-dive doc was written (%d bytes)"
                      % (os.path.getsize(run["deep_dive"])
                         if os.path.isfile(run["deep_dive"]) else 0))
                doc = open(run["deep_dive"], encoding="utf-8").read()
                check(all(c in doc for c in CRITERIA) and "WINNER" in doc,
                      "the doc carries a scorecard for every criterion and names the winner")

                # the scores table is queryable
                connection = connect_scores_ro(run["scores_db"])
                try:
                    rows = connection.execute(
                        "SELECT candidate, criterion, median FROM rebuild_scores "
                        "WHERE criterion = 'readability' ORDER BY median DESC").fetchall()
                    total = connection.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
                finally:
                    connection.close()
                check(len(rows) == run["passing"],
                      "the rebuild_scores view has one readability row per survivor (%d)"
                      % len(rows))
                check(total == run["passing"] * len(CRITERIA) * len(judge_names),
                      "every judge x candidate x criterion score is recorded (%d rows)" % total)

                # 6. the panel is blind.
                print("[6] the panel is BLIND — judges cannot influence one another", file=out)
                forward = dict(config)
                reversed_cfg = dict(config, judges=list(reversed(config["judges"])))
                bench_rows = run["bench"]
                survivors = [run["candidates"][n] for n in run["ranking"]]
                with _stub_modules(stubs):
                    a_scores, _ = run_panel(survivors, bench_rows, forward)
                    b_scores, _ = run_panel(survivors, bench_rows, reversed_cfg)
                check(a_scores == b_scores,
                      "permuting the judge order leaves every judge's score byte-identical — no "
                      "judge saw another's")

                # 7. disagreement is flagged, not hidden.
                print("[7] the aggregate flags disagreement rather than hiding it", file=out)
                split = {"only": {c: {"j1": 1.0, "j2": 9.0} for c in CRITERIA}}
                flagged = aggregate(split, dict(config, disagreement_threshold=2.0))
                row = flagged["table"]["only"]["readability"]
                check(row["median"] == 5.0 and row["spread"] == 8.0 and row["disagreement"],
                      "judges 8.0 apart give median 5.0, spread 8.0, and the DISAGREEMENT flag "
                      "is raised")
                calm = aggregate({"only": {c: {"j1": 5.0, "j2": 5.5} for c in CRITERIA}},
                                 dict(config, disagreement_threshold=2.0))
                check(not calm["table"]["only"]["readability"]["disagreement"],
                      "judges 0.5 apart are not flagged")

                # 8. the #184 litellm adapter.
                print("[8] the #184 litellm adapter routes the CONFIG's model", file=out)
                fenced = "```python\n%s```" % equivalent
                fake = _FakeLiteLLM(fenced)
                saved_litellm = sys.modules.get("litellm", KeyError)
                sys.modules["litellm"] = fake
                try:
                    generated, notes = _litellm_generate(
                        source, unit, {"transforms": ["verbatim"], "scaffold": "full"},
                        unit["name"], "some-vendor/some-model-x", config)
                    check(fake.calls and fake.calls[0]["model"] == "some-vendor/some-model-x",
                          "litellm.completion() was called with the model the CONFIG named, not "
                          "one in the code")
                    check(generated.strip() == equivalent.strip(),
                          "the model's fenced answer is unwrapped into candidate source")
                    check(fake.calls[0]["kwargs"].get("temperature")
                          == config["litellm"]["temperature"],
                          "the config's litellm options are passed through "
                          "(temperature=%r)" % config["litellm"]["temperature"])
                    judge_fake = _FakeLiteLLM(
                        '{"config_completeness": 7, "efficiency": 4.5, "readability": 9}')
                    sys.modules["litellm"] = judge_fake
                    verdict = judge_candidate(
                        {"name": "x", "source": equivalent},
                        {"runtime_s": 0.1, "peak_bytes": 100, "retained_blocks": 3, "calls": 10},
                        {"runtime_s": (0.1, 0.2), "peak_bytes": (100, 200),
                         "retained_blocks": (3, 5)},
                        {"name": "j", "backend": "litellm", "model": "some-vendor/judge-y"},
                        config)
                    check(verdict == {"config_completeness": 7.0, "efficiency": 4.5,
                                      "readability": 9.0},
                          "a litellm judge's JSON answer is read into the three criteria")
                    check(judge_fake.calls[0]["model"] == "some-vendor/judge-y",
                          "the judge's model came from ITS config entry")
                finally:
                    if saved_litellm is KeyError:
                        sys.modules.pop("litellm", None)
                    else:
                        sys.modules["litellm"] = saved_litellm

                # litellm absent: a ConfigError naming it, never a traceback.
                saved_litellm = sys.modules.pop("litellm", KeyError)
                try:
                    _litellm_completion(config, "m", "p")
                    check(False, "selecting litellm without the package raises ConfigError")
                except ConfigError as exc:
                    check("litellm" in str(exc),
                          "selecting litellm without the package raises a ConfigError naming it, "
                          "not a traceback")
                except ImportError:
                    check(False, "selecting litellm without the package raised ImportError, not "
                                 "ConfigError")
                finally:
                    if saved_litellm is not KeyError:
                        sys.modules["litellm"] = saved_litellm

                # 9. side effects: `query` creates nothing; `run` wrote only inside --out.
                print("[9] side effects — query creates no files, run writes only inside --out",
                      file=out)
                db_dir = os.path.dirname(run["scores_db"])
                before = sorted(os.listdir(db_dir))
                connection = connect_scores_ro(run["scores_db"])
                connection.execute("SELECT COUNT(*) FROM rebuild_scores").fetchone()
                connection.close()
                after = sorted(os.listdir(db_dir))
                check(before == after,
                      "query's immutable=1 open created no files (no -wal/-shm sidecars): %s"
                      % before)
                stray = [p for p in os.listdir(workspace)
                         if p not in {"out", "normalize.py", "landed_good.py", "landed_bad.py"}]
                check(not stray,
                      "the tournament wrote nothing outside --out%s"
                      % ("" if not stray else " — stray: %s" % stray))
                check(not os.path.isdir(os.path.join(workspace, "__pycache__")),
                      "exec'ing the candidates left no __pycache__ behind")
    finally:
        os.environ.pop(CONFIG_ENV, None)
        if saved_env is not None:
            os.environ[CONFIG_ENV] = saved_env
        reset_config()
        globals()["_ACTIVE"] = saved

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not failures else "SELFTEST FAILED", checks[0], len(failures)),
          file=out)
    for failure in failures:
        print("  failed: %s" % failure, file=out)
    return len(failures)


if __name__ == "__main__":
    sys.exit(main())
