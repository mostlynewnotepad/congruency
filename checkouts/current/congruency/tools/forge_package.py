#!/usr/bin/env python3
"""forge_package.py — make a forge2 rewrite package's scaffolding ADDITIVE, so N modules of
one package can land INDEPENDENTLY without clobbering each other (ticket #410, the analogue of
the tag-registry fix #281).

THE PROBLEM THIS FIXES. The forge refactor (#201) files ONE rewrite unit per unique MODULE, and
each unit's deliverable is a single file `forge2/<repo>/<module>.py`. But #200 requirement 3
demands each unit be INSTALLABLE — a `pip install -e .` package — so every unit also hand-authored
the package scaffolding: pyproject.toml, __init__.py and registry.json. Those three files are
SHARED by every module of the same repo, and each unit wrote them as if its module were the only
one:
    * __init__.py re-exported ONLY that unit's symbols (`from .fib import fib`);
    * pyproject.toml's [project.scripts] listed ONLY that unit's console entry (`forge2-fib`);
    * registry.json carried ONLY that unit's config section (`forge2.<repo>.<module>`).
So the 2nd, 3rd, ... unit of a repo cannot merge on top of the 1st: its whole-package rewrite
CONFLICTS with the sibling scaffolding already landed, and — worse — where it does land it
CLOBBERS the sibling's entry (the live proof: forge2/artifact_tree_gen shipped add.py #401 with a
`forge2-add` script and an `add` config section, then fib.py #405 rewrote pyproject.toml and
registry.json to mention only fib, silently DROPPING both of add's). #395 (clamp.py, a 3rd module
of that repo) cannot merge at all, and the whole `coupler` fan-out (#389/#391/#393/#399/#403) hits
the same wall at scale.

THE FIX, mirroring #281. #281 turned a hardcoded central map (which every tag unit rewrote, so
every tag unit collided) into per-file registration where each unit only ADDS its own file and
nothing central changes. Here the same principle: a unit writes ONLY its module file; the shared
scaffolding is DERIVED from whatever modules are present, never hand-listed per unit. This tool is
that derivation, and it is safe to run after each module lands because it is a pure function of the
directory's contents:

  pyproject.toml  — REGENERATED from the union of modules present. The package is declared at the
                    PACKAGE level (`packages = ["<import_pkg>"]` + `package-dir` mapping it onto
                    "."), which is how setuptools already includes EVERY `.py` in the directory as a
                    submodule — so adding a module needs NO enumeration change for imports at all.
                    The only per-module part is [project.scripts], and that is regenerated as the
                    UNION over every module that defines a top-level `main()`. Regeneration is a pure
                    function of (repo name, module set), so it is idempotent (re-running writes the
                    identical bytes and reports no change) and it can only GROW the script list on a
                    sequential landing — it never drops a sibling, which is exactly the clobber #410
                    is about. (It restores forge2-add, which fib's clobber had dropped.)
  __init__.py     — CREATE-IF-ABSENT, never overwritten. A fresh package gets a minimal __init__
                    that hardcodes NO module list, so `pip install -e .` + `from <pkg>.<mod> import
                    <name>` works for every module with zero central edits. An __init__ that already
                    exists (e.g. artifact_tree_gen's, which re-exports fib for convenience) is LEFT
                    UNTOUCHED — regenerating it would be the very clobber we forbid, so this tool
                    does the opposite of the old behavior and preserves it.
  registry.json   — ensured to EXIST with a skeleton if absent, and otherwise left alone. Its
                    per-module config sections are additive by nature (`forge2.<repo>.<module>` keys
                    are disjoint), and `merge_registry_section()` is provided so a unit can add its
                    OWN section without reading or rewriting a sibling's. This tool NEVER deletes or
                    rewrites an existing section.

WHY THIS IS ADDITIVE (the #281 property). After this fix a unit's branch changes exactly one thing
that is shared — the regenerated pyproject.toml — and that change is a SUPERSET of the base's
(module set ∪ {this module}). On the sequential landing that pair_loop actually produces (merges are
serialized by an flock, and each new branch is cut from the latest base), the base has not moved, so
the merge is clean and pyproject converges on the full module list. IMPORTS never conflict at all,
because the package-level declaration is byte-identical regardless of which modules are present. The
only residual conflict surface is the [project.scripts] block under a TRUE simultaneous race (two
branches cut from the same base, both landing), and that is a trivial additive-list merge — strictly
better than the status quo, where every 2nd+ unit conflicts unconditionally.

HOW IT IS DRIVEN. Two integration points, either or both:
  * pair_loop.py calls `ensure()` on a forge package right before it commits it (commit_deliverable,
    #409 package scope), so the scaffolding is refreshed from the module the worker just wrote
    WITHOUT the sandboxed worker — which may only read and write its one deliverable — having to run
    anything. This is the production path.
  * A human or a unit can run it directly:  `python3 forge_package.py forge2/<repo>`  — reports what
    it wrote and what it left, writes nothing it does not have to.

SAFE BY DEFAULT. It only ever touches the three scaffolding files of the directory it is pointed at,
never a module (`*.py` that is not __init__.py is read for its `main()` and never written), never a
sibling's config section, never anything outside the package dir. Re-running on a converged package
writes nothing and reports "no change". Pure stdlib.

Exit 0 on success (including "nothing to do"). Exit 2 with a one-line message on a bad target.
"""
import argparse
import ast
import json
import keyword
import os
import re
import sys


