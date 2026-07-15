#!/usr/bin/env python3
"""forge2 / code__code-invalid__coupler / coupler.why5 — a behavior-preserving rewrite of the
forge unit `code__code-invalid__coupler:coupler/why5.py` (module key forge-rw:84dcc08236ce2fd7),
filed under ticket #373 against the FORGE-wide refactor standard #200.

(#373 supersedes #295, which named its source only as a `git cat-file` against the forge's bare
repos that the sandboxed pair_loop worker cannot run. #373 embeds the source instead, so the
rewrite needs no forge access, and the work is done HERE. `ORIGINAL_SOURCE` below is that
embedded copy, and `selftest` check [0] proves it is the real forge blob by hashing it — see THE
EQUIVALENCE BASIS.)

WHAT THIS IS
------------
The original forge unit was 11716 bytes: a 5-why root-cause analysis session backed by Z3. You
assert observable FACTS, then assert a chain of LINKS (`because` implies `cause`), then `check()`
hands the whole chain to a Z3 solver, which reports whether it is consistent and — when it is not
— which link broke it. `save()` writes the verdict to a notes database.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and it adds the three things #200 requires that the original
lacked: it is part of a proper installable package, it is driven by a configuration object, and
it refuses to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
Quoted from ticket #373, which lowered the original with codebean's `lower_node` (#183):

    Why5.__init__(self, session_id: str, db_path: str=None, trigger: str='')
    Why5.fact(self, name: str, value: bool)
    Why5.link(self, label: str, cause: str, because: str)
    Why5.check(self) -> dict
    Why5.save(self) -> str | None
    Why5._format_text(self) -> str
    from_ci_failure(session_id: str, branch: str, pre_sha: str, pytest_output: str, db_path: str=None) -> Why5
    from_commit_failure(session_id: str, agent_name: str, file_path: str, error: str, db_path: str=None) -> Why5

All eight are preserved exactly: same names, same parameters, same defaults, same annotations.
`selftest` check [4] proves it by re-lowering THIS FILE's own AST the way #183 lowers a module
and comparing against those eight lines, rather than asserting it.

The original also bound module-level names that callers and tests read and REBIND. They are part
of the surface in practice, so they are still module globals here, and every method still reads
them at CALL time (not captured at import), so `import coupler.why5 as w; w.COLLECTION = "other"`
keeps working exactly as it did:

    COLLECTION      the notes-db collection `save()` writes to      (a `str`)
    _log            the module's logger
    _z3_available   whether the solver import succeeded             (a `bool`)
    sys, os         imported by the original and never used by it — see LEAKED NAMES

WHY THIS UNIT IS IMPORTABLE WITH NO SOLVER AND NO LOGGER PACKAGE
----------------------------------------------------------------
The original's three dependencies — `dz_debug`, `z3_mcp.solver` and `notes_db_mcp` — are each
imported inside a guard, so the original imports cleanly without any of them. That is preserved
exactly, and it is what lets this module be imported, run and PROVEN in a checkout where none of
the three is installed (which is the case in the congruency checkout that executes this ticket:
`import dz_debug`, `import z3_mcp` and `import notes_db_mcp` all fail here).

The three dependency NAMES are configuration, not code, per #200 requirement 4 — which is also
what lets `selftest` stage fakes under those names and drive the ORIGINAL and this rewrite
through the identical scenario. See THE EQUIVALENCE BASIS.

LEAKED NAMES — THE ORIGINAL'S IMPORTS BIND MODULE ATTRIBUTES, AND THAT IS SURFACE
---------------------------------------------------------------------------------
An `import` statement binds a name in the module namespace, and a name in a module namespace is
readable by any caller. The original's guarded imports therefore leak names CONDITIONALLY, and
which names exist is itself observable behavior. Four cases, all reproduced here and all proven
by `selftest` check [2] against the oracle rather than argued:

  * `from dz_debug import Logger` succeeds -> `coupler.why5.Logger` exists.
  * that import fails -> the `except ImportError` branch runs `import logging`, so
    `coupler.why5.logging` exists and `coupler.why5.Logger` does NOT. This module therefore does
    NOT import `logging` at the top: doing so would make `coupler.why5.logging` resolve even on
    the dz_debug path, where the original leaves it unbound.
  * `from z3_mcp.solver import new_session, add_variable, add_constraint, check, reset_session`
    succeeds -> all five names exist as module globals.
  * that import fails PARTWAY -> the names BEFORE the failing one are already bound. CPython
    emits one IMPORT_FROM/STORE_NAME pair per name, in order, so a `z3_mcp.solver` that has the
    first four names but no `reset_session` leaves four bound globals AND sets
    `_z3_available = False`. That reads like an accident and it is the original's behavior; this
    module binds name-by-name in the same order and check [3] pins it against the oracle.

`from notes_db_mcp import client` sits inside `save()`, so it binds a LOCAL and leaks nothing.
It is resolved per call here too, inside the same guard, for the same reason.

WHAT THE ORIGINAL ACTUALLY DID — READ OFF THE CODE, NOT ASSUMED
---------------------------------------------------------------
Nine details are easy to "fix" and wrong to. Each is preserved deliberately, and each is proven
against the ORIGINAL AS IT RUNS by `selftest` checks [2] and [3]:

  * `check()` REORDERS the chain. `self._links` holds `(label, cause, because)`, but the result
    dict's `"chain"` holds `(label, because, cause)` — cause and because swapped. `"bad_step"` in
    the very same dict is NOT swapped; it stays `(label, cause, because)`. So the two keys of one
    result dict use two different tuple orders.
  * `root_cause` is `self._links[-1][1]` — the CAUSE of the LAST link, i.e. the deepest why.
  * the no-solver result aliases the live list. `{"chain": self._links}` stores the list ITSELF,
    not a copy, so a later `.link()` mutates a result already handed to a caller. Every other
    branch builds a new list. Preserved, and check [3] proves the aliasing by identity.
  * `link()` records `None` in `_facts` for a variable it has not seen — but ONLY when a solver
    is available. With no solver, `_facts` never learns the link's variables at all, so the two
    configurations produce different `_facts` for the same calls.
  * `_format_text()` skips facts whose value `is None`, which is exactly the set `link()`
    invented. A fact explicitly asserted as `None` via `fact(name, None)` is skipped too.
  * `fact()` tests TRUTHINESS, not identity: `fact("x", 1)` asserts `x == True` and
    `fact("x", "")` asserts `x == False`.
  * `save()`'s status ladder is `verified if sat else (broken if sat is False else unknown)` —
    truthiness first, then IDENTITY. So `sat=0` is neither verified (falsy) nor broken
    (`0 is False` is False): it is reported "unknown".
  * `save()` never passes `db_path` to the notes client. `db_path` is only ever tested for
    truthiness as a gate. The note goes wherever the client is already pointed.
  * `save()`'s `except Exception` swallows EVERYTHING after the gate — a missing notes package, a
    malformed response, an exception out of `_format_text()` — and reports it as one `_log.error`
    line, returning None.

THE EQUIVALENCE BASIS (#200 requirement 1, acceptance item (a))
---------------------------------------------------------------
Ticket #373 records that criteria_miner captured NO exemplars for this module — it "mines only
self-contained pure functions (it refuses anything that mentions a world-touching or
non-deterministic name, plus methods and no-arg functions), and nothing here qualified" — and
states that this "does NOT weaken the ticket's bar — it MOVES the work: you must write the
equivalence exemplars by hand from the original's behavior before rewriting, and they are what
settles this ticket."

`EXEMPLARS` and `EDGE_CASES` below are that hand-written table. Their expected values are NOT
hand-copied and hoped to be right: `selftest` runs each scenario against the ORIGINAL and against
this rewrite, under identically staged conditions, and compares the observations field by field.
The original is therefore the oracle, and a disagreement is a FAIL — this is the differential
idiom this package established (`coupler/bridge.py` #357, `coupler/updater.py` #375).

That is only worth anything if the embedded original is really the forge's module, so `selftest`
check [0] hashes `ORIGINAL_SOURCE` as git hashes a blob and compares the digest to the blob sha1
ticket #373 records (`e5e5d778c4eb20084ef64c9888bdee4eabb57439`), and checks its length against
the ticket's stated 11716 bytes. If either differs the whole selftest is worthless, so it is the
first thing checked and it fails loudly.

TERMS USED HERE
---------------
why5 / 5-why
    A root-cause technique: ask "why?" five times, each answer becoming the next question. A
    `Why5` session records that as a chain of five LINKS and asks a solver whether the chain holds
    together.
fact
    A proposition asserted as directly observable, with a known boolean value.
link
    An asserted implication `because -> cause`: "the cause is true BECAUSE the observation is".
    One step of the chain.
Z3 / solver
    Z3 is an SMT (satisfiability-modulo-theories) solver — it decides whether a set of logical
    assertions can all be true at once. `z3_mcp.solver` is the forge package this unit drives it
    through. `sat` means the chain is consistent; `unsat` means it contradicts itself and some
    link is wrong.
registry
    The JSON configuration registry described in this repository's `note-for-claude`: a single
    `.json` file at the root of a package holding the configuration for every tool in that
    package. `note-for-claude` states the contract in its own words — ".json will have all the
    configuration - for all tools in this set of packaging. (a configuration registry) -if a tool
    cannot see the registry it will throw an exeption." [sic] This package ships its own
    `registry.json` at its root, one directory above this file.
config object
    The chunk of that registry belonging to this unit — the section at
    `forge2 -> code__code-invalid__coupler -> coupler.why5`. It is what drives this module.
    `emit-config` prints a template of it. Sibling units in this package (`coupler`,
    `coupler.updater`, `coupler.__main__`, ...) each read their OWN disjoint section, so adding
    this one disturbs none of them.
exemplar
    One (scenario -> expected outcome) pair the rewrite must reproduce, standing in for the
    automated captures ticket #373 could not mine.
oracle
    The embedded original, executed. Every expected value in this file's proof is read off it at
    run time rather than written down here.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The original hardcoded every parameter it had: the collection name `why5-analyses`, the logger
name `jazz-why5`, the `dz_debug`/`z3_mcp.solver`/`notes_db_mcp` dependency names, the notes owner
`system`, the Z3 variable type `bool`, the rule-name and constraint templates (`fact-{name}`,
`{name} == True|False`, `Implies({because}, {cause})`), the `sat`/`unsat` result words, the
`verified`/`broken`/`unknown` status words, the note title template and its 80-character root
clamp, the `pre_sha[:8]` clamp, all three log-message templates, all ten `_format_text` line
templates, and — the bulk of it — every marker string and every one of the 35 causal links that
`from_ci_failure` and `from_commit_failure` bake in. Those are exactly the params #200's fourth
requirement forbids hardcoding, so every one of them is read from this unit's config object and
NOTHING is defaulted in code.

This package ships a `registry.json` carrying precisely the original's values, so an ordinary
`import coupler.why5` from a source checkout or an editable install behaves exactly as the
original did. `selftest` check [2] is what proves that claim — it runs the shipped config against
the original and requires the observations to match — and check [6] proves by AST that none of
those values survives as a literal in this module's executable code.

WHAT IS A SETTING, AND WHAT IS NOT
----------------------------------
#200 requires no hardcoded paths or params; it does not require inventing knobs the unit never
had, and it does not license changing the unit's shape. Settings are the values the original
BAKED IN, listed above. NOT settings, because they are the unit's structure rather than its
configuration:

  * The KEYS of the result dict (`sat`, `session`, `trigger`, `chain`, `root_cause`, `model`,
    `bad_step`, `bad_rules`, `verdict`, `error`, `result`) and of the solver's reply (`result`,
    `model`, `bad_rules`) and of a collection record (`name`) and of a note (`id`). These name the
    fields of a data structure that callers and downstream services index by name; renaming one
    would break the caller, which is the opposite of what this ticket is for. Check [6]'s scan
    excludes literals in dict-key and subscript positions for exactly this reason, and says so.
  * The five solver function names in `SOLVER_NAMES` and the `list_collections` /
    `create_collection` / `add_note` client methods: those are the APIs of other packages.
  * The `warning` / `warn` / `info` logger method names: that is the logging protocol the original
    probes for, not a value it chose.

The config is read at IMPORT, because the original bound `COLLECTION`, `_log` and `_z3_available`
at import and that is the behavior being preserved. So `import coupler.why5` raises `ConfigError`
when no config object can be resolved: ticket #373's acceptance item (d) and `note-for-claude`'s
rule. It does not guess `why5-analyses`, it does not guess `jazz-why5`, and it does not quietly
leave the globals unbound. `selftest` check [1] proves it, in child interpreters.

Resolution order — the first source that answers wins:

  1. the file named by the `COUPLER_WHY5_CONFIG` environment variable, which holds this unit's
     config object itself — exactly what `emit-config` prints;
  2. otherwise, the `forge2 -> code__code-invalid__coupler -> coupler.why5` section of the nearest
     `registry.json` found by walking UP from THIS FILE's directory;
  3. otherwise, the `registry.json` shipped as package data inside the installed
     `code__code_invalid__coupler` package, located with `importlib.util.find_spec`.

The walk-up starts at this file, never at the working directory, so which directory you run from
does not change what config is found. Step 3 exists because a plain (non-editable) `pip install .`
puts this module at `site-packages/coupler/why5.py`, and the walk-up from there passes no registry
at all — `site-packages` has none. See `find_registry`.

The variable is named for THIS unit rather than something forge2-wide on purpose: it names a file
holding ONE unit's config object, and a variable shared across units could only ever point at one
unit's object at a time, so pointing it at a sibling's config would break this one. Each unit in
this package follows that rule with its own name (`coupler._config` uses `COUPLER_CONFIG`,
`coupler.updater` uses `COUPLER_UPDATER_CONFIG`).

HOW A ConfigError ACTUALLY SURFACES — the two paths differ, and saying so is the point
--------------------------------------------------------------------------------------
  * The config gate fires at IMPORT, which happens BEFORE `cli()` exists — `-m` and the console
    script both have to import this module to reach it. So `python3 -m coupler.why5 <anything>`
    with an unresolvable config exits 1 with a Python TRACEBACK whose last line is the
    self-explaining `ConfigError`. That is not a tidy one-liner and this file does not claim it
    is; it is exactly what "throws rather than guessing a default" looks like when the throw
    precedes the argument parser, and it is what acceptance item (d) asks for. `selftest` check
    [1] measures that exact exit, in child interpreters.
  * A `ConfigError` raised while a command is already RUNNING is caught by `cli()`, which prints
    one self-explaining line to stderr, files no bug report, and exits 2. That path is the safety
    net, not the common case.

SIDE EFFECTS
------------
Stated plainly:

  * IMPORTING this module reads one JSON file (its config) and imports the configured logger and
    solver packages if they are installed. It writes nothing and creates no files. The one thing
    that appears on disk is CPython's own `coupler/__pycache__/*.pyc` bytecode cache, which the
    interpreter writes for any module it imports and which `.gitignore` excludes — named here
    rather than claimed away, because "creates no files" would otherwise be false.
  * `Why5.save()` writes a note to whatever notes-db the configured client is pointed at, and
    creates the configured collection if it is absent. It is the only method with an external
    side effect, and it does nothing at all unless the session was built with a truthy `db_path`.
  * `selftest` replaces entries in `sys.modules` with recording stand-ins before anything under
    test runs and puts them back afterwards; check [5] proves the restoration rather than trusting
    it, and check [7] proves this package's tree is unchanged by the whole run. `selftest` writes
    no file outside a temporary directory it removes, and never reaches the network.
  * `install-check` really does run `pip install`, into a throwaway `--prefix`/`--target`
    directory it removes; it never installs into the running interpreter. It is the only command
    that reaches the network, and only if pip needs a build backend it has not cached. It DOES
    leave setuptools' usual `build/` and `*.egg-info/` scaffolding in the package root — named
    here rather than glossed over, because it is a real change to the directory. Those are
    precisely the build artifacts ticket #373 says are "regenerated by any install" and never
    committed, and `.gitignore` excludes both. Check [7]'s before/after snapshot skips them for
    that reason and for that reason only; it is proving the SOURCE tree is untouched, which it is.
  * `ci` and `commit` build and check a chain; with no solver installed they spawn nothing and
    reach nothing. `--save` is the one flag that writes, and it needs `--db-path`.
  * The command line, per `note-for-claude` ("all tools need to pass a bug-report automatically
    (timestamped if an exception is thrown)"), appends one timestamped JSON line to the config's
    `bug_reports` path if it hits an UNEXPECTED exception — a defect in this tool. A `ConfigError`
    or a `UsageError` is designed behavior rather than a defect, so neither ever files one.

RUNNING IT
----------
Every command below is executable as written FROM THE PACKAGE ROOT — the directory holding
`pyproject.toml`, one level above `coupler/` — with nothing installed:

    python3 -m coupler.why5 selftest       # the equivalence proof: [0]-[7], vs the ORIGINAL
    python3 -m coupler.why5 install-check  # really runs pip, in both install layouts
    python3 -m coupler.why5 show-config    # print the resolved config object and its source
    python3 -m coupler.why5 emit-config    # print a config-object template
    python3 -m coupler.why5 ci      --session S --branch B --sha SHA --pytest-output-file F
    python3 -m coupler.why5 commit  --session S --agent A --file F --error E

`python3 coupler/why5.py <command>` also works, from any directory, and unlike the sibling units
in this package that is not an accident to be warned about: this module imports nothing from the
`coupler` package, so it does not care whether that package is importable, and the registry
walk-up starts at THIS FILE rather than at the working directory. The `-m` form is written above
because it is the one that keeps working if this module ever grows a package-relative import, and
because it is what the console script below resolves to. Both forms were run to check this
paragraph; neither is a claim about what ought to happen.

Once installed (see INSTALLABLE), the console script runs from any directory:

    forge2-coupler-why5 selftest

`ci` and `commit` are `from_ci_failure` and `from_commit_failure` behind a command line: each
builds the chain, runs `check()`, and prints the result dict as JSON followed by the
`_format_text()` rendering. They exist because this unit is config-driven and its config carries
35 causal links — an operator who edits them needs to see what the edit did, and with no solver
installed neither command reaches anything at all.

INSTALLABLE (#200 requirement 3, acceptance item (c))
-----------------------------------------------------
This file is one module of the package that surrounds it, committed in full beside it. From the
package root:

    pip install -e .
    forge2-coupler-why5 selftest

Unlike some siblings in this package, that claim is EXECUTED rather than asserted: `install-check`
runs `python3 -m pip install -e . --prefix <tmp>` and then imports `coupler.why5` out of the
result in a child interpreter, and also runs a NON-editable `pip install . --target <tmp>` and
imports it under `python3 -S` so no real site-packages can answer for it.

A NOTE ON THIS PACKAGE'S `pyproject.toml`, WHICH THIS TICKET HAD TO CORRECT
---------------------------------------------------------------------------
`pyproject.toml` is generated by `congruency/tools/forge_package.py` (#410) from the modules
present, and its generator does not recurse into subdirectories: as committed it declared only the
top-level package `code__code_invalid__coupler` mapped onto `.`, and NOT the `coupler` package
that this file, `__init__.py`, `_config.py`, `bridge.py`, `updater.py` and `__main__.py` all live
in. That is not a theoretical gap — the editable install's own generated finder carries exactly
one entry, `{'code__code_invalid__coupler': '<package root>'}`, so `import coupler.why5` resolved
only because the working directory happened to be on `sys.path`, and from an installed copy it did
not resolve at all. Acceptance item (c) requires that it does, so `coupler` is declared now,
alongside the console entry point for this unit. The declaration is additive: every previously
declared package, entry point and package-data rule is still declared, so no sibling unit loses
anything. `install-check` is what proves the corrected declaration, in both layouts.

ONE HONEST LIMIT — A NON-EDITABLE INSTALL NEEDS THE SIBLING'S CONFIG NAMED
--------------------------------------------------------------------------
`find_registry`'s step-3 fallback lets THIS module resolve its config from a non-editable install.
That is not enough on its own, and pretending otherwise would be false: importing ANY module in
the `coupler` package runs `coupler/__init__.py` FIRST, and that sibling (ticket #397) gates on
its own config object with no such fallback — its `_config.find_registry` only walks up, and from
`site-packages/coupler/` the walk-up passes no registry. So from a non-editable install
`import coupler.why5` dies in the SIBLING before this module is reached, and the fix is to set the
sibling's own documented escape hatch, `$COUPLER_CONFIG`, alongside this unit's config.

That gap is #397's, and ticket #373 "covers ONE module — the one identified below — and nothing
else", so this file changes nothing about it: `install-check` REPORTS it, then uses
`$COUPLER_CONFIG` to get past it and prove THIS module's own fallback. An editable install — which
is what acceptance item (c) names — has no such problem, because the registry stays in the
checkout where both units' walk-ups find it.

Requires Python 3.10+, and says so here because this package's generated `requires-python` says
3.8: the original's `save(self) -> str | None` annotation is a PEP 604 union evaluated at function
definition time, so the module cannot even be imported on 3.9 or older. Preserving that annotation
is preserving the surface ticket #373 states, so the floor is the original's floor. The generated
`requires-python` is left alone because it is package-wide and the siblings really do run on 3.8.
"""

