#!/usr/bin/env python3
"""forge2 / code__code-invalid__coupler / coupler_tool — the console script and the selftest
for the `coupler` unit (ticket #397, module key forge-rw:d80efda05c1fe99b).

WHY THIS MODULE IS NOT INSIDE THE `coupler` PACKAGE
---------------------------------------------------
Importing ANY module under `coupler/` runs `coupler/__init__.py` first, and that file is
config-gated on purpose: it raises `ConfigError` when it cannot see its config object
(ticket #397 acceptance item (d)). A console script rooted inside the package would therefore
die with an import-time traceback on precisely the misconfiguration it exists to report as one
clean line, and a selftest rooted inside the package could not run at all without the very
config whose absence it has to test. Both live out here instead, as a top-level module in the
same distribution, and import `coupler` lazily inside a `try`. `pyproject.toml` ships it via
`py-modules = ["coupler_tool"]`.

WHAT THE SELFTEST PROVES, AND HOW
---------------------------------
Ticket #397 records that criteria_miner captured NO behavioral exemplars for this module —
"no function in this module is minable" — and that the work therefore moves to writing the
equivalence exemplars by hand from the original's behavior. Rather than hand-copy expected
values into a table and hope they are right, this selftest embeds THE ORIGINAL'S OWN 132
BYTES (`ORIGINAL_SOURCE`, verbatim from the ticket, length-checked) and runs it as an ORACLE:
every scenario below is executed twice under identical staged conditions — once by the
original, once by the rewrite — and the two results are compared. The expected values are
taken from the original as it runs, not asserted by the author.

"Staged conditions" means `sys.modules["importlib.metadata"]` is temporarily replaced, which
is what both the original and the rewrite resolve their `from importlib.metadata import
version` against. That lets the scenarios reach states the host machine cannot otherwise be
put into — the distribution being installed, the metadata backend raising, the module being
unimportable at all.

For each scenario the compared result is a `(version_string, version_name_is_bound)` pair,
because BOTH are surface: the original's `from ... import version` leaks `version` into the
module namespace, and whether that name exists depends on which step failed.

RUNNING IT
----------
Every command below is executable as written from this file's own directory; from anywhere
else, give the full path to `coupler_tool.py` instead of the bare name. Once the package is
installed, `coupler-version` is the same tool.

    python3 coupler_tool.py selftest       # differential proof against the original
    python3 coupler_tool.py show           # the resolved __version__ and where config came from
    python3 coupler_tool.py show-config    # the config object in force and its source
    python3 coupler_tool.py emit-config    # print a config-object template

SIDE EFFECTS
------------
`show`, `show-config`, `emit-config` and `selftest` write no files of their own and modify
nothing in the package — checked by hashing every file in a pristine copy of the package
before and after each run, with nothing else touching it. The one thing that does appear on
disk is CPython's own `coupler/__pycache__/*.pyc` bytecode cache, which the interpreter
writes when it imports any module and which `.gitignore` excludes; that is the interpreter's
doing, not this tool's, and it is named here rather than claimed away.

The selftest builds its config objects in memory and restores every global it touches:
`sys.modules["importlib.metadata"]`, the injected config, and `$COUPLER_CONFIG`. It does not
create the registry's `logs/` directory.

Per `note-for-claude` ("all tools need to pass a bug-report automatically ... if an exception
is thrown") the CLI appends one timestamped JSON line to the config's `bug_reports` path if
it hits an UNEXPECTED exception. A `ConfigError` is designed behavior, not a bug, so it files
no report and prints no traceback: it exits 2 with a single self-explaining line.
"""

import argparse
import contextlib
import json
import os
import subprocess
import sys
import traceback
import types
from datetime import datetime

#: The package root — the directory holding this file, `pyproject.toml`, `registry.json` and
#: the `coupler/` package. Subprocess checks below run with this on `sys.path`.
PKG_ROOT = os.path.dirname(os.path.abspath(__file__))

#: The ORIGINAL forge unit, verbatim — the 132 bytes ticket #397 embeds as "the
#: behavior-preserving basis". This is the oracle: the selftest EXECUTES it and compares the
#: rewrite against what it actually does. `_check_oracle_bytes` asserts the length below, so
#: a typo in this constant fails the selftest rather than silently weakening it.
ORIGINAL_SOURCE = (
    'try:\n'
    '    from importlib.metadata import version\n'
    '    __version__ = version("coupler")\n'
    'except Exception:\n'
    '    __version__ = "0.0.dev0"\n'
)

