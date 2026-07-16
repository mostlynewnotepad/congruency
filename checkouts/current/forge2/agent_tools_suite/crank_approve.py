#!/usr/bin/env python3
"""forge2 / agent_tools_suite / crank_approve — a behavior-preserving rewrite of the forge unit
`agent_tools_suite:crank_approve.py` (module key forge-rw:2aa9706d7f7163b0), filed under ticket
#418 against the FORGE-wide refactor standard #200.

WHAT THIS IS
------------
The original forge unit was a 4882-byte command-line tool: the HUMAN side of crank approval. An
agent cannot approve a crank because it has no wallet; a human running this tool IS the approval.
The tool reads a ticket's content digest from crankd, shows the operator the ticket, signs that
digest with the wallet's approver key, checks the signature locally, and POSTs it to congruency.

This file is an entirely new implementation of that unit. It keeps the original's observable
behavior and its callable surface, and adds the three things #200 requires that the original
lacked: it is a proper installable package, it is driven by a configuration object, and it refuses
to run when it cannot see that configuration.

TERMS USED HERE (defined at first use, for a reader who has never seen this system)
-----------------------------------------------------------------------------------
crankd
    The daemon that runs "cranks" (privileged operations). It is the SINGLE digest authority: this
    tool asks crankd for the digest rather than computing one, so the two cannot drift apart.
congruency
    The ticket store. This tool reads a ticket from it for display and POSTs the signature back.
the wallet
    An external binary that derives named ssh keys on demand. This tool shells out to it to get the
    approver's private key; it never stores one.
the digest
    An opaque string identifying a ticket's exact content. Signing it is what "approval" means.
the jail venv
    A Python virtual environment that has the `cryptography` library installed. The original
    "self-heals" into it — see THE RE-EXEC below, which is this module's most consequential
    behavior.
registry
    The JSON configuration registry described in this repository's `note-for-claude`: one `.json`
    file in the package root holding the configuration for every tool in the package, which
    registry-gated tools walk UP the tree to find and "throw" if they cannot see. This package
    ships its own at `registry.json`, beside this file.
config object
    The chunk of that registry belonging to this unit — the `forge2.agent_tools_suite.crank_approve`
    section. It is what drives this module. `config_template()` prints a template of it.
exemplar
    A real (input, output) pair taken from the ORIGINAL acting as the oracle — #200's "verified,
    not asserted". `selftest()` replays them.

THE CALLABLE SURFACE (unchanged, so existing callers keep working)
-----------------------------------------------------------------
    _secret(name)      _get(url)      _cong_post(path, obj)
    sign_digest(digest_str)           verifies_locally(digest_str, sig_hex)          main()

The original's module-level CONSTANTS are preserved as module attributes too — `CRANKD`, `CONG`,
`WALLET`, `APPROVER`, `CONGRUENCY_KEY`, `APPROVER_PUBKEY` — because `_cong_post()` and
`verifies_locally()` read them at CALL time, so a caller that assigns `crank_approve.CONG = "..."`
changes where the POST goes. That is the original's behavior and it still works here: these are
real module globals, set once at import, not properties.

THE RE-EXEC — read this before anything else
--------------------------------------------
The original begins, at MODULE level, with a "self-heal": if the jail venv's interpreter exists and
is not the one already running, it `os.execv`s into it. This runs at IMPORT, not in `main()`, and
the consequence is not obvious, so it was MEASURED rather than assumed:

    $ python3 -c "import crank_approve; print('IMPORT RETURNED')"
    usage: crank_approve.py [-h] [--yes] component
    crank_approve.py: error: the following arguments are required: component
    (exit 2 — and "IMPORT RETURNED" is never printed)

Importing the original under a NON-jail interpreter REPLACES THE PROCESS. `os.execv` does not
return, so the import never completes; the interpreter is swapped for the jail one, which then runs
this file as a SCRIPT and argparse rejects the empty argument list. Under the jail interpreter the
guard is false, the import completes normally, and everything proceeds.

This rewrite preserves that exactly, because #200 requirement 1 is behavior preservation and this is
behavior an existing caller can observe. What changes is only that the interpreter path is now a
config key (`jail_python`) instead of a hardcoded `~/jail/.venv/bin/python`, per requirement 4. Set
`jail_python` to `null` to disable the self-heal; the shipped config reproduces the original's path,
so an unmodified checkout behaves exactly like the original.

The re-exec preserves `sys.argv[1:]`, which is why the `forge2-crank-approve` console script works
through it: the generated wrapper imports this module, the import re-execs, and the jail interpreter
runs this file with the same arguments the operator typed.

WHY `cryptography` IS IMPORTED AT MODULE LEVEL, AND WHAT THAT COSTS. The original imports it at
module level, AFTER the re-exec — that ordering is the whole point of the self-heal, since the jail
venv is where `cryptography` lives. This rewrite keeps both the import and its position. So on a host
with no jail venv and no `cryptography`, importing this module raises ImportError — exactly as the
original does, which was measured. Making the import lazy would be a divergence an adversary could
observe by pointing both at a jail-less HOME, so it is not done. The practical consequence: run this
module, and its diagnostics, under an interpreter that HAS `cryptography` — normally the jail one.

CONFIGURATION (#200 requirement 4 — no hardcoded paths or params)
-----------------------------------------------------------------
The original hardcoded every path and parameter: the jail interpreter, the secrets file, the crankd
and congruency URLs and the names of the environment variables that override them, the wallet binary,
the approver key name, the two secret names, the request timeout, the wallet's argv, the API-key
header and the three routes. All of them are now config keys, and NONE has a default. The config
object is resolved from the first source that answers:

  1. the file named by the `FORGE2_CONFIG` environment variable. That file holds the unit config
     object itself — exactly what `config_template()` returns.
  2. otherwise, the `forge2.agent_tools_suite.crank_approve` section of the nearest `registry.json`
     found by walking UP from THIS FILE's directory. This package ships one there, so an unmodified
     checkout resolves to it and the module runs.

If NEITHER answers, the module still IMPORTS, but every operation raises `ConfigError` and nothing is
read, signed or posted. It never guesses a default — that is `note-for-claude`'s rule and this
ticket's acceptance item (d).

The keys, and the original expression each replaces:

    jail_python       str|null  "~/jail/.venv/bin/python"   _JAIL_PY  (null disables the self-heal)
    secrets_file      str       "~/.secrets/ats.env"        the path _secret() reads
    crankd_url        str       "http://127.0.0.1:8812"     the CRANKD_URL fallback
    crankd_url_env    str       "CRANKD_URL"                the env var that overrides it
    congruency_url    str       "http://127.0.0.1:8899"     the CONGRUENCY_URL fallback
    congruency_url_env str      "CONGRUENCY_URL"            the env var that overrides it
    wallet_bin        str       "~/bin/wallet"              the WALLET_BIN fallback
    wallet_bin_env    str       "WALLET_BIN"                the env var that overrides it
    approver          str       "crank-approver"            APPROVER
    api_key_secret    str       "CONGRUENCY_API_KEY"        the secret name for CONGRUENCY_KEY
    pubkey_secret     str       "CRANK_APPROVER_PUBKEY"     the secret name for APPROVER_PUBKEY
    api_key_header    str       "X-Api-Key"                 the header _cong_post() adds
    post_headers      obj       {"Content-Type": "..."}     the headers _cong_post() always sends
    timeout           num|null  5                           urlopen(..., timeout=5), both calls
    wallet_argv       list      ["{wallet}", "ssh", ...]    the subprocess.run argv
    digest_route      str       "/digest?component={component}"
    approval_route    str       "/?route=ticket.approval&component={component}"
    approve_route     str       "/?route=ticket.approve"

A path key may be absolute, may start with `~` (expanded), or may be relative — in which case it
resolves against the directory the config came FROM (the registry's directory), never against the
current working directory. `wallet_argv` and the three route keys are `str.format` TEMPLATES:
`wallet_argv` is given `{wallet}`, `{approver}` and `{keyfile}`; `digest_route` and `approval_route`
are given `{component}`. A component value containing braces is substituted literally and is NOT
re-expanded, matching the original's f-string.

WHAT IS *NOT* CONFIG, AND WHY. The printed lines, the confirmation prompt, the argparse description
and the exit messages are NOT config keys. They are the module's observable BEHAVIOR, which
requirement 1 fixes to the original's; making them configurable would let a config change the very
output this ticket exists to preserve. Requirement 4 asks for paths and params to be config-driven,
and they all are.

`configure(config)` and `using_config(config)` inject a config object in-process, for callers that
hold their configuration in memory rather than on disk. Injecting never re-execs: the self-heal is an
import-time event, and replacing the process in the middle of a call is a side effect the original
never performs there.

RUNNING IT
----------
The CLI is the original's, EXACTLY:

    python crank_approve.py <component>            # asks for confirmation, then signs
    python crank_approve.py <component> --yes      # skips the confirmation prompt

Installed, the same thing through the console script:

    forge2-crank-approve <component> [--yes]

WHAT IT NEEDS THAT THIS PACKAGE DOES NOT SHIP. Approving for real needs a running crankd, a running
congruency, and the wallet binary. Ticket #418 covers exactly one module — this one — so none of
those are here. `selftest()` supplies all three as real local stand-ins.

WHY THERE IS NO `selftest` VERB — and how to run the selftest anyway. The original's argparse takes a
positional `component` and rejects unknown options; `--selftest` would be a usage error there. Adding
a verb would CHANGE the behavior of an input the original already defines, which #200's first
requirement forbids. So the diagnostics are module functions, not verbs. Run them under an
interpreter that has `cryptography` — normally the jail one, which is also the interpreter the
re-exec would send you to anyway:

    ~/jail/.venv/bin/python -B -c "import crank_approve; raise SystemExit(crank_approve.selftest())"
    ~/jail/.venv/bin/python -B -c "import crank_approve; raise SystemExit(crank_approve.check_package())"
    ~/jail/.venv/bin/python -B -c "import crank_approve, json; print(json.dumps(crank_approve.config_template(), indent=2))"

(Run them FROM this file's directory; `python -c` puts the current directory on the import path,
which is why these run as written. `selftest()` and `check_package()` return 0 on success and 1 on
failure, so `raise SystemExit(...)` makes that the process exit code. The `-B` is not required — it
just stops Python caching the bytecode of the module you import, so the command leaves no
`__pycache__` beside the source. Drop it and everything still works.)

To prove acceptance item (d) — that this throws rather than guessing — point the config environment
variable at a file that does not exist:

    FORGE2_CONFIG=/nonexistent.json ~/jail/.venv/bin/python crank_approve.py c1    # exit 2, config error

INSTALLABLE (#200 requirement 3)
--------------------------------
This directory IS the import package `agent_tools_suite`, and ticket #418 lands the whole of it, so
it installs from its own source:

    pip install -e .                      # from this directory
    forge2-crank-approve <component>      # the console script
    ~/jail/.venv/bin/python -c "from agent_tools_suite.crank_approve import sign_digest"

`pyproject.toml` and `__init__.py` are NOT hand-authored here: per #200 requirement 3 they are
DERIVED from the modules present by `congruency/tools/forge_package.py` (#410), so a sibling module
of this package can land later without either unit clobbering the other. They were generated by
running that tool against this directory. `registry.json` gains only this unit's own
`forge2.agent_tools_suite.crank_approve` section, added additively via that tool's
`merge_registry_section()`; no sibling's section is read, edited or dropped.

THE `cryptography` DEPENDENCY, STATED PLAINLY. `forge_package.py` renders `dependencies = []` and is
a pure function of the modules present, so the derived `pyproject.toml` cannot declare
`cryptography`, and `pip install -e .` does not install it. That is not an oversight in this
rewrite — it mirrors the original, whose dependency management IS the jail venv rather than pip: the
re-exec exists precisely because the tool expects to find `cryptography` in the jail, not in the
environment it was launched from. The console script therefore works from any venv, because importing
it re-execs into the jail. Declaring the dependency by hand would mean hand-authoring pyproject.toml,
which this ticket forbids, and it would be regenerated away by the harness regardless.

HOW FAR THIS WAS VERIFIED — and where it stops
----------------------------------------------
Everything claimed here was RUN, and can be re-run:

  * BEHAVIOR was verified DIFFERENTIALLY against the original, not just against expectations. The
    original was reconstructed from ticket #418's embedded source, confirmed byte-identical to forge
    blob 67367c32c83e78ca4a79da7ce3ad6926cf950cae (git blob sha1 over the 4882 bytes), and run side
    by side with this rewrite in identical worlds — same HOME, same fake wallet, same local crankd
    and congruency, same environment — over the CLI end-to-end and every function of the surface.
    The two agreed on exit code, stdout, stderr, the bytes signed, and the requests that reached the
    wire. That harness was mutation-tested: seeded defects in this module (the `CRANKD`/`CONG`
    env-fallback asymmetry, the `rstrip("/")`, the falsy-pubkey path, the api-key header) were each
    caught, so its agreement is evidence rather than an artifact.
  * `selftest()` replays those measured exemplars with real ed25519 keys, a real fake wallet binary
    and real local HTTP servers. `check_package()` checks the derived packaging against this module.
  * `pip install -e .` was executed into a fresh venv, exit 0, and the console script run from it.

Where it stops: the crankd and congruency this was driven against are local stand-ins that speak the
two routes this tool uses, not the real daemons; and the wallet is a stand-in that emits a real
ed25519 OpenSSH key rather than the real wallet. What is proven is that this module reads, prompts,
signs, verifies and posts IDENTICALLY to the original. What the real daemons do with a correct
request was never in this unit's scope.

SIDE EFFECTS — what this module writes, and when
------------------------------------------------
`sign_digest()` creates a temporary directory, has the wallet write a private key into it, and
removes it — the key never outlives the call. Nothing else writes anything: `_secret()`, `_get()`,
`_cong_post()` and `verifies_locally()` create no files. `main()` performs network requests and, on
the approval path, one POST. `selftest()` works entirely inside a temporary directory it removes,
against ephemeral ports, and restores every global and environment variable it touches.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... Filename - function
name - time of occurance - methods to reproduce - possible cause") `main()` appends one timestamped
JSON line to the config's `bug_reports` path if an UNEXPECTED exception escapes — and then RE-RAISES
it, so the exception, its traceback and the exit code the original produced are all unchanged.

THE ONE DELIBERATE DIVERGENCE, stated plainly rather than buried: on that crash path this rewrite
does two things the original did not — it writes the bug-report line, and it prints one extra
`EXCEPTION — ...` line to stderr saying where the report went. This repository's own rule requires
it, and it is confined to the path where the original was already crashing. Everything else an
operator or a caller observes on that path — the exception type, the message, the traceback and the
exit code — is identical; that was verified side by side. Filing the report is best-effort and never
masks the real exception.

A `ConfigError` is designed behavior, not a bug: it files no report and prints no traceback, exiting
2 with a single self-explaining line.
"""
import contextlib
import io
import json
import os
import sys

