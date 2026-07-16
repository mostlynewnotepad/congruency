#!/usr/bin/env python3
"""forge2 / agent_tools_suite / crank_discipline — a behavior-preserving rewrite of the forge unit
`agent_tools_suite:crank_discipline.py` (module key forge-rw:d10d74a9bac32554, git blob
08bc6bba086630d09f1cf36a0f77f01de22a453c, 4790 bytes), filed under ticket #419 against the
FORGE-wide refactor standard #200.

WHAT THIS IS
------------
The original unit is the gate every "crank" routes through. A CRANK is a versioned, tagged state
change; the original's own docstring calls this module "the single, inescapable gate every crank
routes through", imported by every repo's ratchet as a HARD DEPENDENCY. It allows a crank only when

  1. an OPEN memory ticket exists for the component   -> else `CrankRefused`;
  2. its intent + provenance is recorded              -> to a local log, and to congruency;
  3. its patch runs CONFINED under the audit-veto     -> a separate program, `audit_guard`.

This file is an ENTIRELY NEW implementation of that unit. It keeps the original's observable
behavior and its callable surface, and adds the three things #200 requires that the original
lacked: it is a proper installable package, it is driven by a configuration object, and it REFUSES
to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    _now()                                      -> str    UTC timestamp, ISO-8601
    _congruency(method, path, payload=None)     -> obj    one JSON request to congruency
    has_open_ticket(component)                  -> bool   is there an OPEN ticket? (raises OSError)
    record(component, intent, session)          -> dict   the provenance stamp
    gate(component, intent, session=None, require_ticket=True) -> dict   the precondition
    run_confined(patch, repo_root, timeout=300) -> list   run a patch under the audit-veto

`CrankRefused` (the refusal exception) is part of the contract too: callers catch it, and it is
what every precondition failure raises.

Every name, parameter and default above is the original's, verified by `selftest` against
`inspect.signature` — including `timeout=300`, on which see THE `timeout` DEFAULT below.

TERMS USED HERE
---------------
crank
    A versioned, tagged state change. The thing this module gates.
component
    The subsystem a crank targets ("workstation", "congruency", ...). It is the key the OPEN-ticket
    query is filtered by.
congruency
    The HTTP service holding tickets and memories. Reached over plain JSON at a base URL; see
    CONFIGURATION. When it is DOWN, this module degrades — that is a designed behavior, not a bug,
    and it is spelled out under THE OUTAGE RULE.
provenance stamp
    The dict `record()` writes and returns: `{"ts", "kind", "component", "intent", "session"}`, in
    that key order. It is appended as one JSON line to the provenance log and POSTed to congruency.
audit-veto / audit_guard
    A SEPARATE program that runs an untrusted crank patch under a runtime veto and exits non-zero
    if the patch tries to escape. This module treats it as an OPAQUE subprocess — it runs it and
    reads its exit code, exactly as the original did. See THE GUARD IS OPAQUE.
crank patch
    The untrusted Python file the audit-veto runs.
registry / config object
    The JSON configuration registry described in this repository's `note-for-claude`: one `.json`
    file holding the configuration for every tool in a set of packaging. `note-for-claude` states
    the contract this module obeys — "if a tool cannot see the registry it will throw an exeption"
    [sic]. The "config object" is this unit's own `forge2.agent_tools_suite.crank_discipline`
    section of it. THIS package ships a `registry.json` beside this file; see CONFIGURATION.
policy
    The config object, resolved and compiled into the concrete URL, paths and numbers the surface
    consults. Built once, then cached; `show-policy` prints it. See THE POLICY IS FROZEN.

THE OUTAGE RULE (the original's central asymmetry — preserved exactly)
----------------------------------------------------------------------
The three preconditions are NOT equally hard, and the difference is deliberate:

  * The TICKET is hard only when congruency is REACHABLE. `has_open_ticket` RAISES `OSError` when
    congruency is down, and `gate` catches that and PROCEEDS. This is what lets the gate tell "up,
    but no ticket" (refuse) apart from "down" (proceed best-effort). A gate that refused on an
    outage would make every repo's ratchet unusable whenever the service blinked.
  * PROVENANCE never refuses. `record` swallows `OSError` from BOTH sinks and always returns the
    stamp. It degrades to the local log, then to nothing.
  * CONFINEMENT is always hard, independent of congruency: `run_confined` raises `CrankRefused` on
    any non-zero exit from the guard, and there is no outage that softens it.

`OSError` is the exact class the original catches, and it is the right one: `urllib`'s `URLError`
and `HTTPError` are both subclasses of it, so a connection refusal, a DNS failure, a timeout and an
HTTP 500 all read as "congruency is not answering". `CrankRefused` is a `RuntimeError`, NOT an
`OSError`, so the refusal `gate` raises INSIDE that `try` is not swallowed by its own `except
OSError`. That is load-bearing, it is easy to break in a rewrite, and `selftest` pins it.

WHAT DOES *NOT* DEGRADE, AND WHY THAT IS ALSO PRESERVED
-------------------------------------------------------
Only `OSError` is caught. A response that is not JSON, or that is JSON but not an object, is NOT an
outage — it means something is answering on the congruency URL that is not congruency — and the
original lets those surface:

  * a 200 with a non-JSON body   -> `json.loads` raises `ValueError`, which escapes `record` and
                                    `gate` untouched;
  * a 200 whose body is a JSON list -> `has_open_ticket` calls `.get` on a list and raises
                                    `AttributeError`.

Both are reproduced here, and `selftest` pins both. A rewrite that "helpfully" caught them would be
strictly more forgiving than the module it replaces, and would let a crank through on a garbage
response that the original stops.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
Every path, URL, environment-variable name, query string and number the original hardcoded is now a
config key. The unit resolves its config object from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. This file holds the unit config
     object itself — exactly what `emit-config` prints.
  2. otherwise, the `forge2.agent_tools_suite.crank_discipline` section of the nearest
     `registry.json` found by walking UP from THIS FILE's directory.

If NEITHER answers, the unit raises `ConfigError` and gates nothing — it never guesses a default.
That is `note-for-claude`'s rule and this ticket's acceptance item (d). A config object that is
found but is missing a key an operation needs is also a `ConfigError`, naming the key.

This package ships `registry.json` NEXT TO this file, so source 2 answers and the gate works from a
clean checkout with no setup. That shipped registry is the config object this unit runs on; it is
not a fallback baked into the code. Its values are exactly the original's hardcoded ones, which is
what makes this rewrite behavior-preserving in its shipped configuration. Delete it (with
`FORGE2_CONFIG` unset and no other `registry.json` above this directory) and the unit throws — the
gate is in the code, not in the file's presence. `selftest` proves the gate directly, without
deleting anything, by pointing `FORGE2_CONFIG` at a file that does not exist.

The config keys, and the original's value for each:

    url_env          "CONGRUENCY_URL"   env var naming congruency's base URL; empty/unset -> below
    congruency_url   "http://127.0.0.1:8899"
                     The base URL used when `url_env` is empty or unset. The resolved URL has its
                     trailing "/" stripped, as the original's `.rstrip("/")` did.
    http_timeout     3                  seconds, per congruency request
    tickets_query    "/?api=tickets&component={component}&status=OPEN&order=id.desc&per=1"
                     The OPEN-ticket query. `{component}` is substituted; see NOT URL-ENCODED.
    memories_path    "/?api=memories"   where `record` POSTs the stamp
    content_type     "application/json" the Content-Type header on every request
    provenance_log   "~/bin/config/crank/provenance.jsonl"
                     The local jail log. `~` expands; `${here}` is this file's directory and
                     `${base}` the config's directory; a relative path resolves against `${base}`.
    stamp_kind       "crank"            the stamp's "kind" field
    session_env      "CLAUDE_CODE_SESSION_ID"   env var naming the session; read at CALL time
    session_prefix   "crank-"           prefix for the fallback session id, `crank-<pid>`
    guard_path       "${here}/audit_guard.py"
                     The audit-veto program. `${here}` reproduces the original's `HERE` exactly:
                     the guard that sits NEXT TO this module. Same expansions as provenance_log.
    repo_env         "CRANK_REPO"       env var the guard's build repo is passed in
    confine_env      {"PYTHONDONTWRITEBYTECODE": "1"}
                     Extra environment for the guard subprocess, merged over the inherited env
                     AFTER `repo_env`.
    confine_env_drop ["FORGE2_CONFIG"]  Environment names REMOVED from the guard subprocess. See
                     WHY `confine_env_drop` DEFAULTS TO `FORGE2_CONFIG` — it is not a nicety.
    confine_timeout  300                seconds, for the guard subprocess; see THE `timeout` DEFAULT
    error_tail       400                chars of the guard's output kept in the refusal message
    stdout_tail      3                  lines of the guard's stdout returned on success
    bug_reports      "logs/bug_reports.jsonl"
                     Where an UNEXPECTED exception is reported, per `note-for-claude`. Inherited
                     from the registry's top level if the section does not state it.

`error_tail` and `stdout_tail` must be >= 1. They are used as `[-n:]`, and `[-0:]` is the WHOLE
string/list, not an empty one — a `0` would silently mean "no limit" and is rejected as a
`ConfigError` rather than honored as a trap.

WHY `confine_env_drop` DEFAULTS TO `FORGE2_CONFIG`
--------------------------------------------------
Every unit in this package — this one, `audit_guard`, `ats_http`, `ats_service` — reads its config
object from the SAME environment variable, `FORGE2_CONFIG`, and each expects that file to hold ITS
OWN config object. This module is the only unit that SPAWNS a sibling. The original passed its
whole environment to the guard (`env = {**os.environ, ...}`), and in the original's world that was
harmless because `FORGE2_CONFIG` did not exist.

It exists now. So if an operator points `FORGE2_CONFIG` at THIS unit's config object and calls
`run_confined`, a naive passthrough hands the guard a file full of crank_discipline's keys as if it
were the guard's own config — and the guard, correctly, refuses to start. `run_confined` would then
report the patch as refused under the veto when in truth the veto never ran. Dropping
`FORGE2_CONFIG` from the child's environment is what makes the guard resolve ITS OWN config from
the registry, which is precisely the environment the original's guard was launched into. The drop
is therefore behavior-PRESERVING, not an improvement: it reproduces the original's child
environment exactly. It is config, so an operator who really does want passthrough sets
`confine_env_drop` to `[]`. The drop is applied LAST, so a name in both `confine_env` and
`confine_env_drop` is dropped.

THE GUARD IS OPAQUE
-------------------
`run_confined` runs the guard and reads its EXIT CODE. It does not import it, know its flags, or
interpret its output beyond the tail. That is exactly what the original did, and it is why this
module is correct no matter what state the guard is in: any non-zero exit is `CrankRefused`.

Concretely, and stated plainly because a reader will meet it: the `audit_guard.py` shipped beside
this file currently exits 4 ("config error: the registry ... is missing the
'forge2.agent_tools_suite.audit_guard' section") because the shipped `registry.json` carries no
section for it. That is ticket #415's business, not this ticket's — #419 may add ONLY its own
`forge2.agent_tools_suite.crank_discipline` section and must never author a sibling's. The effect
here is well-defined and is the ORIGINAL's behavior for a guard that exits non-zero for any reason:
`run_confined` raises `CrankRefused` naming `rc=4`. `selftest` runs the REAL guard and pins that,
and separately proves the rc=0 path against a guard that exits 0, so both branches are evidenced.

NOT URL-ENCODED (a preserved sharp edge)
----------------------------------------
The original interpolated `component` into the query with an f-string and no quoting, so a
component containing `&` or `=` changes the query's meaning. This rewrite substitutes the same way
and does NOT add encoding. Adding `urllib.parse.quote` would be a BEHAVIOR CHANGE — a different
URL for the same input, i.e. a different set of tickets found — and #200 asks for a rewrite that
reproduces the original, not one that fixes it. `selftest` pins the un-encoded form.

THE POLICY IS FROZEN — AND THE ONE DEVIATION
--------------------------------------------
The original read `CONGRUENCY_URL` ONCE, at IMPORT, into a module constant that never moved again.
This rewrite cannot read its config at import: a missing config must THROW, and a module that
throws at import cannot present a callable surface at all — every ratchet's `import
crank_discipline` would die instead of its `gate()` call. So the policy is resolved on FIRST USE
and then CACHED, and every later call reads the cache.

The property the original had — resolve the URL once, then freeze — is therefore preserved, and
`selftest` proves the freeze (change `CONGRUENCY_URL` after a call; the URL does not move). The
DEVIATION is the INSTANT of the snapshot: import for the original, first use here. It is observable
only by a caller that mutates `os.environ["CONGRUENCY_URL"]` between importing this module and its
first crank — and for the real caller, a ratchet whose environment is set before the process
starts, the two instants are the same. `reset_config()` re-resolves on purpose, which is strictly
more control than the original offered; nothing is taken away.

`session_env` is NOT part of that snapshot: the original read `CLAUDE_CODE_SESSION_ID` inside
`gate`, at CALL time, and so does this. Only the NAME comes from the frozen policy.

WHAT IS *NOT* CONFIG, AND WHY
-----------------------------
The refusal MESSAGES are not config. They are the original's exact words, and callers and logs read
them; a config key would invite them to drift from the module they identify. The stamp's KEY ORDER
is not config either — it is the original's `{"ts", "kind", "component", "intent", "session"}`, and
it is what the provenance JSON line looks like byte for byte. `_now()`'s format is not config: it
is `datetime.now(timezone.utc).isoformat()`, the original's, and a stamp whose `ts` did not parse
as that would break every reader of the log.

THE `timeout` DEFAULT
---------------------
The surface freezes `run_confined(patch, repo_root, timeout=300)`, so `300` must remain the default
a caller and `inspect.signature` both see. #200 requirement 4 says no hardcoded params. Both hold
here: the default is `DEFAULT_TIMEOUT`, an `int` subclass equal to `300` (so `inspect.signature`
renders `timeout=300` and every comparison against `300` is true), whose IDENTITY means "the caller
said nothing". When the caller says nothing, `confine_timeout` from the config decides; when the
caller passes a timeout — including a literal `300` — that value is used verbatim. There is no
ambiguity: an explicitly passed `300` is a plain `int` and is never the sentinel. `selftest` pins
the signature, the equality and both branches.

RUNNING IT
----------
As a library, exactly as the original documented itself:

    import crank_discipline as discipline
    discipline.gate(component="workstation", intent=message)   # ticket + provenance, or raise
    discipline.run_confined(patch, repo_root)                  # the audit-veto

As a package (this is #200 requirement 3 — `pip install -e .` from this directory):

    from agent_tools_suite.crank_discipline import gate, run_confined, CrankRefused

As a CLI, via the generated console script `forge2-crank-discipline`, or `python3
crank_discipline.py`:

    gate --component C --intent I [--session S] [--no-require-ticket]
    record --component C --intent I --session S
    has-open-ticket --component C
    run-confined --patch P --repo R [--timeout N]
    show-config | show-policy | emit-config | selftest

    0  ok      2  usage      3  refused (CrankRefused)      4  no config object

`emit-config` prints this unit's config-object template — the original's values — for an operator
to install. `selftest` runs the equivalence exemplars described below and prints one line per check.

THE EXEMPLARS
-------------
The ticket captured NO behavioral exemplars for this module: `criteria_miner` mines only
self-contained pure functions, and every function here touches the world (the network, the clock,
the filesystem, a subprocess). #200's bar does not move because of that — it MOVES the work onto
this file. `selftest` is that work: it runs each function against a REAL ephemeral congruency (an
`http.server` on 127.0.0.1 answering canned JSON) and REAL guard subprocesses, under a redirected
`HOME` so it writes nothing outside its own temporary directory, and checks each observable the
original defines — including the ones that hurt: the un-encoded query, the `AttributeError` on a
JSON list, the `ValueError` on a non-JSON body, `CrankRefused` surviving `except OSError`, the
`[-400:]` tail, the empty-stdout `[]`, the frozen URL, and — with a guard that writes BOTH streams,
the only way to see it — that the refusal quotes stderr and not stdout.
"""
import argparse
import contextlib
import json
import os
import subprocess
import sys
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone

__all__ = [
    # the original's surface
    "CrankRefused", "_now", "_congruency", "has_open_ticket", "record", "gate", "run_confined",
    # the config layer (#200 requirement 4)
    "ConfigError", "load_config", "configure", "using_config", "reset_config", "config_template",
    "active_config", "active_source", "active_base", "active_policy", "build_policy",
    "find_registry", "DEFAULT_TIMEOUT", "Policy",
    # the package surface
    "main", "selftest",
]

#: This file's directory. The original's `HERE`, and what `${here}` expands to in config paths.
HERE = os.path.dirname(os.path.abspath(__file__))

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: Where this unit's config object lives inside the registry. This is the unit's own ADDRESS in the
#: config document, not a configurable setting — a config-driven tool has to know which section is
#: its own.
UNIT_PATH = ("forge2", "agent_tools_suite", "crank_discipline")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:agent_tools_suite/crank_discipline"

#: Exit codes for the CLI. The original had no CLI; these mirror the sibling units'.
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_REFUSED = 3
EXIT_NO_CONFIG = 4


class CrankRefused(RuntimeError):
    """A crank precondition was not met — the crank is refused before it can change state.

    The original's exception, with the original's meaning and (being a `RuntimeError`) the original's
    place in the class hierarchy. That it is NOT an `OSError` is load-bearing: `gate` raises it from
    inside a `try/except OSError` that must not swallow it.
    """


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that cannot
    see its config throws rather than guessing a default. It is NOT a `CrankRefused`: no crank was
    refused, because no crank was ever gated.
    """


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None      # config object injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution
_POLICY = None      # the compiled policy, cached: see THE POLICY IS FROZEN


def find_registry(start=None):
    """Walk UP from `start` (default: this file's directory) and return the nearest registry path,
    or None if the walk reaches the filesystem root without finding one.

    Starting at THIS FILE, never at the working directory, is deliberate: a ratchet's crank policy
    must not change because the ratchet was invoked from somewhere else. `registry.json` ships as
    package-data, so on a non-editable install it sits in this same directory and the first
    iteration finds it.
    """
    directory = os.path.abspath(start or HERE)
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
            % (UNIT, CONFIG_ENV, REGISTRY_NAME, os.path.abspath(start or HERE)))

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
    disk. The compiled policy is dropped, so the next use recompiles.
    """
    global _ACTIVE, _POLICY
    previous = _ACTIVE
    if config is None:
        _ACTIVE = None
    else:
        if not isinstance(config, dict):
            raise ConfigError("a config object must be a dict, not %s" % type(config).__name__)
        _ACTIVE = (config, base or os.getcwd(), source)
    _POLICY = None
    return previous


@contextlib.contextmanager
def using_config(config, base=None):
    """Use `config` as the config object for the duration of the `with` block."""
    previous = configure(config, base=base)
    try:
        yield config
    finally:
        global _ACTIVE, _POLICY
        _ACTIVE = previous
        _POLICY = None


def reset_config():
    """Drop the injected config, the cached disk resolution and the compiled policy.

    The next use re-resolves from disk and re-reads `url_env` from the environment. This is the
    deliberate escape from the freeze described in THE POLICY IS FROZEN.
    """
    global _ACTIVE, _RESOLVED, _POLICY
    _ACTIVE = None
    _RESOLVED = None
    _POLICY = None


def config_template():
    """Return a template of this unit's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless an
    operator installs it, and until they do the unit throws. The values are the ORIGINAL unit's
    hardcoded ones, so a registry built from this template makes this rewrite behave exactly like
    the module it replaces.
    """
    return {
        "url_env": "CONGRUENCY_URL",
        "congruency_url": "http://127.0.0.1:8899",
        "http_timeout": 3,
        "tickets_query": "/?api=tickets&component={component}&status=OPEN&order=id.desc&per=1",
        "memories_path": "/?api=memories",
        "content_type": "application/json",
        "provenance_log": "~/bin/config/crank/provenance.jsonl",
        "stamp_kind": "crank",
        "session_env": "CLAUDE_CODE_SESSION_ID",
        "session_prefix": "crank-",
        "guard_path": "${here}/audit_guard.py",
        "repo_env": "CRANK_REPO",
        "confine_env": {"PYTHONDONTWRITEBYTECODE": "1"},
        "confine_env_drop": [CONFIG_ENV],
        "confine_timeout": 300,
        "error_tail": 400,
        "stdout_tail": 3,
        "bug_reports": "logs/bug_reports.jsonl",
    }


# ─────────────────────────────── the compiled policy ───────────────────────────────

class _SurfaceDefault(int):
    """An `int` that is `300` to everyone, but whose IDENTITY says "the caller passed nothing".

    See THE `timeout` DEFAULT. `int` subclassing is what lets `inspect.signature(run_confined)`
    render `timeout=300` — the surface the ticket freezes — while `run_confined` can still tell an
    absent argument from an explicit one and let the config decide the former.
    """
    __slots__ = ()


#: The `run_confined` surface default: equal to 300, identity-distinct from a caller's 300.
DEFAULT_TIMEOUT = _SurfaceDefault(300)


class Policy:
    """The config object compiled into the concrete values the surface uses. `show-policy` prints
    it; `_congruency`, `gate`, `record` and `run_confined` read it and never touch the disk for
    config themselves."""
    __slots__ = ("congruency", "url_env", "http_timeout", "tickets_query", "memories_path",
                 "content_type", "provenance_log", "stamp_kind", "session_env", "session_prefix",
                 "guard", "repo_env", "confine_env", "confine_env_drop", "confine_timeout",
                 "error_tail", "stdout_tail")

    def as_dict(self):
        return {name: getattr(self, name) for name in self.__slots__}


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


def _require_positive(config, key, what):
    """Return `config[key]` as a number > 0. `bool` is rejected: `True` is an `int` in Python, and a
    timeout of `True` (one second) is never what an operator meant."""
    value = _require(config, key, (int, float), what)
    if isinstance(value, bool) or value <= 0:
        raise ConfigError("config key %r for %s must be a number greater than 0, not %r"
                          % (key, UNIT, value))
    return value


def _require_tail(config, key, what):
    """Return `config[key]` as an int >= 1.

    Zero is REJECTED rather than honored. These values are used as `[-n:]`, and `[-0:]` is the whole
    string/list — so a `0` would silently mean "no limit at all", the exact opposite of the limit an
    operator wrote it to express."""
    value = _require(config, key, int, what)
    if isinstance(value, bool) or value < 1:
        raise ConfigError("config key %r for %s must be an int >= 1 (it is used as [-n:], where 0 "
                          "would mean NO limit); got %r" % (key, UNIT, value))
    return value


def _expand_path(token, base, what):
    """Expand a config path: `${here}` (this file's directory) and `${base}` (the config's own
    directory) first, then `~`, then resolve a still-relative path against `base`.

    `${here}` is what reproduces the original's `GUARD = os.path.join(HERE, "audit_guard.py")`
    exactly, and it keeps following this module if the package moves — freezing today's absolute
    path into the config would not. No `realpath` is applied, because the original applied none:
    it called `os.path.expanduser` and `os.path.join` and nothing more.
    """
    if not isinstance(token, str):
        raise ConfigError("config key %r for %s must be a string, not %s"
                          % (what, UNIT, type(token).__name__))
    text = token.replace("${here}", HERE).replace("${base}", base)
    text = os.path.expanduser(text)
    if not os.path.isabs(text):
        text = os.path.join(base, text)
    return text


def build_policy(config, base=None):
    """Compile `config` into a `Policy`. Raises ConfigError on a missing or unusable key.

    `base` is the directory relative paths resolve against; it defaults to the active config's base.
    The environment is read HERE, once, for `url_env` — that is the snapshot described in THE POLICY
    IS FROZEN.
    """
    base = base if base is not None else active_base()
    policy = Policy()

    policy.url_env = _require(config, "url_env", str, "env var naming congruency's base URL")
    default_url = _require(config, "congruency_url", str, "congruency's base URL")
    # The original: (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/").
    # `or` — not a `in os.environ` test — so an EMPTY env var falls back, exactly as it did.
    policy.congruency = (os.environ.get(policy.url_env) or default_url).rstrip("/")

    policy.http_timeout = _require_positive(config, "http_timeout", "seconds per congruency request")
    policy.tickets_query = _require(config, "tickets_query", str, "the OPEN-ticket query template")
    policy.memories_path = _require(config, "memories_path", str, "where record() POSTs the stamp")
    policy.content_type = _require(config, "content_type", str, "the Content-Type header")
    policy.provenance_log = _expand_path(_require(config, "provenance_log", str,
                                                 "the local provenance log"), base, "provenance_log")
    policy.stamp_kind = _require(config, "stamp_kind", str, "the stamp's 'kind' field")
    policy.session_env = _require(config, "session_env", str, "env var naming the session")
    policy.session_prefix = _require(config, "session_prefix", str, "prefix for the fallback session id")
    policy.guard = _expand_path(_require(config, "guard_path", str, "the audit-veto program"),
                                base, "guard_path")
    policy.repo_env = _require(config, "repo_env", str, "env var the guard's build repo is passed in")

    confine_env = _require(config, "confine_env", dict, "extra environment for the guard subprocess")
    for name, value in confine_env.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise ConfigError("config key 'confine_env' for %s must map strings to strings; got "
                              "%r -> %r" % (UNIT, name, value))
    policy.confine_env = dict(confine_env)

    drop = _require(config, "confine_env_drop", list, "environment names removed from the guard")
    for name in drop:
        if not isinstance(name, str):
            raise ConfigError("config key 'confine_env_drop' for %s must be a list of strings; it "
                              "contains %r (%s)" % (UNIT, name, type(name).__name__))
    policy.confine_env_drop = tuple(drop)

    policy.confine_timeout = _require_positive(config, "confine_timeout",
                                               "seconds for the guard subprocess")
    policy.error_tail = _require_tail(config, "error_tail", "chars of guard output kept on refusal")
    policy.stdout_tail = _require_tail(config, "stdout_tail", "lines of guard stdout returned")
    return policy


def active_policy():
    """Return the compiled policy in force, building and caching it on first use.

    Raises:
        ConfigError: if there is no config object to compile.
    """
    global _POLICY
    if _POLICY is None:
        _POLICY = build_policy(active_config(), active_base())
    return _POLICY


# ─────────────────────────────── the callable surface ───────────────────────────────

def _now():
    """The stamp's timestamp: an ISO-8601 UTC instant.

    Not config, and not injectable: it is the original's `datetime.now(timezone.utc).isoformat()`,
    and the provenance log's readers parse exactly that.
    """
    return datetime.now(timezone.utc).isoformat()


def _format_query(template, component):
    """Substitute `component` into a query template.

    Deliberately NOT url-encoded — see NOT URL-ENCODED. `str.format` reproduces the original's
    f-string substitution, including `str()` of a non-string component.
    """
    try:
        return template.format(component=component)
    except (KeyError, IndexError, ValueError) as exc:
        raise ConfigError("config key 'tickets_query' for %s is not a usable template (%s): %r"
                          % (UNIT, exc, template)) from exc


def _congruency(method, path, payload=None):
    """One JSON request to congruency. Returns the decoded response, or `{}` for an empty body.

    `payload=None` sends NO body, so a GET stays a GET. The Content-Type header goes out on every
    request either way, as the original's did.

    Raises:
        OSError: if congruency does not answer. `urllib`'s `URLError`/`HTTPError` are `OSError`s,
            which is what makes an outage — and an HTTP 500 — legible to `gate` and `record`.
        ValueError: if the body is not JSON. NOT an outage; see WHAT DOES *NOT* DEGRADE.
        ConfigError: if there is no config object.
    """
    policy = active_policy()
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(policy.congruency + path, data=data, method=method,
                                     headers={"Content-Type": policy.content_type})
    with urllib.request.urlopen(request, timeout=policy.http_timeout) as response:
        return json.loads(response.read().decode() or "{}")


def has_open_ticket(component):
    """True/False if congruency is reachable; RAISES OSError if it is not (ticket unverifiable).

    The raise is the point, and it is the original's: it lets `gate` tell "up but no ticket"
    (refuse) apart from "down" (proceed best-effort). See THE OUTAGE RULE.
    """
    policy = active_policy()
    return bool(_congruency("GET", _format_query(policy.tickets_query, component)).get("rows"))


def record(component, intent, session):
    """Best-effort provenance: ALWAYS to the local jail log, and to congruency when reachable.

    Returns the stamp. Never a refusal reason — provenance degrades gracefully on outage: both
    sinks swallow `OSError` (an unwritable log, a congruency that is down), and the stamp comes back
    regardless. A non-JSON reply from congruency is NOT an outage and is not swallowed; see WHAT
    DOES *NOT* DEGRADE.
    """
    policy = active_policy()
    stamp = {"ts": _now(), "kind": policy.stamp_kind, "component": component, "intent": intent,
             "session": session}
    try:
        os.makedirs(os.path.dirname(policy.provenance_log), exist_ok=True)
        # No `encoding=`: the original passed none, so the line is written in the locale's encoding
        # and this rewrite writes the same bytes on the same host.
        with open(policy.provenance_log, "a") as handle:
            handle.write(json.dumps(stamp) + "\n")
    except OSError:
        pass
    try:
        _congruency("POST", policy.memories_path, stamp)
    except OSError:
        pass
    return stamp


def gate(component, intent, session=None, require_ticket=True):
    """The precondition EVERY crank must pass. Raises CrankRefused. Returns the provenance stamp.

    Ticket is HARD when congruency is reachable; if congruency is DOWN the ticket can't be verified,
    so the crank proceeds (provenance falls back to the local log). Confinement (`run_confined`) is
    always hard, independent of congruency. See THE OUTAGE RULE.

    The empty-`intent` refusal is checked FIRST, before the config is touched: it is the original's
    order, and it is an answer this module can give without a policy.
    """
    if not intent:
        raise CrankRefused("crank discipline: an 'intent' is required (why are you cranking?)")
    policy = active_policy()
    session = session or os.environ.get(policy.session_env) or "%s%d" % (policy.session_prefix,
                                                                         os.getpid())
    if require_ticket:
        try:
            if not has_open_ticket(component):
                raise CrankRefused("crank discipline: no OPEN memory ticket for '%s' — file one "
                                   "first" % component)
        except OSError:
            # congruency unreachable -> ticket unverifiable -> proceed (provenance best-effort).
            # CrankRefused is a RuntimeError, NOT an OSError, so the refusal above sails through
            # this handler untouched. That is deliberate and `selftest` pins it.
            pass
    return record(component, intent, session)


def run_confined(patch, repo_root, timeout=DEFAULT_TIMEOUT):
    """Run a crank patch under the audit-veto. Raises CrankRefused on escape/failure. Returns the
    tail of stdout (`stdout_tail` lines, 3 by the original's reckoning).

    The guard is an OPAQUE subprocess: any non-zero exit is a refusal, whatever the reason. See THE
    GUARD IS OPAQUE.

    `timeout` defaults to `DEFAULT_TIMEOUT`, which IS 300 and which means "let `confine_timeout`
    decide"; an explicitly passed value always wins. See THE `timeout` DEFAULT. A guard that outruns
    it raises `subprocess.TimeoutExpired`, not `CrankRefused` — the original let it propagate, and
    so does this: a timeout is not a verdict from the veto, it is the absence of one.
    """
    policy = active_policy()
    if not os.path.isfile(policy.guard):
        raise CrankRefused("crank discipline: audit_guard missing at %s — cannot confine the patch"
                           % policy.guard)
    if timeout is DEFAULT_TIMEOUT:
        timeout = policy.confine_timeout
    env = {**os.environ, policy.repo_env: os.path.realpath(repo_root), **policy.confine_env}
    for name in policy.confine_env_drop:        # applied LAST: a dropped name stays dropped
        env.pop(name, None)
    result = subprocess.run([sys.executable, policy.guard, patch], cwd=repo_root,
                            capture_output=True, text=True, timeout=timeout, env=env)
    if result.returncode != 0:
        raise CrankRefused("crank discipline: patch refused/failed under the audit-veto "
                           "(rc=%s): %s" % (result.returncode,
                                            (result.stderr or result.stdout).strip()[-policy.error_tail:]))
    return (result.stdout or "").strip().splitlines()[-policy.stdout_tail:]


# ─────────────────────────────── bug reports ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ... Filename -
    function name - time of occurance - methods to reproduce - possible cause"). Best-effort and
    silent on failure: a tool that cannot file a report must still report its original error.
    Returns the path written, or None.

    `CrankRefused` and `ConfigError` never reach here — they are this module's DESIGNED answers, and
    `main` handles both above. Filing a bug report for a refused crank would turn the gate doing its
    job into a defect record.
    """
    try:
        config = active_config()
        base = active_base()
    except ConfigError:
        return None
    relative = config.get("bug_reports")
    # A non-string here (the one config key nothing else validates) would raise INSIDE this
    # handler and replace the original exception with a TypeError from the reporter.
    if not isinstance(relative, str) or not relative:
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
        "traceback": formatted,
    }
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except OSError:
        return None


# ─────────────────────────────── the CLI ───────────────────────────────

def _build_parser():
    parser = argparse.ArgumentParser(
        prog="crank_discipline",
        description="The gate every crank routes through: an OPEN ticket, recorded provenance, and "
                    "a patch confined under the audit-veto. Config comes from %s or the '%s' "
                    "section of the nearest %s; without one this tool throws rather than guessing "
                    "(note-for-claude)." % (CONFIG_ENV, ".".join(UNIT_PATH), REGISTRY_NAME),
        epilog="exit: 0 ok, 2 usage, 3 refused, 4 no config object")
    subparsers = parser.add_subparsers(dest="command")

    p_gate = subparsers.add_parser("gate", help="run the crank precondition; print the stamp")
    p_gate.add_argument("--component", required=True, help="the subsystem being cranked")
    p_gate.add_argument("--intent", required=True, help="why you are cranking")
    p_gate.add_argument("--session", help="session id (default: the session_env var, else "
                                          "<session_prefix><pid>)")
    p_gate.add_argument("--no-require-ticket", dest="require_ticket", action="store_false",
                        help="skip the OPEN-ticket precondition")

    p_record = subparsers.add_parser("record", help="write a provenance stamp; print it")
    p_record.add_argument("--component", required=True)
    p_record.add_argument("--intent", required=True)
    p_record.add_argument("--session", required=True)

    p_ticket = subparsers.add_parser("has-open-ticket", help="is there an OPEN ticket? (true/false)")
    p_ticket.add_argument("--component", required=True)

    p_run = subparsers.add_parser("run-confined", help="run a patch under the audit-veto")
    p_run.add_argument("--patch", required=True, help="the crank patch to run")
    p_run.add_argument("--repo", required=True, help="the build repo the patch may write to")
    p_run.add_argument("--timeout", type=float,
                       help="seconds (default: the config's confine_timeout)")

    subparsers.add_parser("show-config", help="print the config object in force and its source")
    subparsers.add_parser("show-policy", help="print the compiled policy")
    subparsers.add_parser("emit-config", help="print this unit's config-object template")
    subparsers.add_parser("selftest", help="run the equivalence exemplars")
    return parser


def _dispatch(args):
    """Run one CLI command. Returns an exit code. Raises ConfigError/CrankRefused for `main`."""
    if args.command == "emit-config":
        print(json.dumps(config_template(), indent=2))
        return EXIT_OK
    if args.command == "show-config":
        print("source: %s" % active_source())
        print("base  : %s" % active_base())
        print(json.dumps(active_config(), indent=2))
        return EXIT_OK
    if args.command == "show-policy":
        policy = active_policy()
        print(json.dumps({key: (list(value) if isinstance(value, tuple) else value)
                          for key, value in policy.as_dict().items()}, indent=2))
        return EXIT_OK
    if args.command == "selftest":
        return selftest()
    if args.command == "gate":
        print(json.dumps(gate(args.component, args.intent, session=args.session,
                              require_ticket=args.require_ticket), indent=2))
        return EXIT_OK
    if args.command == "record":
        print(json.dumps(record(args.component, args.intent, args.session), indent=2))
        return EXIT_OK
    if args.command == "has-open-ticket":
        print("true" if has_open_ticket(args.component) else "false")
        return EXIT_OK
    if args.command == "run-confined":
        if args.timeout is None:
            tail = run_confined(args.patch, args.repo)      # the config's confine_timeout decides
        else:
            tail = run_confined(args.patch, args.repo, timeout=args.timeout)
        for line in tail:
            print(line)
        return EXIT_OK
    raise AssertionError("unreachable command %r" % args.command)   # pragma: no cover


def main(argv=None):
    """The console entry point (`forge2-crank-discipline`). Returns the process exit code.

    `argv` is the argument list WITHOUT the program name, as `argparse` expects; `None` means
    `sys.argv[1:]`, so the console script — which setuptools calls as `main()` with no arguments —
    and `python3 crank_discipline.py` behave identically.

    The original had no CLI, so nothing here can break an existing caller: `main` is an ADDITION,
    and the six functions of the surface are untouched by it.

        0  ok      2  usage      3  refused      4  no config object

    Usage is checked before config, so a bad command line is exit 2 whether or not a config object
    exists — it needs no policy to answer. A `ConfigError` is one self-explaining line, never a
    traceback, and nothing has been gated when it is printed.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_usage(sys.stderr)
        sys.stderr.write("crank_discipline: a command is required\n")
        return EXIT_USAGE
    try:
        return _dispatch(args)
    except CrankRefused as exc:
        # The gate doing its job. One line, no traceback, no bug report.
        sys.stderr.write("%s\n" % exc)
        return EXIT_REFUSED
    except ConfigError as exc:
        # The #200 requirement-4 gate. Designed behavior, not a defect.
        sys.stderr.write("config error: %s\n" % exc)
        return EXIT_NO_CONFIG
    except Exception as exc:      # noqa: BLE001 — an unexpected exception here IS a defect in this
        # tool, which is exactly what note-for-claude wants reported automatically.
        path = _bug_report(exc, traceback.format_exc(), argv)
        sys.stderr.write("EXCEPTION — %s\n" % ("bug report filed at %s" % path if path
                                               else "no bug report could be filed"))
        raise


# ─────────────────────────────── the selftest ───────────────────────────────
#
# The exemplars. The ticket mined NONE for this module (criteria_miner takes only self-contained
# pure functions, and every function here touches the network, the clock, the filesystem or a
# subprocess), which #200 says MOVES the work here rather than lowering the bar. So these checks are
# written by hand from the ORIGINAL's behavior, and they run against a REAL ephemeral congruency and
# REAL guard subprocesses under a redirected HOME — no mocks of the things being preserved.
#
# `http.server`, `threading`, `tempfile`, `inspect` and `socket` are imported INSIDE these helpers,
# not at module scope. This module is a HARD DEPENDENCY of every repo's ratchet, and a ratchet that
# imports it to call `gate()` should not pay for a web server it will never start.


def _attempt(thunk):
    """Call `thunk`; return `("ok", value)` or `("raised", type_name, message)`.

    A test net that dies on the first unexpected exception hides every check after it and reports a
    traceback where it owes a verdict. Every check whose EXPECTED result is an exception goes through
    here, so that exception is a REPORTED result — including the `OSError`, `ValueError` and
    `AttributeError` the ORIGINAL itself raises, which are expected results here, not accidents.

    Checks on a happy path call the surface directly, because a raise there is not a result anyone
    predicted. Those are covered by the per-section net in `selftest`, which turns an unexpected
    exception into ONE reported FAIL for that section and lets the remaining sections run. Between
    the two, no check can ever answer with a traceback.
    """
    try:
        return ("ok", thunk())
    except BaseException as exc:      # noqa: BLE001 — a test net must survive anything
        return ("raised", type(exc).__name__, str(exc))


def _oracle_config(**overrides):
    """The config object the exemplars run against: the ORIGINAL's hardcoded values, which is the
    whole point — in this configuration the rewrite must BE the original.

    Overrides steer only things the ORIGINAL could ALSO see: a stub guard sitting where its `HERE`
    would find one, a provenance log under a redirected HOME. The congruency URL is steered through
    the `CONGRUENCY_URL` ENVIRONMENT VARIABLE, never through this config, because the original reads
    that variable too — a scenario steered through a config key the original does not have would
    move only the rewrite, and prove nothing.
    """
    config = config_template()
    config.update(overrides)
    return config


class _Checks:
    """A running PASS/FAIL tally that prints one line per check."""

    def __init__(self, stream):
        self.stream = stream
        self.passed = 0
        self.failed = 0

    def equal(self, name, got, want):
        self.that(name, got == want, "got %r, want %r" % (got, want))

    def that(self, name, ok, detail=""):
        if ok:
            self.passed += 1
            self.stream.write("PASS  %s\n" % name)
        else:
            self.failed += 1
            self.stream.write("FAIL  %s\n        %s\n" % (name, detail))
        return ok

    def raises(self, name, outcome, exc_name, message_contains=None):
        ok = outcome[0] == "raised" and outcome[1] == exc_name
        if ok and message_contains is not None:
            ok = message_contains in outcome[2]
        self.that(name, ok, "got %r, want %s containing %r" % (outcome, exc_name, message_contains))
        return ok


@contextlib.contextmanager
def _congruency_server(state):
    """A real HTTP congruency on 127.0.0.1, answering from `state` and RECORDING what it is sent.

    Yields `(base_url, seen)`. `state` is a dict with "status" and "body"; `seen` collects one dict
    per request — method, path, Content-Type and body — which is how the exemplars check the exact
    bytes this module puts on the wire, not merely what it returns.
    """
    import http.server
    import threading

    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def _serve(self):
            length = int(self.headers.get("Content-Length") or 0)
            seen.append({"method": self.command, "path": self.path,
                         "content_type": self.headers.get("Content-Type"),
                         "body": self.rfile.read(length).decode() if length else None})
            raw = state["body"].encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = _serve
        do_POST = _serve

        def log_message(self, *args):       # keep the selftest's output the selftest's
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % server.server_address[1], seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _dead_url():
    """A URL nothing is listening on: bind an ephemeral port, learn its number, release it."""
    import socket
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return "http://127.0.0.1:%d" % port


def _write(path, text):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


#: Stub guards. The guard is an OPAQUE subprocess to this module, so a stub that exits with a code
#: IS a faithful guard for every purpose `run_confined` has — it reads the exit code and the output
#: tail and nothing else. The REAL audit_guard is exercised separately, at the end.
_GUARD_OK = "import sys\nfor i in range(5):\n    print('line%d' % i)\nsys.exit(0)\n"
_GUARD_QUIET = "import sys\nsys.exit(0)\n"
_GUARD_VETO = ("import sys\nsys.stderr.write('CRANK-VETO: wrote outside the repo\\n')\n"
               "sys.exit(3)\n")
_GUARD_LONG = "import sys\nsys.stderr.write('x' * 900)\nsys.exit(1)\n"
_GUARD_STDOUT_ONLY = "import sys\nprint('only on stdout')\nsys.exit(2)\n"
#: A guard that writes BOTH streams. It is the only stub that can see which stream the refusal
#: message prefers: while either stream is empty, the original's `stderr or stdout` and a swapped
#: `stdout or stderr` produce the identical message, so every OTHER stub passes both ways.
_GUARD_BOTH = ("import sys\nprint('ON-STDOUT')\nsys.stderr.write('ON-STDERR\\n')\nsys.exit(5)\n")
_GUARD_SLEEP = "import time\ntime.sleep(3)\n"
_GUARD_ENV = (
    "import json, os, sys\n"
    "print(json.dumps({'repo': os.environ.get('CRANK_REPO'),\n"
    "                  'bytecode': os.environ.get('PYTHONDONTWRITEBYTECODE'),\n"
    "                  'forge2_config': os.environ.get('FORGE2_CONFIG'),\n"
    "                  'cwd': os.getcwd(),\n"
    "                  'patch': sys.argv[1] if len(sys.argv) > 1 else None}))\n")


def _selftest_surface(checks):
    """(b) the callable surface: same names, same parameters, same defaults."""
    import inspect

    for name, want in (("_now", "()"),
                       ("_congruency", "(method, path, payload=None)"),
                       ("has_open_ticket", "(component)"),
                       ("record", "(component, intent, session)"),
                       ("gate", "(component, intent, session=None, require_ticket=True)"),
                       ("run_confined", "(patch, repo_root, timeout=300)")):
        got = str(inspect.signature(globals()[name]))
        checks.equal("surface: %s%s" % (name, want), "%s%s" % (name, got), "%s%s" % (name, want))

    checks.that("surface: CrankRefused is a RuntimeError (the original's class)",
                issubclass(CrankRefused, RuntimeError))
    checks.that("surface: CrankRefused is NOT an OSError, so gate's except OSError cannot eat it",
                not issubclass(CrankRefused, OSError))
    default = inspect.signature(run_confined).parameters["timeout"].default
    checks.that("surface: run_confined's timeout default == 300 and reprs as 300",
                default == 300 and repr(default) == "300", "got %r" % (default,))
    checks.that("surface: the default IS a distinct object equal to 300, so an explicitly passed "
                "300 can never be mistaken for it",
                type(DEFAULT_TIMEOUT) is not int and DEFAULT_TIMEOUT == 300)

    checks.equal("_now() parses as an ISO-8601 UTC instant",
                 datetime.fromisoformat(_now()).tzinfo, timezone.utc)


def _selftest_config_gate(checks, tmp):
    """(d) it throws without a config object, and never guesses a default."""
    missing = os.path.join(tmp, "nowhere", "absent.json")
    reset_config()
    os.environ[CONFIG_ENV] = missing
    try:
        for label, thunk in (("gate", lambda: gate("workstation", "why")),
                             ("record", lambda: record("workstation", "why", "s")),
                             ("has_open_ticket", lambda: has_open_ticket("workstation")),
                             ("_congruency", lambda: _congruency("GET", "/")),
                             ("run_confined", lambda: run_confined("p.py", tmp))):
            checks.raises("no config -> ConfigError: %s" % label, _attempt(thunk), "ConfigError",
                          "no such file exists")

        # The empty-intent refusal needs no policy, and the original answered it first. Proving it
        # HERE, with the config still unreachable, is what pins the ORDER.
        checks.raises("empty intent refuses BEFORE config is touched (the original's order)",
                      _attempt(lambda: gate("workstation", "")), "CrankRefused",
                      "crank discipline: an 'intent' is required (why are you cranking?)")
    finally:
        os.environ.pop(CONFIG_ENV, None)
        reset_config()

    # A config object that IS found but is incomplete names the missing key — it never defaults.
    for key in ("congruency_url", "guard_path", "error_tail"):
        config = _oracle_config()
        config.pop(key)
        with using_config(config, base=tmp):
            checks.raises("incomplete config names the missing key %r" % key,
                          _attempt(active_policy), "ConfigError", repr(key))

    # `[-0:]` is the WHOLE string, so a 0 tail would silently mean "no limit". Rejected, not honored.
    for key in ("error_tail", "stdout_tail"):
        with using_config(_oracle_config(**{key: 0}), base=tmp):
            checks.raises("a %r of 0 is rejected, not honored as [-0:] (no limit)" % key,
                          _attempt(active_policy), "ConfigError", "0 would mean NO limit")

    with using_config(_oracle_config(http_timeout=0), base=tmp):
        checks.raises("a non-positive http_timeout is a ConfigError",
                      _attempt(active_policy), "ConfigError", "greater than 0")

    # A registry that exists but carries no section for this unit is not a config object either.
    empty_registry = os.path.join(tmp, "emptyreg")
    _write(os.path.join(empty_registry, REGISTRY_NAME), json.dumps({"schema": 1, "forge2": {}}))
    checks.raises("a registry with no section for this unit -> ConfigError naming the section",
                  _attempt(lambda: load_config(start=empty_registry)), "ConfigError",
                  "'forge2.agent_tools_suite'")

    # The shipped registry beside this file IS a usable config object (source 2 answers).
    reset_config()
    shipped = _attempt(lambda: load_config())
    checks.that("the SHIPPED registry.json beside this module resolves this unit's config object",
                shipped[0] == "ok" and shipped[1][2].endswith(REGISTRY_NAME), "got %r" % (shipped,))
    if shipped[0] == "ok":
        checks.equal("the shipped config object equals the original's values (behavior-preserving)",
                     {k: v for k, v in shipped[1][0].items() if k in config_template()},
                     config_template())


def _selftest_congruency(checks, tmp):
    """_congruency / has_open_ticket: the wire bytes, the outage, and what does NOT degrade."""
    state = {"status": 200, "body": "{}"}
    log = os.path.join(tmp, "prov", "provenance.jsonl")
    with _congruency_server(state) as (base, seen):
        os.environ["CONGRUENCY_URL"] = base          # the axis the ORIGINAL reads too
        with using_config(_oracle_config(provenance_log=log), base=tmp):
            state["body"] = json.dumps({"rows": [{"id": 7}]})
            checks.equal("has_open_ticket: rows present -> True", has_open_ticket("workstation"), True)
            checks.equal("has_open_ticket sends the ORIGINAL's exact un-encoded query",
                         seen[-1]["path"],
                         "/?api=tickets&component=workstation&status=OPEN&order=id.desc&per=1")
            checks.equal("has_open_ticket is a GET", seen[-1]["method"], "GET")
            checks.equal("a GET carries NO body (payload=None sends no data)", seen[-1]["body"], None)
            checks.equal("every request carries Content-Type: application/json",
                         seen[-1]["content_type"], "application/json")

            state["body"] = json.dumps({"rows": []})
            checks.equal("has_open_ticket: rows empty -> False", has_open_ticket("workstation"), False)
            state["body"] = json.dumps({"other": 1})
            checks.equal("has_open_ticket: no 'rows' key -> False", has_open_ticket("workstation"),
                         False)

            # NOT url-encoded — the original's f-string interpolated raw, and so do we.
            state["body"] = json.dumps({"rows": []})
            has_open_ticket("a&b=c")
            checks.equal("component is NOT url-encoded (the original's sharp edge, preserved)",
                         seen[-1]["path"],
                         "/?api=tickets&component=a&b=c&status=OPEN&order=id.desc&per=1")
            has_open_ticket(42)
            checks.that("a non-string component is str()'d, as the f-string did",
                        "component=42&" in seen[-1]["path"], seen[-1]["path"])

            state["body"] = ""
            checks.equal("_congruency: an EMPTY body decodes as {}", _congruency("GET", "/"), {})

            state["status"], state["body"] = 500, "boom"
            checks.raises("a 500 is an OSError (HTTPError) -> reads as an outage",
                          _attempt(lambda: has_open_ticket("c")), "HTTPError")
            checks.that("...and HTTPError really is an OSError, which is why gate proceeds on it",
                        issubclass(urllib.error.HTTPError, OSError))

            state["status"], state["body"] = 200, "not json at all"
            checks.raises("a non-JSON 200 raises ValueError — NOT swallowed as an outage",
                          _attempt(lambda: has_open_ticket("c")), "JSONDecodeError")

            state["body"] = json.dumps([{"id": 1}])
            checks.raises("a JSON LIST body raises AttributeError from .get — preserved",
                          _attempt(lambda: has_open_ticket("c")), "AttributeError")

    os.environ["CONGRUENCY_URL"] = _dead_url()
    with using_config(_oracle_config(provenance_log=log), base=tmp):
        checks.raises("congruency DOWN -> has_open_ticket raises OSError (ticket unverifiable)",
                      _attempt(lambda: has_open_ticket("workstation")), "URLError")
        checks.that("...and URLError is an OSError, the class the original catches",
                    issubclass(urllib.error.URLError, OSError))

    # The URL is resolved once and then FROZEN, as the original's import-time constant was.
    with _congruency_server(state) as (base, seen):
        os.environ["CONGRUENCY_URL"] = base
        with using_config(_oracle_config(provenance_log=log), base=tmp):
            state["status"], state["body"] = 200, json.dumps({"rows": []})
            has_open_ticket("first")
            frozen = active_policy().congruency
            os.environ["CONGRUENCY_URL"] = "http://127.0.0.1:9/moved"
            has_open_ticket("second")
            checks.equal("the congruency URL is FROZEN after first use (the original froze it at "
                         "import)", active_policy().congruency, frozen)
            checks.equal("...and the frozen URL is still the one on the wire", len(seen), 2)
            checks.equal("an empty CONGRUENCY_URL falls back to congruency_url (`or`, not `in`)",
                         _url_for(""), config_template()["congruency_url"])
            checks.equal("a trailing / on the URL is stripped, as .rstrip('/') did",
                         _url_for("http://example.test:1/"), "http://example.test:1")
    os.environ.pop("CONGRUENCY_URL", None)


def _url_for(env_value):
    """Resolve the congruency URL the way build_policy does, for one value of the env var."""
    previous = os.environ.get("CONGRUENCY_URL")
    os.environ["CONGRUENCY_URL"] = env_value
    try:
        return build_policy(_oracle_config(), base=os.getcwd()).congruency
    finally:
        if previous is None:
            os.environ.pop("CONGRUENCY_URL", None)
        else:
            os.environ["CONGRUENCY_URL"] = previous


def _selftest_record_and_gate(checks, tmp):
    """record / gate: provenance that never refuses, and the outage asymmetry."""
    state = {"status": 200, "body": json.dumps({"rows": [{"id": 1}]})}
    home = os.path.join(tmp, "home")
    os.environ["HOME"] = home            # so the ORIGINAL's own "~/bin/config/crank/..." is safe
    log_relative_to_home = "~/bin/config/crank/provenance.jsonl"
    expected_log = os.path.join(home, "bin", "config", "crank", "provenance.jsonl")

    with _congruency_server(state) as (base, seen):
        os.environ["CONGRUENCY_URL"] = base
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        with using_config(_oracle_config(provenance_log=log_relative_to_home), base=tmp):
            checks.equal("provenance_log expands ~ to the ORIGINAL's path shape under HOME",
                         active_policy().provenance_log, expected_log)

            stamp = record("workstation", "why I cranked", "sess-1")
            checks.equal("record returns the stamp", list(stamp),
                         ["ts", "kind", "component", "intent", "session"])
            checks.equal("record's stamp carries the config's kind", stamp["kind"], "crank")
            with open(expected_log, "r") as handle:
                lines = handle.read().splitlines()
            checks.equal("record CREATES the log's parent dirs and appends ONE line", len(lines), 1)
            checks.equal("the log line is exactly json.dumps(stamp) — key order included",
                         lines[0], json.dumps(stamp))
            checks.equal("record POSTs the stamp to the config's memories path",
                         (seen[-1]["method"], seen[-1]["path"]), ("POST", "/?api=memories"))
            checks.equal("the POSTed body IS the stamp", json.loads(seen[-1]["body"]), stamp)

            record("workstation", "second", "sess-2")
            with open(expected_log, "r") as handle:
                checks.equal("record APPENDS (never truncates the jail log)",
                             len(handle.read().splitlines()), 2)

            # gate: the ticket is HARD while congruency answers.
            state["body"] = json.dumps({"rows": [{"id": 1}]})
            got = _attempt(lambda: gate("workstation", "an intent"))
            checks.that("gate: OPEN ticket + reachable -> returns the stamp",
                        got[0] == "ok" and got[1]["intent"] == "an intent", "%r" % (got,))

            state["body"] = json.dumps({"rows": []})
            checks.raises("gate: reachable + NO ticket -> CrankRefused (the message, verbatim)",
                          _attempt(lambda: gate("workstation", "an intent")), "CrankRefused",
                          "crank discipline: no OPEN memory ticket for 'workstation' — file one first")
            # The check above IS the proof that gate's own `except OSError` does not eat its own
            # refusal: the CrankRefused is raised INSIDE that try and still reached the caller.
            before = len(seen)
            _attempt(lambda: gate("workstation", "an intent"))
            checks.equal("a refused gate records NO provenance (it never reaches record)",
                         len(seen) - before, 1)      # the tickets GET only; no POST followed

            checks.that("gate: require_ticket=False skips the ticket query entirely",
                        _skips_ticket_query(seen))

            # session resolution, at CALL time — the original read the env inside gate().
            os.environ["CLAUDE_CODE_SESSION_ID"] = "from-env"
            checks.equal("gate: session defaults to the session_env var",
                         gate("workstation", "i", require_ticket=False)["session"], "from-env")
            checks.equal("gate: an explicit session wins over the env",
                         gate("workstation", "i", session="explicit",
                              require_ticket=False)["session"], "explicit")
            os.environ["CLAUDE_CODE_SESSION_ID"] = ""
            checks.equal("gate: an EMPTY session_env falls through to <prefix><pid> (`or`)",
                         gate("workstation", "i", require_ticket=False)["session"],
                         "crank-%d" % os.getpid())
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            checks.equal("gate: an UNSET session_env falls through to <prefix><pid>",
                         gate("workstation", "i", require_ticket=False)["session"],
                         "crank-%d" % os.getpid())
            checks.equal("gate: an empty explicit session falls through too (`or`, not `is None`)",
                         gate("workstation", "i", session="", require_ticket=False)["session"],
                         "crank-%d" % os.getpid())

            for empty in ("", None, 0, []):
                checks.raises("gate: a falsy intent %r is refused" % (empty,),
                              _attempt(lambda e=empty: gate("workstation", e)), "CrankRefused",
                              "an 'intent' is required")

            # A non-JSON reply is NOT an outage: it escapes gate and record untouched.
            state["body"] = "<html>not congruency</html>"
            checks.raises("gate: a non-JSON reply raises ValueError (NOT treated as an outage)",
                          _attempt(lambda: gate("workstation", "i")), "JSONDecodeError")
            checks.raises("record: a non-JSON reply to the POST raises too — only OSError degrades",
                          _attempt(lambda: record("workstation", "i", "s")), "JSONDecodeError")

            # A 500 IS an outage (HTTPError is an OSError), so the crank proceeds.
            state["status"], state["body"] = 500, "boom"
            got = _attempt(lambda: gate("workstation", "i"))
            checks.that("gate: a 500 on the ticket query -> proceeds (HTTPError is an OSError)",
                        got[0] == "ok" and got[1]["component"] == "workstation", "%r" % (got,))

    # congruency DOWN: the ticket cannot be verified, so the crank proceeds; provenance degrades.
    os.environ["CONGRUENCY_URL"] = _dead_url()
    with using_config(_oracle_config(provenance_log=log_relative_to_home), base=tmp):
        got = _attempt(lambda: gate("workstation", "offline intent"))
        checks.that("gate: congruency DOWN -> proceeds best-effort and returns the stamp",
                    got[0] == "ok" and got[1]["intent"] == "offline intent", "%r" % (got,))
        with open(expected_log, "r") as handle:
            checks.that("...and the provenance fell back to the local jail log",
                        "offline intent" in handle.read())
        got = _attempt(lambda: record("workstation", "i", "s"))
        checks.that("record: congruency DOWN -> still returns the stamp (never a refusal reason)",
                    got[0] == "ok", "%r" % (got,))

    # An UNWRITABLE log is swallowed too: record must still return the stamp.
    blocker = _write(os.path.join(tmp, "blocker"), "not a directory\n")
    with using_config(_oracle_config(provenance_log=os.path.join(blocker, "prov.jsonl")), base=tmp):
        got = _attempt(lambda: record("workstation", "i", "s"))
        checks.that("record: an UNWRITABLE log is swallowed (OSError) and the stamp still returns",
                    got[0] == "ok" and got[1]["session"] == "s", "%r" % (got,))
    os.environ.pop("CONGRUENCY_URL", None)


def _skips_ticket_query(seen):
    """True if `gate(..., require_ticket=False)` issued no tickets GET — checked by watching the
    real server's log, not by trusting the code path."""
    before = len([r for r in seen if "api=tickets" in r["path"]])
    gate("workstation", "no ticket needed", require_ticket=False)
    after = len([r for r in seen if "api=tickets" in r["path"]])
    return before == after


def _selftest_confine(checks, tmp):
    """run_confined: the guard subprocess, its environment, its verdict and its tails."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    patch = _write(os.path.join(repo, "patch.py"), "print('patched')\n")
    guards = os.path.join(tmp, "guards")

    def with_guard(source, name="audit_guard.py", **overrides):
        """A config whose `${here}`-equivalent guard is this stub. The ORIGINAL found its guard next
        to itself; a stub placed where the config points is the same relationship."""
        path = _write(os.path.join(guards, name), source)
        return _oracle_config(guard_path=path, provenance_log=os.path.join(tmp, "p.jsonl"),
                              **overrides)

    with using_config(with_guard(_GUARD_OK), base=tmp):
        checks.equal("run_confined: rc=0 -> the LAST 3 stdout lines (stdout_tail)",
                     run_confined(patch, repo), ["line2", "line3", "line4"])

    with using_config(with_guard(_GUARD_OK, stdout_tail=2), base=tmp):
        checks.equal("run_confined: stdout_tail is CONFIG, not a hardcoded 3",
                     run_confined(patch, repo), ["line3", "line4"])

    with using_config(with_guard(_GUARD_QUIET), base=tmp):
        checks.equal("run_confined: rc=0 with NO output -> [] ('' .splitlines() is [])",
                     run_confined(patch, repo), [])

    with using_config(with_guard(_GUARD_VETO), base=tmp):
        checks.raises("run_confined: a VETO (rc=3) -> CrankRefused naming rc and the stderr tail",
                      _attempt(lambda: run_confined(patch, repo)), "CrankRefused",
                      "crank discipline: patch refused/failed under the audit-veto (rc=3): "
                      "CRANK-VETO: wrote outside the repo")

    with using_config(with_guard(_GUARD_STDOUT_ONLY), base=tmp):
        checks.raises("run_confined: empty stderr falls back to stdout in the message",
                      _attempt(lambda: run_confined(patch, repo)), "CrankRefused",
                      "(rc=2): only on stdout")

    # With BOTH streams non-empty, stderr WINS — the original's `(result.stderr or result.stdout)`.
    # This is the only check that pins the PRECEDENCE: every other guard stub leaves one stream
    # empty, and with one stream empty a swapped `stdout or stderr` yields the same message and
    # passes. The veto's reason is what an operator reads, so which stream wins is the behavior.
    with using_config(with_guard(_GUARD_BOTH), base=tmp):
        outcome = _attempt(lambda: run_confined(patch, repo))
        checks.that("run_confined: with BOTH streams non-empty, stderr WINS over stdout "
                    "(the original's `stderr or stdout`)",
                    outcome[0] == "raised" and outcome[1] == "CrankRefused"
                    and outcome[2].endswith("(rc=5): ON-STDERR") and "ON-STDOUT" not in outcome[2],
                    "%r" % (outcome,))

    with using_config(with_guard(_GUARD_LONG), base=tmp):
        outcome = _attempt(lambda: run_confined(patch, repo))
        checks.that("run_confined: the output tail is cut to the LAST 400 chars (error_tail)",
                    outcome[0] == "raised" and outcome[2].endswith("(rc=1): " + "x" * 400),
                    "%r" % (outcome,))
    with using_config(with_guard(_GUARD_LONG, error_tail=10), base=tmp):
        outcome = _attempt(lambda: run_confined(patch, repo))
        checks.that("run_confined: error_tail is CONFIG, not a hardcoded 400",
                    outcome[0] == "raised" and outcome[2].endswith("(rc=1): " + "x" * 10),
                    "%r" % (outcome,))

    absent = os.path.join(tmp, "no-such-guard.py")
    with using_config(_oracle_config(guard_path=absent, provenance_log=os.path.join(tmp, "p.jsonl")),
                      base=tmp):
        checks.raises("run_confined: a MISSING guard -> CrankRefused, and the patch never runs",
                      _attempt(lambda: run_confined(patch, repo)), "CrankRefused",
                      "crank discipline: audit_guard missing at %s — cannot confine the patch" % absent)

    # The child's environment: CRANK_REPO, PYTHONDONTWRITEBYTECODE, cwd, argv — and the drop.
    os.environ[CONFIG_ENV] = os.path.join(tmp, "some-crank-config.json")
    with using_config(with_guard(_GUARD_ENV), base=tmp):
        child = json.loads(run_confined(patch, repo)[0])
        checks.equal("run_confined: the guard is passed the patch as argv[1]", child["patch"], patch)
        checks.equal("run_confined: the guard runs with cwd=repo_root", child["cwd"],
                     os.path.realpath(repo))
        checks.equal("run_confined: repo_env carries the REALPATH of repo_root", child["repo"],
                     os.path.realpath(repo))
        checks.equal("run_confined: confine_env reaches the guard (PYTHONDONTWRITEBYTECODE=1)",
                     child["bytecode"], "1")
        checks.equal("run_confined: FORGE2_CONFIG is DROPPED, so the guard reads ITS OWN config "
                     "(the original's child never saw it)", child["forge2_config"], None)

    with using_config(with_guard(_GUARD_ENV, confine_env_drop=[]), base=tmp):
        child = json.loads(run_confined(patch, repo)[0])
        checks.equal("run_confined: the drop is CONFIG — an empty confine_env_drop passes it "
                     "through", child["forge2_config"], os.environ[CONFIG_ENV])
    os.environ.pop(CONFIG_ENV, None)

    with using_config(with_guard(_GUARD_ENV, confine_env={"PYTHONDONTWRITEBYTECODE": "1",
                                                          "CRANK_REPO": "clobbered"}), base=tmp):
        child = json.loads(run_confined(patch, repo)[0])
        checks.equal("run_confined: confine_env is merged AFTER repo_env, so it wins on a clash",
                     child["repo"], "clobbered")

    # The timeout: config decides when the caller says nothing; an explicit value always wins.
    with using_config(with_guard(_GUARD_SLEEP, confine_timeout=0.4), base=tmp):
        checks.raises("run_confined: with no timeout argument, confine_timeout decides (0.4s)",
                      _attempt(lambda: run_confined(patch, repo)), "TimeoutExpired")
    with using_config(with_guard(_GUARD_SLEEP, confine_timeout=60), base=tmp):
        checks.raises("run_confined: an EXPLICIT timeout overrides a generous confine_timeout",
                      _attempt(lambda: run_confined(patch, repo, timeout=0.4)), "TimeoutExpired")
    # The crux of the DEFAULT_TIMEOUT design, tested so it can FAIL: a 3s guard, a config that would
    # time out at 0.4s, and an explicit literal 300. If the sentinel were matched by VALUE rather
    # than identity, the config's 0.4 would apply and this would raise TimeoutExpired.
    with using_config(with_guard(_GUARD_SLEEP, confine_timeout=0.4), base=tmp):
        # Through _attempt, because this check's whole purpose is to FAIL if the sentinel is ever
        # matched by VALUE: a `timeout == DEFAULT_TIMEOUT` test would apply the config's 0.4s to
        # this 3s guard and raise TimeoutExpired. Called bare, that exception would escape the
        # selftest and print a traceback where this check owes a verdict.
        checks.equal("run_confined: an explicit LITERAL 300 is used verbatim and beats a 0.4s "
                     "confine_timeout — it is never mistaken for the sentinel",
                     _attempt(lambda: run_confined(patch, repo, timeout=300)), ("ok", []))

    # And the REAL guard, in the shipped configuration: whatever it answers, the verdict is
    # well-defined, because the guard is OPAQUE to this module.
    reset_config()
    shipped = _attempt(active_policy)
    if shipped[0] == "ok" and os.path.isfile(shipped[1].guard):
        outcome = _attempt(lambda: run_confined(patch, repo))
        ok = (outcome[0] == "ok" and isinstance(outcome[1], list)) or \
             (outcome[0] == "raised" and outcome[1] == "CrankRefused")
        checks.that("the REAL audit_guard beside this module yields a well-defined verdict "
                    "(rc=0 -> tail, rc!=0 -> CrankRefused): %s"
                    % ("tail %r" % (outcome[1],) if outcome[0] == "ok" else outcome[2][:120]), ok,
                    "%r" % (outcome,))


def selftest(stream=None):
    """Run the equivalence exemplars. Prints one line per check; returns 0 if all passed, else 1.

    Everything runs under a temporary HOME and a temporary directory, so this creates NO file
    outside that directory — in particular it never touches the real
    `~/bin/config/crank/provenance.jsonl`. The environment and the config layer are restored on the
    way out, so a caller that runs the selftest and then cranks is unaffected.

    Each section runs inside its own net: an UNEXPECTED exception becomes one reported FAIL for that
    section and the remaining sections still run. A test net owes a verdict, not a traceback, and a
    crash in one section must not silently hide every check behind it — which is exactly what it
    would do if these five calls were bare.
    """
    import tempfile
    out = stream or sys.stdout
    checks = _Checks(out)
    saved_env = dict(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="crank-selftest-") as tmp:
            for name, section in (("surface", lambda: _selftest_surface(checks)),
                                  ("config gate", lambda: _selftest_config_gate(checks, tmp)),
                                  ("congruency", lambda: _selftest_congruency(checks, tmp)),
                                  ("record/gate", lambda: _selftest_record_and_gate(checks, tmp)),
                                  ("confine", lambda: _selftest_confine(checks, tmp))):
                try:
                    section()
                except BaseException as exc:      # noqa: BLE001 — a test net must survive anything
                    checks.that("selftest section %r ran to completion" % name, False,
                                "it raised %s: %s\n%s" % (type(exc).__name__, exc,
                                                          traceback.format_exc()))
    finally:
        os.environ.clear()
        os.environ.update(saved_env)
        reset_config()
    out.write("\n%d passed, %d failed\n" % (checks.passed, checks.failed))
    return EXIT_OK if not checks.failed else 1


if __name__ == "__main__":
    sys.exit(main())