#: The size ticket #397 records for this module, and the two values it hardcoded. The
#: rewrite reads these from config; the ORACLE has them baked in, so the selftest uses these
#: constants only to drive the rewrite into the same shape the oracle is stuck in.
ORIGINAL_SIZE = 132
ORIGINAL_DISTRIBUTION = "coupler"
ORIGINAL_FALLBACK = "0.0.dev0"

METADATA = "importlib.metadata"


# ─────────────────────────── the oracle and the staging ───────────────────────────

def run_original():
    """Execute the ORIGINAL unit's own bytes in a fresh namespace; return its surface.

    Returns:
        A `(version_string, version_name_is_bound)` tuple: what the original leaves in
        `__version__`, and whether its `from importlib.metadata import version` left the name
        `version` behind. `BaseException` is not caught here — if the original lets one
        through, so does this, and the caller compares that against the rewrite.
    """
    namespace = {}
    exec(compile(ORIGINAL_SOURCE, "<original:coupler/__init__.py>", "exec"), namespace)
    return namespace.get("__version__"), ("version" in namespace)


def run_rewrite(distribution=ORIGINAL_DISTRIBUTION, fallback=ORIGINAL_FALLBACK):
    """Run the rewrite's core over the same ground the oracle covers; return its surface.

    Returns the same `(version_string, version_name_is_bound)` shape as `run_original`, so
    the two are directly comparable. `coupler.resolve_version` returns the callable itself
    where the module binds the name `version`; presence of that callable is exactly the
    condition under which `coupler.version` exists (see `coupler/__init__.py`).
    """
    import coupler

    version_string, version_callable = coupler.resolve_version(distribution, fallback)
    return version_string, (version_callable is not None)


def _fake_metadata(version_impl):
    """Build a stand-in `importlib.metadata`. Pass None to omit the `version` attribute,
    which makes `from importlib.metadata import version` raise ImportError."""
    module = types.ModuleType(METADATA)
    if version_impl is not None:
        module.version = version_impl
    return module


@contextlib.contextmanager
def staged_metadata(module):
    """Temporarily install `module` as `sys.modules["importlib.metadata"]`.

    Pass a module object, or None to poison the name so importing it raises ImportError.

    Restoring is done by DELETING the key when it was not there to begin with, never by
    writing the saved None back: a None in `sys.modules` is not an empty slot, it is an
    instruction to the import system to raise ImportError, so restoring one would leave
    `importlib.metadata` broken for the rest of the process.
    """
    was_present = METADATA in sys.modules
    saved = sys.modules.get(METADATA)
    sys.modules[METADATA] = module
    try:
        yield
    finally:
        if was_present:
            sys.modules[METADATA] = saved
        else:
            sys.modules.pop(METADATA, None)


def _raiser(exc):
    def version(distribution):
        raise exc
    return version


def _returner(value):
    def version(distribution):
        return value
    return version


def _package_not_found():
    """The real PackageNotFoundError if this host has it, else a stand-in.

    This is the exception a live `importlib.metadata.version` raises for a distribution that
    is not installed — the single most common way this unit's fallback is reached.
    """
    try:
        from importlib.metadata import PackageNotFoundError
        return PackageNotFoundError("coupler")
    except Exception:
        return LookupError("coupler")


