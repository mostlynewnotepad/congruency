# forge2 — `code__code-invalid__coupler` / `coupler`

A behavior-preserving, installable, control-config'd rewrite of the forge unit
`code__code-invalid__coupler:coupler/__init__.py` (module key `forge-rw:d80efda05c1fe99b`),
produced for **ticket #397** against the FORGE-wide refactor standard **#200**.

Ticket #397 supersedes #284: it carries the original module's bytes on the ticket itself, so
the rewrite needs no forge access.

## What the original did

132 bytes:

```python
try:
    from importlib.metadata import version
    __version__ = version("coupler")
except Exception:
    __version__ = "0.0.dev0"
```

It reported the installed version of the distribution named `coupler`, and fell back to
`"0.0.dev0"` if anything at all went wrong — most commonly because the distribution was not
installed, e.g. when running from a source checkout.

## The surface, preserved

The unit defines no function; its surface is the module-level names it binds, and there are
two:

| name | what it is |
| --- | --- |
| `coupler.__version__` | a `str` — the configured distribution's installed version, or the configured fallback |
| `coupler.version` | `importlib.metadata.version`, re-exported as a side effect of the original's module-level `from ... import version` |

`coupler.version` exists **iff the import succeeded** — including when the import succeeded
but the lookup it was imported for then failed, because `from ... import version` had already
bound the name by that point. That is the original's behavior and it is reproduced exactly;
`from coupler import version` therefore keeps working for the common not-installed case.

Two further details of the original's shape are preserved deliberately:

- `except Exception` does not catch `BaseException`, so a `KeyboardInterrupt` out of the
  lookup propagates rather than being reported as the fallback.
- `__version__` is underscore-prefixed, so `from coupler import *` never exported it. It is
  not in `__all__` here either.

## What changed: it is control-config'd (#200 requirement 4)

The original hardcoded its two parameters. Both now come from a config object and **neither
has a default anywhere in the source**:

```json
{"distribution": "coupler", "fallback": "0.0.dev0"}
```

- `distribution` — the non-empty string handed to `importlib.metadata.version`.
- `fallback` — the string `__version__` takes when no version can be determined. May be
  empty; an empty string is a legitimate value, not a missing one.

The config object is resolved from the file named by `$COUPLER_CONFIG` if set, else from the
`forge2 -> code__code-invalid__coupler -> coupler` section of the nearest `registry.json`
found by **walking up from the package directory** (never from the working directory). This
is the `note-for-claude` registry idiom: *".json will have all the configuration - for all
tools in this set of packaging ... if a tool cannot see the registry it will throw an
exeption."*

This package ships that `registry.json` at its root carrying the original's two values, so a
plain `import coupler` from a source checkout or an editable install behaves exactly as the
original did.

**`import coupler` throws without a config.** That is acceptance item (d), and it is the one
place this rewrite intentionally does not mirror the original — which could not have a
missing config because it had no config at all. It does not guess `"coupler"`, does not guess
`"0.0.dev0"`, and does not leave `__version__` unset. The gate is checked *before* the
guarded lookup is entered, so the `except Exception` that implements the fallback can never
swallow a `ConfigError` and report a config mistake as `"0.0.dev0"`.

## Install (#200 requirement 3)

```
pip install -e .
coupler-version show
```

The distribution is named `coupler` because that is the distribution the original module
shipped in and the one its own lookup names — which is what makes the success path reachable:
install it and `coupler.__version__` becomes the `version` in `pyproject.toml`; uninstall it
and `coupler.__version__` becomes the configured fallback. The `pyproject.toml` name and the
registry's `distribution` key are independent knobs that happen to agree; nothing in the
Python source hardcodes either.

## Layout

```
pyproject.toml      the installable package (#200 requirement 3)
registry.json       the config object (#200 requirement 4)
coupler/
  __init__.py       THE UNIT — the rewritten module and its surface
  _config.py        config resolution: $COUPLER_CONFIG, registry walk-up, injection
coupler_tool.py     the `coupler-version` console script and the selftest
```

`coupler_tool.py` is a **top-level** module, not part of the `coupler` package, on purpose:
importing anything under `coupler/` runs `coupler/__init__.py` first, config gate and all, so
a CLI in there would die with a traceback on exactly the misconfiguration it must report as
one clean line, and a selftest in there could not run without the very config whose absence it
has to test.

## Verify it (#200 requirement 1 — verified, not asserted)

```
python3 coupler_tool.py selftest        # or: coupler-version selftest
```

Ticket #397 records that criteria_miner captured **no** behavioral exemplars for this module,
which moves the work to writing the equivalence exemplars by hand. Rather than hand-copy
expected values into a table and hope they are right, the selftest **embeds the original's own
132 bytes and runs them as an oracle**: each scenario is executed twice under identical staged
conditions — once by the original, once by the rewrite — and the results are compared. The
expected values are taken from the original as it runs.

Staging works by temporarily replacing `sys.modules["importlib.metadata"]`, which is what both
the original and the rewrite resolve their import against. That reaches states this host cannot
otherwise be put in: the distribution being installed at an arbitrary version, the metadata
backend raising, the module being unimportable at all. Each scenario compares the full
`(version_string, version_name_is_bound)` pair, because both halves are surface.

41 checks across 7 sections: the oracle's byte count and its hardcoded constants; the
scenario differential; a differential against the real `importlib.metadata`; the
`BaseException` boundary; the two parameters being config-driven (including an AST check that
neither value survives as a literal in the unit's executable code); the config gate; and the
module-level surface in fresh interpreters (including `import coupler` with an unresolvable
config, which must fail and must not print `0.0.dev0`).

Because the checks are differential rather than a fixed expectation table, they stay correct
as the environment moves. Install the distribution and section [3] reports
`original ('1.0.0', True), rewrite ('1.0.0', True)`; uninstall it and both sides read
`('0.0.dev0', True)` together. A hand-written table would have gone red on the environment
rather than on a defect.