__all__ = [
    "_secret", "_get", "_cong_post", "sign_digest", "verifies_locally", "main",
    "CRANKD", "CONG", "WALLET", "APPROVER", "CONGRUENCY_KEY", "APPROVER_PUBKEY",
    "ConfigError", "load_config", "configure", "using_config", "reset_config",
    "config_template", "show_config", "selftest", "check_package",
]

#: Environment variable naming a file that holds this unit's config object.
CONFIG_ENV = "FORGE2_CONFIG"

#: The registry filename this module walks up the tree looking for.
REGISTRY_NAME = "registry.json"

#: This unit's ADDRESS inside the registry document. Not a configurable setting — a config-driven
#: tool has to know which section is its own.
UNIT_PATH = ("forge2", "agent_tools_suite", "crank_approve")

#: Human-readable unit identity, used in messages.
UNIT = "forge2:agent_tools_suite/crank_approve"

#: The import package this module belongs to, as the derived `pyproject.toml` declares it. Used only
#: by `check_package()`, to check the packaging against itself.
IMPORT_PACKAGE = "agent_tools_suite"

#: The module-level constants the original computed at import, in the order they must be computed
#: (CONGRUENCY_KEY and APPROVER_PUBKEY need `_secret`, which needs `secrets_file`). Preserved as real
#: module globals so a caller can read OR assign them exactly as before.
CONSTANTS = ("CRANKD", "CONG", "WALLET", "APPROVER", "CONGRUENCY_KEY", "APPROVER_PUBKEY")


class ConfigError(RuntimeError):
    """Raised when the config object is absent, unreadable, or missing a required key.

    This is the #200 requirement-4 gate and this ticket's acceptance item (d): a tool that cannot see
    its config throws rather than guessing a default.
    """


# ─────────────────────────────── configuration ───────────────────────────────

_ACTIVE = None       # config injected via configure(); wins over every disk source
_RESOLVED = None     # cache of the last disk resolution, so a call re-reads no files
_INIT_ERROR = None   # the ConfigError that stopped the constants being computed, if any