#: Every scenario the differential covers. Each is (label, staged-module) where the staged
#: module replaces `importlib.metadata` for both the oracle and the rewrite. `_ABSENT` (None)
#: poisons the import outright.
#:
#: These reach what sampling cannot: the distribution being installed (the host cannot be put
#: in that state for an arbitrary version string), each distinct failure step, and the
#: difference between "the lookup failed" and "the import failed" — which the original does
#: NOT treat alike, because only the first leaves `version` bound.
SCENARIOS = [
    ("distribution installed, version '1.2.3'",
     _fake_metadata(_returner("1.2.3"))),
    ("distribution installed, version equal to the fallback string",
     _fake_metadata(_returner(ORIGINAL_FALLBACK))),
    ("distribution installed, empty version string",
     _fake_metadata(_returner(""))),
    ("distribution installed, PEP 440 dev version",
     _fake_metadata(_returner("2.0.1.dev7+g1234abc"))),
    ("not installed: version() raises PackageNotFoundError",
     _fake_metadata(_raiser(_package_not_found()))),
    ("version() raises a bare Exception",
     _fake_metadata(_raiser(Exception("metadata backend exploded")))),
    ("version() raises ValueError",
     _fake_metadata(_raiser(ValueError("bad metadata")))),
    ("version() raises OSError",
     _fake_metadata(_raiser(OSError("site-packages unreadable")))),
    ("importlib.metadata exists but has no `version` attribute (ImportError)",
     _fake_metadata(None)),
    ("importlib.metadata cannot be imported at all (None in sys.modules)",
     None),
]


# ─────────────────────────────── the selftest ───────────────────────────────

class _Report:
    """Tallies checks and prints one PASS/FAIL line each."""

    def __init__(self, stream):
        self.stream = stream
        self.checks = 0
        self.failures = []

    def check(self, ok, label):
        self.checks += 1
        if not ok:
            self.failures.append(label)
        print("  %s  %s" % ("PASS" if ok else "FAIL", label), file=self.stream)
        return ok

    def section(self, title):
        print("\n%s" % title, file=self.stream)

    def raises(self, exc_type, label, fn, *args, **kwargs):
        """Check that `fn` raises `exc_type`; report what it did instead if not."""
        try:
            result = fn(*args, **kwargs)
        except exc_type:
            return self.check(True, label)
        except BaseException as exc:  # noqa: BLE001
            return self.check(False, "%s — raised %s instead: %s"
                              % (label, type(exc).__name__, exc))
        return self.check(False, "%s — returned %r instead of raising" % (label, result))


def _code_string_literals(path):
    """Return every string constant in `path` that is NOT a docstring.

    Used to prove acceptance item (d)'s "ZERO hardcoded settings" against the source itself.
    A docstring is a string expression standing alone as the first statement of the module, a
    class or a function; those quote the original's values to explain them and are
    documentation, not settings. Comments never reach the AST at all.
    """
    import ast

    with open(path, "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)

    docstring_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstring_nodes.add(id(body[0].value))

    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstring_nodes]


