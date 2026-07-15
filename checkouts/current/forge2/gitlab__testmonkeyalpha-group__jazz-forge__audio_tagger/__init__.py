"""forge2 rewrite of the forge repo `gitlab__testmonkeyalpha-group__jazz-forge__audio_tagger` — behavior-preserving, installable,
control-config'd Python, per the FORGE-wide refactor standard #200.

This package is built one module at a time: each forge rewrite unit adds its OWN
`<module>.py` here and NOTHING central (#410, the analogue of the tag-registry fix #281).
This __init__ therefore hardcodes no module list — every module in this directory is
importable directly, e.g. `from gitlab__testmonkeyalpha-group__jazz-forge__audio_tagger.<module> import <name>`, and a `pip install -e .`
from this directory installs them all. A unit that wants a convenience re-export may add one
here for its own symbol without disturbing a sibling's.
"""