def find_registry(start=None):
    """Walk UP from `start` (default: this file's directory) and return the nearest registry path, or
    None if the walk reaches the filesystem root without finding one.

    The walk starts at THIS FILE, never at the working directory, so which directory you run from
    cannot change which config is found. If the walk fails — a layout where the module was installed
    without its package data beside it — it falls back to asking the import system where
    `agent_tools_suite` lives and looks there.
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
    if start is None:
        return _installed_registry()
    return None


def _installed_registry():
    """The registry shipped as package data beside the installed package, or None."""
    try:
        import importlib.util
        spec = importlib.util.find_spec(IMPORT_PACKAGE)
    except (ImportError, ValueError, AttributeError):
        return None
    locations = list(getattr(spec, "submodule_search_locations", None) or []) if spec else []
    for location in locations:
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
            "no config object for %s: %s is unset and no %s was found by walking up from %s. This "
            "tool does not guess defaults — install the config object printed by config_template()."
            % (UNIT, CONFIG_ENV, REGISTRY_NAME,
               os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))))

    document = _read_json(registry_path, "the registry")
    node = document
    for depth, key in enumerate(UNIT_PATH):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                "the registry at %s has no config object for %s: it is missing the %r section. Add "
                "the object returned by config_template() at %s."
                % (registry_path, UNIT, ".".join(UNIT_PATH[: depth + 1]), " -> ".join(UNIT_PATH)))
        node = node[key]
    if not isinstance(node, dict):
        raise ConfigError("the registry section %s at %s must be a JSON object, not %s"
                          % (".".join(UNIT_PATH), registry_path, type(node).__name__))

    config = dict(node)
    # The registry's own top-level bug_reports path is package-wide infrastructure; a unit section
    # may state its own to override it. This is inheritance inside ONE config document, not a
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


def config_template():
    """Return a template of this unit's config object — every key set to the value that reproduces
    the ORIGINAL unit's hardcoded expression.

    This is scaffolding returned on request, not a default: nothing here is applied unless an
    operator installs it, and until they do every operation throws.
    """
    return {
        "jail_python": "~/jail/.venv/bin/python",
        "secrets_file": "~/.secrets/ats.env",
        "crankd_url": "http://127.0.0.1:8812",
        "crankd_url_env": "CRANKD_URL",
        "congruency_url": "http://127.0.0.1:8899",
        "congruency_url_env": "CONGRUENCY_URL",
        "wallet_bin": "~/bin/wallet",
        "wallet_bin_env": "WALLET_BIN",
        "approver": "crank-approver",
        "api_key_secret": "CONGRUENCY_API_KEY",
        "pubkey_secret": "CRANK_APPROVER_PUBKEY",
        "api_key_header": "X-Api-Key",
        "post_headers": {"Content-Type": "application/json"},
        "timeout": 5,
        "wallet_argv": ["{wallet}", "ssh", "{approver}", "-w", "{keyfile}"],
        "digest_route": "/digest?component={component}",
        "approval_route": "/?route=ticket.approval&component={component}",
        "approve_route": "/?route=ticket.approve",
        "bug_reports": "logs/bug_reports.jsonl",
    }


def show_config():
    """Return the config object in force, its source and its base — for a human to inspect.

    Raises:
        ConfigError: if there is no config object to be had.
    """
    return {"unit": UNIT, "source": active_source(), "base": active_base(),
            "config": active_config()}


# ───────────────────────── typed access to the config ─────────────────────────

def _setting(key):
    """The config value for `key`, or ConfigError naming it."""
    config = active_config()
    if key not in config:
        raise ConfigError(
            "config object for %s is missing the required key %r. This tool does not guess "
            "defaults; see config_template() for the full object and the value that reproduces the "
            "original." % (UNIT, key))
    return config[key]


def _str_setting(key):
    value = _setting(key)
    if not isinstance(value, str):
        raise ConfigError("config key %r for %s must be a string, not %s"
                          % (key, UNIT, type(value).__name__))
    return value


def _resolve_path(value):
    """Expand `~` and make a relative path absolute against the directory the CONFIG came from —
    never the working directory."""
    value = os.path.expanduser(value)
    if not os.path.isabs(value):
        value = os.path.join(active_base(), value)
    return value


def _path_setting(key):
    """A path-valued config key, resolved to an absolute path."""
    return _resolve_path(_str_setting(key))


def _timeout_setting():
    """The request timeout: a number of seconds, or null for "no timeout" (Python's default)."""
    value = _setting("timeout")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("config key 'timeout' for %s must be a number of seconds or null, not %s"
                          % (UNIT, type(value).__name__))
    return value


def _str_map_setting(key):
    """A config key holding an object of string -> string."""
    value = _setting(key)
    if not isinstance(value, dict):
        raise ConfigError("config key %r for %s must be a JSON object, not %s"
                          % (key, UNIT, type(value).__name__))
    for name, item in value.items():
        if not isinstance(item, str):
            raise ConfigError("config key %r for %s maps %r to %s; every value must be a string"
                              % (key, UNIT, name, type(item).__name__))
    return value


def _template_setting(key, **fields):
    """A `str.format` template config key, rendered with `fields`.

    A template naming a placeholder this module does not supply, or with unbalanced braces, is a
    CONFIG error rather than a crash — the operator wrote it, so the message names the key. The
    substituted VALUES are inserted literally: `str.format` does not re-expand braces that came from
    a field, so a component named `{x}` reaches the URL as `{x}`, exactly as the original's f-string
    put it there.
    """
    template = _str_setting(key)
    try:
        return template.format(**fields)
    except (KeyError, IndexError, ValueError) as exc:
        raise ConfigError(
            "config key %r for %s is not a usable template (%s: %s). It may use only these "
            "placeholders: %s." % (key, UNIT, type(exc).__name__, exc,
                                   ", ".join("{%s}" % f for f in sorted(fields)) or "(none)")
        ) from exc


def _argv_setting(key, **fields):
    """A config key holding a list of `str.format` templates — the wallet's argv."""
    value = _setting(key)
    if not isinstance(value, list) or not value:
        raise ConfigError("config key %r for %s must be a non-empty JSON array of strings, not %s"
                          % (key, UNIT, type(value).__name__))
    out = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigError("config key %r for %s has a non-string at index %d (%s); every "
                              "element must be a string"
                              % (key, UNIT, index, type(item).__name__))
        try:
            out.append(item.format(**fields))
        except (KeyError, IndexError, ValueError) as exc:
            raise ConfigError(
                "config key %r for %s has an unusable template at index %d (%r — %s: %s). Each "
                "element may use only these placeholders: %s."
                % (key, UNIT, index, item, type(exc).__name__, exc,
                   ", ".join("{%s}" % f for f in sorted(fields)))) from exc
    return out


# ──────────────────── the self-heal, and the import-time constants ────────────────────

def jail_python():
    """The configured jail interpreter as an absolute path, or None if `jail_python` is null.

    Raises:
        ConfigError: if there is no config object, or it has no `jail_python` key.
    """
    value = _setting("jail_python")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError("config key 'jail_python' for %s must be a string or null, not %s"
                          % (UNIT, type(value).__name__))
    return _resolve_path(value)


def _reexec_into_jail():
    """Replace this process with the jail interpreter running this file, if we are not it already.

    This mirrors the original's module-level self-heal exactly, including its guard: the jail
    interpreter must EXIST, and `os.path.realpath` of it must differ from `os.path.realpath` of the
    running interpreter — comparing real paths is what lets the re-exec'd process recognise itself
    through the venv symlink and stop, instead of looping forever.

    `os.execv` does not return. `sys.argv[1:]` is carried across, so the console-script wrapper and a
    direct `python crank_approve.py <component>` both arrive at the same place.
    """
    jail = jail_python()
    if jail is None:
        return
    if os.path.exists(jail) and os.path.realpath(sys.executable) != os.path.realpath(jail):
        os.execv(jail, [jail, os.path.abspath(__file__), *sys.argv[1:]])


def _compute_constants():
    """Compute the six module constants from the config in force, reproducing the original's
    expressions — including their asymmetries, which are easy to get wrong and were measured:

      * CRANKD uses `os.environ.get(name, fallback)`, so `CRANKD_URL=""` yields `""`, NOT the
        fallback, and the value is NOT stripped of a trailing slash.
      * CONG uses `os.environ.get(name) or fallback`, so `CONGRUENCY_URL=""` DOES yield the
        fallback — and the result IS `rstrip("/")`ed.
      * WALLET uses `or` like CONG, and `~` is expanded ONLY on the config fallback, never on the
        environment override — the original's `os.environ.get("WALLET_BIN") or
        os.path.expanduser("~/bin/wallet")`.
    """
    crankd = os.environ.get(_str_setting("crankd_url_env"), _str_setting("crankd_url"))
    cong = (os.environ.get(_str_setting("congruency_url_env"))
            or _str_setting("congruency_url")).rstrip("/")
    wallet = os.environ.get(_str_setting("wallet_bin_env")) or _path_setting("wallet_bin")
    approver = _str_setting("approver")
    # _secret() reads `secrets_file`; resolve the names first so a missing one is named clearly.
    api_key_secret = _str_setting("api_key_secret")
    pubkey_secret = _str_setting("pubkey_secret")
    return {
        "CRANKD": crankd,
        "CONG": cong,
        "WALLET": wallet,
        "APPROVER": approver,
        "CONGRUENCY_KEY": _secret(api_key_secret),
        "APPROVER_PUBKEY": _secret(pubkey_secret),
    }


def _boot_reexec():
    """The self-heal at import, at exactly the position the original performs it: before
    `cryptography` is imported, because the jail venv is where `cryptography` lives.

    A missing config is swallowed HERE rather than raised. Without a config object this module cannot
    know which interpreter the jail is, and requirement 4 forbids guessing one — so it does not
    re-exec, the module still imports, and every operation below throws ConfigError instead. This is
    the only path on which the self-heal does not run when the original's would have, and it exists
    only because "no config" is a state the original had no notion of.
    """
    try:
        _reexec_into_jail()                    # does not return if it fires
    except ConfigError as exc:
        global _INIT_ERROR
        _INIT_ERROR = exc


def _init(reexec=False):
    """Compute the six module constants from the config in force and install them as globals.

    Returns None on success. On a ConfigError it records the error, leaves the constants UNDEFINED
    and RETURNS the error rather than raising, so that a module with no config still IMPORTS and
    every operation reports the problem itself.

    `reexec=True` performs the self-heal first; only the import-time call passes it. Re-initialising
    later — via `configure()` or `reset_config()` — never re-execs: replacing the process in the
    middle of a call is a side effect the original never performs there.
    """
    global _INIT_ERROR
    for name in CONSTANTS:                     # a re-init must not leave a stale constant behind
        globals().pop(name, None)
    try:
        if reexec:
            _reexec_into_jail()
        globals().update(_compute_constants())
    except ConfigError as exc:
        _INIT_ERROR = exc
        return exc
    _INIT_ERROR = None
    return None


def configure(config, base=None, source="injected via configure()"):
    """Inject `config` as the config object for this process and recompute the constants; return the
    previous state.

    `base` is the directory relative paths in `config` resolve against, and defaults to the current
    working directory. Pass `None` as `config` to drop the injection and go back to resolving from
    disk. Injecting never re-execs — see the module docstring.
    """
    global _ACTIVE
    previous = _ACTIVE
    if config is None:
        _ACTIVE = None
    else:
        if not isinstance(config, dict):
            raise ConfigError("a config object must be a dict, not %s" % type(config).__name__)
        _ACTIVE = (config, base or os.getcwd(), source)
    _init(reexec=False)
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
        _init(reexec=False)


def reset_config():
    """Drop the injected config and the cached disk resolution, then re-resolve the constants."""
    global _ACTIVE, _RESOLVED
    _ACTIVE = None
    _RESOLVED = None
    _init(reexec=False)


def _const(name):
    """The module constant `name`, honouring a caller's assignment to it.

    A caller may assign `crank_approve.CONG = "..."`, and the original would use that value, so the
    global is consulted first and only then the config. If the constants are undefined this retries
    the initialisation once — a config installed after import is picked up rather than reported
    stale — and only then raises the ConfigError explaining why they cannot be computed.
    """
    if name in globals():
        return globals()[name]
    error = _init()
    if name in globals():
        return globals()[name]
    raise error or _INIT_ERROR or ConfigError("no config object for %s" % UNIT)


def __getattr__(name):
    """Make `crank_approve.CRANKD` (and the other four) report the CONFIG problem rather than a bare
    AttributeError when there is no config.

    Python calls this only when normal attribute lookup fails, so once the constants are computed —
    or a caller assigns one — this is never reached and the real value is returned.
    """
    if name in CONSTANTS:
        return _const(name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


# The self-heal, at IMPORT and BEFORE the `cryptography` import — exactly where the original puts it.
_boot_reexec()

# AFTER the self-heal, exactly as the original orders it: the jail venv is where `cryptography`
# lives, so this import is the reason the re-exec above exists. See the module docstring.
from cryptography.hazmat.primitives.serialization import (      # noqa: E402
    load_ssh_private_key, load_ssh_public_key)

import argparse         # noqa: E402
import subprocess       # noqa: E402
import tempfile         # noqa: E402
import urllib.request   # noqa: E402


# ─────────────────────────────── the unit itself ───────────────────────────────

def _secret(name):
    """The value of secret `name`: the first `name=` line of the configured secrets file, else the
    environment variable of that name, else None.

    Faithful to the original in every detail that shows:
      * the file is consulted ONLY if it is a regular file; otherwise the environment answers;
      * each line is `strip()`ed BEFORE the `name=` test, so indented lines still match, and the
        value carries no trailing newline;
      * the FIRST matching line wins, and a later one is never read;
      * the value is everything after the first `=`, so `K=a=b` yields `a=b`;
      * `K=` yields `""` — an empty string, which is FALSY, and callers act on that;
      * a file that exists but does not mention `name` falls THROUGH to the environment, rather than
        returning None.

    Raises:
        ConfigError: if there is no config object, or it has no `secrets_file` key.
    """
    path = _path_setting("secrets_file")
    if os.path.isfile(path):
        with open(path) as handle:
            for line in handle:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1]
    return os.environ.get(name)


# The constants, at IMPORT — the original computes CRANKD/CONG/WALLET/APPROVER just after its
# imports and CONGRUENCY_KEY/APPROVER_PUBKEY immediately after `_secret`, which is why this sits
# HERE: `_compute_constants()` needs `_secret` to exist. Both are import-time in the original and
# both are import-time here, so no caller can observe a difference in timing.
#
# If the config cannot be seen, this RECORDS the error instead of raising: the module still imports,
# and every operation throws ConfigError. Nothing is ever guessed.
_init()


def _get(url):
    """GET `url` and return the decoded JSON body; an EMPTY body reads as `{}`.

    The timeout comes from the config's `timeout` key. Transport and HTTP errors are NOT caught —
    the original lets them escape, and `main()` reports them as a traceback.

    Raises:
        ConfigError: if there is no config object, or it has no `timeout` key.
    """
    timeout = _timeout_setting()
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode() or "{}")