# ── names ─────────────────────────────────────────────────────────────────────────────────────────
def import_pkg_name(repo):
    """The Python import package name for a forge repo directory. Normally the directory basename
    verbatim (artifact_tree_gen -> artifact_tree_gen), but a name that is not a valid identifier
    (a forge mirror like `gitlab__x__y` is fine; a dashed name is not) is sanitized to one so the
    generated package is importable. Leading digits and Python keywords are prefixed."""
    name = re.sub(r"\W", "_", repo)
    if not name or name[0].isdigit() or keyword.iskeyword(name):
        name = "pkg_" + name
    return name


def dist_name(repo):
    """The PEP 503 distribution name: `forge2-<repo>` with underscores/dots normalized to dashes,
    lowercased. artifact_tree_gen -> forge2-artifact-tree-gen (the name the landed package uses)."""
    return "forge2-" + re.sub(r"[_.]+", "-", repo).strip("-").lower()


# ── discovery ─────────────────────────────────────────────────────────────────────────────────────
SCAFFOLD_FILES = ("pyproject.toml", "__init__.py", "registry.json")
# Not source and not ours to enumerate — the same build/cache artifacts pair_loop excludes (#409).
_EXCLUDE_DIRS = ("__pycache__", "build", "dist", ".eggs", ".tox", ".nox", ".venv", "venv",
                 ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git")


def module_stems(pkg_dir):
    """Sorted list of top-level module stems in `pkg_dir`: every `*.py` that is not __init__.py and
    not under an excluded build/cache directory. Deterministic, so the regenerated pyproject is a
    pure function of the directory's contents."""
    out = []
    for name in os.listdir(pkg_dir):
        if not name.endswith(".py") or name == "__init__.py":
            continue
        if os.path.isfile(os.path.join(pkg_dir, name)):
            out.append(name[:-3])
    return sorted(out)


def defines_main(path):
    """True if the Python file at `path` defines a top-level `main()` — the signal for a console
    entry point (#200 req 3, 'console entry points where applicable'). A file that does not parse
    (python-2, truncated) simply has no entry point; it is never treated as an error here."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return False
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "main"
               for n in tree.body)


# ── the three scaffolding files ─────────────────────────────────────────────────────────────────
def render_pyproject(repo, stems_with_main):
    """The pyproject.toml text for a repo whose console-scripted modules are `stems_with_main`.
    A pure function of its inputs — this is what makes regeneration idempotent and additive."""
    pkg = import_pkg_name(repo)
    scripts = "".join('%s = "%s.%s:main"\n' % ("forge2-" + re.sub(r"[_.]+", "-", stem).lower(),
                                               pkg, stem)
                      for stem in stems_with_main)
    scripts_block = ("\n[project.scripts]\n" + scripts) if scripts else ""
    return (
        "# Installable package for the forge2 rewrite of the forge repo `%(repo)s`\n"
        "# (#200 req 3: a proper package — pyproject.toml, `pip install -e .` works, console\n"
        "# entry points where applicable). GENERATED by congruency/tools/forge_package.py (#410):\n"
        "# it is a pure function of the modules present, so adding a module regenerates this file as\n"
        "# a SUPERSET and never clobbers a sibling. Do not hand-edit — a rewrite unit writes ONLY its\n"
        "# own `%(pkg)s/<module>.py`; this scaffolding is derived.\n"
        "#\n"
        "# This directory IS the import package, so `package-dir` maps `%(pkg)s` onto '.'; setuptools\n"
        "# then includes EVERY .py here as a submodule, so imports need no per-module enumeration and\n"
        "# `from %(pkg)s.<module> import <name>` resolves for every module that lands.\n"
        "\n"
        "[build-system]\n"
        'requires = ["setuptools>=61.0"]\n'
        'build-backend = "setuptools.build_meta"\n'
        "\n"
        "[project]\n"
        'name = "%(dist)s"\n'
        'version = "1.0.0"\n'
        'description = "forge2 rewrite of the forge repo %(repo)s — behavior-preserving, installable, '
        'control-config\'d Python (refactor standard #200)"\n'
        'requires-python = ">=3.8"\n'
        "dependencies = []\n"
        "%(scripts)s"
        "\n"
        "[tool.setuptools]\n"
        'packages = ["%(pkg)s"]\n'
        "\n"
        "[tool.setuptools.package-dir]\n"
        '%(pkg)s = "."\n'
        "\n"
        "# The config registry ships WITH the package so a non-editable install can still see its\n"
        "# config object by walking up from the installed module.\n"
        "[tool.setuptools.package-data]\n"
        '%(pkg)s = ["registry.json"]\n'
        % {"repo": repo, "pkg": pkg, "dist": dist_name(repo), "scripts": scripts_block})


def render_init(repo):
    """A minimal __init__.py for a FRESH package: it hardcodes NO module list, so it never needs to
    change when a sibling module lands. `pip install -e .` + `from %(pkg)s.<module> import <name>`
    works for every module. Written only when no __init__.py exists — an existing one (which may
    re-export a module for convenience) is preserved, never clobbered."""
    return (
        '"""forge2 rewrite of the forge repo `%(repo)s` — behavior-preserving, installable,\n'
        "control-config'd Python, per the FORGE-wide refactor standard #200.\n"
        "\n"
        "This package is built one module at a time: each forge rewrite unit adds its OWN\n"
        "`<module>.py` here and NOTHING central (#410, the analogue of the tag-registry fix #281).\n"
        "This __init__ therefore hardcodes no module list — every module in this directory is\n"
        "importable directly, e.g. `from %(repo)s.<module> import <name>`, and a `pip install -e .`\n"
        "from this directory installs them all. A unit that wants a convenience re-export may add one\n"
        "here for its own symbol without disturbing a sibling's.\n"
        '"""\n'
        % {"repo": repo})


