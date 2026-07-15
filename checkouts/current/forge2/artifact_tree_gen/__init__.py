"""forge2 rewrite of the forge repo `artifact_tree_gen` — behavior-preserving, installable,
control-config'd Python, per the FORGE-wide refactor standard #200.

Each module here is an entirely new implementation of one forge unit, keeping that unit's
observable behavior and callable surface. Every unit is driven by a config object read from
the `registry.json` beside this file, and throws rather than guessing a default when it
cannot see one. See each module's own docstring for its surface, its config and how to run
its `selftest`.

This package re-exports each unit's FUNCTION for convenience, so after `import
artifact_tree_gen` the attribute `artifact_tree_gen.fib` is the function, not the module of
the same name. `from artifact_tree_gen.fib import fib` is unaffected and is the form to
prefer when you want the module.

Only `fib` is re-exported below: ticket #405 filed this package around that one unit, and a
sibling module is re-exported when its own ticket says so. Every module in this directory is
importable as a submodule regardless — `from artifact_tree_gen import add`.
"""

from .fib import ConfigError, configure, fib, using_config  # noqa: F401

__all__ = ["fib", "ConfigError", "configure", "using_config"]