def _cong_post(path, obj):
    """POST `obj` as JSON to congruency at `path`, and return the decoded JSON body (`{}` if empty).

    `path` is appended to the module's `CONG` constant, which is read HERE, at call time — so a
    caller that assigns `crank_approve.CONG` redirects this, exactly as in the original. The API key
    header is added only when `CONGRUENCY_KEY` is truthy, so an empty key sends NO header.

    Raises:
        ConfigError: if there is no config object, or it lacks a key this needs.
    """
    headers = dict(_str_map_setting("post_headers"))
    key = _const("CONGRUENCY_KEY")
    if key:
        headers[_str_setting("api_key_header")] = key
    timeout = _timeout_setting()
    request = urllib.request.Request(_const("CONG") + path, data=json.dumps(obj).encode(),
                                     method="POST", headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode() or "{}")


def sign_digest(digest_str):
    """Sign the digest string with the wallet-derived approver ed25519 key; return the hex signature.

    The wallet is asked to write the private key into a fresh temporary directory, the key is loaded,
    and the directory — with the key in it — is removed before the signature is produced. The key
    never outlives the call and is never stored.

    `subprocess.run(..., check=True, capture_output=True)` is preserved: a wallet that fails raises
    CalledProcessError, and the wallet's own stdout/stderr are CAPTURED, never shown.

    Raises:
        ConfigError: if there is no config object, or it lacks a key this needs.
    """
    wallet = _const("WALLET")
    approver = _const("APPROVER")
    with tempfile.TemporaryDirectory() as directory:
        keyfile = os.path.join(directory, "k")
        argv = _argv_setting("wallet_argv", wallet=wallet, approver=approver, keyfile=keyfile)
        subprocess.run(argv, check=True, capture_output=True)
        with open(keyfile, "rb") as handle:
            key = load_ssh_private_key(handle.read(), password=None)
    return key.sign(digest_str.encode()).hex()


def verifies_locally(digest_str, sig_hex):
    """True/False if the signature checks against the approver pubkey; None if no pubkey configured.

    "No pubkey configured" is a FALSY `APPROVER_PUBKEY` — which includes an empty string, not just
    None — and it returns None, which `main()` distinguishes from False. Every other failure, from a
    malformed pubkey to a non-hex signature to a genuine mismatch, is caught and returns False: the
    original's `except Exception` is deliberately that broad, so a bad pubkey reads as "does not
    verify" rather than crashing.

    Raises:
        ConfigError: if there is no config object (the pubkey is read from the constants).
    """
    pubkey = _const("APPROVER_PUBKEY")
    if not pubkey:
        return None
    try:
        load_ssh_public_key(pubkey.encode()).verify(bytes.fromhex(sig_hex), digest_str.encode())
        return True
    except Exception:      # noqa: BLE001 — a bad pubkey means "unverified", not "crash"
        return False


