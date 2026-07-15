"""Make `python3 -m audio_tagger ...` run the same command line the installed console script
`forge2-jazz-forge-audio-tagger` runs (ticket #353).

It exists so every invocation in this package's documentation works from a source checkout,
with nothing installed: run from the project root (the directory holding `pyproject.toml`),
which is what puts the `audio_tagger` package on the import path. See `audio_tagger`'s module
docstring, "RUNNING IT".
"""

import sys

from audio_tagger import main

if __name__ == "__main__":
    sys.exit(main())
