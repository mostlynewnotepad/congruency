# Additive packaging for forge2 rewrite units (#410)

## The problem (proven)

The forge refactor (#201) files **one rewrite unit per unique MODULE** — each unit's
deliverable is a single file `forge2/<repo>/<module>.py`. But `#200` requirement 3 demands each
unit be **installable** (`pip install -e .`), so every unit also hand-authored the package
scaffolding that all modules of a repo **share**:

- `__init__.py` re-exported **only that unit's** symbols (`from .fib import fib`);
- `pyproject.toml`'s `[project.scripts]` listed **only that unit's** console entry (`forge2-fib`);
- `registry.json` carried **only that unit's** config section (`forge2.<repo>.<module>`).

So the 2nd, 3rd, … unit of a repo cannot merge on top of the 1st: its whole-package rewrite
**conflicts** with sibling scaffolding already landed, and where it does land it **clobbers** the
sibling's entry.

**Live evidence** in `checkouts/current/forge2/artifact_tree_gen/`: `add.py` (#401) landed with a
`forge2-add` script and an `add` config section; `fib.py` (#405) then rewrote `pyproject.toml` and
`registry.json` to mention **only fib**, silently dropping both of add's. `clamp.py` (#395), a 3rd
module of that repo, cannot merge at all. The whole `coupler` fan-out
(#389/#391/#393/#399/#403) hits the same wall at scale.

## The chosen approach — A (mirrors #281)

`#281` turned a hardcoded central tag map (which every tag unit rewrote → every tag unit collided)
into per-file registration where each unit only **adds its own file** and nothing central changes.
The same principle here: **a unit writes ONLY its module file; the shared scaffolding is DERIVED
from whatever modules are present, never hand-listed per unit.**

`congruency/tools/forge_package.py` is that derivation. It is a pure function of the package
directory's contents, so it is safe to run after each module lands:

| File | Policy | Why additive |
|------|--------|--------------|
| `pyproject.toml` | **Regenerated** from the union of modules present | Package declared at the **package level** (`packages = ["<pkg>"]` + `package-dir` → `.`), which is how setuptools already includes **every** `.py` in the directory as a submodule — so adding a module needs **no enumeration change for imports**. The only per-module part is `[project.scripts]`, regenerated as the **union** over modules defining a top-level `main()`. Regeneration is a pure function of (repo, module set): idempotent, and can only **grow** the script list on a sequential landing — never drops a sibling. |
| `__init__.py` | **Create-if-absent**, never overwritten | A fresh package gets a minimal `__init__` that hardcodes **no** module list; `from <pkg>.<mod> import <name>` works for every module with zero central edits. An existing `__init__` (e.g. artifact_tree_gen's fib re-export) is **preserved** — regenerating it would be the very clobber we forbid. |
| `registry.json` | Skeleton ensured if absent; existing sections **never** touched | Per-module `forge2.<repo>.<module>` sections are disjoint keys, additive by nature. `merge_registry_section()` lets a unit add its **own** section without reading or rewriting a sibling's. |

### Why this is the #281 property

After the fix, a unit's branch changes exactly one **shared** thing — the regenerated
`pyproject.toml` — and that change is a **superset** of the base's (module set ∪ {this module}).
On the sequential landing pair_loop actually produces (merges serialized by an flock, each new
branch cut from the latest base), the base has not moved, so the merge is clean and pyproject
converges on the full module list. **Imports never conflict at all**, because the package-level
declaration is byte-identical regardless of which modules are present. The only residual conflict
surface is the `[project.scripts]` block under a **true simultaneous race** (two branches cut from
the same base, both landing) — a trivial additive-list merge, strictly better than the status quo
where every 2nd+ unit conflicts unconditionally.

## What was implemented

1. **`congruency/tools/forge_package.py`** (new) — the additive-scaffolding helper. Importable
   (`ensure(pkg_dir)`, `merge_registry_section(pkg_dir, repo, module, section)`) and a CLI
   (`python3 forge_package.py forge2/<repo>`). Pure stdlib. Idempotent — a converged package
   reports `unchanged`/`preserved` and writes nothing.

2. **`congruency/tools/pair_loop.py`** (`commit_deliverable`, `scaffold_forge_package`) — the
   harness now refreshes a forge package's additive scaffolding **right before it stages the
   package** (#409 package scope). This is the production path: the sandboxed worker may only touch
   its one deliverable file, so the harness — which holds the git pen — derives the shared
   scaffolding. A missing/broken helper **raises** rather than silently skipping (skipping would
   re-introduce the clobber).

3. **`congruency/tools/forge_refactor_ticketer.py`** (`module_body`) — the unit body template now
   instructs the worker: **write ONLY your module file** `forge2/<repo>/<module>.py`; do **not**
   hand-author `pyproject.toml`/`__init__.py` (the harness derives them, #410/#281); and add **only
   your own** `forge2.<repo>.<module>` registry section, never a sibling's.

Nothing in the landed `forge2/` packages was modified — the proof runs entirely in a scratch copy.

## Proof — 3 same-package modules landing independently

Simulated in a scratch dir: copied the real `add.py` and `fib.py` from the landed package, wrote a
3rd `clamp.py`, and ran `forge_package.py` after each (as pair_loop would):

```
STEP 1  add   -> pyproject scripts: forge2-add                      (pyproject/init/registry: created)
STEP 2  fib   -> pyproject scripts: forge2-add, forge2-fib          (pyproject: updated; init/registry: preserved)
STEP 3  clamp -> pyproject scripts: forge2-add, forge2-clamp, forge2-fib   (pyproject: updated; init/registry: preserved)
```

The final `pyproject.toml` lists **all three** modules' scripts (it **restored** `forge2-add`,
which fib's clobber had dropped) and `packages = ["artifact_tree_gen"]` maps the dir onto `.`.
`merge_registry_section` accumulated all three config sections additively
(`created → updated → updated`); final registry sections present: `['add', 'clamp', 'fib']` — no
clobber.

Then, in a fresh venv from the package dir:

```
pip install -e .        -> exit 0
python -c import         -> add(2,3)=5   fib(10)=55   clamp(9,0,5)=5   (all three import AND run)
forge2-clamp 9 0 5       -> 5.0          (console script works)
```

Idempotency: re-running `ensure` on the converged package reports `pyproject: unchanged`,
`init: preserved`, `registry: preserved` — no churn. Single-module packages still work
(`lonely_repo` → `forge2-only` script, clean install).

## Acceptance

- Two+ modules of the same forge package land independently and the resulting `forge2/<repo>/` is
  a valid installable package (`pip install -e .` works, all modules import). ✓
- Single-module packages still work. ✓
- Landed packages untouched (non-destructive). ✓

## Next step — re-enable the multi-module fan-out

Re-dispatch the blocked same-package units with a **module-only** deliverable, letting the harness
scaffold:

1. **Re-dispatch #395 (clamp.py)** for `artifact_tree_gen` with deliverable
   `checkouts/current/forge2/artifact_tree_gen/clamp.py` — the worker writes only `clamp.py` and its
   registry section; pair_loop's `commit_deliverable` now regenerates the additive `pyproject.toml`
   (adding `forge2-clamp`, restoring `forge2-add`) and leaves the existing `__init__.py`/sibling
   registry sections intact, so it merges cleanly onto the landed add+fib package.
2. Then the `coupler` fan-out (#389/#391/#393/#399/#403) the same way — each unit now touches only
   its own `forge2/coupler/<module>.py`, so they no longer collide.

(Optional follow-up, not required for acceptance: a one-time `forge_package.py
checkouts/current/forge2/artifact_tree_gen` on a ticket branch would restore the `forge2-add`
console script and add's registry section that fib's #405 clobber dropped from the **already
landed** package.)
