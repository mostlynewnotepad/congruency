#!/usr/bin/env python3
"""forge2 / agent_tools_suite / crank_job — a behavior-preserving rewrite of the forge unit
`agent_tools_suite:crank_job.py` (module key forge-rw:be64085c80ed0cfe, git blob
79c284710a05953c9acc70f619991d2df7f4de5e, 2733 bytes), filed under ticket #420 against the
FORGE-wide refactor standard #200.

WHAT THIS IS
------------
A CONTENT-ADDRESSED store for "crank jobs" on congruency. A crank job is a JSON object — a job
SPEC. `put` stores one and prints the hash it is filed under; `get` fetches it back by that hash
and verifies, before printing it, that what came back really does hash to what was asked for.

The address is the hash of the CANONICAL spec — the spec re-serialized with sorted keys and no
insignificant whitespace — so two spec files that differ only in key order or formatting are the
SAME job and land on the same address. That property is this unit's whole reason to exist, and
this rewrite preserves it exactly, byte for byte, hash for hash.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and adds the three things #200 requires that the original
lacked: it is a proper installable package, it is driven by a configuration object, and it refuses
to run when it cannot see that configuration.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    _secret(name)   -> str|None   read a value from the secrets file, else the environment
    canonical(spec) -> str        the spec's canonical JSON text (sorted keys, compact)
    job_hash(spec)  -> str        the spec's content address: the hash of `canonical(spec)`
    put(path)       -> None       store the spec in the file at `path`; print its hash
    fetch(h)        -> str        return the canonical spec text stored at hash `h`, verified
    main()          -> int|None   the CLI

The module attributes the original bound at import — `CONG` (the congruency base URL),
`CONGRUENCY_KEY` (the API key) and `_JAIL_PY` (the self-heal interpreter) — still answer, with the
same values. They are served on first touch instead of at import; see LAZY, NOT EAGER.

`main`'s return type is the surface's one addition: the original always returned None (it reported
every error by raising SystemExit, which this rewrite preserves), and None still means success.
It now returns 4 for the one condition the original could not have — no config object. Nothing
else about the surface moved: no parameter was added, removed, renamed or defaulted.

TERMS USED HERE
---------------
spec
    A crank job: any JSON value, normally an object, read from a file by `put`.
canonical spec
    That spec re-serialized deterministically — keys sorted, no space after `,` or `:`. Two
    different-looking files with the same content canonicalize to identical text.
content address / hash
    The hex digest of the canonical spec's UTF-8 bytes. Under the shipped config this is sha256,
    which is what the original hardcoded.
congruency
    The local HTTP service this unit stores jobs in, reached at `CONG` over two routes,
    `job.put` and `job.get`.
registry / config object
    The JSON configuration registry described in this repository's `note-for-claude`: one `.json`
    file holding the configuration for a set of packaged tools. `note-for-claude` states the
    contract this module obeys — "if a tool cannot see the registry it will throw an exeption"
    [sic]. The "config object" is this unit's own `forge2.agent_tools_suite.crank_job` section of
    it. This package ships a `registry.json` beside this file; see CONFIGURATION.
self-heal
    The original's first act: if the jail virtualenv's interpreter exists and is not the one
    running, replace the process with it (`os.execv`) and start over. Preserved; see THE
    DEVIATIONS.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
Every path, URL, route, header, environment-variable name, timeout and algorithm the original
hardcoded is now a config key. The unit resolves its config object from the first source that
answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. That file holds this unit's
     config object itself — exactly what `config_template()` prints.
  2. otherwise, the `forge2.agent_tools_suite.crank_job` section of the nearest `registry.json`
     found by walking UP from THIS FILE's directory.

If NEITHER answers, the unit raises `ConfigError` and does nothing else — it never guesses a
default. That is `note-for-claude`'s rule and this ticket's acceptance item (d). A config object
that is found but is missing a key, or carries a key of the wrong type, is also a `ConfigError`
naming that key.

This package ships `registry.json` NEXT TO this file, so source 2 answers and the unit works from
a clean checkout with no setup. That shipped registry IS the config object this unit runs on; it
is not a fallback baked into the code. Its values are exactly the original's hardcoded ones, which
is what makes this rewrite behavior-preserving in its shipped configuration. Point `FORGE2_CONFIG`
at a file that does not exist (or delete the registry) and the unit throws — the gate is in the
code, not in the file's presence. `selftest()` proves the gate both ways.

The config keys, and the original's value for each:

    jail.python                 "~/jail/.venv/bin/python"
                                The interpreter the CLI self-heals onto. `~` expands. `null`
                                disables self-heal — the original could not be told not to, but a
                                hardcoded path is exactly what #200 forbids, so the path is config
                                and "no path" has to mean something. It means: do not re-exec.
    congruency.url              {"env": "CONGRUENCY_URL", "value": "http://127.0.0.1:8899"}
                                The base URL. The original read the environment variable and fell
                                back to the literal; the variable's NAME is config now, not a
                                literal in the code. `"env": null` pins the URL to `value` and
                                ignores the environment. Trailing `/` are stripped, as before.
    congruency.timeout          5            seconds, passed to urlopen for both routes
    congruency.content_type     "application/json"      the Content-Type header `put` sends
    congruency.api_key_header   "X-Api-Key"             the header the API key is sent in
    congruency.routes.job_put   "/?route=job.put"       appended to the base URL by `put`
    congruency.routes.job_get   "/?route=job.get&hash={hash}"
                                Appended to the base URL by `fetch`. `{hash}` is replaced with the
                                hash LITERALLY and is NOT url-quoted — the original concatenated
                                the hash onto the query string raw, and a hex digest needs no
                                quoting. A template without `{hash}` would silently ask for
                                nothing, so it is a ConfigError.
    secrets.file                "~/.secrets/ats.env"    the KEY=VALUE file `_secret` reads
    secrets.congruency_api_key  "CONGRUENCY_API_KEY"    the name `_secret` is asked for at startup
    canonical.sort_keys         true         }  the three json.dumps arguments that DEFINE
    canonical.separators        [",", ":"]   }  "canonical". The original passed the first two
    canonical.ensure_ascii      true         }  and inherited the third as json's default.
    hash.algorithm              "sha256"     any algorithm `hashlib.new` accepts on this host
    bug_reports                 "logs/bug_reports.jsonl"    see SIDE EFFECTS

`canonical.*` and `hash.algorithm` are config because #200 says no hardcoded params, and a reader
who wants to know what "canonical" and "the hash" mean here should find the answer in the config
object rather than in the code. Changing them changes what address a job gets — they are the
definition of the content address, so the shipped values are the original's and a store must not
change them under a client that has already filed jobs.

WHAT IS *NOT* CONFIG, AND WHY
-----------------------------
#200 requires no hardcoded paths or params. It does not require inventing knobs the unit never had,
and a "knob" that changes what the code MEANS is not a setting:

  * The JSON field names on the wire — `hash` and `spec` in the body `put` POSTs, `rows` and the
    row's `spec` in what `fetch` reads back — stay in the code. They are not policy: they are the
    shape of the `job.put`/`job.get` payloads, and the code that builds and unpacks them is
    written for that shape. A route with a different payload would be a different protocol, not a
    reconfiguration of this one.
  * The messages (`usage: ...`, `no job for hash %s`, `HASH MISMATCH — ...`) stay in the code.
    They are the behavior this ticket preserves — the exemplars assert them verbatim — not
    settings.
  * The structure — that `put` hashes the canonical text and `fetch` re-hashes what came back and
    refuses a mismatch — is the unit's definition. That check is the point of the tool.

THE DEVIATIONS, STATED PLAINLY
------------------------------
1. SELF-HEAL MOVED FROM IMPORT TO `main()`. The original re-exec'd onto `~/jail/.venv/bin/python`
   as a module-level statement, so merely IMPORTING it could replace your process. Here `main()`
   calls `self_heal()` as its first act instead. For the CLI — the only entry the original
   documents — this is exactly equivalent, and the equivalence is a fact about the code, not an
   argument: `os.execv` REPLACES the process image, so nothing computed before it survives, and
   nothing runs between importing this module and `main()` calling `self_heal()`. The re-exec
   still happens before any argument is looked at, exactly as before, and it still re-execs
   `os.path.abspath(__file__)` with `sys.argv[1:]`.

   It cannot be done at import: the interpreter's path is config now, and reading config at import
   would make the module unimportable without a registry (requirement 4 says throw, not guess) —
   so `import crank_job` to call `canonical()` would throw, or worse, silently re-exec your
   process. The one caller that loses something is one that imports the module as a library and
   expects the IMPORT to have moved it onto the jail interpreter. `self_heal()` is exported for
   that caller, and the CLI's behavior is unchanged.

2. EXIT 4 WHEN THERE IS NO CONFIG OBJECT. New, and required by #200 req 4 / acceptance (d). It
   cannot collide with the original's codes, because the original had no config to be missing:
   it exits 0 on success and 1 (via `sys.exit(message)`) on every error it defines.

3. LAZY, NOT EAGER. The original computed `CONG` and `CONGRUENCY_KEY` at import — it read the
   environment and the secrets file while importing. This module computes them on FIRST TOUCH and
   caches, so the values and the once-only sampling are identical but importing touches nothing.
   `reset_config()` drops the cache, which is how a test gets a fresh sample.

There is NO deviation in the CLI's argument surface, deliberately. The original defines an answer
for EVERY argv: fewer than two arguments is the usage message, and any first argument that is not
`put` or `get` is `unknown command`. So there is no spelling — `selftest`, `emit-config`, anything
— that could be added as a subcommand without CHANGING what the original does with that exact
command line. The new capabilities are therefore module functions, not subcommands, and the CLI
answers precisely as the original does. See RUNNING IT for how to invoke them.

RUNNING IT
----------
Every command below is executable as written from THIS FILE's own directory; from anywhere else,
give the full path to `crank_job.py` instead of the bare name.

    python3 crank_job.py put <job.json>   # store the spec; print the hash to refer to it by
    python3 crank_job.py get <hash>       # fetch + print the spec (verifying the hash on the way back)

    # prove this rewrite against the original's behavior — the exemplars, the edges, the gate:
    python3 -c "import sys, crank_job; sys.exit(crank_job.selftest())"

    # print a config-object template (what FORGE2_CONFIG names, and what the registry section is):
    python3 -c "import json, crank_job; print(json.dumps(crank_job.config_template(), indent=2))"

    # show the config object in force and where it came from:
    python3 -c "import json, crank_job; print(crank_job.active_source()); print(json.dumps(crank_job.active_config(), indent=2))"

Installed (see INSTALLABLE), the same three read `from agent_tools_suite.crank_job import ...` and
work from any directory.

Exit codes:

    0  the job was stored / fetched and printed
    1  every error the original defines: no such command, no such job, hash mismatch, and any
       exception it let propagate (an unreadable job file, a spec that is not JSON, congruency
       refusing the connection) — as before, these print a message or a traceback on stderr
    4  no config object; nothing was read, re-exec'd or requested (see CONFIGURATION)

INSTALLABLE (#200 requirement 3)
--------------------------------
This file is one module of the package that surrounds it, and the package is committed in full
beside it — `pyproject.toml`, `__init__.py`, `registry.json` — all DERIVED from the modules
present by `congruency/tools/forge_package.py` (#410), never hand-authored. From THIS file's
directory:

    pip install -e .
    forge2-crank-job put job.json

`pyproject.toml` maps this directory onto the import package `agent_tools_suite`, so an installed
copy imports as `from agent_tools_suite.crank_job import job_hash`, and it declares the
`forge2-crank-job` console script pointing at `main()` below (the generator derives that script
from this module defining a top-level `main`). `registry.json` is package-data, so it lands NEXT
TO this module on a non-editable install too, and the walk-up in CONFIGURATION source 2 finds it
on its first step.

SIDE EFFECTS
------------
Importing this module touches nothing: no config read, no environment read, no file, no network,
and — unlike the original — no re-exec.

`canonical`, `job_hash`, `_secret`, `config_template`, `active_config` and `selftest` create no
files. `selftest` writes only inside a temporary directory it removes, and serves its HTTP on
127.0.0.1 on a kernel-assigned port.

`put` and `fetch` do what they say: `put` POSTs to congruency, `fetch` GETs from it. `main` may
replace the process (self-heal) before either.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception is
thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path when an
exception escapes. Two do not count and file nothing:

  * `SystemExit` — the original's own error reporting (`usage:`, `no job for hash`,
    `HASH MISMATCH`) and its successful return. Filing a report for the tool WORKING would be
    noise.
  * `ConfigError` — the config gate firing is designed behavior, not a defect. It also has, by
    definition, no config to read the report path out of; a tool that tried would replace a clean
    "you have no config object" message with a crash inside its own error handler.

Everything else files a report and is then RE-RAISED UNCHANGED, so the exception, the traceback,
the exit code and stdout are exactly what the original produced — the report is an addition to the
record, never a change to the behavior. Writing the report is itself best-effort: if the
`bug_reports` key is absent, is not a string, or the path cannot be written, the report is dropped
silently rather than masking the exception the tool is trying to report.
"""