def render_registry_skeleton(repo):
    """A registry.json skeleton for a fresh package: the shared keys plus an empty section object for
    this repo, into which each module additively merges its own `forge2.<repo>.<module>` config."""
    return {
        "_comment": ("Configuration registry for the forge2 %s package. Registry-gated modules walk "
                     "UP from their own file to find this file and throw if they cannot see it. Each "
                     "module reads ONLY its own `forge2.%s.<module>` section; sections are disjoint "
                     "and added additively (see congruency/tools/forge_package.py, #410)."
                     % (repo, repo)),
        "schema": 1,
        "bug_reports": "logs/bug_reports.jsonl",
        "forge2": {repo: {}},
    }


# ── idempotent writes ─────────────────────────────────────────────────────────────────────────────
def _write_if_changed(path, text):
    """Write `text` to `path` only if it differs from what is there. Returns 'created', 'updated' or
    'unchanged' — so a converged package reports no work and re-running churns nothing."""
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            if fh.read() == text:
                return "unchanged"
        verb = "updated"
    else:
        verb = "created"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return verb


def merge_registry_section(pkg_dir, repo, module, section):
    """Additively set `forge2.<repo>.<module>` in the package's registry.json to `section`, WITHOUT
    reading or rewriting any sibling module's section. Creates the registry (skeleton) if absent.
    This is the helper a rewrite unit uses to register its own config — the additive analogue of a
    tag calling its own init() in #281. Returns 'created'/'updated'/'unchanged'."""
    path = os.path.join(pkg_dir, "registry.json")
    data = render_registry_skeleton(repo)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    data.setdefault("forge2", {}).setdefault(repo, {})[module] = section
    return _write_if_changed(path, json.dumps(data, indent=2) + "\n")