import argparse
import ast
import contextlib
import hashlib
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
import types
from datetime import datetime, timezone

# NOTE: `logging` is deliberately NOT imported here. See LEAKED NAMES in the module docstring:
# the original binds `logging` as a module attribute ONLY on the branch where `dz_debug` is
# unavailable, and importing it at the top would make `coupler.why5.logging` resolve on both
# branches, which the original does not do.

#: Environment variable naming a file that holds THIS unit's config object.
CONFIG_ENV = "COUPLER_WHY5_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in
#: the config document, not a configurable setting — a config-driven tool has to know which
#: section is its own. Check [6]'s "no hardcoded values" AST scan skips this assignment for
#: exactly that reason, and says so.
UNIT_PATH = ("forge2", "code__code-invalid__coupler", "coupler.why5")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:code__code-invalid__coupler/coupler/why5"

#: This module's own dotted import name. It is `UNIT_PATH`'s last element by construction — a
#: unit's address inside the registry IS its dotted path within the package — so it is derived
#: rather than written twice and cannot drift from it. Used only to print an invocation a reader
#: can retype; `__name__` is "__main__" under `-m` and `__spec__` is None when this file is run by
#: path, so neither can answer this on its own.
DOTTED_NAME = UNIT_PATH[-1]

#: The installed package that ships `registry.json` as package data. `find_registry` falls back to
#: it so a NON-editable `pip install .` can still find the config: this module then lives at
#: `site-packages/coupler/why5.py` and the walk-up passes no registry at all.
PACKAGE_WITH_REGISTRY = "code__code_invalid__coupler"

#: The ticket this unit was rewritten under, recorded in bug reports.
TICKET = 373

#: The sibling unit `coupler/__init__.py` (#397) — this module's own package — and the env var IT
#: reads its config from. `install-check` needs both; see ONE HONEST LIMIT. Derived from
#: DOTTED_NAME rather than spelled out, so it cannot drift from the package this module lives in.
SIBLING_PACKAGE = DOTTED_NAME.split(".")[0]
SIBLING_CONFIG_ENV = "COUPLER_CONFIG"

#: The solver API the original imported, in the ORDER it imported it. This is STRUCTURE, not a
#: setting: it is another package's API, and the order is load-bearing — see LEAKED NAMES, where a
#: partial failure leaves the earlier names bound. `reset_session` is imported and never used, in
#: the original too, and that is behavior rather than dead weight: a `z3_mcp.solver` without it
#: makes the whole import fail and the unit run solver-less.
SOLVER_NAMES = ("new_session", "add_variable", "add_constraint", "check", "reset_session")


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and ticket #373's acceptance item (d): a tool that cannot
    see its config throws rather than guessing a default.

    It is raised at IMPORT, before any session exists, and it is deliberately NOT an `ImportError`
    and NOT caught by anything in this module's unit code. `Why5.save` swallows `Exception` the
    way the original did, and the two guarded import blocks swallow `ImportError`; config
    resolution and validation happen BEFORE any of those guards is entered, so an operator's
    config mistake can never be mistaken for "the notes package is missing" or "z3 is not
    available" and quietly reported as such.
    """


class UsageError(RuntimeError):
    """Raised when this module was INVOKED in a way that cannot work — not a defect in it.

    Kept apart from every other exception for the same reason `ConfigError` is: the command line
    reports both as one self-explaining line and files NO bug report, because a bug report is
    supposed to mean "this tool is broken". The live case is `ci --pytest-output-file` naming a
    file that cannot be read: that is the caller's typo, a message can fix it in one line, and
    answering it with a traceback and a filed bug report would blame the tool for the invocation
    and put a false record in the sink.
    """


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do this module throws `ConfigError` at import. Every value
    below is one the ORIGINAL hardcoded, so a config built from this template makes the unit behave
    exactly as the original did — which is not a claim, it is what `selftest` check [2] measures
    against the original itself.

    Check [6]'s AST scan skips this function: it is the ONE place the original's values are allowed
    to appear as literals, because printing a template is what makes the values installable data
    rather than behavior. Check [6] also proves this template equals the section the shipped
    `registry.json` carries, so the printed template is the running config.
    """
    return {
        "collection": "why5-analyses",
        "logger": {
            "provider": "dz_debug:Logger",
            "fallback_provider": "logging:getLogger",
            "name": "jazz-why5",
        },
        "solver": {"module": "z3_mcp.solver"},
        "notes_db": {"provider": "notes_db_mcp:client", "owner": "system"},
        "variable_type": "bool",
        "rules": {
            "fact_rule_template": "fact-{name}",
            "fact_constraint_template": "{name} == {value}",
            "true_literal": "True",
            "false_literal": "False",
            "implication_template": "Implies({because}, {cause})",
        },
        "results": {
            "sat_value": "sat",
            "unsat_value": "unsat",
            "unknown_result": "unknown",
            "no_solver_error": "z3 not available",
            "verdict_template": "Chain broken at '{label}': '{because}' does not imply '{cause}'",
            "inconsistent_verdict": "Chain is inconsistent",
        },
        "statuses": {"verified": "verified", "broken": "broken", "unknown": "unknown"},
        "note": {"title_template": "[{status}] {session_id}: {root}", "root_limit": 80},
        "messages": {
            "solver_unavailable":
                "z3_mcp not available — why5 will record chains but cannot verify them",
            "saved": "why5 saved: {session_id} ({status})",
            "save_failed": "why5 save failed: {error}",
        },
        "text": {
            "trigger_line": "TRIGGER: {trigger}",
            "facts_heading": "FACTS:",
            "fact_line": "  {name} = {value}",
            "chain_heading": "CHAIN:",
            "chain_line": "  {index}. [{label}] {because} → {cause}",
            "verified_line": "RESULT: VERIFIED ✓",
            "root_cause_line": "ROOT CAUSE: {root_cause}",
            "broken_line": "RESULT: BROKEN ✗",
            "bad_step_line": "BAD STEP: {verdict}",
            "unknown_line": "RESULT: UNKNOWN",
        },
        "ci": {
            "trigger_template": "CI failed on branch {branch} at {sha}",
            "sha_length": 8,
            "match_lowercase": False,
            "facts": [
                {"name": "ci_failed", "value": True},
                {"name": "tests_exist", "any_of": ["PASSED", "FAILED"]},
                {"name": "import_error", "any_of": ["ImportError", "ModuleNotFoundError"]},
                {"name": "assertion_error", "any_of": ["AssertionError"]},
                {"name": "syntax_error", "any_of": ["SyntaxError"]},
            ],
            "chains": [
                {"any_of": ["SyntaxError"], "links": [
                    ["why1", "test_unparseable", "ci_failed"],
                    ["why2", "syntax_error", "test_unparseable"],
                    ["why3", "code_not_verified_before_commit", "syntax_error"],
                    ["why4", "no_self_check_in_loop", "code_not_verified_before_commit"],
                    ["why5", "loop_missing_verify_step", "no_self_check_in_loop"],
                ]},
                {"any_of": ["ImportError", "ModuleNotFoundError"], "links": [
                    ["why1", "missing_dependency", "ci_failed"],
                    ["why2", "import_error", "missing_dependency"],
                    ["why3", "dependency_not_declared", "import_error"],
                    ["why4", "no_install_check_before_commit", "dependency_not_declared"],
                    ["why5", "agents_assume_env_complete", "no_install_check_before_commit"],
                ]},
                {"any_of": ["AssertionError"], "links": [
                    ["why1", "test_assertion_failed", "ci_failed"],
                    ["why2", "assertion_error", "test_assertion_failed"],
                    ["why3", "code_changed_test_not_updated", "assertion_error"],
                    ["why4", "no_dependency_graph_between_code_and_tests",
                     "code_changed_test_not_updated"],
                    ["why5", "agents_work_without_shared_state",
                     "no_dependency_graph_between_code_and_tests"],
                ]},
                {"links": [
                    ["why1", "test_failed", "ci_failed"],
                    ["why2", "code_incorrect", "test_failed"],
                    ["why3", "no_verification_before_commit", "code_incorrect"],
                    ["why4", "agent_loop_lacks_feedback", "no_verification_before_commit"],
                    ["why5", "consequences_not_felt_at_agent_level", "agent_loop_lacks_feedback"],
                ]},
            ],
        },
        "commit": {
            "trigger_template": "{agent_name} failed to commit {file_path}",
            "match_lowercase": True,
            "facts": [
                {"name": "commit_failed", "value": True},
                {"name": "merge_conflict", "any_of": ["conflict"]},
                {"name": "nothing_to_commit", "any_of": ["nothing to commit"]},
                {"name": "push_rejected", "any_of": ["rejected", "non-fast-forward"]},
            ],
            "chains": [
                {"any_of": ["conflict"], "links": [
                    ["why1", "conflicting_changes", "commit_failed"],
                    ["why2", "merge_conflict", "conflicting_changes"],
                    ["why3", "two_agents_edited_same_file", "merge_conflict"],
                    ["why4", "no_file_ownership_model", "two_agents_edited_same_file"],
                    ["why5", "queue_assigns_same_file_to_multiple_agents",
                     "no_file_ownership_model"],
                ]},
                {"any_of": ["rejected"], "links": [
                    ["why1", "push_rejected", "commit_failed"],
                    ["why2", "remote_ahead_of_local", "push_rejected"],
                    ["why3", "pull_rebase_not_run", "remote_ahead_of_local"],
                    ["why4", "push_called_without_sync", "pull_rebase_not_run"],
                    ["why5", "git_ops_push_missing_rebase", "push_called_without_sync"],
                ]},
                {"links": [
                    ["why1", "write_failed", "commit_failed"],
                    ["why2", "file_not_written", "write_failed"],
                    ["why3", "llm_output_not_parseable", "file_not_written"],
                    ["why4", "output_format_not_enforced", "llm_output_not_parseable"],
                    ["why5", "prompt_missing_format_requirement", "output_format_not_enforced"],
                ]},
            ],
        },
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────────────── reading the config ───────────────────────────────

def find_registry(start=None):
    """Return the path of the registry this unit should read, or None if there is none.

    Walks UP from `start` (default: this file's directory) looking for `REGISTRY_NAME`. If the walk
    reaches the filesystem root without finding one, falls back to the copy shipped as package data
    inside `PACKAGE_WITH_REGISTRY`, which is the only one a non-editable install has. An explicit
    `start` suppresses that fallback: a caller naming a directory to search is asking about THAT
    tree, and quietly answering with the installed package's registry instead would report a config
    the caller never pointed at.
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
    machinery answers this without importing the package, which matters: importing it is not free
    and this is called from the import of a module inside it.
    """
    try:
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


def load_config(start=None, use_env=True):
    """Resolve this unit's config object from disk, ignoring any injected config.

    Returns a `(config, base, source)` triple: the config object, the directory that relative paths
    inside it resolve against, and a human-readable description of where it came from. `start`
    overrides the directory the registry walk-up begins at.

    `use_env=False` skips source 1 (`$COUPLER_WHY5_CONFIG`) and reads the registry directly. That
    is what `selftest` uses to get at the SHIPPED config: the differential proof is only meaningful
    against the config this package ships, so it must not be steerable by the ambient environment
    of whoever runs it.

    Raises:
        ConfigError: if no config object can be found, naming every source that was tried.
    """
    env_path = os.environ.get(CONFIG_ENV) if use_env else None
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
        raise ConfigError(
            "no config object for %s: %s is unset, no %s was found by walking up from %s, and the "
            "installed package %s ships none. Run `%s emit-config` for a template of the config "
            "object to install."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__))),
               PACKAGE_WITH_REGISTRY, _cli_name())
        )

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. Run "
                "`%s emit-config` and add the printed object at %s."
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
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit section
    # may state its own to override it. This is inheritance inside ONE config document, not a
    # guessed default — if neither states it, the key stays absent and the CLI files no report.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


def _cli_name():
    """Name an invocation of this tool that the reader can actually retype.

    The `-m` form, which is what works from a source checkout whether or not this package has been
    installed.
    """
    return "python3 -m " + DOTTED_NAME