import contextlib
import hashlib
import json
import os
import sys
import urllib.request

__all__ = [
    # the original's callable surface
    "_secret", "canonical", "job_hash", "put", "fetch", "main",
    # the config layer (#200 req 4)
    "ConfigError", "find_registry", "load_config", "configure", "using_config", "reset_config",
    "active_config", "active_base", "active_source", "config_template",
    # additions
    "self_heal", "selftest",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename the config walk-up looks for.
REGISTRY_NAME = "registry.json"

#: This unit's own ADDRESS inside the registry document. Not a setting — a config-driven tool has
#: to know which section is its own.
UNIT_PATH = ("forge2", "agent_tools_suite", "crank_job")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:agent_tools_suite/crank_job"

#: The placeholder `congruency.routes.job_get` must contain, replaced with the hash literally.
HASH_PLACEHOLDER = "{hash}"

#: Exit codes. 0 and 1 are the original's (1 is what `sys.exit(message)` produces); 4 is new —
#: see THE DEVIATIONS in the module docstring.
EXIT_OK = 0
EXIT_NO_CONFIG = 4


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a key this unit needs.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that cannot
    see its config throws rather than guessing a default.
    """


# ─────────────────────────────── finding the config object ───────────────────────────────

_ACTIVE = None      # (config, base) injected via configure(); wins over every disk source
_RESOLVED = None    # cache of the last disk resolution
_SETTINGS = None    # the validated settings built from the config in force


def find_registry(start=None):
    """Walk UP from `start` (default: this file's directory) and return the nearest registry path,
    or None if the walk reaches the filesystem root without finding one.

    Starting at THIS FILE, never at the working directory, is deliberate: which congruency this
    unit files jobs into must not depend on where it was launched from. `registry.json` ships as
    package-data, so on an installed copy it sits in this same directory and the first step finds
    it.
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
    """Resolve this unit's config object FROM DISK, ignoring any injected config.

    Returns a `(config, base, source)` triple: the config object, the directory relative paths
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
            "no config object for %s: %s is unset and no %s was found by walking up from %s. "
            "Print a template with: python3 -c \"import json, crank_job; "
            "print(json.dumps(crank_job.config_template(), indent=2))\""
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))))

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. "
                "Add this unit's own section at %s; print it with: python3 -c \"import json, "
                "crank_job; print(json.dumps(crank_job.config_template(), indent=2))\""
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH)))
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError("the registry section %s at %s must be a JSON object, not %s"
                          % (".".join(UNIT_PATH), registry_path, type(node).__name__))

    config = dict(node)
    # The registry's top-level `bug_reports` path is package-wide infrastructure that every module
    # of the package shares; a unit section may state its own to override it. This is inheritance
    # inside ONE config document, not a default guessed by the code.
    if "bug_reports" not in config and "bug_reports" in document:
        config["bug_reports"] = document["bug_reports"]
    return config, os.path.dirname(registry_path), registry_path


def configure(config, base=None):
    """Inject a config object for this process, overriding every disk source.

    `base` is the directory relative paths inside `config` resolve against; it defaults to this
    file's directory. Passing None for `config` clears the injection.
    """
    global _ACTIVE
    _ACTIVE = None if config is None else (
        config, os.path.abspath(base or os.path.dirname(os.path.abspath(__file__))))
    reset_config()


@contextlib.contextmanager
def using_config(config, base=None):
    """Run a block with `config` injected, restoring whatever was in force afterwards."""
    previous = _ACTIVE
    try:
        configure(config, base)
        yield config
    finally:
        globals()["_ACTIVE"] = previous
        reset_config()


def reset_config():
    """Drop every cached resolution, so the next use re-reads the config, the environment and the
    secrets file.

    The original sampled both once, at import. This module samples them once, on first use — this
    is how a test, or a re-configured process, gets a fresh sample.
    """
    global _RESOLVED, _SETTINGS
    _RESOLVED = None
    _SETTINGS = None


def _resolve():
    """The (config, base, source) triple in force: the injected one, else the disk one."""
    global _RESOLVED
    if _ACTIVE is not None:
        return _ACTIVE[0], _ACTIVE[1], "configure()"
    if _RESOLVED is None:
        _RESOLVED = load_config()
    return _RESOLVED


def active_config():
    """The config object in force. Raises ConfigError if there is none."""
    return _resolve()[0]


def active_base():
    """The directory relative paths in the config object resolve against."""
    return _resolve()[1]


def active_source():
    """A human-readable description of where the config object in force came from."""
    return _resolve()[2]


# ─────────────────────────── reading the config object ───────────────────────────

def _need(node, path, where=""):
    """Fetch a required key from the config object, or raise ConfigError naming it."""
    cursor = node
    walked = []
    for key in path:
        walked.append(key)
        if not isinstance(cursor, dict) or key not in cursor:
            raise ConfigError("config object for %s is missing the required key %r%s"
                              % (UNIT, ".".join(walked), " (%s)" % where if where else ""))
        cursor = cursor[key]
    return cursor


def _need_str(node, path, where=""):
    value = _need(node, path, where)
    if not isinstance(value, str):
        raise ConfigError("config key %r for %s must be a string, not %s"
                          % (".".join(path), UNIT, type(value).__name__))
    return value


def _need_bool(node, path, where=""):
    value = _need(node, path, where)
    if not isinstance(value, bool):
        raise ConfigError("config key %r for %s must be true or false, not %s"
                          % (".".join(path), UNIT, type(value).__name__))
    return value


def _need_number(node, path, where=""):
    """A required int-or-float. `bool` is a subclass of int and is NOT a number here."""
    value = _need(node, path, where)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("config key %r for %s must be a number, not %s"
                          % (".".join(path), UNIT, type(value).__name__))
    return value


def _env_setting(node, path, where=""):
    """Resolve an `{"env": NAME|null, "value": V}` setting, reproducing the original's rule.

    The original spelled this `os.environ.get(NAME) or V`, so a variable that is set but EMPTY
    falls back to `V`. That rule is the original's behavior, not a knob: it lives here in the code
    and is proven by `selftest`. Only the variable's NAME and the fallback value are config.
    `"env": null` pins the setting to `value` and ignores the environment entirely.
    """
    spec = _need(node, path, where)
    if not isinstance(spec, dict):
        raise ConfigError(
            'config key %r for %s must be an object like {"env": "NAME", "value": "..."} '
            '(use "env": null to pin the setting and ignore the environment), not %s'
            % (".".join(path), UNIT, type(spec).__name__))
    for key in ("env", "value"):
        if key not in spec:
            raise ConfigError("config key %r for %s must carry a %r key"
                              % (".".join(path), UNIT, key))
    name = spec["env"]
    if name is not None and not isinstance(name, str):
        raise ConfigError("config key %r for %s: 'env' must be an environment variable name or "
                          "null, not %s" % (".".join(path), UNIT, type(name).__name__))
    if not isinstance(spec["value"], str):
        raise ConfigError("config key %r for %s: 'value' must be a string, not %s"
                          % (".".join(path), UNIT, type(spec["value"]).__name__))
    from_env = os.environ.get(name) if name else None
    return from_env if from_env else spec["value"]


def _jail_python(config):
    """The configured self-heal interpreter, `~`-expanded, or None if self-heal is disabled.

    Read on its own, and not as part of the full settings, so that `self_heal()` reads exactly what
    the original read before it re-exec'd — the interpreter path and nothing else. The original
    had not looked at the environment or opened the secrets file at that point either.
    """
    value = _need(config, ("jail", "python"), "the interpreter the CLI self-heals onto")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError("config key 'jail.python' for %s must be a path string or null, not %s"
                          % (UNIT, type(value).__name__))
    return os.path.expanduser(value)


class _Settings(object):
    """The original's import-time constants, computed once from the config object in force.

    The original bound these while importing; this binds them on first use and caches. Same
    values, same once-only sampling of the environment and the secrets file.
    """

    __slots__ = ("cfg", "base", "source", "jail_python", "cong", "timeout", "content_type",
                 "api_key_header", "put_route", "get_route", "secrets_file", "api_key_name",
                 "congruency_key", "sort_keys", "separators", "ensure_ascii", "algorithm")


def _build_settings():
    """Validate the config object and compute every setting the original hardcoded."""
    cfg, base, source = _resolve()
    if not isinstance(cfg, dict):
        raise ConfigError("the config object for %s must be a JSON object, not %s"
                          % (UNIT, type(cfg).__name__))
    s = _Settings()
    s.cfg, s.base, s.source = cfg, base, source

    s.jail_python = _jail_python(cfg)

    # The original: (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")
    s.cong = _env_setting(cfg, ("congruency", "url"), "the congruency base URL").rstrip("/")
    s.timeout = _need_number(cfg, ("congruency", "timeout"), "seconds")
    s.content_type = _need_str(cfg, ("congruency", "content_type"))
    s.api_key_header = _need_str(cfg, ("congruency", "api_key_header"))
    s.put_route = _need_str(cfg, ("congruency", "routes", "job_put"))
    s.get_route = _need_str(cfg, ("congruency", "routes", "job_get"))
    if HASH_PLACEHOLDER not in s.get_route:
        raise ConfigError("config key 'congruency.routes.job_get' for %s must contain the %s "
                          "placeholder — without it the hash would never reach congruency and "
                          "every `get` would ask for the wrong job (got %r)"
                          % (UNIT, HASH_PLACEHOLDER, s.get_route))

    s.secrets_file = os.path.expanduser(_need_str(cfg, ("secrets", "file")))
    s.api_key_name = _need_str(cfg, ("secrets", "congruency_api_key"))

    s.sort_keys = _need_bool(cfg, ("canonical", "sort_keys"))
    separators = _need(cfg, ("canonical", "separators"), "the [item, key] JSON separators")
    if not isinstance(separators, list) or len(separators) != 2 or \
            not all(isinstance(x, str) for x in separators):
        raise ConfigError("config key 'canonical.separators' for %s must be a list of exactly two "
                          'strings, the item and key separators (the original\'s: [",", ":"])'
                          % UNIT)
    s.separators = (separators[0], separators[1])
    s.ensure_ascii = _need_bool(cfg, ("canonical", "ensure_ascii"))

    s.algorithm = _need_str(cfg, ("hash", "algorithm"))
    try:
        hashlib.new(s.algorithm)
    except (ValueError, TypeError) as exc:
        raise ConfigError("config key 'hash.algorithm' for %s names %r, which this host's hashlib "
                          "cannot provide: %s" % (UNIT, s.algorithm, exc)) from exc

    # The original computed this at import, right after CONG. Same single read.
    s.congruency_key = _read_secret(s.secrets_file, s.api_key_name)
    return s


def _settings():
    """The settings in force, built once per config. Raises ConfigError without a config object."""
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = _build_settings()
    return _SETTINGS


def config_template():
    """Return a fresh config object holding EXACTLY the values the original hardcoded.

    This is what `FORGE2_CONFIG` may name, and what this unit's `forge2.agent_tools_suite.crank_job`
    section of the package registry contains. It is returned by a function, not read from the code
    as a default: nothing in this module falls back to it, and a caller must install it somewhere
    the resolution in CONFIGURATION can see before the unit will run.
    """
    return {
        "_comment": "Config object for %s — the forge2 rewrite of agent_tools_suite:crank_job "
                    "(#420, standard #200). Every value here is the one the original hardcoded." % UNIT,
        "jail": {"python": "~/jail/.venv/bin/python"},
        "congruency": {
            "url": {"env": "CONGRUENCY_URL", "value": "http://127.0.0.1:8899"},
            "timeout": 5,
            "content_type": "application/json",
            "api_key_header": "X-Api-Key",
            "routes": {"job_put": "/?route=job.put", "job_get": "/?route=job.get&hash={hash}"},
        },
        "secrets": {"file": "~/.secrets/ats.env", "congruency_api_key": "CONGRUENCY_API_KEY"},
        "canonical": {"sort_keys": True, "separators": [",", ":"], "ensure_ascii": True},
        "hash": {"algorithm": "sha256"},
    }


# ─────────── the original's import-time module attributes, served on first touch ───────────

#: Maps each module attribute the original bound at import onto its settings field. PEP 562's
#: module __getattr__ serves them, so `crank_job.CONG` still answers — and now throws ConfigError
#: instead of guessing when there is no config object.
_MODULE_ATTRS = {"CONG": "cong", "CONGRUENCY_KEY": "congruency_key"}


def __getattr__(name):
    """Serve the original's import-time module attributes on first touch (PEP 562).

    The original bound these while importing. Binding them here instead keeps the values identical
    and the import side-effect-free — see LAZY, NOT EAGER in the module docstring.
    """
    if name in _MODULE_ATTRS:
        return getattr(_settings(), _MODULE_ATTRS[name])
    if name == "_JAIL_PY":
        return _jail_python(active_config())
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(list(globals()) + list(_MODULE_ATTRS) + ["_JAIL_PY"])


# ═══════════════════════════════ the unit itself ═══════════════════════════════

def self_heal():
    """Replace this process with the configured jail interpreter, if that is not already the one
    running it. Returns None; on a re-exec it does not return at all.

    This is the original's first act, preserved. It re-execs THIS file by absolute path with the
    same arguments, so the fresh interpreter runs the same command; the new process finds itself
    already on the jail interpreter and carries on. `jail.python` of null disables it.

    Reading only `jail.python` (not the whole settings) keeps the original's ordering: the
    environment and the secrets file were not touched before the re-exec either.
    """
    jail = _jail_python(active_config())
    if jail and os.path.exists(jail) and \
            os.path.realpath(sys.executable) != os.path.realpath(jail):
        os.execv(jail, [jail, os.path.abspath(__file__), *sys.argv[1:]])


def _read_secret(path, name):
    """The body of `_secret`, taking the secrets file path explicitly.

    Split out so `_build_settings` can read the API key while the settings are still being built,
    without `_secret` having to grow a parameter the ticket's callable surface does not have.

    The rule, which is the original's exactly: the file is read line by line and the FIRST line
    that literally starts with `name=` wins. The match is against the RAW line, so a line that is
    indented does NOT match — leading whitespace is not stripped before the test. The value is
    everything after the first `=` of the STRIPPED line, so `K=a=b` yields `a=b`, a trailing
    newline never reaches the value, and `K=` yields `""`. If the file does not exist, or exists
    with no matching line, the process environment answers instead, and `None` means neither had
    it.
    """
    if os.path.isfile(path):
        with open(path) as handle:
            for line in handle:
                if line.startswith(name + "="):
                    return line.strip().split("=", 1)[1]
    return os.environ.get(name)


def _secret(name):
    """Read `name` from the configured secrets file (KEY=VALUE), else the process environment.

    Returns None when neither has it — which is why the API key header is sent as `""` rather
    than omitted. See `_read_secret` for the exact matching rule.
    """
    return _read_secret(_settings().secrets_file, name)


def _hash_text(text):
    """The content address of `text`: the configured algorithm over its UTF-8 bytes, hex."""
    return hashlib.new(_settings().algorithm, text.encode()).hexdigest()


def canonical(spec):
    """Return the canonical JSON text of `spec`: sorted keys, compact separators.

    This is the serialization the content address is taken over, so two specs that differ only in
    key order or whitespace produce identical text and therefore the same hash.
    """
    s = _settings()
    return json.dumps(spec, sort_keys=s.sort_keys, separators=s.separators,
                      ensure_ascii=s.ensure_ascii)


def job_hash(spec):
    """Return the content address of `spec`: the hash of its canonical text."""
    return _hash_text(canonical(spec))


def put(path):
    """Store the spec in the JSON file at `path` on congruency; print the hash it is filed under.

    `~` in `path` is expanded; a relative path is resolved by the operating system against the
    working directory, not against the config. The hash is computed over the canonical text and
    the canonical TEXT — not the file's bytes — is what is stored, so the store holds one
    byte-exact spec per address.
    """
    s = _settings()
    with open(os.path.expanduser(path)) as handle:
        spec = json.load(handle)
    canon = canonical(spec)
    h = _hash_text(canon)
    body = json.dumps({"hash": h, "spec": canon}).encode()
    request = urllib.request.Request(
        s.cong + s.put_route, data=body, method="POST",
        headers={"Content-Type": s.content_type, s.api_key_header: s.congruency_key or ""})
    with urllib.request.urlopen(request, timeout=s.timeout) as response:
        response.read()
    print(h)


def fetch(h):
    """Return the canonical spec text stored at hash `h`, verifying its content address first.

    Raises SystemExit (exit 1, the original's reporting) if congruency has no job at that hash, or
    if what came back does not hash to `h` — the check the whole content-addressed idea rests on:
    a store that hands back something else is caught here rather than trusted.
    """
    s = _settings()
    url = s.cong + s.get_route.replace(HASH_PLACEHOLDER, h)
    with urllib.request.urlopen(url, timeout=s.timeout) as response:
        rows = json.loads(response.read().decode() or "{}").get("rows") or []
    if not rows:
        sys.exit("no job for hash %s" % h)
    spec = rows[0]["spec"]
    if _hash_text(spec) != h:
        sys.exit("HASH MISMATCH — stored spec does not content-address to %s" % h)
    return spec


def _file_bug_report(exc):
    """Append one JSON line about `exc` to the config's `bug_reports` path — best effort.

    Best effort is the whole contract: this runs while an exception is already on its way out, and
    an error in HERE would replace the tool's real failure with a crash in its own reporter. So a
    missing, non-string or unwritable `bug_reports` path drops the report and changes nothing the
    caller sees.
    """
    try:
        import datetime
        import traceback
        config, base = _resolve()[0], _resolve()[1]
        path = config.get("bug_reports")
        if not isinstance(path, str) or not path:
            return
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(base, path)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        record = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "unit": UNIT,
            "tool": os.path.abspath(__file__),
            "argv": list(sys.argv),
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": "".join(traceback.format_exception(type(exc), exc,
                                                            exc.__traceback__)).strip(),
        }
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except Exception:
        return


def _dispatch():
    """The original's `main` body: self-heal, then run the command in argv."""
    self_heal()
    if len(sys.argv) < 3:
        sys.exit("usage: crank_job.py {put <file.json> | get <hash>}")
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "put":
        put(arg)
    elif cmd == "get":
        print(fetch(arg))
    else:
        sys.exit("unknown command %r" % cmd)


def main():
    """The CLI: `crank_job.py {put <file.json> | get <hash>}`, reading `sys.argv` as the original
    did.

    Returns None on success (so `sys.exit(main())` exits 0, and the generated console script does
    too) and 4 when there is no config object. Every error the original defines still raises
    SystemExit with the original's message and exit code 1.
    """
    try:
        _dispatch()
    except ConfigError as exc:
        sys.stderr.write("crank_job: %s\n" % exc)
        return EXIT_NO_CONFIG
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:                 # noqa: BLE001 — reported, then re-raised as-is
        _file_bug_report(exc)
        raise
    return None


# ═══════════════════════════════ selftest ═══════════════════════════════

def selftest():
    """Prove this rewrite against the original's behavior. Returns 0 if every check passes, 1 if
    any fails. Creates no file outside a temporary directory it removes.

    The expected values below are not invented: they were taken from the ORIGINAL module — the
    2733-byte blob 79c284710a05953c9acc70f619991d2df7f4de5e named in this ticket, rebuilt from the
    ticket's embedded source and confirmed byte-identical by its git blob hash — and this test
    asserts this rewrite reproduces them.
    """
    import http.server
    import shutil
    import subprocess
    import tempfile
    import threading

    failures = []
    checks = [0]

    def check(ok, label):
        checks[0] += 1
        print(("PASS  " if ok else "FAIL  ") + label)
        if not ok:
            failures.append(label)

    def check_eq(got, want, label):
        if got == want:
            check(True, label)
        else:
            check(False, "%s\n        got : %r\n        want: %r" % (label, got, want))

    def io_capture(call):
        """Run `call`, returning everything it printed to stdout."""
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            call()
        return buffer.getvalue()

    def exit_of(call):
        """Run `call` and return the message its SystemExit carried, or None."""
        try:
            call()
        except SystemExit as exc:
            return exc.code
        return None

    @contextlib.contextmanager
    def congruency(get_body=b'{"rows":[]}'):
        """A real HTTP congruency stand-in on 127.0.0.1; yields (base_url, requests)."""
        seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *_args):
                pass

            def _reply(self, body):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                seen.append({"method": "GET", "path": self.path,
                             "headers": {k.lower(): v for k, v in self.headers.items()},
                             "body": None})
                self._reply(get_body() if callable(get_body) else get_body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                seen.append({"method": "POST", "path": self.path,
                             "headers": {k.lower(): v for k, v in self.headers.items()},
                             "body": self.rfile.read(length)})
                self._reply(b'{"ok":true}')

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield "http://127.0.0.1:%d" % server.server_port, seen
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def pinned(url):
        """The template config, pinned to `url` and to no self-heal — the shipped values otherwise.

        Pinned so these checks cannot be steered by an ambient CONGRUENCY_URL, and so they never
        re-exec the test process onto a jail interpreter.
        """
        cfg = config_template()
        cfg["jail"]["python"] = None
        cfg["congruency"]["url"] = {"env": None, "value": url}
        return cfg

    print("== %s selftest ==" % UNIT)
    print("   module   : %s" % os.path.abspath(__file__))
    try:
        print("   config   : %s" % active_source())
    except ConfigError as exc:
        print("   config   : NONE (%s)" % exc)

    tmp = tempfile.mkdtemp(prefix="crank-job-selftest-")
    saved_environ = dict(os.environ)
    saved_active = _ACTIVE
    try:
        # ── 1. the callable surface (acceptance b) ──────────────────────────────────────────
        import inspect
        surface = {
            "_secret": ["name"], "canonical": ["spec"], "job_hash": ["spec"],
            "put": ["path"], "fetch": ["h"], "main": [],
        }
        for name, params in surface.items():
            func = globals().get(name)
            ok = callable(func) and \
                list(inspect.signature(func).parameters) == params and \
                all(p.default is inspect.Parameter.empty
                    for p in inspect.signature(func).parameters.values())
            check(ok, "surface: %s(%s) present with the original's parameters and no defaults"
                      % (name, ", ".join(params)))

        # ── 2. canonical() + job_hash(): exemplars taken from the original ──────────────────
        # (spec, canonical text, hash) triples produced by the verified original blob.
        exemplars = [
            ({"b": 1, "a": 2}, '{"a":2,"b":1}',
             "d3626ac30a87e6f7a6428233b3c68299976865fa5508e4267c5415c76af7a772"),
            ({"a": 1}, '{"a":1}',
             "015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862"),
            ({}, "{}",
             "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"),
            ({"z": [3, 2, 1], "y": {"n": None, "m": True}}, '{"y":{"m":true,"n":null},"z":[3,2,1]}',
             "e839e00a7e4c6df5e24f08f270c0290edba9cb149454501e9c5bd8eda0023ab2"),
            ({"k": "café — naïve"}, '{"k":"caf\\u00e9 \\u2014 na\\u00efve"}',
             "d5b2e031f2e4338f59627a1e98e43fc781d378500e5d29b37a43b66855ab04a3"),
            ({"nested": {"b": 2, "a": 1}, "arr": [{"q": 1, "p": 2}]},
             '{"arr":[{"p":2,"q":1}],"nested":{"a":1,"b":2}}',
             "e9df9463903c2272aa7a5316561626f30f59f9f6da4a5f15624fd733becc04bf"),
            ([1, 2, 3], "[1,2,3]",
             "a615eeaee21de5179de080de8c3052c8da901138406ba71c38c032845f7d54f4"),
            ("bare string", '"bare string"',
             "707207bc9187da639d9321e37a1c1d7782b39758e5dd8eff7a72c7cc815a4452"),
            (42, "42",
             "73475cb40a568e8da8a045ced110137e159f890ac4da883b6b17dc651b3a8049"),
            ({"a": 1.5, "b": 1e300}, '{"a":1.5,"b":1e+300}',
             "4ca5b2ef0d27229d633745cfd694fc55e5d536aace090438c5e3a029dd24efcf"),
        ]
        with using_config(pinned("http://127.0.0.1:1")):
            for spec, text, digest in exemplars:
                check_eq(canonical(spec), text, "canonical(%r)" % (spec,))
                check_eq(job_hash(spec), digest, "job_hash(%r)" % (spec,))

            # the module docstring's central promise: same job, same address, whatever the file
            # looked like
            left = json.loads('{"a":1,"b":[2,3]}')
            right = json.loads('{ "b" : [ 2 , 3 ] ,\n  "a" : 1 }')
            check(job_hash(left) == job_hash(right) ==
                  "efbd0040190fb0871831e606c581f8a66db79d8e2bb836745a70051306956070",
                  "job_hash ignores key order and whitespace (the content-address promise)")
            check_eq(job_hash({"a": 1}), _hash_text(canonical({"a": 1})),
                     "job_hash(spec) is exactly hash(canonical(spec))")

        # ── 3. _secret(): every rule of the original's parser ───────────────────────────────
        secrets = os.path.join(tmp, "ats.env")
        cfg = pinned("http://127.0.0.1:1")
        cfg["secrets"]["file"] = secrets
        os.environ.pop("CONGRUENCY_API_KEY", None)

        with open(secrets, "w") as fh:
            fh.write("OTHER=1\nCONGRUENCY_API_KEY=k=v\nCONGRUENCY_API_KEY=second\n")
        with using_config(cfg):
            check_eq(_secret("CONGRUENCY_API_KEY"), "k=v",
                     "_secret: the FIRST matching line wins, and the value keeps its own '='")
            check_eq(_secret("OTHER"), "1", "_secret: any name, not just the API key")
            check_eq(_secret("ABSENT"), None,
                     "_secret: a name in neither the file nor the environment is None")

        with open(secrets, "w") as fh:
            fh.write("CONGRUENCY_API_KEY=  padded  \n")
        with using_config(cfg):
            check_eq(_secret("CONGRUENCY_API_KEY"), "  padded",
                     "_secret: the LINE is stripped, so trailing blanks go and inner ones stay")

        with open(secrets, "w") as fh:
            fh.write("  CONGRUENCY_API_KEY=indented\n")
        os.environ["CONGRUENCY_API_KEY"] = "from-env"
        with using_config(cfg):
            check_eq(_secret("CONGRUENCY_API_KEY"), "from-env",
                     "_secret: an INDENTED line does not match (the raw line is tested), so the "
                     "environment answers")

        with open(secrets, "w") as fh:
            fh.write("CONGRUENCY_API_KEY_EXTRA=no\nNOTCONGRUENCY_API_KEY=no\n")
        with using_config(cfg):
            check_eq(_secret("CONGRUENCY_API_KEY"), "from-env",
                     "_secret: a name that merely CONTAINS or extends the key does not match")

        with open(secrets, "w") as fh:
            fh.write("CONGRUENCY_API_KEY=\n")
        with using_config(cfg):
            check_eq(_secret("CONGRUENCY_API_KEY"), "",
                     "_secret: 'K=' is the empty string (falsy -> the header is sent empty)")

        os.remove(secrets)
        with using_config(cfg):
            check_eq(_secret("CONGRUENCY_API_KEY"), "from-env",
                     "_secret: no secrets file at all -> the environment answers")
        os.environ.pop("CONGRUENCY_API_KEY", None)
        with using_config(cfg):
            check_eq(_secret("CONGRUENCY_API_KEY"), None,
                     "_secret: no file and no variable -> None")

        # ── 4. CONG: the original's `os.environ.get(...) or default`, then rstrip("/") ──────
        os.environ.pop("CONGRUENCY_URL", None)
        base_cfg = config_template()
        base_cfg["jail"]["python"] = None
        base_cfg["secrets"]["file"] = os.path.join(tmp, "none.env")
        with using_config(base_cfg):
            check_eq(_settings().cong, "http://127.0.0.1:8899",
                     "CONG: unset CONGRUENCY_URL -> the config value (the original's default)")
        os.environ["CONGRUENCY_URL"] = "http://example:9///"
        with using_config(base_cfg):
            check_eq(_settings().cong, "http://example:9",
                     "CONG: a set CONGRUENCY_URL wins and is rstrip('/')ed")
        os.environ["CONGRUENCY_URL"] = ""
        with using_config(base_cfg):
            check_eq(_settings().cong, "http://127.0.0.1:8899",
                     "CONG: a BLANK CONGRUENCY_URL falls back to the config value (the `or` rule)")
        os.environ.pop("CONGRUENCY_URL", None)
        pinned_cfg = dict(base_cfg)
        pinned_cfg["congruency"] = dict(base_cfg["congruency"],
                                        url={"env": None, "value": "http://pinned:1/"})
        os.environ["CONGRUENCY_URL"] = "http://ignored:2"
        with using_config(pinned_cfg):
            check_eq(_settings().cong, "http://pinned:1",
                     'CONG: "env": null pins the URL and ignores the environment')
        os.environ.pop("CONGRUENCY_URL", None)

        # ── 5. put(): the real request the original sends ───────────────────────────────────
        job = os.path.join(tmp, "job.json")
        with open(job, "w") as fh:
            fh.write('{\n  "b": 1,\n  "a": 2\n}\n')          # deliberately unordered + spaced
        with congruency() as (url, seen):
            cfg = pinned(url)
            cfg["secrets"]["file"] = os.path.join(tmp, "none.env")
            with using_config(cfg):
                out = io_capture(lambda: put(job))
            check_eq(out, "d3626ac30a87e6f7a6428233b3c68299976865fa5508e4267c5415c76af7a772\n",
                     "put: prints the hash of the CANONICAL spec, not of the file's bytes")
            check_eq(len(seen), 1, "put: sends exactly one request")
            req = seen[0]
            check_eq(req["method"], "POST", "put: POSTs")
            check_eq(req["path"], "/?route=job.put", "put: to the job.put route")
            check_eq(req["headers"].get("content-type"), "application/json",
                     "put: with the configured Content-Type")
            check_eq(req["headers"].get("x-api-key"), "",
                     "put: with an EMPTY X-Api-Key when there is no secret (the `or \"\"` rule)")
            body = json.loads(req["body"].decode())
            check_eq(sorted(body), ["hash", "spec"], "put: body carries exactly hash + spec")
            check_eq(body["spec"], '{"a":2,"b":1}',
                     "put: stores the CANONICAL text (sorted, compact), not the file")
            check_eq(body["hash"], job_hash({"a": 2, "b": 1}),
                     "put: body hash == job_hash(spec)")

        # the API key, when there IS one
        with open(secrets, "w") as fh:
            fh.write("CONGRUENCY_API_KEY=s3cret\n")
        with congruency() as (url, seen):
            cfg = pinned(url)
            cfg["secrets"]["file"] = secrets
            with using_config(cfg):
                io_capture(lambda: put(job))
            check_eq(seen[0]["headers"].get("x-api-key"), "s3cret",
                     "put: sends the secrets-file API key")
        os.remove(secrets)

        # `~` in the job path is expanded
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        shutil.copyfile(job, os.path.join(home, "job.json"))
        os.environ["HOME"] = home
        with congruency() as (url, seen):
            cfg = pinned(url)
            cfg["secrets"]["file"] = os.path.join(tmp, "none.env")
            with using_config(cfg):
                out = io_capture(lambda: put("~/job.json"))
            check_eq(out, "d3626ac30a87e6f7a6428233b3c68299976865fa5508e4267c5415c76af7a772\n",
                     "put: expands `~` in the job path")
        os.environ["HOME"] = saved_environ.get("HOME", home)

        # ── 6. fetch(): the round trip, and the verification that is the point of it ────────
        canon = '{"a":2,"b":1}'
        digest = job_hash({"a": 2, "b": 1})
        with congruency(get_body=json.dumps({"rows": [{"spec": canon}]}).encode()) as (url, seen):
            cfg = pinned(url)
            cfg["secrets"]["file"] = os.path.join(tmp, "none.env")
            with using_config(cfg):
                check_eq(fetch(digest), canon, "fetch: returns the stored canonical spec")
            check_eq(seen[0]["method"], "GET", "fetch: GETs")
            check_eq(seen[0]["path"], "/?route=job.get&hash=" + digest,
                     "fetch: to the job.get route with the hash appended raw")

        with congruency(get_body=b'{"rows":[]}') as (url, _seen):
            cfg = pinned(url)
            cfg["secrets"]["file"] = os.path.join(tmp, "none.env")
            with using_config(cfg):
                code = exit_of(lambda: fetch(digest))
            check_eq(code, "no job for hash " + digest,
                     "fetch: no rows -> SystemExit('no job for hash <h>')")

        with congruency(get_body=b"") as (url, _seen):
            cfg = pinned(url)
            cfg["secrets"]["file"] = os.path.join(tmp, "none.env")
            with using_config(cfg):
                code = exit_of(lambda: fetch(digest))
            check_eq(code, "no job for hash " + digest,
                     "fetch: an EMPTY response body reads as {} -> the same no-job exit")

        with congruency(get_body=b'{"rows":[{"spec":"{}"}]}') as (url, _seen):
            cfg = pinned(url)
            cfg["secrets"]["file"] = os.path.join(tmp, "none.env")
            with using_config(cfg):
                code = exit_of(lambda: fetch(digest))
            check_eq(code, "HASH MISMATCH — stored spec does not content-address to " + digest,
                     "fetch: a spec that does not hash to the address is REFUSED, verbatim")

        # ── 7. the CLI, end to end, as a real subprocess ────────────────────────────────────
        env = dict(saved_environ)
        env.pop("FORGE2_CONFIG", None)
        env.pop("CONGRUENCY_API_KEY", None)
        env["HOME"] = home                       # no ~/jail interpreter, no ~/.secrets/ats.env
        me = os.path.abspath(__file__)

        def run(args, extra=None):
            e = dict(env)
            e.update(extra or {})
            return subprocess.run([sys.executable, me] + args, env=e, cwd=tmp,
                                  capture_output=True, text=True)

        r = run([])
        check(r.returncode == 1 and
              r.stderr.strip() == "usage: crank_job.py {put <file.json> | get <hash>}",
              "CLI: no arguments -> the original's usage line, exit 1  [%r]" % r.stderr.strip())
        r = run(["put"])
        check(r.returncode == 1 and
              r.stderr.strip() == "usage: crank_job.py {put <file.json> | get <hash>}",
              "CLI: one argument -> the same usage line, exit 1  [%r]" % r.stderr.strip())
        r = run(["frobnicate", "x"])
        check(r.returncode == 1 and r.stderr.strip() == "unknown command 'frobnicate'",
              "CLI: an unknown command -> unknown command %r, exit 1  [%r]"
              % ("frobnicate", r.stderr.strip()))
        r = run(["selftest"])
        check(r.returncode == 1 and
              r.stderr.strip() == "usage: crank_job.py {put <file.json> | get <hash>}",
              "CLI: `selftest` is NOT a subcommand — the original prints usage for any two-word "
              "command line, and so does this  [%r]" % r.stderr.strip())

        with congruency() as (url, seen):
            r = run(["put", job], {"CONGRUENCY_URL": url})
            check(r.returncode == 0 and
                  r.stdout == "d3626ac30a87e6f7a6428233b3c68299976865fa5508e4267c5415c76af7a772\n",
                  "CLI: `put job.json` prints the hash, exit 0  [%r/%r]" % (r.stdout, r.stderr))
            check_eq(len(seen), 1, "CLI: `put` sent one POST")

        with congruency(get_body=json.dumps({"rows": [{"spec": canon}]}).encode()) as (url, seen):
            r = run(["get", digest], {"CONGRUENCY_URL": url})
            check(r.returncode == 0 and r.stdout == canon + "\n",
                  "CLI: `get <hash>` prints the spec, exit 0  [%r/%r]" % (r.stdout, r.stderr))

        # ── 8. the config gate (acceptance d): throws, never guesses ────────────────────────
        missing = os.path.join(tmp, "no-such-config.json")
        r = run(["put", job], {"FORGE2_CONFIG": missing})
        check(r.returncode == EXIT_NO_CONFIG and "no such file exists" in r.stderr and
              "Traceback" not in r.stderr,
              "gate: FORGE2_CONFIG naming a missing file -> exit 4, one line, no traceback  [%r]"
              % r.stderr.strip())

        empty = os.path.join(tmp, "empty-registry.json")
        with open(empty, "w") as fh:
            json.dump({"schema": 1, "forge2": {"agent_tools_suite": {}}}, fh)
        r = run(["put", job], {"FORGE2_CONFIG": empty})
        check(r.returncode == EXIT_NO_CONFIG or r.returncode == 4,
              "gate: a config object with none of this unit's keys -> exit 4, not a guess  [%r]"
              % r.stderr.strip())

        os.environ[CONFIG_ENV] = missing
        try:
            configure(None)
            for name, call in (("canonical", lambda: canonical({"a": 1})),
                               ("job_hash", lambda: job_hash({"a": 1})),
                               ("_secret", lambda: _secret("CONGRUENCY_API_KEY")),
                               ("put", lambda: put(job)),
                               ("fetch", lambda: fetch(digest)),
                               ("CONG", lambda: globals()["__getattr__"]("CONG"))):
                raised = False
                try:
                    call()
                except ConfigError:
                    raised = True
                except Exception:
                    pass
                check(raised, "gate: %s() throws ConfigError with no config object, rather than "
                              "guessing a default" % name)
        finally:
            os.environ.pop(CONFIG_ENV, None)
            reset_config()

        report = os.path.join(tmp, "reports", "bug_reports.jsonl")
        r = run(["put", job], {"FORGE2_CONFIG": missing})
        check(not os.path.exists(report),
              "gate: the config gate files NO bug report (it is designed behavior, not a defect)")

        # ── 9. the bug report: filed on a real fault, and never masking it ──────────────────
        gone = os.path.join(tmp, "no-such-job.json")
        cfg_path = os.path.join(tmp, "cfg-report.json")
        cfg = pinned("http://127.0.0.1:1")
        cfg["bug_reports"] = report
        with open(cfg_path, "w") as fh:
            json.dump(cfg, fh)
        r = run(["put", gone], {"FORGE2_CONFIG": cfg_path})
        check(r.returncode == 1 and "FileNotFoundError" in r.stderr,
              "fault: a missing job file propagates as the original let it — traceback, exit 1"
              "  [%r]" % r.returncode)
        check(os.path.isfile(report) and len(open(report).read().strip().splitlines()) == 1,
              "fault: exactly one bug report line was filed for it")
        if os.path.isfile(report):
            entry = json.loads(open(report).read().strip().splitlines()[0])
            check(entry.get("unit") == UNIT and "FileNotFoundError" in entry.get("error", ""),
                  "fault: the report names this unit and the error")

        cfg["bug_reports"] = 17                  # a non-string path must not mask the fault
        with open(cfg_path, "w") as fh:
            json.dump(cfg, fh)
        r = run(["put", gone], {"FORGE2_CONFIG": cfg_path})
        check(r.returncode == 1 and "FileNotFoundError" in r.stderr and
              "TypeError" not in r.stderr,
              "fault: a bug_reports path of the wrong type drops the report and does NOT replace "
              "the real exception  [%r]" % r.returncode)

        # ── 10. self_heal(): the original's re-exec, and its off switch ─────────────────────
        fake_python = os.path.join(tmp, "fake-python")
        with open(fake_python, "w") as fh:
            fh.write("#!/bin/sh\necho \"SELF-HEALED $*\"\n")
        os.chmod(fake_python, 0o755)
        cfg = pinned("http://127.0.0.1:1")
        cfg["jail"]["python"] = fake_python
        with open(cfg_path, "w") as fh:
            json.dump(cfg, fh)
        r = run(["put", job], {"FORGE2_CONFIG": cfg_path})
        check(r.returncode == 0 and r.stdout.startswith("SELF-HEALED ") and
              me in r.stdout and r.stdout.strip().endswith("put " + job),
              "self_heal: re-execs the configured interpreter with THIS file and the same "
              "arguments  [%r]" % r.stdout.strip())

        cfg["jail"]["python"] = os.path.join(tmp, "no-such-interpreter")
        with open(cfg_path, "w") as fh:
            json.dump(cfg, fh)
        with congruency() as (url, seen):
            cfg["congruency"]["url"] = {"env": None, "value": url}
            with open(cfg_path, "w") as fh:
                json.dump(cfg, fh)
            r = run(["put", job], {"FORGE2_CONFIG": cfg_path})
            check(r.returncode == 0 and len(seen) == 1,
                  "self_heal: an interpreter that does not exist is skipped, as the original "
                  "skipped a missing jail venv  [%r/%r]" % (r.stdout, r.stderr))

        cfg["jail"]["python"] = None
        with open(cfg_path, "w") as fh:
            json.dump(cfg, fh)
        with congruency() as (url, seen):
            cfg["congruency"]["url"] = {"env": None, "value": url}
            with open(cfg_path, "w") as fh:
                json.dump(cfg, fh)
            r = run(["put", job], {"FORGE2_CONFIG": cfg_path})
            check(r.returncode == 0 and len(seen) == 1,
                  'self_heal: "python": null disables it  [%r/%r]' % (r.stdout, r.stderr))

        # ── 11. the shipped registry IS the original's configuration ────────────────────────
        configure(None)
        os.environ.pop(CONFIG_ENV, None)
        reset_config()
        try:
            shipped = load_config()[0]
            template = config_template()
            del template["_comment"]
            trimmed = {k: v for k, v in shipped.items() if k not in ("_comment", "bug_reports")}
            check_eq(trimmed, template,
                     "shipped: the registry section beside this file holds exactly the original's "
                     "hardcoded values")
        except ConfigError as exc:
            check(False, "shipped: this package's registry.json answers for this unit (%s)" % exc)
    finally:
        os.environ.clear()
        os.environ.update(saved_environ)
        globals()["_ACTIVE"] = saved_active
        reset_config()
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d checks, %d failed" % (checks[0], len(failures)))
    for label in failures:
        print("  FAILED: %s" % label.splitlines()[0])
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