def ensure(pkg_dir, repo=None):
    """Make `pkg_dir`'s scaffolding additive and complete for the modules present. The one entry
    point pair_loop and the CLI both call. Returns a summary dict:
        {repo, import_pkg, dist, modules, scripts, pyproject, init, registry}
    where the last three are 'created'/'updated'/'unchanged'/'preserved'. Raises Fault on a target
    that is not a directory."""
    if not os.path.isdir(pkg_dir):
        raise Fault("not a package directory: %s" % pkg_dir)
    repo = repo or os.path.basename(os.path.normpath(pkg_dir))
    stems = module_stems(pkg_dir)
    scripted = [s for s in stems if defines_main(os.path.join(pkg_dir, s + ".py"))]

    pyproject = _write_if_changed(os.path.join(pkg_dir, "pyproject.toml"),
                                  render_pyproject(repo, scripted))

    init_path = os.path.join(pkg_dir, "__init__.py")
    if os.path.isfile(init_path):
        init = "preserved"                       # never clobber an existing __init__ (may re-export)
    else:
        init = _write_if_changed(init_path, render_init(repo))

    reg_path = os.path.join(pkg_dir, "registry.json")
    if os.path.isfile(reg_path):
        registry = "preserved"                   # never clobber existing config sections
    else:
        registry = _write_if_changed(reg_path, json.dumps(render_registry_skeleton(repo), indent=2) + "\n")

    return {"repo": repo, "import_pkg": import_pkg_name(repo), "dist": dist_name(repo),
            "modules": stems, "scripts": scripted,
            "pyproject": pyproject, "init": init, "registry": registry}


class Fault(Exception):
    """A precondition failure — reported as one line, exit 2."""


# ── CLI ───────────────────────────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Regenerate a forge2 package's additive scaffolding (#410). Writes only "
                    "pyproject.toml, and __init__.py/registry.json if absent; never clobbers a "
                    "sibling module or an existing config section.")
    ap.add_argument("pkg_dir", help="the forge2/<repo> package directory to scaffold")
    ap.add_argument("--repo", help="override the repo name (default: the directory basename)")
    args = ap.parse_args(argv)
    try:
        summary = ensure(args.pkg_dir, args.repo)
    except Fault as e:
        print("forge_package: %s" % e)
        return 2
    print("== forge_package == %s  (import as %s, dist %s)"
          % (summary["repo"], summary["import_pkg"], summary["dist"]))
    print("   modules : %s" % (", ".join(summary["modules"]) or "(none yet)"))
    print("   scripts : %s" % (", ".join("forge2-" + re.sub(r"[_.]+", "-", s).lower()
                                          for s in summary["scripts"]) or "(none)"))
    for f in ("pyproject", "init", "registry"):
        print("   %-10s: %s" % (f, summary[f]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