# ─────────────────────────────── the bug report ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception. Returns the path written,
    or None.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ... Filename -
    function name - time of occurance - methods to reproduce - possible cause").

    TRULY best-effort: the whole body is guarded, because this runs INSIDE an `except` block and any
    exception raised here would REPLACE the real one the operator needs to see. That includes a
    `bug_reports` key holding a non-string, which would otherwise raise TypeError from
    `os.path.isabs` and bury the original error.
    """
    try:
        import traceback
        from datetime import datetime
        try:
            config = active_config()
            base = active_base()
        except ConfigError:
            return None                        # no config to tell us where reports go
        relative = config.get("bug_reports")
        if not isinstance(relative, str) or not relative:
            return None
        path = relative if os.path.isabs(relative) else os.path.join(base, relative)
        frames = traceback.extract_tb(exc.__traceback__)
        entry = {
            "filename": os.path.basename(os.path.abspath(__file__)),
            "function": frames[-1].name if frames else "?",
            "time-of-occurance": datetime.now().isoformat(),
            "methods-to-reproduce": "python3 %s %s" % (
                os.path.basename(os.path.abspath(__file__)), " ".join(argv)),
            "possible-cause": "%s: %s" % (type(exc).__name__, exc),
            "traceback": formatted.strip().splitlines()[-6:],
            "note": "%s (ticket #418, module key forge-rw:2aa9706d7f7163b0)" % UNIT,
        }
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except Exception:                          # noqa: BLE001 — never mask the real exception
        return None


# ─────────────────────────────── the command line ───────────────────────────────

def _run():
    """The original `main()`'s body: parse, fetch, show, confirm, sign, verify, post.

    Split out from `main()` only so the bug-report wrapper can sit around it; the sequence, the
    printed lines and the exit messages are the original's, verbatim.
    """
    ap = argparse.ArgumentParser(description="wallet-sign a crank ticket so crankd will run it")
    ap.add_argument("component")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args()

    info = _get(_const("CRANKD") + _template_setting("digest_route", component=args.component))
    if "digest" not in info:
        sys.exit(f"no approvable ticket for {args.component!r}: {info.get('error', info)}")
    ticket_id, digest = info["ticket"], info["digest"]

    ticket = (_get(_const("CONG") + _template_setting("approval_route", component=args.component))
              .get("rows") or [{}])[0]
    print(f"  component : {args.component}")
    print(f"  ticket    : {ticket_id}")
    print(f"  title     : {ticket.get('title', '')}")
    print(f"  body      : {ticket.get('body', '')}")
    patch = ticket.get("patch") or ""
    if patch.strip():
        print("  patch     |\n" + "\n".join("    " + line for line in patch.splitlines()))
    print(f"  digest    : {digest}")

    if not args.yes:
        if input("\n  wallet-sign and approve this ticket? [y/N] ").strip().lower() != "y":
            sys.exit("  aborted — not approved")

    sig = sign_digest(digest)
    ok = verifies_locally(digest, sig)
    if ok is False:
        sys.exit("  ✗ the produced signature does NOT verify against the approver pubkey — aborting")
    _cong_post(_str_setting("approve_route"), {"id": ticket_id, "approval_sig": sig})
    print(f"\n  ✓ approved ticket {ticket_id} — signature stored"
          f"{' (verified locally)' if ok else ''}")
    print(f"  crankd will now run it:  POST {_const('CRANKD')}/crank "
          f"{{\"component\":\"{args.component}\",\"intent\":\"...\"}}")


def main():
    """The original's entry point: approve one component, named on the command line.

    Returns None, and exits 0, on success — so the `forge2-crank-approve` console script, whose
    generated wrapper calls `sys.exit(main())`, exits 0 too. Every `sys.exit(message)` the original
    performs is preserved: it prints the message on stderr and exits 1.

    NO argument was added. `--selftest` and a bare invocation are usage errors here because they were
    usage errors in the original — see the module docstring on why, and for how to run the
    diagnostics.
    """
    try:
        _run()
    except ConfigError as exc:
        # Designed behavior, not a bug: one self-explaining line, no traceback, no report.
        print("config error: %s" % exc, file=sys.stderr)
        raise SystemExit(2) from None
    except Exception as exc:                   # noqa: BLE001
        import traceback
        path = _bug_report(exc, traceback.format_exc(), sys.argv[1:])
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        # Re-raise: the original crashed with a traceback and a non-zero exit, and filing a report
        # must not change that.
        raise


# ───────────────────────── the exemplars and the selftest ─────────────────────────

#: The wallet stand-in the selftest installs. It is a real executable that speaks the argv the
#: original passes — `<wallet> ssh <approver> -w <keyfile>` — and writes a REAL ed25519 private key in
#: OpenSSH format, so `load_ssh_private_key` and the signature that follows are genuine. It records
#: every argv it was called with, so the selftest can check what reached the wallet.
_FAKE_WALLET = '''#!/usr/bin/env python3
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "wallet-calls.jsonl"), "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
if os.path.exists(os.path.join(here, "wallet-fail")):
    sys.stderr.write("wallet: no such key\\n")
    sys.stdout.write("some stdout the original never shows\\n")
    sys.exit(3)
out = None
argv = sys.argv[1:]
if "-w" in argv:
    out = argv[argv.index("-w") + 1]
if out:
    with open(os.path.join(here, "key"), "rb") as fh:
        data = fh.read()
    with open(out, "wb") as fh:
        fh.write(data)
'''


class _Server:
    """A real HTTP server on an ephemeral port that answers from a scripted table and records every
    request — so the selftest checks the WIRE, not just return values."""

    def __init__(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        self.seen = []
        self.routes = {}          # path -> (status, body_bytes)
        seen, routes = self.seen, self.routes

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def _answer(self):
                length = int(self.headers.get("Content-Length") or 0)
                seen.append({"method": self.command, "path": self.path,
                             "body": self.rfile.read(length).decode() if length else "",
                             "headers": {k.lower(): v for k, v in self.headers.items()}})
                status, body = routes.get(self.path, (404, b'{"error": "no such route"}'))
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            do_GET = do_POST = _answer

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def route(self, path, obj, status=200):
        self.routes[path] = (status, json.dumps(obj).encode() if obj is not None else b"")
        return self

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.server.server_address[1]

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        return False


def _make_key(directory):
    """Write a real ed25519 OpenSSH private key into `directory/key` and return its OpenSSH pubkey
    text. Real crypto — the selftest signs and verifies for real."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.generate()
    with open(os.path.join(directory, "key"), "wb") as handle:
        handle.write(key.private_bytes(serialization.Encoding.PEM,
                                       serialization.PrivateFormat.OpenSSH,
                                       serialization.NoEncryption()))
    return key.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                         serialization.PublicFormat.OpenSSH).decode()