def _run_python(code, env_overrides=None):
    """Run `code` in a fresh interpreter rooted at the package root; return (rc, out, err).

    A subprocess is the only honest way to test IMPORT-time behavior: `coupler/__init__.py`
    resolves its config and its version exactly once, when it is first imported, and this
    process has already imported it.
    """
    env = dict(os.environ)
    env.pop("COUPLER_CONFIG", None)
    env["PYTHONPATH"] = PKG_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    for key, value in (env_overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    proc = subprocess.run([sys.executable, "-c", code], cwd=PKG_ROOT, env=env,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _check_oracle_bytes(report):
    report.section("[1] the oracle is the ticket's bytes")
    size = len(ORIGINAL_SOURCE.encode("utf-8"))
    report.check(size == ORIGINAL_SIZE,
                 "the embedded ORIGINAL_SOURCE is %d bytes, the size ticket #397 records (%d)"
                 % (size, ORIGINAL_SIZE))

    # Prove the oracle really is hardcoded to the two values the rewrite reads from config —
    # this is what the "no hardcoded params" requirement is measured against.
    seen = []

    def recorder(distribution):
        seen.append(distribution)
        return "recorded"

    with staged_metadata(_fake_metadata(recorder)):
        run_original()
    report.check(seen == [ORIGINAL_DISTRIBUTION],
                 "the original hardcodes its distribution name: it called version(%r)"
                 % (seen[0] if seen else None))

    with staged_metadata(_fake_metadata(_raiser(Exception("x")))):
        fallback_value, _ = run_original()
    report.check(fallback_value == ORIGINAL_FALLBACK,
                 "the original hardcodes its fallback: it produced %r" % (fallback_value,))


def _check_differential(report):
    report.section("[2] differential vs the original — identical staging, both executed")
    for label, module in SCENARIOS:
        with staged_metadata(module):
            expected = run_original()      # the oracle decides what is correct
            actual = run_rewrite()         # the rewrite must agree
        same = (actual == expected
                and type(actual[0]) is type(expected[0]))
        report.check(same,
                     "%s -> original %r, rewrite %r" % (label, expected, actual)
                     + ("" if same else "   <-- MISMATCH"))


def _check_real_metadata(report):
    report.section("[3] differential against the REAL importlib.metadata (no staging)")
    expected = run_original()
    actual = run_rewrite()
    report.check(actual == expected,
                 "unstaged, this host: original %r, rewrite %r" % (expected, actual))


def _check_base_exception(report):
    report.section("[4] `except Exception` spares BaseException — in both")
    for exc_type in (KeyboardInterrupt, SystemExit):
        with staged_metadata(_fake_metadata(_raiser(exc_type("interrupted")))):
            original_propagated = False
            try:
                run_original()
            except exc_type:
                original_propagated = True

            rewrite_propagated = False
            try:
                run_rewrite()
            except exc_type:
                rewrite_propagated = True

        report.check(original_propagated and rewrite_propagated,
                     "%s out of version() propagates — original %s, rewrite %s (neither "
                     "reports it as the fallback)"
                     % (exc_type.__name__,
                        "propagated" if original_propagated else "SWALLOWED",
                        "propagated" if rewrite_propagated else "SWALLOWED"))


def _check_config_driven(report):
    report.section("[5] the two parameters are config-driven, not hardcoded")
    import coupler

    seen = []

    def recorder(distribution):
        seen.append(distribution)
        raise _package_not_found()

    with staged_metadata(_fake_metadata(recorder)):
        with coupler.using_config({"distribution": "some-other-dist",
                                   "fallback": "SENTINEL-FALLBACK"}):
            version_string, _ = coupler.version_from_config()
    report.check(seen == ["some-other-dist"],
                 "the distribution looked up comes from config: version(%r) was called"
                 % (seen[0] if seen else None))
    report.check(version_string == "SENTINEL-FALLBACK",
                 "the fallback comes from config: a config fallback of 'SENTINEL-FALLBACK' "
                 "produced %r (the original's hardcoded %r would be a failure here)"
                 % (version_string, ORIGINAL_FALLBACK))

    with staged_metadata(_fake_metadata(_returner("3.3.3"))):
        with coupler.using_config({"distribution": "anything", "fallback": ""}):
            empty_fallback, _ = coupler.version_from_config()
    report.check(empty_fallback == "3.3.3",
                 "a config-supplied version still wins over the fallback (%r)"
                 % (empty_fallback,))

    with staged_metadata(_fake_metadata(_raiser(_package_not_found()))):
        with coupler.using_config({"distribution": "anything", "fallback": ""}):
            empty_fallback, _ = coupler.version_from_config()
    report.check(empty_fallback == "",
                 "an EMPTY fallback is a legitimate config value, not a missing one (%r)"
                 % (empty_fallback,))

    # Acceptance item (d) says "ZERO hardcoded settings". Prove it mechanically rather than
    # by assertion: parse the rewritten unit and confirm neither of the original's two
    # parameters survives as a string literal anywhere in its EXECUTABLE code. Docstrings are
    # excluded — they quote both values to explain them, which is documentation, not a
    # setting. (config_template() in _config.py does hold them, as scaffolding printed on
    # request; the gate checks above prove it is never applied as a default.)
    literals = _code_string_literals(os.path.join(PKG_ROOT, "coupler", "__init__.py"))
    leaked = sorted(l for l in literals if l in (ORIGINAL_DISTRIBUTION, ORIGINAL_FALLBACK))
    report.check(not leaked,
                 "coupler/__init__.py's executable code contains neither %r nor %r as a "
                 "literal — the settings live in config, not source%s"
                 % (ORIGINAL_DISTRIBUTION, ORIGINAL_FALLBACK,
                    "" if not leaked else " (found: %s)" % leaked))

    # The shipped registry must carry the original's values, or an ordinary import of this
    # package would not reproduce the original.
    shipped, _, source = coupler.load_config()
    report.check(shipped.get("distribution") == ORIGINAL_DISTRIBUTION
                 and shipped.get("fallback") == ORIGINAL_FALLBACK,
                 "the shipped registry carries the original's two values "
                 "(distribution=%r, fallback=%r) from %s"
                 % (shipped.get("distribution"), shipped.get("fallback"),
                    os.path.relpath(source, PKG_ROOT) if os.path.isabs(source) else source))


def _check_config_gate(report):
    report.section("[6] the config gate — a tool that cannot see its config throws")
    import coupler

    report.raises(coupler.ConfigError,
                  "a config object with no 'distribution' raises ConfigError",
                  coupler.version_from_config, {"fallback": "x"})
    report.raises(coupler.ConfigError,
                  "a config object with no 'fallback' raises ConfigError",
                  coupler.version_from_config, {"distribution": "coupler"})
    report.raises(coupler.ConfigError,
                  "a non-string 'distribution' raises ConfigError (not swallowed as fallback)",
                  coupler.version_from_config, {"distribution": 123, "fallback": "x"})
    report.raises(coupler.ConfigError,
                  "an empty 'distribution' raises ConfigError",
                  coupler.version_from_config, {"distribution": "", "fallback": "x"})
    report.raises(coupler.ConfigError,
                  "a non-string 'fallback' raises ConfigError",
                  coupler.version_from_config, {"distribution": "coupler", "fallback": 5})
    report.raises(coupler.ConfigError,
                  "a config object that is not a dict raises ConfigError",
                  coupler.version_from_config, ["not", "a", "dict"])

    # The error names the key, so the operator can act on it without reading the source.
    try:
        coupler.version_from_config({"fallback": "x"})
        message = ""
    except coupler.ConfigError as exc:
        message = str(exc)
    report.check("distribution" in message,
                 "the ConfigError names the missing key: %r" % message)

    # A ConfigError must never be reported as the fallback. Staged so that if the gate DID
    # leak into the guarded lookup, the result would be the fallback rather than an error.
    with staged_metadata(_fake_metadata(_returner("9.9.9"))):
        report.raises(coupler.ConfigError,
                      "a config error is never swallowed and reported as the fallback",
                      coupler.version_from_config, {"distribution": None, "fallback": "x"})

    # $COUPLER_CONFIG pointing at a file that does not exist outranks the registry walk-up,
    # so this proves the gate whether or not a registry is installed near the package.
    saved_env = os.environ.get(coupler.CONFIG_ENV)
    os.environ[coupler.CONFIG_ENV] = os.path.join(PKG_ROOT, "no-such-config-file.json")
    try:
        coupler.reset_config()
        report.raises(coupler.ConfigError,
                      "$%s naming a missing file raises ConfigError" % coupler.CONFIG_ENV,
                      coupler.load_config)
    finally:
        if saved_env is None:
            os.environ.pop(coupler.CONFIG_ENV, None)
        else:
            os.environ[coupler.CONFIG_ENV] = saved_env
        coupler.reset_config()


def _check_module_surface(report):
    report.section("[7] the module-level surface, in fresh interpreters")

    # The plain import: what any existing caller does.
    rc, out, err = _run_python(
        "import coupler; print(repr(coupler.__version__)); "
        "print(type(coupler.__version__).__name__); print(hasattr(coupler, 'version'))")
    report.check(rc == 0, "`import coupler` succeeds with the shipped registry (rc=%d) %s"
                 % (rc, err.splitlines()[-1] if rc and err else ""))
    lines = out.splitlines()
    report.check(len(lines) == 3 and lines[1] == "str",
                 "coupler.__version__ is a str: %s" % (lines[0] if lines else "(no output)"))
    report.check(len(lines) == 3 and lines[2] == "True",
                 "coupler.version is bound (importlib.metadata imports on this host)")

    # Module-level differential: the ORIGINAL and the REWRITTEN MODULE, same staging, same
    # interpreter. This is the surface an existing caller actually touches.
    for label, stage_code, expect_bound in (
        ("staged installed version '7.7.7'",
         "m = types.ModuleType('importlib.metadata'); m.version = lambda d: '7.7.7'; "
         "sys.modules['importlib.metadata'] = m", True),
        ("staged unimportable importlib.metadata",
         "sys.modules['importlib.metadata'] = None", False),
    ):
        code = (
            "import sys, types\n"
            + stage_code + "\n"
            + "ns = {}\n"
            + "exec(compile(%r, '<original>', 'exec'), ns)\n" % ORIGINAL_SOURCE
            + "import coupler\n"
            + "print(ns.get('__version__') == coupler.__version__ and "
              "('version' in ns) == hasattr(coupler, 'version'))\n"
            + "print(repr(ns.get('__version__')), repr(coupler.__version__), "
              "'version' in ns, hasattr(coupler, 'version'))\n"
        )
        rc, out, err = _run_python(code)
        lines = out.splitlines()
        report.check(rc == 0 and lines and lines[0] == "True",
                     "module-level differential, %s -> %s"
                     % (label, lines[1] if len(lines) > 1 else ("rc=%d %s" % (rc, err))))

        # And the `version` name behaves as an absent name should when the import failed.
        probe = (
            "import sys, types\n"
            + stage_code + "\n"
            + "import coupler\n"
            + "try:\n"
            + "    from coupler import version\n"
            + "    print('bound')\n"
            + "except ImportError:\n"
            + "    print('absent')\n"
        )
        rc, out, err = _run_python(probe)
        report.check(rc == 0 and out == ("bound" if expect_bound else "absent"),
                     "`from coupler import version` is %s, %s (got %r)"
                     % ("bound" if expect_bound else "absent", label, out))

    # `from coupler import *` must not export __version__ — it never did, because the name
    # is underscore-prefixed.
    rc, out, err = _run_python(
        "ns = {}\n"
        "exec('from coupler import *', ns)\n"
        "print('__version__' in ns, 'version' in ns)\n")
    report.check(rc == 0 and out == "False True",
                 "`from coupler import *` exports `version` but not `__version__`, as the "
                 "original did (got %r)" % out)

    # The import-time gate, in a fresh interpreter: no config, no version, no guess.
    rc, out, err = _run_python(
        "import coupler; print(coupler.__version__)",
        env_overrides={"COUPLER_CONFIG": os.path.join(PKG_ROOT, "no-such-config-file.json")})
    report.check(rc != 0 and "ConfigError" in err,
                 "`import coupler` with an unresolvable config raises ConfigError and "
                 "computes no version (rc=%d)" % rc)
    report.check("0.0.dev0" not in out,
                 "...and it does NOT guess the original's hardcoded fallback (stdout %r)" % out)


def selftest(stream=None):
    """Prove this rewrite against ticket #397's acceptance items (a), (b) and (d).

    Runs the ORIGINAL's own embedded bytes as an oracle and compares the rewrite against what
    that oracle actually does, under staged conditions neither could otherwise reach. Builds
    its config objects in memory, writes no files, and restores every global it touches.

    Returns the number of failures.
    """
    out = stream or sys.stdout
    report = _Report(out)

    print("selftest: forge2 rewrite of code__code-invalid__coupler:coupler/__init__.py "
          "(ticket #397)", file=out)
    print("oracle:   the original's own %d bytes, executed — not a hand-written "
          "expectation table" % ORIGINAL_SIZE, file=out)

    saved_env = os.environ.pop("COUPLER_CONFIG", None)
    try:
        import coupler
        coupler.reset_config()

        _check_oracle_bytes(report)
        _check_differential(report)
        _check_real_metadata(report)
        _check_base_exception(report)
        _check_config_driven(report)
        _check_config_gate(report)
        _check_module_surface(report)
    finally:
        if saved_env is not None:
            os.environ["COUPLER_CONFIG"] = saved_env
        try:
            import coupler
            coupler.reset_config()
        except Exception:  # noqa: BLE001
            pass

    print("\n%s — %d checks, %d failure(s)"
          % ("SELFTEST PASSED" if not report.failures else "SELFTEST FAILED",
             report.checks, len(report.failures)), file=out)
    for failure in report.failures:
        print("  failed: %s" % failure, file=out)
    return len(report.failures)


# ─────────────────────────────── the command line ───────────────────────────────

def _bug_report(exc, formatted, argv):
    """Append one timestamped bug-report line for an UNEXPECTED exception.

    Required by note-for-claude ("all tools need to pass a bug-report automatically ...
    Filename - function name - time of occurance - methods to reproduce - possible cause").
    Best-effort and silent on failure: a tool that cannot file a report must still report its
    original error, and no report is ever filed for a ConfigError, which is designed behavior
    rather than a bug. Returns the path written, or None.
    """
    try:
        from coupler import _config
        config = _config.active_config()
        base = _config.active_base()
    except Exception:  # noqa: BLE001
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
        "methods-to-reproduce": "python3 %s %s"
                                % (os.path.basename(os.path.abspath(__file__)),
                                   " ".join(argv)),
        "possible-cause": "%s: %s" % (type(exc).__name__, exc),
        "traceback": formatted.strip().splitlines()[-6:],
        "note": "forge2:code__code-invalid__coupler/coupler (ticket #397, module key "
                "forge-rw:d80efda05c1fe99b)",
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return path
    except OSError:
        return None


def _build_parser():
    # Imported lazily and defensively: building the parser must not depend on the config
    # gate, or `--help` would fail on exactly the misconfiguration it should explain.
    try:
        from coupler._config import CONFIG_ENV, REGISTRY_NAME, UNIT_PATH
        env, registry, unit_path = CONFIG_ENV, REGISTRY_NAME, ".".join(UNIT_PATH)
    except Exception:  # noqa: BLE001
        env, registry, unit_path = "COUPLER_CONFIG", "registry.json", "forge2...coupler"

    parser = argparse.ArgumentParser(
        prog="coupler-version",
        description="forge2 rewrite of the forge unit "
                    "code__code-invalid__coupler:coupler/__init__.py (ticket #397). "
                    "Config-driven: every command below except `emit-config` and `selftest` "
                    "throws if it cannot see its config object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="config is read from the file named by $%s, else from the %s section of the "
               "nearest %s found by walking up from the coupler package. Run `emit-config` "
               "for a template." % (env, unit_path, registry),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="print the resolved __version__ and where it came from")
    sub.add_parser("show-config", help="print the config object in force and its source")
    sub.add_parser("emit-config", help="print a template of this unit's config object")
    sub.add_parser("selftest",
                   help="prove the rewrite against the original, which it embeds and runs")
    return parser


def main(argv=None):
    """Entry point for the `coupler-version` console script. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(argv)

    # Imported here, not at module scope, so a ConfigError raised by the package's import-time
    # gate is caught below and reported as one line rather than an import traceback.
    try:
        if args.command == "emit-config":
            from coupler._config import CONFIG_ENV, REGISTRY_NAME, UNIT_PATH, config_template
            print(json.dumps(config_template(), indent=2))
            print("\n# Install this at %s in your %s, or save it to a file and point $%s at "
                  "it.\n# Until it is installed, `import coupler` throws — it will not guess "
                  "a default." % (" -> ".join(UNIT_PATH), REGISTRY_NAME, CONFIG_ENV),
                  file=sys.stderr)
            return 0

        if args.command == "selftest":
            return 0 if selftest() == 0 else 1

        if args.command == "show-config":
            import coupler
            print(json.dumps({"unit": coupler.UNIT, "source": coupler.active_source(),
                              "base": coupler.active_base(),
                              "config": coupler.active_config()}, indent=2))
            return 0

        if args.command == "show":
            import coupler
            print(json.dumps({
                "unit": coupler.UNIT,
                "__version__": coupler.__version__,
                "distribution": coupler.active_config().get("distribution"),
                "installed": coupler.__version__ != coupler.active_config().get("fallback"),
                "version_re_exported": hasattr(coupler, "version"),
                "config_source": coupler.active_source(),
            }, indent=2))
            return 0

    except Exception as exc:  # noqa: BLE001
        # ConfigError is designed behavior, not a bug: one self-explaining line, no
        # traceback, no bug report. It is matched by name rather than by `except
        # ConfigError`, because the import that would bind that name is the very thing that
        # may have raised.
        if type(exc).__name__ == "ConfigError":
            print("config error: %s" % exc, file=sys.stderr)
            return 2
        path = _bug_report(exc, traceback.format_exc(), argv)
        print("EXCEPTION — %s" % ("bug report filed at %s" % path if path
                                  else "no bug report could be filed"), file=sys.stderr)
        raise

    return 0


if __name__ == "__main__":
    sys.exit(main())
