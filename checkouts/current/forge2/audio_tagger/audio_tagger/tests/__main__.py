# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 testmonkeyalpha — Claude & Co.
"""Make `python3 -m audio_tagger.tests` run this package's config-driven test tool.

This is packaging, not a rewrite of any forge unit: a package `__init__.py` cannot be run as
a script (`python3 __init__.py` has no package around it to discover), so ticket #387's unit
needs this three-line launcher to be runnable without being installed first. It adds no
behavior of its own — every command, every exit code and the config gate all live in
`__init__.py`, whose header documents them.

    python3 -m audio_tagger.tests                # discover + run this package's tests
    python3 -m audio_tagger.tests list
    python3 -m audio_tagger.tests show-config
    python3 -m audio_tagger.tests emit-config

Run it from the PACKAGE ROOT (`forge2/audio_tagger/`, the directory holding pyproject.toml),
or from anywhere once `pip install -e .` has been run there.

This file is named `__main__.py`, so `unittest` discovery never collects it: the config's
`pattern` is `test*.py`, which `__main__.py` does not match.
"""

import sys

from . import main

if __name__ == "__main__":
    sys.exit(main())