def _capture(fn, *args, **kwargs):
    """Run `fn` and return (stdout_text, returned_value)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        value = fn(*args, **kwargs)
    return buffer.getvalue(), value


def selftest(stream=None):
    """Replay the ORIGINAL's measured behavior against this rewrite. Returns 0 or 1.

    Every expectation below was OBSERVED by running the original — reconstructed from ticket #418's
    embedded source and confirmed byte-identical to the forge blob
    67367c32c83e78ca4a79da7ce3ad6926cf950cae — side by side with this module in identical worlds.
    These are #200's exemplars: the original is the oracle, and this replays what it actually did
    rather than what its source appears to say.

    Runs entirely inside a temporary directory it removes, against real HTTP servers on ephemeral
    ports, a real executable wallet stand-in and real ed25519 keys. It restores every global and
    environment variable it touches.
    """
    import shutil
    import stat
    import subprocess as sp
    import tempfile as tf

    out = stream or sys.stdout
    checks = []

    def ck(name, ok, detail=""):
        checks.append((name, bool(ok)))
        print("  %-4s %s%s" % ("PASS" if ok else "FAIL", name,
                               "" if ok else "   <- %s" % detail), file=out)

    root = tf.mkdtemp(prefix="crank-approve-selftest-")
    saved_env = {k: os.environ.get(k) for k in
                 (CONFIG_ENV, "CRANKD_URL", "CONGRUENCY_URL", "WALLET_BIN",
                  "CONGRUENCY_API_KEY", "CRANK_APPROVER_PUBKEY")}
    saved_state = (_ACTIVE, _RESOLVED, _INIT_ERROR,
                   {n: globals()[n] for n in CONSTANTS if n in globals()})
    try:
        for k in saved_env:
            os.environ.pop(k, None)

        pubkey = _make_key(root)
        wallet = os.path.join(root, "wallet")
        with open(wallet, "w") as handle:
            handle.write(_FAKE_WALLET)
        os.chmod(wallet, os.stat(wallet).st_mode | stat.S_IXUSR)
        secrets = os.path.join(root, "ats.env")

        def cfg(**over):
            base = dict(config_template())
            base.update({"jail_python": None, "secrets_file": secrets, "wallet_bin": wallet,
                         "timeout": 5})
            base.update(over)
            return base

        def write_secrets(text):
            with open(secrets, "w") as handle:
                handle.write(text)

        print("== forge2:agent_tools_suite/crank_approve — exemplars replayed from the original",
              file=out)

        # ── _secret(): the file/env precedence and the parsing edge cases ──
        print("-- _secret(): file wins, first match wins, everything after the first '=' is the "
              "value", file=out)
        with using_config(cfg(), base=root):
            if os.path.exists(secrets):
                os.remove(secrets)
            ck("no secrets file, no env -> None", _secret("K") is None)

            os.environ["K"] = "from-env"
            ck("no secrets file -> the environment answers", _secret("K") == "from-env")

            write_secrets("K=from-file\n")
            ck("the secrets FILE wins over the environment", _secret("K") == "from-file")

            write_secrets("OTHER=x\n")
            ck("a file that does not mention the name FALLS THROUGH to the environment",
               _secret("K") == "from-env")
            os.environ.pop("K", None)
            ck("... and to None when the environment has it neither", _secret("K") is None)

            write_secrets("K=first\nK=second\n")
            ck("the FIRST matching line wins", _secret("K") == "first")

            write_secrets("  K=indented  \n")
            ck("lines are strip()ed BEFORE the match, so an indented line still matches, and the "
               "value carries no trailing space", _secret("K") == "indented")

            write_secrets("K=a=b=c\n")
            ck("only the FIRST '=' splits, so 'K=a=b=c' -> 'a=b=c'", _secret("K") == "a=b=c")

            write_secrets("K=\n")
            got = _secret("K")
            ck("'K=' -> '' (empty string, and it is FALSY — not None)",
               got == "" and got is not None, "got %r" % (got,))

            write_secrets("KK=nope\n")
            ck("the match is a PREFIX test on 'name=', so 'KK=' does not answer for 'K'",
               _secret("K") is None)

            os.mkdir(os.path.join(root, "dir.env"))
            with using_config(cfg(secrets_file=os.path.join(root, "dir.env")), base=root):
                os.environ["K"] = "env-again"
                ck("a secrets path that is a DIRECTORY is not a regular file -> the environment "
                   "answers", _secret("K") == "env-again")
                os.environ.pop("K", None)

        # ── the constants: the env-fallback asymmetries ──
        print("-- the module constants: CRANKD/CONG/WALLET differ in how they fall back", file=out)
        write_secrets("")
        with using_config(cfg(), base=root):
            ck("CRANKD defaults to the config's crankd_url", _const("CRANKD") == "http://127.0.0.1:8812")
            ck("CONG defaults to the config's congruency_url",
               _const("CONG") == "http://127.0.0.1:8899")
            ck("WALLET defaults to the config's wallet_bin", _const("WALLET") == wallet)
            ck("APPROVER comes from the config", _const("APPROVER") == "crank-approver")

        os.environ["CRANKD_URL"] = ""
        os.environ["CONGRUENCY_URL"] = ""
        with using_config(cfg(), base=root):
            ck("CRANKD_URL='' -> CRANKD is '' (get(name, default) does NOT fall back on empty)",
               _const("CRANKD") == "", repr(_const("CRANKD")))
            ck("CONGRUENCY_URL='' -> CONG DOES fall back ('or' treats '' as absent)",
               _const("CONG") == "http://127.0.0.1:8899", repr(_const("CONG")))
        os.environ.pop("CRANKD_URL", None)
        os.environ.pop("CONGRUENCY_URL", None)

        os.environ["CONGRUENCY_URL"] = "http://example.invalid:9/"
        with using_config(cfg(), base=root):
            ck("CONG is rstrip('/')ed", _const("CONG") == "http://example.invalid:9",
               repr(_const("CONG")))
        os.environ["CONGRUENCY_URL"] = "http://example.invalid:9///"
        with using_config(cfg(), base=root):
            ck("rstrip('/') removes EVERY trailing slash, not just one",
               _const("CONG") == "http://example.invalid:9", repr(_const("CONG")))
        os.environ.pop("CONGRUENCY_URL", None)

        os.environ["CRANKD_URL"] = "http://example.invalid:8/"
        with using_config(cfg(), base=root):
            ck("CRANKD is NOT rstrip('/')ed — only CONG is",
               _const("CRANKD") == "http://example.invalid:8/", repr(_const("CRANKD")))
        os.environ.pop("CRANKD_URL", None)

        os.environ["WALLET_BIN"] = "~/literal/wallet"
        with using_config(cfg(), base=root):
            ck("WALLET_BIN is used RAW — '~' is expanded only on the config fallback",
               _const("WALLET") == "~/literal/wallet", repr(_const("WALLET")))
        os.environ.pop("WALLET_BIN", None)

        # ── CONGRUENCY_KEY / APPROVER_PUBKEY come from _secret at INIT ──
        print("-- CONGRUENCY_KEY / APPROVER_PUBKEY are read through _secret() when the constants "
              "are computed", file=out)
        write_secrets("CONGRUENCY_API_KEY=k-from-file\nCRANK_APPROVER_PUBKEY=%s\n" % pubkey.strip())
        with using_config(cfg(), base=root):
            ck("CONGRUENCY_KEY is read from the secrets file",
               _const("CONGRUENCY_KEY") == "k-from-file")
            ck("APPROVER_PUBKEY is read from the secrets file",
               _const("APPROVER_PUBKEY") == pubkey.strip())

        # ── sign_digest() + verifies_locally(): real keys, real signatures ──
        print("-- sign_digest() / verifies_locally(): real ed25519 through a real wallet binary",
              file=out)
        with using_config(cfg(), base=root):
            calls = os.path.join(root, "wallet-calls.jsonl")
            if os.path.exists(calls):
                os.remove(calls)
            sig = sign_digest("the-digest")
            ck("sign_digest() returns lowercase hex of a 64-byte ed25519 signature",
               len(sig) == 128 and all(c in "0123456789abcdef" for c in sig), sig[:40])
            recorded = json.loads(open(calls).read().splitlines()[0])
            ck("the wallet was called as `ssh <approver> -w <keyfile>`",
               recorded[:2] == ["ssh", "crank-approver"] and recorded[2] == "-w",
               repr(recorded))
            ck("the keyfile the wallet wrote is GONE after the call (TemporaryDirectory)",
               not os.path.exists(recorded[3]), recorded[3])
            ck("verifies_locally() -> True for a signature this key really made",
               verifies_locally("the-digest", sig) is True)
            ck("verifies_locally() -> False when the digest differs",
               verifies_locally("another-digest", sig) is False)
            ck("verifies_locally() -> False for a non-hex signature (broad except, no crash)",
               verifies_locally("the-digest", "zz") is False)
            ck("verifies_locally() -> False for a well-formed but wrong signature",
               verifies_locally("the-digest", "00" * 64) is False)
            ck("sign_digest() is deterministic for ed25519 (same key, same digest, same sig)",
               sign_digest("the-digest") == sig)

            other = sign_digest("d2")
            ck("a different digest gives a different signature", other != sig)

        write_secrets("CRANK_APPROVER_PUBKEY=\n")
        with using_config(cfg(), base=root):
            ck("an EMPTY pubkey is falsy -> verifies_locally() is None, not False",
               verifies_locally("d", "00") is None)
        write_secrets("")
        with using_config(cfg(), base=root):
            ck("no pubkey at all -> verifies_locally() is None",
               verifies_locally("d", "00") is None)

        write_secrets("CRANK_APPROVER_PUBKEY=ssh-ed25519 not-a-real-key\n")
        with using_config(cfg(), base=root):
            ck("a MALFORMED pubkey -> False (it is caught), not an exception",
               verifies_locally("d", "00" * 64) is False)

        write_secrets("CRANK_APPROVER_PUBKEY=%s\n" % pubkey.strip())
        with using_config(cfg(), base=root):
            os.remove(os.path.join(root, "wallet-calls.jsonl"))
            open(os.path.join(root, "wallet-fail"), "w").close()
            try:
                sign_digest("d")
                ck("a FAILING wallet raises CalledProcessError (check=True)", False, "no raise")
            except sp.CalledProcessError as exc:
                ck("a FAILING wallet raises CalledProcessError (check=True)", True)
                ck("the wallet's output is CAPTURED, not shown (capture_output=True)",
                   exc.stderr == b"wallet: no such key\n"
                   and exc.stdout == b"some stdout the original never shows\n",
                   repr((exc.stdout, exc.stderr)))
            os.remove(os.path.join(root, "wallet-fail"))

        # ── _get() / _cong_post(): the wire ──
        print("-- _get() / _cong_post(): empty body reads as {}, the api key header is "
              "conditional", file=out)
        with _Server() as srv:
            srv.route("/j", {"a": 1}).route("/empty", None).route("/post", {"ok": True})
            with using_config(cfg(), base=root):
                ck("_get() decodes a JSON body", _get(srv.url + "/j") == {"a": 1})
                ck("_get() reads an EMPTY body as {}", _get(srv.url + "/empty") == {})

            write_secrets("CONGRUENCY_API_KEY=secret-key\n")
            with using_config(cfg(congruency_url=srv.url), base=root):
                ck("_cong_post() returns the decoded body",
                   _cong_post("/post", {"id": 7}) == {"ok": True})
                sent = srv.seen[-1]
                ck("_cong_post() POSTs the object as JSON to CONG + path",
                   sent["method"] == "POST" and sent["path"] == "/post"
                   and json.loads(sent["body"]) == {"id": 7}, repr(sent))
                ck("_cong_post() sends Content-Type: application/json",
                   sent["headers"].get("content-type") == "application/json", repr(sent["headers"]))
                ck("_cong_post() sends the api key header when the key is truthy",
                   sent["headers"].get("x-api-key") == "secret-key", repr(sent["headers"]))

            write_secrets("CONGRUENCY_API_KEY=\n")
            with using_config(cfg(congruency_url=srv.url), base=root):
                _cong_post("/post", {"id": 8})
                ck("an EMPTY api key is falsy -> NO api key header at all",
                   "x-api-key" not in srv.seen[-1]["headers"], repr(srv.seen[-1]["headers"]))

            write_secrets("")
            with using_config(cfg(congruency_url=srv.url), base=root):
                _cong_post("/post", {"id": 9})
                ck("no api key -> no api key header",
                   "x-api-key" not in srv.seen[-1]["headers"], repr(srv.seen[-1]["headers"]))

            print("-- a caller may still assign CONG, and _cong_post() honours it at CALL time",
                  file=out)
            with using_config(cfg(congruency_url="http://example.invalid:9"), base=root):
                globals()["CONG"] = srv.url
                try:
                    ck("assigning crank_approve.CONG redirects the POST",
                       _cong_post("/post", {"id": 10}) == {"ok": True})
                finally:
                    _init(reexec=False)

        # ── main(): the CLI, end to end, against real servers ──
        print("-- main(): the CLI end-to-end, against a real crankd and congruency stand-in",
              file=out)
        write_secrets("CRANK_APPROVER_PUBKEY=%s\n" % pubkey.strip())
        saved_argv = sys.argv
        try:
            with _Server() as crankd, _Server() as cong:
                crankd.route("/digest?component=c1", {"ticket": 42, "digest": "DIG-42"})
                crankd.route("/digest?component=nope", {"error": "no ticket"})
                crankd.route("/digest?component=weird", {})
                cong.route("/?route=ticket.approval&component=c1",
                           {"rows": [{"title": "T", "body": "B", "patch": "l1\nl2"}]})
                cong.route("/?route=ticket.approval&component=empty", {"rows": []})
                cong.route("/?route=ticket.approve", {"ok": 1})

                conf = cfg(crankd_url=crankd.url, congruency_url=cong.url)
                with using_config(conf, base=root):
                    sys.argv = ["crank_approve.py", "c1", "--yes"]
                    text, _ = _capture(main)
                    ck("--yes prints the ticket, signs and reports approval, with the patch "
                       "indented by four spaces and '(verified locally)' appended",
                       text == ("  component : c1\n  ticket    : 42\n  title     : T\n"
                                "  body      : B\n  patch     |\n    l1\n    l2\n"
                                "  digest    : DIG-42\n"
                                "\n  ✓ approved ticket 42 — signature stored (verified locally)\n"
                                "  crankd will now run it:  POST %s/crank "
                                '{"component":"c1","intent":"..."}\n' % crankd.url), repr(text))
                    posted = [s for s in cong.seen if s["method"] == "POST"][-1]
                    body = json.loads(posted["body"])
                    ck("the POST carries the ticket id and a signature over the DIGEST",
                       body["id"] == 42 and verifies_locally("DIG-42", body["approval_sig"]) is True,
                       repr(body))

                    sys.argv = ["crank_approve.py", "nope", "--yes"]
                    try:
                        main()
                        ck("a component with no approvable ticket exits", False, "no exit")
                    except SystemExit as exc:
                        ck("no digest -> SystemExit with the crankd 'error' field interpolated",
                           exc.code == "no approvable ticket for 'nope': no ticket",
                           repr(exc.code))

                    sys.argv = ["crank_approve.py", "weird", "--yes"]
                    try:
                        main()
                        ck("an EMPTY crankd answer exits", False, "no exit")
                    except SystemExit as exc:
                        ck("no 'error' key either -> the whole object is interpolated",
                           exc.code == "no approvable ticket for 'weird': {}", repr(exc.code))

                    # the confirmation prompt: ONLY a bare "y", case-folded and stripped, approves
                    import builtins
                    for answer, approves in (("y", True), ("Y", True), (" y \n", True),
                                             ("n", False), ("", False), ("yes", False)):
                        sys.argv = ["crank_approve.py", "c1"]
                        saved_input = builtins.input
                        builtins.input = lambda _prompt, _answer=answer: _answer
                        try:
                            with contextlib.redirect_stdout(io.StringIO()):
                                try:
                                    main()
                                    outcome = "approved"
                                except SystemExit as exc:
                                    outcome = exc.code
                        finally:
                            builtins.input = saved_input
                        if approves:
                            ck("prompt answered %r -> approves" % answer, outcome == "approved",
                               repr(outcome))
                        else:
                            ck("prompt answered %r -> SystemExit('  aborted — not approved')"
                               % answer, outcome == "  aborted — not approved", repr(outcome))

                    # an empty rows list still prints, from the {} fallback
                    crankd.route("/digest?component=empty", {"ticket": 7, "digest": "D7"})
                    sys.argv = ["crank_approve.py", "empty", "--yes"]
                    text, _ = _capture(main)
                    ck("rows:[] -> the [{}] fallback prints empty title/body and NO patch block",
                       text.startswith("  component : empty\n  ticket    : 7\n  title     : \n"
                                       "  body      : \n  digest    : D7\n"), repr(text))

                    # a whitespace-only patch is not printed
                    cong.route("/?route=ticket.approval&component=c1",
                               {"rows": [{"title": "T", "body": "B", "patch": "   \n  "}]})
                    sys.argv = ["crank_approve.py", "c1", "--yes"]
                    text, _ = _capture(main)
                    ck("a whitespace-only patch is NOT printed (patch.strip() is the test)",
                       "patch" not in text, repr(text))

                # no pubkey -> approves, but WITHOUT '(verified locally)'
                write_secrets("")
                with using_config(conf, base=root):
                    cong.route("/?route=ticket.approval&component=c1", {"rows": [{}]})
                    sys.argv = ["crank_approve.py", "c1", "--yes"]
                    text, _ = _capture(main)
                    ck("no pubkey -> still approves, and '(verified locally)' is ABSENT",
                       "✓ approved ticket 42 — signature stored\n" in text
                       and "verified locally" not in text, repr(text))

                # a pubkey that does not match the wallet's key -> abort BEFORE the POST
                other_dir = tf.mkdtemp(prefix="crank-approve-otherkey-")
                try:
                    wrong_pub = _make_key(other_dir)
                    write_secrets("CRANK_APPROVER_PUBKEY=%s\n" % wrong_pub.strip())
                    with using_config(conf, base=root):
                        before = len([s for s in cong.seen if s["method"] == "POST"])
                        sys.argv = ["crank_approve.py", "c1", "--yes"]
                        try:
                            with contextlib.redirect_stdout(io.StringIO()):
                                main()
                            ck("a signature that does not verify aborts", False, "no exit")
                        except SystemExit as exc:
                            ck("verifies_locally() False -> SystemExit with the ✗ message",
                               exc.code == ("  ✗ the produced signature does NOT verify against "
                                            "the approver pubkey — aborting"), repr(exc.code))
                        after = len([s for s in cong.seen if s["method"] == "POST"])
                        ck("... and NOTHING was posted — the abort happens BEFORE the POST",
                           after == before, "posts before=%d after=%d" % (before, after))
                finally:
                    shutil.rmtree(other_dir, ignore_errors=True)
        finally:
            sys.argv = saved_argv

        # ── the config gate (#200 req 4 / acceptance (d)) ──
        print("-- the config gate: no config -> throw, never guess", file=out)
        write_secrets("")
        missing = os.path.join(root, "nope.json")
        os.environ[CONFIG_ENV] = missing
        try:
            reset_config()
            for name, fn, args in (("_secret", _secret, ("K",)), ("_get", _get, ("http://x/",)),
                                   ("_cong_post", _cong_post, ("/p", {})),
                                   ("sign_digest", sign_digest, ("d",)),
                                   ("verifies_locally", verifies_locally, ("d", "00"))):
                try:
                    fn(*args)
                    ck("%s() throws without a config" % name, False, "returned instead")
                except ConfigError:
                    ck("%s() throws ConfigError without a config" % name, True)
                except Exception as exc:       # noqa: BLE001
                    ck("%s() throws ConfigError without a config" % name, False,
                       "raised %r" % exc)
            for name in CONSTANTS:
                try:
                    getattr(sys.modules[__name__], name)
                    ck("reading %s without a config throws" % name, False, "returned instead")
                except ConfigError:
                    ck("reading %s without a config throws ConfigError" % name, True)
                except Exception as exc:       # noqa: BLE001
                    ck("reading %s without a config throws ConfigError" % name, False,
                       "raised %r" % exc)
            sys.argv = ["crank_approve.py", "c1", "--yes"]
            try:
                main()
                ck("main() without a config exits 2", False, "returned instead")
            except SystemExit as exc:
                ck("main() without a config exits 2 with one line, no traceback", exc.code == 2,
                   repr(exc.code))
            finally:
                sys.argv = saved_argv
        finally:
            os.environ.pop(CONFIG_ENV, None)
            reset_config()

        partial = os.path.join(root, "partial.json")
        with open(partial, "w") as handle:
            json.dump({"secrets_file": secrets}, handle)     # has secrets_file, lacks the rest
        os.environ[CONFIG_ENV] = partial
        try:
            reset_config()
            ck("a key a call does NOT need is not demanded (_secret with only 'secrets_file')",
               _secret("K") is None)
            try:
                _const("CRANKD")
                ck("a constant whose key is absent throws", False, "returned instead")
            except ConfigError as exc:
                ck("an incomplete config throws ConfigError naming the missing key",
                   "'crankd_url_env'" in str(exc) or "'crankd_url'" in str(exc), str(exc))
        finally:
            os.environ.pop(CONFIG_ENV, None)
            reset_config()

        print("-- config templates and types", file=out)
        with using_config(cfg(wallet_argv=["{wallet}", "{nope}"]), base=root):
            try:
                sign_digest("d")
                ck("an unknown placeholder in wallet_argv throws", False, "returned instead")
            except ConfigError as exc:
                ck("an unknown placeholder in wallet_argv -> ConfigError naming the key",
                   "wallet_argv" in str(exc), str(exc))
        with using_config(cfg(timeout="5"), base=root):
            try:
                _get("http://127.0.0.1:1/")
                ck("a wrongly-typed timeout throws", False, "returned instead")
            except ConfigError:
                ck("a wrongly-typed timeout ('5') -> ConfigError", True)
        with using_config(cfg(digest_route="/d?c={bogus}"), base=root):
            try:
                _template_setting("digest_route", component="c")
                ck("an unknown placeholder in a route throws", False, "returned instead")
            except ConfigError:
                ck("an unknown placeholder in a route -> ConfigError", True)
        with using_config(cfg(), base=root):
            ck("a component containing braces is substituted LITERALLY, not re-expanded",
               _template_setting("digest_route", component="{x}") == "/digest?component={x}")
            ck("config_template() carries every key this module reads",
               set(config_template()) >= {"jail_python", "secrets_file", "crankd_url",
                                          "crankd_url_env", "congruency_url", "congruency_url_env",
                                          "wallet_bin", "wallet_bin_env", "approver",
                                          "api_key_secret", "pubkey_secret", "api_key_header",
                                          "post_headers", "timeout", "wallet_argv", "digest_route",
                                          "approval_route", "approve_route"})
            ck("jail_python: null disables the self-heal (it returns without exec'ing)",
               jail_python() is None and _reexec_into_jail() is None)

    finally:
        shutil.rmtree(root, ignore_errors=True)
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        globals()["_ACTIVE"], globals()["_RESOLVED"], globals()["_INIT_ERROR"] = saved_state[:3]
        for name in CONSTANTS:
            globals().pop(name, None)
        globals().update(saved_state[3])

    failed = [name for name, ok in checks if not ok]
    print("\n%d/%d checks passed%s"
          % (len(checks) - len(failed), len(checks),
             "" if not failed else " — FAILED: %s" % ", ".join(failed)), file=out)
    return 0 if not failed else 1


# ──────────────────── the packaging, checked against itself ────────────────────

def check_package(stream=None):
    """Prove this package's DERIVED pyproject.toml is coherent with this module. Returns 0/1.

    Checks what an install depends on: that the pyproject parses, declares the import package this
    module names, maps it onto this directory, ships registry.json as package data, and declares a
    console script whose `module:function` target names this module's `main`.

    It does NOT import the package. Importing this module from a non-jail interpreter re-execs and
    never returns (see the module docstring), and importing it a SECOND time under a different name
    would run the self-heal and the constants again for no gain. The console-script target is checked
    against THIS module object instead — the same code the generated wrapper imports.
    """
    out = stream or sys.stdout
    checks = []

    def ck(name, ok, detail=""):
        checks.append((name, bool(ok)))
        print("  %-4s %s%s" % ("PASS" if ok else "FAIL", name,
                               "" if ok else "   <- %s" % detail), file=out)

    try:
        import tomllib
    except ImportError:
        print("check_package: needs Python 3.11+ for tomllib; skipped", file=out)
        return 0

    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "pyproject.toml")
    print("== packaging: %s" % path, file=out)
    if not os.path.isfile(path):
        ck("pyproject.toml exists", False, "not found — the package cannot install")
        return 1
    with open(path, "rb") as handle:
        data = tomllib.load(handle)

    ck("pyproject.toml parses as TOML", True)
    tool = data.get("tool", {}).get("setuptools", {})
    ck("declares the import package %r" % IMPORT_PACKAGE,
       IMPORT_PACKAGE in tool.get("packages", []), repr(tool.get("packages")))
    ck("maps %r onto this directory" % IMPORT_PACKAGE,
       tool.get("package-dir", {}).get(IMPORT_PACKAGE) == ".", repr(tool.get("package-dir")))
    ck("ships %s as package data (so a non-editable install can still see its config)"
       % REGISTRY_NAME,
       REGISTRY_NAME in tool.get("package-data", {}).get(IMPORT_PACKAGE, []),
       repr(tool.get("package-data")))
    ck("declares a build backend",
       bool(data.get("build-system", {}).get("build-backend")), repr(data.get("build-system")))
    ck("names a distribution", bool(data.get("project", {}).get("name")))

    stem = os.path.splitext(os.path.basename(os.path.abspath(__file__)))[0]
    scripts = data.get("project", {}).get("scripts", {})
    target = "%s.%s:main" % (IMPORT_PACKAGE, stem)
    named = [name for name, value in scripts.items() if value == target]
    ck("declares a console script pointing at %s" % target, bool(named), repr(scripts))
    ck("this module exposes the original's callable surface, so that target and every existing "
       "caller resolve",
       all(callable(globals().get(n)) for n in
           ("_secret", "_get", "_cong_post", "sign_digest", "verifies_locally", "main")),
       repr([n for n in ("_secret", "_get", "_cong_post", "sign_digest", "verifies_locally",
                         "main") if not callable(globals().get(n))]))

    registry = os.path.join(here, REGISTRY_NAME)
    if os.path.isfile(registry):
        with open(registry) as handle:
            document = json.load(handle)
        node = document
        ok = True
        for key in UNIT_PATH:
            if not isinstance(node, dict) or key not in node:
                ok = False
                break
            node = node[key]
        ck("registry.json carries this unit's own %s section" % ".".join(UNIT_PATH), ok)
        if ok:
            required = set(config_template()) - {"bug_reports"}
            ck("that section has every key this module requires",
               required <= set(node), repr(sorted(required - set(node))))
        siblings = document.get("forge2", {}).get("agent_tools_suite", {})
        ck("no sibling's registry section was dropped (this unit only ADDS its own key)",
           UNIT_PATH[-1] in siblings, repr(sorted(siblings)))
    else:
        ck("registry.json exists", False, "not found")

    failed = [name for name, ok in checks if not ok]
    print("\n%d/%d checks passed%s"
          % (len(checks) - len(failed), len(checks),
             "" if not failed else " — FAILED: %s" % ", ".join(failed)), file=out)
    return 0 if not failed else 1


if __name__ == "__main__":
    main()