def require(section, key, where, types_):
    """Return `section[key]`, proving it is present and of the right type; else raise ConfigError.

    Type-checking here rather than letting a bad value flow onward is deliberate, and it is the
    reason this module validates its WHOLE config at import instead of reading keys lazily where
    they are used. `Why5.save` runs inside `except Exception`; a malformed `note.title_template`
    read there would be swallowed and reported as "why5 save failed", turning an operator's config
    mistake into a plausible-looking wrong answer. A malformed config object is a config error, and
    it is raised as one, at import, naming the key.

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
            "the config section %s for %s is missing the required key %r. Run `%s emit-config` for "
            "a template." % (where, UNIT, key, _cli_name())
        )
    value = section[key]
    # `bool` is a subclass of `int`, so isinstance(True, int) is True. A `true` where a string or a
    # number belongs is a config mistake, and silently accepting it would let it reach a template.
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


def _type_names(wanted):
    return " or ".join(t.__name__ for t in wanted)


def require_template(section, key, where, fields):
    """Return `section[key]`, proving it is a string whose `{...}` placeholders are exactly usable.

    The value is TEST-RENDERED here, at import, with a sample for every field the call site will
    supply. A template naming a field this unit does not have (`{sesion_id}`, say) would otherwise
    raise `KeyError` at the moment of use — inside `save()`'s `except Exception` for half of them,
    where it would be reported as "why5 save failed" and the operator would never learn their
    config was wrong. Proving it renders is cheap and it is done once.

    Args:
        section: the config object (or sub-object) to read.
        key: the key to require.
        where: human-readable description of the section, for the error message.
        fields: the placeholder names this unit will supply when it renders the template.

    Raises:
        ConfigError: if the value is not a string, or names a placeholder outside `fields`, or is
            malformed.
    """
    value = require(section, key, where, str)
    try:
        value.format(**{name: "" for name in fields})
    except (KeyError, IndexError, ValueError) as exc:
        raise ConfigError(
            "the config key %r in %s for %s is not a usable template (%s: %s). It may use only "
            "these placeholders: %s. Run `%s emit-config` for a template."
            % (key, where, UNIT, type(exc).__name__, exc,
               ", ".join("{%s}" % name for name in fields) or "(none)", _cli_name())
        ) from exc
    return value


def require_str_list(section, key, where):
    """Return `section[key]`, proving it is a non-empty list of strings; else raise ConfigError.

    Every one of these is a marker searched for in a pytest log or a git error. An empty list would
    silently never match, and a non-string would raise `TypeError` from the `in` test at the point
    of use, blaming this unit's code for a config mistake.
    """
    value = require(section, key, where, list)
    if not value:
        raise ConfigError(
            "the config key %r in %s for %s must not be an empty list of markers: it could never "
            "match anything." % (key, where, UNIT)
        )
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigError(
                "the config key %r in %s for %s must be a list of strings, but element %d is %s"
                % (key, where, UNIT, index, type(item).__name__)
            )
    return list(value)


def _provider_spec(section, key, where):
    """Return `(module, attr)` from a `"module:attr"` config string; else raise ConfigError.

    Splitting and validating HERE, at import, rather than at the point of use is what keeps a
    malformed spec from being swallowed: `save()` resolves `notes_db.provider` inside its
    `except Exception`, so a `ConfigError` raised there would be reported as "why5 save failed"
    rather than as the config error it is. By the time `save()` runs, this has already proven the
    spec is well-formed, and the only thing left for the guard to catch is the genuine ImportError
    the original caught too.
    """
    value = require(section, key, where, str)
    module, sep, attr = value.partition(":")
    if not sep or not module or not attr:
        raise ConfigError(
            "the config key %r in %s for %s must be a \"module:attr\" string (e.g. "
            "\"dz_debug:Logger\"), not %r. Run `%s emit-config` for a template."
            % (key, where, UNIT, value, _cli_name())
        )
    return module, attr


def _chain_section(cfg, section_key, extra_fields):
    """Read and validate one of the two chain-builder sections (`ci`, `commit`).

    Both `from_ci_failure` and `from_commit_failure` have the identical shape — render a trigger,
    assert a list of facts, then pick the FIRST chain whose markers appear in the haystack — so
    both are described by the identical config shape and validated here once.

    A fact entry is either `{"name": ..., "value": <bool>}` (the original's constant `True`
    assertions) or `{"name": ..., "any_of": [markers]}` (the original's `"X" in output or "Y" in
    output` tests). A chain entry with no `any_of` is the default arm — the original's `else`.

    Args:
        cfg: this unit's config object.
        section_key: `"ci"` or `"commit"`.
        extra_fields: the placeholder names this section's trigger template may use.

    Raises:
        ConfigError: if the section is absent or malformed in any way.
    """
    where = "%s -> %s" % (UNIT, section_key)
    section = require(cfg, section_key, UNIT, dict)

    out = {
        "trigger_template": require_template(section, "trigger_template", where, extra_fields),
        "match_lowercase": require(section, "match_lowercase", where, bool),
        "facts": [],
        "chains": [],
    }
    if section_key == "ci":
        # Only the CI builder clamps a sha; the commit builder has no such value. The clamp is the
        # original's `pre_sha[:8]`, and a negative or non-int length is a config mistake.
        length = require(section, "sha_length", where, int)
        if length < 0:
            raise ConfigError(
                "the config key 'sha_length' in %s for %s must not be negative, not %d"
                % (where, UNIT, length)
            )
        out["sha_length"] = length

    facts = require(section, "facts", where, list)
    if not facts:
        raise ConfigError("the config key 'facts' in %s for %s must not be empty" % (where, UNIT))
    for index, spec in enumerate(facts):
        at = "%s -> facts[%d]" % (where, index)
        if not isinstance(spec, dict):
            raise ConfigError(
                "%s for %s must be a JSON object, not %s" % (at, UNIT, type(spec).__name__)
            )
        entry = {"name": require(spec, "name", at, str)}
        if "value" in spec:
            entry["value"] = require(spec, "value", at, bool)
        elif "any_of" in spec:
            entry["any_of"] = require_str_list(spec, "any_of", at)
        else:
            raise ConfigError(
                "%s for %s must have either a 'value' (a constant assertion) or an 'any_of' (a "
                "list of markers to search the input for). Run `%s emit-config` for a template."
                % (at, UNIT, _cli_name())
            )
        out["facts"].append(entry)

    chains = require(section, "chains", where, list)
    if not chains:
        raise ConfigError("the config key 'chains' in %s for %s must not be empty" % (where, UNIT))
    for index, spec in enumerate(chains):
        at = "%s -> chains[%d]" % (where, index)
        if not isinstance(spec, dict):
            raise ConfigError(
                "%s for %s must be a JSON object, not %s" % (at, UNIT, type(spec).__name__)
            )
        entry = {"any_of": require_str_list(spec, "any_of", at) if "any_of" in spec else None}
        links = require(spec, "links", at, list)
        if not links:
            raise ConfigError("the config key 'links' in %s for %s must not be empty" % (at, UNIT))
        entry["links"] = []
        for position, link in enumerate(links):
            if (not isinstance(link, list) or len(link) != 3
                    or not all(isinstance(part, str) for part in link)):
                raise ConfigError(
                    "%s -> links[%d] for %s must be a [label, cause, because] list of three "
                    "strings, not %r. Run `%s emit-config` for a template."
                    % (at, position, UNIT, link, _cli_name())
                )
            entry["links"].append(tuple(link))
        out["chains"].append(entry)

    if not any(chain["any_of"] is None for chain in out["chains"]):
        raise ConfigError(
            "the config key 'chains' in %s for %s has no default arm: exactly one chain must omit "
            "'any_of', which is the chain used when no marker matches (the original's `else`). Run "
            "`%s emit-config` for a template." % (where, UNIT, _cli_name())
        )
    return out


def settings_from_config(config=None, base=None):
    """Read and validate a config object into this module's flattened settings.

    The WHOLE object is validated here, at import, rather than key-by-key where each value is used.
    See `require` for why that is not merely tidiness: two of this unit's three consumers of config
    values run inside exception guards that would swallow a `ConfigError` and misreport it.

    Args:
        config: a config object to read; omit it to use the config in force.
        base: accepted for symmetry with the sibling units, and unused: this unit's config holds no
            paths, so there is nothing for a relative path to resolve against. It is named rather
            than silently absent so a reader comparing the units does not think it was forgotten.

    Returns:
        A dict of validated settings — the values this module's globals are bound from.

    Raises:
        ConfigError: if there is no config object to be had, or any key is missing or malformed.
    """
    cfg = active_config() if config is None else config
    if not isinstance(cfg, dict):
        raise ConfigError("a config object must be a dict, not %s" % type(cfg).__name__)

    logger_where = "%s -> logger" % UNIT
    logger = require(cfg, "logger", UNIT, dict)
    solver_where = "%s -> solver" % UNIT
    solver = require(cfg, "solver", UNIT, dict)
    notes_where = "%s -> notes_db" % UNIT
    notes = require(cfg, "notes_db", UNIT, dict)
    rules_where = "%s -> rules" % UNIT
    rules = require(cfg, "rules", UNIT, dict)
    results_where = "%s -> results" % UNIT
    results = require(cfg, "results", UNIT, dict)
    statuses_where = "%s -> statuses" % UNIT
    statuses = require(cfg, "statuses", UNIT, dict)
    note_where = "%s -> note" % UNIT
    note = require(cfg, "note", UNIT, dict)
    messages_where = "%s -> messages" % UNIT
    messages = require(cfg, "messages", UNIT, dict)
    text_where = "%s -> text" % UNIT
    text = require(cfg, "text", UNIT, dict)

    root_limit = require(note, "root_limit", note_where, int)
    if root_limit < 0:
        raise ConfigError(
            "the config key 'root_limit' in %s for %s must not be negative, not %d"
            % (note_where, UNIT, root_limit)
        )

    settings = {
        "collection": require(cfg, "collection", UNIT, str),
        "logger_provider": _provider_spec(logger, "provider", logger_where),
        "logger_fallback_provider": _provider_spec(logger, "fallback_provider", logger_where),
        "logger_name": require(logger, "name", logger_where, str),
        "solver_module": require(solver, "module", solver_where, str),
        "notes_provider": _provider_spec(notes, "provider", notes_where),
        "notes_owner": require(notes, "owner", notes_where, str),
        "variable_type": require(cfg, "variable_type", UNIT, str),
        "rules": {
            "fact_rule_template": require_template(rules, "fact_rule_template", rules_where,
                                                   ("name",)),
            "fact_constraint_template": require_template(rules, "fact_constraint_template",
                                                         rules_where, ("name", "value")),
            "true_literal": require(rules, "true_literal", rules_where, str),
            "false_literal": require(rules, "false_literal", rules_where, str),
            "implication_template": require_template(rules, "implication_template", rules_where,
                                                     ("because", "cause")),
        },
        "results": {
            "sat_value": require(results, "sat_value", results_where, str),
            "unsat_value": require(results, "unsat_value", results_where, str),
            "unknown_result": require(results, "unknown_result", results_where, str),
            "no_solver_error": require(results, "no_solver_error", results_where, str),
            "verdict_template": require_template(results, "verdict_template", results_where,
                                                 ("label", "cause", "because")),
            "inconsistent_verdict": require(results, "inconsistent_verdict", results_where, str),
        },
        "statuses": {key: require(statuses, key, statuses_where, str)
                     for key in ("verified", "broken", "unknown")},
        "note": {
            "title_template": require_template(note, "title_template", note_where,
                                               ("status", "session_id", "root")),
            "root_limit": root_limit,
        },
        "messages": {
            "solver_unavailable": require(messages, "solver_unavailable", messages_where, str),
            "saved": require_template(messages, "saved", messages_where, ("session_id", "status")),
            "save_failed": require_template(messages, "save_failed", messages_where, ("error",)),
        },
        "text": {
            "trigger_line": require_template(text, "trigger_line", text_where, ("trigger",)),
            "facts_heading": require(text, "facts_heading", text_where, str),
            "fact_line": require_template(text, "fact_line", text_where, ("name", "value")),
            "chain_heading": require(text, "chain_heading", text_where, str),
            "chain_line": require_template(text, "chain_line", text_where,
                                           ("index", "label", "because", "cause")),
            "verified_line": require(text, "verified_line", text_where, str),
            "root_cause_line": require_template(text, "root_cause_line", text_where,
                                                ("root_cause",)),
            "broken_line": require(text, "broken_line", text_where, str),
            "bad_step_line": require_template(text, "bad_step_line", text_where, ("verdict",)),
            "unknown_line": require(text, "unknown_line", text_where, str),
        },
        "ci": _chain_section(cfg, "ci", ("branch", "sha")),
        "commit": _chain_section(cfg, "commit", ("agent_name", "file_path")),
    }
    if results["sat_value"] == results["unsat_value"]:
        raise ConfigError(
            "the config keys 'sat_value' and 'unsat_value' in %s for %s are both %r; the unit "
            "distinguishes a consistent chain from a broken one by comparing the solver's reply "
            "against each in turn, so they must differ."
            % (results_where, UNIT, results["sat_value"])
        )
    return settings


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
    """Return the directory that relative paths in the config resolve against.

    This unit's own config holds no paths (see `settings_from_config`); the one path in reach is
    the CLI's `bug_reports` sink, which resolves against this.
    """
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

    `base` is the directory relative paths in `config` resolve against, and defaults to the current
    working directory. Pass `None` as `config` to drop the injection and go back to resolving from
    disk.

    Injecting a config does NOT rebind this module's globals: the original bound `COLLECTION`,
    `_log` and `_z3_available` once, at import, and that is preserved. `settings_from_config()` is
    the way to ask what some other config object would yield.
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


# ─────────────────────────── importing what the config names ───────────────────────────
#
# These three helpers exist so that a config-NAMED dependency is imported with exactly the
# semantics the original's hardcoded `import` statement had — including which names it leaves
# behind in this module's namespace, and which exception it raises when it fails. See LEAKED NAMES
# in the module docstring.

#: Sentinel distinguishing "absent from sys.modules" from "present and None". A plain
#: `sys.modules.get(name)` cannot tell them apart, and they mean opposite things: absent means
#: "load it", None means "raise ImportError".
_MISSING = object()


def _import_module(name):
    """Import `name` the way an `import` statement's module-loading half does.

    A module already in `sys.modules` is returned as-is, exactly as the statement would, and a
    `None` entry there raises ImportError, exactly as the statement would. Both are what let
    `selftest` stage fakes — and stage ABSENCES — for the oracle and this rewrite alike, through
    the identical machinery.
    """
    module = sys.modules.get(name, _MISSING)
    if module is _MISSING:
        return importlib.import_module(name)
    if module is None:
        # `import x` raises this itself when sys.modules["x"] is None; importlib.import_module
        # would too, but only for a name it has to load. Reproduced here so the short-circuit above
        # cannot skip it.
        raise ImportError("import of %s halted; None in sys.modules" % name, name=name)
    return module


def _from_import(module, name):
    """Get `name` off `module`, raising ImportError — not AttributeError — when it is absent.

    `from X import a` raises ImportError for a missing name, and BOTH of this module's guarded
    import blocks catch `ImportError` specifically. Going through a bare `getattr` would raise
    AttributeError, which those guards do not catch — so a `dz_debug` without `Logger`, which the
    original quietly fell back from, would instead crash the import. The ImportError is therefore
    reconstructed here with the phrasing the `from ... import` form uses.
    """
    try:
        return getattr(module, name)
    except AttributeError:
        raise ImportError(
            "cannot import name %r from %r (%s)"
            % (name, module.__name__, getattr(module, "__file__", "unknown location")),
            name=name,
        ) from None


def _bind_from_import(spec):
    """Do what `from <module> import <attr>` does: import, fetch, and BIND `attr` in this module.

    The binding is the point. The original's `from dz_debug import Logger` leaves `Logger` in this
    module's namespace, where any caller can read it, so reproducing the original's surface means
    reproducing that name — and the name is the config's `attr`, not a literal in this file.

    Returns the imported object. Raises ImportError exactly where the statement would.
    """
    module_name, attr = spec
    value = _from_import(_import_module(module_name), attr)
    globals()[attr] = value
    return value


def _bind_import(name):
    """Do what `import <name>` does: import the module and BIND its ROOT name in this module.

    `import a.b` binds `a`, not `a.b` — so the root is what is bound here too. The original's
    fallback branch runs `import logging`, which is why `coupler.why5.logging` exists on that
    branch and only on that branch.

    Returns the imported module (the full dotted one, as `importlib` yields it).
    """
    module = _import_module(name)
    root = name.split(".")[0]
    globals()[root] = _import_module(root) if root != name else module
    return module


def _build_logger():
    """Reproduce the original's logger block, statement for statement, and return its `_log`.

    A function rather than a bare `try` at module scope so that the intermediate names it needs do
    not become module globals of their own — every global this module binds is one the original
    bound, and check [2] compares the two namespaces to prove it.

    The `except ImportError` covers the import AND the construction AND the probing, exactly as the
    original's does, so a `Logger` class whose constructor raises ImportError falls back too. Only
    ImportError; anything else propagates. Note that the fallback does NOT undo the `Logger`
    binding `_bind_from_import` already made — neither does the original's, whose
    `from dz_debug import Logger` had bound the name before the constructor ever ran.

    `warning`/`warn`/`info` are spelled literally because they are the logging PROTOCOL this unit
    probes for, not values the original chose — see WHAT IS A SETTING, AND WHAT IS NOT.
    """
    try:
        logger_class = _bind_from_import(_SETTINGS["logger_provider"])
        log = logger_class(_SETTINGS["logger_name"])
        if not hasattr(log, "warning"):
            log.warning = log.warn if hasattr(log, "warn") else log.info
        return log
    except ImportError:
        module_name, attr = _SETTINGS["logger_fallback_provider"]
        return getattr(_bind_import(module_name), attr)(_SETTINGS["logger_name"])


def _import_solver_names():
    """Reproduce the original's `from <solver> import <SOLVER_NAMES>`, binding each name here.

    Binding name-by-name in `SOLVER_NAMES` order is not a stylistic choice: it is what makes a
    PARTIAL import leave the earlier names bound, which is what CPython's `from X import a, b, c`
    does — one IMPORT_FROM/STORE_NAME pair per name, in order — and therefore what the original
    does. See LEAKED NAMES.
    """
    module = _import_module(_SETTINGS["solver_module"])
    for name in SOLVER_NAMES:
        globals()[name] = _from_import(module, name)


# ─────────────────────────────── the module-level surface ───────────────────────────────
#
# Everything here reproduces what the original's module-level code left in this namespace, with the
# values it hardcoded now read from the config object. `settings_from_config()` raises ConfigError
# right here, at import, if this unit cannot see its config: acceptance item (d). That call sits
# OUTSIDE both guarded import blocks below and outside `save()`'s guard, so a config error can
# never be swallowed and reported as a missing dependency.

_SETTINGS = settings_from_config()

#: This unit's logger. The original hardcoded the name "jazz-why5" and the `dz_debug`/`logging`
#: providers. A module global, read by `save()` at call time, because the original's was.
_log = _build_logger()

try:
    _import_solver_names()
    #: Whether the configured solver was importable. A module global that callers and tests read
    #: AND rebind, and that every method below reads at CALL time, because the original's did.
    _z3_available = True
except ImportError:
    _z3_available = False
    _log.warning(_SETTINGS["messages"]["solver_unavailable"])

#: The notes-db collection `save()` writes to. The original hardcoded "why5-analyses". It is a
#: module global, and `save()` reads it as one at call time, because the original did and a caller
#: can rebind it.
COLLECTION = _SETTINGS["collection"]


# ─────────────────────────────── the unit itself ───────────────────────────────

class Why5:
    """
    A verified causal chain. Build it with .fact() and .link(), then .check().
    """

    def __init__(self, session_id: str, db_path: str = None, trigger: str = ""):
        """Open a session. Registers it with the solver when one is available.

        `db_path` is only ever tested for truthiness, by `save()`, as a gate — it is never handed
        to the notes client. That is the original's shape and it is preserved; see WHAT THE
        ORIGINAL ACTUALLY DID.
        """
        self.session_id = session_id
        self.db_path = db_path
        self.trigger = trigger
        self._facts = {}       # name -> bool value
        self._links = []       # ordered list of (label, cause, because)
        self._result = None

        if _z3_available:
            new_session(session_id)  # noqa: F821 — bound by _import_solver_names(); see LEAKED NAMES

    def fact(self, name: str, value: bool):
        """Assert a known fact — something we can observe directly. Returns self, so calls chain.

        `value` is tested for TRUTHINESS, not identity, so `fact("x", 1)` asserts the configured
        true literal and `fact("x", "")` the false one. The raw value — not the coerced bool — is
        what lands in `_facts`, and so is what `_format_text()` later renders.
        """
        self._facts[name] = value
        if _z3_available:
            rules = _SETTINGS["rules"]
            add_variable(self.session_id, name, _SETTINGS["variable_type"])  # noqa: F821
            add_constraint(  # noqa: F821
                self.session_id,
                rules["fact_rule_template"].format(name=name),
                rules["fact_constraint_template"].format(
                    name=name,
                    value=rules["true_literal"] if value else rules["false_literal"],
                ),
            )
        return self

    def link(self, label: str, cause: str, because: str):
        """
        Assert: if `because` is true, then `cause` must be true.
        because → cause  (this is one step in the why chain)

        Returns self, so calls chain. Note that the variable bookkeeping — recording an unseen
        `cause` or `because` in `_facts` as None, meaning "unknown, solver decides" — happens ONLY
        when a solver is available. With no solver the link is recorded but `_facts` never learns
        its variables, so the two configurations produce different `_facts` for the same calls.
        That is the original's behavior, preserved.
        """
        self._links.append((label, cause, because))
        if _z3_available:
            # ensure both variables exist
            for var in (cause, because):
                if var not in self._facts:
                    add_variable(self.session_id, var, _SETTINGS["variable_type"])  # noqa: F821
                    self._facts[var] = None  # unknown, solver decides
            add_constraint(  # noqa: F821
                self.session_id,
                label,
                _SETTINGS["rules"]["implication_template"].format(because=because, cause=cause),
            )
        return self

    def check(self) -> dict:
        """Verify the chain. Returns result dict with sat/unsat and bad step if any.

        Three shapes of the returned dict are the original's and are preserved exactly:

          * with no solver, `"chain"` is `self._links` ITSELF — the live list, not a copy — so a
            later `.link()` mutates a result already handed to a caller;
          * on every other branch `"chain"` is a NEW list of `(label, because, cause)` triples,
            with cause and because SWAPPED relative to `_links`;
          * `"bad_step"` in that same dict is NOT swapped: it stays `(label, cause, because)`.

        The bare name `check` below is the module-global solver function this module bound at
        import, not this method — a method name is not in scope inside its own body.

        Raises:
            KeyError: if the solver's reply has no "result" key, as the original's `raw["result"]`
                did.
        """
        if not _z3_available:
            self._result = {"sat": None, "error": _SETTINGS["results"]["no_solver_error"],
                            "chain": self._links}
            return self._result

        raw = check(self.session_id)  # noqa: F821 — bound by _import_solver_names()
        results = _SETTINGS["results"]

        if raw["result"] == results["sat_value"]:
            self._result = {
                "sat": True,
                "session": self.session_id,
                "trigger": self.trigger,
                "chain": [(label, because, cause) for label, cause, because in self._links],
                "root_cause": self._links[-1][1] if self._links else None,
                "model": raw.get("model", {}),
            }
        elif raw["result"] == results["unsat_value"]:
            bad = raw.get("bad_rules", [])
            # find the first link label that appears in bad_rules
            bad_step = next(
                ((label, cause, because) for label, cause, because in self._links
                 if label in bad),
                None
            )
            self._result = {
                "sat": False,
                "session": self.session_id,
                "trigger": self.trigger,
                "chain": [(label, because, cause) for label, cause, because in self._links],
                "bad_step": bad_step,
                "bad_rules": bad,
                "verdict": (
                    results["verdict_template"].format(
                        label=bad_step[0], cause=bad_step[1], because=bad_step[2])
                ) if bad_step else results["inconsistent_verdict"],
            }
        else:
            self._result = {"sat": None, "result": results["unknown_result"],
                            "session": self.session_id}

        return self._result

    def save(self) -> str | None:
        """Write the result to notes-db. Returns note id or None.

        The gate is `db_path` AND `_result`, both by truthiness, so a session that was never
        checked — or was checked into an empty dict — writes nothing.

        Everything after the gate runs inside `except Exception`, exactly as the original had it: a
        missing notes package, a malformed reply, an exception out of `_format_text()`, all become
        one `_log.error` line and a None return. A `ConfigError` cannot land here — this unit's
        whole config was resolved and validated at import, and the only import left inside the
        guard is the genuine one the original guarded too.

        The status ladder is truthiness-then-IDENTITY, as the original wrote it: a `sat` of 0 is
        neither verified nor broken, and comes out "unknown". `db_path` is not passed on; see
        `__init__`.
        """
        if not self.db_path or not self._result:
            return None
        try:
            client = _notes_client()
            cols = {c["name"] for c in client.list_collections()}
            if COLLECTION not in cols:
                client.create_collection(COLLECTION, owner=_SETTINGS["notes_owner"])

            sat = self._result.get("sat")
            statuses = _SETTINGS["statuses"]
            status = statuses["verified"] if sat else (
                statuses["broken"] if sat is False else statuses["unknown"])
            root = self._result.get("root_cause") or self._result.get("verdict", "")

            note = client.add_note(
                collection=COLLECTION,
                title=_SETTINGS["note"]["title_template"].format(
                    status=status,
                    session_id=self.session_id,
                    root=root[:_SETTINGS["note"]["root_limit"]],
                ),
                text=self._format_text(),
                topic=self.session_id,
                tag=status,
                owner=_SETTINGS["notes_owner"],
                extra=self._result,
            )
            _log.info(_SETTINGS["messages"]["saved"].format(
                session_id=self.session_id, status=status))
            return note.get("id") if isinstance(note, dict) else None
        except Exception as e:
            _log.error(_SETTINGS["messages"]["save_failed"].format(error=e))
            return None

    def _format_text(self) -> str:
        """Render the session as the note body: trigger, facts, chain, verdict.

        Facts whose value `is None` are skipped — which is exactly the set `link()` invents for
        variables it has not seen, and also catches a fact explicitly asserted as None.
        """
        text = _SETTINGS["text"]
        lines = [text["trigger_line"].format(trigger=self.trigger), ""]
        lines.append(text["facts_heading"])
        for name, val in self._facts.items():
            if val is not None:
                lines.append(text["fact_line"].format(name=name, value=val))
        lines.append("")
        lines.append(text["chain_heading"])
        for i, (label, cause, because) in enumerate(self._links, 1):
            lines.append(text["chain_line"].format(
                index=i, label=label, because=because, cause=cause))
        lines.append("")
        if self._result:
            if self._result.get("sat"):
                lines.append(text["verified_line"])
                lines.append(text["root_cause_line"].format(
                    root_cause=self._result.get("root_cause")))
            elif self._result.get("sat") is False:
                lines.append(text["broken_line"])
                lines.append(text["bad_step_line"].format(verdict=self._result.get("verdict")))
            else:
                lines.append(text["unknown_line"])
        return "\n".join(lines)


def _notes_client():
    """Resolve the configured notes client, exactly as `from notes_db_mcp import client` would.

    Called from inside `save()`'s `except Exception`, so it must raise what the original's import
    statement raised — an ImportError, whose message becomes the `why5 save failed: ...` line. It
    must NOT bind a module global: the original's import sits in a function body and binds a LOCAL,
    so `coupler.why5.client` does not exist, and inventing it would add a name to the surface.
    """
    module_name, attr = _SETTINGS["notes_provider"]
    return _from_import(_import_module(module_name), attr)


def _build_chain(section_key, session_id, db_path, trigger, haystack):
    """Build a `Why5` from a config chain section: assert its facts, then pick its first matching
    chain and lay down that chain's links.

    Both builders below are this function with a different section, because the original's two
    builders are the same shape with different data — a trigger, a fact list, and an if/elif ladder
    over marker strings. #200 requirement 4 moved that data into the config; what is left is the
    shape, and it is written once.

    The ladder semantics are the original's: the FIRST chain whose markers match wins, arms are
    tried in config order, and the arm with no markers is the `else`. `_chain_section` proved at
    import that exactly one such arm exists.

    Args:
        section_key: `"ci"` or `"commit"`.
        session_id, db_path, trigger: passed to `Why5`.
        haystack: the text the markers are searched for in — already lowercased by the caller if
            the section says so.
    """
    section = _SETTINGS[section_key]
    w = Why5(session_id=session_id, db_path=db_path, trigger=trigger)

    for spec in section["facts"]:
        if "value" in spec:
            value = spec["value"]
        else:
            # `any(...)` is a bool, exactly as the original's `"X" in out or "Y" in out` was: both
            # operands of that `or` are already bools, so it never returned a non-bool.
            value = any(marker in haystack for marker in spec["any_of"])
        w.fact(spec["name"], value)

    for chain in section["chains"]:
        if chain["any_of"] is None or any(marker in haystack for marker in chain["any_of"]):
            for label, cause, because in chain["links"]:
                w.link(label, cause=cause, because=because)
            break

    return w


def _haystack(section_key, text):
    """Return the text the section's markers are searched in.

    The CI builder searches the pytest output verbatim (its markers are `SyntaxError` and friends,
    which are capitalised); the commit builder searches `error.lower()` (its markers are lowercase
    phrases like `nothing to commit`). That asymmetry is the original's, and it is config here
    because it is a param the original baked in.
    """
    return text.lower() if _SETTINGS[section_key]["match_lowercase"] else text


def from_ci_failure(session_id: str, branch: str, pre_sha: str,
                    pytest_output: str, db_path: str = None) -> Why5:
    """
    Build a why5 chain from a CI failure.
    Facts are derived from what we know at pipeline failure time.
    """
    section = _SETTINGS["ci"]
    return _build_chain(
        "ci", session_id, db_path,
        section["trigger_template"].format(
            branch=branch, sha=pre_sha[:section["sha_length"]]),
        _haystack("ci", pytest_output),
    )


def from_commit_failure(session_id: str, agent_name: str, file_path: str,
                        error: str, db_path: str = None) -> Why5:
    """Build a why5 chain from a failed commit or write in the agent loop."""
    section = _SETTINGS["commit"]
    return _build_chain(
        "commit", session_id, db_path,
        section["trigger_template"].format(agent_name=agent_name, file_path=file_path),
        _haystack("commit", error),
    )


# ═════════════════════════ the original, embedded verbatim ═════════════════════════
#
# Ticket #373's own words: "THE ORIGINAL SOURCE, EMBEDDED — YOU NEED NO FORGE ACCESS TO DO THIS
# TICKET. The module's own bytes are reproduced below, inside this ticket. THEY are the
# authoritative copy and the behavior-preserving basis." They are reproduced here for the same
# reason: so this file's equivalence claim can be CHECKED by whoever reads it, with no forge access
# and no trust in the author. `selftest` [0] hashes these bytes and [2]/[3] RUN them as the oracle.
#
# A RAW string is required, not decoration: the source's last statement is `return "\n".join(lines)`,
# and in a cooked string that `\n` would become a real newline and change the bytes — check [0]'s
# hash would fail, which is exactly the point of hashing it.

ORIGINAL_SOURCE = r'''# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 testmonkeyalpha — Claude & Co.

"""
why5.py — verified root cause analysis via Z3.

A Why5 session is a causal chain of 5 links. Each link asserts:
  observation → cause

Z3 verifies the full chain is consistent with known facts.
If any link is wrong, Z3 returns unsat and names the bad step.

(Ported into the coupler package from jazz/jazz/agent/why5.py during the
jazz→jazz-new fold: z3_mcp is now the installed forge package, not a relative
path into the jazz tree.)

Usage:
    w = Why5("ci-failure-abc123", db_path=db_path)
    w.fact("ci_failed", True)
    w.fact("llm_is_down", False)
    w.link("why1", cause="test_file_broken", because="ci_failed")
    ...
    result = w.check()
    w.save()   # writes to notes-db
"""

import sys
import os

try:
    from dz_debug import Logger
    _log = Logger("jazz-why5")
    if not hasattr(_log, "warning"):
        _log.warning = _log.warn if hasattr(_log, "warn") else _log.info
except ImportError:
    import logging
    _log = logging.getLogger("jazz-why5")

# z3_mcp is an installed package (forge/work/z3_mcp) — import its solver directly
try:
    from z3_mcp.solver import new_session, add_variable, add_constraint, check, reset_session
    _z3_available = True
except ImportError:
    _z3_available = False
    _log.warning("z3_mcp not available — why5 will record chains but cannot verify them")

COLLECTION = "why5-analyses"


class Why5:
    """
    A verified causal chain. Build it with .fact() and .link(), then .check().
    """

    def __init__(self, session_id: str, db_path: str = None, trigger: str = ""):
        self.session_id = session_id
        self.db_path = db_path
        self.trigger = trigger
        self._facts = {}       # name -> bool value
        self._links = []       # ordered list of (label, cause, because)
        self._result = None

        if _z3_available:
            new_session(session_id)

    def fact(self, name: str, value: bool):
        """Assert a known fact — something we can observe directly."""
        self._facts[name] = value
        if _z3_available:
            add_variable(self.session_id, name, "bool")
            add_constraint(
                self.session_id,
                f"fact-{name}",
                f"{name} == {'True' if value else 'False'}"
            )
        return self

    def link(self, label: str, cause: str, because: str):
        """
        Assert: if `because` is true, then `cause` must be true.
        because → cause  (this is one step in the why chain)
        """
        self._links.append((label, cause, because))
        if _z3_available:
            # ensure both variables exist
            for var in (cause, because):
                if var not in self._facts:
                    add_variable(self.session_id, var, "bool")
                    self._facts[var] = None  # unknown, solver decides
            add_constraint(
                self.session_id,
                label,
                f"Implies({because}, {cause})"
            )
        return self

    def check(self) -> dict:
        """Verify the chain. Returns result dict with sat/unsat and bad step if any."""
        if not _z3_available:
            self._result = {"sat": None, "error": "z3 not available", "chain": self._links}
            return self._result

        raw = check(self.session_id)

        if raw["result"] == "sat":
            self._result = {
                "sat": True,
                "session": self.session_id,
                "trigger": self.trigger,
                "chain": [(label, because, cause) for label, cause, because in self._links],
                "root_cause": self._links[-1][1] if self._links else None,
                "model": raw.get("model", {}),
            }
        elif raw["result"] == "unsat":
            bad = raw.get("bad_rules", [])
            # find the first link label that appears in bad_rules
            bad_step = next(
                ((label, cause, because) for label, cause, because in self._links
                 if label in bad),
                None
            )
            self._result = {
                "sat": False,
                "session": self.session_id,
                "trigger": self.trigger,
                "chain": [(label, because, cause) for label, cause, because in self._links],
                "bad_step": bad_step,
                "bad_rules": bad,
                "verdict": (
                    f"Chain broken at '{bad_step[0]}': "
                    f"'{bad_step[2]}' does not imply '{bad_step[1]}'"
                ) if bad_step else "Chain is inconsistent",
            }
        else:
            self._result = {"sat": None, "result": "unknown", "session": self.session_id}

        return self._result

    def save(self) -> str | None:
        """Write the result to notes-db. Returns note id or None."""
        if not self.db_path or not self._result:
            return None
        try:
            from notes_db_mcp import client
            cols = {c["name"] for c in client.list_collections()}
            if COLLECTION not in cols:
                client.create_collection(COLLECTION, owner="system")

            sat = self._result.get("sat")
            status = "verified" if sat else ("broken" if sat is False else "unknown")
            root = self._result.get("root_cause") or self._result.get("verdict", "")

            note = client.add_note(
                collection=COLLECTION,
                title=f"[{status}] {self.session_id}: {root[:80]}",
                text=self._format_text(),
                topic=self.session_id,
                tag=status,
                owner="system",
                extra=self._result,
            )
            _log.info(f"why5 saved: {self.session_id} ({status})")
            return note.get("id") if isinstance(note, dict) else None
        except Exception as e:
            _log.error(f"why5 save failed: {e}")
            return None

    def _format_text(self) -> str:
        lines = [f"TRIGGER: {self.trigger}", ""]
        lines.append("FACTS:")
        for name, val in self._facts.items():
            if val is not None:
                lines.append(f"  {name} = {val}")
        lines.append("")
        lines.append("CHAIN:")
        for i, (label, cause, because) in enumerate(self._links, 1):
            lines.append(f"  {i}. [{label}] {because} → {cause}")
        lines.append("")
        if self._result:
            if self._result.get("sat"):
                lines.append(f"RESULT: VERIFIED ✓")
                lines.append(f"ROOT CAUSE: {self._result.get('root_cause')}")
            elif self._result.get("sat") is False:
                lines.append(f"RESULT: BROKEN ✗")
                lines.append(f"BAD STEP: {self._result.get('verdict')}")
            else:
                lines.append("RESULT: UNKNOWN")
        return "\n".join(lines)


def from_ci_failure(session_id: str, branch: str, pre_sha: str,
                    pytest_output: str, db_path: str = None) -> Why5:
    """
    Build a why5 chain from a CI failure.
    Facts are derived from what we know at pipeline failure time.
    """
    w = Why5(
        session_id=session_id,
        db_path=db_path,
        trigger=f"CI failed on branch {branch} at {pre_sha[:8]}"
    )

    # known facts from CI run
    w.fact("ci_failed", True)
    w.fact("tests_exist", "PASSED" in pytest_output or "FAILED" in pytest_output)
    w.fact("import_error", "ImportError" in pytest_output or "ModuleNotFoundError" in pytest_output)
    w.fact("assertion_error", "AssertionError" in pytest_output)
    w.fact("syntax_error", "SyntaxError" in pytest_output)

    # build the most likely chain based on error type
    if "SyntaxError" in pytest_output:
        w.link("why1", cause="test_unparseable", because="ci_failed")
        w.link("why2", cause="syntax_error", because="test_unparseable")
        w.link("why3", cause="code_not_verified_before_commit", because="syntax_error")
        w.link("why4", cause="no_self_check_in_loop", because="code_not_verified_before_commit")
        w.link("why5", cause="loop_missing_verify_step", because="no_self_check_in_loop")
    elif "ImportError" in pytest_output or "ModuleNotFoundError" in pytest_output:
        w.link("why1", cause="missing_dependency", because="ci_failed")
        w.link("why2", cause="import_error", because="missing_dependency")
        w.link("why3", cause="dependency_not_declared", because="import_error")
        w.link("why4", cause="no_install_check_before_commit", because="dependency_not_declared")
        w.link("why5", cause="agents_assume_env_complete", because="no_install_check_before_commit")
    elif "AssertionError" in pytest_output:
        w.link("why1", cause="test_assertion_failed", because="ci_failed")
        w.link("why2", cause="assertion_error", because="test_assertion_failed")
        w.link("why3", cause="code_changed_test_not_updated", because="assertion_error")
        w.link("why4", cause="no_dependency_graph_between_code_and_tests", because="code_changed_test_not_updated")
        w.link("why5", cause="agents_work_without_shared_state", because="no_dependency_graph_between_code_and_tests")
    else:
        w.link("why1", cause="test_failed", because="ci_failed")
        w.link("why2", cause="code_incorrect", because="test_failed")
        w.link("why3", cause="no_verification_before_commit", because="code_incorrect")
        w.link("why4", cause="agent_loop_lacks_feedback", because="no_verification_before_commit")
        w.link("why5", cause="consequences_not_felt_at_agent_level", because="agent_loop_lacks_feedback")

    return w


def from_commit_failure(session_id: str, agent_name: str, file_path: str,
                        error: str, db_path: str = None) -> Why5:
    """Build a why5 chain from a failed commit or write in the agent loop."""
    w = Why5(
        session_id=session_id,
        db_path=db_path,
        trigger=f"{agent_name} failed to commit {file_path}"
    )

    w.fact("commit_failed", True)
    w.fact("merge_conflict", "conflict" in error.lower())
    w.fact("nothing_to_commit", "nothing to commit" in error.lower())
    w.fact("push_rejected", "rejected" in error.lower() or "non-fast-forward" in error.lower())

    if "conflict" in error.lower():
        w.link("why1", cause="conflicting_changes", because="commit_failed")
        w.link("why2", cause="merge_conflict", because="conflicting_changes")
        w.link("why3", cause="two_agents_edited_same_file", because="merge_conflict")
        w.link("why4", cause="no_file_ownership_model", because="two_agents_edited_same_file")
        w.link("why5", cause="queue_assigns_same_file_to_multiple_agents", because="no_file_ownership_model")
    elif "rejected" in error.lower():
        w.link("why1", cause="push_rejected", because="commit_failed")
        w.link("why2", cause="remote_ahead_of_local", because="push_rejected")
        w.link("why3", cause="pull_rebase_not_run", because="remote_ahead_of_local")
        w.link("why4", cause="push_called_without_sync", because="pull_rebase_not_run")
        w.link("why5", cause="git_ops_push_missing_rebase", because="push_called_without_sync")
    else:
        w.link("why1", cause="write_failed", because="commit_failed")
        w.link("why2", cause="file_not_written", because="write_failed")
        w.link("why3", cause="llm_output_not_parseable", because="file_not_written")
        w.link("why4", cause="output_format_not_enforced", because="llm_output_not_parseable")
        w.link("why5", cause="prompt_missing_format_requirement", because="output_format_not_enforced")

    return w
'''

#: The blob sha1 ticket #373 records for the canonical source, and the size it states. Check [0]
#: proves ORIGINAL_SOURCE against both, so a reader needs no forge access to know the oracle below
#: is the real forge module rather than a paraphrase.
ORIGINAL_BLOB_SHA1 = "e5e5d778c4eb20084ef64c9888bdee4eabb57439"
ORIGINAL_SIZE = 11716


def _git_blob_sha1(data: bytes) -> str:
    """Hash `data` the way git hashes a blob: sha1 over `blob <len>\\0` + the bytes.

    This is git's object-id rule, so the digest is directly comparable to the blob sha1 the ticket
    records — no forge access required to check that the embedded copy is genuine.
    """
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# ═════════════════════════ the differential harness ═════════════════════════
#
# Everything below this line is proof machinery and command line. None of it runs at import, and
# nothing above this line calls into it — the unit itself is complete already.
#
# The idea is one sentence: run the ORIGINAL and this rewrite through the SAME scenario, with the
# SAME fakes standing in for dz_debug / z3_mcp.solver / notes_db_mcp, and compare what they did.
# The expected values are therefore never this author's belief about the original; they are read
# off the original as it runs. This is the idiom `coupler/bridge.py` (#357) and
# `coupler/updater.py` (#375) established in this package.
#
# The fakes are reachable by BOTH sides for one reason: the original hardcodes the names
# `dz_debug`, `z3_mcp.solver` and `notes_db_mcp`, and this rewrite's SHIPPED config names exactly
# those same strings. Staging a module in `sys.modules` under a name is what both an `import`
# statement and `importlib.import_module` consult first, so both sides resolve to the identical
# object.


class _SelftestFailure(RuntimeError):
    """Raised when a check fails. Carries no extra state; the message is the report."""


@contextlib.contextmanager
def _staged(mapping):
    """Install `mapping` into `sys.modules` for the duration of the block, then put it all back.

    A value of `None` in `mapping` stages an ABSENCE: `sys.modules[name] = None` is what makes both
    `import name` and `importlib.import_module(name)` raise ImportError, which is how a scenario
    says "this package is not installed" without uninstalling anything. A name that was absent
    before is removed again afterwards; a name that was present is restored to the object it was.
    Check [5] proves the restoration rather than trusting this docstring.
    """
    before = {name: sys.modules.get(name, _MISSING) for name in mapping}
    try:
        sys.modules.update(mapping)
        yield
    finally:
        for name, previous in before.items():
            if previous is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


@contextlib.contextmanager
def _env(**names):
    """Set/unset environment variables for the duration of the block, then put them back.

    A value of `None` unsets. Used to point a freshly executed copy of this module at a specific
    config file, so the differential is immune to whatever `$COUPLER_WHY5_CONFIG` happens to be set
    to in the shell that runs `selftest`.
    """
    before = {name: os.environ.get(name) for name in names}
    try:
        for name, value in names.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _exec_module(source, name, file_path):
    """Execute `source` as a fresh, throwaway module and return it.

    Fresh per scenario, because both the original and this rewrite decide `_z3_available`, `_log`
    and their leaked names at IMPORT — so the import is part of what a scenario stages, and a
    module imported once could only ever exercise one branch. `name` is never `"__main__"`, so this
    module's own command-line block does not fire when the rewrite is executed this way.

    The module is put in `sys.modules` for the duration (import machinery expects to find an
    executing module there) and removed afterwards, so nothing that follows can accidentally import
    a throwaway copy.
    """
    module = types.ModuleType(name)
    module.__file__ = file_path
    sys.modules[name] = module
    try:
        exec(compile(source, file_path, "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


def _own_source():
    """Return THIS file's source text, for executing a fresh copy of the rewrite.

    Read from disk rather than reconstructed, so what is proven is the file that ships.
    """
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as handle:
        return handle.read()


def shipped_config():
    """Return the config object THIS PACKAGE SHIPS, ignoring `$COUPLER_WHY5_CONFIG`.

    The differential is only meaningful against the shipped config — that is the whole claim: that
    the values in `registry.json` are the original's values. Reading it through the environment
    would let whoever runs `selftest` steer the proof, so the environment is skipped here.

    Raises:
        ConfigError: if this package's own registry cannot be read.
    """
    config, _base, _source = load_config(
        start=os.path.dirname(os.path.abspath(__file__)), use_env=False)
    return config


def _freeze(obj):
    """Render `obj` as a stable, TYPE-SENSITIVE string, for comparing oracle against rewrite.

    Type-sensitive matters more than it looks: `repr` distinguishes `True` from `1` and from
    `"True"`, and a tuple from a list — and this unit's behavior turns on exactly those
    distinctions (`fact()`'s truthiness, `save()`'s `sat is False`, `check()`'s tuples). Dict order
    is preserved rather than sorted, because `_facts`' insertion order is observable through
    `_format_text()`.
    """
    if isinstance(obj, dict):
        return "{" + ", ".join("%s: %s" % (_freeze(k), _freeze(v)) for k, v in obj.items()) + "}"
    if isinstance(obj, tuple):
        return "(" + ", ".join(_freeze(item) for item in obj) + ")"
    if isinstance(obj, list):
        return "[" + ", ".join(_freeze(item) for item in obj) + "]"
    if isinstance(obj, (set, frozenset)):
        return "{" + ", ".join(sorted(_freeze(item) for item in obj)) + "}"
    if isinstance(obj, (str, bool, int, float, type(None))):
        return repr(obj)
    if isinstance(obj, BaseException):
        return "%s(%s)" % (type(obj).__name__, obj)
    return "<%s>" % type(obj).__name__


# ─────────────────────────── the fakes a scenario stages ───────────────────────────

def _fake_logger_class(rec, methods):
    """Build a stand-in for `dz_debug.Logger` carrying exactly `methods`.

    Which methods exist is the point: the original probes `hasattr(_log, "warning")` and then
    `hasattr(_log, "warn")`, so a Logger with only `warn`, or with neither, drives a different
    branch. Every call is recorded UNDER THE NAME OF THE METHOD THAT RAN, so the aliasing
    `_log.warning = _log.warn` is proven behaviorally — the record says `warn` — rather than by
    inspecting an attribute.
    """
    namespace = {"__init__": lambda self, name: rec.append(("Logger(", _freeze(name), ")"))}
    for method in methods:
        def make(method_name):
            def call(self, *args):
                rec.append(("log." + method_name,) + tuple(_freeze(a) for a in args))
            return call
        namespace[method] = make(method)
    return type("FakeLogger", (), namespace)


def _fake_solver(rec, reply, omit=()):
    """Build a stand-in for `z3_mcp.solver`.

    `reply` is what `check()` answers with — a dict, or an Exception instance to raise. `omit`
    leaves names OFF the module, which is how the partial-import case is staged: CPython binds the
    names of a `from X import a, b, c` one at a time, so omitting `reset_session` must leave the
    other four bound and still set `_z3_available = False`.
    """
    module = types.ModuleType("z3_mcp.solver")

    def new_session(session_id):
        rec.append(("new_session", _freeze(session_id)))

    def add_variable(session_id, name, kind):
        rec.append(("add_variable", _freeze(session_id), _freeze(name), _freeze(kind)))

    def add_constraint(session_id, label, expression):
        rec.append(("add_constraint", _freeze(session_id), _freeze(label), _freeze(expression)))

    def check_(session_id):
        rec.append(("check", _freeze(session_id)))
        if isinstance(reply, BaseException):
            raise reply
        return reply

    def reset_session(session_id):
        rec.append(("reset_session", _freeze(session_id)))

    for name, value in (("new_session", new_session), ("add_variable", add_variable),
                        ("add_constraint", add_constraint), ("check", check_),
                        ("reset_session", reset_session)):
        if name not in omit:
            setattr(module, name, value)
    return module


def _fake_notes(rec, collections=(), note=None, raises=None):
    """Build a stand-in for `notes_db_mcp`, exposing the `client` the original imports from it.

    `collections` are the collection names `list_collections` reports (so a scenario can stage the
    collection as already-present or absent, which decides whether `create_collection` is called).
    `note` is what `add_note` returns. `raises` makes `add_note` raise, to drive `save()`'s guard.
    """
    module = types.ModuleType("notes_db_mcp")
    client = types.ModuleType("notes_db_mcp.client")

    def list_collections():
        rec.append(("list_collections",))
        return [{"name": name} for name in collections]

    def create_collection(name, owner=None):
        rec.append(("create_collection", _freeze(name), _freeze(owner)))

    def add_note(**kwargs):
        rec.append(("add_note", _freeze(dict(sorted(kwargs.items())))))
        if raises is not None:
            raise raises
        return note

    client.list_collections = list_collections
    client.create_collection = create_collection
    client.add_note = add_note
    module.client = client
    return module


def _stage_for(rec, dz="full", solver=None, solver_omit=(), notes=None):
    """Build the `sys.modules` mapping one scenario stages. See `_staged` for the None convention.

    Args:
        rec: the list every fake records its calls into.
        dz: "full" (a Logger with warning+warn+info+error+debug), "warn-only" (no `warning`),
            "bare" (neither `warning` nor `warn`), "no-Logger" (the module exists but has no
            `Logger`), or "absent" (the package is not installed).
        solver: None to stage `z3_mcp` as absent; otherwise the reply `check()` answers with.
        solver_omit: names to leave off the fake solver, for the partial-import case.
        notes: None to stage `notes_db_mcp` as absent; otherwise a kwargs dict for `_fake_notes`.
    """
    mapping = {}

    if dz == "absent":
        mapping["dz_debug"] = None
    else:
        module = types.ModuleType("dz_debug")
        if dz == "full":
            module.Logger = _fake_logger_class(rec, ("warning", "warn", "info", "error", "debug"))
        elif dz == "warn-only":
            module.Logger = _fake_logger_class(rec, ("warn", "info", "error", "debug"))
        elif dz == "bare":
            module.Logger = _fake_logger_class(rec, ("info", "error", "debug"))
        elif dz == "no-Logger":
            pass  # the module exists but has no `Logger`: `from dz_debug import Logger` raises
        else:
            raise _SelftestFailure("unknown dz staging %r" % (dz,))
        mapping["dz_debug"] = module

    if solver is None:
        mapping["z3_mcp"] = None
        mapping["z3_mcp.solver"] = None
    else:
        package = types.ModuleType("z3_mcp")
        package.__path__ = []
        solver_module = _fake_solver(rec, solver, omit=solver_omit)
        package.solver = solver_module
        mapping["z3_mcp"] = package
        mapping["z3_mcp.solver"] = solver_module

    if notes is None:
        mapping["notes_db_mcp"] = None
    else:
        mapping["notes_db_mcp"] = _fake_notes(rec, **notes)

    return mapping


def _module_names(module):
    """Report which of the original's conditionally-leaked module attributes exist.

    See LEAKED NAMES: which names an import left behind is observable behavior, so it is compared
    rather than described.
    """
    watched = ("Logger", "logging", "client") + SOLVER_NAMES
    return [name for name in watched if hasattr(module, name)]


def _observe(scenario, source, name, file_path, config_path):
    """Import a module under the scenario's staging, drive it, and report everything observable.

    Called once for the ORACLE and once for the REWRITE, with the identical scenario, and the two
    reports are compared field for field. `config_path` is only used by the rewrite — the original
    has no config to point at, which is the entire reason this ticket exists.
    """
    rec = []
    with _staged(_stage_for(rec, **scenario.get("stage", {}))):
        try:
            with _env(**{CONFIG_ENV: config_path}):
                module = _exec_module(source, name, file_path)
        except BaseException as exc:  # noqa: BLE001 — an import that dies IS an observation
            return {"import": "RAISED " + _freeze(exc), "names": [], "z3": None,
                    "collection": None, "ran": None, "calls": _freeze(rec)}

        report = {
            "import": "ok",
            "names": _module_names(module),
            "z3": _freeze(getattr(module, "_z3_available", "<unbound>")),
            "collection": _freeze(getattr(module, "COLLECTION", "<unbound>")),
        }
        try:
            report["ran"] = _freeze(scenario["run"](module))
        except BaseException as exc:  # noqa: BLE001 — a raise IS an observation, and is compared
            report["ran"] = "RAISED " + _freeze(exc)
        report["calls"] = _freeze(rec)
        return report


# ─────────────────────────── the drivers a scenario runs ───────────────────────────
#
# Each takes a MODULE — the oracle or the rewrite, indistinguishably — and returns whatever it
# observed. The same driver runs against both, which is what makes the comparison meaningful.

SAT_REPLY = {"result": "sat", "model": {"ci_failed": True, "test_failed": True}}
UNSAT_REPLY = {"result": "unsat", "bad_rules": ["why3"]}

CI_LOG_IMPORT = "E   ImportError: cannot import name 'x'\n1 failed"
CI_LOG_SYNTAX = "E   SyntaxError: invalid syntax\nE   AssertionError: also this\n1 failed"
CI_LOG_ASSERT = "E   AssertionError: assert 1 == 2\nPASSED tests/test_a.py::test_b"
CI_LOG_PLAIN = "1 failed, 0 passed -- something went wrong"


def _session(module, **kw):
    """Open a session the way a caller would. Kept in one place so oracle and rewrite are opened
    identically."""
    return module.Why5("s-1", **kw)


def _drive_manual(module, db_path=None):
    """Build a small chain by hand, check it, and render it — the module docstring's own Usage."""
    w = _session(module, db_path=db_path, trigger="t")
    chained = w.fact("ci_failed", True) is w and w.fact("llm_is_down", False) is w
    chained = chained and w.link("why1", cause="test_file_broken", because="ci_failed") is w
    w.link("why2", cause="root", because="test_file_broken")
    result = w.check()
    return {"chaining_returns_self": chained, "result": result, "facts": w._facts,
            "links": w._links, "text": w._format_text()}


def _drive_save(module, db_path="/tmp/notes.db", reply=None):
    """Build, check and SAVE — the whole path through the notes client."""
    w = _session(module, db_path=db_path, trigger="t")
    w.fact("ci_failed", True)
    w.link("why1", cause="root", because="ci_failed")
    result = w.check()
    return {"result": result, "saved": w.save(), "text": w._format_text()}


def _drive_save_forced(module, sat, db_path="/tmp/notes.db"):
    """Force a `_result` with a chosen `sat` and save it, to walk `save()`'s status ladder.

    Reaching in and setting `_result` is the only way to stage a `sat` of 0 or 1: no solver reply
    produces one. The ladder is the original's `verified if sat else (broken if sat is False else
    unknown)`, and 0 falls through BOTH tests. Both sides are staged identically.
    """
    w = _session(module, db_path=db_path, trigger="t")
    w.fact("ci_failed", True)
    w.link("why1", cause="root", because="ci_failed")
    w._result = {"sat": sat, "root_cause": "root", "verdict": "v"}
    return {"saved": w.save(), "text": w._format_text()}


def _drive_ci(module, log, sha="abcdef1234567890", branch="main"):
    """Run from_ci_failure and report everything it built."""
    w = module.from_ci_failure("s-1", branch=branch, pre_sha=sha, pytest_output=log)
    return {"trigger": w.trigger, "facts": w._facts, "links": w._links,
            "db_path": w.db_path, "type": type(w).__name__}


def _drive_commit(module, error, agent="coder-1", path="a/b.py"):
    """Run from_commit_failure and report everything it built."""
    w = module.from_commit_failure("s-1", agent_name=agent, file_path=path, error=error)
    return {"trigger": w.trigger, "facts": w._facts, "links": w._links, "db_path": w.db_path}


def _drive_alias(module):
    """Prove the no-solver result's `chain` IS the live `_links` list, by identity, and that a
    later `.link()` therefore mutates a result already returned."""
    w = _session(module)
    w.link("why1", cause="a", because="b")
    result = w.check()
    aliased = result["chain"] is w._links
    w.link("why2", cause="c", because="d")
    return {"chain_is_links": aliased, "chain_after_later_link": result["chain"]}


# ─────────────────────────── the equivalence tables ───────────────────────────
#
# Ticket #373 captured NO exemplars (criteria_miner "mines only self-contained pure functions ...
# and nothing here qualified"), and says that "MOVES the work: you must write the equivalence
# exemplars by hand from the original's behavior before rewriting, and they are what settles this
# ticket". These two tables are that hand-written work.
#
# EXEMPLARS are the behavior a caller of this unit actually exercises. EDGE_CASES are the corners
# "what sampling cannot reach" — the quirks listed under WHAT THE ORIGINAL ACTUALLY DID, the
# conditional name leaks, and the failure paths.
#
# Each entry is (label, what it pins down, what to stage, what to run). NO EXPECTED VALUE IS
# WRITTEN HERE, and that is deliberate: `_check_differential` runs every entry against the ORACLE
# and against this rewrite under identical staging and requires the observations to be equal, so
# the expectation is the original itself. A table of hand-typed expectations would only ever be as
# good as its author's reading of the original; this cannot be.

EXEMPLARS = [
    {
        "label": "sat: hand-built chain, solver says the chain holds",
        "pins": "the sat result dict, its SWAPPED (label, because, cause) chain, root_cause as the "
                "last link's cause, the model passthrough, and the exact z3 call sequence",
        "stage": {"solver": SAT_REPLY},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "unsat: solver names why3 as the broken rule",
        "pins": "the unsat result dict, bad_step in UNSWAPPED (label, cause, because) order beside "
                "a swapped chain, and the rendered verdict",
        "stage": {"solver": UNSAT_REPLY},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "no solver: the unit records the chain but cannot verify it",
        "pins": "the import-time warning, _z3_available, the {sat: None, error, chain} result, and "
                "that no z3 call is made at all",
        "stage": {"solver": None},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "from_ci_failure: an ImportError log",
        "pins": "the trigger with pre_sha[:8], the five derived facts, and the missing_dependency "
                "chain",
        "stage": {"solver": None},
        "run": lambda m: _drive_ci(m, CI_LOG_IMPORT),
    },
    {
        "label": "from_ci_failure: a SyntaxError log that ALSO contains AssertionError",
        "pins": "that the ladder is first-match-wins in source order — syntax beats assertion — "
                "while BOTH facts are still asserted true",
        "stage": {"solver": None},
        "run": lambda m: _drive_ci(m, CI_LOG_SYNTAX),
    },
    {
        "label": "from_ci_failure: an AssertionError log with a PASSED line",
        "pins": "the assertion chain and tests_exist becoming True from the PASSED marker",
        "stage": {"solver": None},
        "run": lambda m: _drive_ci(m, CI_LOG_ASSERT),
    },
    {
        "label": "from_ci_failure: a log with no recognised marker",
        "pins": "the default (else) chain, and every marker-derived fact being False",
        "stage": {"solver": None},
        "run": lambda m: _drive_ci(m, CI_LOG_PLAIN),
    },
    {
        "label": "from_commit_failure: a merge conflict",
        "pins": "the trigger, the four facts, and the conflict chain",
        "stage": {"solver": None},
        "run": lambda m: _drive_commit(m, "CONFLICT (content): Merge conflict in a/b.py"),
    },
    {
        "label": "from_commit_failure: a rejected push",
        "pins": "the rejected chain, and that 'rejected' is matched case-insensitively",
        "stage": {"solver": None},
        "run": lambda m: _drive_commit(m, "! [remote rejected] main -> main (non-fast-forward)"),
    },
    {
        "label": "from_commit_failure: anything else",
        "pins": "the default write_failed chain and nothing_to_commit staying False",
        "stage": {"solver": None},
        "run": lambda m: _drive_commit(m, "fatal: could not write file"),
    },
    {
        "label": "save: the collection does not exist yet",
        "pins": "create_collection with the configured owner, the note title, tag, topic, extra "
                "and body, the saved log line, and the returned note id",
        "stage": {"solver": SAT_REPLY, "notes": {"collections": (), "note": {"id": "n-7"}}},
        "run": lambda m: _drive_save(m),
    },
    {
        "label": "save: the collection already exists",
        "pins": "that create_collection is NOT called when list_collections already names it",
        "stage": {"solver": SAT_REPLY,
                  "notes": {"collections": ("why5-analyses",), "note": {"id": "n-8"}}},
        "run": lambda m: _drive_save(m),
    },
    {
        "label": "save: a broken chain is saved as status 'broken'",
        "pins": "the status ladder's sat-is-False arm, and the title's root falling back to the "
                "verdict when there is no root_cause",
        "stage": {"solver": UNSAT_REPLY,
                  "notes": {"collections": (), "note": {"id": "n-9"}}},
        "run": lambda m: _drive_save(m),
    },
    {
        "label": "dz_debug present: its Logger is used and leaks the name",
        "pins": "Logger(name) construction and that coupler.why5.Logger resolves while "
                "coupler.why5.logging does not",
        "stage": {"dz": "full", "solver": SAT_REPLY},
        "run": lambda m: _drive_manual(m),
    },
]

EDGE_CASES = [
    {
        "label": "the no-solver result ALIASES the live _links list",
        "pins": "that {'chain': self._links} stores the list itself, so a later .link() mutates a "
                "result already handed to the caller — every other branch copies",
        "stage": {"solver": None},
        "run": _drive_alias,
    },
    {
        "label": "link() teaches _facts its variables ONLY when a solver is available",
        "pins": "that the same calls produce different _facts with and without a solver, and that "
                "_format_text() skips the None-valued ones the solver path invents",
        "stage": {"solver": SAT_REPLY},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "fact() tests truthiness, not identity",
        "pins": "that 1/''/None/[] choose the true or false literal by truthiness, that the RAW "
                "value lands in _facts, and that a None fact is skipped by _format_text()",
        "stage": {"solver": SAT_REPLY},
        "run": lambda m: _drive_truthiness(m),
    },
    {
        "label": "unsat naming a rule this chain does not have",
        "pins": "bad_step None and the 'Chain is inconsistent' verdict",
        "stage": {"solver": {"result": "unsat", "bad_rules": ["nope"]}},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "unsat with no bad_rules key at all",
        "pins": "the .get default of [] and the inconsistent verdict",
        "stage": {"solver": {"result": "unsat"}},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "sat with no model key",
        "pins": "the .get default of {} for model",
        "stage": {"solver": {"result": "sat"}},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "the solver answers something that is neither sat nor unsat",
        "pins": "the {sat: None, result: 'unknown', session} branch and its RESULT: UNKNOWN body",
        "stage": {"solver": {"result": "timeout"}},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "the solver's reply has no 'result' key",
        "pins": "that raw['result'] raises KeyError out of check(), ungarded, as the original left "
                "it",
        "stage": {"solver": {"nope": 1}},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "sat on a session with NO links",
        "pins": "root_cause None from the empty-links conditional",
        "stage": {"solver": SAT_REPLY},
        "run": lambda m: _drive_no_links(m),
    },
    {
        "label": "z3_mcp.solver exists but has no reset_session",
        "pins": "the PARTIAL import: the four names before it stay bound, _z3_available is False, "
                "and the unavailable warning is logged anyway",
        "stage": {"solver": SAT_REPLY, "solver_omit": ("reset_session",)},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "z3_mcp.solver exists but has no check",
        "pins": "the partial import stopping mid-list: new_session/add_variable/add_constraint "
                "stay bound, reset_session never binds",
        "stage": {"solver": SAT_REPLY, "solver_omit": ("check",)},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "dz_debug absent: the logging fallback",
        "pins": "that `import logging` runs, leaking coupler.why5.logging and NOT Logger",
        "stage": {"dz": "absent", "solver": None},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "dz_debug present but without Logger",
        "pins": "that a missing attribute raises ImportError (not AttributeError) and so falls "
                "back to logging, exactly as `from dz_debug import Logger` would",
        "stage": {"dz": "no-Logger", "solver": None},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "a Logger with warn but no warning",
        "pins": "the alias _log.warning = _log.warn — the record names the method that RAN",
        "stage": {"dz": "warn-only", "solver": None},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "a Logger with neither warning nor warn",
        "pins": "the second alias arm, _log.warning = _log.info",
        "stage": {"dz": "bare", "solver": None},
        "run": lambda m: _drive_manual(m),
    },
    {
        "label": "save with no db_path",
        "pins": "the gate: None returned and the notes client never even imported",
        "stage": {"solver": SAT_REPLY, "notes": {"collections": (), "note": {"id": "n"}}},
        "run": lambda m: _drive_save(m, db_path=None),
    },
    {
        "label": "save with an empty-string db_path",
        "pins": "that the gate is truthiness, not None-ness",
        "stage": {"solver": SAT_REPLY, "notes": {"collections": (), "note": {"id": "n"}}},
        "run": lambda m: _drive_save(m, db_path=""),
    },
    {
        "label": "save before check()",
        "pins": "the _result half of the gate",
        "stage": {"solver": SAT_REPLY, "notes": {"collections": (), "note": {"id": "n"}}},
        "run": lambda m: _drive_save_unchecked(m),
    },
    {
        "label": "save when notes_db_mcp is not installed",
        "pins": "that the ImportError is swallowed by save()'s guard and reported as one "
                "'why5 save failed: ...' error line, returning None",
        "stage": {"solver": SAT_REPLY, "notes": None},
        "run": lambda m: _drive_save(m),
    },
    {
        "label": "save when add_note raises",
        "pins": "the same guard catching a live client's failure",
        "stage": {"solver": SAT_REPLY,
                  "notes": {"collections": (), "raises": RuntimeError("db is down")}},
        "run": lambda m: _drive_save(m),
    },
    {
        "label": "save when add_note returns a non-dict",
        "pins": "the isinstance test: None returned rather than an AttributeError",
        "stage": {"solver": SAT_REPLY, "notes": {"collections": (), "note": "not-a-dict"}},
        "run": lambda m: _drive_save(m),
    },
    {
        "label": "save when add_note returns a dict with no id",
        "pins": "note.get('id') answering None",
        "stage": {"solver": SAT_REPLY, "notes": {"collections": (), "note": {"other": 1}}},
        "run": lambda m: _drive_save(m),
    },
    {
        "label": "save: sat=0 is neither verified nor broken",
        "pins": "the ladder's truthiness-then-IDENTITY shape — 0 is falsy but `0 is False` is "
                "False, so it lands on 'unknown'",
        "stage": {"solver": None, "notes": {"collections": (), "note": {"id": "n"}}},
        "run": lambda m: _drive_save_forced(m, 0),
    },
    {
        "label": "save: sat=1 is verified",
        "pins": "the same ladder's truthy arm accepting a non-True truthy value",
        "stage": {"solver": None, "notes": {"collections": (), "note": {"id": "n"}}},
        "run": lambda m: _drive_save_forced(m, 1),
    },
    {
        "label": "save: a root_cause longer than the title clamp",
        "pins": "the title's root[:80] truncation",
        "stage": {"solver": None, "notes": {"collections": (), "note": {"id": "n"}}},
        "run": lambda m: _drive_long_root(m),
    },
    {
        "label": "from_ci_failure: a sha shorter than the clamp",
        "pins": "that pre_sha[:8] does not pad or raise on a short sha",
        "stage": {"solver": None},
        "run": lambda m: _drive_ci(m, CI_LOG_PLAIN, sha="abc"),
    },
    {
        "label": "from_ci_failure: an empty sha and an empty branch",
        "pins": "the trigger rendering with empty values rather than failing",
        "stage": {"solver": None},
        "run": lambda m: _drive_ci(m, CI_LOG_PLAIN, sha="", branch=""),
    },
    {
        "label": "from_ci_failure: a ModuleNotFoundError log",
        "pins": "the SECOND marker of the import arm's any_of matching on its own",
        "stage": {"solver": None},
        "run": lambda m: _drive_ci(m, "E   ModuleNotFoundError: No module named 'x'"),
    },
    {
        "label": "from_commit_failure: an UPPERCASE error",
        "pins": "that the commit builder lowercases its haystack and the ci builder does not",
        "stage": {"solver": None},
        "run": lambda m: _drive_commit(m, "NOTHING TO COMMIT, WORKING TREE CLEAN"),
    },
    {
        "label": "from_ci_failure: a lowercase 'syntaxerror' does NOT match",
        "pins": "the ci builder's case SENSITIVITY — the mirror of the case above",
        "stage": {"solver": None},
        "run": lambda m: _drive_ci(m, "e   syntaxerror: invalid syntax"),
    },
    {
        "label": "a chain built with from_ci_failure and then checked and saved",
        "pins": "the two builders composing with check() and save() end to end",
        "stage": {"solver": SAT_REPLY, "notes": {"collections": (), "note": {"id": "n-1"}}},
        "run": lambda m: _drive_ci_saved(m),
    },
    {
        "label": "link() with cause and because already known facts",
        "pins": "that no add_variable is emitted for a variable already in _facts, and that _facts "
                "keeps its original value rather than being reset to None",
        "stage": {"solver": SAT_REPLY},
        "run": lambda m: _drive_known_vars(m),
    },
    {
        "label": "a session_id and fact names containing brace characters",
        "pins": "that values are never re-interpreted as format templates — the original's "
                "f-strings could not, and neither may a .format()-based rewrite",
        "stage": {"solver": SAT_REPLY, "notes": {"collections": (), "note": {"id": "n"}}},
        "run": lambda m: _drive_braces(m),
    },
]


def _drive_truthiness(module):
    """Assert facts with assorted truthy/falsy values and report what was asserted and rendered."""
    w = _session(module, trigger="t")
    for name, value in (("a", 1), ("b", ""), ("c", None), ("d", []), ("e", "no"), ("f", 0)):
        w.fact(name, value)
    return {"facts": w._facts, "text": w._format_text()}


def _drive_no_links(module):
    """Check a session that has facts but no links at all."""
    w = _session(module, trigger="t")
    w.fact("ci_failed", True)
    return {"result": w.check(), "text": w._format_text()}


def _drive_save_unchecked(module):
    """Save without ever calling check()."""
    w = _session(module, db_path="/tmp/notes.db", trigger="t")
    w.fact("ci_failed", True)
    return {"saved": w.save()}


def _drive_long_root(module):
    """Force a root_cause well past the title clamp and save it."""
    w = _session(module, db_path="/tmp/notes.db", trigger="t")
    w._result = {"sat": True, "root_cause": "r" * 200}
    return {"saved": w.save()}


def _drive_ci_saved(module):
    """from_ci_failure -> check -> save, end to end."""
    w = module.from_ci_failure("s-1", branch="main", pre_sha="deadbeefcafe",
                               pytest_output=CI_LOG_ASSERT, db_path="/tmp/notes.db")
    return {"result": w.check(), "saved": w.save(), "text": w._format_text()}


def _drive_known_vars(module):
    """Link variables that are already facts, so link()'s add_variable bookkeeping is skipped."""
    w = _session(module, trigger="t")
    w.fact("ci_failed", True)
    w.fact("root", False)
    w.link("why1", cause="root", because="ci_failed")
    return {"facts": w._facts, "result": w.check(), "text": w._format_text()}


def _drive_braces(module):
    """Drive brace-laden values through every template this unit renders."""
    w = module.Why5("s{0}-{bad}", db_path="/tmp/notes.db", trigger="tr{igger}")
    w.fact("fa{ct}", True)
    w.link("why{1}", cause="ca{use}", because="be{cause}")
    return {"result": w.check(), "saved": w.save(), "text": w._format_text()}


# ─────────────────────────────── the checks ───────────────────────────────

def _report(out, ok, label, detail=""):
    """Print one check line and return `ok`, so a caller can accumulate the verdict."""
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", label, ("  — " + detail) if detail else ""),
          file=out)
    return ok


def _check_original(out):
    """[0] The embedded original IS the forge blob ticket #373 names.

    Everything else in this selftest treats `ORIGINAL_SOURCE` as the oracle, so if these bytes are
    not the real module then every PASS below is meaningless. Hashed the way git hashes a blob, and
    compared against the ticket's own recorded sha1 — which needs no forge access to check.
    """
    print("[0] the embedded original is the forge blob (no forge access needed)", file=out)
    raw = ORIGINAL_SOURCE.encode("utf-8")
    ok = _report(out, len(raw) == ORIGINAL_SIZE, "size is the ticket's %d bytes" % ORIGINAL_SIZE,
                 "got %d" % len(raw))
    digest = _git_blob_sha1(raw)
    ok = _report(out, digest == ORIGINAL_BLOB_SHA1,
                 "git blob sha1 is the ticket's %s" % ORIGINAL_BLOB_SHA1, digest) and ok
    if not ok:
        raise _SelftestFailure(
            "the embedded ORIGINAL_SOURCE is not the blob ticket #373 records, so nothing below "
            "could be trusted. Refusing to report a verdict."
        )
    return ok


def _check_gate(out, package_root):
    """[1] Without a config object, importing this module THROWS. Acceptance item (d).

    Measured in CHILD INTERPRETERS, because the gate fires at import and this process has already
    imported the module successfully — an in-process test could not see the failure it claims to
    prove. Each child runs `import coupler.why5` with `$COUPLER_WHY5_CONFIG` pointed somewhere
    specific, and the child's exit code and stderr are the evidence.
    """
    print("[1] the config gate: no config object -> ConfigError, in child interpreters", file=out)
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        missing = os.path.join(tmp, "does-not-exist.json")
        partial = os.path.join(tmp, "partial.json")
        broken = os.path.join(tmp, "broken.json")
        good = os.path.join(tmp, "good.json")
        config = shipped_config()
        with open(partial, "w", encoding="utf-8") as handle:
            json.dump({key: value for key, value in config.items() if key != "collection"}, handle)
        with open(broken, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        with open(good, "w", encoding="utf-8") as handle:
            json.dump(config, handle)

        cases = [
            (missing, "names a file that does not exist", CONFIG_ENV),
            (partial, "is missing a required key", "collection"),
            (broken, "is not readable as JSON", "could not be read as JSON"),
        ]
        for path, label, needle in cases:
            done = subprocess.run(
                [sys.executable, "-c", "import coupler.why5"],
                cwd=package_root, capture_output=True, text=True,
                env=dict(os.environ, **{CONFIG_ENV: path}),
            )
            ok = _report(out, done.returncode == 1 and "ConfigError" in done.stderr
                         and needle in done.stderr,
                         "$%s %s -> import raises ConfigError naming it" % (CONFIG_ENV, label),
                         "exit %d" % done.returncode) and ok

        done = subprocess.run(
            [sys.executable, "-c", "import coupler.why5; print(coupler.why5.COLLECTION)"],
            cwd=package_root, capture_output=True, text=True,
            env=dict(os.environ, **{CONFIG_ENV: good}),
        )
        ok = _report(out, done.returncode == 0 and config["collection"] in done.stdout,
                     "$%s naming a good config object -> imports and uses it" % CONFIG_ENV,
                     "exit %d" % done.returncode) and ok

        # And the gate is in the CODE, not in the file's presence: with the env var pointed at a
        # config-shaped file that has no unit section, and the walk-up started somewhere with no
        # registry, resolution fails rather than falling back to anything.
        done = subprocess.run(
            [sys.executable, "-c",
             "import coupler.why5 as w; w.load_config(start=%r)" % tmp],
            cwd=package_root, capture_output=True, text=True,
            env={key: value for key, value in os.environ.items() if key != CONFIG_ENV},
        )
        ok = _report(out, done.returncode == 1 and "ConfigError" in done.stderr
                     and "emit-config" in done.stderr,
                     "a walk-up that finds no registry -> ConfigError pointing at emit-config",
                     "exit %d" % done.returncode) and ok
    return ok


def _check_differential(out, title, table, config_path):
    """[2]/[3] Run every table entry against the ORACLE and this REWRITE and compare.

    This is the heart of the ticket. Identical staging, identical driver, two modules; every
    observable — which names the import leaked, `_z3_available`, `COLLECTION`, the driver's whole
    return value, and the exact sequence of calls the fakes recorded — must match. A single
    differing field fails the entry and prints both sides.
    """
    print(title, file=out)
    source = _own_source()
    ok = True
    for index, scenario in enumerate(table):
        oracle = _observe(scenario, ORIGINAL_SOURCE, "_why5_oracle_%d" % index,
                          "<original why5.py>", config_path)
        rewrite = _observe(scenario, source, "_why5_rewrite_%d" % index,
                           os.path.abspath(__file__), config_path)
        differing = [field for field in oracle if oracle[field] != rewrite.get(field)]
        ok = _report(out, not differing, scenario["label"],
                     "" if not differing else "differs in: " + ", ".join(differing)) and ok
        if differing:
            for field in differing:
                print("        %-11s oracle : %s" % (field, oracle[field]), file=out)
                print("        %-11s rewrite: %s" % ("", rewrite.get(field)), file=out)
        else:
            print("        pins: %s" % scenario["pins"], file=out)
    return ok


def _lower_callables(source):
    """Lower every module-level function and method the way codebean's `lower_node` (#183) does.

    The ticket states the surface in exactly this notation, so reproducing the notation is what
    lets check [4] compare against the ticket's own words rather than against a paraphrase of them.
    """
    lowered = []

    def one(node, prefix):
        arguments = node.args
        parts = []
        positional = list(arguments.posonlyargs) + list(arguments.args)
        offset = len(positional) - len(arguments.defaults)
        for position, argument in enumerate(positional):
            rendered = argument.arg
            if argument.annotation is not None:
                rendered += ": " + ast.unparse(argument.annotation)
            if position >= offset:
                rendered += "=" + ast.unparse(arguments.defaults[position - offset])
            parts.append(rendered)
        if arguments.vararg is not None:
            parts.append("*" + arguments.vararg.arg)
        for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults):
            rendered = argument.arg
            if argument.annotation is not None:
                rendered += ": " + ast.unparse(argument.annotation)
            if default is not None:
                rendered += "=" + ast.unparse(default)
            parts.append(rendered)
        if arguments.kwarg is not None:
            parts.append("**" + arguments.kwarg.arg)
        rendered = "%s%s(%s)" % (prefix, node.name, ", ".join(parts))
        if node.returns is not None:
            rendered += " -> " + ast.unparse(node.returns)
        lowered.append(rendered)

    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            one(node, "")
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    one(child, node.name + ".")
    return lowered


#: The callable surface ticket #373 states, verbatim from the ticket. Check [4] requires this file
#: to present every one of these, so existing callers keep working — acceptance item (b).
TICKET_SURFACE = [
    "Why5.__init__(self, session_id: str, db_path: str=None, trigger: str='')",
    "Why5.fact(self, name: str, value: bool)",
    "Why5.link(self, label: str, cause: str, because: str)",
    "Why5.check(self) -> dict",
    "Why5.save(self) -> str | None",
    "Why5._format_text(self) -> str",
    "from_ci_failure(session_id: str, branch: str, pre_sha: str, pytest_output: str, "
    "db_path: str=None) -> Why5",
    "from_commit_failure(session_id: str, agent_name: str, file_path: str, error: str, "
    "db_path: str=None) -> Why5",
]


def _check_surface(out):
    """[4] This file presents the callable surface the ticket states. Acceptance item (b).

    Proven by re-lowering THIS FILE's own AST and comparing, rather than asserted. The ORIGINAL is
    lowered too and required to produce the identical eight lines — which is what proves the
    lowering here is faithful rather than tuned to make this file pass.
    """
    print("[4] the callable surface the ticket states is presented", file=out)
    mine = _lower_callables(_own_source())
    theirs = _lower_callables(ORIGINAL_SOURCE)
    ok = True
    for signature in TICKET_SURFACE:
        ok = _report(out, signature in mine, signature) and ok
    ok = _report(out, sorted(theirs) == sorted(TICKET_SURFACE),
                 "and lowering the ORIGINAL yields exactly those eight, so the lowering is honest",
                 "" if sorted(theirs) == sorted(TICKET_SURFACE)
                 else "original lowers to: %s" % theirs) and ok
    return ok


def _check_restored(out, before_modules, before_env):
    """[5] The selftest put `sys.modules` and the environment back exactly as it found them.

    The fakes are installed by mutating global interpreter state, so proving the restoration is not
    ceremony: a leaked `sys.modules["z3_mcp"]` would silently change what every later import in
    this process resolves to.
    """
    print("[5] the selftest left no fake behind", file=out)
    watched = ("dz_debug", "z3_mcp", "z3_mcp.solver", "notes_db_mcp")
    now = {name: sys.modules.get(name, _MISSING) for name in watched}
    ok = _report(out, now == before_modules, "sys.modules entries for the staged names restored",
                 "" if now == before_modules else "now: %r" % (now,))
    now_env = os.environ.get(CONFIG_ENV)
    ok = _report(out, now_env == before_env, "$%s restored" % CONFIG_ENV,
                 "" if now_env == before_env else "now: %r" % (now_env,)) and ok
    ok = _report(out, not [name for name in sys.modules
                           if name.startswith(("_why5_oracle", "_why5_rewrite"))],
                 "no throwaway oracle/rewrite module left in sys.modules") and ok
    return ok


def _config_literals(node):
    """Collect every string leaf of the config template, recursively — the values check [6] forbids
    appearing as literals in this module's executable code."""
    found = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found |= _config_literals(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            found |= _config_literals(item)
    elif isinstance(node, str):
        found.add(node)
    return found


def _strip_comments(node):
    """Return `node` with every `_comment` key removed, at every depth.

    The registry embeds its documentation inside the objects it describes — this repository's
    idiom — and `config_template()` is code, which carries its documentation in a docstring. So the
    two are compared with the comments taken out.
    """
    if isinstance(node, dict):
        return {key: _strip_comments(value) for key, value in node.items() if key != "_comment"}
    if isinstance(node, list):
        return [_strip_comments(item) for item in node]
    return node


#: The name whose definition marks the end of the UNIT and the start of the proof machinery. Check
#: [6] scans only what comes before it, and proves that boundary is real rather than trusting it.
UNIT_ENDS_AT = "_SelftestFailure"


def _unit_boundary(tree):
    """Return the line where the unit's code ends and the proof machinery begins.

    Check [6] polices THE UNIT — the code that runs when a caller imports this module and builds a
    session. Everything below the boundary is fixtures, drivers and command line, and a fixture is
    REQUIRED to name the things it fakes: the scenario that stages an absent solver has to say
    `z3_mcp.solver`, and the one that pins `sat` has to say `sat`. Scanning them would not be
    stricter, it would be wrong — it would forbid the proof from describing what it proves.

    The boundary is the definition of `UNIT_ENDS_AT`, and `_check_no_hardcoding` proves it means
    what this docstring says by requiring `Why5` and both builders to fall ABOVE it and the
    differential's own entry point to fall below. Without that, a boundary that drifted to the top
    of the file would silently make the check vacuous.
    """
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == UNIT_ENDS_AT:
            return node.lineno
    raise _SelftestFailure(
        "check [6] cannot find %s, the marker that separates the unit from its proof machinery"
        % UNIT_ENDS_AT
    )


def _defined_at(tree, name):
    """Return the line a module-level class or function is defined at, or None."""
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == name:
            return node.lineno
    return None


def _check_no_hardcoding(out):
    """[6] Not one of the original's params survives as a literal in the unit. Acceptance item (d).

    An AST scan, not a text search, so it can tell a literal that DRIVES behavior from one that
    merely names a field. Two positions are excluded and the reason is the same for both: a string
    used as a dict KEY or as a SUBSCRIPT index names a field of a data structure — the result dict
    this unit returns, the solver's reply, a note record — and those are the unit's structure, not
    its configuration (see WHAT IS A SETTING, AND WHAT IS NOT). Renaming one would break a caller,
    which is what this ticket exists to prevent. Everything else in the unit is scanned.

    Two things are excluded wholesale. `config_template()` is the one place the values are allowed,
    because printing them as installable data is the point of it. The `ORIGINAL_SOURCE` assignment
    is the original's own 11716 bytes, which of course contain every literal the original
    hardcoded — that is what makes it the oracle, and check [0] fails loudly if a single byte of it
    ever changes. The scan stops at `_unit_boundary`; see there for why, and for how this check
    proves the boundary is honest.
    """
    print("[6] no hardcoded settings: the original's params exist only as config", file=out)
    template = config_template()
    forbidden = _config_literals(template)
    tree = ast.parse(_own_source())
    boundary = _unit_boundary(tree)

    # Prove the boundary is where this check claims: the whole unit above it, the proof below.
    above = [name for name in ("Why5", "from_ci_failure", "from_commit_failure", "config_template",
                               "settings_from_config", "load_config")
             if (_defined_at(tree, name) or 0) < boundary and _defined_at(tree, name)]
    below = [name for name in ("selftest", "_observe", "_stage_for", "cli")
             if (_defined_at(tree, name) or 0) > boundary]
    ok = _report(out, len(above) == 6 and len(below) == 4,
                 "the scan covers the unit: %s above the line, %s below it"
                 % (", ".join(above), ", ".join(below)),
                 "" if len(above) == 6 and len(below) == 4 else "boundary at line %d is wrong"
                 % boundary)

    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "config_template":
            skip |= {id(child) for child in ast.walk(node)}
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "ORIGINAL_SOURCE"
                for target in node.targets):
            skip |= {id(child) for child in ast.walk(node)}
        # A docstring or any other bare string statement is documentation, not behavior.
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            skip.add(id(node.value))
        # Structure, not configuration: these name fields, they do not carry values.
        if isinstance(node, ast.Dict):
            skip |= {id(key) for key in node.keys if key is not None}
        if isinstance(node, ast.Subscript):
            skip |= {id(child) for child in ast.walk(node.slice)}

    offenders = sorted({
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.lineno < boundary and id(node) not in skip and node.value in forbidden
    })
    ok = _report(out, not offenders,
                 "none of the %d configured values appears as a literal in the unit's code"
                 % len(forbidden),
                 "" if not offenders else "found: %r" % (offenders,)) and ok

    shipped = _strip_comments(shipped_config())
    shipped.pop("bug_reports", None)
    wanted = dict(template)
    wanted.pop("bug_reports", None)
    ok = _report(out, shipped == wanted,
                 "and `emit-config` prints exactly the section registry.json ships, so the "
                 "template IS the running config") and ok
    if shipped != wanted:
        print("        template: %s" % json.dumps(wanted, sort_keys=True)[:400], file=out)
        print("        shipped : %s" % json.dumps(shipped, sort_keys=True)[:400], file=out)
    return ok


def _snapshot(root):
    """Hash every committed source file under `root`, for a before/after comparison.

    Build artifacts are skipped, and ONLY those: ticket #373 names `__pycache__`, `*.egg-info/`,
    `build/` and `dist/` as "regenerated by any install" and never committed, `.gitignore` excludes
    them, and `install-check` legitimately creates them. What is being proven is that the SOURCE
    tree is untouched.
    """
    skip = ("__pycache__", "build", "dist", ".git", "logs")
    found = {}
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [name for name in subdirectories
                             if name not in skip and not name.endswith(".egg-info")]
        for name in files:
            path = os.path.join(directory, name)
            with open(path, "rb") as handle:
                found[os.path.relpath(path, root)] = hashlib.sha256(handle.read()).hexdigest()
    return found


def _check_tree(out, before, root):
    """[7] The whole selftest changed no file in this package."""
    print("[7] the selftest wrote nothing into this package", file=out)
    after = _snapshot(root)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(name for name in set(before) & set(after) if before[name] != after[name])
    ok = _report(out, not (added or removed or changed),
                 "%d source files, all byte-identical before and after" % len(before),
                 "" if not (added or removed or changed)
                 else "added=%r removed=%r changed=%r" % (added, removed, changed))
    return ok


def selftest(out=None):
    """Run every check and return True if all passed.

    The checks in order: [0] the embedded original is genuine, [1] the config gate throws, [2] the
    exemplars match the original, [3] the edge cases match the original, [4] the ticket's callable
    surface is presented, [5] no fake leaked, [6] nothing is hardcoded, [7] no file was touched.
    """
    out = out or sys.stdout
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    before_modules = {name: sys.modules.get(name, _MISSING)
                      for name in ("dz_debug", "z3_mcp", "z3_mcp.solver", "notes_db_mcp")}
    before_env = os.environ.get(CONFIG_ENV)
    before_tree = _snapshot(root)

    print("selftest for %s (ticket #%d)" % (UNIT, TICKET), file=out)
    print("proving this rewrite against the ORIGINAL it embeds, which check [0] proves is the "
          "forge blob\n", file=out)

    results = [_check_original(out)]
    print("", file=out)

    with tempfile.TemporaryDirectory() as tmp:
        config_path = os.path.join(tmp, "why5-config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(shipped_config(), handle)

        results.append(_check_gate(out, root))
        print("", file=out)
        results.append(_check_differential(
            out, "[2] the exemplars: this rewrite vs the ORIGINAL, same fakes, same drivers",
            EXEMPLARS, config_path))
        print("", file=out)
        results.append(_check_differential(
            out, "[3] the edge cases sampling cannot reach: same differential",
            EDGE_CASES, config_path))
        print("", file=out)

    results.append(_check_surface(out))
    print("", file=out)
    results.append(_check_restored(out, before_modules, before_env))
    print("", file=out)
    results.append(_check_no_hardcoding(out))
    print("", file=out)
    results.append(_check_tree(out, before_tree, root))

    ok = all(results)
    print("\n%s — %d/%d check groups passed"
          % ("ALL PASS" if ok else "FAILED", sum(1 for r in results if r), len(results)), file=out)
    return ok


# ─────────────────────────────── install-check ───────────────────────────────

def install_check(out=None):
    """Really install this package with pip, twice, and import this unit out of each result.

    Acceptance item (c) says `pip install -e .` must install this package clean from its own
    pyproject.toml. This EXECUTES that claim rather than asserting it:

      1. `pip install -e . --prefix <tmp>` — the editable layout item (c) names — then imports
         `coupler.why5` from it in a child interpreter.
      2. `pip install . --target <tmp>` — the NON-editable layout — then imports it under
         `python3 -S`, so no real site-packages can answer for it and only what pip actually copied
         is on the path. This is the layout that proves `find_registry`'s installed-registry
         fallback does its job, and the one where the sibling's gate has to be opened with
         `$COUPLER_CONFIG` (see ONE HONEST LIMIT).

    Both temporary trees are removed afterwards. Nothing is installed into the running interpreter.
    This is the only command that reaches the network, and only if pip needs a build backend it has
    not cached; see SIDE EFFECTS for the `build/` and `*.egg-info/` scaffolding it leaves behind.
    """
    out = out or sys.stdout
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print("install-check for %s (ticket #%d)" % (UNIT, TICKET), file=out)
    print("package root: %s\n" % root, file=out)
    ok = True

    # ── 1. the editable install acceptance item (c) names ──
    print("[a] pip install -e . --prefix <tmp>", file=out)
    with tempfile.TemporaryDirectory() as tmp:
        done = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", ".", "--prefix", tmp, "--no-input"],
            cwd=root, capture_output=True, text=True,
        )
        ok = _report(out, done.returncode == 0, "pip install -e . succeeds",
                     "exit %d%s" % (done.returncode,
                                    "" if done.returncode == 0 else "\n" + done.stderr[-800:]))
        if done.returncode == 0:
            site = _site_dir(tmp)
            probe = ("import coupler.why5 as w; "
                     "print('COLLECTION', w.COLLECTION); print('surface', "
                     "all(hasattr(w, n) for n in ('Why5','from_ci_failure','from_commit_failure')))")
            imported = subprocess.run(
                [sys.executable, "-c", probe], cwd=tempfile.gettempdir(), capture_output=True,
                text=True, env=dict(os.environ, PYTHONPATH=site),
            )
            ok = _report(out, imported.returncode == 0 and "surface True" in imported.stdout,
                         "and `import coupler.why5` resolves out of it, from an unrelated cwd",
                         imported.stdout.strip().replace("\n", " | ")
                         or imported.stderr.strip()[-300:]) and ok

    # ── 2. the non-editable install, isolated from every real site-packages ──
    print("\n[b] pip install . --target <tmp>, imported under python3 -S", file=out)
    with tempfile.TemporaryDirectory() as tmp:
        done = subprocess.run(
            [sys.executable, "-m", "pip", "install", ".", "--target", tmp, "--no-input"],
            cwd=root, capture_output=True, text=True,
        )
        ok = _report(out, done.returncode == 0, "pip install . succeeds",
                     "exit %d%s" % (done.returncode,
                                    "" if done.returncode == 0 else "\n" + done.stderr[-800:])) and ok
        if done.returncode == 0:
            ok = _report(out, os.path.isfile(os.path.join(tmp, "coupler", "why5.py")),
                         "the corrected pyproject.toml actually ships coupler/why5.py") and ok
            ok = _report(out, os.path.isfile(os.path.join(tmp, REGISTRY_NAME)),
                         "and ships %s as package data, which is what the installed-registry "
                         "fallback finds" % REGISTRY_NAME) and ok

            # The sibling coupler/__init__.py (#397) gates at import with no installed-registry
            # fallback of its own, so its own documented escape hatch is used to get past it. That
            # gap is #397's; see ONE HONEST LIMIT. This proves THIS module's fallback, which is the
            # only thing #373 is allowed to touch.
            sibling_config = os.path.join(tmp, "sibling.json")
            document = _read_json(os.path.join(tmp, REGISTRY_NAME), "the installed registry")
            node = document
            for key in UNIT_PATH[:-1] + (SIBLING_PACKAGE,):
                node = node[key]
            with open(sibling_config, "w", encoding="utf-8") as handle:
                json.dump(node, handle)

            env = {key: value for key, value in os.environ.items()
                   if key not in (CONFIG_ENV, "PYTHONPATH")}
            env[SIBLING_CONFIG_ENV] = sibling_config
            env["PYTHONPATH"] = tmp
            imported = subprocess.run(
                [sys.executable, "-S", "-c",
                 "import coupler.why5 as w; print('SOURCE', w.active_source())"],
                cwd=tempfile.gettempdir(), capture_output=True, text=True, env=env,
            )
            ok = _report(out, imported.returncode == 0 and tmp in imported.stdout,
                         "and `import coupler.why5` resolves its config from the INSTALLED "
                         "registry, with no checkout in reach",
                         imported.stdout.strip() or imported.stderr.strip()[-400:]) and ok

            # And removing that installed registry brings the gate back — proving the fallback is
            # what answered above, rather than something else on the path.
            os.remove(os.path.join(tmp, REGISTRY_NAME))
            gated = subprocess.run(
                [sys.executable, "-S", "-c", "import coupler.why5"],
                cwd=tempfile.gettempdir(), capture_output=True, text=True, env=env,
            )
            ok = _report(out, gated.returncode != 0 and "ConfigError" in gated.stderr,
                         "and deleting that registry brings the ConfigError gate straight back",
                         "exit %d" % gated.returncode) and ok

    print("\n%s" % ("ALL PASS" if ok else "FAILED"), file=out)
    return ok


def _site_dir(prefix):
    """Return the site-packages directory `pip install --prefix <prefix>` wrote into.

    The path embeds the interpreter's version (`lib/python3.14/site-packages`), so it is discovered
    rather than assembled from a guess about the layout.
    """
    for directory, subdirectories, _files in os.walk(prefix):
        if os.path.basename(directory) == "site-packages":
            return directory
        subdirectories[:] = sorted(subdirectories)
    return os.path.join(prefix, "lib", "site-packages")


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, command):
    """Append one timestamped JSON line about an UNEXPECTED exception to the config's sink.

    `note-for-claude`'s rule: "all tools need to pass a bug-report automatically (timestamped if an
    exception is thrown)". A bug report means "this tool is broken", so the two exceptions that are
    DESIGNED behavior — `ConfigError` and `UsageError` — never reach here. Best-effort by
    construction: if the sink cannot be written, the original exception is still reported to the
    user, and a failure to file must never replace it.
    """
    try:
        config = active_config()
        if "bug_reports" not in config:
            return None
        path = config["bug_reports"]
        if not isinstance(path, str) or not path:
            return None
        if not os.path.isabs(path):
            path = os.path.join(active_base(), path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ticket": TICKET,
                "unit": UNIT,
                "command": command,
                "error": "%s: %s" % (type(exc).__name__, exc),
                "traceback": traceback.format_exc(),
            }) + "\n")
        return path
    except Exception:  # noqa: BLE001 — filing a report must never mask the error being reported
        return None


def _build_parser():
    """Build the argument parser. Every command's help is its own explanation."""
    parser = argparse.ArgumentParser(
        prog=_cli_name(),
        description=("why5 — verified root cause analysis via Z3. A behavior-preserving, "
                     "installable, control-config'd rewrite of the forge unit "
                     "code__code-invalid__coupler:coupler/why5.py (ticket #%d, standard #200)."
                     % TICKET),
        epilog=("This unit is driven by a config object and throws rather than guessing one: see "
                "`show-config` for the one in force and `emit-config` for a template. "
                "`selftest` proves this rewrite against the ORIGINAL, which it embeds."),
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("selftest", help="prove this rewrite against the ORIGINAL it embeds")
    sub.add_parser("install-check", help="really run pip, in both install layouts")
    sub.add_parser("show-config", help="print the config object in force and where it came from")
    sub.add_parser("emit-config", help="print a config-object template to fill in and install")

    ci = sub.add_parser("ci", help="build and check a why5 chain from CI pytest output")
    ci.add_argument("--session", required=True, help="session id")
    ci.add_argument("--branch", required=True, help="the branch CI failed on")
    ci.add_argument("--sha", required=True, help="the pre-failure sha (clamped, as the unit does)")
    source = ci.add_mutually_exclusive_group(required=True)
    source.add_argument("--pytest-output-file", help="file holding the pytest output")
    source.add_argument("--pytest-output", help="the pytest output itself")

    commit = sub.add_parser("commit", help="build and check a why5 chain from a failed commit")
    commit.add_argument("--session", required=True, help="session id")
    commit.add_argument("--agent", required=True, help="the agent that failed to commit")
    commit.add_argument("--file", required=True, help="the file it failed to commit")
    commit.add_argument("--error", required=True, help="the error text git produced")

    for command in (ci, commit):
        command.add_argument("--db-path", help="notes-db path; without it --save does nothing, "
                                               "exactly as the unit's own gate has it")
        command.add_argument("--save", action="store_true",
                             help="write the verdict to notes-db (the only flag that writes)")
    return parser


def _print_session(w, save, out):
    """Check a session, print its result JSON and its rendered body, and optionally save it."""
    result = w.check()
    print(json.dumps(result, indent=2, default=str), file=out)
    print("", file=out)
    print(w._format_text(), file=out)
    if save:
        note_id = w.save()
        print("\nsaved: %s" % (note_id if note_id is not None else
                               "(nothing — see the log line above; save() swallows every failure "
                               "and returns None, as the original did)"), file=out)
    return 0


def cli(argv=None, out=None):
    """Run one command. Returns the process exit code.

    Exit codes: 0 success, 2 a ConfigError or UsageError (one self-explaining line, no traceback,
    no bug report — both are designed behavior), 1 an unexpected exception (traceback plus a filed
    bug report — that means this tool is broken).

    Note that the config gate fires at IMPORT, before this function exists, so an unresolvable
    config never reaches here — it exits 1 with a ConfigError traceback. See HOW A ConfigError
    ACTUALLY SURFACES. The ConfigError arm below is the safety net for one raised mid-command.
    """
    out = out or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(out)
        return 0

    try:
        if args.command == "selftest":
            return 0 if selftest(out) else 1
        if args.command == "install-check":
            return 0 if install_check(out) else 1
        if args.command == "emit-config":
            print(json.dumps(config_template(), indent=2, ensure_ascii=False), file=out)
            return 0
        if args.command == "show-config":
            print("# config object in force for %s" % UNIT, file=out)
            print("# source: %s" % active_source(), file=out)
            print(json.dumps(active_config(), indent=2, ensure_ascii=False), file=out)
            return 0
        if args.command == "ci":
            if args.pytest_output_file:
                try:
                    with open(args.pytest_output_file, "r", encoding="utf-8") as handle:
                        output = handle.read()
                except OSError as exc:
                    raise UsageError(
                        "--pytest-output-file %r could not be read: %s"
                        % (args.pytest_output_file, exc)
                    ) from exc
            else:
                output = args.pytest_output
            return _print_session(
                from_ci_failure(args.session, branch=args.branch, pre_sha=args.sha,
                                pytest_output=output, db_path=args.db_path),
                args.save, out)
        if args.command == "commit":
            return _print_session(
                from_commit_failure(args.session, agent_name=args.agent, file_path=args.file,
                                    error=args.error, db_path=args.db_path),
                args.save, out)
        # Defensive: argparse's subparsers already reject an unknown command, so this is reachable
        # only if a command is added to the parser without a handler here. Better a clear line than
        # a silent `return None`.
        raise UsageError("unknown command %r" % args.command)
    except (ConfigError, UsageError) as exc:
        # Designed behavior, not a defect: one line, no traceback, no bug report.
        print("%s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 2
    except _SelftestFailure as exc:
        print("selftest aborted: %s" % exc, file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — this IS the unexpected-exception path
        traceback.print_exc()
        filed = _bug_report(exc, args.command)
        if filed:
            print("a bug report was filed at %s" % filed, file=sys.stderr)
        return 1


def main():
    """Console-script entry point. See RUNNING IT in the module docstring."""
    sys.exit(cli())


if __name__ == "__main__":
    main()
